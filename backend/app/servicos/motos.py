"""Cadastro e consulta de estoque."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.despesa import DespesaMoto
from app.models.moto import CondicaoMoto, Moto, StatusMoto
from app.schemas.despesa import DespesaEntrada


class MotoJaVendida(Exception):
    """Tentativa de editar ou apagar uma moto que já saiu pro cliente."""


class MotoInexistente(Exception):
    pass


class PlacaObrigatoria(Exception):
    """A moto ficaria sem placa depois deste PATCH — o dono pediu que isso
    nunca seja permitido, nem numa moto antiga que nasceu sem placa antes
    dessa regra existir."""


class CompraIncompleta(Exception):
    """Ficaria com valor de compra sem data, ou o contrário. O financeiro
    lança a compra no dia dela: valor sem data é um gasto que o dono
    digitou e nunca mais encontra em mês nenhum."""


async def listar(
    sessao: AsyncSession,
    *,
    somente_disponivel: bool = False,
    condicao: CondicaoMoto | None = None,
    marca: str | None = None,
    modelo: str | None = None,
) -> list[Moto]:
    consulta = select(Moto).order_by(Moto.marca, Moto.modelo, Moto.ano)
    if somente_disponivel:
        consulta = consulta.where(Moto.status == StatusMoto.DISPONIVEL)
    if condicao is not None:
        consulta = consulta.where(Moto.condicao == condicao)
    if marca is not None:
        consulta = consulta.where(Moto.marca.ilike(f"%{marca}%"))
    if modelo is not None:
        consulta = consulta.where(Moto.modelo.ilike(f"%{modelo}%"))
    return list((await sessao.execute(consulta)).scalars())


async def por_placa(sessao: AsyncSession, placa: str) -> Moto | None:
    """Busca exata por placa — é assim que a tela MOTOS abre o histórico de
    uma unidade. Maiúscula/minúscula não deveria importar pra quem digita
    olhando a placa física."""
    consulta = select(Moto).where(Moto.placa.ilike(placa.strip()))
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def editar(sessao: AsyncSession, moto: Moto, campos: dict) -> Moto:
    """Aplica o PATCH. Recusa mexer numa moto que já foi vendida.

    Preço/km/cor de uma moto vendida não interessam mais a ninguém editar — e
    deixar editar deixaria a `Venda` (que já congelou o preço vendido)
    dessincronizada do que a tela de estoque mostra pra essa unidade.
    """
    if moto.status == StatusMoto.VENDIDA:
        raise MotoJaVendida()

    for campo, valor in campos.items():
        setattr(moto, campo, valor)

    # Checado depois de aplicar os campos, não só quando `placa` está no
    # PATCH: uma moto que já nasceu sem placa (de antes desta regra existir)
    # não pode ser salva de novo — em nada — até alguém preencher a placa.
    if not moto.placa or not moto.placa.strip():
        raise PlacaObrigatoria()

    # Checado sobre o estado final, não sobre o que veio no PATCH: quem
    # edita só a cor não precisa remandar a compra, mas quem lança o
    # valor tem que dizer o dia.
    if (moto.valor_compra_centavos is None) != (moto.data_compra is None):
        raise CompraIncompleta()

    await sessao.flush()
    return moto


async def despesa_por_id_cliente(
    sessao: AsyncSession, id_cliente: uuid.UUID
) -> DespesaMoto | None:
    return (
        await sessao.execute(
            select(DespesaMoto).where(DespesaMoto.id_cliente == id_cliente)
        )
    ).scalar_one_or_none()


async def lancar_despesa(
    sessao: AsyncSession, moto: Moto, dados: DespesaEntrada, criado_por: int
) -> tuple[DespesaMoto, bool]:
    """Gasto de arrumação — sem a trava de `MotoJaVendida`: uma revisão pode
    muito bem ter sido paga na semana em que a moto já tinha comprador, antes
    da entrega.

    Devolve (despesa, criada_agora). `criada_agora=False` é o reenvio do mesmo
    `id_cliente` — duplo clique, ou a fila offline subindo duas vezes — que
    devolve o gasto que já existe em vez de lançar o mesmo dinheiro de novo.
    """
    existente = await despesa_por_id_cliente(sessao, dados.id_cliente)
    if existente is not None:
        return existente, False

    despesa = DespesaMoto(
        id_cliente=dados.id_cliente,
        moto_id=moto.id,
        descricao=dados.descricao,
        valor_centavos=dados.valor_centavos,
        data=dados.data,
        criado_por=criado_por,
    )
    sessao.add(despesa)
    await sessao.flush()
    return despesa, True
