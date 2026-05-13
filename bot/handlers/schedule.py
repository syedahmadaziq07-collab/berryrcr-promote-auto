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
            InlineKeyboardButton(text="✏️ Edit Schedule",   callback_data="schedule_set"),
            InlineKeyboardButton(text="🗑 Remove Schedule", callback_data="schedule_delete_confirm"),
        ])
    else:
        buttons.append([InlineKeyboardButton(text="✏️ Edit Schedule", callback_data="schedule_set")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")])
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
        status = "✅ Promote Session Active" if (aktif and dalam) else "⏸️ Promote Session Inactive"
        text = (
            "⏰ *Auto Active Schedule*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🟢 Start Time  : *{mula}*\n"
            f"🌙 End Time    : *{tamat}*\n"
            f"🌍 Timezone    : Asia/Kuala\\_Lumpur\n"
            f"⌚️ Current Time : *{now_str}*\n\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🚦 *Status Now:*\n"
            f"{status}"
        )
    else:
        text = (
            "⏰ *Auto Active Schedule*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "_No schedule set yet._\n\n"
            "Promote running 24/7 by default.\n"
            "Set a schedule to limit your active hours."
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
        "✏️ *Edit Schedule — Start Time*\n\n"
        "Send your start time in *HH:MM* format.\n\n"
        "Example: `09:00` for 9am",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="schedule_menu")]
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
            "⚠️ Invalid format bro. Use *HH:MM*\nExample: `09:00`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="schedule_menu")]
            ]),
        )
        return

    await state.update_data(waktu_mula=raw)
    await message.answer(
        f"✅ Start Time set: *{raw}*\n\n"
        "✏️ *Edit Schedule — End Time*\n\n"
        "Now send your end time in *HH:MM* format.\n\n"
        "Example: `23:00` for 11pm",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="schedule_menu")]
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
            "⚠️ Invalid format bro. Use *HH:MM*\nExample: `23:00`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="schedule_menu")]
            ]),
        )
        return

    await state.clear()
    uid   = message.from_user.id
    ub_id = await _get_userbot_id(uid)

    if not ub_id:
        await message.answer("⚠️ Userbot not found.", reply_markup=back_to_menu_kb())
        return

    ok = await db.set_schedule(ub_id, uid, mula, raw)
    if ok:
        await message.answer(
            "✅ *Schedule Saved!*\n\n"
            f"🟢 Start Time  : *{mula}*\n"
            f"🌙 End Time    : *{raw}*\n"
            f"🌍 Timezone    : Asia/Kuala\\_Lumpur\n\n"
            "Promote only runs within your set hours. 🔥",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏰ View Schedule", callback_data="schedule_menu")],
                [InlineKeyboardButton(text="⬅️ Back",          callback_data="main_menu")],
            ]),
        )
    else:
        await message.answer("❌ Failed to save schedule. Try again.", reply_markup=back_to_menu_kb())


# ─────────────────────────────────────────────
# Padam Jadual
# ─────────────────────────────────────────────

@router.callback_query(F.data == "schedule_delete_confirm")
async def cb_schedule_delete_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🗑 *Remove Schedule?*\n\n"
        "Promote will run 24/7 with no time limit.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Remove", callback_data="schedule_delete_do"),
                InlineKeyboardButton(text="❌ Cancel",       callback_data="schedule_menu"),
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
        "✅ *Schedule removed.*\n\nPromote now running 24/7. 🚀",
        parse_mode="Markdown",
        reply_markup=_schedule_menu_kb(False),
    )
