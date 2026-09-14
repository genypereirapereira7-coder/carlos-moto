/** Bootstrap do painel do dono: login, menu lateral, conexão em tempo real. */

import * as api from "../comum/api.js";
import { conectar } from "../comum/ws.js";
import { avisar, abrirModal, fecharModal } from "./ui.js";
import { atualizarContador, sincronizar } from "./fila-ui.js";
import { abrirPainelDeAcesso } from "./acesso.js";
import { marcarErro, limparErros } from "./validacao.js";
import { renderMotos } from "./telas/motos.js";
import { renderClientes } from "./telas/clientes.js";
import { renderParcelas } from "./telas/parcelas.js";
import { renderFinanceiro } from "./telas/financeiro.js";

const telaLogin = document.getElementById("tela-login");
const app = document.getElementById("app");
const conteudo = document.getElementById("conteudo");
const pontoConexao = document.getElementById("ponto-conexao");
const usuarioNomeEl = document.getElementById("usuario-nome");

const TELAS = {
  motos: renderMotos,
  clientes: renderClientes,
  parcelas: renderParcelas,
  financeiro: renderFinanceiro,
};

let abaAtual = null;

function abrirAba(nome) {
  abaAtual = nome;
  document.querySelectorAll(".aba").forEach((botao) => {
    botao.dataset.ativa = botao.dataset.tab === nome ? "1" : "0";
  });
  location.hash = nome;
  TELAS[nome]?.(conteudo);
}

function abaDaUrl() {
  const nome = location.hash.replace("#", "");
  return TELAS[nome] ? nome : "motos";
}

function mostrarApp(nome) {
  telaLogin.hidden = true;
  app.hidden = false;
  usuarioNomeEl.textContent = nome;
  abrirAba(abaDaUrl());
  // Abriu o sistema: mostra o que ficou esperando da última vez e já tenta
  // subir. É o gatilho mais importante dos quatro — cobre o caso de fechar o
  // navegador sem internet e voltar no dia seguinte.
  atualizarContador();
  sincronizar();
  oferecerInstalacao();
}

function mostrarLogin() {
  app.hidden = true;
  telaLogin.hidden = false;
}

// ------------------------------------------------------------------ login

document.getElementById("form-login").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const form = evento.target;
  limparErros(form);
  const chave = document.getElementById("login-chave").value.trim();

  if (!chave) {
    marcarErro(form, "login-chave", "Digite a chave de acesso");
    return;
  }

  try {
    const sessao = await api.parear(chave);
    if (sessao.papel !== "DONO") {
      await api.sair();
      marcarErro(form, "login-chave", "Esta chave não é a do dono.");
      return;
    }
    mostrarApp(sessao.nome);
    iniciarWs();
  } catch (erro) {
    if (erro?.status === 401) {
      marcarErro(form, "login-chave", "Chave de acesso inválida.");
    } else if (erro?.status === 429) {
      marcarErro(form, "login-chave", erro.message);
    } else {
      avisar(erro.message || "Não deu pra conectar.", "erro");
    }
  }
});

document.getElementById("botao-acesso").addEventListener("click", abrirPainelDeAcesso);

document.getElementById("botao-sair").addEventListener("click", async () => {
  await api.sair();
  faixaOffline.hidden = true;
  mostrarLogin();
});

document.querySelectorAll(".aba").forEach((botao) => {
  botao.addEventListener("click", () => abrirAba(botao.dataset.tab));
});

window.addEventListener("hashchange", () => {
  if (!app.hidden) abrirAba(abaDaUrl());
});

api.aoPerderSessao(() => mostrarLogin());

// ------------------------------------------------------------- tempo real

let canalWs = null;

function iniciarWs() {
  canalWs?.fechar();
  canalWs = conectar({
    aoMudarConexao: (ligado) => {
      pontoConexao.dataset.estado = ligado ? "online" : "offline";
      // O WebSocket reconectar é o sinal mais confiável de que dá pra
      // enviar: o `online` do navegador só diz que existe wi-fi, não que o
      // servidor está respondendo.
      if (ligado) sincronizar();
    },
    aoEvento: (evento) => {
      // Qualquer evento de moto/venda/parcela/cliente pode ter mudado o que
      // a aba aberta está mostrando — recarregar é mais simples e mais
      // seguro do que tentar remendar o estado na tela por tipo de evento.
      if (abaAtual && TELAS[abaAtual]) {
        TELAS[abaAtual](conteudo);
      }
      if (evento.startsWith("parcela") || evento.startsWith("venda")) {
        avisar("Atualizado agora", "ok");
      }
    },
  });
}

// ------------------------------------------------------- lendo sem conexão

const faixaOffline = document.getElementById("faixa-offline");

function _quandoFoiGuardado(iso) {
  const d = new Date(iso);
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (new Date().toDateString() === d.toDateString()) return `hoje às ${hora}`;
  return `${d.toLocaleDateString("pt-BR")} às ${hora}`;
}

