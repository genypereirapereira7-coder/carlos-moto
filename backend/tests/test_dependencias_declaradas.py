"""Toda biblioteca que o código importa tem que estar no `requirements.txt`.

Este teste existe por causa de um apagão: o `nota_fiscal.py` passou a importar
`defusedxml`, que estava instalado na máquina de quem escreveu e **não** estava
declarado. Em produção o import falhou antes de o servidor carregar o app — e
não foi só a nota fiscal que parou, foi o site inteiro, com 502 até na tela de
entrar. O dono não conseguia nem abrir o sistema.

`requirements.txt` é o que a hospedagem lê pra montar o contêiner, então é
contra ele que a conferência tem que ser feita — não contra o `pyproject.toml`,
que é só o limite de versão, nem contra o que está instalado aqui.
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
RAIZ = BACKEND.parent

# O nome que se importa não é sempre o nome do pacote.
NOME_DO_IMPORT = {
    "pyjwt": "jwt",
    "python_multipart": "multipart",
    "sqlalchemy": "sqlalchemy",
}

# Nossos próprios módulos: não são pacote de fora.
NOSSOS = {"app", "migracoes", "producao", "dev", "tests", "conftest"}


def _declaradas() -> set[str]:
    texto = (RAIZ / "requirements.txt").read_text()
    nomes: set[str] = set()
    for linha in texto.splitlines():
        limpo = linha.split("#")[0].strip()
        if not limpo:
            continue
        pacote = re.split(r"[\[=<>!;]", limpo)[0].strip().replace("-", "_").lower()
        nomes.add(pacote)
        if pacote in NOME_DO_IMPORT:
            nomes.add(NOME_DO_IMPORT[pacote])
    return nomes


def _importadas() -> dict[str, set[str]]:
    """Cada biblioteca de fora e os arquivos que a importam.

    Só o código que roda em produção: o `tests/` pode usar o que quiser (o
    `aiosqlite` e o `httpx` são de desenvolvimento e não vão pro contêiner).
    """
    encontradas: dict[str, set[str]] = {}
    arquivos = [a for a in BACKEND.rglob("*.py")
                if ".venv" not in a.parts and "tests" not in a.parts]
    for arquivo in arquivos:
        arvore = ast.parse(arquivo.read_text())
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes = [a.name.split(".")[0] for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                nomes = [no.module.split(".")[0]]
            else:
                continue
            for nome in nomes:
                if nome in sys.stdlib_module_names or nome in NOSSOS:
                    continue
                encontradas.setdefault(nome, set()).add(
                    str(arquivo.relative_to(RAIZ))
                )
    return encontradas


def test_toda_biblioteca_importada_esta_no_requirements():
    declaradas = _declaradas()
    faltando = {
        nome: sorted(arquivos)
        for nome, arquivos in _importadas().items()
        if nome.replace("-", "_").lower() not in declaradas
    }
    assert not faltando, (
        "Estas bibliotecas são importadas e não estão no requirements.txt. "
        "Em produção o servidor não sobe e o site todo dá 502:\n"
        + "\n".join(f"  {n}  (em {', '.join(a)})" for n, a in faltando.items())
    )


def test_o_arquivo_que_a_hospedagem_le_existe_e_tem_o_servidor():
    """Se este arquivo mudar de nome ou de lugar, o teste de cima passa a
    conferir contra o vazio e não protege mais nada."""
    requirements = RAIZ / "requirements.txt"
    assert requirements.is_file(), "requirements.txt saiu da raiz do repositório"
    declaradas = _declaradas()
    for essencial in ("fastapi", "uvicorn", "sqlalchemy", "asyncpg"):
        assert essencial in declaradas, f"{essencial} não está no requirements.txt"
