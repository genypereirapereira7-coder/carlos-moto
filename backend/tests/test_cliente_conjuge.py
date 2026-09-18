"""Estado civil do cliente e os dados do cônjuge.

Casado: nome e telefone do cônjuge são obrigatórios (é por eles que a loja
acha a família quando o titular some). CPF do cônjuge é opcional.
"""


def _cliente(**extra) -> dict:
    base = {"nome": "Ana Teste", "cpf": "111.444.777-35", "telefone": "69992125902"}
    base.update(extra)
    return base


async def test_casado_guarda_os_dados_do_conjuge(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(
        casado=True,
        conjuge_nome="Bruno Teste",
        conjuge_cpf="529.982.247-25",
        conjuge_telefone="(69) 98442-0093",
    ), headers=dono)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["casado"] is True
    assert corpo["conjuge_nome"] == "Bruno Teste"
    assert corpo["conjuge_cpf"] == "52998224725"
    assert corpo["conjuge_telefone"] == "69984420093"


async def test_casado_sem_nome_ou_sem_telefone_do_conjuge_e_recusado(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    sem_nome = await cliente.post("/clientes", json=_cliente(
        casado=True, conjuge_telefone="69984420093"
    ), headers=dono)
    assert sem_nome.status_code == 422

    sem_fone = await cliente.post("/clientes", json=_cliente(
        cpf="529.982.247-25", casado=True, conjuge_nome="Bruno"
    ), headers=dono)
    assert sem_fone.status_code == 422


async def test_solteiro_nao_precisa_de_conjuge(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(casado=False), headers=dono)
    assert r.status_code == 201, r.text
    assert r.json()["casado"] is False
    assert r.json()["conjuge_nome"] is None


async def test_cpf_do_conjuge_invalido_e_recusado(cliente, dados, entrar):
    dono = await entrar(dados["carlos"].id)
    r = await cliente.post("/clientes", json=_cliente(
        casado=True, conjuge_nome="Bruno", conjuge_telefone="69984420093",
        conjuge_cpf="111.111.111-11",
    ), headers=dono)
    assert r.status_code == 422
