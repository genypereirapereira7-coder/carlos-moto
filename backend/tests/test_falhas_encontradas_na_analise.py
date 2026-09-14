"""Regressão das falhas achadas na análise do sistema inteiro.

Cada teste aqui nasceu de um problema que existia de verdade e foi
reproduzido antes de ser corrigido.
"""

import uuid
from datetime import date

import pytest

from app.config import Config
from app.models.base import hoje


# ------------------------------------------- produção com segredo de dev

def test_producao_recusa_subir_com_o_segredo_de_desenvolvimento():
    """O padrão está no código, que é público: com ele, qualquer um assina um
    token de DONO. O servidor subia calado assim."""
    with pytest.raises(ValueError, match="JWT_SEGREDO"):
        Config(
            ambiente="producao",
            jwt_segredo="dev-inseguro-troque-em-producao",
            database_url="sqlite+aiosqlite:///:memory:",
        )


def test_producao_recusa_segredo_curto():
    with pytest.raises(ValueError, match="JWT_SEGREDO"):
        Config(
            ambiente="producao",
            jwt_segredo="curto-demais",
            database_url="sqlite+aiosqlite:///:memory:",
        )


def test_producao_aceita_segredo_de_verdade():
    cfg = Config(
        ambiente="producao",
        jwt_segredo="t" * 48,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    assert cfg.producao is True


def test_desenvolvimento_continua_simples():
    """Exigir segredo forte pra rodar na própria máquina só atrapalharia."""
    assert Config(ambiente="dev", database_url="sqlite+aiosqlite:///:memory:").producao is False


# ------------------------------------------------ relatório no fuso certo

async def test_venda_das_22h_do_ultimo_dia_entra_no_relatorio_do_mes(cliente, dados, entrar):
    """22h30 de 31/08 em Brasília já é 1º/09 em UTC. O relatório de agosto
    montava o intervalo sem fuso e perdia essa venda."""
    cabecalho = await entrar(dados["carlos"].id)
    venda = await cliente.post(
        "/vendas",
        json={
            "id_cliente": str(uuid.uuid4()),
            "moto_id": dados["cg160"].id,
            "cliente_id": dados["maria"].id,
            "forma_pagamento": "A_VISTA",
            "preco_venda_centavos": 1_000_000,
            "data_venda": "2026-08-31T22:30:00-03:00",
        },
        headers=cabecalho,
    )
    assert venda.status_code == 201, venda.text

    agosto = await cliente.get(
        "/relatorios/resumo",
        params={"data_inicio": "2026-08-01", "data_fim": "2026-08-31"},
        headers=cabecalho,
    )
    assert agosto.json()["qtd_vendas"] == 1
    assert agosto.json()["total_centavos"] == 1_000_000

    setembro = await cliente.get(
        "/relatorios/resumo",
        params={"data_inicio": "2026-09-01", "data_fim": "2026-09-30"},
        headers=cabecalho,
    )
    assert setembro.json()["qtd_vendas"] == 0


# A falha do bcrypt com senha acentuada saiu junto com as senhas: o sistema
# passou a usar chave de acesso gerada pelo servidor, e não há mais senha
# digitada por ninguém. Ver `tests/test_auth.py`.


# ------------------------------------------------------- porta da frente

async def test_raiz_nao_manda_pra_uma_tela_que_nao_existe(cliente):
    """Apontava fixo pra /vendas/, que responde 404."""
    resposta = await cliente.get("/", follow_redirects=False)
    assert resposta.status_code in (307, 302)
    destino = resposta.headers["location"]

    tela = await cliente.get(destino, follow_redirects=False)
    assert tela.status_code != 404, f"a raiz manda pra {destino}, que não existe"
