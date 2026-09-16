"""Migração do sistema antigo — PROVISÓRIO: sai do sistema depois da virada.

Só funciona onde o sistema antigo está. O servidor que atende esta rota
precisa estar rodando no computador do cliente: um servidor na nuvem não
enxerga o disco de ninguém. Lá `CARLOSMOTO_MIGRACAO_ORIGEM` fica vazia, a
rota responde 409 e o botão nem aparece.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

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


@rotas.get("/estado")
async def estado(_: SoDono):
    return {
        "disponivel": bool(_origem() and _destino()),
        "origem": _origem() or None,
        "rodando": _rodando(),
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
