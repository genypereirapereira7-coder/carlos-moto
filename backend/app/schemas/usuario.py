"""Cadastro de vendedor e administração de contas pelo dono."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, computed_field

from app.schemas.tipos import Utc
from app.schemas.validadores import validar_texto_nao_vazio


class VendedorNovo(BaseModel):
    """O dono cria a conta do vendedor. Não há senha pra escolher: o servidor
    gera a chave e a mostra uma vez, pro dono passar pra pessoa."""

    nome: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(validar_texto_nao_vazio)]


class ChaveNova(BaseModel):
    """A chave em claro — mostrada **uma única vez**, na hora em que nasce.

    O banco guarda só o hash. Se o dono perder a chave, não há como recuperá-la:
    gera-se outra, e a antiga deixa de valer."""

    usuario_id: int
    nome: str
    chave: str


class VendedorResumo(BaseModel):
    """Uma linha na lista de vendedores que o dono gerencia."""

    id: int
    nome: str
    ativo: bool
    criado_em: Utc
    aprovado_em: Utc | None = None

    @computed_field
    @property
    def aguardando(self) -> bool:
        return self.aprovado_em is None and not self.ativo

    model_config = {"from_attributes": True}


class AtivoEntrada(BaseModel):
    ativo: bool
