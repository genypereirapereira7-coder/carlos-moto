"""Consulta e baixa de parcelas do crediário próprio da loja.

Esta tela só existe pra mostrar quem está devendo — por isso a única consulta
daqui já sai com cliente e moto grudados na parcela, em vez de a tela ter que
buscar os três em três chamadas separadas."""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FUSO_DA_LOJA, agora, como_utc, hoje
from app.models.cliente import Cliente
from app.models.moto import Moto
from app.models.pagamento_parcela import PagamentoParcela
from app.models.parcela import Parcela
from app.models.venda import Venda


class ParcelaInexistente(Exception):
    pass


class PagamentoAntesDaVenda(Exception):
    """A data de pagamento informada é anterior à própria venda — a parcela
    nem existia ainda."""


class PagamentoInvalido(Exception):
    """O valor do pagamento não cabe: passa do que ainda falta, ou a parcela
    já está quitada."""


def pago_por_parcela():
    """Subconsulta: quanto já entrou em cada parcela.

    Existe porque "quanto o cliente deve" não é a soma do valor das parcelas
    em aberto — é a soma do que **falta** nelas. Sem descontar o que já foi
    pago em pedaços, quem pagou metade de uma parcela de R$ 300 aparece
    devendo os R$ 300, e o "a receber" do financeiro fica inflado.
    """
    return (
        select(
            PagamentoParcela.parcela_id.label("parcela_id"),
            func.coalesce(func.sum(PagamentoParcela.valor_centavos), 0).label("pago"),
        )
        .group_by(PagamentoParcela.parcela_id)
        .subquery()
    )


def saldo_da_parcela(pago_sub):
    """Expressão SQL do que falta numa parcela: valor menos o já pago."""
    return Parcela.valor_centavos - func.coalesce(pago_sub.c.pago, 0)


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


def _nao_antes_da_venda(parcela: Parcela, momento: datetime) -> None:
    dia_da_venda = como_utc(parcela.venda.data_venda).astimezone(FUSO_DA_LOJA).date()
    if momento.astimezone(FUSO_DA_LOJA).date() < dia_da_venda:
        raise PagamentoAntesDaVenda()


async def registrar_pagamento(
    sessao: AsyncSession,
    parcela_id: uuid.UUID,
    valor_centavos: int,
    data_pagamento: date | None = None,
) -> Parcela:
    """Lança um pagamento em pedaço: o cliente pagou `valor_centavos` da
    parcela. Não pode passar do que ainda falta. Quando o pagamento zera o
    saldo, a parcela fica quitada (`pago_em` marca esse instante); enquanto
    sobrar saldo, ela continua aberta com o valor abatido."""
    parcela = await sessao.get(Parcela, parcela_id)
    if parcela is None:
        raise ParcelaInexistente()
    if valor_centavos <= 0 or valor_centavos > parcela.saldo_centavos:
        raise PagamentoInvalido()

    momento = _momento_do_pagamento(data_pagamento)
    _nao_antes_da_venda(parcela, momento)

    parcela.pagamentos.append(PagamentoParcela(valor_centavos=valor_centavos, pago_em=momento))
    # `pago_em` da parcela é o espelho rápido de "quitada?": vira o instante do
    # pagamento que fechou a conta, e só quando ela realmente fecha. É o que a
    # lista de pendentes e o histórico leem. Mantido aqui, num lugar só, junto
    # com o pagamento — pra nunca discordar do extrato.
    await sessao.flush()
    if parcela.saldo_centavos == 0:
        parcela.pago_em = momento
    await sessao.flush()
    return parcela


async def marcar(
    sessao: AsyncSession,
    parcela_id: uuid.UUID,
    pago: bool,
    data_pagamento: date | None = None,
) -> Parcela:
    """Quita a parcela inteira (na data informada, ou hoje) — ou desfaz, quando
    foi engano. Quitar paga de uma vez tudo o que ainda falta; desfazer estorna
    o que já tinha sido pago e reabre a parcela. O estorno é uma linha negativa
    no extrato, não um apagão — o sistema não apaga nada."""
    parcela = await sessao.get(Parcela, parcela_id)
    if parcela is None:
        raise ParcelaInexistente()

    if not pago:
        # Reabre: estorna o que estava pago (linha negativa) e limpa o espelho.
        pago_ate_agora = parcela.total_pago_centavos
        if pago_ate_agora > 0:
            parcela.pagamentos.append(
                PagamentoParcela(valor_centavos=-pago_ate_agora, pago_em=agora())
            )
        parcela.pago_em = None
        await sessao.flush()
        return parcela

    momento = _momento_do_pagamento(data_pagamento)
    _nao_antes_da_venda(parcela, momento)

    # Quita o que falta de uma vez. Parcela já quitada é no-op — só reafirma a
    # data, que é como o dono corrige um pagamento lançado no dia errado.
    falta = parcela.saldo_centavos
    if falta > 0:
        parcela.pagamentos.append(PagamentoParcela(valor_centavos=falta, pago_em=momento))
    parcela.pago_em = momento
    await sessao.flush()
    return parcela
