"""Cliente: qualquer pessoa que compra moto da loja ou vende moto pra ela."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, agora


class Cliente(Base):
    """Uma pessoa só tem uma linha aqui, compre ela da loja ou venda pra
    loja — é o que deixa a tela do cliente juntar as duas pontas ("comprou"
    e "vendeu") embaixo do mesmo nome, em vez de duplicar o cadastro."""

    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)

    # Só dígitos, sem ponto nem traço — formatação é problema da tela, não do
    # banco. Único porque é o jeito de achar o mesmo cliente sem depender de
    # grafia de nome (dois "João da Silva" existem; dois CPFs iguais, não).
    cpf: Mapped[str] = mapped_column(String(11), nullable=False, unique=True, index=True)

    telefone: Mapped[str | None] = mapped_column(String(20))

    # Estado civil e cônjuge. Na venda de veículo o cônjuge costuma assinar
    # junto, e é ele que a loja procura quando o titular some — por isso nome
    # e telefone do cônjuge são exigidos quando casado, e o CPF não (nem
    # sempre a loja tem o documento dele na hora). `None` = não perguntado.
    casado: Mapped[bool | None] = mapped_column(Boolean)
    conjuge_nome: Mapped[str | None] = mapped_column(String(120))
    conjuge_cpf: Mapped[str | None] = mapped_column(String(11))
    conjuge_telefone: Mapped[str | None] = mapped_column(String(20))

    # RG e nascimento: é com eles, junto do CPF, que o contrato qualifica o
    # comprador. O sistema antigo da loja guardava os dois, e o RG não tem
    # formato único no Brasil (tamanho varia por estado), daí texto.
    rg: Mapped[str | None] = mapped_column(String(20))
    nascimento: Mapped[date | None] = mapped_column(Date)

    # E-mail e endereço. O sistema antigo da loja já guardava os dois em todo
    # cliente, e é o que faz carnê e contrato saírem com endereço em vez de em
    # branco. Tudo opcional: o dono cadastra na pressa do balcão e completa
    # depois, e cliente antigo nem sempre tem e-mail.
    email: Mapped[str | None] = mapped_column(String(120))
    endereco: Mapped[str | None] = mapped_column(String(160))
    # Texto, não número: existe "123 A", "S/N" e "km 4".
    numero: Mapped[str | None] = mapped_column(String(20))
    complemento: Mapped[str | None] = mapped_column(String(80))
    bairro: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(String(2))
    # Só dígitos, como o CPF: formatar é problema da tela.
    cep: Mapped[str | None] = mapped_column(String(8))

    # Anotação livre sobre o cliente — o que o dono quer lembrar dele.
    observacao: Mapped[str | None] = mapped_column(String(1000))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    # Motos que este cliente comprou da loja — aba "comprou" da tela dele.
    vendas: Mapped[list["Venda"]] = relationship(back_populates="cliente", lazy="selectin")

    __table_args__ = (
        # Busca por nome é `ILIKE %...%` — sem índice funcional isso não ajuda
        # muito, mas evita pelo menos o pior caso de ordenar sem índice nenhum.
        Index("ix_cliente_nome", "nome"),
    )
