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


class MessagesFSM(StatesGroup):
    waiting_new_message = State()


def _messages_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁️ Lihat Mesej",    callback_data="bcast_view"),
            InlineKeyboardButton(text="➕ Tambah Mesej",   callback_data="bcast_add"),
        ],
        [
            InlineKeyboardButton(text="✂️ Buang Mesej",    callback_data="bcast_remove_menu"),
            InlineKeyboardButton(text="🧹 Kosongkan Semua", callback_data="bcast_clear_confirm"),
        ],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
    ])


def _remove_messages_kb(messages: list) -> InlineKeyboardMarkup:
    buttons = []
    for msg in messages:
        content = msg.get("text_content") or f"[{msg.get('content_type', 'fail')}]"
        preview = (content[:28] + "...") if len(content) > 28 else content
        buttons.append([
            InlineKeyboardButton(
                text=f"✂️ {preview}",
                callback_data=f"bcast_del_{msg['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="bcast_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _confirm_clear_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ya, Padam Semua", callback_data="bcast_clear_do"),
            InlineKeyboardButton(text="❌ Batal",            callback_data="bcast_menu"),
        ]
    ])


async def _get_userbot_id(uid: int):
    session = await db.get_session(uid)
    if session and session.get("userbot_id"):
        return session["userbot_id"]
    userbot = await db.get_userbot(uid)
    return userbot["userbot_id"] if userbot else None


# ─────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────

@router.callback_query(F.data == "bcast_menu")
async def cb_bcast_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid      = callback.from_user.id
    ub_id    = await _get_userbot_id(uid)
    count    = await db.count_broadcast_messages(ub_id) if ub_id else 0
    await callback.message.edit_text(
        "📋 *Senarai Mesej Sebarkan*\n\n"
        f"Jumlah mesej: *{count}/10*\n\n"
        "Urus mesej yang akan dihantar secara bergilir-gilir:",
        parse_mode="Markdown",
        reply_markup=_messages_menu_kb(),
    )


# ─────────────────────────────────────────────
# 👁️ Lihat Mesej
# ─────────────────────────────────────────────

@router.callback_query(F.data == "bcast_view")
async def cb_bcast_view(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)

    if not ub_id:
        await callback.message.edit_text(
            "⚠️ Sila sambung akaun dan aktifkan pelan dahulu.",
            reply_markup=back_to_menu_kb(),
        )
        return

    messages = await db.get_broadcast_messages(ub_id)

    if not messages:
        await callback.message.edit_text(
            "📋 *SENARAI MESEJ SEBARKAN*\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_Tiada mesej dalam senarai._\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=_messages_menu_kb(),
        )
        return

    lines = []
    for i, msg in enumerate(messages, 1):
        content = msg.get("text_content") or f"[{msg.get('content_type', 'fail')}]"
        preview = (content[:50] + "...") if len(content) > 50 else content
        lines.append(f"{i}. {preview}")

    text = (
        "📋 *SENARAI MESEJ SEBARKAN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) + "\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Jumlah: *{len(messages)} mesej*"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=_messages_menu_kb())


# ─────────────────────────────────────────────
# ➕ Tambah Mesej
# ─────────────────────────────────────────────

@router.callback_query(F.data == "bcast_add")
async def cb_bcast_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)

    if not ub_id:
        await callback.answer("⚠️ Sila sambung akaun dahulu!", show_alert=True)
        return

    count = await db.count_broadcast_messages(ub_id)
    if count >= 10:
        await callback.answer("⚠️ Had maksimum 10 mesej telah dicapai!", show_alert=True)
        return

    await callback.message.edit_text(
        f"➕ *Tambah Mesej Sebarkan*\n\n"
        f"Mesej semasa: *{count}/10*\n\n"
        "Hantar mesej yang ingin ditambah.\n"
        "Sokong: teks, gambar, atau video.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="bcast_menu")]
        ]),
    )
    await state.set_state(MessagesFSM.waiting_new_message)


