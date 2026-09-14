"""Ajustes de esquema em bancos que já existem.

`create_all` cria a tabela que falta, mas não toca em tabela que já existe:
uma coluna nova nunca chega sozinha num banco que já tem dados. Estas
migrações rodam toda vez que o servidor sobe e não fazem nada quando já foram
aplicadas, então é seguro repetir.

Isto **não** substitui uma ferramenta de migração de verdade (Alembic) no dia
em que o sistema for pra produção com Postgres. Resolve o banco de
desenvolvimento sem obrigar o dono a apagar o que já cadastrou pra testar.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def _colunas(conexao, tabela: str) -> set[str]:
    linhas = await conexao.execute(text(f"PRAGMA table_info({tabela})"))
    return {linha[1] for linha in linhas}


async def aplicar(engine: AsyncEngine) -> list[str]:
    """Devolve o que foi aplicado agora — vazio quando não havia nada a fazer."""
    if engine.dialect.name != "sqlite":
        # Postgres é o banco de produção, e lá o esquema é assunto de
        # migração versionada, não deste atalho.
        return []

    feitas: list[str] = []
    async with engine.begin() as conexao:
        if "id_cliente" not in await _colunas(conexao, "despesa_moto"):
            # Nula nas linhas antigas: gasto lançado antes desta coluna
            # existir não tem como ganhar um id retroativo, e o índice único
            # do SQLite aceita vários NULL.
            await conexao.execute(
                text("ALTER TABLE despesa_moto ADD COLUMN id_cliente CHAR(32)")
            )
            await conexao.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_despesa_moto_id_cliente "
                "ON despesa_moto (id_cliente)"
            ))
            feitas.append("despesa_moto.id_cliente (evita lançar o mesmo gasto duas vezes)")

        # O sistema deixou de ter senha: a coluna vira `chave_hash`, e quem
        # já estava no banco ganha uma chave nova (a senha antiga não vira
        # chave — são coisas diferentes, e o hash de bcrypt nem daria).
        colunas_usuario = await _colunas(conexao, "usuario")
        if "senha_hash" in colunas_usuario and "chave_hash" not in colunas_usuario:
            from app.seguranca import gerar_chave, hash_chave

            await conexao.execute(
                text("ALTER TABLE usuario RENAME COLUMN senha_hash TO chave_hash")
            )
            linhas = await conexao.execute(text("SELECT id, nome FROM usuario"))
            for usuario_id, nome in linhas:
                chave = gerar_chave()
                await conexao.execute(
                    text("UPDATE usuario SET chave_hash = :h WHERE id = :i"),
                    {"h": hash_chave(chave), "i": usuario_id},
                )
                feitas.append(f"chave de acesso nova para {nome}: {chave}")
            await conexao.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_usuario_chave_hash "
                "ON usuario (chave_hash)"
            ))

    return feitas
