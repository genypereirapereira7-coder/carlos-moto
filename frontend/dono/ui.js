/** Utilidades de tela compartilhadas pelas abas do painel do dono. */

import { ErroNaFila } from "../comum/api.js";

const elAviso = document.getElementById("aviso");
let timerAviso = null;

/** Toast de canto de tela — some sozinho. */
export function avisar(mensagem, tipo = "ok") {
  elAviso.textContent = mensagem;
  elAviso.dataset.tipo = tipo;
  elAviso.dataset.visivel = "1";
  clearTimeout(timerAviso);
  timerAviso = setTimeout(() => {
    elAviso.dataset.visivel = "0";
  }, 3200);
}

/**
 * Abre um modal a partir de um HTML de formulário e devolve o elemento raiz
 * do modal, pra quem chamou plugar os próprios listeners nos campos/botões.
 */
export function abrirModal(innerHTML) {
  const sobreposicao = document.createElement("div");
  sobreposicao.className = "sobreposicao";
  sobreposicao.innerHTML = `<div class="modal cartao">${innerHTML}</div>`;

  sobreposicao.addEventListener("click", (evento) => {
    if (evento.target === sobreposicao) sobreposicao.remove();
  });

  document.body.appendChild(sobreposicao);
  return sobreposicao.querySelector(".modal");
}

export function fecharModal(elementoDentroDoModal) {
  elementoDentroDoModal.closest(".sobreposicao")?.remove();
}

/** Mensagem de erro amigável pra `ErroApi`/`ErroRede`. */
export function mensagemDeErro(erro) {
  return erro?.message || "Não deu pra completar. Tente de novo.";
}

export function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

export function rotuloFormaPagamento(forma) {
  return {
    A_VISTA: "À vista",
    PARCELADO: "Parcelado (loja)",
    CHEQUE: "Cheque pré-datado",
    CARTAO: "Parcelado no cartão",
    FINANCIADO: "Financiado",
    CONSORCIO: "Consórcio",
  }[forma] || forma;
}

/** Situação de uma parcela, do jeito que o dono fala. */
export function rotuloStatusParcela(status) {
  return { PENDENTE: "a vencer", ATRASADA: "atrasada", PAGA: "paga" }[status] || status;
}

/**
 * Cor de uma parcela: vermelho só pra atrasada, amarelo pra que ainda vai
 * vencer. As duas são dinheiro a receber, mas quem está em dia não está
 * devendo do mesmo jeito que quem passou do prazo — pintar tudo de vermelho
 * escondia justamente quem precisa de cobrança.
 */
export function classeStatusParcela(status) {
  return { ATRASADA: "texto-devendo", PENDENTE: "texto-a-vencer" }[status] || "";
}

/** Cor do "falta receber" de uma venda: vermelho se alguma parcela já
 * atrasou, amarelo se só tem parcela por vencer. */
export function classeDoSaldo(parcelas) {
  if (parcelas.some((p) => p.status === "ATRASADA")) return "texto-devendo";
  if (parcelas.some((p) => p.status === "PENDENTE")) return "texto-a-vencer";
  return "";
}

/**
 * "Foi pra fila" não é erro de tela. O cadastro está guardado no computador e
 * sobe sozinho quando a internet voltar, então a tela fecha o modal e segue
 * como se tivesse dado certo — porque, pro dono, deu.
 *
 * Devolve `true` quando era isso, pra quem chamou saber que já foi tratado.
 */
export function guardadoNaFila(erro, oQue) {
  if (!(erro instanceof ErroNaFila)) return false;
  avisar(`${oQue} — guardado, sobe quando a internet voltar`, "ok");
  return true;
}
