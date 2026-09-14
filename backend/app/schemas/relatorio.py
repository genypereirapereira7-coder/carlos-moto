"""Schemas dos relatórios do dono. Todo dinheiro é inteiro em centavos."""

from datetime import date

from pydantic import BaseModel


class ResumoPeriodo(BaseModel):
    data_inicio: date
    data_fim: date
    qtd_vendas: int
    total_centavos: int
    ticket_medio_centavos: int


class VendaPorVendedor(BaseModel):
    vendedor_id: int
    nome: str
    qtd_vendas: int
    total_centavos: int


class ResumoEstoque(BaseModel):
    qtd_disponivel_novas: int
    qtd_disponivel_usadas: int
    valor_total_centavos: int
