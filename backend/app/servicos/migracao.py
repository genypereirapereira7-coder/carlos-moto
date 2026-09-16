"""PASSO 1 da migração: copiar o sistema antigo inteiro pro espelho na nuvem.

Lê cada tabela do sistema antigo do jeito que ela está e grava uma cópia no
PostgreSQL da nuvem, no schema `migracao`: uma tabela `temp_<nome>` por tabela
antiga, com todas as colunas TEXT aceitando NULL.

Nada é interpretado aqui — nem CPF, nem data, nem valor. Um "31/02/2019" ou um
"R$ 1.500,OO" com letra O entra do jeito que veio. Interpretar é o passo 2, com
os dados já a salvo na nuvem: se o computador do cliente desligar no meio da
conversão, a cópia bruta não se perde.

Roda no computador onde o sistema antigo está, de dois jeitos:

    pelo botão do painel (rota POST /migracao/passo-1), ou direto:
    MIGRACAO_DESTINO="postgresql://..." python migracao.py --origem "C:\\Sistema\\dados.mdb"

Origens que ele sabe abrir:

    .db .sqlite .sqlite3       SQLite
    .mdb .accdb                Access                 (pip install pyodbc)
    .fdb .gdb                  Firebird               (pip install firebird-driver)
    .dbf, ou pasta de .dbf     dBase, Clipper, FoxPro (pip install dbfread)
    .csv .txt, ou pasta        planilha exportada
    .zip                       a pasta inteira do sistema antigo, compactada
    odbc:<string de conexão>   MySQL, SQL Server, qualquer banco com driver ODBC

Não importa nada do app, de propósito: é um arquivo que dá pra copiar sozinho
pra outro computador e rodar lá.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import datetime as dt
import io
import itertools
import json
import os
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

SCHEMA = "migracao"
LINHAS_POR_ENVIO = 2_000

# O nome que o passo 2 vai procurar, pras tabelas conhecidas. A chave é o nome
# no sistema antigo, sem diferenciar maiúscula. Tabela que não estiver aqui vira
# `temp_<nome_dela>` do mesmo jeito: nada fica pra trás por não ter sido previsto.
NOMES_CONHECIDOS = {
    "clientes": "temp_clientes_antigos",
    "cliente": "temp_clientes_antigos",
    "contratos": "temp_contratos_antigos",
    "contrato": "temp_contratos_antigos",
    "tickets": "temp_tickets_antigos",
    "chamados": "temp_tickets_antigos",
    "empresa": "temp_empresa_antiga",
    "empresas": "temp_empresa_antiga",
    "log": "temp_logs_sistema",
    "logs": "temp_logs_sistema",
}

# O mesmo que está em `migracao_passo1.sql`. Repetido aqui pra o botão funcionar
# num banco onde ninguém rodou o SQL à mão.
DDL_BASE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE IF NOT EXISTS {SCHEMA}.lotes (
    id            BIGSERIAL   PRIMARY KEY,
    origem        TEXT        NOT NULL,
    tipo_origem   TEXT        NULL,
    situacao      TEXT        NOT NULL DEFAULT 'RODANDO',
    iniciado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminado_em  TIMESTAMPTZ NULL,
    tabelas       JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
    erros         JSONB       NOT NULL DEFAULT '[]'::jsonb
);
"""


@dataclass
class TabelaAntiga:
    nome: str               # como está no sistema antigo
    colunas: list[str]
    linhas: Iterator        # uma sequência de valores por registro, na ordem de `colunas`


# ------------------------------------------------------------ o sistema antigo


