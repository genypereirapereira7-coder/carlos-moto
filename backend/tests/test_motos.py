import uuid

import pytest


async def test_historico_por_placa_mostra_compra_venda_e_lucro(cliente, dados, entrar):
    """O caso de uso principal da tela MOTOS: pesquisar pela placa e ver
    compra, gastos, venda (com parcelas) e o lucro calculado, tudo junto."""
    import uuid

    cabecalho_dono = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000, "data_compra": "2026-07-01"},
        headers=cabecalho_dono,
    )
    await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "Revisão", "valor_centavos": 50_000, "data": "2026-07-10"},
        headers=cabecalho_dono,
    )

    cabecalho_vendedor = await entrar(dados["joao"].id)
    await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["factor"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "PARCELADO",
            "preco_venda_centavos": 1_150_000,
            "numero_parcelas": 2,
            "valor_entrada_centavos": 150_000,
            "primeiro_vencimento": "2026-08-01",
        },
        headers=cabecalho_vendedor,
    )

    historico = await cliente.get(
        f"/motos/por-placa/{dados['factor'].placa}", headers=cabecalho_dono
    )
    assert historico.status_code == 200
    corpo = historico.json()

    assert corpo["total_gastos_centavos"] == 50_000
    assert corpo["venda"]["parcelado"] is True
    assert corpo["venda"]["saldo_devedor_centavos"] == 1_000_000
    assert len(corpo["venda"]["parcelas"]) == 2
    # custo = 800_000 (compra) + 50_000 (gasto) = 850_000
    # lucro = 1_150_000 - 850_000 = 300_000
    assert corpo["lucro_centavos"] == 300_000
    assert corpo["lucro_percentual"] == pytest.approx(35.29, abs=0.01)


async def test_vendedor_ve_so_disponivel(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.get("/motos/disponiveis", headers=cabecalho)
    assert resposta.status_code == 200
    nomes = {m["modelo"] for m in resposta.json()}
    assert nomes == {"CG160 Titan", "Factor 125"}


async def test_dono_cadastra_moto(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos",
        json={
            "marca": "Honda",
            "modelo": "Biz 125",
            "ano": 2026,
            "placa": "BIZ1234",
            "cor": "Branca",
            "condicao": "NOVA",
            "chassi": "9C2KC0000RR999999",
            "km": 0,
            "preco_centavos": 1_200_000,
        },
        headers=cabecalho,
    )
    assert resposta.status_code == 201
    assert resposta.json()["status"] == "DISPONIVEL"


async def test_chassi_duplicado_e_recusado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos",
        json={
            "marca": "Honda",
            "modelo": "Outra",
            "ano": 2026,
            "placa": "OUT1234",
            "condicao": "NOVA",
            "chassi": dados["cg160"].chassi,
            "km": 0,
            "preco_centavos": 1_000_000,
        },
        headers=cabecalho,
    )
    assert resposta.status_code == 409


async def test_vendedor_nao_pode_cadastrar_moto(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.post(
        "/motos",
        json={
            "marca": "Honda",
            "modelo": "Pop 110",
            "ano": 2026,
            "placa": "POP1234",
            "condicao": "NOVA",
            "chassi": "9C2KC0000RR888888",
            "km": 0,
            "preco_centavos": 900_000,
        },
        headers=cabecalho,
    )
    assert resposta.status_code == 403


async def test_editar_moto_vendida_e_recusado(cliente, dados, entrar):
    cabecalho_vendedor = await entrar(dados["joao"].id)
    import uuid

    venda = await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["cg160"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "A_VISTA",
            "preco_venda_centavos": 1_650_000,
        },
        headers=cabecalho_vendedor,
    )
    assert venda.status_code == 201

    cabecalho_dono = await entrar(dados["carlos"].id)
    edicao = await cliente.patch(
        f"/motos/{dados['cg160'].id}",
        json={"preco_centavos": 1_500_000},
        headers=cabecalho_dono,
    )
    assert edicao.status_code == 409
