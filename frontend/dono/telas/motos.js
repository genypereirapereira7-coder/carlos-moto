/**
 * Tela MOTOS: buscar pela placa e ver o histórico inteiro — compra, gastos,
 * venda, lucro — mais o estoque completo pra cadastrar, editar e lançar
 * gasto.
 */

import * as api from "../../comum/api.js";
import { reais, dataBr, hojeIso, km as formatarKm } from "../../comum/formato.js";
import {
  abrirModal, fecharModal, avisar, mensagemDeErro, guardadoNaFila,
  rotuloStatusParcela, classeStatusParcela, classeDoSaldo,
} from "../ui.js";
import * as v from "../validacao.js";
import { htmlCampoModelo, ligarAutocompleteModelo } from "../marca-modelo.js";
import { abrirModalVenda } from "./vender.js";
import { htmlCampoObservacao, lerObservacao, regrasObservacao } from "../observacao.js";
import {
  imprimirComprovanteCompra, imprimirContratoCompra,
  imprimirComprovanteVenda, imprimirContratoVenda,
} from "../comprovantes.js";

function escapar(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// ---------------------------------------- quem vendeu a moto pra loja
// Os mesmos campos aparecem no cadastro e na edição: ler, validar e montar o
// corpo mora aqui pra as duas telas não saírem de sincronia.

function lerFornecedor(dados) {
  const texto = (campo) => (dados.get(campo) || "").trim();
  return {
    nome: texto("fornecedor_nome"),
    cpf: texto("fornecedor_cpf"),
    email: texto("fornecedor_email"),
    contato: texto("fornecedor_contato"),
    casado: dados.get("fornecedor_casado"),
    conjugeNome: texto("fornecedor_conjuge_nome"),
    conjugeContato: texto("fornecedor_conjuge_contato"),
  };
}

function regrasFornecedor(f) {
  // Tudo opcional — mas o que vier preenchido tem que estar certo.
  return [
    ["fornecedor_cpf", !f.cpf || v.cpfValido(f.cpf), "CPF inválido — confira os números"],
    ["fornecedor_email", !f.email || v.emailValido(f.email), "E-mail inválido — confira o endereço"],
    ["fornecedor_contato", !f.contato || v.telefoneValido(f.contato), "Contato precisa ter 10 ou 11 dígitos, com DDD"],
    ["fornecedor_conjuge_nome", f.casado !== "sim" || !!f.conjugeNome, "Informe o nome do cônjuge"],
    ["fornecedor_conjuge_contato", !f.conjugeContato || v.telefoneValido(f.conjugeContato), "Contato do cônjuge precisa ter 10 ou 11 dígitos, com DDD"],
  ];
}

function corpoFornecedor(f) {
  return {
    fornecedor_nome: f.nome || null,
    fornecedor_cpf: f.cpf || null,
    fornecedor_email: f.email || null,
    fornecedor_contato: f.contato || null,
    // "" (não respondido) vira null; só "sim"/"nao" viram booleano.
    fornecedor_casado: f.casado === "" ? null : f.casado === "sim",
    // Cônjuge só vai junto quando casado — responder "não" limpa o que tinha
    // ficado de uma resposta anterior.
    fornecedor_conjuge_nome: f.casado === "sim" ? (f.conjugeNome || null) : null,
    fornecedor_conjuge_contato: f.casado === "sim" ? (f.conjugeContato || null) : null,
  };
}

function centavosParaReaisInput(centavos) {
  return centavos == null ? "" : (centavos / 100).toFixed(2);
}

function reaisInputParaCentavos(valor) {
  const numero = Number.parseFloat(String(valor).replace(",", "."));
  return Number.isFinite(numero) ? Math.round(numero * 100) : 0;
}

// Sobrevive a um `renderMotos` novo — o `app.js` chama esta função de novo a
// cada evento do WebSocket (inclusive o eco da própria ação de quem está
// olhando a tela), e sem isto o detalhe aberto desaparecia no meio de uma
// edição: a tela toda é reconstruída, o `<div id="detalhe-moto">` de antes
// vira um elemento órfão, e o que a edição escrevia nele não aparecia mais
// em lugar nenhum.
let motoAbertaId = null;

// Duas aberturas de detalhe podem estar no ar ao mesmo tempo: a que o usuário
// pediu e a que o re-render do WebSocket dispara pra reabrir o que estava
// aberto. Quem responde por último pinta a tela — e era assim que cadastrar
// uma moto com outra aberta acabava mostrando a moto anterior por cima da
// recém-criada. Só a última abertura pedida tem direito de escrever.
let pedidoDetalhe = 0;

export async function renderMotos(raiz) {
  raiz.innerHTML = `
    <h2>Motos</h2>
    <div class="barra-busca">
      <input id="busca-placa" placeholder="Buscar pela placa (ex: ABC1D23)" autocomplete="off" />
      <button class="botao" id="botao-buscar-placa" type="button">Buscar</button>
      <button class="botao botao--fantasma" id="botao-nova-moto" type="button">Cadastrar moto</button>
    </div>
    <div id="detalhe-moto"></div>
    <div class="cartao">
      <h3>Estoque</h3>
      <div class="tabela-wrap">
        <table class="tabela">
          <thead>
            <tr><th>Placa</th><th>Marca / Modelo</th><th>Ano</th><th>Status</th><th>Preço</th></tr>
          </thead>
          <tbody id="linhas-estoque"><tr><td colspan="5" class="fraco">Carregando…</td></tr></tbody>
        </table>
      </div>
    </div>
  `;

  // Procurados na hora do uso, não guardados: o `app.js` refaz esta tela a
  // cada evento do WebSocket, e um elemento guardado aqui vira nó órfão —
  // o que for escrito nele não aparece mais. `raiz` é o que sobrevive.
  const corpoTabela = () => raiz.querySelector("#linhas-estoque");
  const detalheEl = () => raiz.querySelector("#detalhe-moto");

  async function carregarLista() {
    try {
      const motos = await api.pedir("GET", "/motos");
      if (!motos.length) {
        corpoTabela().innerHTML = '<tr><td colspan="5" class="fraco">Nenhuma moto cadastrada ainda.</td></tr>';
        return;
      }
      corpoTabela().innerHTML = motos.map((m) => `
        <tr data-id="${m.id}">
          <td>${escapar(m.placa || "—")}</td>
          <td data-rotulo="Marca / Modelo">${escapar(m.marca)} ${escapar(m.modelo)}</td>
          <td data-rotulo="Ano">${m.ano}</td>
          <td data-rotulo="Status"><span class="selo ${m.status === "DISPONIVEL" ? "selo--disponivel" : "selo--vendida"}">${m.status === "DISPONIVEL" ? "Disponível" : "Vendida"}</span></td>
          <td data-rotulo="Preço">${reais(m.preco_centavos)}</td>
        </tr>
      `).join("");

      // O histórico de cada moto é buscado em segundo plano só pra ficar
      // guardado: sem isto o estoque abre sem internet, mas clicar numa moto
      // não abre nada — e procurar uma placa é justamente o que esta tela faz.
      api.preAquecer(motos.map((m) => `/motos/${m.id}`));
    } catch (erro) {
      corpoTabela().innerHTML = `<tr><td colspan="5" class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</td></tr>`;
    }
  }

  async function abrirDetalhe(idOuPlaca, { porPlaca = false } = {}) {
    // Marcado antes do await sempre que já se sabe o id: o re-render
    // disparado pelo WebSocket lê este valor pra reabrir o detalhe certo, e
    // se ele só fosse escrito depois da resposta, o eco da própria ação
    // reabriria a moto anterior por cima desta. Na busca por placa não dá
    // pra adiantar — o id só chega junto com a moto.
    const meuPedido = ++pedidoDetalhe;
    if (!porPlaca) motoAbertaId = Number(idOuPlaca);
    detalheEl().innerHTML = '<div class="cartao fraco">Carregando histórico…</div>';
    try {
      const caminho = porPlaca
        ? `/motos/por-placa/${encodeURIComponent(idOuPlaca)}`
        : `/motos/${idOuPlaca}`;
      const moto = await api.pedir("GET", caminho);
      if (meuPedido !== pedidoDetalhe) return;
      motoAbertaId = moto.id;
      detalheEl().innerHTML = montarDetalhe(moto);
      plugarAcoesDoDetalhe(moto);
    } catch (erro) {
      if (meuPedido !== pedidoDetalhe) return;
      detalheEl().innerHTML = `<div class="cartao"><p class="faixa faixa--erro">${escapar(mensagemDeErro(erro))}</p></div>`;
    }
  }

  function montarDetalhe(m) {
    const fornecedor = m.fornecedor_nome_efetivo || "—";
    const compra = m.valor_compra_centavos != null
      ? `${reais(m.valor_compra_centavos)}${m.data_compra ? ` em ${dataBr(m.data_compra)}` : ""}`
      : "Ainda não lançada";

    const despesasHtml = m.despesas.length
      ? `<ul class="lista-despesas">${m.despesas.map((d) => `
          <li><span>${escapar(d.descricao)} · ${dataBr(d.data)}</span><strong>${reais(d.valor_centavos)}</strong></li>
        `).join("")}</ul>`
      : '<p class="fraco">Nenhum gasto lançado.</p>';

    let vendaHtml = '<p class="fraco">Ainda não foi vendida.</p>';
    if (m.venda) {
      const v = m.venda;
      const parcelasHtml = v.parcelas.length
        ? `<ul class="lista-despesas">${v.parcelas.map((p) => `
            <li>
              <span>Parcela ${p.numero} · vence ${dataBr(p.vencimento)}</span>
              <strong class="${classeStatusParcela(p.status)}">${reais(p.valor_centavos)} · ${rotuloStatusParcela(p.status)}</strong>
            </li>
          `).join("")}</ul>`
        : "";
      vendaHtml = `
        <dl class="linhas-dados">
          <div><dt>Vendida para</dt><dd>${escapar(v.cliente_nome)}</dd></div>
          <div><dt>Forma de pagamento</dt><dd>${rotuloFormaPagamento(v.forma_pagamento)}</dd></div>
          <div><dt>Valor da venda</dt><dd>${reais(v.preco_venda_centavos)}</dd></div>
          <div><dt>Data da venda</dt><dd>${dataBr(v.data_venda)}</dd></div>
          ${v.parcelado ? `<div><dt>Falta receber</dt><dd class="${classeDoSaldo(v.parcelas)}">${reais(v.saldo_devedor_centavos)}</dd></div>` : ""}
        </dl>
        ${parcelasHtml}
      `;
    }

    const lucroClasse = m.lucro_centavos == null ? "" : (m.lucro_centavos >= 0 ? "lucro-positivo" : "lucro-negativo");

    return `
      <div class="cartao">
        <div class="modal-topo">
          <h3>${escapar(m.marca)} ${escapar(m.modelo)} ${m.ano} ${m.placa ? `— ${escapar(m.placa)}` : ""}</h3>
          <div class="acoes-linha">
            ${m.status === "DISPONIVEL" ? '<button class="botao" id="botao-vender-moto" type="button">Vender</button>' : ""}
            <button class="botao botao--fantasma" id="botao-editar-moto" type="button">Editar</button>
            <button class="botao botao--fantasma" id="botao-lancar-despesa" type="button">Lançar gasto</button>
          </div>
        </div>
        <dl class="linhas-dados">
          <div><dt>Chassi</dt><dd>${escapar(m.chassi || "—")}</dd></div>
          <div><dt>Cor</dt><dd>${escapar(m.cor || "—")}</dd></div>
          <div><dt>Km</dt><dd>${formatarKm(m.km)}</dd></div>
          <div><dt>Preço anunciado</dt><dd>${reais(m.preco_centavos)}</dd></div>
        </dl>

        ${m.observacao ? `
          <h3 class="secao-seguinte">Observação</h3>
          <p class="texto-observacao">${escapar(m.observacao)}</p>` : ""}

        <h3 class="secao-seguinte">Compra</h3>
        <dl class="linhas-dados">
          <div><dt>Valor pago</dt><dd>${compra}</dd></div>
          <div><dt>Comprada de</dt><dd>${escapar(fornecedor)}</dd></div>
        </dl>
        ${m.valor_compra_centavos != null ? `
          <div class="acoes-linha">
            <button class="botao botao--fantasma" id="doc-comprovante-compra" type="button">Comprovante de compra</button>
            <button class="botao botao--fantasma" id="doc-contrato-compra" type="button">Contrato de compra</button>
          </div>` : ""}

        <h3 class="secao-seguinte">Gastos</h3>
        ${despesasHtml}
        <p><strong>Total em gastos: ${reais(m.total_gastos_centavos)}</strong></p>

        <h3 class="secao-seguinte">Venda</h3>
        ${vendaHtml}
        ${m.venda ? `
          <div class="acoes-linha">
            <button class="botao botao--fantasma" id="doc-comprovante-venda" type="button">Comprovante de venda</button>
            <button class="botao botao--fantasma" id="doc-contrato-venda" type="button">Contrato de venda</button>
          </div>` : ""}

        ${m.lucro_centavos != null ? `
          <h3 class="secao-seguinte">Resultado</h3>
          <dl class="linhas-dados">
            <div><dt>Lucro</dt><dd class="${lucroClasse}">${reais(m.lucro_centavos)}</dd></div>
            <div><dt>% de lucro sobre o custo</dt><dd class="${lucroClasse}">${m.lucro_percentual}%</dd></div>
          </dl>
        ` : ""}
      </div>
    `;
  }

  function rotuloFormaPagamento(forma) {
    return {
      A_VISTA: "À vista", PARCELADO: "Parcelado (loja)", CHEQUE: "Cheque pré-datado",
      CARTAO: "Parcelado no cartão", FINANCIADO: "Financiado", CONSORCIO: "Consórcio",
    }[forma] || forma;
  }

  function plugarAcoesDoDetalhe(moto) {
    raiz.querySelector("#botao-editar-moto")?.addEventListener("click", () => abrirModalEditar(moto));
    raiz.querySelector("#botao-lancar-despesa")?.addEventListener("click", () => abrirModalDespesa(moto));
    raiz.querySelector("#botao-vender-moto")?.addEventListener("click", () => {
      abrirModalVenda(moto, async () => {
        await carregarLista();
        await abrirDetalhe(moto.id);
      });
    });

    // Documentos de compra — montados direto da moto (fornecedor, valor, data).
    raiz.querySelector("#doc-comprovante-compra")?.addEventListener("click", () => imprimirComprovanteCompra(moto));
    raiz.querySelector("#doc-contrato-compra")?.addEventListener("click", () => imprimirContratoCompra(moto));

    // Documentos de venda — o detalhe da moto traz só um resumo da venda, sem
    // parcelas nem avalistas. Busca a venda inteira antes de imprimir.
    async function imprimirVenda(imprimir, botao) {
      const rotulo = botao.textContent;
      botao.disabled = true;
      botao.textContent = "Abrindo…";
      try {
        const venda = await api.pedir("GET", `/vendas/${moto.venda.venda_id}`);
        imprimir(venda);
      } catch (erro) {
        avisar(mensagemDeErro(erro), "erro");
      } finally {
        botao.disabled = false;
        botao.textContent = rotulo;
      }
    }
    raiz.querySelector("#doc-comprovante-venda")?.addEventListener("click", (e) => imprimirVenda(imprimirComprovanteVenda, e.currentTarget));
    raiz.querySelector("#doc-contrato-venda")?.addEventListener("click", (e) => imprimirVenda(imprimirContratoVenda, e.currentTarget));
  }

  function abrirModalEditar(moto) {
    const anoMaximo = new Date().getFullYear() + 1;
    const hoje = hojeIso();
    const modal = abrirModal(`
      <div class="modal-topo"><h3>Editar moto</h3></div>
      <form id="form-editar-moto" novalidate>
        <div class="grade-2">
          ${htmlCampoModelo(moto.marca, moto.modelo)}
          <label class="campo">Ano<input name="ano" type="number" min="1980" max="${anoMaximo}" value="${moto.ano}" required /></label>
          <label class="campo">Cor<input name="cor" value="${escapar(moto.cor || "")}" /></label>
          <label class="campo">Placa<input name="placa" value="${escapar(moto.placa || "")}" maxlength="8" placeholder="ABC1234 ou ABC1D23" required /></label>
          <label class="campo">Chassi<input name="chassi" value="${escapar(moto.chassi || "")}" maxlength="17" placeholder="17 letras/números" /></label>
          <label class="campo">Km<input name="km" type="number" min="0" value="${moto.km}" /></label>
          <label class="campo">Condição
            <select name="condicao">
              <option value="NOVA" ${moto.condicao === "NOVA" ? "selected" : ""}>Nova</option>
              <option value="USADA" ${moto.condicao === "USADA" ? "selected" : ""}>Usada</option>
            </select>
          </label>
          <label class="campo">Preço anunciado (R$)<input name="preco" type="number" step="0.01" min="0.01" value="${centavosParaReaisInput(moto.preco_centavos)}" required /></label>
          <label class="campo">Valor de compra (R$)<input name="valor_compra" type="number" step="0.01" min="0.01" value="${centavosParaReaisInput(moto.valor_compra_centavos)}" /></label>
          <label class="campo">Data da compra<input name="data_compra" type="date" max="${hoje}" value="${moto.data_compra || ""}" /></label>
        </div>

        <fieldset class="bloco">
          <legend>Quem vendeu a moto pra loja</legend>
          <p class="fraco">É esta pessoa que assina o contrato de compra. Preencha o que a loja tiver.</p>
          <div class="grade-2">
            <label class="campo">Nome<input name="fornecedor_nome" value="${escapar(moto.fornecedor_nome || "")}" /></label>
            <label class="campo">CPF<input name="fornecedor_cpf" maxlength="14" placeholder="000.000.000-00" value="${escapar(moto.fornecedor_cpf || "")}" /></label>
            <label class="campo">E-mail<input name="fornecedor_email" placeholder="nome@email.com" value="${escapar(moto.fornecedor_email || "")}" /></label>
            <label class="campo">Contato<input name="fornecedor_contato" placeholder="(69) 99999-0000" value="${escapar(moto.fornecedor_contato || "")}" /></label>
            <label class="campo">É casado(a)?
              <select name="fornecedor_casado">
                <option value="" ${moto.fornecedor_casado == null ? "selected" : ""}>—</option>
                <option value="nao" ${moto.fornecedor_casado === false ? "selected" : ""}>Não</option>
                <option value="sim" ${moto.fornecedor_casado === true ? "selected" : ""}>Sim</option>
              </select>
            </label>
          </div>
          <div class="grade-2" id="bloco-conjuge" ${moto.fornecedor_casado === true ? "" : "hidden"}>
            <label class="campo">Nome do cônjuge<input name="fornecedor_conjuge_nome" value="${escapar(moto.fornecedor_conjuge_nome || "")}" /></label>
            <label class="campo">Contato do cônjuge<input name="fornecedor_conjuge_contato" placeholder="(69) 99999-0000" value="${escapar(moto.fornecedor_conjuge_contato || "")}" /></label>
          </div>
        </fieldset>
        ${htmlCampoObservacao(moto.observacao, "Ex.: riscado no tanque; veio sem chave reserva.")}

        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-editar-moto">Cancelar</button>
          <button type="submit" class="botao">Salvar</button>
        </div>
      </form>
    `);

    ligarAutocompleteModelo(modal.querySelector("#form-editar-moto"));

    // Cônjuge só faz sentido quando casado — some do formulário fora disso,
    // pra não pedir dado que ninguém vai preencher.
    const selectCasado = modal.querySelector('select[name="fornecedor_casado"]');
    const blocoConjuge = modal.querySelector("#bloco-conjuge");
    selectCasado.addEventListener("change", () => {
      blocoConjuge.hidden = selectCasado.value !== "sim";
    });

    modal.querySelector("#cancelar-editar-moto").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#form-editar-moto").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const form = evento.target;
      const dados = new FormData(form);
      const marca = dados.get("marca");
      const modelo = dados.get("modelo");
      const ano = dados.get("ano");
      const placa = dados.get("placa");
      const chassi = dados.get("chassi");
      const km = dados.get("km");
      const preco = dados.get("preco");
      const valorCompra = dados.get("valor_compra");
      const dataCompra = dados.get("data_compra");
      const forn = lerFornecedor(dados);
      const observacao = lerObservacao(dados);

      const valido = v.validarFormulario(form, [
        ["marca", v.textoPreenchido(marca), "Informe a marca"],
        ["modelo", v.textoPreenchido(modelo), "Informe o modelo"],
        ["ano", v.anoValido(ano), `Ano precisa ser entre 1980 e ${anoMaximo}`],
        ["placa", v.textoPreenchido(placa), "Placa é obrigatória"],
        ["placa", !v.textoPreenchido(placa) || v.placaValida(placa), "Placa inválida — use ABC1234 ou ABC1D23"],
        ["chassi", v.chassiValido(chassi), "Chassi precisa ter 17 letras/números"],
        ["km", v.numeroNaoNegativo(km), "Km não pode ser negativo"],
        ["preco", v.numeroPositivo(preco), "Informe um preço maior que zero"],
        ["valor_compra", !valorCompra || v.numeroPositivo(valorCompra), "Valor de compra precisa ser maior que zero"],
        ["valor_compra", !dataCompra || !!valorCompra, "Informe o valor da compra"],
        ["data_compra", !valorCompra || !!dataCompra, "Informe a data da compra"],
        ["data_compra", v.dataNaoFutura(dataCompra), "Data da compra não pode ser no futuro"],
        ...regrasFornecedor(forn),
        ...regrasObservacao(observacao),
      ]);
      if (!valido) return;

      const corpo = {
        marca,
        modelo,
        ano: Number(ano),
        cor: dados.get("cor") || null,
        placa: placa || null,
        chassi: chassi || null,
        km: Number(km || 0),
        condicao: dados.get("condicao"),
        preco_centavos: reaisInputParaCentavos(preco),
        ...corpoFornecedor(forn),
        observacao,
      };
      if (valorCompra) corpo.valor_compra_centavos = reaisInputParaCentavos(valorCompra);
      if (dataCompra) corpo.data_compra = dataCompra;

      try {
        await api.enviar("PATCH", `/motos/${moto.id}`, corpo, {
          rotulo: `Edição da moto ${moto.placa || moto.modelo}`,
        });
        fecharModal(modal);
        avisar("Moto atualizada");
        await carregarLista();
        await abrirDetalhe(moto.id);
      } catch (erro) {
        if (guardadoNaFila(erro, `Edição da moto ${moto.placa || moto.modelo}`)) {
          fecharModal(modal);
          return;
        }
        // Não dá pra pintar campo nenhum de vermelho aqui: o problema não é
        // o que foi digitado, é que a moto mudou de estado embaixo do dono
        // enquanto o modal estava aberto (outra venda entrou primeiro).
        if (erro?.corpo?.detail?.includes("já foi vendida")) {
          fecharModal(modal);
          avisar(erro.corpo.detail, "erro");
          await carregarLista();
          await abrirDetalhe(moto.id);
          return;
        }
        v.mostrarErroDeApi(form, erro, {
          renomear: { preco_centavos: "preco", valor_compra_centavos: "valor_compra" },
          porPalavra: [["placa", "placa"], ["chassi", "chassi"]],
        });
      }
    });
  }

  function abrirModalDespesa(moto) {
    const hoje = hojeIso();
    const modal = abrirModal(`
      <div class="modal-topo"><h3>Lançar gasto — ${escapar(moto.modelo)}</h3></div>
      <form id="form-despesa" novalidate>
        <div class="form-linha">
          <label class="campo">Descrição<input name="descricao" placeholder="Ex: revisão, pneu, guincho" /></label>
          <label class="campo">Valor (R$)<input name="valor" type="number" step="0.01" min="0.01" /></label>
          <label class="campo">Data<input name="data" type="date" max="${hoje}" value="${hoje}" /></label>
        </div>
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-despesa">Cancelar</button>
          <button type="submit" class="botao">Lançar</button>
        </div>
      </form>
    `);

    modal.querySelector("#cancelar-despesa").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#form-despesa").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const form = evento.target;
      const dados = new FormData(form);
      const descricao = dados.get("descricao");
      const valor = dados.get("valor");
      const data = dados.get("data");

      const valido = v.validarFormulario(form, [
        ["descricao", v.textoPreenchido(descricao), "Descreva o gasto"],
        ["valor", v.numeroPositivo(valor), "Informe um valor maior que zero"],
        ["data", v.textoPreenchido(data) && v.dataNaoFutura(data), "Escolha uma data válida, não no futuro"],
      ]);
      if (!valido) return;

      try {
        await api.enviar("POST", `/motos/${moto.id}/despesas`, {
          // Gerado aqui, antes de enviar: é o que impede este mesmo gasto de
          // ser lançado duas vezes se o envio for repetido — duplo clique ou
          // a fila subindo de novo. Ver `backend/app/models/despesa.py`.
          id_cliente: crypto.randomUUID(),
          descricao,
          valor_centavos: reaisInputParaCentavos(valor),
          data,
        }, { rotulo: `Gasto "${descricao}" na moto ${moto.placa || moto.modelo}` });
        fecharModal(modal);
        avisar("Gasto lançado");
        await abrirDetalhe(moto.id);
      } catch (erro) {
        if (guardadoNaFila(erro, `Gasto "${descricao}"`)) {
          fecharModal(modal);
          return;
        }
        v.mostrarErroDeApi(form, erro);
      }
    });
  }

  function abrirModalNovaMoto() {
    const anoMaximo = new Date().getFullYear() + 1;
    const hoje = hojeIso();
    const modal = abrirModal(`
      <div class="modal-topo"><h3>Cadastrar moto</h3></div>
      <p class="fraco">Placa, marca, modelo e ano agora — o resto (compra, valores) se completa depois, na edição.</p>
      <form id="form-nova-moto" novalidate>
        <div class="grade-2">
          ${htmlCampoModelo()}
          <label class="campo">Ano<input name="ano" type="number" min="1980" max="${anoMaximo}" required value="${new Date().getFullYear()}" /></label>
          <label class="campo">Placa<input name="placa" maxlength="8" placeholder="ABC1234 ou ABC1D23" required /></label>
          <label class="campo">Valor que você pagou (R$)<input name="valor_compra" type="number" step="0.01" min="0.01" /></label>
          <label class="campo">Data da compra<input name="data_compra" type="date" max="${hoje}" value="${hoje}" /></label>
        </div>
        <p class="fraco">O valor pago entra no Financeiro como gasto com compra de moto, no dia da compra. Pode deixar em branco e lançar depois, na edição.</p>

        <fieldset class="bloco">
          <legend>Quem vendeu a moto pra loja</legend>
          <p class="fraco">É esta pessoa que assina o contrato de compra. Preencha o que a loja tiver.</p>
          <div class="grade-2">
            <label class="campo">Nome<input name="fornecedor_nome" /></label>
            <label class="campo">CPF<input name="fornecedor_cpf" maxlength="14" placeholder="000.000.000-00" /></label>
            <label class="campo">E-mail<input name="fornecedor_email" placeholder="nome@email.com" /></label>
            <label class="campo">Contato<input name="fornecedor_contato" placeholder="(69) 99999-0000" /></label>
            <label class="campo">É casado(a)?
              <select name="fornecedor_casado">
                <option value="" selected>—</option>
                <option value="nao">Não</option>
                <option value="sim">Sim</option>
              </select>
            </label>
          </div>
          <div class="grade-2" id="bloco-conjuge-novo" hidden>
            <label class="campo">Nome do cônjuge<input name="fornecedor_conjuge_nome" /></label>
            <label class="campo">Contato do cônjuge<input name="fornecedor_conjuge_contato" placeholder="(69) 99999-0000" /></label>
          </div>
        </fieldset>
        ${htmlCampoObservacao("", "Ex.: riscado no tanque; veio sem chave reserva.")}
        <div class="acoes-modal">
          <button type="button" class="botao botao--fantasma" id="cancelar-nova-moto">Cancelar</button>
          <button type="submit" class="botao">Cadastrar</button>
        </div>
      </form>
    `);

    ligarAutocompleteModelo(modal.querySelector("#form-nova-moto"));

    // Cônjuge só aparece quando casado — ver o mesmo no formulário de edição.
    const casadoNovo = modal.querySelector('select[name="fornecedor_casado"]');
    const conjugeNovo = modal.querySelector("#bloco-conjuge-novo");
    casadoNovo.addEventListener("change", () => {
      conjugeNovo.hidden = casadoNovo.value !== "sim";
    });
    modal.querySelector("#cancelar-nova-moto").addEventListener("click", () => fecharModal(modal));
    modal.querySelector("#form-nova-moto").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const form = evento.target;
      const dados = new FormData(form);
      const marca = dados.get("marca");
      const modelo = dados.get("modelo");
      const ano = dados.get("ano");
      const placa = dados.get("placa");
      const valorCompra = dados.get("valor_compra");
      const dataCompra = dados.get("data_compra");
      const forn = lerFornecedor(dados);
      const observacao = lerObservacao(dados);

      const valido = v.validarFormulario(form, [
        ["marca", v.textoPreenchido(marca), "Selecione a marca"],
        ["modelo", v.textoPreenchido(modelo), "Selecione o modelo"],
        ["ano", v.anoValido(ano), `Ano precisa ser entre 1980 e ${anoMaximo}`],
        ["placa", v.textoPreenchido(placa), "Placa é obrigatória"],
        ["placa", !v.textoPreenchido(placa) || v.placaValida(placa), "Placa inválida — use ABC1234 ou ABC1D23"],
        ["valor_compra", !valorCompra || v.numeroPositivo(valorCompra), "O valor pago precisa ser maior que zero"],
        ["data_compra", !valorCompra || v.textoPreenchido(dataCompra), "Informe a data da compra"],
        ["data_compra", v.dataNaoFutura(dataCompra), "Data da compra não pode ser no futuro"],
        ...regrasFornecedor(forn),
        ...regrasObservacao(observacao),
      ]);
      if (!valido) return;

      const corpo = {
        marca,
        modelo,
        ano: Number(ano),
        placa: placa || null,
        ...corpoFornecedor(forn),
        observacao,
      };
      // Valor e data viajam juntos: sem valor, a data preenchida sozinha
      // não vira gasto nenhum e o servidor recusaria o par pela metade.
      if (valorCompra) {
        corpo.valor_compra_centavos = reaisInputParaCentavos(valorCompra);
        corpo.data_compra = dataCompra;
      }

      try {
        const moto = await api.enviar("POST", "/motos", corpo, {
          rotulo: `Moto ${marca} ${modelo} · ${placa}`,
        });
        fecharModal(modal);
        avisar("Moto cadastrada — agora é só completar os dados na edição");
        await carregarLista();
        await abrirDetalhe(moto.id);
      } catch (erro) {
        // Sem internet a moto ainda não tem id, então não há detalhe pra
        // abrir — mas o cadastro está guardado e o modal pode fechar.
        if (guardadoNaFila(erro, `Moto ${placa}`)) {
          fecharModal(modal);
          return;
        }
        v.mostrarErroDeApi(form, erro, {
          porPalavra: [["placa", "placa"], ["chassi", "placa"]],
        });
      }
    });
  }

  raiz.querySelector("#botao-nova-moto").addEventListener("click", abrirModalNovaMoto);
  raiz.querySelector("#botao-buscar-placa").addEventListener("click", () => {
    const placa = raiz.querySelector("#busca-placa").value.trim();
    if (placa) abrirDetalhe(placa, { porPlaca: true });
  });
  raiz.querySelector("#busca-placa").addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") raiz.querySelector("#botao-buscar-placa").click();
  });
  corpoTabela().addEventListener("click", (evento) => {
    const linha = evento.target.closest("tr[data-id]");
    if (linha) abrirDetalhe(linha.dataset.id);
  });

  await carregarLista();
  if (motoAbertaId != null) await abrirDetalhe(motoAbertaId);
}
