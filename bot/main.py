import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError

from config import BOT_TOKEN
from handlers import all_routers
from services import scheduler_service
from services.supabase_service import get_client
from aiogram.fsm.storage.memory import MemoryStorage
from services.subscription_checker import check_expired_subscriptions
from services import expiry_notifier
from services import safe_mode_checker
from services import daily_report_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Suppress noisy conflict warnings — we handle them ourselves
logging.getLogger("aiogram.dispatcher").setLevel(logging.ERROR)


async def aggressive_poll(bot: Bot, dp: Dispatcher):
    """
    Custom polling loop with fast retry on conflict.

    If another instance sends getUpdates first we get a 409 TelegramConflictError.
    We retry after 0.1 s; the other instance uses aiogram's exponential backoff
    (starts at 1 s and grows), so we win the next slot almost every time.
    """
    offset = 0
    allowed_updates = ["message", "callback_query"]
    consecutive_errors = 0

    while True:
        try:
            updates = await bot.get_updates(
                offset=offset,
                timeout=25,
                allowed_updates=allowed_updates,
            )
            consecutive_errors = 0
            for update in updates:
                offset = update.update_id + 1
                asyncio.create_task(dp.feed_update(bot, update))

        except TelegramConflictError:
            consecutive_errors += 1
            if consecutive_errors % 20 == 1:          # log every 20 occurrences
                logger.warning(f"Conflict #{consecutive_errors} — retry dalam 0.1s")
            await asyncio.sleep(0.1)                   # fast retry — we beat their backoff

        except TelegramNetworkError as e:
            logger.warning(f"Network error: {e} — retry dalam 2s")
            await asyncio.sleep(2)

        except asyncio.CancelledError:
            break

        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(2)


