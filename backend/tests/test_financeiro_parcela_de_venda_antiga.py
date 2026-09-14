"""Parcela paga num mês em que a venda não aconteceu.

É o caso mais comum de um carnê: a moto foi vendida em janeiro e o cliente
paga todo mês até dezembro. Em setembro o financeiro só tem a parcela — a
venda de janeiro não está no período —, e a venda só é alcançada a partir
dela.
"""

import uuid
from datetime import date

import pytest


async def _venda_parcelada_antiga(cliente, dados, entrar) -> str:
    vendedor = await entrar(dados["joao"].id)
    venda = await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["cg160"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "PARCELADO",
            "preco_venda_centavos": 900_000,
            "valor_entrada_centavos": 300_000,
            "numero_parcelas": 6,
            "data_venda": "2026-01-10T12:00:00-03:00",
        },
        headers=vendedor,
    )
    assert venda.status_code == 201, venda.text
    return venda.json()["parcelas"][0]["id"]


@pytest.mark.parametrize("rota,params", [
    ("/financeiro/mes", {"ano": 2026, "mes": 3}),
    ("/financeiro/diario", {"dia": "2026-03-05"}),
])
async def test_financeiro_abre_com_parcela_de_venda_de_outro_mes(
    cliente, dados, entrar, rota, params
):
    parcela_id = await _venda_parcelada_antiga(cliente, dados, entrar)
    cabecalho = await entrar(dados["carlos"].id)
    pago = await cliente.patch(
        f"/parcelas/{parcela_id}",
        json={"pago": True, "data_pagamento": "2026-03-05"},
        headers=cabecalho,
    )
    assert pago.status_code == 200, pago.text

    resposta = await cliente.get(rota, params=params, headers=cabecalho)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["entrou_centavos"] == 100_000


async def test_descricao_da_parcela_diz_de_quantas_ela_e(cliente, dados, entrar):
    """"Parcela 1 de 6" — o "de 6" vem de `venda.parcelas`, que é justamente
    o que não estava sendo carregado."""
    parcela_id = await _venda_parcelada_antiga(cliente, dados, entrar)
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/parcelas/{parcela_id}",
        json={"pago": True, "data_pagamento": "2026-03-05"},
        headers=cabecalho,
    )

    mes = (await cliente.get(
        "/financeiro/mes", params={"ano": 2026, "mes": 3}, headers=cabecalho
    )).json()
    movimentos = [m for d in mes["dias"] for m in d["movimentos"] if m["tipo"] == "PARCELA"]
    assert len(movimentos) == 1
    assert "Parcela 1 de 6" in movimentos[0]["descricao"]
    assert "Maria Souza" in movimentos[0]["descricao"]
