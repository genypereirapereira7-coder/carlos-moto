"""A rota que recebe o sistema antigo pela tela.

É o caminho que funciona a partir da nuvem: o navegador não deixa um site
vasculhar o disco, mas deixa a pessoa escolher um arquivo. O que se testa aqui
são as recusas — quem pode mandar, o que pode mandar e de que tamanho. A cópia
em si precisa de um PostgreSQL de verdade e é testada no navegador.
"""

import pytest

from app.rotas import migracao as rota


@pytest.fixture
def com_destino(monkeypatch):
    """Finge que existe um banco na nuvem pra receber a cópia."""
    monkeypatch.setattr(rota, "_destino", lambda: "postgresql://nuvem/de-mentira")
    monkeypatch.setattr(rota, "_rodando", lambda: False)


def _arquivo(nome: str, tamanho: int = 64):
    return {"arquivo": (nome, b"x" * tamanho, "application/octet-stream")}


async def test_estado_diz_que_da_pra_enviar_da_nuvem(cliente, dados, entrar, com_destino):
    """Na nuvem não há disco pra ler, mas há para onde copiar — e é isso que
    acende o botão de enviar."""
    cabecalho = await entrar(dados["carlos"].id)
    corpo = (await cliente.get("/migracao/estado", headers=cabecalho)).json()
    assert corpo["envio"] is True
    assert corpo["disponivel"] is False       # nenhum sistema antigo neste disco
    assert ".zip" in corpo["formatos"]


async def test_vendedor_nao_migra(cliente, dados, entrar, com_destino):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.post("/migracao/enviar", files=_arquivo("dados.db"), headers=cabecalho)
    assert resposta.status_code == 403


async def test_access_e_firebird_sao_recusados_com_explicacao(cliente, dados, entrar, com_destino):
    """Eles precisam de um driver que só existe na máquina do cliente. Recusar
    com o motivo é melhor do que aceitar e falhar na cópia, meia hora depois."""
    cabecalho = await entrar(dados["carlos"].id)
    for nome in ("clientes.mdb", "base.accdb", "dados.fdb", "dados.gdb"):
        resposta = await cliente.post("/migracao/enviar", files=_arquivo(nome), headers=cabecalho)
        assert resposta.status_code == 415, nome
        assert "computador" in resposta.json()["detail"]


async def test_formato_desconhecido_diz_o_que_aceita(cliente, dados, entrar, com_destino):
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/migracao/enviar", files=_arquivo("planilha.xlsx"), headers=cabecalho)
    assert resposta.status_code == 415
    assert ".zip" in resposta.json()["detail"]


async def test_arquivo_grande_demais_e_cortado_no_meio_do_envio(cliente, dados, entrar, com_destino, monkeypatch):
    """O limite é conferido enquanto o arquivo chega, e não depois: esperar o
    fim pra então recusar é gravar o arquivo inteiro no disco à toa."""
    monkeypatch.setattr(rota, "LIMITE_BYTES", 100)
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/migracao/enviar", files=_arquivo("grande.db", 5_000), headers=cabecalho)
    assert resposta.status_code == 413
    assert "MB" in resposta.json()["detail"]


async def test_sem_banco_na_nuvem_nao_aceita_nada(cliente, dados, entrar, monkeypatch):
    monkeypatch.setattr(rota, "_destino", lambda: "")
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/migracao/enviar", files=_arquivo("dados.db"), headers=cabecalho)
    assert resposta.status_code == 409


async def test_uma_copia_de_cada_vez(cliente, dados, entrar, com_destino, monkeypatch):
    monkeypatch.setattr(rota, "_rodando", lambda: True)
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/migracao/enviar", files=_arquivo("dados.db"), headers=cabecalho)
    assert resposta.status_code == 409
    assert "rodando" in resposta.json()["detail"]
