"""Cadastro e consulta de clientes — quem compra da loja e quem vende pra ela."""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import hoje
from app.models.cliente import Cliente
from app.models.moto import Moto
from app.models.parcela import Parcela
from app.models.venda import Venda
from app.schemas.cliente import ClienteEntrada


class CpfDuplicado(Exception):
    pass


class ClienteInexistente(Exception):
    pass


@dataclass(frozen=True)
class ResumoDoCliente:
    """Uma linha da lista de clientes, com o que a tela precisa pra pintar de
    vermelho e pra filtrar por "comprou"/"vendeu" sem abrir cada cadastro."""

    cliente: Cliente
    saldo_devedor_centavos: int
    saldo_atrasado_centavos: int
    qtd_comprou: int
    qtd_vendeu: int

    @property
    def deve_parcela(self) -> bool:
        return self.saldo_devedor_centavos > 0


def _so_digitos(valor: str) -> str:
    return "".join(c for c in valor if c.isdigit())


async def criar(sessao: AsyncSession, dados: ClienteEntrada) -> Cliente:
    cliente = Cliente(nome=dados.nome, cpf=dados.cpf, telefone=dados.telefone)
    sessao.add(cliente)
    try:
        await sessao.flush()
    except IntegrityError as erro:
        raise CpfDuplicado() from erro
    return cliente


async def editar(sessao: AsyncSession, cliente: Cliente, campos: dict) -> Cliente:
    for campo, valor in campos.items():
        setattr(cliente, campo, valor)
    await sessao.flush()
    return cliente


# ------------------------------------------------------------- agregações
#
# Uma consulta por total, pra lista inteira — nunca uma por cliente: a tela mostra
# dezenas de linhas de uma vez, e uma consulta por linha derrubaria a lista
# assim que a carteira de clientes crescesse.


async def _saldo_por_cliente(sessao: AsyncSession, ids: list[int]) -> dict[int, int]:
    consulta = (
        select(Venda.cliente_id, func.coalesce(func.sum(Parcela.valor_centavos), 0))
        .join(Parcela, Parcela.venda_id == Venda.id)
        .where(Parcela.pago_em.is_(None), Venda.cliente_id.in_(ids))
        .group_by(Venda.cliente_id)
    )
    return {cid: int(total) for cid, total in (await sessao.execute(consulta)).all()}


async def _saldo_atrasado_por_cliente(sessao: AsyncSession, ids: list[int]) -> dict[int, int]:
    """Só as parcelas que já passaram do vencimento, no dia da loja."""
    consulta = (
        select(Venda.cliente_id, func.coalesce(func.sum(Parcela.valor_centavos), 0))
        .join(Parcela, Parcela.venda_id == Venda.id)
        .where(
            Parcela.pago_em.is_(None),
            Parcela.vencimento < hoje(),
            Venda.cliente_id.in_(ids),
        )
        .group_by(Venda.cliente_id)
    )
    return {cid: int(total) for cid, total in (await sessao.execute(consulta)).all()}


async def _qtd_comprou_por_cliente(sessao: AsyncSession, ids: list[int]) -> dict[int, int]:
    """Quantas motos cada cliente comprou **da** loja."""
    consulta = (
        select(Venda.cliente_id, func.count(Venda.id))
        .where(Venda.cliente_id.in_(ids))
        .group_by(Venda.cliente_id)
    )
    return {cid: int(qtd) for cid, qtd in (await sessao.execute(consulta)).all()}


async def _qtd_vendeu_por_cliente(sessao: AsyncSession, ids: list[int]) -> dict[int, int]:
    """Quantas motos cada cliente vendeu **pra** loja."""
    consulta = (
        select(Moto.fornecedor_cliente_id, func.count(Moto.id))
        .where(Moto.fornecedor_cliente_id.in_(ids))
        .group_by(Moto.fornecedor_cliente_id)
    )
    return {cid: int(qtd) for cid, qtd in (await sessao.execute(consulta)).all()}


# ---------------------------------------------------------------- consultas


async def listar(sessao: AsyncSession, *, busca: str | None = None) -> list[ResumoDoCliente]:
    """Clientes em ordem alfabética, já com saldo devedor e contagens.

    A busca aceita nome (parcial, sem diferenciar caixa) ou CPF (com ou sem
    pontuação — só os dígitos importam): a tela tem um campo só, e quem
    decide o que a pessoa quis dizer é aqui."""
    consulta = select(Cliente).order_by(Cliente.nome)
    if busca:
        digitos = _so_digitos(busca)
        if digitos and len(digitos) >= 3:
            consulta = consulta.where(
                or_(Cliente.cpf.contains(digitos), Cliente.nome.ilike(f"%{busca}%"))
            )
        else:
            consulta = consulta.where(Cliente.nome.ilike(f"%{busca}%"))

    clientes = list((await sessao.execute(consulta)).scalars())
    if not clientes:
        return []

    ids = [c.id for c in clientes]
    saldos = await _saldo_por_cliente(sessao, ids)
    atrasados = await _saldo_atrasado_por_cliente(sessao, ids)
    comprou = await _qtd_comprou_por_cliente(sessao, ids)
    vendeu = await _qtd_vendeu_por_cliente(sessao, ids)

    return [
        ResumoDoCliente(
            cliente=c,
            saldo_devedor_centavos=saldos.get(c.id, 0),
            saldo_atrasado_centavos=atrasados.get(c.id, 0),
            qtd_comprou=comprou.get(c.id, 0),
            qtd_vendeu=vendeu.get(c.id, 0),
        )
        for c in clientes
    ]


async def saldo_devedor(sessao: AsyncSession, cliente_id: int) -> int:
    """Quanto este cliente ainda deve, somando toda parcela não paga."""
    consulta = (
        select(func.coalesce(func.sum(Parcela.valor_centavos), 0))
        .join(Venda, Venda.id == Parcela.venda_id)
        .where(Venda.cliente_id == cliente_id, Parcela.pago_em.is_(None))
    )
    return int((await sessao.execute(consulta)).scalar_one())


async def saldo_atrasado(sessao: AsyncSession, cliente_id: int) -> int:
    """Quanto deste cliente já está vencido e não foi pago."""
    return (await _saldo_atrasado_por_cliente(sessao, [cliente_id])).get(cliente_id, 0)


async def motos_compradas_de(sessao: AsyncSession, cliente_id: int) -> list[Moto]:
    """Motos que este cliente vendeu pra loja — aba "vendeu" na tela dele."""
    consulta = (
        select(Moto)
        .where(Moto.fornecedor_cliente_id == cliente_id)
        .order_by(Moto.data_compra.desc().nulls_last())
    )
    return list((await sessao.execute(consulta)).scalars())
