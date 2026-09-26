"""Busca dentro de uma tabela do sistema antigo.

Existe porque procurar texto cru não acha o que o dono digita. Dois casos que
aconteceram com os dados da Monte São Motos:

- **CPF e CNPJ vêm formatados** no arquivo (`000.000.000-00` em 1.634 dos 1.782
  cadastros, e sem pontuação em 31). Quem digita só os números não achava nada,
  e quem digita com ponto não achava os 31 sem ponto.
- **Data vem em ISO** (`2026-09-26`), e ninguém no balcão digita data assim.
  Quem procura uma venda digita `26/09/2026`, ou `09/2026` pro mês inteiro.

Então o termo digitado é traduzido nas formas que o arquivo pode ter, e a
comparação é feita contra o texto **e** contra só os dígitos do valor.
"""

import re
from dataclasses import dataclass

_SEPARADOR_DE_DATA = re.compile(r"[/.\-]")


def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


@dataclass(frozen=True)
class Busca:
    """O que procurar, já traduzido pras formas que o arquivo usa."""

    # Casam contra o texto do valor, em minúscula. Qualquer um serve.
    textos: tuple[str, ...]
    # Casa contra só os dígitos do valor. É o que faz CPF achar com ou sem
    # ponto. `None` quando o termo não tem dígitos suficientes pra valer.
    digitos: str | None

    def __bool__(self) -> bool:
        return bool(self.textos or self.digitos)


def _datas_possiveis(termo: str) -> list[str]:
    """`26/09/2026` -> `2026-09-26`. `09/2026` -> `2026-09-`. `26/09` -> `-09-26`.

    O pedaço parcial é de propósito: quem digita só mês e ano quer o mês
    inteiro, e quem digita dia e mês quer aquele dia em qualquer ano.
    """
    partes = [p for p in _SEPARADOR_DE_DATA.split(termo) if p]
    if not 2 <= len(partes) <= 3 or not all(p.isdigit() and len(p) <= 4 for p in partes):
        return []

    def ano(p: str) -> str:
        # `26` como ano viraria 2026; mas dia 26 também é "26". Só trato como
        # ano o que tem 4 dígitos — adivinhar século aqui erraria silenciosamente.
        return p if len(p) == 4 else ""

    if len(partes) == 3:
        dia, mes, a = partes
        if ano(a):
            return [f"{a}-{mes.zfill(2)}-{dia.zfill(2)}"]
        # `2026-09-26` digitado direto já vem nesta ordem.
        if ano(dia):
            return [f"{dia}-{mes.zfill(2)}-{a.zfill(2)}"]
        return []

    a, b = partes
    if ano(b):                      # 09/2026 -> o mês inteiro
        return [f"{b}-{a.zfill(2)}-"]
    if ano(a):                      # 2026-09 -> o mês inteiro
        return [f"{a}-{b.zfill(2)}-"]
    return [f"-{b.zfill(2)}-{a.zfill(2)}"]   # 26/09 -> aquele dia, qualquer ano


def preparar(termo: str | None) -> Busca | None:
    """Traduz o que o dono digitou. `None` quando não há o que procurar."""
    limpo = (termo or "").strip()
    if not limpo:
        return None

    textos = [limpo.lower()]
    textos.extend(_datas_possiveis(limpo))

    # 3 dígitos é o mínimo pra busca por número não devolver metade do arquivo.
    digitos = _so_digitos(limpo)
    return Busca(
        textos=tuple(dict.fromkeys(textos)),
        digitos=digitos if len(digitos) >= 3 else None,
    )


def combina(dados: dict, busca: Busca) -> bool:
    """Se alguma coluna desta linha atende à busca."""
    for valor in dados.values():
        if valor is None:
            continue
        texto = str(valor)
        baixo = texto.lower()
        if any(t in baixo for t in busca.textos):
            return True
        if busca.digitos and busca.digitos in _so_digitos(texto):
            return True
    return False
