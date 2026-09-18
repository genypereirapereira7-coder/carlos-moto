/** Bootstrap do painel do dono: login, menu, conexão em tempo real. */

import * as api from "../comum/api.js";
import { conectar } from "../comum/ws.js";
import { avisar } from "./ui.js";
import { atualizarContador, sincronizar } from "./fila-ui.js";
import { abrirPainelDeAcesso } from "./acesso.js";
import * as instalar from "./instalar.js";
import { oferecerMigracao } from "./migracao.js";
import { marcarErro, limparErros } from "./validacao.js";
import { renderMotos } from "./telas/motos.js";
import { renderClientes } from "./telas/clientes.js";
import { renderParcelas } from "./telas/parcelas.js";
import { renderFinanceiro } from "./telas/financeiro.js";
import { renderAntigo } from "./telas/antigo.js";

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
  antigo: renderAntigo,
};

let abaAtual = null;

// --------------------------------------------------------- menu do celular

// No celular a lateral vira duas barras: as quatro abas embaixo, perto do
// polegar, e o resto — instalar, chave, sair — num menu "Mais". São coisas de
// uma vez na vida, e não podem roubar lugar das abas, que se usa o dia
// inteiro. No computador o botão "Mais" nem aparece e isto não faz nada.
const lateral = document.querySelector(".lateral");
const botaoMais = document.getElementById("botao-mais");
const fundoMenu = document.getElementById("fundo-menu");

function menuAberto(aberto) {
  lateral.dataset.menu = aberto ? "aberto" : "";
  botaoMais.setAttribute("aria-expanded", aberto ? "true" : "false");
  fundoMenu.hidden = !aberto;
}

botaoMais.addEventListener("click", () => menuAberto(lateral.dataset.menu !== "aberto"));
fundoMenu.addEventListener("click", () => menuAberto(false));
// Tocou numa opção: o menu sai da frente do que ela for abrir.
document.getElementById("menu-mais").addEventListener("click", (evento) => {
  if (evento.target.closest("button")) menuAberto(false);
});
window.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") menuAberto(false);
});

// ------------------------------------------------------------------- abas

function abrirAba(nome) {
  abaAtual = nome;
  menuAberto(false);
  document.querySelectorAll(".aba").forEach((botao) => {
    botao.dataset.ativa = botao.dataset.tab === nome ? "1" : "0";
  });
  location.hash = nome;
  // Trocou de aba: começa do topo, e não no meio da rolagem da anterior. No
  // celular quem rola é o documento; no computador, o `body`.
  window.scrollTo(0, 0);
  document.body.scrollTop = 0;
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
  // O botão só aparece onde o sistema antigo está — ver `migracao.js`.
  oferecerMigracao();
}

function mostrarLogin() {
  app.hidden = true;
  telaLogin.hidden = false;
  oferecerInstalacao();
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
document.getElementById("botao-antigo").addEventListener("click", () => abrirAba("antigo"));

document.getElementById("botao-sair").addEventListener("click", async () => {
  await api.sair();
  faixaOffline.hidden = true;
  mostrarLogin();
});

document.querySelectorAll(".aba[data-tab]").forEach((botao) => {
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

// Três portas pro mesmo lugar, porque cada uma pega o dono num momento:
//   - no menu (lateral no computador, "Mais" no celular): sempre à mão;
//   - o convite no topo do painel, só no celular — lá ninguém abre um menu
//     procurando "instalar", e quem não vê o convite não instala nunca;
//   - na tela da chave, também só no celular. No iPhone é a hora certa: o app
//     instalado guarda tudo separado do Safari, e quem conecta antes de
//     instalar digita a chave duas vezes.
const botaoInstalar = document.getElementById("botao-instalar");
const botaoInstalarLogin = document.getElementById("botao-instalar-login");
const dicaInstalarLogin = document.getElementById("dica-instalar-login");
const conviteInstalar = document.getElementById("convite-instalar");

// Onde o navegador entrega o pedido pronto, o botão espera um pouco por ele
// antes de aparecer pelo caminho das instruções — senão ele surge, e um
// segundo depois muda de comportamento. No iPhone e no navegador de dentro de
// outro app esse pedido nunca vem, então lá não há o que esperar.
let semPedidoPodeMostrar = instalar.aparelho.ios || instalar.aparelho.dentroDeApp;

function pintarInstalacao() {
  const oferecer = !instalar.ehAplicativo() && !instalar.jaInstalou()
    && (instalar.temPedidoPronto() || semPedidoPodeMostrar);
  const noCelular = oferecer && instalar.aparelho.celular;

  botaoInstalar.textContent = instalar.rotulo();
  botaoInstalar.hidden = !oferecer;
  botaoInstalarLogin.hidden = !noCelular;
  dicaInstalarLogin.hidden = !(noCelular && instalar.aparelho.ios);
  conviteInstalar.hidden = !(noCelular && !instalar.conviteDispensado());
}

function oferecerInstalacao() {
  pintarInstalacao();
  if (semPedidoPodeMostrar) return;
  setTimeout(() => {
    semPedidoPodeMostrar = true;
    pintarInstalacao();
  }, 3000);
}

async function aoTocarInstalar(botao) {
  botao.disabled = true;
  try {
    if ((await instalar.instalar()) === "recusado") {
      avisar("Tudo bem — dá pra instalar depois, pelo menu", "ok");
    }
  } finally {
    botao.disabled = false;
    pintarInstalacao();
  }
}

botaoInstalar.addEventListener("click", () => aoTocarInstalar(botaoInstalar));
botaoInstalarLogin.addEventListener("click", () => aoTocarInstalar(botaoInstalarLogin));
document.getElementById("convite-sim").addEventListener("click", (evento) => {
  aoTocarInstalar(evento.currentTarget);
});
document.getElementById("convite-nao").addEventListener("click", () => {
  instalar.dispensarConvite();
  pintarInstalacao();
});

instalar.aoMudar((oQue) => {
  if (oQue === "instalado") avisar("Instalado! Procure Carlos Moto entre os seus apps", "ok");
  pintarInstalacao();
});

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
