"""Grava sozinho tudo que muda, e impede que qualquer coisa seja apagada.

Duas garantias, e as duas valem pro sistema inteiro — inclusive pra código
que ainda não foi escrito:

1. **Nada é apagado.** Qualquer tentativa de remover uma linha do banco
   estoura `ApagarProibido` antes de chegar no disco. Quem precisa "sumir"
   com alguma coisa desativa, pausa ou marca como cancelada — o registro
   continua lá.

2. **Toda alteração vira histórico.** Cadastrar e editar geram uma linha em
   `historico` com o que mudou, de quanto pra quanto, quando e por quem.

Isso mora num ouvinte do SQLAlchemy, e não em cada rota, de propósito: a
garantia não pode depender de alguém lembrar de chamar. Uma rota nova escrita
daqui a um ano já nasce coberta.

**O que fica de fora, e por quê.** As sessões de login (`SessaoAuth`) não
entram no histórico: elas giram sozinhas a cada renovação de token, várias
vezes por dia por aparelho, e guardam o hash do refresh. Registrá-las
encheria o histórico de ruído e ainda copiaria credencial pra outra tabela.
Pelo mesmo motivo, chave de acesso e token nunca são copiados pra cá.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Delete, event, insert, inspect
from sqlalchemy.orm import Session

from app.models.historico import AcaoHistorico, Historico
from app.models.dado_antigo import LinhaAntiga
from app.models.moto import Moto, StatusMoto
from app.models.usuario import SessaoAuth

# Não entram no histórico. `Historico` por razão óbvia (seria infinito),
# `SessaoAuth` pelo motivo explicado no topo, e `LinhaAntiga` porque ela já é
# um arquivo morto: ninguém edita linha de backup do sistema antigo. Registrar
# uma criação por linha punha 73.793 linhas de ruído no histórico da loja num
# único import — e enterrava justamente o que o dono abre o histórico pra ver.
# O `LoteAntigo` continua entrando: "quem importou o quê e quando" é evento.
_FORA = (Historico, SessaoAuth, LinhaAntiga)

# Nunca copiados pra outra tabela, nem pra dizer que mudaram. `chave_hash` é
# a chave de acesso do dono: o banco guarda só o hash justamente pra ela não
# existir em claro em lugar nenhum, e copiá-lo pro histórico — que o dono lê
# pela API — seria espalhar credencial por uma tabela a mais.
_CAMPOS_SECRETOS = {"chave_hash", "senha_hash", "refresh_hash", "token_hash"}


class ApagarProibido(Exception):
    """Alguém tentou remover uma linha do banco.

    O sistema não apaga nada: o histórico da loja é o próprio banco, e um
    registro que some leva junto a prova de que existiu.
    """


def _simples(valor):
    """Deixa o valor num formato que o JSON aceita, sem perder o que ele é."""
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, (uuid.UUID, Decimal)):
        return str(valor)
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return repr(valor)


def _id_do_registro(obj) -> str | None:
    chaves = inspect(obj).mapper.primary_key
    valores = [getattr(obj, c.key, None) for c in chaves]
    if any(v is None for v in valores):
        return None  # ainda não foi pro banco; lido de novo depois do flush
    return "|".join(str(v) for v in valores)


def _valores_iniciais(obj) -> dict:
    """Todos os campos de um registro recém-criado, como 'antes: nulo'."""
    mudancas = {}
    for coluna in inspect(obj).mapper.column_attrs:
        if coluna.key in _CAMPOS_SECRETOS:
            continue
        valor = getattr(obj, coluna.key, None)
        if valor is None:
            continue  # campo em branco no cadastro não é informação
        mudancas[coluna.key] = {"antes": None, "depois": _simples(valor)}
    return mudancas


def _mudancas(obj) -> dict:
    """O que mudou neste registro, de quanto pra quanto."""
    estado = inspect(obj)
    mudancas = {}
    for coluna in estado.mapper.column_attrs:
        if coluna.key in _CAMPOS_SECRETOS:
            continue
        historico = estado.attrs[coluna.key].history
        if not historico.has_changes():
            continue
        antes = historico.deleted[0] if historico.deleted else None
        depois = historico.added[0] if historico.added else None
        if antes == depois:
            continue  # gravou o mesmo valor por cima; não é mudança
        mudancas[coluna.key] = {"antes": _simples(antes), "depois": _simples(depois)}
    return mudancas


@event.listens_for(Session, "do_orm_execute")
def _barrar_delete_em_massa(estado):
    """Fecha o outro caminho pra apagar.

    `sessao.delete(obj)` cai no `before_flush` abaixo. Mas
    `sessao.execute(delete(Tabela).where(...))` não passa por lá — ele vira
    SQL direto, sem a sessão saber que existia um objeto. Era assim que o
    código antigo removia as sessões de login de um vendedor excluído.
    """
    if isinstance(estado.statement, Delete):
        alvo = getattr(estado.statement.table, "name", "desconhecida")
        raise ApagarProibido(
            f"Este sistema não apaga registro (DELETE em {alvo}). "
            "Marque como revogado, inativo ou cancelado."
        )


@event.listens_for(Session, "before_flush")
def _antes_de_gravar(sessao, _contexto, _instancias):
    if sessao.deleted:
        # Única exceção ao "nada é apagado": moto ainda em estoque (DISPONIVEL),
        # que nunca foi vendida. Não há venda nem carnê em cima dela — é só uma
        # moto cadastrada errado. A vendida continua intocável.
        if not all(
            isinstance(o, Moto) and o.status == StatusMoto.DISPONIVEL
            for o in sessao.deleted
        ):
            quais = ", ".join(sorted({type(o).__name__ for o in sessao.deleted}))
            raise ApagarProibido(
                f"Este sistema não apaga registro ({quais}). "
                "Desative, pause ou cancele — o registro continua no banco."
            )

    pendentes = []
    for obj in sessao.new:
        if isinstance(obj, _FORA):
            continue
        pendentes.append((obj, AcaoHistorico.CRIADO, _valores_iniciais(obj)))

    for obj in sessao.dirty:
        if isinstance(obj, _FORA) or not sessao.is_modified(obj):
            continue
        mudancas = _mudancas(obj)
        if mudancas:
            pendentes.append((obj, AcaoHistorico.ALTERADO, mudancas))

    # Guardado pra depois do flush: um registro novo com id automático só
    # ganha o id quando o INSERT roda, e histórico sem o id do registro não
    # serve pra achar nada.
    if pendentes:
        sessao.info.setdefault("_historico_pendente", []).extend(pendentes)


@event.listens_for(Session, "after_flush")
def _depois_de_gravar(sessao, _contexto):
    pendentes = sessao.info.pop("_historico_pendente", None)
    if not pendentes:
        return

    usuario_id = sessao.info.get("usuario_id")
    linhas = []
    for obj, acao, mudancas in pendentes:
        registro_id = _id_do_registro(obj)
        if registro_id is None:
            continue
        linhas.append({
            "tabela": obj.__tablename__,
            "registro_id": registro_id,
            "acao": acao,
            "mudancas": mudancas,
            "usuario_id": usuario_id,
        })

    # `insert` do Core, não `sessao.add`: aqui dentro o flush já está rodando
    # e a sessão não aceitaria objetos novos sem um segundo flush.
    if linhas:
        sessao.execute(insert(Historico), linhas)


def registrar_autor(sessao, usuario_id: int | None) -> None:
    """Diz de quem é a mão nas mudanças desta requisição."""
    sessao.info["usuario_id"] = usuario_id
