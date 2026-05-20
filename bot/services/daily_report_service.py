"""
services/daily_report_service.py — Auto daily admin report setiap hari pukul 00:00 MYT.

Trigger: CronTrigger(hour=0, minute=0, timezone='Asia/Kuala_Lumpur') pada scheduler sedia ada.
Report dihantar kepada ADMIN_ID sahaja — TIDAK kepada customer.
Job ID: 'daily_admin_report' — replace_existing=True menghalang duplikat semasa bot restart.
"""

import logging
from datetime import datetime, timezone, timedelta

import pytz
from aiogram import Bot

import database as db
from config import ADMIN_ID

logger = logging.getLogger(__name__)

_MY_TZ = pytz.timezone("Asia/Kuala_Lumpur")
_bot: Bot | None = None


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


def register_daily_report_job() -> None:
    """
    Daftar CronTrigger job pada scheduler sedia ada (dari scheduler_service).
    Mesti dipanggil SELEPAS scheduler_service.start_scheduler().
    replace_existing=True — selamat dipanggil semula semasa restart.
    """
    from services.scheduler_service import scheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        _scheduled_daily_report,
        trigger=CronTrigger(hour=0, minute=0, timezone=_MY_TZ),
        id="daily_admin_report",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(
        "[DAILY_REPORT] Job berjaya didaftarkan — trigger: 00:00 Asia/Kuala_Lumpur setiap hari"
    )


async def _scheduled_daily_report() -> None:
    """Dipanggil oleh APScheduler setiap hari 00:00 MYT. Hantar report untuk semalam."""
    now_my = datetime.now(_MY_TZ)
    # Hantar report untuk SEMALAM (hari yang baru sahaja tamat pada midnight)
    yesterday = (now_my - timedelta(days=1)).strftime("%Y-%m-%d")
    logger.info("[DAILY_REPORT] daily_report_started | date=%s", yesterday)
    await run_daily_report(target_date=yesterday)


async def run_daily_report(target_date: str | None = None) -> None:
    """
    Jana dan hantar daily report kepada ADMIN_ID.

    Args:
        target_date: "YYYY-MM-DD" dalam timezone MY. Default = semalam.
                     Untuk /daily_report manual, admin boleh pass tarikh hari ini atau mana-mana.
    """
    if _bot is None:
        logger.error("[DAILY_REPORT] bot belum diset — panggil set_bot() dulu")
        return

    if not ADMIN_ID:
        logger.warning("[DAILY_REPORT] ADMIN_ID tidak dikonfigurasi — skip")
        return

    if target_date is None:
        now_my = datetime.now(_MY_TZ)
        target_date = (now_my - timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("[DAILY_REPORT] daily_report_started | target_date=%s", target_date)

    try:
        new_users_count = await db.get_new_users_count_for_date(target_date)
        approved_orders = await db.get_approved_orders_for_date(target_date)
    except Exception as e:
        logger.error("[DAILY_REPORT] daily_report_failed | target_date=%s | error=%s", target_date, e)
        try:
            await _bot.send_message(
                ADMIN_ID,
                f"⚠️ <b>Daily Report Gagal</b>\n\nDate: <code>{target_date}</code>\nError: <code>{str(e)[:200]}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    completed_count = len(approved_orders)

    if completed_count == 0:
        logger.info("[DAILY_REPORT] daily_report_no_orders | target_date=%s | new_users=%d", target_date, new_users_count)

    text = _build_report_text(target_date, new_users_count, approved_orders)

    try:
        await _bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        logger.info(
            "[DAILY_REPORT] daily_report_sent | date=%s | new_users=%d | completed_orders=%d",
            target_date, new_users_count, completed_count,
        )
    except Exception as e:
        logger.error(
            "[DAILY_REPORT] daily_report_failed (send) | date=%s | error=%s",
            target_date, e,
        )


def _build_report_text(date_str: str, new_users: int, orders: list) -> str:
    """Format teks report dalam HTML."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%d/%m/%Y")
    except Exception:
        date_display = date_str

    completed_count = len(orders)

    lines = [
        "📊 <b>Daily Sales Report</b>",
        f"Date: {date_display}",
        "━━━━━━━━━━━━━━━━━━",
        f"Total Orders Completed: <b>{completed_count}</b>",
        f"Total New Users: <b>{new_users}</b>",
        "",
    ]

    if not orders:
        lines.append("No completed orders.")
    else:
        for order in orders:
            amount = order.get("amount_rm") or 0.0
            coins  = order.get("coins") or 0
            uname  = order.get("username") or ""
            uid    = order.get("user_id") or ""

            if uname:
                who = f"@{uname}"
            else:
                who = str(uid)

            item = f"{coins:,} Syiling Reload" if coins else "Reload Syiling"
            lines.append(f"• RM{float(amount):.2f} — {item} — {who}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "<i>This report is sent to admin only</i>",
    ]

    return "\n".join(lines)
