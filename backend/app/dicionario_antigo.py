"""Tradução do sistema antigo para o vocabulário da loja.

A aba "Dados" mostrou 183 tabelas com nome de banco (`temp_tb_estado`,
`temp_pemissoes`) e colunas como `DTVENCIMENTO` e `VL_RESTANTE`. O dono nunca
abriu — e não era falta de dado, era falta de tradução. Nome de tabela de
banco não é informação pra quem vende moto.

Este arquivo é a tradução. Ele decide três coisas:

- **Como cada tabela se chama** pra um ser humano.
- **Quais tabelas são ruído** — tabela de estado, NCM, CFOP, ICMS, rateio
  contábil e tabela temporária vêm junto com qualquer ERP do Brasil, são
  iguais em toda loja do país e não dizem nada sobre esta. Ficam escondidas,
  não apagadas: quem quiser, expande.
- **Como cada coluna se chama**, pras que importam.

Cobre os dois sistemas que o Zé Carlos já usou: o ERP genérico em Firebird
(`pessoa`, `vendas_master`) e o sistema de motos em MySQL (`clientes`,
`pedidos`, `it_pedid`) — que é o que tem a vida da loja de verdade.

O que não está aqui aparece com o nome cru. É de propósito: sistema
desconhecido não deve sumir da tela só porque ninguém traduziu ainda.
"""

# Tabelas que dizem algo sobre ESTA loja, na ordem em que interessam.
# A ordem é a da aba: o que o dono procura primeiro vem primeiro. Um lote vem
# de um sistema só, então os dois blocos nunca disputam a mesma tela.
RELEVANTES: dict[str, str] = {
    # --- sistema de motos (MySQL) ---
    "clientes": "Clientes",
    "pedidos": "Vendas",
    "it_pedid": "Motos e itens vendidos",
    "parcelas": "Parcelas em aberto",
    "recebidas": "Parcelas já recebidas",
    "renegociar": "Renegociações",
    "cheques": "Cheques",
    "clientes_contatos": "Referências dos clientes",
    "pedidoscancelados": "Vendas canceladas",
    "it_cancelado": "Itens das vendas canceladas",
    "produtos": "Produtos",
    "produtos_saldo": "Estoque",
    "produtos_entradas": "Entradas de produto",
    "produtos_saidas": "Saídas de produto",
    "produtos_alteracao": "Alterações de produto",
    "mov_prod": "Movimento de estoque",
    "corrente": "Movimento do caixa",
    "veiculos": "Veículos",
    "fornecedor": "Fornecedores",
    "cadven": "Vendedores",
    "pagar": "Contas a pagar",
    "creditos": "Créditos de clientes",
    "custos": "Custos",
    "centro_custo": "Centro de custo",
    "f_pagamentos": "Formas de pagamento",
    "grupos": "Grupos de produto",
    "cobrador": "Cobradores",
    "nfe_saida": "Notas fiscais emitidas",
    "nfe_pedidos": "Notas das vendas",
    "xml_nfe": "XML das notas",
    "nfe_devolucao": "Notas de devolução",
    "devolucoes_compras": "Devoluções de compra",
    "it_devolucoes": "Itens devolvidos",
    "it_troca": "Itens trocados",
    "usuario": "Usuários do sistema",
    # --- ERP genérico (Firebird) ---
    "creceber": "Contas a receber",
    "crrecebimento": "Recebimentos",
    "pessoa": "Clientes e fornecedores",
    "vendas_master": "Vendas",
    "vendas_detalhe": "Itens das vendas",
    "vendas_fpg": "Pagamentos das vendas",
    "produto": "Produtos",
    "prod_ultimos_precos": "Últimos preços",
    "vendedores": "Vendedores",
    "empresa": "Dados da empresa",
    "caixa": "Caixa",
    "resumo_caixa": "Resumo do caixa",
    "contas": "Contas bancárias",
    "contas_movimento": "Movimento das contas",
    "nfce_master": "Notas fiscais",
    "nfce_detalhe": "Itens das notas",
    "marca": "Marcas",
    "grupo": "Grupos de produto",
    "tabela_preco": "Tabelas de preço",
    "plano": "Planos de pagamento",
    "forma_pagamento": "Formas de pagamento",
    "acerta_estoque": "Ajustes de estoque",
}

