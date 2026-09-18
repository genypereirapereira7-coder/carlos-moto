import uuid
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models.moto import CondicaoMoto, StatusMoto
from app.models.venda import FormaPagamento
from app.schemas.despesa import DespesaSaida
from app.schemas.parcela import ParcelaSaida
from app.schemas.tipos import Utc
from app.schemas.validadores import (
    validar_ano,
    validar_chassi,
    validar_cpf_opcional,
    validar_email,
    validar_nao_no_futuro,
    validar_observacao,
    validar_placa,
    validar_placa_obrigatoria,
    validar_telefone,
    validar_texto_nao_vazio,
)

_Placa = Annotated[str, Field(max_length=8), AfterValidator(validar_placa)]
_PlacaObrigatoria = Annotated[str, Field(min_length=1, max_length=8), AfterValidator(validar_placa_obrigatoria)]
_Chassi = Annotated[str, Field(max_length=17), AfterValidator(validar_chassi)]
_Ano = Annotated[int, AfterValidator(validar_ano)]
_DataCompra = Annotated[date, AfterValidator(validar_nao_no_futuro)]

# Dados de quem vendeu a moto pra loja. Todos opcionais — entra o que a loja
# tiver na hora da compra —, mas o que vier preenchido é validado como
# qualquer outro campo do sistema.
_CpfOpcional = Annotated[str, AfterValidator(validar_cpf_opcional)]
_Email = Annotated[str, Field(max_length=120), AfterValidator(validar_email)]
_Contato = Annotated[str, Field(max_length=20), AfterValidator(validar_telefone)]

# Anotação livre do dono. Não sai em contrato nem comprovante.
_Observacao = Annotated[str, Field(max_length=1000), AfterValidator(validar_observacao)]


class MotoEntrada(BaseModel):
    """Cadastro: placa, modelo, ano. Marca, chassi e valores são completados
    depois, na edição, com calma — mas a placa não dá mais pra deixar pra lá:
    é ela que identifica a unidade de verdade, e o dono pediu que não desse
    pra cadastrar (nem salvar depois) uma moto sem ela."""

    modelo: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(validar_texto_nao_vazio)]
    ano: _Ano
    placa: _PlacaObrigatoria
    marca: str = Field(default="", max_length=60)
    cor: str | None = Field(default=None, max_length=40)
    condicao: CondicaoMoto = CondicaoMoto.USADA
    chassi: _Chassi | None = None
    km: int = Field(default=0, ge=0)
    preco_centavos: int = Field(default=0, ge=0)

    # Quanto a loja pagou e quando. Os dois juntos ou nenhum dos dois:
    # valor sem data não cai em mês nenhum do financeiro — vira um gasto
    # que existe no cadastro da moto e não existe no caixa.
    valor_compra_centavos: int | None = Field(default=None, gt=0)
    data_compra: _DataCompra | None = None

    # Quem vendeu a moto pra loja. Entra já no cadastro porque é nesse
    # momento que a compra acontece e o contrato é assinado — mas tudo
    # opcional, pra não travar o cadastro rápido de quem só quer pôr a moto
    # no estoque e completar depois.
    fornecedor_nome: str | None = Field(default=None, max_length=120)
    fornecedor_cpf: _CpfOpcional | None = None
    fornecedor_email: _Email | None = None
    fornecedor_contato: _Contato | None = None
    fornecedor_casado: bool | None = None
    fornecedor_conjuge_nome: str | None = Field(default=None, max_length=120)
    fornecedor_conjuge_contato: _Contato | None = None

    observacao: _Observacao | None = None

    @model_validator(mode="after")
    def _compra_completa(self) -> "MotoEntrada":
        if (self.valor_compra_centavos is None) != (self.data_compra is None):
            raise ValueError("Valor e data da compra andam juntos — preencha os dois")
        return self


