/**
 * Botão PROVISÓRIO de migração do sistema antigo — sai depois da virada.
 *
 * Só aparece quando o servidor diz que dá: ele precisa estar rodando no
 * computador onde o sistema antigo está. Um clique copia tudo pro espelho na
 * nuvem, e a janela acompanha tabela por tabela.
 */

import * as api from "../comum/api.js";
import { abrirModal, fecharModal, avisar, escapar, mensagemDeErro } from "./ui.js";

const botao = document.getElementById("botao-migracao");
const espera = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

const TITULO = {
  RODANDO: "Copiando…",
  CONCLUIDO: "Cópia concluída",
  COM_ERROS: "Terminou, mas com tabelas que falharam",
  FALHOU: "A cópia não aconteceu",
};

export async function oferecerMigracao() {
  try {
    const estado = await api.pedir("GET", "/migracao/estado");
    botao.hidden = !estado.disponivel;
  } catch {
    botao.hidden = true;
  }
}

function desenharTabelas(lote) {
  const tabelas = Object.entries(lote.tabelas || {});
  if (!tabelas.length) return '<li class="fraco">Abrindo o sistema antigo…</li>';
  return tabelas.map(([nome, info]) => `
    <li>
      <div>
        <strong>${escapar(nome)}</strong>
        <p class="fraco">de ${escapar(info.origem)}${info.erro
          ? ` · <span class="texto-devendo">${escapar(info.erro)}</span>` : ""}</p>
      </div>
      <strong>${Number(info.linhas || 0).toLocaleString("pt-BR")}</strong>
    </li>`).join("");
}

async function acompanhar(modal, loteId) {
  // Para sozinho quando a janela é fechada; a cópia continua no servidor.
  while (modal.isConnected) {
    let lote;
    try {
      lote = await api.pedir("GET", `/migracao/lotes/${loteId}`);
    } catch (erro) {
      modal.querySelector("#migracao-situacao").textContent = mensagemDeErro(erro);
      await espera(4000);
      continue;
    }
    modal.querySelector("#migracao-situacao").textContent =
      `${TITULO[lote.situacao] || lote.situacao} — lote ${lote.id}`;
    modal.querySelector("#migracao-tabelas").innerHTML = desenharTabelas(lote);
    modal.querySelector("#migracao-erros").innerHTML = (lote.erros || [])
      .map((e) => `<li class="texto-devendo">${escapar(e.tabela || "origem")}: ${escapar(e.erro)}</li>`)
      .join("");

    if (lote.situacao !== "RODANDO") {
      avisar(TITULO[lote.situacao], lote.situacao === "CONCLUIDO" ? "ok" : "erro");
      return;
    }
    await espera(2000);
  }
}

botao.addEventListener("click", () => {
  const modal = abrirModal(`
    <div class="modal-topo"><h3>Migrar o sistema antigo — passo 1</h3></div>
    <p>Copia <strong>tudo</strong> do sistema antigo deste computador pra nuvem, do jeito que está:
      clientes, contratos, tickets, dados da empresa e qualquer outra tabela que existir.</p>
    <p class="fraco">O sistema antigo não é alterado, e nada entra ainda no sistema novo — a cópia
      fica separada, esperando o passo 2. Pode repetir: cada clique gera um lote novo.</p>
    <p id="migracao-situacao" class="fraco"></p>
    <ul class="lista-fila" id="migracao-tabelas"></ul>
    <ul class="lista-simples" id="migracao-erros"></ul>
    <div class="acoes-modal">
      <button class="botao botao--fantasma" data-fechar type="button">Fechar</button>
      <button class="botao" id="migracao-iniciar" type="button">Copiar agora</button>
    </div>
  `);

  modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));
  modal.querySelector("#migracao-iniciar").addEventListener("click", async (evento) => {
    const iniciar = evento.currentTarget;
    iniciar.disabled = true;
    try {
      // `pedir`, e não `enviar`: sem internet isto não pode ir pra fila e
      // disparar sozinho horas depois.
      const { lote_id: loteId } = await api.pedir("POST", "/migracao/passo-1");
      iniciar.hidden = true;
      await acompanhar(modal, loteId);
    } catch (erro) {
      iniciar.disabled = false;
      avisar(mensagemDeErro(erro), "erro");
    }
  });
});
