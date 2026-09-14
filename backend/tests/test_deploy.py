"""O que precisa estar certo para o sistema subir numa hospedagem.

Estes testes não olham uma tela nem uma regra de negócio: olham as condições
em que o servidor aceita (ou recusa) subir. Cada um trava uma armadilha que
só apareceria depois de publicado, quando o estrago já é público.
"""

import pytest
from pydantic import ValidationError

from app.config import Config

# ------------------------------------------------- o segredo do JWT em produção

def test_producao_recusa_o_segredo_de_desenvolvimento():
    """O padrão está escrito no código, que vai pro GitHub. Quem o ler assina
    um token de DONO e entra como dono da loja."""
    with pytest.raises(ValidationError, match="desenvolvimento"):
        Config(ambiente="producao", jwt_segredo="dev-inseguro-troque-em-producao")


def test_producao_recusa_segredo_curto():
    with pytest.raises(ValidationError):
        Config(ambiente="producao", jwt_segredo="curto-demais")


def test_producao_aceita_segredo_de_verdade():
    cfg = Config(ambiente="producao", jwt_segredo="x" * 48)
    assert cfg.producao


def test_desenvolvimento_continua_sem_burocracia():
    """A trava é só de produção — o `dev.py` não pode passar a exigir nada."""
    assert Config(ambiente="dev", jwt_segredo="dev-inseguro").producao is False


# ------------------------------------------ a URL que a hospedagem entrega

def test_aceita_a_url_crua_do_postgres_da_railway():
    """A Railway publica `postgresql://…`. Sem o `+asyncpg` o SQLAlchemy
    carrega o driver síncrono e morre com "the greenlet library is required"."""
    cfg = Config(
        jwt_segredo="x" * 48,
        database_url="postgresql://usuario:senha@algo.railway.internal:5432/railway",
    )
    assert cfg.database_url.startswith("postgresql+asyncpg://")


def test_aceita_o_postgres_antigo_do_heroku():
    cfg = Config(jwt_segredo="x" * 48, database_url="postgres://u:s@host:5432/db")
    assert cfg.database_url.startswith("postgresql+asyncpg://")


def test_traduz_o_sslmode_que_o_asyncpg_nao_conhece():
    """A URL *externa* vem com `?sslmode=require` pendurado, e o asyncpg
    rejeita a conexão por parâmetro desconhecido antes de tentar."""
    cfg = Config(
        jwt_segredo="x" * 48,
        database_url="postgresql://u:s@host:5432/db?sslmode=require",
    )
    assert "sslmode" not in cfg.database_url
    assert "ssl=require" in cfg.database_url


def test_sslmode_disable_nao_vira_parametro_nenhum():
    cfg = Config(
        jwt_segredo="x" * 48,
        database_url="postgresql://u:s@host:5432/db?sslmode=disable",
    )
    assert "ssl" not in cfg.database_url.split("?")[-1]


# --------------------------------------------------------- a conferência de vida

async def test_health_responde_ok_com_o_banco_de_pe(cliente, engine, monkeypatch):
    # O `/health` encosta no engine global do `app.db` — em produção é ele
    # mesmo que serve as telas. Aqui o global aponta pro Postgres padrão, que
    # não existe na máquina de teste; o da fixture faz o papel dele.
    import app.main

    monkeypatch.setattr(app.main, "engine", engine)

    resposta = await cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["ok"] is True


async def test_health_responde_503_com_o_banco_fora(cliente, monkeypatch):
    """É isto que faz a hospedagem recusar um deploy com o banco errado.

    Com 200, um `DATABASE_URL` torto passa pela conferência, o deploy é dado
    como bem-sucedido e o erro só aparece quando o Carlos abre uma tela — com
    a versão boa já substituída.
    """
    import app.main

    class BancoMorto:
        def connect(self):
            raise OSError("connection refused")

    monkeypatch.setattr(app.main, "engine", BancoMorto())

    resposta = await cliente.get("/health")
    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["banco"] == "indisponivel"


# ------------------------------------------------- a documentação da API

