"""Pareamento por chave de acesso — o sistema não tem senha.

A chave é digitada uma vez por aparelho. Depois disso quem mantém o acesso é
o refresh token, e nada mais é pedido.
"""

from tests.conftest import CHAVES


async def test_parear_com_a_chave_certa_funciona(cliente, dados):
    resposta = await cliente.post("/auth/parear", json={"chave": CHAVES["Carlos"]})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["papel"] == "DONO"
    assert corpo["nome"] == "Carlos"
    # É o refresh que faz o aparelho não pedir mais nada.
    assert corpo["refresh"]


async def test_chave_errada_e_recusada(cliente, dados):
    resposta = await cliente.post("/auth/parear", json={"chave": "XXXX-YYYY-ZZZZ-9999"})
    assert resposta.status_code == 401


async def test_chave_aceita_digitacao_torta(cliente, dados):
    """Quem lê a chave de um bilhete não pode ser reprovado por um traço."""
    torta = CHAVES["Carlos"].lower().replace("-", " ")
    resposta = await cliente.post("/auth/parear", json={"chave": f"  {torta}  "})
    assert resposta.status_code == 200


async def test_nao_existe_mais_login_por_senha(cliente, dados):
    """As rotas de senha saíram do sistema — não ficaram desativadas."""
    assert (await cliente.post("/auth/login", json={"usuario": "Carlos", "segredo": "x"})).status_code == 404
    assert (await cliente.post("/auth/cadastro", json={"nome": "X", "senha": "y"})).status_code == 404


async def test_aparelho_pareado_continua_entrando_sem_a_chave(cliente, dados):
    """O ponto da mudança: a chave serve uma vez; depois o aparelho se vira
    sozinho com o refresh."""
    parear = (await cliente.post("/auth/parear", json={"chave": CHAVES["Carlos"]})).json()

    renovado = await cliente.post("/auth/renovar", json={"refresh": parear["refresh"]})
    assert renovado.status_code == 200

    # O refresh roda a cada uso: o anterior é aposentado na troca.
    assert renovado.json()["refresh"] != parear["refresh"]

    # E o acesso renovado abre o sistema, sem a chave aparecer em momento algum.
    cabecalho = {"Authorization": f"Bearer {renovado.json()['acesso']}"}
    assert (await cliente.get("/motos", headers=cabecalho)).status_code == 200


async def test_dono_cria_vendedor_e_recebe_a_chave_dele(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    novo = await cliente.post("/usuarios", json={"nome": "Vendedora Nova"}, headers=cabecalho)
    assert novo.status_code == 201

    chave = novo.json()["chave"]
    assert len(chave) >= 16

    # A chave entregue funciona, e já entra como vendedor.
    entrada = await cliente.post("/auth/parear", json={"chave": chave})
    assert entrada.status_code == 200
    assert entrada.json()["papel"] == "VENDEDOR"


async def test_chave_nova_aposenta_a_anterior(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    nova = await cliente.post(f"/usuarios/{dados['carlos'].id}/chave", headers=cabecalho)
    assert nova.status_code == 200

    assert (await cliente.post("/auth/parear", json={"chave": nova.json()["chave"]})).status_code == 200
    assert (await cliente.post("/auth/parear", json={"chave": CHAVES["Carlos"]})).status_code == 401


async def test_trocar_a_chave_nao_desconecta_quem_ja_esta_dentro(cliente, dados, entrar):
    """A chave só pareia aparelho novo. Pra tirar um aparelho do ar existe a
    tela de sessões — trocar a chave não faria isso."""
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.post(f"/usuarios/{dados['carlos'].id}/chave", headers=cabecalho)
    assert (await cliente.get("/motos", headers=cabecalho)).status_code == 200


async def test_vendedor_desativado_nao_pareia(cliente, dados, entrar):
    cabecalho = await entrar(dados["carlos"].id)
    await cliente.delete(f"/usuarios/{dados['joao'].id}", headers=cabecalho)
    assert (await cliente.post("/auth/parear", json={"chave": CHAVES["João"]})).status_code == 401


async def test_vendedor_nao_cria_conta_nem_troca_chave(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    assert (await cliente.post("/usuarios", json={"nome": "X"}, headers=cabecalho)).status_code == 403
    assert (await cliente.post(f"/usuarios/{dados['joao'].id}/chave", headers=cabecalho)).status_code == 403


async def test_vendedor_nao_pode_ver_relatorios(cliente, dados, entrar):
    cabecalho = await entrar(dados["joao"].id)
    resposta = await cliente.get(
        "/relatorios/resumo",
        params={"data_inicio": "2026-01-01", "data_fim": "2026-12-31"},
        headers=cabecalho,
    )
    assert resposta.status_code == 403
