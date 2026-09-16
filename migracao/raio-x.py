"""Raio-x do espelho: o que foi que chegou do sistema antigo.

O passo 1 copia sem interpretar. Antes de converter qualquer coisa, alguém
precisa olhar o que veio — e olhar 40 colunas de 1.240 linhas à mão não é
olhar, é chutar.

Este programa lê o espelho e conta, coluna por coluna: quantas linhas têm
valor, quantos valores diferentes existem, três exemplos, um palpite do que a
coluna é (CPF, telefone, data, dinheiro, placa, e-mail) e — o que mais
importa — **o que vai dar problema na conversão**: CPF que não fecha, data que
não existe no calendário, valor com letra no meio.

    MIGRACAO_DESTINO="postgresql://..." python raio-x.py
    MIGRACAO_DESTINO="postgresql://..." python raio-x.py --lote 4 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg

SCHEMA = "migracao"
AMOSTRA = 500          # linhas lidas por tabela: o bastante pra reconhecer um padrão
CONTROLE = ("_lote_id", "_linha", "_origem")


# ----------------------------------------------------------- reconhecimento

def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def _cpf_fecha(valor: str) -> bool:
    """A conta dos dois dígitos do fim. É ela que separa um CPF de um número
    de 11 casas digitado errado."""
    numeros = _digitos(valor)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (11 - soma % 11) % 11
        if digito >= 10:
            digito = 0
        if digito != int(numeros[tamanho]):
            return False
    return True


def _cnpj_fecha(valor: str) -> bool:
    numeros = _digitos(valor)
    if len(numeros) != 14 or numeros == numeros[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(numeros[i]) * pesos[i] for i in range(tamanho))
        digito = (11 - soma % 11) % 11
        if digito >= 10:
            digito = 0
        if digito != int(numeros[tamanho]):
            return False
    return True


def _data_existe(valor: str) -> bool | None:
    """True se é data válida, False se PARECE data mas não existe no
    calendário (31/02, mês 13), None se não parece data."""
    texto = valor.strip()
    formatos = (
        (r"^(\d{2})/(\d{2})/(\d{4})", (2, 1, 0)),   # 15/03/2011
        (r"^(\d{4})-(\d{2})-(\d{2})", (0, 1, 2)),   # 2011-03-15
        (r"^(\d{2})-(\d{2})-(\d{4})", (2, 1, 0)),
    )
    for padrao, ordem in formatos:
        achado = re.match(padrao, texto)
        if not achado:
            continue
        partes = achado.groups()
        try:
            date(int(partes[ordem[0]]), int(partes[ordem[1]]), int(partes[ordem[2]]))
            return True
        except ValueError:
            return False
    return None


_PLACA = re.compile(r"^[A-Z]{3}-?\d{4}$|^[A-Z]{3}\d[A-Z]\d{2}$", re.I)
_DINHEIRO = re.compile(r"^R?\$?\s*-?[\d.]+,\d{2}$|^-?\d+\.\d{2}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _palpite(valores: list[str]) -> tuple[str, list[str]]:
    """O que esta coluna parece ser, e o que vai dar problema."""
    if not valores:
        return "sempre vazia", []

    quantos = len(valores)
    def fracao(condicao) -> float:
        return sum(1 for v in valores if condicao(v)) / quantos

    avisos: list[str] = []

    onze = fracao(lambda v: len(_digitos(v)) == 11)
    quatorze = fracao(lambda v: len(_digitos(v)) == 14)

    # Uma coluna só pra pessoa e empresa é o mais comum em sistema antigo: 11
    # dígitos numas linhas, 14 noutras. Tratar como "texto" esconderia que ali
    # tem documento pra validar.
    if onze > 0 and quatorze > 0 and onze + quatorze > 0.8:
        ruins = [v for v in valores if not (_cpf_fecha(v) or _cnpj_fecha(v))]
        if ruins:
            avisos.append(f"{len(ruins)} de {quantos} não fecham a conta (ex: {ruins[0]!r})")
        return "CPF/CNPJ (misturados)", avisos

    if onze > 0.8:
        ruins = [v for v in valores if not _cpf_fecha(v)]
        if len(ruins) / quantos < 0.5:
            if ruins:
                avisos.append(f"{len(ruins)} de {quantos} não fecham a conta do CPF (ex: {ruins[0]!r})")
            return "CPF", avisos

    if quatorze > 0.8:
        ruins = [v for v in valores if not _cnpj_fecha(v)]
        if ruins:
            avisos.append(f"{len(ruins)} de {quantos} não fecham a conta do CNPJ")
        return "CNPJ", avisos

    datas = [(_data_existe(v)) for v in valores]
    if sum(1 for d in datas if d is not None) / quantos > 0.8:
        impossiveis = [v for v, d in zip(valores, datas) if d is False]
        if impossiveis:
            avisos.append(f"{len(impossiveis)} data(s) que não existem no calendário (ex: {impossiveis[0]!r})")
        return "data", avisos

    if fracao(lambda v: bool(_DINHEIRO.match(v.strip()))) > 0.7:
        estranhos = [v for v in valores if not _DINHEIRO.match(v.strip())]
        if estranhos:
            avisos.append(f"{len(estranhos)} valor(es) que não são número (ex: {estranhos[0]!r})")
        return "dinheiro", avisos

    if fracao(lambda v: bool(_PLACA.match(v.strip()))) > 0.7:
        return "placa", avisos
    if fracao(lambda v: bool(_EMAIL.match(v.strip()))) > 0.7:
        return "e-mail", avisos
    if fracao(lambda v: 10 <= len(_digitos(v)) <= 11 and _digitos(v)[:2].isdigit()) > 0.8:
        return "telefone", avisos
    if fracao(lambda v: v.strip().lstrip("-").isdigit()) > 0.9:
        return "número inteiro", avisos
    if fracao(lambda v: v.startswith("base64:")) > 0.5:
        return "arquivo/foto", avisos

    if fracao(lambda v: v != v.strip()) > 0.3:
        avisos.append("espaço sobrando no começo ou no fim")
    return "texto", avisos


# ------------------------------------------------------------------- leitura

def _dsn(url: str) -> str:
    partes = urlsplit(url.strip())
    consulta = [("sslmode" if k == "ssl" else k, v) for k, v in parse_qsl(partes.query)]
    return urlunsplit(partes._replace(scheme="postgresql", query=urlencode(consulta)))


async def radiografar(destino: str, lote_id: int | None) -> dict:
    conexao = await asyncpg.connect(_dsn(destino))
    try:
        if lote_id is None:
            lote_id = await conexao.fetchval(
                f"SELECT id FROM {SCHEMA}.lotes WHERE situacao IN ('CONCLUIDO','COM_ERROS') "
                "ORDER BY id DESC LIMIT 1"
            )
        if lote_id is None:
            raise SystemExit("Nenhum lote concluído no espelho. Rode o passo 1 primeiro.")

        lote = await conexao.fetchrow(f"SELECT id, origem, tabelas FROM {SCHEMA}.lotes WHERE id = $1", lote_id)
        if lote is None:
            raise SystemExit(f"Lote {lote_id} não existe.")

        tabelas_do_lote = json.loads(lote["tabelas"])
        relatorio = {"lote": lote_id, "origem": lote["origem"], "tabelas": {}}

        for nome, info in sorted(tabelas_do_lote.items()):
            total = await conexao.fetchval(
                f'SELECT count(*) FROM {SCHEMA}."{nome}" WHERE _lote_id = $1', lote_id
            )
            linhas = await conexao.fetch(
                f'SELECT * FROM {SCHEMA}."{nome}" WHERE _lote_id = $1 LIMIT {AMOSTRA}', lote_id
            )
            colunas = {}
            for coluna in (c for c in (linhas[0].keys() if linhas else []) if c not in CONTROLE):
                valores = [str(l[coluna]) for l in linhas if l[coluna] is not None and str(l[coluna]) != ""]
                tipo, avisos = _palpite(valores)
                colunas[coluna] = {
                    "veio_de": (info.get("colunas") or {}).get(coluna, coluna),
                    "parece": tipo,
                    "preenchidas": len(valores),
                    "vazias": len(linhas) - len(valores),
                    "diferentes": len(Counter(valores)),
                    "exemplos": [v[:40] for v, _ in Counter(valores).most_common(3)],
                    "avisos": avisos,
                }
            relatorio["tabelas"][nome] = {
                "veio_de": info.get("origem"), "linhas": total, "colunas": colunas,
            }
        return relatorio
    finally:
        await conexao.close()


def _imprimir(relatorio: dict) -> None:
    print(f"\nLote {relatorio['lote']} — {relatorio['origem']}\n")
    for nome, tabela in relatorio["tabelas"].items():
        quantas = f"{tabela['linhas']:,}".replace(",", ".")
        print(f"{'=' * 78}\n{nome}   ({quantas} linhas, de {tabela['veio_de']})")
        print(f"{'-' * 78}")
        if not tabela["colunas"]:
            print("  (sem colunas — tabela vazia no sistema antigo)")
            continue
        vazias = [c for c, d in tabela["colunas"].items() if d["preenchidas"] == 0]
        for coluna, dados in tabela["colunas"].items():
            if dados["preenchidas"] == 0:
                continue
            print(f"  {coluna:<24} {dados['parece']:<15} "
                  f"{dados['preenchidas']:>4} com valor, {dados['vazias']:>4} vazias, "
                  f"{dados['diferentes']:>4} diferentes")
            print(f"  {'':<24} veio de {dados['veio_de']!r}; ex: " +
                  ", ".join(repr(e) for e in dados["exemplos"]))
            for aviso in dados["avisos"]:
                print(f"  {'':<24} ⚠ {aviso}")
        if vazias:
            print(f"  ({len(vazias)} coluna(s) sem nada neste lote — normalmente vieram de outra "
                  f"cópia: {', '.join(vazias)})")
        print()


def _principal() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--lote", type=int, default=None, help="qual lote olhar (padrão: o último concluído)")
    argumentos.add_argument("--json", action="store_true", help="devolve o relatório em JSON, pra alimentar o passo 2")
    argumentos.add_argument("--destino", default=os.environ.get("MIGRACAO_DESTINO"))
    opcoes = argumentos.parse_args()
    if not opcoes.destino:
        argumentos.error("informe a URL do banco em MIGRACAO_DESTINO")

    relatorio = asyncio.run(radiografar(opcoes.destino, opcoes.lote))
    if opcoes.json:
        json.dump(relatorio, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        _imprimir(relatorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(_principal())
