"""Totais de vendas por período e por vendedor, e resumo de estoque.

Diferente de uma sorveteria, moto não vende toda hora — não existe aqui o
ritual de "fechar o caixa do dia". Relatório é sempre uma soma ad-hoc sobre o
que já foi vendido num intervalo de datas, direto da tabela `Venda`.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FUSO_DA_LOJA
from app.models.moto import CondicaoMoto, Moto, StatusMoto
from app.models.usuario import Usuario
from app.models.venda import Venda
from app.schemas.relatorio import ResumoEstoque, ResumoPeriodo, VendaPorVendedor


def _intervalo_utc(data_inicio: date, data_fim: date) -> tuple[datetime, datetime]:
    """As duas pontas do período, no relógio da loja e convertidas pra UTC.

    Sem o fuso isto ficava errado por um dia inteiro nas pontas: uma venda às
    22h de 31/08 em Brasília já é 1º/09 em UTC, e sumia do relatório de
    agosto. É a mesma conta de `servicos/financeiro.py::_limites_utc` — este
    módulo é que tinha ficado pra trás.
    """
    inicio = datetime.combine(data_inicio, time.min, tzinfo=FUSO_DA_LOJA)
    fim = datetime.combine(data_fim + timedelta(days=1), time.min, tzinfo=FUSO_DA_LOJA)
    return inicio.astimezone(UTC), fim.astimezone(UTC)


async def resumo_periodo(
    sessao: AsyncSession, data_inicio: date, data_fim: date
) -> ResumoPeriodo:
    inicio, fim = _intervalo_utc(data_inicio, data_fim)
    consulta = select(
        func.count(Venda.id),
        func.coalesce(func.sum(Venda.preco_venda_centavos), 0),
    ).where(Venda.data_venda >= inicio, Venda.data_venda < fim)
    qtd, total = (await sessao.execute(consulta)).one()
    qtd, total = int(qtd), int(total)

    return ResumoPeriodo(
        data_inicio=data_inicio,
        data_fim=data_fim,
        qtd_vendas=qtd,
        total_centavos=total,
        # Arredondamento em inteiro: dividir em float dá 17999.999... num total
        # que fecha redondo.
        ticket_medio_centavos=(total + qtd // 2) // qtd if qtd else 0,
    )


async def por_vendedor(
    sessao: AsyncSession, data_inicio: date, data_fim: date
) -> list[VendaPorVendedor]:
    inicio, fim = _intervalo_utc(data_inicio, data_fim)
    consulta = (
        select(
            Venda.vendedor_id,
            Usuario.nome,
            func.count(Venda.id).label("qtd"),
            func.coalesce(func.sum(Venda.preco_venda_centavos), 0).label("total"),
        )
        .join(Usuario, Venda.vendedor_id == Usuario.id)
        .where(Venda.data_venda >= inicio, Venda.data_venda < fim)
        .group_by(Venda.vendedor_id, Usuario.nome)
        .order_by(func.sum(Venda.preco_venda_centavos).desc())
    )
    return [
        VendaPorVendedor(vendedor_id=vendedor_id, nome=nome, qtd_vendas=int(qtd), total_centavos=int(total))
        for vendedor_id, nome, qtd, total in (await sessao.execute(consulta)).all()
    ]


async def resumo_estoque(sessao: AsyncSession) -> ResumoEstoque:
    consulta = select(Moto.condicao, func.count(Moto.id), func.coalesce(func.sum(Moto.preco_centavos), 0)).where(
        Moto.status == StatusMoto.DISPONIVEL
    ).group_by(Moto.condicao)

    novas = usadas = 0
    valor_total = 0
    for condicao, qtd, valor in (await sessao.execute(consulta)).all():
        if condicao == CondicaoMoto.NOVA:
            novas = int(qtd)
        else:
            usadas = int(qtd)
        valor_total += int(valor)

    return ResumoEstoque(
        qtd_disponivel_novas=novas,
        qtd_disponivel_usadas=usadas,
        valor_total_centavos=valor_total,
    )
