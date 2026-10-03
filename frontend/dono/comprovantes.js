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
import { enderecoEmUmaLinha } from "./endereco.js";
import { dataNascimentoBr } from "./documentos.js";

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
  // Os dados que saem no contrato e na nota promissória, como estão nos
  // documentos que a loja já usa em papel.
  const padrao = {
    nome: "MONTE SIÃO MOTOS",
    documento: "27.415.529/0001-22",
    endereco: "AV NORTE SUL, 4097 - ROLIM DE MOURA - RO",
    cidade: "ROLIM DE MOURA",
    uf: "RO",
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
      ["RG", venda.cliente_endereco?.rg ? escapar(venda.cliente_endereco.rg) : ""],
      ["Nascimento", escapar(dataNascimentoBr(venda.cliente_endereco?.nascimento))],
      ["Telefone", venda.cliente_telefone ? escapar(fmtTel(venda.cliente_telefone)) : ""],
      ["E-mail", venda.cliente_endereco?.email ? escapar(venda.cliente_endereco.email) : ""],
      ["Endereço", escapar(enderecoEmUmaLinha(venda.cliente_endereco))],
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

/**
 * Contrato de compra e venda a prazo — o mesmo documento que a loja já usa em
 * papel, preenchido pelo sistema.
 *
 * O texto das cláusulas é o da Monte Sião Motos e **não se mexe**: juros de
 * mora de 0,23% ao dia, retomada do veículo com duas parcelas em atraso,
 * multa de 20% por desistência. O que muda de um contrato pro outro são só os
 * dados — comprador, moto, valores, parcelas e avalistas.
 */
function htmlContratoVenda(venda) {
  const loja = dadosLoja();
  const e = venda.cliente_endereco || {};
  const m = venda.moto;
  const parcelas = venda.parcelas || [];
  const entrada = venda.valor_entrada_centavos || 0;
  const avalistas = venda.avalistas || [];

  // A "fatura" é o número que amarra as parcelas umas às outras e à nota —
  // no papel antigo era o número do pedido com a série na frente.
  const fatura = numeroDaFatura(venda);

  const endereco = [e.endereco, e.numero].filter(Boolean).join(", ");

  return `
    <h2 class="doc-titulo doc-titulo--caixa">CONTRATO DE COMPRA E VENDA A PRAZO</h2>

    <h3 class="doc-secao">1 - Dados do Comprador</h3>
    <div class="doc-grade">
      <div><span>Nome:</span> <strong>${escapar(venda.cliente_nome)}</strong></div>
      <div><span>Código:</span> ${String(venda.cliente_id).padStart(5, "0")}</div>
      <div><span>Endereço:</span> ${escapar(endereco || "—")}</div>
      <div><span>Bairro:</span> ${escapar(e.bairro || "—")}</div>
      <div><span>Cidade:</span> ${escapar(e.cidade || "—")}</div>
      <div><span>Estado:</span> ${escapar(e.uf || "—")}</div>
      <div><span>CNPJ/CPF:</span> ${venda.cliente_cpf ? escapar(fmtCpf(venda.cliente_cpf)) : "—"}</div>
      <div><span>Inscrição/RG:</span> ${escapar(e.rg || "—")}</div>
    </div>

    <h3 class="doc-secao">2 - Dados da Compra</h3>
    <div class="doc-grade">
      <div><span>Valor da Compra:</span> <strong>${reais(venda.preco_venda_centavos)}</strong></div>
      <div><span>Nota Fiscal/Cupom Fiscal:</span> ${escapar(fatura.documento)}</div>
      <div><span>Valor da Entrada:</span> ${reais(entrada)}</div>
      <div><span>Emissão:</span> ${escapar(dataBr(venda.data_venda))}</div>
    </div>

    <h3 class="doc-secao">3 - Desdobramento das Parcelas</h3>
    ${parcelas.length ? `
      <table class="doc-tabela">
        <thead><tr><th>Fatura</th><th>PC</th><th>Vencimento</th><th>Valor</th></tr></thead>
        <tbody>${parcelas.map((p) => `
          <tr>
            <td>${escapar(fatura.numero)}</td>
            <td>${String(p.numero).padStart(2, "0")}</td>
            <td>${escapar(dataBr(p.vencimento))}</td>
            <td class="direita">${reais(p.valor_centavos)}</td>
          </tr>`).join("")}</tbody>
      </table>` : '<p class="fraco">Venda à vista — sem parcelas.</p>'}

    <h3 class="doc-secao">4 - Itens da Venda</h3>
    <table class="doc-tabela">
      <tbody>
        <tr>
          <td>${String(m.id).padStart(6, "0")}</td>
          <td>${escapar(`${m.modelo} ${m.ano}${m.placa ? ` ${m.placa}` : ""}`)}</td>
          <td>${escapar(m.marca)}</td>
          <td class="direita">1,00</td>
          <td class="direita">${reais(venda.preco_venda_centavos)}</td>
          <td class="direita">${reais(venda.preco_venda_centavos)}</td>
        </tr>
      </tbody>
    </table>

    ${venda.observacao ? `<p class="doc-livre">${escapar(venda.observacao)}</p>` : ""}
    ${avalistas.length ? `<p class="doc-livre">${avalistas.map((a) => (
      `AVALISTA ${a.ordem} : ${escapar(a.nome)}`
      + (a.cpf ? ` CPF: ${escapar(fmtCpf(a.cpf))}` : "")
      + (a.telefone ? ` ${escapar(fmtTel(a.telefone))}` : "")
    )).join("<br />")}</p>` : ""}

    <p>Por este instrumento particular de contrato de compra e venda, a empresa ${escapar(loja.nome)}
    ${loja.documento ? `inscrita no CNPJ nº ${escapar(loja.documento)}, ` : ""}${loja.endereco ? `estabelecida na ${escapar(loja.endereco)}` : ""}
    doravante denominada ${escapar(loja.nome)} e o(a) COMPRADOR acima qualificado, tem justo e contratado o seguinte:</p>

    <p>1ª - A ${escapar(loja.nome)} abre ao(a) COMPRADOR(A) um crédito para compra de mercadorias em seu estabelecimento.</p>
    <p>2ª - o veiculo, objeto deste contrato é usado apresentando desgate natural decorrente do tempo, ja visto e inspecionado
    pelo comprador, oqual tomou ciência de suas condições do estado de conservação.
    a transferência da propriedade do veiculo por conta do COMPRADOR.</p>
    <p>3ª - Do valor contratado poderá a ${escapar(loja.nome)} emitir duplicata(s) e/ou carnê(s) para pagamento(s) em única,
    ou diversas prestações mensais e consecutivas, sendo que o(a) COMPRADOR(A) obriga-se a pagar dentro do(s) prazo(s)
    a(s) prestação(ões), no estabelecimento da ${escapar(loja.nome)} e/ou boleto bancário caso seja emitido.</p>
    <p>4ª - o vendedor se responsabiliza pelo documento do veiculo e multas do mesmo dessa data para traz, mais não
    responsabilizará pelos danos causados no veiculo por negligência do COMPRADOR, e por problemas decorrentes.</p>
    <p>5ª - A falta do pagamento, até o respectivo vencimento, das obrigações contraídas pelo(a) COMPRADOR(A) ficará ciente
    que atraso de 2 duas parcela terá seu veiculo retido ao pátio da loja até o respectivo pagamento das parcela em atraso.
    ${escapar(loja.nome)}</p>
    <p>6ª - Havendo a inadimplência do(a) COMPRADOR(A), este se obrigará, além do débito principal, a encargos correspondentes
    a juros de mora de 0,23% (zero vírgula vinte e três por cento) ao dia, correção monetária, despesas de cobrança,
    honorários advocatício no importe de 10% (dez por cento) no caso de cobrança extrajudicial e, de 20% (vinte por centro)
    no caso de cobrança judicial, custas e demais despesas, que serão considerados vencidos, líquidos, certos e exigíveis
    para efeito de execução na forma da legislação em vigor.</p>
    <p>7ª - Ocorrendo o caso de à ${escapar(loja.nome)} aceitar o(s) pagamento(s) de prestação(ões) vencida(s), será este ato
    considerado simples liberdade da mesma, sem que constitua novação ou remuneração ou renuncia de direitos decorrentes
    deste contrato, tampouco tido como dispensada de multa contratual, juros de mora, despesas de cobrança ou demais encargos.</p>
    <p>8ª - caso haja desistência de qualquer das partes, fica convencionado uma multa equivalente 20% (vinte por cento)
    do valor do contrato.</p>
    <p>9ª - Fica eleito o foro da Comarca do local de celebração do presente contrato, com renuncia das partes de qualquer
    outro, por mais privilegiado que seja, para dirimir as questões decorrentes deste instrumento.</p>
    <p>E, por assim se acharem ajustados e contratados, acompanhados de duas testemunhas, firmam o presente instrumento
    em duas vias.</p>

    <p class="doc-local">Local ${escapar(loja.cidade || "")} , ${escapar(porExtensoData(venda.data_venda))} .</p>

    <div class="assinaturas">
      ${assinatura("COMPRADOR(A)/DEPOSITÁRIO")}
      ${assinatura(loja.nome)}
    </div>
    <div class="assinaturas">
      ${assinatura("AVALISTA:<br />RG:<br />CPF:")}
    </div>`;
}

/** `22 de Setembro de 2026` — como vai escrito no rodapé do contrato. */
function porExtensoData(valor) {
  const MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  const texto = String(valor || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto)) return "";
  const [a, m, d] = texto.split("-").map(Number);
  return `${d} de ${MESES[m - 1]} de ${a}`;
}

