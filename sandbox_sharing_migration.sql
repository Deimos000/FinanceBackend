-- ═══════════════════════════════════════════
-- Friends & Sandbox Sharing Migration
-- Run this in the Supabase SQL Editor
-- ═══════════════════════════════════════════

-- 1. Friendships table
CREATE TABLE IF NOT EXISTS friendships (
    id SERIAL PRIMARY KEY,
    requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    addressee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(requester_id, addressee_id)
);

CREATE INDEX IF NOT EXISTS idx_friendships_requester ON friendships(requester_id);
CREATE INDEX IF NOT EXISTS idx_friendships_addressee ON friendships(addressee_id);

-- 2. Sandbox Shares table
CREATE TABLE IF NOT EXISTS sandbox_shares (
    id SERIAL PRIMARY KEY,
    sandbox_id INTEGER NOT NULL REFERENCES sandboxes(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_with_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT NOT NULL DEFAULT 'watch' CHECK (permission IN ('watch', 'edit')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sandbox_id, shared_with_id)
);

CREATE INDEX IF NOT EXISTS idx_sandbox_shares_sandbox ON sandbox_shares(sandbox_id);
CREATE INDEX IF NOT EXISTS idx_sandbox_shares_shared_with ON sandbox_shares(shared_with_id);
