"""Uma venda: uma moto, um vendedor, um cliente — sem volta."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class FormaPagamento(str, enum.Enum):
    A_VISTA = "A_VISTA"

    # Crediário da própria loja (o "carnê"). Ver `COM_CARNE` abaixo.
    PARCELADO = "PARCELADO"

    # Cheque pré-datado: na prática é o mesmo risco do carnê — a loja entrega
    # a moto e fica esperando o dinheiro entrar folha a folha. Por isso gera
    # parcela e aceita avalista igual ao carnê.
    CHEQUE = "CHEQUE"

    # Parcelado no cartão: a operadora paga a loja, o parcelamento é entre o
    # cliente e o cartão. A loja não tem o que cobrar depois.
    CARTAO = "CARTAO"

    FINANCIADO = "FINANCIADO"
    CONSORCIO = "CONSORCIO"


# As formas em que **a loja carrega a dívida**: entregou a moto e vai receber
# aos poucos, por conta e risco dela. São as únicas que geram `Parcela` (o
# carnê que o dono precisa cobrar) e as únicas que aceitam avalista.
#
# Financiado por banco, consórcio e cartão ficam de fora porque a loja já
# recebeu o valor cheio: o parcelamento de lá é problema entre o cliente e a
# instituição, não há nada pra esta tela acompanhar.
COM_CARNE = frozenset({FormaPagamento.PARCELADO, FormaPagamento.CHEQUE})

# Juros da loja também só existe em `COM_CARNE`, e é por isso que não há uma
# lista separada: quem parcela no cartão ou no consórcio é a operadora, não a
# loja — o juro de lá é entre o cliente e eles, e registrar isso aqui seria
# guardar um número que a loja não cobra nem recebe.


class Venda(Base):
    __tablename__ = "venda"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Gerado no aparelho do vendedor antes de enviar — protege contra o duplo
    # toque numa conexão lenta virando duas vendas da mesma moto pro mesmo
    # cliente. Ver `servicos/vendas.py::criar_venda`.
    id_cliente: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)

    # A trava de verdade contra vender a mesma moto duas vezes pra clientes
    # diferentes: nenhuma moto pode aparecer em mais de uma Venda, ponto — o
    # banco recusa a segunda linha independente de qualquer lock que o código
    # tenha esquecido de tomar. Ver `servicos/vendas.py`.
    moto_id: Mapped[int] = mapped_column(ForeignKey("moto.id"), nullable=False, unique=True)

    vendedor_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), nullable=False, index=True)

    forma_pagamento: Mapped[FormaPagamento] = mapped_column(
        Enum(FormaPagamento, name="forma_pagamento"), nullable=False
    )

    # Pode diferir do `Moto.preco_centavos` por negociação — congelado aqui
    # porque o preço anunciado pode mudar depois (o dono reajusta a tabela),
    # mas o preço vendido nunca deve.
    preco_venda_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    # O que o cliente deu de entrada no ato. Guardado, e não deduzido de
    # `preço − soma das parcelas`: com juros no carnê as parcelas somam MAIS
    # que o saldo financiado, e aquela subtração passaria a mentir justamente
    # no número que o financeiro usa como "entrou no caixa no dia da venda".
    valor_entrada_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Juros que a loja cobra pra parcelar, em centésimos de por cento
    # (5,5% = 550). Inteiro pelo mesmo motivo do dinheiro em centavos: taxa
    # em float acumula erro de arredondamento e o carnê deixa de fechar.
    # 0 = sem juros.
    juros_centesimos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Anotação livre sobre esta venda — o combinado que não cabe nos
    # campos ("leva o capacete junto", "volta dia 10 pra transferência").
    observacao: Mapped[str | None] = mapped_column(String(1000))

    # O índice vem do `Index` nomeado em `__table_args__` logo abaixo, não de
    # `index=True` aqui — as duas formas geram o mesmo nome pela convenção em
    # `models/base.py`, e o `create_all` recusa criar o mesmo índice duas vezes.
    data_venda: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    moto: Mapped["Moto"] = relationship(back_populates="venda", lazy="selectin")
    vendedor: Mapped["Usuario"] = relationship(foreign_keys=[vendedor_id], lazy="selectin")
    cliente: Mapped["Cliente"] = relationship(back_populates="vendas", lazy="selectin")
    # Sem `delete-orphan`: o sistema não apaga nada (ver `app/historico.py`),
    # e essa cascata era o caminho por onde um carnê inteiro sumiria junto com
    # a venda, sem deixar rastro.
    parcelas: Mapped[list["Parcela"]] = relationship(
        back_populates="venda", lazy="selectin", order_by="Parcela.numero"
    )
    # Só existem em venda parcelada no carnê da loja — quem avaliza o crédito
    # que a loja mesma concedeu. Sem `delete-orphan` pelo mesmo motivo das
    # parcelas: o sistema não apaga nada.
    avalistas: Mapped[list["Avalista"]] = relationship(
        back_populates="venda", lazy="selectin", order_by="Avalista.ordem"
    )

    __table_args__ = (
        CheckConstraint("preco_venda_centavos >= 0", name="preco_venda_nao_negativo"),
        Index("ix_venda_data_venda", "data_venda"),
    )

    @property
    def parcelado(self) -> bool:
        """Tem carnê pra loja cobrar — carnê próprio ou cheque pré-datado."""
        return self.forma_pagamento in COM_CARNE

    @property
    def saldo_devedor_centavos(self) -> int:
        # Soma o que falta em cada parcela — parcela paga em parte conta só o
        # saldo, não o valor cheio.
        return sum(p.saldo_centavos for p in self.parcelas)
