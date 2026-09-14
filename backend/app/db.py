"""Engine, sessão e dependência de banco."""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Só o import já registra os ouvintes que gravam o histórico e barram o
# apagar. Fica aqui, e não em `main.py`, porque quem mexe no banco sempre
# passa por este módulo — inclusive os scripts de carga e os testes.
import app.historico  # noqa: F401  (efeito colateral proposital)
from app.config import get_config

_cfg = get_config()


def preparar_sqlite_serializavel(motor: AsyncEngine) -> None:
    """SQLite começa a transação de forma preguiçosa: só trava o arquivo no
    primeiro `INSERT`/`UPDATE`, não no primeiro `SELECT`. Duas vendas
    simultâneas da mesma moto então não serializam na leitura, só na
    escrita — e a segunda estoura `database is locked` em vez de esperar a
    primeira terminar e encontrar `status=VENDIDA`, como o Postgres faria
    sozinho com o `SELECT ... FOR UPDATE` de `servicos/vendas.py`.

    `BEGIN IMMEDIATE` pede o lock de escrita já na abertura da transação: a
    segunda conexão espera (até o `timeout` da conexão) em vez de falhar, e
    só então lê o estado que a primeira acabou de gravar. Sem efeito nenhum
    no Postgres — só se aplica quando o dialeto é SQLite (dev e testes).
    """
    if motor.dialect.name != "sqlite":
        return

    @event.listens_for(motor.sync_engine, "connect")
    def _sem_begin_automatico(conexao_dbapi, _registro):
        # Desliga o "BEGIN" que o driver pysqlite emite sozinho no primeiro
        # SELECT — é ele quem esconde o `BEGIN IMMEDIATE` de baixo.
        conexao_dbapi.isolation_level = None

    @event.listens_for(motor.sync_engine, "begin")
    def _begin_immediate(conexao):
        conexao.exec_driver_sql("BEGIN IMMEDIATE")


engine = create_async_engine(
    _cfg.database_url,
    echo=False,
    pool_pre_ping=True,  # a hospedagem derruba conexão ociosa; sem isso a primeira query do dia falha
    # E aposenta a conexão antes disso acontecer. O `pre_ping` conserta
    # depois do fato (descobre que morreu e abre outra); trocar de meia em
    # meia hora evita o encontro. Numa loja que fica horas sem ninguém
    # mexendo, é a diferença entre abrir a tela e ver um erro no primeiro
    # clique da manhã.
    pool_recycle=1800,
)
preparar_sqlite_serializavel(engine)

Sessao = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_sessao() -> AsyncGenerator[AsyncSession, None]:
    async with Sessao() as sessao:
        try:
            yield sessao
            await sessao.commit()
        except Exception:
            await sessao.rollback()
            raise
