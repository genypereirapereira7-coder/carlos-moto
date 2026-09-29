"""Trazer as parcelas do sistema antigo pra aba PARCELAS (histórico completo).

Uma parcela no sistema novo não vive sozinha: ela pendura numa venda, que
pendura numa moto e num cliente. Então trazer a dívida significa reconstruir a
corrente inteira a partir do que o backup tem:

    parcelas.nrped -> pedidos (a venda) -> it_pedid (a moto) -> clientes (quem deve)

**O que o backup tem e o que não tem.** As 455 parcelas da tabela `parcelas`
estão todas em aberto (as pagas ficam em `recebidas`, 10.954 delas). Só que o
item da venda **não tem campo de placa nem de marca**: os dois vivem soltos
dentro da descrição, escrita à mão pelo balcão — `BIZ 125 ES 2013 NDB1A23`. Daí
a leitura por padrão de texto aqui embaixo.

**O que entra.** Lê `parcelas` (em aberto) e `recebidas` (já pagas) pra
reconstruir o carnê inteiro de cada venda: a parcela paga entra quitada (com o
pagamento no valor cheio e `pago_em` marcado), a aberta entra devendo. Assim o
histórico fica no sistema novo, e não só o que ainda tem pra receber.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cliente import Cliente
from app.models.dado_antigo import LinhaAntiga
from app.models.moto import CondicaoMoto, Moto, StatusMoto
from app.models.pagamento_parcela import PagamentoParcela
from app.models.parcela import Parcela
from app.models.venda import FormaPagamento, Venda

log = logging.getLogger("carlosmoto.trazer_parcelas")

# Para o `uuid5` de cada venda importada ficar sempre o mesmo: é o que faz
# rodar duas vezes não criar a venda duas vezes.
_NAMESPACE = uuid.UUID("6f1b2c4e-8a3d-4f5b-9c7e-1d2a3b4c5d6e")

_PLACA_ANTIGA = re.compile(r"\b([A-Z]{3})[\s.-]?(\d{4})\b")
_PLACA_MERCOSUL = re.compile(r"\b([A-Z]{3}\d[A-Z]\d{2})\b")
# 196x a 204x: faixa de ano de moto que existe. Sem a faixa, o "150" de
# "BROS 150" e o "2013" de um telefone entrariam como ano.
_ANO = re.compile(r"\b(19[6-9]\d|20[0-4]\d)\b")

# A família do modelo diz a marca — é o que o balcão escreve. A mesma ideia do
# catálogo da tela de cadastro (`frontend/dono/dados-motos.js`), só com as
# famílias que aparecem no arquivo desta loja.
_MARCA_DA_FAMILIA = {
    "BIZ": "Honda", "POP": "Honda", "NXR": "Honda", "BROS": "Honda",
    "FAN": "Honda", "TITAN": "Honda", "CG": "Honda", "XRE": "Honda",
    "CB": "Honda", "PCX": "Honda", "LEAD": "Honda", "ELITE": "Honda",
    "TWISTER": "Honda", "HORNET": "Honda", "SHADOW": "Honda", "CRF": "Honda",
    "XR": "Honda", "HONDA": "Honda",
    "FACTOR": "Yamaha", "YBR": "Yamaha", "CRYPTON": "Yamaha",
    "FAZER": "Yamaha", "LANDER": "Yamaha", "TENERE": "Yamaha",
    "NEO": "Yamaha", "XTZ": "Yamaha", "YS": "Yamaha", "YAMAHA": "Yamaha",
    "SHINERAY": "Shineray", "DAFRA": "Dafra", "HAOJUE": "Haojue",
    "SUZUKI": "Suzuki", "BAJAJ": "Bajaj", "KAWASAKI": "Kawasaki",
    "TRAXX": "Traxx", "MOTTU": "Mottu", "KASINSKI": "Kasinski",
}


@dataclass
class VendaPulada:
    numero: str
    nome: str
    parcelas: int
    motivo: str


@dataclass
class ResultadoParcelas:
    motos: int = 0
    vendas: int = 0
    parcelas: int = 0
    centavos: int = 0
    puladas: list[VendaPulada] = field(default_factory=list)

    @property
    def parcelas_puladas(self) -> int:
        return sum(p.parcelas for p in self.puladas)


def _digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _centavos(valor: str | None) -> int:
    """`8500.00` -> 850000. `Decimal` e não `float`: dinheiro em float erra no
    arredondamento, e aqui o erro seria no saldo que o cliente deve."""
    texto = (valor or "").strip().replace(",", ".")
    if not texto:
        return 0
    try:
        return int((Decimal(texto) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return 0


def _data(valor: str | None) -> date | None:
    texto = (valor or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        return None
    try:
        d = date.fromisoformat(texto)
    except ValueError:
        return None
    # `0001-01-01` é o "vazio" do sistema antigo.
    return d if d.year >= 1900 else None


def achar_placa(texto: str) -> str | None:
    achado = _PLACA_MERCOSUL.search(texto)
    if achado:
        return achado.group(1)
    achado = _PLACA_ANTIGA.search(texto)
    if achado:
        return achado.group(1) + achado.group(2)
    return None


def achar_marca(texto: str) -> str | None:
    for palavra in re.findall(r"[A-Z]{2,}", texto):
        marca = _MARCA_DA_FAMILIA.get(palavra)
        if marca:
            return marca
    return None


def achar_ano(texto: str) -> int | None:
    """`BIZ 125 2010/2011` -> 2011: entre fabricação e modelo, o ano-modelo é o
    que vai no documento da moto."""
    anos = [int(a) for a in _ANO.findall(texto)]
    return max(anos) if anos else None


@dataclass
class MotoLida:
    marca: str
    modelo: str
    ano: int
    placa: str | None
    ano_era_do_pedido: bool


def ler_moto(descricao: str, ano_da_venda: int | None) -> MotoLida | None:
    """A moto que está escrita na descrição do item, ou `None` se não é moto.

    `None` é resposta legítima: entre os itens parcelados existe
    "TRANSFERENCIA DE NOME", que é serviço. Virar moto seria inventar veículo.
    """
    texto = (descricao or "").strip()
    if not texto:
        return None
    cru = texto.upper()
    marca = achar_marca(cru)
    if marca is None:
        return None

    ano = achar_ano(cru)
    ano_do_pedido = ano is None
    if ano is None:
        ano = ano_da_venda
    if ano is None:
        return None

    return MotoLida(
        marca=marca,
        # A descrição inteira como modelo: é o que o balcão escreveu, e jogar
        # fora pedaço dela perderia cilindrada, versão e o "R:" do Renavam.
        modelo=texto[:80],
        ano=ano,
        placa=achar_placa(cru),
        ano_era_do_pedido=ano_do_pedido,
    )


def _meio_dia_utc(dia: date) -> datetime:
    """Longe da meia-noite pra conversão de fuso não jogar a venda pro dia
    vizinho — mesma razão do `_momento_do_pagamento` em `servicos/parcelas.py`."""
    return datetime(dia.year, dia.month, dia.day, 15, tzinfo=UTC)


async def _linhas(sessao: AsyncSession, lote_id: uuid.UUID, tabela: str) -> list[dict]:
    return list((
        await sessao.execute(
            select(LinhaAntiga.dados)
            .where(LinhaAntiga.lote_id == lote_id, LinhaAntiga.tabela == tabela)
            .order_by(LinhaAntiga.numero_linha)
        )
    ).scalars().all())


async def trazer_parcelas(
    sessao: AsyncSession, lote_id: uuid.UUID, usuario_id: int
) -> ResultadoParcelas:
    """Reconstrói moto + venda + carnê do histórico completo de cada venda do
    sistema antigo — parcelas em aberto (`parcelas`) e já pagas (`recebidas`)."""
    r = ResultadoParcelas()

    antigas = await _linhas(sessao, lote_id, "parcelas")
    antigas += await _linhas(sessao, lote_id, "recebidas")
    pedidos = {(p.get("nrped") or "").strip(): p for p in await _linhas(sessao, lote_id, "pedidos")}
    itens: dict[str, list[dict]] = {}
    for item in await _linhas(sessao, lote_id, "it_pedid"):
        itens.setdefault((item.get("nrped") or "").strip(), []).append(item)
    # codcli do sistema antigo -> CPF, que é como o cliente foi importado.
    cpf_do_codigo = {
        (c.get("codcli") or "").strip(): _digitos(c.get("cnpj_cpf"))
        for c in await _linhas(sessao, lote_id, "clientes")
    }

    clientes = {c.cpf: c for c in (await sessao.execute(select(Cliente))).scalars().all()}
    placas_usadas = {
        p for p in (await sessao.execute(select(Moto.placa))).scalars().all() if p
    }
    vendas_existentes = set((await sessao.execute(select(Venda.id_cliente))).scalars().all())

    # Uma venda por pedido, com cada parcela uma única vez. A mesma parcela
    # pode aparecer nas duas tabelas — aberta em `parcelas` e paga em
    # `recebidas` (pagamento em pedaços). Nesse caso a paga é o estado final
    # e vence a duplicação.
    por_parcela: dict[tuple[str, str], dict] = {}
    for parcela in antigas:
        nrped = (parcela.get("nrped") or "").strip()
        pc = (parcela.get("pc") or "").strip()
        chave = (nrped, pc) if pc else (nrped, f"vazio-{len(por_parcela)}")
        atual = por_parcela.get(chave)
        if atual is None:
            por_parcela[chave] = parcela
        elif (
            _data(parcela.get("data_pagto")) is not None
            and _data(atual.get("data_pagto")) is None
        ):
            por_parcela[chave] = parcela

    por_pedido: dict[str, list[dict]] = {}
    for parcela in por_parcela.values():
        por_pedido.setdefault((parcela.get("nrped") or "").strip(), []).append(parcela)

    for numero, parcelas in sorted(por_pedido.items()):
        nome = (parcelas[0].get("nome") or "").strip()[:120]

        def pular(motivo: str) -> None:
            r.puladas.append(VendaPulada(numero, nome, len(parcelas), motivo))

        pedido = pedidos.get(numero)
        if pedido is None:
            pular("a venda não está no backup — só as parcelas dela")
            continue

        codcli = (parcelas[0].get("codcli") or pedido.get("codcli") or "").strip()
        cpf = cpf_do_codigo.get(codcli, "")
        cliente = clientes.get(cpf) if len(cpf) == 11 else None
        if cliente is None:
            pular("o cliente desta venda não entrou no sistema (sem CPF de 11 dígitos)")
            continue

        emissao = _data(pedido.get("emissao"))
        item = (itens.get(numero) or [{}])[0]
        moto_lida = ler_moto(item.get("descr_item") or "", emissao.year if emissao else None)
        if moto_lida is None:
            pular("o item da venda não é uma moto que eu consiga identificar")
            continue

        # Idempotência: o mesmo pedido gera sempre o mesmo `id_cliente`.
        id_venda = uuid.uuid5(_NAMESPACE, f"antigo:{lote_id}:{numero}")
        if id_venda in vendas_existentes:
            continue

        if moto_lida.placa and moto_lida.placa in placas_usadas:
            pular(f"a placa {moto_lida.placa} já está em outra moto do sistema")
            continue

        avisos = [f"Sistema antigo: venda nº {numero}."]
        if moto_lida.ano_era_do_pedido:
            avisos.append("O ano não constava no sistema antigo — usei o ano da venda, confira.")

        moto = Moto(
            marca=moto_lida.marca,
            modelo=moto_lida.modelo,
            ano=moto_lida.ano,
            placa=moto_lida.placa,
            km=0,
            condicao=CondicaoMoto.USADA,
            preco_centavos=_centavos(pedido.get("valor")),
            status=StatusMoto.VENDIDA,
            criado_por=usuario_id,
            data_compra=emissao,
            observacao=" ".join(avisos)[:1000],
        )
        sessao.add(moto)
        await sessao.flush()  # precisa do id pra pendurar a venda
        if moto_lida.placa:
            placas_usadas.add(moto_lida.placa)
        r.motos += 1

        venda = Venda(
            id_cliente=id_venda,
            moto_id=moto.id,
            vendedor_id=usuario_id,
            cliente_id=cliente.id,
            forma_pagamento=FormaPagamento.PARCELADO,
            preco_venda_centavos=_centavos(pedido.get("valor")),
            data_venda=_meio_dia_utc(emissao) if emissao else _meio_dia_utc(date.today()),
            observacao=f"Venda nº {numero} do sistema antigo.",
        )
        sessao.add(venda)
        await sessao.flush()
        vendas_existentes.add(id_venda)
        r.vendas += 1

        for antiga in parcelas:
            vencimento = _data(antiga.get("vencimento"))
            valor = _centavos(antiga.get("valor"))
            if vencimento is None or valor <= 0:
                continue
            # O número é o que a parcela tinha no carnê antigo: o cliente vê
            # "parcela 7 de 12" no papel que está com ele.
            try:
                numero_parcela = int(_digitos(antiga.get("pc")) or 0)
            except ValueError:
                numero_parcela = 0
            # `data_pagto` preenchida = parcela já recebida no sistema antigo.
            # Aí ela entra quitada: um pagamento no valor cheio, espelhado no
            # `pago_em` — igual ao fluxo normal de registrar pagamento.
            data_pgto = _data(antiga.get("data_pagto"))
            parcela = Parcela(
                venda_id=venda.id,
                numero=numero_parcela or (r.parcelas + 1),
                valor_centavos=valor,
                vencimento=vencimento,
                pagamentos=[],
            )
            if data_pgto:
                momento = _meio_dia_utc(data_pgto)
                parcela.pagamentos.append(PagamentoParcela(valor_centavos=valor, pago_em=momento))
                parcela.pago_em = momento
            sessao.add(parcela)
            r.parcelas += 1
            r.centavos += valor

    await sessao.flush()
    log.info(
        "trazer parcelas: %d motos, %d vendas, %d parcelas (R$ %.2f), %d puladas",
        r.motos, r.vendas, r.parcelas, r.centavos / 100, r.parcelas_puladas,
    )
    return r
