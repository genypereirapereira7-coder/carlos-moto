"""Painel financeiro do dono: o mês em números e o dia a dia."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencias import SessaoDep, SoDono
from app.schemas.financeiro import FinanceiroMes, MovimentoDiario, ResumoFinanceiroMes
from app.servicos import financeiro as servico

rotas = APIRouter(prefix="/financeiro", tags=["financeiro"])

# Validados aqui e não deixados pro `date(ano, mes, 1)` lá dentro: mês 13
# virava erro 500 em vez de uma mensagem dizendo o que está errado.
_Ano = Annotated[int, Query(ge=2000, le=2100)]
_Mes = Annotated[int, Query(ge=1, le=12)]


@rotas.get("/mes", response_model=FinanceiroMes)
async def mes_completo(ano: _Ano, mes: _Mes, sessao: SessaoDep, _: SoDono):
    """A tela FINANCEIRO: resumo do mês e o dia a dia, numa chamada só."""
    return await servico.do_mes(sessao, ano, mes)


@rotas.get("/resumo-mes", response_model=ResumoFinanceiroMes)
async def resumo_mes(ano: _Ano, mes: _Mes, sessao: SessaoDep, _: SoDono):
    return await servico.resumo_mes(sessao, ano, mes)


@rotas.get("/diario", response_model=MovimentoDiario)
async def diario(dia: date, sessao: SessaoDep, _: SoDono):
    return await servico.movimento_diario(sessao, dia)
