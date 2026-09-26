"""Aba DADOS: o arquivo do sistema antigo, organizado.

Os CSVs destes testes são inventados. Dado de sistema antigo é sujo — separador
diferente, acento de Windows, linha torta — e é exatamente isso que precisa ser
exercitado, com arquivos que eu controlo.
"""

import io
import zipfile

from app import dicionario_antigo as dic


def _csv(*linhas: str) -> bytes:
    return "\n".join(linhas).encode("utf-8")


def _arquivo(nome: str, conteudo: bytes):
    return ("arquivos", (nome, conteudo, "text/csv"))


# -------------------------------------------------------------- tradução


def test_tabela_fiscal_e_reconhecida_como_ruido():
    """Tabela de estado, NCM e CFOP vem de fábrica com qualquer ERP do Brasil
    — não diz nada sobre esta loja."""
    for t in ("tb_estado", "ibpt", "cidade", "cfop", "cst_icms", "telas"):
        assert dic.e_ruido(t), f"{t} devia ser ruído"


def test_tabela_da_loja_nao_e_ruido():
    for t in ("pessoa", "creceber", "vendas_master", "produto"):
        assert not dic.e_ruido(t), f"{t} NÃO devia ser ruído"


def test_tabela_desconhecida_aparece_em_vez_de_sumir():
    """Sistema que ninguém viu ainda não pode desaparecer da tela."""
    assert not dic.e_ruido("tabela_que_ninguem_conhece")
    assert dic.nome_da_tabela("tabela_que_ninguem_conhece") == "Tabela que ninguem conhece"


def test_coluna_ganha_nome_de_gente():
    assert dic.nome_da_coluna("DTVENCIMENTO") == "Vencimento"
    assert dic.nome_da_coluna("VL_RESTANTE") == "Falta pagar"
    assert dic.nome_da_coluna("RAZAO") == "Nome / Razão social"


def test_coluna_de_controle_interno_fica_escondida():
    for c in ("FKCLIENTE", "REGISTRO_STATUS", "REMESSA_DATA", "PATH_PDF_BOLETO"):
        assert dic.coluna_escondida(c), f"{c} devia ficar escondida"


# -------------------------------------------------------------- importar


