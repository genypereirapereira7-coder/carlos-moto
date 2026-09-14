/**
 * Tela FINANCEIRO: o mês em números e, embaixo, o que aconteceu em cada dia.
 *
 * Todos os números saem de uma lista só de movimentos, montada no servidor
 * (`servicos/financeiro.py`): o total do mês é sempre a soma dos dias. E o
 * dia é o de Brasília — uma venda das 22h entra no caixa daquele dia, não do
 * seguinte.
 */

import * as api from "../../comum/api.js";
import { reais, dataBr, contar } from "../../comum/formato.js";
import { escapar, mensagemDeErro } from "../ui.js";

const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

const TIPOS = {
  VENDA: { rotulo: "Venda", classe: "selo--venda" },
  PARCELA: { rotulo: "Parcela", classe: "selo--parcela" },
  COMPRA: { rotulo: "Compra", classe: "selo--compra" },
  GASTO: { rotulo: "Gasto", classe: "selo--gasto" },
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
    <div class="cartao">
      <h3>Dia a dia</h3>
      <p class="fraco">Clique num dia pra ver o que aconteceu.</p>
      <div id="dias-financeiro"><p class="fraco">Carregando…</p></div>
    </div>
  `;

  // Procurados na hora do uso — ver o mesmo comentário em `telas/clientes.js`.
  const cartoesEl = () => raiz.querySelector("#cartoes-financeiro");
  const diasEl = () => raiz.querySelector("#dias-financeiro");
  let dados = null;

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
                <td class="${d.entrou_centavos ? "entrada" : "fraco"}">${d.entrou_centavos ? reais(d.entrou_centavos) : "—"}</td>
                <td class="${d.saiu_centavos ? "saida" : "fraco"}">${d.saiu_centavos ? reais(d.saiu_centavos) : "—"}</td>
                <td class="${classeDoValor(d.saldo_centavos)}"><strong>${reais(d.saldo_centavos)}</strong></td>
                <td>${escapar(resumoDoDia(d.movimentos))}</td>
              </tr>
              ${d.dia === diaAberto ? linhaDetalhe(d) : ""}
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
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

  await carregar();
}
