"""O que a loja pagou pela moto tem que aparecer no financeiro.

Valor e data da compra andam juntos: o financeiro lança a compra no dia dela,
então valor sem data é um gasto que o dono digita e nunca mais encontra."""

from app.models.base import hoje


def _mes_atual() -> dict:
    return {"ano": hoje().year, "mes": hoje().month}


async def test_moto_cadastrada_com_valor_pago_entra_no_financeiro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    cadastro = await cliente.post(
        "/motos",
        json={
            "marca": "Honda",
            "modelo": "Biz 125",
            "ano": 2026,
            "placa": "BIZ1A23",
            "valor_compra_centavos": 900_000,
            "data_compra": str(hoje()),
        },
        headers=cabecalho,
    )
    assert cadastro.status_code == 201

    mes = (await cliente.get("/financeiro/mes", params=_mes_atual(), headers=cabecalho)).json()
    assert mes["gasto_compra_motos_centavos"] == 900_000
    assert mes["qtd_motos_compradas"] == 1

    compras = [m for d in mes["dias"] for m in d["movimentos"] if m["tipo"] == "COMPRA"]
    assert len(compras) == 1
    assert compras[0]["saida_centavos"] == 900_000
    assert "Biz 125" in compras[0]["descricao"]


async def test_cadastro_recusa_valor_sem_data(cliente, dados, entrar):
    """Era assim que o gasto sumia: salvava e não caía em mês nenhum."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos",
        json={"modelo": "Biz 125", "ano": 2026, "placa": "BIZ1A23", "valor_compra_centavos": 900_000},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert "juntos" in resposta.json()["detail"][0]["msg"]


async def test_cadastro_recusa_data_sem_valor(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos",
        json={"modelo": "Biz 125", "ano": 2026, "placa": "BIZ1A23", "data_compra": str(hoje())},
        headers=cabecalho,
    )
    assert resposta.status_code == 422


async def test_cadastro_sem_compra_nenhuma_continua_valendo(cliente, dados, entrar):
    """Moto que chegou e ainda não foi paga (ou o dono lança depois)."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 2026, "placa": "BIZ1A23"}, headers=cabecalho
    )
    assert resposta.status_code == 201
    assert resposta.json()["valor_compra_centavos"] is None


async def test_editar_recusa_valor_sem_data(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert "juntos" in resposta.json()["detail"]


async def test_editar_com_o_par_completo_entra_no_financeiro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000, "data_compra": str(hoje())},
        headers=cabecalho,
    )
    assert resposta.status_code == 200

    mes = (await cliente.get("/financeiro/mes", params=_mes_atual(), headers=cabecalho)).json()
    assert mes["gasto_compra_motos_centavos"] == 800_000


async def test_editar_so_a_cor_nao_exige_remandar_a_compra(cliente, dados, entrar):
    """Quem já tem a compra lançada não precisa reenviá-la a cada edição."""
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000, "data_compra": str(hoje())},
        headers=cabecalho,
    )
    resposta = await cliente.patch(
        f"/motos/{dados['factor'].id}", json={"cor": "Azul"}, headers=cabecalho
    )
    assert resposta.status_code == 200
    assert resposta.json()["cor"] == "Azul"
    assert resposta.json()["valor_compra_centavos"] == 800_000
