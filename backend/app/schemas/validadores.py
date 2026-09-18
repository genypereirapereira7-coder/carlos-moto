"""Validadores reaproveitados por vários schemas de entrada.

Regra do sistema: todo campo que o dono digita é validado tanto na tela
quanto aqui — a tela impede o erro óbvio na hora, isto aqui impede que
qualquer caminho (API direta, uma tela nova, um bug na validação da tela)
grave dado errado no banco.
"""

import re
from datetime import UTC, date, datetime, timedelta

from app.models.base import agora, como_utc, hoje

_PLACA_ANTIGA = re.compile(r"^[A-Z]{3}\d{4}$")
_PLACA_MERCOSUL = re.compile(r"^[A-Z]{3}\d[A-Z]\d{2}$")


def validar_placa(valor: str | None) -> str | None:
    """Aceita os dois padrões usados no Brasil: `ABC1234` (antigo) e
    `ABC1D23` (Mercosul). `None`/vazio passa — placa é opcional (moto 0km
    ainda não emplacada)."""
    if valor is None:
        return None
    limpa = valor.strip().upper().replace("-", "")
    if not limpa:
        return None
    if not (_PLACA_ANTIGA.match(limpa) or _PLACA_MERCOSUL.match(limpa)):
        raise ValueError("Placa inválida — use o formato ABC1234 ou ABC1D23")
    return limpa


def validar_placa_obrigatoria(valor: str | None) -> str:
    """Mesma regra de formato de `validar_placa`, mas aqui vazio não passa —
    cadastrar moto sem placa deixou de ser permitido: o dono pediu que não dê
    pra salvar sem ela."""
    resultado = validar_placa(valor)
    if resultado is None:
        raise ValueError("Placa é obrigatória")
    return resultado


def validar_chassi(valor: str | None) -> str | None:
    """Chassi de verdade tem sempre 17 caracteres — um valor mais curto não é
    "incompleto", é digitado errado."""
    if valor is None:
        return None
    limpo = valor.strip().upper()
    if not limpo:
        return None
    if len(limpo) != 17 or not limpo.isalnum():
        raise ValueError("Chassi precisa ter 17 letras/números")
    return limpo


def validar_ano(valor: int | None) -> int | None:
    if valor is None:
        return None
    limite_futuro = hoje().year + 1  # ano que vem já vende 0km do modelo novo
    if not (1980 <= valor <= limite_futuro):
        raise ValueError(f"Ano precisa estar entre 1980 e {limite_futuro}")
    return valor


def validar_nao_no_futuro(valor: date | None) -> date | None:
    if valor is not None and valor > hoje():
        raise ValueError("Data não pode ser no futuro")
    return valor


def validar_datahora_nao_no_futuro(valor: datetime | None) -> datetime | None:
    """Mesma regra da data, pra campo com hora. Uma margem de um minuto
    perdoa o relógio do computador do balcão estar um pouco adiantado — sem
    ela, "vender agora" viraria erro de validação em algumas máquinas."""
    if valor is None:
        return None
    # `.astimezone(UTC)`: o SQLite grava a hora sem o fuso, então um
    # "22:30-03:00" guardado como veio viraria 22:30 UTC — três horas errado.
    momento = como_utc(valor).astimezone(UTC)
    if momento > agora() + timedelta(minutes=1):
        raise ValueError("Data não pode ser no futuro")
    return momento


def validar_cpf(valor: str) -> str:
    """Guarda só os dígitos, conferidos pelos dois verificadores.

    Contar 11 dígitos não basta: o dono digita o CPF olhando um documento na
    mão, e um dígito trocado vira um cliente novo que ninguém encontra na
    busca depois — e some da lista de quem está devendo. Os verificadores
    pegam justamente a troca e a inversão de dígitos, que é o erro que
    acontece de verdade.
    """
    digitos = "".join(c for c in str(valor) if c.isdigit())
    if len(digitos) != 11:
        raise ValueError("CPF precisa ter 11 dígitos")

    # 111.111.111-11 e companhia passam na conta dos verificadores, mas não
    # são CPF de ninguém — é o que sai quando alguém segura uma tecla.
    if digitos == digitos[0] * 11:
        raise ValueError("CPF inválido — confira os números")

    for quantos in (9, 10):
        soma = sum(int(d) * (quantos + 1 - i) for i, d in enumerate(digitos[:quantos]))
        esperado = (soma * 10) % 11 % 10
        if int(digitos[quantos]) != esperado:
            raise ValueError("CPF inválido — confira os números")

    return digitos


def validar_telefone(valor: str | None) -> str | None:
    """Só os dígitos: `(11) 99999-0000` e `11999990000` são o mesmo telefone,
    e guardar os dois formatos faria a busca não bater com nenhum.

    Campo em branco passa (telefone é opcional), mas campo **preenchido com
    algo que não vira telefone**, não: antes, "abcdefghij" sobrava vazio na
    limpeza dos dígitos e era gravado como "sem telefone" — o dono digitava
    errado e o sistema aceitava calado.
    """
    if valor is None:
        return None
    texto = valor.strip()
    if not texto:
        return None

    digitos = "".join(c for c in texto if c.isdigit())
    if len(digitos) not in (10, 11):
        raise ValueError("Telefone precisa ter 10 ou 11 dígitos, com DDD")
    return digitos


def validar_cpf_opcional(valor: str | None) -> str | None:
    """CPF que pode faltar (o do fornecedor, o do avalista): em branco passa,
    preenchido tem que fechar a conta como qualquer outro CPF."""
    if valor is None or not str(valor).strip():
        return None
    return validar_cpf(valor)


# Regex de e-mail proposital de "bom o bastante": algo@algo.algo, sem espaço.
# Não é a gramática completa do RFC — essa recusa e-mail de verdade e aceita
# lixo, e aqui o que importa é pegar o dedo escorregado, não certificar.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_email(valor: str | None) -> str | None:
    """Em branco passa (e-mail é opcional). Preenchido, tem que ter cara de
    e-mail — senão o dono digitou errado e ninguém avisa."""
    if valor is None:
        return None
    texto = valor.strip().lower()
    if not texto:
        return None
    if not _EMAIL.match(texto):
        raise ValueError("E-mail inválido — confira o endereço")
    return texto


def validar_observacao(valor: str | None) -> str | None:
    """Anotação livre do dono. Em branco (ou só espaço) vira `None` — assim a
    tela não precisa distinguir "campo vazio" de "campo com um espaço", e o
    banco não guarda linha em branco que parece anotação."""
    if valor is None:
        return None
    texto = valor.strip()
    return texto or None


def validar_texto_nao_vazio(valor: str | None) -> str | None:
    """Pega o `"   "` que passaria num `min_length=1` sem perceber que é só
    espaço em branco."""
    if valor is None:
        return None
    limpo = valor.strip()
    if not limpo:
        raise ValueError("Não pode ficar em branco")
    return limpo

