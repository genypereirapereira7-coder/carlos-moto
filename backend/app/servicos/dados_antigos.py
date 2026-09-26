"""Ler os CSVs do sistema antigo e guardar como arquivo consultável.

Aceita **CSV** e **backup `.sql` de MySQL/MariaDB** — que é o que a maioria
dos sistemas exporta. Nada de conexão direta ao banco antigo: o sistema não
precisa saber de onde veio, e a loja não fica presa a um conversor que só serve
pra um ERP. Ver `dump_mysql.py` pra como o `.sql` é lido.

Três coisas que este arquivo trata porque dado de sistema antigo é sujo:

- **Separador.** Uns exportam com `;`, outros com `,` ou tabulação. Descobre
  olhando a primeira linha, em vez de exigir um formato.
- **Acentuação.** Sistema velho de Windows grava em `cp1252`. Ler como UTF-8
  estoura ou vira `Jo?o`. Tenta UTF-8 e cai pra `cp1252`.
- **Coluna sem nome e linha torta.** Arquivo exportado na mão tem disso. Nada
  aqui pode derrubar a importação inteira por causa de uma linha ruim.
"""

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dado_antigo import LinhaAntiga, LoteAntigo
from app.servicos import dump_mysql

log = logging.getLogger("carlosmoto.dados_antigos")

# Teto por arquivo, pra um CSV gigante não derrubar o processo.
_MAX_LINHAS_POR_TABELA = 100_000


@dataclass
class Resultado:
    lote_id: str = ""
    tabelas: dict[str, int] = field(default_factory=dict)
    ignorados: list[str] = field(default_factory=list)

    @property
    def total_linhas(self) -> int:
        return sum(self.tabelas.values())


def _texto(dados: bytes) -> str:
    """Decodifica sem estourar. Sistema velho de Windows é `cp1252`."""
    for codificacao in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    # `latin-1` aceita qualquer byte, então isto quase nunca acontece.
    return dados.decode("latin-1", errors="replace")


def _separador(primeira_linha: str) -> str:
    """Qual caractere separa as colunas. Vence quem aparece mais."""
    candidatos = {sep: primeira_linha.count(sep) for sep in (";", ",", "\t", "|")}
    melhor = max(candidatos, key=candidatos.get)
    return melhor if candidatos[melhor] > 0 else ";"


def ler_csv(nome_arquivo: str, conteudo: bytes) -> tuple[str, list[dict]]:
    """Devolve `(nome_da_tabela, linhas)`. Nome da tabela = nome do arquivo."""
    tabela = nome_arquivo.rsplit("/", 1)[-1].rsplit(".", 1)[0].strip().lower()
    texto = _texto(conteudo)
    if not texto.strip():
        return tabela, []

    primeira = texto.split("\n", 1)[0]
    leitor = csv.reader(io.StringIO(texto), delimiter=_separador(primeira))

    try:
        cabecalho = next(leitor)
    except StopIteration:
        return tabela, []

    # Coluna sem nome ganha um: senão a linha inteira seria descartada.
    colunas = [
        (c.strip() or f"coluna_{i + 1}") for i, c in enumerate(cabecalho)
    ]

    linhas: list[dict] = []
    for bruta in leitor:
        if len(linhas) >= _MAX_LINHAS_POR_TABELA:
            log.warning("%s: passou de %d linhas, o resto foi ignorado", tabela, _MAX_LINHAS_POR_TABELA)
            break
        # Linha vazia não é dado.
        if not any(v.strip() for v in bruta):
            continue
        # Linha com menos/mais campos que o cabeçalho: completa ou sobra em
        # `coluna_N`. Descartar perderia dado que talvez seja o único registro
        # daquele cliente.
        registro = {}
        for i, valor in enumerate(bruta):
            chave = colunas[i] if i < len(colunas) else f"coluna_{i + 1}"
            registro[chave] = valor.strip()
        linhas.append(registro)
    return tabela, linhas


def _arquivos_do_zip(conteudo: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        return [
            (info.filename, pacote.read(info))
            for info in pacote.infolist()
            if not info.is_dir() and info.filename.lower().endswith((".csv", ".sql"))
        ]


async def importar(
    sessao: AsyncSession,
    arquivos: list[tuple[str, bytes]],
    *,
    descricao: str,
    origem: str | None = None,
) -> Resultado:
    """Guarda os CSVs como um lote. ZIP é aberto e os CSVs de dentro entram."""
    lote = LoteAntigo(descricao=descricao, origem=origem)
    sessao.add(lote)
    await sessao.flush()

    resultado = Resultado(lote_id=str(lote.id))

    # Expande os ZIPs primeiro.
    planos: list[tuple[str, bytes]] = []
    for nome, conteudo in arquivos:
        if nome.lower().endswith(".zip"):
            try:
                planos.extend(_arquivos_do_zip(conteudo))
            except zipfile.BadZipFile:
                resultado.ignorados.append(f"{nome}: não é um zip válido")
        elif nome.lower().endswith((".csv", ".sql")):
            planos.append((nome, conteudo))
        else:
            resultado.ignorados.append(f"{nome}: só aceito .csv, .sql e .zip")

    for nome, conteudo in planos:
        try:
            # Um `.sql` traz muitas tabelas de uma vez; um `.csv` traz uma.
            if nome.lower().endswith(".sql"):
                por_tabela = dump_mysql.ler(_texto(conteudo))
            else:
                tabela, linhas = ler_csv(nome, conteudo)
                por_tabela = {tabela: linhas} if linhas else {}
        except Exception as erro:
            # Um arquivo ruim não derruba a importação dos outros.
            log.warning("não deu pra ler %s: %s", nome, erro)
            resultado.ignorados.append(f"{nome}: {erro}")
            continue

        for tabela, linhas in por_tabela.items():
            if not linhas:
                continue
            if len(linhas) > _MAX_LINHAS_POR_TABELA:
                log.warning("%s: %d linhas, guardando as primeiras %d",
                            tabela, len(linhas), _MAX_LINHAS_POR_TABELA)
                linhas = linhas[:_MAX_LINHAS_POR_TABELA]
            sessao.add_all([
                LinhaAntiga(lote_id=lote.id, tabela=tabela, numero_linha=i + 1, dados=linha)
                for i, linha in enumerate(linhas)
            ])
            resultado.tabelas[tabela] = resultado.tabelas.get(tabela, 0) + len(linhas)

    await sessao.flush()
    return resultado
