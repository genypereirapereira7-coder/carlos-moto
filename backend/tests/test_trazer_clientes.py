"""Trazer o cadastro do sistema antigo pro cadastro de clientes.

Cada caso aqui é uma sujeira que existe de verdade no backup da Monte São
Motos: nascimento `0001-01-01` (611 cadastros), UF `"R"`, CPF que não fecha no
dígito verificador (16), número da casa `"0"` (481), CNPJ no lugar do CPF (9),
a mesma pessoa cadastrada duas vezes (4). A regra em todas: **o campo ruim fica
de fora, não a pessoa**.
"""

_COLUNAS = (
    "codcli", "nome", "cnpj_cpf", "insc_rg", "dtnasc", "email", "fone", "celular",
    "endereco", "numero", "complemento", "bairro", "cidade", "estado", "cep",
    "est_civil", "conjuge", "fone_conj", "obs_venda", "historico",
)


def _dump(*pessoas: dict) -> str:
    """Monta um backup .sql com as colunas que o sistema antigo tem."""
    def valor(v):
        return "NULL" if v is None else "'" + str(v).replace("'", "\\'") + "'"

    linhas = ",\n".join(
        "(" + ",".join(valor(p.get(c)) for c in _COLUNAS) + ")" for p in pessoas
    )
    colunas = ", ".join(f"`{c}` varchar(160)" for c in _COLUNAS)
    return f"CREATE TABLE `clientes` ({colunas});\nINSERT INTO `clientes` VALUES\n{linhas};\n"


def _arquivo(*pessoas: dict):
    return ("arquivos", ("BACKUP.SQL", _dump(*pessoas).encode("utf-8"), "application/sql"))


async def _importar(cliente, dono, *pessoas: dict) -> dict:
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Backup"}, files=[_arquivo(*pessoas)], headers=dono)).json()["lote_id"]
    r = await cliente.post(f"/dados/{lote}/trazer/clientes", headers=dono)
    assert r.status_code == 200, r.text
    return r.json()


async def _por_cpf(cliente, dono, cpf: str) -> dict | None:
    # `por_pagina` alto porque aqui a lista é pequena e o teste quer ver tudo.
    lista = (await cliente.get("/clientes?por_pagina=200", headers=dono)).json()["clientes"]
    return next((c for c in lista if c["cpf"] == cpf), None)


# --------------------------------------------------------- o caminho bom

