"""Chave de acesso, tokens JWT e trava de tentativas."""

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_config
from app.models.usuario import Papel

cfg = get_config()


# ------------------------------------------------------------ chave de acesso

# Alfabeto sem os pares que a gente confunde lendo de um papel: sem O e 0,
# sem I, 1 e L, sem U e V. Quem digita a chave está lendo de uma tela ou de
# um bilhete, uma vez só na vida — não pode errar por causa da fonte.
_ALFABETO = "ABCDEFGHJKMNPQRSTWXYZ23456789"
_GRUPOS = 4
_POR_GRUPO = 4


def gerar_chave() -> str:
    """Uma chave nova, no formato `XKFD-7H3A-9QPM-R4TW`.

    16 caracteres num alfabeto de 29 dá cerca de 78 bits de aleatoriedade —
    forte o bastante pra ninguém adivinhar, curta o bastante pra caber num
    bilhete e ser digitada sem raiva.
    """
    letras = "".join(secrets.choice(_ALFABETO) for _ in range(_GRUPOS * _POR_GRUPO))
    return "-".join(
        letras[i : i + _POR_GRUPO] for i in range(0, len(letras), _POR_GRUPO)
    )


def normalizar_chave(bruta: str) -> str:
    """Aceita com ou sem tracinho, em minúscula, com espaço sobrando."""
    return "".join(c for c in bruta.upper() if c.isalnum())


def hash_chave(bruta: str) -> str:
    """SHA-256, e não bcrypt, pelo mesmo motivo do refresh token: a chave já é
    aleatória de ~78 bits, não existe dicionário que a alcance. E precisa ser
    determinístico — é assim que o pareamento acha o dono pela chave
    digitada, sem varrer a tabela testando um a um."""
    return hashlib.sha256(normalizar_chave(bruta).encode()).hexdigest()


# ---------------------------------------------------------------------- JWT

@dataclass(frozen=True)
class Identidade:
    usuario_id: int
    nome: str
    papel: Papel


def criar_token_acesso(usuario_id: int, nome: str, papel: Papel) -> tuple[str, int]:
    """Devolve (token, segundos_de_validade)."""
    expira_em = datetime.now(UTC) + timedelta(minutes=cfg.acesso_expira_min)
    corpo = {
        "sub": str(usuario_id),
        "nome": nome,
        "papel": papel.value,
        "exp": expira_em,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(corpo, cfg.jwt_segredo, algorithm=cfg.jwt_algoritmo)
    return token, cfg.acesso_expira_min * 60


def ler_token_acesso(token: str) -> Identidade | None:
    try:
        corpo = jwt.decode(token, cfg.jwt_segredo, algorithms=[cfg.jwt_algoritmo])
        return Identidade(
            usuario_id=int(corpo["sub"]),
            nome=corpo.get("nome", ""),
            papel=Papel(corpo["papel"]),
        )
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def validade_do_token(token: str) -> datetime | None:
    """Quando este access token expira.

    Só o `/ws` precisa disto: uma conexão HTTP morre a cada requisição e
    revalida o token na seguinte; um WebSocket aberto ficaria de pé pra sempre
    com o token que apresentou na entrada. Sabendo a validade, a rota derruba
    o socket no vencimento e o cliente reconecta com um token novo.
    """
    try:
        corpo = jwt.decode(token, cfg.jwt_segredo, algorithms=[cfg.jwt_algoritmo])
        return datetime.fromtimestamp(corpo["exp"], UTC)
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError, OSError):
        return None


# ------------------------------------------------------------ refresh token

def gerar_refresh() -> tuple[str, str]:
    """Devolve (token_em_claro, hash_pra_guardar).

    SHA-256 e não bcrypt: o refresh já é aleatório de 256 bits, não tem o que
    forçar por dicionário, e o /auth/renovar precisa ser rápido.
    """
    bruto = f"{uuid.uuid4()}.{secrets.token_urlsafe(32)}"
    return bruto, hashlib.sha256(bruto.encode()).hexdigest()


def hash_refresh(bruto: str) -> str:
    return hashlib.sha256(bruto.encode()).hexdigest()


# -------------------------------------------------- trava de força bruta

@dataclass
class _Tentativas:
    contagem: int = 0
    bloqueado_ate: float = 0.0


@dataclass
class TravaLogin:
    """Em memória de propósito: a v1 roda com um worker só."""

    max_tentativas: int = cfg.login_max_tentativas
    bloqueio_seg: int = cfg.login_bloqueio_seg
    _por_chave: dict[str, _Tentativas] = field(default_factory=dict)

    def segundos_restantes(self, chave: str) -> int:
        registro = self._por_chave.get(chave)
        if not registro:
            return 0
        restante = registro.bloqueado_ate - time.monotonic()
        return int(restante) + 1 if restante > 0 else 0

    def registrar_falha(self, chave: str) -> None:
        registro = self._por_chave.setdefault(chave, _Tentativas())
        registro.contagem += 1
        if registro.contagem >= self.max_tentativas:
            registro.bloqueado_ate = time.monotonic() + self.bloqueio_seg
            registro.contagem = 0

    def limpar(self, chave: str) -> None:
        self._por_chave.pop(chave, None)


trava_login = TravaLogin()
