"""
handlers/plan_flow.py — Shared handlers for plan duration selection & purchase confirmation.

Callback patterns:
  plan_dur:{context}:{plan}:{months}   → papar confirmation page
  plan_dur_back:{context}:{plan}       → balik ke duration selection
  plan_final:{context}:{plan}:{months} → proses purchase

Context values:
  "buy" = kedai.py (beli userbot baru + plan)
  "act" = buat_userbot.py (aktifkan plan pada userbot sedia ada)
  "sub" = subscription.py (flow alternatif)
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

_MY_TZ = timezone(timedelta(hours=8))

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

import database as db
from config import COIN_PLANS
from keyboards import (
    plan_duration_kb,
    plan_confirm_final_kb,
    kedai_menu_kb,
    back_to_menu_kb,
)

router = Router()
logger = logging.getLogger(__name__)

PLAN_COINS = {"PLUS": 300, "PRO": 600, "PREMIUM": 1000}
PLAN_ICON  = {"PLUS": "⚡ PLUS", "PRO": "👑 PRO", "PREMIUM": "💎 PREMIUM"}

# ─────────────────────────────────────────────
# In-memory idempotency guard
# Key format: "{user_id}:{message_id}"
# Prevents duplicate deductions even if DB check is slow
# ─────────────────────────────────────────────
processed_subscription_purchases: set[str] = set()


def _duration_text(plan_key: str) -> str:
    icon            = PLAN_ICON.get(plan_key, plan_key)
    coins_per_month = PLAN_COINS.get(plan_key, 300)
    return (
        f"🗓️ *Pilih Tempoh*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"Plan: *{icon}*\n"
        f"Rate: *{coins_per_month:,} Syiling / bulan*\n\n"
        "Berapa bulan korang nak aktifkan? 👇"
    )


def _confirm_text(plan_key: str, months: int, balance: int) -> str:
    icon            = PLAN_ICON.get(plan_key, plan_key)
    coins_per_month = PLAN_COINS.get(plan_key, 300)
    total           = coins_per_month * months
    after           = balance - total
    return (
        f"📋 *Confirm Purchase*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📦 Plan Selected:\n*{icon}*\n\n"
        f"🗓️ Duration:\n*{months} bulan*\n\n"
        f"🪙 Total:\n*{total:,} Syiling*\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 Wallet:\n*{balance:,} Syiling*\n\n"
        f"📌 Balance After:\n*{max(0, after):,} Syiling*"
    )


# ─────────────────────────────────────────────
# Langkah 1 → Langkah 2: Papar confirmation
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("plan_dur:"))
async def cb_plan_dur(callback: CallbackQuery):
    await callback.answer()
    try:
        _, context, plan_key, months_str = callback.data.split(":")
        months   = int(months_str)
        plan_key = plan_key.upper()
    except Exception:
        await callback.answer("⚠️ Ralat data.", show_alert=True)
        return

    if plan_key not in PLAN_COINS:
        await callback.answer("⚠️ Pelan tidak sah.", show_alert=True)
        return

    uid     = callback.from_user.id
    balance = await db.get_wallet(uid)
    total   = PLAN_COINS[plan_key] * months
    text    = _confirm_text(plan_key, months, balance)

    if balance < total:
        text += (
            f"\n\n❌ *Baki tak cukup bro!*\n"
            f"Perlu lagi *{total - balance:,} Syiling*.\n"
            "Reload via 🪙 Reload Syiling."
        )

    await callback.message.edit_text(
        text, parse_mode="Markdown",
        reply_markup=plan_confirm_final_kb(context, plan_key, months),
    )


# ─────────────────────────────────────────────
# Back dari confirmation → balik ke duration
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("plan_dur_back:"))
async def cb_plan_dur_back(callback: CallbackQuery):
    await callback.answer()
    try:
        _, context, plan_key = callback.data.split(":")
        plan_key = plan_key.upper()
    except Exception:
        await callback.answer("⚠️ Ralat.", show_alert=True)
        return

    await callback.message.edit_text(
        _duration_text(plan_key),
        parse_mode="Markdown",
        reply_markup=plan_duration_kb(plan_key, context),
    )


# ─────────────────────────────────────────────
# Langkah 2 → Proses purchase (idempotent)
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("plan_final:"))
async def cb_plan_final(callback: CallbackQuery):
    # Answer immediately so button doesn't stay loading
    await callback.answer("⏳ Memproses...")

    uid        = callback.from_user.id
    message_id = callback.message.message_id

    # ── Idempotency key: unique per user + confirmation message ──
    purchase_key = f"{uid}:{message_id}"

    # ── In-memory duplicate check (fast path) ──
    if purchase_key in processed_subscription_purchases:
        await callback.answer("⚠️ Purchase ini sudah diproses.", show_alert=True)
        logger.warning(
            "[PURCHASE] duplicate_attempt=True | user_id=%s | purchase_key=%s",
            uid, purchase_key,
        )
        return

    try:
        _, context, plan_key, months_str = callback.data.split(":")
        months   = int(months_str)
        plan_key = plan_key.upper()
    except Exception:
        await callback.message.edit_text("⚠️ Ralat data. Sila cuba lagi.")
        return

    if plan_key not in PLAN_COINS:
        await callback.message.edit_text("⚠️ Pelan tidak sah.")
        return

    coins_per_month = PLAN_COINS[plan_key]
    total           = coins_per_month * months
    plan            = COIN_PLANS[plan_key]
    icon            = PLAN_ICON[plan_key]

    # ── Fetch balance BEFORE any deduction ──
    coins_before = await db.get_wallet(uid)

    logger.info(
        "[PURCHASE] user_id=%s | plan=%s | months=%s | total=%s | coins_before=%s | purchase_key=%s",
        uid, plan_key, months, total, coins_before, purchase_key,
    )

    if coins_before < total:
        await callback.message.edit_text(
            f"❌ *Baki tak cukup bro!*\n\n"
            f"Need: *{total:,} Syiling*\n"
            f"Ada: *{coins_before:,} Syiling*\n\n"
            "Reload dulu via 🪙 Reload Syiling.",
            parse_mode="Markdown",
        )
        return

    # ── Mark in-memory BEFORE DB write to block concurrent taps ──
    processed_subscription_purchases.add(purchase_key)

    ok = await db.deduct_coins(uid, total, f"Aktifkan {plan['name']} {months} bulan")
    if not ok:
        # Deduction failed — unmark so user can retry
        processed_subscription_purchases.discard(purchase_key)
        coins_after = await db.get_wallet(uid)
        logger.error(
            "[PURCHASE] deduct_failed | user_id=%s | plan=%s | coins_before=%s | coins_after=%s",
            uid, plan_key, coins_before, coins_after,
        )
        await callback.message.edit_text(
            f"❌ *Transaksi gagal!*\n\nBalance: *{coins_after:,} Syiling*",
            parse_mode="Markdown",
        )
        return

    coins_after = coins_before - total

    logger.info(
        "[PURCHASE] success | user_id=%s | plan=%s | months=%s | "
        "coins_before=%s | coins_deducted=%s | coins_after=%s | purchase_key=%s",
        uid, plan_key, months, coins_before, total, coins_after, purchase_key,
    )

    userbot_id = None
    if context == "buy":
        existing = await db.get_userbot(uid)
        if existing:
            userbot_id = existing.get("userbot_id")
        else:
            userbot_id = await db.create_userbot(uid)
            try:
                session = await db.get_session(uid)
                if session:
                    await db.save_session(
                        uid,
                        session.get("phone_number", ""),
                        session.get("session_string", ""),
                        tg_username=session.get("tg_username", ""),
                        userbot_id=userbot_id,
                    )
            except Exception as e:
                logger.warning("plan_final: update session userbot_id gagal uid=%s: %s", uid, e)

    started, expires = await db.create_subscription(uid, plan_key, months)
    expires_str = expires.strftime("%d %b %Y")
    started_str = started.strftime("%d %b %Y")

    if context == "buy" and userbot_id:
        success = (
            f"✅ *Secured! Userbot + Plan dah ready bro* 🎉\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🤖 Userbot ID:\n`{userbot_id}`\n\n"
            f"📦 Plan Selected: *{icon}*\n"
            f"🗓️ Duration: *{months} bulan*\n"
            f"🪙 Total: *{total:,} Syiling*\n"
            f"📆 Mula: *{started_str}*\n"
            f"📅 Tamat: *{expires_str}*\n\n"
            "━━━━━━━━━━━━━━━\n"
            "⚠️ *Save Userbot ID korang!*\n"
            "_ID ni guna untuk recover kalau account kena limit/banned._\n\n"
            "Next steps:\n"
            "1️⃣ *📚 Buat Userbot* — connect Telegram account\n"
            "2️⃣ *⚙️ Tetapan* — setup group & message\n"
            "3️⃣ Tekan 🚀 *Start Promote!*"
        )
    elif context == "renew":
        success = (
            f"✅ *Plan activated, bot ready jalan auto!* 🔥\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📦 Plan Selected: *{icon}*\n"
            f"🗓️ Duration: *{months} bulan*\n"
            f"🪙 Total: *{total:,} Syiling*\n"
            f"📆 Mula: *{started_str}*\n"
            f"📅 Tamat: *{expires_str}*\n\n"
            "━━━━━━━━━━━━━━━\n"
            "Bot dah ready. Setup group & message dekat *⚙️ Tetapan* pastu tekan 🚀 Promote! 💨"
        )
    else:
        success = (
            f"✅ *Lets gooo! Pelan korang dah aktif* 🔥\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📦 Plan Selected: *{icon}*\n"
            f"🗓️ Duration: *{months} bulan*\n"
            f"🪙 Total: *{total:,} Syiling*\n"
            f"📆 Mula: *{started_str}*\n"
            f"📅 Tamat: *{expires_str}*\n\n"
            "━━━━━━━━━━━━━━━\n"
            "Bot dah ready bro! Setup group & message dekat *⚙️ Tetapan* pastu tekan 🚀 Promote! 💨"
        )

    # Edit message — remove inline keyboard so Confirm button disappears
    await callback.message.edit_text(success, parse_mode="Markdown", reply_markup=back_to_menu_kb())

    if context in ("buy", "renew"):
        await callback.message.answer("⚡ Back to Shop Zone:", reply_markup=kedai_menu_kb())