def abrir_sistema_antigo(origem: str) -> tuple[str, Iterator[TabelaAntiga]]:
    """Descobre o formato pelo que está no disco. Devolve (tipo, tabelas).

    As tabelas vêm uma de cada vez e são lidas enquanto são copiadas: um log de
    dois milhões de linhas nunca fica inteiro na memória.
    """
    if origem.lower().startswith("odbc:"):
        return "odbc", _ler_odbc(origem[len("odbc:"):])

    caminho = Path(origem)
    if not caminho.exists():
        raise FileNotFoundError(f"Não achei o sistema antigo em {caminho}")
    if caminho.is_dir():
        return "pasta", _ler_pasta(caminho)

    sufixo = caminho.suffix.lower()
    if sufixo in {".db", ".sqlite", ".sqlite3"}:
        return "sqlite", _ler_sqlite(caminho)
    if sufixo in {".mdb", ".accdb"}:
        return "access", _ler_odbc(
            f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={caminho};ReadOnly=1;"
        )
    if sufixo in {".fdb", ".gdb"}:
        return "firebird", _ler_firebird(caminho)
    if sufixo == ".dbf":
        return "dbf", iter([_ler_dbf(caminho)])
    if sufixo in {".csv", ".txt"}:
        return "csv", iter([_ler_csv(caminho)])
    if sufixo == ".zip":
        return "zip", _ler_zip(caminho)
    raise ValueError(f"Não sei abrir este formato de sistema antigo: {caminho.name}")


def _decodificar(bruto: bytes) -> str:
    """UTF-8 quando for; senão Windows-1252, que é o de quase todo sistema
    brasileiro antigo. Nunca falha: um caractere que não existe vira '�', em vez
    de a tabela inteira ficar de fora por causa dele."""
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("cp1252", errors="replace")


def _ler_sqlite(arquivo: Path) -> Iterator[TabelaAntiga]:
    # Só leitura, pela URI: o sistema antigo pode estar aberto, e a migração não
    # pode nem arriscar escrever no banco dele. `check_same_thread=False` porque
    # a leitura anda em threads diferentes (uma por lote de linhas), sempre uma
    # de cada vez.
    conexao = sqlite3.connect(f"{arquivo.resolve().as_uri()}?mode=ro", uri=True,
                              check_same_thread=False)
    conexao.text_factory = _decodificar
    try:
        nomes = [n for (n,) in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        for nome in nomes:
            cursor = conexao.execute(f'SELECT * FROM "{nome.replace(chr(34), chr(34) * 2)}"')
            yield TabelaAntiga(nome, [d[0] for d in cursor.description], iter(cursor))
    finally:
        conexao.close()


def _ler_odbc(texto_conexao: str) -> Iterator[TabelaAntiga]:
    # No Windows o driver do Access já vem com o Office. `readonly` pelo mesmo
    # motivo do SQLite.
    import pyodbc

    conexao = pyodbc.connect(texto_conexao, autocommit=True, readonly=True)
    try:
        aspas = (conexao.getinfo(pyodbc.SQL_IDENTIFIER_QUOTE_CHAR) or '"').strip() or '"'
        abre, fecha = ("[", "]") if aspas == "[" else (aspas, aspas)

        def citar(nome: str) -> str:
            return f"{abre}{nome.replace(fecha, fecha * 2)}{fecha}"

        tabelas = [(t.table_schem, t.table_name) for t in conexao.cursor().tables(tableType="TABLE")]
        for esquema, nome in tabelas:
            alvo = f"{citar(esquema)}.{citar(nome)}" if esquema else citar(nome)
            cursor = conexao.cursor()
            cursor.execute(f"SELECT * FROM {alvo}")
            yield TabelaAntiga(nome, [d[0] for d in cursor.description], iter(cursor))
    finally:
        conexao.close()


def _ler_firebird(arquivo: Path) -> Iterator[TabelaAntiga]:
    from firebird.driver import connect

    conexao = connect(
        str(arquivo),
        user=os.environ.get("MIGRACAO_FIREBIRD_USUARIO", "SYSDBA"),
        # "masterkey" é a senha que o Firebird instala por padrão — a do sistema
        # antigo do cliente, não uma nossa.
        password=os.environ.get("MIGRACAO_FIREBIRD_SENHA", "masterkey"),
        charset=os.environ.get("MIGRACAO_FIREBIRD_CHARSET", "WIN1252"),
    )
    try:
        cursor = conexao.cursor()
        cursor.execute(
            "SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS "
            "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$VIEW_BLR IS NULL ORDER BY 1"
        )
        for (nome,) in cursor.fetchall():
            leitura = conexao.cursor()
            leitura.execute(f'SELECT * FROM "{nome}"')
            yield TabelaAntiga(nome, [d[0] for d in leitura.description], iter(leitura))
    finally:
        conexao.close()


def _ler_dbf(arquivo: Path) -> TabelaAntiga:
    from dbfread import DBF

    tabela = DBF(
        str(arquivo),
        # cp850 é o padrão dos sistemas de DOS. Acento saiu torto? É cp1252.
        encoding=os.environ.get("MIGRACAO_DBF_CODIFICACAO", "cp850"),
        char_decode_errors="replace",
        ignore_missing_memofile=True,
    )
    # dBase não apaga de verdade: marca o registro e esconde. Ele vem junto, com
    # a marca — "ler tudo" inclui o que o sistema antigo escondia, e decidir se
    # volta é o passo 2.
    vivos = (tuple(r.values()) + ("nao",) for r in tabela)
    apagados = (tuple(r.values()) + ("sim",) for r in tabela.deleted)
    return TabelaAntiga(arquivo.stem, [*tabela.field_names, "apagado_no_sistema_antigo"],
                        itertools.chain(vivos, apagados))


def _ler_csv(arquivo: Path) -> TabelaAntiga:
    texto = _decodificar(arquivo.read_bytes()).lstrip("\ufeff")
    try:
        # Planilha brasileira sai com ";" (a vírgula é o decimal).
        dialeto = csv.Sniffer().sniff(texto[:50_000], delimiters=";,\t|")
        linhas = list(csv.reader(io.StringIO(texto), dialeto))
    except csv.Error:
        linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))

    cabecalho, corpo = (linhas[0], linhas[1:]) if linhas else ([], [])
    largura = max([len(cabecalho), *map(len, corpo)], default=0)
    # Linha com mais campos que o cabeçalho — um ";" a mais no meio de um
    # endereço — ganha coluna extra, em vez de perder o que sobrou.
    extras = [f"coluna_extra_{i}" for i in range(len(cabecalho) + 1, largura + 1)]
    return TabelaAntiga(arquivo.stem, [*cabecalho, *extras], iter(corpo))


