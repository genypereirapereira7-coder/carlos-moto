import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models.venda import FormaPagamento
from app.schemas.moto import MotoSaida
from app.schemas.parcela import ParcelaSaida
from app.schemas.tipos import Utc
from app.schemas.validadores import validar_datahora_nao_no_futuro


class VendaEntrada(BaseModel):
    # Gerado no aparelho do vendedor: o mesmo `id_cliente` reenviado (duplo
    # toque, conexão lenta) devolve a venda que já existe em vez de tentar
    # vender a moto de novo. Não confundir com `cliente_id` — este é o
    # identificador da *tentativa de venda*, não da pessoa.
    id_cliente: uuid.UUID
    moto_id: int
    cliente_id: int
    forma_pagamento: FormaPagamento
    # `gt=0`: moto dada de graça não é venda — é o preço que ficou por
    # preencher.
    preco_venda_centavos: int = Field(gt=0)

    data_venda: Annotated[datetime, AfterValidator(validar_datahora_nao_no_futuro)] | None = None

    # Só fazem sentido (e só são exigidos) quando `forma_pagamento ==
    # PARCELADO` — ver validação abaixo.
    numero_parcelas: int | None = Field(default=None, ge=1, le=60)
    valor_entrada_centavos: int = Field(default=0, ge=0)
    primeiro_vencimento: date | None = None

    @model_validator(mode="after")
    def _parcelado_exige_parcelas(self) -> "VendaEntrada":
        if self.forma_pagamento == FormaPagamento.PARCELADO:
            if not self.numero_parcelas:
                raise ValueError("Venda parcelada precisa do número de parcelas")
            # `>=`, não `>`: entrada igual ao preço não sobra nada pra
            # parcelar — geraria um carnê de parcelas de R$ 0,00. Quem paga
            # tudo na entrada está fazendo uma venda à vista.
            if self.valor_entrada_centavos >= self.preco_venda_centavos:
                raise ValueError(
                    "A entrada não pode ser maior nem igual ao preço — nesse caso a venda é à vista"
                )
        return self


class VendaSaida(BaseModel):
    id: uuid.UUID
    moto: MotoSaida
    vendedor_id: int
    vendedor_nome: str
    cliente_id: int
    cliente_nome: str
    cliente_cpf: str
    cliente_telefone: str | None
    forma_pagamento: FormaPagamento
    preco_venda_centavos: int
    data_venda: Utc
    criado_em: Utc
    parcelas: list[ParcelaSaida]
    saldo_devedor_centavos: int
