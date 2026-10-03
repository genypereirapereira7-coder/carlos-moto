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

from app.models.avalista import Avalista
from app.models.base import agora, hoje
from app.models.cliente import Cliente
from app.models.moto import Moto, StatusMoto
from app.models.parcela import Parcela
from app.models.usuario import Papel, Usuario
from app.models.venda import COM_CARNE, Venda
from app.schemas.venda import VendaEntrada


class MotoJaVendida(Exception):
    """A moto não está mais DISPONIVEL — outra venda venceu a corrida, ou o
    dono a tirou de linha por outro caminho."""


class MotoInexistente(Exception):
    pass


class ClienteInexistente(Exception):
    pass


class VendedorInvalido(Exception):
    """O `vendedor_id` escolhido no formulário não é um vendedor ativo (nem o
    dono) — não dá pra atribuir a venda a quem não vende na loja."""


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


def _com_juros(saldo_centavos: int, juros_centesimos: int) -> int:
    """O saldo financiado acrescido dos juros da loja.

    Juro simples sobre o saldo: R$ 1.000 a 10% viram R$ 1.100 divididos nas
    parcelas. É a conta que a loja faz de cabeça no balcão — e a tela mostra
    o total antes de confirmar, pra não haver surpresa no carnê.

    A divisão inteira arredonda pra baixo (centavo não se parte), então o
    cliente nunca paga um centavo a mais do que a conta fecha.
    """
    if juros_centesimos <= 0:
        return saldo_centavos
    # `// 10_000` porque o juro está em centésimos de por cento: 550 = 5,5%.
    return saldo_centavos + (saldo_centavos * juros_centesimos) // 10_000


def _gerar_parcelas(entrada: VendaEntrada) -> list[Parcela]:
    """Divide o saldo (preço - entrada, mais juros) em N parcelas mensais iguais.

    O resto da divisão inteira vai pra última parcela — nunca pra primeira —
    porque é a última que o cliente vai conferir contra "quanto falta", e
    fechar exatamente redondo aí evita a pergunta "por que essa é 1 centavo
    diferente das outras".
    """
    saldo = _com_juros(
        entrada.preco_venda_centavos - entrada.valor_entrada_centavos,
        entrada.juros_centesimos,
    )
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
                # Vazio e explícito: a parcela nasce nesta sessão e nunca foi
                # carregada por query, então sem isto ler `saldo_centavos` (que
                # olha `pagamentos`) viraria lazy-load fora do contexto async e
                # cairia com MissingGreenlet ao montar a resposta da venda.
                pagamentos=[],
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

    # Quem a venda credita: o vendedor escolhido no formulário quando veio um,
    # senão quem está logado. O escolhido precisa ser um vendedor ativo (ou o
    # próprio dono) — a tela não deixa mandar outra coisa, mas a API confere.
    vendedor = await sessao.get(Usuario, entrada.vendedor_id or vendedor_id)
    if entrada.vendedor_id is not None and (
        vendedor is None
        or not vendedor.ativo
        or vendedor.papel not in (Papel.VENDEDOR, Papel.DONO)
    ):
        raise VendedorInvalido()

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
            valor_entrada_centavos=entrada.valor_entrada_centavos,
            juros_centesimos=entrada.juros_centesimos,
            observacao=entrada.observacao,
            data_venda=entrada.data_venda or agora(),
        )
        # Sempre atribuído — mesmo vazio — pelo mesmo motivo do bloco acima:
        # depois do `flush()` a venda deixa de ser "pending" e uma coleção
        # nunca tocada vira lazy-load em vez de lista vazia em memória.
        parcelado = entrada.forma_pagamento in COM_CARNE
        venda.parcelas = _gerar_parcelas(entrada) if parcelado else []
        # Avalistas só em venda parcelada — o schema já recusa o contrário; aqui
        # é a segunda barreira. Numerados na ordem em que vieram do formulário.
        venda.avalistas = (
            [
                Avalista(
                    ordem=i + 1,
                    nome=a.nome,
                    cpf=a.cpf,
                    telefone=a.telefone,
                    endereco=a.endereco,
                )
                for i, a in enumerate(entrada.avalistas)
            ]
            if parcelado
            else []
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


class MotoNaoVendida(Exception):
    """A moto não está vendida — não há o que desfazer."""


async def devolver_ao_estoque(sessao: AsyncSession, moto: Moto) -> Venda:
    """Desfaz a venda: a moto volta pro estoque e pode ser vendida de novo.

    **Nada é apagado.** A venda, o carnê e os pagamentos continuam gravados,
    marcados com a data em que foram desfeitos — some só a dívida: o cliente
    deixa de dever as parcelas, e o financeiro deixa de contar aquela venda.
    É o caso do cliente que desiste e devolve a moto, e da venda lançada na
    moto errada.

    O que já foi pago **não** é estornado aqui: dinheiro que entrou e volta
    pro cliente é decisão do dono, no caixa, não efeito colateral de um botão.
    """
    venda = (
        await sessao.execute(
            select(Venda).where(Venda.moto_id == moto.id, Venda.cancelada_em.is_(None))
        )
    ).scalars().first()
    if venda is None or moto.status != StatusMoto.VENDIDA:
        raise MotoNaoVendida()

    venda.cancelada_em = agora()
    moto.status = StatusMoto.DISPONIVEL
    await sessao.flush()
    return venda
