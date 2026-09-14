/** Formatação compartilhada pelos dois PWAs. */

const REAIS = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

/** 169900000 → "R$ 16.990,00". Dinheiro é inteiro em centavos em todo o sistema. */
export function reais(centavos) {
  return REAIS.format((centavos ?? 0) / 100);
}

export function hora(instante) {
  const d = instante instanceof Date ? instante : new Date(instante);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function doisDigitos(n) {
  return String(n).padStart(2, "0");
}

/** Uma `Date` como "AAAA-MM-DD" no relógio de quem está olhando, não em UTC. */
export function isoLocal(momento) {
  return `${momento.getFullYear()}-${doisDigitos(momento.getMonth() + 1)}-${doisDigitos(momento.getDate())}`;
}

/** Hoje, no relógio do balcão. `toISOString()` dá o dia em UTC — depois das
 * 21h em Brasília ele já devolve amanhã, e o campo de data nascia errado. */
export function hojeIso() {
  return isoLocal(new Date());
}

/**
 * "2026-10-10" → "10/10/2026".
 *
 * Um instante com hora ("…T01:30:00Z") é mostrado no dia local: uma venda
 * das 22h30 de Brasília já está gravada no dia seguinte em UTC. Uma data pura
 * (vencimento) nunca passa por `Date` — seria lida como meia-noite UTC e
 * voltaria um dia no Brasil.
 */
export function dataBr(iso) {
  const texto = String(iso);
  if (texto.includes("T")) {
    const d = new Date(texto);
    return `${doisDigitos(d.getDate())}/${doisDigitos(d.getMonth() + 1)}/${d.getFullYear()}`;
  }
  const [ano, mes, dia] = texto.split("-");
  return `${dia}/${mes}/${ano}`;
}

/** "52998224725" → "529.982.247-25". O banco guarda só os dígitos. */
export function cpf(digitos) {
  const d = String(digitos ?? "").replace(/\D/g, "");
  if (d.length !== 11) return digitos || "—";
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/** "11988887777" → "(11) 98888-7777"; "1133334444" → "(11) 3333-4444". */
export function telefone(digitos) {
  const d = String(digitos ?? "").replace(/\D/g, "");
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return digitos || "—";
}

export function km(valor) {
  return `${Number(valor).toLocaleString("pt-BR")} km`;
}

export function contar(n, singular, plural) {
  return `${n} ${n === 1 ? singular : plural}`;
}