# Ruído: vem de fábrica com o ERP, é igual em toda loja do Brasil.
# Casado por prefixo porque cada ERP nomeia essas do seu jeito.
# Prefixo só entra aqui quando não tem como pegar tabela boa junto: `tabela_`
# esconderia `tabela_preco`, `convenio` esconderia um cadastro de convênio.
# Na dúvida o nome vai pro conjunto exato abaixo — o dicionário erra pra
# mostrar, nunca pra esconder.
PREFIXOS_DE_RUIDO = (
    "tb_", "temp_", "tmp_", "ibpt", "cidade", "cest", "cfop",
    "cst", "csosn", "ncm", "cts_", "motivo_", "produto_impostos", "aliq",
    "tabela_icms", "telas", "pemissoes", "permissoes", "usuarios_telas",
    "veiculo_", "municipio", "pais", "estado", "banco_", "feriado",
)

# Ruído que não cabe em prefixo nenhum: nome próprio de tabela de controle
# interno ou de referência fiscal. Contador de documento, rateio contábil,
# tabela do Simples Nacional, cadastro auxiliar de duas linhas.
RUIDO: frozenset[str] = frozenset({
    "rateiodp", "custo_medio", "tipi", "tsn", "origem_cst", "tab_partilha",
    "procesos", "codigo", "contador", "it_tmp", "cadtec", "tipoitem",
    "unidade", "placasentrega", "entregador", "clientes_autorizacao",
    "cbd001det", "cbddocreferenciado", "convenioicms", "tabelas_sped",
    "tabela_ibpt", "nfe_parametros", "tab_cest", "tab_partilha",
})


def e_ruido(tabela: str) -> bool:
    """Tabela de referência fiscal ou de controle interno do próprio ERP."""
    nome = tabela.lower()
    if nome in RELEVANTES:
        return False
    return nome in RUIDO or nome.startswith(PREFIXOS_DE_RUIDO)


def nome_da_tabela(tabela: str) -> str:
    """O nome que aparece na tela."""
    nome = tabela.lower()
    if nome in RELEVANTES:
        return RELEVANTES[nome]
    # Sem tradução: pelo menos tira o underscore e põe maiúscula.
    return tabela.replace("_", " ").strip().capitalize()


def ordem_da_tabela(tabela: str) -> int:
    """Menor vem primeiro. Ruído vai pro fim."""
    nome = tabela.lower()
    if nome in RELEVANTES:
        return list(RELEVANTES).index(nome)
    return 500 if e_ruido(nome) else 100


