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

    logger.info("Fallback: uid=%s state=None text=%r", message.from_user.id, text)
    await message.answer(
        "❓ Sila gunakan menu di bawah untuk navigasi.",
        reply_markup=main_menu_kb(),
    )