@router.message(MessagesFSM.waiting_new_message)
async def process_new_message(message: Message, state: FSMContext):
    await state.clear()
    uid   = message.from_user.id
    ub_id = await _get_userbot_id(uid)

    if not ub_id:
        await message.answer("⚠️ Ralat: Userbot ID tidak dijumpai.", reply_markup=back_to_menu_kb())
        return

    try:
        if message.photo:
            content_type = "photo"
            file_id      = message.photo[-1].file_id
            text_content = message.caption or ""
        elif message.video:
            content_type = "video"
            file_id      = message.video.file_id
            text_content = message.caption or ""
        elif message.text:
            content_type = "text"
            file_id      = None
            text_content = message.text
        else:
            await message.answer(
                "⚠️ Jenis mesej tidak disokong. Hantar teks, gambar, atau video sahaja.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Kembali", callback_data="bcast_menu")]
                ]),
            )
            return

        added = await db.add_broadcast_message(ub_id, uid, content_type, text_content, file_id)
        if added:
            count = await db.count_broadcast_messages(ub_id)
            await message.answer(
                f"✅ *Mesej berjaya ditambah!*\n\nJumlah mesej: *{count}/10*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Lihat Senarai", callback_data="bcast_menu")],
                    [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")],
                ]),
            )
        else:
            await message.answer(
                "⚠️ Had 10 mesej telah dicapai atau ralat berlaku.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Kembali", callback_data="bcast_menu")]
                ]),
            )
    except Exception as e:
        logger.warning("process_new_message error uid=%s: %s", uid, e)
        await message.answer("❌ Gagal menambah mesej. Sila cuba lagi.", reply_markup=back_to_menu_kb())


# ─────────────────────────────────────────────
# ✂️ Buang Mesej
# ─────────────────────────────────────────────

@router.callback_query(F.data == "bcast_remove_menu")
async def cb_bcast_remove_menu(callback: CallbackQuery):
    await callback.answer()
    uid      = callback.from_user.id
    ub_id    = await _get_userbot_id(uid)
    messages = await db.get_broadcast_messages(ub_id) if ub_id else []

    if not messages:
        await callback.message.edit_text(
            "✂️ *Buang Mesej*\n\nTiada mesej untuk dibuang.",
            parse_mode="Markdown",
            reply_markup=_messages_menu_kb(),
        )
        return

    await callback.message.edit_text(
        "✂️ *Buang Mesej*\n\nPilih mesej yang ingin dibuang:",
        parse_mode="Markdown",
        reply_markup=_remove_messages_kb(messages),
    )


@router.callback_query(F.data.startswith("bcast_del_"))
async def cb_bcast_del(callback: CallbackQuery):
    await callback.answer()
    msg_id = callback.data.replace("bcast_del_", "")
    ok     = await db.delete_broadcast_message(msg_id)
    uid    = callback.from_user.id
    ub_id  = await _get_userbot_id(uid)
    count  = await db.count_broadcast_messages(ub_id) if ub_id else 0

    if ok:
        await callback.message.edit_text(
            f"✅ *Mesej berjaya dibuang.*\n\nBaki mesej: *{count}/10*",
            parse_mode="Markdown",
            reply_markup=_messages_menu_kb(),
        )
    else:
        await callback.message.edit_text(
            "❌ Gagal membuang mesej.",
            reply_markup=_messages_menu_kb(),
        )


# ─────────────────────────────────────────────
# 🧹 Kosongkan Semua Mesej
# ─────────────────────────────────────────────

@router.callback_query(F.data == "bcast_clear_confirm")
async def cb_bcast_clear_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🧹 *Kosongkan Semua Mesej?*\n\n"
        "Adakah anda pasti mahu memadamkan *SEMUA* mesej dalam senarai sebarkan?",
        parse_mode="Markdown",
        reply_markup=_confirm_clear_kb(),
    )


@router.callback_query(F.data == "bcast_clear_do")
async def cb_bcast_clear_do(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    count = await db.clear_broadcast_messages(ub_id) if ub_id else 0
    await callback.message.edit_text(
        f"✅ *{count} mesej telah dipadamkan.*",
        parse_mode="Markdown",
        reply_markup=_messages_menu_kb(),
    )
