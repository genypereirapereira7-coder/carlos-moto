/**
 * Botão PROVISÓRIO de migração do sistema antigo — sai depois da virada.
 *
 * A ordem importa: **primeiro ele procura sozinho.** No computador onde o
 * sistema antigo está, o servidor varre o disco, acha o banco e copia — um
 * clique, sem ninguém escolher arquivo nenhum.
 *
 * Escolher arquivo só aparece quando não há o que procurar: é o caso de quem
 * abre o sistema pela internet. Ali o navegador proíbe qualquer página de
 * vasculhar o disco (e ainda bem), e a única saída é a pessoa apontar o
 * arquivo de propósito.
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

function tamanho(bytes) {
  const mega = bytes / (1024 * 1024);
  return mega >= 1 ? `${mega.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
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

botao.addEventListener("click", async () => {
  const estado = estadoAtual || {};
  const modal = abrirModal(`
    <div class="modal-topo"><h3>Migrar o sistema antigo — passo 1</h3></div>
    <p>Copia <strong>tudo</strong> do sistema antigo pra nuvem, do jeito que está: clientes,
      contratos, tickets, dados da empresa e qualquer outra tabela que existir.</p>
    <p class="fraco">O sistema antigo não é alterado, e nada entra ainda no sistema novo — a cópia
      fica separada, esperando o passo 2. Pode repetir: cada cópia gera um lote novo.</p>
    <div id="migracao-escolhas"><p class="fraco">Procurando o sistema antigo neste computador…</p></div>
    <p id="migracao-situacao" class="fraco"></p>
    <ul class="lista-fila" id="migracao-tabelas"></ul>
    <ul class="lista-simples" id="migracao-erros"></ul>
    <div class="acoes-modal">
      <button class="botao botao--fantasma" data-fechar type="button">Fechar</button>
    </div>
  `);

  const escolhas = modal.querySelector("#migracao-escolhas");
  const situacao = (texto) => { modal.querySelector("#migracao-situacao").textContent = texto; };
  modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));

  // ------------------------------------------------- procura, antes de tudo
  let achados = [];
  try {
    achados = (await api.pedir("GET", "/migracao/procurar")).achados || [];
  } catch { /* na nuvem não acha nada; o seletor entra no lugar */ }
  if (!modal.isConnected) return;

  const seletor = estado.envio ? `
    <p class="fraco" id="migracao-alternativa">
      ${achados.length
        ? 'Não é nenhum desses? <button type="button" class="link" id="migracao-mostrar-envio">Enviar o arquivo</button>'
        : "Este servidor não achou nenhum sistema antigo no disco — é o que acontece quando você abre pela internet. Escolha o arquivo do sistema antigo no seu computador:"}
    </p>
    <div id="migracao-envio" ${achados.length ? "hidden" : ""}>
      <label class="campo">Arquivo do sistema antigo
        <input type="file" id="migracao-arquivo" accept="${(estado.formatos || []).join(",")}" />
      </label>
      <p class="fraco">Aceita ${(estado.formatos || []).join(", ")}, até ${estado.limite_mb || 500} MB.
        Se for uma pasta com vários arquivos, compacte em .zip.</p>
      <div class="acoes-modal">
        <button class="botao" id="migracao-enviar" type="button">Enviar e copiar</button>
      </div>
    </div>` : "";

  escolhas.innerHTML = `
    ${achados.length ? `
      <h3 class="secao-seguinte">Achei ${achados.length === 1 ? "o sistema antigo" : `${achados.length} possíveis sistemas antigos`} neste computador</h3>
      ${achados[0].busca_incompleta ? '<p class="fraco">A busca parou antes de varrer o disco inteiro (disco grande ou lento). Se o sistema antigo não estiver na lista, use o envio de arquivo abaixo.</p>' : ""}
      <ul class="lista-fila">
        ${achados.map((a, i) => `
          <li>
            <div>
              <strong>${escapar(a.nome)}</strong>${i === 0 ? ' <span class="selo selo--em-dia">mais provável</span>' : ""}
              <p class="fraco">${escapar(a.tipo)} · ${tamanho(a.bytes)}${a.arquivos > 1 ? ` · ${a.arquivos} arquivos` : ""}
                · mexido em ${escapar(a.modificado)}<br />${escapar(a.caminho)}</p>
            </div>
            <button class="botao botao--pequeno" data-copiar="${escapar(a.caminho)}" type="button">Copiar agora</button>
          </li>`).join("")}
      </ul>` : ""}
    ${seletor}`;

  const esconderEscolhas = () => { escolhas.hidden = true; };

  // ------------------------------------------------------- copiar o achado
  escolhas.addEventListener("click", async (evento) => {
    const mostrar = evento.target.closest("#migracao-mostrar-envio");
    if (mostrar) {
      modal.querySelector("#migracao-envio").hidden = false;
      mostrar.hidden = true;
      return;
    }

    const copiar = evento.target.closest("[data-copiar]");
    if (copiar) {
      copiar.disabled = true;
      try {
        // `pedir`, e não `enviar`: sem internet isto não pode ir pra fila e
        // disparar sozinho horas depois.
        const { lote_id: loteId } = await api.pedir("POST", "/migracao/passo-1", {
          caminho: copiar.dataset.copiar,
        });
        esconderEscolhas();
        await acompanhar(modal, loteId);
      } catch (erro) {
        copiar.disabled = false;
        avisar(mensagemDeErro(erro), "erro");
      }
      return;
    }

    const enviar = evento.target.closest("#migracao-enviar");
    if (enviar) {
      const arquivo = modal.querySelector("#migracao-arquivo")?.files?.[0];
      if (!arquivo) {
        avisar("Escolha o arquivo do sistema antigo primeiro", "erro");
        return;
      }
      enviar.disabled = true;
      try {
        const { lote_id: loteId } = await api.enviarArquivo("/migracao/enviar", arquivo, {
          aoProgredir: (fracao) => situacao(`Enviando ${arquivo.name} — ${Math.round(fracao * 100)}%`),
        });
        situacao("Arquivo recebido. Copiando…");
        esconderEscolhas();
        await acompanhar(modal, loteId);
      } catch (erro) {
        enviar.disabled = false;
        situacao("");
        avisar(mensagemDeErro(erro), "erro");
      }
    }
  });
});
