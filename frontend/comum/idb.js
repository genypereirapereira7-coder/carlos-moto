/**
 * O banco local do navegador, num lugar só.
 *
 * Duas coisas moram nele e precisam abrir o mesmo banco sem brigar pela
 * versão: a fila de envios que esperam internet (`fila.js`) e a cópia da
 * última resposta de cada tela (`cache.js`). Quando uma loja nova aparece
 * aqui, o `VERSAO` sobe e o `onupgradeneeded` cria só o que falta — quem já
 * tinha a fila cheia não perde nada.
 */

const BANCO = "carlosmoto";
const VERSAO = 2;

export const LOJA_FILA = "fila";
export const LOJA_CACHE = "cache";

let bancoEmVoo = null;

export function abrir() {
  if (bancoEmVoo) return bancoEmVoo;

  bancoEmVoo = new Promise((ok, falhou) => {
    const pedido = indexedDB.open(BANCO, VERSAO);

    pedido.onupgradeneeded = () => {
      const bd = pedido.result;
      // `contains` em cada uma: quem vem da versão 1 já tem a fila e só
      // precisa ganhar o cache.
      if (!bd.objectStoreNames.contains(LOJA_FILA)) {
        bd.createObjectStore(LOJA_FILA, { keyPath: "id" });
      }
      if (!bd.objectStoreNames.contains(LOJA_CACHE)) {
        bd.createObjectStore(LOJA_CACHE, { keyPath: "chave" });
      }
    };

    pedido.onsuccess = () => ok(pedido.result);
    pedido.onerror = () => falhou(pedido.error);
    // Outra aba segurando a versão antiga. Sem isto a promessa ficaria
    // pendurada pra sempre e a tela travaria esperando.
    pedido.onblocked = () => falhou(new Error("Banco local preso por outra aba aberta"));
  }).catch((erro) => {
    // Navegação privada, cota negada, perfil corrompido. Zerar a promessa
    // deixa a próxima tentativa abrir de novo em vez de herdar a falha.
    bancoEmVoo = null;
    throw erro;
  });

  return bancoEmVoo;
}

/** Envolve um pedido do IndexedDB numa promessa. */
export function resultado(pedido) {
  return new Promise((ok, falhou) => {
    pedido.onsuccess = () => ok(pedido.result);
    pedido.onerror = () => falhou(pedido.error);
  });
}

export async function loja(nome, modo) {
  const bd = await abrir();
  return bd.transaction(nome, modo).objectStore(nome);
}

/** O navegador deixa gravar? Em aba anônima costuma não deixar. */
export async function disponivel() {
  try {
    await abrir();
    return true;
  } catch {
    return false;
  }
}
