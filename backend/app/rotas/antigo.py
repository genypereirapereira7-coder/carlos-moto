"""Sistema Antigo — consultar o que foi migrado e trazer os clientes.

PROVISÓRIO, irmão de `rotas/migracao.py`: sai quando a migração acabar.

O passo 1 (`migracao.py`) copiou o sistema antigo inteiro pro schema
`migracao`, como texto. Aqui é o passo 2, e só faz duas coisas:

  - **Mostrar** o que veio, tabela por tabela, pra consulta (só leitura).
  - **Trazer os clientes** pra tela de Clientes do Carlos Moto — com ensaio
    antes de gravar, pra ninguém escrever no banco às cegas.

O que não encaixa no Carlos Moto (venda de comida, nota fiscal, imposto) fica
só no espelho, pra consultar. Cliente é o que tem par direto: uma pessoa vira
um cadastro.
"""

import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.dependencias import SessaoDep, SoDono
from app.models.cliente import Cliente

rotas = APIRouter(prefix="/antigo", tags=["sistema-antigo"])

# Nome de tabela do espelho: letras, números e _ . É contra SQL injection —
# o nome vai cru na consulta (não dá pra passar identificador por parâmetro),
# então ou casa com isto, ou não roda.
_NOME_OK = re.compile(r"^temp_[a-z0-9_]+$")


def _tem_espelho(sessao) -> bool:
    """O schema `migracao` só existe no Postgres da nuvem. No SQLite do dev
    local ele não existe — e as telas do Sistema Antigo devem responder
    "nada migrado" em vez de estourar."""
    return sessao.bind.dialect.name == "postgresql"


async def _lote_mais_recente(sessao) -> int | None:
    if not _tem_espelho(sessao):
        return None
    linha = await sessao.execute(text(
        "SELECT id FROM migracao.lotes WHERE situacao IN ('CONCLUIDO','COM_ERROS') "
        "ORDER BY id DESC LIMIT 1"
    ))
    return linha.scalar()


@rotas.get("")
async def resumo(sessao: SessaoDep, _: SoDono):
    """As tabelas do sistema antigo que têm dados — do lote mais recente.

    As tabelas vazias e as de imposto/configuração ficam de fora do resumo:
    são 183 no total, e quase todas são enfeite fiscal que não interessa.
    """
    lote = await _lote_mais_recente(sessao)
    if lote is None:
        return {"lote": None, "tabelas": []}

    nomes = (await sessao.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='migracao' AND table_name LIKE 'temp\\_%' ESCAPE '\\' "
        "ORDER BY table_name"
    ))).scalars().all()

    tabelas = []
    for nome in nomes:
        if not _NOME_OK.match(nome):
            continue
        n = (await sessao.execute(text(
            f'SELECT count(*) FROM migracao."{nome}" WHERE _lote_id = :l'
        ), {"l": lote})).scalar()
        if n:
            tabelas.append({"nome": nome, "curto": nome.removeprefix("temp_"), "linhas": n})

    tabelas.sort(key=lambda t: t["linhas"], reverse=True)
    return {"lote": lote, "tabelas": tabelas}


@rotas.get("/tabela/{nome}")
async def ver_tabela(nome: str, sessao: SessaoDep, _: SoDono, limite: int = 200):
    """As linhas de uma tabela do espelho — pra consulta, com um teto de linhas."""
    if not _NOME_OK.match(nome):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nome de tabela inválido.")
    if not _tem_espelho(sessao):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa tabela não existe no espelho.")
    existe = (await sessao.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='migracao' AND table_name = :t"
    ), {"t": nome})).scalar()
    if not existe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa tabela não existe no espelho.")

    lote = await _lote_mais_recente(sessao)
    colunas = (await sessao.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='migracao' AND table_name = :t AND column_name NOT LIKE '\\_%' ESCAPE '\\' "
        "ORDER BY ordinal_position"
    ), {"t": nome})).scalars().all()

    limite = max(1, min(limite, 1000))
    linhas = (await sessao.execute(text(
        f'SELECT * FROM migracao."{nome}" WHERE _lote_id = :l ORDER BY _linha LIMIT :lim'
    ), {"l": lote, "lim": limite})).mappings().all()

    return {
        "tabela": nome,
        "colunas": colunas,
        "linhas": [[linha.get(c) for c in colunas] for linha in linhas],
        "total": (await sessao.execute(text(
            f'SELECT count(*) FROM migracao."{nome}" WHERE _lote_id = :l'
        ), {"l": lote})).scalar(),
    }


# ----------------------------------------------------- importar clientes

