"""Sobe tudo pra rodar na sua máquina, com um comando só.

    cd backend
    .venv/bin/python dev.py

Assume os padrões de desenvolvimento, cria o banco se não existir, semeia se
estiver vazio e sobe o servidor. Nada aqui vale em produção.
"""

import asyncio
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BANCO = AQUI / "_dev.db"

sys.stdout.reconfigure(line_buffering=True, errors="replace")

# Antes de qualquer `import app.*`: o `get_config` é cacheado e o `app.db` cria
# a engine no import.
PADROES = {
    "CARLOSMOTO_DATABASE_URL": f"sqlite+aiosqlite:///{BANCO.as_posix()}",
    "CARLOSMOTO_JWT_SEGREDO": "dev-local-inseguro-nao-use-em-producao-32bytes",
    "CARLOSMOTO_AMBIENTE": "dev",
}
for chave, valor in PADROES.items():
    os.environ.setdefault(chave, valor)


async def preparar() -> None:
    from app.db import engine
    from app.models import Base

    async with engine.begin() as conexao:
        await conexao.run_sync(Base.metadata.create_all)

    # Depois do `create_all`: é o que leva coluna nova pra um banco que já
    # existe, sem apagar o que o dono já cadastrou.
    from migracoes import aplicar

    for feita in await aplicar(engine):
        print(f"migração: {feita}", flush=True)

    from app.seed import semear

    await semear(detalhado=False)
    await engine.dispose()


def main() -> None:
    porta = int(os.environ.get("PORTA") or 8000)
    novo = not BANCO.exists()

    print(f"banco:   {BANCO}{'  (criando agora)' if novo else ''}", flush=True)
    asyncio.run(preparar())

    print(
        "\ntelas pra abrir no navegador:"
        f"\n  vendas   http://127.0.0.1:{porta}/vendas/     toque em 'Criar minha conta'"
        f"\n  dono     http://127.0.0.1:{porta}/dono/       usuario: Carlos"
        f"\n  API      http://127.0.0.1:{porta}/docs"
        "\n\nVendedor novo fica pendente — entre como Carlos, aba Vendedores,"
        "\ntoque em Liberar.\n",
        flush=True,
    )

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=porta,
        reload=True,
        reload_dirs=[str(AQUI / "app")],
    )


if __name__ == "__main__":
    sys.exit(main())
