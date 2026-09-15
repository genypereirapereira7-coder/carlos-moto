/**
 * Tela PARCELAS: quem está devendo, e o botão de receber.
 *
 * Só aparece quem tem parcela em aberto — quitou tudo, sai da lista. Parcela
 * atrasada é vermelha; quem só tem parcela pra vencer fica em amarelo (ver
 * `classeStatusParcela` em `ui.js`). Clicar no cliente abre as parcelas dele
 * pra marcar o que foi pago, e o histórico do comprador logo abaixo.
 */

import * as api from "../../comum/api.js";
import {
  reais, dataBr, hojeIso, isoLocal, contar,
  cpf as formatarCpf, telefone as formatarTelefone,
} from "../../comum/formato.js";
import {
  abrirModal, fecharModal, avisar, mensagemDeErro, escapar, guardadoNaFila,
  rotuloFormaPagamento, rotuloStatusParcela, classeStatusParcela, classeDoSaldo,
} from "../ui.js";
import * as v from "../validacao.js";

// Sobrevivem a um `renderParcelas` novo: o `app.js` refaz a tela a cada
// evento do WebSocket — inclusive o eco de uma parcela recebida aqui — e sem
// isto o cliente aberto e o filtro escolhido sumiam no meio da cobrança.
let clienteAbertoId = null;

// Duas aberturas de detalhe podem estar no ar ao mesmo tempo: a que o usuário
// pediu e a que o re-render do WebSocket dispara pra reabrir o que estava
// aberto. Quem responde por último pinta a tela — e era assim que um cadastro
// novo acabava mostrando o cadastro anterior por cima dele. Só a última
// abertura pedida tem direito de escrever.
let pedidoDetalhe = 0;
let filtro = "todos";
let textoFiltro = "";

function daquiA(dias) {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return isoLocal(d);
}

function tituloMoto(m) {
  return `${escapar(m.marca)} ${escapar(m.modelo)} ${m.ano ?? ""}${m.placa ? ` — ${escapar(m.placa)}` : ""}`;
}

/**
 * A API devolve uma linha por parcela; a tela mostra uma por cliente.
 * Atrasados primeiro (quem está há mais tempo sem pagar no topo), depois os
 * em dia pelo próximo vencimento.
 */
function agruparPorCliente(parcelas) {
  const porCliente = new Map();
  for (const p of parcelas) {
    let g = porCliente.get(p.cliente_id);
    if (!g) {
      g = {
        id: p.cliente_id,
        nome: p.cliente_nome,
        cpf: p.cliente_cpf,
        telefone: p.cliente_telefone,
        motos: new Set(),
        emAberto: 0,
        qtd: 0,
        atrasado: 0,
        proximo: null,
      };
      porCliente.set(p.cliente_id, g);
    }
    g.motos.add(`${p.moto_marca} ${p.moto_modelo}${p.moto_placa ? ` (${p.moto_placa})` : ""}`);
    g.emAberto += p.valor_centavos;
    g.qtd += 1;
    if (p.status === "ATRASADA") g.atrasado += p.valor_centavos;
    if (!g.proximo || p.vencimento < g.proximo) g.proximo = p.vencimento;
  }
  return [...porCliente.values()].sort((a, b) => {
    if ((a.atrasado > 0) !== (b.atrasado > 0)) return a.atrasado > 0 ? -1 : 1;
    return a.proximo.localeCompare(b.proximo);
  });
}

