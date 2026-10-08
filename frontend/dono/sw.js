/**
 * Service worker do painel do Dono.
 *
 * Só garante que o app **abra** sem internet. Nada de API entra em cache —
 * ver a mesma decisão em `frontend/vendas/sw.js`. O que o dono cadastra sem
 * conexão não passa por aqui: fica no IndexedDB (`comum/fila.js`) e sobe
 * sozinho depois. Falta ainda poder **consultar** offline.
 *
 * Ao mexer nos arquivos do app, suba o VERSAO: é ele que descarta o cache
 * antigo e evita o PWA congelado numa versão antiga.
 */

const VERSAO = "v62";
const CACHE = `carlosmoto-dono-${VERSAO}`;

const CASCA = [
  "./",
  "./index.html",
  "./app.js",
  "./ui.js",
  "./validacao.js",
  "./fila-ui.js",
  "./acesso.js",
  "./instalar.js",
  "./dados-motos.js",
  "./marca-modelo.js",
  "./comprovantes.js",
  "./conjuge.js",
  "./observacao.js",
  "./endereco.js",
  "./documentos.js",
  "./dono.css",
  "./documento.css",
  "./manifest.json",
  "./icones/icone-192.png",
  "./icones/icone-512.png",
  "./icones/icone-maskable-512.png",
  "./icones/apple-touch-icon.png",
  "./telas/motos.js",
  "./telas/clientes.js",
  "./telas/vender.js",
  "./telas/parcelas.js",
  "./telas/financeiro.js",
  "./telas/dados.js",
  "../comum/api.js",
  "../comum/fila.js",
  "../comum/cache.js",
  "../comum/idb.js",
  "../comum/formato.js",
  "../comum/ws.js",
  "../comum/estilo.css",
];

// `versao.js` é o código que conserta uma versão velha — guardá-lo no cache
// seria prendê-lo dentro da versão que ele deveria consertar. Sempre da rede.
const FORA_DO_CACHE = ["/dono/versao.js"];

const CAMINHOS_API = [
  "/auth", "/motos", "/vendas", "/clientes", "/parcelas", "/financeiro",
  "/usuarios", "/relatorios", "/health", "/ws", "/dados",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      await Promise.all(
        CASCA.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch((erro) => {
            console.warn("[sw] não cacheou", url, erro);
          }),
        ),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    (async () => {
      for (const nome of await caches.keys()) {
        if (nome.startsWith("carlosmoto-dono-") && nome !== CACHE) {
          await caches.delete(nome);
        }
      }
      await self.clients.claim();
    })(),
  );
});

// A página pede pra versão nova assumir na hora. O `skipWaiting` do install
// já resolve o caso normal; isto cobre o service worker que ficou parado
// esperando — sem ele, o dono continuaria na versão velha sem entender por quê.
self.addEventListener("message", (evento) => {
  if (evento.data?.tipo === "assumir") self.skipWaiting();
});

self.addEventListener("fetch", (evento) => {
  const { request } = evento;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (CAMINHOS_API.some((p) => url.pathname === p || url.pathname.startsWith(`${p}/`))) {
    return;
  }
  if (FORA_DO_CACHE.includes(url.pathname)) return;

  if (request.mode === "navigate") {
    evento.respondWith(
      (async () => {
        try {
          const resposta = await fetch(request);
          const cache = await caches.open(CACHE);
          cache.put("./index.html", resposta.clone());
          return resposta;
        } catch {
          return (await caches.match("./index.html")) ?? Response.error();
        }
      })(),
    );
    return;
  }

  evento.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const guardado = await cache.match(request);

      const daRede = fetch(request)
        .then((resposta) => {
          if (resposta.ok) cache.put(request, resposta.clone());
          return resposta;
        })
        .catch(() => null);

      return guardado ?? (await daRede) ?? Response.error();
    })(),
  );
});
