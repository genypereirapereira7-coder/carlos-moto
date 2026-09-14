"""As mensagens de validação chegam na tela em português.

A tela mostra o `msg` de cada erro embaixo do campo — se o Pydantic responde
"Field required", é isso que o dono lê. Ver `app/erros.py`."""

import uuid


async def _erros(resposta) -> list[str]:
    return [erro["msg"] for erro in resposta.json()["detail"]]


async def test_campo_faltando_vem_em_portugues(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/motos", json={"ano": 2026}, headers=cabecalho)

    assert resposta.status_code == 422
    mensagens = await _erros(resposta)
    assert "Campo obrigatório" in mensagens
    assert not any("required" in m.lower() for m in mensagens)


async def test_numero_invalido_vem_em_portugues(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos",
        json={"modelo": "Biz 125", "ano": "não é ano", "placa": "AAA1111"},
        headers=cabecalho,
    )

    assert resposta.status_code == 422
    assert await _erros(resposta) == ["Precisa ser um número inteiro"]


async def test_valor_fora_do_limite_vem_em_portugues(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        f"/motos/{dados['factor'].id}/despesas",
        json={"id_cliente": str(uuid.uuid4()), "descricao": "Revisão", "valor_centavos": 0, "data": "2026-01-01"},
        headers=cabecalho,
    )

    assert resposta.status_code == 422
    assert await _erros(resposta) == ["Precisa ser maior que 0"]


async def test_mensagem_dos_nossos_validadores_chega_limpa(cliente, dados, entrar):
    """Nossos validadores já escrevem em português — só não pode chegar com o
    "Value error, " que o Pydantic gruda na frente."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos",
        json={"modelo": "Biz 125", "ano": 2026, "placa": "123ABC"},
        headers=cabecalho,
    )

    assert resposta.status_code == 422
    assert await _erros(resposta) == ["Placa inválida — use o formato ABC1234 ou ABC1D23"]


async def test_loc_do_campo_continua_vindo(cliente, dados, entrar):
    """É pelo `loc` que a tela sabe qual quadrado pintar de vermelho."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post(
        "/motos", json={"modelo": "Biz 125", "ano": 1900, "placa": "AAA1111"}, headers=cabecalho
    )

    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["loc"] == ["body", "ano"]
