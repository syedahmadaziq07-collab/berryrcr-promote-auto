import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from keyboards import back_to_menu_kb, groups_selection_kb
from services.telethon_service import fetch_user_groups, resolve_entity

router = Router()
logger = logging.getLogger(__name__)


class GroupsFSM(StatesGroup):
    selecting    = State()
    adding_manual = State()


_temp_groups: dict = {}
_temp_selected: dict = {}


def _groups_manage_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁️ Lihat Kumpulan",   callback_data="view_groups"),
            InlineKeyboardButton(text="➕ Tambah Kumpulan",  callback_data="add_group_manual"),
        ],
        [
            InlineKeyboardButton(text="✂️ Buang Kumpulan",   callback_data="remove_group_menu"),
            InlineKeyboardButton(text="🧹 Kosongkan Semua",  callback_data="clear_groups_confirm"),
        ],
        [
            InlineKeyboardButton(text="🔄 Pilih dari Senarai", callback_data="select_groups_list"),
        ],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
    ])


def _remove_group_list_kb(groups: list) -> InlineKeyboardMarkup:
    buttons = []
    for g in groups:
        title = (g.get("group_name") or g.get("group_title") or "Tanpa nama")[:28]
        buttons.append([
            InlineKeyboardButton(
                text=f"✂️ {title}",
                callback_data=f"rm_grp_{g['group_id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="groups_manage")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _confirm_remove_kb(group_id: str, group_title: str) -> InlineKeyboardMarkup:
    safe_title = group_title[:20]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ya, Buang",  callback_data=f"rm_grp_confirm_{group_id}"),
            InlineKeyboardButton(text="❌ Batal",       callback_data="remove_group_menu"),
        ]
    ])


def _confirm_clear_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ya, Kosongkan Semua", callback_data="clear_groups_do"),
            InlineKeyboardButton(text="❌ Batal",                callback_data="groups_manage"),
        ]
    ])


# ─────────────────────────────────────────────
# Entry: Menu Urus Kumpulan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "groups_manage")
async def cb_groups_manage(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid    = callback.from_user.id
    groups = await db.get_selected_groups(uid)
    await callback.message.edit_text(
        f"👥 *Urus Kumpulan*\n\n"
        f"Kumpulan dipilih: *{len(groups)} kumpulan*\n\n"
        "Pilih tindakan:",
        parse_mode="Markdown",
        reply_markup=_groups_manage_kb(),
    )


# ─────────────────────────────────────────────
# 👁️ Lihat Kumpulan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "view_groups")
async def cb_view_groups(callback: CallbackQuery):
    await callback.answer()
    uid    = callback.from_user.id
    groups = await db.get_selected_groups(uid)

    if not groups:
        await callback.message.edit_text(
            "👁️ *SENARAI KUMPULAN AKTIF*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_Tiada kumpulan dipilih._\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=_groups_manage_kb(),
        )
        return

    lines = []
    for i, g in enumerate(groups, 1):
        title = g.get("group_name") or g.get("group_title") or "Tanpa nama"
        lines.append(f"{i}. {title}")

    text = (
        "👁️ *SENARAI KUMPULAN AKTIF*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) + "\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Jumlah: *{len(groups)} kumpulan dipilih*"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=_groups_manage_kb()
    )


# ─────────────────────────────────────────────
# ➕ Tambah Kumpulan Secara Manual
# ─────────────────────────────────────────────

@router.callback_query(F.data == "add_group_manual")
async def cb_add_group_manual(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid     = callback.from_user.id
    session = await db.get_session(uid)
    if not session:
        await callback.answer("⚠️ Sila sambung akaun Telegram dahulu!", show_alert=True)
        return

    await callback.message.edit_text(
        "➕ *Tambah Kumpulan Manual*\n\n"
        "Hantar ID kumpulan atau username:\n\n"
        "Contoh:\n"
        "• `-1001234567890`\n"
        "• `@namagrup`\n\n"
        "_Bot akan sahkan kumpulan sebelum disimpan._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="groups_manage")]
        ]),
    )
    await state.set_state(GroupsFSM.adding_manual)


