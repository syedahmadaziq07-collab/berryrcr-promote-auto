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
        "🎁 *GET FREE 100 SYILING*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Share link referral korang dengan kawan.\n"
        "Bila dorang activate plan *PLUS* atau *PRO*,\n"
        "korang dapat *100 Syiling* — kawan korang pun dapat *100 Syiling*! 🤑\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 *Link Referral Korang:*\n"
        f"```\n{link}\n```\n\n"
        f"📊 *Stat Korang:*\n"
        f"👥 Jemputan Berjaya: *{stats['paid_count']} orang*\n"
        f"⏳ Pending (belum aktif plan): *{stats['pending_count']} orang*\n"
        f"🪙 Total Syiling Diterima: *{stats['total_coins']} Syiling*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *Cara kerja:*\n"
        "1️⃣ Share link kat kawan\n"
        "2️⃣ Kawan guna link tu untuk /start\n"
        "3️⃣ Kawan activate plan PLUS atau PRO\n"
        "4️⃣ Korang & kawan masing-masing dapat 100 Syiling 🎉\n\n"
        "⚠️ Reward hanya 1x per kawan — tak boleh self-refer."
    )


@router.message(F.text == "🎁 Get Free 100 Syiling")
async def msg_referral(message: Message):
    uid = message.from_user.id
    logger.info("[REFERRAL] referral_link_opened | user_id=%s", uid)
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
            [InlineKeyboardButton(text="🔄 Refresh Stats", callback_data="referral_menu")],
        ]),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "referral_menu")
async def cb_referral_menu(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    logger.info("[REFERRAL] referral_link_opened (cb) | user_id=%s", uid)
    try:
        bot_info = await callback.bot.get_me()
        bot_username = bot_info.username or "bot"
    except Exception:
        bot_username = "bot"

    text = await _build_referral_text(uid, bot_username)
    try:
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh Stats", callback_data="referral_menu")],
                [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")],
            ]),
            disable_web_page_preview=True,
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh Stats", callback_data="referral_menu")],
            ]),
            disable_web_page_preview=True,
        )
