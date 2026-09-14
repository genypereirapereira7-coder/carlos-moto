/**
 * Fila de envios que ficaram esperando a internet voltar.
 *
 * Quando o dono cadastra uma moto sem conexão, o trabalho dele não pode
 * sumir junto com a mensagem de erro. O envio vai pro IndexedDB do próprio
 * computador e sobe sozinho quando a rede volta.
 *
 * **Por que IndexedDB e não localStorage:** o localStorage é síncrono (trava
 * a tela), tem limite baixo, e guarda só texto. A fila precisa sobreviver a
 * fechar o navegador e a ficar dias esperando, com o corpo inteiro de cada
 * envio dentro.
 *
 * **A ordem importa.** Os envios sobem na ordem em que foram feitos, um de
 * cada vez. Se um gasto de uma moto subisse antes da moto, o servidor
 * responderia 404 e o gasto seria descartado como impossível.
 *
 * **Reenvio não pode cobrar duas vezes.** Um envio que o servidor recebeu mas
 * cuja resposta se perdeu volta pra fila e sobe de novo. Quem garante que
 * isso não vira dois gastos ou duas vendas é o `id_cliente` que vai no corpo
 * (ver `backend/tests/test_reenvio_nao_duplica.py`); aqui a fila só cuida de
 * não perder nada e de não embaralhar a ordem.
 */

import { LOJA_FILA, disponivel as bancoDisponivel, loja, resultado } from "./idb.js";

/** Qual dos dois PWAs guardou o item — eles dividem a mesma origem. */
function _app() {
  return location.pathname.split("/").filter(Boolean)[0] || "raiz";
}

const ouvintes = new Set();

/** Avisa quando a fila muda, pra tela redesenhar o contador. */
export function aoMudar(callback) {
  ouvintes.add(callback);
  return () => ouvintes.delete(callback);
}

function _avisar() {
  for (const ouvinte of ouvintes) {
    try {
      ouvinte();
    } catch (erro) {
      console.warn("[fila] ouvinte falhou", erro);
    }
  }
}

const _loja = (modo) => loja(LOJA_FILA, modo);
const _resultado = resultado;

/** A fila funciona neste navegador? Em aba anônima costuma não funcionar. */
export const disponivel = bancoDisponivel;

// ---------------------------------------------------------------- leitura

/** Os envios deste app esperando, do mais antigo pro mais novo. */
export async function listar() {
  try {
    const todos = await _resultado((await _loja("readonly")).getAll());
    return todos
      .filter((item) => item.app === _app())
      .sort((a, b) => a.criadoEm.localeCompare(b.criadoEm));
  } catch (erro) {
    console.warn("[fila] não deu pra ler", erro);
    return [];
  }
}

export async function contar() {
  return (await listar()).length;
}

/** Só os que ainda vão subir — os recusados esperam o dono decidir. */
export async function pendentes() {
  return (await listar()).filter((item) => !item.recusado);
}

// ---------------------------------------------------------------- escrita

export async function guardar({ metodo, caminho, corpo, rotulo }) {
  const item = {
    id: crypto.randomUUID(),
    app: _app(),
    metodo,
    caminho,
    corpo,
    rotulo,
    criadoEm: new Date().toISOString(),
    tentativas: 0,
    ultimoErro: null,
    recusado: false,
  };
  await _resultado((await _loja("readwrite")).add(item));
  _avisar();
  return item;
}

export async function remover(id) {
  await _resultado((await _loja("readwrite")).delete(id));
  _avisar();
}

async function _gravar(item) {
  await _resultado((await _loja("readwrite")).put(item));
  _avisar();
}

/** Some com tudo que este app deixou na fila — inclusive o que foi recusado. */
export async function limpar() {
  for (const item of await listar()) {
    await _resultado((await _loja("readwrite")).delete(item.id));
  }
  _avisar();
}

// ------------------------------------------------------------ sincronizar

/**
 * Sobe a fila, um item de cada vez, parando na primeira falha de rede — se a
 * internet caiu de novo, insistir nos outros só gasta tempo e bagunça a
 * ordem.
 *
 * @param {(metodo, caminho, corpo) => Promise} enviar  quem fala com a API
 * @param {(erro) => boolean} eDeRede  se o erro foi "não deu pra falar"
 * @returns {Promise<{subiram: array, recusados: array, parou: boolean}>}
 */
export async function sincronizar(enviar, eDeRede) {
  const subiram = [];
  const recusados = [];

  for (const item of await pendentes()) {
    try {
      await enviar(item.metodo, item.caminho, item.corpo);
      await remover(item.id);
      subiram.push(item);
    } catch (erro) {
      // Rede caiu, sessão expirou, servidor com problema: nenhum dos três é
      // culpa do que está sendo enviado, e todos passam sozinhos. O item
      // continua na fila e a subida para por aqui.
      if (eDeRede(erro) || erro.status === 401 || erro.status >= 500) {
        item.tentativas += 1;
        item.ultimoErro = erro.message;
        await _gravar(item);
        return { subiram, recusados, parou: true };
      }

      // 4xx que não muda com o tempo (409, 422, 404, 403). Reenviar não
      // resolve, e apagar calado esconderia do dono um cadastro que ele deu
      // por feito.
      //
      // O 409 fica aqui de propósito, e não tratado como "já subiu". Ele é
      // ambíguo: pode ser o reenvio esbarrando na placa que a primeira
      // tentativa gravou — ou uma placa digitada duas vezes, ou uma moto que
      // alguém já vendeu enquanto isto esperava. Só o dono sabe qual dos
      // três, e nenhum deles justifica sumir com o lançamento.
      item.recusado = true;
      item.ultimoErro = erro.message;
      await _gravar(item);
      recusados.push(item);
    }
  }

  return { subiram, recusados, parou: false };
}
