# Publicar a Carlos Moto na Railway

Passo a passo, do jeito que precisa ser feito na primeira vez. Depois disso,
publicar uma mudança vira um `git push` e mais nada.

Leva uns 15 minutos.

---

## Antes de começar

Você vai precisar de duas contas, as duas de graça:

- **GitHub** — github.com. É onde o código fica guardado.
- **Railway** — railway.app. É quem roda o sistema na internet. Entre com a
  conta do GitHub, assim as duas já ficam ligadas.

> **Sobre dinheiro:** a Railway cobra por uso. Um sistema deste tamanho, com
> um Postgres pequeno, fica na faixa de **US$ 5 a 10 por mês**. O plano
> gratuito dá um crédito inicial que serve pra testar, mas não sustenta um
> sistema ligado o mês inteiro — pra usar de verdade na loja, é o plano pago.

---

## Passo 1 — Mandar o código pro GitHub

Na pasta do projeto, no terminal:

```bash
cd ~/Downloads/geny/carlos-moto

git add .
git commit -m "Carlos Moto: sistema pronto pra publicar"
git push -u origin main
```

O repositório já está configurado
(`github.com/genypereirapereira7-coder/carlos-moto`).

**Deixe o repositório privado.** Ele não tem segredo nenhum dentro — o
`.gitignore` segura o banco, os backups e o arquivo `.env` — mas é o sistema
da sua loja, e não há motivo pra ele ser público.

---

## Passo 2 — Criar o projeto na Railway

1. railway.app → **New Project** → **Deploy from GitHub repo**
2. Escolha o repositório `carlos-moto`
3. Ela começa a montar sozinha. **Vai falhar nesta primeira vez** — falta o
   banco e faltam as variáveis. É esperado, siga em frente.

---

## Passo 3 — Adicionar o banco de dados

No mesmo projeto: **New** → **Database** → **Add PostgreSQL**.

Espere ele ficar verde. Pronto — é o banco onde as motos, os clientes e as
vendas vão morar.

> **Tem que ser no mesmo projeto.** O sistema fala com o banco por um endereço
> interno (`.railway.internal`) que só existe dentro do projeto. Banco em
> outro projeto não é enxergado.

---

## Passo 4 — Ligar o banco ao sistema

Clique no serviço do **sistema** (não no do banco) → aba **Variables**.

**Primeira variável — o banco:**

- **Add Variable** → **Add Reference** → escolha `Postgres` → `DATABASE_URL`

Use o *Add Reference*, não copie a URL na mão. Assim, se a Railway trocar a
senha do banco algum dia, o sistema acompanha sozinho.

**Segunda variável — o segredo dos tokens:**

Gere um, no seu terminal:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o resultado e crie:

- **Nome:** `CARLOSMOTO_JWT_SEGREDO`
- **Valor:** o que saiu do comando

> Este valor é o que assina os crachás de acesso. Quem tiver ele consegue
> entrar como dono da loja. Guarde como você guardaria a chave do cofre — e
> nunca coloque no GitHub.

**Terceira variável — a sua chave de acesso:**

- **Nome:** `CARLOSMOTO_CHAVE_DONO`
- **Valor:** uma chave no formato `ABCD-EFGH-JKMN-PQRS`

Gere uma boa assim:

```bash
cd backend && .venv/bin/python -c "from app.seguranca import gerar_chave; print(gerar_chave())"
```

**Esta variável manda.** Enquanto ela tiver valor, a chave do dono é aquela —
vale pra conta que está nascendo agora e também pra uma que já exista. Coloque
a chave que você quiser usar e é essa que vai abrir o sistema.

Pode colar com traço ou sem, em maiúscula ou minúscula: o sistema entende.

Tecnicamente é opcional — sem ela o sistema sorteia uma e mostra no log. Mas
preencha: assim a chave fica guardada no painel da Railway e você pode ir lá
olhar quando esquecer. Sem ela, se perder o log, fica de fora.

> **O preço disso:** se um dia você trocar a chave pela tela do sistema
> (botão *Chave e aparelhos*), o próximo deploy devolve a da variável. Trocou
> pela tela? Atualize a variável também, ou apague ela.

---

## Passo 5 — Subir

Aba **Deployments** → **Deploy** (ou espere: adicionar variável já dispara).

Acompanhe pelo log. Quando der certo você vê, em letras grandes:

```
  ================================================================
   CONTA DO DONO CRIADA AGORA
  ================================================================
   CHAVE DE ACESSO DE CARLOS

         ABCD-EFGH-JKMN-PQRS

   Digite esta chave uma vez ao abrir o sistema. Depois disso
   aquele aparelho nao pede mais nada.
  ================================================================
```

**Anote essa chave.** O banco guarda só o embaralhado dela — ela não aparece
de novo.

Se faltar alguma variável, o log diz qual e o que fazer, e o sistema não sobe.
É de propósito: melhor não subir do que subir quebrado.

