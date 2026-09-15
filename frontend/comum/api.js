/**
 * Cliente da API da Carlos Moto.
 *
 * Três coisas moram aqui porque os dois PWAs precisam das três:
 *
 * 1. A sessão (tokens + quem está logado), guardada no localStorage — o
 *    celular do vendedor não pode deslogar sozinho no meio do expediente. O
 *    refresh dura um ano e desliza a cada renovação: a senha é digitada uma
 *    vez no aparelho e não é pedida de novo. Quem tira o acesso de alguém é o
 *    dono, pela tela de sessões, e não o relógio.
 * 2. A renovação do token de acesso, que dura 30 minutos, sem o vendedor
 *    perceber.
 * 3. A diferença entre "a internet caiu" (`ErroRede`) e "o servidor recusou"
 *    (`ErroApi`) — a tela mostra as duas de formas diferentes. É essa
 *    diferença que decide o que vai pra fila offline (`fila.js`): o que a
 *    rede engoliu sobe depois, o que o servidor recusou não adianta
 *    reenviar.
 */

import * as cache from "./cache.js";
import * as fila from "./fila.js";

// A chave leva o nome do PWA porque os dois rodam na mesma origem e
// dividiriam o mesmo localStorage. Sem isto, o dono que abre o app de vendas
// pra conferir uma coisa desloga do app dele.
const CHAVE_SESSAO = `carlosmoto.sessao.${_app()}`;

function _app() {
  return location.pathname.split("/").filter(Boolean)[0] || "raiz";
}

navigator.storage?.persist?.().catch(() => {});

/** O servidor recusou: 4xx/5xx com resposta. Reenviar não resolve. */
export class ErroApi extends Error {
  constructor(status, mensagem, corpo) {
    super(mensagem);
    this.name = "ErroApi";
    this.status = status;
    this.corpo = corpo;
  }
}

/** Não deu pra falar com o servidor. Reenviar depois costuma resolver. */
export class ErroRede extends Error {
  constructor(causa) {
    super("Sem conexão com o servidor");
    this.name = "ErroRede";
    this.causa = causa;
  }
}

/**
 * Guardado na fila: não deu pra falar com o servidor agora, mas o cadastro
 * não se perdeu. Quem chama `enviar` trata isto como "deu certo, só ainda não
 * subiu" — é diferente de `ErroRede`, que é a tentativa que se perdeu.
 */
export class ErroNaFila extends Error {
  constructor(rotulo) {
    super("Sem internet — guardado aqui, sobe quando a conexão voltar");
    this.name = "ErroNaFila";
    this.rotulo = rotulo;
  }
}

let sessao = _ler();
let renovacaoEmVoo = null;
const ouvintesSessao = new Set();
const ouvintesOrigem = new Set();

/**
 * Avisa de onde veio a última leitura: do servidor agora, ou da cópia
 * guardada aqui (e de quando ela é).
 *
 * É por aqui que a tela sabe que precisa dizer "sem conexão — mostrando os
 * dados das 14:30". Mostrar número velho sem essa faixa é o jeito mais fácil
 * de o dono decidir errado.
 *
 * @param {(origem: {deCache: boolean, gravadoEm?: string}) => void} callback
 */
export function aoMudarOrigem(callback) {
  ouvintesOrigem.add(callback);
  return () => ouvintesOrigem.delete(callback);
}

function _avisarOrigem(origem) {
  for (const ouvinte of ouvintesOrigem) {
    try {
      ouvinte(origem);
    } catch (erro) {
      console.warn("[api] ouvinte de origem falhou", erro);
    }
  }
}

// ------------------------------------------------------------------ sessão

export function sessaoAtual() {
  return sessao;
}

export function estaLogado() {
  return sessao !== null;
}

/** Avisa quando a sessão cai (refresh expirado ou revogado). */
export function aoPerderSessao(callback) {
  ouvintesSessao.add(callback);
  return () => ouvintesSessao.delete(callback);
}

/**
 * Liga este aparelho ao sistema com a chave de acesso. Uma vez só.
 *
 * Não existe senha em lugar nenhum: o que mantém o aparelho conectado daqui
 * em diante é o refresh token guardado aqui, renovado sozinho.
 */
export async function parear(chave) {
  const tokens = await pedir("POST", "/auth/parear", {
    chave,
    dispositivo: _dispositivo(),
  }, { autenticado: false });

  _gravar(tokens);
  return sessao;
}

export async function sair() {
  const refresh = sessao?.refresh;
  _gravar(null);
  // O próximo a entrar neste computador não pode ver o estoque e o
  // financeiro de quem saiu.
  await cache.limpar();
  if (refresh) {
    try {
      await pedir("POST", "/auth/sair", { refresh }, { autenticado: false });
    } catch { /* melhor esforço */ }
  }
}

