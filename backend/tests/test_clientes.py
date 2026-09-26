import uuid


async def test_cadastrar_e_buscar_por_cpf(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes",
        json={"nome": "José Pereira", "cpf": "111.444.777-35", "telefone": "11988887777"},
        headers=cabecalho,
    )
    assert resposta.status_code == 201
    assert resposta.json()["cpf"] == "11144477735"

    busca = await cliente.get("/clientes", params={"busca": "11144477735"}, headers=cabecalho)
    nomes = {c["nome"] for c in busca.json()["clientes"]}
    assert "José Pereira" in nomes


async def test_buscar_por_nome_parcial(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.get("/clientes", params={"busca": "mari"}, headers=cabecalho)
    assert resposta.status_code == 200
    assert any(c["nome"] == "Maria Souza" for c in resposta.json()["clientes"])


async def test_cpf_duplicado_da_409(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes",
        json={"nome": "Outra Maria", "cpf": dados["maria"].cpf},
        headers=cabecalho,
    )
    assert resposta.status_code == 409


async def test_detalhe_mostra_comprou_e_vendeu(cliente, dados, entrar):
    cabecalho_vendedor = await entrar(dados["joao"].id)
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
    # A data vai junto com o valor: desde que o gasto passou a cair no
    # financeiro no dia da compra, um sem o outro é recusado.
    compra = await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={
            "fornecedor_cliente_id": dados["maria"].id,
            "valor_compra_centavos": 850_000,
            "data_compra": "2026-07-15",
        },
        headers=cabecalho_dono,
    )
    assert compra.status_code == 200, compra.text

    detalhe = await cliente.get(f"/clientes/{dados['maria'].id}", headers=cabecalho_dono)
    assert detalhe.status_code == 200
    corpo = detalhe.json()
    assert len(corpo["comprou"]) == 1
    assert corpo["comprou"][0]["moto"]["id"] == dados["cg160"].id
    assert len(corpo["vendeu"]) == 1
    assert corpo["vendeu"][0]["moto"]["id"] == dados["factor"].id
    assert corpo["deve_parcela"] is False
