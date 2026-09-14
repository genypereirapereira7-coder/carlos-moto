/**
 * Par de campos Marca → Modelo, usado no cadastro e na edição de moto.
 * O select de modelo só faz sentido depois que uma marca foi escolhida — a
 * lista de modelos é grande demais pra mostrar todas juntas.
 */

import { MARCAS, MARCAS_E_MODELOS, MODELOS_ANTIGOS } from "./dados-motos.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// Escapa porque marca e modelo "fora da lista" vêm do banco — de antes da
// lista fixa existir, digitados à mão — e um `"` no nome quebraria o HTML.
function opcao(valor, rotulo, selecionado) {
  return `<option value="${escapar(valor)}" ${selecionado ? "selected" : ""}>${escapar(rotulo)}</option>`;
}

function antigosDa(marca) {
  return (MODELOS_ANTIGOS[marca] || []).map((item) =>
    Array.isArray(item) ? { nome: item[0], nota: item[1] } : { nome: item, nota: "" },
  );
}

export function htmlSelectMarca(marcaAtual = "") {
  const options = [opcao("", "Selecione a marca", !marcaAtual)];
  for (const marca of MARCAS) {
    options.push(opcao(marca, marca, marca === marcaAtual));
  }
  // Marca já gravada mas fora da lista fixa (dado antigo) — mantém pra não
  // apagar o que já tinha sem o dono perceber.
  if (marcaAtual && !MARCAS.includes(marcaAtual)) {
    options.push(opcao(marcaAtual, `${marcaAtual} (fora da lista)`, true));
  }
  return options.join("");
}

export function htmlSelectModelo(marcaAtual = "", modeloAtual = "") {
  const atuais = MARCAS_E_MODELOS[marcaAtual] || [];
  const antigos = antigosDa(marcaAtual);
  const conhecidos = [...atuais, ...antigos.map((a) => a.nome)];

  const partes = [
    opcao("", conhecidos.length ? "Selecione o modelo" : "Escolha a marca primeiro", !modeloAtual),
  ];
  const htmlAtuais = atuais.map((m) => opcao(m, m, m === modeloAtual)).join("");

  if (antigos.length) {
    const htmlAntigos = antigos
      .map((a) => opcao(a.nome, a.nota ? `${a.nome} — ${a.nota}` : a.nome, a.nome === modeloAtual))
      .join("");
    partes.push(`<optgroup label="Modelos atuais">${htmlAtuais}</optgroup>`);
    partes.push(`<optgroup label="Modelos antigos">${htmlAntigos}</optgroup>`);
  } else {
    partes.push(htmlAtuais);
  }

  if (modeloAtual && !conhecidos.includes(modeloAtual)) {
    partes.push(opcao(modeloAtual, `${modeloAtual} (fora da lista)`, true));
  }
  return partes.join("");
}

/** Troca de marca reconstrói as opções de modelo do zero, dentro do form dado. */
export function ligarMarcaModelo(form, { nomeMarca = "marca", nomeModelo = "modelo" } = {}) {
  const selectMarca = form.elements[nomeMarca];
  const selectModelo = form.elements[nomeModelo];
  selectMarca.addEventListener("change", () => {
    selectModelo.innerHTML = htmlSelectModelo(selectMarca.value);
  });
}
