-- =============================================================================
-- MIGRAÇÃO — PASSO 1: espelho do sistema antigo no PostgreSQL da nuvem
-- =============================================================================
--
-- Rodar uma vez, no banco da nuvem, com o usuário principal. O botão também
-- cria o schema e a tabela de lotes se faltarem; este arquivo é o lugar de
-- criar o usuário restrito (no fim) e deixar as tabelas conhecidas prontas.
--
-- Duas decisões:
--
--   TEXT, e não VARCHAR(n). No PostgreSQL os dois têm o mesmo desempenho, e
--   VARCHAR(n) quebra com "value too long" no primeiro nome maior que o
--   previsto — justo o erro que o espelho existe pra evitar.
--
--   Tabela normal, e não CREATE TEMP TABLE. Tabela TEMP do Postgres some quando
--   a conexão fecha: o passo 2 abriria o banco e não acharia nada. Aqui,
--   "temporária" quer dizer que o schema inteiro sai depois da virada.

CREATE SCHEMA IF NOT EXISTS migracao;

-- Um registro por clique no botão. Cópia nova nunca sobrescreve a anterior:
-- cada uma ganha seu lote, e o passo 2 escolhe de qual ler.
CREATE TABLE IF NOT EXISTS migracao.lotes (
    id            BIGSERIAL   PRIMARY KEY,
    origem        TEXT        NOT NULL,           -- caminho do sistema antigo
    tipo_origem   TEXT        NULL,               -- sqlite, access, firebird, dbf, csv, odbc
    situacao      TEXT        NOT NULL DEFAULT 'RODANDO',  -- RODANDO, CONCLUIDO, COM_ERROS, FALHOU
    iniciado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminado_em  TIMESTAMPTZ NULL,
    tabelas       JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- linhas copiadas e nome original de cada coluna
    erros         JSONB       NOT NULL DEFAULT '[]'::jsonb
);

-- -----------------------------------------------------------------------------
-- As tabelas espelho.
--
-- O código cria uma pra cada tabela do sistema antigo e acrescenta as colunas
-- que ela tiver — inclusive as que ninguém previu. Estas ficam criadas desde já
-- pra o passo 2 poder contar com elas.
--
-- As três colunas com "_" na frente são o controle da migração. Todas as outras
-- vêm do sistema antigo e são TEXT NULL, sem exceção.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS migracao.temp_clientes_antigos (
    -- Sem REFERENCES pra lotes, de propósito: criar tabela com chave estrangeira
    -- tranca `lotes` durante a cópia, e o progresso é gravado lá. Travava.
    _lote_id  BIGINT NOT NULL,  -- número do lote em migracao.lotes
    _linha    BIGINT NOT NULL,  -- posição da linha no sistema antigo
    _origem   TEXT   NOT NULL,  -- nome original da tabela lá
    PRIMARY KEY (_lote_id, _linha)
    -- + as colunas do sistema antigo, acrescentadas na cópia: "nome" TEXT NULL, ...
);

CREATE TABLE IF NOT EXISTS migracao.temp_contratos_antigos (
    _lote_id  BIGINT NOT NULL,
    _linha    BIGINT NOT NULL,
    _origem   TEXT   NOT NULL,
    PRIMARY KEY (_lote_id, _linha)
);

CREATE TABLE IF NOT EXISTS migracao.temp_tickets_antigos (
    _lote_id  BIGINT NOT NULL,
    _linha    BIGINT NOT NULL,
    _origem   TEXT   NOT NULL,
    PRIMARY KEY (_lote_id, _linha)
);

CREATE TABLE IF NOT EXISTS migracao.temp_empresa_antiga (
    _lote_id  BIGINT NOT NULL,
    _linha    BIGINT NOT NULL,
    _origem   TEXT   NOT NULL,
    PRIMARY KEY (_lote_id, _linha)
);

CREATE TABLE IF NOT EXISTS migracao.temp_logs_sistema (
    _lote_id  BIGINT NOT NULL,
    _linha    BIGINT NOT NULL,
    _origem   TEXT   NOT NULL,
    PRIMARY KEY (_lote_id, _linha)
);

-- -----------------------------------------------------------------------------
-- Recomendado: um usuário só da migração.
--
-- A URL do banco vai ficar no computador do cliente. Com o usuário principal,
-- quem pegar aquele computador lê e apaga o sistema novo inteiro. Com este,
-- só enxerga o schema da migração. TROQUE A SENHA antes de rodar.
-- ("railway" é o nome do banco no Railway; troque se for outro.)
-- -----------------------------------------------------------------------------

CREATE ROLE migracao_cliente LOGIN PASSWORD 'TROQUE-POR-UMA-SENHA-LONGA-E-ALEATORIA';
GRANT CONNECT ON DATABASE railway TO migracao_cliente;
GRANT USAGE, CREATE ON SCHEMA migracao TO migracao_cliente;
GRANT SELECT, INSERT, UPDATE ON migracao.lotes TO migracao_cliente;
GRANT USAGE ON SEQUENCE migracao.lotes_id_seq TO migracao_cliente;
-- Acrescentar coluna exige ser dono da tabela.
ALTER TABLE migracao.temp_clientes_antigos  OWNER TO migracao_cliente;
ALTER TABLE migracao.temp_contratos_antigos OWNER TO migracao_cliente;
ALTER TABLE migracao.temp_tickets_antigos   OWNER TO migracao_cliente;
ALTER TABLE migracao.temp_empresa_antiga    OWNER TO migracao_cliente;
ALTER TABLE migracao.temp_logs_sistema      OWNER TO migracao_cliente;