async def check_tables():
    """
    Semak semua table kritikal pada startup.
    Cetak SQL migration dalam log jika ada yang hilang.
    """
    client = await get_client()
    issues = []

    # ── Semak topup_requests ──
    try:
        await client.table("topup_requests").select("order_id").limit(1).execute()
        logger.info("Table topup_requests — OK")
    except Exception as e:
        issues.append(f"topup_requests: {e}")

    # ── Semak sessions.userbot_id column (KRITIKAL untuk Log Masuk Token) ──
    try:
        await client.table("sessions").select("userbot_id").limit(1).execute()
        logger.info("Column sessions.userbot_id — OK")
    except Exception as e:
        issues.append(f"sessions.userbot_id COLUMN HILANG: {e}")
        logger.error(
            "=" * 60 + "\n"
            "KRITIKAL: sessions.userbot_id COLUMN TIDAK WUJUD!\n"
            "Log Masuk Token TIDAK akan berfungsi sehingga column ini ditambah.\n"
            "Jalankan SQL berikut dalam Supabase SQL Editor:\n"
            "https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql\n\n"
            "  ALTER TABLE sessions ADD COLUMN IF NOT EXISTS userbot_id   TEXT;\n"
            "  ALTER TABLE sessions ADD COLUMN IF NOT EXISTS tg_username  TEXT;\n"
            "  ALTER TABLE sessions ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;\n\n"
            "Bot akan tetap berjalan — userbots table digunakan sebagai backup lookup.\n"
            + "=" * 60
        )

    # ── Semak userbots table (backup registry) ──
    try:
        await client.table("userbots").select("userbot_id").limit(1).execute()
        logger.info("Table userbots — OK")
    except Exception as e:
        issues.append(f"userbots: {e}")

    # ── Semak subscriptions table (KRITIKAL untuk pelan PLUS/PRO/PREMIUM) ──
    # Semak menggunakan select("user_id,plan") sahaja — column paling asas
    sub_ok = False
    try:
        await client.table("subscriptions").select("user_id,plan").limit(1).execute()
        sub_ok = True
        logger.info("Table subscriptions (user_id,plan) — OK")
    except Exception as e:
        issues.append(f"subscriptions [table]: {e}")

    # Semak column active berasingan — mungkin tidak wujud pada schema lama
    if sub_ok:
        try:
            await client.table("subscriptions").select("active").limit(1).execute()
            logger.info("Table subscriptions (active column) — OK")
        except Exception:
            issues.append("subscriptions [active column]")
            logger.error(
                "=" * 60 + "\n"
                "KRITIKAL: Column 'active' TIADA dalam table subscriptions!\n"
                "Jalankan SQL ini dalam Supabase SQL Editor:\n"
                "https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql\n\n"
                "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS active              BOOLEAN DEFAULT TRUE;\n"
                "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();\n"
                "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS expires_at          TIMESTAMPTZ;\n"
                "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_started_at     TIMESTAMPTZ;\n"
                "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_duration_months INTEGER DEFAULT 1;\n\n"
                "  -- Kemaskini rekod lama supaya active = TRUE\n"
                "  UPDATE subscriptions SET active = TRUE WHERE active IS NULL;\n"
                "  UPDATE subscriptions SET plan_started_at = created_at WHERE plan_started_at IS NULL;\n"
                + "=" * 60
            )
    else:
        logger.error(
            "=" * 60 + "\n"
            "KRITIKAL: Table 'subscriptions' TIDAK WUJUD!\n"
            "Jalankan SQL ini dalam Supabase SQL Editor:\n"
            "https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql\n\n"
            "  CREATE TABLE IF NOT EXISTS subscriptions (\n"
            "    id         BIGSERIAL PRIMARY KEY,\n"
            "    user_id    BIGINT,\n"
            "    plan       TEXT NOT NULL,\n"
            "    active     BOOLEAN DEFAULT TRUE,\n"
            "    created_at TIMESTAMPTZ DEFAULT NOW(),\n"
            "    expires_at TIMESTAMPTZ\n"
            "  );\n"
            + "=" * 60
        )

    # ── Semak wallets table ──
    try:
        await client.table("wallets").select("user_id").limit(1).execute()
        logger.info("Table wallets — OK")
    except Exception as e:
        issues.append(f"wallets: {e}")

    # ── Migration hint — subscription columns ──
    logger.info(
        "=" * 60 + "\n"
        "SQL MIGRATION — jalankan dalam Supabase SQL Editor jika column belum ada:\n"
        "https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql\n\n"
        "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_started_at     TIMESTAMPTZ;\n"
        "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_duration_months INTEGER DEFAULT 1;\n"
        "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS expires_at          TIMESTAMPTZ;\n"
        "  ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS active              BOOLEAN DEFAULT TRUE;\n\n"
        "  ALTER TABLE userbots ADD COLUMN IF NOT EXISTS plan_type TEXT;\n\n"
        "  -- Kemaskini rekod lama\n"
        "  UPDATE subscriptions SET active = TRUE WHERE active IS NULL;\n"
        + "=" * 60
    )

    # ── Semak safe_mode_status table ──
    try:
        await client.table("safe_mode_status").select("id").limit(1).execute()
        logger.info("Table safe_mode_status — OK")
    except Exception as e:
        issues.append(f"safe_mode_status: {e}")
        logger.error(
            "=" * 60 + "\n"
            "KRITIKAL: Table 'safe_mode_status' TIDAK WUJUD!\n"
            "Jalankan SQL ini dalam Supabase SQL Editor:\n"
            "https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql\n\n"
            "  CREATE TABLE IF NOT EXISTS safe_mode_status (\n"
            "    id               BIGSERIAL PRIMARY KEY,\n"
            "    user_id          BIGINT NOT NULL,\n"
            "    userbot_id       VARCHAR(50),\n"
            "    safe_mode_active BOOLEAN DEFAULT FALSE,\n"
            "    original_delay   INTEGER NOT NULL,\n"
            "    safe_delay       INTEGER NOT NULL,\n"
            "    reason           TEXT,\n"
            "    risk_level       VARCHAR(20),\n"
            "    activated_at     TIMESTAMPTZ DEFAULT NOW(),\n"
            "    cooldown_until   TIMESTAMPTZ,\n"
            "    restored_at      TIMESTAMPTZ,\n"
            "    UNIQUE(user_id, userbot_id)\n"
            "  );\n"
            "  CREATE INDEX IF NOT EXISTS idx_safe_mode_active ON safe_mode_status(safe_mode_active);\n"
            "  CREATE INDEX IF NOT EXISTS idx_safe_mode_cooldown ON safe_mode_status(cooldown_until);\n\n"
            "Safe Mode system TIDAK akan berfungsi sehingga table ini dibuat.\n"
            + "=" * 60
        )

    # ── Jika ada isu, cetak SQL penuh ──
    if issues:
        logger.error("=" * 60)
        logger.error("ISU TABLE/COLUMN DITEMUI: %s", issues)
        logger.error("Sila jalankan SQL berikut dalam Supabase SQL Editor:")
        logger.error("https://supabase.com/dashboard/project/ymlofdqtmsfftnuskgbq/sql")
        logger.error("")
        sql_path = os.path.join(os.path.dirname(__file__), "setup_tables.sql")
        if os.path.exists(sql_path):
            with open(sql_path) as f:
                logger.error(f.read())
        logger.error("=" * 60)
    else:
        logger.info("Semua table dan column — OK")


