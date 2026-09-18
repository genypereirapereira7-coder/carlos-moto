/**
 * Campo de observação — a anotação livre que o dono escreve sobre uma moto,
 * um cliente ou uma venda.
 *
 * É o campo pro que não cabe em campo nenhum: "riscado no tanque", "prefere
 * WhatsApp", "volta dia 10 pra transferência". Fica no sistema pra ele —
 * **não sai em contrato nem comprovante**, justamente porque é anotação
 * interna e nem toda anotação é pro cliente ler.
 */

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

export function htmlCampoObservacao(valorAtual = "", dica = "") {
  return `
    <label class="campo campo--largo">Observação <span class="fraco">(opcional)</span>
      <textarea name="observacao" rows="3" maxlength="1000"
                placeholder="${escapar(dica || "Anotação livre — só pra você ver.")}">${escapar(valorAtual || "")}</textarea>
    </label>`;
}

/** O texto digitado, ou `null` quando está em branco (igual ao servidor). */
export function lerObservacao(dados) {
  const texto = (dados.get("observacao") || "").trim();
  return texto || null;
}

/** Regra única: cabe em 1000 caracteres. O `maxlength` já segura, isto é a rede. */
export function regrasObservacao(texto) {
  return [["observacao", !texto || texto.length <= 1000, "Observação muito longa (máx. 1000 caracteres)"]];
}