async def test_traz_o_cadastro_inteiro(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    resumo = await _importar(cliente, dono, {
        "codcli": "00071", "nome": "CLIENTE DE TESTE", "cnpj_cpf": "111.444.777-35",
        "insc_rg": "1234567", "dtnasc": "1988-07-19", "email": "CLIENTE@Email.com",
        "celular": "(69) 99212-5902", "endereco": "Av. Tancredo Neves", "numero": "1620",
        "complemento": "Fundos", "bairro": "Setor 03", "cidade": "Ariquemes",
        "estado": "ro", "cep": "76870-000", "est_civil": "1", "conjuge": "MARIA DA SILVA",
        "fone_conj": "69984420135", "obs_venda": "Cliente antigo da loja",
    })
    assert resumo["criados"] == 1
    c = await _por_cpf(cliente, dono, "11144477735")
    assert c["nome"] == "CLIENTE DE TESTE"
    assert c["rg"] == "1234567"
    assert c["nascimento"] == "1988-07-19"
    assert c["email"] == "cliente@email.com"
    assert c["telefone"] == "69992125902"
    assert c["endereco"] == "Av. Tancredo Neves"
    assert c["numero"] == "1620"
    assert c["bairro"] == "Setor 03"
    assert c["cidade"] == "Ariquemes"
    assert c["uf"] == "RO"
    assert c["cep"] == "76870000"
    assert c["casado"] is True
    assert c["conjuge_nome"] == "MARIA DA SILVA"
    assert c["conjuge_telefone"] == "69984420135"
    assert "Cliente antigo da loja" in c["observacao"]


async def test_celular_ganha_do_fixo(cliente, dados, entrar):
    """É por onde a loja fala com o cliente hoje."""
    dono = await entrar(dados["carlos"].id)
    await _importar(cliente, dono, {
        "nome": "ANA", "cnpj_cpf": "111.444.777-35",
        "fone": "6935351111", "celular": "69992125902",
    })
    assert (await _por_cpf(cliente, dono, "11144477735"))["telefone"] == "69992125902"


# ------------------------------------------- campo torto sai, pessoa fica

async def test_nascimento_em_branco_do_sistema_antigo_nao_entra(cliente, dados, entrar):
    """`0001-01-01` é a data vazia do sistema antigo: 611 cadastros vieram
    assim. Entrando, a loja teria 611 clientes nascidos no ano 1."""
    dono = await entrar(dados["carlos"].id)
    resumo = await _importar(cliente, dono,
        {"nome": "ANA", "cnpj_cpf": "111.444.777-35", "dtnasc": "0001-01-01"},
        {"nome": "BRUNO", "cnpj_cpf": "123.456.789-09", "dtnasc": "7197-03-02"},
    )
    assert resumo["criados"] == 2  # as duas pessoas entraram
    assert (await _por_cpf(cliente, dono, "11144477735"))["nascimento"] is None
    assert (await _por_cpf(cliente, dono, "12345678909"))["nascimento"] is None
    assert resumo["descartados"]["nascimento"] == 2


async def test_uf_email_e_cep_tortos_saem_sozinhos(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    resumo = await _importar(cliente, dono, {
        "nome": "ANA", "cnpj_cpf": "111.444.777-35",
        "estado": "R", "email": "ana@", "cep": "7687", "cidade": "Ariquemes",
    })
    assert resumo["criados"] == 1
    c = await _por_cpf(cliente, dono, "11144477735")
    assert c["uf"] is None
    assert c["email"] is None
    assert c["cep"] is None
    # o que estava bom continua lá
    assert c["cidade"] == "Ariquemes"
    assert resumo["descartados"] == {"uf": 1, "email": 1, "cep": 1}


async def test_numero_zero_nao_vira_numero_da_casa(cliente, dados, entrar):
    """481 cadastros têm `numero` = "0" — é como o sistema antigo diz "sem
    número". No contrato sairia "Rua X, 0"."""
    dono = await entrar(dados["carlos"].id)
    await _importar(cliente, dono, {
        "nome": "ANA", "cnpj_cpf": "111.444.777-35",
        "endereco": "Linha 605", "numero": "0",
    })
    c = await _por_cpf(cliente, dono, "11144477735")
    assert c["numero"] is None
    assert c["endereco"] == "Linha 605"


async def test_cpf_que_nao_fecha_entra_mas_fica_avisado(cliente, dados, entrar):
    """16 cadastros têm CPF com dígito verificador errado. Recusar perderia o
    cliente; entrar calado deixaria contrato sair com CPF errado."""
    dono = await entrar(dados["carlos"].id)
    resumo = await _importar(cliente, dono,
        {"nome": "ANA", "cnpj_cpf": "111.111.111-11"})
    assert resumo["criados"] == 1
    c = await _por_cpf(cliente, dono, "11111111111")
    assert "dígito verificador" in c["observacao"]


# ------------------------------------------------ quem não dá pra trazer

async def test_sem_cpf_cnpj_e_cpf_incompleto_ficam_na_lista(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    resumo = await _importar(cliente, dono,
        {"codcli": "1", "nome": "SEM DOCUMENTO", "cnpj_cpf": None},
        {"codcli": "2", "nome": "OFICINA LTDA", "cnpj_cpf": "12.345.678/0001-95"},
        {"codcli": "3", "nome": "CPF CURTO", "cnpj_cpf": "1234567"},
        {"codcli": "4", "nome": "BOM", "cnpj_cpf": "111.444.777-35"},
    )
    assert resumo["criados"] == 1
    motivos = {p["nome"]: p["motivo"] for p in resumo["pulados"]}
    assert motivos["SEM DOCUMENTO"] == "sem CPF"
    assert "CNPJ" in motivos["OFICINA LTDA"]
    assert "7 dígitos" in motivos["CPF CURTO"]
    # o código do sistema antigo vai junto, pra ele achar a pessoa lá
    assert {p["codigo"] for p in resumo["pulados"]} == {"1", "2", "3"}


# --------------------------------------------------------- não estraga nada

async def test_pessoa_repetida_no_arquivo_vira_um_cadastro(cliente, dados, entrar):
    """4 CPFs aparecem duas vezes no backup. A segunda linha completa a
    primeira em vez de estourar o índice único do CPF."""
    dono = await entrar(dados["carlos"].id)
    resumo = await _importar(cliente, dono,
        {"nome": "CLIENTE DOIS", "cnpj_cpf": "111.444.777-35", "cidade": "Ariquemes"},
        {"nome": "CLIENTE DOIS", "cnpj_cpf": "111.444.777-35", "celular": "69992125902"},
    )
    assert resumo["criados"] == 1
    assert resumo["juntados"] == 1
    c = await _por_cpf(cliente, dono, "11144477735")
    assert c["cidade"] == "Ariquemes"
    assert c["telefone"] == "69992125902"


async def test_nao_sobrescreve_o_que_o_dono_digitou(cliente, dados, entrar):
    """Ele digitou olhando o cliente na frente dele; o sistema antigo pode
    estar velho. Só o que está em branco é preenchido."""
    dono = await entrar(dados["carlos"].id)
    meu = (await cliente.post("/clientes", json={
        "nome": "Cliente Dois", "cpf": "111.444.777-35", "telefone": "69992125902",
    }, headers=dono)).json()

    resumo = await _importar(cliente, dono, {
        "nome": "CLIENTE DOIS ANTIGO", "cnpj_cpf": "111.444.777-35",
        "celular": "6935359999", "cidade": "Ariquemes", "estado": "RO",
    })
    assert resumo["criados"] == 0
    assert resumo["completados"] == 1

    c = (await cliente.get(f"/clientes/{meu['id']}", headers=dono)).json()
    assert c["nome"] == "Cliente Dois"       # o nome dele fica
    assert c["telefone"] == "69992125902"    # o telefone dele fica
    assert c["cidade"] == "Ariquemes"        # o que faltava veio do antigo
    assert c["uf"] == "RO"


async def test_rodar_duas_vezes_nao_duplica(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    pessoa = {"nome": "ANA", "cnpj_cpf": "111.444.777-35", "cidade": "Ariquemes"}
    lote = (await cliente.post("/dados/importar",
        data={"descricao": "Backup"}, files=[_arquivo(pessoa)], headers=dono)).json()["lote_id"]

    um = (await cliente.post(f"/dados/{lote}/trazer/clientes", headers=dono)).json()
    dois = (await cliente.post(f"/dados/{lote}/trazer/clientes", headers=dono)).json()
    assert um["criados"] == 1
    assert dois["criados"] == 0
    assert dois["completados"] == 0
    quantos = sum(1 for c in (await cliente.get("/clientes?por_pagina=200", headers=dono)).json()["clientes"]
                  if c["cpf"] == "11144477735")
    assert quantos == 1


# ---------------------------------------------------------- estado civil

async def test_casado_sem_nome_do_conjuge_nao_e_marcado_casado(cliente, dados, entrar):
    """Marcar "casado" sem o nome criaria cadastro que a própria tela considera
    incompleto, e ele bateria nisso ao editar qualquer outra coisa. O estado
    civil do sistema antigo vai pra observação, pra não sumir."""
    dono = await entrar(dados["carlos"].id)
    await _importar(cliente, dono,
        {"nome": "ANA", "cnpj_cpf": "111.444.777-35", "est_civil": "1"})
    c = await _por_cpf(cliente, dono, "11144477735")
    assert c["casado"] is None
    assert "estado civil casado" in c["observacao"]


async def test_estado_civil_nao_informado_fica_sem_resposta(cliente, dados, entrar):
    """Código 0 são 1.032 cadastros: "não perguntado", que não é "não casado"."""
    dono = await entrar(dados["carlos"].id)
    await _importar(cliente, dono,
        {"nome": "ANA", "cnpj_cpf": "111.444.777-35", "est_civil": "0"},
        {"nome": "BRUNO", "cnpj_cpf": "123.456.789-09", "est_civil": "2"},
    )
    assert (await _por_cpf(cliente, dono, "11144477735"))["casado"] is None
    assert (await _por_cpf(cliente, dono, "12345678909"))["casado"] is False


async def test_so_o_dono_traz_clientes(cliente, dados, entrar):
    vendedor = await entrar(dados["joao"].id)
    import uuid
    r = await cliente.post(f"/dados/{uuid.uuid4()}/trazer/clientes", headers=vendedor)
    assert r.status_code == 403
