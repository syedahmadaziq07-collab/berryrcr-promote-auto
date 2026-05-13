import logging
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


class ExpertFSM(StatesGroup):
    waiting_group_message = State()


def _expert_menu_kb(expert_on: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Matikan Mod Lanjutan" if expert_on else "🟢 Hidupkan Mod Lanjutan"
    toggle_cb   = "expert_off" if expert_on else "expert_on"
    buttons = [
        [InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)],
    ]
    if expert_on:
        buttons.append([
            InlineKeyboardButton(text="📝 Tetap Mesej Kumpulan", callback_data="expert_set_group_msg"),
        ])
        buttons.append([
            InlineKeyboardButton(text="👁️ Lihat Mesej Kumpulan", callback_data="expert_view_msgs"),
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _pick_group_kb(groups: list, group_msgs: dict) -> InlineKeyboardMarkup:
    buttons = []
    for g in groups:
        gid   = g["group_id"]
        title = (g.get("group_name") or g.get("group_title") or "Tanpa nama")[:25]
        has   = "✅ " if gid in group_msgs else "◻️ "
        buttons.append([
            InlineKeyboardButton(text=f"{has}{title}", callback_data=f"expert_pick_{gid}")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="expert_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────

@router.callback_query(F.data == "expert_menu")
async def cb_expert_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid        = callback.from_user.id
    expert_on  = await db.get_expert_mode(uid)
    groups     = await db.get_selected_groups(uid)
    group_msgs = await db.get_all_group_messages(uid)

    status_icon = "🟢 Aktif" if expert_on else "🔴 Tidak Aktif"
    set_count   = len(group_msgs)

    text = (
        "🔬 *MOD LANJUTAN*\n\n"
        f"Status: *{status_icon}*\n\n"
        "Mod Lanjutan membolehkan anda menetapkan mesej yang *berbeza* untuk setiap kumpulan.\n\n"
        f"Kumpulan dipilih: *{len(groups)}*\n"
        f"Mesej ditetapkan: *{set_count} kumpulan*"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=_expert_menu_kb(expert_on))


# ─────────────────────────────────────────────
# Toggle Mod Lanjutan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "expert_on")
async def cb_expert_on(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await db.set_expert_mode(uid, True)
    await callback.message.edit_text(
        "🔬 *MOD LANJUTAN*\n\n"
        "Status: *🟢 Aktif*\n\n"
        "Anda kini boleh menetapkan mesej khusus untuk setiap kumpulan.",
        parse_mode="Markdown",
        reply_markup=_expert_menu_kb(True),
    )


@router.callback_query(F.data == "expert_off")
async def cb_expert_off(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await db.set_expert_mode(uid, False)
    await callback.message.edit_text(
        "🔬 *MOD LANJUTAN*\n\n"
        "Status: *🔴 Tidak Aktif*\n\n"
        "Semua kumpulan akan menerima mesej yang sama.",
        parse_mode="Markdown",
        reply_markup=_expert_menu_kb(False),
    )


# ─────────────────────────────────────────────
# Tetapkan Mesej Kumpulan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "expert_set_group_msg")
async def cb_expert_set_group_msg(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid        = callback.from_user.id
    groups     = await db.get_selected_groups(uid)
    group_msgs = await db.get_all_group_messages(uid)

    if not groups:
        await callback.message.edit_text(
            "⚠️ Tiada kumpulan dipilih.\n\nSila pilih kumpulan dahulu melalui ⚙️ Tetapan.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Kembali", callback_data="expert_menu")]
            ]),
        )
        return

    await callback.message.edit_text(
        "📝 *Tetapkan Mesej untuk Kumpulan*\n\n"
        "✅ = sudah ada mesej khusus\n"
        "◻️ = guna mesej umum\n\n"
        "Pilih kumpulan untuk tetapkan mesej:",
        parse_mode="Markdown",
        reply_markup=_pick_group_kb(groups, group_msgs),
    )


@router.callback_query(F.data.startswith("expert_pick_"))
async def cb_expert_pick_group(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid      = callback.from_user.id
    group_id = callback.data.replace("expert_pick_", "")

    groups = await db.get_selected_groups(uid)
    group  = next((g for g in groups if g["group_id"] == group_id), None)
    title  = (group.get("group_name") or group.get("group_title") or group_id) if group else group_id

    existing = await db.get_group_message(uid, group_id)
    preview  = f"\n\nMesej semasa:\n```{existing[:100]}```" if existing else ""

    await state.update_data(expert_group_id=group_id, expert_group_title=title)
    await callback.message.edit_text(
        f"📝 *Mesej untuk: {title}*{preview}\n\n"
        "Hantar mesej khusus untuk kumpulan ini.\n"
        "_(Footer akan ditambah mengikut pelan)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Padam Mesej Ini", callback_data=f"expert_del_{group_id}")],
            [InlineKeyboardButton(text="❌ Batal", callback_data="expert_set_group_msg")],
        ]),
    )
    await state.set_state(ExpertFSM.waiting_group_message)


@router.message(ExpertFSM.waiting_group_message)
async def process_expert_group_message(message: Message, state: FSMContext):
    data     = await state.get_data()
    group_id = data.get("expert_group_id")
    title    = data.get("expert_group_title", group_id)
    await state.clear()

    uid      = message.from_user.id
    msg_text = message.text

    if not msg_text or not msg_text.strip():
        await message.answer("⚠️ Mesej tidak boleh kosong.", reply_markup=back_to_menu_kb())
        return
    if len(msg_text) > 4000:
        await message.answer("⚠️ Mesej terlalu panjang (maksimum 4,000 aksara).", reply_markup=back_to_menu_kb())
        return

    ok = await db.set_group_message(uid, group_id, msg_text.strip())
    if ok:
        await message.answer(
            f"✅ *Mesej untuk {title} berjaya disimpan!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Tetapkan Kumpulan Lain", callback_data="expert_set_group_msg")],
                [InlineKeyboardButton(text="🔙 Menu Lanjutan", callback_data="expert_menu")],
            ]),
        )
    else:
        await message.answer("❌ Gagal menyimpan mesej.", reply_markup=back_to_menu_kb())


@router.callback_query(F.data.startswith("expert_del_"))
async def cb_expert_del_group_msg(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid      = callback.from_user.id
    group_id = callback.data.replace("expert_del_", "")
    await db.delete_group_message(uid, group_id)
    await callback.message.edit_text(
        "✅ *Mesej khusus dipadamkan.*\nKumpulan ini akan guna mesej umum.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="expert_menu")]
        ]),
    )


# ─────────────────────────────────────────────
# Lihat Semua Mesej Kumpulan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "expert_view_msgs")
async def cb_expert_view_msgs(callback: CallbackQuery):
    await callback.answer()
    uid        = callback.from_user.id
    group_msgs = await db.get_all_group_messages(uid)
    groups     = await db.get_selected_groups(uid)

    group_map = {g["group_id"]: (g.get("group_name") or g.get("group_title") or g["group_id"]) for g in groups}

    if not group_msgs:
        text = "👁️ *Mesej Kumpulan (Mod Lanjutan)*\n\n_Tiada mesej khusus ditetapkan._"
    else:
        lines = []
        for gid, msg in group_msgs.items():
            title   = group_map.get(gid, gid)
            preview = (msg[:40] + "...") if len(msg) > 40 else msg
            lines.append(f"📍 *{title}*\n`{preview}`")
        text = "👁️ *Mesej Kumpulan (Mod Lanjutan)*\n\n" + "\n\n".join(lines)

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Kembali", callback_data="expert_menu")]
        ]),
    )
