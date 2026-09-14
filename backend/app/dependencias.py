"""Dependências de autenticação/autorização das rotas."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessao
from app.historico import registrar_autor
from app.models.usuario import Papel, Usuario
from app.seguranca import Identidade, ler_token_acesso

esquema = HTTPBearer(auto_error=False)

SessaoDep = Annotated[AsyncSession, Depends(get_sessao)]


async def identidade_atual(
    credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema)],
) -> Identidade:
    if credencial is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sem token")
    ident = ler_token_acesso(credencial.credentials)
    if ident is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido ou expirado")
    return ident


IdentidadeDep = Annotated[Identidade, Depends(identidade_atual)]


async def usuario_atual(ident: IdentidadeDep, sessao: SessaoDep) -> Usuario:
    usuario = await sessao.get(Usuario, ident.usuario_id)
    if usuario is None or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo")
    registrar_autor(sessao, ident.usuario_id)
    return usuario


UsuarioDep = Annotated[Usuario, Depends(usuario_atual)]


def exige(*papeis: Papel) -> Callable[..., Coroutine[Any, Any, Identidade]]:
    """Uso: `_: Annotated[Identidade, Depends(exige(Papel.DONO))]`."""

    async def verificar(ident: IdentidadeDep, sessao: SessaoDep) -> Identidade:
        if ident.papel not in papeis:
            permitidos = ", ".join(p.value for p in papeis)
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requer papel: {permitidos}"
            )
        # Carimba o autor antes de a rota mexer em qualquer coisa: é o que
        # faz o histórico saber de quem foi a mão.
        registrar_autor(sessao, ident.usuario_id)
        return ident

    return verificar


SoDono = Annotated[Identidade, Depends(exige(Papel.DONO))]

# Dono também pode registrar e ver venda — é o celular dele que resolve um
# atendimento se o vendedor não estiver com o próprio aparelho em mãos.
SoVendedor = Annotated[Identidade, Depends(exige(Papel.VENDEDOR, Papel.DONO))]
