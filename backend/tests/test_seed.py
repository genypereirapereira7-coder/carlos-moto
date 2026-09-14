from sqlalchemy import select

from app import seed
from app.models import Moto, Papel, Usuario


async def test_semear_cria_carlos_e_estoque(sessao, monkeypatch):
    monkeypatch.setattr(seed, "Sessao", _fabrica_sessao(sessao))
    await seed.semear(detalhado=False)

    carlos = (
        await sessao.execute(select(Usuario).where(Usuario.nome == "Carlos"))
    ).scalar_one()
    assert carlos.papel == Papel.DONO
    assert carlos.ativo is True

    motos = (await sessao.execute(select(Moto))).scalars().all()
    assert len(motos) == len(seed.MOTOS)


async def test_rodar_de_novo_nao_duplica(sessao, monkeypatch):
    monkeypatch.setattr(seed, "Sessao", _fabrica_sessao(sessao))
    await seed.semear(detalhado=False)
    antes = len((await sessao.execute(select(Moto))).scalars().all())

    await seed.semear(detalhado=False)
    depois = len((await sessao.execute(select(Moto))).scalars().all())

    assert antes == depois


def _fabrica_sessao(sessao):
    """`seed.semear` abre sua própria sessão via `Sessao()`; nos testes,
    reaproveita a sessão do banco em memória em vez de bater no Postgres
    default do `config.py`."""

    class _CtxSessao:
        async def __aenter__(self):
            return sessao

        async def __aexit__(self, *_exc):
            return False

    def _fabrica():
        return _CtxSessao()

    return _fabrica
