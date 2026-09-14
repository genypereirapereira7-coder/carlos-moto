"""Gasto lançado numa moto do estoque — mecânica, revisão, guincho, o que for.

Fica em tabela própria, não numa coluna `gastos_centavos` na `Moto`, porque o
dono lança gasto aos poucos ao longo de semanas ("revisão", "pneu novo",
"emplacamento") e precisa depois lembrar o quê e quando — uma coluna só
teria a soma, mas perderia a lista. O total por moto é sempre `SUM` sobre
esta tabela.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class DespesaMoto(Base):
    __tablename__ = "despesa_moto"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Gerado no navegador antes de enviar, igual ao da `Venda`: sem ele um
    # gasto reenviado — duplo clique, ou a fila offline subindo duas vezes —
    # vira dois gastos iguais, e o dinheiro dobra calado no financeiro. Nulo
    # só nas linhas lançadas antes desta coluna existir.
    id_cliente: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, unique=True)

    moto_id: Mapped[int] = mapped_column(ForeignKey("moto.id"), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(160), nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    # Data do gasto (não de quando foi digitado) — é ela que entra no
    # fechamento diário/mensal do financeiro.
    data: Mapped[date] = mapped_column(Date, nullable=False)

    criado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    moto: Mapped["Moto"] = relationship(back_populates="despesas")

    __table_args__ = (
        CheckConstraint("valor_centavos >= 0", name="valor_nao_negativo"),
        Index("ix_despesa_moto_data", "data"),
    )
