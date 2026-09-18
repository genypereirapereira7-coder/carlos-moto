/**
 * Estado civil e dados do cônjuge — os mesmos campos em todo lugar que
 * cadastra uma pessoa: cliente novo, edição do cliente e o cadastro rápido
 * dentro da venda.
 *
 * Mora num módulo só porque a regra é a mesma nos três: **casado exige nome e
 * telefone do cônjuge**. É por eles que a loja acha a família quando o titular
 * some, e na venda de veículo o cônjuge costuma assinar junto. O CPF dele é
 * opcional — nem sempre o documento está na mão na hora.
 *
 * O `prefixo` existe porque o formulário de cliente dentro da venda usa nomes
 * próprios (`novo_...`) pra não colidir com os campos da venda em volta.
 */

import * as v from "./validacao.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

export function htmlCamposConjuge(pessoa = null, prefixo = "") {
  const casado = pessoa?.casado;
  return `
    <label class="campo">É casado(a)?
      <select name="${prefixo}casado">
        <option value="" ${casado == null ? "selected" : ""}>—</option>
        <option value="nao" ${casado === false ? "selected" : ""}>Não</option>
        <option value="sim" ${casado === true ? "selected" : ""}>Sim</option>
      </select>
    </label>
    <div class="grade-2 bloco-conjuge" ${casado === true ? "" : "hidden"}>
      <label class="campo">Nome do cônjuge
        <input name="${prefixo}conjuge_nome" value="${escapar(pessoa?.conjuge_nome || "")}" />
      </label>
      <label class="campo">Telefone do cônjuge
        <input name="${prefixo}conjuge_telefone" placeholder="(69) 99999-0000" value="${escapar(pessoa?.conjuge_telefone || "")}" />
      </label>
      <label class="campo">CPF do cônjuge <span class="fraco">(opcional)</span>
        <input name="${prefixo}conjuge_cpf" maxlength="14" placeholder="000.000.000-00" value="${escapar(pessoa?.conjuge_cpf || "")}" />
      </label>
    </div>`;
}

/** Mostra/esconde o bloco do cônjuge conforme a resposta. */
export function ligarConjuge(raiz, prefixo = "") {
  const select = raiz.querySelector(`select[name="${prefixo}casado"]`);
  if (!select) return;
  const bloco = select.closest("form")?.querySelector(".bloco-conjuge")
    || raiz.querySelector(".bloco-conjuge");
  select.addEventListener("change", () => {
    if (bloco) bloco.hidden = select.value !== "sim";
  });
}

export function lerConjuge(dados, prefixo = "") {
  const texto = (campo) => (dados.get(prefixo + campo) || "").trim();
  return {
    casado: dados.get(`${prefixo}casado`),
    nome: texto("conjuge_nome"),
    telefone: texto("conjuge_telefone"),
    cpf: texto("conjuge_cpf"),
  };
}

export function regrasConjuge(c, prefixo = "") {
  const casado = c.casado === "sim";
  return [
    [`${prefixo}conjuge_nome`, !casado || !!c.nome, "Casado: informe o nome do cônjuge"],
    [`${prefixo}conjuge_telefone`, !casado || !!c.telefone, "Casado: informe o telefone do cônjuge"],
    [`${prefixo}conjuge_telefone`, !c.telefone || v.telefoneValido(c.telefone),
      "Telefone do cônjuge precisa ter 10 ou 11 dígitos, com DDD"],
    [`${prefixo}conjuge_cpf`, !c.cpf || v.cpfValido(c.cpf), "CPF do cônjuge inválido — confira os números"],
  ];
}

export function corpoConjuge(c) {
  const casado = c.casado === "sim";
  return {
    // "" (não respondido) vira null; só "sim"/"nao" viram booleano.
    casado: c.casado === "" ? null : casado,
    // Responder "não" limpa o que tinha ficado de uma resposta anterior.
    conjuge_nome: casado ? (c.nome || null) : null,
    conjuge_telefone: casado ? (c.telefone || null) : null,
    conjuge_cpf: casado ? (c.cpf || null) : null,
  };
}