def _digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _cpf_fecha(numeros: str) -> bool:
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tam in (9, 10):
        soma = sum(int(numeros[i]) * (tam + 1 - i) for i in range(tam))
        d = (11 - soma % 11) % 11
        if (d if d < 10 else 0) != int(numeros[tam]):
            return False
    return True


def _preparar_cliente(linha: dict) -> tuple[dict | None, str | None]:
    """Uma linha de PESSOA vira um cliente, ou um motivo pra ter ficado de fora.

    Devolve ({nome, cpf, telefone}, None) quando dá, ou (None, "motivo")."""
    nome = (linha.get("razao") or linha.get("fantasia") or "").strip()
    if not nome:
        return None, "sem nome"

    cpf = _digitos(linha.get("cnpj"))
    if len(cpf) == 14:
        return None, f"{nome}: é empresa (CNPJ), e a tela de Clientes guarda só CPF"
    if len(cpf) != 11:
        return None, f"{nome}: sem CPF válido (veio {cpf!r})"

    # O primeiro telefone que existir, na ordem de quem mais usa WhatsApp.
    telefone = ""
    for campo in ("celular1", "whatsapp", "celular2", "fone1", "fone2"):
        t = _digitos(linha.get(campo))
        if 10 <= len(t) <= 11:
            telefone = t
            break

    aviso = None if _cpf_fecha(cpf) else "CPF não fecha a conta (importado assim mesmo)"
    return {"nome": nome[:120], "cpf": cpf, "telefone": telefone or None, "aviso": aviso}, None


class ImportarEntrada(BaseModel):
    # True = só mostra o que entraria, não grava. É o padrão de propósito:
    # ninguém escreve no banco sem ver antes.
    ensaio: bool = True


@rotas.post("/importar-clientes")
async def importar_clientes(dados: ImportarEntrada, sessao: SessaoDep, _: SoDono):
    """Traz as pessoas do sistema antigo (PESSOA) pra tela de Clientes.

    Com `ensaio=true` (padrão) só conta e mostra amostras — não grava nada.
    Com `ensaio=false` grava, e é idempotente: rodar de novo não duplica
    (o CPF é único; quem já existe é pulado).
    """
    if not _tem_espelho(sessao):
        raise HTTPException(status.HTTP_409_CONFLICT,
            "A importação só roda na nuvem, onde estão os dados migrados. Aqui no computador não há espelho.")
    lote = await _lote_mais_recente(sessao)
    if lote is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há dados migrados pra importar.")

    existe = (await sessao.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='migracao' AND table_name='temp_pessoa'"
    ))).scalar()
    if not existe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Não achei a tabela de pessoas (temp_pessoa) no espelho.")

    pessoas = (await sessao.execute(text(
        "SELECT * FROM migracao.temp_pessoa WHERE _lote_id = :l ORDER BY _linha"
    ), {"l": lote})).mappings().all()

    # CPFs que já estão no Carlos Moto — pra não duplicar.
    ja_no_sistema = set((await sessao.execute(text("SELECT cpf FROM cliente"))).scalars().all())

    a_criar: list[dict] = []
    pulados: list[str] = []
    ja_existiam = 0
    avisos: list[str] = []
    vistos: set[str] = set()

    for linha in pessoas:
        cliente, motivo = _preparar_cliente(dict(linha))
        if motivo:
            pulados.append(motivo)
            continue
        if cliente["cpf"] in ja_no_sistema or cliente["cpf"] in vistos:
            ja_existiam += 1
            continue
        vistos.add(cliente["cpf"])
        if cliente.pop("aviso"):
            avisos.append(f"{cliente['nome']}: CPF não fecha a conta")
        a_criar.append(cliente)

    if not dados.ensaio:
        for c in a_criar:
            sessao.add(Cliente(nome=c["nome"], cpf=c["cpf"], telefone=c["telefone"]))
        # Commit aqui, e não só na saída da dependência: assim a resposta
        # "criados N" já reflete o que está gravado, e a tela que recarrega os
        # clientes logo em seguida os encontra. O append-only grava o histórico
        # de cada cliente criado sozinho, no flush.
        await sessao.commit()

    return {
        "ensaio": dados.ensaio,
        "total_pessoas": len(pessoas),
        "criados" if not dados.ensaio else "criaria": len(a_criar),
        "ja_existiam": ja_existiam,
        "pulados": pulados,
        "avisos": avisos,
        "amostra": [{"nome": c["nome"], "cpf": c["cpf"], "telefone": c["telefone"]} for c in a_criar[:10]],
    }