export async function renderParcelas(raiz) {
  raiz.innerHTML = `
    <h2>Parcelas</h2>
    <div class="resumo-cartoes" id="resumo-parcelas"></div>
    <div id="detalhe-devedor"></div>
    <div class="cartao">
      <div class="modal-topo">
        <h3>Quem está devendo</h3>
        <div class="abas-filtro" id="filtro-parcelas">
          <button class="aba-filtro" data-filtro="todos" type="button">Todos</button>
          <button class="aba-filtro" data-filtro="atrasados" type="button">Atrasados</button>
          <button class="aba-filtro" data-filtro="em-dia" type="button">Em dia</button>
        </div>
      </div>
      <div class="barra-busca">
        <input id="filtro-devedor" placeholder="Filtrar por nome ou CPF" autocomplete="off" value="${escapar(textoFiltro)}" />
      </div>
      <div class="tabela-wrap">
        <table class="tabela">
          <thead>
            <tr><th>Cliente</th><th>Telefone</th><th>Moto</th><th>Em aberto</th><th>Próximo vencimento</th><th>Situação</th></tr>
          </thead>
          <tbody id="linhas-devedores"><tr><td colspan="6" class="fraco">Carregando…</td></tr></tbody>
        </table>
      </div>
    </div>
  `;

  // Procurados na hora do uso — ver o mesmo comentário em `telas/clientes.js`.
  const resumoEl = () => raiz.querySelector("#resumo-parcelas");
  const corpoTabela = () => raiz.querySelector("#linhas-devedores");
  const detalheEl = () => raiz.querySelector("#detalhe-devedor");
  let grupos = [];
  let clienteAtual = null;

  // ------------------------------------------------------------- resumo

  function desenharResumo(parcelas) {
    const hoje = hojeIso();
    const semana = daquiA(7);
    const soma = (lista) => lista.reduce((total, p) => total + p.valor_centavos, 0);
    const atrasadas = parcelas.filter((p) => p.status === "ATRASADA");
    const naSemana = parcelas.filter(
      (p) => p.status === "PENDENTE" && p.vencimento >= hoje && p.vencimento <= semana,
    );
    const clientes = new Set(parcelas.map((p) => p.cliente_id)).size;
    const clientesAtrasados = new Set(atrasadas.map((p) => p.cliente_id)).size;

    resumoEl().innerHTML = `
      <div class="cartao">
        <p class="resumo-rotulo">A receber</p>
        <p class="resumo-valor">${reais(soma(parcelas))}</p>
        <p class="resumo-detalhe">${contar(parcelas.length, "parcela", "parcelas")} · ${contar(clientes, "cliente", "clientes")}</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">Atrasado</p>
        <p class="resumo-valor ${atrasadas.length ? "texto-devendo" : ""}">${reais(soma(atrasadas))}</p>
        <p class="resumo-detalhe">${contar(clientesAtrasados, "cliente", "clientes")} com parcela vencida</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">Vence nos próximos 7 dias</p>
        <p class="resumo-valor ${naSemana.length ? "texto-a-vencer" : ""}">${reais(soma(naSemana))}</p>
        <p class="resumo-detalhe">${contar(naSemana.length, "parcela", "parcelas")}</p>
      </div>
    `;
  }

  // -------------------------------------------------------------- lista

  function pintarFiltro() {
    raiz.querySelectorAll("#filtro-parcelas .aba-filtro").forEach((botao) => {
      botao.dataset.ativa = botao.dataset.filtro === filtro ? "1" : "0";
    });
  }

  function visiveis() {
    let lista = grupos;
    if (filtro === "atrasados") lista = lista.filter((g) => g.atrasado > 0);
    if (filtro === "em-dia") lista = lista.filter((g) => g.atrasado === 0);
    const termo = textoFiltro.trim().toLowerCase();
    if (termo) {
      const digitos = termo.replace(/\D/g, "");
      lista = lista.filter(
        (g) => g.nome.toLowerCase().includes(termo) || (digitos.length >= 3 && g.cpf.includes(digitos)),
      );
    }
    return lista;
  }

  function desenharTabela() {
    if (!grupos.length) {
      corpoTabela().innerHTML =
        '<tr><td colspan="6" class="fraco">Ninguém devendo — nenhuma parcela em aberto.</td></tr>';
      return;
    }
    const lista = visiveis();
    if (!lista.length) {
      corpoTabela().innerHTML = '<tr><td colspan="6" class="fraco">Nenhum cliente nesse filtro.</td></tr>';
      return;
    }
    const hoje = hojeIso();
    corpoTabela().innerHTML = lista.map((g) => {
      const vencido = g.proximo < hoje;
      return `
        <tr data-id="${g.id}">
          <td>${escapar(g.nome)}<br /><span class="fraco">${formatarCpf(g.cpf)}</span></td>
          <td data-rotulo="Telefone">${escapar(formatarTelefone(g.telefone))}</td>
          <td data-rotulo="Moto">${[...g.motos].map(escapar).join("<br />")}</td>
          <td data-rotulo="Em aberto">${reais(g.emAberto)}<br /><span class="fraco">${contar(g.qtd, "parcela", "parcelas")}</span></td>
          <td data-rotulo="Próximo vencimento" class="${vencido ? "texto-devendo" : ""}">${vencido ? "venceu " : ""}${dataBr(g.proximo)}</td>
          <td data-rotulo="Situação">${g.atrasado > 0
            ? `<span class="selo selo--devendo">Atrasado ${reais(g.atrasado)}</span>`
            : '<span class="selo selo--pendente">Em dia</span>'}</td>
        </tr>
      `;
    }).join("");
  }

  async function carregarLista() {
    try {
      const parcelas = await api.pedir("GET", "/parcelas");
      grupos = agruparPorCliente(parcelas);
      desenharResumo(parcelas);
      desenharTabela();
    } catch (erro) {
      corpoTabela().innerHTML = `<tr><td colspan="6" class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</td></tr>`;
    }
  }

  // ------------------------------------------------------------ detalhe

  async function abrirDetalhe(clienteId) {
    // Antes do await — ver `abrirDetalhe` em `telas/clientes.js`.
    const meuPedido = ++pedidoDetalhe;
    clienteAbertoId = Number(clienteId);
    detalheEl().innerHTML = '<div class="cartao fraco">Carregando parcelas…</div>';
    try {
      const cliente = await api.pedir("GET", `/clientes/${clienteId}`);
      if (meuPedido !== pedidoDetalhe) return;
      clienteAtual = cliente;
      detalheEl().innerHTML = montarDetalhe(clienteAtual);
    } catch (erro) {
      if (meuPedido !== pedidoDetalhe) return;
      detalheEl().innerHTML = `<div class="cartao"><p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p></div>`;
    }
  }

  function montarDetalhe(c) {
    const abertas = c.comprou.filter((venda) => venda.parcelado && venda.saldo_devedor_centavos > 0);
    const digitosFone = (c.telefone || "").replace(/\D/g, "");

    let situacao = '<span class="selo selo--em-dia">Tudo pago</span>';
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
          <button class="botao botao--fantasma" id="fechar-devedor" type="button">Fechar</button>
        </div>
        <dl class="linhas-dados">
          <div><dt>CPF</dt><dd>${formatarCpf(c.cpf)}</dd></div>
          <div><dt>Telefone</dt><dd>${digitosFone
            ? `<a href="tel:+55${digitosFone}">${escapar(formatarTelefone(c.telefone))}</a>`
            : "—"}</dd></div>
          <div><dt>Situação</dt><dd>${situacao}</dd></div>
        </dl>

        <h3 class="secao-seguinte">Parcelas em aberto</h3>
        ${abertas.length
          ? `<ul class="lista-historico">${abertas.map(montarVendaAberta).join("")}</ul>`
          : '<p class="fraco">Tudo pago — este cliente não deve mais nada.</p>'}

        <h3 class="secao-seguinte">Histórico do comprador</h3>
        ${montarHistorico(c)}
      </div>
    `;
  }

  function montarVendaAberta(venda) {
    return `
      <li class="item-historico">
        <h4>${tituloMoto(venda.moto)}</h4>
        <p class="fraco">Comprou em ${dataBr(venda.data_venda)} · pagou ${reais(venda.preco_venda_centavos)}</p>
        <p><strong class="${classeDoSaldo(venda.parcelas)}">
          ${venda.qtd_parcelas_pagas} de ${venda.qtd_parcelas} pagas · falta ${reais(venda.saldo_devedor_centavos)}
        </strong></p>
        <ul class="sub-parcelas">
          ${venda.parcelas.map((p) => `
            <li>
              <span>Parcela ${p.numero} · vence ${dataBr(p.vencimento)}</span>
              <span class="linha-acao">
                <span class="${classeStatusParcela(p.status)}">
                  ${reais(p.valor_centavos)} · ${p.status === "PAGA" ? `paga em ${dataBr(p.pago_em)}` : rotuloStatusParcela(p.status)}
                </span>
                ${p.status === "PAGA"
                  ? `<button class="link" data-desfazer="${p.id}" type="button">desfazer</button>`
                  : `<button class="botao botao--pequeno" data-receber="${p.id}" type="button">Receber</button>`}
              </span>
            </li>
          `).join("")}
        </ul>
      </li>
    `;
  }

  function montarHistorico(c) {
    const comprou = c.comprou.map((venda) => {
      let fim = "";
      if (venda.parcelado) {
        fim = venda.saldo_devedor_centavos > 0 ? ` · falta ${reais(venda.saldo_devedor_centavos)}` : " · quitado";
      }
      return `<li>Comprou <strong>${tituloMoto(venda.moto)}</strong> em ${dataBr(venda.data_venda)}
        · ${rotuloFormaPagamento(venda.forma_pagamento)} · ${reais(venda.preco_venda_centavos)}${fim}</li>`;
    });
    const vendeu = c.vendeu.map((compra) => `<li>Vendeu pra loja <strong>${tituloMoto(compra.moto)}</strong>${
      compra.data_compra ? ` em ${dataBr(compra.data_compra)}` : ""}${
      compra.valor_compra_centavos != null ? ` · ${reais(compra.valor_compra_centavos)}` : ""}</li>`);
    const todas = [...comprou, ...vendeu];
    return todas.length ? `<ul class="lista-simples">${todas.join("")}</ul>` : '<p class="fraco">Sem histórico.</p>';
  }

  function acharParcela(parcelaId) {
    for (const venda of clienteAtual?.comprou || []) {
      const parcela = venda.parcelas.find((p) => p.id === parcelaId);
      if (parcela) return { venda, parcela };
    }
    return null;
  }

  // -------------------------------------------------------------- modais

  function abrirModalReceber(parcelaId) {
    const achado = acharParcela(parcelaId);
    if (!achado) return;
    const { venda, parcela } = achado;
    const hoje = hojeIso();
    const diaDaVenda = isoLocal(new Date(venda.data_venda));

    const modal = abrirModal(`
      <div class="modal-topo"><h3>Receber parcela ${parcela.numero} de ${venda.qtd_parcelas}</h3></div>
      <p>${escapar(clienteAtual.nome)} · ${tituloMoto(venda.moto)}</p>
      <p><strong>${reais(parcela.valor_centavos)}</strong> ·
        ${parcela.status === "ATRASADA"
          ? `<span class="texto-devendo">venceu ${dataBr(parcela.vencimento)}</span>`
          : `vence ${dataBr(parcela.vencimento)}`}</p>
      <form id="form-receber" novalidate>
        <label class="campo">Data do pagamento
          <input name="data_pagamento" type="date" min="${diaDaVenda}" max="${hoje}" value="${hoje}" />
        </label>
        <p class="fraco">Use o dia em que o cliente pagou — é nesse dia que o dinheiro entra no financeiro.</p>
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-receber">Cancelar</button>
          <button type="submit" class="botao">Confirmar recebimento</button>
        </div>
      </form>
    `);

    const form = modal.querySelector("#form-receber");
    modal.querySelector("#cancelar-receber").addEventListener("click", () => fecharModal(modal));
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const data = form.elements.data_pagamento.value;
      const valido = v.validarFormulario(form, [
        ["data_pagamento", v.textoPreenchido(data), "Informe a data do pagamento"],
        ["data_pagamento", !data || v.dataNaoFutura(data), "Data não pode ser no futuro"],
        ["data_pagamento", !data || data >= diaDaVenda, `Não pode ser antes da venda (${dataBr(diaDaVenda)})`],
      ]);
      if (!valido) return;

      try {
        // `data_pagamento` vai sempre preenchida, e é isso que deixa este
        // PATCH poder esperar na fila: o servidor usaria "agora" se ela
        // faltasse, e uma parcela recebida no sábado que só sobe na segunda
        // cairia no caixa da segunda.
        await api.enviar("PATCH", `/parcelas/${parcela.id}`, {
          pago: true, data_pagamento: data,
        }, { rotulo: `Parcela ${parcela.numero} de ${clienteAtual?.nome || "cliente"} recebida` });
        fecharModal(modal);
        avisar(`Parcela ${parcela.numero} recebida`);
        await atualizarTudo();
      } catch (erro) {
        if (guardadoNaFila(erro, `Parcela ${parcela.numero} recebida`)) {
          fecharModal(modal);
          await atualizarTudo();
          return;
        }
        v.mostrarErroDeApi(form, erro, { porPalavra: [["data", "data_pagamento"]] });
      }
    });
  }

  function abrirModalDesfazer(parcelaId) {
    const achado = acharParcela(parcelaId);
    if (!achado) return;
    const { parcela } = achado;

    const modal = abrirModal(`
      <div class="modal-topo"><h3>Desfazer o recebimento?</h3></div>
      <p>A parcela ${parcela.numero} (${reais(parcela.valor_centavos)}), marcada como paga em
        ${dataBr(parcela.pago_em)}, volta a contar como devida.</p>
      <div class="acoes-modal">
        <button type="button" class="botao botao--fantasma" id="cancelar-desfazer">Cancelar</button>
        <button type="button" class="botao botao--perigo" id="confirmar-desfazer">Desfazer recebimento</button>
      </div>
    `);

    modal.querySelector("#cancelar-desfazer").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#confirmar-desfazer").addEventListener("click", async () => {
      try {
        await api.enviar("PATCH", `/parcelas/${parcela.id}`, { pago: false }, {
          rotulo: `Desfazer o recebimento da parcela ${parcela.numero}`,
        });
        fecharModal(modal);
        avisar("Recebimento desfeito");
        await atualizarTudo();
      } catch (erro) {
        if (guardadoNaFila(erro, `Desfazer a parcela ${parcela.numero}`)) {
          fecharModal(modal);
          return;
        }
        avisar(mensagemDeErro(erro), "erro");
      }
    });
  }

  async function atualizarTudo() {
    await carregarLista();
    if (clienteAbertoId != null) await abrirDetalhe(clienteAbertoId);
  }

  // ------------------------------------------------------------ ligações

  raiz.querySelector("#filtro-parcelas").addEventListener("click", (evento) => {
    const botao = evento.target.closest(".aba-filtro");
    if (!botao) return;
    filtro = botao.dataset.filtro;
    pintarFiltro();
    desenharTabela();
  });
  raiz.querySelector("#filtro-devedor").addEventListener("input", (evento) => {
    textoFiltro = evento.target.value;
    desenharTabela();
  });
  corpoTabela().addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-id]");
    if (linha) abrirDetalhe(linha.dataset.id);
  });
  // Um ouvinte só, no contêiner, ligado uma vez por desenho da tela: o
  // conteúdo do detalhe é trocado a cada cliente aberto, e ligar botão por
  // botão a cada abertura empilharia ouvintes — um clique abriria dois modais.
  detalheEl().addEventListener("click", (evento) => {
    if (evento.target.closest("#fechar-devedor")) {
      clienteAbertoId = null;
      clienteAtual = null;
      detalheEl().innerHTML = "";
      return;
    }
    const receber = evento.target.closest("[data-receber]");
    if (receber) return abrirModalReceber(receber.dataset.receber);
    const desfazer = evento.target.closest("[data-desfazer]");
    if (desfazer) abrirModalDesfazer(desfazer.dataset.desfazer);
  });

  pintarFiltro();
  await carregarLista();
  if (clienteAbertoId != null) await abrirDetalhe(clienteAbertoId);
}
