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
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS active              BOOLEAN DEFAULT TRUE;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS expires_at          TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_started_at     TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_duration_months INTEGER DEFAULT 1;
-- Kemaskini rekod lama yang tiada nilai active
UPDATE subscriptions SET active = TRUE WHERE active IS NULL;
-- Backfill plan_started_at untuk rekod lama (guna created_at jika kosong)
UPDATE subscriptions SET plan_started_at = created_at WHERE plan_started_at IS NULL;

-- TABLE: sessions
CREATE TABLE IF NOT EXISTS sessions (
    user_id        BIGINT PRIMARY KEY,
    phone_number   TEXT,
    session_string TEXT,
    tg_username    TEXT,
    userbot_id     TEXT,
    connected_at   TIMESTAMPTZ,
    backup_email   TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- MIGRATION: Tambah column ke sessions table jika belum ada
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS userbot_id   TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS tg_username  TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS backup_email TEXT;

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
    notif_aktif   BOOLEAN DEFAULT TRUE,
    expert_mode   BOOLEAN DEFAULT FALSE,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- MIGRATION: Tambah column baru ke promo_settings
ALTER TABLE promo_settings ADD COLUMN IF NOT EXISTS notif_aktif BOOLEAN DEFAULT TRUE;
ALTER TABLE promo_settings ADD COLUMN IF NOT EXISTS expert_mode BOOLEAN DEFAULT FALSE;

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

-- INDEX untuk carian pantas topup_requests
CREATE INDEX IF NOT EXISTS idx_topup_requests_user_id  ON topup_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_topup_requests_status   ON topup_requests(status);
CREATE INDEX IF NOT EXISTS idx_topup_requests_order_id ON topup_requests(order_id);

-- ─────────────────────────────────────────────
-- JADUAL BARU — Features tambahan
-- ─────────────────────────────────────────────

-- TABLE: broadcast_messages (senarai mesej sebarkan)
CREATE TABLE IF NOT EXISTS broadcast_messages (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    userbot_id   TEXT NOT NULL,
    user_id      BIGINT NOT NULL,
    content_type TEXT NOT NULL,
    text_content TEXT,
    file_id      TEXT,
    urutan       INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_broadcast_userbot ON broadcast_messages(userbot_id);

-- TABLE: autoreply_channels (saluran balas auto)
CREATE TABLE IF NOT EXISTS autoreply_channels (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    userbot_id   TEXT NOT NULL,
    user_id      BIGINT NOT NULL,
    channel_id   TEXT NOT NULL,
    channel_name TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (userbot_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_autoreply_channels_userbot ON autoreply_channels(userbot_id);

-- TABLE: autoreply_texts (teks balas auto)
CREATE TABLE IF NOT EXISTS autoreply_texts (
    id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    userbot_id TEXT NOT NULL,
    user_id    BIGINT NOT NULL,
    teks       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_autoreply_texts_userbot ON autoreply_texts(userbot_id);

-- TABLE: schedules (jadual aktif promote)
CREATE TABLE IF NOT EXISTS schedules (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    userbot_id  TEXT UNIQUE NOT NULL,
    user_id     BIGINT NOT NULL,
    waktu_mula  TIME NOT NULL,
    waktu_tamat TIME NOT NULL,
    aktif       BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_schedules_userbot ON schedules(userbot_id);

-- TABLE: referrals (kod rujukan)
CREATE TABLE IF NOT EXISTS referrals (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    referrer_id BIGINT NOT NULL,
    referred_id BIGINT NOT NULL UNIQUE,
    ref_code    TEXT NOT NULL,
    coins_given INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);

-- TABLE: group_messages (mesej khusus per kumpulan — Mod Lanjutan)
CREATE TABLE IF NOT EXISTS group_messages (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    group_id     TEXT NOT NULL,
    message_text TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_group_messages_user ON group_messages(user_id);

-- ─────────────────────────────────────────────
-- FUNGSI RPC ATOM UNTUK WALLET
-- Elak race condition pada add_coins / deduct_coins
-- Jalankan ini supaya operasi wallet adalah selamat
-- ─────────────────────────────────────────────

CREATE OR REPLACE FUNCTION add_coins(
    p_user_id BIGINT,
    p_amount  INTEGER
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO wallets (user_id, coins)
    VALUES (p_user_id, p_amount)
    ON CONFLICT (user_id)
    DO UPDATE SET coins = wallets.coins + p_amount;
END;
$$;

CREATE OR REPLACE FUNCTION deduct_coins(
    p_user_id BIGINT,
    p_amount  INTEGER
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE wallets
    SET    coins = coins - p_amount
    WHERE  user_id = p_user_id
    AND    coins >= p_amount;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Baki tidak mencukupi';
    END IF;
END;
$$;

-- ─────────────────────────────────────────────
-- RPC: transfer_coins (atomic, elak race condition)
-- Guna p_from_user_id, p_to_user_id, p_amount, p_description
-- ─────────────────────────────────────────────

CREATE OR REPLACE FUNCTION transfer_coins(
    p_from_user_id BIGINT,
    p_to_user_id   BIGINT,
    p_amount       INTEGER,
    p_description  TEXT DEFAULT 'Transfer'
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_from_coins INTEGER;
BEGIN
    -- Lock baris sender dan semak baki
    SELECT coins INTO v_from_coins
    FROM wallets
    WHERE user_id = p_from_user_id
    FOR UPDATE;

    IF v_from_coins IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'Wallet penghantar tidak dijumpai');
    END IF;

    IF v_from_coins < p_amount THEN
        RETURN jsonb_build_object('success', false, 'error', 'Baki tidak mencukupi');
    END IF;

    -- Tolak dari penghantar
    UPDATE wallets SET coins = coins - p_amount WHERE user_id = p_from_user_id;

    -- Tambah ke penerima (upsert supaya wallet penerima dicipta jika belum wujud)
    INSERT INTO wallets (user_id, coins)
    VALUES (p_to_user_id, p_amount)
    ON CONFLICT (user_id)
    DO UPDATE SET coins = wallets.coins + p_amount;

    -- Log kedua-dua belah
    INSERT INTO transactions (user_id, type, amount, description)
    VALUES
        (p_from_user_id, 'debit',  p_amount, 'Hantar ke ' || p_to_user_id || ' — ' || p_description),
        (p_to_user_id,   'credit', p_amount, 'Terima dari ' || p_from_user_id || ' — ' || p_description);

    RETURN jsonb_build_object('success', true);

EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'error', SQLERRM);
END;
$$;

-- ============================================================
-- SELESAI — Semua table, column, index dan fungsi RPC
-- telah berjaya dicipta / dikemaskini
-- ============================================================