def _ler_zip(arquivo: Path) -> Iterator[TabelaAntiga]:
    """A pasta do sistema antigo, compactada — é assim que ela chega pela
    internet quando o cliente manda pelo navegador.

    Descompacta num lugar temporário e lê de lá; no fim apaga. O conteúdo é o
    banco do cliente: não pode ficar sobrando no disco do servidor.
    """
    import shutil
    import tempfile
    import zipfile

    temporaria = Path(tempfile.mkdtemp(prefix="migracao-zip-"))
    try:
        with zipfile.ZipFile(arquivo) as zip_:
            for membro in zip_.infolist():
                if membro.is_dir():
                    continue
                # Um .zip pode trazer nomes como "../../etc/senha" e escrever
                # fora da pasta. Só o nome do arquivo entra, sem caminho.
                nome = Path(membro.filename).name
                if not nome or nome.startswith("."):
                    continue
                with zip_.open(membro) as origem, open(temporaria / nome, "wb") as destino:
                    shutil.copyfileobj(origem, destino)

        # De dentro do zip pode vir um banco só (um .mdb, um .db) ou a pasta
        # inteira de .dbf — os dois casos caem no leitor de pasta.
        arquivos = sorted(p for p in temporaria.iterdir() if p.is_file())
        unico = [p for p in arquivos if p.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".fdb", ".gdb"}]
        if len(unico) == 1 and len(arquivos) == 1:
            _, tabelas = abrir_sistema_antigo(str(unico[0]))
            yield from tabelas
        else:
            yield from _ler_pasta(temporaria)
    finally:
        shutil.rmtree(temporaria, ignore_errors=True)


def _ler_pasta(pasta: Path) -> Iterator[TabelaAntiga]:
    # Sistema de dBase/Clipper guarda uma tabela por arquivo, tudo numa pasta;
    # exportação de planilha costuma vir do mesmo jeito.
    for arquivo in sorted(pasta.iterdir()):
        sufixo = arquivo.suffix.lower()
        if sufixo == ".dbf":
            yield _ler_dbf(arquivo)
        elif sufixo in {".csv", ".txt"}:
            yield _ler_csv(arquivo)


