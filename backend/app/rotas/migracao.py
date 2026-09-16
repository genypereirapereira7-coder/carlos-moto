"""Migração do sistema antigo — PROVISÓRIO: sai do sistema depois da virada.

Dois caminhos pro mesmo lugar, porque o cliente pode estar em dois lugares:

  `POST /migracao/passo-1` — o servidor lê o sistema antigo direto do disco.
  Só funciona quando ele está rodando **no computador do cliente**: um
  servidor na nuvem não enxerga o disco de ninguém.

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


@rotas.post("/passo-1", status_code=status.HTTP_202_ACCEPTED)
async def iniciar_passo_1(_: SoDono):
    """Começa a cópia e responde na hora com o número do lote. A cópia continua
    em segundo plano; a tela acompanha por `GET /migracao/lotes/{id}`."""
    global _tarefa
    if not (_origem() and _destino()):
        raise HTTPException(status.HTTP_409_CONFLICT, "A migração não está configurada neste computador.")
    if _rodando():
        raise HTTPException(status.HTTP_409_CONFLICT, "Já tem uma cópia rodando.")

    try:
        lote_id = await migracao.abrir_lote(_destino(), _origem())
    except Exception as erro:
        log.warning("migração: banco da nuvem não respondeu", exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Não deu pra falar com o banco da nuvem ({type(erro).__name__}).") from None

    _tarefa = asyncio.create_task(migracao.executar_passo_1(_destino(), _origem(), lote_id))
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
async def enviar_sistema_antigo(_: SoDono, arquivo: UploadFile):
    """Recebe o banco do sistema antigo escolhido na tela e copia pro espelho.

    O arquivo é gravado em pedaços, e não lido de uma vez: um banco de 300 MB
    lido inteiro na memória derruba o servidor.
    """
    global _tarefa
    destino = _destino()
    if not destino:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há banco na nuvem configurado para receber a cópia.")
    if _rodando():
        raise HTTPException(status.HTTP_409_CONFLICT, "Já tem uma cópia rodando. Espere ela terminar.")

    nome = Path(arquivo.filename or "sistema-antigo").name
    sufixo = Path(nome).suffix.lower()
    if sufixo in PRECISAM_DE_DRIVER:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Arquivo {sufixo} (Access ou Firebird) precisa de um programa que só existe no "
            "computador onde o sistema antigo está. A cópia desse tipo tem que ser feita lá.",
        )
    if sufixo not in ACEITOS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Não sei abrir {sufixo or 'arquivo sem extensão'}. Aceito: {', '.join(sorted(ACEITOS))}. "
            "A pasta inteira do sistema antigo pode vir num .zip.",
        )

    pasta = Path(tempfile.mkdtemp(prefix="migracao-envio-"))
    caminho = pasta / nome
    tamanho = 0
    try:
        with caminho.open("wb") as saida:
            while pedaco := await arquivo.read(PEDACO):
                tamanho += len(pedaco)
                if tamanho > LIMITE_BYTES:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"Arquivo maior que {LIMITE_BYTES // (1024 * 1024)} MB. "
                        "Um desse tamanho é melhor copiar no próprio computador do cliente.",
                    )
                saida.write(pedaco)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise

    # O lote guarda o nome que o dono reconhece; a leitura usa o caminho temporário.
    lote_id = await migracao.abrir_lote(destino, f"enviado: {nome}")
    _tarefa = asyncio.create_task(_copiar_e_apagar(destino, caminho, lote_id))
    _tarefa.add_done_callback(_registrar_fim)
    return {"lote_id": lote_id, "arquivo": nome, "bytes": tamanho}


async def _copiar_e_apagar(destino: str, caminho: Path, lote_id: int) -> dict:
    try:
        return await migracao.executar_passo_1(destino, str(caminho), lote_id)
    finally:
        # O banco do cliente não fica guardado no servidor depois da cópia.
        shutil.rmtree(caminho.parent, ignore_errors=True)
