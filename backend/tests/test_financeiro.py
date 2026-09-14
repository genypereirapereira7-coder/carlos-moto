import uuid
from datetime import date

from app.models.base import hoje as hoje_da_loja


async def test_resumo_mes_soma_venda_a_vista_e_despesa(cliente, dados, entrar):
    cabecalho_vendedor = await entrar(dados["joao"].id)
    venda = await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["cg160"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "A_VISTA",
            "preco_venda_centavos": 1_650_000,
        },
        headers=cabecalho_vendedor,
    )
    assert venda.status_code == 201

    cabecalho_dono = await entrar(dados["carlos"].id)
    despesa = await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "descricao": "Revisão",
            "valor_centavos": 30_000,
            "data": str(hoje_da_loja()),
        },
        headers=cabecalho_dono,
    )
    assert despesa.status_code == 201

    hoje = hoje_da_loja()
    resumo = await cliente.get(
        "/financeiro/resumo-mes", params={"ano": hoje.year, "mes": hoje.month}, headers=cabecalho_dono
    )
    assert resumo.status_code == 200
    corpo = resumo.json()
    assert corpo["entrou_centavos"] == 1_650_000
    assert corpo["gasto_arrumacao_centavos"] == 30_000
    assert corpo["qtd_vendas"] == 1


async def test_resumo_mes_venda_parcelada_conta_so_a_entrada(cliente, dados, entrar):
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
            "primeiro_vencimento": str(date(2020, 1, 1)),
        },
        headers=cabecalho_vendedor,
    )

    cabecalho_dono = await entrar(dados["carlos"].id)
    hoje = hoje_da_loja()
    resumo = await cliente.get(
        "/financeiro/resumo-mes", params={"ano": hoje.year, "mes": hoje.month}, headers=cabecalho_dono
    )
    corpo = resumo.json()
    assert corpo["entrou_centavos"] == 200_000
    assert corpo["a_receber_centavos"] == 800_000
