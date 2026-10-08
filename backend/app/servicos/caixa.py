"""Entrada e saída de dinheiro lançadas à mão, e o fechamento do dia.

O financeiro responde "como foi o mês". Isto responde outra pergunta, a que o
dono faz todo fim de tarde: **quanto tem que estar na gaveta agora**. Por isso
o caixa do dia começa do zero toda manhã — ele não é um saldo que se acumula,
é o movimento daquele dia.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FUSO_DA_LOJA, agora, hoje
from app.models.caixa import MovimentoCaixa, TipoCaixa
from app.schemas.caixa import CaixaDoDia, LinhaDeCaixa


class MovimentoInexistente(Exception):
    pass


class JaEstornado(Exception):
    """Estornar duas vezes devolveria o dinheiro duas vezes na conta."""


def _momento(dia: date | None) -> datetime:
    """Em branco ou hoje = agora. Dia passado = meio-dia daquele dia no fuso
    da loja, longe o bastante da meia-noite pra conversão de fuso não jogar o
    lançamento pro dia vizinho. Mesma regra do pagamento de parcela."""
    if dia is None or dia == hoje():
        return agora()
    return datetime.combine(dia, time(12), tzinfo=FUSO_DA_LOJA).astimezone(UTC)


async def registrar(
    sessao: AsyncSession,
    *,
    tipo: TipoCaixa,
    valor_centavos: int,
    descricao: str,
    usuario_id: int,
    dia: date | None = None,
) -> MovimentoCaixa:
    movimento = MovimentoCaixa(
        tipo=tipo,
        valor_centavos=valor_centavos,
        descricao=descricao.strip(),
        ocorrido_em=_momento(dia),
        criado_por=usuario_id,
    )
    sessao.add(movimento)
    await sessao.flush()
    # Carrega o autor agora, de propósito: o objeto acabou de nascer nesta
    # sessão e nunca passou por um `select`, então ler `movimento.autor` na
    # montagem da resposta seria uma ida ao banco fora de hora — que no modo
    # assíncrono não é lentidão, é erro (`MissingGreenlet`).
    await sessao.refresh(movimento, ["autor"])
    return movimento


async def estornar(
    sessao: AsyncSession, movimento_id: uuid.UUID, motivo: str | None = None
) -> MovimentoCaixa:
    """Desfaz um lançamento. Ele sai da conta e fica no histórico marcado —
    o sistema não apaga nada, e um lançamento que some sem rastro é a coisa
    que faz o dono desconfiar do caixa inteiro."""
    movimento = await sessao.get(MovimentoCaixa, movimento_id)
    if movimento is None:
        raise MovimentoInexistente()
    if movimento.estornado_em is not None:
        raise JaEstornado()

    movimento.estornado_em = agora()
    movimento.motivo_estorno = (motivo or "").strip() or None
    await sessao.flush()
    await sessao.refresh(movimento, ["autor"])
    return movimento


@dataclass
class _Limites:
    inicio: datetime
    fim: datetime


def _dia_da_loja(dia: date) -> _Limites:
    comeco = datetime.combine(dia, time.min, tzinfo=FUSO_DA_LOJA)
    return _Limites(
        inicio=comeco.astimezone(UTC),
        fim=datetime.combine(dia, time.max, tzinfo=FUSO_DA_LOJA).astimezone(UTC),
    )


async def listar(
    sessao: AsyncSession, *, de: date | None = None, ate: date | None = None
) -> list[MovimentoCaixa]:
    """Os lançamentos do período, mais recente primeiro. **Inclui os
    estornados** — aqui é o histórico, e é onde o dono vai procurar o
    lançamento errado que ele desfez semana passada."""
    consulta = select(MovimentoCaixa).order_by(MovimentoCaixa.ocorrido_em.desc())
    if de is not None:
        consulta = consulta.where(MovimentoCaixa.ocorrido_em >= _dia_da_loja(de).inicio)
    if ate is not None:
        consulta = consulta.where(MovimentoCaixa.ocorrido_em <= _dia_da_loja(ate).fim)
    return list((await sessao.execute(consulta)).scalars())


async def do_dia(sessao: AsyncSession, dia: date) -> CaixaDoDia:
    """O fechamento de um dia: tudo que mexeu no caixa, na ordem.

    Reaproveita o motor do financeiro de propósito. Se o caixa do dia somasse
    por conta própria, mais cedo ou mais tarde ele diria um número e o
    financeiro do mês diria outro — e aí o dono para de confiar nos dois.
    """
    from app.servicos import financeiro

    periodo = await financeiro._carregar(sessao, dia, dia)
    movimentos = financeiro._movimentos(periodo)

    linhas = [
        LinhaDeCaixa(
            tipo=movimento.tipo.value,
            descricao=movimento.descricao,
            entrada_centavos=movimento.entrada_centavos,
            saida_centavos=movimento.saida_centavos,
            # Só lançamento à mão traz id: é o único que se estorna daqui. O
            # resto se desfaz onde nasceu — na parcela ou na venda.
            movimento_id=movimento.origem_id,
        )
        for movimento in movimentos
    ]

    entrou = sum(l.entrada_centavos for l in linhas)
    saiu = sum(l.saida_centavos for l in linhas)
    return CaixaDoDia(
        dia=dia,
        entrou_centavos=entrou,
        saiu_centavos=saiu,
        saldo_centavos=entrou - saiu,
        movimentos=linhas,
    )
