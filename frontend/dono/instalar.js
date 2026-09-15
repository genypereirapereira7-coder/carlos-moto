/**
 * Instalar o painel como aplicativo — no computador e no celular.
 *
 * Cada aparelho instala de um jeito, e a tela precisa saber qual é o caso:
 * mandar o dono procurar um botão que não existe no aparelho dele dá no
 * mesmo que não oferecer instalação nenhuma.
 *
 *   - Chrome e Edge, no Android e no computador: o navegador entrega o
 *     pedido de instalação pronto (`beforeinstallprompt`). Um toque e acabou.
 *   - iPhone e iPad: esse pedido não existe, em navegador nenhum. O caminho é
 *     Compartilhar → "Adicionar à Tela de Início", e a tela ensina.
 *   - Navegador de dentro de outro app (link aberto no Instagram, Facebook,
 *     TikTok): não instala de jeito nenhum. A tela manda abrir no navegador
 *     de verdade — senão o dono procura uma opção que ali não existe.
 *   - Firefox, Safari no Mac, Android sem o pedido: instrução pelo menu.
 */

import { abrirModal, fecharModal } from "./ui.js";

const ua = navigator.userAgent;

// O iPad se apresenta como Mac desde o iPadOS 13. O que o entrega é a tela de
// toque — Mac nenhum tem.
const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
const android = /Android/.test(ua);

/** Que aparelho é este, no que interessa pra instalar. */
export const aparelho = Object.freeze({
  ios,
  android,
  // `; wv)` é o WebView do Android: o navegador embutido dentro de outro app.
  dentroDeApp: /FBAN|FBAV|FB_IAB|Instagram|Line\/|TikTok|musical_ly|Snapchat|; wv\)/.test(ua),
  celular: ios || android
    || (matchMedia("(pointer: coarse)").matches && matchMedia("(max-width: 900px)").matches),
});

/** Aberto pelo ícone instalado: janela própria, sem a barra do navegador. */
export function ehAplicativo() {
  return matchMedia("(display-mode: standalone)").matches
    || matchMedia("(display-mode: fullscreen)").matches
    // O iPhone antigo não entende `display-mode`; este é o jeito dele dizer.
    || navigator.standalone === true;
}

export function rotulo() {
  return aparelho.celular ? "Instalar no celular" : "Instalar no computador";
}

// ------------------------------------------------ o pedido do navegador

// O navegador dispara `beforeinstallprompt` quando o app cumpre os requisitos
// de instalação — manifesto com ícones de 192 e 512, service worker, origem
// segura — e ainda não está instalado. Guardar o evento é obrigatório:
// `prompt()` só funciona a partir dele. E ele pode chegar antes do login, por
// isso é escutado aqui, no carregamento do módulo, e não quando a tela abre.
let pedido = null;
let instalouAgora = false;
const ouvintes = new Set();

/** Avisa quando muda o que dá pra fazer: o pedido chegou, ou já instalou. */
export function aoMudar(callback) {
  ouvintes.add(callback);
  return () => ouvintes.delete(callback);
}

function _avisar(oQue) {
  for (const ouvinte of ouvintes) ouvinte(oQue);
}

window.addEventListener("beforeinstallprompt", (evento) => {
  // Sem o preventDefault o Chrome põe a barrinha dele por cima do painel.
  evento.preventDefault();
  pedido = evento;
  _avisar("pedido");
});

window.addEventListener("appinstalled", () => {
  pedido = null;
  instalouAgora = true;
  _avisar("instalado");
});

export function temPedidoPronto() {
  return pedido !== null;
}

/** Instalou nesta visita: a aba do navegador segue aberta, mas não há mais o que oferecer. */
export function jaInstalou() {
  return instalouAgora;
}

/** Instala, ou ensina a instalar. Devolve "aceito", "recusado" ou "explicado". */
export async function instalar() {
  if (!pedido) {
    explicar();
    return "explicado";
  }
  const esteEvento = pedido;
  // O evento não se reaproveita: usado uma vez, acabou. Se o dono recusar, o
  // navegador manda outro mais tarde — até lá, o botão cai nas instruções.
  pedido = null;
  esteEvento.prompt();
  const { outcome } = await esteEvento.userChoice;
  return outcome === "accepted" ? "aceito" : "recusado";
}

// ------------------------------------------------------- o convite

// "Agora não" vale por uma semana. Pra sempre seria perder o dono que só
// dispensou porque estava com pressa; a cada abertura seria um convite que ele
// aprende a fechar sem ler.
const CHAVE_CONVITE = "carlosmoto.convite-instalar";
const UMA_SEMANA_MS = 7 * 24 * 60 * 60 * 1000;

