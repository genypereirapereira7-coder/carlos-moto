"""Base declarativa e helpers de tempo."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.config import get_config

# Nomes previsíveis pros constraints — sem isso o Alembic gera migration
# com nome automático e o autogenerate fica ruidoso a cada rodada.
convencao = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

FUSO_DA_LOJA = ZoneInfo(get_config().fuso)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convencao)


def agora() -> datetime:
    """Sempre UTC no banco. A conversão pro fuso de quem olha é feita na borda."""
    return datetime.now(UTC)


def hoje() -> date:
    """O dia de hoje no relógio da loja, não em UTC.

    `agora().date()` erra por três horas todo fim de dia: às 22h em Brasília
    já é amanhã em UTC. Pra instante (quando algo aconteceu) vale UTC; pra
    **dia** (vencimento, "não pode ser no futuro", fechamento do caixa) vale
    este.
    """
    return datetime.now(FUSO_DA_LOJA).date()


def como_utc(momento: datetime) -> datetime:
    """Garante datetime com fuso.

    O Postgres devolve `timestamptz` já com fuso, mas SQLite (usado nos testes
    e no dev local) devolve naive — e comparar naive com aware levanta
    TypeError. Normalizar aqui evita que a diferença entre os dois bancos vire
    bug.
    """
    return momento.replace(tzinfo=UTC) if momento.tzinfo is None else momento
