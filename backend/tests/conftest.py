"""Fixtures. Os testes rodam em SQLite num arquivo temporário — sem docker,
sem Postgres.

**Arquivo, não `:memory:` com `StaticPool`.** Um banco em memória com
`StaticPool` força toda sessão a compartilhar a mesma conexão física — e duas
transações "simultâneas" (é exatamente o que `test_duas_vendas_simultaneas...`
verifica) na mesma conexão bruta não são simultâneas de verdade: uma
atrapalha a outra e a segunda acaba desfazendo o commit da primeira. Um
arquivo temporário deixa o SQLAlchemy abrir uma conexão por sessão, cada uma
com sua própria transação — o mesmo "trancar o arquivo inteiro" que o
comentário em `servicos/vendas.py` descreve para o SQLite do dev.
"""

import os
import tempfile

os.environ.setdefault(
    "CARLOSMOTO_JWT_SEGREDO", "segredo-de-teste-com-mais-de-32-bytes-pra-hmac-sha256"
)
os.environ.setdefault("CARLOSMOTO_AMBIENTE", "teste")

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_sessao, preparar_sqlite_serializavel
from app.main import app
from app.models import Base, Cliente, CondicaoMoto, Moto, Papel, Usuario
from app.seguranca import hash_chave, trava_login


@pytest_asyncio.fixture
async def engine():
    descritor, caminho = tempfile.mkstemp(suffix=".db")
    os.close(descritor)
    try:
        # `timeout`: quanto o SQLite espera por um arquivo travado por outra
        # conexão em vez de estourar `OperationalError: database is locked`
        # na hora — é o "esperar o primeiro terminar" que o Postgres faz
        # sozinho com `SELECT ... FOR UPDATE` e que aqui precisa ser pedido.
        motor = create_async_engine(
            f"sqlite+aiosqlite:///{caminho}", connect_args={"timeout": 30}
        )
        preparar_sqlite_serializavel(motor)
        async with motor.begin() as conexao:
            await conexao.run_sync(Base.metadata.create_all)
        yield motor
        await motor.dispose()
    finally:
        os.unlink(caminho)


@pytest_asyncio.fixture
async def sessao(engine):
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as s:
        yield s


@pytest_asyncio.fixture
async def cliente(engine):
    fabrica = async_sessionmaker(engine, expire_on_commit=False)

    async def sessao_de_teste():
        async with fabrica() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_sessao] = sessao_de_teste
    trava_login._por_chave.clear()

    transporte = ASGITransport(app=app)
    async with AsyncClient(transport=transporte, base_url="http://teste") as c:
        yield c

    app.dependency_overrides.clear()


# Chaves fixas nos testes pra o pareamento ser previsível. Em produção elas
# nascem aleatórias (`seguranca.gerar_chave`).
CHAVES = {"Carlos": "DONO-TEST-CHAV-2345", "João": "VEND-TEST-CHAV-6789"}


@pytest_asyncio.fixture
async def dados(sessao):
    """Um dono, um vendedor e duas motos disponíveis."""
    carlos = Usuario(
        nome="Carlos", chave_hash=hash_chave(CHAVES["Carlos"]), papel=Papel.DONO
    )
    joao = Usuario(
        nome="João",
        chave_hash=hash_chave(CHAVES["João"]),
        papel=Papel.VENDEDOR,
        ativo=True,
    )
    sessao.add_all([carlos, joao])
    await sessao.flush()

    cg160 = Moto(
        marca="Honda",
        modelo="CG160 Titan",
        ano=2026,
        cor="Vermelha",
        condicao=CondicaoMoto.NOVA,
        chassi=f"9C2KC{uuid.uuid4().hex[:12].upper()}",
        km=0,
        preco_centavos=1_699_000,
        criado_por=carlos.id,
    )
    factor = Moto(
        marca="Yamaha",
        modelo="Factor 125",
        ano=2025,
        cor="Azul",
        condicao=CondicaoMoto.USADA,
        chassi=f"9C6KE{uuid.uuid4().hex[:12].upper()}",
        placa="ABC1D23",
        km=8200,
        preco_centavos=1_150_000,
        criado_por=carlos.id,
    )
    maria = Cliente(nome="Maria Souza", cpf="52998224725", telefone="11999990000")

    sessao.add_all([cg160, factor, maria])
    await sessao.commit()

    return {"carlos": carlos, "joao": joao, "cg160": cg160, "factor": factor, "maria": maria}


@pytest_asyncio.fixture
async def entrar(cliente, sessao):
    """Pareia o aparelho com a chave do usuário e devolve o header pronto."""

    async def _entrar(usuario_id: int) -> dict[str, str]:
        usuario = await sessao.get(Usuario, usuario_id)
        assert usuario is not None, f"usuário {usuario_id} não existe"

        resposta = await cliente.post(
            "/auth/parear", json={"chave": CHAVES[usuario.nome]}
        )
        assert resposta.status_code == 200, resposta.text
        return {"Authorization": f"Bearer {resposta.json()['acesso']}"}

    return _entrar
