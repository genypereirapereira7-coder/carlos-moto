"""Tudo que já mudou no sistema, para sempre.

A regra do dono é simples: **nada some**. Nem o que foi apagado, nem o valor
que estava ali antes de uma correção. Editar o valor de compra de uma moto
não pode fazer o número antigo desaparecer — ele fica aqui, com a data e com
quem trocou.

Uma linha por mudança, gravada sozinha pelo `app/historico.py` a cada
alteração no banco. É de propósito que nenhuma rota escreve aqui na mão:
histórico que depende de alguém lembrar de chamar é histórico que um dia
falta justo no registro que interessa.

Esta tabela só recebe linha. Nada aqui é alterado nem apagado depois.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, agora


class AcaoHistorico(str, enum.Enum):
    CRIADO = "CRIADO"
    ALTERADO = "ALTERADO"


class Historico(Base):
    __tablename__ = "historico"

    id: Mapped[int] = mapped_column(primary_key=True)

    # `tabela` + `registro_id` em vez de uma foreign key: a chave apontaria
    # pra uma tabela só, e o histórico precisa servir moto, cliente, venda,
    # parcela e gasto com a mesma estrutura. `registro_id` é texto porque uns
    # têm id inteiro e outros uuid.
    tabela: Mapped[str] = mapped_column(String(60), nullable=False)
    registro_id: Mapped[str] = mapped_column(String(60), nullable=False)

    acao: Mapped[AcaoHistorico] = mapped_column(
        String(12), nullable=False, default=AcaoHistorico.ALTERADO
    )

    # {"preco_centavos": {"antes": 950000, "depois": 890000}}
    # No cadastro, "antes" vem nulo em todos os campos.
    mudancas: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Nulo quando não houve gente no meio: a carga inicial do sistema, ou uma
    # tarefa automática.
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    quando: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora
    )

    __table_args__ = (
        # A pergunta que esta tabela responde é sempre "o que aconteceu com
        # este registro?" — e quase sempre do mais recente pro mais antigo.
        Index("ix_historico_registro", "tabela", "registro_id", "quando"),
        Index("ix_historico_quando", "quando"),
    )
