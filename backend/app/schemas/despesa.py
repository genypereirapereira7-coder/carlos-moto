"""Gasto lançado numa moto do estoque."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.schemas.tipos import Utc
from app.schemas.validadores import validar_nao_no_futuro, validar_texto_nao_vazio


class DespesaEntrada(BaseModel):
    # Gerado no navegador antes de enviar — é o que faz o reenvio do mesmo
    # gasto devolver o que já existe em vez de lançar de novo. Ver
    # `models/despesa.py` e `servicos/motos.py::lancar_despesa`.
    id_cliente: uuid.UUID

    descricao: Annotated[str, Field(min_length=1, max_length=160), AfterValidator(validar_texto_nao_vazio)]

    # `gt=0`, não `ge=0`: um gasto de R$ 0,00 não é gasto nenhum — é o
    # dono esquecendo de preencher o valor antes de salvar.
    valor_centavos: int = Field(gt=0)

    data: Annotated[date, AfterValidator(validar_nao_no_futuro)]


class DespesaSaida(BaseModel):
    id: int
    descricao: str
    valor_centavos: int
    data: date
    criado_em: Utc

    model_config = {"from_attributes": True}
