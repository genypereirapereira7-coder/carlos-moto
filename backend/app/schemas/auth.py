import uuid
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.usuario import Papel
from app.schemas.tipos import Utc


class ParearEntrada(BaseModel):
    """A chave de acesso, digitada uma vez neste aparelho.

    Não há nome de usuário: a chave já diz quem é. E não há senha em lugar
    nenhum do sistema — depois deste pareamento, quem mantém o aparelho
    conectado é o refresh token, renovado sozinho.
    """

    chave: Annotated[str, Field(min_length=8, max_length=40)]
    dispositivo: str | None = Field(default=None, max_length=120)


class RenovarEntrada(BaseModel):
    refresh: str


class TokensSaida(BaseModel):
    acesso: str
    refresh: str
    expira_em: int  # segundos de validade do token de acesso
    usuario_id: int
    nome: str
    papel: Papel


class UsuarioPublico(BaseModel):
    """Quem está logado agora, pro `/auth/eu`."""

    id: int
    nome: str
    papel: Papel

    model_config = {"from_attributes": True}


class SessaoAtiva(BaseModel):
    """Um aparelho logado, na tela de acesso do dono."""

    id: uuid.UUID
    usuario_id: int
    usuario_nome: str
    papel: Papel
    dispositivo: str | None
    criado_em: Utc
    expira_em: Utc

    # "Este é o seu login." O token de acesso carrega o usuário, não a sessão,
    # então dá pra dizer de quem é o aparelho, mas não qual deles é este.
    meu_usuario: bool
