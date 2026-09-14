"""Registrar uma venda — e garantir que a mesma moto não seja vendida duas vezes.

Ao contrário de um pedido de sorvete, aqui o item é uma unidade física de alto
valor: vender a mesma moto pra dois clientes não é um erro que se resolve
telefonando, é dois contratos concorrendo pelo mesmo bem. Por isso a trava tem
duas camadas, não uma:

1. `SELECT ... FOR UPDATE` na moto: trava a linha até este commit, então um
   segundo `POST /vendas` pra mesma moto, chegando um milissegundo depois,
   fica parado aqui até o primeiro terminar — e aí encontra `status=VENDIDA` e
   cai no erro abaixo, em vez de vender a mesma moto duas vezes.
2. A constraint única em `Venda.moto_id`: mesmo que o lock acima falhe por
   algum motivo (o SQLite do dev, por exemplo, não bloqueia linha a linha como
   o Postgres — ele serializa a escrita trancando o arquivo inteiro, o que
   também resolve, mas por um mecanismo diferente), o banco recusa a segunda
   linha com o mesmo `moto_id` de qualquer jeito. É a garantia que não depende
   de nenhum código ter lembrado de tomar o lock certo.
"""

import calendar
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import agora, hoje
from app.models.cliente import Cliente
from app.models.moto import Moto, StatusMoto
from app.models.parcela import Parcela
from app.models.usuario import Usuario
from app.models.venda import FormaPagamento, Venda
from app.schemas.venda import VendaEntrada


class MotoJaVendida(Exception):
    """A moto não está mais DISPONIVEL — outra venda venceu a corrida, ou o
    dono a tirou de linha por outro caminho."""


class MotoInexistente(Exception):
    pass


class ClienteInexistente(Exception):
    pass


async def por_id_cliente(sessao: AsyncSession, id_cliente: uuid.UUID) -> Venda | None:
    return (
        await sessao.execute(select(Venda).where(Venda.id_cliente == id_cliente))
    ).scalar_one_or_none()


def _somar_meses(dia: date, meses: int) -> date:
    """`date + N meses`, sem depender de nenhuma lib externa.

    Ajusta pro último dia do mês quando o dia não existe no mês de destino
    (dia 31 de janeiro + 1 mês não é 31 de fevereiro)."""
    mes_total = dia.month - 1 + meses
    ano = dia.year + mes_total // 12
    mes = mes_total % 12 + 1
    ultimo_dia_do_mes = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia.day, ultimo_dia_do_mes))


def _gerar_parcelas(entrada: VendaEntrada) -> list[Parcela]:
    """Divide o saldo (preço - entrada) em N parcelas mensais iguais.

    O resto da divisão inteira vai pra última parcela — nunca pra primeira —
    porque é a última que o cliente vai conferir contra "quanto falta", e
    fechar exatamente redondo aí evita a pergunta "por que essa é 1 centavo
    diferente das outras".
    """
    saldo = entrada.preco_venda_centavos - entrada.valor_entrada_centavos
    n = entrada.numero_parcelas or 1
    valor_base = saldo // n
    resto = saldo - valor_base * n
    primeiro_vencimento = entrada.primeiro_vencimento or (hoje() + timedelta(days=30))

    parcelas = []
    for i in range(n):
        valor = valor_base + (resto if i == n - 1 else 0)
        parcelas.append(
            Parcela(
                numero=i + 1,
                valor_centavos=valor,
                vencimento=_somar_meses(primeiro_vencimento, i),
            )
        )
    return parcelas


async def criar_venda(
    sessao: AsyncSession, entrada: VendaEntrada, vendedor_id: int
) -> tuple[Venda, bool]:
    """Devolve (venda, criada_agora). `criada_agora=False` é o reenvio do
    mesmo `id_cliente` — duplo toque, rede oscilando — que devolve a venda que
    já existe em vez de tentar vender a moto de novo."""
    existente = await por_id_cliente(sessao, entrada.id_cliente)
    if existente is not None:
        return existente, False

    cliente = await sessao.get(Cliente, entrada.cliente_id)
    if cliente is None:
        raise ClienteInexistente()
    vendedor = await sessao.get(Usuario, vendedor_id)

    async with sessao.begin_nested():
        moto = (
            await sessao.execute(
                select(Moto).where(Moto.id == entrada.moto_id).with_for_update()
            )
        ).scalar_one_or_none()

        if moto is None:
            raise MotoInexistente()
        if moto.status != StatusMoto.DISPONIVEL:
            raise MotoJaVendida()

        moto.status = StatusMoto.VENDIDA
        # As relações (não só os `_id`) são atribuídas aqui de propósito: a
        # `Venda` acabou de nascer nesta sessão, nunca foi carregada por um
        # `select()` — sem isso `_saida()` tentaria um lazy-load fora do
        # contexto assíncrono certo e cairia com `MissingGreenlet`.
        venda = Venda(
            id_cliente=entrada.id_cliente,
            moto=moto,
            vendedor=vendedor,
            cliente=cliente,
            forma_pagamento=entrada.forma_pagamento,
            preco_venda_centavos=entrada.preco_venda_centavos,
            data_venda=entrada.data_venda or agora(),
        )
        # Sempre atribuído — mesmo vazio — pelo mesmo motivo do bloco acima:
        # depois do `flush()` a venda deixa de ser "pending" e uma coleção
        # nunca tocada vira lazy-load em vez de lista vazia em memória.
        venda.parcelas = (
            _gerar_parcelas(entrada) if entrada.forma_pagamento == FormaPagamento.PARCELADO else []
        )

        try:
            sessao.add(venda)
            await sessao.flush()
        except IntegrityError as erro:
            raise MotoJaVendida() from erro

    return venda, True


async def listar(
    sessao: AsyncSession,
    *,
    vendedor_id: int | None = None,
) -> list[Venda]:
    consulta = select(Venda).order_by(Venda.data_venda.desc())
    if vendedor_id is not None:
        consulta = consulta.where(Venda.vendedor_id == vendedor_id)
    return list((await sessao.execute(consulta)).scalars())
