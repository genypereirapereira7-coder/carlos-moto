/**
 * A última resposta de cada tela, guardada pra quando o servidor não
 * responder.
 *
 * Sem isto o app abre sem internet e mostra tudo vazio: nenhuma moto, nenhum
 * cliente, financeiro zerado. Abrir vazio é pior do que não abrir — parece
 * que os dados sumiram.
 *
 * **O que é guardado:** só leitura (GET), e só o que deu certo. Escrita tem
 * outro caminho — a fila (`fila.js`).
 *
 * **A data anda junto, sempre.** O risco de mostrar dado velho não é o dado
 * velho: é o dono olhar um saldo de ontem achando que é de agora e decidir
 * em cima disso. Por isso nada sai daqui sem o horário em que foi guardado,
 * e a tela é obrigada a mostrá-lo.
 */

import { LOJA_CACHE, loja, resultado } from "./idb.js";

/** Os dois PWAs dividem a origem — e não podem dividir o cache. */
function _app() {
  return location.pathname.split("/").filter(Boolean)[0] || "raiz";
}

const _chave = (caminho) => `${_app()}|${caminho}`;

// Teto de segurança. Cada resposta é pequena, mas `/financeiro/mes` muda de
// chave a cada mês consultado e cresceria pra sempre.
const MAXIMO = 300;

export async function guardar(caminho, dados) {
  try {
    await resultado((await loja(LOJA_CACHE, "readwrite")).put({
      chave: _chave(caminho),
      caminho,
      app: _app(),
      dados,
      gravadoEm: new Date().toISOString(),
    }));
    await _podar();
  } catch (erro) {
    // Não deu pra guardar (cota cheia, aba anônima): a tela já tem o dado
    // fresco na mão, então isto não pode atrapalhar nada.
    console.warn("[cache] não deu pra guardar", caminho, erro);
  }
}

/** @returns {Promise<{dados: any, gravadoEm: string} | null>} */
export async function ler(caminho) {
  try {
    const item = await resultado((await loja(LOJA_CACHE, "readonly")).get(_chave(caminho)));
    return item ? { dados: item.dados, gravadoEm: item.gravadoEm } : null;
  } catch (erro) {
    console.warn("[cache] não deu pra ler", caminho, erro);
    return null;
  }
}

/**
 * Some com tudo. Chamado quando o dono sai: o próximo a entrar neste
 * computador não pode ver o estoque e o financeiro de quem saiu.
 */
export async function limpar() {
  try {
    const todos = await resultado((await loja(LOJA_CACHE, "readonly")).getAll());
    for (const item of todos.filter((i) => i.app === _app())) {
      await resultado((await loja(LOJA_CACHE, "readwrite")).delete(item.chave));
    }
  } catch (erro) {
    console.warn("[cache] não deu pra limpar", erro);
  }
}

async function _podar() {
  const todos = await resultado((await loja(LOJA_CACHE, "readonly")).getAll());
  const meus = todos.filter((i) => i.app === _app());
  if (meus.length <= MAXIMO) return;

  meus.sort((a, b) => a.gravadoEm.localeCompare(b.gravadoEm));
  for (const velho of meus.slice(0, meus.length - MAXIMO)) {
    await resultado((await loja(LOJA_CACHE, "readwrite")).delete(velho.chave));
  }
}
