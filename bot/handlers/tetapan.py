"""
handlers/tetapan.py — Menu Tetapan: kumpulan, mesej, jarak masa, promote, status.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from config import MIN_DELAY_MINUTES
from keyboards import (
    tetapan_kb, back_to_menu_kb, cancel_kb, main_menu_kb, delay_timer_kb,
)
from services import scheduler_service

router = Router()
logger = logging.getLogger(__name__)


class SettingsFSM(StatesGroup):
    waiting_message = State()


# ─────────────────────────────────────────────
# ⚙️ TETAPAN UTAMA
# ─────────────────────────────────────────────

@router.message(F.text == "⚙️ Control Panel")
async def msg_tetapan(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    sub      = await db.get_active_subscription(uid)
    session  = await db.get_session(uid)
    settings = await db.get_promo_settings(uid)
    groups   = await db.get_selected_groups(uid)

    plan        = sub["plan"] if sub else "None"
    tg_user     = session.get("tg_username", "") if session else ""
    phone       = session.get("phone_number", "") if session else ""
    acc         = f"@{tg_user}" if tg_user else (f"`{phone}`" if phone else "Not connected")
    is_running  = settings.get("is_running", False) if settings else False
    status_icon = "Active 🟢" if is_running else "Not Active 🔴"

    text = (
        "⚙️ *Control Panel*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📦 Current Plan: *{plan}*\n"
        f"📱 Connected Account: {acc}\n"
        f"👥 Selected Group: *{len(groups)}*\n"
        f"🤖 Bot Status: *{status_icon}*\n\n"
        "Customize setting korang dekat bawah 👇"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=tetapan_kb())


# ─────────────────────────────────────────────
# 📝 TETAPKAN MESEJ
# ─────────────────────────────────────────────

@router.callback_query(F.data == "set_message")
async def cb_set_message(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    sub = await db.get_active_subscription(uid)
    if not sub:
        await callback.answer(
            "⚠️ Sila aktifkan pelan PLUS/PRO dahulu!",
            show_alert=True,
        )
        return

    # Jawab SEBELUM DB call seterusnya
    await callback.answer()
    settings = await db.get_promo_settings(uid)
    current  = (settings.get("message") or settings.get("message_text")) if settings else None
    preview  = f"```\n{current}\n```" if current else "_No message set yet_"

    await callback.message.edit_text(
        f"✏️ *Edit Message*\n\n"
        f"Current message:\n{preview}\n\n"
        f"Send your new promo message:",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_message)


@router.message(SettingsFSM.waiting_message)
async def process_message(message: Message, state: FSMContext):
    msg_text = message.text
    if not msg_text or not msg_text.strip():
        await message.answer("⚠️ Message can't be empty.", reply_markup=cancel_kb())
        return
    if len(msg_text) > 4000:
        await message.answer(
            "⚠️ Too long lah — max 4,000 characters.",
            reply_markup=cancel_kb(),
        )
        return

    await db.update_promo_message(message.from_user.id, msg_text)
    preview = (msg_text[:200] + "...") if len(msg_text) > 200 else msg_text
    await message.answer(
        f"✅ *Message saved!*\n\nPreview:\n```\n{preview}\n```",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )
    await state.clear()


# ─────────────────────────────────────────────
# ⏱️ TETAPKAN JARAK MASA
# ─────────────────────────────────────────────

@router.callback_query(F.data == "set_delay")
async def cb_set_delay(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    sub = await db.get_active_subscription(uid)
    if not sub:
        await callback.answer(
            "⚠️ Sila aktifkan pelan PLUS/PRO dahulu!",
            show_alert=True,
        )
        return

    await callback.answer()
    settings      = await db.get_promo_settings(uid)
    current_delay = settings["delay_minutes"] if settings else MIN_DELAY_MINUTES

    await callback.message.edit_text(
        "⏱️ *Delay Timer*\n\n"
        "Pilih berapa minit sekali bot ulang promote 💨\n\n"
        "⚠️ *Recommended:*\n"
        "30 minit ke atas untuk elakkan spam Telegram\\.\n\n"
        "📌 Delay rendah \\= promote lebih laju\n"
        "📌 Delay tinggi \\= lebih selamat untuk account\n\n"
        f"_Current: *{current_delay}m*_\n\n"
        "Available timer:\n"
        "5m hingga 300m \\(gandaan 5 minit\\)",
        parse_mode="MarkdownV2",
        reply_markup=delay_timer_kb(current=current_delay),
    )
    await state.clear()


@router.callback_query(F.data.startswith("delay_set:"))
async def cb_delay_set(callback: CallbackQuery, state: FSMContext):
    uid   = callback.from_user.id
    delay = int(callback.data.split(":")[1])

    await db.update_promo_delay(uid, delay)
    hours = delay // 60
    mins  = delay % 60
    human = f"{hours}j {mins}m" if hours > 0 else f"{mins}m"

    await callback.answer(f"✅ Timer ditetapkan: {human}", show_alert=False)

    await callback.message.edit_text(
        "⏱️ *Delay Timer*\n\n"
        "Pilih berapa minit sekali bot ulang promote 💨\n\n"
        "⚠️ *Recommended:*\n"
        "30 minit ke atas untuk elakkan spam Telegram\\.\n\n"
        "📌 Delay rendah \\= promote lebih laju\n"
        "📌 Delay tinggi \\= lebih selamat untuk account\n\n"
        f"_Current: *{delay}m*_\n\n"
        "Available timer:\n"
        "5m hingga 300m \\(gandaan 5 minit\\)",
        parse_mode="MarkdownV2",
        reply_markup=delay_timer_kb(current=delay),
    )


@router.callback_query(F.data == "set_delay_back")
async def cb_set_delay_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid      = callback.from_user.id
    sub      = await db.get_active_subscription(uid)
    session  = await db.get_session(uid)
    settings = await db.get_promo_settings(uid)
    groups   = await db.get_selected_groups(uid)

    plan        = sub["plan"] if sub else "None"
    tg_user     = session.get("tg_username", "") if session else ""
    phone       = session.get("phone_number", "") if session else ""
    acc         = f"@{tg_user}" if tg_user else (f"`{phone}`" if phone else "Not connected")
    is_running  = settings.get("is_running", False) if settings else False
    status_icon = "Active 🟢" if is_running else "Not Active 🔴"

    text = (
        "⚙️ *Control Panel*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📦 Current Plan: *{plan}*\n"
        f"📱 Connected Account: {acc}\n"
        f"👥 Selected Group: *{len(groups)}*\n"
        f"🤖 Bot Status: *{status_icon}*\n\n"
        "Customize setting korang dekat bawah 👇"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=tetapan_kb())


# Promote (mula/henti) dikendalikan oleh handlers/promote.py


