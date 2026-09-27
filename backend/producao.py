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


def ligar_modo_producao() -> None:
    """Confere a configuração e acende as travas de produção.

    Precisa rodar **antes** de qualquer `import app.*`: a configuração é lida
    e guardada no primeiro import, e depois disso mudar a variável não muda
    mais nada. Como este módulo só importa `os`, `sys` e `asyncio` lá em
    cima, chamar isto no começo do `main()` chega a tempo.

    Ficava solto no topo do arquivo, e aí *importar* `producao` já derrubava o
    processo inteiro com `SystemExit` quando faltava uma variável — o que
    tornava impossível testar qualquer coisa daqui. Import não pode ter esse
    poder; quem decide encerrar é quem manda rodar.
    """
    conferir_ambiente()
    # O arquivo se chama `producao.py`: ligar o modo de produção é a razão
    # dele existir, não uma coisa pra lembrar de configurar.
    os.environ.setdefault("CARLOSMOTO_AMBIENTE", "producao")


# ------------------------------------------------------------------ preparo

async def preparar() -> None:
    from app.db import engine
    from app.models import Base

    try:
        # `create_all` só cria o que falta e não encosta em tabela que já
        # existe: resolve tabela nova, não coluna nova.
        async with engine.begin() as conexao:
            await conexao.run_sync(Base.metadata.create_all)

        # Coluna nova numa tabela que já existe é o `migracoes`. Sem esta
        # chamada, o campo novo ficava só no desenvolvimento e o site quebrava
        # em produção na primeira tela que lesse a coluna que não existia lá.
        from migracoes import aplicar

        feitas = await aplicar(engine)
        for feita in feitas:
            print(f"   migracao: {feita}", flush=True)

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
    """Deixa o acesso do dono batendo com o que foi pedido, e diz qual é.

    **`CARLOSMOTO_CHAVE_DONO` manda.** Se essa variável tem valor, a chave do
    dono passa a ser aquela — na conta que está sendo criada agora e também
    na que já existia. Uma variável, um efeito, do jeito que a pessoa pensa
    nela: "a chave é essa".

    Antes era preciso combinar duas variáveis pra trocar uma chave já criada,
    e quem só preenchia a `CHAVE_DONO` levava "Chave de acesso inválida" sem
    nenhuma pista do porquê — a variável estava certa, cadastrada, e ignorada
    em silêncio. Isso era uma armadilha, não uma trava de segurança.

    **O preço, que é real:** trocar a chave pela tela do sistema não sobrevive
    ao próximo deploy se essa variável continuar preenchida — ela volta a
    valer. Trocou pela tela? Atualize a variável, ou apague ela.

    Sem a variável, nada disso acontece: a chave que está no banco fica como
    está, e uma conta nova nasce com uma chave sorteada aqui.
    """
    from sqlalchemy import select

    from app.config import get_config
    from app.db import Sessao
    from app.models.usuario import Papel, Usuario
    from app.seguranca import gerar_chave, hash_chave, normalizar_chave

    cfg = get_config()
    pedida = normalizar_chave(cfg.chave_dono) if cfg.chave_dono else ""
    forcar_nova = os.environ.get("CARLOSMOTO_REDEFINIR_CHAVE", "").strip().lower() in {
        "1", "true", "sim", "yes",
    }

    async with Sessao() as sessao:
        dono = (
            await sessao.execute(select(Usuario).where(Usuario.papel == Papel.DONO))
        ).scalars().first()

        # ------------------------------------------------- conta ainda não existe
        if dono is None:
            chave = cfg.chave_dono or gerar_chave()
            sessao.add(
                Usuario(nome="Carlos", chave_hash=hash_chave(chave), papel=Papel.DONO, ativo=True)
            )
            await sessao.commit()
            _anunciar_chave("Carlos", chave, "CONTA DO DONO CRIADA AGORA")
            return

        # ------------------------------------------------- a variável manda
        if pedida:
            if dono.chave_hash == hash_chave(pedida):
                # Já é essa. Nada a fazer, e nada a gravar — uma escrita à toa
                # viraria uma linha no histórico a cada subida do servidor.
                print(
                    f"dono: {dono.nome} — a chave ja e a da variavel CARLOSMOTO_CHAVE_DONO",
                    flush=True,
                )
                return

            dono.chave_hash = hash_chave(pedida)
            await sessao.commit()
            _anunciar_chave(
                dono.nome, cfg.chave_dono, "CHAVE TROCADA PELA VARIAVEL",
                "A chave anterior nao vale mais.",
                "",
                "Nenhum aparelho ja pareado foi desconectado — quem faz isso e",
                "o botao 'Chave e aparelhos', dentro do sistema.",
            )
            return

        # --------------------------- sem variável: sortear uma, se pedirem
        if forcar_nova:
            chave = gerar_chave()
            dono.chave_hash = hash_chave(chave)
            await sessao.commit()
            _anunciar_chave(
                dono.nome, chave, "CHAVE NOVA SORTEADA A PEDIDO",
                "Apague a variavel CARLOSMOTO_REDEFINIR_CHAVE agora: enquanto",
                "ela existir, toda subida do servidor sorteia outra.",
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

# Todas as interfaces, e não `127.0.0.1`. Dentro de um contêiner, `localhost`
# quer dizer "só eu mesmo": o servidor sobe, o log diz que está no ar, e o
# proxy da hospedagem bate numa porta que não responde a ninguém de fora. É a
# causa clássica de "Application failed to respond" com o deploy verde.
_HOST = "0.0.0.0"


def _porta() -> tuple[int, bool]:
    """A porta, e se ela veio da hospedagem ou é chute nosso.

    Quem escolhe a porta é a hospedagem, e ela manda em `PORT` — não se
    adapta a quem escolher sozinho. Saber a diferença é o que permite avisar,
    em vez de subir calado na porta errada.
    """
    bruta = (os.environ.get("PORT") or "").strip()
    if not bruta:
        return 8000, False
    try:
        return int(bruta), True
    except ValueError:
        _falar(
            "PORT VEIO COM UM VALOR ESTRANHO",
            f"PORT = {bruta!r}, que nao e um numero.",
            "Subindo na 8000. Confira a variavel no painel.",
        )
        return 8000, False


def main() -> None:
    ligar_modo_producao()

    porta, veio_da_hospedagem = _porta()

    if not veio_da_hospedagem:
        # Este é o motivo número um do "Application failed to respond": o
        # contêiner sobe, o servidor escuta, e escuta na porta errada. A
        # hospedagem tenta falar numa porta onde não tem ninguém.
        _falar(
            "ATENCAO: A VARIAVEL PORT NAO VEIO",
            f"Subindo na porta {porta}, que e o padrao — um chute.",
            "",
            "A hospedagem normalmente injeta PORT sozinha e espera o servidor",
            "atender exatamente nela. Se a pagina publica der",
            "'Application failed to respond', e quase certo que e isto.",
            "",
            "Na Railway: Settings > Networking > no dominio gerado, confira",
            "o Target Port — ele tem que bater com a porta acima.",
        )

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

    # Este bloco existe pro log responder sozinho à pergunta "por que a
    # página não abre". Sem ele, o log diz "Application startup complete" e
    # cala justamente sobre onde o servidor foi parar.
    _falar(
        "SERVIDOR NO AR",
        f"porta:     {porta}"
        f"  ({'veio da hospedagem' if veio_da_hospedagem else 'PADRAO — a hospedagem nao mandou'})",
        f"interface: {_HOST} (todas) — alcancavel de fora do conteiner",
        f"ambiente:  {os.environ.get('CARLOSMOTO_AMBIENTE')}",
        "",
        "Se a pagina publica ainda der 'Application failed to respond', o",
        "problema nao esta aqui dentro: e o Target Port do dominio, ou um",
        "Start Command no painel passando por cima do railway.json.",
    )
    uvicorn.run(
        "app.main:app",
        host=_HOST,
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
