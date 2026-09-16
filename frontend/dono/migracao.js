/**
 * Botão PROVISÓRIO de migração do sistema antigo — sai depois da virada.
 *
 * Dois caminhos, e a janela mostra o que o servidor disser que dá:
 *
 *   - **Enviar o arquivo**: o dono escolhe o banco do sistema antigo na tela e
 *     manda pra nuvem. Funciona de qualquer computador, sem instalar nada. O
 *     navegador não deixa um site vasculhar o disco, mas deixa a pessoa
 *     apontar um arquivo — e é essa a diferença.
 *   - **Copiar daqui**: o servidor lê o disco direto. Só existe quando ele
 *     está rodando no computador onde o sistema antigo está.
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

let estadoAtual = null;

export async function oferecerMigracao() {
  try {
    estadoAtual = await api.pedir("GET", "/migracao/estado");
    botao.hidden = !(estadoAtual.disponivel || estadoAtual.envio);
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
  const estado = estadoAtual || {};
  const formatos = (estado.formatos || []).join(", ");

  const modal = abrirModal(`
    <div class="modal-topo"><h3>Migrar o sistema antigo — passo 1</h3></div>
    <p>Copia <strong>tudo</strong> do sistema antigo pra nuvem, do jeito que está: clientes,
      contratos, tickets, dados da empresa e qualquer outra tabela que existir.</p>
    <p class="fraco">O sistema antigo não é alterado, e nada entra ainda no sistema novo — a cópia
      fica separada, esperando o passo 2. Pode repetir: cada envio gera um lote novo.</p>

    ${estado.envio ? `
      <h3 class="secao-seguinte">Enviar o arquivo do sistema antigo</h3>
      <label class="campo">Escolha o arquivo no seu computador
        <input type="file" id="migracao-arquivo" accept="${(estado.formatos || []).join(",")}" />
      </label>
      <p class="fraco">Aceita ${formatos || "os formatos do sistema antigo"}, até
        ${estado.limite_mb || 500} MB. Se o sistema antigo for uma pasta com vários arquivos,
        compacte a pasta em .zip e mande o .zip.</p>
      <div class="acoes-modal">
        <button class="botao" id="migracao-enviar" type="button">Enviar e copiar</button>
      </div>` : ""}

    ${estado.disponivel ? `
      <h3 class="secao-seguinte">Ou copiar direto deste computador</h3>
      <p class="fraco">O sistema antigo foi encontrado aqui: <strong>${escapar(estado.origem || "")}</strong></p>
      <div class="acoes-modal">
        <button class="botao botao--fantasma" id="migracao-iniciar" type="button">Copiar daqui</button>
      </div>` : ""}

    <p id="migracao-situacao" class="fraco"></p>
    <ul class="lista-fila" id="migracao-tabelas"></ul>
    <ul class="lista-simples" id="migracao-erros"></ul>
    <div class="acoes-modal">
      <button class="botao botao--fantasma" data-fechar type="button">Fechar</button>
    </div>
  `);

  const situacao = (texto) => { modal.querySelector("#migracao-situacao").textContent = texto; };
  const esconderEscolhas = () => {
    for (const id of ["#migracao-enviar", "#migracao-iniciar", "#migracao-arquivo"]) {
      const alvo = modal.querySelector(id);
      if (alvo) alvo.closest(".acoes-modal, .campo")?.setAttribute("hidden", "");
    }
  };

  modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));

  modal.querySelector("#migracao-enviar")?.addEventListener("click", async (evento) => {
    const botaoEnviar = evento.currentTarget;
    const campo = modal.querySelector("#migracao-arquivo");
    const arquivo = campo?.files?.[0];
    if (!arquivo) {
      avisar("Escolha o arquivo do sistema antigo primeiro", "erro");
      return;
    }
    botaoEnviar.disabled = true;
    try {
      const { lote_id: loteId } = await api.enviarArquivo("/migracao/enviar", arquivo, {
        aoProgredir: (fracao) => situacao(`Enviando ${arquivo.name} — ${Math.round(fracao * 100)}%`),
      });
      situacao("Arquivo recebido. Copiando…");
      esconderEscolhas();
      await acompanhar(modal, loteId);
    } catch (erro) {
      botaoEnviar.disabled = false;
      situacao("");
      avisar(mensagemDeErro(erro), "erro");
    }
  });

  modal.querySelector("#migracao-iniciar")?.addEventListener("click", async (evento) => {
    const iniciar = evento.currentTarget;
    iniciar.disabled = true;
    try {
      // `pedir`, e não `enviar`: sem internet isto não pode ir pra fila e
      // disparar sozinho horas depois.
      const { lote_id: loteId } = await api.pedir("POST", "/migracao/passo-1");
      esconderEscolhas();
      await acompanhar(modal, loteId);
    } catch (erro) {
      iniciar.disabled = false;
      avisar(mensagemDeErro(erro), "erro");
    }
  });
});
