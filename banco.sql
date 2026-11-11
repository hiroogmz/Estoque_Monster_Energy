-- ============================================================================
-- Banco de Dados - Estoque Monster Energy
-- ============================================================================
-- Pré-requisito: execute com um usuário que tenha permissão de administrador.
-- Exemplo no terminal:
--   mysql -u root -p < banco.sql
-- Ou abra no MySQL Workbench e execute o script completo.
-- ============================================================================

-- ---- Banco e usuário de aplicação ------------------------------------------
CREATE DATABASE IF NOT EXISTS estoque
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'estoque'@'localhost' IDENTIFIED BY 'EXPOTECHMONSTER';

GRANT ALL PRIVILEGES ON estoque.* TO 'estoque'@'localhost';
FLUSH PRIVILEGES;

USE estoque;

-- ---- Tabelas ----------------------------------------------------------------

-- Usuários do sistema (contas principais e contribuintes)
CREATE TABLE IF NOT EXISTS usuarios (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    usuario   VARCHAR(50)  NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NOT NULL,
    criado_em DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Movimentações de estoque (entradas e saídas, com sabor registrado)
CREATE TABLE IF NOT EXISTS movimentos (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    tipo      ENUM('entrada','saida') NOT NULL,
    quantidade INT NOT NULL,
    sabor     VARCHAR(120),
    usuario   VARCHAR(50)  NOT NULL,
    criado_em DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_usuario (usuario),
    CONSTRAINT chk_quantidade CHECK (quantidade > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tentativas de login (proteção contra força bruta por IP e por usuário)
CREATE TABLE IF NOT EXISTS tentativas_login (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    usuario   VARCHAR(50) NOT NULL,
    ip        VARCHAR(45) NOT NULL,
    criado_em DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ip      (ip, criado_em),
    INDEX idx_usuario (usuario, criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Vínculo entre conta supervisor (dono) e contribuintes
CREATE TABLE IF NOT EXISTS contribuintes (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    dono         VARCHAR(50) NOT NULL,
    contribuinte VARCHAR(50) NOT NULL UNIQUE,
    criado_em    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dono        (dono),
    INDEX idx_contribuinte (contribuinte)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---- Migração: renomear observacao → sabor (caso o banco já exista) --------
-- Só precisa rodar UMA VEZ se a coluna ainda se chamar 'observacao'.
-- Se já se chama 'sabor', pode ignorar ou comentar as linhas abaixo.

SET @col_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'movimentos'
      AND COLUMN_NAME  = 'observacao'
);

SET @sql = IF(@col_exists > 0,
    'ALTER TABLE movimentos CHANGE observacao sabor VARCHAR(120)',
    'SELECT ''coluna sabor ja existe, nada a fazer'' AS info'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
