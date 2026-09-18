/**
 * Tela CLIENTES: buscar por nome ou CPF e abrir o cadastro da pessoa com as
 * duas pontas do histórico — o que ela **comprou** da loja e o que **vendeu**
 * pra loja.
 *
 * Quem deve parcela aparece em vermelho, na lista e no cadastro: é a
 * pergunta que o dono faz mais vezes por dia nesta tela.
 */

import * as api from "../../comum/api.js";
import { reais, dataBr, cpf as formatarCpf, telefone as formatarTelefone } from "../../comum/formato.js";
import {
  abrirModal, fecharModal, avisar, mensagemDeErro, guardadoNaFila,
  rotuloStatusParcela, classeStatusParcela, classeDoSaldo,
} from "../ui.js";
import * as v from "../validacao.js";
import { htmlCamposConjuge, ligarConjuge, lerConjuge, regrasConjuge, corpoConjuge } from "../conjuge.js";
import { htmlCampoObservacao, lerObservacao, regrasObservacao } from "../observacao.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// Sobrevivem a um `renderClientes` novo — o `app.js` refaz a tela inteira a
// cada evento do WebSocket, e sem isto o cadastro aberto (e a aba escolhida
// dentro dele) sumiam sozinhos no meio de uma consulta.
let clienteAbertoId = null;

// Duas aberturas de detalhe podem estar no ar ao mesmo tempo: a que o usuário
// pediu e a que o re-render do WebSocket dispara pra reabrir o que estava
// aberto. Quem responde por último pinta a tela — e era assim que um cadastro
// novo acabava mostrando o cadastro anterior por cima dele. Só a última
// abertura pedida tem direito de escrever.
let pedidoDetalhe = 0;
let abaHistorico = "comprou";
let filtroLista = "todos";
let buscaAtual = "";

