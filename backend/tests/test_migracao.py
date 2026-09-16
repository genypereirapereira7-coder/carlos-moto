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


# ------------------------------------------- achar o sistema antigo sozinho

async def test_procurar_lista_o_que_achou(cliente, dados, entrar, com_destino):
    """Na máquina do cliente devolve os bancos encontrados; na nuvem, lista
    vazia — e é assim que a tela sabe que ali o jeito é receber o arquivo."""
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.get("/migracao/procurar", headers=cabecalho)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo["achados"], list)
    for achado in corpo["achados"]:
        assert {"caminho", "nome", "tipo", "bytes", "modificado", "arquivos"} <= achado.keys()


async def test_vendedor_nao_procura(cliente, dados, entrar, com_destino):
    cabecalho = await entrar(dados["joao"].id)
    assert (await cliente.get("/migracao/procurar", headers=cabecalho)).status_code == 403


async def test_caminho_de_fora_da_varredura_e_recusado(cliente, dados, entrar, com_destino):
    """A trava que impede a rota de virar "leia qualquer arquivo do servidor".

    Sem ela, bastaria pedir `/etc/passwd` — ou o banco do próprio sistema — e o
    conteúdo subiria pro espelho.
    """
    cabecalho = await entrar(dados["carlos"].id)
    for caminho in ("/etc/passwd", "/etc/hosts", "../../backend/_dev.db"):
        resposta = await cliente.post("/migracao/passo-1", json={"caminho": caminho}, headers=cabecalho)
        assert resposta.status_code == 400, caminho
        assert "encontrados" in resposta.json()["detail"]


async def test_sem_nada_configurado_e_sem_escolha_nao_copia(cliente, dados, entrar, com_destino, monkeypatch):
    """Nenhuma origem na variável de ambiente e nenhum caminho escolhido: a
    rota diz que não achou, em vez de estourar lá dentro."""
    monkeypatch.setattr(rota, "_origem", lambda: "")
    cabecalho = await entrar(dados["carlos"].id)
    resposta = await cliente.post("/migracao/passo-1", json={}, headers=cabecalho)
    assert resposta.status_code == 409
    assert "não achei" in resposta.json()["detail"].lower()


# ------------------------------------------------ a varredura tem que parar

def test_varredura_para_no_tempo_e_avisa(monkeypatch, tmp_path):
    """O limite de tempo não é enfeite: no HD velho de uma loja a varredura
    pode demorar minutos, e o dono fica olhando uma tela parada.

    Aqui o limite vira zero, então ela para na primeira volta — e o que
    importa é que o resultado venha marcado como incompleto. "Não achei nada"
    e "parei no meio" são respostas diferentes.
    """
    from app.servicos import migracao as servico

    (tmp_path / "CLIENTES.DBF").write_bytes(b"x" * 100)
    monkeypatch.setattr(servico, "TEMPO_LIMITE_S", 0.0)

    achados = servico.procurar_sistemas_antigos(raizes=[tmp_path])
    assert achados == [] or all(a["busca_incompleta"] for a in achados)


def test_varredura_respeita_o_teto_de_arquivos(monkeypatch, tmp_path):
    """Mesma ideia pelo outro lado: disco gigante não pode virar varredura
    infinita."""
    from app.servicos import migracao as servico

    for numero in range(30):
        (tmp_path / f"tabela{numero}.dbf").write_bytes(b"x" * 10)
    monkeypatch.setattr(servico, "TETO_DE_ARQUIVOS", 5)

    achados = servico.procurar_sistemas_antigos(raizes=[tmp_path])
    assert all(a["busca_incompleta"] for a in achados)


def test_pasta_de_dbf_conta_como_um_sistema_so(tmp_path):
    """Em dBase e Clipper cada tabela é um arquivo — o sistema é a pasta. A
    lista tem que mostrar um candidato, não trinta."""
    from app.servicos import migracao as servico

    for nome in ("CLIENTES", "CONTRATOS", "TICKETS"):
        (tmp_path / f"{nome}.DBF").write_bytes(b"x" * 100)

    achados = servico.procurar_sistemas_antigos(raizes=[tmp_path])
    assert len(achados) == 1
    assert achados[0]["tipo"] == "dbf"
    assert achados[0]["arquivos"] == 3
    assert achados[0]["caminho"] == str(tmp_path)
