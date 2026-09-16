# Migração do sistema antigo — PASSO 1

Provisório: sai do sistema depois que o último cliente virar.

Um botão no painel do dono lê o sistema antigo que está no computador do
cliente e copia **tudo** para o schema `migracao` no Postgres da nuvem, como
texto. Nada é interpretado aqui — converter é o passo 2.

## Dois caminhos

**1. O cliente envia o arquivo (funciona da nuvem).** Ele clica no botão,
escolhe o banco do sistema antigo e manda. O navegador não deixa um site
vasculhar o disco, mas deixa a pessoa apontar um arquivo de propósito — e é
essa a diferença. Serve pra quem abre o sistema pelo endereço da internet, sem
instalar nada no computador da loja.

Formatos que o servidor da nuvem abre sozinho: `.db`, `.sqlite`, `.dbf`,
`.csv`, `.txt` e `.zip` (a pasta inteira do sistema antigo, compactada). Até
500 MB.

Access (`.mdb`, `.accdb`) e Firebird (`.fdb`, `.gdb`) **não** — eles precisam
de um driver que só existe na máquina do cliente. A rota recusa com essa
explicação, em vez de aceitar e falhar meia hora depois.

**2. O programa que o cliente executa (`MigrarCarlosMoto.exe`).** Um arquivo
só, dois cliques: procura o sistema antigo no disco, escolhe o mais provável,
manda pra nuvem e mostra o que copiou. Ninguém escolhe arquivo nenhum — é o
mais perto de "clica e clona" que existe, porque **só um programa rodando
naquela máquina pode ler o disco dela**; página de internet nenhuma pode.

O código é `agente.py`. O `.exe` sai da automação
`.github/workflows/clonador-windows.yml` (Actions → "Clonador do sistema
antigo" → Run workflow), porque executável de Windows só se compila no
Windows. O endereço do sistema vai embutido; a chave de acesso não — um `.exe`
com a chave dentro abre o sistema pra quem pegar o arquivo.

### O jeito mais fácil pro cliente: o programa já com a chave

O `MigrarCarlosMoto.exe` sozinho pede a chave. Se você quiser que o cliente
**só abra o programa**, sem digitar nada, ponha um arquivo `chave.txt` ao lado
do `.exe` (mesmo pendrive, mesma pasta) com a chave de acesso dentro. O
programa lê dali.

Ao abrir, ele avisa o que vai fazer e dá 5 segundos pra fechar — ele não roda
escondido; o cliente vê a cópia acontecer. Consentimento é a pessoa ver, não
um formulário.

**Regra de segurança:** gere uma chave só pra isso no painel (Chave e
aparelhos) e revogue-a assim que a migração terminar. A chave num `chave.txt`
abre o sistema pra quem pegar o pendrive — ela tem que morrer logo. E nunca
embuta a chave no próprio `.exe`: o executável passa por gente e por log, o
`chave.txt` você apaga.

**3. O servidor lê o disco direto.** Só quando ele está rodando no computador
onde o sistema antigo está. É o caminho pro Access e pro Firebird, e pra banco
grande demais pra subir pela internet da loja. Sem
`CARLOSMOTO_MIGRACAO_ORIGEM` essa metade some da tela.

## Ligar o caminho 2 (só na máquina do cliente)

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
