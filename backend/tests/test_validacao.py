"""Validação de entrada: cadastro e edição de moto, e lançamento de gasto.

Regra do sistema (pedida explicitamente): todo campo tem validação tanto na
tela quanto aqui na API — a tela impede o óbvio na hora, a API garante que
nenhum caminho (tela nova, chamada direta) grava dado errado."""

import uuid


async def test_cadastro_recusa_ano_fora_do_intervalo(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 1900, "placa": "AAA1111"}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_cadastro_recusa_ano_muito_no_futuro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 2099, "placa": "AAA1111"}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_cadastro_recusa_modelo_so_com_espaco(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "   ", "ano": 2026, "placa": "AAA1111"}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_cadastro_recusa_moto_sem_placa(cliente, dados, entrar):
    """A regra pedida explicitamente: não dá pra cadastrar moto nenhuma sem
    placa — nem 0km ainda não emplacado."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 2026}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_editar_recusa_salvar_moto_que_nasceu_sem_placa(cliente, dados, entrar):
    """`cg160`, no fixture de teste, nasceu sem placa (como o estoque de 0km
    fazia antes desta regra existir). Nenhuma edição deve salvar enquanto a
    placa não for preenchida — nem uma que não mexe na placa."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/motos/{dados['cg160'].id}", json={"cor": "Azul"}, headers=cabecalho
    )
    assert resposta.status_code == 422

    corrigida = await cliente.patch(
        f"/motos/{dados['cg160'].id}",
        json={"cor": "Azul", "placa": "AAA1111"},
        headers=cabecalho,
    )
    assert corrigida.status_code == 200
    assert corrigida.json()["placa"] == "AAA1111"


async def test_cadastro_recusa_placa_com_formato_invalido(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 2026, "placa": "123ABC"}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_cadastro_aceita_placa_antiga_e_mercosul(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    antiga = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 2026, "placa": "def-9876"}, headers=cabecalho
    )
    assert antiga.status_code == 201
    assert antiga.json()["placa"] == "DEF9876"

    mercosul = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 2026, "placa": "xyz9a99"}, headers=cabecalho
    )
    assert mercosul.status_code == 201
    assert mercosul.json()["placa"] == "XYZ9A99"


async def test_editar_recusa_chassi_com_tamanho_errado(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/motos/{dados['factor'].id}", json={"chassi": "CURTO123"}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_editar_recusa_data_de_compra_no_futuro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/motos/{dados['factor'].id}",
        json={"data_compra": "2999-01-01"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422


async def test_editar_recusa_marca_em_branco(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.patch(
        f"/motos/{dados['factor'].id}", json={"marca": "   "}, headers=cabecalho
    )
    assert resposta.status_code == 422


async def test_despesa_recusa_valor_zero(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "Revisão", "valor_centavos": 0, "data": "2026-01-01"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422


async def test_despesa_recusa_data_no_futuro(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "Revisão", "valor_centavos": 5_000, "data": "2999-01-01"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422


async def test_despesa_recusa_descricao_em_branco(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "   ", "valor_centavos": 5_000, "data": "2026-01-01"},
        headers=cabecalho,
    )
    assert resposta.status_code == 422
