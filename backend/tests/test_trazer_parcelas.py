"""Trazer as parcelas em aberto do sistema antigo pra aba PARCELAS.

Parcela no sistema novo não vive solta: pendura numa venda, que pendura numa
moto e num cliente. Cada caso aqui é uma situação real do backup da Monte São
Motos: item que é serviço e não moto ("TRANSFERECIA DE NOME"), placa escondida
dentro da descrição escrita à mão, ano que não veio, venda cuja linha não está
no arquivo, e a mesma importação rodada duas vezes.
"""

_CLIENTE_COLS = ("codcli", "nome", "cnpj_cpf")
_PEDIDO_COLS = ("nrped", "codcli", "nome", "emissao", "valor", "status")
_ITEM_COLS = ("nrped", "descr_item")
_PARCELA_COLS = ("nrped", "codcli", "nome", "pc", "valor", "vencimento", "data_pagto")


def _tabela(nome: str, colunas: tuple[str, ...], linhas: list[dict]) -> str:
    def valor(v):
        return "NULL" if v is None else "'" + str(v).replace("'", "\\'") + "'"
    if not linhas:
        return ""
    corpo = ",\n".join("(" + ",".join(valor(l.get(c)) for c in colunas) + ")" for l in linhas)
    cols = ", ".join(f"`{c}` varchar(200)" for c in colunas)
    return f"CREATE TABLE `{nome}` ({cols});\nINSERT INTO `{nome}` VALUES\n{corpo};\n"


def _dump(clientes, pedidos, itens, parcelas) -> bytes:
    return "".join([
        _tabela("clientes", _CLIENTE_COLS, clientes),
        _tabela("pedidos", _PEDIDO_COLS, pedidos),
        _tabela("it_pedid", _ITEM_COLS, itens),
        _tabela("parcelas", _PARCELA_COLS, parcelas),
    ]).encode("utf-8")


async def _preparar(cliente, dono, clientes, pedidos, itens, parcelas) -> str:
    r = await cliente.post("/dados/importar",
        data={"descricao": "Backup"},
        files=[("arquivos", ("BACKUP.SQL", _dump(clientes, pedidos, itens, parcelas), "application/sql"))],
        headers=dono)
    assert r.status_code == 201, r.text
    lote = r.json()["lote_id"]
    # Os clientes vêm primeiro: a parcela precisa de alguém pra pendurar.
    await cliente.post(f"/dados/{lote}/trazer/clientes", headers=dono)
    return lote


# Uma venda completa: cliente com CPF válido, pedido, item de moto, 2 parcelas.
_BASE = dict(
    clientes=[{"codcli": "00071", "nome": "CLIENTE DE TESTE", "cnpj_cpf": "111.444.777-35"}],
    pedidos=[{"nrped": "1042", "codcli": "00071", "nome": "CLIENTE DE TESTE",
              "emissao": "2024-03-15", "valor": "8500.00", "status": "A prazo"}],
    itens=[{"nrped": "1042", "descr_item": "BIZ 125 ES 2013/2014 NDB1A23 R: 123456"}],
    parcelas=[
        {"nrped": "1042", "codcli": "00071", "nome": "CLIENTE DE TESTE", "pc": "07",
         "valor": "650.00", "vencimento": "2026-10-10", "data_pagto": "0001-01-01"},
        {"nrped": "1042", "codcli": "00071", "nome": "CLIENTE DE TESTE", "pc": "08",
         "valor": "650.00", "vencimento": "2026-11-10", "data_pagto": "0001-01-01"},
    ],
)


async def test_traz_moto_venda_e_carne(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono, **_BASE)

    r = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert r["motos"] == 1
    assert r["vendas"] == 1
    assert r["parcelas"] == 2
    assert r["centavos"] == 130_000

    # A moto saiu da descrição escrita à mão pelo balcão.
    motos = (await cliente.get("/motos", headers=dono)).json()
    moto = next(m for m in motos if m["placa"] == "NDB1A23")
    assert moto["marca"] == "Honda"
    assert moto["ano"] == 2014          # entre fabricação e modelo, o ano-modelo
    assert moto["status"] == "VENDIDA"
    assert moto["preco_centavos"] == 850_000
    assert "BIZ 125 ES" in moto["modelo"]

    # E a parcela aparece na tela de quem deve, com o número do carnê de papel.
    pendentes = (await cliente.get("/parcelas", headers=dono)).json()
    minhas = [p for p in pendentes if p["cliente_nome"] == "CLIENTE DE TESTE"]
    assert {p["numero"] for p in minhas} == {7, 8}
    assert sum(p["valor_centavos"] for p in minhas) == 130_000


async def test_venda_guarda_o_preco_cheio_e_diz_onde_esta_o_resto(cliente, dados, entrar):
    """O que o cliente já pagou está em `recebidas` e não é trazido. A venda
    guarda o valor real dela (R$ 8.500) mesmo com só R$ 1.300 em aberto — senão
    o histórico do cliente mentiria o preço da moto."""
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono, **_BASE)
    await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)

    lista = (await cliente.get("/clientes?busca=CLIENTE", headers=dono)).json()["clientes"]
    detalhe = (await cliente.get(f"/clientes/{lista[0]['id']}", headers=dono)).json()
    venda = detalhe["comprou"][0]
    assert venda["preco_venda_centavos"] == 850_000
    # O que ainda falta é só o que veio em aberto.
    assert venda["saldo_devedor_centavos"] == 130_000
    assert venda["qtd_parcelas"] == 2