async def test_importa_csv_e_conta_as_linhas(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Sistema da loja, setembro"},
        files=[
            _arquivo("PESSOA.csv", _csv("CODIGO;RAZAO;CELULAR1", "1;Ana;69999990000", "2;Bruno;69988887777")),
            _arquivo("CRECEBER.csv", _csv("CODIGO;VALOR;DTVENCIMENTO;VL_RESTANTE", "1;300,00;2026-10-10;150,00")),
        ],
        headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["tabelas"] == 2
    assert r.json()["linhas"] == 3


async def test_importa_zip_com_os_csvs_dentro(cliente, dados, entrar):
    """É o formato que sai do conversor: um zip com tudo."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("PESSOA.csv", "CODIGO;RAZAO\n1;Ana\n")
        z.writestr("PRODUTO.csv", "CODIGO;DESCRICAO\n1;Capacete\n2;Óleo\n")
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Zip do conversor"},
        files=[("arquivos", ("export.zip", memoria.getvalue(), "application/zip"))],
        headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["linhas"] == 3


async def test_acento_de_windows_nao_vira_lixo(cliente, dados, entrar):
    """Sistema velho grava em cp1252. Lido como UTF-8 viraria `Jo?o`."""
    dono = await entrar(dados["carlos"].id)
    conteudo = "CODIGO;RAZAO\n1;João da Conceição\n".encode("cp1252")
    r = await cliente.post("/dados/importar",
        data={"descricao": "Acentuado"},
        files=[_arquivo("PESSOA.csv", conteudo)], headers=dono)
    assert r.status_code == 201, r.text
    lote = r.json()["lote_id"]
    tabela = (await cliente.get(f"/dados/{lote}/pessoa", headers=dono)).json()
    assert "João da Conceição" in str(tabela["linhas"])


async def test_um_arquivo_ruim_nao_derruba_os_outros(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Com um zip quebrado"},
        files=[
            _arquivo("PESSOA.csv", _csv("CODIGO;RAZAO", "1;Ana")),
            ("arquivos", ("quebrado.zip", b"isto nao e um zip", "application/zip")),
        ],
        headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["linhas"] == 1
    assert any("zip" in i for i in r.json()["ignorados"])


async def test_importacao_sem_nada_legivel_e_recusada(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Vazio"},
        files=[_arquivo("VAZIO.csv", b"")], headers=dono)
    assert r.status_code == 422


# ------------------------------------------------------------ apresentação


async def test_resumo_separa_o_que_importa_do_ruido_fiscal(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Com fiscal"},
        files=[
            _arquivo("PESSOA.csv", _csv("CODIGO;RAZAO", "1;Ana")),
            _arquivo("CRECEBER.csv", _csv("CODIGO;VALOR", "1;100")),
            _arquivo("TB_ESTADO.csv", _csv("CODIGO;NOME", "1;RO", "2;SP")),
            _arquivo("IBPT.csv", _csv("CODIGO;ALIQ", "1;0.5")),
        ],
        headers=dono)
    lote = r.json()["lote_id"]
    resumo = (await cliente.get(f"/dados/{lote}", headers=dono)).json()

    nomes = [t["tabela"] for t in resumo["tabelas"]]
    fiscais = [t["tabela"] for t in resumo["fiscais"]]
    assert nomes == ["creceber", "pessoa"], "contas a receber vem antes, é o que importa"
    assert set(fiscais) == {"tb_estado", "ibpt"}
    assert resumo["tabelas"][0]["titulo"] == "Contas a receber"


async def test_tabela_esconde_coluna_de_controle_interno(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Colunas"},
        files=[_arquivo("CRECEBER.csv", _csv(
            "CODIGO;VALOR;DTVENCIMENTO;FKCLIENTE;REGISTRO_STATUS",
            "1;300,00;2026-10-10;7;OK"))],
        headers=dono)
    lote = r.json()["lote_id"]
    t = (await cliente.get(f"/dados/{lote}/creceber", headers=dono)).json()
    titulos = [c["titulo"] for c in t["colunas"]]
    assert "Vencimento" in titulos
    assert not any("Fkcliente" in x for x in titulos)
    assert t["escondidas"] == 2


async def test_busca_dentro_da_tabela(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Busca"},
        files=[_arquivo("PESSOA.csv", _csv("CODIGO;RAZAO", "1;Ana Souza", "2;Bruno Lima", "3;Carla Souza"))],
        headers=dono)
    lote = r.json()["lote_id"]
    t = (await cliente.get(f"/dados/{lote}/pessoa?busca=souza", headers=dono)).json()
    assert t["total"] == 2


async def test_so_o_dono_ve_os_dados_antigos(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    r = await cliente.get("/dados/lotes", headers=vendedor)
    assert r.status_code == 403


# ------------------------------------------------- backup .sql do MySQL

_DUMP = """
/*!40101 SET NAMES utf8 */;
DROP TABLE IF EXISTS `clientes`;
CREATE TABLE `clientes` (
  `codcli` varchar(6) NOT NULL,
  `nome` varchar(60) DEFAULT NULL,
  `cnpj_cpf` varchar(18) DEFAULT NULL,
  `obs_venda` text,
  `limite` decimal(10,2) DEFAULT '0.00',
  PRIMARY KEY (`codcli`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
INSERT INTO `clientes` VALUES ('00071','CLIENTE UM DE TESTE','111.444.777-35','TROCA EM 14/01, DEU A MOTO (ABC1D23), R$1.000,00','0.00'),
('00072','TESTE, O DA ESQUINA','123.456.789-09',NULL,'500.50'),
('00073','JOSE D\\'TESTE','529.982.247-25','Obs com ) parentese e , virgula','0.00');
DROP TABLE IF EXISTS `it_pedid`;
CREATE TABLE `it_pedid` (
  `nrped` int(11) NOT NULL,
  `descr_item` varchar(80) DEFAULT NULL,
  `placa` varchar(10) DEFAULT NULL,
  `marca` varchar(30) DEFAULT NULL,
  `km` varchar(10) DEFAULT NULL,
  `cst_icms` varchar(3) DEFAULT NULL
) ENGINE=InnoDB;
INSERT INTO `it_pedid` VALUES (1,'HONDA CG 160 FAN','NCH1D23','HONDA','18500','000');
DROP TABLE IF EXISTS `tipi`;
CREATE TABLE `tipi` (`ncm` varchar(10), `descricao` text) ENGINE=InnoDB;
INSERT INTO `tipi` VALUES ('87111000','Motocicletas');
"""


def _sql(nome: str = "BACKUP.SQL", texto: str = _DUMP):
    return ("arquivos", (nome, texto.encode("utf-8"), "application/sql"))


async def test_importa_backup_sql_do_mysql(cliente, dados, entrar):
    """O backup do sistema antigo é um .sql só, com todas as tabelas dentro —
    o dono não tem que converter nada pra CSV antes."""
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Backup do sistema de motos"},
        files=[_sql()], headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["tabelas"] == 3
    assert r.json()["linhas"] == 5


async def test_sql_preserva_texto_com_virgula_parentese_e_apostrofo(cliente, dados, entrar):
    """O caso que quebra quem lê dump com regex: vírgula e parêntese dentro do
    texto, e apóstrofo escapado. Se partir no lugar errado, todo o cadastro
    entra com as colunas deslocadas — CPF no campo de nome."""
    dono = await entrar(dados["carlos"].id)
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Texto sujo"}, files=[_sql()], headers=dono)).json()["lote_id"]
    t = (await cliente.get(f"/dados/{lote}/clientes?tudo=true", headers=dono)).json()
    campos = [c["campo"] for c in t["colunas"]]
    por_nome = {l[campos.index("nome")]: l for l in t["linhas"]}

    assert "TESTE, O DA ESQUINA" in por_nome
    assert por_nome["TESTE, O DA ESQUINA"][campos.index("cnpj_cpf")] == "123.456.789-09"
    assert "JOSE D'TESTE" in por_nome
    primeiro = por_nome["CLIENTE UM DE TESTE"]
    assert primeiro[campos.index("obs_venda")].endswith("(ABC1D23), R$1.000,00")
    assert primeiro[campos.index("limite")] == "0.00"


async def test_sql_traduz_os_nomes_do_sistema_de_motos(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Tradução"}, files=[_sql()], headers=dono)).json()["lote_id"]
    resumo = (await cliente.get(f"/dados/{lote}", headers=dono)).json()

    uteis = {t["tabela"]: t["titulo"] for t in resumo["tabelas"]}
    assert uteis["clientes"] == "Clientes"
    assert uteis["it_pedid"] == "Motos e itens vendidos"
    # TIPI é a tabela de NCM da Receita: igual em toda loja do Brasil.
    assert "tipi" in {t["tabela"] for t in resumo["fiscais"]}

    t = (await cliente.get(f"/dados/{lote}/it_pedid", headers=dono)).json()
    titulos = [c["titulo"] for c in t["colunas"]]
    assert titulos[:4] == ["Nº da venda", "Descrição", "Placa", "Marca"]
    assert "KM" in titulos
    assert not any("Cst" in x for x in titulos)  # tributação fica escondida


async def test_mostrar_tudo_traz_de_volta_as_colunas_escondidas(cliente, dados, entrar):
    """Esconder tributação é pra tela ficar legível, não pra sonegar dado: um
    dia o dono precisa justo da coluna que eu escondi."""
    dono = await entrar(dados["carlos"].id)
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Mostrar tudo"}, files=[_sql()], headers=dono)).json()["lote_id"]

    normal = (await cliente.get(f"/dados/{lote}/it_pedid", headers=dono)).json()
    tudo = (await cliente.get(f"/dados/{lote}/it_pedid?tudo=true", headers=dono)).json()
    assert normal["escondidas"] == 1
    assert tudo["escondidas"] == 0
    assert "cst_icms" in [c["campo"] for c in tudo["colunas"]]
    assert len(tudo["colunas"]) == len(normal["colunas"]) + 1


async def test_sql_dentro_do_zip(cliente, dados, entrar):
    """Backup grande vem zipado — e o dono manda o zip como recebeu."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("BACKUP_26-09-2026.SQL", _DUMP)
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Zip com o backup"},
        files=[("arquivos", ("backup.zip", memoria.getvalue(), "application/zip"))],
        headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["linhas"] == 5


async def test_arquivo_de_outro_tipo_diz_o_que_serve(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/dados/importar",
        data={"descricao": "Tipo errado"},
        files=[("arquivos", ("planilha.xlsx", b"PK\x03\x04qualquer", "application/vnd.ms-excel")),
               _sql()],
        headers=dono)
    assert r.status_code == 201, r.text
    assert any(".csv" in x and ".sql" in x for x in r.json()["ignorados"])
    assert r.json()["linhas"] == 5


async def test_coluna_importante_vem_antes_do_lixo_do_erp(cliente, dados, entrar):
    """A ordem do `CREATE TABLE` do ERP põe flag de configuração antes do nome
    do cliente. Quem abre a tabela quer nome e CPF primeiro."""
    dono = await entrar(dados["carlos"].id)
    dump = """
CREATE TABLE `clientes` (
  `vendedor` varchar(6),
  `ativo` char(1),
  `codcli` varchar(6),
  `nome` varchar(60),
  `cnpj_cpf` varchar(18),
  `fone` varchar(15)
) ENGINE=InnoDB;
INSERT INTO `clientes` VALUES ('01','S','00071','CLIENTE DE TESTE','111.444.777-35','6999990000');
"""
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Ordem"}, files=[_sql(texto=dump)], headers=dono)).json()["lote_id"]
    t = (await cliente.get(f"/dados/{lote}/clientes", headers=dono)).json()
    titulos = [c["titulo"] for c in t["colunas"]]
    assert titulos[:5] == ["Cód. cliente", "Nome", "CPF / CNPJ", "Telefone", "Ativo"]
    assert titulos.index("Nome") < titulos.index("Vendedor")


async def test_colunas_de_mesmo_titulo_ganham_o_nome_cru(cliente, dados, entrar):
    """`st` e `status` traduzem os dois pra "Situação". Três colunas "Situação"
    lado a lado não dizem em qual o dono deve olhar."""
    dono = await entrar(dados["carlos"].id)
    dump = """
CREATE TABLE `parcelas` (`nrped` int, `st` char(1), `status` varchar(10), `valor` decimal(10,2));
INSERT INTO `parcelas` VALUES (1,'A','ABERTA','300.00');
"""
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Repetidos"}, files=[_sql(texto=dump)], headers=dono)).json()["lote_id"]
    t = (await cliente.get(f"/dados/{lote}/parcelas", headers=dono)).json()
    titulos = [c["titulo"] for c in t["colunas"]]
    assert "Situação (st)" in titulos
    assert "Situação (status)" in titulos
    assert "Valor" in titulos  # só desambigua o que repete


async def test_create_de_uma_linha_nao_engole_o_insert_seguinte(cliente, dados, entrar):
    """O CREATE de uma linha só fazia a tabela seguinte desaparecer inteira,
    sem erro nenhum — o pior tipo de defeito num importador."""
    dono = await entrar(dados["carlos"].id)
    dump = """
CREATE TABLE `tipi` (`ncm` varchar(10), `descricao` text) ENGINE=InnoDB;
INSERT INTO `tipi` VALUES ('87111000','Motocicletas');
CREATE TABLE `clientes` (`codcli` varchar(6), `nome` varchar(60));
INSERT INTO `clientes` VALUES ('00071','CLIENTE UM'),('00072','CLIENTE DOIS');
"""
    r = await cliente.post("/dados/importar",
        data={"descricao": "Uma linha"}, files=[_sql(texto=dump)], headers=dono)
    assert r.json()["tabelas"] == 2
    t = (await cliente.get(f"/dados/{r.json()['lote_id']}/clientes", headers=dono)).json()
    assert t["total"] == 2


async def test_insert_com_lista_de_colunas_propria(cliente, dados, entrar):
    """Formato do phpMyAdmin. A lista do INSERT manda, não a do CREATE — aqui
    ela está fora de ordem de propósito."""
    dono = await entrar(dados["carlos"].id)
    dump = """
CREATE TABLE `clientes` (`codcli` varchar(6), `nome` varchar(60), `fone` varchar(15));
INSERT INTO `clientes` (`nome`, `codcli`) VALUES ('CLIENTE UM','00071');
"""
    r = await cliente.post("/dados/importar",
        data={"descricao": "phpMyAdmin"}, files=[_sql(texto=dump)], headers=dono)
    t = (await cliente.get(f"/dados/{r.json()['lote_id']}/clientes", headers=dono)).json()
    campos = [c["campo"] for c in t["colunas"]]
    assert t["linhas"][0][campos.index("nome")] == "CLIENTE UM"
    assert t["linhas"][0][campos.index("codcli")] == "00071"


async def test_lote_mostra_o_tamanho_na_lista(cliente, dados, entrar):
    """Com duas importações do mesmo sistema, descrição e data não dizem qual é
    a completa e qual foi o teste."""
    dono = await entrar(dados["carlos"].id)
    await cliente.post("/dados/importar",
        data={"descricao": "Backup"}, files=[_sql()], headers=dono)
    lista = (await cliente.get("/dados/lotes", headers=dono)).json()
    assert lista[0]["linhas"] == 5
    assert lista[0]["tabelas"] == 3
