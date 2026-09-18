"""Campo de observação — anotação livre em moto, cliente e venda.

É o que não cabe em campo nenhum ("riscado no tanque", "volta dia 10 pra
transferência"). Fica no sistema pro dono; não sai em contrato nem
comprovante.
"""

import uuid


async def test_moto_guarda_observacao(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/motos", json={
        "marca": "Honda", "modelo": "Biz 125", "ano": 2026, "placa": "OBS1234",
        "condicao": "USADA", "km": 100, "preco_centavos": 1_000_000,
        "observacao": "  Riscado no tanque do lado direito.  ",
    }, headers=dono)
    assert r.status_code == 201, r.text
    # Espaço das pontas some — o que fica é o texto.
    assert r.json()["observacao"] == "Riscado no tanque do lado direito."


async def test_cliente_guarda_observacao(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json={
        "nome": "Zé Observado", "cpf": "111.444.777-35",
        "observacao": "Prefere ser chamado no WhatsApp.",
    }, headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["observacao"] == "Prefere ser chamado no WhatsApp."


async def test_venda_guarda_observacao(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json={
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_000_000,
        "observacao": "Leva o capacete junto.",
    }, headers=vendedor)
    assert r.status_code == 201, r.text
    assert r.json()["observacao"] == "Leva o capacete junto."


async def test_observacao_so_de_espaco_vira_vazio(cliente, dados, entrar):
    """Campo com um espaço não é anotação — não pode virar linha em branco
    que parece que alguém escreveu algo."""
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json={
        "nome": "Sem Nota", "cpf": "07418529694", "observacao": "   ",
    }, headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["observacao"] is None


async def test_editar_moto_adiciona_observacao_depois(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"observacao": "Cliente pediu pra guardar até sexta."},
        headers=dono,
    )
    assert r.status_code == 200, r.text
    assert r.json()["observacao"] == "Cliente pediu pra guardar até sexta."
