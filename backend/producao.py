"""Sobe o sistema numa hospedagem de verdade (Railway, Render, Fly).

    python backend/producao.py

Faz, nesta ordem:

  1. confere as variáveis que não podem faltar, e explica em português cada
     uma que faltar — em vez de subir e quebrar na primeira tela;
  2. cria as tabelas que ainda não existem;
  3. garante que o dono existe, e grita a chave de acesso dele uma vez;
  4. sobe o servidor na porta que a hospedagem mandar.

Diferente do `dev.py`, aqui **não** entra estoque nem cliente de exemplo: em
produção o banco começa vazio, do jeito que o dono pediu.
"""

import asyncio
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

# `python backend/producao.py` roda com a raiz do repositório como diretório
# atual, e aí `import app` não acha nada. Pôr esta pasta no caminho deixa o
# comando funcionar de onde quer que ele seja chamado.
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

sys.stdout.reconfigure(line_buffering=True, errors="replace")


# ----------------------------------------------------------- antes de tudo

def _falar(titulo: str, *linhas: str) -> None:
    """Recado emoldurado. O log da hospedagem é uma parede de texto; o que
    importa tem que saltar dela."""
    largura = 64
    print("\n  " + "=" * largura, flush=True)
    print(f"   {titulo}", flush=True)
    print("  " + "=" * largura, flush=True)
    for linha in linhas:
        print(f"   {linha}", flush=True)
    print("  " + "=" * largura + "\n", flush=True)


