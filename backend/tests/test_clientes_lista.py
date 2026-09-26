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
    maria = next(c for c in lista.json()["clientes"] if c["id"] == dados["maria"].id)

    assert maria["qtd_comprou"] == 1
    assert maria["qtd_vendeu"] == 1
    assert maria["deve_parcela"] is True
    assert maria["saldo_devedor_centavos"] == 800_000


async def test_quem_nao_deve_nada_vem_zerado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    lista = await cliente.get("/clientes", headers=cabecalho)
    maria = next(c for c in lista.json()["clientes"] if c["id"] == dados["maria"].id)

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


# ------------------------------------------------------------- por página

async def _muitos_clientes(cliente, cabecalho, quantos: int) -> None:
    """Cadastra `quantos` clientes com CPF válido, pra ter lista de verdade."""
    def cpf(n: int) -> str:
        base = f"{n:09d}"
        for _ in range(2):
            soma = sum(int(d) * (len(base) + 1 - i) for i, d in enumerate(base))
            resto = 11 - soma % 11
            base += "0" if resto > 9 else str(resto)
        return base

    for n in range(quantos):
        r = await cliente.post("/clientes", json={
            "nome": f"Cliente {n:04d}", "cpf": cpf(n + 1000),
        }, headers=cabecalho)
        assert r.status_code == 201, r.text


async def test_lista_vem_por_pagina_com_o_total(cliente, dados, entrar):
    """São 1.686 clientes depois da importação do sistema antigo: mandar todos
    numa resposta travava a tela do celular por dez segundos."""
    cabecalho = await entrar(dados["carlos"].id)
    await _muitos_clientes(cliente, cabecalho, 60)

    primeira = (await cliente.get("/clientes?por_pagina=25", headers=cabecalho)).json()
    assert len(primeira["clientes"]) == 25
    assert primeira["total"] >= 60          # os 60 + os do conftest
    assert primeira["pagina"] == 1

    segunda = (await cliente.get("/clientes?por_pagina=25&pagina=2", headers=cabecalho)).json()
    assert len(segunda["clientes"]) == 25
    assert segunda["total"] == primeira["total"]
    # Páginas diferentes, gente diferente — e a ordem é estável (por nome).
    assert not ({c["id"] for c in primeira["clientes"]}
                & {c["id"] for c in segunda["clientes"]})


async def test_pagina_alem_do_fim_vem_vazia_sem_erro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    r = await cliente.get("/clientes?pagina=9999", headers=cabecalho)
    assert r.status_code == 200
    assert r.json()["clientes"] == []
    assert r.json()["total"] >= 1


async def test_por_pagina_absurdo_e_contido(cliente, dados, entrar):
    """Pedir 100 mil de uma vez é o mesmo problema de antes, por outro caminho."""
    cabecalho = await entrar(dados["carlos"].id)
    r = await cliente.get("/clientes?por_pagina=100000", headers=cabecalho)
    assert r.json()["por_pagina"] == 200


async def test_busca_conta_todos_os_achados_nao_so_a_pagina(cliente, dados, entrar):
    """O número que a tela mostra ("50 de 330") é o total da busca. Se viesse
    só o tamanho da página, ela diria "50 de 50" e esconderia 280 pessoas."""
    cabecalho = await entrar(dados["carlos"].id)
    await _muitos_clientes(cliente, cabecalho, 60)
    r = (await cliente.get("/clientes?busca=Cliente&por_pagina=10", headers=cabecalho)).json()
    assert len(r["clientes"]) == 10
    assert r["total"] == 60


# ------------------------------------------------- filtro comprou/vendeu

async def test_filtro_comprou_e_do_servidor(cliente, dados, entrar):
    """Filtrar no navegador só olharia a página carregada, e diria "1 cliente
    que comprou" quando existem trezentos."""
    vendedor = await entrar(dados["joao"].id)
    venda = await cliente.post("/vendas", json={
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_000_000,
    }, headers=vendedor)
    assert venda.status_code == 201, venda.text

    cabecalho = await entrar(dados["carlos"].id)
    await _muitos_clientes(cliente, cabecalho, 60)

    r = (await cliente.get("/clientes?filtro=comprou&por_pagina=10", headers=cabecalho)).json()
    assert r["total"] == 1                      # e não 61
    assert r["clientes"][0]["id"] == dados["maria"].id
    assert r["clientes"][0]["qtd_comprou"] == 1


async def test_filtro_vendeu_acha_quem_trouxe_moto_pra_loja(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    patch = await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"fornecedor_cliente_id": dados["maria"].id},
        headers=cabecalho,
    )
    assert patch.status_code == 200, patch.text

    r = (await cliente.get("/clientes?filtro=vendeu", headers=cabecalho)).json()
    assert r["total"] == 1
    assert r["clientes"][0]["id"] == dados["maria"].id
    assert r["clientes"][0]["qtd_vendeu"] == 1


async def test_filtro_desconhecido_e_recusado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    r = await cliente.get("/clientes?filtro=qualquer", headers=cabecalho)
    assert r.status_code == 422
