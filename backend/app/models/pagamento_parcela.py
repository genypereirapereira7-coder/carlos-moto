"""Pagamento de uma parcela do carnê da loja — um por vez, quanto o cliente
trouxer.

O carnê da loja aceita pagamento em pedaços: a parcela de R$ 300 pode entrar
como R$ 100 hoje e R$ 200 depois. Cada entrada é uma linha aqui. A parcela
está quitada quando a soma das linhas cobre o valor dela; até lá continua
aberta, mostrando o que falta.

Por que uma tabela, e não uma coluna "valor_pago" que vai somando: o painel
financeiro conta o dinheiro pelo **dia em que entrou**, e cada pedaço pode ter
entrado num dia diferente. Uma coluna só guardaria o total, sem as datas — e o
caixa do dia deixaria de bater. Aqui cada pagamento leva a própria data.

Estorno (desfazer um recebimento lançado errado) é uma linha de valor
negativo, não um apagão: o sistema não apaga nada, então corrigir é lançar o
contrário, e a conta volta ao lugar com o rastro inteiro preservado.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class PagamentoParcela(Base):
    __tablename__ = "pagamento_parcela"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parcela_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parcela.id"), nullable=False, index=True
    )

    # Positivo = dinheiro que entrou; negativo = estorno de um lançamento
    # errado. Nunca zero — um pagamento de nada não é um pagamento.
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    # O dia/hora em que o cliente pagou — não o dia do lançamento. É por esta
    # data que o financeiro joga o valor no caixa do dia certo. Sempre em UTC,
    # como o resto do sistema.
    pago_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    parcela: Mapped["Parcela"] = relationship(back_populates="pagamentos", lazy="selectin")

    __table_args__ = (
        CheckConstraint("valor_centavos <> 0", name="pagamento_valor_nao_zero"),
        Index("ix_pagamento_parcela_pago_em", "pago_em"),
    )
