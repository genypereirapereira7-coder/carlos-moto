/**
 * Validação de formulário — reaproveitada em toda tela do painel do dono.
 *
 * Regra do sistema: toda entrada é validada aqui na tela (pra avisar na hora,
 * sem esperar o servidor) **e** de novo na API (`app/schemas/validadores.py`)
 * — a tela não é a única porta de entrada, e o servidor não confia nela.
 */

import { hojeIso } from "../comum/formato.js";
import { avisar } from "./ui.js";

const REGEX_PLACA_ANTIGA = /^[A-Z]{3}\d{4}$/;
const REGEX_PLACA_MERCOSUL = /^[A-Z]{3}\d[A-Z]\d{2}$/;

export function limparPlaca(valor) {
  return String(valor || "").trim().toUpperCase().replace(/-/g, "");
}

/** Vazio conta como válido — placa é sempre opcional (0km sem emplacar). */
export function placaValida(valor) {
  const limpa = limparPlaca(valor);
  return !limpa || REGEX_PLACA_ANTIGA.test(limpa) || REGEX_PLACA_MERCOSUL.test(limpa);
}

export function chassiValido(valor) {
  const limpo = String(valor || "").trim().toUpperCase();
  return !limpo || (limpo.length === 17 && /^[A-Z0-9]+$/.test(limpo));
}

export function anoValido(valor) {
  const n = Number(valor);
  const limiteFuturo = new Date().getFullYear() + 1;
  return Number.isInteger(n) && n >= 1980 && n <= limiteFuturo;
}

/**
 * CPF conferido pelos dois dígitos verificadores — a mesma conta de
 * `app/schemas/validadores.py::validar_cpf`. Contar 11 dígitos não pega o
 * erro que acontece de verdade, que é digitar um número trocado olhando o
 * documento.
 */
export function cpfValido(valor) {
  const d = String(valor ?? "").replace(/\D/g, "");
  if (d.length !== 11 || d === d[0].repeat(11)) return false;

  for (const quantos of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < quantos; i += 1) soma += Number(d[i]) * (quantos + 1 - i);
    if (Number(d[quantos]) !== ((soma * 10) % 11) % 10) return false;
  }
  return true;
}

/**
 * Não preencher é válido (telefone é opcional) — mas preencher com algo que
 * não vira telefone, não. Sem essa distinção, "abcdefghij" virava vazio na
 * limpeza dos dígitos e passava como se o campo estivesse em branco: o dono
 * digitava errado, o sistema aceitava calado e o cliente ficava sem telefone
 * justamente quando ele precisa ligar pra cobrar.
 */
export function telefoneValido(valor) {
  const texto = String(valor ?? "").trim();
  if (!texto) return true;
  const d = texto.replace(/\D/g, "");
  return d.length === 10 || d.length === 11;
}

/**
 * E-mail: em branco passa (é opcional), preenchido tem que ter cara de
 * e-mail. Mesma regra frouxa de propósito do servidor — o objetivo é pegar o
 * dedo escorregado, não certificar endereço.
 */
export function emailValido(valor) {
  const texto = String(valor ?? "").trim();
  if (!texto) return true;
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(texto);
}

/** CEP: em branco passa (é opcional); preenchido tem que ter 8 dígitos. */
export function cepValido(valor) {
  const texto = String(valor ?? "").trim();
  if (!texto) return true;
  return texto.replace(/\D/g, "").length === 8;
}

// Lista fechada, igual à do servidor: "RR" e "RO" são um caractere de
// diferença, e a loja é de Rondônia.
const UFS = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
  "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
  "SP", "SE", "TO",
];

export const UFS_DO_BRASIL = UFS;

/** UF: em branco passa (é opcional); preenchida tem que existir. */
export function ufValida(valor) {
  const texto = String(valor ?? "").trim().toUpperCase();
  if (!texto) return true;
  return UFS.includes(texto);
}

/**
 * Nascimento: em branco passa (é opcional). No futuro é dedo escorregado; antes
 * de 1900 é a "data em branco" do sistema antigo (`0001-01-01`) — 611 cadastros
 * da loja vinham assim, e sem esta regra a tela encheria de gente do ano 1.
 */
export function nascimentoValido(valor) {
  const texto = String(valor ?? "").trim();
  if (!texto) return true;
  const d = new Date(`${texto}T12:00:00`);
  if (Number.isNaN(d.getTime())) return false;
  const hoje = new Date();
  return d <= hoje && d.getFullYear() >= 1900;
}

