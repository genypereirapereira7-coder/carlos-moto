"""Lê um backup `.sql` de MySQL/MariaDB — o que a maioria dos sistemas exporta.

Existe porque o sistema antigo da loja entregou um `BACKUP.SQL` de 13 MB, e
exigir que o dono converta isso pra CSV antes de usar seria transferir pra ele
um trabalho que a máquina faz.

**Por que um leitor próprio, e não `mysql < backup.sql`:** rodar o dump exigiria
instalar e subir um MySQL só pra ler um arquivo. O que interessa aqui são as
linhas, e elas estão em texto no arquivo.

**Por que não expressão regular:** valor de texto em dump vem com vírgula,
parêntese e aspas escapada dentro (`'TROCA FEITA EM 14/01, R$1.000,00'`). Regex
quebra a linha no lugar errado e embaralha as colunas — o nome de um cliente
vai pro campo de CPF e ninguém percebe. Daí o percorrer caractere a caractere
abaixo: é mais código, e é o que não erra.
"""

import logging
import re

log = logging.getLogger("carlosmoto.dump_mysql")

_CREATE = re.compile(r"^CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF NOT EXISTS\s+)?[`\"]?([A-Za-z_0-9]+)[`\"]?", re.I)
# A lista de colunas é opcional: o mysqldump escreve `INSERT INTO t VALUES`, o
# phpMyAdmin escreve `INSERT INTO t (a, b) VALUES`. Sem aceitar as duas, um
# dump inteiro entra vazio sem dar erro.
_INSERT = re.compile(
    r"^INSERT\s+(?:IGNORE\s+)?INTO\s+[`\"]?([A-Za-z_0-9]+)[`\"]?\s*(\([^)]*\))?\s*VALUES\s*",
    re.I,
)
_NOME = re.compile(r"[`\"]?([A-Za-z_0-9]+)[`\"]?")

# Linha de dentro do CREATE que define uma chave, não uma coluna.
_NAO_E_COLUNA = (
    "primary", "unique", "key", "index", "constraint", "fulltext", "spatial",
    "check", "foreign",
)

# O que `\n` e companhia significam dentro de um texto do dump.
_ESCAPES = {
    "0": "\0", "n": "\n", "r": "\r", "t": "\t", "b": "\b",
    "Z": "\x1a", "\\": "\\", "'": "'", '"': '"', "%": "\\%", "_": "\\_",
}


def _ler_valores(trecho: str) -> list[list[str | None]]:
    """Quebra `(1,'Ana',NULL),(2,'Bruno, o Silva',3.5)` em listas de valores.

    Percorre caractere a caractere porque dentro de aspas tudo é texto:
    vírgula, parêntese e aspas escapada não separam nada.
    """
    linhas: list[list[str | None]] = []
    atual: list[str | None] = []
    pedaco: list[str] = []
    dentro_de_texto = False
    era_texto = False
    dentro_de_linha = False
    i = 0
    tamanho = len(trecho)

    while i < tamanho:
        c = trecho[i]

        if dentro_de_texto:
            if c == "\\" and i + 1 < tamanho:
                seguinte = trecho[i + 1]
                pedaco.append(_ESCAPES.get(seguinte, seguinte))
                i += 2
                continue
            # `''` dentro de texto é uma aspa, não o fim dele.
            if c == "'" and i + 1 < tamanho and trecho[i + 1] == "'":
                pedaco.append("'")
                i += 2
                continue
            if c == "'":
                dentro_de_texto = False
                i += 1
                continue
            pedaco.append(c)
            i += 1
            continue

        if c == "(" and not dentro_de_linha:
            dentro_de_linha = True
            atual, pedaco, era_texto = [], [], False
            i += 1
            continue

        if not dentro_de_linha:
            i += 1
            continue

        if c == "'":
            dentro_de_texto = True
            era_texto = True
            i += 1
            continue

        if c in ",)":
            bruto = "".join(pedaco).strip()
            # `NULL` sem aspas é ausência de valor. `'NULL'` com aspas é o
            # texto "NULL", e são coisas diferentes.
            atual.append(None if (not era_texto and bruto.upper() == "NULL") else bruto)
            pedaco, era_texto = [], False
            if c == ")":
                linhas.append(atual)
                dentro_de_linha = False
            i += 1
            continue

        pedaco.append(c)
        i += 1

    return linhas


def _ate_o_ponto_e_virgula(linha: str, dentro_de_texto: bool) -> tuple[bool, bool]:
    """`(terminou, dentro_de_texto)` depois de varrer esta linha.

    Um `INSERT` pode ocupar uma linha ou dez mil: o mysqldump põe tudo numa
    linha, o phpMyAdmin quebra a cada registro. Quem decide o fim é o `;` fora
    de aspas — `;` dentro de um texto ('PAGO; VER OBS') não termina nada.

    Varre cada linha uma vez só, levando o estado de aspas adiante, porque
    reler o acumulado a cada linha nova viraria trabalho ao quadrado num
    arquivo de 13 MB.
    """
    i, n = 0, len(linha)
    while i < n:
        c = linha[i]
        if dentro_de_texto:
            if c == "\\":
                i += 2
                continue
            if c == "'" and i + 1 < n and linha[i + 1] == "'":
                i += 2
                continue
            if c == "'":
                dentro_de_texto = False
            i += 1
            continue
        if c == "'":
            dentro_de_texto = True
        elif c == ";":
            return True, False
        i += 1
    return False, dentro_de_texto


