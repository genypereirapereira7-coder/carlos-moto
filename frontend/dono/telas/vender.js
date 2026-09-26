/**
 * Vender uma moto, pelo painel do dono.
 *
 * Sai daqui a única coisa que faz o resto do sistema ter o que mostrar: a
 * venda dá baixa da moto no estoque, entra no histórico do cliente e, quando
 * é parcelada, é ela que cria o carnê que aparece em PARCELAS e no
 * FINANCEIRO. Tudo isso é o servidor que faz — aqui é só o formulário.
 */

import * as api from "../../comum/api.js";
import { reais, cpf as formatarCpf, hojeIso, isoLocal } from "../../comum/formato.js";
import { abrirModal, fecharModal, avisar, guardadoNaFila } from "../ui.js";
import { imprimirComprovanteVenda, imprimirContratoVenda } from "../comprovantes.js";
import * as v from "../validacao.js";
import { htmlCamposConjuge, ligarConjuge, lerConjuge, regrasConjuge, corpoConjuge } from "../conjuge.js";
import { htmlCamposEndereco, lerEndereco, regrasEndereco, corpoEndereco } from "../endereco.js";
import { htmlCamposDocumentos, lerDocumentos, regrasDocumentos, corpoDocumentos } from "../documentos.js";
import { htmlCampoObservacao, lerObservacao, regrasObservacao } from "../observacao.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function centavos(valorEmReais) {
  const n = Number.parseFloat(String(valorEmReais).replace(",", "."));
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

function paraInput(centavosValor) {
  return centavosValor == null ? "" : (centavosValor / 100).toFixed(2);
}

function daquiAUmMes() {
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return isoLocal(d);
}

/**
 * @param {object} moto - a moto (precisa estar DISPONIVEL)
 * @param {() => Promise<void>} aoVender - chamado depois da venda gravada
 */
