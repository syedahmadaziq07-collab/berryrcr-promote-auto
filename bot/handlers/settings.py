import logging
import re
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards import back_to_menu_kb

router = Router()
logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$")


class SettingsExtraFSM(StatesGroup):
    waiting_email = State()


# ─────────────────────────────────────────────
# 🔕 URUS PEMBERITAHUAN
# ─────────────────────────────────────────────

@router.callback_query(F.data == "notif_menu")
async def cb_notif_menu(callback: CallbackQuery):
    await callback.answer()
    uid    = callback.from_user.id
    aktif  = await db.get_notif_status(uid)
    icon   = "🔔 Aktif" if aktif else "🔕 Tidak Aktif"

    await callback.message.edit_text(
        "🔕 *URUS PEMBERITAHUAN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Status semasa: *{icon}*\n\n"
        "Pemberitahuan dihantar apabila mesej promosi berjaya dihantar.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Hidupkan", callback_data="notif_on"),
                InlineKeyboardButton(text="🔕 Matikan",  callback_data="notif_off"),
            ],
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
        ]),
    )


@router.callback_query(F.data == "notif_on")
async def cb_notif_on(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await db.set_notif_status(uid, True)
    await callback.message.edit_text(
        "🔔 *URUS PEMBERITAHUAN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Status semasa: *🔔 Aktif*\n\n"
        "Anda akan menerima pemberitahuan setiap kali mesej promosi dihantar.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Hidupkan", callback_data="notif_on"),
                InlineKeyboardButton(text="🔕 Matikan",  callback_data="notif_off"),
            ],
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
        ]),
    )


@router.callback_query(F.data == "notif_off")
async def cb_notif_off(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await db.set_notif_status(uid, False)
    await callback.message.edit_text(
        "🔕 *URUS PEMBERITAHUAN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Status semasa: *🔕 Tidak Aktif*\n\n"
        "Pemberitahuan telah dimatikan.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Hidupkan", callback_data="notif_on"),
                InlineKeyboardButton(text="🔕 Matikan",  callback_data="notif_off"),
            ],
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
        ]),
    )


# ─────────────────────────────────────────────
# 📧 EMEL SANDARAN
# ─────────────────────────────────────────────

@router.callback_query(F.data == "email_menu")
async def cb_email_menu(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    email = await db.get_backup_email(uid)
    emel_display = f"`{email}`" if email else "_Belum ditetapkan_"

    await callback.message.edit_text(
        "📧 *EMEL SANDARAN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Emel semasa: {emel_display}\n\n"
        "Emel ini digunakan untuk menerima token sandaran sekiranya anda kehilangan akses.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Tetapkan Emel", callback_data="email_set")],
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
        ]),
    )


@router.callback_query(F.data == "email_set")
async def cb_email_set(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📧 *Tetapkan Emel Sandaran*\n\n"
        "Hantar alamat emel anda:\n"
        "Contoh: `nama@email.com`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="email_menu")]
        ]),
    )
    await state.set_state(SettingsExtraFSM.waiting_email)


@router.message(SettingsExtraFSM.waiting_email)
async def process_email(message: Message, state: FSMContext):
    await state.clear()
    uid   = message.from_user.id
    email = message.text.strip() if message.text else ""

    if not EMAIL_REGEX.match(email):
        await message.answer(
            "⚠️ Format emel tidak sah.\n\nContoh: `nama@email.com`\n\nSila hantar semula:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Batal", callback_data="email_menu")]
            ]),
        )
        await state.set_state(SettingsExtraFSM.waiting_email)
        return

    ok = await db.set_backup_email(uid, email)
    if ok:
        await message.answer(
            f"✅ *Emel sandaran berjaya disimpan!*\n\n📧 `{email}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")]
            ]),
        )
    else:
        await message.answer(
            "❌ Gagal menyimpan emel. Pastikan anda sudah mempunyai akaun yang disambungkan.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Kembali", callback_data="email_menu")]
            ]),
        )
