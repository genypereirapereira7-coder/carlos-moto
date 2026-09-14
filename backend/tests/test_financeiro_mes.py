"""Tela FINANCEIRO: o mês em números e o dia a dia — no dia de Brasília."""

import uuid
from datetime import timedelta

from app.models.base import hoje


async def _vender(cliente, cabecalho, moto_id: int, cliente_id: int, **extra) -> dict:
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": moto_id,
        "cliente_id": cliente_id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_000_000,
    }
    corpo.update(extra)
    resposta = await cliente.post("/vendas", json=corpo, headers=cabecalho)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _mes_atual() -> dict:
    return {"ano": hoje().year, "mes": hoje().month}


async def test_venda_das_22h_do_ultimo_dia_fica_no_mes_certo(cliente, dados, entrar):
    """22h30 de 31/08 em Brasília já é 1º/09 em UTC. Tem que cair em agosto —
    e no dia 31, não no 1º."""
    cabecalho = await entrar(dados["carlos"].id)
    await _vender(
        cliente, cabecalho, dados["cg160"].id, dados["maria"].id,
        data_venda="2026-08-31T22:30:00-03:00",
    )

    agosto = await cliente.get("/financeiro/mes", params={"ano": 2026, "mes": 8}, headers=cabecalho)
    setembro = await cliente.get("/financeiro/mes", params={"ano": 2026, "mes": 9}, headers=cabecalho)

    assert agosto.json()["entrou_centavos"] == 1_000_000
    assert agosto.json()["dias"][0]["dia"] == "2026-08-31"
    assert setembro.json()["entrou_centavos"] == 0


async def test_os_dias_somam_o_total_do_mes(cliente, dados, entrar):
    """O número do cartão tem que ser a soma da tabela embaixo — sempre."""
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000, "data_compra": str(hoje())},
        headers=cabecalho,
    )
    await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "Revisão", "valor_centavos": 50_000, "data": str(hoje())},
        headers=cabecalho,
    )
    venda = await _vender(
        cliente, cabecalho, dados["cg160"].id, dados["maria"].id,
        forma_pagamento="PARCELADO",
        preco_venda_centavos=900_000,
        valor_entrada_centavos=300_000,
        numero_parcelas=2,
        primeiro_vencimento=str(hoje() + timedelta(days=30)),
    )
    await cliente.patch(
        f"/parcelas/{venda['parcelas'][0]['id']}", json={"pago": True}, headers=cabecalho
    )

    mes = (await cliente.get("/financeiro/mes", params=_mes_atual(), headers=cabecalho)).json()

    assert mes["entrou_centavos"] == 300_000 + 300_000  # entrada + a parcela paga
    assert mes["gasto_compra_motos_centavos"] == 800_000
    assert mes["gasto_arrumacao_centavos"] == 50_000
    assert mes["lucro_centavos"] == 600_000 - 850_000
    assert mes["qtd_parcelas_recebidas"] == 1
    assert mes["a_receber_centavos"] == 300_000
    assert sum(d["entrou_centavos"] for d in mes["dias"]) == mes["entrou_centavos"]
    assert sum(d["saiu_centavos"] for d in mes["dias"]) == 850_000
    tipos = sorted(m["tipo"] for d in mes["dias"] for m in d["movimentos"])
    assert tipos == ["COMPRA", "GASTO", "PARCELA", "VENDA"]


async def test_lucro_nas_vendas_deixa_de_fora_quem_nao_tem_custo(cliente, dados, entrar):
    """A Factor tem custo lançado (compra + gasto); a CG160 não. O lucro das
    vendas só pode contar a Factor — e avisar que a outra ficou de fora."""
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000, "data_compra": "2026-07-01"},
        headers=cabecalho,
    )
    await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "Revisão", "valor_centavos": 50_000, "data": "2026-07-10"},
        headers=cabecalho,
    )
    await _vender(cliente, cabecalho, dados["factor"].id, dados["maria"].id, preco_venda_centavos=1_150_000)
    await _vender(cliente, cabecalho, dados["cg160"].id, dados["maria"].id)

    mes = (await cliente.get("/financeiro/mes", params=_mes_atual(), headers=cabecalho)).json()

    assert mes["lucro_vendas_centavos"] == 1_150_000 - 800_000 - 50_000
    assert mes["qtd_vendas_sem_custo"] == 1
    # Compra e gasto foram em julho: não saem do caixa deste mês.
    assert mes["lucro_centavos"] == 2_150_000


async def test_mes_invalido_e_recusado_em_portugues(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.get("/financeiro/mes", params={"ano": 2026, "mes": 13}, headers=cabecalho)
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["msg"] == "Precisa ser 12 ou menos"


async def test_vendedor_nao_ve_o_financeiro(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.get("/financeiro/mes", params=_mes_atual(), headers=cabecalho)
    assert resposta.status_code == 403
