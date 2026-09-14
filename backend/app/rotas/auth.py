"""Pareamento por chave de acesso, renovação de token, logout e sessões.

**O sistema não tem senha.** Quem abre o app num aparelho novo digita a chave
de acesso uma única vez; daí em diante o refresh token mantém aquele aparelho
conectado e nada mais é pedido.

A troca é consciente: a chave sozinha abre o sistema inteiro. O que segura
essa ponta é a tela de sessões — todo aparelho pareado aparece lá e pode ser
desconectado na hora. É ela, e não uma senha, a trava contra um aparelho
perdido ou emprestado.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.config import get_config
from app.dependencias import IdentidadeDep, SessaoDep, SoDono
from app.models.base import agora
from app.models.usuario import Papel, SessaoAuth, Usuario
from app.schemas.auth import (
    ParearEntrada,
    RenovarEntrada,
    SessaoAtiva,
    TokensSaida,
    UsuarioPublico,
)
from app.seguranca import (
    criar_token_acesso,
    gerar_refresh,
    hash_chave,
    hash_refresh,
    normalizar_chave,
    trava_login,
)
from app.servicos.eventos import Evento, publicar_apos_commit

cfg = get_config()
rotas = APIRouter(prefix="/auth", tags=["auth"])


@rotas.post("/parear", response_model=TokensSaida)
async def parear(dados: ParearEntrada, request: Request, sessao: SessaoDep):
    """Liga este aparelho ao sistema. Uma vez só, na primeira abertura.

    Aceita a chave como ela for digitada — com tracinho ou sem, em maiúscula
    ou não. Quem lê de um bilhete não deve ser reprovado por um traço.
    """
    chave = normalizar_chave(dados.chave)
    trava = f"parear:{request.client.host if request.client else '?'}"

    bloqueio = trava_login.segundos_restantes(trava)
    if bloqueio:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas. Tente de novo em {bloqueio}s.",
        )

    # Busca direta pelo hash: a chave é longa e aleatória, então não há
    # dicionário a temer, e assim não se varre a tabela testando uma a uma.
    consulta = select(Usuario).where(Usuario.chave_hash == hash_chave(chave))
    usuario = (await sessao.execute(consulta)).scalar_one_or_none()

    if usuario is None or not usuario.ativo:
        trava_login.registrar_falha(trava)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de acesso inválida")

    trava_login.limpar(trava)
    return await _emitir_tokens(sessao, usuario, dados.dispositivo)


@rotas.post("/renovar", response_model=TokensSaida)
async def renovar(dados: RenovarEntrada, sessao: SessaoDep):
    """Troca o refresh por um par novo.

    O refresh antigo é revogado na troca (rotação). Se um refresh já usado
    aparecer de novo, é sinal de token roubado — derrubamos todas as sessões
    daquele usuário.
    """
    consulta = select(SessaoAuth).where(SessaoAuth.refresh_hash == hash_refresh(dados.refresh))
    sessao_auth = (await sessao.execute(consulta)).scalar_one_or_none()

    if sessao_auth is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh inválido")

    if sessao_auth.usado_em is not None:
        await _revogar_todas(sessao, sessao_auth.usuario_id)
        await sessao.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Refresh reutilizado — sessões encerradas"
        )

    if not sessao_auth.valida:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")

    usuario = await sessao.get(Usuario, sessao_auth.usuario_id)
    if usuario is None or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo")

    sessao_auth.usado_em = agora()
    sessao_auth.revogado_em = agora()
    return await _emitir_tokens(sessao, usuario, sessao_auth.dispositivo)


@rotas.post("/sair", status_code=status.HTTP_204_NO_CONTENT)
async def sair(dados: RenovarEntrada, sessao: SessaoDep):
    consulta = select(SessaoAuth).where(SessaoAuth.refresh_hash == hash_refresh(dados.refresh))
    sessao_auth = (await sessao.execute(consulta)).scalar_one_or_none()
    if sessao_auth and sessao_auth.revogado_em is None:
        sessao_auth.revogado_em = agora()


@rotas.get("/sessoes", response_model=list[SessaoAtiva])
async def sessoes_abertas(sessao: SessaoDep, dono: SoDono):
    """Quem está logado agora, do login mais recente pro mais antigo. Só o dono vê."""
    consulta = (
        select(SessaoAuth, Usuario)
        .join(Usuario, Usuario.id == SessaoAuth.usuario_id)
        .where(SessaoAuth.revogado_em.is_(None), SessaoAuth.expira_em > agora())
        .order_by(SessaoAuth.criado_em.desc())
    )

    return [
        SessaoAtiva(
            id=s.id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            papel=usuario.papel,
            dispositivo=s.dispositivo,
            criado_em=s.criado_em,
            expira_em=s.expira_em,
            meu_usuario=usuario.id == dono.usuario_id,
        )
        for s, usuario in (await sessao.execute(consulta)).all()
    ]


@rotas.delete("/sessoes/{sessao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revogar_sessao(sessao_id: uuid.UUID, sessao: SessaoDep, _: SoDono):
    """Tira o acesso de um aparelho — o refresh morre na hora."""
    aberta = await sessao.get(SessaoAuth, sessao_id)
    if aberta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não existe")
    if aberta.revogado_em is None:
        aberta.revogado_em = agora()


@rotas.get("/eu", response_model=UsuarioPublico)
async def eu(ident: IdentidadeDep, sessao: SessaoDep):
    usuario = await sessao.get(Usuario, ident.usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário não existe mais")
    return usuario


# ------------------------------------------------------------------ internos

async def _emitir_tokens(sessao, usuario: Usuario, dispositivo: str | None) -> TokensSaida:
    acesso, validade = criar_token_acesso(usuario.id, usuario.nome, usuario.papel)
    bruto, guardado = gerar_refresh()

    sessao.add(
        SessaoAuth(
            usuario_id=usuario.id,
            refresh_hash=guardado,
            dispositivo=dispositivo,
            expira_em=agora() + timedelta(days=cfg.refresh_expira_dias),
        )
    )

    return TokensSaida(
        acesso=acesso,
        refresh=bruto,
        expira_em=validade,
        usuario_id=usuario.id,
        nome=usuario.nome,
        papel=usuario.papel,
    )


async def _revogar_todas(sessao, usuario_id: int) -> None:
    consulta = select(SessaoAuth).where(
        SessaoAuth.usuario_id == usuario_id, SessaoAuth.revogado_em.is_(None)
    )
    for s in (await sessao.execute(consulta)).scalars():
        s.revogado_em = agora()
