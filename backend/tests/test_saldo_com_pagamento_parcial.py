"""As somas de dívida têm que descontar o que já foi pago em pedaços.

Bug real encontrado: quatro consultas somavam o valor **cheio** das parcelas em
aberto. Quem pagava R$ 4.000 de uma parcela de R$ 10.000 aparecia devendo os
R$ 10.000 — inclusive no "a receber" do painel financeiro, que é o número em
que o dono confia pra saber quanto ainda entra.
"""

import uuid
from datetime import date, timedelta

from app.models.base import hoje


async def _venda_parcelada(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    r = await cliente.post("/vendas", json={
        "id_cliente": str(uuid.uuid4()),
        "moto_id": dados["cg160"].id,
        "cliente_id": dados["maria"].id,
        "forma_pagamento": "PARCELADO",
        "preco_venda_centavos": 1_000_000,
        "numero_parcelas": 1,
        "primeiro_vencimento": str(hoje() - timedelta(days=5)),
    }, headers=vendedor)
    assert r.status_code == 201, r.text
    return r.json()


async def test_saldo_do_cliente_desconta_pagamento_parcial(cliente, dados, entrar):
    venda = await _venda_parcelada(cliente, dados, entrar)
    dono = await entrar(dados["carlos"].id)
    await cliente.post(
        f"/parcelas/{venda['parcelas'][0]['id']}/pagamentos",
        json={"valor_centavos": 400_000}, headers=dono,
    )
    devedor = next(c for c in (await cliente.get("/clientes", headers=dono)).json()["clientes"]
                   if c["id"] == dados["maria"].id)
    assert devedor["saldo_devedor_centavos"] == 600_000
    assert devedor["saldo_atrasado_centavos"] == 600_000


async def test_a_receber_do_financeiro_desconta_pagamento_parcial(cliente, dados, entrar):
    """O painel não pode inflar o "a receber" com o que já entrou."""
    venda = await _venda_parcelada(cliente, dados, entrar)
    dono = await entrar(dados["carlos"].id)
    await cliente.post(
        f"/parcelas/{venda['parcelas'][0]['id']}/pagamentos",
        json={"valor_centavos": 400_000}, headers=dono,
    )
    h = hoje()
    mes = (await cliente.get(f"/financeiro/mes?ano={h.year}&mes={h.month}", headers=dono)).json()
    assert mes["a_receber_centavos"] == 600_000


async def test_detalhe_do_cliente_tambem_desconta(cliente, dados, entrar):
    venda = await _venda_parcelada(cliente, dados, entrar)
    dono = await entrar(dados["carlos"].id)
    await cliente.post(
        f"/parcelas/{venda['parcelas'][0]['id']}/pagamentos",
        json={"valor_centavos": 400_000}, headers=dono,
    )
    d = (await cliente.get(f"/clientes/{dados['maria'].id}", headers=dono)).json()
    assert d["saldo_devedor_centavos"] == 600_000
