"""Painel financeiro do dono: quanto entrou, quanto saiu, quanto falta entrar."""

import enum
import uuid
from datetime import date

from pydantic import BaseModel


class ResumoFinanceiroMes(BaseModel):
    ano: int
    mes: int

    # Tudo que entrou de fato no caixa no mês: vendas à vista/financiadas/por
    # consórcio, a entrada das vendas parceladas, e toda parcela paga no
    # período — não importa de qual venda a parcela veio.
    entrou_centavos: int

    gasto_compra_motos_centavos: int
    gasto_arrumacao_centavos: int

    # Saldo de parcelas em aberto **hoje**, de qualquer venda — não é "do
    # mês", é o que ainda falta entrar no caixa inteiro.
    a_receber_centavos: int

    # Dinheiro que andou por fora das vendas, lançado à mão. Separado dos
    # outros totais porque responde outra pergunta: "o que eu tirei e pus no
    # caixa este mês", que não é venda nem gasto de moto.
    entradas_caixa_centavos: int = 0
    saidas_caixa_centavos: int = 0

    lucro_centavos: int
    qtd_vendas: int
    qtd_motos_compradas: int


class TipoMovimento(str, enum.Enum):
    VENDA = "VENDA"
    PARCELA = "PARCELA"
    COMPRA = "COMPRA"
    GASTO = "GASTO"

    # Dinheiro que entrou ou saiu por fora das vendas, lançado à mão pelo
    # dono: aluguel, troco na gaveta, serviço avulso. Ver `models/caixa.py`.
    ENTRADA_CAIXA = "ENTRADA_CAIXA"
    SAIDA_CAIXA = "SAIDA_CAIXA"


class Movimento(BaseModel):
    """Uma linha do "o que aconteceu no dia": dinheiro que entrou ou saiu."""

    dia: date
    tipo: TipoMovimento
    descricao: str
    entrada_centavos: int
    saida_centavos: int

    # De onde a linha veio, quando dá pra agir sobre ela. Hoje só o
    # lançamento à mão usa: é por este id que o botão de estornar sabe o que
    # desfazer. Casar por valor e descrição não serviria — dois lançamentos
    # iguais no mesmo dia são comuns (duas retiradas de R$ 50 pra almoço).
    origem_id: uuid.UUID | None = None


class DiaFinanceiro(BaseModel):
    dia: date
    entrou_centavos: int
    saiu_centavos: int
    saldo_centavos: int
    movimentos: list[Movimento]


class FinanceiroMes(ResumoFinanceiroMes):
    """A tela FINANCEIRO inteira: o resumo do mês e, embaixo, cada dia que
    teve movimento, do mais recente pro mais antigo."""

    qtd_parcelas_recebidas: int

    # Venda − compra − gastos de cada moto vendida no mês. Moto vendida sem
    # valor de compra lançado fica de fora — e é contada à parte, pra tela
    # avisar que o número está incompleto em vez de mostrar um lucro inflado.
    lucro_vendas_centavos: int
    qtd_vendas_sem_custo: int

    dias: list[DiaFinanceiro]


class MovimentoDiario(BaseModel):
    dia: date
    entrou_centavos: int
    gasto_centavos: int
    qtd_vendas: int
    qtd_compras: int
