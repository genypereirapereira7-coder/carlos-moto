"""Tela PARCELAS: só clientes com parcela em aberto, marcar como paga ou não."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencias import SessaoDep, SoDono
from app.models.cliente import Cliente
from app.models.moto import Moto
from app.models.parcela import Parcela
from app.models.venda import Venda
from app.schemas.parcela import MarcarPagaEntrada, ParcelaComCliente
from app.servicos import parcelas as servico
from app.servicos.eventos import Evento, publicar_apos_commit

rotas = APIRouter(prefix="/parcelas", tags=["parcelas"])


def _saida(parcela: Parcela, venda: Venda, cliente: Cliente, moto: Moto) -> ParcelaComCliente:
    return ParcelaComCliente(
        id=parcela.id,
        numero=parcela.numero,
        valor_centavos=parcela.valor_centavos,
        vencimento=parcela.vencimento,
        pago_em=parcela.pago_em,
        status=parcela.status,
        venda_id=venda.id,
        cliente_id=cliente.id,
        cliente_nome=cliente.nome,
        cliente_cpf=cliente.cpf,
        cliente_telefone=cliente.telefone,
        moto_marca=moto.marca,
        moto_modelo=moto.modelo,
        moto_placa=moto.placa,
    )


@rotas.get("", response_model=list[ParcelaComCliente])
async def listar(sessao: SessaoDep, _: SoDono):
    """Toda parcela ainda não paga — pendente ou atrasada — vencimento mais
    próximo primeiro. Quem não deve nada nem aparece aqui."""
    return [_saida(*linha) for linha in await servico.listar_pendentes(sessao)]


@rotas.patch("/{parcela_id}", response_model=ParcelaComCliente)
async def marcar(parcela_id: uuid.UUID, dados: MarcarPagaEntrada, sessao: SessaoDep, _: SoDono):
    """Marca (ou desmarca, se foi engano) uma parcela como paga."""
    try:
        parcela = await servico.marcar(sessao, parcela_id, dados.pago, dados.data_pagamento)
    except servico.ParcelaInexistente as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parcela não existe") from erro
    except servico.PagamentoAntesDaVenda as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A data do pagamento não pode ser antes da data da venda",
        ) from erro

    venda = parcela.venda
    saida = _saida(parcela, venda, venda.cliente, venda.moto)
    await publicar_apos_commit(sessao, Evento.PARCELA_ATUALIZADA, saida.model_dump(mode="json"))
    return saida