async def main():
    # Baca semula dari os.environ pada waktu runtime —
    # elak isu secrets tidak disuntik semasa import awal
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        # Cuba sekali lagi selepas 2 saat (Replit kadang lambat inject secrets)
        await asyncio.sleep(2)
        token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.error("BOT_TOKEN tidak ditetapkan! Pastikan secret BOT_TOKEN ada dalam Replit Secrets.")
        sys.exit(1)

    logger.info("Menyambung ke Supabase...")
    await get_client()
    logger.info("Supabase bersedia.")

    await check_tables()

    bot = Bot(token=token)
    logger.warning(
        "Using MemoryStorage — FSM state resets on bot restart. "
        "Use Redis for production multi-instance setup."
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    for router in all_routers:
        dp.include_router(router)

    scheduler_service.set_bot(bot)
    scheduler_service.start_scheduler()
    expiry_notifier.set_bot(bot)
    safe_mode_checker.set_bot(bot)
    daily_report_service.set_bot(bot)
    daily_report_service.register_daily_report_job()
    logger.info("Daily report scheduler didaftarkan — trigger: 00:00 Asia/Kuala_Lumpur")
    try:
        await scheduler_service.restore_running_promos()
        logger.info("Scheduler dan promo jobs dipulihkan.")
    except Exception as e:
        logger.warning("restore_running_promos gagal (network/Supabase) — bot tetap berjalan: %s", e)

    asyncio.create_task(check_expired_subscriptions())
    logger.info("Subscription checker dimulakan (semak setiap 1 jam).")
    asyncio.create_task(expiry_notifier.run_expiry_check_loop())
    logger.info("Expiry notifier dimulakan (semak setiap 12 jam).")
    asyncio.create_task(safe_mode_checker.run_safe_mode_restore_loop())
    logger.info("Safe Mode checker dimulakan (semak setiap 15 minit).")

    # Clear webhook so polling can work
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logger.info("=" * 55)
    logger.info("BOT MODE  : polling aktif — webhook dilumpuhkan")
    logger.info("BOT       : @%s (id=%s)", me.username, me.id)
    logger.info("STORAGE   : SQLiteStorage (FSM persistent — fsm_storage.db)")
    logger.info("INSTANCE  : satu — drop_pending_updates=True")
    logger.info("=" * 55)

    try:
        await aggressive_poll(bot, dp)
    finally:
        scheduler_service.scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot dihentikan.")


if __name__ == "__main__":
    asyncio.run(main())
