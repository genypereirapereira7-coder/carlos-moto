"""Painel financeiro do dono: quanto entrou, quanto saiu, quanto falta entrar.

**"Entrou no caixa" não é o mesmo que "vendeu".** Uma venda parcelada de
R$ 3.000 em 10x não põe R$ 3.000 no caixa no dia da venda — põe a entrada (se
houve) naquele dia, e cada parcela no dia em que for paga. Financiado por
banco e consórcio pagam a loja inteira na hora, então contam como à vista.

**Tudo sai de uma lista só de movimentos.** O resumo do mês, o dia a dia e o
dia avulso são somas da mesma lista: se cada número viesse de uma consulta
separada, cedo ou tarde o total do mês deixaria de bater com a soma dos dias,
e o dono passaria a desconfiar de todos.

**O dia é o da loja.** O banco guarda instantes em UTC, e uma venda às 22h do
dia 31 em Brasília já é dia 1º em UTC. Os limites de cada dia são calculados
no fuso da loja e só depois convertidos pra UTC na consulta.

**Dois lucros, porque respondem perguntas diferentes.** O "lucro do mês" é de
caixa — entrou menos o que saiu comprando e arrumando moto —, a pergunta de
fim de mês ("sobrou dinheiro?"). O "lucro nas motos vendidas" soma, pra cada
moto vendida no mês, venda − compra − gastos. Num mês em que a loja comprou
muito estoque o primeiro fica negativo mesmo com as vendas dando lucro, e sem
o segundo o dono não teria como enxergar isso.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import FUSO_DA_LOJA, como_utc
from app.models.despesa import DespesaMoto
from app.models.moto import Moto
from app.models.pagamento_parcela import PagamentoParcela
from app.models.parcela import Parcela
from app.models.venda import COM_CARNE, FormaPagamento, Venda
from app.servicos.parcelas import pago_por_parcela, saldo_da_parcela
from app.schemas.financeiro import (
    DiaFinanceiro,
    FinanceiroMes,
    Movimento,
    MovimentoDiario,
    TipoMovimento,
)

# Dentro de um dia: primeiro o que entrou (venda, parcela), depois o que saiu.
_ORDEM = {
    TipoMovimento.VENDA: 0,
    TipoMovimento.PARCELA: 1,
    TipoMovimento.COMPRA: 2,
    TipoMovimento.GASTO: 3,
}

_FORMA = {
    FormaPagamento.A_VISTA: "à vista",
    FormaPagamento.FINANCIADO: "financiada",
    FormaPagamento.CONSORCIO: "por consórcio",
    FormaPagamento.CARTAO: "no cartão",
}


@dataclass
class _Periodo:
    """Tudo que mexeu no caixa num intervalo de dias, carregado uma vez só."""

    vendas: list[Venda]
    pagamentos: list[PagamentoParcela]
    compras: list[Moto]
    gastos: list[DespesaMoto]


def _limites_do_mes(ano: int, mes: int) -> tuple[date, date]:
    primeiro = date(ano, mes, 1)
    ultimo = date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)
    return primeiro, ultimo


def _limites_utc(primeiro: date, ultimo: date) -> tuple[datetime, datetime]:
    """Da meia-noite do primeiro dia à meia-noite do dia seguinte ao último,
    no relógio da loja, convertidos pra UTC — que é como o banco guarda."""
    inicio = datetime.combine(primeiro, time.min, tzinfo=FUSO_DA_LOJA)
    fim = datetime.combine(ultimo + timedelta(days=1), time.min, tzinfo=FUSO_DA_LOJA)
    return inicio.astimezone(UTC), fim.astimezone(UTC)


def _dia_da_loja(instante: datetime) -> date:
    return como_utc(instante).astimezone(FUSO_DA_LOJA).date()


def _nome_moto(moto: Moto) -> str:
    nome = f"{moto.marca} {moto.modelo}".strip()
    return f"{nome} ({moto.placa})" if moto.placa else nome


async def _carregar(sessao: AsyncSession, primeiro: date, ultimo: date) -> _Periodo:
    inicio, fim = _limites_utc(primeiro, ultimo)

    # O que cada consulta carrega junto está escrito na mão de propósito. As
    # relações são `lazy="selectin"`, mas `Parcela.venda` e `Venda.parcelas`
    # apontam uma pra outra: o carregamento automático para no ciclo e deixa
    # `venda.parcelas` sem carregar. Numa parcela paga em setembro de uma
    # venda de janeiro a venda só é alcançada pela parcela, e montar a
    # descrição ("Parcela 1 de 6") ia buscar no banco no meio da montagem —
    # que no modo assíncrono não é lentidão, é erro: a tela inteira quebrava.
    vendas = await sessao.execute(
        select(Venda)
        .options(
            selectinload(Venda.parcelas),
            selectinload(Venda.cliente),
            selectinload(Venda.moto).selectinload(Moto.despesas),
        )
        .where(Venda.data_venda >= inicio, Venda.data_venda < fim)
    )
    # Cada pagamento em pedaço entra no caixa pelo próprio dia e valor — por
    # isso a consulta é dos pagamentos, não das parcelas. Uma parcela paga de
    # uma vez vira um pagamento só, do valor cheio, no dia; o total bate igual.
    pagamentos = await sessao.execute(
        select(PagamentoParcela)
        .options(
            selectinload(PagamentoParcela.parcela).selectinload(Parcela.venda).selectinload(Venda.parcelas),
            selectinload(PagamentoParcela.parcela).selectinload(Parcela.venda).selectinload(Venda.cliente),
            selectinload(PagamentoParcela.parcela).selectinload(Parcela.venda).selectinload(Venda.moto),
        )
        .where(PagamentoParcela.pago_em >= inicio, PagamentoParcela.pago_em < fim)
    )
    # Compra e gasto são datas puras — já são o dia da loja, sem conversão.
    compras = await sessao.execute(
        select(Moto).where(
            Moto.data_compra >= primeiro,
            Moto.data_compra <= ultimo,
            Moto.valor_compra_centavos.is_not(None),
        )
    )
    # `DespesaMoto.moto` não é carregada junto por padrão, e o nome da moto
    # vai na descrição: sem o `selectinload` seria um lazy-load por gasto —
    # que no modo assíncrono nem é permitido.
    gastos = await sessao.execute(
        select(DespesaMoto)
        .options(selectinload(DespesaMoto.moto))
        .where(DespesaMoto.data >= primeiro, DespesaMoto.data <= ultimo)
    )
    return _Periodo(
        vendas=list(vendas.scalars()),
        pagamentos=list(pagamentos.scalars()),
        compras=list(compras.scalars()),
        gastos=list(gastos.scalars()),
    )


def _entrada_da_venda(venda: Venda) -> int:
    """O que a venda pôs no caixa no dia dela. Com carnê: só a entrada — o
    resto chega parcela por parcela.

    Lê o campo gravado em vez de `preço − soma das parcelas`: com juros no
    carnê as parcelas somam mais que o saldo financiado, e aquela subtração
    daria entrada negativa.
    """
    if venda.forma_pagamento in COM_CARNE:
        return venda.valor_entrada_centavos
    return venda.preco_venda_centavos


def _movimentos(periodo: _Periodo) -> list[Movimento]:
    lista: list[Movimento] = []

    for venda in periodo.vendas:
        entrada = _entrada_da_venda(venda)
        if venda.forma_pagamento in COM_CARNE:
            carne = "no cheque" if venda.forma_pagamento == FormaPagamento.CHEQUE else "parcelada"
            tipo_de_venda = f"{carne}, entrada" if entrada else f"{carne}, sem entrada"
        else:
            tipo_de_venda = _FORMA[venda.forma_pagamento]
        lista.append(Movimento(
            dia=_dia_da_loja(venda.data_venda),
            tipo=TipoMovimento.VENDA,
            descricao=f"Venda {tipo_de_venda} — {_nome_moto(venda.moto)} para {venda.cliente.nome}",
            entrada_centavos=entrada,
            saida_centavos=0,
        ))

    for pagamento in periodo.pagamentos:
        parcela = pagamento.parcela
        venda = parcela.venda
        estorno = pagamento.valor_centavos < 0
        valor = abs(pagamento.valor_centavos)
        rotulo = "Estorno de parcela" if estorno else "Parcela"
        lista.append(Movimento(
            dia=_dia_da_loja(pagamento.pago_em),
            tipo=TipoMovimento.PARCELA,
            descricao=(
                f"{rotulo} {parcela.numero} de {len(venda.parcelas)} — "
                f"{venda.cliente.nome} · {_nome_moto(venda.moto)}"
            ),
            # Estorno é dinheiro saindo do caixa daquele dia — desconta em vez
            # de somar, e o saldo do dia continua certo.
            entrada_centavos=0 if estorno else valor,
            saida_centavos=valor if estorno else 0,
        ))

    for moto in periodo.compras:
        fornecedor = moto.fornecedor.nome if moto.fornecedor else moto.fornecedor_nome
        lista.append(Movimento(
            dia=moto.data_compra,
            tipo=TipoMovimento.COMPRA,
            descricao=f"Compra de moto — {_nome_moto(moto)}" + (f" de {fornecedor}" if fornecedor else ""),
            entrada_centavos=0,
            saida_centavos=moto.valor_compra_centavos,
        ))

    for gasto in periodo.gastos:
        lista.append(Movimento(
            dia=gasto.data,
            tipo=TipoMovimento.GASTO,
            descricao=f"{gasto.descricao} — {_nome_moto(gasto.moto)}",
            entrada_centavos=0,
            saida_centavos=gasto.valor_centavos,
        ))

    lista.sort(key=lambda m: (m.dia, _ORDEM[m.tipo]))
    return lista


def _dias(movimentos: list[Movimento]) -> list[DiaFinanceiro]:
    """Só os dias que tiveram movimento, do mais recente pro mais antigo."""
    por_dia: dict[date, list[Movimento]] = {}
    for movimento in movimentos:
        por_dia.setdefault(movimento.dia, []).append(movimento)

    dias = []
    for dia in sorted(por_dia, reverse=True):
        do_dia = por_dia[dia]
        entrou = sum(m.entrada_centavos for m in do_dia)
        saiu = sum(m.saida_centavos for m in do_dia)
        dias.append(DiaFinanceiro(
            dia=dia,
            entrou_centavos=entrou,
            saiu_centavos=saiu,
            saldo_centavos=entrou - saiu,
            movimentos=do_dia,
        ))
    return dias


def _lucro_nas_vendas(vendas: list[Venda]) -> tuple[int, int]:
    """(lucro, quantas vendas ficaram de fora por não ter valor de compra)."""
    lucro = 0
    sem_custo = 0
    for venda in vendas:
        moto = venda.moto
        if moto.valor_compra_centavos is None:
            sem_custo += 1
            continue
        gastos = sum(d.valor_centavos for d in moto.despesas)
        lucro += venda.preco_venda_centavos - moto.valor_compra_centavos - gastos
    return lucro, sem_custo


async def _a_receber(sessao: AsyncSession) -> int:
    """Quanto ainda falta entrar de todo o carnê da loja.

    O que **falta** em cada parcela, não o valor cheio dela: parcela paga pela
    metade tem só metade a receber. Sem isto o número do painel fica inflado
    exatamente no valor que os clientes já adiantaram.
    """
    pago = pago_por_parcela()
    consulta = (
        select(func.coalesce(func.sum(saldo_da_parcela(pago)), 0))
        .select_from(Parcela)
        .outerjoin(pago, pago.c.parcela_id == Parcela.id)
        .where(Parcela.pago_em.is_(None))
    )
    return int((await sessao.execute(consulta)).scalar_one())


async def do_mes(sessao: AsyncSession, ano: int, mes: int) -> FinanceiroMes:
    primeiro, ultimo = _limites_do_mes(ano, mes)
    periodo = await _carregar(sessao, primeiro, ultimo)
    movimentos = _movimentos(periodo)

    entrou = sum(m.entrada_centavos for m in movimentos)
    compras = sum(m.saida_centavos for m in movimentos if m.tipo == TipoMovimento.COMPRA)
    arrumacao = sum(m.saida_centavos for m in movimentos if m.tipo == TipoMovimento.GASTO)
    lucro_vendas, sem_custo = _lucro_nas_vendas(periodo.vendas)

    return FinanceiroMes(
        ano=ano,
        mes=mes,
        entrou_centavos=entrou,
        gasto_compra_motos_centavos=compras,
        gasto_arrumacao_centavos=arrumacao,
        a_receber_centavos=await _a_receber(sessao),
        lucro_centavos=entrou - compras - arrumacao,
        qtd_vendas=len(periodo.vendas),
        qtd_motos_compradas=len(periodo.compras),
        # Conta os recebimentos (pagamentos positivos) do período — estorno não
        # é recebimento. Parcela quitada de uma vez é um recebimento só.
        qtd_parcelas_recebidas=sum(1 for p in periodo.pagamentos if p.valor_centavos > 0),
        lucro_vendas_centavos=lucro_vendas,
        qtd_vendas_sem_custo=sem_custo,
        dias=_dias(movimentos),
    )


async def resumo_mes(sessao: AsyncSession, ano: int, mes: int) -> FinanceiroMes:
    """O mesmo cálculo de `do_mes` — a rota de resumo só não devolve os dias."""
    return await do_mes(sessao, ano, mes)


async def movimento_diario(sessao: AsyncSession, dia: date) -> MovimentoDiario:
    periodo = await _carregar(sessao, dia, dia)
    movimentos = _movimentos(periodo)
    return MovimentoDiario(
        dia=dia,
        entrou_centavos=sum(m.entrada_centavos for m in movimentos),
        gasto_centavos=sum(m.saida_centavos for m in movimentos),
        qtd_vendas=len(periodo.vendas),
        qtd_compras=len(periodo.compras),
    )
