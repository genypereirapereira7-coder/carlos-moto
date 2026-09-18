"""Popula o banco com o Carlos e um estoque de exemplo.

    python -m app.seed

Idempotente: rodar de novo não duplica nada.
"""

import asyncio
from datetime import date

from sqlalchemy import select

from app.config import get_config
from app.db import Sessao
from app.models.base import agora
from app.models.cliente import Cliente
from app.models.moto import CondicaoMoto, Moto
from app.models.usuario import Papel, Usuario
from app.seguranca import gerar_chave, hash_chave

cfg = get_config()

USUARIOS = [
    ("Carlos", Papel.DONO),
    # Os dois vendedores da loja. Entram já liberados — o dono escolhe qual
    # deles fez cada venda no formulário de venda. Cada um ganha a própria
    # chave de acesso no seed (podem, se quiserem, entrar no próprio aparelho).
    ("Zé Carlos", Papel.VENDEDOR),
    ("Dani", Papel.VENDEDOR),
]

# (nome, cpf, telefone)
CLIENTES = [
    ("Maria Souza", "52998224725", "11999990000"),
    ("José Pereira", "11144477735", "11988887777"),
]

# (marca, modelo, ano, cor, condicao, chassi, placa, km, preco_centavos,
#  valor_compra_centavos, data_compra, fornecedor_nome)
MOTOS = [
    ("Honda", "CG160 Titan", 2026, "Vermelha", CondicaoMoto.NOVA, "9C2KC1234RR000001", "HON1A01", 0, 1_699_000, 1_400_000, date(2026, 8, 1), "Distribuidora Honda SP"),
    ("Honda", "CG160 Titan", 2026, "Preta", CondicaoMoto.NOVA, "9C2KC1234RR000002", "HON1A02", 0, 1_699_000, 1_400_000, date(2026, 8, 1), "Distribuidora Honda SP"),
    ("Honda", "CG160 Titan", 2026, "Branca", CondicaoMoto.NOVA, "9C2KC1234RR000003", "HON1A03", 0, 1_699_000, 1_400_000, date(2026, 8, 1), "Distribuidora Honda SP"),
    ("Yamaha", "Factor 125", 2025, "Azul", CondicaoMoto.USADA, "9C6KE0850RR123456", "ABC1D23", 8200, 1_150_000, 850_000, date(2026, 7, 15), None),
    ("Yamaha", "Fazer 250", 2023, "Grafite", CondicaoMoto.USADA, "9C6RN0470PR654321", "XYZ9K87", 21000, 1_890_000, 1_400_000, date(2026, 6, 20), None),
]


def _anunciar_chave(nome: str, chave: str) -> None:
    """Grita a chave na tela. É a única vez que ela aparece."""
    print(
        "\n"
        "  ============================================================\n"
        f"   CHAVE DE ACESSO DE {nome.upper()}\n"
        "  ============================================================\n"
        f"\n        {chave}\n\n"
        "   Digite esta chave uma vez ao abrir o sistema. Depois disso\n"
        "   este computador nao pede mais nada.\n"
        "\n"
        "   Anote em algum lugar seguro: ela nao aparece de novo. Se\n"
        "   perder, gere outra pela tela do dono.\n"
        "  ============================================================\n",
        flush=True,
    )


async def semear(detalhado: bool = True) -> None:
    async with Sessao() as sessao:
        criados: list[str] = []

        carlos_id: int | None = None
        for nome, papel in USUARIOS:
            usuario = (
                await sessao.execute(select(Usuario).where(Usuario.nome == nome))
            ).scalar_one_or_none()
            if usuario is None:
                # A chave só existe em claro aqui, neste instante. O banco
                # guarda o hash; por isso ela é impressa logo abaixo — se
                # passar batido, o jeito é gerar outra.
                #
                # `chave_dono` (a fixa do ambiente) é só do dono: usá-la pra
                # todos colidiria o hash único assim que entrasse o segundo
                # usuário. Vendedor sempre ganha uma chave aleatória própria.
                chave = (cfg.chave_dono if papel == Papel.DONO else "") or gerar_chave()
                usuario = Usuario(
                    nome=nome,
                    chave_hash=hash_chave(chave),
                    papel=papel,
                    ativo=True,
                    # Nasce liberado — o dono e os vendedores existem antes de
                    # o sistema subir, não passam pela fila de aprovação.
                    aprovado_em=agora(),
                )
                sessao.add(usuario)
                await sessao.flush()
                _anunciar_chave(nome, chave)
                criados.append(f"usuário {nome} ({papel.value})")
            if papel == Papel.DONO:
                carlos_id = usuario.id

        if not cfg.semear_exemplos:
            # Só as contas. Sem estoque nem cliente de mentira — a loja entra
            # com os dados dela.
            await sessao.commit()
            if criados:
                print(f"seed: {len(criados)} conta(s) criada(s), sem dados de exemplo")
            else:
                print("seed: nada a fazer, banco já semeado")
            return

        clientes_por_nome: dict[str, Cliente] = {}
        for nome, cpf, telefone in CLIENTES:
            cliente = (
                await sessao.execute(select(Cliente).where(Cliente.cpf == cpf))
            ).scalar_one_or_none()
            if cliente is None:
                cliente = Cliente(nome=nome, cpf=cpf, telefone=telefone)
                sessao.add(cliente)
                await sessao.flush()
                criados.append(f"cliente {nome}")
            clientes_por_nome[nome] = cliente

        # A Factor foi comprada da Maria — exemplo da aba "vendeu" no cadastro dela.
        fornecedor_maria_id = clientes_por_nome["Maria Souza"].id

        for (
            marca, modelo, ano, cor, condicao, chassi, placa, km, preco,
            valor_compra, data_compra, fornecedor_nome,
        ) in MOTOS:
            existe = (
                await sessao.execute(select(Moto).where(Moto.chassi == chassi))
            ).scalar_one_or_none()
            if existe is None:
                sessao.add(
                    Moto(
                        marca=marca,
                        modelo=modelo,
                        ano=ano,
                        cor=cor,
                        condicao=condicao,
                        chassi=chassi,
                        placa=placa,
                        km=km,
                        preco_centavos=preco,
                        valor_compra_centavos=valor_compra,
                        data_compra=data_compra,
                        fornecedor_cliente_id=fornecedor_maria_id if modelo == "Factor 125" else None,
                        fornecedor_nome=fornecedor_nome,
                        criado_por=carlos_id,
                    )
                )
                criados.append(f"moto {marca} {modelo} ({chassi})")

        await sessao.commit()

    if criados:
        print(f"seed: {len(criados)} registros criados")
        if detalhado:
            for linha in criados:
                print(f"  + {linha}")
    else:
        print("seed: nada a fazer, banco já semeado")


if __name__ == "__main__":
    asyncio.run(semear())
