"""Configuração via variáveis de ambiente (prefixo CARLOSMOTO_)."""

from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# O que o `sslmode` do libpq quer dizer pro asyncpg, que usa outro nome e outro
# vocabulário. "disable" fica de fora de propósito: não vira parâmetro nenhum,
# porque não exigir TLS já é o padrão do asyncpg.
_SSL_EQUIVALENTE = {
    "allow": "prefer",
    "prefer": "prefer",
    "require": "require",
    "verify-ca": "verify-ca",
    "verify-full": "verify-full",
}


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARLOSMOTO_", env_file=".env", extra="ignore")

    ambiente: str = "dev"

    # Duas variáveis, nesta ordem: a nossa primeiro, `DATABASE_URL` depois.
    # Serviço de banco gerenciado publica a string de conexão como
    # `DATABASE_URL` — é o nome que o Railway, o Heroku e o Fly usam. Aceitar o
    # nome de lá economiza o passo mais fácil de esquecer na hora de publicar.
    # `CARLOSMOTO_DATABASE_URL` continua ganhando quando as duas existem.
    database_url: str = Field(
        default="postgresql+asyncpg://carlosmoto:carlosmoto@localhost:5432/carlosmoto",
        validation_alias=AliasChoices("CARLOSMOTO_DATABASE_URL", "DATABASE_URL"),
    )

    # Autenticação
    jwt_segredo: str = "dev-inseguro-troque-em-producao"
    jwt_algoritmo: str = "HS256"
    acesso_expira_min: int = 30          # token curto, renovado pelo refresh

    # Um ano, e deslizante: cada renovação abre uma sessão nova com o prazo
    # cheio. Na prática a senha é digitada uma vez e nunca mais. Quem tira o
    # acesso de alguém é o dono, pela tela de sessões, e não o relógio.
    refresh_expira_dias: int = 365

    login_max_tentativas: int = 5        # tentativas de parear, por IP
    login_bloqueio_seg: int = 300

    # Os dois PWAs e a API vivem na mesma origem, então o navegador nunca
    # precisa de CORS pra usar o sistema. Lista vazia = só a própria origem.
    cors_origens: list[str] = []

    # A política de conteúdo. Tudo vem da própria origem porque não há CDN,
    # fonte externa nem script de terceiro em lugar nenhum do frontend.
    # `CARLOSMOTO_CSP=""` desliga.
    csp: str = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' ws: wss:; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    # HSTS: um ano, e só em produção e só sobre HTTPS.
    hsts_max_age: int = 31536000

    # Onde ficam os PWAs; em dev o próprio FastAPI serve os arquivos.
    dir_frontend: str = "../frontend"

    # Só o dono nasce pelo seed. Fica aqui como padrão pra que a garagem
    # funcione sem ninguém decorar variável de ambiente.
    # Chave inicial do dono. Em branco = o seed gera uma e mostra na tela —
    # que é o caminho normal. Definir aqui só serve pra reproduzir um
    # ambiente de teste com chave conhecida.
    chave_dono: str = ""

    # O seed cria um estoque e clientes de exemplo pra quem está conhecendo o
    # sistema. Com `CARLOSMOTO_SEMEAR_EXEMPLOS=false` ele cria só as contas
    # (dono e vendedores) e deixa o resto vazio — é como a loja começa de
    # verdade, sem moto inventada no estoque.
    semear_exemplos: bool = True

    # Migração do sistema antigo (PROVISÓRIO). Só preenchidas no computador
    # do cliente, onde o sistema antigo está; na nuvem ficam vazias e o
    # botão nem aparece.
    migracao_origem: str = ""
    migracao_destino: str = ""

    # Fuso da loja. O banco guarda tudo em UTC, mas "hoje" — o dia em que uma
    # parcela passa a estar atrasada, o dia que fecha o caixa — é o dia no
    # relógio do balcão. Sem isto, depois das 21h de Brasília o UTC já virou
    # o dia, e uma parcela que vence hoje aparecia atrasada.
    fuso: str = "America/Sao_Paulo"

    @model_validator(mode="after")
    def _segredo_tem_que_ser_trocado(self) -> "Config":
        """Em produção, recusa subir com o segredo de desenvolvimento.

        O padrão está escrito no código, que é público: quem o lê consegue
        assinar um token de DONO e entrar como dono da loja. Antes desta
        checagem o servidor subia calado com ele — a pior forma de falhar,
        porque tudo parece funcionar.
        """
        if not self.producao:
            return self
        if self.jwt_segredo.startswith("dev-") or len(self.jwt_segredo) < 32:
            raise ValueError(
                "CARLOSMOTO_JWT_SEGREDO ainda é o de desenvolvimento (ou é curto "
                "demais). Em produção use um segredo aleatório de 32 caracteres ou "
                "mais: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return self

    @field_validator("database_url")
    @classmethod
    def _url_para_asyncpg(cls, valor: str) -> str:
        """Aceita a URL que o provedor de banco entrega, sem edição manual.

        O Render (e o Heroku, e o Railway) publica a string de conexão no
        formato do libpq — `postgresql://…`, às vezes ainda com o `postgres://`
        antigo, e a externa vem com `?sslmode=require` pendurado. Nada disso
        serve pra engine async: sem o `+asyncpg` o SQLAlchemy carrega o driver
        síncrono e morre com "the greenlet library is required"; e o asyncpg
        não conhece `sslmode`, então rejeita a conexão por parâmetro
        desconhecido antes mesmo de tentar.
        """
        valor = valor.strip()
        if not valor:
            return valor

        esquema, resto = (valor.split("://", 1) + [""])[:2] if "://" in valor else (valor, None)
        if resto is None:
            return valor
        if esquema in {"postgres", "postgresql"} or esquema.startswith(("postgres+", "postgresql+")) and "asyncpg" not in esquema:
            esquema = "postgresql+asyncpg"
        valor = f"{esquema}://{resto}"

        if esquema != "postgresql+asyncpg":
            return valor

        partes = urlsplit(valor)
        consulta = parse_qsl(partes.query, keep_blank_values=True)
        traduzida: list[tuple[str, str]] = []
        for chave, item in consulta:
            if chave == "sslmode":
                modo = item.lower()
                if modo == "disable":
                    continue
                traduzida.append(("ssl", _SSL_EQUIVALENTE.get(modo, "require")))
            elif chave == "channel_binding":
                continue
            else:
                traduzida.append((chave, item))
        return urlunsplit(partes._replace(query=urlencode(traduzida)))

    @property
    def producao(self) -> bool:
        return self.ambiente.lower() in {"prod", "producao", "production"}


@lru_cache
def get_config() -> Config:
    return Config()
