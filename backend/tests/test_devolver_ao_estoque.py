"""Desfazer a venda: a moto volta pro estoque.

O cliente desistiu e devolveu a moto, ou a venda foi lançada na moto errada.
Nada é apagado — a venda e o carnê continuam gravados; o que some é a dívida.
"""

import uuid


async def _vender(cliente, dados, cabecalho, moto_id=None, parcelado=True):
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": moto_id or dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "preco_venda_centavos": 1_000_000,
    }
    if parcelado:
        corpo |= {
            "forma_pagamento": "PARCELADO",
            "numero_parcelas": 4,
            "primeiro_vencimento": "2027-01-10",
            "avalistas": [{"nome": "Avalista Teste", "telefone": "69992125902"}],
        }
    else:
        corpo["forma_pagamento"] = "A_VISTA"
    r = await cliente.post("/vendas", json=corpo, headers=cabecalho)
    assert r.status_code == 201, r.text
    return r.json()


async def test_moto_volta_pro_estoque_e_a_divida_some(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    await _vender(cliente, dados, dono)

    antes = (await cliente.get(f"/clientes/{dados['maria'].id}", headers=dono)).json()
    assert antes["saldo_devedor_centavos"] > 0

    r = await cliente.post(f"/motos/{dados['cg160'].id}/devolver-ao-estoque", headers=dono)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "DISPONIVEL"

    depois = (await cliente.get(f"/clientes/{dados['maria'].id}", headers=dono)).json()
    assert depois["saldo_devedor_centavos"] == 0
    assert depois["deve_parcela"] is False
    # A parcela sai da tela de quem deve.
    pendentes = (await cliente.get("/parcelas", headers=dono)).json()
    assert not [p for p in pendentes if p["moto_id"] == dados["cg160"].id]


async def test_a_venda_nao_e_apagada(cliente, dados, entrar):
    """Some a dívida, não o registro: o sistema não apaga nada."""
    dono = await entrar(dados["carlos"].id)
    venda = await _vender(cliente, dados, dono)
    await cliente.post(f"/motos/{dados['cg160'].id}/devolver-ao-estoque", headers=dono)

    ainda = await cliente.get(f"/vendas/{venda['id']}", headers=dono)
    assert ainda.status_code == 200
    assert ainda.json()["preco_venda_centavos"] == 1_000_000


async def test_a_moto_pode_ser_vendida_de_novo(cliente, dados, entrar):
    """É o ponto do botão: a moto devolvida volta a ser vendável. O banco
    guarda uma venda ATIVA por moto, não uma venda por moto pra sempre."""
    dono = await entrar(dados["carlos"].id)
    await _vender(cliente, dados, dono)
    await cliente.post(f"/motos/{dados['cg160'].id}/devolver-ao-estoque", headers=dono)

    de_novo = await _vender(cliente, dados, dono, parcelado=False)
    assert de_novo["moto"]["id"] == dados["cg160"].id

    motos = (await cliente.get("/motos", headers=dono)).json()
    lista = motos["motos"] if isinstance(motos, dict) else motos
    moto = next(m for m in lista if m["id"] == dados["cg160"].id)
    assert moto["status"] == "VENDIDA"


async def test_moto_em_estoque_nao_tem_o_que_desfazer(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post(f"/motos/{dados['factor'].id}/devolver-ao-estoque", headers=dono)
    assert r.status_code == 409


async def test_so_o_dono_desfaz_venda(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    r = await cliente.post(f"/motos/{dados['cg160'].id}/devolver-ao-estoque", headers=vendedor)
    assert r.status_code == 403
