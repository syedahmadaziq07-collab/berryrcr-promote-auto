"""
services/expiry_notifier.py — Auto-notify users before subscription expires.

Runs every 12 hours. Sends warnings at:
  - 3 days before expiry  → "3_days"
  - 1 day before expiry   → "1_day"
  - On expiry day (day 0) → "expired"

Tracks sent notifications in expiry_notifications table to avoid duplicate sends.

SQL to create tracking table (run once in Supabase SQL Editor):
  CREATE TABLE IF NOT EXISTS expiry_notifications (
      id                BIGSERIAL PRIMARY KEY,
      user_id           BIGINT    NOT NULL,
      notification_type TEXT      NOT NULL,
      cycle_key         TEXT      NOT NULL,
      sent_at           TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE (user_id, notification_type, cycle_key)
  );
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

_MY_TZ = timezone(timedelta(hours=8))
_bot: Bot | None = None

THRESHOLDS = [
    ("3_days",  3),
    ("1_day",   1),
    ("expired", 0),
]

PLAN_ICON   = {"PLUS": "⚡ PLUS", "PRO": "👑 PRO", "PREMIUM": "💎 PREMIUM"}
PLAN_COINS  = {"PLUS": 300, "PRO": 600, "PREMIUM": 1000}


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


def renew_plan_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Renew Plan Sekarang", callback_data="goto_kedai_renew")],
    ])


def _build_message(notif_type: str, plan: str, expires_str: str, days_left: int, balance: int) -> str:
    icon           = PLAN_ICON.get(plan, plan)
    renew_cost     = PLAN_COINS.get(plan, 300)
    enough         = "✅ Cukup" if balance >= renew_cost else f"❌ Kurang {renew_cost - balance:,} syiling"

    if notif_type == "3_days":
        header  = "⚠️ *REMINDER — PLAN HAMPIR TAMAT*"
        baki    = f"*{days_left} hari*"
    elif notif_type == "1_day":
        header  = "🚨 *URGENT — PLAN TAMAT ESOK!*"
        baki    = "*1 hari (ESOK!)*"
    else:
        header  = "❌ *PLAN ANDA TELAH TAMAT*"
        baki    = "*Tamat hari ini*"

    return (
        f"{header}\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📦 Plan anda: {icon}\n"
        f"📅 Tamat pada: *{expires_str}*\n"
        f"⏳ Baki masa: {baki}\n\n"
        f"💰 Wallet: *{balance:,} Syiling*\n"
        f"🔄 Kos renew: *{renew_cost:,} Syiling* — {enough}\n\n"
        "Renew sekarang untuk elak gangguan! 👇"
    )


async def _was_notified(client, user_id: int, notif_type: str, cycle_key: str) -> bool:
    """Return True if this notification was already sent for this subscription cycle."""
    try:
        res = (
            await client.table("expiry_notifications")
            .select("id")
            .eq("user_id", user_id)
            .eq("notification_type", notif_type)
            .eq("cycle_key", cycle_key)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


async def _mark_notified(client, user_id: int, notif_type: str, cycle_key: str) -> None:
    try:
        await (
            client.table("expiry_notifications")
            .insert({
                "user_id":           user_id,
                "notification_type": notif_type,
                "cycle_key":         cycle_key,
                "sent_at":           datetime.now(_MY_TZ).isoformat(),
            })
            .execute()
        )
    except Exception as e:
        logger.warning(
            "expiry_notifier: gagal simpan record uid=%s type=%s — %s",
            user_id, notif_type, e,
        )


async def run_single_check() -> dict:
    """
    Run one full expiry-notification pass.
    Returns stats dict: {checked, sent, skipped, errors}.
    Safe to call manually (admin command) or from loop.
    """
    from services.supabase_service import get_client
    import database as db

    stats = {"checked": 0, "sent": 0, "skipped": 0, "errors": 0}

    if _bot is None:
        logger.error("expiry_notifier: bot belum diset — panggil set_bot() dulu")
        return stats

    try:
        client = await get_client()
        now_my = datetime.now(_MY_TZ)

        res = (
            await client.table("subscriptions")
            .select("user_id, plan, expires_at")
            .eq("active", True)
            .not_.is_("expires_at", "null")
            .execute()
        )

        subs = res.data or []
        stats["checked"] = len(subs)
        logger.info("expiry_notifier: semak %d subscription aktif", len(subs))

        for sub in subs:
            user_id = sub["user_id"]
            plan    = sub.get("plan", "PLUS")
            raw_exp = sub.get("expires_at", "")

            try:
                exp_dt = datetime.fromisoformat(
                    str(raw_exp).replace("Z", "+00:00")
                ).astimezone(_MY_TZ)
            except Exception:
                stats["skipped"] += 1
                continue

            days_left   = (exp_dt.date() - now_my.date()).days
            expires_str = exp_dt.strftime("%d %b %Y")
            cycle_key   = exp_dt.strftime("%Y-%m-%d")

            for notif_type, threshold in THRESHOLDS:
                if days_left != threshold:
                    continue

                already_sent = await _was_notified(client, user_id, notif_type, cycle_key)
                if already_sent:
                    logger.debug(
                        "expiry_notifier: skip uid=%s type=%s cycle=%s (sudah dihantar)",
                        user_id, notif_type, cycle_key,
                    )
                    stats["skipped"] += 1
                    continue

                balance = await db.get_wallet(user_id)
                text    = _build_message(notif_type, plan, expires_str, days_left, balance)

                try:
                    await _bot.send_message(
                        user_id,
                        text,
                        parse_mode="Markdown",
                        reply_markup=renew_plan_kb(),
                    )
                    await _mark_notified(client, user_id, notif_type, cycle_key)
                    stats["sent"] += 1
                    logger.info(
                        "expiry_notifier: ✅ hantar %s | uid=%s | plan=%s | tamat=%s | "
                        "days_left=%d | wallet=%d",
                        notif_type, user_id, plan, expires_str, days_left, balance,
                    )
                    if balance < PLAN_COINS.get(plan, 300):
                        logger.warning(
                            "expiry_notifier: ⚠️ uid=%s wallet TIDAK CUKUP untuk renew "
                            "(%d / %d syiling diperlukan)",
                            user_id, balance, PLAN_COINS.get(plan, 300),
                        )
                except Exception as send_err:
                    stats["errors"] += 1
                    logger.error(
                        "expiry_notifier: gagal hantar ke uid=%s: %s",
                        user_id, send_err,
                    )

    except Exception as e:
        stats["errors"] += 1
        logger.error("expiry_notifier: ralat semasa check: %s", e)

    logger.info(
        "expiry_notifier: selesai — checked=%d sent=%d skipped=%d errors=%d",
        stats["checked"], stats["sent"], stats["skipped"], stats["errors"],
    )
    return stats


async def run_expiry_check_loop() -> None:
    """Background asyncio loop — runs run_single_check() every 12 hours."""
    logger.info("expiry_notifier: loop dimulakan (semak setiap 12 jam)")
    while True:
        await run_single_check()
        await asyncio.sleep(12 * 3600)