class MotoPatch(BaseModel):
    """Edição de uma moto ainda disponível — é aqui que entram os dados
    financeiros que o cadastro rápido deixou de fora.

    Não tem `status` aqui de propósito: quem vende uma moto é a rota
    `POST /vendas`, não um PATCH direto — é ela que trava a linha e garante
    que a mesma moto não seja vendida duas vezes. Deixar o status editável
    por aqui abriria um segundo caminho pra marcar VENDIDA sem essa trava.
    """

    marca: Annotated[str, Field(min_length=1, max_length=60), AfterValidator(validar_texto_nao_vazio)] | None = None
    modelo: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(validar_texto_nao_vazio)] | None = None
    ano: _Ano | None = None
    cor: str | None = Field(default=None, max_length=40)
    condicao: CondicaoMoto | None = None
    chassi: _Chassi | None = None
    placa: _Placa | None = None
    km: int | None = Field(default=None, ge=0)
    preco_centavos: int | None = Field(default=None, ge=0)

    # Lado "compra" do histórico.
    valor_compra_centavos: int | None = Field(default=None, gt=0)
    data_compra: _DataCompra | None = None
    fornecedor_cliente_id: int | None = None
    fornecedor_nome: str | None = Field(default=None, max_length=120)

    # Quem vendeu a moto pra loja: o contrato de compra é assinado por essa
    # pessoa, então é aqui que entram CPF, e-mail e contato dela. Casado:
    # o cônjuge costuma assinar junto a venda de veículo.
    fornecedor_cpf: _CpfOpcional | None = None
    fornecedor_email: _Email | None = None
    fornecedor_contato: _Contato | None = None
    fornecedor_casado: bool | None = None
    fornecedor_conjuge_nome: str | None = Field(default=None, max_length=120)
    fornecedor_conjuge_contato: _Contato | None = None

    observacao: _Observacao | None = None


class MotoSaida(BaseModel):
    id: int
    marca: str
    modelo: str
    ano: int
    cor: str | None
    condicao: CondicaoMoto
    chassi: str | None
    placa: str | None
    km: int
    preco_centavos: int
    valor_compra_centavos: int | None
    data_compra: date | None
    fornecedor_cliente_id: int | None
    fornecedor_nome: str | None
    fornecedor_cpf: str | None = None
    fornecedor_email: str | None = None
    fornecedor_contato: str | None = None
    fornecedor_casado: bool | None = None
    fornecedor_conjuge_nome: str | None = None
    fornecedor_conjuge_contato: str | None = None
    observacao: str | None = None
    status: StatusMoto
    criado_em: Utc
    atualizado_em: Utc

    model_config = {"from_attributes": True}


class MotoVitrine(BaseModel):
    """A moto como o **vendedor** pode vê-la: o que ele precisa pra vender, e
    nada além disso.

    Fora daqui, de propósito: `valor_compra_centavos`, `data_compra`,
    `fornecedor_*` e qualquer conta de lucro. O que a loja pagou e com quem
    negociou é informação do dono — é a mesma razão pela qual a tela
    FINANCEIRO inteira exige papel DONO. Antes desta separação, `MotoSaida`
    ia inteira pro vendedor e entregava o custo de cada moto do estoque.
    """

    id: int
    marca: str
    modelo: str
    ano: int
    cor: str | None
    condicao: CondicaoMoto
    chassi: str | None
    placa: str | None
    km: int
    preco_centavos: int
    status: StatusMoto

    model_config = {"from_attributes": True}


class VendaDaMoto(BaseModel):
    """O lado "venda" do histórico de uma moto — só o que a tela MOTOS precisa
    mostrar; o histórico completo da venda (com parcelas) mora em
    `schemas.venda`."""

    venda_id: uuid.UUID
    cliente_id: int
    cliente_nome: str
    cliente_cpf: str
    forma_pagamento: FormaPagamento
    parcelado: bool
    preco_venda_centavos: int
    data_venda: Utc
    parcelas: list[ParcelaSaida]
    saldo_devedor_centavos: int


class MotoHistorico(MotoSaida):
    """Detalhe completo por placa: compra, gastos, venda e o lucro entre eles
    — a tela que abre quando o dono pesquisa uma moto pela placa."""

    fornecedor_nome_efetivo: str | None
    despesas: list[DespesaSaida]
    total_gastos_centavos: int
    venda: VendaDaMoto | None

    # `None` enquanto faltar compra ou venda pra calcular — lucro parcial
    # não é lucro, é só a metade de uma conta.
    lucro_centavos: int | None
    lucro_percentual: float | None
