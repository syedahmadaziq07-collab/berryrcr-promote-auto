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
    icon   = "🔔 On" if aktif else "🔕 Off"

    await callback.message.edit_text(
        "🔔 *Notification*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Current status: *{icon}*\n\n"
        "You'll get notified every time your promo message gets sent.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Turn On",  callback_data="notif_on"),
                InlineKeyboardButton(text="🔕 Turn Off", callback_data="notif_off"),
            ],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
        ]),
    )


@router.callback_query(F.data == "notif_on")
async def cb_notif_on(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await db.set_notif_status(uid, True)
    await callback.message.edit_text(
        "🔔 *Notification*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Current status: *🔔 On*\n\n"
        "Notification ON — you'll get pinged each time a promo goes out.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Turn On",  callback_data="notif_on"),
                InlineKeyboardButton(text="🔕 Turn Off", callback_data="notif_off"),
            ],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
        ]),
    )


@router.callback_query(F.data == "notif_off")
async def cb_notif_off(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await db.set_notif_status(uid, False)
    await callback.message.edit_text(
        "🔕 *Notification*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Current status: *🔕 Off*\n\n"
        "Notification OFF — no more pings for you.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Turn On",  callback_data="notif_on"),
                InlineKeyboardButton(text="🔕 Turn Off", callback_data="notif_off"),
            ],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
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
    emel_display = f"`{email}`" if email else "_Not set yet_"

    await callback.message.edit_text(
        "📩 *Backup Email*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Current email: {emel_display}\n\n"
        "This email is used to receive your backup token if you ever lose access.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Set Email", callback_data="email_set")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
        ]),
    )


@router.callback_query(F.data == "email_set")
async def cb_email_set(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📩 *Set Backup Email*\n\n"
        "Send your email address:\n"
        "e.g. `nama@email.com`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="email_menu")]
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
            "⚠️ Invalid email format.\n\ne.g. `nama@email.com`\n\nTry again:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="email_menu")]
            ]),
        )
        await state.set_state(SettingsExtraFSM.waiting_email)
        return

    ok = await db.set_backup_email(uid, email)
    if ok:
        await message.answer(
            f"✅ *Backup email saved!*\n\n📩 `{email}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
            ]),
        )
    else:
        await message.answer(
            "❌ Failed to save email. Make sure your account is connected first.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Back", callback_data="email_menu")]
            ]),
        )
