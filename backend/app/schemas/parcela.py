"""Parcela do crediário próprio da loja."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.models.parcela import StatusParcela
from app.schemas.tipos import Utc
from app.schemas.validadores import validar_nao_no_futuro


class ParcelaSaida(BaseModel):
    id: uuid.UUID
    numero: int
    valor_centavos: int
    vencimento: date
    pago_em: Utc | None
    status: StatusParcela

    # Quanto já entrou e quanto falta — o que dá sentido ao pagamento em
    # pedaços. Parcela sem pagamento nenhum: total_pago 0 e saldo = valor.
    total_pago_centavos: int = 0
    saldo_centavos: int = 0

    model_config = {"from_attributes": True}


class ParcelaComCliente(ParcelaSaida):
    """Uma linha da tela PARCELAS: a parcela junto de quem deve e da moto —
    essa tela só existe pra mostrar quem está devendo."""

    venda_id: uuid.UUID
    cliente_id: int
    cliente_nome: str
    cliente_cpf: str

    # Numa tela de cobrança é a informação que mais importa: é pra este
    # número que o dono liga quando vê a linha vermelha.
    cliente_telefone: str | None

    moto_marca: str
    moto_modelo: str
    moto_placa: str | None


class MarcarPagaEntrada(BaseModel):
    pago: bool = True

    # O dia em que o cliente pagou — não o dia em que o dono lançou. Quem
    # recebe no sábado e só lança na segunda precisa que o dinheiro entre no
    # caixa de sábado, senão o financeiro do dia fica errado. Em branco = hoje.
    data_pagamento: Annotated[date, AfterValidator(validar_nao_no_futuro)] | None = None


class PagamentoEntrada(BaseModel):
    """Um pagamento em pedaço: o cliente pagou parte da parcela."""

    # `gt=0`: pagamento de nada não existe. O teto (não passar do saldo) é
    # conferido no serviço, que é quem sabe quanto ainda falta.
    valor_centavos: int = Field(gt=0)
    data_pagamento: Annotated[date, AfterValidator(validar_nao_no_futuro)] | None = None
