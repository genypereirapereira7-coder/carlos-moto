"""O que mudou num registro, pra quem for conferir depois."""

from datetime import datetime

from pydantic import BaseModel

from app.models.historico import AcaoHistorico
from app.schemas.tipos import Utc


class MudancaSaida(BaseModel):
    id: int
    acao: AcaoHistorico
    # {"preco_centavos": {"antes": 1150000, "depois": 1050000}}
    mudancas: dict
    usuario_id: int | None
    usuario_nome: str | None
    quando: Utc
