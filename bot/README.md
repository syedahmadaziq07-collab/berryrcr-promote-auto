# Promote Auto by @berryrcr

Bot Telegram untuk auto-promote mesej ke kumpulan yang dipilih pengguna.
Database: **Supabase (PostgreSQL)**

---

## Struktur Projek

```
bot/
├── main.py                      ← Entry point utama
├── config.py                    ← Konfigurasi (baca .env)
├── database.py                  ← Semua operasi DB (async, Supabase)
├── keyboards.py                 ← Semua inline keyboard markup
├── requirements.txt             ← Dependencies Python
├── .env                         ← Environment variables (JANGAN commit)
├── .gitignore
│
├── handlers/
│   ├── __init__.py
│   ├── start.py                 ← /start & menu utama + notif admin
│   ├── wallet.py                ← Wallet & topup syiling
│   ├── subscription.py          ← Beli pelan PLUS/PRO
│   ├── account.py               ← Sambung akaun (OTP + 2FA)
│   ├── groups.py                ← Pilih kumpulan sasaran
│   ├── settings.py              ← Tetapkan mesej & jeda
│   ├── promote.py               ← Mula/henti promote
│   ├── status.py                ← Dashboard status
│   └── help.py                  ← Bantuan & disclaimer
│
├── services/
│   ├── __init__.py
│   ├── supabase_service.py      ← Supabase async client singleton
│   ├── telethon_service.py      ← Login userbot & hantar mesej
│   └── scheduler_service.py    ← Jadual APScheduler
│
├── sessions/                    ← Fail session tambahan
└── media/                       ← Media/gambar
```

---

## Keperluan

- Python 3.10+
- Akaun [Supabase](https://supabase.com) (percuma)
- API ID & API Hash dari [my.telegram.org](https://my.telegram.org)
- Bot Token dari [@BotFather](https://t.me/BotFather)

---

## Pemasangan

### 1. Pasang dependencies

```bash
pip install -r requirements.txt
```

### 2. Isi `.env`

```env
BOT_TOKEN=token_bot_anda_dari_botfather
API_ID=12345678
API_HASH=api_hash_dari_my_telegram_org
ADMIN_ID=id_telegram_anda

SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=your_supabase_anon_or_service_role_key
```

> **Cara dapat SUPABASE_URL & SUPABASE_KEY:**
> 1. Log masuk [supabase.com](https://supabase.com)
> 2. Buat projek baru
> 3. Pergi ke **Settings → API**
> 4. Salin `Project URL` → masukkan sebagai `SUPABASE_URL`
> 5. Salin `service_role` key → masukkan sebagai `SUPABASE_KEY`

### 3. Cipta jadual dalam Supabase

Pergi ke **Supabase Dashboard → SQL Editor** dan jalankan SQL berikut:

```sql
-- USERS
CREATE TABLE users (
  user_id     BIGINT PRIMARY KEY,
  username    TEXT,
  full_name   TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- WALLETS
CREATE TABLE wallets (
  user_id    BIGINT PRIMARY KEY REFERENCES users(user_id),
  balance    INTEGER DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- SUBSCRIPTIONS
CREATE TABLE subscriptions (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT REFERENCES users(user_id),
  plan       TEXT NOT NULL,
  active     BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ
);

-- SESSIONS
CREATE TABLE sessions (
  user_id        BIGINT PRIMARY KEY REFERENCES users(user_id),
  phone_number   TEXT,
  session_string TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- SELECTED GROUPS
CREATE TABLE selected_groups (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT REFERENCES users(user_id),
  group_id       TEXT NOT NULL,
  group_title    TEXT,
  group_username TEXT
);

-- PROMO SETTINGS
CREATE TABLE promo_settings (
  user_id       BIGINT PRIMARY KEY REFERENCES users(user_id),
  message_text  TEXT,
  delay_minutes INTEGER DEFAULT 60,
  is_running    BOOLEAN DEFAULT FALSE,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- TRANSACTIONS
CREATE TABLE transactions (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT REFERENCES users(user_id),
  type        TEXT,
  amount      INTEGER,
  description TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ADMIN LOGS
CREATE TABLE admin_logs (
  id             BIGSERIAL PRIMARY KEY,
  admin_id       BIGINT,
  action         TEXT,
  target_user_id BIGINT,
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- DAILY REPORTS
CREATE TABLE daily_reports (
  report_date         DATE PRIMARY KEY,
  new_users           INTEGER DEFAULT 0,
  total_messages_sent INTEGER DEFAULT 0,
  total_coins_added   INTEGER DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. Jalankan bot

```bash
python main.py
```

---

## Pelan & Harga

| Pelan | Syiling | Harga  | Footer         |
|-------|---------|--------|----------------|
| PLUS  | 300     | RM 3   | Wajib          |
| PRO   | 600     | RM 6   | Boleh tutup    |

### Pakej Topup Syiling

| Syiling | Harga  |
|---------|--------|
| 300     | RM 3   |
| 600     | RM 6   |
| 1200    | RM 12  |

---

## Database Tables

| Jadual           | Keterangan                        |
|------------------|-----------------------------------|
| `users`          | Data pengguna                     |
| `wallets`        | Baki syiling                      |
| `subscriptions`  | Rekod pelan aktif                 |
| `sessions`       | Session string Telethon           |
| `selected_groups`| Kumpulan dipilih pengguna         |
| `promo_settings` | Tetapan mesej & jeda              |
| `transactions`   | Sejarah transaksi syiling         |
| `admin_logs`     | Log tindakan admin                |
| `daily_reports`  | Laporan harian bot                |

---

## Tambah Syiling (Admin)

Gunakan fungsi async dalam Python untuk tambah syiling secara manual:

```python
import asyncio
import database as db

async def topup():
    await db.add_coins(USER_ID, 300, "Topup manual RM3")

asyncio.run(topup())
```

---

## Nota Keselamatan

- Jeda minimum **30 minit** — dikuatkuasakan dalam kod
- Bot hanya menghantar ke **kumpulan yang dipilih pengguna sendiri**
- Session string disimpan dalam Supabase — gunakan **service_role** key & aktifkan RLS
- Penggunaan auto-promote boleh menyebabkan akaun dihadkan oleh Telegram

---

## Sokongan

Hubungi admin: [@berryrcr](https://t.me/berryrcr)