def conferir_ambiente() -> None:
    """Recusa subir com configuração faltando, dizendo o que fazer.

    Sem isto o servidor sobe alegre e só falha quando alguém aperta um botão:
    o banco padrão aponta pra um `localhost` que não existe no contêiner, e o
    segredo padrão do JWT está escrito no código — qualquer um que leia o
    repositório assina um token de DONO e entra como dono da loja.
    """
    faltando: list[str] = []

    if not (os.environ.get("CARLOSMOTO_DATABASE_URL") or os.environ.get("DATABASE_URL")):
        faltando.append(
            "DATABASE_URL — na Railway, adicione um banco Postgres ao projeto e\n"
            "     ligue a variável ao serviço (Variables > Add Reference)."
        )

    segredo = os.environ.get("CARLOSMOTO_JWT_SEGREDO", "")
    if not segredo or segredo.startswith("dev-") or len(segredo) < 32:
        faltando.append(
            "CARLOSMOTO_JWT_SEGREDO — o segredo que assina os tokens de acesso.\n"
            "     Gere um assim, e cole o resultado na variável:\n"
            '       python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    if faltando:
        _falar(
            "NAO DA PRA SUBIR: FALTA CONFIGURACAO",
            *[f"{i}. {item}" for i, item in enumerate(faltando, 1)],
            "",
            "Nada foi iniciado. Preencha as variaveis e mande subir de novo.",
        )
        raise SystemExit(1)


# O arquivo se chama `producao.py`: ligar o modo de produção é a razão dele
# existir, não uma coisa pra lembrar de configurar. Isto acende as travas de
# uma vez — documentação fechada, HSTS, e a recusa de subir com o segredo de
# desenvolvimento (`app/config.py`).
conferir_ambiente()
os.environ.setdefault("CARLOSMOTO_AMBIENTE", "producao")


# ------------------------------------------------------------------ preparo

async def preparar() -> None:
    from app.db import engine
    from app.models import Base

    try:
        # `create_all` só cria o que falta e não encosta em tabela que já
        # existe. É o bastante pro primeiro deploy e pra qualquer tabela
        # nova. **Não** é o bastante pra coluna nova numa tabela que já
        # existe: no dia em que um campo mudar, a ferramenta certa é o
        # Alembic. Está escrito no DEPLOY.md.
        async with engine.begin() as conexao:
            await conexao.run_sync(Base.metadata.create_all)

        await _garantir_dono()
    except Exception as erro:
        # Sem isto, um endereço de banco errado sai como trinta linhas de
        # stack trace do asyncpg no log da hospedagem — e não há nada ali que
        # diga a quem está publicando o que fazer a respeito.
        _falar(
            "NAO DA PRA FALAR COM O BANCO DE DADOS",
            f"endereco: {_endereco_do_banco()}",
            f"erro:     {type(erro).__name__}: {erro}",
            "",
            "Confira, no painel da hospedagem:",
            "  1. o banco Postgres existe e esta rodando;",
            "  2. a variavel DATABASE_URL aponta pra ele — na Railway, use",
            "     Variables > Add Reference em vez de copiar a URL na mao;",
            "  3. o banco e o sistema estao no MESMO projeto (senao o endereco",
            "     interno .railway.internal nao resolve).",
            "",
            "Nada foi criado. O sistema nao subiu de proposito: subir sem",
            "banco daria um site que abre e quebra em toda tela.",
        )
        raise SystemExit(1) from None
    finally:
        await engine.dispose()


def _endereco_do_banco() -> str:
    """O host e o nome do banco, sem a senha — isto vai pro log."""
    from urllib.parse import urlsplit

    bruto = os.environ.get("CARLOSMOTO_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    partes = urlsplit(bruto)
    return f"{partes.hostname or '?'}:{partes.port or 5432}{partes.path or ''}"


async def _garantir_dono() -> None:
    """Cria o dono se ele ainda não existe, e mostra a chave dele uma vez.

    A chave só existe em claro neste instante: o banco guarda o hash dela. Se
    o recado passar batido no log, o caminho de volta é o `CARLOSMOTO_CHAVE_DONO`
    junto com `CARLOSMOTO_REDEFINIR_CHAVE=1` — ver DEPLOY.md.
    """
    from sqlalchemy import select

    from app.config import get_config
    from app.db import Sessao
    from app.models.usuario import Papel, Usuario
    from app.seguranca import gerar_chave, hash_chave

    cfg = get_config()
    redefinir = os.environ.get("CARLOSMOTO_REDEFINIR_CHAVE", "").strip().lower() in {
        "1", "true", "sim", "yes",
    }

    async with Sessao() as sessao:
        dono = (
            await sessao.execute(select(Usuario).where(Usuario.papel == Papel.DONO))
        ).scalars().first()

        if dono is None:
            chave = cfg.chave_dono or gerar_chave()
            sessao.add(
                Usuario(nome="Carlos", chave_hash=hash_chave(chave), papel=Papel.DONO, ativo=True)
            )
            await sessao.commit()
            _anunciar_chave("Carlos", chave, "CONTA DO DONO CRIADA AGORA")
            return

        if redefinir:
            # Caminho de emergência: o dono perdeu a chave e não consegue
            # entrar. Trocar o hash não derruba aparelho nenhum que já esteja
            # pareado — quem faz isso é a tela de sessões.
            chave = cfg.chave_dono or gerar_chave()
            dono.chave_hash = hash_chave(chave)
            await sessao.commit()
            _anunciar_chave(
                dono.nome, chave, "CHAVE REDEFINIDA A PEDIDO",
                "Apague a variavel CARLOSMOTO_REDEFINIR_CHAVE agora: enquanto",
                "ela existir, toda subida do servidor troca a chave de novo.",
            )
            return

        print(f"dono: {dono.nome} ja existe, chave mantida", flush=True)


def _anunciar_chave(nome: str, chave: str, titulo: str, *extra: str) -> None:
    _falar(
        titulo,
        f"CHAVE DE ACESSO DE {nome.upper()}",
        "",
        f"      {chave}",
        "",
        "Digite esta chave uma vez ao abrir o sistema. Depois disso",
        "aquele aparelho nao pede mais nada.",
        "",
        "Anote em lugar seguro: ela nao aparece de novo.",
        *extra,
    )


# ------------------------------------------------------------------ servidor

def main() -> None:
    porta = int(os.environ.get("PORT") or 8000)

    asyncio.run(preparar())

    # Um processo só, de propósito. Duas coisas do sistema vivem na memória do
    # servidor e não são compartilhadas entre processos: a trava de tentativas
    # de pareamento (`app/seguranca.py`) e a lista de telas conectadas ao
    # WebSocket (`app/servicos/eventos.py`). Com dois workers, metade das
    # telas deixaria de receber a atualização em tempo real e a trava contra
    # força bruta valeria metade. Uma loja não precisa de mais de um.
    if os.environ.get("WEB_CONCURRENCY") not in (None, "", "1"):
        _falar(
            "AVISO: WEB_CONCURRENCY IGNORADO",
            "Este sistema roda com um processo so — o tempo real e a trava de",
            "tentativas moram na memoria dele. Subindo assim mesmo, com 1.",
        )

    import uvicorn

    print(f"servidor: 0.0.0.0:{porta}", flush=True)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=porta,
        workers=1,
        # A hospedagem fica na frente como proxy reverso. Sem isto, todo
        # pedido parece vir do IP dela: a trava de força bruta contaria as
        # tentativas de todo mundo num balde só (cinco erros de um estranho
        # trancariam o dono junto), e o HSTS nunca sairia, porque o servidor
        # veria "http" mesmo com o cadeado no navegador.
        proxy_headers=True,
        forwarded_allow_ips="*",
        # O contêiner só é alcançável pelo proxy da hospedagem, então confiar
        # no cabeçalho que ele manda é seguro aqui. Não seria numa máquina
        # exposta direto na internet.
        access_log=True,
        server_header=False,  # não anunciar versão do uvicorn pra quem varre
    )


if __name__ == "__main__":
    sys.exit(main())
