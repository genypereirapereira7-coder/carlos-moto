"""Cliente e o histórico dele com a loja (o que comprou, o que vendeu).

**"Comprou" e "vendeu" são do ponto de vista do cliente**, que é como o dono
fala: "comprou" é moto que saiu da loja pra ele (uma `Venda`), "vendeu" é
moto que ele trouxe e a loja pagou (uma `Moto` com ele de fornecedor). Os
dois nomes aparecem assim nas abas da tela dele.
"""

import uuid
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.models.venda import FormaPagamento
from app.schemas.parcela import ParcelaSaida
from app.schemas.tipos import Utc
from app.schemas.validadores import validar_cpf, validar_telefone, validar_texto_nao_vazio

_Nome = Annotated[
    str, Field(min_length=1, max_length=120), AfterValidator(validar_texto_nao_vazio)
]
_Cpf = Annotated[str, AfterValidator(validar_cpf)]
_Telefone = Annotated[str, Field(max_length=20), AfterValidator(validar_telefone)]


class ClienteEntrada(BaseModel):
    nome: _Nome
    cpf: _Cpf
    telefone: _Telefone | None = None


class ClientePatch(BaseModel):
    nome: _Nome | None = None
    telefone: _Telefone | None = None


class ClienteSaida(BaseModel):
    id: int
    nome: str
    cpf: str
    telefone: str | None
    criado_em: Utc

    model_config = {"from_attributes": True}


class ClienteResumo(ClienteSaida):
    """Linha da lista de clientes. O sinal vermelho (quem deve) e as duas
    contagens já vêm calculados daqui — a tela não precisa abrir cliente por
    cliente pra saber quem filtrar em "comprou" e em "vendeu"."""

    deve_parcela: bool
    saldo_devedor_centavos: int

    # Só o que já passou do vencimento. É isto que pinta a linha de
    # vermelho — quem só tem parcela pra vencer aparece em amarelo.
    saldo_atrasado_centavos: int

    qtd_comprou: int
    qtd_vendeu: int


class MotoNoHistorico(BaseModel):
    id: int
    marca: str
    modelo: str
    ano: int
    placa: str | None
    chassi: str | None

    model_config = {"from_attributes": True}


class CompraDoCliente(BaseModel):
    """Uma moto que a loja comprou deste cliente — aba "vendeu" na tela dele:
    ele vendeu a moto própria pra loja."""

    moto: MotoNoHistorico
    data_compra: date | None
    valor_compra_centavos: int | None


class VendaDoCliente(BaseModel):
    """Uma moto que este cliente comprou da loja — aba "comprou" na tela dele."""

    venda_id: uuid.UUID
    moto: MotoNoHistorico
    data_venda: Utc
    preco_venda_centavos: int
    forma_pagamento: FormaPagamento
    parcelado: bool
    qtd_parcelas: int
    qtd_parcelas_pagas: int
    saldo_devedor_centavos: int

    # A lista inteira, paga e a pagar: é o que o dono aponta na tela quando o
    # cliente pergunta "quanto já paguei?".
    parcelas: list[ParcelaSaida]


class ClienteDetalhe(ClienteSaida):
    deve_parcela: bool
    saldo_devedor_centavos: int
    saldo_atrasado_centavos: int
    comprou: list[VendaDoCliente]
    vendeu: list[CompraDoCliente]
