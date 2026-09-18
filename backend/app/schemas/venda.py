import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models.venda import COM_CARNE, COM_JUROS, FormaPagamento
from app.schemas.avalista import AvalistaEntrada, AvalistaSaida
from app.schemas.moto import MotoSaida
from app.schemas.parcela import ParcelaSaida
from app.schemas.tipos import Utc
from app.schemas.validadores import validar_datahora_nao_no_futuro, validar_observacao


class VendaEntrada(BaseModel):
    # Gerado no aparelho do vendedor: o mesmo `id_cliente` reenviado (duplo
    # toque, conexão lenta) devolve a venda que já existe em vez de tentar
    # vender a moto de novo. Não confundir com `cliente_id` — este é o
    # identificador da *tentativa de venda*, não da pessoa.
    id_cliente: uuid.UUID
    moto_id: int
    cliente_id: int

    # Quem fez a venda — Zé Carlos ou Dani. Opcional: quando não vem, fica com
    # quem está logado (o celular do dono resolvendo um atendimento). A tela do
    # dono manda sempre, porque lá quem opera é o dono em nome do vendedor.
    vendedor_id: int | None = None

    forma_pagamento: FormaPagamento
    # `gt=0`: moto dada de graça não é venda — é o preço que ficou por
    # preencher.
    preco_venda_centavos: int = Field(gt=0)

    data_venda: Annotated[datetime, AfterValidator(validar_datahora_nao_no_futuro)] | None = None

    # Só fazem sentido (e só são exigidos) nas formas com carnê (carnê da
    # loja e cheque pré-datado) — ver validação abaixo.
    numero_parcelas: int | None = Field(default=None, ge=1, le=60)
    valor_entrada_centavos: int = Field(default=0, ge=0)
    primeiro_vencimento: date | None = None

    # Juros da loja em centésimos de por cento (5,5% = 550). Teto de 100% pra
    # barrar o zero a mais digitado sem querer. Ver `COM_JUROS`.
    juros_centesimos: int = Field(default=0, ge=0, le=10_000)

    # Anotação livre sobre a venda. Não sai nos documentos.
    observacao: Annotated[str, Field(max_length=1000), AfterValidator(validar_observacao)] | None = None

    # No máximo três, e só em venda parcelada no carnê da loja: é o crédito da
    # própria loja que se avaliza. Ver validação abaixo.
    avalistas: list[AvalistaEntrada] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _parcelado_exige_parcelas(self) -> "VendaEntrada":
        if self.forma_pagamento in COM_CARNE:
            if not self.numero_parcelas:
                raise ValueError("Venda parcelada precisa do número de parcelas")
            # `>=`, não `>`: entrada igual ao preço não sobra nada pra
            # parcelar — geraria um carnê de parcelas de R$ 0,00. Quem paga
            # tudo na entrada está fazendo uma venda à vista.
            if self.valor_entrada_centavos >= self.preco_venda_centavos:
                raise ValueError(
                    "A entrada não pode ser maior nem igual ao preço — nesse caso a venda é à vista"
                )
        elif self.avalistas:
            # Avalista fora das formas com carnê não faz sentido: banco,
            # consórcio e cartão já pagaram a loja; à vista não há dívida.
            raise ValueError("Avalista só entra em venda no carnê da loja ou em cheque")

        if self.juros_centesimos and self.forma_pagamento not in COM_JUROS:
            raise ValueError("Essa forma de pagamento não tem juros da loja")
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
    valor_entrada_centavos: int = 0
    juros_centesimos: int = 0
    observacao: str | None = None
    data_venda: Utc
    criado_em: Utc
    parcelas: list[ParcelaSaida]
    avalistas: list[AvalistaSaida] = []
    saldo_devedor_centavos: int
