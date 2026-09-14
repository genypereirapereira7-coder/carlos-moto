"""Validação da venda — as regras que o botão "Vender" do painel do dono
confia que o servidor também aplica."""

import uuid
from datetime import UTC, datetime, timedelta


def _venda(dados, **extra) -> dict:
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "A_VISTA",
        "preco_venda_centavos": 1_500_000,
    }
    corpo.update(extra)
    return corpo


async def test_venda_com_preco_zero_e_recusada(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/vendas", json=_venda(dados, preco_venda_centavos=0), headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_parcelado_com_entrada_igual_ao_preco_e_recusado(cliente, dados, entrar):
    """Entrada igual ao preço não sobra nada pra parcelar — sem esta trava
    nascia um carnê de parcelas de R$ 0,00."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/vendas",
        json=_venda(
            dados,
            forma_pagamento="PARCELADO",
            numero_parcelas=3,
            valor_entrada_centavos=1_500_000,
            primeiro_vencimento="2026-12-01",
        ),
        headers=cabecalho,
    )
    assert resposta.status_code == 422
    assert "à vista" in resposta.json()["detail"][0]["msg"]


async def test_venda_com_data_no_futuro_e_recusada(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    amanha = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    resposta = await cliente.post(
        "/vendas", json=_venda(dados, data_venda=amanha), headers=cabecalho
    )
    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["msg"] == "Data não pode ser no futuro"


async def test_venda_com_data_de_hoje_passa(cliente, dados, entrar):
    """A margem de um minuto existe pra isto: "vender agora" não pode virar
    erro só porque o relógio do computador está um pouco adiantado."""
    cabecalho = await entrar(dados["carlos"].id)
    agora_adiantado = (datetime.now(UTC) + timedelta(seconds=20)).isoformat()
    resposta = await cliente.post(
        "/vendas", json=_venda(dados, data_venda=agora_adiantado), headers=cabecalho
    )
    assert resposta.status_code == 201


async def test_dono_consegue_vender(cliente, dados, entrar):
    """O botão "Vender" fica no painel do dono — a rota tem que aceitar o
    dono, não só vendedor."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/vendas", json=_venda(dados), headers=cabecalho)
    assert resposta.status_code == 201
    assert resposta.json()["moto"]["status"] == "VENDIDA"
