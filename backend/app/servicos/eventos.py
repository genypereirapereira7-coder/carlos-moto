"""Hub do WebSocket: quem está conectado e quem recebe cada evento.

O roteamento é **por papel**, não por usuário: todo vendedor conectado recebe
`moto.vendida`. Quem está conectado mora num dicionário em memória — decisão
consciente pra v1 rodando com um worker só.

**Publicar nunca pode derrubar a rota que publicou.** Uma tela que fechou o
navegador sem encerrar o socket não pode fazer o `POST /vendas` falhar — a
venda já aconteceu. Por isso todo envio é isolado e o pior caso é a conexão
morta sair do hub e a tela se virar com o polling até reconectar.
"""

import asyncio
import enum
import logging
from collections import defaultdict
from typing import Any, Protocol

from app.models.usuario import Papel

log = logging.getLogger(__name__)

# Uma tela travada não segura o broadcast das outras — e muito menos a resposta
# HTTP de quem publicou. Passou disto, a conexão é tratada como morta.
ENVIO_TIMEOUT_S = 2.0


class Evento(str, enum.Enum):
    MOTO_CADASTRADA = "moto.cadastrada"
    MOTO_ATUALIZADA = "moto.atualizada"
    MOTO_VENDIDA = "moto.vendida"
    MOTO_EXCLUIDA = "moto.excluida"
    DESPESA_LANCADA = "despesa.lancada"
    VENDA_REGISTRADA = "venda.registrada"
    CLIENTE_CADASTRADO = "cliente.cadastrado"
    PARCELA_ATUALIZADA = "parcela.atualizada"
    USUARIO_PENDENTE = "usuario.pendente"
    USUARIO_DESATIVADO = "usuario.desativado"


# Quem recebe o quê. Mora aqui, junto do enum, pra que o destino seja uma
# decisão só.
DESTINOS: dict[Evento, tuple[Papel, ...]] = {
    # Some da vitrine de todo vendedor conectado na hora — é o ponto sensível:
    # dois vendedores olhando a mesma moto, o segundo não pode continuar
    # oferecendo o que o primeiro acabou de vender.
    Evento.MOTO_VENDIDA: (Papel.VENDEDOR, Papel.DONO),
    Evento.MOTO_EXCLUIDA: (Papel.VENDEDOR, Papel.DONO),
    Evento.MOTO_CADASTRADA: (Papel.VENDEDOR, Papel.DONO),
    Evento.MOTO_ATUALIZADA: (Papel.VENDEDOR, Papel.DONO),
    Evento.VENDA_REGISTRADA: (Papel.DONO,),
    Evento.DESPESA_LANCADA: (Papel.DONO,),
    Evento.CLIENTE_CADASTRADO: (Papel.DONO,),
    Evento.PARCELA_ATUALIZADA: (Papel.DONO,),
    # Alguém pediu conta. Só o dono libera, então só o dono ouve — na hora: um
    # vendedor parado esperando pra começar é a diferença entre um toque agora
    # e um telefonema.
    Evento.USUARIO_PENDENTE: (Papel.DONO,),
    Evento.USUARIO_DESATIVADO: (Papel.VENDEDOR,),
}


class Canal(Protocol):
    """O mínimo que o hub precisa de uma conexão."""

    async def send_json(self, dados: Any) -> None: ...


class Hub:
    def __init__(self) -> None:
        self._por_papel: dict[Papel, set[Canal]] = defaultdict(set)

    def entrar(self, canal: Canal, papel: Papel) -> None:
        self._por_papel[papel].add(canal)

    def sair(self, canal: Canal, papel: Papel) -> None:
        self._por_papel[papel].discard(canal)

    def conectados(self, papel: Papel) -> int:
        return len(self._por_papel[papel])

    async def publicar(self, evento: Evento, dados: Any) -> None:
        """Manda o evento pra quem o `DESTINOS` diz que assina.

        Não levanta exceção: ver o cabeçalho do módulo.
        """
        alvos = {canal for papel in DESTINOS[evento] for canal in self._por_papel[papel]}
        if not alvos:
            return

        mensagem = {"evento": evento.value, "dados": dados}
        mortas = await asyncio.gather(*(self._enviar(c, mensagem) for c in alvos))

        for canal in filter(None, mortas):
            for conexoes in self._por_papel.values():
                conexoes.discard(canal)

    async def _enviar(self, canal: Canal, mensagem: dict) -> Canal | None:
        """Devolve a conexão quando ela morreu, pro `publicar` removê-la."""
        try:
            async with asyncio.timeout(ENVIO_TIMEOUT_S):
                await canal.send_json(mensagem)
        except Exception:
            log.debug("conexão morta descartada do hub", exc_info=True)
            return canal
        return None


hub = Hub()


async def publicar_apos_commit(sessao, evento: Evento, dados: Any) -> None:
    """Grava de verdade e só então anuncia.

    A ordem não é preciosismo: publicar no meio do handler anunciaria uma
    venda que ainda pode não existir se o commit falhar. Commitar antes de
    publicar troca esse erro pelo único aceitável — a venda existir e o aviso
    não sair, que o próximo refetch conserta sozinho.
    """
    await sessao.commit()
    await hub.publicar(evento, dados)
