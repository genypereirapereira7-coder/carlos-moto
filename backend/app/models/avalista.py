"""Avalista de uma venda parcelada no crediário da loja.

Só existe quando a loja carrega o risco — venda no carnê da própria loja (ou
paga em cheque). Quem financia por banco ou consórcio já recebeu tudo; não há
o que avalizar. São no máximo três por venda, na ordem em que foram anotados.

O CPF é opcional aqui de propósito: na hora da venda a loja às vezes só tem o
nome e o telefone de quem avaliza, e prender a venda por causa disso atrapalha
mais do que ajuda. O que dá pra ter, entra; o resto se completa depois.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class Avalista(Base):
    __tablename__ = "avalista"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    venda_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venda.id"), nullable=False, index=True
    )

    # 1, 2 ou 3 — a ordem em que aparecem no contrato ("Avalista 1", etc.).
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    # Só dígitos, como no Cliente — formatação é problema da tela.
    cpf: Mapped[str | None] = mapped_column(String(11))
    telefone: Mapped[str | None] = mapped_column(String(20))
    endereco: Mapped[str | None] = mapped_column(String(200))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    venda: Mapped["Venda"] = relationship(back_populates="avalistas", lazy="selectin")

    __table_args__ = (
        CheckConstraint("ordem >= 1 AND ordem <= 3", name="avalista_ordem_1_a_3"),
        # Dois avalistas na mesma posição da mesma venda seriam um erro de
        # gravação, não duas pessoas — o par (venda, ordem) é único.
        Index("ix_avalista_venda_ordem", "venda_id", "ordem", unique=True),
    )
