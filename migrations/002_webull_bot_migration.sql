-- Migration Script: Extend option_contracts table for Webull Bot monitoring
-- Run this in your PostgreSQL database

-- Add new columns for monitoring functionality
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS symbol VARCHAR(20);
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS contract_type VARCHAR(1);
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS expiration DATE;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS chat_id BIGINT;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS target_price DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_price DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS notification_mode VARCHAR(20) DEFAULT 'always';
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS contract_oid TEXT;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_option_contracts_status ON option_contracts(status);
CREATE INDEX IF NOT EXISTS idx_option_contracts_chat_id ON option_contracts(chat_id);
CREATE INDEX IF NOT EXISTS idx_option_contracts_symbol ON option_contracts(symbol);

-- Add monitoring_commands table as backup/alternative (mirrors SQLite structure)
CREATE TABLE IF NOT EXISTS monitoring_commands (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    strike DECIMAL NOT NULL,
    contract_type VARCHAR(1) NOT NULL,
    expiration DATE NOT NULL,
    target_price DECIMAL,
    entry_price DECIMAL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    contract_id TEXT,
    notification_mode VARCHAR(20) DEFAULT 'always',
    postgres_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_monitoring_commands_status ON monitoring_commands(status);
CREATE INDEX IF NOT EXISTS idx_monitoring_commands_chat_id ON monitoring_commands(chat_id);
