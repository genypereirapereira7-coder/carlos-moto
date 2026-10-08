"""Entrada e saída de dinheiro no caixa, lançadas à mão."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.models.caixa import TipoCaixa
from app.schemas.tipos import Utc
from app.schemas.validadores import validar_nao_no_futuro, validar_texto_nao_vazio


class MovimentoCaixaEntrada(BaseModel):
    tipo: TipoCaixa

    # `gt=0`: o que diz se soma ou subtrai é o tipo, nunca o sinal do valor.
    valor_centavos: int = Field(gt=0)

    # Obrigatória: "saiu R$ 300" sem dizer do quê é o lançamento que ninguém
    # consegue explicar no fechamento do mês.
    descricao: Annotated[
        str, Field(min_length=1, max_length=200), AfterValidator(validar_texto_nao_vazio)
    ]

    # O dia em que o dinheiro andou, não o dia do lançamento. Em branco = hoje.
    # Não aceita futuro: caixa é o que já aconteceu.
    dia: Annotated[date, AfterValidator(validar_nao_no_futuro)] | None = None


class EstornoEntrada(BaseModel):
    motivo: Annotated[str, Field(max_length=200)] | None = None


class MovimentoCaixaSaida(BaseModel):
    id: uuid.UUID
    tipo: TipoCaixa
    valor_centavos: int
    descricao: str
    ocorrido_em: Utc
    estornado_em: Utc | None = None
    motivo_estorno: str | None = None
    autor_nome: str | None = None
    criado_em: Utc

    model_config = {"from_attributes": True}


class CaixaDoDia(BaseModel):
    """O fechamento de um dia: o que entrou, o que saiu, e o que tem que estar
    na gaveta. Começa do zero toda manhã — não é saldo acumulado."""

    dia: date
    entrou_centavos: int
    saiu_centavos: int
    saldo_centavos: int
    movimentos: list["LinhaDeCaixa"]


class LinhaDeCaixa(BaseModel):
    """Uma linha do caixa — venda, parcela recebida, gasto ou lançamento à mão."""

    tipo: str
    descricao: str
    entrada_centavos: int
    saida_centavos: int
    # Só os lançamentos à mão podem ser estornados daqui; nos outros o estorno
    # é na própria parcela ou na venda.
    movimento_id: uuid.UUID | None = None
    estornado: bool = False
