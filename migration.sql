-- 1. Create the users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Insert the initial user 'Deimos' with password '1130'
INSERT INTO users (username, password_hash)
VALUES ('Deimos', 'pbkdf2:sha256:600000$7518223488cdbabd1260d45e32e3ff13$206528180159325b26919a5bae449930e23d052d6eea30d72bbd01ea1c988e4d')
ON CONFLICT (username) DO NOTHING;

-- 3. Add user_id column to all relevant tables if they don't exist
-- Note: 'cash_accounts' was removed as it uses the 'accounts' table.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE categories ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE cash_transactions ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE debts ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE sub_debts ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE sandboxes ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE sandbox_portfolio ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE sandbox_transactions ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE wishlist ADD COLUMN IF NOT EXISTS user_id INTEGER;
ALTER TABLE budget_settings ADD COLUMN IF NOT EXISTS user_id INTEGER;

-- 4. Assign all existing data to the Deimos user automatically by looking up their ID
UPDATE accounts SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE transactions SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE categories SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE cash_transactions SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE debts SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE persons SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE sub_debts SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE sandboxes SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE sandbox_portfolio SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE sandbox_transactions SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE wishlist SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;
UPDATE budget_settings SET user_id = (SELECT id FROM users WHERE username = 'Deimos') WHERE user_id IS NULL;

-- 5. Add foreign key constraints to enforce referential integrity and cascade deletes
ALTER TABLE accounts DROP CONSTRAINT IF EXISTS fk_accounts_user_id;
ALTER TABLE accounts ADD CONSTRAINT fk_accounts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_transactions_user_id;
ALTER TABLE transactions ADD CONSTRAINT fk_transactions_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE categories DROP CONSTRAINT IF EXISTS fk_categories_user_id;
ALTER TABLE categories ADD CONSTRAINT fk_categories_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE cash_transactions DROP CONSTRAINT IF EXISTS fk_cash_transactions_user_id;
ALTER TABLE cash_transactions ADD CONSTRAINT fk_cash_transactions_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE debts DROP CONSTRAINT IF EXISTS fk_debts_user_id;
ALTER TABLE debts ADD CONSTRAINT fk_debts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE persons DROP CONSTRAINT IF EXISTS fk_persons_user_id;
ALTER TABLE persons ADD CONSTRAINT fk_persons_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE sub_debts DROP CONSTRAINT IF EXISTS fk_sub_debts_user_id;
ALTER TABLE sub_debts ADD CONSTRAINT fk_sub_debts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE sandboxes DROP CONSTRAINT IF EXISTS fk_sandboxes_user_id;
ALTER TABLE sandboxes ADD CONSTRAINT fk_sandboxes_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE sandbox_portfolio DROP CONSTRAINT IF EXISTS fk_sandbox_portfolio_user_id;
ALTER TABLE sandbox_portfolio ADD CONSTRAINT fk_sandbox_portfolio_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE sandbox_transactions DROP CONSTRAINT IF EXISTS fk_sandbox_transactions_user_id;
ALTER TABLE sandbox_transactions ADD CONSTRAINT fk_sandbox_transactions_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE wishlist DROP CONSTRAINT IF EXISTS fk_wishlist_user_id;
ALTER TABLE wishlist ADD CONSTRAINT fk_wishlist_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE budget_settings DROP CONSTRAINT IF EXISTS fk_budget_settings_user_id;
ALTER TABLE budget_settings ADD CONSTRAINT fk_budget_settings_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