# ------------------------------------------------------------ valores e nomes


def _como_texto(valor) -> str | None:
    """Qualquer valor do sistema antigo, como texto. `None` continua NULL."""
    if valor is None:
        return None
    if hasattr(valor, "read"):          # BLOB grande do Firebird chega como leitor
        valor = valor.read()
    if isinstance(valor, memoryview):
        valor = valor.tobytes()
    if isinstance(valor, (bytes, bytearray)):
        # Foto, anexo, campo binário: vai inteiro, em base64, marcado pra não
        # ser confundido com texto de verdade.
        return "base64:" + base64.b64encode(valor).decode("ascii")
    if isinstance(valor, (dt.datetime, dt.date, dt.time)):
        return valor.isoformat()
    # O Postgres recusa o caractere nulo dentro de TEXT, e banco antigo de campo
    # de tamanho fixo vem cheio dele no fim dos campos. É o único caractere que
    # sai: espaço sobrando, zero à esquerda e erro de digitação ficam.
    return str(valor).replace("\x00", "")


def _nome_seguro(bruto: str, usados: set[str], prefixo: str = "") -> str:
    """Nome que o Postgres aceita sem aspas nem susto: minúsculo, sem acento nem
    espaço, até 63 bytes e sem repetir. `Data Nasc.` vira `data_nasc`, e duas
    colunas `NOME` e `nome` viram `nome` e `nome_2`."""
    ascii_ = unicodedata.normalize("NFKD", str(bruto)).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_") or "coluna"
    if base[0].isdigit():
        base = f"c_{base}"
    base = f"{prefixo}{base}"[:55]  # sobra espaço pro "_2" dentro dos 63
    nome, n = base, 2
    while nome in usados:
        nome, n = f"{base}_{n}", n + 1
    usados.add(nome)
    return nome


def _nome_da_tabela(nome_antigo: str, usados: set[str]) -> str:
    conhecido = NOMES_CONHECIDOS.get(str(nome_antigo).strip().lower())
    if conhecido and conhecido not in usados:
        usados.add(conhecido)
        return conhecido
    return _nome_seguro(nome_antigo, usados, prefixo="temp_")


def _dsn(url: str) -> str:
    """A URL como o asyncpg quer. Aceita a do SQLAlchemy (`+asyncpg`, `?ssl=`) e
    a do Railway do jeito que vem."""
    partes = urlsplit(url.strip())
    consulta = [("sslmode" if k == "ssl" else k, v) for k, v in parse_qsl(partes.query)]
    return urlunsplit(partes._replace(scheme="postgresql", query=urlencode(consulta)))


# ----------------------------------------------------------------- a cópia


async def _preparar_schema(conexao: asyncpg.Connection) -> None:
    # Só cria se faltar. O usuário restrito da migração (ver o SQL) não tem
    # permissão de criar schema — e nem precisa, depois da primeira vez.
    if await conexao.fetchval(f"SELECT to_regclass('{SCHEMA}.lotes')") is None:
        await conexao.execute(DDL_BASE)


async def abrir_lote(destino: str, origem: str) -> int:
    """Registra a tentativa e devolve o número do lote, antes de copiar nada —
    quem apertou o botão já tem o que acompanhar."""
    conexao = await asyncpg.connect(_dsn(destino))
    try:
        await _preparar_schema(conexao)
        return await conexao.fetchval(
            f"INSERT INTO {SCHEMA}.lotes (origem) VALUES ($1) RETURNING id", origem
        )
    finally:
        await conexao.close()