def _colunas_do_create(instrucao: str) -> list[str]:
    """Os nomes de coluna de um `CREATE TABLE`, na ordem em que estão nele.

    Não dá pra pegar por linha: o mysqldump põe uma coluna por linha, mas
    `CREATE TABLE tipi (ncm varchar(10), descricao text) ENGINE=InnoDB;` cabe
    numa linha só — e aí ler por linha não acha coluna nenhuma. Aqui o corpo é
    partido nas vírgulas **do primeiro nível**: as de dentro de `varchar(10)`,
    `decimal(10,2)` e `enum('a','b')` não separam coluna.
    """
    colunas: list[str] = []

    def guardar(pedaco: list[str]) -> None:
        texto = "".join(pedaco).strip()
        if not texto:
            return
        primeira = texto.split(None, 1)[0].strip("`\"").lower()
        if primeira in _NAO_E_COLUNA:
            return  # PRIMARY KEY, KEY, CONSTRAINT: não é coluna
        achou = _NOME.match(texto)
        if achou:
            colunas.append(achou.group(1))

    pedaco: list[str] = []
    profundidade = 0
    dentro_de_texto = False
    i, n = 0, len(instrucao)

    while i < n:
        c = instrucao[i]

        if dentro_de_texto:
            # O conteúdo do texto não interessa (é default ou enum): só
            # atravessar sem deixar vírgula de dentro dele partir coluna.
            if c == "\\":
                i += 2
                continue
            if c == "'" and i + 1 < n and instrucao[i + 1] == "'":
                i += 2
                continue
            if c == "'":
                dentro_de_texto = False
            i += 1
            continue

        if c == "'":
            dentro_de_texto = True
            i += 1
            continue

        if c == "(":
            profundidade += 1
            if profundidade == 1:
                pedaco = []
                i += 1
                continue
        elif c == ")":
            profundidade -= 1
            if profundidade == 0:
                guardar(pedaco)
                break

        if profundidade == 1 and c == ",":
            guardar(pedaco)
            pedaco = []
            i += 1
            continue

        if profundidade >= 1:
            pedaco.append(c)
        i += 1

    return colunas


def ler(texto: str) -> dict[str, list[dict]]:
    """Devolve `{tabela: [linha, ...]}`, cada linha `{coluna: valor}`.

    Uma instrução pode ocupar qualquer número de linhas, então o arquivo é
    lido por **instrução** (até o `;` fora de aspas), não por linha. Ler por
    linha fazia duas coisas erradas em silêncio: perdia os registros do
    segundo em diante num INSERT quebrado, e um CREATE de uma linha engolia o
    INSERT que vinha depois — a tabela inteira sumia sem erro nenhum.
    """
    colunas_por_tabela: dict[str, list[str]] = {}
    linhas_por_tabela: dict[str, list[dict]] = {}

    todas = texto.splitlines()
    i = 0
    while i < len(todas):
        linha = todas[i]
        i += 1

        criar = _CREATE.match(linha)
        inserir = None if criar else _INSERT.match(linha)
        if not criar and not inserir:
            continue

        pedacos = [linha]
        terminou, dentro_de_texto = _ate_o_ponto_e_virgula(linha, False)
        while not terminou and i < len(todas):
            pedacos.append(todas[i])
            terminou, dentro_de_texto = _ate_o_ponto_e_virgula(todas[i], dentro_de_texto)
            i += 1
        instrucao = "\n".join(pedacos)

        if criar:
            colunas_por_tabela[criar.group(1).lower()] = _colunas_do_create(instrucao)
            continue

        tabela = inserir.group(1).lower()
        # A lista de colunas do próprio INSERT manda: quando ela vem, é ela
        # que diz a ordem dos valores, não a ordem do CREATE TABLE.
        if inserir.group(2):
            colunas = _colunas_do_create(inserir.group(2))
        else:
            colunas = colunas_por_tabela.get(tabela, [])

        valores = _ler_valores(instrucao[inserir.end():])
        destino = linhas_por_tabela.setdefault(tabela, [])

        for valor in valores:
            if colunas and len(valor) == len(colunas):
                destino.append(dict(zip(colunas, valor)))
            else:
                # Sem `CREATE TABLE` no arquivo, ou contagem diferente: guarda
                # por posição. Perder a linha seria pior — pode ser o único
                # registro de um cliente.
                if colunas:
                    log.warning(
                        "%s: linha com %d valores e %d colunas",
                        tabela, len(valor), len(colunas),
                    )
                destino.append({f"coluna_{pos + 1}": v for pos, v in enumerate(valor)})

    return linhas_por_tabela
