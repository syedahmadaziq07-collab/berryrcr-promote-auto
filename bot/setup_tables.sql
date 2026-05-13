-- ============================================================
-- SETUP SQL — Jalankan sekali dalam Supabase SQL Editor
-- URL: https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql
-- ============================================================

-- TABLE: bot_users
CREATE TABLE IF NOT EXISTS bot_users (
    id          BIGINT PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE: wallets
CREATE TABLE IF NOT EXISTS wallets (
    user_id        BIGINT PRIMARY KEY,
    coins          INTEGER DEFAULT 0,
    total_topup_rm NUMERIC DEFAULT 0,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE: subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT,
    plan       TEXT NOT NULL,
    active     BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- MIGRATION: Tambah column hilang jika table sudah wujud dengan schema lama
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS active     BOOLEAN DEFAULT TRUE;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
-- Kemaskini rekod lama yang tiada nilai active
UPDATE subscriptions SET active = TRUE WHERE active IS NULL;

-- TABLE: sessions
-- PENTING: Pastikan column userbot_id, tg_username, connected_at wujud!
CREATE TABLE IF NOT EXISTS sessions (
    user_id        BIGINT PRIMARY KEY,
    phone_number   TEXT,
    session_string TEXT,
    tg_username    TEXT,
    userbot_id     TEXT,
    connected_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- MIGRATION: Tambah column ke sessions table jika belum ada
-- (Selamat dijalankan walaupun column sudah wujud)
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS userbot_id   TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS tg_username  TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;

-- TABLE: selected_groups
CREATE TABLE IF NOT EXISTS selected_groups (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT,
    group_id       TEXT NOT NULL,
    group_title    TEXT,
    group_username TEXT
);

-- TABLE: promo_settings
CREATE TABLE IF NOT EXISTS promo_settings (
    user_id       BIGINT PRIMARY KEY,
    message_text  TEXT,
    delay_minutes INTEGER DEFAULT 60,
    is_running    BOOLEAN DEFAULT FALSE,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE: transactions
CREATE TABLE IF NOT EXISTS transactions (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     BIGINT,
    type        TEXT,
    amount      INTEGER,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE: admin_logs
CREATE TABLE IF NOT EXISTS admin_logs (
    id             BIGSERIAL PRIMARY KEY,
    admin_id       BIGINT,
    action         TEXT,
    target_user_id BIGINT,
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE: daily_reports
CREATE TABLE IF NOT EXISTS daily_reports (
    report_date         DATE PRIMARY KEY,
    new_users           INTEGER DEFAULT 0,
    total_messages_sent INTEGER DEFAULT 0,
    total_coins_added   INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE: userbots (KRITIKAL — backup registry untuk Log Masuk Token)
CREATE TABLE IF NOT EXISTS userbots (
    id         BIGSERIAL PRIMARY KEY,
    userbot_id TEXT UNIQUE NOT NULL,
    owner_id   BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active  BOOLEAN DEFAULT TRUE
);

-- INDEX untuk carian pantas userbots
CREATE INDEX IF NOT EXISTS idx_userbots_owner_id   ON userbots(owner_id);
CREATE INDEX IF NOT EXISTS idx_userbots_userbot_id ON userbots(userbot_id);
CREATE INDEX IF NOT EXISTS idx_sessions_userbot_id ON sessions(userbot_id);

-- TABLE: topup_requests
CREATE TABLE IF NOT EXISTS topup_requests (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    order_id         TEXT UNIQUE NOT NULL,
    user_id          BIGINT NOT NULL,
    username         TEXT,
    coins            INTEGER NOT NULL,
    amount_rm        NUMERIC NOT NULL,
    receipt_file_id  TEXT,
    status           TEXT DEFAULT 'pending',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    approved_at      TIMESTAMPTZ,
    approved_by      BIGINT
);

-- INDEX untuk carian pantas
CREATE INDEX IF NOT EXISTS idx_topup_requests_user_id  ON topup_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_topup_requests_status   ON topup_requests(status);
CREATE INDEX IF NOT EXISTS idx_topup_requests_order_id ON topup_requests(order_id);

-- ============================================================
-- SELESAI — Semua table dan column berjaya dicipta/dikemaskini
-- ============================================================
