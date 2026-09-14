"""Consulta e baixa de parcelas do crediário próprio da loja.

Esta tela só existe pra mostrar quem está devendo — por isso a única consulta
daqui já sai com cliente e moto grudados na parcela, em vez de a tela ter que
buscar os três em três chamadas separadas."""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FUSO_DA_LOJA, agora, como_utc, hoje
from app.models.cliente import Cliente
from app.models.moto import Moto
from app.models.parcela import Parcela
from app.models.venda import Venda


class ParcelaInexistente(Exception):
    pass


class PagamentoAntesDaVenda(Exception):
    """A data de pagamento informada é anterior à própria venda — a parcela
    nem existia ainda."""


async def listar_pendentes(sessao: AsyncSession) -> list[tuple[Parcela, Venda, Cliente, Moto]]:
    """Toda parcela ainda não paga (pendente ou atrasada), vencimento mais
    próximo primeiro."""
    consulta = (
        select(Parcela, Venda, Cliente, Moto)
        .join(Venda, Venda.id == Parcela.venda_id)
        .join(Cliente, Cliente.id == Venda.cliente_id)
        .join(Moto, Moto.id == Venda.moto_id)
        .where(Parcela.pago_em.is_(None))
        .order_by(Parcela.vencimento)
    )
    return list((await sessao.execute(consulta)).all())


def _momento_do_pagamento(dia: date | None) -> datetime:
    """Em branco ou hoje vira o instante de agora, com a hora certa. Um dia
    passado vira meio-dia daquele dia no fuso da loja: longe o bastante da
    meia-noite pra conversão nenhuma de fuso jogar o pagamento pro dia
    vizinho no fechamento do caixa. Gravado sempre em UTC, como todo o resto.
    """
    if dia is None or dia == hoje():
        return agora()
    return datetime.combine(dia, time(12), tzinfo=FUSO_DA_LOJA).astimezone(UTC)


async def marcar(
    sessao: AsyncSession,
    parcela_id: uuid.UUID,
    pago: bool,
    data_pagamento: date | None = None,
) -> Parcela:
    """Marca como paga (na data informada, ou hoje) — ou desmarca, quando foi
    engano. Remarcar uma parcela já paga troca a data: é assim que o dono
    corrige um pagamento lançado no dia errado."""
    parcela = await sessao.get(Parcela, parcela_id)
    if parcela is None:
        raise ParcelaInexistente()

    if not pago:
        parcela.pago_em = None
    else:
        momento = _momento_do_pagamento(data_pagamento)
        dia_da_venda = como_utc(parcela.venda.data_venda).astimezone(FUSO_DA_LOJA).date()
        if momento.astimezone(FUSO_DA_LOJA).date() < dia_da_venda:
            raise PagamentoAntesDaVenda()
        parcela.pago_em = momento

    await sessao.flush()
    return parcela