@router.message(GroupsFSM.adding_manual)
async def process_add_group_manual(message: Message, state: FSMContext):
    await state.clear()
    uid     = message.from_user.id
    raw     = message.text.strip()
    session = await db.get_session(uid)

    if not session:
        await message.answer(
            "⚠️ Sila sambung akaun Telegram dahulu!",
            reply_markup=back_to_menu_kb(),
        )
        return

    wait = await message.answer("⏳ Menyahkan kumpulan...")
    try:
        entity = await resolve_entity(session["session_string"], raw)
        if not entity:
            await wait.edit_text(
                "❌ *Kumpulan tidak dijumpai.*\n\n"
                "Pastikan ID atau username betul dan userbot sudah menyertai kumpulan tersebut.",
                parse_mode="Markdown",
                reply_markup=back_to_menu_kb(),
            )
            return

        group_id    = str(entity["id"])
        group_title = entity["title"]
        group_uname = entity.get("username")
        target_type = entity.get("target_type", "group")
        access_hash = entity.get("access_hash")
        type_icon   = "📢" if target_type == "channel" else ("👥" if target_type == "supergroup" else "💬")

        added = await db.add_single_group(
            uid, group_id, group_title, group_uname,
            target_type=target_type,
            access_hash=str(access_hash) if access_hash else None,
        )
        if added:
            await wait.edit_text(
                f"✅ *Target Berjaya Ditambah!*\n\n"
                f"{type_icon} {group_title}\n"
                f"🆔 `{group_id}`\n"
                f"📌 Jenis: *{target_type}*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="👥 Urus Kumpulan", callback_data="groups_manage")],
                    [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")],
                ]),
            )
        else:
            await wait.edit_text(
                f"ℹ️ *Kumpulan sudah ada dalam senarai.*\n\n{group_title}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="👥 Urus Kumpulan", callback_data="groups_manage")],
                ]),
            )
    except Exception as e:
        logger.warning("process_add_group_manual error uid=%s: %s", uid, e)
        await wait.edit_text(
            f"❌ *Gagal menambah kumpulan.*\n\nRalat: `{str(e)}`",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )


# ─────────────────────────────────────────────
# ✂️ Buang Kumpulan (dengan pengesahan)
# ─────────────────────────────────────────────

@router.callback_query(F.data == "remove_group_menu")
async def cb_remove_group_menu(callback: CallbackQuery):
    await callback.answer()
    uid    = callback.from_user.id
    groups = await db.get_selected_groups(uid)

    if not groups:
        await callback.message.edit_text(
            "✂️ *Buang Kumpulan*\n\nTiada kumpulan untuk dibuang.",
            parse_mode="Markdown",
            reply_markup=_groups_manage_kb(),
        )
        return

    await callback.message.edit_text(
        "✂️ *Buang Kumpulan*\n\nPilih kumpulan yang ingin dibuang:",
        parse_mode="Markdown",
        reply_markup=_remove_group_list_kb(groups),
    )


@router.callback_query(F.data.startswith("rm_grp_") & ~F.data.startswith("rm_grp_confirm_"))
async def cb_rm_grp_ask(callback: CallbackQuery):
    await callback.answer()
    uid      = callback.from_user.id
    group_id = callback.data.replace("rm_grp_", "")
    groups   = await db.get_selected_groups(uid)
    group    = next((g for g in groups if g["group_id"] == group_id), None)

    if not group:
        await callback.answer("⚠️ Kumpulan tidak dijumpai.", show_alert=True)
        return

    title = group.get("group_name") or group.get("group_title") or "Tanpa nama"
    await callback.message.edit_text(
        f"✂️ *Buang Kumpulan?*\n\n"
        f"Adakah anda pasti mahu membuang:\n"
        f"📍 *{title}*",
        parse_mode="Markdown",
        reply_markup=_confirm_remove_kb(group_id, title),
    )


@router.callback_query(F.data.startswith("rm_grp_confirm_"))
async def cb_rm_grp_confirm(callback: CallbackQuery):
    await callback.answer()
    uid      = callback.from_user.id
    group_id = callback.data.replace("rm_grp_confirm_", "")

    ok = await db.remove_single_group(uid, group_id)
    if ok:
        groups = await db.get_selected_groups(uid)
        await callback.message.edit_text(
            f"✅ *Kumpulan berjaya dibuang.*\n\n"
            f"Baki kumpulan: *{len(groups)} kumpulan*",
            parse_mode="Markdown",
            reply_markup=_groups_manage_kb(),
        )
    else:
        await callback.message.edit_text(
            "❌ Gagal membuang kumpulan. Sila cuba lagi.",
            reply_markup=_groups_manage_kb(),
        )


