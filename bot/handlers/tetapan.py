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
    tetapan_kb, back_to_menu_kb, cancel_kb, main_menu_kb,
)
from services import scheduler_service

router = Router()
logger = logging.getLogger(__name__)


class SettingsFSM(StatesGroup):
    waiting_message    = State()
    waiting_delay      = State()


# ─────────────────────────────────────────────
# ⚙️ TETAPAN UTAMA
# ─────────────────────────────────────────────

@router.message(F.text == "⚙️ Tetapan")
async def msg_tetapan(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    sub      = await db.get_active_subscription(uid)
    session  = await db.get_session(uid)
    settings = await db.get_promo_settings(uid)
    groups   = await db.get_selected_groups(uid)

    plan        = sub["plan"] if sub else "Tiada"
    tg_user     = session.get("tg_username", "") if session else ""
    phone       = session.get("phone_number", "") if session else ""
    acc         = f"@{tg_user}" if tg_user else (f"`{phone}`" if phone else "Belum disambungkan")
    is_running  = settings.get("is_running", False) if settings else False
    status_icon = "🟢 Aktif" if is_running else "🔴 Tidak aktif"

    text = (
        "⚙️ *Tetapan*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📋 Pelan: *{plan}*\n"
        f"📱 Akaun: {acc}\n"
        f"👥 Kumpulan: *{len(groups)} dipilih*\n"
        f"🔑 Status: *{status_icon}*\n\n"
        "Pilih tetapan di bawah:"
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
    current  = settings.get("message_text") if settings else None
    preview  = f"```\n{current}\n```" if current else "_Tiada mesej ditetapkan_"

    await callback.message.edit_text(
        f"📝 *Tetapkan Mesej Promosi*\n\n"
        f"Mesej semasa:\n{preview}\n\n"
        f"Hantar mesej promosi baharu anda:",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_message)


@router.message(SettingsFSM.waiting_message)
async def process_message(message: Message, state: FSMContext):
    msg_text = message.text
    if not msg_text or not msg_text.strip():
        await message.answer("⚠️ Mesej tidak boleh kosong.", reply_markup=cancel_kb())
        return
    if len(msg_text) > 4000:
        await message.answer(
            "⚠️ Mesej terlalu panjang (maksimum 4,000 aksara).",
            reply_markup=cancel_kb(),
        )
        return

    await db.update_promo_message(message.from_user.id, msg_text)
    preview = (msg_text[:200] + "...") if len(msg_text) > 200 else msg_text
    await message.answer(
        f"✅ *Mesej Berjaya Disimpan!*\n\nPratonton:\n```\n{preview}\n```",
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

    # Jawab SEBELUM DB call seterusnya
    await callback.answer()
    settings          = await db.get_promo_settings(uid)
    current_delay     = settings["delay_minutes"] if settings else MIN_DELAY_MINUTES

    await callback.message.edit_text(
        f"⏱️ *Tetapkan Jarak Masa Promote*\n\n"
        f"Jarak masa semasa: *{current_delay} minit*\n"
        f"Minimum jarak masa: *{MIN_DELAY_MINUTES} minit*\n\n"
        f"Hantar jarak masa dalam minit:\n"
        f"Contoh: `60` = setiap 1 jam | `120` = setiap 2 jam",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_delay)


@router.message(SettingsFSM.waiting_delay)
async def process_delay(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer(
            "⚠️ Sila masukkan nombor sahaja.\nContoh: `60`",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
        return

    delay = int(text)
    if delay < MIN_DELAY_MINUTES:
        await message.answer(
            f"⚠️ Jarak masa minimum ialah *{MIN_DELAY_MINUTES} minit*.\n\nSila masukkan semula:",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
        return

    await db.update_promo_delay(message.from_user.id, delay)
    hours = delay // 60
    mins  = delay % 60
    human = f"{hours} jam {mins} minit" if hours > 0 else f"{mins} minit"

    await message.answer(
        f"✅ *Jarak Masa Berjaya Ditetapkan!*\n\n"
        f"Mesej akan dihantar setiap *{human}*.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )
    await state.clear()


# ─────────────────────────────────────────────
# 🚀 MULA PROMOTE
# ─────────────────────────────────────────────

@router.callback_query(F.data == "start_promote")
async def cb_start_promote(callback: CallbackQuery):
    uid = callback.from_user.id

    sub = await db.get_active_subscription(uid)
    if not sub:
        await callback.answer(
            "⚠️ Sila aktifkan pelan PLUS/PRO dahulu melalui 📚 Buat Userbot!",
            show_alert=True,
        )
        return

    session = await db.get_session(uid)
    if not session:
        await callback.answer(
            "⚠️ Sila sambung akaun Telegram dahulu melalui 📚 Buat Userbot!",
            show_alert=True,
        )
        return

    settings = await db.get_promo_settings(uid)
    if not settings or not settings.get("message_text"):
        await callback.answer(
            "⚠️ Sila tetapkan mesej promosi dahulu melalui 📝 Tetapkan Mesej!",
            show_alert=True,
        )
        return

    groups = await db.get_selected_groups(uid)
    if not groups:
        await callback.answer(
            "⚠️ Sila pilih kumpulan dahulu melalui 👥 Pilih Kumpulan!",
            show_alert=True,
        )
        return

    if settings.get("is_running"):
        await callback.answer("ℹ️ Promote sudah berjalan!", show_alert=True)
        return

    # Jawab SEBELUM operasi DB + scheduler
    await callback.answer("🚀 Memulakan promote...")
    await db.set_promo_running(uid, True)
    scheduler_service.start_promo_job(uid, delay_minutes=settings["delay_minutes"])

    plan_name   = sub["plan"]
    delay       = settings["delay_minutes"]
    hours       = delay // 60
    mins        = delay % 60
    human_delay = f"{hours}j {mins}m" if hours > 0 else f"{mins}m"

    await callback.message.edit_text(
        f"🚀 *Promote Dimulakan!*\n\n"
        f"📋 Pelan: *{plan_name}*\n"
        f"👥 Kumpulan: *{len(groups)} kumpulan*\n"
        f"⏱️ Jarak Masa: *setiap {human_delay}*\n\n"
        f"Bot akan menghantar mesej secara automatik.\n\n"
        f"⚠️ _Auto-promote boleh menyebabkan akaun dihadkan oleh Telegram. "
        f"Gunakan dengan berhati-hati._",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )


# ─────────────────────────────────────────────
# ⏹️ HENTI PROMOTE
# ─────────────────────────────────────────────

@router.callback_query(F.data == "stop_promote")
async def cb_stop_promote(callback: CallbackQuery):
    uid      = callback.from_user.id
    settings = await db.get_promo_settings(uid)

    if not settings or not settings.get("is_running"):
        await callback.answer("ℹ️ Promote tidak sedang berjalan.", show_alert=True)
        return

    # Jawab SEBELUM DB + scheduler
    await callback.answer("⏹️ Menghentikan promote...")
    await db.set_promo_running(uid, False)
    scheduler_service.stop_promo_job(uid)

    await callback.message.edit_text(
        "⏹️ *Promote Dihentikan*\n\n"
        "Semua promosi automatik telah dihentikan.\n"
        "Guna *⚙️ Tetapan → 🚀 Mula Promote* untuk mulakan semula.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )


