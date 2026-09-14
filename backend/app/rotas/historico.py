"""Consulta do histórico: o que já aconteceu com um registro.

Só o dono lê. O histórico mostra valores antigos de preço, custo e lucro —
é a mesma informação que a tela FINANCEIRO protege.
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencias import SessaoDep, SoDono
from app.models.historico import Historico
from app.models.usuario import Usuario
from app.schemas.historico import MudancaSaida

rotas = APIRouter(prefix="/historico", tags=["historico"])


@rotas.get("/{tabela}/{registro_id}", response_model=list[MudancaSaida])
async def de_um_registro(tabela: str, registro_id: str, sessao: SessaoDep, _: SoDono):
    """Tudo que já mudou neste registro, do mais recente pro mais antigo.

    `tabela` é o nome da tabela (`moto`, `cliente`, `venda`, `parcela`,
    `despesa_moto`) e `registro_id` é o id daquele registro.
    """
    consulta = (
        select(Historico, Usuario.nome)
        .outerjoin(Usuario, Usuario.id == Historico.usuario_id)
        .where(Historico.tabela == tabela, Historico.registro_id == str(registro_id))
        .order_by(Historico.quando.desc(), Historico.id.desc())
    )
    return [
        MudancaSaida(
            id=linha.id,
            acao=linha.acao,
            mudancas=linha.mudancas,
            usuario_id=linha.usuario_id,
            usuario_nome=nome,
            quando=linha.quando,
        )
        for linha, nome in (await sessao.execute(consulta)).all()
    ]
