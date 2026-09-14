"""Reenviar o mesmo lançamento não pode cobrar duas vezes.

A fila offline sobe o que foi cadastrado sem internet, e um envio que o
servidor recebeu mas cuja resposta se perdeu volta pra fila e sobe de novo.
Sem proteção, o dono paga a revisão uma vez e o financeiro mostra duas.

Cada operação de escrita se protege de um jeito: gasto e venda por um id
gerado no navegador, moto pela placa, cliente pelo CPF, e parcela porque
marcar como paga duas vezes dá o mesmo estado.
"""

import uuid

from datetime import timedelta

from app.models.base import hoje


async def test_mesmo_gasto_enviado_duas_vezes_lanca_uma_so(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "descricao": "Revisão completa",
        "valor_centavos": 40_000,
        "data": str(hoje()),
    }
    caminho = f"/motos/{dados['factor'].id}/despesas"

    primeira = await cliente.post(caminho, json=corpo, headers=cabecalho)
    segunda = await cliente.post(caminho, json=corpo, headers=cabecalho)

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    # O reenvio devolve o gasto que já existe, não um novo.
    assert segunda.json()["id"] == primeira.json()["id"]

    detalhe = (await cliente.get(f"/motos/{dados['factor'].id}", headers=cabecalho)).json()
    assert len(detalhe["despesas"]) == 1
    assert detalhe["total_gastos_centavos"] == 40_000


async def test_gastos_diferentes_com_o_mesmo_texto_continuam_dois(cliente, dados, entrar):
    """Duas revisões de R$ 400 no mesmo dia são dois gastos de verdade — o que
    separa um reenvio de um gasto novo é o id, não o conteúdo."""
    cabecalho = await entrar(dados["carlos"].id)
    caminho = f"/motos/{dados['factor'].id}/despesas"
    base = {"descricao": "Revisão completa", "valor_centavos": 40_000, "data": str(hoje())}

    await cliente.post(caminho, json={"id_cliente": str(uuid.uuid4()), **base}, headers=cabecalho)
    await cliente.post(caminho, json={"id_cliente": str(uuid.uuid4()), **base}, headers=cabecalho)

    detalhe = (await cliente.get(f"/motos/{dados['factor'].id}", headers=cabecalho)).json()
    assert len(detalhe["despesas"]) == 2
    assert detalhe["total_gastos_centavos"] == 80_000


async def test_gasto_reenviado_nao_dobra_no_financeiro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "descricao": "Pneu novo",
        "valor_centavos": 55_000,
        "data": str(hoje()),
    }
    caminho = f"/motos/{dados['factor'].id}/despesas"
    await cliente.post(caminho, json=corpo, headers=cabecalho)
    await cliente.post(caminho, json=corpo, headers=cabecalho)

    mes = (await cliente.get(
        "/financeiro/mes",
        params={"ano": hoje().year, "mes": hoje().month},
        headers=cabecalho,
    )).json()
    assert mes["gasto_arrumacao_centavos"] == 55_000


async def test_gasto_sem_id_cliente_e_recusado(cliente, dados, entrar):
    """Sem o id não há como saber se é reenvio — melhor recusar do que
    arriscar lançar o mesmo dinheiro duas vezes."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"descricao": "Revisão", "valor_centavos": 40_000, "data": str(hoje())},
        headers=cabecalho,
    )
    assert resposta.status_code == 422


async def test_mesma_venda_enviada_duas_vezes_vende_uma_so(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_650_000,
    }

    primeira = await cliente.post("/vendas", json=corpo, headers=cabecalho)
    segunda = await cliente.post("/vendas", json=corpo, headers=cabecalho)

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert segunda.json()["id"] == primeira.json()["id"]

    dono = await entrar(dados["carlos"].id)
    vendas = (await cliente.get("/vendas", headers=dono)).json()
    assert len([v for v in vendas if v["moto"]["id"] == dados["cg160"].id]) == 1


async def test_mesma_moto_cadastrada_duas_vezes_para_no_409(cliente, dados, entrar):
    """A placa é única: o reenvio esbarra nela em vez de criar uma segunda
    linha da mesma moto. A fila trata esse 409 como 'já subiu'."""
    cabecalho = await entrar(dados["carlos"].id)
    corpo = {"marca": "Honda", "modelo": "Biz 125", "ano": 2026, "placa": "REP1A11"}

    primeira = await cliente.post("/motos", json=corpo, headers=cabecalho)
    segunda = await cliente.post("/motos", json=corpo, headers=cabecalho)

    assert primeira.status_code == 201
    assert segunda.status_code == 409


async def test_mesmo_cliente_cadastrado_duas_vezes_para_no_409(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    corpo = {"nome": "Repetido da Silva", "cpf": "111.444.777-35", "telefone": "11988887777"}

    primeira = await cliente.post("/clientes", json=corpo, headers=cabecalho)
    segunda = await cliente.post("/clientes", json=corpo, headers=cabecalho)

    assert primeira.status_code == 201
    assert segunda.status_code == 409


async def test_mesma_parcela_paga_duas_vezes_nao_move_a_data(cliente, dados, entrar):
    """Marcar paga é idempotente *desde que a data vá junto*. Sem ela o
    servidor usaria "agora", e uma parcela recebida no sábado que só sobe da
    fila na segunda cairia no caixa da segunda — por isso a tela nunca manda
    esse PATCH sem `data_pagamento`."""
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
        },
        headers=vendedor,
    )
    parcela_id = venda.json()["parcelas"][0]["id"]

    cabecalho = await entrar(dados["carlos"].id)
    corpo = {"pago": True, "data_pagamento": str(hoje())}
    primeira = await cliente.patch(f"/parcelas/{parcela_id}", json=corpo, headers=cabecalho)
    segunda = await cliente.patch(f"/parcelas/{parcela_id}", json=corpo, headers=cabecalho)

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    # O instante pode mudar por milissegundos no reenvio do mesmo dia; o que
    # não pode mudar é o dia, que é o que o caixa fecha.
    assert segunda.json()["pago_em"][:10] == primeira.json()["pago_em"][:10]

    mes = (await cliente.get(
        "/financeiro/mes",
        params={"ano": hoje().year, "mes": hoje().month},
        headers=cabecalho,
    )).json()
    assert mes["qtd_parcelas_recebidas"] == 1


async def test_parcela_paga_ontem_e_enviada_hoje_fica_em_ontem(cliente, dados, entrar):
    """O caso que a fila cria de verdade: o dono recebe e marca sem internet,
    e o envio só sobe no dia seguinte. O dinheiro tem que entrar no caixa do
    dia em que foi recebido."""
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
    parcela_id = venda.json()["parcelas"][0]["id"]

    ontem = hoje() - timedelta(days=1)
    cabecalho = await entrar(dados["carlos"].id)
    corpo = {"pago": True, "data_pagamento": str(ontem)}
    await cliente.patch(f"/parcelas/{parcela_id}", json=corpo, headers=cabecalho)
    segunda = await cliente.patch(f"/parcelas/{parcela_id}", json=corpo, headers=cabecalho)

    assert segunda.status_code == 200
    dia = (await cliente.get(
        "/financeiro/diario", params={"dia": str(ontem)}, headers=cabecalho
    )).json()
    assert dia["entrou_centavos"] == 100_000  # (900.000 - 300.000) / 6