/**
 * O número que amarra contrato, carnê e nota promissória.
 *
 * No sistema antigo era a "fatura": série + número do pedido, e cada parcela
 * saía como `0100006462-02`. Aqui o papel é o mesmo, montado a partir do id
 * da venda — o cliente confere o número do papel com o do sistema.
 */
function numeroDaFatura(venda) {
  const documento = String(venda.numero_venda || "").trim()
    || String(venda.id || "").replace(/\D/g, "").slice(0, 6).padStart(6, "0");
  return { documento, numero: `01${documento.padStart(8, "0")}` };
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

// O estilo dos documentos mora em `documento.css` — arquivo de verdade, não
// `<style>` embutido, porque o app roda com `style-src 'self'` e estilo
// embutido é bloqueado. A prévia e a impressão carregam o mesmo arquivo.
const FOLHA_DE_ESTILO = "/dono/documento.css";


/**
 * A página inteira do documento — é ela que vai pra impressora **e** pra
 * prévia na tela.
 *
 * As duas usando a mesma função é o que garante que o que o dono vê é o que
 * sai no papel. Antes a prévia era o HTML solto dentro do app, sem o estilo
 * do documento: a nota promissória aparecia como texto empilhado, sem o
 * desenho do talão, e só ficava certa depois de mandar imprimir.
 */
function paginaDoDocumento(titulo, corpoHtml) {
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
    <title>${escapar(titulo)}</title>
    <link rel="stylesheet" href="${FOLHA_DE_ESTILO}"></head><body>${corpoHtml}</body></html>`;
}

/** Manda o documento pra impressora via um iframe isolado (não mexe no app). */
function imprimir(titulo, corpoHtml) {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow.document;
  doc.open();
  doc.write(paginaDoDocumento(titulo, corpoHtml));
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
    <iframe class="folha-previa" title="Prévia do documento"></iframe>
  `);
  modal.classList.add("modal--folha");

  // `srcdoc` e não `innerHTML`: dentro do iframe o documento tem o CSS dele e
  // nada do app vaza pra dentro (nem o contrário).
  const folha = modal.querySelector(".folha-previa");
  folha.srcdoc = paginaDoDocumento(titulo, corpoHtml);
  // Cresce até caber o documento: iframe tem altura fixa por padrão, e um
  // contrato de 15 parcelas ficava cortado com barra de rolagem dentro.
  folha.addEventListener("load", () => {
    const doc = folha.contentDocument;
    if (doc) folha.style.height = `${doc.documentElement.scrollHeight + 24}px`;
  });

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

// ---------------------------------------------------------------- extenso

const UNIDADES = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
  "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"];
const DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"];
const CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
  "seiscentos", "setecentos", "oitocentos", "novecentos"];

function ate999(n) {
  if (n === 100) return "cem";
  const c = Math.floor(n / 100);
  const d = Math.floor((n % 100) / 10);
  const u = n % 10;
  const partes = [];
  if (c) partes.push(CENTENAS[c]);
  if (n % 100 < 20) {
    if (n % 100) partes.push(UNIDADES[n % 100]);
  } else {
    partes.push(DEZENAS[d]);
    if (u) partes.push(UNIDADES[u]);
  }
  return partes.join(" e ");
}

/**
 * O valor por extenso, como manda a nota promissória: "OITOCENTOS REAIS".
 *
 * A nota promissória é título de crédito — o valor em palavras é o que vale
 * se divergir do número, então ele não pode ser "aproximadamente".
 */
export function porExtenso(centavos) {
  const total = Math.round(Math.abs(centavos));
  const reaisInteiros = Math.floor(total / 100);
  const cents = total % 100;
  const blocos = [];

  const escala = [
    [1_000_000_000, "bilhão", "bilhões"],
    [1_000_000, "milhão", "milhões"],
    [1_000, "mil", "mil"],
  ];
  let resto = reaisInteiros;
  for (const [valor, singular, plural] of escala) {
    const quantos = Math.floor(resto / valor);
    if (quantos) {
      blocos.push(valor === 1_000 && quantos === 1 ? "mil" : `${ate999(quantos)} ${quantos === 1 ? singular : plural}`);
      resto %= valor;
    }
  }
  // O "e" antes do último bloco só entra quando ele é menor que cem ou uma
  // centena redonda: "mil e duzentos", mas "mil duzentos e trinta e quatro".
  const ultimo = resto ? ate999(resto) : "";
  let inteiro = blocos.join(" e ");
  if (ultimo) {
    inteiro = inteiro
      ? `${inteiro}${resto < 100 || resto % 100 === 0 ? " e " : " "}${ultimo}`
      : ultimo;
  }

  const partes = [];
  if (reaisInteiros) {
    partes.push(`${inteiro} ${reaisInteiros === 1 ? "real" : "reais"}`);
  }
  if (cents) {
    partes.push(`${ate999(cents)} ${cents === 1 ? "centavo" : "centavos"}`);
  }
  if (!partes.length) return "zero reais";
  return partes.join(" e ");
}

