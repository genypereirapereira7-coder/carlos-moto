"""Migração do sistema antigo — PROVISÓRIO: sai do sistema depois da virada.

Dois caminhos pro mesmo lugar, porque o cliente pode estar em dois lugares:

  `GET /migracao/procurar` + `POST /migracao/passo-1` — o servidor **acha o
  sistema antigo sozinho** no disco e copia. Ninguém escolhe arquivo nenhum:
  um clique e acabou. Só funciona quando o servidor está rodando **no
  computador do cliente**; na nuvem a varredura não acha nada, porque lá não
  existe o disco dele.

  `POST /migracao/enviar` — o cliente **escolhe o arquivo** na tela e manda
  pra cá. Funciona da nuvem, de qualquer computador, sem instalar nada: o
  navegador não deixa um site vasculhar o disco, mas deixa a pessoa apontar um
  arquivo de propósito. É o caminho pra quem abre o sistema pelo endereço da
  internet.

O arquivo enviado é apagado assim que a cópia termina. Ele é o banco do
cliente inteiro; não fica sobrando no disco do servidor.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import get_config
from app.dependencias import SoDono
from app.servicos import migracao

log = logging.getLogger(__name__)
cfg = get_config()
rotas = APIRouter(prefix="/migracao", tags=["migracao"])

# Guardada numa variável: tarefa do asyncio sem referência pode ser recolhida
# pelo coletor de lixo no meio da cópia.
_tarefa: asyncio.Task | None = None


def _origem() -> str:
    return cfg.migracao_origem.strip()


def _destino() -> str:
    # Vazio = o próprio banco do sistema, se for Postgres. Nunca o SQLite de
    # desenvolvimento: o espelho tem que ir pra nuvem.
    if cfg.migracao_destino.strip():
        return cfg.migracao_destino.strip()
    return cfg.database_url if cfg.database_url.startswith("postgresql") else ""


def _rodando() -> bool:
    return _tarefa is not None and not _tarefa.done()


# Formatos que o servidor da nuvem consegue abrir sozinho: são lidos por
# Python puro, sem driver nenhum instalado.
ACEITOS = {".db", ".sqlite", ".sqlite3", ".dbf", ".csv", ".txt", ".zip"}

# Estes precisam de driver do Windows (Access) ou do cliente do Firebird. Num
# servidor Linux não há como abrir — a cópia desses tem que ser feita no
# computador onde o sistema antigo está.
PRECISAM_DE_DRIVER = {".mdb", ".accdb", ".fdb", ".gdb"}

# Meio giga. Acima disso o envio pela internet da loja é sofrimento, e o
# caminho melhor é rodar a cópia lá mesmo.
LIMITE_BYTES = 500 * 1024 * 1024
PEDACO = 1024 * 1024


@rotas.get("/estado")
async def estado(_: SoDono):
    return {
        # Ler o disco daqui: só onde o sistema antigo está.
        "disponivel": bool(_origem() and _destino()),
        # Receber o arquivo pela tela: funciona em qualquer lugar que tenha
        # para onde copiar — inclusive na nuvem.
        "envio": bool(_destino()),
        "origem": _origem() or None,
        "rodando": _rodando(),
        "limite_mb": LIMITE_BYTES // (1024 * 1024),
        "formatos": sorted(ACEITOS),
    }


class EscolhaEntrada(BaseModel):
    """Qual dos sistemas antigos encontrados copiar. Vazio = o configurado na
    variável de ambiente."""

    caminho: str | None = None


@rotas.get("/procurar")
async def procurar(_: SoDono):
    """Varre o disco deste computador atrás do sistema antigo.

    Na nuvem devolve lista vazia, e é assim que a tela sabe que ali o jeito é
    receber o arquivo pela mão do dono.
    """
    achados = await asyncio.to_thread(migracao.procurar_sistemas_antigos)
    return {"achados": achados, "origem_configurada": _origem() or None}


@rotas.post("/passo-1", status_code=status.HTTP_202_ACCEPTED)
async def iniciar_passo_1(_: SoDono, escolha: EscolhaEntrada | None = None):
    """Começa a cópia e responde na hora com o número do lote. A cópia continua
    em segundo plano; a tela acompanha por `GET /migracao/lotes/{id}`."""
    global _tarefa
    if not _destino():
        raise HTTPException(status.HTTP_409_CONFLICT, "A migração não está configurada neste computador.")
    if _rodando():
        raise HTTPException(status.HTTP_409_CONFLICT, "Já tem uma cópia rodando.")

    escolhido = (escolha.caminho or "").strip() if escolha else ""
    if escolhido:
        # Só caminho que apareceu na varredura. Sem esta conferência, a rota
        # viraria "leia qualquer arquivo do servidor pra mim" — inclusive os
        # que não são banco de sistema antigo nenhum.
        encontrados = await asyncio.to_thread(migracao.procurar_sistemas_antigos)
        if escolhido not in {achado["caminho"] for achado in encontrados}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Esse caminho não está entre os sistemas antigos encontrados neste computador.",
            )
    origem = escolhido or _origem()
    if not origem:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Não achei nenhum sistema antigo neste computador.",
        )

    try:
        lote_id = await migracao.abrir_lote(_destino(), origem)
    except Exception as erro:
        log.warning("migração: banco da nuvem não respondeu", exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Não deu pra falar com o banco da nuvem ({type(erro).__name__}).") from None

    _tarefa = asyncio.create_task(migracao.executar_passo_1(_destino(), origem, lote_id))
    _tarefa.add_done_callback(_registrar_fim)
    return {"lote_id": lote_id}


def _registrar_fim(tarefa: asyncio.Task) -> None:
    if not tarefa.cancelled() and tarefa.exception() is not None:
        log.error("migração: passo 1 terminou com exceção", exc_info=tarefa.exception())


@rotas.get("/lotes/{lote_id}")
async def ver_lote(lote_id: int, _: SoDono):
    if not _destino():
        raise HTTPException(status.HTTP_409_CONFLICT, "A migração não está configurada neste computador.")
    lote = await migracao.ler_lote(_destino(), lote_id)
    if lote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lote não encontrado")
    return lote


@rotas.post("/enviar", status_code=status.HTTP_202_ACCEPTED)
async def enviar_sistema_antigo(_: SoDono, arquivos: list[UploadFile]):
    """Recebe o sistema antigo pela tela e copia pro espelho.

    Aceita **um arquivo ou a pasta inteira**. Apontar a pasta é o caminho bom:
    o dono não precisa saber qual dos 47 arquivos é o banco — o que não for
    dado (programa, ajuda, imagem) é descartado aqui, sem reclamar.

    Cada arquivo é gravado em pedaços, e não lido de uma vez: um banco de
    300 MB lido inteiro na memória derruba o servidor.
    """
    global _tarefa
    destino = _destino()
    if not destino:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há banco na nuvem configurado para receber a cópia.")
    if _rodando():
        raise HTTPException(status.HTTP_409_CONFLICT, "Já tem uma cópia rodando. Espere ela terminar.")

    pasta = Path(tempfile.mkdtemp(prefix="migracao-envio-"))
    guardados: list[Path] = []
    precisavam_de_driver: list[str] = []
    tamanho = 0
    try:
        for arquivo in arquivos:
            nome = Path(arquivo.filename or "sistema-antigo").name
            sufixo = Path(nome).suffix.lower()
            if sufixo in PRECISAM_DE_DRIVER:
                precisavam_de_driver.append(nome)
                continue
            if sufixo not in ACEITOS:
                continue  # programa, ajuda, imagem: a pasta vem cheia disso

            caminho = pasta / nome
            with caminho.open("wb") as saida:
                while pedaco := await arquivo.read(PEDACO):
                    tamanho += len(pedaco)
                    if tamanho > LIMITE_BYTES:
                        raise HTTPException(
                            status.HTTP_413_CONTENT_TOO_LARGE,
                            f"O envio passou de {LIMITE_BYTES // (1024 * 1024)} MB. "
                            "Desse tamanho é melhor copiar no próprio computador do cliente.",
                        )
                    saida.write(pedaco)
            guardados.append(caminho)

        if not guardados:
            shutil.rmtree(pasta, ignore_errors=True)
            if precisavam_de_driver:
                raise HTTPException(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    f"{', '.join(precisavam_de_driver[:3])} é Access ou Firebird, e precisa de um "
                    "programa que só existe no computador onde o sistema antigo está. "
                    "A cópia desse tipo tem que ser feita lá.",
                )
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"Nenhum arquivo que eu saiba abrir. Aceito: {', '.join(sorted(ACEITOS))}.",
            )
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise

    # Um arquivo só: lê ele. Vários: lê a pasta inteira, de uma vez.
    origem = guardados[0] if len(guardados) == 1 else pasta
    rotulo = guardados[0].name if len(guardados) == 1 else f"{len(guardados)} arquivos da pasta"

    # O lote guarda o nome que o dono reconhece; a leitura usa o caminho temporário.
    try:
        lote_id = await migracao.abrir_lote(destino, f"enviado: {rotulo}")
    except Exception as erro:
        # Sem isto, banco da nuvem fora do ar vira erro cru na cara do cliente,
        # depois de ele ter esperado o arquivo inteiro subir. O `/passo-1` já
        # tratava; aqui tinha passado.
        shutil.rmtree(pasta, ignore_errors=True)
        log.warning("migração: banco da nuvem não respondeu no envio", exc_info=True)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"O arquivo chegou, mas não deu pra falar com o banco da nuvem ({type(erro).__name__}).",
        ) from None
    _tarefa = asyncio.create_task(_copiar_e_apagar(destino, origem, pasta, lote_id))
    _tarefa.add_done_callback(_registrar_fim)
    return {
        "lote_id": lote_id,
        "arquivos": [caminho.name for caminho in guardados],
        "ignorados": len(arquivos) - len(guardados),
        "precisam_de_driver": precisavam_de_driver,
        "bytes": tamanho,
    }


async def _copiar_e_apagar(destino: str, origem: Path, pasta: Path, lote_id: int) -> dict:
    try:
        return await migracao.executar_passo_1(destino, str(origem), lote_id)
    finally:
        # O banco do cliente não fica guardado no servidor depois da cópia.
        shutil.rmtree(pasta, ignore_errors=True)