# Colunas que aparecem nas tabelas que importam. O resto mostra o nome cru.
COLUNAS: dict[str, str] = {
    # --- quem é a pessoa ---
    "codcli": "Cód. cliente",
    "nome": "Nome",
    "razao": "Nome / Razão social",
    "razao_soc": "Razão social",
    "fantasia": "Nome fantasia",
    "cnpj": "CPF / CNPJ",
    "cnpj_cpf": "CPF / CNPJ",
    "cpf": "CPF",
    "insc_rg": "RG",
    "rg": "RG",
    "ie": "Inscrição estadual",
    "fone": "Telefone",
    "fone1": "Telefone",
    "fone2": "Telefone 2",
    "telefone": "Telefone",
    "celular": "Celular",
    "celular1": "Celular",
    "celular2": "Celular 2",
    "whatsapp": "WhatsApp",
    "email": "E-mail",
    "email1": "E-mail",
    "email2": "E-mail 2",
    "endereco": "Endereço",
    "numero": "Número",
    "complemento": "Complemento",
    "bairro": "Bairro",
    "cidade": "Cidade",
    "municipio": "Cidade",
    "uf": "UF",
    "estado": "UF",
    "cep": "CEP",
    "dtnasc": "Nascimento",
    "dt_nasc": "Nascimento",
    "est_civil": "Estado civil",
    "ecivil": "Estado civil",
    "sexo": "Sexo",
    "profissao": "Profissão",
    "obs": "Observação",
    "obs_venda": "Observação de venda",
    "obs_receb": "Observação de cobrança",
    "dt_cadastro": "Cadastrado em",
    "dtcad": "Cadastrado em",
    "dtalt": "Alterado em",
    "dtcons": "Última consulta",
    "ativo": "Ativo",
    "limite": "Limite de crédito",
    "credito": "Crédito",
    "debito": "Débito",
    "prazo": "Prazo",
    "spc": "SPC",
    "dtspc": "Data do SPC",
    "negativo": "Negativado",
    "motivo": "Motivo",
    "portador": "Portador",
    "contatos": "Contatos",
    # família e trabalho — é o que o crediário da loja usa pra confiar
    "conjuge": "Cônjuge",
    "fone_conj": "Telefone do cônjuge",
    "nasc_conju": "Nascimento do cônjuge",
    "trab_conj": "Trabalho do cônjuge",
    "salario_conj": "Salário do cônjuge",
    "pai": "Pai",
    "mae": "Mãe",
    "parentesco": "Parentesco",
    "pessoa1": "Referência 1",
    "pessoa2": "Referência 2",
    "grau1": "Parentesco da referência 1",
    "grau2": "Parentesco da referência 2",
    "fonepes1": "Telefone da referência 1",
    "fonepes2": "Telefone da referência 2",
    "loja1": "Referência comercial 1",
    "loja2": "Referência comercial 2",
    "loja3": "Referência comercial 3",
    "fone_loja1": "Telefone comercial 1",
    "fone_loja2": "Telefone comercial 2",
    "fone_loja3": "Telefone comercial 3",
    "loc_trab": "Local de trabalho",
    "end_trab": "Endereço do trabalho",
    "fone_trab": "Telefone do trabalho",
    "cargo": "Cargo",
    "salario": "Salário",
    "admissao": "Admissão",
    "cob_end": "Endereço de cobrança",
    "cob_bairro": "Bairro de cobrança",
    "cob_cidade": "Cidade de cobrança",
    "cob_cep": "CEP de cobrança",
    "cob_estado": "UF de cobrança",
    "cob_email": "E-mail de cobrança",
    # --- dinheiro a receber ---
    "valor": "Valor",
    "vencimento": "Vencimento",
    "dtvencimento": "Vencimento",
    "datavenc": "Vencimento",
    "emissao": "Data",
    "data_pagto": "Pago em",
    "datapag": "Pago em",
    "data_baixa": "Baixado em",
    "data_recebimento": "Recebido em",
    "valor_rec": "Valor recebido",
    "vrecebido": "Valor recebido",
    "valor_recebido": "Valor recebido",
    "valorpag": "Valor pago",
    "valorpar": "Valor da parcela",
    "valortot": "Valor total",
    "vpago": "Valor pago",
    "vl_restante": "Falta pagar",
    "situacao": "Situação",
    "status": "Situação",
    "st": "Situação",
    "juros": "Juros",
    "valor_juros": "Juros",
    "valjuros": "Juros pago",
    "valor_abatimento": "Abatimento",
    "desconto": "Desconto",
    "valdesc": "Desconto (R$)",
    "historico": "Histórico",
    "doc": "Documento",
    "documento": "Documento",
    "nboleto": "Boleto",
    "valor_parcela": "Valor da parcela",
    "pc": "Parcela",
    "numparc": "Nº da parcela",
    "condicao": "Condição",
    "formapagto": "Forma de pagamento",
    "tipo_pgto": "Forma de pagamento",
    "cobrador": "Cobrador",
    "banco": "Banco",
    "agencia": "Agência",
    "conta": "Conta",
    # cheque
    "cheque": "Nº do cheque",
    "numero_cheque": "Cheque",
    "nome_cli": "Nome no cheque",
    "doc_cli": "CPF / CNPJ no cheque",
    "data_dep": "Depositado em",
    "baixado": "Baixado",
    "liquidado": "Liquidado",
    "devolvido": "Devolvido",
    # --- venda ---
    "nrped": "Nº da venda",
    "nf": "Nota fiscal",
    "vendedor": "Vendedor",
    "operador": "Operador",
    "usuario": "Usuário",
    "data_emissao": "Data",
    "data_saida": "Saída",
    "data": "Data",
    "hora": "Hora",
    "subtotal": "Subtotal",
    "total": "Total",
    "totvenda": "Total",
    "valorliq": "Valor líquido",
    "acrescimo": "Acréscimo",
    "troco": "Troco",
    "dinheiro": "Dinheiro",
    "cartao": "Cartão",
    "pix": "Pix",
    "vale": "Vale",
    "observacoes": "Observações",
    "cpf_nota": "CPF na nota",
    "tipo_venda": "Tipo de venda",
    "devolucao": "Devolução",
    "frete": "Frete",
    "taxa_entrega": "Taxa de entrega",
    "entrega": "Entrega",
    "motorista": "Motorista",
    "cupom": "Cupom",
    "comissao": "Comissão",
    "valcomis": "Comissão",
    # --- a moto / o item ---
    "placa": "Placa",
    "km": "KM",
    "chassi": "Chassi",
    "marca": "Marca",
    "modelo": "Modelo",
    "cor": "Cor",
    "ano": "Ano",
    "item": "Item",
    "cod_item": "Cód. produto",
    "descr_item": "Descrição",
    "descr_serv": "Serviço",
    "descricao": "Descrição",
    "codbarra": "Código de barras",
    "referencia": "Referência",
    "unidade": "Unidade",
    "quant": "Quantidade",
    "quantidade": "Quantidade",
    "quant_dev": "Quantidade devolvida",
    "quant_ent": "Entrada",
    "quant_sai": "Saída",
    "unit": "Valor unitário",
    "venda": "Valor de venda",
    "compra": "Valor de compra",
    "custo": "Custo",
    "cusmed": "Custo médio",
    "pr_custo": "Preço de custo",
    "pr_venda": "Preço de venda",
    "pr_avista": "Preço à vista",
    "pr_aprazo": "Preço a prazo",
    "saldo": "Saldo",
    "qtd_atual": "Estoque",
    "qtd_min": "Estoque mínimo",
    "minimo": "Estoque mínimo",
    "maximo": "Estoque máximo",
    "margem": "Margem",
    "garantia": "Garantia",
    "validade": "Validade",
    "fornecedor": "Fornecedor",
    "tecnico": "Técnico",
    "tipo_item": "Tipo",
    "tipo": "Tipo",
    "grupo": "Grupo",
    "subgrupo": "Subgrupo",
    "lancamento": "Lançamento",
    # --- genéricos ---
    "codigo": "Código",
}

