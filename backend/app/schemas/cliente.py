"""Cliente e o histórico dele com a loja (o que comprou, o que vendeu).

**"Comprou" e "vendeu" são do ponto de vista do cliente**, que é como o dono
fala: "comprou" é moto que saiu da loja pra ele (uma `Venda`), "vendeu" é
moto que ele trouxe e a loja pagou (uma `Moto` com ele de fornecedor). Os
dois nomes aparecem assim nas abas da tela dele.
"""

import uuid
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models.venda import FormaPagamento
from app.schemas.parcela import ParcelaSaida
from app.schemas.tipos import Utc
from app.schemas.validadores import (
    validar_cep,
    validar_cpf,
    validar_cpf_opcional,
    validar_email,
    validar_nascimento,
    validar_observacao,
    validar_rg,
    validar_telefone,
    validar_texto_nao_vazio,
    validar_uf,
)

_Nome = Annotated[
    str, Field(min_length=1, max_length=120), AfterValidator(validar_texto_nao_vazio)
]
_Cpf = Annotated[str, AfterValidator(validar_cpf)]
_Telefone = Annotated[str, Field(max_length=20), AfterValidator(validar_telefone)]
_Observacao = Annotated[str, Field(max_length=1000), AfterValidator(validar_observacao)]
_Email = Annotated[str, Field(max_length=120), AfterValidator(validar_email)]
_Uf = Annotated[str, Field(max_length=2), AfterValidator(validar_uf)]
_Cep = Annotated[str, Field(max_length=10), AfterValidator(validar_cep)]


class _ComDocumentos(BaseModel):
    """RG e nascimento — o que, junto do CPF, qualifica a pessoa no contrato.

    Os dois são opcionais: o balcão cadastra com o que tem na mão. O sistema
    antigo da loja guardava ambos, e é por isso que eles existem aqui.
    """

    rg: Annotated[str, Field(max_length=20), AfterValidator(validar_rg)] | None = None
    nascimento: Annotated[date, AfterValidator(validar_nascimento)] | None = None


class _ComEndereco(BaseModel):
    """E-mail e endereço, iguais no cadastro e na edição.

    Tudo opcional: o dono cadastra na pressa do balcão e completa depois. O
    que não é opcional é estar *certo* quando vem preenchido — UF que não
    existe e CEP de 7 dígitos entram calados e só aparecem no dia em que o
    contrato sai errado.
    """

    email: _Email | None = None
    endereco: Annotated[str, Field(max_length=160)] | None = None
    numero: Annotated[str, Field(max_length=20)] | None = None
    complemento: Annotated[str, Field(max_length=80)] | None = None
    bairro: Annotated[str, Field(max_length=80)] | None = None
    cidade: Annotated[str, Field(max_length=80)] | None = None
    uf: _Uf | None = None
    cep: _Cep | None = None


class _ComConjuge(BaseModel):
    """Estado civil + cônjuge, com a regra que vale nos dois sentidos.

    Casado: nome e telefone do cônjuge são obrigatórios — é por eles que a
    loja acha a família quando o titular some. CPF do cônjuge é opcional,
    porque nem sempre o documento dele está na mão na hora do cadastro.
    """

    casado: bool | None = None
    conjuge_nome: Annotated[str, Field(max_length=120)] | None = None
    conjuge_cpf: Annotated[str, AfterValidator(validar_cpf_opcional)] | None = None
    conjuge_telefone: _Telefone | None = None

    @model_validator(mode="after")
    def _conjuge_completo(self):
        if self.casado:
            if not (self.conjuge_nome or "").strip():
                raise ValueError("Casado: informe o nome do cônjuge")
            if not (self.conjuge_telefone or "").strip():
                raise ValueError("Casado: informe o telefone do cônjuge")
        return self


class EnderecoDoCliente(BaseModel):
    """O endereço do cliente do jeito que o contrato precisa dele.

    Vai junto na venda (e não só na tela do cliente) porque contrato de compra
    e venda sem endereço do comprador é fraco justo onde ele precisa valer.
    Objeto separado, montado com `model_validate`, pra que campo novo de
    endereço chegue ao documento sem alguém lembrar de mexer no `_saida()`.
    """

    rg: str | None = None
    nascimento: date | None = None
    email: str | None = None
    endereco: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None

    model_config = {"from_attributes": True}


class ClienteEntrada(_ComConjuge, _ComEndereco, _ComDocumentos):
    nome: _Nome
    cpf: _Cpf
    telefone: _Telefone | None = None
    observacao: _Observacao | None = None


class ClientePatch(_ComConjuge, _ComEndereco, _ComDocumentos):
    nome: _Nome | None = None
    telefone: _Telefone | None = None
    observacao: _Observacao | None = None


class ClienteSaida(BaseModel):
    id: int
    nome: str
    cpf: str
    telefone: str | None
    casado: bool | None = None
    conjuge_nome: str | None = None
    conjuge_cpf: str | None = None
    conjuge_telefone: str | None = None
    rg: str | None = None
    nascimento: date | None = None
    email: str | None = None
    endereco: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None
    observacao: str | None = None
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


class PaginaDeClientes(BaseModel):
    """Uma página da lista, com o total que deu na busca.

    O total vai junto porque sem ele a tela não sabe dizer "50 de 1.686" — e
    uma lista cortada em silêncio faria o dono jurar que o cliente não está
    cadastrado.
    """

    clientes: list[ClienteResumo]
    total: int
    pagina: int
    por_pagina: int


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
