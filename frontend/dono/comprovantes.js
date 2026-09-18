/**
 * Comprovantes (tíquetes) e contratos de venda e de compra, prontos pra
 * imprimir.
 *
 * Tudo daqui é papel: o dono clica, vê a prévia numa janela e manda pra
 * impressora (ou salva em PDF pelo próprio diálogo de impressão do navegador,
 * que é o que resolve no celular). Nada é gravado no servidor — o documento é
 * montado a partir da venda ou da moto que já veio de lá.
 *
 * São quatro documentos:
 *   - Comprovante de VENDA  — o recibo que fica com o cliente que comprou.
 *   - Contrato de VENDA     — o contrato da moto vendida (com avalistas, se houver).
 *   - Comprovante de COMPRA — o recibo de quando a loja compra uma moto.
 *   - Contrato de COMPRA    — o contrato dessa compra.
 */

import { reais, dataBr, cpf as fmtCpf, telefone as fmtTel, km as fmtKm } from "../comum/formato.js";
import { abrirModal, fecharModal } from "./ui.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/**
 * Dados da loja pro cabeçalho. Ficam no navegador (localStorage) pra o dono
 * poder preencher CNPJ, endereço e telefone sem depender de tela nova — e por
 * padrão sai só o nome, sem inventar documento de ninguém.
 */
export function dadosLoja() {
  const padrao = {
    nome: "Monte São Motos",
    documento: "",
    endereco: "",
    telefone: "+55 69 99212-5902",
  };
  try {
    const salvo = JSON.parse(localStorage.getItem("carlosmoto_loja") || "{}");
    return { ...padrao, ...salvo };
  } catch {
    return padrao;
  }
}

// Contato de cada vendedor, pra sair no documento junto do nome de quem vendeu.
// São só estes dois; a chave é o nome sem acento e em minúscula.
const CONTATO_VENDEDOR = {
  "ze carlos": "+55 69 98442-0093",
  "dani": "+55 69 98487-0135",
};

