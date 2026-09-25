/**
 * Registro do service worker e atualização automática do app.
 *
 * **Arquivo separado, e nunca guardado em cache** — as duas coisas de propósito:
 *
 * - Separado porque a política de segurança da página (`script-src 'self'`)
 *   proíbe script escrito dentro do HTML. Inline não roda, e o registro do
 *   service worker morre junto.
 * - Nunca em cache (ver `FORA_DO_CACHE` no `sw.js`) porque este é o código que
 *   conserta uma versão velha. Se ele próprio viesse do cache, ficaria preso
 *   dentro da versão que deveria consertar — foi exatamente o que aconteceu:
 *   a lógica estava no `app.js`, o cache servia o `app.js` antigo, e o dono
 *   não conseguia atualizar de jeito nenhum.
 *
 * O nome do arquivo também ajuda: um cache antigo não pode conter um arquivo
 * que não existia quando ele foi criado, então a primeira visita já o busca
 * da rede.
 */
(function () {
  if (!("serviceWorker" in navigator)) return;

  // Primeira visita não tem controlador: a troca ali é o service worker
  // nascendo, não versão nova. Recarregar seria um susto à toa.
  var tinhaControlador = Boolean(navigator.serviceWorker.controller);
  var recarregando = false;

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (!tinhaControlador || recarregando) return;
    recarregando = true;

    // Espera fechar o que estiver aberto. Recarregar no meio de uma venda
    // jogaria fora o que o dono acabou de digitar — e ele descobriria isso
    // com o cliente na frente.
    (function quandoNaoAtrapalhar() {
      if (document.querySelector(".sobreposicao")) {
        setTimeout(quandoNaoAtrapalhar, 1000);
        return;
      }
      location.reload();
    })();
  });

  navigator.serviceWorker.register("./sw.js").then(function (registro) {
    function procurar() {
      registro.update().catch(function () {});
      // Versão nova parada esperando: manda assumir agora.
      if (registro.waiting) registro.waiting.postMessage({ tipo: "assumir" });
    }
    procurar();
    // Toda vez que a aba volta pro foco. Sem isto o navegador só conferiria
    // de tempos em tempos, e o dono ficaria na versão velha sem saber.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") procurar();
    });
  }).catch(function (erro) {
    console.warn("[dono] service worker não registrou", erro);
  });
})();
