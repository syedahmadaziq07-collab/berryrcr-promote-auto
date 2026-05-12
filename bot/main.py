import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import all_routers
from services import scheduler_service
from services.supabase_service import get_client

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
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN tidak ditetapkan!")
        sys.exit(1)

    logger.info("Menyambung ke Supabase...")
    await get_client()
    logger.info("Supabase bersedia.")

    await check_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    for router in all_routers:
        dp.include_router(router)

    scheduler_service.set_bot(bot)
    scheduler_service.start_scheduler()
    await scheduler_service.restore_running_promos()
    logger.info("Scheduler dan promo jobs dipulihkan.")

    # Clear webhook so polling can work
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logger.info(f"Bot aktif: @{me.username} (id={me.id}) — polling bermula")

    try:
        await aggressive_poll(bot, dp)
    finally:
        scheduler_service.scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot dihentikan.")


if __name__ == "__main__":
    asyncio.run(main())
