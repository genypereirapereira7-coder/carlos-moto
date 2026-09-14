"""A lista da tela CLIENTES: CPF conferido de verdade, e cada linha já
sabendo quanto o cliente deve e quantas motos comprou e vendeu."""

import uuid


async def test_cpf_com_digito_verificador_errado_e_recusado(cliente, dados, entrar):
    """529.982.247-2**6** é o CPF da Maria com o último dígito trocado — o
    tipo de erro que acontece digitando de um documento na mão."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes", json={"nome": "Fulano", "cpf": "52998224726"}, headers=cabecalho
    )
    assert resposta.status_code == 422
    assert "CPF" in resposta.json()["detail"][0]["msg"]


async def test_cpf_com_digitos_repetidos_e_recusado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes", json={"nome": "Fulano", "cpf": "111.111.111-11"}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_telefone_guarda_so_os_digitos(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes",
        json={"nome": "Fulano", "cpf": "111.444.777-35", "telefone": "(11) 98888-7777"},
        headers=cabecalho,
    )
    assert resposta.status_code == 201
    assert resposta.json()["telefone"] == "11988887777"


async def test_telefone_que_nao_tem_numero_nenhum_e_recusado(cliente, dados, entrar):
    """Antes isto passava: a limpeza dos dígitos deixava a string vazia e o
    campo era gravado como "sem telefone", sem avisar ninguém."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes",
        json={"nome": "Fulano", "cpf": "111.444.777-35", "telefone": "não sei"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert "Telefone" in resposta.json()["detail"][0]["msg"]


async def test_telefone_em_branco_continua_valendo(cliente, dados, entrar):
    """Telefone segue opcional — quem não tem, não tem."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes",
        json={"nome": "Fulano", "cpf": "111.444.777-35", "telefone": "   "},
        headers=cabecalho,
    )
    assert resposta.status_code == 201
    assert resposta.json()["telefone"] is None


async def test_telefone_sem_ddd_e_recusado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/clientes",
        json={"nome": "Fulano", "cpf": "111.444.777-35", "telefone": "988887777"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422


async def test_lista_traz_saldo_e_contagens_de_cada_cliente(cliente, dados, entrar):
    """A Maria compra uma moto parcelada e vende outra pra loja: a linha dela
    tem que sair com as duas contagens e o saldo devedor."""
    cabecalho_vendedor = await entrar(dados["joao"].id)
    await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["cg160"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "PARCELADO",
            "preco_venda_centavos": 1_000_000,
            "numero_parcelas": 4,
            "valor_entrada_centavos": 200_000,
            "primeiro_vencimento": "2026-01-01",
        },
        headers=cabecalho_vendedor,
    )

    cabecalho_dono = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"fornecedor_cliente_id": dados["maria"].id},
        headers=cabecalho_dono,
    )

    lista = await cliente.get("/clientes", headers=cabecalho_dono)
    assert lista.status_code == 200
    maria = next(c for c in lista.json() if c["id"] == dados["maria"].id)

    assert maria["qtd_comprou"] == 1
    assert maria["qtd_vendeu"] == 1
    assert maria["deve_parcela"] is True
    assert maria["saldo_devedor_centavos"] == 800_000


async def test_quem_nao_deve_nada_vem_zerado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    lista = await cliente.get("/clientes", headers=cabecalho)
    maria = next(c for c in lista.json() if c["id"] == dados["maria"].id)

    assert maria["deve_parcela"] is False
    assert maria["saldo_devedor_centavos"] == 0
    assert maria["qtd_comprou"] == 0
    assert maria["qtd_vendeu"] == 0


async def test_detalhe_traz_as_parcelas_da_compra(cliente, dados, entrar):
    """O dono precisa apontar na tela quais parcelas o cliente já pagou."""
    cabecalho_vendedor = await entrar(dados["joao"].id)
    venda = await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["cg160"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "PARCELADO",
            "preco_venda_centavos": 900_000,
            "numero_parcelas": 3,
            "primeiro_vencimento": "2026-01-01",
        },
        headers=cabecalho_vendedor,
    )
    primeira = venda.json()["parcelas"][0]["id"]

    cabecalho_dono = await entrar(dados["carlos"].id)
    await cliente.patch(f"/parcelas/{primeira}", json={"pago": True}, headers=cabecalho_dono)

    detalhe = await cliente.get(f"/clientes/{dados['maria'].id}", headers=cabecalho_dono)
    compra = detalhe.json()["comprou"][0]

    assert len(compra["parcelas"]) == 3
    assert compra["qtd_parcelas_pagas"] == 1
    assert [p["status"] for p in compra["parcelas"]].count("PAGA") == 1
    assert detalhe.json()["saldo_devedor_centavos"] == 600_000
