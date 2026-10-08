/**
 * Tela FINANCEIRO: o mês em números e, embaixo, o que aconteceu em cada dia.
 *
 * Todos os números saem de uma lista só de movimentos, montada no servidor
 * (`servicos/financeiro.py`): o total do mês é sempre a soma dos dias. E o
 * dia é o de Brasília — uma venda das 22h entra no caixa daquele dia, não do
 * seguinte.
 */

import * as api from "../../comum/api.js";
import { reais, dataBr, contar, hojeIso } from "../../comum/formato.js";
import { abrirModal, fecharModal, avisar, escapar, mensagemDeErro } from "../ui.js";
import * as v from "../validacao.js";

const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

const TIPOS = {
  VENDA: { rotulo: "Venda", classe: "selo--venda" },
  PARCELA: { rotulo: "Parcela", classe: "selo--parcela" },
  COMPRA: { rotulo: "Compra", classe: "selo--compra" },
  GASTO: { rotulo: "Gasto", classe: "selo--gasto" },
  ENTRADA_CAIXA: { rotulo: "Entrada", classe: "selo--parcela" },
  SAIDA_CAIXA: { rotulo: "Saída", classe: "selo--gasto" },
};

// Sobrevivem a um `renderFinanceiro` novo: o `app.js` refaz a tela a cada
// evento do WebSocket, e sem isto o mês escolhido voltava sozinho pro atual.
let anoVisto = null;
let mesVisto = null;
let diaAberto = null;

function mesDeHoje() {
  const d = new Date();
  return { ano: d.getFullYear(), mes: d.getMonth() + 1 };
}

function ehMesAtualOuDepois(ano, mes) {
  const agora = mesDeHoje();
  return ano > agora.ano || (ano === agora.ano && mes >= agora.mes);
}

function diaDaSemana(iso) {
  // Meio-dia local: "AAAA-MM-DD" sozinho seria lido como meia-noite UTC — no
  // Brasil ainda o dia anterior, e a semana sairia com um dia de atraso.
  return new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
}

function resumoDoDia(movimentos) {
  const quantos = (tipo) => movimentos.filter((m) => m.tipo === tipo).length;
  return [
    quantos("VENDA") && contar(quantos("VENDA"), "venda", "vendas"),
    quantos("PARCELA") && contar(quantos("PARCELA"), "parcela recebida", "parcelas recebidas"),
    quantos("COMPRA") && contar(quantos("COMPRA"), "compra de moto", "compras de moto"),
    quantos("GASTO") && contar(quantos("GASTO"), "gasto", "gastos"),
  ].filter(Boolean).join(" · ");
}

function classeDoValor(centavos) {
  if (centavos > 0) return "lucro-positivo";
  if (centavos < 0) return "lucro-negativo";
  return "";
}

