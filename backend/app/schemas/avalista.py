"""Avalista de uma venda parcelada — entrada e saída.

Nome e telefone são obrigatórios — avalista sem telefone não serve pra nada
na hora de cobrar. CPF e endereço são opcionais, mas quando vêm preenchidos
passam pela mesma validação do cliente (CPF com dígito verificador, telefone
com DDD). Meio-preenchido errado não entra: ou está certo, ou fica em branco.
"""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.schemas.validadores import validar_cpf, validar_telefone, validar_texto_nao_vazio


def _cpf_opcional(valor: str | None) -> str | None:
    """CPF do avalista pode faltar; se vier, tem que fechar a conta."""
    if valor is None or not str(valor).strip():
        return None
    return validar_cpf(valor)


class AvalistaEntrada(BaseModel):
    nome: Annotated[str, Field(min_length=1, max_length=120), AfterValidator(validar_texto_nao_vazio)]
    # Telefone é obrigatório: avalista que a loja não consegue ligar não
    # avaliza nada. CPF continua opcional — nem sempre está na mão na hora.
    telefone: Annotated[str, Field(min_length=1, max_length=20), AfterValidator(validar_telefone)]
    cpf: Annotated[str | None, AfterValidator(_cpf_opcional)] = None
    endereco: Annotated[str | None, Field(max_length=200)] = None

    @model_validator(mode="after")
    def _telefone_de_verdade(self) -> "AvalistaEntrada":
        # `validar_telefone` devolve None pra string em branco; aqui em branco
        # não pode passar.
        if not self.telefone:
            raise ValueError("Avalista precisa de telefone")
        return self


class AvalistaSaida(BaseModel):
    id: uuid.UUID
    ordem: int
    nome: str
    cpf: str | None
    telefone: str | None
    endereco: str | None

    model_config = {"from_attributes": True}