def test_producao_fecha_as_tres_portas_da_documentacao():
    """Fechar só o `/docs` não fecha nada.

    O `/docs` é a página bonita; o conteúdo mora no `/openapi.json` — toda
    rota, todo campo, todo formato aceito, inclusive as rotas que só o dono
    enxerga. E o `/redoc` lê esse mesmo arquivo. Fechar um dos três e achar
    que fechou é o erro que este teste existe pra impedir.
    """
    from fastapi import FastAPI

    def montar(producao: bool) -> FastAPI:
        aberta = not producao
        return FastAPI(
            docs_url="/docs" if aberta else None,
            redoc_url="/redoc" if aberta else None,
            openapi_url="/openapi.json" if aberta else None,
        )

    em_producao = montar(producao=True)
    assert em_producao.docs_url is None
    assert em_producao.redoc_url is None
    assert em_producao.openapi_url is None

    # E em desenvolvimento continuam abertas — a documentação é útil.
    em_dev = montar(producao=False)
    assert em_dev.docs_url and em_dev.redoc_url and em_dev.openapi_url


def test_o_app_de_verdade_segue_a_regra_do_ambiente():
    """Amarra o teste acima ao app real, e não a uma cópia da lógica."""
    import app.main
    from app.config import get_config

    if get_config().producao:
        assert app.main.app.openapi_url is None
    else:
        assert app.main.app.openapi_url == "/openapi.json"


# ------------------------------------------- a chave do dono na hospedagem

async def _dono_de(sessao):
    from sqlalchemy import select

    from app.models.usuario import Papel, Usuario

    return (
        await sessao.execute(select(Usuario).where(Usuario.papel == Papel.DONO))
    ).scalars().first()


async def _rodar_garantir_dono(engine, monkeypatch, chave_dono="", redefinir=False):
    """Roda o `_garantir_dono` do arranque contra o banco de teste."""
    import sys
    from pathlib import Path

    from sqlalchemy.ext.asyncio import async_sessionmaker

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))

    import app.config
    import app.db

    monkeypatch.setattr(app.db, "Sessao", async_sessionmaker(engine, expire_on_commit=False))

    cfg = app.config.get_config()
    monkeypatch.setattr(cfg, "chave_dono", chave_dono)
    monkeypatch.setattr(app.config, "get_config", lambda: cfg)

    monkeypatch.setenv("CARLOSMOTO_REDEFINIR_CHAVE", "1" if redefinir else "")

    import producao

    await producao._garantir_dono()


async def test_a_variavel_da_chave_vale_pra_conta_que_ja_existe(engine, dados, monkeypatch):
    """O que travou o deploy de verdade.

    O dono já tinha nascido com uma chave sorteada. Preencher a
    `CARLOSMOTO_CHAVE_DONO` com outra não mudava nada — e a tela respondia
    "Chave de acesso inválida" com a variável certa, cadastrada e ignorada em
    silêncio. Uma variável que não faz o que diz é pior que variável nenhuma.
    """
    from app.seguranca import hash_chave
    from sqlalchemy.ext.asyncio import async_sessionmaker

    nova = "39S7-D88Q-W4HC-GYFE"
    await _rodar_garantir_dono(engine, monkeypatch, chave_dono=nova)

    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as s:
        dono = await _dono_de(s)
        assert dono.chave_hash == hash_chave(nova)


async def test_a_variavel_aceita_a_chave_digitada_torta(engine, dados, monkeypatch):
    """Quem cola a chave no painel pode colar sem traço ou em minúscula."""
    from app.seguranca import hash_chave
    from sqlalchemy.ext.asyncio import async_sessionmaker

    await _rodar_garantir_dono(engine, monkeypatch, chave_dono="  39s7 d88q w4hc gyfe ")

    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as s:
        dono = await _dono_de(s)
        assert dono.chave_hash == hash_chave("39S7-D88Q-W4HC-GYFE")


async def test_subir_de_novo_com_a_mesma_variavel_nao_mexe_em_nada(engine, dados, monkeypatch):
    """Senão cada deploy gravaria uma linha de histórico à toa — e, pior, a
    chave "trocaria" pela mesma, poluindo o log com um alarme falso."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    nova = "39S7-D88Q-W4HC-GYFE"
    await _rodar_garantir_dono(engine, monkeypatch, chave_dono=nova)

    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as s:
        antes = (await _dono_de(s)).chave_hash

    await _rodar_garantir_dono(engine, monkeypatch, chave_dono=nova)

    async with fabrica() as s:
        assert (await _dono_de(s)).chave_hash == antes


async def test_sem_a_variavel_a_chave_do_banco_fica_como_esta(engine, dados, monkeypatch):
    """A variável em branco não pode mexer em nada — quem trocou a chave pela
    tela do sistema não pode perdê-la no próximo deploy."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as s:
        antes = (await _dono_de(s)).chave_hash

    await _rodar_garantir_dono(engine, monkeypatch, chave_dono="")

    async with fabrica() as s:
        assert (await _dono_de(s)).chave_hash == antes
