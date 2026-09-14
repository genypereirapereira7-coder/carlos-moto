"""Parcela do crediário próprio da loja.

Só existe quando a venda foi feita no `FormaPagamento.PARCELADO` — dinheiro
que a loja mesma financiou e que ainda vai entrar aos poucos. Venda à vista,
no cartão, financiada por banco ou por consórcio não gera linha aqui: nesses
casos a loja já recebeu (ou nunca vai cobrar) o valor cheio, então não há
nada seu pra acompanhar."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora, hoje


class StatusParcela(str, enum.Enum):
    PENDENTE = "PENDENTE"
    ATRASADA = "ATRASADA"
    PAGA = "PAGA"


class Parcela(Base):
    __tablename__ = "parcela"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    venda_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venda.id"), nullable=False, index=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)

    # `None` = ainda devendo. Não tem coluna `status` separada de propósito:
    # duas fontes de verdade pro mesmo fato (paga ou não) é como o pago fica
    # "pendente" na tela depois de alguém esquecer de atualizar a outra coluna.
    pago_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    venda: Mapped["Venda"] = relationship(back_populates="parcelas", lazy="selectin")

    __table_args__ = (
        CheckConstraint("valor_centavos >= 0", name="valor_nao_negativo"),
        Index("ix_parcela_venda_numero", "venda_id", "numero", unique=True),
        Index("ix_parcela_vencimento", "vencimento"),
    )

    @property
    def status(self) -> StatusParcela:
        """Atrasada só no dia seguinte ao vencimento, no relógio da loja — a
        parcela que vence hoje ainda está em dia até a meia-noite de Brasília,
        não até a meia-noite de Londres."""
        if self.pago_em is not None:
            return StatusParcela.PAGA
        return StatusParcela.ATRASADA if self.vencimento < hoje() else StatusParcela.PENDENTE
