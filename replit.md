# CleanBot — Promote Auto by @berryrcr

Bot Telegram untuk auto-promote mesej ke kumpulan yang dipilih pengguna. Menggunakan aiogram 3 + Telethon + Supabase.

## Run & Operate

- Workflow: **Telegram Bot** — `cd bot && python main.py`
- Required secrets: `BOT_TOKEN`, `API_ID`, `API_HASH`, `ADMIN_ID`, `SUPABASE_URL`, `SUPABASE_KEY`

## Stack

- Python 3.11
- aiogram 3.13 — Telegram bot framework
- Telethon 1.36 — Telegram userbot / OTP login
- APScheduler 3.10 — jadual auto-promote
- Supabase (PostgreSQL) — database

## Where things live

- `bot/main.py` — entry point
- `bot/config.py` — konfigurasi dari env vars (Replit Secrets)
- `bot/database.py` — semua operasi Supabase
- `bot/keyboards.py` — semua keyboard markup
- `bot/handlers/` — semua handler aiogram
- `bot/services/` — Supabase client, Telethon service, scheduler
- `bot/sessions/` — fail session Telethon tambahan
- `pyproject.toml` — Python dependencies (uv)

## Architecture decisions

- Polling custom (`aggressive_poll`) untuk menang konflik jika instance lain berjalan
- FSM (MemoryStorage) untuk flow OTP login userbot
- Session string Telethon disimpan dalam Supabase (tidak di fail)
- Semua mesej dalam Bahasa Melayu
- `bot_users` sebagai nama jadual pengguna (bukan `users`) — elak konflik dengan auth.users Supabase

## Product

- **🛒 Kedai** — topup syiling, beli userbot, hantar syiling, leaderboard
- **📚 Buat Userbot** — sambung akaun Telegram via OTP, aktif pelan PLUS/PRO
- **⚙️ Tetapan** — pilih kumpulan, tetapkan mesej & jeda, mula/henti promote
- **🔑 Log Masuk Token** — pindah akses userbot via ID Userbot
- **Admin panel** — tambah syiling, broadcast, lihat statistik

## User preferences

- JANGAN buat web/frontend/API server — ini hanya Telegram bot Python
- Semua mesej dalam Bahasa Melayu
- Jangan print/log maklumat sensitif (OTP, password, session string, token)

## Gotchas

- Jadual dipanggil `bot_users` bukan `users`
- Jadual `userbots` perlu dibuat secara manual (lihat bot/database.py header)
- `sessions` table perlu ada kolum `tg_username`, `userbot_id`, dan `connected_at`
- Conflict warning semasa polling adalah normal jika ada instance lain berjalan
- Secrets diurus melalui Replit Secrets — tiada `.env` file diperlukan

## Supabase Tables Diperlukan

Jalankan SQL ini dalam Supabase SQL Editor:

```sql
CREATE TABLE bot_users (
  id          BIGINT PRIMARY KEY,
  username    TEXT,
  full_name   TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE wallets (
  user_id       BIGINT PRIMARY KEY REFERENCES bot_users(id),
  coins         INTEGER DEFAULT 0,
  total_topup_rm DECIMAL DEFAULT 0
);

CREATE TABLE subscriptions (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT REFERENCES bot_users(id),
  plan       TEXT NOT NULL,
  active     BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sessions (
  user_id        BIGINT PRIMARY KEY REFERENCES bot_users(id),
  phone_number   TEXT,
  session_string TEXT,
  tg_username    TEXT,
  userbot_id     TEXT,
  connected_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE selected_groups (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT REFERENCES bot_users(id),
  group_id       TEXT NOT NULL,
  group_title    TEXT,
  group_username TEXT
);

CREATE TABLE promo_settings (
  user_id       BIGINT PRIMARY KEY REFERENCES bot_users(id),
  message_text  TEXT,
  delay_minutes INTEGER DEFAULT 60,
  is_running    BOOLEAN DEFAULT FALSE
);

CREATE TABLE transactions (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT REFERENCES bot_users(id),
  type        TEXT,
  amount      INTEGER,
  description TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE admin_logs (
  id             BIGSERIAL PRIMARY KEY,
  admin_id       BIGINT,
  action         TEXT,
  target_user_id BIGINT,
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE daily_reports (
  report_date         DATE PRIMARY KEY,
  new_users           INTEGER DEFAULT 0,
  total_messages_sent INTEGER DEFAULT 0,
  total_coins_added   INTEGER DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE userbots (
  id          BIGSERIAL PRIMARY KEY,
  userbot_id  TEXT UNIQUE NOT NULL,
  owner_id    BIGINT REFERENCES bot_users(id),
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  is_active   BOOLEAN DEFAULT TRUE
);

CREATE TABLE topups (
  id               BIGSERIAL PRIMARY KEY,
  user_id          BIGINT REFERENCES bot_users(id),
  package_name     TEXT NOT NULL,
  coins            INTEGER NOT NULL,
  price            DECIMAL(10,2) NOT NULL,
  receipt_file_id  TEXT NOT NULL,
  status           TEXT DEFAULT 'pending',
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  approved_at      TIMESTAMPTZ,
  approved_by      BIGINT
);
```

## Topup Manual Approval Flow

1. User tekan 💳 Topup Syiling → pilih pakej (Reply Keyboard)
2. Bot hantar gambar QR dari `bot/media/qr_payment.jpg` + arahan bayar
3. User upload resit → simpan dalam `topup_requests` (status: pending)
4. Admin terima notifikasi + gambar resit
5. Admin guna `/approve_topup <id>` atau `/reject_topup <id>`
6. User dinotifikasi hasil kelulusan

Admin commands topup:
- `/topup_pending` — senarai semua request pending
- `/approve_topup <id>` — lulus & kredit syiling ke wallet user
- `/reject_topup <id>` — tolak & notify user

**Letak gambar QR di: `bot/media/qr_payment.jpg`**
