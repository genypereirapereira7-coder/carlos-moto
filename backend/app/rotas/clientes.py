"""Cadastro e consulta de clientes — quem compra da loja e quem vende pra ela."""

from fastapi import APIRouter, HTTPException, status

from app.dependencias import SessaoDep, SoDono, SoVendedor
from app.models.cliente import Cliente
from app.schemas.cliente import (
    ClienteDetalhe,
    ClienteEntrada,
    ClientePatch,
    ClienteResumo,
    ClienteSaida,
    CompraDoCliente,
    MotoNoHistorico,
    VendaDoCliente,
)
from app.servicos import clientes as servico
from app.servicos.eventos import Evento, publicar_apos_commit

rotas = APIRouter(prefix="/clientes", tags=["clientes"])


@rotas.get("", response_model=list[ClienteResumo])
async def listar(sessao: SessaoDep, _: SoVendedor, busca: str | None = None):
    """Busca por nome ou CPF. A mesma rota serve a lista da tela CLIENTES e o
    passo "escolher cliente" na hora de registrar uma venda."""
    return [
        ClienteResumo(
            **ClienteSaida.model_validate(resumo.cliente).model_dump(),
            deve_parcela=resumo.deve_parcela,
            saldo_devedor_centavos=resumo.saldo_devedor_centavos,
            saldo_atrasado_centavos=resumo.saldo_atrasado_centavos,
            qtd_comprou=resumo.qtd_comprou,
            qtd_vendeu=resumo.qtd_vendeu,
        )
        for resumo in await servico.listar(sessao, busca=busca)
    ]


@rotas.post("", response_model=ClienteSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar(dados: ClienteEntrada, sessao: SessaoDep, _: SoVendedor):
    try:
        cliente = await servico.criar(sessao, dados)
    except servico.CpfDuplicado as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe cliente com esse CPF") from erro

    saida = ClienteSaida.model_validate(cliente)
    await publicar_apos_commit(sessao, Evento.CLIENTE_CADASTRADO, saida.model_dump(mode="json"))
    return saida


@rotas.patch("/{cliente_id}", response_model=ClienteSaida)
async def editar(cliente_id: int, dados: ClientePatch, sessao: SessaoDep, _: SoDono):
    cliente = await sessao.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não existe")
    await servico.editar(sessao, cliente, dados.model_dump(exclude_unset=True))
    return ClienteSaida.model_validate(cliente)


@rotas.get("/{cliente_id}", response_model=ClienteDetalhe)
async def detalhe(cliente_id: int, sessao: SessaoDep, _: SoDono):
    """Abre o cadastro do cliente: o que ele comprou da loja (aba "comprou")
    e o que vendeu pra ela (aba "vendeu"), com o sinal de parcela em aberto."""
    cliente = await sessao.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não existe")

    comprou = [
        VendaDoCliente(
            venda_id=v.id,
            moto=MotoNoHistorico.model_validate(v.moto),
            data_venda=v.data_venda,
            preco_venda_centavos=v.preco_venda_centavos,
            forma_pagamento=v.forma_pagamento,
            parcelado=v.parcelado,
            qtd_parcelas=len(v.parcelas),
            qtd_parcelas_pagas=sum(1 for p in v.parcelas if p.pago_em is not None),
            saldo_devedor_centavos=v.saldo_devedor_centavos,
            parcelas=list(v.parcelas),
        )
        for v in sorted(cliente.vendas, key=lambda v: v.data_venda, reverse=True)
    ]

    motos_fornecidas = await servico.motos_compradas_de(sessao, cliente_id)
    vendeu = [
        CompraDoCliente(
            moto=MotoNoHistorico.model_validate(m),
            data_compra=m.data_compra,
            valor_compra_centavos=m.valor_compra_centavos,
        )
        for m in motos_fornecidas
    ]

    saldo = await servico.saldo_devedor(sessao, cliente_id)
    atrasado = await servico.saldo_atrasado(sessao, cliente_id)
    return ClienteDetalhe(
        **ClienteSaida.model_validate(cliente).model_dump(),
        deve_parcela=saldo > 0,
        saldo_devedor_centavos=saldo,
        saldo_atrasado_centavos=atrasado,
        comprou=comprou,
        vendeu=vendeu,
    )
