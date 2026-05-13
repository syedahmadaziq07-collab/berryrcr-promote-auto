import logging
from datetime import datetime
import pytz
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

MY_TZ = pytz.timezone("Asia/Kuala_Lumpur")


class ScheduleFSM(StatesGroup):
    waiting_mula  = State()
    waiting_tamat = State()


def _schedule_menu_kb(has_schedule: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_schedule:
        buttons.append([
            InlineKeyboardButton(text="✏️ Kemaskini Jadual",  callback_data="schedule_set"),
            InlineKeyboardButton(text="🗑️ Padam Jadual",      callback_data="schedule_delete_confirm"),
        ])
    else:
        buttons.append([InlineKeyboardButton(text="➕ Tetapkan Jadual", callback_data="schedule_set")])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _get_userbot_id(uid: int):
    session = await db.get_session(uid)
    if session and session.get("userbot_id"):
        return session["userbot_id"]
    userbot = await db.get_userbot(uid)
    return userbot["userbot_id"] if userbot else None


def _is_within_schedule(waktu_mula: str, waktu_tamat: str) -> bool:
    now  = datetime.now(MY_TZ).time()
    try:
        mula  = datetime.strptime(waktu_mula, "%H:%M").time()
        tamat = datetime.strptime(waktu_tamat, "%H:%M").time()
    except ValueError:
        return True

    if mula <= tamat:
        return mula <= now <= tamat
    else:
        return now >= mula or now <= tamat


def is_schedule_active(schedule: dict) -> bool:
    if not schedule or not schedule.get("aktif"):
        return True
    return _is_within_schedule(
        str(schedule["waktu_mula"])[:5],
        str(schedule["waktu_tamat"])[:5],
    )


# ─────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────

@router.callback_query(F.data == "schedule_menu")
async def cb_schedule_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    sched = await db.get_schedule(ub_id) if ub_id else None

    now_str = datetime.now(MY_TZ).strftime("%H:%M")

    if sched:
        mula   = str(sched["waktu_mula"])[:5]
        tamat  = str(sched["waktu_tamat"])[:5]
        aktif  = sched.get("aktif", True)
        dalam  = _is_within_schedule(mula, tamat)
        status = "✅ Dalam waktu aktif" if (aktif and dalam) else "⏸️ Diluar waktu aktif"
        text = (
            "🕐 *JADUAL AKTIF*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Waktu Mula  : *{mula}*\n"
            f"⏰ Waktu Tamat : *{tamat}*\n"
            f"📍 Zon Waktu   : Asia/Kuala\\_Lumpur\n"
            f"🕑 Masa Kini   : *{now_str}*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Status: {status}"
        )
    else:
        text = (
            "🕐 *JADUAL AKTIF*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_Tiada jadual ditetapkan._\n\n"
            "Promote akan berjalan 24 jam.\n"
            "Tetapkan jadual untuk hadkan waktu aktif."
        )

    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=_schedule_menu_kb(sched is not None)
    )


# ─────────────────────────────────────────────
# Tetapkan Jadual
# ─────────────────────────────────────────────

@router.callback_query(F.data == "schedule_set")
async def cb_schedule_set(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🕐 *Tetapkan Jadual — Waktu Mula*\n\n"
        "Hantar waktu mula dalam format *HH:MM*\n\n"
        "Contoh: `09:00` untuk 9 pagi",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="schedule_menu")]
        ]),
    )
    await state.set_state(ScheduleFSM.waiting_mula)


@router.message(ScheduleFSM.waiting_mula)
async def process_waktu_mula(message: Message, state: FSMContext):
    raw = message.text.strip()
    try:
        datetime.strptime(raw, "%H:%M")
    except ValueError:
        await message.answer(
            "⚠️ Format tidak sah. Gunakan format *HH:MM*\nContoh: `09:00`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Batal", callback_data="schedule_menu")]
            ]),
        )
        return

    await state.update_data(waktu_mula=raw)
    await message.answer(
        f"✅ Waktu mula: *{raw}*\n\n"
        "🕐 *Tetapkan Jadual — Waktu Tamat*\n\n"
        "Hantar waktu tamat dalam format *HH:MM*\n\n"
        "Contoh: `23:00` untuk 11 malam",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="schedule_menu")]
        ]),
    )
    await state.set_state(ScheduleFSM.waiting_tamat)


@router.message(ScheduleFSM.waiting_tamat)
async def process_waktu_tamat(message: Message, state: FSMContext):
    raw  = message.text.strip()
    data = await state.get_data()
    mula = data.get("waktu_mula", "")

    try:
        datetime.strptime(raw, "%H:%M")
    except ValueError:
        await message.answer(
            "⚠️ Format tidak sah. Gunakan format *HH:MM*\nContoh: `23:00`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Batal", callback_data="schedule_menu")]
            ]),
        )
        return

    await state.clear()
    uid   = message.from_user.id
    ub_id = await _get_userbot_id(uid)

    if not ub_id:
        await message.answer("⚠️ Userbot tidak dijumpai.", reply_markup=back_to_menu_kb())
        return

    ok = await db.set_schedule(ub_id, uid, mula, raw)
    if ok:
        await message.answer(
            "✅ *Jadual Berjaya Ditetapkan!*\n\n"
            f"⏰ Waktu Mula  : *{mula}*\n"
            f"⏰ Waktu Tamat : *{raw}*\n"
            f"📍 Zon Waktu   : Asia/Kuala\\_Lumpur\n\n"
            "Promote hanya akan aktif dalam waktu yang ditetapkan.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🕐 Lihat Jadual", callback_data="schedule_menu")],
                [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")],
            ]),
        )
    else:
        await message.answer("❌ Gagal menyimpan jadual. Sila cuba lagi.", reply_markup=back_to_menu_kb())


# ─────────────────────────────────────────────
# Padam Jadual
# ─────────────────────────────────────────────

@router.callback_query(F.data == "schedule_delete_confirm")
async def cb_schedule_delete_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🗑️ *Padam Jadual?*\n\n"
        "Promote akan berjalan 24 jam tanpa had waktu.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ya, Padam",  callback_data="schedule_delete_do"),
                InlineKeyboardButton(text="❌ Batal",       callback_data="schedule_menu"),
            ]
        ]),
    )


@router.callback_query(F.data == "schedule_delete_do")
async def cb_schedule_delete_do(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    if ub_id:
        await db.delete_schedule(ub_id)
    await callback.message.edit_text(
        "✅ *Jadual berjaya dipadamkan.*\n\nPromote kini aktif 24 jam.",
        parse_mode="Markdown",
        reply_markup=_schedule_menu_kb(False),
    )
