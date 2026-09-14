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
import * as v from "../validacao.js";

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
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-cliente-novo">Cancelar</button>
          <button type="button" class="botao" id="salvar-cliente-novo">Cadastrar e usar</button>
        </div>
      </fieldset>

      <div class="grade-2 secao-seguinte">
        <label class="campo">Valor da venda (R$)
          <input name="preco" type="number" step="0.01" min="0.01" value="${paraInput(moto.preco_centavos)}" />
        </label>
        <label class="campo">Forma de pagamento
          <select name="forma_pagamento">
            <option value="A_VISTA">À vista</option>
            <option value="PARCELADO">Parcelado (carnê da loja)</option>
            <option value="FINANCIADO">Financiado por banco</option>
            <option value="CONSORCIO">Consórcio</option>
          </select>
        </label>
        <label class="campo">Data da venda
          <input name="data_venda" type="date" max="${hojeIso()}" value="${hojeIso()}" />
        </label>
      </div>

      <fieldset id="bloco-parcelas" class="bloco" hidden>
        <legend>Carnê da loja</legend>
        <div class="grade-2">
          <label class="campo">Entrada (R$)<input name="entrada" type="number" step="0.01" min="0" value="0.00" /></label>
          <label class="campo">Quantas parcelas<input name="numero_parcelas" type="number" min="1" max="60" value="10" /></label>
          <label class="campo">1º vencimento<input name="primeiro_vencimento" type="date" value="${daquiAUmMes()}" /></label>
        </div>
        <p id="previa-parcelas" class="previa"></p>
      </fieldset>

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
        const achados = await api.pedir("GET", `/clientes?busca=${encodeURIComponent(termo)}`);
        listaResultado.hidden = false;
        listaResultado.innerHTML = achados.length
          ? achados.slice(0, 8).map((c) => `
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

    const valido = v.validarFormulario(form, [
      ["novo_nome", v.textoPreenchido(nome), "Informe o nome"],
      ["novo_cpf", v.textoPreenchido(documento), "CPF é obrigatório"],
      ["novo_cpf", !v.textoPreenchido(documento) || v.cpfValido(documento), "CPF inválido — confira os números"],
      ["novo_telefone", v.telefoneValido(fone), "Telefone precisa ter 10 ou 11 dígitos, com DDD"],
    ]);
    if (!valido) return;

    try {
      const novo = await api.pedir("POST", "/clientes", {
        nome,
        cpf: documento,
        telefone: fone || null,
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
        porPalavra: [["cpf", "novo_cpf"], ["telefone", "novo_telefone"]],
      });
    }
  });

  // ------------------------------------------------------------ parcelas

  function atualizarParcelas() {
    const parcelado = form.elements.forma_pagamento.value === "PARCELADO";
    blocoParcelas.hidden = !parcelado;
    if (!parcelado) return;

    const preco = centavos(form.elements.preco.value);
    const entrada = centavos(form.elements.entrada.value);
    const quantas = Number(form.elements.numero_parcelas.value);
    const saldo = preco - entrada;

    if (saldo <= 0 || !quantas || quantas < 1) {
      previa.textContent = "";
      return;
    }
    // A última parcela leva o resto da divisão — igual ao servidor faz.
    const base = Math.floor(saldo / quantas);
    const ultima = base + (saldo - base * quantas);
    previa.textContent = quantas === 1
      ? `1 parcela de ${reais(saldo)}`
      : `${quantas - 1}x de ${reais(base)} + última de ${reais(ultima)} · total a receber ${reais(saldo)}`;
  }

  form.elements.forma_pagamento.addEventListener("change", atualizarParcelas);
  ["preco", "entrada", "numero_parcelas"].forEach((nome) => {
    form.elements[nome].addEventListener("input", atualizarParcelas);
  });
  atualizarParcelas();

  // -------------------------------------------------------------- envio

  modal.querySelector("#cancelar-venda").addEventListener("click", () => fecharModal(modal));

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const preco = form.elements.preco.value;
    const forma = form.elements.forma_pagamento.value;
    const dataVenda = form.elements.data_venda.value;
    const parcelado = forma === "PARCELADO";
    const entrada = form.elements.entrada.value;
    const quantas = form.elements.numero_parcelas.value;
    const vencimento = form.elements.primeiro_vencimento.value;

    const regras = [
      ["cliente", clienteEscolhido !== null, "Escolha o cliente da venda"],
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
    if (!v.validarFormulario(form, regras)) return;

    const corpo = {
      id_cliente: idDaTentativa,
      moto_id: moto.id,
      cliente_id: clienteEscolhido.id,
      forma_pagamento: forma,
      preco_venda_centavos: centavos(preco),
    };
    // Só manda a data quando não é hoje: assim a venda de hoje fica com a
    // hora certa (o servidor carimba `agora()`). Um dia passado vai como
    // meio-dia no relógio de quem está usando — só a data seria lida como
    // meia-noite UTC, que no Brasil ainda é o dia anterior.
    if (dataVenda !== hojeIso()) corpo.data_venda = new Date(`${dataVenda}T12:00:00`).toISOString();
    if (parcelado) {
      corpo.numero_parcelas = Number(quantas);
      corpo.valor_entrada_centavos = centavos(entrada);
      corpo.primeiro_vencimento = vencimento;
    }

    const botao = modal.querySelector("#confirmar-venda");
    botao.disabled = true;
    try {
      // Pode esperar na fila: a moto e o cliente já existem no servidor
      // (os dois vieram de listas dele), e o `id_cliente` garante que subir
      // duas vezes não vende a mesma moto duas vezes.
      await api.enviar("POST", "/vendas", corpo, {
        rotulo: `Venda da ${moto.marca} ${moto.modelo} (${moto.placa || "sem placa"}) para ${clienteEscolhido.nome}`,
      });
      fecharModal(modal);
      avisar("Venda registrada — a moto saiu do estoque");
      await aoVender();
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
        porPalavra: [["entrada", "entrada"], ["parcelas", "numero_parcelas"], ["cliente", "cliente"]],
      });
    }
  });
}
