/**
 * Tela SISTEMA ANTIGO — o que veio da migração, e o botão de trazer clientes.
 *
 * PROVISÓRIA, sai quando a migração acabar. Mostra as tabelas do sistema
 * antigo (só as que têm dados) pra consulta, e traz as pessoas pra tela de
 * Clientes — sempre com um ensaio antes, pra ninguém gravar às cegas.
 */

import * as api from "../../comum/api.js";
import { abrirModal, fecharModal, avisar, escapar, mensagemDeErro } from "../ui.js";

export async function renderAntigo(raiz) {
  raiz.innerHTML = `
    <h2>Sistema Antigo</h2>
    <p class="fraco">O que foi copiado do sistema antigo, esperando o passo 2. Nada aqui está
      dentro do sistema ainda — é uma cópia separada, só pra consulta e pra trazer os clientes.</p>

    <div class="cartao">
      <div class="modal-topo">
        <h3>Trazer clientes pro sistema</h3>
        <button class="botao" id="botao-importar-clientes" type="button">Trazer clientes</button>
      </div>
      <p class="fraco">Pega as pessoas do sistema antigo e cria o cadastro delas na aba Clientes.
        Antes de gravar, mostra o que vai entrar e o que fica de fora.</p>
    </div>

    <div class="cartao">
      <h3>Tabelas migradas</h3>
      <div id="antigo-tabelas"><p class="fraco">Carregando…</p></div>
    </div>

    <div id="antigo-detalhe"></div>
  `;

  const listaEl = () => raiz.querySelector("#antigo-tabelas");
  const detalheEl = () => raiz.querySelector("#antigo-detalhe");

  async function carregar() {
    try {
      const { lote, tabelas } = await api.pedir("GET", "/antigo");
      if (!lote || !tabelas.length) {
        listaEl().innerHTML = '<p class="fraco">Nada migrado ainda. Use "Migrar sistema antigo" primeiro.</p>';
        return;
      }
      listaEl().innerHTML = `
        <p class="fraco">Lote ${lote} · ${tabelas.length} tabela(s) com dados (as vazias e as de imposto ficaram de fora)</p>
        <div class="tabela-wrap">
          <table class="tabela">
            <thead><tr><th>Tabela</th><th>Registros</th></tr></thead>
            <tbody id="antigo-linhas">${tabelas.map((t) => `
              <tr data-tabela="${escapar(t.nome)}">
                <td data-rotulo="Tabela">${escapar(t.curto)}</td>
                <td data-rotulo="Registros">${t.linhas.toLocaleString("pt-BR")}</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>`;
    } catch (erro) {
      listaEl().innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
    }
  }

  async function abrirTabela(nome) {
    detalheEl().innerHTML = '<div class="cartao fraco">Carregando…</div>';
    try {
      const { colunas, linhas, total } = await api.pedir("GET", `/antigo/tabela/${nome}`);
      detalheEl().innerHTML = `
        <div class="cartao">
          <div class="modal-topo">
            <h3>${escapar(nome.replace("temp_", ""))} <span class="fraco">· ${total.toLocaleString("pt-BR")} linhas${linhas.length < total ? ` (mostrando ${linhas.length})` : ""}</span></h3>
            <button class="botao botao--fantasma" id="fechar-tabela" type="button">Fechar</button>
          </div>
          <div class="tabela-wrap">
            <table class="tabela">
              <thead><tr>${colunas.map((c) => `<th>${escapar(c)}</th>`).join("")}</tr></thead>
              <tbody>${linhas.map((l) => `<tr>${l.map((v) => `<td>${escapar(v ?? "")}</td>`).join("")}</tr>`).join("")}</tbody>
            </table>
          </div>
        </div>`;
      detalheEl().querySelector("#fechar-tabela").addEventListener("click", () => { detalheEl().innerHTML = ""; });
      detalheEl().scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (erro) {
      detalheEl().innerHTML = `<div class="cartao"><p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p></div>`;
    }
  }

  // ------------------------------------------------ importar clientes

  function _resultado(r) {
    const quantos = r.ensaio ? r.criaria : r.criados;
    const pulados = r.pulados.length
      ? `<h3 class="secao-seguinte">Ficaram de fora (${r.pulados.length})</h3>
         <ul class="lista-simples">${r.pulados.map((m) => `<li>${escapar(m)}</li>`).join("")}</ul>`
      : "";
    const avisos = r.avisos.length
      ? `<h3 class="secao-seguinte">Entraram com aviso (${r.avisos.length})</h3>
         <ul class="lista-simples">${r.avisos.map((a) => `<li class="texto-a-vencer">${escapar(a)}</li>`).join("")}</ul>`
      : "";
    const amostra = r.amostra.length
      ? `<h3 class="secao-seguinte">${r.ensaio ? "Amostra do que vai entrar" : "Alguns que entraram"}</h3>
         <ul class="lista-simples">${r.amostra.map((c) =>
            `<li>${escapar(c.nome)} · ${escapar(c.cpf)}${c.telefone ? ` · ${escapar(c.telefone)}` : ""}</li>`).join("")}</ul>`
      : "";
    return `
      <p><strong>${quantos}</strong> ${r.ensaio ? "cliente(s) vão entrar" : "cliente(s) criados"} ·
         <strong>${r.ja_existiam}</strong> já estavam no sistema · de ${r.total_pessoas} pessoas no total.</p>
      ${amostra}${avisos}${pulados}`;
  }

  async function importar() {
    let ensaio;
    try {
      ensaio = await api.pedir("POST", "/antigo/importar-clientes", { ensaio: true });
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
      return;
    }

    const modal = abrirModal(`
      <div class="modal-topo"><h3>Trazer clientes — conferência</h3></div>
      <p class="fraco">Isto é só a prévia. Nada foi gravado ainda. Confira e decida.</p>
      <div id="ensaio-resultado">${_resultado(ensaio)}</div>
      <div class="acoes-modal">
        <button class="botao botao--fantasma" data-fechar type="button">Cancelar</button>
        <button class="botao" id="confirmar-importar" type="button" ${ensaio.criaria ? "" : "disabled"}>
          Importar ${ensaio.criaria} cliente(s)
        </button>
      </div>
    `);

    modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#confirmar-importar").addEventListener("click", async (evento) => {
      const botao = evento.currentTarget;
      botao.disabled = true;
      botao.textContent = "Importando…";
      try {
        const feito = await api.pedir("POST", "/antigo/importar-clientes", { ensaio: false });
        modal.querySelector("#ensaio-resultado").innerHTML = _resultado(feito);
        modal.querySelector(".acoes-modal").innerHTML =
          '<button class="botao" data-fechar type="button">Pronto</button>';
        modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));
        avisar(`${feito.criados} cliente(s) trazidos pro sistema`, "ok");
      } catch (erro) {
        botao.disabled = false;
        botao.textContent = "Tentar de novo";
        avisar(mensagemDeErro(erro), "erro");
      }
    });
  }

  raiz.querySelector("#botao-importar-clientes").addEventListener("click", importar);
  raiz.querySelector("#antigo-tabelas").addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-tabela]");
    if (linha) abrirTabela(linha.dataset.tabela);
  });

  await carregar();
}
