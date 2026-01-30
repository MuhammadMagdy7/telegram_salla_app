-- Users table to store Telegram info and phone number
CREATE TABLE IF NOT EXISTS users (
    telegram_user_id BIGINT PRIMARY KEY,
    telegram_username TEXT,
    telegram_full_name TEXT,
    phone_number TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT REFERENCES users(telegram_user_id),
    salla_order_id TEXT UNIQUE,
    status TEXT DEFAULT 'active', -- active, expired, cancelled, pending_verification
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    remaining_days INTEGER DEFAULT 30,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Webhook logs for auditing
CREATE TABLE IF NOT EXISTS webhook_logs (
    id SERIAL PRIMARY KEY,
    payload JSONB,
    event_type TEXT,
    status TEXT, -- success, failed, ignored
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Admin users (simple table for the example, usually you might want a hashed password)
CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. جدول الأسهم
CREATE TABLE stocks (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    company_name VARCHAR(150),
    market VARCHAR(50)
);


-- Option Contracts for Reports
CREATE TABLE IF NOT EXISTS option_contracts (
    id SERIAL PRIMARY KEY,
    contract_date DATE NOT NULL,
    strike TEXT NOT NULL,
    contract_price DECIMAL DEFAULT 0,
    profit DECIMAL DEFAULT 0,
    loss DECIMAL DEFAULT 0,
    net_profit DECIMAL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Pending Subscriptions (for users who paid but haven't registered yet)
CREATE TABLE IF NOT EXISTS pending_subscriptions (
    id SERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    salla_order_id TEXT UNIQUE, 
    days INTEGER DEFAULT 30,
    status TEXT DEFAULT 'pending', -- pending, claimed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pending_phone ON pending_subscriptions(phone_number);
