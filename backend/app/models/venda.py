"""Uma venda: uma moto, um vendedor, um cliente — sem volta."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class FormaPagamento(str, enum.Enum):
    A_VISTA = "A_VISTA"

    # Crediário da própria loja: é a única forma que gera `Parcela` — dinheiro
    # que ainda vai entrar aos poucos e que o dono precisa cobrar. Financiado
    # por banco e consórcio já pagam a loja inteira na hora; o parcelamento
    # deles é entre o cliente e o banco, não é problema da loja acompanhar.
    PARCELADO = "PARCELADO"

    FINANCIADO = "FINANCIADO"
    CONSORCIO = "CONSORCIO"


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

    __table_args__ = (
        CheckConstraint("preco_venda_centavos >= 0", name="preco_venda_nao_negativo"),
        Index("ix_venda_data_venda", "data_venda"),
    )

    @property
    def parcelado(self) -> bool:
        return self.forma_pagamento == FormaPagamento.PARCELADO

    @property
    def saldo_devedor_centavos(self) -> int:
        return sum(p.valor_centavos for p in self.parcelas if p.pago_em is None)
