"""Estoque: leitura pra vendedor e dono, escrita só pro dono."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.dependencias import SessaoDep, SoDono, SoVendedor
from app.models.moto import CondicaoMoto, Moto
from app.schemas.despesa import DespesaEntrada, DespesaSaida
from app.schemas.moto import (
    MotoEntrada,
    MotoHistorico,
    MotoPatch,
    MotoSaida,
    MotoVitrine,
    VendaDaMoto,
)
from app.servicos import motos as servico
from app.servicos.eventos import Evento, publicar_apos_commit

rotas = APIRouter(prefix="/motos", tags=["motos"])


def _historico(moto: Moto) -> MotoHistorico:
    """Monta o detalhe completo por placa: compra, gastos, venda e o lucro
    entre eles. Lucro é sempre contra o custo (compra + gastos) — é a conta
    que responde "quanto rendeu sobre o que botei nessa moto", não sobre o
    preço de venda."""
    total_gastos = sum(d.valor_centavos for d in moto.despesas)
    custo_total = (
        moto.valor_compra_centavos + total_gastos if moto.valor_compra_centavos is not None else None
    )

    venda_saida = None
    lucro_centavos = None
    lucro_percentual = None
    if moto.venda is not None:
        v = moto.venda
        venda_saida = VendaDaMoto(
            venda_id=v.id,
            cliente_id=v.cliente_id,
            cliente_nome=v.cliente.nome,
            cliente_cpf=v.cliente.cpf,
            forma_pagamento=v.forma_pagamento,
            parcelado=v.parcelado,
            preco_venda_centavos=v.preco_venda_centavos,
            data_venda=v.data_venda,
            parcelas=list(v.parcelas),
            saldo_devedor_centavos=v.saldo_devedor_centavos,
        )
        if custo_total is not None:
            lucro_centavos = v.preco_venda_centavos - custo_total
            if custo_total > 0:
                lucro_percentual = round(lucro_centavos / custo_total * 100, 2)

    fornecedor_nome_efetivo = moto.fornecedor.nome if moto.fornecedor else moto.fornecedor_nome

    return MotoHistorico(
        **MotoSaida.model_validate(moto).model_dump(),
        fornecedor_nome_efetivo=fornecedor_nome_efetivo,
        despesas=[DespesaSaida.model_validate(d) for d in moto.despesas],
        total_gastos_centavos=total_gastos,
        venda=venda_saida,
        lucro_centavos=lucro_centavos,
        lucro_percentual=lucro_percentual,
    )


@rotas.get("", response_model=list[MotoSaida])
async def listar(
    sessao: SessaoDep,
    _: SoDono,
    condicao: CondicaoMoto | None = None,
    marca: str | None = None,
    modelo: str | None = None,
):
    """Estoque inteiro, disponível e vendida — é a tela do dono."""
    return await servico.listar(sessao, condicao=condicao, marca=marca, modelo=modelo)


@rotas.get("/disponiveis", response_model=list[MotoVitrine])
async def disponiveis(
    sessao: SessaoDep,
    _: SoVendedor,
    condicao: CondicaoMoto | None = None,
    marca: str | None = None,
    modelo: str | None = None,
):
    """A vitrine do vendedor — só o que ainda pode ser vendido."""
    return await servico.listar(
        sessao, somente_disponivel=True, condicao=condicao, marca=marca, modelo=modelo
    )


@rotas.get("/por-placa/{placa}", response_model=MotoHistorico)
async def por_placa(placa: str, sessao: SessaoDep, _: SoDono):
    """A busca da tela MOTOS: digita a placa, sai o histórico inteiro."""
    moto = await servico.por_placa(sessao, placa)
    if moto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma moto com essa placa")
    return _historico(moto)


@rotas.get("/{moto_id}/vitrine", response_model=MotoVitrine)
async def detalhe_para_vender(moto_id: int, sessao: SessaoDep, _: SoVendedor):
    """A moto como o vendedor precisa vê-la pra fechar a venda.

    Existe separada de `/{moto_id}` porque aquela devolve o histórico
    completo — custo, gastos e lucro —, que é informação do dono.
    """
    moto = await sessao.get(Moto, moto_id)
    if moto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moto não existe")
    return moto


@rotas.get("/{moto_id}", response_model=MotoHistorico)
async def detalhe(moto_id: int, sessao: SessaoDep, _: SoDono):
    """Histórico completo — compra, gastos, venda e lucro. Só o dono.

    Era `SoVendedor` e entregava o custo e a margem de cada moto pra quem
    vendia. O vendedor usa `/{moto_id}/vitrine`.
    """
    moto = await sessao.get(Moto, moto_id)
    if moto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moto não existe")
    return _historico(moto)


@rotas.post("", response_model=MotoSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar(dados: MotoEntrada, sessao: SessaoDep, dono: SoDono):
    """Cadastro rápido — placa, modelo, ano. O resto se completa depois, com
    um PATCH."""
    moto = Moto(**dados.model_dump(), criado_por=dono.usuario_id)
    sessao.add(moto)
    try:
        await sessao.flush()
    except IntegrityError as erro:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe uma moto com esse chassi ou placa"
        ) from erro

    saida = MotoSaida.model_validate(moto)
    await publicar_apos_commit(sessao, Evento.MOTO_CADASTRADA, saida.model_dump(mode="json"))
    return saida


@rotas.patch("/{moto_id}", response_model=MotoSaida)
async def editar(moto_id: int, dados: MotoPatch, sessao: SessaoDep, _: SoDono):
    moto = await sessao.get(Moto, moto_id)
    if moto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moto não existe")

    campos = dados.model_dump(exclude_unset=True)
    try:
        await servico.editar(sessao, moto, campos)
    except servico.MotoJaVendida as erro:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Essa moto já foi vendida — não dá pra editar"
        ) from erro
    except servico.PlacaObrigatoria as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Placa é obrigatória") from erro
    except servico.CompraIncompleta as erro:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Valor e data da compra andam juntos — preencha os dois",
        ) from erro
    except IntegrityError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, "Placa já usada por outra moto") from erro

    saida = MotoSaida.model_validate(moto)
    await publicar_apos_commit(sessao, Evento.MOTO_ATUALIZADA, saida.model_dump(mode="json"))
    return saida


@rotas.post(
    "/{moto_id}/despesas", response_model=DespesaSaida, status_code=status.HTTP_201_CREATED
)
async def lancar_despesa(moto_id: int, dados: DespesaEntrada, sessao: SessaoDep, dono: SoDono):
    """Lança um gasto de arrumação nesta moto — mecânica, revisão, guincho."""
    moto = await sessao.get(Moto, moto_id)
    if moto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Moto não existe")

    despesa, criada = await servico.lancar_despesa(sessao, moto, dados, dono.usuario_id)
    saida = DespesaSaida.model_validate(despesa)
    # Reenvio do mesmo gasto não republica o evento: a tela já mostrou este
    # lançamento da primeira vez, e um segundo aviso faria parecer que
    # entrou dinheiro novo.
    if criada:
        await publicar_apos_commit(
            sessao, Evento.DESPESA_LANCADA, {"moto_id": moto_id, **saida.model_dump(mode="json")}
        )
    return saida
