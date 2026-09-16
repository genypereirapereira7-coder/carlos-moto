# Migração do sistema antigo — PASSO 1

Provisório: sai do sistema depois que o último cliente virar.

Um botão no painel do dono lê o sistema antigo que está no computador do
cliente e copia **tudo** para o schema `migracao` no Postgres da nuvem, como
texto. Nada é interpretado aqui — converter é o passo 2.

## Onde funciona

Só onde o sistema antigo está. O servidor que atende a rota precisa estar
rodando **naquele computador**: um servidor na nuvem não enxerga o disco de
ninguém, e o navegador tampouco. Na Railway as variáveis abaixo ficam vazias,
a rota responde 409 e o botão nem aparece.

## Ligar (só na máquina do cliente)

```
CARLOSMOTO_MIGRACAO_ORIGEM=C:\SistemaAntigo\dados.mdb
CARLOSMOTO_MIGRACAO_DESTINO=postgresql://migracao_cliente:senha@host:5432/railway?sslmode=require
```

`ORIGEM` aceita `.db/.sqlite`, `.mdb/.accdb` (Access), `.fdb/.gdb` (Firebird),
`.dbf`, `.csv`, uma **pasta** de `.dbf`/`.csv`, ou `odbc:<string de conexão>`.
`DESTINO` vazio = o próprio banco do sistema, se já for Postgres.

Drivers extras, conforme o caso: `pip install pyodbc` (Access),
`firebird-driver` (Firebird), `dbfread` (dBase/Clipper/FoxPro).

## Sem o botão

Serve de plano B, e evita instalar o sistema na loja:

```bash
MIGRACAO_DESTINO="postgresql://..." python backend/app/servicos/migracao.py --origem "C:\SistemaAntigo\dados.mdb"
```

## Antes de ir na loja

`diagnostico-windows.ps1` roda na máquina do cliente e responde de uma vez:
qual é o formato do banco, se os arquivos estão travados, se o driver existe
e de que bitagem, se o Python está lá e se a rede alcança a nuvem. Não copia
nem altera nada.

## O que o espelho guarda

Uma tabela `migracao.temp_<nome>` por tabela antiga, toda coluna `TEXT NULL`,
mais três de controle: `_lote_id` (qual cópia trouxe a linha), `_linha` (a
posição dela no sistema antigo) e `_origem` (o nome original da tabela). O
de-para dos nomes de coluna fica em `migracao.lotes.tabelas`.

Cada clique é um lote novo: nada sobrescreve a cópia anterior.

## Depois da virada

```sql
DROP SCHEMA migracao CASCADE;
DROP ROLE migracao_cliente;
```

O espelho guarda CPF, telefone e endereço em texto puro. Enquanto existir, é
uma segunda cópia dos dados pessoais — não deixe para depois.
