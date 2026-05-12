import asyncio
import logging
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


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN tidak ditetapkan!")
        sys.exit(1)

    logger.info("Menyambung ke Supabase...")
    await get_client()
    logger.info("Supabase bersedia.")

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
