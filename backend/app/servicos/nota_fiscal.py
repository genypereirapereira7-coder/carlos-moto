"""Abrir a nota fiscal guardada no backup do sistema antigo.

O backup traz o **XML inteiro** de cada NF-e (uns 7 KB por nota, 100 notas). Na
tabela isso aparecia como uma coluna ilegível de sete mil caracteres. Aqui o
XML é lido e virado nos campos que a loja olha: número, data, quem emitiu, pra
quem, os itens, o total e a autorização da Receita.

**Por que `defusedxml` e não `xml.etree` direto:** o XML vem de arquivo que
alguém envia pelo navegador. A biblioteca padrão do Python é explicitamente
insegura pra XML de fora — uma nota com poucas linhas de DTD consegue consumir
toda a memória da máquina (o "billion laughs"). O `defusedxml` recusa DTD,
entidade externa e bomba de expansão antes de tentar montar a árvore.
"""

from dataclasses import dataclass, field

from defusedxml.ElementTree import fromstring

# Todo campo da NF-e vive neste namespace.
_NS = {"n": "http://www.portalfiscal.inf.br/nfe"}

# Teto de tamanho. Nota de moto tem 7 KB; 4 MB é folga de sobra e ainda barra
# um arquivo montado pra ocupar memória.
_MAX_BYTES = 4 * 1024 * 1024

# `tPag` da NF-e. Só os códigos que aparecem em loja; o resto sai como o número
# mesmo, que é melhor do que mentir o nome.
_FORMA_DE_PAGAMENTO = {
    "01": "Dinheiro",
    "02": "Cheque",
    "03": "Cartão de crédito",
    "04": "Cartão de débito",
    "05": "Crédito da loja",
    "14": "Duplicata mercantil",
    "15": "Boleto bancário",
    "16": "Depósito bancário",
    "17": "Pix",
    "18": "Transferência bancária",
    "19": "Programa de fidelidade",
    "90": "Sem pagamento",
    "99": "Outros",
}


class NotaIlegivel(Exception):
    """O XML não é uma NF-e que dê pra ler."""


@dataclass
class Item:
    codigo: str = ""
    descricao: str = ""
    unidade: str = ""
    quantidade: str = ""
    valor_unitario: str = ""
    valor_total: str = ""
    ncm: str = ""
    cfop: str = ""


@dataclass
class Pessoa:
    nome: str = ""
    fantasia: str = ""
    documento: str = ""
    inscricao: str = ""
    endereco: str = ""
    telefone: str = ""


@dataclass
class Nota:
    numero: str = ""
    serie: str = ""
    chave: str = ""
    emitida_em: str = ""
    natureza: str = ""
    tipo: str = ""
    emitente: Pessoa = field(default_factory=Pessoa)
    destinatario: Pessoa = field(default_factory=Pessoa)
    itens: list[Item] = field(default_factory=list)
    valor_produtos: str = ""
    valor_desconto: str = ""
    valor_frete: str = ""
    valor_total: str = ""
    pagamentos: list[dict] = field(default_factory=list)
    protocolo: str = ""
    autorizada_em: str = ""
    situacao: str = ""
    observacao: str = ""
    cancelada: bool = False


def _texto(no, caminho: str) -> str:
    if no is None:
        return ""
    achado = no.find(caminho, _NS)
    return (achado.text or "").strip() if achado is not None else ""


def _endereco(no) -> str:
    """O endereço da nota numa linha, do jeito que se lê num documento."""
    if no is None:
        return ""
    rua = ", ".join(p for p in (_texto(no, "n:xLgr"), _texto(no, "n:nro")) if p)
    cidade = " - ".join(p for p in (_texto(no, "n:xMun"), _texto(no, "n:UF")) if p)
    cep = _texto(no, "n:CEP")
    if len(cep) == 8:
        cep = f"{cep[:5]}-{cep[5:]}"
    partes = (rua, _texto(no, "n:xCpl"), _texto(no, "n:xBairro"), cidade, cep)
    return " · ".join(p for p in partes if p)


