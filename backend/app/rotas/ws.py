"""O canal WebSocket. Um endpoint só, com o papel vindo do JWT.

**A autenticação é a primeira mensagem, não a URL.** O navegador não deixa pôr
cabeçalho `Authorization` num WebSocket, e o caminho comum — `/ws?token=…` —
grava o token de acesso no log de requisições e no histórico do navegador. Um
segredo que vive em arquivo de log é um segredo vazado. Então o servidor
aceita a conexão, espera a mensagem `{"tipo": "auth", "token": "…"}` por
poucos segundos e fecha se ela não vier.
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.base import agora
from app.seguranca import Identidade, ler_token_acesso, validade_do_token
from app.servicos.eventos import hub

log = logging.getLogger(__name__)

rotas = APIRouter()

# Curto: quem abre o socket já tem o token na mão. Este prazo é só pra que uma
# conexão que abriu e ficou muda não ocupe lugar.
PRAZO_AUTENTICACAO_S = 5.0

# O cliente manda `ping` a cada 25s. Passou disto sem nenhuma mensagem, a outra
# ponta sumiu sem avisar. Sem este teto, sockets fantasmas se acumulariam até
# o próximo restart — e um token expirado ficaria valendo indefinidamente.
PRAZO_OCIOSO_S = 60.0

# "Policy violation": não autenticou, ou não tem mais direito de estar aqui.
FECHAR_POLITICA = 1008


@rotas.websocket("/ws")
async def canal(ws: WebSocket) -> None:
    await ws.accept()

    autenticado = await _autenticar(ws)
    if autenticado is None:
        return
    ident, expira_em = autenticado

    hub.entrar(ws, ident.papel)
    log.info("ws: %s (%s) entrou", ident.nome, ident.papel.value)
    try:
        await ws.send_json({
            "evento": "pronto",
            "dados": {
                "papel": ident.papel.value,
                "nome": ident.nome,
                "agora": agora().isoformat(),
            },
        })
        await _escutar(ws, ident, expira_em)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.warning("ws: conexão de %s caiu com erro", ident.nome, exc_info=True)
    finally:
        hub.sair(ws, ident.papel)


# ------------------------------------------------------------------ internos

async def _autenticar(ws: WebSocket) -> tuple[Identidade, datetime | None] | None:
    """Lê a primeira mensagem e confere o token. `None` = já fechou a conexão."""
    try:
        async with asyncio.timeout(PRAZO_AUTENTICACAO_S):
            primeira = await ws.receive_json()
    except (TimeoutError, WebSocketDisconnect, ValueError, RuntimeError):
        await _fechar(ws, "Sem autenticação")
        return None

    token = primeira.get("token") if isinstance(primeira, dict) else None
    ident = ler_token_acesso(token) if isinstance(token, str) else None
    if ident is None:
        await _fechar(ws, "Token inválido ou expirado")
        return None

    return ident, validade_do_token(token)


async def _escutar(ws: WebSocket, ident: Identidade, expira_em: datetime | None) -> None:
    """Fica lendo o socket até a outra ponta sumir.

    Ler é obrigatório mesmo sem ter o que fazer com a maioria das mensagens: é
    a leitura que descobre a desconexão e tira a conexão morta do hub.
    """
    while True:
        try:
            async with asyncio.timeout(PRAZO_OCIOSO_S):
                mensagem = await ws.receive_json()
        except TimeoutError:
            await _fechar(ws, "Sem sinal de vida", codigo=1001)
            return
        except ValueError:
            continue  # mandou algo que não é JSON; ignorar é mais barato que cair

        if expira_em is not None and datetime.now(UTC) >= expira_em:
            await _fechar(ws, "Token expirou, reconecte")
            return

        if isinstance(mensagem, dict) and mensagem.get("tipo") == "ping":
            await ws.send_json({"evento": "pong", "dados": {}})


async def _fechar(ws: WebSocket, motivo: str, codigo: int = FECHAR_POLITICA) -> None:
    """Fecha explicando o porquê. Falha em silêncio se já estiver fechado."""
    try:
        await ws.close(code=codigo, reason=motivo)
    except Exception:
        log.debug("não deu pra fechar o socket (%s)", motivo, exc_info=True)
