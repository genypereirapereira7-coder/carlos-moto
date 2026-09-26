"""Registrar e consultar vendas."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencias import SessaoDep, SoDono, SoVendedor
from app.models.venda import Venda
from app.schemas.cliente import EnderecoDoCliente
from app.schemas.venda import VendaEntrada, VendaSaida
from app.servicos import vendas as servico
from app.servicos.eventos import Evento, hub

rotas = APIRouter(prefix="/vendas", tags=["vendas"])


def _saida(venda: Venda) -> VendaSaida:
    return VendaSaida(
        id=venda.id,
        moto=venda.moto,
        vendedor_id=venda.vendedor_id,
        vendedor_nome=venda.vendedor.nome,
        cliente_id=venda.cliente_id,
        cliente_nome=venda.cliente.nome,
        cliente_cpf=venda.cliente.cpf,
        cliente_telefone=venda.cliente.telefone,
        cliente_endereco=EnderecoDoCliente.model_validate(venda.cliente),
        forma_pagamento=venda.forma_pagamento,
        preco_venda_centavos=venda.preco_venda_centavos,
        valor_entrada_centavos=venda.valor_entrada_centavos,
        juros_centesimos=venda.juros_centesimos,
        observacao=venda.observacao,
        data_venda=venda.data_venda,
        criado_em=venda.criado_em,
        parcelas=list(venda.parcelas),
        avalistas=list(venda.avalistas),
        saldo_devedor_centavos=venda.saldo_devedor_centavos,
    )


@rotas.post("", response_model=VendaSaida, status_code=status.HTTP_201_CREATED)
async def registrar(dados: VendaEntrada, sessao: SessaoDep, ident: SoVendedor):
    """Vende uma moto. Recusa com 409 se ela já não estiver mais disponível —
    ver `servicos/vendas.py` pra como isso é garantido mesmo com dois toques
    simultâneos na mesma moto."""
    try:
        venda, criada = await servico.criar_venda(sessao, dados, ident.usuario_id)
    except servico.MotoJaVendida as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, "Essa moto já foi vendida") from erro
    except servico.MotoInexistente as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moto não existe") from erro
    except servico.ClienteInexistente as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não existe") from erro
    except servico.VendedorInvalido as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Vendedor inválido"
        ) from erro

    saida = _saida(venda)
    if criada:
        # Commit explícito e não `publicar_apos_commit`: aqui saem dois
        # eventos pro mesmo commit — a moto que sumiu da vitrine, e a venda
        # que entrou no painel do dono — e as duas publicações precisam do
        # mesmo estado já gravado.
        await sessao.commit()
        await hub.publicar(Evento.MOTO_VENDIDA, saida.moto.model_dump(mode="json"))
        await hub.publicar(Evento.VENDA_REGISTRADA, saida.model_dump(mode="json"))
    return saida


@rotas.get("", response_model=list[VendaSaida])
async def listar(sessao: SessaoDep, _: SoDono):
    """Todas as vendas, mais recente primeiro. Só o dono vê o total do negócio."""
    return [_saida(v) for v in await servico.listar(sessao)]


@rotas.get("/minhas", response_model=list[VendaSaida])
async def minhas(sessao: SessaoDep, ident: SoVendedor):
    """As vendas do próprio vendedor logado."""
    return [_saida(v) for v in await servico.listar(sessao, vendedor_id=ident.usuario_id)]


@rotas.get("/{venda_id}", response_model=VendaSaida)
async def obter(venda_id: uuid.UUID, sessao: SessaoDep, _: SoDono):
    """Uma venda inteira — com parcelas e avalistas. É o que a tela usa pra
    reimprimir o comprovante e o contrato depois, fora do momento da venda."""
    venda = await sessao.get(Venda, venda_id)
    if venda is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venda não existe")
    return _saida(venda)
