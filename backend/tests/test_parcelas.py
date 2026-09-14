import uuid
from datetime import date


def _corpo_venda_parcelada(moto_id: int, cliente_id: int) -> dict:
    return {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": moto_id,
        "cliente_id": cliente_id,
        "forma_pagamento": "PARCELADO",
        "preco_venda_centavos": 1_000_000,
        "numero_parcelas": 4,
        "valor_entrada_centavos": 200_000,
        "primeiro_vencimento": str(date(2020, 1, 1)),
    }


async def test_venda_parcelada_gera_parcelas_com_soma_correta(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.post(
        "/vendas", json=_corpo_venda_parcelada(dados["cg160"].id, dados["maria"].id), headers=cabecalho
    )
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert len(corpo["parcelas"]) == 4
    assert sum(p["valor_centavos"] for p in corpo["parcelas"]) == 800_000
    assert corpo["saldo_devedor_centavos"] == 800_000


async def test_parcela_vencida_aparece_como_devedora_na_tela_parcelas(cliente, dados, entrar):
    """Vencimento em 2020: já está atrasada — e é exatamente isso que a tela
    PARCELAS existe pra mostrar em vermelho."""
    cabecalho_vendedor = await entrar(dados["joao"].id)
    await cliente.post(
        "/vendas", json=_corpo_venda_parcelada(dados["cg160"].id, dados["maria"].id), headers=cabecalho_vendedor
    )

    cabecalho_dono = await entrar(dados["carlos"].id)
    listagem = await cliente.get("/parcelas", headers=cabecalho_dono)
    assert listagem.status_code == 200
    parcelas = listagem.json()
    assert len(parcelas) == 4
    assert all(p["status"] == "ATRASADA" for p in parcelas)
    assert parcelas[0]["cliente_nome"] == "Maria Souza"


async def test_marcar_parcela_paga_some_da_lista_de_pendentes(cliente, dados, entrar):
    cabecalho_vendedor = await entrar(dados["joao"].id)
    venda = await cliente.post(
        "/vendas", json=_corpo_venda_parcelada(dados["cg160"].id, dados["maria"].id), headers=cabecalho_vendedor
    )
    primeira_parcela_id = venda.json()["parcelas"][0]["id"]

    cabecalho_dono = await entrar(dados["carlos"].id)
    marcar = await cliente.patch(
        f"/parcelas/{primeira_parcela_id}", json={"pago": True}, headers=cabecalho_dono
    )
    assert marcar.status_code == 200
    assert marcar.json()["status"] == "PAGA"

    pendentes = await cliente.get("/parcelas", headers=cabecalho_dono)
    ids_pendentes = {p["id"] for p in pendentes.json()}
    assert primeira_parcela_id not in ids_pendentes

    detalhe_cliente = await cliente.get(f"/clientes/{dados['maria'].id}", headers=cabecalho_dono)
    assert detalhe_cliente.json()["deve_parcela"] is True  # ainda faltam 3
