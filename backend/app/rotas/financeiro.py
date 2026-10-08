"""Painel financeiro do dono: o mês em números, o dia a dia e o caixa."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencias import SessaoDep, SoDono
from app.models.base import hoje
from app.schemas.caixa import (
    CaixaDoDia,
    EstornoEntrada,
    MovimentoCaixaEntrada,
    MovimentoCaixaSaida,
)
from app.schemas.financeiro import FinanceiroMes, MovimentoDiario, ResumoFinanceiroMes
from app.servicos import caixa as servico_caixa
from app.servicos import financeiro as servico
from app.servicos.eventos import Evento, publicar_apos_commit

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


# ----------------------------------------------------------------- caixa


def _saida(movimento) -> MovimentoCaixaSaida:
    return MovimentoCaixaSaida(
        **{
            c: getattr(movimento, c)
            for c in ("id", "tipo", "valor_centavos", "descricao", "ocorrido_em",
                      "estornado_em", "motivo_estorno", "criado_em")
        },
        autor_nome=movimento.autor.nome if movimento.autor else None,
    )


@rotas.get("/caixa/hoje", response_model=CaixaDoDia)
async def caixa_de_hoje(sessao: SessaoDep, _: SoDono):
    """O caixa de hoje — começa do zero toda manhã.

    É a pergunta do fim da tarde: quanto tem que estar na gaveta agora.
    """
    return await servico_caixa.do_dia(sessao, hoje())


@rotas.get("/caixa/dia", response_model=CaixaDoDia)
async def caixa_do_dia(dia: date, sessao: SessaoDep, _: SoDono):
    """O caixa de um dia qualquer — é o que abre quando o dono toca no caixa
    de hoje pra ver o histórico."""
    return await servico_caixa.do_dia(sessao, dia)


@rotas.get("/caixa/lancamentos", response_model=list[MovimentoCaixaSaida])
async def lancamentos(
    sessao: SessaoDep,
    _: SoDono,
    de: date | None = None,
    ate: date | None = None,
):
    """Os lançamentos à mão do período, **inclusive os estornados** — é aqui
    que o dono procura aquele lançamento errado que ele desfez."""
    return [_saida(m) for m in await servico_caixa.listar(sessao, de=de, ate=ate)]


@rotas.post(
    "/caixa", response_model=MovimentoCaixaSaida, status_code=status.HTTP_201_CREATED
)
async def lancar(dados: MovimentoCaixaEntrada, sessao: SessaoDep, dono: SoDono):
    """Lança uma entrada ou saída de dinheiro no caixa."""
    movimento = await servico_caixa.registrar(
        sessao,
        tipo=dados.tipo,
        valor_centavos=dados.valor_centavos,
        descricao=dados.descricao,
        usuario_id=dono.usuario_id,
        dia=dados.dia,
    )
    saida = _saida(movimento)
    await publicar_apos_commit(
        sessao, Evento.CAIXA_LANCADO, saida.model_dump(mode="json")
    )
    return saida


@rotas.post("/caixa/{movimento_id}/estornar", response_model=MovimentoCaixaSaida)
async def estornar(
    movimento_id: uuid.UUID,
    dados: EstornoEntrada,
    sessao: SessaoDep,
    _: SoDono,
):
    """Desfaz um lançamento à mão. Ele sai da conta e fica no histórico
    marcado como estornado — nada é apagado."""
    try:
        movimento = await servico_caixa.estornar(sessao, movimento_id, dados.motivo)
    except servico_caixa.MovimentoInexistente as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lançamento não existe") from erro
    except servico_caixa.JaEstornado as erro:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este lançamento já foi estornado"
        ) from erro

    saida = _saida(movimento)
    await publicar_apos_commit(
        sessao, Evento.CAIXA_LANCADO, saida.model_dump(mode="json")
    )
    return saida
