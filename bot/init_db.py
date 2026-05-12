"""
init_db.py — Cipta semua jadual Supabase secara automatik menggunakan asyncpg.
Jalankan sekali sebelum boot bot.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")

SQL = """
-- Drop and recreate all bot tables cleanly
-- NOTE: We use bot_users instead of users to avoid conflict with Supabase auth.users

CREATE TABLE IF NOT EXISTS bot_users (
    id          BIGINT PRIMARY KEY,
    username    TEXT,
    full_name   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id    BIGINT PRIMARY KEY REFERENCES bot_users(id) ON DELETE CASCADE,
    balance    INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT REFERENCES bot_users(id) ON DELETE CASCADE,
    plan       TEXT NOT NULL,
    active     BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
    user_id        BIGINT PRIMARY KEY REFERENCES bot_users(id) ON DELETE CASCADE,
    phone_number   TEXT,
    session_string TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS selected_groups (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT REFERENCES bot_users(id) ON DELETE CASCADE,
    group_id       TEXT NOT NULL,
    group_title    TEXT,
    group_username TEXT
);

CREATE TABLE IF NOT EXISTS promo_settings (
    user_id       BIGINT PRIMARY KEY REFERENCES bot_users(id) ON DELETE CASCADE,
    message_text  TEXT,
    delay_minutes INTEGER DEFAULT 60,
    is_running    BOOLEAN DEFAULT FALSE,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES bot_users(id) ON DELETE CASCADE,
    type        TEXT,
    amount      INTEGER,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id             BIGSERIAL PRIMARY KEY,
    admin_id       BIGINT,
    action         TEXT,
    target_user_id BIGINT,
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_reports (
    report_date         DATE PRIMARY KEY,
    new_users           INTEGER DEFAULT 0,
    total_messages_sent INTEGER DEFAULT 0,
    total_coins_added   INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
"""


async def init():
    import asyncpg

    if not DATABASE_URL:
        print("❌ DATABASE_URL tidak ditetapkan! Sila set dalam .env atau Replit Secrets.")
        sys.exit(1)

    print("🔌 Menyambung ke PostgreSQL...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Gagal sambung: {e}")
        sys.exit(1)

    print("🏗️  Mencipta jadual...")
    try:
        await conn.execute(SQL)
        print("✅ Semua jadual berjaya dicipta:")
        print("   - bot_users")
        print("   - wallets")
        print("   - subscriptions")
        print("   - sessions")
        print("   - selected_groups")
        print("   - promo_settings")
        print("   - transactions")
        print("   - admin_logs")
        print("   - daily_reports")
    except Exception as e:
        print(f"❌ Ralat cipta jadual: {e}")
        await conn.close()
        sys.exit(1)
    finally:
        await conn.close()

    print("\n🎉 Database berjaya diinisialisasi. Bot boleh dijalankan.")


if __name__ == "__main__":
    asyncio.run(init())
