"""Dinheiro que entra e sai do caixa por fora das vendas.

O financeiro monta tudo a partir de venda, parcela paga e gasto de moto. Só que
o caixa da loja tem movimento que não nasce de nenhum dos três: o dono tira
R$ 200 pra almoço da equipe, paga o aluguel, põe troco na gaveta, recebe um
serviço avulso. Sem lugar pra isso, o caixa do dia nunca fecha com o que está
na gaveta — e um financeiro que não bate deixa de ser consultado.

**Nada é apagado**, como no resto do sistema: lançamento errado é estornado,
não removido. O estorno deixa os dois registros no histórico, e o dono
consegue explicar depois o que aconteceu.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class TipoCaixa(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class MovimentoCaixa(Base):
    """Uma entrada ou saída de dinheiro lançada à mão pelo dono."""

    __tablename__ = "movimento_caixa"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    tipo: Mapped[TipoCaixa] = mapped_column(
        Enum(TipoCaixa, name="tipo_caixa"), nullable=False
    )

    # Sempre positivo: o que diz se soma ou subtrai é o `tipo`. Guardar saída
    # como número negativo faria toda soma do financeiro ter que lembrar do
    # sinal, e uma que esquecesse erraria o caixa sem reclamar.
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    # Obrigatória: "saiu R$ 300" sem dizer do quê é exatamente o lançamento
    # que ninguém consegue explicar no fim do mês.
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)

    # O dia em que o dinheiro andou — não o dia em que foi lançado. Quem paga
    # o aluguel na sexta e lança na segunda precisa que saia do caixa de
    # sexta, senão o fechamento dos dois dias fica errado.
    ocorrido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora, index=True
    )

    # Lançamento desfeito. Continua no histórico: some da conta, não do mundo.
    estornado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_estorno: Mapped[str | None] = mapped_column(String(200))

    criado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    autor: Mapped["Usuario"] = relationship(lazy="selectin")

    __table_args__ = (
        CheckConstraint("valor_centavos > 0", name="valor_caixa_positivo"),
        Index("ix_movimento_caixa_ocorrido", "ocorrido_em"),
    )

    @property
    def ativo(self) -> bool:
        return self.estornado_em is None
