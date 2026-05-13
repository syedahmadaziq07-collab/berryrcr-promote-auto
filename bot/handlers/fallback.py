import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
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
async def fallback_handler(message: Message, state: FSMContext):
    text = message.text or ""

    # Jangan interfere dengan menu buttons yang ada handler sendiri
    if text in MENU_BUTTONS:
        return

    # Jangan interfere dengan FSM flows yang sedang aktif
    # (topup, OTP, send coins, gift, dll)
    current_state = await state.get_state()
    if current_state is not None:
        return

    # Jika input nampak seperti kod OTP (digit sahaja, atau digit dengan jarak)
    # — kemungkinan bot restart dan state hilang
    cleaned = text.strip().replace(" ", "")
    if cleaned.isdigit() and 4 <= len(cleaned) <= 7:
        logger.info("Fallback OTP-like input uid=%s — sesi mungkin tamat", message.from_user.id)
        await message.answer(
            "⚠️ Sesi anda telah tamat.\n"
            "Sila mulakan semula proses sambung akaun melalui *📚 Buat Userbot*.",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(),
        )
        return

    logger.info("Fallback: uid=%s state=None text=%r", message.from_user.id, text)
    await message.answer(
        "❓ Sila gunakan menu di bawah untuk navigasi.",
        reply_markup=main_menu_kb(),
    )