# ─────────────────────────────────────────────
# 🧹 Kosongkan Semua Kumpulan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "clear_groups_confirm")
async def cb_clear_groups_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🧹 *Kosongkan Semua Kumpulan?*\n\n"
        "Adakah anda pasti mahu memadamkan *SEMUA* kumpulan dari senarai promote?",
        parse_mode="Markdown",
        reply_markup=_confirm_clear_kb(),
    )


@router.callback_query(F.data == "clear_groups_do")
async def cb_clear_groups_do(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    count = await db.clear_all_groups(uid)
    await callback.message.edit_text(
        f"✅ *{count} kumpulan telah dipadamkan.*\n\n"
        "Senarai kumpulan kini kosong.",
        parse_mode="Markdown",
        reply_markup=_groups_manage_kb(),
    )


# ─────────────────────────────────────────────
# 🔄 Pilih dari Senarai Kumpulan (existing flow)
# ─────────────────────────────────────────────

@router.callback_query(F.data == "select_groups_list")
async def cb_select_groups_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid     = callback.from_user.id
    session = await db.get_session(uid)
    if not session:
        await callback.answer("⚠️ Sila sambung akaun dahulu!", show_alert=True)
        return

    sub = await db.get_active_subscription(uid)
    if not sub:
        await callback.answer("⚠️ Sila aktifkan pelan PLUS/PRO dahulu!", show_alert=True)
        return

    msg = await callback.message.edit_text("⏳ Memuat senarai kumpulan anda...")
    try:
        groups = await fetch_user_groups(session["session_string"])
        if not groups:
            await msg.edit_text(
                "ℹ️ Tiada kumpulan ditemui. Pastikan akaun sudah menyertai sekurang-kurangnya satu kumpulan.",
                reply_markup=back_to_menu_kb(),
            )
            return

        _temp_groups[uid]   = groups
        saved               = await db.get_selected_groups(uid)
        selected_ids        = {int(row["group_id"]) for row in saved}
        _temp_selected[uid] = selected_ids

        await state.set_state(GroupsFSM.selecting)
        await msg.edit_text(
            f"👥 *Pilih Kumpulan Promote*\n\n"
            f"Ditemui *{len(groups)}* kumpulan.\n"
            "✅ = dipilih | ◻️ = tidak dipilih",
            parse_mode="Markdown",
            reply_markup=groups_selection_kb(groups, selected_ids),
        )
    except Exception as e:
        logger.error("fetch_user_groups error uid=%s: %s", uid, e)
        await msg.edit_text(
            f"❌ Gagal memuat kumpulan: `{str(e)}`",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )


@router.callback_query(F.data == "select_groups")
async def cb_select_groups(callback: CallbackQuery, state: FSMContext):
    callback.data = "select_groups_list"
    await cb_select_groups_list(callback, state)


@router.callback_query(F.data.startswith("toggle_group_"))
async def cb_toggle_group(callback: CallbackQuery):
    await callback.answer()
    uid      = callback.from_user.id
    group_id = int(callback.data.replace("toggle_group_", ""))
    groups   = _temp_groups.get(uid, [])
    selected = _temp_selected.get(uid, set())

    if group_id in selected:
        selected.discard(group_id)
    else:
        selected.add(group_id)
    _temp_selected[uid] = selected

    await callback.message.edit_reply_markup(reply_markup=groups_selection_kb(groups, selected))


@router.callback_query(F.data == "save_groups")
async def cb_save_groups(callback: CallbackQuery, state: FSMContext):
    uid      = callback.from_user.id
    groups   = _temp_groups.get(uid, [])
    selected = _temp_selected.get(uid, set())

    if not selected:
        await callback.answer("⚠️ Sila pilih sekurang-kurangnya satu kumpulan!", show_alert=True)
        return

    await callback.answer("✅ Menyimpan kumpulan...")
    selected_groups = [g for g in groups if g["id"] in selected]
    await db.save_selected_groups(uid, selected_groups)
    _temp_groups.pop(uid, None)
    _temp_selected.pop(uid, None)
    await state.clear()

    await callback.message.edit_text(
        f"✅ *{len(selected_groups)} kumpulan berjaya disimpan!*",
        parse_mode="Markdown",
        reply_markup=_groups_manage_kb(),
    )
