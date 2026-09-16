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

  // Quando a varredura não acha nada, quem está olhando abriu o sistema pela
  // internet — e aí nenhuma página pode ler o disco dela. O que a página pode
  // fazer é entregar o programa que lê: ele roda na máquina, acha sozinho e
  // copia. É o "clica e clona" possível.
  const programa = achados.length ? "" : `
    <h3 class="secao-seguinte">Clonar sem escolher nada</h3>
    <p class="fraco">Esta página não consegue varrer o disco deste computador — nenhum site
      consegue, e é o que impede qualquer site de ler os seus documentos. Quem varre é um
      programa rodando aqui dentro:</p>
    <ol class="passos-instalar">
      <li><span>Baixe o programa abaixo e abra com dois cliques.</span></li>
      <li><span>O Windows vai avisar que é um programa desconhecido:
        <strong>Mais informações</strong> → <strong>Executar assim mesmo</strong>.</span></li>
      <li><span>Cole a chave de acesso. Ele acha o sistema antigo sozinho, copia e avisa
        quando terminar.</span></li>
    </ol>
    <div class="acoes-modal">
      <a class="botao" href="./MigrarCarlosMoto.exe" download="MigrarCarlosMoto.exe">
        Baixar o clonador (Windows)
      </a>
    </div>`;

  const seletor = estado.envio ? `
    ${programa}
    <p class="fraco" id="migracao-alternativa">
      ${achados.length
        ? 'Não é nenhum desses? <button type="button" class="link" id="migracao-mostrar-envio">Enviar o arquivo</button>'
        : "Ou, se preferir fazer por aqui mesmo, aponte a pasta do sistema antigo:"}
    </p>
    <div id="migracao-envio" ${achados.length ? "hidden" : ""}>
      <label class="campo">A pasta inteira do sistema antigo <span class="fraco">(o jeito bom)</span>
        <input type="file" id="migracao-pasta" webkitdirectory directory multiple />
      </label>
      <label class="campo">Ou um arquivo só, se você souber qual é
        <input type="file" id="migracao-arquivo" accept="${(estado.formatos || []).join(",")}" multiple />
      </label>
      <p class="fraco" id="migracao-resumo">Aponte a pasta onde o sistema antigo está instalado.
        O que não for banco de dados (programa, ajuda, imagem) é descartado sozinho — até
        ${estado.limite_mb || 500} MB no total.</p>
      <div class="acoes-modal">
        <button class="botao" id="migracao-enviar" type="button">Clonar os dados</button>
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

  // Da pasta inteira, só o que é banco de dados. Uma pasta de sistema antigo
  // tem dezenas de .exe, .dll e ajuda — mandar tudo seria megabytes à toa, e o
  // servidor descartaria do mesmo jeito.
  const formatos = (estado.formatos || []).map((f) => f.toLowerCase());
  const eBanco = (arquivo) => formatos.some((f) => arquivo.name.toLowerCase().endsWith(f));

  function selecionados() {
    const daPasta = [...(modal.querySelector("#migracao-pasta")?.files || [])];
    const soltos = [...(modal.querySelector("#migracao-arquivo")?.files || [])];
    return [...daPasta, ...soltos].filter(eBanco);
  }

  // Assim que a pasta é apontada, a tela diz o que vai mandar — antes de mandar.
  escolhas.addEventListener("change", (evento) => {
    if (!evento.target.matches("#migracao-pasta, #migracao-arquivo")) return;
    const total = [...(modal.querySelector("#migracao-pasta")?.files || []),
                   ...(modal.querySelector("#migracao-arquivo")?.files || [])].length;
    const bons = selecionados();
    const bytes = bons.reduce((soma, a) => soma + a.size, 0);
    const resumo = modal.querySelector("#migracao-resumo");
    if (!resumo) return;
    resumo.textContent = bons.length
      ? `Achei ${bons.length} arquivo(s) de banco de dados em ${total}, somando ${tamanho(bytes)}. `
        + "O resto (programa, ajuda, imagem) não vai."
      : `Nenhum dos ${total} arquivos é banco de dados que eu saiba abrir.`;
  });

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
      const escolhidos = selecionados();
      if (!escolhidos.length) {
        avisar("Aponte a pasta do sistema antigo primeiro", "erro");
        return;
      }
      enviar.disabled = true;
      const rotulo = escolhidos.length === 1 ? escolhidos[0].name : `${escolhidos.length} arquivos`;
      try {
        const { lote_id: loteId } = await api.enviarArquivo("/migracao/enviar", escolhidos, {
          aoProgredir: (fracao) => situacao(`Enviando ${rotulo} — ${Math.round(fracao * 100)}%`),
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
