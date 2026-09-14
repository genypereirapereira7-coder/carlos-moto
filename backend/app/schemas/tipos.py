"""Tipos compartilhados pelos schemas."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BeforeValidator


def _com_fuso(valor: datetime | str | None) -> datetime | str | None:
    if isinstance(valor, datetime) and valor.tzinfo is None:
        return valor.replace(tzinfo=UTC)
    return valor


Utc = Annotated[datetime, BeforeValidator(_com_fuso)]
"""Datetime que sempre sai no JSON com o fuso explícito.

O SQLite devolve `datetime` sem fuso e o Postgres devolve com. Um campo que
esquece de normalizar vira JSON sem o "Z", o navegador lê a hora UTC como
local, e o horário aparece deslocado. Usar este tipo em vez de `datetime` nos
schemas de saída fecha a porta: a normalização passa a ser padrão.
"""