// A faixa aparece quando alguma leitura veio da cópia guardada e some na
// primeira que vier do servidor. Ela diz a hora do dado — sem isso o dono
// olharia um saldo de ontem achando que é de agora.
api.aoMudarOrigem(({ deCache, gravadoEm }) => {
  if (!deCache) {
    faixaOffline.hidden = true;
    return;
  }
  faixaOffline.textContent =
    `Sem conexão com o servidor — mostrando os dados de ${_quandoFoiGuardado(gravadoEm)}. `
    + "O que você cadastrar agora fica guardado e sobe quando a internet voltar.";
  faixaOffline.hidden = false;
});

// ---------------------------------------------------------------- instalar

// O navegador dispara `beforeinstallprompt` quando o app cumpre os requisitos
// de instalação — manifest com ícone de 192 e de 512, service worker, origem
// segura — e ainda não está instalado. Guardar o evento é obrigatório:
// `prompt()` só funciona a partir dele.
let pedidoDeInstalacao = null;
const botaoInstalar = document.getElementById("botao-instalar");

// Aberto como aplicativo (janela própria, sem barra de endereço) não tem o
// que instalar.
const jaEhAplicativo = () => window.matchMedia("(display-mode: standalone)").matches;

window.addEventListener("beforeinstallprompt", (evento) => {
  // Sem o preventDefault o Chrome mostra a barrinha dele por cima do painel.
  evento.preventDefault();
  pedidoDeInstalacao = evento;
  if (!jaEhAplicativo()) botaoInstalar.hidden = false;
});

window.addEventListener("appinstalled", () => {
  pedidoDeInstalacao = null;
  botaoInstalar.hidden = true;
  avisar("Instalado! Procure Carlos Moto entre os seus programas", "ok");
});

/**
 * Safari e Firefox não têm `beforeinstallprompt` — neles a instalação é pelo
 * menu do navegador. Em vez de sumir com o botão e deixar o dono sem saber
 * que dá pra instalar, ele abre as instruções.
 */
function explicarComoInstalar() {
  const modal = abrirModal(`
    <div class="modal-topo"><h3>Instalar no computador</h3></div>
    <p class="fraco">Este navegador não instala sozinho. Em dois cliques:</p>
    <ul class="lista-ajuda">
      <li><strong>Chrome ou Edge:</strong> menu <strong>⋮</strong> no canto superior direito →
        <strong>Transmitir, salvar e compartilhar</strong> → <strong>Instalar página como app</strong>.</li>
      <li><strong>Safari:</strong> menu <strong>Arquivo</strong> → <strong>Adicionar à Dock</strong>.</li>
    </ul>
    <p class="fraco">Depois de instalado ele abre em janela própria, sem barra de
      endereço, e continua funcionando sem internet.</p>
    <div class="acoes-modal">
      <button class="botao" data-fechar type="button">Entendi</button>
    </div>
  `);
  modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));
}

botaoInstalar.addEventListener("click", async () => {
  if (!pedidoDeInstalacao) {
    explicarComoInstalar();
    return;
  }

  botaoInstalar.disabled = true;
  pedidoDeInstalacao.prompt();
  const { outcome } = await pedidoDeInstalacao.userChoice;
  // O evento não se reaproveita. Se o dono recusar, o navegador manda outro
  // mais tarde — até lá o botão cai no caminho das instruções.
  pedidoDeInstalacao = null;
  botaoInstalar.disabled = false;
  if (outcome !== "accepted") {
    avisar("Tudo bem — dá pra instalar depois por este botão", "ok");
  }
});

// Se o evento não veio (navegador que não suporta, ou app já instalado em
// outro perfil), o botão aparece assim mesmo pra oferecer as instruções.
function oferecerInstalacao() {
  if (jaEhAplicativo()) return;
  setTimeout(() => {
    if (!jaEhAplicativo()) botaoInstalar.hidden = false;
  }, 3000);
}

// -------------------------------------------------------------- fila offline

// O navegador avisando que a rede voltou. Pode ser otimista demais (wi-fi de
// hotel que ainda não autenticou), e por isso não é o único gatilho — mas é o
// mais rápido quando funciona.
window.addEventListener("online", () => sincronizar());

// A rede pode voltar sem nenhum dos dois avisos: o WebSocket já estar caído
// há tempo e o `online` não disparar porque a placa nunca "desconectou". Uma
// tentativa por minuto é barata (uma leitura local quando a fila está vazia)
// e fecha esse buraco.
setInterval(() => sincronizar(), 60_000);

// ------------------------------------------------------------------ start

if (api.estaLogado()) {
  mostrarApp(api.sessaoAtual().nome);
  iniciarWs();
} else {
  mostrarLogin();
}

// Registra o service worker por último: é só o que deixa o app abrir sem
// internet e aparecer como instalável — não deve atrasar nem quebrar o
// primeiro carregamento se falhar.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch((erro) => {
    console.warn("[dono] service worker não registrou", erro);
  });
}
