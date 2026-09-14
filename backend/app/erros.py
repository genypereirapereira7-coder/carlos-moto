"""Tradução das mensagens de validação que o Pydantic devolve em inglês.

O sistema inteiro fala português: as mensagens que a própria API escreve
(`HTTPException(..., "Placa já usada por outra moto")`) e as que a tela
escreve (`frontend/dono/validacao.js`). Só as do Pydantic vinham em inglês
— "Field required", "Input should be greater than 0" — e são justamente
elas que aparecem embaixo do campo quando o servidor recusa algo que a tela
deixou passar. Traduzir aqui, na saída, conserta pra toda tela de uma vez
(a de vendas inclusive) em vez de cada uma manter seu próprio dicionário.

O formato da resposta continua o do Pydantic (`detail` como lista de
`{loc, msg, type}`): é o `loc` que a tela usa pra saber qual campo pintar de
vermelho. `ctx` fica de fora de propósito — ele às vezes carrega o próprio
objeto da exceção, que não vira JSON.
"""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Prefixos que o Pydantic gruda na frente das mensagens levantadas pelos
# nossos próprios validadores (`schemas/validadores.py`) — que já estão em
# português e não precisam de tradução, só de limpeza.
_PREFIXOS_NOSSOS = ("Value error, ", "Assertion failed, ")

_POR_TIPO = {
    "missing": "Campo obrigatório",
    "string_type": "Precisa ser texto",
    "int_type": "Precisa ser um número inteiro",
    "int_parsing": "Precisa ser um número inteiro",
    "float_type": "Precisa ser um número",
    "float_parsing": "Precisa ser um número",
    "decimal_parsing": "Precisa ser um número",
    "bool_type": "Precisa ser sim ou não",
    "bool_parsing": "Precisa ser sim ou não",
    "date_type": "Data inválida",
    "date_parsing": "Data inválida",
    "date_from_datetime_parsing": "Data inválida",
    "datetime_type": "Data e hora inválidas",
    "datetime_parsing": "Data e hora inválidas",
    "uuid_type": "Identificador inválido",
    "uuid_parsing": "Identificador inválido",
    "enum": "Opção inválida",
    "literal_error": "Opção inválida",
    "json_invalid": "Dados enviados em formato inválido",
    "model_type": "Dados enviados em formato inválido",
    "model_attributes_type": "Dados enviados em formato inválido",
    "extra_forbidden": "Campo não existe",
}


def _contar(quantidade, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def traduzir(erro: dict) -> str:
    """Uma mensagem de erro do Pydantic, em português."""
    tipo = erro.get("type", "")
    contexto = erro.get("ctx") or {}
    mensagem = str(erro.get("msg", ""))

    for prefixo in _PREFIXOS_NOSSOS:
        if mensagem.startswith(prefixo):
            return mensagem.removeprefix(prefixo) or "Valor inválido"

    if tipo in _POR_TIPO:
        return _POR_TIPO[tipo]

    if tipo == "string_too_short":
        return f"Precisa ter pelo menos {_contar(contexto.get('min_length'), 'caractere', 'caracteres')}"
    if tipo == "string_too_long":
        return f"Precisa ter no máximo {_contar(contexto.get('max_length'), 'caractere', 'caracteres')}"
    if tipo == "greater_than":
        return f"Precisa ser maior que {contexto.get('gt')}"
    if tipo == "greater_than_equal":
        return f"Precisa ser {contexto.get('ge')} ou mais"
    if tipo == "less_than":
        return f"Precisa ser menor que {contexto.get('lt')}"
    if tipo == "less_than_equal":
        return f"Precisa ser {contexto.get('le')} ou menos"

    return "Valor inválido"


async def tratar_erro_de_validacao(_: Request, excecao: Exception) -> JSONResponse:
    erros = excecao.errors() if isinstance(excecao, RequestValidationError) else []
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": [
                {
                    "loc": list(erro.get("loc", [])),
                    "msg": traduzir(erro),
                    "type": erro.get("type", ""),
                }
                for erro in erros
            ]
        },
    )