# Colunas que não interessam a ninguém: controle interno do ERP, campos de
# remessa de boleto, tributação, flags de sincronização. Somem da tela — mas
# continuam guardadas, e a tabela tem um "mostrar tudo" pra quando precisar.
PREFIXOS_DE_COLUNA_ESCONDIDA = (
    "fk", "registro_", "retorno_", "remessa", "id_cbr", "flag",
    "path_pdf", "envio_whats", "dash_", "chave_ativacao", "vecto_ativacao",
    # tributação: igual em todo ERP do Brasil, não diz nada sobre a loja
    "cst", "cfop", "ncm", "cest", "icms", "pis", "cofins", "vtottrib",
    "base_icms", "cod_ncm", "tributacao", "ipi", "aliq", "perc", "csll",
    "irpj", "cpp", "dif_alicot", "codigo_anp", "suframa",
    # controle interno
    "id_", "exp_", "dt_select", "dt_alt", "us_alt", "cod_barra", "prctab",
    "tabela", "tx_", "emitir", "bloqueia", "desconto_agua", "desconto_gas",
    "descontoagua", "descontogas", "chave_", "num_ecf", "serie_ecf",
    "obs_cst", "cclass_trib", "poutrasdespesas", "envia_balanca",
)

# Escondidas por nome exato: não dá pra pegar por prefixo sem levar coluna
# boa junto ("se" pegaria "sexo", "im" pegaria "imagem" e "importado").
COLUNAS_ESCONDIDAS: frozenset[str] = frozenset({
    "selecao", "requisicao", "registro", "lote", "filial", "contacaixa",
    "codmun", "codpais", "imagem", "regime", "im", "fis_jur", "fax",
    "avisa_venc", "deposito", "envelope", "convenio", "cob_protesto",
    "modalidadefrete", "tipo_cartao", "destinooperacao", "consumidorfinal",
    "autorizacao_compra", "se", "bx", "setor", "formulario", "libera",
    "dsc_receb", "tp_receb", "obsbloqueio", "tpstatus", "descstatus",
    "conferido", "bloqueado", "fechado", "senha", "pessoa_autorizada",
    "markup", "serie", "entrege", "cusant", "cod_kit", "quant_kit",
    "codtec", "codfbr", "codfor", "conta_dep", "conferencia",
    "dt_conferencia", "bloqueiasaldo", "c_custo", "s_custo",
    "conta_contabil", "cod_contabil", "seqdoc", "clifor", "codvend",
    "pespro", "tara", "locacao", "lista", "embalagem", "unid_inv",
    "saldo_cons", "quant_caixa", "desc_caixa", "desc_promo", "datval",
    "datalt", "dtvalidadepromocao", "dtalt_saldo", "codtitulo",
    "id", "nao_bloqueia_parcelas", "vendedor_padrao",
    # O XML da nota tem 7 mil caracteres: some da grade e abre na tela da
    # nota fiscal (ver `servicos/nota_fiscal.py`).
    "xml", "xml_can",
})


