-- Migration Script: Add entry/exit market data columns to option_contracts
-- Run this in your PostgreSQL database

-- Entry data (captured when contract is first logged)
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_bid DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_ask DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_underlying DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_volume INTEGER;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_oi INTEGER;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_iv DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Exit data (captured when contract is closed)
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_bid DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_ask DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_underlying DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_volume INTEGER;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_oi INTEGER;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_iv DECIMAL;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS exit_timestamp TIMESTAMP WITH TIME ZONE;
