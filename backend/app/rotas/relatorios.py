"""Relatórios de vendas e estoque — restrito ao dono."""

from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.dependencias import SessaoDep, SoDono
from app.schemas.relatorio import ResumoEstoque, ResumoPeriodo, VendaPorVendedor
from app.servicos import relatorios as servico

rotas = APIRouter(prefix="/relatorios", tags=["relatorios"])


@rotas.get("/resumo", response_model=ResumoPeriodo)
async def resumo(data_inicio: date, data_fim: date, sessao: SessaoDep, _: SoDono):
    if data_fim < data_inicio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data_fim não pode vir antes de data_inicio")
    return await servico.resumo_periodo(sessao, data_inicio, data_fim)


@rotas.get("/por-vendedor", response_model=list[VendaPorVendedor])
async def por_vendedor(data_inicio: date, data_fim: date, sessao: SessaoDep, _: SoDono):
    if data_fim < data_inicio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data_fim não pode vir antes de data_inicio")
    return await servico.por_vendedor(sessao, data_inicio, data_fim)


@rotas.get("/estoque", response_model=ResumoEstoque)
async def estoque(sessao: SessaoDep, _: SoDono):
    return await servico.resumo_estoque(sessao)
