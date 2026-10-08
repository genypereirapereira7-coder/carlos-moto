"""Caixa: entrada e saída lançadas à mão, e o fechamento do dia.

O caixa do dia responde a pergunta do fim da tarde — quanto tem que estar na
gaveta. Ele sai do mesmo motor do financeiro do mês de propósito: se somasse
por conta própria, um dia diria um número e o outro diria outro.
"""

import uuid
from datetime import timedelta

from app.models.base import hoje


async def _lancar(cliente, cabecalho, tipo, centavos, descricao, dia=None):
    corpo = {"tipo": tipo, "valor_centavos": centavos, "descricao": descricao}
    if dia:
        corpo["dia"] = str(dia)
    return await cliente.post("/financeiro/caixa", json=corpo, headers=cabecalho)


async def test_entrada_e_saida_fecham_o_caixa_do_dia(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    assert (await _lancar(cliente, dono, "ENTRADA", 20_000, "Serviço avulso")).status_code == 201
    assert (await _lancar(cliente, dono, "SAIDA", 5_000, "Almoço da equipe")).status_code == 201

    caixa = (await cliente.get("/financeiro/caixa/hoje", headers=dono)).json()
    assert caixa["entrou_centavos"] == 20_000
    assert caixa["saiu_centavos"] == 5_000
    assert caixa["saldo_centavos"] == 15_000
    descricoes = [m["descricao"] for m in caixa["movimentos"]]
    assert "Serviço avulso" in descricoes
    assert "Almoço da equipe" in descricoes


async def test_o_caixa_zera_todo_dia(cliente, dados, entrar):
    """Não é saldo acumulado: é o movimento daquele dia."""
    dono = await entrar(dados["carlos"].id)
    ontem = hoje() - timedelta(days=1)
    await _lancar(cliente, dono, "ENTRADA", 70_000, "Venda de peça", dia=ontem)

    de_hoje = (await cliente.get("/financeiro/caixa/hoje", headers=dono)).json()
    assert de_hoje["entrou_centavos"] == 0
    assert de_hoje["saldo_centavos"] == 0

    de_ontem = (await cliente.get(f"/financeiro/caixa/dia?dia={ontem}", headers=dono)).json()
    assert de_ontem["entrou_centavos"] == 70_000


async def test_estorno_tira_da_conta_e_fica_no_historico(cliente, dados, entrar):
    """Nada é apagado: lançamento errado some da conta, não do mundo."""
    dono = await entrar(dados["carlos"].id)
    criado = (await _lancar(cliente, dono, "SAIDA", 30_000, "Lancei errado")).json()

    r = await cliente.post(
        f"/financeiro/caixa/{criado['id']}/estornar",
        json={"motivo": "valor trocado"}, headers=dono)
    assert r.status_code == 200
    assert r.json()["estornado_em"] is not None

    caixa = (await cliente.get("/financeiro/caixa/hoje", headers=dono)).json()
    assert caixa["saiu_centavos"] == 0

    historico = (await cliente.get("/financeiro/caixa/lancamentos", headers=dono)).json()
    estornado = next(m for m in historico if m["id"] == criado["id"])
    assert estornado["motivo_estorno"] == "valor trocado"


async def test_estornar_duas_vezes_e_recusado(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    criado = (await _lancar(cliente, dono, "SAIDA", 1_000, "Teste")).json()
    await cliente.post(f"/financeiro/caixa/{criado['id']}/estornar", json={}, headers=dono)
    de_novo = await cliente.post(
        f"/financeiro/caixa/{criado['id']}/estornar", json={}, headers=dono)
    assert de_novo.status_code == 409


async def test_saida_do_caixa_entra_na_conta_do_lucro(cliente, dados, entrar):
    """Sem isso o lucro do mês ficaria maior que o dinheiro que sobrou."""
    dono = await entrar(dados["carlos"].id)
    antes = (await cliente.get(
        f"/financeiro/mes?ano={hoje().year}&mes={hoje().month}", headers=dono)).json()
    await _lancar(cliente, dono, "SAIDA", 40_000, "Aluguel")
    depois = (await cliente.get(
        f"/financeiro/mes?ano={hoje().year}&mes={hoje().month}", headers=dono)).json()

    assert depois["saidas_caixa_centavos"] == antes["saidas_caixa_centavos"] + 40_000
    assert depois["lucro_centavos"] == antes["lucro_centavos"] - 40_000


async def test_lancamento_sem_descricao_e_recusado(cliente, dados, entrar):
    """"Saiu R$ 300" sem dizer do quê ninguém explica no fim do mês."""
    dono = await entrar(dados["carlos"].id)
    r = await _lancar(cliente, dono, "SAIDA", 30_000, "   ")
    assert r.status_code == 422


async def test_valor_zero_ou_negativo_e_recusado(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    assert (await _lancar(cliente, dono, "ENTRADA", 0, "Nada")).status_code == 422
    assert (await _lancar(cliente, dono, "SAIDA", -5_000, "Negativo")).status_code == 422


async def test_lancamento_no_futuro_e_recusado(cliente, dados, entrar):
    """Caixa é o que já aconteceu."""
    dono = await entrar(dados["carlos"].id)
    r = await _lancar(cliente, dono, "ENTRADA", 1_000, "Amanhã", dia=hoje() + timedelta(days=1))
    assert r.status_code == 422


async def test_so_o_dono_mexe_no_caixa(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    assert (await _lancar(cliente, vendedor, "SAIDA", 1_000, "x")).status_code == 403
    assert (await cliente.get("/financeiro/caixa/hoje", headers=vendedor)).status_code == 403


async def test_estornar_lancamento_que_nao_existe(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post(f"/financeiro/caixa/{uuid.uuid4()}/estornar", json={}, headers=dono)
    assert r.status_code == 404
