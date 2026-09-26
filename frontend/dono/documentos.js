/**
 * RG e nascimento — os documentos que, junto do CPF, qualificam a pessoa no
 * contrato de compra e venda.
 *
 * Módulo próprio pelo mesmo motivo do cônjuge e do endereço: os campos
 * aparecem no cadastro do cliente, na edição e no cadastro rápido dentro da
 * venda, e a regra tem que ser a mesma nos três. Os dois são opcionais — o
 * balcão cadastra com o que o cliente trouxe na mão.
 *
 * O `prefixo` existe porque o formulário dentro da venda usa nomes próprios
 * (`novo_...`) pra não colidir com os campos da venda em volta.
 */

import * as v from "./validacao.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/** 1988-07-19 -> 19/07/1988, pra mostrar na tela e nos documentos. */
export function dataNascimentoBr(valor) {
  const texto = String(valor ?? "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto)) return "";
  const [a, m, d] = texto.split("-");
  return `${d}/${m}/${a}`;
}

export function htmlCamposDocumentos(pessoa = null, prefixo = "") {
  return `
    <div class="grade-2">
      <label class="campo">RG <span class="fraco">(opcional)</span>
        <input name="${prefixo}rg" maxlength="20" value="${escapar(pessoa?.rg || "")}" />
      </label>
      <label class="campo">Nascimento <span class="fraco">(opcional)</span>
        <input name="${prefixo}nascimento" type="date" max="${new Date().toISOString().slice(0, 10)}"
          value="${escapar(String(pessoa?.nascimento || "").slice(0, 10))}" />
      </label>
    </div>`;
}

export function lerDocumentos(dados, prefixo = "") {
  return {
    rg: (dados.get(`${prefixo}rg`) || "").trim(),
    nascimento: (dados.get(`${prefixo}nascimento`) || "").trim(),
  };
}

export function regrasDocumentos(d, prefixo = "") {
  return [
    [`${prefixo}nascimento`, v.nascimentoValido(d.nascimento),
      "Confira a data de nascimento"],
  ];
}

export function corpoDocumentos(d) {
  return {
    rg: d.rg || null,
    nascimento: d.nascimento || null,
  };
}
