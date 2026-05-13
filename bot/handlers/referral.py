import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
import database as db
from keyboards import back_to_menu_kb

router = Router()
logger = logging.getLogger(__name__)


async def _build_referral_text(uid: int, bot_username: str) -> str:
    ref_code = await db.get_referral_code(uid)
    stats    = await db.get_referral_stats(uid)
    link     = f"https://t.me/{bot_username}?start={ref_code}"

    return (
        "🎁 *KOD RUJUKAN ANDA*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 Kod    : `{ref_code}`\n"
        f"📎 Link   : {link}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Jumlah Rujukan     : *{stats['count']} orang*\n"
        f"🪙 Syiling Diperoleh  : *{stats['total_coins']} syiling*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "_Setiap rujukan memberikan:_\n"
        "• Anda: *100 syiling*\n"
        "• Rakan baru: *50 syiling*"
    )


@router.callback_query(F.data == "referral_menu")
async def cb_referral_menu(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    try:
        bot_info = await callback.bot.get_me()
        bot_username = bot_info.username or "bot"
    except Exception:
        bot_username = "bot"

    text = await _build_referral_text(uid, bot_username)
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Muat Semula", callback_data="referral_menu")],
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
        ]),
        disable_web_page_preview=True,
    )


@router.message(F.text == "🎁 Rujukan")
async def msg_referral(message: Message):
    uid = message.from_user.id
    try:
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username or "bot"
    except Exception:
        bot_username = "bot"

    text = await _build_referral_text(uid, bot_username)
    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Lihat Rujukan", callback_data="referral_menu")],
            [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")],
        ]),
        disable_web_page_preview=True,
    )
