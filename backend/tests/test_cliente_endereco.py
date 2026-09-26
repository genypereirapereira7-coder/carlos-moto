"""E-mail e endereço do cliente.

Tudo opcional — o dono cadastra na pressa do balcão e completa depois. O que
não é opcional é estar certo quando vem preenchido: UF que não existe e CEP de
7 dígitos entrariam calados e só apareceriam no dia em que o contrato sai com
o endereço errado.

Os campos existem porque o sistema antigo da loja já guardava os dois em todo
cliente — sem eles, importar o cadastro antigo perderia o endereço de 1.782
pessoas.
"""


def _cliente(**extra) -> dict:
    base = {"nome": "Ana Teste", "cpf": "111.444.777-35", "telefone": "69992125902"}
    base.update(extra)
    return base


_ENDERECO = {
    "email": "ana@email.com",
    "endereco": "Av. Tancredo Neves",
    "numero": "1620",
    "complemento": "Sala 2",
    "bairro": "Setor 03",
    "cidade": "Ariquemes",
    "uf": "RO",
    "cep": "76870-000",
}


async def test_cadastra_com_email_e_endereco(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(**_ENDERECO), headers=dono)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["email"] == "ana@email.com"
    assert c["endereco"] == "Av. Tancredo Neves"
    assert c["numero"] == "1620"
    assert c["complemento"] == "Sala 2"
    assert c["bairro"] == "Setor 03"
    assert c["cidade"] == "Ariquemes"
    assert c["uf"] == "RO"
    # Guardado só com dígitos, como o CPF: formatar é problema da tela.
    assert c["cep"] == "76870000"


async def test_sem_endereco_continua_valendo(cliente, dados, entrar):
    """O cadastro rápido do balcão não pode virar um formulário obrigatório."""
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(), headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["email"] is None
    assert r.json()["cidade"] is None


async def test_email_torto_e_recusado(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(email="ana@"), headers=dono)
    assert r.status_code == 422
    assert "mail" in r.text.lower()


async def test_uf_que_nao_existe_e_recusada(cliente, dados, entrar):
    """"RR" e "RO" são um caractere de diferença, e a loja é de Rondônia."""
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(uf="XX"), headers=dono)
    assert r.status_code == 422
    assert "UF" in r.text


async def test_cep_com_numero_de_digitos_errado_e_recusado(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(cep="7687000"), headers=dono)
    assert r.status_code == 422
    assert "CEP" in r.text


async def test_email_e_uf_entram_arrumados(cliente, dados, entrar):
    """O dono digita como der: maiúscula no e-mail, minúscula na UF."""
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(
        email="  ANA@Email.COM  ", uf="ro", cep="76.870-000"
    ), headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "ana@email.com"
    assert r.json()["uf"] == "RO"
    assert r.json()["cep"] == "76870000"


async def test_edicao_completa_e_apaga_endereco(cliente, dados, entrar):
    """Completar depois é o caminho normal: cadastra no balcão, preenche o
    endereço quando o cliente traz o comprovante. E apagar tem que apagar."""
    dono = await entrar(dados["carlos"].id)
    novo = (await cliente.post("/clientes", json=_cliente(), headers=dono)).json()

    completou = await cliente.patch(f"/clientes/{novo['id']}", json=_ENDERECO, headers=dono)
    assert completou.status_code == 200, completou.text
    assert completou.json()["cidade"] == "Ariquemes"
    assert completou.json()["cep"] == "76870000"

    apagou = await cliente.patch(
        f"/clientes/{novo['id']}", json={"endereco": None, "cep": None, "email": None}, headers=dono
    )
    assert apagou.status_code == 200, apagou.text
    assert apagou.json()["endereco"] is None
    assert apagou.json()["cep"] is None
    assert apagou.json()["email"] is None
    # O que não foi mandado no PATCH continua lá.
    assert apagou.json()["cidade"] == "Ariquemes"


async def test_endereco_aparece_na_lista_e_no_detalhe(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    novo = (await cliente.post("/clientes", json=_cliente(**_ENDERECO), headers=dono)).json()

    lista = (await cliente.get("/clientes", headers=dono)).json()["clientes"]
    na_lista = next(c for c in lista if c["id"] == novo["id"])
    assert na_lista["cidade"] == "Ariquemes"

    detalhe = (await cliente.get(f"/clientes/{novo['id']}", headers=dono)).json()
    assert detalhe["email"] == "ana@email.com"
    assert detalhe["uf"] == "RO"
