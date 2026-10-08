"""Corrigir o dia em que o pagamento de uma parcela entrou no caixa.

Pro recebimento lançado no dia errado — recebeu sábado, lançou segunda. O que
importa é que o dinheiro **se mova no financeiro**: mudar só a data que
aparece na tela seria pior que não mudar nada, porque parece resolvido.
"""

import uuid
from datetime import timedelta

from app.models.base import hoje


async def _venda_parcelada(cliente, dados, entrar):
    """Datada uma semana atrás: a correção de data só pode mirar dias depois
    da venda, e uma venda de hoje não deixaria espaço pra testar isso."""
    vendedor = await entrar(dados["joao"].id)
    uma_semana = hoje() - timedelta(days=7)
    r = await cliente.post("/vendas", json={
        "data_venda": f"{uma_semana}T12:00:00Z",
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "PARCELADO",
        "preco_venda_centavos": 1_000_000,
        "numero_parcelas": 2,
        "primeiro_vencimento": str(hoje()),
        "avalistas": [{"nome": "Avalista Teste", "telefone": "69992125902"}],
    }, headers=vendedor)
    assert r.status_code == 201, r.text
    return r.json()


async def _entrou_no_dia(cliente, cabecalho, dia) -> int:
    caixa = (await cliente.get(f"/financeiro/caixa/dia?dia={dia}", headers=cabecalho)).json()
    return caixa["entrou_centavos"]


async def test_corrigir_a_data_move_o_dinheiro_de_dia(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    venda = await _venda_parcelada(cliente, dados, entrar)
    parcela = venda["parcelas"][0]
    ontem = hoje() - timedelta(days=1)

    # recebe hoje (lançado no dia errado)
    r = await cliente.patch(f"/parcelas/{parcela['id']}", json={"pago": True}, headers=dono)
    assert r.status_code == 200
    valor = parcela["valor_centavos"]
    assert await _entrou_no_dia(cliente, dono, hoje()) >= valor

    # corrige pra ontem
    r = await cliente.patch(f"/parcelas/{parcela['id']}/data-pagamento",
                            json={"data_pagamento": str(ontem)}, headers=dono)
    assert r.status_code == 200, r.text
    assert r.json()["pago_em"].startswith(str(ontem))

    # o dinheiro saiu de hoje e entrou em ontem — é o ponto do recurso
    assert await _entrou_no_dia(cliente, dono, ontem) == valor
    assert await _entrou_no_dia(cliente, dono, hoje()) == 0


async def test_parcela_nao_paga_nao_tem_data_pra_corrigir(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    venda = await _venda_parcelada(cliente, dados, entrar)
    r = await cliente.patch(f"/parcelas/{venda['parcelas'][0]['id']}/data-pagamento",
                            json={"data_pagamento": str(hoje())}, headers=dono)
    assert r.status_code == 409


async def test_data_antes_da_venda_e_recusada(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    venda = await _venda_parcelada(cliente, dados, entrar)
    parcela = venda["parcelas"][0]
    await cliente.patch(f"/parcelas/{parcela['id']}", json={"pago": True}, headers=dono)

    r = await cliente.patch(f"/parcelas/{parcela['id']}/data-pagamento",
                            json={"data_pagamento": str(hoje() - timedelta(days=60))},
                            headers=dono)
    assert r.status_code == 422


async def test_data_no_futuro_e_recusada(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    venda = await _venda_parcelada(cliente, dados, entrar)
    parcela = venda["parcelas"][0]
    await cliente.patch(f"/parcelas/{parcela['id']}", json={"pago": True}, headers=dono)

    r = await cliente.patch(f"/parcelas/{parcela['id']}/data-pagamento",
                            json={"data_pagamento": str(hoje() + timedelta(days=1))},
                            headers=dono)
    assert r.status_code == 422


async def test_pagamento_em_pedacos_so_move_o_que_quitou(cliente, dados, entrar):
    """Os pedaços pagos em dias anteriores ficam onde estão: eles aconteceram
    naqueles dias, e empurrar todos pro mesmo dia apagaria isso."""
    dono = await entrar(dados["carlos"].id)
    venda = await _venda_parcelada(cliente, dados, entrar)
    parcela = venda["parcelas"][0]
    anteontem = hoje() - timedelta(days=2)
    ontem = hoje() - timedelta(days=1)

    metade = parcela["valor_centavos"] // 2
    await cliente.post(f"/parcelas/{parcela['id']}/pagamentos",
        json={"valor_centavos": metade, "data_pagamento": str(anteontem)}, headers=dono)
    await cliente.patch(f"/parcelas/{parcela['id']}", json={"pago": True}, headers=dono)

    await cliente.patch(f"/parcelas/{parcela['id']}/data-pagamento",
                        json={"data_pagamento": str(ontem)}, headers=dono)

    assert await _entrou_no_dia(cliente, dono, anteontem) == metade
    assert await _entrou_no_dia(cliente, dono, ontem) == parcela["valor_centavos"] - metade


async def test_so_o_dono_corrige(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    r = await cliente.patch(f"/parcelas/{uuid.uuid4()}/data-pagamento",
                            json={"data_pagamento": str(hoje())}, headers=vendedor)
    assert r.status_code == 403