function _semAcento(texto) {
  return String(texto ?? "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
}

function contatoVendedor(nome) {
  return CONTATO_VENDEDOR[_semAcento(nome)] || "";
}

// Nome do vendedor com o contato dele ao lado, quando conhecido.
function vendedorComContato(nome) {
  const contato = contatoVendedor(nome);
  return contato ? `${escapar(nome)} · ${escapar(contato)}` : escapar(nome);
}

function linhaLoja() {
  const l = dadosLoja();
  const extras = [
    l.documento && `CNPJ/CPF: ${escapar(l.documento)}`,
    l.endereco && escapar(l.endereco),
    l.telefone && `Tel.: ${escapar(l.telefone)}`,
  ].filter(Boolean);
  return `
    <header class="doc-topo">
      <h1>${escapar(l.nome)}</h1>
      ${extras.length ? `<p class="doc-sub">${extras.join(" · ")}</p>` : ""}
    </header>`;
}

// Bloco "Chave: valor" reaproveitado. Pula o que estiver vazio.
function linhas(pares) {
  return `<dl class="doc-dados">${pares
    .filter(([, valor]) => valor != null && valor !== "")
    .map(([rotulo, valor]) => `<div><dt>${escapar(rotulo)}</dt><dd>${valor}</dd></div>`)
    .join("")}</dl>`;
}

function assinatura(rotulo) {
  return `<div class="assinatura"><span class="linha-assinatura"></span><span>${escapar(rotulo)}</span></div>`;
}

function descricaoMoto(m) {
  const partes = [m.marca, m.modelo, m.ano].filter(Boolean).join(" ");
  return escapar(partes);
}

function blocoMoto(m) {
  return linhas([
    ["Veículo", descricaoMoto(m)],
    ["Cor", m.cor ? escapar(m.cor) : ""],
    ["Placa", m.placa ? escapar(m.placa) : ""],
    ["Chassi", m.chassi ? escapar(m.chassi) : ""],
    ["Km", m.km != null ? fmtKm(m.km) : ""],
  ]);
}

const ROTULO_FORMA = {
  A_VISTA: "À vista",
  PARCELADO: "Parcelado no carnê da loja",
  CHEQUE: "Cheque pré-datado",
  CARTAO: "Parcelado no cartão",
  FINANCIADO: "Financiado por banco",
  CONSORCIO: "Consórcio",
};

function tabelaParcelas(parcelas) {
  if (!parcelas || !parcelas.length) return "";
  const linhasHtml = parcelas.map((p) => `
    <tr><td>${p.numero}</td><td>${escapar(dataBr(p.vencimento))}</td><td class="dir">${escapar(reais(p.valor_centavos))}</td></tr>
  `).join("");
  const total = parcelas.reduce((s, p) => s + p.valor_centavos, 0);
  return `
    <table class="doc-tabela">
      <thead><tr><th>Parcela</th><th>Vencimento</th><th class="dir">Valor</th></tr></thead>
      <tbody>${linhasHtml}</tbody>
      <tfoot><tr><td colspan="2">Total das parcelas</td><td class="dir">${escapar(reais(total))}</td></tr></tfoot>
    </table>`;
}

function blocoAvalistas(avalistas) {
  if (!avalistas || !avalistas.length) return "";
  const itens = avalistas.map((a) => linhas([
    [`Avalista ${a.ordem}`, escapar(a.nome)],
    ["CPF", a.cpf ? escapar(fmtCpf(a.cpf)) : ""],
    ["Telefone", a.telefone ? escapar(fmtTel(a.telefone)) : ""],
    ["Endereço", a.endereco ? escapar(a.endereco) : ""],
  ])).join("");
  return `<h2>Avalistas</h2>${itens}`;
}

// ------------------------------------------------------------- VENDA

/** Recibo da venda — o que fica com o cliente. */
function htmlComprovanteVenda(venda) {
  const parcelado = venda.forma_pagamento === "PARCELADO";
  return `
    ${linhaLoja()}
    <h2 class="doc-titulo">Comprovante de venda</h2>
    <p class="doc-data">Emitido em ${escapar(dataBr(venda.data_venda))}</p>

    <h2>Comprador</h2>
    ${linhas([
      ["Nome", escapar(venda.cliente_nome)],
      ["CPF", venda.cliente_cpf ? escapar(fmtCpf(venda.cliente_cpf)) : ""],
      ["Telefone", venda.cliente_telefone ? escapar(fmtTel(venda.cliente_telefone)) : ""],
    ])}

    <h2>Motocicleta</h2>
    ${blocoMoto(venda.moto)}

    <h2>Pagamento</h2>
    ${linhas([
      ["Valor da venda", escapar(reais(venda.preco_venda_centavos))],
      ["Forma", ROTULO_FORMA[venda.forma_pagamento] || venda.forma_pagamento],
      ["Vendedor", vendedorComContato(venda.vendedor_nome)],
      venda.valor_entrada_centavos ? ["Entrada", escapar(reais(venda.valor_entrada_centavos))] : ["", ""],
      venda.juros_centesimos ? ["Juros da loja", `${escapar((venda.juros_centesimos / 100).toFixed(2).replace(".", ","))}%`] : ["", ""],
      parcelado ? ["Falta receber", escapar(reais(venda.saldo_devedor_centavos))] : ["", ""],
    ])}
    ${parcelado ? tabelaParcelas(venda.parcelas) : ""}

    <div class="assinaturas">
      ${assinatura(dadosLoja().nome)}
      ${assinatura(venda.cliente_nome)}
    </div>`;
}

/** Contrato da venda — moto, preço, parcelas e avalistas. */
function htmlContratoVenda(venda) {
  const loja = dadosLoja();
  const parcelado = venda.forma_pagamento === "PARCELADO";
  const m = venda.moto;
  const clausulaPagamento = parcelado
    ? `O pagamento será feito de forma parcelada no carnê da própria loja, conforme a tabela de parcelas
       abaixo, comprometendo-se o COMPRADOR a quitar cada parcela até a respectiva data de vencimento.`
    : `O pagamento é feito na modalidade <strong>${escapar((ROTULO_FORMA[venda.forma_pagamento] || "").toLowerCase())}</strong>,
       dando a VENDEDORA plena quitação do valor acordado.`;
  return `
    ${linhaLoja()}
    <h2 class="doc-titulo">Contrato de compra e venda de motocicleta</h2>
    <p class="doc-data">${escapar(dataBr(venda.data_venda))}</p>

    <p><strong>VENDEDORA:</strong> ${escapar(loja.nome)}${loja.documento ? `, inscrita sob ${escapar(loja.documento)}` : ""}${loja.telefone ? `, telefone ${escapar(loja.telefone)}` : ""}.</p>
    <p><strong>Vendedor responsável:</strong> ${vendedorComContato(venda.vendedor_nome)}.</p>
    <p><strong>COMPRADOR:</strong> ${escapar(venda.cliente_nome)}${venda.cliente_cpf ? `, CPF ${escapar(fmtCpf(venda.cliente_cpf))}` : ""}${venda.cliente_telefone ? `, telefone ${escapar(fmtTel(venda.cliente_telefone))}` : ""}.</p>

    <p>As partes acima têm entre si, justo e contratado, a compra e venda do veículo abaixo, que se regerá pelas cláusulas seguintes:</p>

    <h2>1. Objeto</h2>
    <p>A VENDEDORA vende ao COMPRADOR a motocicleta:</p>
    ${blocoMoto(m)}

    <h2>2. Preço e pagamento</h2>
    <p>O valor total da venda é de <strong>${escapar(reais(venda.preco_venda_centavos))}</strong>${
      venda.valor_entrada_centavos ? `, com entrada de <strong>${escapar(reais(venda.valor_entrada_centavos))}</strong>` : ""
    }. ${clausulaPagamento}${
      venda.juros_centesimos
        ? ` Sobre o saldo financiado incidem juros de <strong>${escapar((venda.juros_centesimos / 100).toFixed(2).replace(".", ","))}%</strong>, já embutidos nas parcelas abaixo.`
        : ""
    }</p>
    ${parcelado ? tabelaParcelas(venda.parcelas) : ""}

    <h2>3. Entrega e propriedade</h2>
    <p>O veículo é entregue no estado em que se encontra, conhecido e aceito pelo COMPRADOR. A transferência
       da propriedade junto ao órgão de trânsito é de responsabilidade do COMPRADOR, que assume também os
       encargos, multas e tributos a partir desta data.</p>

    ${parcelado ? `
    <h2>4. Reserva de domínio e inadimplência</h2>
    <p>Enquanto houver parcela em aberto, o não pagamento de qualquer parcela na data de vencimento poderá
       acarretar a cobrança do saldo devedor e demais medidas cabíveis, respondendo o COMPRADOR e os avalistas
       abaixo, solidariamente, pelo valor devido.</p>
    ${blocoAvalistas(venda.avalistas)}
    ` : ""}

    <p class="doc-fecho">Por estarem assim justas e contratadas, as partes assinam o presente instrumento.</p>

    <div class="assinaturas">
      ${assinatura(`VENDEDORA — ${loja.nome}`)}
      ${assinatura(`COMPRADOR — ${venda.cliente_nome}`)}
    </div>
    ${parcelado && venda.avalistas && venda.avalistas.length
      ? `<div class="assinaturas">${venda.avalistas.map((a) => assinatura(`Avalista ${a.ordem} — ${a.nome}`)).join("")}</div>`
      : ""}`;
}

// ------------------------------------------------------------- COMPRA

function fornecedorDaMoto(m) {
  return m.fornecedor_nome_efetivo || m.fornecedor_nome || "—";
}

/** Os dados de quem vendeu a moto pra loja — o que estiver preenchido. */
function blocoFornecedor(m) {
  const casado = m.fornecedor_casado === true;
  return linhas([
    ["Nome", escapar(fornecedorDaMoto(m))],
    ["CPF", m.fornecedor_cpf ? escapar(fmtCpf(m.fornecedor_cpf)) : ""],
    ["E-mail", m.fornecedor_email ? escapar(m.fornecedor_email) : ""],
    ["Contato", m.fornecedor_contato ? escapar(fmtTel(m.fornecedor_contato)) : ""],
    ["Estado civil", m.fornecedor_casado == null ? "" : (casado ? "Casado(a)" : "Solteiro(a)")],
    ["Cônjuge", casado && m.fornecedor_conjuge_nome ? escapar(m.fornecedor_conjuge_nome) : ""],
    ["Contato do cônjuge", casado && m.fornecedor_conjuge_contato ? escapar(fmtTel(m.fornecedor_conjuge_contato)) : ""],
  ]);
}

// Quando casado, o cônjuge assina junto a venda do veículo.
function assinaturasDaCompra(m) {
  const casado = m.fornecedor_casado === true && m.fornecedor_conjuge_nome;
  return `
    <div class="assinaturas">
      ${assinatura(`Vendedor — ${fornecedorDaMoto(m)}`)}
      ${assinatura(`Comprador — ${dadosLoja().nome}`)}
    </div>
    ${casado ? `<div class="assinaturas">${assinatura(`Cônjuge — ${m.fornecedor_conjuge_nome}`)}</div>` : ""}`;
}

/** Recibo da compra — quando a loja compra a moto de alguém. */
function htmlComprovanteCompra(m) {
  return `
    ${linhaLoja()}
    <h2 class="doc-titulo">Comprovante de compra</h2>
    ${m.data_compra ? `<p class="doc-data">Emitido em ${escapar(dataBr(m.data_compra))}</p>` : ""}

    <h2>Vendedor (quem entregou a moto)</h2>
    ${blocoFornecedor(m)}

    <h2>Motocicleta</h2>
    ${blocoMoto(m)}

    <h2>Pagamento</h2>
    ${linhas([
      ["Valor pago pela loja", m.valor_compra_centavos != null ? escapar(reais(m.valor_compra_centavos)) : "—"],
      ["Data da compra", m.data_compra ? escapar(dataBr(m.data_compra)) : ""],
    ])}

    ${assinaturasDaCompra(m)}`;
}

/** Contrato da compra — loja como compradora. */
function htmlContratoCompra(m) {
  const loja = dadosLoja();
  return `
    ${linhaLoja()}
    <h2 class="doc-titulo">Contrato de compra e venda de motocicleta</h2>
    ${m.data_compra ? `<p class="doc-data">${escapar(dataBr(m.data_compra))}</p>` : ""}

    <p><strong>COMPRADORA:</strong> ${escapar(loja.nome)}${loja.documento ? `, inscrita sob ${escapar(loja.documento)}` : ""}${loja.telefone ? `, telefone ${escapar(loja.telefone)}` : ""}.</p>
    <p><strong>VENDEDOR:</strong> ${escapar(fornecedorDaMoto(m))}${m.fornecedor_cpf ? `, CPF ${escapar(fmtCpf(m.fornecedor_cpf))}` : ""}${m.fornecedor_contato ? `, telefone ${escapar(fmtTel(m.fornecedor_contato))}` : ""}${m.fornecedor_email ? `, e-mail ${escapar(m.fornecedor_email)}` : ""}.</p>
    ${m.fornecedor_casado === true && m.fornecedor_conjuge_nome
      ? `<p><strong>CÔNJUGE DO VENDEDOR:</strong> ${escapar(m.fornecedor_conjuge_nome)}${m.fornecedor_conjuge_contato ? `, telefone ${escapar(fmtTel(m.fornecedor_conjuge_contato))}` : ""}, que assina em anuência à venda.</p>`
      : ""}

    <p>As partes têm entre si, justo e contratado, a compra e venda do veículo abaixo:</p>

    <h2>1. Objeto</h2>
    ${blocoMoto(m)}

    <h2>Dados do vendedor</h2>
    ${blocoFornecedor(m)}

    <h2>2. Preço</h2>
    <p>A COMPRADORA paga ao VENDEDOR o valor de
       <strong>${m.valor_compra_centavos != null ? escapar(reais(m.valor_compra_centavos)) : "—"}</strong>
       pela motocicleta descrita, dando plena quitação.</p>

    <h2>3. Responsabilidades</h2>
    <p>O VENDEDOR declara que o veículo é de sua propriedade, está livre de ônus e responde por débitos,
       multas e tributos anteriores a esta data. A COMPRADORA assume o veículo no estado em que se encontra.</p>

    <p class="doc-fecho">Por estarem assim justas e contratadas, as partes assinam o presente instrumento.</p>

    <div class="assinaturas">
      ${assinatura(`VENDEDOR — ${fornecedorDaMoto(m)}`)}
      ${assinatura(`COMPRADORA — ${loja.nome}`)}
    </div>
    ${m.fornecedor_casado === true && m.fornecedor_conjuge_nome
      ? `<div class="assinaturas">${assinatura(`CÔNJUGE — ${m.fornecedor_conjuge_nome}`)}</div>`
      : ""}`;
}

// ------------------------------------------------------- prévia + impressão

const ESTILO = `
  * { box-sizing: border-box; }
  body { font: 13px/1.5 "Segoe UI", system-ui, Arial, sans-serif; color: #111; margin: 0; padding: 24px; }
  .doc-topo { text-align: center; border-bottom: 2px solid #111; padding-bottom: 10px; margin-bottom: 16px; }
  .doc-topo h1 { margin: 0; font-size: 22px; letter-spacing: .5px; }
  .doc-sub { margin: 4px 0 0; font-size: 12px; color: #444; }
  .doc-titulo { font-size: 16px; text-transform: uppercase; letter-spacing: .5px; margin: 14px 0 2px; }
  .doc-data { color: #555; margin: 0 0 8px; font-size: 12px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .4px; border-bottom: 1px solid #ccc;
       padding-bottom: 3px; margin: 16px 0 8px; }
  p { margin: 6px 0; }
  .doc-dados { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 24px; margin: 4px 0 8px; }
  .doc-dados > div { display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px dotted #ddd; padding: 3px 0; }
  .doc-dados dt { color: #555; margin: 0; }
  .doc-dados dd { margin: 0; font-weight: 600; text-align: right; }
  .doc-tabela { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }
  .doc-tabela th, .doc-tabela td { border: 1px solid #ccc; padding: 5px 8px; text-align: left; }
  .doc-tabela .dir { text-align: right; }
  .doc-tabela tfoot td { font-weight: 700; background: #f3f3f3; }
  .doc-fecho { margin-top: 16px; }
  .assinaturas { display: flex; gap: 32px; margin-top: 40px; page-break-inside: avoid; }
  .assinatura { flex: 1; text-align: center; font-size: 12px; }
  .linha-assinatura { display: block; border-top: 1px solid #111; margin-bottom: 4px; height: 1px; }
  @media print { body { padding: 0; } }
`;

/** Manda o documento pra impressora via um iframe isolado (não mexe no app). */
function imprimir(titulo, corpoHtml) {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow.document;
  doc.open();
  doc.write(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
    <title>${escapar(titulo)}</title><style>${ESTILO}</style></head><body>${corpoHtml}</body></html>`);
  doc.close();

  const win = iframe.contentWindow;
  const limpar = () => setTimeout(() => iframe.remove(), 800);
  win.onafterprint = limpar;
  // Espera o layout assentar antes de chamar o diálogo (sem isso o Safari
  // às vezes imprime a folha em branco).
  setTimeout(() => {
    try {
      win.focus();
      win.print();
    } catch {
      iframe.remove();
    }
  }, 250);
}

/** Abre a prévia do documento com os botões Imprimir e Fechar. */
function abrirDocumento(titulo, corpoHtml) {
  const modal = abrirModal(`
    <div class="modal-topo">
      <h3>${escapar(titulo)}</h3>
      <div class="acoes-linha">
        <button class="botao" id="imprimir-doc" type="button">Imprimir</button>
        <button class="botao botao--fantasma" data-fechar type="button">Fechar</button>
      </div>
    </div>
    <div class="folha-previa">${corpoHtml}</div>
  `);
  modal.classList.add("modal--folha");

  modal.querySelector("[data-fechar]").addEventListener("click", () => fecharModal(modal));
  modal.querySelector("#imprimir-doc").addEventListener("click", () => imprimir(titulo, corpoHtml));
}

// ------------------------------------------------------------- API pública

export function imprimirComprovanteVenda(venda) {
  abrirDocumento("Comprovante de venda", htmlComprovanteVenda(venda));
}
export function imprimirContratoVenda(venda) {
  abrirDocumento("Contrato de venda", htmlContratoVenda(venda));
}
export function imprimirComprovanteCompra(moto) {
  abrirDocumento("Comprovante de compra", htmlComprovanteCompra(moto));
}
export function imprimirContratoCompra(moto) {
  abrirDocumento("Contrato de compra", htmlContratoCompra(moto));
}