def _ddl_espelho(nome: str, colunas: list[str]) -> str:
    # Sem chave estrangeira pra `lotes`, de propósito. Criar uma tabela que
    # aponta pra `lotes` tranca `lotes` até a transação terminar — e o progresso
    # da cópia é gravado justamente em `lotes`, por outra conexão. As duas
    # ficavam esperando uma pela outra pra sempre: o botão nunca terminava, e o
    # Postgres não acusa, porque quem espera é o Python.
    definicoes = [
        "_lote_id BIGINT NOT NULL",
        "_linha BIGINT NOT NULL",
        "_origem TEXT NOT NULL",
        *(f'"{c}" TEXT NULL' for c in colunas),
        "PRIMARY KEY (_lote_id, _linha)",
    ]
    return f'CREATE TABLE IF NOT EXISTS {SCHEMA}."{nome}" (\n    ' + ",\n    ".join(definicoes) + "\n)"


async def _copiar_tabela(dados, gravar_progresso, lote_id: int, tabela: TabelaAntiga,
                         nome: str, resumo: dict) -> None:
    usadas = {"_lote_id", "_linha", "_origem"}
    colunas = [_nome_seguro(c, usadas) for c in tabela.colunas]
    info = {"origem": str(tabela.nome), "linhas": 0,
            "colunas": dict(zip(colunas, map(str, tabela.colunas)))}
    resumo[nome] = info

    # A estrutura primeiro, confirmada na hora. Dentro da transação da cópia, o
    # ALTER TABLE deixaria a tabela espelho trancada — até pra leitura — enquanto
    # a cópia inteira não terminasse.
    await dados.execute(_ddl_espelho(nome, colunas))
    # A tabela já existe de um lote anterior, e o sistema antigo ganhou uma
    # coluna desde então: ela chega aqui.
    for coluna in colunas:
        await dados.execute(f'ALTER TABLE {SCHEMA}."{nome}" ADD COLUMN IF NOT EXISTS "{coluna}" TEXT NULL')

    # Os dados, numa transação por tabela: se a leitura quebra no meio (arquivo
    # corrompido, tabela travada), as linhas daquela tabela voltam inteiras pra
    # trás e as outras seguem. Meia tabela copiada é pior que nenhuma — parece
    # completa.
    async with dados.transaction():
        registros = iter(tabela.linhas)
        numero = 0
        while bloco := await asyncio.to_thread(lambda: list(itertools.islice(registros, LINHAS_POR_ENVIO))):
            envio = []
            for registro in bloco:
                numero += 1
                valores = [_como_texto(v) for v in registro][: len(colunas)]
                valores += [None] * (len(colunas) - len(valores))
                envio.append((lote_id, numero, str(tabela.nome), *valores))
            # COPY, e não INSERT linha a linha: dezenas de vezes mais rápido, e o
            # valor nunca passa por dentro de um texto SQL.
            await dados.copy_records_to_table(
                nome, schema_name=SCHEMA, records=envio,
                columns=["_lote_id", "_linha", "_origem", *colunas],
            )
            info["linhas"] = numero
            await gravar_progresso()


