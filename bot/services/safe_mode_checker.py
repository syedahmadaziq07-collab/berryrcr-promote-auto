"""
safe_mode_checker.py — Background loop yang semak safe mode cooldown
dan auto-restore delay asal selepas 2 jam.
"""

import asyncio
import logging
import database as db
from utils.safe_mode import is_cooldown_expired

logger = logging.getLogger(__name__)

_bot_instance = None
_scheduler_ref = None


def set_bot(bot):
    global _bot_instance
    _bot_instance = bot


def set_scheduler(sched):
    global _scheduler_ref
    _scheduler_ref = sched


async def _notify(user_id: int, text: str):
    if _bot_instance:
        try:
            await _bot_instance.send_message(user_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.warning("[SAFEMODE] Gagal notify uid=%s: %s", user_id, e)


async def run_safe_mode_restore_loop():
    """
    Loop setiap 15 minit — semak semua safe mode aktif.
    Jika cooldown sudah tamat, restore delay asal dan reschedule job.
    """
    logger.info("[SAFEMODE] Restore loop dimulakan (semak setiap 15 minit)")
    await asyncio.sleep(60)

    while True:
        try:
            records = await db.get_all_active_safe_modes()
            logger.info("[SAFEMODE] Semak %d rekod safe mode aktif", len(records))

            for rec in records:
                user_id       = rec["user_id"]
                original_delay = rec["original_delay"]
                safe_delay     = rec["safe_delay"]
                reason         = rec.get("reason", "")
                cooldown_until = rec.get("cooldown_until")

                if not cooldown_until or not is_cooldown_expired(cooldown_until):
                    continue

                logger.info(
                    "[SAFEMODE] uid=%s cooldown tamat — restore delay %dm → %dm",
                    user_id, safe_delay, original_delay,
                )

                ok = await db.restore_safe_mode(user_id)
                if not ok:
                    logger.warning("[SAFEMODE] uid=%s restore DB gagal", user_id)
                    continue

                if _scheduler_ref:
                    try:
                        from services.scheduler_service import start_promo_job
                        settings = await db.get_promo_settings(user_id)
                        if settings and settings.get("is_running"):
                            start_promo_job(user_id, delay_minutes=original_delay)
                            logger.info(
                                "[SAFEMODE] uid=%s job di-reschedule → %dm (delay asal)",
                                user_id, original_delay,
                            )
                    except Exception as e:
                        logger.warning("[SAFEMODE] uid=%s reschedule gagal: %s", user_id, e)

                await _notify(
                    user_id,
                    f"✅ *Safe Mode Restored!*\n\n"
                    f"Cooldown 2 jam selesai.\n"
                    f"📦 Delay dikembalikan ke: *{original_delay} minit*\n\n"
                    f"⚡ Auto running...",
                )

        except Exception as e:
            logger.error("[SAFEMODE] Restore loop error: %s", e, exc_info=True)

        await asyncio.sleep(15 * 60)