def coluna_escondida(coluna: str) -> bool:
    nome = coluna.lower()
    return nome in COLUNAS_ESCONDIDAS or nome.startswith(PREFIXOS_DE_COLUNA_ESCONDIDA)


def nome_da_coluna(coluna: str) -> str:
    nome = coluna.lower()
    return COLUNAS.get(nome, coluna.replace("_", " ").strip().capitalize())


# Colunas que vêm antes de todas as outras: são por onde o dono acha o
# registro. Sem isso a tela de Clientes abria com "Vendedor", "Não bloqueia
# parcelas" e "Ativo" nas três primeiras colunas, e o nome do cliente em
# quarto — porque a ordem era a do `CREATE TABLE` do ERP, não a de quem lê.
PRIMEIRAS = (
    "nrped", "nf", "item", "pc", "numparc",
    "codcli", "nome", "descr_item", "placa", "marca",
    "emissao", "data", "hora",
)


def ordem_da_coluna(coluna: str) -> int:
    """Menor vem primeiro. Coluna sem tradução vai pro fim, na ordem do
    arquivo — não some, só deixa de disputar o começo da tabela."""
    nome = coluna.lower()
    if nome in PRIMEIRAS:
        return PRIMEIRAS.index(nome)
    if nome in COLUNAS:
        return len(PRIMEIRAS) + list(COLUNAS).index(nome)
    return 10_000


def titulos(colunas: list[str]) -> list[str]:
    """Os títulos na ordem das colunas dadas, com o nome cru entre parênteses
    quando dois campos diferentes traduzem pro mesmo título.

    `st` e `status` viram os dois "Situação", e `juros`/`valor_juros` viram os
    dois "Juros": três colunas "Situação" lado a lado não dizem qual é qual, e
    o dono precisa saber em qual olhar.
    """
    nomes = [nome_da_coluna(c) for c in colunas]
    repetidos = {n for n in nomes if nomes.count(n) > 1}
    return [
        f"{n} ({c.lower()})" if n in repetidos else n
        for c, n in zip(colunas, nomes)
    ]
