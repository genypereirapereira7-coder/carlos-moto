"""Arquivo do sistema antigo da loja — o que ela tinha antes do Carlos Moto.

**Uma tabela genérica, não uma tabela por tabela do sistema dela.** A primeira
versão disto criava `temp_pessoa`, `temp_vendas_master` e outras 181, cada uma
com colunas descobertas no arquivo. Deu três problemas que este desenho não
tem:

1. Exigia criar tabela em tempo de execução — coisa que só funcionava no
   Postgres, e o banco de desenvolvimento (SQLite) precisava de remendos pra
   não estourar.
2. Cada sistema antigo tem colunas diferentes. Guardar em JSON aceita qualquer
   estrutura que apareça, inclusive de um sistema que ninguém viu ainda.
3. Ninguém nunca leu aquilo. Nome de tabela de banco não é informação pra
   dono de loja — a tradução pra nome de gente mora em
   `app/dicionario_antigo.py`, e é ela que faz a aba valer alguma coisa.

Só leitura depois de importado: é arquivo, não cadastro. O que precisa entrar
no sistema vivo entra por um caminho explícito, com conferência antes.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, agora


class LoteAntigo(Base):
    """Uma importação. Duas importações do mesmo sistema não se misturam —
    a loja pode puxar de novo depois e comparar com o que veio antes."""

    __tablename__ = "lote_antigo"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Como a loja reconhece este lote ("Sistema da Monte São Motos, 26/09").
    descricao: Mapped[str] = mapped_column(String(160), nullable=False)

    # De onde veio, pra quem olhar em 2030 saber o que é isto.
    origem: Mapped[str | None] = mapped_column(String(160))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    linhas: Mapped[list["LinhaAntiga"]] = relationship(back_populates="lote", lazy="noload")


class LinhaAntiga(Base):
    """Uma linha de uma tabela do sistema antigo, como ela veio."""

    __tablename__ = "linha_antiga"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lote_antigo.id"), nullable=False, index=True
    )

    # O nome da tabela no sistema antigo, em minúscula (`pessoa`, `creceber`).
    tabela: Mapped[str] = mapped_column(String(80), nullable=False)

    # A posição no arquivo. Serve pra mostrar na mesma ordem que estava lá.
    numero_linha: Mapped[int] = mapped_column(Integer, nullable=False)

    # `{coluna: valor}`, tudo texto. Texto porque não há como adivinhar tipo do
    # sistema de outra pessoa, e converter errado é pior que não converter:
    # uma data que virou número não volta.
    dados: Mapped[dict] = mapped_column(JSON, nullable=False)

    lote: Mapped[LoteAntigo] = relationship(back_populates="linhas")

    __table_args__ = (
        # A consulta da aba é sempre "as linhas desta tabela deste lote".
        Index("ix_linha_antiga_lote_tabela", "lote_id", "tabela"),
    )
