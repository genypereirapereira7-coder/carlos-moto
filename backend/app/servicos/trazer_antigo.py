"""Trazer o cadastro do sistema antigo pro sistema novo.

A aba Dados guarda o backup inteiro, em texto, do jeito que veio. Aqui é o
passo seguinte: virar **cliente de verdade** no Carlos Moto, com o que der pra
aproveitar de cada cadastro.

**Por que não passa pelos schemas do Pydantic:** eles existem pra proteger o
que o dono digita, e recusam o cadastro inteiro quando um campo está errado.
Dado de sistema antigo é sujo por natureza — 611 cadastros da Monte São Motos
têm nascimento `0001-01-01`, um tem UF `"R"`, 16 têm CPF que não fecha no
dígito verificador. Recusar a pessoa por causa do campo torto perderia o
cliente; então aqui cada campo é conferido sozinho, e **o campo ruim fica de
fora, não a pessoa**. O que sobrou fora é contado e devolvido, pra ninguém
descobrir depois que faltou algo.

**O que nunca acontece:** sobrescrever dado que o dono digitou. Cliente que já
existe (mesmo CPF) só recebe o que está em branco nele.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import hoje
from app.models.cliente import Cliente
from app.models.dado_antigo import LinhaAntiga
from app.schemas.validadores import validar_cpf, validar_email, validar_uf

log = logging.getLogger("carlosmoto.trazer_antigo")

# Estado civil no sistema antigo é código numérico. Descobri qual é "casado"
# cruzando com o campo do cônjuge: no código 1, 38% têm cônjuge preenchido; em
# todos os outros, entre 0% e 5%. O 0 é "não informado" (1.032 cadastros).
_CASADO = "1"
_NAO_INFORMADO = "0"

# Esses campos do sistema antigo são o cadastro de uma pessoa. O que não está
# aqui (limite de crédito, SPC, salário, referências, razão social) continua na
# aba Dados: não tem lugar no sistema novo e inventar coluna pra guardar o que
# ninguém usa seria remontar o ERP antigo aqui dentro.
_LIMITE_OBSERVACAO = 1000


@dataclass
class Pulado:
    """Cadastro que não virou cliente, e por quê — pra ele completar à mão."""

    codigo: str
    nome: str
    motivo: str


@dataclass
class ResultadoClientes:
    criados: int = 0
    completados: int = 0
    juntados: int = 0
    pulados: list[Pulado] = field(default_factory=list)
    # campo -> quantas vezes veio torto e ficou de fora
    descartados: dict[str, int] = field(default_factory=dict)

    def descartou(self, campo: str) -> None:
        self.descartados[campo] = self.descartados.get(campo, 0) + 1


def _digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _texto(valor: str | None, limite: int) -> str | None:
    limpo = (valor or "").strip()
    return limpo[:limite] if limpo else None


def _cpf_valido(digitos: str) -> bool:
    try:
        validar_cpf(digitos)
        return True
    except ValueError:
        return False


def _telefone(linha: dict) -> str | None:
    """Celular na frente do fixo: é por onde a loja fala com o cliente hoje."""
    for campo in ("celular", "fone"):
        d = _digitos(linha.get(campo))
        if len(d) in (10, 11):
            return d
    return None


def _nascimento(valor: str | None, r: ResultadoClientes) -> date | None:
    """`0001-01-01` é como o sistema antigo gravava data em branco — 611
    cadastros vieram assim, e um veio com ano 7197."""
    texto = (valor or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        return None
    try:
        d = date.fromisoformat(texto)
    except ValueError:
        r.descartou("nascimento")
        return None
    if d.year < 1900 or d > hoje():
        r.descartou("nascimento")
        return None
    return d


def _email(valor: str | None, r: ResultadoClientes) -> str | None:
    try:
        return validar_email(valor)
    except ValueError:
        r.descartou("email")
        return None


def _uf(valor: str | None, r: ResultadoClientes) -> str | None:
    try:
        return validar_uf(valor)
    except ValueError:
        r.descartou("uf")
        return None


def _cep(valor: str | None, r: ResultadoClientes) -> str | None:
    d = _digitos(valor)
    if not d:
        return None
    if len(d) != 8:
        r.descartou("cep")
        return None
    return d


def _numero(valor: str | None) -> str | None:
    """`0` é o que o sistema antigo põe quando não tem número — 481 cadastros.
    Guardar "0" como número da casa seria endereço errado no contrato."""
    limpo = (valor or "").strip()
    if limpo in ("", "0", "00", "000"):
        return None
    return limpo[:20]


def _observacao(linha: dict, notas: list[str]) -> str | None:
    """As anotações que a própria loja escreveu no sistema antigo, mais o que
    eu preciso avisar sobre este cadastro."""
    pedacos = [
        (linha.get("obs_venda") or "").strip(),
        (linha.get("historico") or "").strip(),
        *notas,
    ]
    junto = " · ".join(p for p in pedacos if p)
    return junto[:_LIMITE_OBSERVACAO] if junto else None


def traduzir(linha: dict, r: ResultadoClientes) -> tuple[dict | None, str | None]:
    """`(campos, motivo_do_pulo)` — um dos dois vem vazio."""
    nome = _texto(linha.get("nome"), 120)
    if not nome:
        return None, "sem nome"

    documento = _digitos(linha.get("cnpj_cpf"))
    if len(documento) == 14:
        return None, "é CNPJ (empresa), e o cadastro de cliente usa CPF"
    if len(documento) != 11:
        return None, "sem CPF" if not documento else f"CPF incompleto ({len(documento)} dígitos)"

    notas: list[str] = []
    if not _cpf_valido(documento):
        notas.append("CPF não fecha no dígito verificador — veio assim do sistema antigo, conferir")

    # Casado só quando o nome do cônjuge veio junto: marcar "casado" sem ter o
    # nome criaria cadastro que a própria tela considera incompleto, e o dono
    # ia bater nisso no dia em que fosse editar qualquer outra coisa.
    conjuge_nome = _texto(linha.get("conjuge"), 120)
    civil = (linha.get("est_civil") or "").strip()
    if conjuge_nome:
        casado: bool | None = True
    elif civil == _CASADO:
        casado = None
        notas.append("Sistema antigo: estado civil casado, mas sem o nome do cônjuge")
    elif civil and civil != _NAO_INFORMADO:
        casado = False
    else:
        casado = None

    fone_conjuge = _digitos(linha.get("fone_conj"))
    return {
        "nome": nome,
        "cpf": documento,
        "telefone": _telefone(linha),
        "rg": _texto(linha.get("insc_rg"), 20),
        "nascimento": _nascimento(linha.get("dtnasc"), r),
        "email": _email(linha.get("email"), r),
        "endereco": _texto(linha.get("endereco"), 160),
        "numero": _numero(linha.get("numero")),
        "complemento": _texto(linha.get("complemento"), 80),
        "bairro": _texto(linha.get("bairro"), 80),
        "cidade": _texto(linha.get("cidade"), 80),
        "uf": _uf(linha.get("estado"), r),
        "cep": _cep(linha.get("cep"), r),
        "casado": casado,
        "conjuge_nome": conjuge_nome if casado else None,
        "conjuge_telefone": (fone_conjuge if len(fone_conjuge) in (10, 11) else None) if casado else None,
        "observacao": _observacao(linha, notas),
    }, None


def _completar(cliente: Cliente, campos: dict) -> bool:
    """Preenche só o que está em branco. Devolve se mudou algo.

    Nunca sobrescreve: o que o dono digitou vale mais que o que veio do sistema
    antigo — ele digitou olhando o cliente na frente dele.
    """
    mudou = False
    for campo, valor in campos.items():
        if campo in ("cpf", "nome") or valor is None:
            continue
        if getattr(cliente, campo) in (None, ""):
            setattr(cliente, campo, valor)
            mudou = True
    return mudou


async def trazer_clientes(sessao: AsyncSession, lote_id: uuid.UUID) -> ResultadoClientes:
    """Cria (ou completa) um Cliente por cadastro da tabela `clientes` do lote."""
    r = ResultadoClientes()

    linhas = (
        await sessao.execute(
            select(LinhaAntiga.dados)
            .where(LinhaAntiga.lote_id == lote_id, LinhaAntiga.tabela == "clientes")
            .order_by(LinhaAntiga.numero_linha)
        )
    ).scalars().all()

    # Uma consulta só: com 1.782 cadastros, um `SELECT` por CPF seriam 1.782
    # idas ao banco.
    ja_existem = {
        c.cpf: c for c in (await sessao.execute(select(Cliente))).scalars().all()
    }
    novos_deste_lote: dict[str, Cliente] = {}

    for linha in linhas:
        campos, motivo = traduzir(linha, r)
        if campos is None:
            r.pulados.append(Pulado(
                codigo=(linha.get("codcli") or "").strip(),
                nome=(linha.get("nome") or "").strip()[:120],
                motivo=motivo or "não deu pra aproveitar",
            ))
            continue

        cpf = campos["cpf"]

        # Mesma pessoa duas vezes no arquivo (4 CPFs repetem): junta no cadastro
        # que já foi criado, em vez de estourar o índice único do CPF.
        if cpf in novos_deste_lote:
            _completar(novos_deste_lote[cpf], campos)
            r.juntados += 1
            continue

        existente = ja_existem.get(cpf)
        if existente is not None:
            if _completar(existente, campos):
                r.completados += 1
            continue

        cliente = Cliente(**campos)
        sessao.add(cliente)
        novos_deste_lote[cpf] = cliente
        r.criados += 1

    await sessao.flush()
    log.info(
        "trazer clientes: %d criados, %d completados, %d juntados, %d pulados",
        r.criados, r.completados, r.juntados, len(r.pulados),
    )
    return r
