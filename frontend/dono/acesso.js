/**
 * Chave de acesso e aparelhos conectados.
 *
 * Sem senha, a chave sozinha abre o sistema inteiro. O que segura essa ponta
 * é esta tela: todo aparelho pareado aparece aqui e pode ser desconectado na
 * hora. É ela, e não uma senha, a trava contra um aparelho perdido,
 * emprestado ou vendido.
 */

import * as api from "../comum/api.js";
import { abrirModal, avisar, escapar, mensagemDeErro } from "./ui.js";

function _quando(iso) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR")} às ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit", minute: "2-digit",
  })}`;
}

function _linhaAparelho(s) {
  const esteAqui = s.meu_usuario
    ? '<span class="selo selo--em-dia">seu acesso</span>'
    : "";
  return `
    <li>
      <div>
        <strong>${escapar(s.dispositivo || "aparelho sem nome")}</strong> ${esteAqui}
        <p class="fraco">${escapar(s.usuario_nome)} · conectado em ${_quando(s.criado_em)}</p>
      </div>
      <button class="botao botao--fantasma botao--pequeno" data-desconectar="${s.id}" type="button">
        Desconectar
      </button>
    </li>`;
}

export async function abrirPainelDeAcesso() {
  const modal = abrirModal(`
    <div class="modal-topo"><h3>Chave e aparelhos</h3></div>

    <p class="fraco">
      Aparelhos conectados. Desconectar tira o acesso na hora — é o que fazer
      se um computador ou celular se perder.
    </p>
    <ul class="lista-fila" id="lista-aparelhos"><li class="fraco">Carregando…</li></ul>

    <div class="modal-topo"><h4>Chave de acesso</h4></div>
    <p class="fraco">
      Serve só para conectar um aparelho novo. Trocar a chave <strong>não</strong>
      desconecta os que já estão na lista acima.
    </p>
    <div id="chave-nova"></div>
    <div class="acoes-modal">
      <button class="botao botao--fantasma" data-fechar type="button">Fechar</button>
      <button class="botao botao--perigo" id="botao-nova-chave" type="button">Gerar chave nova</button>
    </div>
  `);

  async function desenharAparelhos() {
    const lista = modal.querySelector("#lista-aparelhos");
    if (!lista) return;
    try {
      const sessoes = await api.pedir("GET", "/auth/sessoes");
      lista.innerHTML = sessoes.length
        ? sessoes.map(_linhaAparelho).join("")
        : '<li class="fraco">Nenhum aparelho conectado.</li>';
    } catch (erro) {
      lista.innerHTML = `<li class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</li>`;
    }
  }

  modal.addEventListener("click", async (evento) => {
    if (evento.target.closest("[data-fechar]")) {
      modal.closest(".sobreposicao")?.remove();
      return;
    }

    const desconectar = evento.target.closest("[data-desconectar]");
    if (desconectar) {
      try {
        await api.pedir("DELETE", `/auth/sessoes/${desconectar.dataset.desconectar}`);
        avisar("Aparelho desconectado");
        await desenharAparelhos();
      } catch (erro) {
        avisar(mensagemDeErro(erro), "erro");
      }
      return;
    }

    if (evento.target.closest("#botao-nova-chave")) {
      const botao = modal.querySelector("#botao-nova-chave");
      botao.disabled = true;
      try {
        const { chave } = await api.pedir(
          "POST", `/usuarios/${api.sessaoAtual().usuario_id}/chave`
        );
        // Mostrada aqui e em lugar nenhum mais: o servidor guarda só o hash.
        modal.querySelector("#chave-nova").innerHTML = `
          <div class="chave-mostrada">${escapar(chave)}</div>
          <p class="fraco">
            Anote agora — esta chave não aparece de novo. A anterior deixou de valer.
          </p>`;
      } catch (erro) {
        avisar(mensagemDeErro(erro), "erro");
      } finally {
        botao.disabled = false;
      }
    }
  });

  await desenharAparelhos();
}