---

## Passo 6 — Abrir o sistema

Aba **Settings** → **Networking** → **Generate Domain**.

Sai um endereço tipo `carlos-moto-production.up.railway.app`. Seu sistema é:

```
https://carlos-moto-production.up.railway.app/dono/
```

Abra, digite a chave de acesso — **uma vez** — e pronto. Aquele computador
não pede mais nada.

### Instalar como aplicativo

Com a tela aberta, clique em **Instalar no computador** no canto. Ele passa a
abrir em janela própria, sem barra de endereço, como qualquer programa. E
continua funcionando sem internet: consulta o que já viu e guarda o que você
cadastrar até a conexão voltar.

Funciona no celular também — mesmo endereço, **Adicionar à tela de início**.

### Domínio próprio (opcional)

Comprou um `carlosmoto.com.br`? **Settings** → **Networking** → **Custom
Domain**. A Railway te dá o que apontar no registro.br e cuida do cadeado
(HTTPS) sozinha.

---

## Do segundo dia em diante

Mudou alguma coisa no sistema:

```bash
git add .
git commit -m "o que mudou"
git push
```

A Railway vê o push e publica sozinha, em uns dois minutos. Se a nova versão
não subir direito, a anterior continua no ar — a conferência de saúde
(`/health`) recusa promover um deploy que não alcança o banco.

> **Mexeu numa tela?** Suba o `VERSAO` no `frontend/dono/sw.js` (hoje `v22`)
> antes do push. É ele que faz o navegador largar a versão antiga — sem isso
> o app fica congelado na anterior, sem dar erro nenhum.

---

## Backup

Isto é o mais importante desta página.

Na Railway: clique no **Postgres** → aba **Backups** → ligue o backup
automático e escolha a frequência (diário serve).

Ligue hoje, não depois. O sistema nunca apaga nada por dentro — o histórico
guarda até o valor que estava ali antes de uma correção — mas isso não protege
contra o banco em si se perder. Backup é a única coisa que protege.

Pra baixar uma cópia na sua máquina, quando quiser:

```bash
pg_dump "COLE_AQUI_A_DATABASE_URL_PUBLICA" > carlosmoto-$(date +%Y%m%d).sql
```

A URL pública está em Postgres → **Variables** → `DATABASE_PUBLIC_URL`.

---

## Quando der problema

### "Chave de acesso inválida", e eu tenho certeza que é essa

Em **Variables**, no serviço do sistema, ponha a chave que você quer em
`CARLOSMOTO_CHAVE_DONO` e espere subir. Pronto — é essa que passa a valer,
mesmo que a conta já existisse com outra.

O log confirma, em letras grandes: **CHAVE TROCADA PELA VARIAVEL**. Se em vez
disso ele disser *"a chave ja e a da variavel"*, então a chave está certa e o
problema é outro — me chame.

Trocar a chave **não desconecta** os aparelhos que já estão pareados. Pra tirar
um aparelho do ar, use o botão **Chave e aparelhos** dentro do sistema.

### O deploy falhou

Leia o log. Os erros que dependem de você saem emoldurados e em português,
dizendo o que fazer. Os dois mais comuns:

- **"NAO DA PRA SUBIR: FALTA CONFIGURACAO"** — faltou uma variável; ele diz
  qual.
- **"NAO DA PRA FALAR COM O BANCO DE DADOS"** — o `DATABASE_URL` não aponta
  pro banco, ou o banco está em outro projeto.

### As telas abrem mas dão erro

Veja `https://SEU-ENDERECO/health`. Se responder `"banco": "indisponivel"`, é
o banco. Se responder `"ok": true`, o problema é outro — me mostre o log.

---

## Duas coisas pra saber antes que apareçam

**1. Não aumente o número de réplicas.** Fica travado em 1 no `railway.json`,
e é de propósito. Duas coisas do sistema vivem na memória do servidor: a
atualização em tempo real das telas e a trava contra chute de chave. Com dois
processos, metade das telas pararia de atualizar sozinha e a trava valeria
metade. Uma loja não precisa de mais de um.

**2. Coluna nova no banco vai precisar de mais cuidado.** Hoje o sistema cria
as tabelas que faltam sozinho, no arranque. Isso resolve o primeiro deploy e
qualquer tabela nova — mas **não** adiciona uma coluna numa tabela que já tem
dados. No dia em que um campo mudar, a ferramenta certa chama-se Alembic, e é
meia hora de trabalho. Não é urgente; é só pra não ser surpresa.

---

## O que está publicado

| | |
|---|---|
| `/dono/` | O painel: motos, clientes, parcelas, financeiro |
| `/health` | Se o sistema está de pé (é o que a Railway consulta) |
| `/docs` | Documentação da API — **fechada em produção**, de propósito |
| `/vendas/` | Ainda não existe. Só o manifesto foi criado; a tela não. |
