"""O vendedor não pode ver o que a loja pagou nem quanto ganhou.

É a mesma regra que fecha a tela FINANCEIRO pro papel DONO. Ela existia lá e
não existia nas rotas de moto: `GET /motos/{id}` e `GET /motos/disponiveis`
devolviam `valor_compra_centavos`, gastos, fornecedor e lucro pra qualquer
vendedor logado.
"""

import pytest

CAMPOS_DO_DONO = (
    "valor_compra_centavos",
    "data_compra",
    "fornecedor_cliente_id",
    "fornecedor_nome",
    "fornecedor_nome_efetivo",
    "total_gastos_centavos",
    "lucro_centavos",
    "lucro_percentual",
    "despesas",
    "venda",
)


@pytest.fixture
async def com_custo(cliente, dados, entrar):
    """Põe custo e gasto numa moto, pra haver o que vazar."""
    dono = await entrar(dados["carlos"].id)
    await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"valor_compra_centavos": 800_000, "data_compra": "2026-07-10"},
        headers=dono,
    )
    return dados["factor"].id


async def test_vitrine_do_vendedor_nao_traz_custo(cliente, dados, entrar, com_custo):
    vendedor = await entrar(dados["joao"].id)
    vitrine = (await cliente.get("/motos/disponiveis", headers=vendedor)).json()

    moto = next(m for m in vitrine if m["id"] == com_custo)
    for campo in CAMPOS_DO_DONO:
        assert campo not in moto, f"vendedor viu {campo}"
    # E continua trazendo o que ele precisa pra vender.
    assert moto["preco_centavos"] > 0
    assert moto["placa"]


async def test_detalhe_completo_e_so_do_dono(cliente, dados, entrar, com_custo):
    vendedor = await entrar(dados["joao"].id)
    resposta = await cliente.get(f"/motos/{com_custo}", headers=vendedor)
    assert resposta.status_code == 403


async def test_dono_continua_vendo_tudo(cliente, dados, entrar, com_custo):
    dono = await entrar(dados["carlos"].id)
    detalhe = (await cliente.get(f"/motos/{com_custo}", headers=dono)).json()
    assert detalhe["valor_compra_centavos"] == 800_000
    assert "lucro_centavos" in detalhe


async def test_vendedor_tem_a_rota_dele_pra_uma_moto(cliente, dados, entrar, com_custo):
    """Tirar o acesso não pode deixá-lo sem como abrir a moto que vai vender."""
    vendedor = await entrar(dados["joao"].id)
    resposta = await cliente.get(f"/motos/{com_custo}/vitrine", headers=vendedor)
    assert resposta.status_code == 200
    for campo in CAMPOS_DO_DONO:
        assert campo not in resposta.json()
    assert resposta.json()["modelo"] == "Factor 125"
