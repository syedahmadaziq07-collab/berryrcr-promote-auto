from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards import groups_selection_kb, back_to_menu_kb
from services.telethon_service import fetch_user_groups

router = Router()


class GroupsFSM(StatesGroup):
    selecting = State()


_temp_groups: dict = {}
_temp_selected: dict = {}


async def _load_groups(uid: int, send_fn, edit_fn, state: FSMContext):
    session = await db.get_session(uid)
    if not session:
        await send_fn(
            "⚠️ *Sila sambungkan akaun Telegram anda dahulu!*\n\nTekan 📱 Sambung Akaun.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    sub = await db.get_active_subscription(uid)
    if not sub:
        await send_fn(
            "⚠️ *Anda perlu beli Userbot dahulu!*\n\nTekan 🛒 Beli Userbot.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    msg = await send_fn("⏳ Memuat senarai kumpulan anda...")
    try:
        groups = await fetch_user_groups(session["session_string"])
        if not groups:
            await msg.edit_text(
                "ℹ️ Tiada kumpulan ditemui. Pastikan akaun anda sudah menyertai sekurang-kurangnya satu kumpulan.",
                reply_markup=back_to_menu_kb(),
            )
            return

        _temp_groups[uid] = groups
        saved = await db.get_selected_groups(uid)
        selected_ids = {int(row["group_id"]) for row in saved}
        _temp_selected[uid] = selected_ids

        await state.set_state(GroupsFSM.selecting)
        await msg.edit_text(
            f"👥 *Pilih Kumpulan Promote*\n\n"
            f"Ditemui *{len(groups)}* kumpulan. Tekan untuk pilih/nyahpilih.\n"
            f"✅ = dipilih | ◻️ = tidak dipilih",
            parse_mode="Markdown",
            reply_markup=groups_selection_kb(groups, selected_ids),
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ Gagal memuatkan kumpulan: {str(e)}\n\nSila cuba lagi.",
            reply_markup=back_to_menu_kb(),
        )


# ─────────────────────────────────────────────
# Reply keyboard trigger
# ─────────────────────────────────────────────

@router.message(F.text == "👥 Pilih Kumpulan")
async def msg_select_groups(message: Message, state: FSMContext):
    await _load_groups(message.from_user.id, message.answer, None, state)


# ─────────────────────────────────────────────
# Inline callback handlers
# ─────────────────────────────────────────────

@router.callback_query(F.data == "select_groups")
async def cb_select_groups(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id

    session = await db.get_session(uid)
    if not session:
        await callback.answer("⚠️ Sila sambungkan akaun Telegram anda dahulu!", show_alert=True)
        return

    sub = await db.get_active_subscription(uid)
    if not sub:
        await callback.answer("⚠️ Anda perlu beli Userbot dahulu!", show_alert=True)
        return

    msg = await callback.message.edit_text("⏳ Memuat senarai kumpulan anda...")
    try:
        groups = await fetch_user_groups(session["session_string"])
        if not groups:
            await msg.edit_text(
                "ℹ️ Tiada kumpulan ditemui. Pastikan akaun anda sudah menyertai sekurang-kurangnya satu kumpulan.",
                reply_markup=back_to_menu_kb(),
            )
            return

        _temp_groups[uid] = groups
        saved = await db.get_selected_groups(uid)
        selected_ids = {int(row["group_id"]) for row in saved}
        _temp_selected[uid] = selected_ids

        await state.set_state(GroupsFSM.selecting)
        await msg.edit_text(
            f"👥 *Pilih Kumpulan Promote*\n\n"
            f"Ditemui *{len(groups)}* kumpulan. Tekan untuk pilih/nyahpilih.\n"
            f"✅ = dipilih | ◻️ = tidak dipilih",
            parse_mode="Markdown",
            reply_markup=groups_selection_kb(groups, selected_ids),
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ Gagal memuatkan kumpulan: {str(e)}\n\nSila cuba lagi.",
            reply_markup=back_to_menu_kb(),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("toggle_group_"), GroupsFSM.selecting)
async def cb_toggle_group(callback: CallbackQuery):
    uid = callback.from_user.id
    group_id = int(callback.data.replace("toggle_group_", ""))
    groups = _temp_groups.get(uid, [])
    selected = _temp_selected.get(uid, set())

    if group_id in selected:
        selected.discard(group_id)
    else:
        selected.add(group_id)
    _temp_selected[uid] = selected

    await callback.message.edit_reply_markup(reply_markup=groups_selection_kb(groups, selected))
    await callback.answer()


@router.callback_query(F.data == "save_groups", GroupsFSM.selecting)
async def cb_save_groups(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    groups = _temp_groups.get(uid, [])
    selected = _temp_selected.get(uid, set())

    if not selected:
        await callback.answer("⚠️ Sila pilih sekurang-kurangnya satu kumpulan!", show_alert=True)
        return

    selected_groups = [g for g in groups if g["id"] in selected]
    await db.save_selected_groups(uid, selected_groups)

    _temp_groups.pop(uid, None)
    _temp_selected.pop(uid, None)
    await state.clear()

    await callback.message.edit_text(
        f"✅ *{len(selected_groups)} kumpulan berjaya disimpan!*\n\n"
        f"Bot akan menghantar promosi ke kumpulan yang dipilih sahaja.\n\n"
        f"Langkah seterusnya: Tetapkan mesej promosi anda.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer("✅ Kumpulan disimpan!")
