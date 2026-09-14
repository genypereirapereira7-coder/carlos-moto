"""Estoque: toda moto, nova ou usada, é uma linha nesta tabela."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class CondicaoMoto(str, enum.Enum):
    NOVA = "NOVA"
    USADA = "USADA"


class StatusMoto(str, enum.Enum):
    DISPONIVEL = "DISPONIVEL"
    VENDIDA = "VENDIDA"


class Moto(Base):
    """Toda unidade física em estoque — 0km ou usada, uma linha por moto.

    Não existe tabela de "catálogo" separada da "unidade": no Brasil toda
    moto, nova ou usada, sai de fábrica com chassi próprio, então "5 CG160
    2026 em estoque" já É 5 linhas com 5 chassis diferentes — não uma linha de
    catálogo com quantidade=5. "Quantas CG160 sobram" é
    `COUNT(*) WHERE modelo=... AND status=DISPONIVEL`, não uma coluna que
    alguém precisa lembrar de decrementar.
    """

    __tablename__ = "moto"

    id: Mapped[int] = mapped_column(primary_key=True)
    marca: Mapped[str] = mapped_column(String(60), nullable=False)
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    cor: Mapped[str | None] = mapped_column(String(40))
    condicao: Mapped[CondicaoMoto] = mapped_column(
        Enum(CondicaoMoto, name="condicao_moto"), nullable=False
    )

    # Todo veículo tem chassi de fábrica, novo ou usado — é a identidade real
    # da unidade física. Único no banco: duas linhas com o mesmo chassi seriam
    # a mesma moto cadastrada duas vezes. Nulo no cadastro rápido (placa,
    # modelo, ano) — completado depois, na edição, junto do resto dos dados
    # financeiros. NULL não colide com NULL numa unique constraint.
    chassi: Mapped[str | None] = mapped_column(String(17), unique=True, index=True)

    # Nula na coluna (Postgres e SQLite tratam cada NULL como distinto numa
    # unique constraint, então isso nunca travaria duas motos sem placa entre
    # si) — mas na prática nunca fica nula: `MotoEntrada` exige placa no
    # cadastro, e `servicos/motos.py::editar` recusa salvar qualquer edição
    # enquanto a moto não tiver uma. O dono pediu que não desse pra guardar
    # moto sem placa de jeito nenhum.
    placa: Mapped[str | None] = mapped_column(String(8), unique=True)

    km: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Preço anunciado — o que está na vitrine. Pode diferir do que a moto
    # acaba saindo por (`Venda.preco_venda_centavos`), que é o valor
    # negociado de verdade.
    preco_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    # De quanto a loja pagou por esta unidade, de quem, e quando — o lado
    # "compra" do histórico que a tela de MOTOS mostra ao lado da venda.
    # `None` até a edição preencher: uma moto acabada de cadastrar ainda não
    # tem esse dado lançado.
    valor_compra_centavos: Mapped[int | None] = mapped_column(Integer)
    data_compra: Mapped[date | None] = mapped_column(Date)

    # De quem a loja comprou. Um cliente cadastrado (pessoa física que vendeu
    # a própria moto pra loja — aparece na aba "vendeu" do cadastro dele) ou,
    # quando não há cadastro (distribuidora, revenda, 0km de fábrica),
    # só o nome em texto livre. Nunca os dois ao mesmo tempo importam: quem
    # tem `fornecedor_cliente_id` usa o nome de lá.
    fornecedor_cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id"))
    fornecedor_nome: Mapped[str | None] = mapped_column(String(120))

    status: Mapped[StatusMoto] = mapped_column(
        Enum(StatusMoto, name="status_moto"), nullable=False, default=StatusMoto.DISPONIVEL
    )

    criado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora, onupdate=agora
    )

    venda: Mapped["Venda | None"] = relationship(back_populates="moto", lazy="selectin")
    fornecedor: Mapped["Cliente | None"] = relationship(lazy="selectin")
    # Sem `delete-orphan`, pelo mesmo motivo das parcelas em `venda.py`: os
    # gastos de uma moto não podem sumir junto com ela.
    despesas: Mapped[list["DespesaMoto"]] = relationship(
        back_populates="moto", lazy="selectin", order_by="DespesaMoto.data"
    )

    __table_args__ = (
        CheckConstraint("preco_centavos >= 0", name="preco_nao_negativo"),
        CheckConstraint("km >= 0", name="km_nao_negativo"),
        CheckConstraint(
            "valor_compra_centavos IS NULL OR valor_compra_centavos >= 0",
            name="valor_compra_nao_negativo",
        ),
        # A pergunta mais comum do vendedor é "quantas CG160 sobram" — filtro
        # por modelo+status. Sem este índice composto isso vira table scan
        # assim que o estoque passar de umas centenas de linhas.
        Index("ix_moto_modelo_status", "modelo", "status"),
    )
