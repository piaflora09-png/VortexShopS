import asyncpg


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS users (
    discord_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    avatar TEXT,
    is_owner BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    csrf_token TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS verification_records (
    id BIGSERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES users(discord_id),
    guild_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','verified','failed')),
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS moderation_cases (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS security_events (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    user_id BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS access_keys (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT UNIQUE NOT NULL,
    duration_hours INTEGER NOT NULL CHECK (duration_hours > 0),
    max_uses INTEGER NOT NULL DEFAULT 1 CHECK (max_uses > 0),
    uses INTEGER NOT NULL DEFAULT 0,
    created_by BIGINT NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES users(discord_id),
    access_key_id BIGINT REFERENCES access_keys(id),
    starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS tickets (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT UNIQUE,
    user_id BIGINT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    assigned_staff_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS ticket_panel_settings (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    title TEXT NOT NULL DEFAULT 'Vortex Support',
    description TEXT NOT NULL DEFAULT 'Choose a category below to open a private support ticket.',
    categories TEXT[] NOT NULL DEFAULT ARRAY['General Support','Report a User','Billing'],
    panel_channel_id BIGINT,
    panel_message_id BIGINT,
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO ticket_panel_settings(id) VALUES(1) ON CONFLICT (id) DO NOTHING;
CREATE TABLE IF NOT EXISTS ticket_messages (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS campaigns (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    channel_ids BIGINT[] NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    scheduled_at TIMESTAMPTZ,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS campaign_deliveries (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS giveaways (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    prize_type TEXT NOT NULL,
    prize TEXT NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    winner_id BIGINT,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id BIGINT NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (giveaway_id, user_id)
);
CREATE TABLE IF NOT EXISTS middleman_requests (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    requester_id BIGINT NOT NULL,
    middleman_id BIGINT,
    status TEXT NOT NULL DEFAULT 'open',
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS vouches (
    id BIGSERIAL PRIMARY KEY,
    middleman_id BIGINT NOT NULL,
    author_id BIGINT NOT NULL,
    trade_id BIGINT,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS disputes (
    id BIGSERIAL PRIMARY KEY,
    trade_id BIGINT NOT NULL,
    reporter_id BIGINT NOT NULL,
    details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL,
    description TEXT,
    recorded_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS staff_activity (
    id BIGSERIAL PRIMARY KEY,
    staff_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT,
    action TEXT NOT NULL,
    resource TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moderation_cases_user ON moderation_cases(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at DESC);
"""


async def initialize_database(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
    async with pool.acquire() as connection:
        await connection.execute(SCHEMA)
    return pool