export function abrirModalVenda(moto, aoVender) {
  // Gerado uma vez, aqui: se o dono clicar duas vezes em "Confirmar" (ou a
  // rede engasgar e o navegador reenviar), o servidor reconhece a mesma
  // tentativa e devolve a venda que já existe em vez de recusar dizendo que
  // a moto já foi vendida. Ver `servicos/vendas.py::criar_venda`.
  const idDaTentativa = crypto.randomUUID();
  let clienteEscolhido = null;

  const modal = abrirModal(`
    <div class="modal-topo">
      <h3>Vender ${escapar(moto.marca)} ${escapar(moto.modelo)}${moto.placa ? ` — ${escapar(moto.placa)}` : ""}</h3>
    </div>
    <form id="form-venda" novalidate>
      <label class="campo">Cliente
        <input id="busca-cliente-venda" placeholder="Buscar por nome ou CPF" autocomplete="off" name="cliente" />
      </label>
      <div id="resultado-clientes" class="resultado-busca" hidden></div>
      <div id="cliente-escolhido" hidden></div>
      <p class="fraco" id="dica-cliente">
        Não achou? <button type="button" class="link" id="botao-cliente-novo">Cadastrar cliente novo</button>
      </p>

      <fieldset id="bloco-cliente-novo" class="bloco" hidden>
        <legend>Cliente novo</legend>
        <div class="grade-2">
          <label class="campo">Nome<input name="novo_nome" /></label>
          <label class="campo">CPF<input name="novo_cpf" placeholder="000.000.000-00" maxlength="14" /></label>
          <label class="campo">Telefone<input name="novo_telefone" placeholder="(11) 99999-0000" /></label>
        </div>
        ${htmlCamposDocumentos(null, "novo_")}
        ${htmlCamposConjuge(null, "novo_")}
        ${htmlCamposEndereco(null, "novo_")}
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-cliente-novo">Cancelar</button>
          <button type="button" class="botao" id="salvar-cliente-novo">Cadastrar e usar</button>
        </div>
      </fieldset>

      <div class="grade-2 secao-seguinte">
        <label class="campo">Vendedor
          <select name="vendedor_id">
            <option value="">Carregando…</option>
          </select>
        </label>
        <label class="campo">Valor da venda (R$)
          <input name="preco" type="number" step="0.01" min="0.01" value="${paraInput(moto.preco_centavos)}" />
        </label>
        <label class="campo">Forma de pagamento
          <select name="forma_pagamento">
            <option value="A_VISTA">À vista</option>
            <option value="PARCELADO">Parcelado (carnê da loja)</option>
            <option value="CHEQUE">Cheque pré-datado</option>
            <option value="CARTAO">Parcelado no cartão</option>
            <option value="FINANCIADO">Financiado por banco</option>
            <option value="CONSORCIO">Consórcio</option>
          </select>
        </label>
        <label class="campo">Data da venda
          <input name="data_venda" type="date" max="${hojeIso()}" value="${hojeIso()}" />
        </label>
      </div>

      <fieldset id="bloco-juros" class="bloco" hidden>
        <legend>Juros da loja</legend>
        <div class="grade-2">
          <label class="campo">Juros que a loja cobra (%)
            <input name="juros" type="number" step="0.01" min="0" max="100" value="0" />
          </label>
        </div>
        <div class="conta-juros" id="previa-juros"></div>
      </fieldset>

      <fieldset id="bloco-parcelas" class="bloco" hidden>
        <legend>Parcelas</legend>
        <div class="grade-2">
          <label class="campo">Entrada (R$)<input name="entrada" type="number" step="0.01" min="0" value="0.00" /></label>
          <label class="campo">Quantas parcelas<input name="numero_parcelas" type="number" min="1" max="60" value="10" /></label>
          <label class="campo">1º vencimento<input name="primeiro_vencimento" type="date" value="${daquiAUmMes()}" /></label>
        </div>
        <p id="previa-parcelas" class="previa"></p>

        <div class="avalistas secao-seguinte">
          <div class="modal-topo">
            <strong>Avalistas <span class="fraco">— quem garante o carnê (até 3)</span></strong>
            <button type="button" class="botao botao--fantasma" id="add-avalista">+ avalista</button>
          </div>
          <p class="fraco">Só no carnê da loja e no cheque. <strong>Nome e telefone são obrigatórios</strong>; CPF e endereço, opcionais.</p>
          <div id="lista-avalistas"></div>
        </div>
      </fieldset>

      ${htmlCampoObservacao("", "Ex.: leva o capacete junto; volta dia 10 pra transferência.")}

      <div class="acoes-modal">
        <button type="button" class="botao botao--fantasma" id="cancelar-venda">Cancelar</button>
        <button type="submit" class="botao" id="confirmar-venda">Confirmar venda</button>
      </div>
    </form>
  `);

  const form = modal.querySelector("#form-venda");
  const campoBusca = modal.querySelector("#busca-cliente-venda");
  const listaResultado = modal.querySelector("#resultado-clientes");
  const painelEscolhido = modal.querySelector("#cliente-escolhido");
  const blocoNovo = modal.querySelector("#bloco-cliente-novo");
  const blocoParcelas = modal.querySelector("#bloco-parcelas");
  const previa = modal.querySelector("#previa-parcelas");
  const selectVendedor = form.elements.vendedor_id;

  // ------------------------------------------------------------ vendedor

  // Preenche o select com os vendedores ativos (Zé Carlos, Dani). Falha de
  // rede não trava a venda: cai pra um campo digitável — melhor registrar a
  // venda sem culpar quem vendeu do que não registrar.
  (async () => {
    try {
      const gente = await api.pedir("GET", "/usuarios");
      const ativos = gente.filter((u) => u.ativo);
      if (!ativos.length) throw new Error("sem vendedores");
      selectVendedor.innerHTML =
        '<option value="">Selecione o vendedor</option>' +
        ativos.map((u) => `<option value="${u.id}">${escapar(u.nome)}</option>`).join("");
    } catch {
      // Sem a lista, o campo vira só um aviso — a venda segue com quem logou.
      selectVendedor.innerHTML = '<option value="">— vai como você —</option>';
    }
  })();

  // ------------------------------------------------------------- cliente

  function mostrarEscolhido() {
    painelEscolhido.hidden = false;
    painelEscolhido.innerHTML = `
      <div class="cliente-escolhido">
        <span><strong>${escapar(clienteEscolhido.nome)}</strong> · ${formatarCpf(clienteEscolhido.cpf)}</span>
        <button type="button" class="link" id="trocar-cliente">trocar</button>
      </div>
    `;
    campoBusca.closest(".campo").hidden = true;
    listaResultado.hidden = true;
    modal.querySelector("#dica-cliente").hidden = true;
    blocoNovo.hidden = true;
    v.limparErros(form);

    painelEscolhido.querySelector("#trocar-cliente").addEventListener("click", () => {
      clienteEscolhido = null;
      painelEscolhido.hidden = true;
      campoBusca.closest(".campo").hidden = false;
      modal.querySelector("#dica-cliente").hidden = false;
      campoBusca.value = "";
      campoBusca.focus();
    });
  }

  let timerBusca = null;
  campoBusca.addEventListener("input", () => {
    clearTimeout(timerBusca);
    const termo = campoBusca.value.trim();
    if (termo.length < 2) {
      listaResultado.hidden = true;
      return;
    }
    // Espera a digitação parar: sem isso é uma chamada por tecla apertada.
    timerBusca = setTimeout(async () => {
      try {
        // `por_pagina=8`: a lista de sugestão mostra 8, então não faz sentido
        // trazer 50 do servidor pra jogar 42 fora.
        const pagina = await api.pedir(
          "GET",
          `/clientes?busca=${encodeURIComponent(termo)}&por_pagina=8`,
        );
        const achados = pagina.clientes;
        listaResultado.hidden = false;
        listaResultado.innerHTML = achados.length
          ? achados.map((c) => `
              <button type="button" class="resultado-item" data-id="${c.id}" data-nome="${escapar(c.nome)}" data-cpf="${c.cpf}">
                ${escapar(c.nome)} <span class="fraco">· ${formatarCpf(c.cpf)}</span>
              </button>
            `).join("")
          : '<p class="fraco resultado-vazio">Nenhum cliente com esse nome ou CPF.</p>';
      } catch {
        listaResultado.hidden = true;
      }
    }, 250);
  });

  listaResultado.addEventListener("click", (evento) => {
    const item = evento.target.closest(".resultado-item");
    if (!item) return;
    clienteEscolhido = { id: Number(item.dataset.id), nome: item.dataset.nome, cpf: item.dataset.cpf };
    mostrarEscolhido();
  });

  ligarConjuge(modal, "novo_");

  modal.querySelector("#botao-cliente-novo").addEventListener("click", () => {
    blocoNovo.hidden = false;
    form.elements.novo_nome.value = campoBusca.value.trim();
    form.elements.novo_nome.focus();
  });

  modal.querySelector("#cancelar-cliente-novo").addEventListener("click", () => {
    blocoNovo.hidden = true;
  });

  modal.querySelector("#salvar-cliente-novo").addEventListener("click", async () => {
    const nome = form.elements.novo_nome.value;
    const documento = form.elements.novo_cpf.value;
    const fone = form.elements.novo_telefone.value;

    const dadosDoForm = new FormData(form);
    const conjuge = lerConjuge(dadosDoForm, "novo_");
    const endereco = lerEndereco(dadosDoForm, "novo_");
    const documentos = lerDocumentos(dadosDoForm, "novo_");
    const valido = v.validarFormulario(form, [
      ["novo_nome", v.textoPreenchido(nome), "Informe o nome"],
      ["novo_cpf", v.textoPreenchido(documento), "CPF é obrigatório"],
      ["novo_cpf", !v.textoPreenchido(documento) || v.cpfValido(documento), "CPF inválido — confira os números"],
      ["novo_telefone", v.telefoneValido(fone), "Telefone precisa ter 10 ou 11 dígitos, com DDD"],
      ...regrasConjuge(conjuge, "novo_"),
      ...regrasEndereco(endereco, "novo_"),
      ...regrasDocumentos(documentos, "novo_"),
    ]);
    if (!valido) return;

    try {
      const novo = await api.pedir("POST", "/clientes", {
        nome,
        cpf: documento,
        telefone: fone || null,
        ...corpoConjuge(conjuge),
        ...corpoEndereco(endereco),
        ...corpoDocumentos(documentos),
      });
      clienteEscolhido = novo;
      avisar("Cliente cadastrado");
      mostrarEscolhido();
    } catch (erro) {
      // Este cadastro **não** vai pra fila, de propósito: a venda logo abaixo
      // precisa do id que só o servidor dá, e um cliente esperando na fila
      // não tem id nenhum. Melhor dizer o caminho do que guardar uma venda
      // que vai ser recusada quando subir.
      if (erro instanceof api.ErroRede) {
        avisar(
          "Sem internet: cadastre o cliente na aba Clientes (fica guardado) " +
          "e faça a venda quando a conexão voltar.",
          "erro",
        );
        return;
      }
      v.mostrarErroDeApi(form, erro, {
        renomear: { nome: "novo_nome", cpf: "novo_cpf", telefone: "novo_telefone" },
        porPalavra: [["cpf", "novo_cpf"], ["telefone", "novo_telefone"],
                     ["e-mail", "novo_email"], ["cep", "novo_cep"], ["uf", "novo_uf"]],
      });
    }
  });

  // ------------------------------------------------------------ parcelas

  // As formas em que a loja carrega a dívida: gera carnê pra cobrar, aceita
  // avalista e é onde existe juros da loja. Precisa bater com `COM_CARNE` do
  // servidor. No cartão e no consórcio quem parcela é a operadora, então não
  // há juro da loja a cobrar.
  const COM_CARNE = ["PARCELADO", "CHEQUE"];

  const blocoJuros = modal.querySelector("#bloco-juros");
  const previaJuros = modal.querySelector("#previa-juros");

  /** Juros digitado em %, convertido pros centésimos que a API espera. */
  function jurosCentesimos() {
    const n = Number.parseFloat(String(form.elements.juros.value).replace(",", "."));
    return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : 0;
  }

  /** Mesma conta do servidor: juro simples sobre o saldo, arredondado pra baixo. */
  function comJuros(saldo) {
    const j = jurosCentesimos();
    return j > 0 ? saldo + Math.floor((saldo * j) / 10000) : saldo;
  }

  function atualizarParcelas() {
    const forma = form.elements.forma_pagamento.value;
    const temCarne = COM_CARNE.includes(forma);
    blocoParcelas.hidden = !temCarne;
    blocoJuros.hidden = !COM_CARNE.includes(forma);

    if (!COM_CARNE.includes(forma)) {
      // Forma sem juros: zera pra não mandar juro de uma escolha anterior.
      form.elements.juros.value = "0";
      previaJuros.innerHTML = "";
    }
    if (!temCarne) {
      previa.textContent = "";
      previaJuros.innerHTML = "";
      return;
    }

    const preco = centavos(form.elements.preco.value);
    const entrada = centavos(form.elements.entrada.value);
    const quantas = Number(form.elements.numero_parcelas.value);
    const saldo = preco - entrada;

    if (saldo <= 0 || !quantas || quantas < 1) {
      previa.textContent = "";
      previaJuros.innerHTML = "";
      return;
    }

    const total = comJuros(saldo);
    // A conta aberta, linha a linha, embaixo do campo de juros: o que está
    // sendo financiado, quanto o juros acrescenta, e quanto o cliente vai
    // pagar no fim. É o número que ele vai conferir no balcão.
    const acrescimo = total - saldo;
    previaJuros.innerHTML = acrescimo > 0
      ? `
        <div class="conta-linha"><span>Financiado</span><span>${reais(saldo)}</span></div>
        <div class="conta-linha conta-linha--soma">
          <span>Juros de ${(jurosCentesimos() / 100).toFixed(2).replace(".", ",")}%</span>
          <span>+ ${reais(acrescimo)}</span>
        </div>
        <div class="conta-linha conta-linha--total">
          <span>Total a receber</span><span>${reais(total)}</span>
        </div>`
      : `<div class="conta-linha conta-linha--total">
           <span>Total a receber <span class="fraco">(sem juros)</span></span><span>${reais(saldo)}</span>
         </div>`;

    // A última parcela leva o resto da divisão — igual ao servidor faz.
    const base = Math.floor(total / quantas);
    const ultima = base + (total - base * quantas);
    previa.textContent = quantas === 1
      ? `1 parcela de ${reais(total)}`
      : `${quantas - 1}x de ${reais(base)} + última de ${reais(ultima)} · total a receber ${reais(total)}`;
  }

  form.elements.forma_pagamento.addEventListener("change", atualizarParcelas);
  ["preco", "entrada", "numero_parcelas", "juros"].forEach((nome) => {
    form.elements[nome].addEventListener("input", atualizarParcelas);
  });
  atualizarParcelas();

  // ------------------------------------------------------------ avalistas

  const listaAvalistas = modal.querySelector("#lista-avalistas");
  const botaoAddAvalista = modal.querySelector("#add-avalista");

  function renumerarAvalistas() {
    const itens = [...listaAvalistas.querySelectorAll(".avalista-item")];
    itens.forEach((item, i) => {
      item.querySelector(".avalista-titulo").textContent = `Avalista ${i + 1}`;
    });
    // Três é o teto — some o botão quando cheio, volta quando abre vaga.
    botaoAddAvalista.hidden = itens.length >= 3;
  }

  function adicionarAvalista() {
    if (listaAvalistas.querySelectorAll(".avalista-item").length >= 3) return;
    const item = document.createElement("fieldset");
    item.className = "bloco avalista-item";
    item.innerHTML = `
      <legend><span class="avalista-titulo"></span>
        <button type="button" class="link remover-avalista">remover</button></legend>
      <div class="grade-2">
        <label class="campo">Nome<input class="av-nome" autocomplete="off" /></label>
        <label class="campo">CPF<input class="av-cpf" maxlength="14" placeholder="opcional" autocomplete="off" /></label>
        <label class="campo">Telefone<input class="av-telefone" placeholder="(69) 99999-0000" autocomplete="off" /></label>
        <label class="campo">Endereço<input class="av-endereco" placeholder="opcional" autocomplete="off" /></label>
      </div>
`;
    listaAvalistas.appendChild(item);
    item.querySelector(".remover-avalista").addEventListener("click", () => {
      item.remove();
      renumerarAvalistas();
    });
    renumerarAvalistas();
    item.querySelector(".av-nome").focus();
  }

  botaoAddAvalista.addEventListener("click", adicionarAvalista);

  /** Lê os avalistas preenchidos e valida cada um. Devolve {ok, lista}. */
  function coletarAvalistas() {
    const itens = [...listaAvalistas.querySelectorAll(".avalista-item")];
    const lista = [];
    let ok = true;
    for (const item of itens) {
      const nome = item.querySelector(".av-nome").value.trim();
      const cpf = item.querySelector(".av-cpf").value.trim();
      const telefone = item.querySelector(".av-telefone").value.trim();
      const endereco = item.querySelector(".av-endereco").value.trim();
      // Linha totalmente em branco: o dono abriu e não usou — ignora sem erro.
      if (!nome && !cpf && !telefone && !endereco) continue;

      let erro = "";
      if (!nome) erro = "Avalista precisa de nome (ou apague a linha)";
      // Telefone é obrigatório: avalista que a loja não consegue ligar não
      // avaliza nada.
      else if (!telefone) erro = "Avalista precisa de telefone";
      else if (!v.telefoneValido(telefone)) erro = "Telefone do avalista inválido (DDD + número)";
      else if (cpf && !v.cpfValido(cpf)) erro = "CPF do avalista inválido";

      // Criado na hora: `validarFormulario` chama `limparErros`, que **remove**
      // todo `.erro-campo` do formulário — um elemento guardado no HTML do
      // avalista some na primeira tentativa e o aviso nunca mais aparecia.
      item.querySelector(".erro-campo")?.remove();
      if (erro) {
        const aviso = document.createElement("p");
        aviso.className = "erro-campo";
        aviso.textContent = erro;
        item.appendChild(aviso);
        ok = false;
        continue;
      }

      lista.push({
        nome,
        cpf: cpf || null,
        telefone: telefone || null,
        endereco: endereco || null,
      });
    }
    return { ok, lista };
  }

  // ---------------------------------------------------- sucesso + impressão

  // Troca o formulário por um painel de "vendido", com os documentos à mão.
  // O `aoVender` (recarrega o estoque) só roda quando o dono conclui, pra a
  // moto não sumir da lista atrás enquanto ele ainda imprime.
  function mostrarSucesso(venda, aoConcluir) {
    modal.innerHTML = `
      <div class="modal-topo"><h3>Venda registrada ✓</h3></div>
      <p class="fraco">A moto saiu do estoque. Imprima o que precisar e conclua.</p>
      <div class="acoes-modal acoes-empilhadas">
        <button class="botao" id="doc-comprovante-venda" type="button">Imprimir comprovante</button>
        <button class="botao" id="doc-contrato-venda" type="button">Imprimir contrato</button>
        <button class="botao botao--fantasma" id="concluir-venda" type="button">Concluir</button>
      </div>`;
    modal.querySelector("#doc-comprovante-venda").addEventListener("click", () => imprimirComprovanteVenda(venda));
    modal.querySelector("#doc-contrato-venda").addEventListener("click", () => imprimirContratoVenda(venda));
    modal.querySelector("#concluir-venda").addEventListener("click", async () => {
      fecharModal(modal);
      await aoConcluir();
    });
  }

  // -------------------------------------------------------------- envio

  modal.querySelector("#cancelar-venda").addEventListener("click", () => fecharModal(modal));

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const preco = form.elements.preco.value;
    const forma = form.elements.forma_pagamento.value;
    const dataVenda = form.elements.data_venda.value;
    const parcelado = COM_CARNE.includes(forma);
    const entrada = form.elements.entrada.value;
    const quantas = form.elements.numero_parcelas.value;
    const vencimento = form.elements.primeiro_vencimento.value;

    const vendedorId = selectVendedor.value;
    // Só exige escolher quando a lista carregou (as options têm value). Se a
    // rede falhou e o campo virou aviso, não trava — a venda vai com quem logou.
    const temListaVendedor = [...selectVendedor.options].some((o) => o.value);

    const observacao = lerObservacao(new FormData(form));
    const regras = [
      ["cliente", clienteEscolhido !== null, "Escolha o cliente da venda"],
      ...regrasObservacao(observacao),
      ["vendedor_id", !temListaVendedor || v.textoPreenchido(vendedorId), "Escolha quem fez a venda"],
      ["preco", v.numeroPositivo(preco), "Informe o valor da venda"],
      ["data_venda", v.textoPreenchido(dataVenda) && v.dataNaoFutura(dataVenda), "Data da venda inválida"],
    ];
    if (parcelado) {
      regras.push(
        ["entrada", v.numeroNaoNegativo(entrada), "Entrada não pode ser negativa"],
        ["entrada", centavos(entrada) < centavos(preco), "A entrada tem que ser menor que o valor da venda"],
        ["numero_parcelas", Number(quantas) >= 1 && Number(quantas) <= 60, "Entre 1 e 60 parcelas"],
        ["primeiro_vencimento", v.textoPreenchido(vencimento), "Informe o 1º vencimento"],
      );
    }
    // Nesta ordem de propósito: `validarFormulario` começa limpando os erros
    // do formulário inteiro, então coletar os avalistas antes dele faria o
    // aviso deles ser apagado no mesmo instante em que foi escrito.
    const formOk = v.validarFormulario(form, regras);
    const avalistas = parcelado ? coletarAvalistas() : { ok: true, lista: [] };
    if (!formOk || !avalistas.ok) return;

    const corpo = {
      id_cliente: idDaTentativa,
      moto_id: moto.id,
      cliente_id: clienteEscolhido.id,
      forma_pagamento: forma,
      preco_venda_centavos: centavos(preco),
    };
    if (vendedorId) corpo.vendedor_id = Number(vendedorId);
    if (observacao) corpo.observacao = observacao;
    // Só manda a data quando não é hoje: assim a venda de hoje fica com a
    // hora certa (o servidor carimba `agora()`). Um dia passado vai como
    // meio-dia no relógio de quem está usando — só a data seria lida como
    // meia-noite UTC, que no Brasil ainda é o dia anterior.
    if (dataVenda !== hojeIso()) corpo.data_venda = new Date(`${dataVenda}T12:00:00`).toISOString();
    if (COM_CARNE.includes(forma) && jurosCentesimos()) corpo.juros_centesimos = jurosCentesimos();
    if (parcelado) {
      corpo.numero_parcelas = Number(quantas);
      corpo.valor_entrada_centavos = centavos(entrada);
      corpo.primeiro_vencimento = vencimento;
      if (avalistas.lista.length) corpo.avalistas = avalistas.lista;
    }

    const botao = modal.querySelector("#confirmar-venda");
    botao.disabled = true;
    try {
      // Pode esperar na fila: a moto e o cliente já existem no servidor
      // (os dois vieram de listas dele), e o `id_cliente` garante que subir
      // duas vezes não vende a mesma moto duas vezes.
      const venda = await api.enviar("POST", "/vendas", corpo, {
        rotulo: `Venda da ${moto.marca} ${moto.modelo} (${moto.placa || "sem placa"}) para ${clienteEscolhido.nome}`,
      });
      avisar("Venda registrada — a moto saiu do estoque");
      // `venda` é a resposta do servidor, com tudo pra imprimir. Fica com o
      // painel de sucesso aberto (comprovante/contrato) até o dono concluir.
      mostrarSucesso(venda, aoVender);
    } catch (erro) {
      if (guardadoNaFila(erro, "Venda")) {
        fecharModal(modal);
        await aoVender();
        return;
      }
      botao.disabled = false;
      v.mostrarErroDeApi(form, erro, {
        renomear: {
          preco_venda_centavos: "preco",
          valor_entrada_centavos: "entrada",
          cliente_id: "cliente",
        },
        porPalavra: [
          ["entrada", "entrada"], ["parcelas", "numero_parcelas"],
          ["cliente", "cliente"], ["vendedor", "vendedor_id"],
        ],
      });
    }
  });
}