export function renovarSessao() {
  return _renovar();
}

// ------------------------------------------------------------------ chamadas

/**
 * @param {object} [opcoes]
 * @param {boolean} [opcoes.autenticado=true]
 * @param {boolean} [opcoes.jaRenovou=false]
 * @param {boolean} [opcoes.avisarOrigem=true]  false no pré-aquecimento: ele
 *   roda sozinho em segundo plano e não pode acender a faixa de "sem
 *   conexão" por causa de um pedido que o dono nem fez.
 */
export async function pedir(metodo, caminho, corpo = null, opcoes = {}) {
  const { autenticado = true, jaRenovou = false, avisarOrigem = true } = opcoes;

  if (autenticado && !sessao) {
    throw new ErroApi(401, "Sem sessão");
  }

  const cabecalhos = {};
  if (corpo !== null) cabecalhos["Content-Type"] = "application/json";
  if (autenticado) cabecalhos["Authorization"] = `Bearer ${sessao.acesso}`;

  let resposta;
  try {
    resposta = await fetch(caminho, {
      method: metodo,
      headers: cabecalhos,
      body: corpo === null ? undefined : JSON.stringify(corpo),
    });
  } catch (erro) {
    // O servidor não respondeu. Numa leitura, a cópia guardada aqui é melhor
    // do que uma tela vazia — desde que fique dito que ela é de antes.
    if (metodo === "GET") {
      const guardado = await cache.ler(caminho);
      if (guardado) {
        if (avisarOrigem) _avisarOrigem({ deCache: true, gravadoEm: guardado.gravadoEm });
        return guardado.dados;
      }
    }
    throw new ErroRede(erro);
  }

  if (resposta.status === 401 && autenticado && !jaRenovou) {
    if (await _renovar()) {
      return pedir(metodo, caminho, corpo, { ...opcoes, jaRenovou: true });
    }
  }

  if (resposta.status === 204) return null;

  const texto = await resposta.text();
  const dados = texto ? _json(texto) : null;

  if (!resposta.ok) {
    throw new ErroApi(resposta.status, _mensagem(dados, resposta), dados);
  }

  if (metodo === "GET" && autenticado) {
    if (avisarOrigem) _avisarOrigem({ deCache: false });
    // Sem `await`: guardar é um favor pro futuro, e a tela não tem por que
    // esperar o disco pra mostrar o que já está na mão.
    cache.guardar(caminho, dados);
  }

  return dados;
}

/**
 * Envio que **não pode se perder** — cadastro, venda, gasto, parcela paga.
 *
 * Tenta mandar agora; se a rede não deixar, guarda na fila e avisa com
 * `ErroNaFila` em vez de `ErroRede`. A tela precisa tratar os dois de formas
 * diferentes: um é "não foi, tenta de novo", o outro é "foi guardado".
 *
 * Só para escrita. Leitura que falha não vai pra fila nenhuma: o dono quer o
 * dado agora, não amanhã.
 *
 * @param {string} rotulo  o que é isto, em português, pro dono reconhecer na
 *                         lista de espera ("Moto Honda Biz 125 · ABC1D23").
 */
export async function enviar(metodo, caminho, corpo = null, { rotulo } = {}) {
  try {
    return await pedir(metodo, caminho, corpo);
  } catch (erro) {
    if (!(erro instanceof ErroRede)) throw erro;
    if (!(await fila.disponivel())) throw erro;

    await fila.guardar({ metodo, caminho, corpo, rotulo });
    throw new ErroNaFila(rotulo);
  }
}

const jaAquecidos = new Set();

/**
 * Busca em segundo plano leituras que o dono provavelmente vai abrir, só pra
 * elas já estarem guardadas se a internet cair.
 *
 * Sem isto o estoque abre offline mas nenhuma moto abre: a lista tinha sido
 * lida, o histórico de cada uma não.
 *
 * Um pedido de cada vez e sem fazer barulho: é conveniência, não pode
 * competir com o que a tela está pedindo agora. Cada caminho é aquecido uma
 * vez por carregamento da página — o re-render do WebSocket acontece a toda
 * hora e viraria uma enxurrada de pedidos.
 */
export async function preAquecer(caminhos) {
  if (!sessao || !navigator.onLine) return;

  for (const caminho of caminhos) {
    if (jaAquecidos.has(caminho)) continue;
    jaAquecidos.add(caminho);
    try {
      await pedir("GET", caminho, null, { avisarOrigem: false });
    } catch {
      // Caiu a conexão no meio, ou a sessão expirou. Insistir nos outros só
      // gasta tempo; e este fica livre pra tentar de novo depois.
      jaAquecidos.delete(caminho);
      return;
    }
  }
}

