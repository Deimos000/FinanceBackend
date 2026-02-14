-- ============================================================
-- Finance App - Supabase PostgreSQL Schema
-- Run this entire script in the Supabase SQL Editor
-- ============================================================

-- 1. Accounts table (bank accounts + cash account)
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'Bank Account',
    iban TEXT DEFAULT '',
    balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR',
    bank_name TEXT DEFAULT 'Bank',
    type TEXT DEFAULT 'depository',
    subtype TEXT DEFAULT 'checking',
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    booking_date DATE NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    creditor_name TEXT,
    debtor_name TEXT,
    remittance_information TEXT DEFAULT '',
    category TEXT DEFAULT '',
    type TEXT DEFAULT '',
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_booking_date ON transactions(booking_date);

-- 3. Categories table
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    icon TEXT
);

-- Seed default categories
INSERT INTO categories (name, color, icon) VALUES
    ('Groceries', '#FF9800', 'cart'),
    ('Shopping', '#E91E63', 'bag-handle'),
    ('Transport', '#2196F3', 'car'),
    ('Income', '#4CAF50', 'cash'),
    ('Utilities', '#9C27B0', 'flash'),
    ('Entertainment', '#673AB7', 'film'),
    ('Health', '#F44336', 'heart'),
    ('Dining', '#795548', 'restaurant')
ON CONFLICT (name) DO NOTHING;

-- 4. Persons table (people involved in debts)
CREATE TABLE IF NOT EXISTS persons (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Debts table
CREATE TABLE IF NOT EXISTS debts (
    id SERIAL PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('OWED_BY_ME', 'OWED_TO_ME')),
    amount NUMERIC(14,2) NOT NULL,
    currency TEXT DEFAULT 'EUR',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_settled BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_debts_person_id ON debts(person_id);

-- 6. Sub-debts table (partial payments toward a debt)
CREATE TABLE IF NOT EXISTS sub_debts (
    id SERIAL PRIMARY KEY,
    debt_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sub_debts_debt_id ON sub_debts(debt_id);

-- 7. Cash transactions table
CREATE TABLE IF NOT EXISTS cash_transactions (
    id TEXT PRIMARY KEY,
    amount NUMERIC(14,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    name TEXT DEFAULT '',
    description TEXT DEFAULT 'Manual Transaction',
    booking_date TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
