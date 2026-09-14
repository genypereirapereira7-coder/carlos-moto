/**
 * Cliente do WebSocket, compartilhado pelos dois PWAs.
 *
 * **O socket acelera; quem garante é o polling/recarregamento.** Nenhuma das
 * duas telas depende deste arquivo pra estar correta — se ele nunca
 * conectar (proxy que bloqueia, rede capenga, servidor reiniciando), as telas
 * continuam funcionando, só mais devagar.
 *
 * Por isso aqui não há fila de mensagens perdidas nem reenvio: evento que não
 * chegou é evento que o próximo recarregamento resolve.
 *
 * **A autenticação é a primeira mensagem, não a URL.** O navegador não deixa
 * pôr cabeçalho `Authorization` num WebSocket, e `?token=…` gravaria o token
 * de acesso no log do servidor. Ver `app/rotas/ws.py`.
 */

import * as api from "./api.js";

/** O servidor derruba quem fica 60s sem falar. */
const PING_MS = 25000;

const RECONEXAO_MIN_MS = 1000;
const RECONEXAO_MAX_MS = 30000;

/** "Policy violation" — não autenticou ou o token venceu. */
const FECHOU_POR_POLITICA = 1008;

/**
 * Abre e mantém a conexão. Devolve `{ fechar() }`.
 *
 * @param {object} opcoes
 * @param {(evento: string, dados: any) => void} opcoes.aoEvento
 * @param {(ligado: boolean) => void} [opcoes.aoMudarConexao]
 */
export function conectar({ aoEvento, aoMudarConexao }) {
  let socket = null;
  let timerPing = null;
  let timerReconexao = null;
  let espera = RECONEXAO_MIN_MS;
  let ativo = true;
  let anunciado = false;

  function avisar(ligado) {
    if (ligado === anunciado) return;
    anunciado = ligado;
    aoMudarConexao?.(ligado);
  }

  function abrir() {
    if (!ativo || !api.estaLogado()) return;

    const url = new URL("/ws", location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";

    try {
      socket = new WebSocket(url);
    } catch {
      return reagendar();
    }

    socket.onopen = () => {
      const sessao = api.sessaoAtual();
      if (!sessao) return socket.close();

      socket.send(JSON.stringify({ tipo: "auth", token: sessao.acesso }));
      timerPing = setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ tipo: "ping" }));
        }
      }, PING_MS);
    };

    socket.onmessage = (mensagem) => {
      let pacote;
      try {
        pacote = JSON.parse(mensagem.data);
      } catch {
        return;
      }

      if (pacote.evento === "pronto") {
        espera = RECONEXAO_MIN_MS;
        avisar(true);
        return;
      }

      if (pacote.evento === "pong") return;

      aoEvento(pacote.evento, pacote.dados);
    };

    socket.onclose = async (fechamento) => {
      limpar();
      avisar(false);

      if (fechamento.code === FECHOU_POR_POLITICA && api.estaLogado()) {
        await api.renovarSessao();
      }

      reagendar();
    };

    socket.onerror = () => {
      // O `onclose` vem logo atrás e é lá que a reconexão é marcada.
    };
  }

  function reagendar() {
    if (!ativo || timerReconexao) return;
    timerReconexao = setTimeout(() => {
      timerReconexao = null;
      abrir();
    }, espera);
    espera = Math.min(espera * 2, RECONEXAO_MAX_MS);
  }

  function limpar() {
    clearInterval(timerPing);
    timerPing = null;
    socket = null;
  }

  const aoVoltar = () => {
    if (document.visibilityState === "visible" && !socket && ativo) {
      espera = RECONEXAO_MIN_MS;
      clearTimeout(timerReconexao);
      timerReconexao = null;
      abrir();
    }
  };
  document.addEventListener("visibilitychange", aoVoltar);
  window.addEventListener("online", aoVoltar);

  abrir();

  return {
    fechar() {
      ativo = false;
      document.removeEventListener("visibilitychange", aoVoltar);
      window.removeEventListener("online", aoVoltar);
      clearTimeout(timerReconexao);
      try {
        socket?.close();
      } catch { /* já estava fechado */ }
      limpar();
    },
  };
}