let sincronizacaoEmVoo = null;

/**
 * Sobe o que está esperando. Pode ser chamada à vontade — de vários gatilhos
 * ao mesmo tempo — que só roda uma por vez: duas subidas em paralelo
 * mandariam o mesmo item duas vezes.
 */
export function sincronizarFila() {
  if (sincronizacaoEmVoo) return sincronizacaoEmVoo;

  sincronizacaoEmVoo = (async () => {
    // Sem sessão não há o que subir: todo envio voltaria 401 e a fila
    // inteira seria marcada como recusada por um motivo que passa sozinho
    // assim que o dono entrar de novo.
    if (!sessao) return { subiram: [], recusados: [], parou: true };

    try {
      return await fila.sincronizar(
        (metodo, caminho, corpo) => pedir(metodo, caminho, corpo),
        (erro) => erro instanceof ErroRede,
      );
    } finally {
      sincronizacaoEmVoo = null;
    }
  })();

  return sincronizacaoEmVoo;
}

// ------------------------------------------------------------------ internos

async function _renovar() {
  if (!sessao?.refresh) return false;

  if (renovacaoEmVoo) return renovacaoEmVoo;

  renovacaoEmVoo = (async () => {
    try {
      const tokens = await pedir(
        "POST", "/auth/renovar", { refresh: sessao.refresh }, { autenticado: false },
      );
      _gravar(tokens);
      return true;
    } catch (erro) {
      if (erro instanceof ErroRede) return false;
      _gravar(null);
      for (const ouvinte of ouvintesSessao) ouvinte();
      return false;
    } finally {
      renovacaoEmVoo = null;
    }
  })();

  return renovacaoEmVoo;
}

function _gravar(tokens) {
  if (tokens === null) {
    sessao = null;
    localStorage.removeItem(CHAVE_SESSAO);
    return;
  }
  sessao = {
    acesso: tokens.acesso,
    refresh: tokens.refresh,
    usuario_id: tokens.usuario_id,
    nome: tokens.nome,
    papel: tokens.papel,
  };
  localStorage.setItem(CHAVE_SESSAO, JSON.stringify(sessao));
}

function _ler() {
  try {
    const bruto = localStorage.getItem(CHAVE_SESSAO);
    if (!bruto) return null;
    const dados = JSON.parse(bruto);
    return dados?.acesso && dados?.refresh ? dados : null;
  } catch {
    return null;
  }
}

function _json(texto) {
  try {
    return JSON.parse(texto);
  } catch {
    return { detail: texto };
  }
}

function _mensagem(dados, resposta) {
  const detalhe = dados?.detail;
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe) && detalhe.length) {
    return detalhe.map((e) => e.msg).join("; ");
  }
  return `Erro ${resposta.status}`;
}

/**
 * Nome do aparelho na lista "Chave e aparelhos" — é por ele que o dono acha
 * qual desconectar quando um celular se perde.
 *
 * Saía do trecho entre parênteses do user agent, e o Chrome de hoje reduz
 * esse trecho de propósito: todo Android virava "K", e todo Mac "Intel Mac OS
 * X 10_15_7", até Mac que nem é Intel. Numa lista com dois "K", não dá pra
 * saber qual é o celular perdido.
 */
function _dispositivo() {
  const ua = navigator.userAgent;
  const toque = navigator.maxTouchPoints > 1;

  let aparelho = "Navegador";
  if (/iPhone|iPod/.test(ua)) aparelho = "iPhone";
  else if (/iPad/.test(ua) || (/Macintosh/.test(ua) && toque)) aparelho = "iPad";
  else if (/Android/.test(ua)) aparelho = /Mobile/.test(ua) ? "Celular Android" : "Tablet Android";
  else if (/Windows/.test(ua)) aparelho = "Computador Windows";
  else if (/Macintosh/.test(ua)) aparelho = "Mac";
  else if (/CrOS/.test(ua)) aparelho = "Chromebook";
  else if (/Linux/.test(ua)) aparelho = "Computador Linux";

  let navegador = "";
  if (/SamsungBrowser/.test(ua)) navegador = "Samsung Internet";
  else if (/EdgA?\/|EdgiOS/.test(ua)) navegador = "Edge";
  else if (/FxiOS|Firefox\//.test(ua)) navegador = "Firefox";
  else if (/CriOS|Chrome\//.test(ua)) navegador = "Chrome";
  else if (/Safari\//.test(ua)) navegador = "Safari";

  const instalado = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  return [aparelho, navegador, instalado ? "app instalado" : "", _app() === "dono" ? "" : _app()]
    .filter(Boolean)
    .join(" · ")
    .slice(0, 120);
}
