import logging
from aiogram import Router
from aiogram.types import Message
from keyboards import main_menu_kb

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = {
    "🛒 Kedai",
    "⚠️ Bantuan",
    "🔑 Log Masuk Token",
    "📚 Buat Userbot",
    "⚙️ Tetapan",
}


@router.message()
async def fallback_handler(message: Message):
    text = message.text or ""
    if text in MENU_BUTTONS:
        return
    logger.info(f"Fallback: user {message.from_user.id} — {text!r}")
    await message.answer(
        "❓ Sila gunakan menu di bawah untuk navigasi.",
        reply_markup=main_menu_kb(),
    )
