"""
handlers/account.py — 🔑 Log Masuk Token:
  User masukkan ID Userbot (UB-xxx) untuk tuntut / pulihkan akses.
  Digunakan apabila akaun lama dibanned/restricted.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards import back_to_menu_kb, cancel_kb, main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


class LogMasukTokenFSM(StatesGroup):
    waiting_userbot_id = State()


# ─────────────────────────────────────────────
# 🔑 Log Masuk Token — Entry
# ─────────────────────────────────────────────

@router.message(F.text == "🔑 Log Masuk Token")
async def msg_log_masuk(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    session = await db.get_session(uid)

    if session and session.get("userbot_id"):
        userbot_id = session["userbot_id"]
        tg_user = session.get("tg_username", "")
        phone = session.get("phone_number", "")
        sub = await db.get_active_subscription(uid)
        acc = f"@{tg_user}" if tg_user else (f"`{phone}`" if phone else "Belum disambungkan")
        plan = sub["plan"] if sub else "Tiada"

        await message.answer(
            "🔑 *Log Masuk Token*\n\n"
            "Anda sudah mempunyai userbot aktif:\n\n"
            f"🆔 ID Userbot: `{userbot_id}`\n"
            f"📱 Akaun: {acc}\n"
            f"📋 Pelan: *{plan}*\n\n"
            "Untuk pindah akses ke akaun lain, guna *📚 Buat Userbot* → Pindah Userbot.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    await message.answer(
        "🔑 *Log Masuk Token*\n\n"
        "Masukkan *ID Userbot* anda untuk pulihkan akses.\n\n"
        "Format: `UB-<id>-XXXXXX`\n\n"
        "ID Userbot ini diberikan semasa anda mula-mula sambung akaun. "
        "Simpan ID ini untuk pulihkan akses jika akaun lama anda kena limit/banned.",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(LogMasukTokenFSM.waiting_userbot_id)


# ─────────────────────────────────────────────
# FSM: Terima Userbot ID
# ─────────────────────────────────────────────

@router.message(LogMasukTokenFSM.waiting_userbot_id)
async def process_userbot_id(message: Message, state: FSMContext):
    uid = message.from_user.id
    userbot_id = message.text.strip().upper()

    if not userbot_id.startswith("UB-"):
        await message.answer(
            "⚠️ Format ID tidak sah. ID Userbot bermula dengan `UB-`\n\n"
            "Contoh: `UB-123456789-ABC123`",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
        return

    session = await db.get_session_by_userbot_id(userbot_id)

    if not session:
        await message.answer(
            "❌ *ID Userbot tidak dijumpai.*\n\n"
            "Pastikan ID yang dimasukkan adalah betul.\n"
            "Hubungi @berryrcr jika anda perlukan bantuan.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    owner_id = session.get("user_id")

    if owner_id == uid:
        await message.answer(
            "✅ *ID Userbot Dijumpai*\n\n"
            f"🆔 ID: `{userbot_id}`\n"
            "Userbot ini sudah milik anda.\n\n"
            "Guna *📚 Buat Userbot* untuk sambung akaun.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    my_session = await db.get_session(uid)
    if my_session and my_session.get("userbot_id"):
        await message.answer(
            "⚠️ Anda sudah mempunyai userbot.\n\n"
            f"ID Userbot semasa anda: `{my_session['userbot_id']}`\n\n"
            "Setiap akaun hanya boleh mempunyai satu userbot.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    await db.transfer_userbot_session(owner_id, uid)
    await state.clear()

    await message.answer(
        "✅ *Akses Userbot Berjaya Dipulihkan!*\n\n"
        f"🆔 ID Userbot: `{userbot_id}`\n\n"
        "Anda kini pemilik userbot ini.\n\n"
        "Langkah seterusnya:\n"
        "• Tekan *📚 Buat Userbot* untuk sambung akaun Telegram baharu\n"
        "• Guna *⚙️ Tetapan* untuk konfigurasi promote",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
    logger.info("Userbot %s dipindahkan → uid=%s (Log Masuk Token)", userbot_id, uid)
