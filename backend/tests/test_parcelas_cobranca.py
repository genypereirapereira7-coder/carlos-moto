"""Tela PARCELAS: receber na data certa, e atrasado separado de "a vencer"."""

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.base import FUSO_DA_LOJA, hoje


async def _vender_parcelado(cliente, dados, entrar, **extra) -> dict:
    cabecalho = await entrar(dados["carlos"].id)
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "PARCELADO",
        "preco_venda_centavos": 900_000,
        "numero_parcelas": 3,
        "primeiro_vencimento": str(hoje() + timedelta(days=30)),
    }
    corpo.update(extra)
    resposta = await cliente.post("/vendas", json=corpo, headers=cabecalho)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _dia_na_loja(instante_iso: str) -> date:
    return datetime.fromisoformat(instante_iso).astimezone(FUSO_DA_LOJA).date()


async def test_receber_com_data_passada_grava_aquele_dia(cliente, dados, entrar):
    """Recebeu no sábado, lançou na segunda: o dinheiro tem que cair no
    sábado, senão o financeiro do dia fica errado."""
    dez_dias_atras = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    venda = await _vender_parcelado(cliente, dados, entrar, data_venda=dez_dias_atras)
    dia = hoje() - timedelta(days=3)

    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/parcelas/{venda['parcelas'][0]['id']}",
        json={"pago": True, "data_pagamento": str(dia)},
        headers=cabecalho,
    )
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "PAGA"
    assert _dia_na_loja(resposta.json()["pago_em"]) == dia


async def test_receber_sem_data_usa_hoje(cliente, dados, entrar):
    venda = await _vender_parcelado(cliente, dados, entrar)
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/parcelas/{venda['parcelas'][0]['id']}", json={"pago": True}, headers=cabecalho
    )
    assert resposta.status_code == 200
    assert _dia_na_loja(resposta.json()["pago_em"]) == hoje()


async def test_receber_com_data_no_futuro_e_recusado(cliente, dados, entrar):
    venda = await _vender_parcelado(cliente, dados, entrar)
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/parcelas/{venda['parcelas'][0]['id']}",
        json={"pago": True, "data_pagamento": str(hoje() + timedelta(days=1))},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["msg"] == "Data não pode ser no futuro"


async def test_receber_antes_da_venda_e_recusado(cliente, dados, entrar):
    venda = await _vender_parcelado(cliente, dados, entrar)  # vendida hoje
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/parcelas/{venda['parcelas'][0]['id']}",
        json={"pago": True, "data_pagamento": str(hoje() - timedelta(days=1))},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert "antes da data da venda" in resposta.json()["detail"]


async def test_desfazer_volta_a_parcela_pra_devida(cliente, dados, entrar):
    venda = await _vender_parcelado(cliente, dados, entrar)
    parcela_id = venda["parcelas"][0]["id"]
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.patch(f"/parcelas/{parcela_id}", json={"pago": True}, headers=cabecalho)

    desfeita = await cliente.patch(f"/parcelas/{parcela_id}", json={"pago": False}, headers=cabecalho)
    assert desfeita.status_code == 200
    assert desfeita.json()["pago_em"] is None
    assert desfeita.json()["status"] == "PENDENTE"


async def test_parcela_que_vence_hoje_ainda_nao_esta_atrasada(cliente, dados, entrar):
    """Atrasada só a partir de amanhã — no relógio da loja."""
    await _vender_parcelado(cliente, dados, entrar, numero_parcelas=1, primeiro_vencimento=str(hoje()))
    cabecalho = await entrar(dados["carlos"].id)
    lista = await cliente.get("/parcelas", headers=cabecalho)
    assert [p["status"] for p in lista.json()] == ["PENDENTE"]


async def test_lista_de_parcelas_traz_telefone_e_marca(cliente, dados, entrar):
    """O telefone é pra quem o dono liga quando vê a linha vermelha."""
    await _vender_parcelado(cliente, dados, entrar)
    cabecalho = await entrar(dados["carlos"].id)
    primeira = (await cliente.get("/parcelas", headers=cabecalho)).json()[0]
    assert primeira["cliente_telefone"] == "11999990000"
    assert primeira["moto_marca"] == "Honda"


async def test_cliente_separa_atrasado_do_total_a_receber(cliente, dados, entrar):
    """Três parcelas de R$ 3.000: a de 40 dias atrás e a de ~10 dias atrás já
    venceram, a do mês que vem não. Vermelho é só pelos R$ 6.000."""
    await _vender_parcelado(
        cliente, dados, entrar, primeiro_vencimento=str(hoje() - timedelta(days=40))
    )
    cabecalho = await entrar(dados["carlos"].id)

    lista = await cliente.get("/clientes", headers=cabecalho)
    maria = next(c for c in lista.json()["clientes"] if c["id"] == dados["maria"].id)
    assert maria["saldo_devedor_centavos"] == 900_000
    assert maria["saldo_atrasado_centavos"] == 600_000

    detalhe = await cliente.get(f"/clientes/{dados['maria'].id}", headers=cabecalho)
    assert detalhe.json()["saldo_atrasado_centavos"] == 600_000