async def test_item_que_e_servico_nao_vira_moto(cliente, dados, entrar):
    """"TRANSFERECIA DE NOME" é serviço. Virar moto seria inventar veículo."""
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono,
        clientes=_BASE["clientes"],
        pedidos=[{"nrped": "99", "codcli": "00071", "nome": "CLIENTE DE TESTE",
                  "emissao": "2024-03-15", "valor": "150.00", "status": "A prazo"}],
        itens=[{"nrped": "99", "descr_item": "TRANSFERECIA DE NOME"}],
        parcelas=[{"nrped": "99", "codcli": "00071", "nome": "CLIENTE DE TESTE", "pc": "01",
                   "valor": "150.00", "vencimento": "2026-10-10", "data_pagto": "0001-01-01"}])

    r = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert r["motos"] == 0
    assert r["parcelas"] == 0
    assert r["puladas"][0]["motivo"].startswith("o item da venda não é uma moto")
    assert r["puladas"][0]["parcelas"] == 1


async def test_parcela_sem_a_venda_no_arquivo_fica_de_fora(cliente, dados, entrar):
    """108 das 455 parcelas reais são assim: a parcela está no backup, mas a
    linha da venda dela não."""
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono,
        clientes=_BASE["clientes"], pedidos=_BASE["pedidos"], itens=_BASE["itens"],
        parcelas=_BASE["parcelas"] + [
            {"nrped": "555", "codcli": "00071", "nome": "CLIENTE DE TESTE", "pc": "03",
             "valor": "400.00", "vencimento": "2026-12-10", "data_pagto": "0001-01-01"}])

    r = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert r["parcelas"] == 2
    pulada = next(p for p in r["puladas"] if p["numero"] == "555")
    assert "não está no backup" in pulada["motivo"]


async def test_parcela_ja_paga_nao_entra(cliente, dados, entrar):
    """As pagas moram em `recebidas`. Uma com `data_pagto` de verdade aqui é
    parcela quitada, e trazer viraria cobrança de quem não deve."""
    dono = await entrar(dados["carlos"].id)
    paga = dict(_BASE["parcelas"][0], pc="06", data_pagto="2026-04-02")
    lote = await _preparar(cliente, dono,
        clientes=_BASE["clientes"], pedidos=_BASE["pedidos"], itens=_BASE["itens"],
        parcelas=[paga, _BASE["parcelas"][1]])

    r = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert r["parcelas"] == 1
    pendentes = (await cliente.get("/parcelas", headers=dono)).json()
    assert {p["numero"] for p in pendentes if p["cliente_nome"] == "CLIENTE DE TESTE"} == {8}


async def test_cliente_que_nao_entrou_no_sistema_nao_gera_divida_orfa(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono,
        clientes=[{"codcli": "00071", "nome": "SEM DOCUMENTO", "cnpj_cpf": None}],
        pedidos=_BASE["pedidos"], itens=_BASE["itens"], parcelas=_BASE["parcelas"])

    r = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert r["vendas"] == 0
    assert "cliente desta venda não entrou" in r["puladas"][0]["motivo"]


async def test_ano_que_nao_veio_usa_o_da_venda_e_avisa(cliente, dados, entrar):
    """17 das 74 vendas reais não têm ano na descrição. Perder a dívida por
    causa disso seria pior; entrar calado, também."""
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono,
        clientes=_BASE["clientes"], pedidos=_BASE["pedidos"],
        itens=[{"nrped": "1042", "descr_item": "HONDA/ NXR 150 BROS ES P:OHV1234"}],
        parcelas=_BASE["parcelas"])

    await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)
    motos = (await cliente.get("/motos", headers=dono)).json()
    moto = next(m for m in motos if m["placa"] == "OHV1234")
    assert moto["ano"] == 2024                       # o ano da venda
    assert "não constava no sistema antigo" in moto["observacao"]


async def test_rodar_duas_vezes_nao_duplica(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    lote = await _preparar(cliente, dono, **_BASE)

    um = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    dois = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert um["parcelas"] == 2
    assert dois["parcelas"] == 0
    assert dois["motos"] == 0
    pendentes = (await cliente.get("/parcelas", headers=dono)).json()
    assert len([p for p in pendentes if p["cliente_nome"] == "CLIENTE DE TESTE"]) == 2


async def test_placa_que_ja_existe_no_sistema_nao_atropela_a_moto_de_la(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    minha = await cliente.post("/motos", json={
        "marca": "Honda", "modelo": "Biz 125 ES", "ano": 2014, "placa": "NDB1A23",
        "km": 12000, "condicao": "USADA", "preco_centavos": 900_000,
    }, headers=dono)
    assert minha.status_code == 201, minha.text

    lote = await _preparar(cliente, dono, **_BASE)
    r = (await cliente.post(f"/dados/{lote}/trazer/parcelas", headers=dono)).json()
    assert r["motos"] == 0
    assert "já está em outra moto" in r["puladas"][0]["motivo"]


async def test_so_o_dono_traz_parcelas(cliente, dados, entrar):
    import uuid
    vendedor = await entrar(dados["joao"].id)
    r = await cliente.post(f"/dados/{uuid.uuid4()}/trazer/parcelas", headers=vendedor)
    assert r.status_code == 403