export async function renderFinanceiro(raiz) {
  if (anoVisto === null) ({ ano: anoVisto, mes: mesVisto } = mesDeHoje());

  raiz.innerHTML = `
    <div class="topo-financeiro">
      <h2>Financeiro</h2>
      <div class="seletor-mes">
        <button class="botao botao--fantasma botao--pequeno" id="mes-anterior" type="button" aria-label="Mês anterior">‹</button>
        <strong id="nome-mes"></strong>
        <button class="botao botao--fantasma botao--pequeno" id="mes-seguinte" type="button" aria-label="Próximo mês">›</button>
      </div>
    </div>
    <div class="resumo-cartoes" id="cartoes-financeiro"></div>

    <div class="cartao" id="caixa-hoje">
      <p class="fraco">Carregando o caixa…</p>
    </div>

    <div class="cartao">
      <h3>Dia a dia</h3>
      <p class="fraco">Abra um dia pra ver o que aconteceu nele.</p>
      <div id="dias-financeiro"><p class="fraco">Carregando…</p></div>
    </div>
  `;

  // Procurados na hora do uso — ver o mesmo comentário em `telas/clientes.js`.
  const cartoesEl = () => raiz.querySelector("#cartoes-financeiro");
  const diasEl = () => raiz.querySelector("#dias-financeiro");
  const caixaEl = () => raiz.querySelector("#caixa-hoje");
  let dados = null;
  let caixa = null;

  function pintarSeletor() {
    raiz.querySelector("#nome-mes").textContent = `${MESES[mesVisto - 1]} de ${anoVisto}`;
    raiz.querySelector("#mes-seguinte").disabled = ehMesAtualOuDepois(anoVisto, mesVisto);
  }

  function desenharCartoes(f) {
    const semCusto = f.qtd_vendas_sem_custo
      ? `<br /><span class="aviso-cartao">${contar(f.qtd_vendas_sem_custo, "venda sem valor de compra lançado ficou", "vendas sem valor de compra lançado ficaram")} de fora</span>`
      : "";
    cartoesEl().innerHTML = `
      <div class="cartao">
        <p class="resumo-rotulo">Entrou no mês</p>
        <p class="resumo-valor entrada">${reais(f.entrou_centavos)}</p>
        <p class="resumo-detalhe">${contar(f.qtd_vendas, "venda", "vendas")} · ${contar(f.qtd_parcelas_recebidas, "parcela recebida", "parcelas recebidas")}</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">Gasto com compra de motos</p>
        <p class="resumo-valor saida">${reais(f.gasto_compra_motos_centavos)}</p>
        <p class="resumo-detalhe">${contar(f.qtd_motos_compradas, "moto comprada", "motos compradas")}</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">Gasto com arrumação</p>
        <p class="resumo-valor saida">${reais(f.gasto_arrumacao_centavos)}</p>
        <p class="resumo-detalhe">mecânica, peças, revisão</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">Lucro do mês</p>
        <p class="resumo-valor ${classeDoValor(f.lucro_centavos)}">${reais(f.lucro_centavos)}</p>
        <p class="resumo-detalhe">o que entrou, menos compras e arrumação</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">Lucro nas motos vendidas</p>
        <p class="resumo-valor ${classeDoValor(f.lucro_vendas_centavos)}">${reais(f.lucro_vendas_centavos)}</p>
        <p class="resumo-detalhe">venda − compra − gastos de cada moto${semCusto}</p>
      </div>
      <div class="cartao">
        <p class="resumo-rotulo">A receber de parcelas</p>
        <p class="resumo-valor texto-a-vencer">${reais(f.a_receber_centavos)}</p>
        <p class="resumo-detalhe">tudo que está em aberto hoje</p>
      </div>
    `;
  }

  function linhaDetalhe(dia) {
    return `
      <tr class="detalhe-dia"><td colspan="5">
        <ul class="lista-movimentos">
          ${dia.movimentos.map((m) => `
            <li>
              <span class="selo ${TIPOS[m.tipo].classe}">${TIPOS[m.tipo].rotulo}</span>
              <span class="descricao">${escapar(m.descricao)}</span>
              ${m.entrada_centavos ? `<strong class="entrada">+ ${reais(m.entrada_centavos)}</strong>` : ""}
              ${m.saida_centavos ? `<strong class="saida">− ${reais(m.saida_centavos)}</strong>` : ""}
              ${!m.entrada_centavos && !m.saida_centavos ? `<span class="fraco">${reais(0)}</span>` : ""}
            </li>
          `).join("")}
        </ul>
      </td></tr>
    `;
  }

  function desenharDias(f) {
    if (!f.dias.length) {
      diasEl().innerHTML = '<p class="fraco">Nenhuma movimentação neste mês.</p>';
      return;
    }
    diasEl().innerHTML = `
      <div class="tabela-wrap">
        <table class="tabela">
          <thead>
            <tr><th>Dia</th><th>Entrou</th><th>Saiu</th><th>Saldo do dia</th><th>O que aconteceu</th></tr>
          </thead>
          <tbody>
            ${f.dias.map((d) => `
              <tr data-dia="${d.dia}" class="${d.dia === diaAberto ? "linha-dia-aberta" : ""}">
                <td><strong>${dataBr(d.dia)}</strong> <span class="fraco">${diaDaSemana(d.dia)}</span></td>
                <td data-rotulo="Entrou" class="${d.entrou_centavos ? "entrada" : "fraco"}">${d.entrou_centavos ? reais(d.entrou_centavos) : "—"}</td>
                <td data-rotulo="Saiu" class="${d.saiu_centavos ? "saida" : "fraco"}">${d.saiu_centavos ? reais(d.saiu_centavos) : "—"}</td>
                <td data-rotulo="Saldo do dia" class="${classeDoValor(d.saldo_centavos)}"><strong>${reais(d.saldo_centavos)}</strong></td>
                <td data-rotulo="O que aconteceu">${escapar(resumoDoDia(d.movimentos))}</td>
              </tr>
              ${d.dia === diaAberto ? linhaDetalhe(d) : ""}
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  // ----------------------------------------------------------- caixa

  /**
   * O caixa de hoje — a pergunta do fim da tarde: quanto tem que estar na
   * gaveta agora.
   *
   * Começa do zero toda manhã de propósito. Não é saldo que se acumula: é o
   * movimento do dia, pra conferir com o dinheiro que está na mão. O
   * histórico fica a um toque, no "ver outros dias".
   */
  async function carregarCaixa() {
    try {
      caixa = await api.pedir("GET", "/financeiro/caixa/hoje");
      desenharCaixa();
    } catch (erro) {
      if (caixaEl()) {
        caixaEl().innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
      }
    }
  }

  function desenharCaixa() {
    const onde = caixaEl();
    if (!onde || !caixa) return;
    const linhas = caixa.movimentos || [];
    onde.innerHTML = `
      <div class="modal-topo">
        <h3>Caixa de hoje <span class="fraco">· ${dataBr(caixa.dia)}</span></h3>
        <div class="acoes-linha">
          <button class="botao botao--pequeno" id="caixa-entrada" type="button">Entrada</button>
          <button class="botao botao--pequeno botao--fantasma" id="caixa-saida" type="button">Saída</button>
        </div>
      </div>

      <div class="caixa-totais">
        <div><p class="resumo-rotulo">Entrou</p><p class="valor-positivo">${reais(caixa.entrou_centavos)}</p></div>
        <div><p class="resumo-rotulo">Saiu</p><p class="valor-negativo">${reais(caixa.saiu_centavos)}</p></div>
        <div><p class="resumo-rotulo">Deve ter na gaveta</p>
          <p class="valor-forte ${classeDoValor(caixa.saldo_centavos)}">${reais(caixa.saldo_centavos)}</p></div>
      </div>

      ${linhas.length ? `
        <ul class="lista-caixa">
          ${linhas.map((m) => `
            <li>
              <span class="selo ${TIPOS[m.tipo]?.classe || ""}">${TIPOS[m.tipo]?.rotulo || m.tipo}</span>
              <span class="caixa-descricao">${escapar(m.descricao)}</span>
              <span class="${m.entrada_centavos ? "valor-positivo" : "valor-negativo"}">
                ${m.entrada_centavos ? "+" : "−"} ${reais(m.entrada_centavos || m.saida_centavos)}
              </span>
              ${m.movimento_id
                ? `<button class="link" data-estornar="${m.movimento_id}" type="button">estornar</button>`
                : '<span class="fraco caixa-origem">da venda</span>'}
            </li>`).join("")}
        </ul>`
        : '<p class="fraco">Nada movimentou o caixa hoje ainda.</p>'}

      <div class="acoes-linha secao-seguinte">
        <button class="botao botao--fantasma botao--pequeno" id="caixa-historico" type="button">Ver outros dias</button>
        <button class="botao botao--fantasma botao--pequeno" id="caixa-relatorio" type="button">Relatório de caixa</button>
      </div>`;
  }

  // ------------------------------------------------- lançar e estornar

  function abrirLancamento(tipo) {
    const entrada = tipo === "ENTRADA";
    const janela = abrirModal(`
      <div class="modal-topo"><h3>${entrada ? "Entrada" : "Saída"} de caixa</h3></div>
      <form id="form-caixa" novalidate>
        <label class="campo">Valor (R$)
          <input name="valor" type="number" step="0.01" min="0.01" inputmode="decimal" />
        </label>
        <label class="campo">${entrada ? "De onde veio" : "Do que foi"}
          <input name="descricao" maxlength="200" autocomplete="off"
            placeholder="${entrada ? "Ex.: serviço avulso, troco inicial" : "Ex.: aluguel, almoço da equipe"}" />
        </label>
        <label class="campo">Dia
          <input name="dia" type="date" max="${hojeIso()}" value="${hojeIso()}" />
        </label>
        <p class="fraco">Use o dia em que o dinheiro andou, não o de hoje — é nesse
          dia que ele entra no caixa.</p>
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-caixa">Cancelar</button>
          <button type="submit" class="botao">Lançar</button>
        </div>
      </form>`);

    const form = janela.querySelector("#form-caixa");
    janela.querySelector("#cancelar-caixa").addEventListener("click", () => fecharModal(janela));
    form.elements.valor.focus();

    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const valor = form.elements.valor.value;
      const descricao = form.elements.descricao.value;
      const valido = v.validarFormulario(form, [
        ["valor", v.numeroPositivo(valor), "Informe um valor maior que zero"],
        ["descricao", v.textoPreenchido(descricao),
          `Diga ${entrada ? "de onde veio" : "do que foi"} — sem isso ninguém explica no fim do mês`],
      ]);
      if (!valido) return;
      try {
        await api.enviar("POST", "/financeiro/caixa", {
          tipo,
          valor_centavos: Math.round(Number(valor) * 100),
          descricao: descricao.trim(),
          dia: form.elements.dia.value || null,
        }, { rotulo: `${entrada ? "Entrada" : "Saída"} de ${reais(Math.round(Number(valor) * 100))}` });
        fecharModal(janela);
        avisar(`${entrada ? "Entrada" : "Saída"} lançada`);
        await carregar();
      } catch (erro) {
        v.mostrarErroDeApi(form, erro, { porPalavra: [["valor", "valor"], ["descri", "descricao"], ["dia", "dia"]] });
      }
    });
  }

  async function estornarLancamento(id) {
    const motivo = window.prompt(
      "Estornar este lançamento?\n\nEle sai da conta do caixa e fica no histórico "
      + "marcado como estornado — nada é apagado.\n\nMotivo (opcional):");
    if (motivo === null) return;
    try {
      await api.enviar("POST", `/financeiro/caixa/${id}/estornar`, { motivo: motivo || null },
        { rotulo: "Estorno de caixa" });
      avisar("Lançamento estornado");
      await carregar();
    } catch (erro) {
      avisar(mensagemDeErro(erro), "erro");
    }
  }

  // --------------------------------------------- histórico e relatório

  /** O caixa de um dia qualquer — é o "ver outros dias". */
  async function abrirDiaDoCaixa(dia) {
    const janela = abrirModal('<div class="cartao fraco">Abrindo o caixa…</div>');
    async function pintar(alvo) {
      const d = await api.pedir("GET", `/financeiro/caixa/dia?dia=${alvo}`);
      janela.innerHTML = `
        <div class="modal-topo">
          <h3>Caixa de ${dataBr(d.dia)}</h3>
          <button class="botao botao--fantasma" id="fechar-dia-caixa" type="button">Fechar</button>
        </div>
        <label class="campo">Ver outro dia
          <input id="dia-do-caixa" type="date" max="${hojeIso()}" value="${d.dia}" />
        </label>
        <div class="caixa-totais">
          <div><p class="resumo-rotulo">Entrou</p><p class="valor-positivo">${reais(d.entrou_centavos)}</p></div>
          <div><p class="resumo-rotulo">Saiu</p><p class="valor-negativo">${reais(d.saiu_centavos)}</p></div>
          <div><p class="resumo-rotulo">Saldo do dia</p>
            <p class="valor-forte ${classeDoValor(d.saldo_centavos)}">${reais(d.saldo_centavos)}</p></div>
        </div>
        ${d.movimentos.length ? `
          <ul class="lista-caixa">
            ${d.movimentos.map((m) => `
              <li>
                <span class="selo ${TIPOS[m.tipo]?.classe || ""}">${TIPOS[m.tipo]?.rotulo || m.tipo}</span>
                <span class="caixa-descricao">${escapar(m.descricao)}</span>
                <span class="${m.entrada_centavos ? "valor-positivo" : "valor-negativo"}">
                  ${m.entrada_centavos ? "+" : "−"} ${reais(m.entrada_centavos || m.saida_centavos)}
                </span>
              </li>`).join("")}
          </ul>`
          : '<p class="fraco">Nada movimentou o caixa neste dia.</p>'}`;
      janela.querySelector("#fechar-dia-caixa").addEventListener("click", () => fecharModal(janela));
      janela.querySelector("#dia-do-caixa").addEventListener("change", (e) => {
        if (e.target.value) pintar(e.target.value);
      });
    }
    try {
      await pintar(dia);
    } catch (erro) {
      janela.innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
    }
  }

  /**
   * Relatório de caixa do mês que está na tela: mostra na hora e baixa.
   *
   * Sai do `dados` que a tela já tem — a mesma lista de movimentos que soma os
   * cartões lá em cima. Um relatório que busca os números por outro caminho
   * acaba discordando da tela, e aí não serve pra levar ao contador.
   */
  function abrirRelatorio() {
    if (!dados) return;
    const periodo = `${MESES[mesVisto - 1]} de ${anoVisto}`;
    const linhas = [];
    for (const dia of [...dados.dias].reverse()) {
      for (const m of dia.movimentos) {
        linhas.push({ dia: dia.dia, ...m });
      }
    }

    const janela = abrirModal(`
      <div class="modal-topo">
        <h3>Relatório de caixa <span class="fraco">· ${escapar(periodo)}</span></h3>
        <div class="acoes-linha">
          <button class="botao botao--pequeno" id="baixar-relatorio" type="button">Baixar</button>
          <button class="botao botao--fantasma" id="fechar-relatorio" type="button">Fechar</button>
        </div>
      </div>

      <div class="caixa-totais">
        <div><p class="resumo-rotulo">Entrou</p><p class="valor-positivo">${reais(dados.entrou_centavos)}</p></div>
        <div><p class="resumo-rotulo">Saiu</p><p class="valor-negativo">${reais(
          dados.gasto_compra_motos_centavos + dados.gasto_arrumacao_centavos + (dados.saidas_caixa_centavos || 0))}</p></div>
        <div><p class="resumo-rotulo">Sobrou</p>
          <p class="valor-forte ${classeDoValor(dados.lucro_centavos)}">${reais(dados.lucro_centavos)}</p></div>
      </div>

      ${linhas.length ? `
        <div class="tabela-wrap">
          <table class="tabela">
            <thead><tr><th>Dia</th><th>O que foi</th><th>Descrição</th><th>Entrou</th><th>Saiu</th></tr></thead>
            <tbody>${linhas.map((l) => `
              <tr>
                <td>${dataBr(l.dia)}</td>
                <td data-rotulo="O que foi">${TIPOS[l.tipo]?.rotulo || l.tipo}</td>
                <td data-rotulo="Descrição">${escapar(l.descricao)}</td>
                <td data-rotulo="Entrou" class="valor-positivo">${l.entrada_centavos ? reais(l.entrada_centavos) : ""}</td>
                <td data-rotulo="Saiu" class="valor-negativo">${l.saida_centavos ? reais(l.saida_centavos) : ""}</td>
              </tr>`).join("")}</tbody>
          </table>
        </div>`
        : '<p class="fraco">Nenhuma movimentação neste mês.</p>'}`);

    janela.querySelector("#fechar-relatorio").addEventListener("click", () => fecharModal(janela));
    janela.querySelector("#baixar-relatorio").addEventListener("click", () => baixarRelatorio(periodo, linhas));
  }

  /**
   * Baixa o relatório como CSV — que abre no Excel e o contador aceita.
   *
   * Ponto e vírgula como separador e vírgula no decimal: é o que o Excel em
   * português entende sem perguntar nada. Com vírgula de separador ele joga
   * a planilha inteira numa coluna só.
   */
  function baixarRelatorio(periodo, linhas) {
    const limpar = (texto) => `"${String(texto ?? "").replace(/"/g, '""')}"`;
    const dinheiro = (centavos) => (centavos ? (centavos / 100).toFixed(2).replace(".", ",") : "");
    const csv = [
      ["Dia", "O que foi", "Descrição", "Entrou", "Saiu"].join(";"),
      ...linhas.map((l) => [
        limpar(dataBr(l.dia)),
        limpar(TIPOS[l.tipo]?.rotulo || l.tipo),
        limpar(l.descricao),
        dinheiro(l.entrada_centavos),
        dinheiro(l.saida_centavos),
      ].join(";")),
    ].join("\r\n");

    // `\ufeff` (BOM) na frente: sem ele o Excel lê o arquivo como se não
    // fosse UTF-8 e os acentos viram caracteres estranhos.
    const arquivo = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(arquivo);
    const link = document.createElement("a");
    link.href = url;
    link.download = `caixa-${anoVisto}-${String(mesVisto).padStart(2, "0")}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    avisar("Relatório baixado");
  }

  async function carregar() {
    pintarSeletor();
    try {
      dados = await api.pedir("GET", `/financeiro/mes?ano=${anoVisto}&mes=${mesVisto}`);
      desenharCartoes(dados);
      desenharDias(dados);
    } catch (erro) {
      diasEl().innerHTML = `<p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p>`;
    }
    await carregarCaixa();
  }

  function trocarMes(passo) {
    if (passo > 0 && ehMesAtualOuDepois(anoVisto, mesVisto)) return;
    let mes = mesVisto + passo;
    let ano = anoVisto;
    if (mes < 1) { mes = 12; ano -= 1; }
    if (mes > 12) { mes = 1; ano += 1; }
    anoVisto = ano;
    mesVisto = mes;
    diaAberto = null;
    carregar();
  }

  raiz.querySelector("#mes-anterior").addEventListener("click", () => trocarMes(-1));
  raiz.querySelector("#mes-seguinte").addEventListener("click", () => trocarMes(1));
  diasEl().addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-dia]");
    if (!linha || !dados) return;
    diaAberto = diaAberto === linha.dataset.dia ? null : linha.dataset.dia;
    desenharDias(dados);
  });

  // Um ouvinte só no cartão do caixa, ligado uma vez por desenho da tela: o
  // conteúdo dele é refeito a cada lançamento, e ligar botão por botão
  // empilharia ouvintes — um toque abriria dois modais.
  caixaEl().addEventListener("click", (evento) => {
    const alvo = evento.target;
    if (alvo.closest("#caixa-entrada")) return abrirLancamento("ENTRADA");
    if (alvo.closest("#caixa-saida")) return abrirLancamento("SAIDA");
    if (alvo.closest("#caixa-historico")) return abrirDiaDoCaixa(caixa?.dia || hojeIso());
    if (alvo.closest("#caixa-relatorio")) return abrirRelatorio();
    const estornar = alvo.closest("[data-estornar]");
    if (estornar) return estornarLancamento(estornar.dataset.estornar);
  });

  await carregar();
}
