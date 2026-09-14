"""Administração de contas de vendedor, pelo dono."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.dependencias import SessaoDep, SoDono
from app.models.base import agora
from app.models.usuario import Papel, SessaoAuth, Usuario
from app.seguranca import gerar_chave, hash_chave
from app.schemas.usuario import AtivoEntrada, ChaveNova, VendedorNovo, VendedorResumo
from app.servicos.eventos import Evento, publicar_apos_commit

rotas = APIRouter(prefix="/usuarios", tags=["usuarios"])


@rotas.get("", response_model=list[VendedorResumo])
async def listar_vendedores(sessao: SessaoDep, _: SoDono):
    """Só vendedor aparece aqui — o dono não se gerencia por esta tela."""
    consulta = select(Usuario).where(Usuario.papel == Papel.VENDEDOR).order_by(Usuario.nome)
    return (await sessao.execute(consulta)).scalars().all()


@rotas.post("", response_model=ChaveNova, status_code=status.HTTP_201_CREATED)
async def criar_vendedor(dados: VendedorNovo, sessao: SessaoDep, _: SoDono):
    """Cria a conta de um vendedor e devolve a chave dele — **uma vez só**.

    Não há senha pra ninguém escolher: o servidor gera a chave, ela aparece
    nesta resposta e nunca mais. O banco guarda só o hash. O dono anota e
    entrega; o vendedor digita uma vez no aparelho dele.
    """
    nome = dados.nome.strip()
    existe = (
        await sessao.execute(select(Usuario).where(func.lower(Usuario.nome) == nome.lower()))
    ).scalar_one_or_none()
    if existe is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esse nome já está em uso")

    chave = gerar_chave()
    usuario = Usuario(
        nome=nome,
        chave_hash=hash_chave(chave),
        papel=Papel.VENDEDOR,
        ativo=True,
        aprovado_em=agora(),
    )
    sessao.add(usuario)
    await sessao.flush()

    return ChaveNova(usuario_id=usuario.id, nome=usuario.nome, chave=chave)


@rotas.post("/{usuario_id}/chave", response_model=ChaveNova)
async def trocar_chave(usuario_id: int, sessao: SessaoDep, dono: SoDono):
    """Gera uma chave nova e aposenta a anterior. Serve pro dono também.

    **Não desconecta os aparelhos já pareados**, de propósito: a chave só
    serve pra parear um aparelho novo, e quem mantém os antigos conectados é
    o refresh token de cada um. Pra tirar o acesso de um aparelho perdido, o
    caminho é a tela de sessões — trocar a chave não faria isso.
    """
    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não existe")

    chave = gerar_chave()
    usuario.chave_hash = hash_chave(chave)
    await sessao.flush()

    return ChaveNova(usuario_id=usuario.id, nome=usuario.nome, chave=chave)


@rotas.patch("/{usuario_id}", response_model=VendedorResumo)
async def pausar_ou_reativar(
    usuario_id: int, dados: AtivoEntrada, sessao: SessaoDep, _: SoDono
):
    """Mesma rota libera um cadastro pendente e pausa/reativa um vendedor.

    Liberar pela primeira vez carimba `aprovado_em`; pausar e reativar depois
    não o apaga. É o carimbo que faz a tela do dono distinguir "esperando
    liberação" de "pausei esta pessoa de propósito".
    """
    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None or usuario.papel != Papel.VENDEDOR:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendedor não existe")

    usuario.ativo = dados.ativo
    if dados.ativo and usuario.aprovado_em is None:
        usuario.aprovado_em = agora()

    await sessao.flush()
    saida = VendedorResumo.model_validate(usuario)
    await publicar_apos_commit(
        sessao, Evento.USUARIO_DESATIVADO, {"usuario_id": usuario_id}
    )
    return saida


@rotas.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desativar(usuario_id: int, sessao: SessaoDep, _: SoDono):
    """Tira o acesso do vendedor — **sem apagar a conta**.

    Antes esta rota removia a linha do banco, e recusava com 409 quando o
    vendedor já tinha vendas (a foreign key de `Venda.vendedor_id` segurava).
    Não remove mais nada: o sistema não apaga registro nenhum (ver
    `app/historico.py`), porque sumir com a conta levava junto a resposta pra
    "quem atendeu esse cliente em março?".

    A conta fica no banco, desativada, e os aparelhos dela perdem o acesso na
    hora. Vale pra qualquer vendedor, com vendas ou sem.
    """
    usuario = await sessao.get(Usuario, usuario_id)
    if usuario is None or usuario.papel != Papel.VENDEDOR:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendedor não existe")

    usuario.ativo = False

    # Revogadas, não apagadas: o refresh para de valer na hora e fica
    # registrado quando foi cortado.
    abertas = await sessao.execute(
        select(SessaoAuth).where(
            SessaoAuth.usuario_id == usuario_id, SessaoAuth.revogado_em.is_(None)
        )
    )
    for aberta in abertas.scalars():
        aberta.revogado_em = agora()

    await publicar_apos_commit(
        sessao, Evento.USUARIO_DESATIVADO, {"usuario_id": usuario_id}
    )