async def executar_passo_1(destino: str, origem: str, lote_id: int,
                           avisar: Callable[[str], None] = lambda _: None) -> dict:
    """Copia tudo. Nunca levanta exceção por causa de uma tabela: o que falhar
    fica anotado no lote, e a cópia segue com as outras."""
    dados = await asyncpg.connect(_dsn(destino))
    # Segunda conexão só pro progresso: o que a de dados grava só aparece pra
    # quem está acompanhando quando a tabela inteira confirma.
    painel = await asyncpg.connect(_dsn(destino))
    resumo: dict = {}
    erros: list[dict] = []
    tabelas: Iterator[TabelaAntiga] | None = None
    situacao = "FALHOU"

    async def gravar_progresso(final: str | None = None) -> None:
        await painel.execute(
            f"UPDATE {SCHEMA}.lotes SET tabelas = $2::jsonb, erros = $3::jsonb, "
            "situacao = COALESCE($4, situacao), "
            "terminado_em = CASE WHEN $4::text IS NULL THEN NULL ELSE now() END WHERE id = $1",
            lote_id, json.dumps(resumo, ensure_ascii=False), json.dumps(erros, ensure_ascii=False), final,
        )

    try:
        # Dois cliques, ou o botão e a linha de comando ao mesmo tempo: a trava
        # do próprio Postgres garante uma cópia por origem, em qualquer processo.
        if not await dados.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", origem):
            raise RuntimeError("Já existe uma migração desta origem rodando")

        tipo, tabelas = await asyncio.to_thread(abrir_sistema_antigo, origem)
        await painel.execute(f"UPDATE {SCHEMA}.lotes SET tipo_origem = $2 WHERE id = $1", lote_id, tipo)

        usados: set[str] = set()
        while True:
            try:
                tabela = await asyncio.to_thread(next, tabelas, None)
            except Exception as erro:  # a origem quebrou entre uma tabela e outra
                erros.append({"tabela": None, "erro": f"{type(erro).__name__}: {erro}"})
                break
            if tabela is None:
                break
            nome = _nome_da_tabela(tabela.nome, usados)
            avisar(f"copiando {tabela.nome} → {SCHEMA}.{nome}")
            try:
                await _copiar_tabela(dados, gravar_progresso, lote_id, tabela, nome, resumo)
            except Exception as erro:
                resumo[nome] = {**resumo.get(nome, {}), "origem": str(tabela.nome), "linhas": 0,
                                "erro": f"{type(erro).__name__}: {erro}"[:500]}
                erros.append({"tabela": str(tabela.nome), "erro": f"{type(erro).__name__}: {erro}"[:500]})
            await gravar_progresso()

        situacao = "COM_ERROS" if erros else "CONCLUIDO"
    except Exception as erro:
        erros.append({"tabela": None, "erro": f"{type(erro).__name__}: {erro}"[:500]})
        situacao = "FALHOU"
    finally:
        if tabelas is not None and hasattr(tabelas, "close"):
            tabelas.close()  # fecha o banco antigo
        await gravar_progresso(situacao)
        await dados.close()  # solta a trava junto
        await painel.close()

    return {"lote_id": lote_id, "situacao": situacao, "tabelas": resumo, "erros": erros}


async def ler_lote(destino: str, lote_id: int) -> dict | None:
    conexao = await asyncpg.connect(_dsn(destino))
    try:
        linha = await conexao.fetchrow(
            f"SELECT id, origem, tipo_origem, situacao, iniciado_em, terminado_em, tabelas, erros "
            f"FROM {SCHEMA}.lotes WHERE id = $1", lote_id,
        )
    finally:
        await conexao.close()
    if linha is None:
        return None
    lote = dict(linha)
    lote["tabelas"] = json.loads(lote["tabelas"])
    lote["erros"] = json.loads(lote["erros"])
    return lote


# ---------------------------------------------------------- linha de comando


def _principal() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--origem", required=True,
                            help="arquivo do banco antigo, pasta de .dbf/.csv, ou odbc:<string de conexão>")
    argumentos.add_argument("--destino", default=os.environ.get("MIGRACAO_DESTINO"),
                            help="URL do PostgreSQL da nuvem. Prefira a variável MIGRACAO_DESTINO: "
                                 "o que vai na linha de comando fica no histórico do terminal")
    opcoes = argumentos.parse_args()
    if not opcoes.destino:
        argumentos.error("informe a URL do banco da nuvem na variável MIGRACAO_DESTINO")

    async def rodar() -> int:
        lote = await abrir_lote(opcoes.destino, opcoes.origem)
        print(f"lote {lote}: lendo {opcoes.origem}", flush=True)
        resultado = await executar_passo_1(opcoes.destino, opcoes.origem, lote,
                                           avisar=lambda m: print(f"  {m}", flush=True))
        print()
        for nome, info in resultado["tabelas"].items():
            print(f"  {SCHEMA}.{nome:<36} {info['linhas']:>9} linhas   (de {info['origem']})")
        for erro in resultado["erros"]:
            print(f"  ERRO em {erro['tabela'] or 'origem'}: {erro['erro']}")
        print(f"\nlote {lote}: {resultado['situacao']}")
        return 0 if resultado["situacao"] == "CONCLUIDO" else 1

    return asyncio.run(rodar())


if __name__ == "__main__":
    raise SystemExit(_principal())
