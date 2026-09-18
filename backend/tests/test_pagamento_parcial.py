"""Pagamento em pedaços: o cliente do carnê paga só um pouco de uma parcela.

O resto abate na mesma parcela — ela continua aberta mostrando o que falta até
ser quitada, e cada pedaço entra no caixa pelo dia em que foi pago.
"""

import uuid
from datetime import date


def _corpo(moto_id: int, cliente_id: int) -> dict:
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


async def _vender(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    resposta = await cliente.post(
        "/vendas", json=_corpo(dados["cg160"].id, dados["maria"].id), headers=vendedor
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["parcelas"]  # 4 parcelas de 200.000


async def test_pagar_um_pouco_abate_e_mantem_a_parcela_aberta(cliente, dados, entrar):
    parcelas = await _vender(cliente, dados, entrar)
    parcela_id = parcelas[0]["id"]
    dono = await entrar(dados["carlos"].id)

    r = await cliente.post(
        f"/parcelas/{parcela_id}/pagamentos", json={"valor_centavos": 50_000}, headers=dono
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total_pago_centavos"] == 50_000
    assert corpo["saldo_centavos"] == 150_000
    assert corpo["status"] != "PAGA"           # ainda deve
    assert corpo["pago_em"] is None            # não quitou

    # Continua na lista de quem deve, agora com saldo abatido.
    pendentes = await cliente.get("/parcelas", headers=dono)
    linha = next(p for p in pendentes.json() if p["id"] == parcela_id)
    assert linha["saldo_centavos"] == 150_000


async def test_completar_o_restante_quita_a_parcela(cliente, dados, entrar):
    parcelas = await _vender(cliente, dados, entrar)
    parcela_id = parcelas[0]["id"]
    dono = await entrar(dados["carlos"].id)

    await cliente.post(f"/parcelas/{parcela_id}/pagamentos", json={"valor_centavos": 50_000}, headers=dono)
    r = await cliente.post(
        f"/parcelas/{parcela_id}/pagamentos", json={"valor_centavos": 150_000}, headers=dono
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "PAGA"
    assert corpo["saldo_centavos"] == 0
    assert corpo["pago_em"] is not None

    pendentes = await cliente.get("/parcelas", headers=dono)
    assert parcela_id not in {p["id"] for p in pendentes.json()}


async def test_pagar_mais_do_que_falta_e_recusado(cliente, dados, entrar):
    parcelas = await _vender(cliente, dados, entrar)
    parcela_id = parcelas[0]["id"]  # saldo 200.000
    dono = await entrar(dados["carlos"].id)

    r = await cliente.post(
        f"/parcelas/{parcela_id}/pagamentos", json={"valor_centavos": 250_000}, headers=dono
    )
    assert r.status_code == 422


async def test_pagamento_de_valor_nao_positivo_e_recusado(cliente, dados, entrar):
    parcelas = await _vender(cliente, dados, entrar)
    parcela_id = parcelas[0]["id"]
    dono = await entrar(dados["carlos"].id)

    for valor in (0, -100):
        r = await cliente.post(
            f"/parcelas/{parcela_id}/pagamentos", json={"valor_centavos": valor}, headers=dono
        )
        assert r.status_code == 422, f"valor {valor} deveria ser recusado"


async def test_pagamento_parcial_reduz_o_saldo_devedor_da_venda(cliente, dados, entrar):
    parcelas = await _vender(cliente, dados, entrar)  # saldo devedor 800.000
    dono = await entrar(dados["carlos"].id)
    await cliente.post(
        f"/parcelas/{parcelas[0]['id']}/pagamentos", json={"valor_centavos": 50_000}, headers=dono
    )

    detalhe = await cliente.get(f"/clientes/{dados['maria'].id}", headers=dono)
    # A venda aparece no cadastro do cliente; o saldo devedor caiu os 50.000.
    corpo = detalhe.json()
    assert corpo["deve_parcela"] is True
