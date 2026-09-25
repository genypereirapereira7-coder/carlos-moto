"""Aplicação FastAPI."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_config
from app.db import engine
from app.erros import tratar_erro_de_validacao
from app.rotas import (
    auth,
    clientes,
    financeiro,
    historico,
    motos,
    parcelas,
    relatorios,
    usuarios,
    vendas,
    ws,
)

log = logging.getLogger("carlosmoto")

cfg = get_config()


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    """Encosta no banco no arranque e grita se ele não responder.

    Sem isto o servidor sobe feliz, serve as duas telas e só falha quando
    alguém aperta um botão. Avisa, mas não derruba: em produção o banco pode
    subir depois da API.
    """
    try:
        async with engine.connect() as conexao:
            await conexao.execute(text("SELECT 1"))
    except Exception as erro:
        alvo = cfg.database_url.split("@")[-1]  # sem a senha
        log.error(
            "\n"
            "  ============================================================\n"
            "   O BANCO NAO RESPONDEU - as telas abrem, mas nada funciona\n"
            "  ============================================================\n"
            "   tentei: %s\n"
            "   erro:   %s\n"
            "\n"
            "   Rodando na sua maquina? Use o atalho que ja cuida disso:\n"
            "       cd backend && .venv/bin/python dev.py\n"
            "   Ele aponta pro SQLite, cria o banco e semeia o Carlos + estoque.\n"
            "  ============================================================\n",
            alvo,
            erro,
        )
    yield


# Em produção, as três portas da documentação ficam fechadas — e são três,
# não uma. Desligar só o `docs_url` fecha a página bonita e deixa de pé o
# `/openapi.json`, que é onde o conteúdo realmente está: toda rota, todo
# campo, todo formato aceito, incluindo as rotas que só o dono enxerga. É o
# mapa da casa entregue a quem passa na rua. O `/redoc` lê o mesmo arquivo.
_DOCUMENTACAO_ABERTA = not cfg.producao

app = FastAPI(
    title="Carlos Moto",
    description="Sistema de estoque e vendas da Carlos Moto",
    version="0.1.0",
    docs_url="/docs" if _DOCUMENTACAO_ABERTA else None,
    redoc_url="/redoc" if _DOCUMENTACAO_ABERTA else None,
    openapi_url="/openapi.json" if _DOCUMENTACAO_ABERTA else None,
    lifespan=ciclo_de_vida,
)

# As mensagens de validação do Pydantic saem em inglês; a tela mostra elas
# cruas embaixo do campo. Ver `app/erros.py`.
app.add_exception_handler(RequestValidationError, tratar_erro_de_validacao)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cabecalhos_de_seguranca(requisicao, proxima):
    """Cabeçalhos de segurança que uma hospedagem gerenciada não põe sozinha."""
    resposta = await proxima(requisicao)

    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    resposta.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
    )

    if cfg.csp:
        resposta.headers.setdefault("Content-Security-Policy", cfg.csp)

    if cfg.producao and requisicao.url.scheme == "https":
        resposta.headers.setdefault(
            "Strict-Transport-Security", f"max-age={cfg.hsts_max_age}"
        )

    return resposta


@app.middleware("http")
async def nao_cachear_service_worker(requisicao, proxima):
    """Service worker nunca em cache — senão o navegador guarda o `sw.js`
    antigo e a tela teima em rodar a versão anterior depois de qualquer
    alteração, sem erro nenhum aparecendo."""
    resposta = await proxima(requisicao)
    if requisicao.url.path.endswith("/sw.js"):
        resposta.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resposta


app.include_router(auth.rotas)
app.include_router(motos.rotas)
app.include_router(usuarios.rotas)
app.include_router(vendas.rotas)
app.include_router(clientes.rotas)
app.include_router(parcelas.rotas)
app.include_router(financeiro.rotas)
app.include_router(historico.rotas)
app.include_router(relatorios.rotas)
app.include_router(ws.rotas)


# Qual PWA tem página de verdade. `vendas/` hoje só tem manifesto e service
# worker — mandar a raiz pra lá dava 404.
_DIR_FRONTEND = (Path(__file__).resolve().parent.parent / cfg.dir_frontend).resolve()
_TELA_INICIAL = (
    "/vendas/" if (_DIR_FRONTEND / "vendas" / "index.html").is_file() else "/dono/"
)


@app.get("/", include_in_schema=False)
async def raiz():
    """Manda pra primeira tela que existe de verdade.

    Apontava fixo pra `/vendas/`, que hoje responde 404: aquele PWA tem só o
    manifesto e o service worker, sem página nenhuma. A porta da frente do
    sistema levava a um erro.
    """
    return RedirectResponse(_TELA_INICIAL)


@app.get("/health", tags=["infra"])
async def health(resposta: Response):
    """Diz se o sistema está de pé — e é isto que a hospedagem consulta pra
    decidir se o deploy deu certo.

    Devolve **503 quando o banco não responde**, e não 200. A diferença
    importa na hora de publicar: com 200, um `DATABASE_URL` errado passa pela
    conferência da hospedagem, o deploy é dado como bem-sucedido e o erro só
    aparece quando o Carlos abre uma tela. Com 503, a publicação falha ali
    mesmo e a versão anterior continua no ar.

    O corpo é o mesmo nos dois casos — quem lê o `ok` continua lendo igual.
    """
    banco_ok = True
    try:
        async with engine.connect() as conexao:
            await conexao.execute(text("SELECT 1"))
    except Exception:
        banco_ok = False

    if not banco_ok:
        resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ok": banco_ok,
        "ambiente": cfg.ambiente,
        "agora_utc": datetime.now(UTC).isoformat(),
        "banco": "ok" if banco_ok else "indisponivel",
    }


# Dois PWAs: vendas e dono, e uma pasta comum de utilitários compartilhados.
_frontend = (Path(__file__).resolve().parent.parent / cfg.dir_frontend).resolve()
for _nome in ("vendas", "dono"):
    _pasta = _frontend / _nome
    if _pasta.is_dir():
        app.mount(f"/{_nome}", StaticFiles(directory=_pasta, html=True), name=_nome)
if (_frontend / "comum").is_dir():
    app.mount("/comum", StaticFiles(directory=_frontend / "comum"), name="comum")


# ---------------------------------------------------------------- rodar direto

if __name__ == "__main__":
    """`python backend/app/main.py` — sobe o sistema igual ao `producao.py`.

    Este arquivo **define** a aplicação; quem a coloca no ar é o
    `backend/producao.py`. A confusão é fácil de fazer: num projeto Python é
    quase sempre o `main.py` que se manda rodar, e apontar a hospedagem pra
    cá parece a coisa óbvia.

    Só que rodar este arquivo sem esta parte não subia servidor nenhum: o
    módulo era importado, o objeto `app` criado, e o processo terminava em
    silêncio — deploy verde, log limpo, e a página respondendo
    "Application failed to respond". Um jeito bem ruim de falhar.

    Em vez de deixar essa armadilha aberta, este atalho leva pro caminho
    certo: mesma preparação de banco, mesma porta da hospedagem, mesmas
    travas de produção.
    """
    import sys
    from pathlib import Path as _Caminho

    # `python backend/app/main.py` deixa `backend/app` no caminho de import,
    # não `backend` — sem isto, `import producao` não acha nada.
    _BACKEND = _Caminho(__file__).resolve().parent.parent
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))

    import producao

    sys.exit(producao.main())
