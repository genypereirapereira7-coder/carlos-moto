"""Formas de pagamento novas (cheque, cartão) e os juros da loja.

Cheque é carnê: a loja entregou a moto e vai receber folha a folha, então
gera parcela e aceita avalista igual ao carnê próprio. Cartão e consórcio
não — quem parcela lá não é a loja.
"""

import uuid
from datetime import date


def _venda(moto_id: int, cliente_id: int, **extra) -> dict:
    base = {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": moto_id,
        "cliente_id": cliente_id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_000_000,
    }
    base.update(extra)
    return base


async def test_cheque_gera_carne_e_aceita_avalista(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json=_venda(
        dados["cg160"].id, dados["maria"].id,
        forma_pagamento="CHEQUE", numero_parcelas=4, valor_entrada_centavos=200_000,
        avalistas=[{"nome": "Fulano", "telefone": "69984420093"}],
    ), headers=cabecalho)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert len(corpo["parcelas"]) == 4, "cheque tem que gerar carnê"
    assert len(corpo["avalistas"]) == 1
    assert sum(p["valor_centavos"] for p in corpo["parcelas"]) == 800_000


async def test_juros_entram_nas_parcelas_e_a_entrada_fica_gravada(cliente, dados, entrar):
    """10% sobre o saldo de 800.000 = 880.000 dividido nas parcelas."""
    cabecalho = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json=_venda(
        dados["cg160"].id, dados["maria"].id,
        forma_pagamento="PARCELADO", numero_parcelas=4,
        valor_entrada_centavos=200_000, juros_centesimos=1000,
    ), headers=cabecalho)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert sum(p["valor_centavos"] for p in corpo["parcelas"]) == 880_000
    assert corpo["valor_entrada_centavos"] == 200_000
    assert corpo["juros_centesimos"] == 1000
    assert corpo["saldo_devedor_centavos"] == 880_000


async def test_entrada_da_venda_com_juros_nao_fica_negativa_no_financeiro(cliente, dados, entrar):
    """Com juros as parcelas somam mais que o saldo: a entrada do caixa tem
    que vir do campo gravado, não de `preço − parcelas`."""
    vendedor = await entrar(dados["joao"].id)
    await cliente.post("/vendas", json=_venda(
        dados["cg160"].id, dados["maria"].id,
        forma_pagamento="PARCELADO", numero_parcelas=4,
        valor_entrada_centavos=200_000, juros_centesimos=5000,
    ), headers=vendedor)

    dono = await entrar(dados["carlos"].id)
    agora = date.today()
    resposta = await cliente.get(
        f"/financeiro/mes?ano={agora.year}&mes={agora.month}", headers=dono
    )
    assert resposta.status_code == 200, resposta.text
    hoje = resposta.json()
    entradas = [m for d in hoje["dias"] for m in d["movimentos"] if m["tipo"] == "VENDA"]
    assert entradas, "a venda tem que aparecer no financeiro"
    assert all(m["entrada_centavos"] >= 0 for m in entradas)
    assert entradas[0]["entrada_centavos"] == 200_000


async def test_juros_em_forma_que_nao_tem_juros_e_recusado(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json=_venda(
        dados["cg160"].id, dados["maria"].id,
        forma_pagamento="A_VISTA", juros_centesimos=500,
    ), headers=cabecalho)
    assert r.status_code == 422


async def test_cartao_nao_gera_carne(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json=_venda(
        dados["cg160"].id, dados["maria"].id, forma_pagamento="CARTAO",
    ), headers=cabecalho)
    assert r.status_code == 201, r.text
    assert r.json()["parcelas"] == []


async def test_juros_da_loja_nao_existe_no_cartao_nem_no_consorcio(cliente, dados, entrar):
    """Quem parcela no cartão e no consórcio é a operadora, não a loja — não
    há juro da loja pra cobrar, e guardar um seria inventar número."""
    cabecalho = await entrar(dados["joao"].id)
    for forma in ("CARTAO", "CONSORCIO"):
        r = await cliente.post("/vendas", json=_venda(
            dados["cg160"].id, dados["maria"].id,
            forma_pagamento=forma, juros_centesimos=300,
        ), headers=cabecalho)
        assert r.status_code == 422, f"{forma} não devia aceitar juros da loja"


async def test_avalista_sem_telefone_e_recusado(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json=_venda(
        dados["cg160"].id, dados["maria"].id,
        forma_pagamento="PARCELADO", numero_parcelas=3,
        avalistas=[{"nome": "Sem Telefone"}],
    ), headers=cabecalho)
    assert r.status_code == 422