// -------------------------------------------------- nota promissória

/**
 * Uma nota promissória por parcela — o mesmo papel que a loja já imprime.
 *
 * É título de crédito, não recibo: quem promete pagar é o **cliente** (o
 * emitente), e a loja é quem recebe. Por isso o valor vai também por extenso
 * — se divergir do número, é a palavra que vale.
 */
function htmlNotaPromissoria(venda, parcela, fatura) {
  const loja = dadosLoja();
  const e = venda.cliente_endereco || {};
  const endereco = [e.endereco, e.numero].filter(Boolean).join(",");
  const praca = `${loja.cidade || ""}${loja.uf ? `  -${loja.uf}` : ""}`;
  // Sem "R$" e sem milhar: é como está impresso no talão.
  const valor = (parcela.valor_centavos / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  const extenso = porExtenso(parcela.valor_centavos).toUpperCase();

  return `
    <div class="promissoria">
      <div class="pr-selo"><span>REPÚBLICA FEDERATIVA DO BRASIL</span></div>
      <div class="pr-corpo">

        <div class="pr-cabecalho">
          <div class="pr-numero"><em>Número</em> <span class="pr-caixa-clara">${escapar(fatura.numero)} -${String(parcela.numero).padStart(2, "0")}</span></div>
          <div class="pr-direita">
            <div class="pr-par"><em>Vencimento</em><span class="pr-caixa">${escapar(dataBr(parcela.vencimento))}</span></div>
            <div class="pr-par"><em>Valor</em><span class="pr-caixa pr-valor">${escapar(valor)}</span></div>
          </div>
        </div>

        <p class="pr-aos">A(os) ${escapar(porExtensoDataMinuscula(parcela.vencimento))}</p>

        <div class="pr-titulo">
          <em>pagarei por está única via de</em>
          <strong>NOTA PROMISSÓRIA</strong>
          <em>a</em>
        </div>

        <div class="pr-beneficiario">
          <div class="pr-pontilhado"><strong>${escapar(loja.nome)}</strong></div>
          <div class="pr-cnpj"><span class="pr-rot">CNPJ/CPF</span>
            <span class="pr-pontilhado"><strong>${escapar(loja.documento || "")}</strong></span></div>
        </div>

        <div class="pr-quantia">
          <span class="pr-rot pr-rot--duas">OU A SUA ORDEM<br />A QUANTIA DE</span>
          <span class="pr-extenso">${escapar(extenso)}${"/".repeat(70)}</span>
        </div>
        <p class="pr-moeda">EM MOEDA CORRENTE<br />DESTE PAIS</p>

        <div class="pr-rodape">
          <div class="pr-emitente">
            <p><em>Pagável em</em> <span class="pr-pontilhado"><strong>${escapar(praca)}</strong></span></p>
            <p class="pr-dado"><strong>${escapar(venda.cliente_nome)}</strong></p>
            <p class="pr-rot">EMITENTE</p>
            <p class="pr-dado"><span class="pr-rot">CNPJ/CPF</span> <strong>${venda.cliente_cpf ? escapar(fmtCpf(venda.cliente_cpf)) : ""}</strong></p>
            <p class="pr-dado"><strong>${escapar(endereco)}</strong></p>
            <p class="pr-rot">ENDEREÇO</p>
          </div>
          <div class="pr-assinatura">
            <p class="pr-local">${escapar(loja.cidade || "")} &nbsp;&nbsp; ${escapar(porExtensoDataMinuscula(venda.data_venda))}</p>
            <p class="pr-linha-assinatura">Assinatura</p>
          </div>
        </div>

      </div>
    </div>`;
}

/** `22 de setembro de 2026` — minúscula, como sai na promissória. */
function porExtensoDataMinuscula(valor) {
  const texto = porExtensoData(valor);
  return texto ? texto.replace(/ de ([A-ZÇ])/g, (_, l) => ` de ${l.toLowerCase()}`) : "";
}

export function imprimirNotasPromissorias(venda) {
  const parcelas = (venda.parcelas || []).filter((p) => !p.pago_em);
  if (!parcelas.length) {
    avisarSemParcelas();
    return;
  }
  const fatura = numeroDaFatura(venda);
  abrirDocumento(
    "Notas promissórias",
    parcelas.map((p) => htmlNotaPromissoria(venda, p, fatura)).join(""),
  );
}

function avisarSemParcelas() {
  // Venda à vista ou carnê quitado: não há promessa de pagamento pra emitir.
  window.alert("Esta venda não tem parcela em aberto pra emitir nota promissória.");
}
