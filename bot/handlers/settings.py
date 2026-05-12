from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards import back_to_menu_kb, cancel_kb
from config import MIN_DELAY_MINUTES

router = Router()


class SettingsFSM(StatesGroup):
    waiting_message = State()
    waiting_delay   = State()


# ─────────────────────────────────────────────
# Reply keyboard triggers
# ─────────────────────────────────────────────

@router.message(F.text == "📝 Tetapkan Mesej")
async def msg_set_message(message: Message, state: FSMContext):
    uid = message.from_user.id
    sub = await db.get_active_subscription(uid)
    if not sub:
        await message.answer(
            "⚠️ *Sila aktifkan pelan PLUS/PRO dahulu melalui 📚 Buat Userbot!*",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    settings = await db.get_promo_settings(uid)
    current  = settings["message_text"] if settings and settings.get("message_text") else "Tiada mesej ditetapkan"

    await message.answer(
        f"📝 *Tetapkan Mesej Promosi*\n\n"
        f"Mesej semasa:\n```{current}```\n\n"
        f"Sila hantar mesej promosi baharu anda.\n"
        f"(Footer akan ditambah secara automatik mengikut pelan)",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_message)


@router.message(F.text == "⏱️ Tetapkan Jarak Masa")
async def msg_set_delay(message: Message, state: FSMContext):
    uid = message.from_user.id
    sub = await db.get_active_subscription(uid)
    if not sub:
        await message.answer(
            "⚠️ *Sila aktifkan pelan PLUS/PRO dahulu melalui 📚 Buat Userbot!*",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    settings      = await db.get_promo_settings(uid)
    current_delay = settings["delay_minutes"] if settings else MIN_DELAY_MINUTES

    await message.answer(
        f"⏱️ *Tetapkan Jarak Masa Promote*\n\n"
        f"Jarak masa semasa: *{current_delay} minit*\n\n"
        f"Minimum jarak masa: *{MIN_DELAY_MINUTES} minit*\n\n"
        f"Sila masukkan jarak masa dalam minit (nombor sahaja):\n"
        f"Contoh: `60` = hantar setiap 1 jam",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_delay)


# ─────────────────────────────────────────────
# Inline callback handlers
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

    settings = await db.get_promo_settings(uid)
    current  = settings["message_text"] if settings and settings.get("message_text") else "Tiada mesej ditetapkan"

    await callback.message.edit_text(
        f"📝 *Tetapkan Mesej Promosi*\n\n"
        f"Mesej semasa:\n```{current}```\n\n"
        f"Sila hantar mesej promosi baharu anda.\n"
        f"(Footer akan ditambah secara automatik mengikut pelan)",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_message)
    await callback.answer()


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

    settings      = await db.get_promo_settings(uid)
    current_delay = settings["delay_minutes"] if settings else MIN_DELAY_MINUTES

    await callback.message.edit_text(
        f"⏱️ *Tetapkan Jarak Masa Promote*\n\n"
        f"Jarak masa semasa: *{current_delay} minit*\n\n"
        f"Minimum jarak masa: *{MIN_DELAY_MINUTES} minit*\n\n"
        f"Sila masukkan jarak masa dalam minit (nombor sahaja):\n"
        f"Contoh: `60` = hantar setiap 1 jam",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(SettingsFSM.waiting_delay)
    await callback.answer()


# ─────────────────────────────────────────────
# FSM: Message input
# ─────────────────────────────────────────────

@router.message(SettingsFSM.waiting_message)
async def process_message(message: Message, state: FSMContext):
    uid      = message.from_user.id
    msg_text = message.text

    if not msg_text or len(msg_text.strip()) == 0:
        await message.answer("⚠️ Mesej tidak boleh kosong. Sila cuba lagi:", reply_markup=cancel_kb())
        return
    if len(msg_text) > 4000:
        await message.answer(
            "⚠️ Mesej terlalu panjang (maksimum 4,000 aksara). Sila pendekkan.",
            reply_markup=cancel_kb(),
        )
        return

    await db.update_promo_message(uid, msg_text)
    await message.answer(
        f"✅ *Mesej Berjaya Disimpan!*\n\nMesej anda:\n```{msg_text}```",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )
    await state.clear()


# ─────────────────────────────────────────────
# FSM: Delay input
# ─────────────────────────────────────────────

@router.message(SettingsFSM.waiting_delay)
async def process_delay(message: Message, state: FSMContext):
    uid  = message.from_user.id
    text = message.text.strip()

    if not text.isdigit():
        await message.answer(
            "⚠️ Sila masukkan nombor sahaja (contoh: 60):",
            reply_markup=cancel_kb(),
        )
        return

    delay = int(text)
    if delay < MIN_DELAY_MINUTES:
        await message.answer(
            f"⚠️ Jarak masa minimum ialah *{MIN_DELAY_MINUTES} minit*. Sila masukkan nilai yang lebih besar:",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
        return

    await db.update_promo_delay(uid, delay)
    hours = delay // 60
    mins  = delay % 60
    human = f"{hours} jam {mins} minit" if hours > 0 else f"{mins} minit"

    await message.answer(
        f"✅ *Jarak Masa Berjaya Ditetapkan!*\n\nMesej akan dihantar setiap *{human}*.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )
    await state.clear()