export function textoPreenchido(valor) {
  return String(valor ?? "").trim().length > 0;
}

export function numeroNaoNegativo(valor) {
  if (valor === "" || valor == null) return true; // opcional — vazio não é negativo
  const n = Number(valor);
  return Number.isFinite(n) && n >= 0;
}

export function numeroPositivo(valor) {
  const n = Number(valor);
  return Number.isFinite(n) && n > 0;
}

/** Vazio conta como válido — a data em si pode ser opcional; quem exige
 * preenchimento usa `textoPreenchido` junto. */
export function dataNaoFutura(valor) {
  if (!valor) return true;
  return valor <= hojeIso();
}

/**
 * Roda `regras` (array de `[nomeDoCampo, condicaoOk, mensagem]`) contra um
 * `<form>`, marca cada campo que falhou e escreve a mensagem embaixo dele.
 * Devolve `true` só se tudo passou.
 */
export function validarFormulario(form, regras) {
  limparErros(form);
  let valido = true;
  for (const [nomeCampo, ok, mensagem] of regras) {
    if (!ok) {
      valido = false;
      marcarErro(form, nomeCampo, mensagem);
    }
  }
  return valido;
}

export function marcarErro(form, nomeCampo, mensagem) {
  const campo = form.elements[nomeCampo];
  if (!campo) return;
  campo.setAttribute("aria-invalid", "true");
  campo.classList.add("invalido");
  const dono = campo.closest(".campo") || campo.parentElement;
  let erroEl = dono.querySelector(".erro-campo");
  if (!erroEl) {
    erroEl = document.createElement("small");
    erroEl.className = "erro-campo";
    dono.appendChild(erroEl);
  }
  erroEl.textContent = mensagem;

  // Some assim que a pessoa mexe no campo: um quadrado que continua vermelho
  // depois de corrigido parece que a correção não foi aceita. Se o valor
  // novo também estiver errado, o próximo "Salvar" marca de novo.
  const parar = new AbortController();
  const limpar = () => {
    campo.classList.remove("invalido");
    campo.removeAttribute("aria-invalid");
    dono.querySelector(".erro-campo")?.remove();
    parar.abort();
  };
  campo.addEventListener("input", limpar, { signal: parar.signal });
  campo.addEventListener("change", limpar, { signal: parar.signal });
}

export function limparErros(form) {
  form.querySelectorAll(".invalido").forEach((el) => {
    el.classList.remove("invalido");
    el.removeAttribute("aria-invalid");
  });
  form.querySelectorAll(".erro-campo").forEach((el) => el.remove());
}

/**
 * Erro que voltou do servidor — não vira caixa de aviso no formulário: o
 * campo errado fica vermelho e a mensagem aparece pequena embaixo dele,
 * igual à validação da própria tela. Só um erro que não dá pra apontar pra
 * nenhum campo (rede caiu, conflito de estado tipo "moto já foi vendida")
 * vira um toast — não tem quadrado nenhum pra pintar de vermelho.
 *
 * @param {HTMLFormElement} form
 * @param {*} erro - `ErroApi` ou `ErroRede`, de `comum/api.js`.
 * @param {object} [opcoes]
 * @param {Record<string,string>} [opcoes.renomear] - nome do campo na API,
 *   quando difere do `name` do input (ex.: API manda `preco_centavos`, o
 *   input se chama `preco`).
 * @param {[string, string][]} [opcoes.porPalavra] - para erros que voltam
 *   como texto solto (409, por exemplo): `[trechoDaMensagem, nomeDoCampo]`,
 *   testado em ordem até achar um trecho presente na mensagem.
 */
export function mostrarErroDeApi(form, erro, { renomear = {}, porPalavra = [] } = {}) {
  const detalhe = erro?.corpo?.detail;

  if (Array.isArray(detalhe)) {
    for (const item of detalhe) {
      const campoDaApi = item.loc?.[item.loc.length - 1];
      const campo = renomear[campoDaApi] || campoDaApi;
      if (campo && form.elements[campo]) {
        marcarErro(form, campo, item.msg);
      } else {
        avisar(item.msg, "erro");
      }
    }
    return;
  }

  if (typeof detalhe === "string") {
    for (const [trecho, campo] of porPalavra) {
      if (detalhe.toLowerCase().includes(trecho.toLowerCase()) && form.elements[campo]) {
        marcarErro(form, campo, detalhe);
        return;
      }
    }
  }

  avisar(erro?.message || "Não deu pra completar. Tente de novo.", "erro");
}
