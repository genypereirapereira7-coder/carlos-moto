/**
 * E-mail e endereço — os mesmos campos em todo lugar que cadastra uma pessoa:
 * cliente novo, edição do cliente e o cadastro rápido dentro da venda.
 *
 * Mora num módulo só, como o do cônjuge, porque a regra é a mesma nos três:
 * **tudo opcional, mas o que vier preenchido tem que estar certo**. O dono
 * cadastra na pressa do balcão e completa depois — o que não pode é UF que não
 * existe e CEP de 7 dígitos entrarem calados e só aparecerem no dia em que o
 * contrato sai com o endereço errado.
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

/** CEP só com dígitos vira 76870-000 na hora de mostrar. */
export function formatarCep(valor) {
  const d = String(valor ?? "").replace(/\D/g, "");
  return d.length === 8 ? `${d.slice(0, 5)}-${d.slice(5)}` : String(valor ?? "");
}

export function htmlCamposEndereco(pessoa = null, prefixo = "") {
  const uf = (pessoa?.uf || "").toUpperCase();
  return `
    <label class="campo">E-mail <span class="fraco">(opcional)</span>
      <input name="${prefixo}email" type="email" inputmode="email" autocapitalize="off"
        placeholder="nome@email.com" value="${escapar(pessoa?.email || "")}" />
    </label>
    <div class="grade-2">
      <label class="campo">Endereço
        <input name="${prefixo}endereco" placeholder="Rua, avenida…" value="${escapar(pessoa?.endereco || "")}" />
      </label>
      <label class="campo">Número
        <input name="${prefixo}numero" placeholder="123 ou S/N" value="${escapar(pessoa?.numero || "")}" />
      </label>
      <label class="campo">Complemento
        <input name="${prefixo}complemento" placeholder="Casa, apto, fundos…" value="${escapar(pessoa?.complemento || "")}" />
      </label>
      <label class="campo">Bairro
        <input name="${prefixo}bairro" value="${escapar(pessoa?.bairro || "")}" />
      </label>
      <label class="campo">Cidade
        <input name="${prefixo}cidade" value="${escapar(pessoa?.cidade || "")}" />
      </label>
      <label class="campo">UF
        <select name="${prefixo}uf">
          <option value="" ${uf ? "" : "selected"}>—</option>
          ${v.UFS_DO_BRASIL.map((s) => (
            `<option value="${s}" ${s === uf ? "selected" : ""}>${s}</option>`
          )).join("")}
        </select>
      </label>
      <label class="campo">CEP
        <input name="${prefixo}cep" inputmode="numeric" maxlength="9" placeholder="76870-000"
          value="${escapar(formatarCep(pessoa?.cep || ""))}" />
      </label>
    </div>`;
}

export function lerEndereco(dados, prefixo = "") {
  const texto = (campo) => (dados.get(prefixo + campo) || "").trim();
  return {
    email: texto("email"),
    endereco: texto("endereco"),
    numero: texto("numero"),
    complemento: texto("complemento"),
    bairro: texto("bairro"),
    cidade: texto("cidade"),
    uf: texto("uf"),
    cep: texto("cep"),
  };
}

export function regrasEndereco(e, prefixo = "") {
  return [
    [`${prefixo}email`, v.emailValido(e.email), "E-mail inválido — confira o endereço"],
    [`${prefixo}cep`, v.cepValido(e.cep), "CEP tem 8 dígitos"],
    [`${prefixo}uf`, v.ufValida(e.uf), "UF inválida — use a sigla do estado, como RO"],
  ];
}

export function corpoEndereco(e) {
  // Campo em branco vai como `null`, não como "": assim apagar um endereço na
  // edição realmente apaga, em vez de gravar texto vazio.
  const ou = (valor) => (valor ? valor : null);
  return {
    email: ou(e.email),
    endereco: ou(e.endereco),
    numero: ou(e.numero),
    complemento: ou(e.complemento),
    bairro: ou(e.bairro),
    cidade: ou(e.cidade),
    uf: ou(e.uf ? e.uf.toUpperCase() : ""),
    cep: ou(e.cep ? e.cep.replace(/\D/g, "") : ""),
  };
}

/** O endereço numa linha, pra mostrar na tela do cliente. */
export function enderecoEmUmaLinha(pessoa) {
  const rua = [pessoa?.endereco, pessoa?.numero].filter(Boolean).join(", ");
  const local = [pessoa?.cidade, pessoa?.uf].filter(Boolean).join(" - ");
  return [rua, pessoa?.complemento, pessoa?.bairro, local,
          pessoa?.cep ? formatarCep(pessoa.cep) : ""].filter(Boolean).join(" · ");
}
