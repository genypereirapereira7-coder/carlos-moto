"""Dados de quem vendeu a moto pra loja.

São eles que vão no contrato e no comprovante de compra. Tudo opcional — a
loja preenche o que tiver na hora —, mas o que vier preenchido é validado
como qualquer outro campo do sistema.
"""


def _moto(**extra) -> dict:
    base = {
        "marca": "Honda",
        "modelo": "Biz 125",
        "ano": 2026,
        "placa": "FOR1234",
        "condicao": "USADA",
        "km": 100,
        "preco_centavos": 1_000_000,
    }
    base.update(extra)
    return base


async def test_cadastro_guarda_quem_vendeu_a_moto(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/motos", json=_moto(
        fornecedor_nome="Joana da Silva",
        fornecedor_cpf="111.444.777-35",
        fornecedor_email="Joana@Email.com",
        fornecedor_contato="(69) 99212-5902",
        fornecedor_casado=True,
        fornecedor_conjuge_nome="Pedro da Silva",
        fornecedor_conjuge_contato="69984420093",
    ), headers=dono)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["fornecedor_nome"] == "Joana da Silva"
    # CPF e telefone guardam só dígitos; e-mail vira minúscula.
    assert corpo["fornecedor_cpf"] == "11144477735"
    assert corpo["fornecedor_email"] == "joana@email.com"
    assert corpo["fornecedor_contato"] == "69992125902"
    assert corpo["fornecedor_casado"] is True
    assert corpo["fornecedor_conjuge_nome"] == "Pedro da Silva"


async def test_moto_sem_dados_do_vendedor_continua_passando(cliente, dados, entrar):
    """O cadastro rápido não pode ficar travado por causa de campo opcional."""
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/motos", json=_moto(placa="RAP1234"), headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["fornecedor_cpf"] is None
    assert r.json()["fornecedor_casado"] is None


async def test_cpf_e_email_errados_do_vendedor_sao_recusados(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    ruim = await cliente.post(
        "/motos", json=_moto(placa="RUI1234", fornecedor_cpf="111.111.111-11"), headers=dono
    )
    assert ruim.status_code == 422, "CPF que não fecha a conta não pode entrar"

    email = await cliente.post(
        "/motos", json=_moto(placa="MAI1234", fornecedor_email="isso nao e email"), headers=dono
    )
    assert email.status_code == 422

    fone = await cliente.post(
        "/motos", json=_moto(placa="FON1234", fornecedor_contato="123"), headers=dono
    )
    assert fone.status_code == 422


async def test_editar_completa_os_dados_do_vendedor_depois(cliente, dados, entrar):
    """O caminho normal: cadastra rápido e completa a compra na edição."""
    dono = await entrar(dados["carlos"].id)
    criada = await cliente.post("/motos", json=_moto(placa="DEP1234"), headers=dono)
    moto_id = criada.json()["id"]

    r = await cliente.patch(f"/motos/{moto_id}", json={
        "fornecedor_nome": "Carlos Vendedor",
        "fornecedor_cpf": "529.982.247-25",
        "fornecedor_casado": False,
    }, headers=dono)
    assert r.status_code == 200, r.text
    assert r.json()["fornecedor_cpf"] == "52998224725"
    assert r.json()["fornecedor_casado"] is False
