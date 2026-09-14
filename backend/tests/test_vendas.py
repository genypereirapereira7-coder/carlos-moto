import asyncio
import uuid

from sqlalchemy import func, select

from app.models import Venda


def _corpo_venda(moto_id: int, cliente_id: int, id_cliente: str | None = None) -> dict:
    return {
        "id_cliente": id_cliente or str(uuid.uuid4()),
        "moto_id": moto_id,
        "cliente_id": cliente_id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_650_000,
    }


async def test_registrar_venda_marca_moto_vendida(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.post(
        "/vendas", json=_corpo_venda(dados["cg160"].id, dados["maria"].id), headers=cabecalho
    )
    assert resposta.status_code == 201
    assert resposta.json()["moto"]["status"] == "VENDIDA"

    disponiveis = await cliente.get("/motos/disponiveis", headers=cabecalho)
    ids = {m["id"] for m in disponiveis.json()}
    assert dados["cg160"].id not in ids


async def test_vender_moto_ja_vendida_da_409(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    primeira = await cliente.post(
        "/vendas", json=_corpo_venda(dados["cg160"].id, dados["maria"].id), headers=cabecalho
    )
    assert primeira.status_code == 201

    segunda = await cliente.post(
        "/vendas", json=_corpo_venda(dados["cg160"].id, dados["maria"].id), headers=cabecalho
    )
    assert segunda.status_code == 409
    assert "já foi vendida" in segunda.json()["detail"]


async def test_reenviar_mesmo_id_cliente_nao_duplica(cliente, dados, entrar):
    """Duplo toque numa rede lenta: o mesmo `id_cliente` reenviado devolve a
    venda que já existe, em vez de recusar ou vender de novo."""
    cabecalho = await entrar(dados["joao"].id)
    corpo = _corpo_venda(dados["cg160"].id, dados["maria"].id)

    primeira = await cliente.post("/vendas", json=corpo, headers=cabecalho)
    segunda = await cliente.post("/vendas", json=corpo, headers=cabecalho)

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.json()["id"] == segunda.json()["id"]


async def test_vender_moto_inexistente_da_404(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.post(
        "/vendas", json=_corpo_venda(999999, dados["maria"].id), headers=cabecalho
    )
    assert resposta.status_code == 404


async def test_duas_vendas_simultaneas_da_mesma_moto_so_uma_vence(cliente, dados, entrar, sessao):
    """O teste que importa: dois vendedores tentando vender a mesma moto ao
    mesmo tempo não podem os dois ganhar. Ver `servicos/vendas.py`."""
    cabecalho = await entrar(dados["joao"].id)

    respostas = await asyncio.gather(
        cliente.post(
            "/vendas",
            json=_corpo_venda(dados["cg160"].id, dados["maria"].id, str(uuid.uuid4())),
            headers=cabecalho,
        ),
        cliente.post(
            "/vendas",
            json=_corpo_venda(dados["cg160"].id, dados["maria"].id, str(uuid.uuid4())),
            headers=cabecalho,
        ),
    )

    codigos = sorted(r.status_code for r in respostas)
    assert codigos == [201, 409]

    total = (
        await sessao.execute(
            select(func.count(Venda.id)).where(Venda.moto_id == dados["cg160"].id)
        )
    ).scalar_one()
    assert total == 1
