-- Migration: Update option_contracts table for enhanced reports
-- Date: 2026-03-05

-- Add new columns to option_contracts
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS symbol VARCHAR(30);
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS contract_type VARCHAR(10); -- PUT or CALL
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS entry_price DECIMAL DEFAULT 0;
ALTER TABLE option_contracts ADD COLUMN IF NOT EXISTS highest_price DECIMAL DEFAULT 0;

-- Update existing records: extract symbol and type from strike column if possible
-- Example: if strike is "MSTR 119.0 P", extract symbol=MSTR, type=PUT

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_option_contracts_date ON option_contracts(contract_date DESC);
CREATE INDEX IF NOT EXISTS idx_option_contracts_type ON option_contracts(contract_type);

-- Optional: Update strike column format for existing data
COMMENT ON COLUMN option_contracts.symbol IS 'Stock/ETF symbol (e.g., MSTR, NVDA, TSLA, SPX)';
COMMENT ON COLUMN option_contracts.contract_type IS 'Option type: CALL or PUT';
COMMENT ON COLUMN option_contracts.entry_price IS 'Entry price of the contract';
COMMENT ON COLUMN option_contracts.highest_price IS 'Highest price reached';