export async function renderClientes(raiz) {
  raiz.innerHTML = `
    <h2>Clientes</h2>
    <div class="barra-busca">
      <input id="busca-cliente" placeholder="Buscar por nome ou CPF" autocomplete="off" value="${escapar(buscaAtual)}" />
      <button class="botao" id="botao-buscar-cliente" type="button">Buscar</button>
      <button class="botao botao--fantasma" id="botao-novo-cliente" type="button">Cadastrar cliente</button>
    </div>
    <div id="detalhe-cliente"></div>
    <div class="cartao">
      <div class="modal-topo">
        <h3>Clientes</h3>
        <div class="abas-filtro" id="filtro-clientes">
          <button class="aba-filtro" data-filtro="todos" type="button">Todos</button>
          <button class="aba-filtro" data-filtro="comprou" type="button">Comprou</button>
          <button class="aba-filtro" data-filtro="vendeu" type="button">Vendeu</button>
        </div>
      </div>
      <div class="tabela-wrap">
        <table class="tabela">
          <thead>
            <tr><th>Nome</th><th>CPF</th><th>Telefone</th><th>Comprou</th><th>Vendeu</th><th>Parcelas</th></tr>
          </thead>
          <tbody id="linhas-clientes"><tr><td colspan="6" class="fraco">Carregando…</td></tr></tbody>
        </table>
      </div>
    </div>
  `;

  // Procurados na hora do uso, não guardados numa variável: o `app.js` refaz
  // esta tela a cada evento do WebSocket, e um elemento guardado aqui vira um
  // nó órfão — o texto escrito nele não aparece mais em lugar nenhum. `raiz`
  // é o único que sobrevive (é o `#conteudo` fixo do app).
  const corpoTabela = () => raiz.querySelector("#linhas-clientes");
  const detalheEl = () => raiz.querySelector("#detalhe-cliente");
  let carregados = [];

  function pintarFiltro() {
    raiz.querySelectorAll(".aba-filtro").forEach((botao) => {
      botao.dataset.ativa = botao.dataset.filtro === filtroLista ? "1" : "0";
    });
  }

  function filtrados() {
    if (filtroLista === "comprou") return carregados.filter((c) => c.qtd_comprou > 0);
    if (filtroLista === "vendeu") return carregados.filter((c) => c.qtd_vendeu > 0);
    return carregados;
  }

  function selo(cliente) {
    if (cliente.saldo_atrasado_centavos > 0) {
      return `<span class="selo selo--devendo">Atrasado ${reais(cliente.saldo_atrasado_centavos)}</span>`;
    }
    if (cliente.deve_parcela) {
      return `<span class="selo selo--pendente">A receber ${reais(cliente.saldo_devedor_centavos)}</span>`;
    }
    if (cliente.qtd_comprou > 0) return '<span class="selo selo--em-dia">Em dia</span>';
    return '<span class="fraco">Sem parcelas</span>';
  }

  function desenharTabela() {
    const lista = filtrados();
    if (!lista.length) {
      corpoTabela().innerHTML =
        '<tr><td colspan="6" class="fraco">Nenhum cliente encontrado.</td></tr>';
      return;
    }
    corpoTabela().innerHTML = lista.map((c) => `
      <tr data-id="${c.id}">
        <td>${escapar(c.nome)}</td>
        <td data-rotulo="CPF">${formatarCpf(c.cpf)}</td>
        <td data-rotulo="Telefone">${escapar(formatarTelefone(c.telefone))}</td>
        <td data-rotulo="Comprou">${c.qtd_comprou}</td>
        <td data-rotulo="Vendeu">${c.qtd_vendeu}</td>
        <td data-rotulo="Parcelas">${selo(c)}</td>
      </tr>
    `).join("");
  }

  async function carregarLista() {
    try {
      const caminho = buscaAtual
        ? `/clientes?busca=${encodeURIComponent(buscaAtual)}`
        : "/clientes";
      carregados = await api.pedir("GET", caminho);
      desenharTabela();
      // Mesma ideia de `telas/motos.js`: sem o cadastro de cada um guardado,
      // a lista abre offline mas nenhum cliente abre.
      api.preAquecer(carregados.map((c) => `/clientes/${c.id}`));
    } catch (erro) {
      corpoTabela().innerHTML = `<tr><td colspan="6" class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</td></tr>`;
    }
  }

  // ------------------------------------------------------------- detalhe

  async function abrirDetalhe(clienteId) {
    // Marcado **antes** do await, não depois: o `app.js` refaz esta tela a
    // cada evento do WebSocket — inclusive o eco do cadastro que acabou de
    // ser feito aqui — e o re-render lê este id pra reabrir o cadastro
    // certo. Se ele fosse marcado só depois da resposta, o re-render
    // chegaria primeiro e reabriria o cliente anterior por cima deste.
    const meuPedido = ++pedidoDetalhe;
    clienteAbertoId = Number(clienteId);
    detalheEl().innerHTML = '<div class="cartao fraco">Carregando cadastro…</div>';
    try {
      const cliente = await api.pedir("GET", `/clientes/${clienteId}`);
      if (meuPedido !== pedidoDetalhe) return;
      detalheEl().innerHTML = montarDetalhe(cliente);
      plugarAcoesDoDetalhe(cliente);
    } catch (erro) {
      if (meuPedido !== pedidoDetalhe) return;
      detalheEl().innerHTML = `<div class="cartao"><p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p></div>`;
    }
  }

  function montarDetalhe(c) {
    let situacao = '<span class="selo selo--em-dia">Nenhuma parcela em aberto</span>';
    if (c.saldo_atrasado_centavos > 0) {
      situacao = `<span class="selo selo--devendo">Atrasado ${reais(c.saldo_atrasado_centavos)}</span>
        <span class="fraco">de ${reais(c.saldo_devedor_centavos)} a receber</span>`;
    } else if (c.deve_parcela) {
      situacao = `<span class="selo selo--pendente">A receber ${reais(c.saldo_devedor_centavos)} · em dia</span>`;
    }

    return `
      <div class="cartao">
        <div class="modal-topo">
          <h3>${escapar(c.nome)}</h3>
          <div class="acoes-linha">
            <button class="botao botao--fantasma" id="botao-editar-cliente" type="button">Editar</button>
            <button class="botao botao--fantasma" id="botao-fechar-cliente" type="button">Fechar</button>
          </div>
        </div>
        <dl class="linhas-dados">
          <div><dt>CPF</dt><dd>${formatarCpf(c.cpf)}</dd></div>
          <div><dt>Telefone</dt><dd>${escapar(formatarTelefone(c.telefone))}</dd></div>
          <div><dt>Situação</dt><dd>${situacao}</dd></div>
          ${c.casado == null ? "" : `<div><dt>Estado civil</dt><dd>${c.casado ? "Casado(a)" : "Solteiro(a)"}</dd></div>`}
          ${c.casado && c.conjuge_nome ? `<div><dt>Cônjuge</dt><dd>${escapar(c.conjuge_nome)}</dd></div>` : ""}
          ${c.casado && c.conjuge_telefone ? `<div><dt>Telefone do cônjuge</dt><dd>${escapar(formatarTelefone(c.conjuge_telefone))}</dd></div>` : ""}
        </dl>
        ${c.observacao ? `
          <h3 class="secao-seguinte">Observação</h3>
          <p class="texto-observacao">${escapar(c.observacao)}</p>` : ""}

        <div class="abas-filtro secao-seguinte" id="abas-historico">
          <button class="aba-filtro" data-aba="comprou" type="button">Comprou (${c.comprou.length})</button>
          <button class="aba-filtro" data-aba="vendeu" type="button">Vendeu (${c.vendeu.length})</button>
        </div>
        <div id="conteudo-historico">${montarHistorico(c)}</div>
      </div>
    `;
  }

  function montarHistorico(c) {
    if (abaHistorico === "vendeu") {
      if (!c.vendeu.length) {
        return '<p class="fraco">Este cliente nunca vendeu moto pra loja.</p>';
      }
      return `<ul class="lista-historico">${c.vendeu.map((compra) => `
        <li class="item-historico">
          <h4>${escapar(compra.moto.marca)} ${escapar(compra.moto.modelo)} ${compra.moto.ano} ${compra.moto.placa ? `— ${escapar(compra.moto.placa)}` : ""}</h4>
          <p class="fraco">
            Vendeu pra loja${compra.data_compra ? ` em ${dataBr(compra.data_compra)}` : ""}
            ${compra.valor_compra_centavos != null ? ` · a loja pagou ${reais(compra.valor_compra_centavos)}` : " · valor ainda não lançado"}
          </p>
        </li>
      `).join("")}</ul>`;
    }

    if (!c.comprou.length) {
      return '<p class="fraco">Este cliente ainda não comprou moto da loja.</p>';
    }
    return `<ul class="lista-historico">${c.comprou.map((venda) => `
      <li class="item-historico">
        <h4>${escapar(venda.moto.marca)} ${escapar(venda.moto.modelo)} ${venda.moto.ano} ${venda.moto.placa ? `— ${escapar(venda.moto.placa)}` : ""}</h4>
        <p class="fraco">
          Comprou em ${dataBr(venda.data_venda)} · ${rotuloFormaPagamento(venda.forma_pagamento)}
          · pagou ${reais(venda.preco_venda_centavos)}
        </p>
        ${venda.parcelado ? montarParcelas(venda) : ""}
      </li>
    `).join("")}</ul>`;
  }

  function montarParcelas(venda) {
    const resumo = venda.saldo_devedor_centavos > 0
      ? `<strong class="${classeDoSaldo(venda.parcelas)}">${venda.qtd_parcelas_pagas} de ${venda.qtd_parcelas} pagas · falta ${reais(venda.saldo_devedor_centavos)}</strong>`
      : `<strong class="lucro-positivo">${venda.qtd_parcelas} de ${venda.qtd_parcelas} pagas · quitado</strong>`;

    return `
      <p>${resumo}</p>
      <ul class="sub-parcelas">
        ${venda.parcelas.map((p) => `
          <li>
            <span>Parcela ${p.numero} · vence ${dataBr(p.vencimento)}</span>
            <span class="${classeStatusParcela(p.status)}">
              ${reais(p.valor_centavos)} · ${rotuloStatusParcela(p.status)}
            </span>
          </li>
        `).join("")}
      </ul>
    `;
  }

  function rotuloFormaPagamento(forma) {
    return {
      A_VISTA: "À vista",
      PARCELADO: "Parcelado (loja)",
      FINANCIADO: "Financiado",
      CONSORCIO: "Consórcio",
    }[forma] || forma;
  }

  function plugarAcoesDoDetalhe(cliente) {
    raiz.querySelectorAll("#abas-historico .aba-filtro").forEach((botao) => {
      botao.dataset.ativa = botao.dataset.aba === abaHistorico ? "1" : "0";
      botao.addEventListener("click", () => {
        abaHistorico = botao.dataset.aba;
        raiz.querySelector("#conteudo-historico").innerHTML = montarHistorico(cliente);
        raiz.querySelectorAll("#abas-historico .aba-filtro").forEach((outro) => {
          outro.dataset.ativa = outro.dataset.aba === abaHistorico ? "1" : "0";
        });
      });
    });

    raiz.querySelector("#botao-editar-cliente")?.addEventListener("click", () => {
      abrirModalEditar(cliente);
    });
    raiz.querySelector("#botao-fechar-cliente")?.addEventListener("click", () => {
      clienteAbertoId = null;
      detalheEl().innerHTML = "";
    });
  }

  // -------------------------------------------------------------- modais

  function camposDoFormulario(cliente) {
    return `
      <div class="grade-2">
        <label class="campo">Nome<input name="nome" value="${escapar(cliente?.nome || "")}" required /></label>
        <label class="campo">Telefone<input name="telefone" value="${escapar(cliente?.telefone || "")}" placeholder="(11) 99999-0000" /></label>
      </div>
      ${htmlCamposConjuge(cliente)}
      ${htmlCampoObservacao(cliente?.observacao, "Ex.: prefere WhatsApp; cliente antigo da loja.")}
    `;
  }

  function abrirModalNovo() {
    const modal = abrirModal(`
      <div class="modal-topo"><h3>Cadastrar cliente</h3></div>
      <form id="form-novo-cliente" novalidate>
        ${camposDoFormulario(null)}
        <label class="campo">CPF<input name="cpf" placeholder="000.000.000-00" maxlength="14" required /></label>
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-novo-cliente">Cancelar</button>
          <button type="submit" class="botao">Cadastrar</button>
        </div>
      </form>
    `);

    ligarConjuge(modal);
    modal.querySelector("#cancelar-novo-cliente").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#form-novo-cliente").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const form = evento.target;
      const dados = new FormData(form);
      const nome = dados.get("nome");
      const documento = dados.get("cpf");
      const fone = dados.get("telefone");
      const conjuge = lerConjuge(dados);
      const observacao = lerObservacao(dados);

      const valido = v.validarFormulario(form, [
        ["nome", v.textoPreenchido(nome), "Informe o nome"],
        ["cpf", v.textoPreenchido(documento), "CPF é obrigatório"],
        ["cpf", !v.textoPreenchido(documento) || v.cpfValido(documento), "CPF inválido — confira os números"],
        ["telefone", v.telefoneValido(fone), "Telefone precisa ter 10 ou 11 dígitos, com DDD"],
        ...regrasConjuge(conjuge),
        ...regrasObservacao(observacao),
      ]);
      if (!valido) return;

      try {
        const cliente = await api.enviar("POST", "/clientes", {
          nome,
          cpf: documento,
          telefone: fone || null,
          ...corpoConjuge(conjuge),
          observacao,
        }, { rotulo: `Cliente ${nome}` });
        fecharModal(modal);
        avisar("Cliente cadastrado");
        await carregarLista();
        await abrirDetalhe(cliente.id);
      } catch (erro) {
        if (guardadoNaFila(erro, `Cliente ${nome}`)) {
          fecharModal(modal);
          return;
        }
        v.mostrarErroDeApi(form, erro, { porPalavra: [["cpf", "cpf"], ["telefone", "telefone"]] });
      }
    });
  }

  function abrirModalEditar(cliente) {
    const modal = abrirModal(`
      <div class="modal-topo"><h3>Editar cliente</h3></div>
      <form id="form-editar-cliente" novalidate>
        ${camposDoFormulario(cliente)}
        <p class="fraco">O CPF (${formatarCpf(cliente.cpf)}) não muda — é ele que identifica a pessoa no histórico.</p>
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-editar-cliente">Cancelar</button>
          <button type="submit" class="botao">Salvar</button>
        </div>
      </form>
    `);

    ligarConjuge(modal);
    modal.querySelector("#cancelar-editar-cliente").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#form-editar-cliente").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const form = evento.target;
      const dados = new FormData(form);
      const nome = dados.get("nome");
      const fone = dados.get("telefone");

      const conjuge = lerConjuge(dados);
      const observacao = lerObservacao(dados);

      const valido = v.validarFormulario(form, [
        ["nome", v.textoPreenchido(nome), "Informe o nome"],
        ["telefone", v.telefoneValido(fone), "Telefone precisa ter 10 ou 11 dígitos, com DDD"],
        ...regrasConjuge(conjuge),
        ...regrasObservacao(observacao),
      ]);
      if (!valido) return;

      try {
        await api.enviar("PATCH", `/clientes/${cliente.id}`, {
          nome, telefone: fone || null, ...corpoConjuge(conjuge), observacao,
        }, { rotulo: `Edição do cliente ${nome}` });
        fecharModal(modal);
        avisar("Cliente atualizado");
        await carregarLista();
        await abrirDetalhe(cliente.id);
      } catch (erro) {
        if (guardadoNaFila(erro, `Edição do cliente ${nome}`)) {
          fecharModal(modal);
          return;
        }
        v.mostrarErroDeApi(form, erro, { porPalavra: [["telefone", "telefone"]] });
      }
    });
  }

  // ------------------------------------------------------------- ligações

  raiz.querySelector("#botao-novo-cliente").addEventListener("click", abrirModalNovo);
  raiz.querySelector("#botao-buscar-cliente").addEventListener("click", async () => {
    buscaAtual = raiz.querySelector("#busca-cliente").value.trim();
    await carregarLista();
  });
  raiz.querySelector("#busca-cliente").addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") raiz.querySelector("#botao-buscar-cliente").click();
  });
  raiz.querySelector("#filtro-clientes").addEventListener("click", (evento) => {
    const botao = evento.target.closest(".aba-filtro");
    if (!botao) return;
    filtroLista = botao.dataset.filtro;
    pintarFiltro();
    desenharTabela();
  });
  corpoTabela().addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-id]");
    if (linha) abrirDetalhe(linha.dataset.id);
  });

  pintarFiltro();
  await carregarLista();
  if (clienteAbertoId != null) await abrirDetalhe(clienteAbertoId);
}
