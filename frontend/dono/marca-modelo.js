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

// ---------------------------------------------------- modelo por autocomplete

// Uma lista achatada {marca, modelo} de tudo que a loja conhece — é o que o
// campo procura enquanto o dono digita. Montada uma vez.
function _listaBusca() {
  const lista = [];
  for (const [marca, modelos] of Object.entries(MARCAS_E_MODELOS)) {
    for (const modelo of modelos) lista.push({ marca, modelo });
    for (const antigo of antigosDa(marca)) lista.push({ marca, modelo: antigo.nome });
  }
  return lista;
}

const _MODELOS = _listaBusca();

function _semAcento(texto) {
  return String(texto).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

/**
 * O par Marca/Modelo, agora sem os selects: o dono **digita** o modelo e a
 * lista aparece embaixo, já com a marca. Cada família da moto casa pelo começo
 * (digitou "CG 160" → aparecem os CG 160), e o resto da palavra em qualquer
 * lugar. Modelo fora da lista continua valendo: é só digitar e seguir.
 */
export function htmlCampoModelo(marcaAtual = "", modeloAtual = "") {
  return `
    <label class="campo campo-modelo">Modelo
      <input name="modelo" class="entrada-modelo" autocomplete="off" spellcheck="false"
             value="${escapar(modeloAtual)}" placeholder="Digite: CG 160, Biz, PCX…" required />
      <div class="resultado-busca sugestoes-modelo" hidden></div>
    </label>
    <label class="campo">Marca
      <input name="marca" class="entrada-marca" autocomplete="off"
             value="${escapar(marcaAtual)}" placeholder="Honda, Yamaha…" required />
    </label>`;
}

/** Liga o autocomplete do campo de modelo dentro do form dado. */
export function ligarAutocompleteModelo(form) {
  const campoModelo = form.querySelector(".entrada-modelo");
  const campoMarca = form.querySelector(".entrada-marca");
  const caixa = form.querySelector(".sugestoes-modelo");
  if (!campoModelo || !caixa) return;

  let destaque = -1;

  function fechar() {
    caixa.hidden = true;
    caixa.innerHTML = "";
    destaque = -1;
  }

  function achados(termo) {
    const t = _semAcento(termo.trim());
    if (t.length < 2) return [];
    // Começa com o termo vem primeiro (o que o dono espera ao digitar "CG
    // 160"); depois os que contêm o termo no meio.
    const comeca = [];
    const contem = [];
    for (const item of _MODELOS) {
      const alvo = _semAcento(item.modelo);
      if (alvo.startsWith(t)) comeca.push(item);
      else if (alvo.includes(t) || _semAcento(`${item.marca} ${item.modelo}`).includes(t)) contem.push(item);
    }
    return [...comeca, ...contem].slice(0, 8);
  }

  function desenhar(lista) {
    if (!lista.length) return fechar();
    caixa.innerHTML = lista.map((item, i) => `
      <button type="button" class="resultado-item" data-i="${i}"
              data-modelo="${escapar(item.modelo)}" data-marca="${escapar(item.marca)}"
              ${i === destaque ? 'data-destaque="1"' : ""}>
        ${escapar(item.modelo)} <span class="fraco">· ${escapar(item.marca)}</span>
      </button>`).join("");
    caixa.hidden = false;
  }

  function escolher(botao) {
    campoModelo.value = botao.dataset.modelo;
    campoMarca.value = botao.dataset.marca;
    fechar();
    campoModelo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  campoModelo.addEventListener("input", () => {
    destaque = -1;
    desenhar(achados(campoModelo.value));
  });

  campoModelo.addEventListener("keydown", (evento) => {
    const itens = [...caixa.querySelectorAll(".resultado-item")];
    if (!itens.length) return;
    if (evento.key === "ArrowDown") {
      evento.preventDefault();
      destaque = (destaque + 1) % itens.length;
    } else if (evento.key === "ArrowUp") {
      evento.preventDefault();
      destaque = (destaque - 1 + itens.length) % itens.length;
    } else if (evento.key === "Enter" && !caixa.hidden) {
      evento.preventDefault();
      escolher(itens[destaque >= 0 ? destaque : 0]);
      return;
    } else if (evento.key === "Escape") {
      fechar();
      return;
    } else {
      return;
    }
    itens.forEach((el, i) => { el.dataset.destaque = i === destaque ? "1" : "0"; });
  });

  caixa.addEventListener("mousedown", (evento) => {
    // mousedown, e não click: o blur do campo dispara antes do click e fecharia
    // a caixa, engolindo a escolha.
    const botao = evento.target.closest(".resultado-item");
    if (botao) { evento.preventDefault(); escolher(botao); }
  });

  campoModelo.addEventListener("blur", () => setTimeout(fechar, 150));
}
