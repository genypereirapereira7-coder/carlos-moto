/**
 * A fila offline na tela: o contador na lateral e o painel que lista o que
 * está esperando.
 *
 * O dono precisa ver o que ainda não subiu. Um cadastro que ele deu por feito
 * e que está parado numa fila invisível é pior do que um erro na cara: ele
 * fecha a loja achando que lançou.
 */

import * as api from "../comum/api.js";
import * as fila from "../comum/fila.js";
import { abrirModal, avisar, escapar } from "./ui.js";

const botao = document.getElementById("botao-fila");
const contadorEl = document.getElementById("fila-contador");

function _quando(iso) {
  const d = new Date(iso);
  const hoje = new Date().toDateString() === d.toDateString();
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return hoje ? `hoje ${hora}` : `${d.toLocaleDateString("pt-BR")} ${hora}`;
}

export async function atualizarContador() {
  const itens = await fila.listar();
  botao.hidden = itens.length === 0;
  contadorEl.textContent = String(itens.length);
  // Recusado não sobe sozinho — o botão fica vermelho pra não passar batido.
  botao.dataset.recusados = itens.some((i) => i.recusado) ? "1" : "0";
}

function _linha(item) {
  const situacao = item.recusado
    ? `<span class="selo selo--devendo">Recusado</span>
       <span class="fraco">${escapar(item.ultimoErro || "o servidor não aceitou")}</span>`
    : '<span class="selo selo--pendente">Esperando internet</span>';

  const descartar = item.recusado
    ? `<button class="botao botao--fantasma botao--pequeno" data-descartar="${item.id}" type="button">Descartar</button>`
    : "";

  return `
    <li>
      <div>
        <strong>${escapar(item.rotulo || `${item.metodo} ${item.caminho}`)}</strong>
        <p class="fraco">${_quando(item.criadoEm)} · ${situacao}</p>
      </div>
      ${descartar}
    </li>`;
}

export async function abrirPainel() {
  const modal = abrirModal(`
    <h3>Esperando internet</h3>
    <p class="fraco">
      Isto já está guardado neste aparelho e sobe sozinho quando a conexão
      voltar. Pode fechar o sistema que não se perde.
    </p>
    <ul class="lista-fila" id="lista-fila"></ul>
    <div class="acoes-modal">
      <button class="botao botao--fantasma" data-fechar type="button">Fechar</button>
      <button class="botao" id="botao-tentar-agora" type="button">Tentar agora</button>
    </div>
  `);

  async function desenhar() {
    const itens = await fila.listar();
    const lista = modal.querySelector("#lista-fila");
    if (!lista) return;
    lista.innerHTML = itens.length
      ? itens.map(_linha).join("")
      : '<li class="fraco">Nada esperando — está tudo no servidor.</li>';
  }

  modal.addEventListener("click", async (evento) => {
    if (evento.target.closest("[data-fechar]")) {
      modal.closest(".sobreposicao")?.remove();
      return;
    }

    const descartar = evento.target.closest("[data-descartar]");
    if (descartar) {
      await fila.remover(descartar.dataset.descartar);
      await desenhar();
      await atualizarContador();
      return;
    }

    if (evento.target.closest("#botao-tentar-agora")) {
      const botaoTentar = modal.querySelector("#botao-tentar-agora");
      botaoTentar.disabled = true;
      botaoTentar.textContent = "Enviando…";
      await sincronizar({ silencioso: false });
      await desenhar();
      botaoTentar.disabled = false;
      botaoTentar.textContent = "Tentar agora";
    }
  });

  await desenhar();
}

/**
 * Sobe a fila e conta pro dono o que aconteceu.
 *
 * `silencioso` cala o aviso de "não foi" — nas tentativas automáticas, que
 * acontecem de minuto em minuto, avisar toda vez que a internet continua
 * fora vira barulho.
 */
export async function sincronizar({ silencioso = true } = {}) {
  const { subiram, recusados, parou } = await api.sincronizarFila();
  await atualizarContador();

  if (subiram.length) {
    avisar(
      subiram.length === 1 ? "1 cadastro subiu agora" : `${subiram.length} cadastros subiram agora`,
      "ok",
    );
  }

  if (recusados.length) {
    avisar(
      recusados.length === 1
        ? `O servidor recusou: ${recusados[0].rotulo}`
        : `O servidor recusou ${recusados.length} envios`,
      "erro",
    );
  }

  if (parou && !silencioso && !subiram.length) {
    avisar("Ainda sem conexão — continua guardado", "erro");
  }

  return { subiram, recusados, parou };
}

botao.addEventListener("click", abrirPainel);
fila.aoMudar(atualizarContador);
