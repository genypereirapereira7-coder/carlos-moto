/**
 * Tela DADOS — o arquivo do sistema antigo da loja.
 *
 * A versão anterior disto mostrava 183 tabelas com nome de banco
 * (`temp_tb_estado`, `temp_pemissoes`) e o dono nunca abriu. Aqui a tela abre
 * mostrando só o que diz algo sobre ESTA loja — contas a receber, clientes,
 * vendas — com nome de gente. Tabela de estado, NCM e CFOP vem de fábrica com
 * qualquer ERP do Brasil e fica num grupo fechado, pra quem insistir.
 *
 * Só leitura. O que precisa entrar no sistema vivo sai por botão explícito,
 * com conferência antes — não por efeito colateral de abrir uma tela.
 */

import * as api from "../../comum/api.js";
import { dataBr } from "../../comum/formato.js";
import { abrirModal, fecharModal, avisar, mensagemDeErro, escapar } from "../ui.js";

// Sobrevivem ao re-render do WebSocket, como nas outras telas.
let loteAberto = null;
let tabelaAberta = null;
let buscaAberta = "";
let tudoAberto = false;

export async function renderDados(raiz) {
  raiz.innerHTML = `
    <h2>Dados do sistema antigo</h2>
    <p class="fraco">O que a loja tinha antes do Carlos Moto, guardado pra consulta.
      Nada aqui está dentro do sistema — estoque, vendas e financeiro seguem só com o que
      foi cadastrado aqui.</p>

    <div class="cartao">
      <div class="modal-topo">
        <h3>Importações</h3>
        <button class="botao" id="botao-importar-dados" type="button">Importar CSV</button>
      </div>
      <div id="lista-lotes"><p class="fraco">Carregando…</p></div>
    </div>

    <div id="resumo-lote"></div>
    <div id="detalhe-tabela"></div>
  `;

  const lotesEl = () => raiz.querySelector("#lista-lotes");
  const resumoEl = () => raiz.querySelector("#resumo-lote");
  const detalheEl = () => raiz.querySelector("#detalhe-tabela");

  // ----------------------------------------------------------- importações

  async function carregarLotes() {
    try {
      const lotes = await api.pedir("GET", "/dados/lotes");
      if (!lotes.length) {
        lotesEl().innerHTML = `<p class="fraco">Nenhuma importação ainda.
          Gere os CSVs do sistema antigo e toque em <strong>Importar CSV</strong>.</p>`;
        return;
      }
      lotesEl().innerHTML = `
        <div class="tabela-wrap">
          <table class="tabela">
            <thead><tr><th>Importação</th><th>Tamanho</th><th>De onde veio</th><th>Quando</th></tr></thead>
            <tbody>${lotes.map((l) => `
              <tr data-lote="${escapar(l.id)}">
                <td>${escapar(l.descricao)}</td>
                <td data-rotulo="Tamanho">${(l.linhas || 0).toLocaleString("pt-BR")} registro(s)
                  <span class="fraco">· ${l.tabelas || 0} tabela(s)</span></td>
                <td data-rotulo="De onde veio">${escapar(l.origem || "—")}</td>
                <td data-rotulo="Quando">${dataBr(l.criado_em)}</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>`;
      // Reabre o que estava aberto antes do re-render.
      if (loteAberto) await abrirLote(loteAberto);
    } catch (erro) {
      if (lotesEl()) {
        lotesEl().innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
      }
    }
  }

  // ---------------------------------------------------------------- lote

  async function abrirLote(loteId) {
    loteAberto = loteId;
    resumoEl().innerHTML = '<div class="cartao fraco">Carregando…</div>';
    try {
      const { lote, tabelas, fiscais } = await api.pedir("GET", `/dados/${loteId}`);
      const linha = (t) => `
        <tr data-tabela="${escapar(t.tabela)}">
          <td>${escapar(t.titulo)}</td>
          <td data-rotulo="Registros">${t.linhas.toLocaleString("pt-BR")}</td>
          <td data-rotulo="No sistema antigo"><span class="fraco">${escapar(t.tabela)}</span></td>
        </tr>`;
      // O botão só faz sentido quando o lote tem a tabela de clientes.
      const temClientes = tabelas.some((t) => t.tabela === "clientes" && t.linhas > 0);
      const temParcelas = tabelas.some((t) => t.tabela === "parcelas" && t.linhas > 0);
      if (!resumoEl()) return;
      resumoEl().innerHTML = `
        <div class="cartao">
          <div class="modal-topo">
            <h3>${escapar(lote.descricao)}</h3>
            <button class="botao botao--fantasma" id="fechar-lote" type="button">Fechar</button>
          </div>
          ${tabelas.length ? `
            <div class="tabela-wrap">
              <table class="tabela">
                <thead><tr><th>O que é</th><th>Registros</th><th>No sistema antigo</th></tr></thead>
                <tbody id="linhas-tabelas">${tabelas.map(linha).join("")}</tbody>
              </table>
            </div>`
            : '<p class="fraco">Nada com dado de loja nesta importação.</p>'}

          ${temClientes ? `
            <div class="secao-seguinte caixa-destaque">
              <p><strong>Trazer os clientes pro sistema</strong></p>
              <p class="fraco">Cria os clientes do sistema antigo na aba Clientes, com nome, CPF,
                RG, nascimento, telefone, e-mail, endereço e cônjuge — o que cada cadastro tiver.
                Pode rodar de novo: quem já está no sistema só recebe o que está em branco, e nada
                que você digitou é sobrescrito.</p>
              <button class="botao" id="trazer-clientes" type="button">Trazer clientes</button>
              <div id="resultado-trazer"></div>
            </div>` : ""}

          ${temParcelas ? `
            <div class="secao-seguinte caixa-destaque">
              <p><strong>Trazer as parcelas em aberto</strong></p>
              <p class="fraco">Põe na aba Parcelas o que os clientes ainda devem. Pra cada venda
                que tem parcela aberta, monta a moto, a venda e o carnê com as parcelas que
                faltam — com o número que elas têm no carnê de papel do cliente. O que já foi
                pago continua só aqui, em "Parcelas já recebidas". Pode rodar de novo sem
                duplicar.</p>
              <button class="botao" id="trazer-parcelas" type="button">Trazer parcelas</button>
              <div id="resultado-parcelas"></div>
            </div>` : ""}

          ${fiscais.length ? `
            <details class="secao-seguinte">
              <summary class="fraco">${fiscais.length} tabela(s) fiscal/configuração —
                vêm de fábrica com o sistema, iguais em toda loja do Brasil</summary>
              <div class="tabela-wrap">
                <table class="tabela">
                  <thead><tr><th>O que é</th><th>Registros</th><th>No sistema antigo</th></tr></thead>
                  <tbody id="linhas-fiscais">${fiscais.map(linha).join("")}</tbody>
                </table>
              </div>
            </details>` : ""}
        </div>`;
      resumoEl().querySelector("#trazer-clientes")?.addEventListener("click", async (evento) => {
        const botao = evento.target;
        const onde = resumoEl().querySelector("#resultado-trazer");
        botao.disabled = true;
        botao.textContent = "Trazendo…";
        onde.innerHTML = "";
        try {
          const r = await api.pedir("POST", `/dados/${loteAberto}/trazer/clientes`);
          onde.innerHTML = htmlResultadoTrazer(r);
          avisar(`${r.criados.toLocaleString("pt-BR")} cliente(s) no sistema`);
        } catch (erro) {
          onde.innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
        } finally {
          botao.disabled = false;
          botao.textContent = "Trazer clientes";
        }
      });
      resumoEl().querySelector("#trazer-parcelas")?.addEventListener("click", async (evento) => {
        const botao = evento.target;
        const onde = resumoEl().querySelector("#resultado-parcelas");
        botao.disabled = true;
        botao.textContent = "Trazendo…";
        onde.innerHTML = "";
        try {
          const r = await api.pedir("POST", `/dados/${loteAberto}/trazer/parcelas`);
          onde.innerHTML = htmlResultadoParcelas(r);
          avisar(`${r.parcelas.toLocaleString("pt-BR")} parcela(s) na aba Parcelas`);
        } catch (erro) {
          onde.innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
        } finally {
          botao.disabled = false;
          botao.textContent = "Trazer parcelas";
        }
      });
      resumoEl().querySelector("#fechar-lote").addEventListener("click", () => {
        loteAberto = null; tabelaAberta = null;
        resumoEl().innerHTML = ""; detalheEl().innerHTML = "";
      });
      if (tabelaAberta) await abrirTabela(tabelaAberta);
    } catch (erro) {
      if (resumoEl()) {
        resumoEl().innerHTML = `<div class="cartao"><p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p></div>`;
      }
    }
  }

  /**
   * O que aconteceu na importação — inclusive o que **não** entrou.
   *
   * A lista de quem ficou de fora é o ponto todo desta tela: sem ela o dono
   * fecharia a página acreditando que os 1.782 cadastros entraram, e ia
   * descobrir o furo no dia em que procurasse um cliente e não achasse.
   */
  function htmlResultadoTrazer(r) {
    const descartados = Object.entries(r.descartados || {});
    return `
      <div class="secao-seguinte">
        <p class="faixa faixa--ok">${r.criados.toLocaleString("pt-BR")} cliente(s) criado(s)${
          r.completados ? `, ${r.completados} que já existia(m) ganharam dados que faltavam` : ""
        }${r.juntados ? `, ${r.juntados} cadastro(s) repetido(s) juntado(s)` : ""}.</p>

        ${descartados.length ? `
          <p class="fraco">Campo que veio errado do sistema antigo e ficou de fora
            (o cliente entrou, só sem ele):
            ${descartados.map(([campo, n]) => `<strong>${escapar(campo)}</strong> em ${n}`).join(", ")}.</p>` : ""}

        ${r.pulados?.length ? `
          <details class="secao-seguinte">
            <summary><strong>${r.pulados.length} cadastro(s) não deu pra trazer</strong> —
              toque pra ver quem, e completar à mão</summary>
            <p class="fraco">Eles continuam inteiros aqui na aba Dados. O que falta é o CPF:
              é ele que identifica a pessoa no sistema novo.</p>
            <div class="tabela-wrap">
              <table class="tabela">
                <thead><tr><th>Código no sistema antigo</th><th>Nome</th><th>Por quê</th></tr></thead>
                <tbody>${r.pulados.map((p) => `
                  <tr>
                    <td>${escapar(p.codigo || "—")}</td>
                    <td data-rotulo="Nome">${escapar(p.nome)}</td>
                    <td data-rotulo="Por quê"><span class="fraco">${escapar(p.motivo)}</span></td>
                  </tr>`).join("")}</tbody>
              </table>
            </div>
          </details>` : ""}
      </div>`;
  }

  // Lupa. Fica num pedaço de HTML só pra não repetir o SVG em cada tela.
  const HTML_LUPA = `
    <svg class="lupa" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path>
    </svg>`;

  /**
   * A dica do campo diz **como** procurar naquela tabela.
   *
   * Sem isso o dono digitava o CPF com ponto e não achava (no arquivo antigo
   * uns vêm formatados e outros não), e tentava a data em dd/mm/aaaa numa
   * busca que só olhava o texto cru, em aaaa-mm-dd. As duas coisas agora
   * funcionam — ver `servicos/busca_antiga.py` — e a dica é o que conta isso
   * pra quem está olhando a tela.
   */
  function dicaDeBusca(tabela) {
    const nome = String(tabela || "").toLowerCase();
    if (nome === "clientes" || nome === "pessoa" || nome === "fornecedor") {
      return "Buscar por nome, CPF ou CNPJ";
    }
    if (nome === "pedidos" || nome === "pedidoscancelados" || nome === "it_pedid") {
      return "Buscar por nome, nº da venda ou data (26/09/2026)";
    }
    if (nome === "parcelas" || nome === "recebidas" || nome === "renegociar" || nome === "cheques") {
      return "Buscar por nome ou vencimento (10/2026)";
    }
    return "Buscar nesta tabela";
  }

  function htmlResultadoParcelas(r) {
    const reais = (centavos) => (centavos / 100).toLocaleString(
      "pt-BR", { style: "currency", currency: "BRL" });
    return `
      <div class="secao-seguinte">
        <p class="faixa faixa--ok">${r.parcelas.toLocaleString("pt-BR")} parcela(s) em aberto,
          ${reais(r.centavos)} a receber — em ${r.vendas} venda(s) e ${r.motos} moto(s).</p>

        ${r.puladas?.length ? `
          <details class="secao-seguinte">
            <summary><strong>${r.parcelas_puladas} parcela(s) não deu pra trazer</strong> —
              toque pra ver por quê</summary>
            <p class="fraco">Elas continuam aqui na aba Dados, na tabela "Parcelas em aberto".
              O que falta é a venda ou a moto por trás delas.</p>
            <div class="tabela-wrap">
              <table class="tabela">
                <thead><tr><th>Venda nº</th><th>Cliente</th><th>Parcelas</th><th>Por quê</th></tr></thead>
                <tbody>${r.puladas.map((p) => `
                  <tr>
                    <td>${escapar(p.numero || "—")}</td>
                    <td data-rotulo="Cliente">${escapar(p.nome)}</td>
                    <td data-rotulo="Parcelas">${p.parcelas}</td>
                    <td data-rotulo="Por quê"><span class="fraco">${escapar(p.motivo)}</span></td>
                  </tr>`).join("")}</tbody>
              </table>
            </div>
          </details>` : ""}
      </div>`;
  }

  // -------------------------------------------------------- nota fiscal

  /**
   * Abre a nota fiscal do backup como documento.
   *
   * O XML fica guardado inteiro na tabela — sete mil caracteres numa célula,
   * que ninguém lê. Quem transforma isso em número, emitente, itens e total é
   * o servidor (`servicos/nota_fiscal.py`); aqui é só a folha.
   */
  async function abrirNota(tabela, numero) {
    const modal = abrirModal('<div class="cartao fraco">Abrindo a nota…</div>');
    try {
      const n = await api.pedir(
        "GET",
        `/dados/${loteAberto}/nota/${numero}?tabela=${encodeURIComponent(tabela)}`,
      );
      modal.innerHTML = htmlNota(n);
      modal.querySelector("#fechar-nota").addEventListener("click", () => fecharModal(modal));
    } catch (erro) {
      modal.innerHTML = `
        <div class="modal-topo"><h3>Nota fiscal</h3></div>
        <p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>
        <div class="acoes-modal">
          <button class="botao botao--fantasma" id="fechar-nota" type="button">Fechar</button>
        </div>`;
      modal.querySelector("#fechar-nota").addEventListener("click", () => fecharModal(modal));
    }
  }

  /** `2026-09-26T14:32:05-04:00` -> `26/09/2026 14:32`. */
  function dataHoraBr(valor) {
    const texto = String(valor || "");
    const dia = texto.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dia)) return texto;
    const [a, m, d] = dia.split("-");
    const hora = texto.slice(11, 16);
    return hora ? `${d}/${m}/${a} ${hora}` : `${d}/${m}/${a}`;
  }

  /** `1234.56` do XML -> `R$ 1.234,56`. */
  function reaisDoXml(valor) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return escapar(valor || "");
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function documentoBr(doc) {
    const d = String(doc || "").replace(/\D/g, "");
    if (d.length === 11) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
    if (d.length === 14) {
      return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
    }
    return d;
  }

  function blocoPessoa(titulo, p) {
    if (!p?.nome) return "";
    return `
      <h4>${escapar(titulo)}</h4>
      <p>${escapar(p.nome)}${p.fantasia && p.fantasia !== p.nome ? ` <span class="fraco">(${escapar(p.fantasia)})</span>` : ""}</p>
      <p class="fraco">
        ${p.documento ? escapar(documentoBr(p.documento)) : ""}
        ${p.inscricao ? ` · IE ${escapar(p.inscricao)}` : ""}
        ${p.telefone ? ` · ${escapar(p.telefone)}` : ""}
      </p>
      ${p.endereco ? `<p class="fraco">${escapar(p.endereco)}</p>` : ""}`;
  }

  function htmlNota(n) {
    return `
      <div class="modal-topo">
        <h3>Nota fiscal ${escapar(n.numero)}${n.serie ? ` · série ${escapar(n.serie)}` : ""}</h3>
        <button class="botao botao--fantasma" id="fechar-nota" type="button">Fechar</button>
      </div>

      ${n.cancelada ? '<p class="faixa faixa--erro">Nota cancelada.</p>' : ""}
      ${n.situacao && !n.cancelada ? `<p class="faixa faixa--ok">${escapar(n.situacao)}</p>` : ""}

      <dl class="linhas-dados">
        <div><dt>Emitida em</dt><dd>${escapar(dataHoraBr(n.emitida_em))}</dd></div>
        <div><dt>Tipo</dt><dd>${escapar(n.tipo)}</dd></div>
        ${n.natureza ? `<div><dt>Natureza da operação</dt><dd>${escapar(n.natureza)}</dd></div>` : ""}
        ${n.protocolo ? `<div><dt>Protocolo</dt><dd>${escapar(n.protocolo)}</dd></div>` : ""}
        ${n.autorizada_em ? `<div><dt>Autorizada em</dt><dd>${escapar(dataHoraBr(n.autorizada_em))}</dd></div>` : ""}
      </dl>
      ${n.chave ? `<p class="fraco">Chave de acesso: <span class="chave-nota">${escapar(n.chave)}</span></p>` : ""}

      <div class="grade-2 secao-seguinte">
        <div>${blocoPessoa("Emitente", n.emitente)}</div>
        <div>${blocoPessoa("Destinatário", n.destinatario)}</div>
      </div>

      ${n.itens?.length ? `
        <h4 class="secao-seguinte">Itens</h4>
        <div class="tabela-wrap">
          <table class="tabela">
            <thead><tr>
              <th>Descrição</th><th>Un.</th><th>Qtd.</th><th>Valor unitário</th><th>Total</th>
            </tr></thead>
            <tbody>${n.itens.map((i) => `
              <tr>
                <td>${escapar(i.descricao)}${i.codigo ? ` <span class="fraco">· cód. ${escapar(i.codigo)}</span>` : ""}</td>
                <td data-rotulo="Un.">${escapar(i.unidade)}</td>
                <td data-rotulo="Qtd.">${escapar(String(Number(i.quantidade) || i.quantidade))}</td>
                <td data-rotulo="Valor unitário">${reaisDoXml(i.valor_unitario)}</td>
                <td data-rotulo="Total">${reaisDoXml(i.valor_total)}</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>` : ""}

      <div class="conta secao-seguinte">
        <div class="conta-linha"><span>Produtos</span><span>${reaisDoXml(n.valor_produtos)}</span></div>
        ${Number(n.valor_desconto) ? `<div class="conta-linha"><span>Desconto</span><span>- ${reaisDoXml(n.valor_desconto)}</span></div>` : ""}
        ${Number(n.valor_frete) ? `<div class="conta-linha"><span>Frete</span><span>${reaisDoXml(n.valor_frete)}</span></div>` : ""}
        <div class="conta-linha conta-linha--total"><span>Total da nota</span><span>${reaisDoXml(n.valor_total)}</span></div>
      </div>

      ${n.pagamentos?.length ? `
        <p class="fraco secao-seguinte">Pagamento:
          ${n.pagamentos.map((p) => `${escapar(p.forma)} ${reaisDoXml(p.valor)}`).join(", ")}</p>` : ""}
      ${n.observacao ? `
        <h4 class="secao-seguinte">Observações</h4>
        <p class="texto-observacao">${escapar(n.observacao)}</p>` : ""}`;
  }

  // -------------------------------------------------------------- tabela

  async function abrirTabela(tabela, pagina = 1) {
    // Trocar de tabela começa de novo: busca e "mostrar tudo" são da tabela
    // que estava aberta, não do lote. Sem isso o termo digitado em Clientes
    // filtrava Vendas e parecia que Vendas estava vazia.
    if (tabela !== tabelaAberta) { buscaAberta = ""; tudoAberto = false; }
    tabelaAberta = tabela;
    detalheEl().innerHTML = '<div class="cartao fraco">Carregando…</div>';
    try {
      const busca = buscaAberta ? `&busca=${encodeURIComponent(buscaAberta)}` : "";
      const d = await api.pedir(
        "GET",
        `/dados/${loteAberto}/${tabela}?pagina=${pagina}${busca}${tudoAberto ? "&tudo=true" : ""}`,
      );
      const paginas = Math.max(1, Math.ceil(d.total / d.por_pagina));
      // Trocou de aba antes da resposta? Então este bloco já saiu da tela.
      if (!detalheEl()) return;
      detalheEl().innerHTML = `
        <div class="cartao">
          <div class="modal-topo">
            <h3>${escapar(d.titulo)} <span class="fraco">· ${d.total.toLocaleString("pt-BR")} registro(s)</span></h3>
            <button class="botao botao--fantasma" id="fechar-tabela" type="button">Fechar</button>
          </div>
          <div class="barra-busca">
            <label class="campo-busca">
              ${HTML_LUPA}
              <input id="busca-dados" placeholder="${escapar(dicaDeBusca(tabela))}"
                autocomplete="off" inputmode="search" value="${escapar(buscaAberta)}" />
            </label>
          </div>
          ${d.escondidas ? `<p class="fraco">${d.escondidas} coluna(s) de controle interno do sistema antigo
            não aparecem — são códigos de ligação, tributação e campos de boleto.
            <button class="botao-link" id="mostrar-tudo" type="button">Mostrar todas</button></p>`
            : tudoAberto ? `<p class="fraco">Mostrando todas as colunas, inclusive as de controle interno.
            <button class="botao-link" id="mostrar-tudo" type="button">Esconder as internas</button></p>` : ""}
          ${d.linhas.length ? `
            <div class="tabela-wrap">
              <table class="tabela">
                <thead><tr>
                  ${d.tem_nota ? "<th>Nota</th>" : ""}
                  ${d.colunas.map((c) => `<th>${escapar(c.titulo)}</th>`).join("")}
                </tr></thead>
                <tbody>${d.linhas.map((l, i) => `<tr>
                  ${d.tem_nota ? `<td data-rotulo="Nota">
                    <button class="botao-link abrir-nota" type="button"
                      data-numero="${d.numeros[i]}">Abrir nota</button></td>` : ""}
                  ${l.map((v) => `<td>${escapar(v ?? "")}</td>`).join("")}
                </tr>`).join("")}</tbody>
              </table>
            </div>
            ${paginas > 1 ? `
              <div class="acoes-linha secao-seguinte">
                <button class="botao botao--fantasma" id="pagina-anterior" type="button" ${pagina <= 1 ? "disabled" : ""}>Anterior</button>
                <span class="fraco">página ${pagina} de ${paginas}</span>
                <button class="botao botao--fantasma" id="pagina-proxima" type="button" ${pagina >= paginas ? "disabled" : ""}>Próxima</button>
              </div>` : ""}`
            : `<p class="fraco">${buscaAberta ? "Nada encontrado com esse termo." : "Tabela vazia."}</p>`}
        </div>`;

      detalheEl().querySelector("#fechar-tabela").addEventListener("click", () => {
        tabelaAberta = null; buscaAberta = ""; tudoAberto = false; detalheEl().innerHTML = "";
      });
      let timer = null;
      detalheEl().querySelector("#busca-dados").addEventListener("input", (evento) => {
        const termo = evento.target.value;
        clearTimeout(timer);
        // Espera a digitação parar — senão é uma busca por tecla apertada.
        timer = setTimeout(() => { buscaAberta = termo.trim(); abrirTabela(tabela, 1); }, 300);
      });
      detalheEl().querySelectorAll(".abrir-nota").forEach((botao) => {
        botao.addEventListener("click", () => abrirNota(tabela, botao.dataset.numero));
      });
      detalheEl().querySelector("#mostrar-tudo")?.addEventListener("click", () => {
        tudoAberto = !tudoAberto;
        abrirTabela(tabela, pagina);
      });
      detalheEl().querySelector("#pagina-anterior")?.addEventListener("click", () => abrirTabela(tabela, pagina - 1));
      detalheEl().querySelector("#pagina-proxima")?.addEventListener("click", () => abrirTabela(tabela, pagina + 1));
      detalheEl().scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (erro) {
      if (detalheEl()) {
        detalheEl().innerHTML = `<div class="cartao"><p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p></div>`;
      }
    }
  }

  // ------------------------------------------------------------ importar

  function abrirModalImportar() {
    const modal = abrirModal(`
      <div class="modal-topo"><h3>Importar dados do sistema antigo</h3></div>
      <p class="fraco">Serve o <strong>backup .sql</strong> do sistema antigo (MySQL/MariaDB),
        arquivos <strong>.csv</strong>, ou um <strong>.zip</strong> com eles dentro.</p>
      <form id="form-importar-dados" novalidate>
        <label class="campo">Nome desta importação
          <input name="descricao" placeholder="Ex.: Sistema da loja, setembro/2026" required />
        </label>
        <label class="campo">De onde veio <span class="fraco">(opcional)</span>
          <input name="origem" placeholder="Ex.: computador do balcão, banco Firebird" />
        </label>
        <label class="campo">Arquivos
          <input name="arquivos" type="file" accept=".csv,.sql,.zip" multiple required />
        </label>
        <p class="previa" id="previa-importar"></p>
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-importar">Cancelar</button>
          <button type="submit" class="botao" id="confirmar-importar">Importar</button>
        </div>
      </form>
    `);
    const form = modal.querySelector("#form-importar-dados");
    const previa = modal.querySelector("#previa-importar");
    modal.querySelector("#cancelar-importar").addEventListener("click", () => fecharModal(modal));

    form.elements.arquivos.addEventListener("change", () => {
      const lista = [...form.elements.arquivos.files];
      const mb = lista.reduce((t, f) => t + f.size, 0) / 1024 / 1024;
      previa.textContent = lista.length
        ? `${lista.length} arquivo(s) · ${mb.toFixed(1)} MB`
        : "";
    });

    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const lista = [...form.elements.arquivos.files];
      if (!form.elements.descricao.value.trim() || !lista.length) {
        avisar("Dê um nome à importação e escolha os arquivos", "erro");
        return;
      }
      const botao = modal.querySelector("#confirmar-importar");
      botao.disabled = true;
      botao.textContent = "Importando…";
      try {
        const r = await api.enviarArquivo("/dados/importar", lista, {
          extras: {
            descricao: form.elements.descricao.value.trim(),
            origem: form.elements.origem.value.trim(),
          },
          aoProgredir: (fracao) => {
            botao.textContent = `Importando… ${Math.round(fracao * 100)}%`;
          },
        });
        fecharModal(modal);
        avisar(`${r.linhas.toLocaleString("pt-BR")} registro(s) em ${r.tabelas} tabela(s)`, "ok");
        if (r.ignorados?.length) {
          avisar(`${r.ignorados.length} arquivo(s) ignorado(s) — veja a lista`, "erro");
        }
        loteAberto = r.lote_id;
        await carregarLotes();
      } catch (erro) {
        botao.disabled = false;
        botao.textContent = "Importar";
        avisar(mensagemDeErro(erro), "erro");
      }
    });
  }

  // ------------------------------------------------------------ ligações

  raiz.querySelector("#botao-importar-dados").addEventListener("click", abrirModalImportar);
  lotesEl().addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-lote]");
    if (linha) { tabelaAberta = null; buscaAberta = ""; abrirLote(linha.dataset.lote); }
  });
  resumoEl().addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-tabela]");
    if (linha) { buscaAberta = ""; abrirTabela(linha.dataset.tabela); }
  });

  await carregarLotes();
}