export function conviteDispensado() {
  try {
    const quando = Number(localStorage.getItem(CHAVE_CONVITE));
    return quando > 0 && Date.now() - quando < UMA_SEMANA_MS;
  } catch {
    return false;
  }
}

export function dispensarConvite() {
  try {
    localStorage.setItem(CHAVE_CONVITE, String(Date.now()));
  } catch { /* aba anônima sem armazenamento: o convite volta, e tudo bem */ }
}

// ---------------------------------------------------------- instruções

const ICONE_COMPARTILHAR = `<svg class="icone-inline" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
  role="img" aria-label="ícone de compartilhar"><path d="M12 15V3M7.5 7.5 12 3l4.5 4.5"/>
  <path d="M8 10H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2"/></svg>`;

function _instrucoes() {
  if (aparelho.dentroDeApp) {
    return {
      titulo: "Abra no navegador primeiro",
      corpo: `
        <p>Este link abriu dentro de outro aplicativo, e daqui não dá pra instalar.</p>
        <ol class="passos-instalar">
          <li><span>Toque em <strong>⋯</strong> (ou no ícone de bússola) num canto da tela.</span></li>
          <li><span>Escolha <strong>Abrir no navegador</strong> — ${ios ? "o Safari" : "o Chrome"}.</span></li>
          <li><span>Lá, toque de novo em <strong>Instalar no celular</strong>.</span></li>
        </ol>
        <button class="botao botao--fantasma" data-copiar type="button">Copiar o endereço</button>
      `,
    };
  }

  if (ios) {
    return {
      titulo: "Instalar no iPhone",
      corpo: `
        <ol class="passos-instalar">
          <li><span>Toque no botão <strong>Compartilhar</strong> ${ICONE_COMPARTILHAR}, na barra
            do Safari. Se ele não aparecer, toque antes em <strong>⋯</strong>.</span></li>
          <li><span>Role a lista pra baixo e toque em <strong>Adicionar à Tela de Início</strong>.</span></li>
          <li><span>Toque em <strong>Adicionar</strong>. Se aparecer <strong>Abrir como App</strong>,
            deixe ligado.</span></li>
        </ol>
        <p class="fraco">O ícone da Carlos Moto aparece junto dos seus outros apps. Abra sempre por ele.</p>
        <p class="fraco">No iPhone o app instalado guarda tudo separado do Safari, então ele pode
          pedir a chave de acesso uma vez, na primeira abertura. Não achou o botão? Abra este
          endereço no Safari.</p>
      `,
    };
  }

  if (android) {
    return {
      titulo: "Instalar no celular",
      corpo: `
        <ol class="passos-instalar">
          <li><span>Toque no menu <strong>⋮</strong>, no canto de cima do navegador.</span></li>
          <li><span>Toque em <strong>Instalar app</strong>. Em alguns celulares o nome é
            <strong>Adicionar à tela inicial</strong>.</span></li>
          <li><span>Confirme em <strong>Instalar</strong>.</span></li>
        </ol>
        <p class="fraco">O ícone da Carlos Moto aparece junto dos seus outros apps e abre sem a
          barra do navegador.</p>
      `,
    };
  }

  return {
    titulo: "Instalar no computador",
    corpo: `
      <p class="fraco">Este navegador não instala sozinho. Em dois cliques:</p>
      <ul class="lista-ajuda">
        <li><strong>Chrome ou Edge:</strong> menu <strong>⋮</strong> no canto superior direito →
          <strong>Transmitir, salvar e compartilhar</strong> → <strong>Instalar página como app</strong>.</li>
        <li><strong>Safari:</strong> menu <strong>Arquivo</strong> → <strong>Adicionar à Dock</strong>.</li>
      </ul>
      <p class="fraco">Depois de instalado ele abre em janela própria, sem barra de
        endereço, e continua funcionando sem internet.</p>
    `,
  };
}

export function explicar() {
  const { titulo, corpo } = _instrucoes();
  const modal = abrirModal(`
    <div class="modal-topo"><h3>${titulo}</h3></div>
    ${corpo}
    <div class="acoes-modal">
      <button class="botao" data-fechar type="button">Entendi</button>
    </div>
  `);

  modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));
  modal.querySelector("[data-copiar]")?.addEventListener("click", async (evento) => {
    const botao = evento.currentTarget;
    const endereco = `${location.origin}${location.pathname}`;
    try {
      await navigator.clipboard.writeText(endereco);
      botao.textContent = "Endereço copiado — cole no navegador";
    } catch {
      // Navegador de dentro de app costuma bloquear a área de transferência.
      // Mostrar o endereço deixa copiar na mão.
      botao.textContent = endereco;
    }
  });
}