def _pessoa(no, prefixo: str) -> Pessoa:
    if no is None:
        return Pessoa()
    return Pessoa(
        nome=_texto(no, "n:xNome"),
        fantasia=_texto(no, "n:xFant"),
        # Pessoa física manda CPF, empresa manda CNPJ. Vem um dos dois.
        documento=_texto(no, "n:CNPJ") or _texto(no, "n:CPF"),
        inscricao=_texto(no, "n:IE"),
        endereco=_endereco(no.find(prefixo, _NS)),
        telefone=_texto(no, f"{prefixo}/n:fone"),
    )


def ler(xml: str, xml_cancelamento: str | None = None) -> Nota:
    """O XML da NF-e nos campos que a loja olha."""
    bruto = (xml or "").strip()
    if not bruto:
        raise NotaIlegivel("Esta nota não tem XML guardado no backup")
    if len(bruto.encode("utf-8", "ignore")) > _MAX_BYTES:
        raise NotaIlegivel("XML grande demais pra ser uma nota fiscal")

    try:
        raiz = fromstring(bruto)
    except Exception as erro:  # defusedxml levanta tipos próprios
        raise NotaIlegivel("O XML desta nota está corrompido") from erro

    # O arquivo pode ser o `nfeProc` (nota + autorização) ou só a `NFe`.
    inf = raiz.find(".//n:infNFe", _NS)
    if inf is None:
        raise NotaIlegivel("Não achei os dados da nota dentro do XML")

    ide = inf.find("n:ide", _NS)
    total = inf.find("n:total/n:ICMSTot", _NS)
    prot = raiz.find(".//n:infProt", _NS)

    nota = Nota(
        numero=_texto(ide, "n:nNF"),
        serie=_texto(ide, "n:serie"),
        # O Id vem como "NFe" + os 44 dígitos da chave.
        chave=(inf.get("Id") or "").replace("NFe", "").strip(),
        emitida_em=_texto(ide, "n:dhEmi") or _texto(ide, "n:dEmi"),
        natureza=_texto(ide, "n:natOp"),
        tipo="Saída" if _texto(ide, "n:tpNF") == "1" else "Entrada",
        emitente=_pessoa(inf.find("n:emit", _NS), "n:enderEmit"),
        destinatario=_pessoa(inf.find("n:dest", _NS), "n:enderDest"),
        valor_produtos=_texto(total, "n:vProd"),
        valor_desconto=_texto(total, "n:vDesc"),
        valor_frete=_texto(total, "n:vFrete"),
        valor_total=_texto(total, "n:vNF"),
        protocolo=_texto(prot, "n:nProt"),
        autorizada_em=_texto(prot, "n:dhRecbto"),
        situacao=_texto(prot, "n:xMotivo"),
        observacao=_texto(inf, "n:infAdic/n:infCpl"),
        cancelada=bool((xml_cancelamento or "").strip()),
    )

    for det in inf.findall("n:det", _NS):
        prod = det.find("n:prod", _NS)
        if prod is None:
            continue
        nota.itens.append(Item(
            codigo=_texto(prod, "n:cProd"),
            descricao=_texto(prod, "n:xProd"),
            unidade=_texto(prod, "n:uCom"),
            quantidade=_texto(prod, "n:qCom"),
            valor_unitario=_texto(prod, "n:vUnCom"),
            valor_total=_texto(prod, "n:vProd"),
            ncm=_texto(prod, "n:NCM"),
            cfop=_texto(prod, "n:CFOP"),
        ))

    for pag in inf.findall("n:pag/n:detPag", _NS):
        codigo = _texto(pag, "n:tPag")
        nota.pagamentos.append({
            "forma": _FORMA_DE_PAGAMENTO.get(codigo, codigo),
            "valor": _texto(pag, "n:vPag"),
        })

    return nota
