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


class AutoreplyFSM(StatesGroup):
    waiting_channel    = State()
    waiting_reply_text = State()


def _autoreply_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁️ Lihat Saluran",      callback_data="ar_channels_view"),
            InlineKeyboardButton(text="➕ Tambah Saluran",     callback_data="ar_channels_add"),
        ],
        [
            InlineKeyboardButton(text="✂️ Buang Saluran",      callback_data="ar_channels_remove"),
            InlineKeyboardButton(text="🧹 Kosongkan Saluran",  callback_data="ar_channels_clear_confirm"),
        ],
        [
            InlineKeyboardButton(text="👁️ Lihat Teks Balas",   callback_data="ar_texts_view"),
            InlineKeyboardButton(text="➕ Tambah Teks Balas",  callback_data="ar_texts_add"),
        ],
        [
            InlineKeyboardButton(text="✂️ Buang Teks",         callback_data="ar_texts_remove"),
            InlineKeyboardButton(text="🧹 Kosongkan Teks",     callback_data="ar_texts_clear_confirm"),
        ],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")],
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

@router.callback_query(F.data == "autoreply_menu")
async def cb_autoreply_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    ch    = len(await db.get_autoreply_channels(ub_id)) if ub_id else 0
    tx    = len(await db.get_autoreply_texts(ub_id)) if ub_id else 0
    await callback.message.edit_text(
        "🤖 *Balas Automatik*\n\n"
        f"📡 Saluran/Kumpulan: *{ch}*\n"
        f"💬 Teks Balas: *{tx}*\n\n"
        "Bot akan balas secara automatik apabila ada mesej masuk.",
        parse_mode="Markdown",
        reply_markup=_autoreply_menu_kb(),
    )


# ─────────────────────────────────────────────
# SALURAN
# ─────────────────────────────────────────────

@router.callback_query(F.data == "ar_channels_view")
async def cb_ar_channels_view(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    chs   = await db.get_autoreply_channels(ub_id) if ub_id else []

    if not chs:
        text = (
            "👁️ *SENARAI SALURAN BALAS AUTOMATIK*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_Tiada saluran didaftarkan._\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        lines = [f"{i}. {c.get('channel_name') or c['channel_id']}" for i, c in enumerate(chs, 1)]
        text = (
            "👁️ *SENARAI SALURAN BALAS AUTOMATIK*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) + "\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Jumlah: *{len(chs)} saluran*"
        )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=_autoreply_menu_kb())


@router.callback_query(F.data == "ar_channels_add")
async def cb_ar_channels_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "➕ *Tambah Saluran Balas Automatik*\n\n"
        "Hantar ID atau username saluran/kumpulan:\n\n"
        "Contoh:\n• `-1001234567890`\n• `@namasaluran`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="autoreply_menu")]
        ]),
    )
    await state.set_state(AutoreplyFSM.waiting_channel)


@router.message(AutoreplyFSM.waiting_channel)
async def process_ar_channel(message: Message, state: FSMContext):
    await state.clear()
    uid   = message.from_user.id
    raw   = message.text.strip()
    ub_id = await _get_userbot_id(uid)

    if not ub_id:
        await message.answer("⚠️ Userbot tidak dijumpai.", reply_markup=back_to_menu_kb())
        return

    channel_id   = raw
    channel_name = raw

    try:
        added = await db.add_autoreply_channel(ub_id, uid, channel_id, channel_name)
        if added:
            await message.answer(
                f"✅ *Saluran berjaya ditambah!*\n\n`{channel_id}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Kembali", callback_data="autoreply_menu")]
                ]),
            )
        else:
            await message.answer(
                "ℹ️ Saluran sudah ada dalam senarai.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Kembali", callback_data="autoreply_menu")]
                ]),
            )
    except Exception as e:
        logger.warning("process_ar_channel error: %s", e)
        await message.answer("❌ Gagal menambah saluran.", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "ar_channels_remove")
async def cb_ar_channels_remove(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    chs   = await db.get_autoreply_channels(ub_id) if ub_id else []

    if not chs:
        await callback.message.edit_text(
            "✂️ Tiada saluran untuk dibuang.",
            reply_markup=_autoreply_menu_kb(),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"✂️ {c.get('channel_name') or c['channel_id']}",
            callback_data=f"ar_ch_del_{c['id']}",
        )]
        for c in chs
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="autoreply_menu")])
    await callback.message.edit_text(
        "✂️ *Buang Saluran*\n\nPilih saluran untuk dibuang:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("ar_ch_del_"))
async def cb_ar_ch_del(callback: CallbackQuery):
    await callback.answer()
    ch_uuid = callback.data.replace("ar_ch_del_", "")
    ok      = await db.delete_autoreply_channel(ch_uuid)
    await callback.message.edit_text(
        "✅ *Saluran berjaya dibuang.*" if ok else "❌ Gagal membuang saluran.",
        parse_mode="Markdown",
        reply_markup=_autoreply_menu_kb(),
    )


@router.callback_query(F.data == "ar_channels_clear_confirm")
async def cb_ar_channels_clear_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🧹 *Kosongkan Semua Saluran?*\n\n"
        "Adakah anda pasti mahu memadamkan semua saluran balas automatik?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ya, Kosongkan", callback_data="ar_channels_clear_do"),
                InlineKeyboardButton(text="❌ Batal",          callback_data="autoreply_menu"),
            ]
        ]),
    )


@router.callback_query(F.data == "ar_channels_clear_do")
async def cb_ar_channels_clear_do(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    count = await db.clear_autoreply_channels(ub_id) if ub_id else 0
    await callback.message.edit_text(
        f"✅ *{count} saluran telah dipadamkan.*",
        parse_mode="Markdown",
        reply_markup=_autoreply_menu_kb(),
    )


# ─────────────────────────────────────────────
# TEKS BALAS
# ─────────────────────────────────────────────

@router.callback_query(F.data == "ar_texts_view")
async def cb_ar_texts_view(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    txts  = await db.get_autoreply_texts(ub_id) if ub_id else []

    if not txts:
        text = (
            "👁️ *SENARAI TEKS BALAS AUTOMATIK*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_Tiada teks balas ditetapkan._\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        lines = []
        for i, t in enumerate(txts, 1):
            preview = (t["teks"][:50] + "...") if len(t["teks"]) > 50 else t["teks"]
            lines.append(f"{i}. {preview}")
        text = (
            "👁️ *SENARAI TEKS BALAS AUTOMATIK*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) + "\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Jumlah: *{len(txts)} teks*\n"
            "_Bot akan pilih secara rawak._"
        )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=_autoreply_menu_kb())


@router.callback_query(F.data == "ar_texts_add")
async def cb_ar_texts_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "➕ *Tambah Teks Balas Automatik*\n\n"
        "Hantar teks yang akan digunakan untuk membalas secara automatik.\n\n"
        "_Bot akan pilih secara rawak jika ada berbilang teks._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Batal", callback_data="autoreply_menu")]
        ]),
    )
    await state.set_state(AutoreplyFSM.waiting_reply_text)


@router.message(AutoreplyFSM.waiting_reply_text)
async def process_ar_text(message: Message, state: FSMContext):
    await state.clear()
    uid   = message.from_user.id
    teks  = message.text
    ub_id = await _get_userbot_id(uid)

    if not teks or not teks.strip():
        await message.answer("⚠️ Teks tidak boleh kosong.", reply_markup=back_to_menu_kb())
        return
    if not ub_id:
        await message.answer("⚠️ Userbot tidak dijumpai.", reply_markup=back_to_menu_kb())
        return

    try:
        ok = await db.add_autoreply_text(ub_id, uid, teks.strip())
        if ok:
            count = len(await db.get_autoreply_texts(ub_id))
            await message.answer(
                f"✅ *Teks balas berjaya ditambah!*\n\nJumlah teks: *{count}*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Kembali", callback_data="autoreply_menu")]
                ]),
            )
        else:
            await message.answer("❌ Gagal menambah teks.", reply_markup=back_to_menu_kb())
    except Exception as e:
        logger.warning("process_ar_text error: %s", e)
        await message.answer("❌ Ralat berlaku.", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "ar_texts_remove")
async def cb_ar_texts_remove(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    txts  = await db.get_autoreply_texts(ub_id) if ub_id else []

    if not txts:
        await callback.message.edit_text(
            "✂️ Tiada teks untuk dibuang.",
            reply_markup=_autoreply_menu_kb(),
        )
        return

    buttons = []
    for t in txts:
        preview = (t["teks"][:28] + "...") if len(t["teks"]) > 28 else t["teks"]
        buttons.append([
            InlineKeyboardButton(text=f"✂️ {preview}", callback_data=f"ar_tx_del_{t['id']}")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="autoreply_menu")])
    await callback.message.edit_text(
        "✂️ *Buang Teks Balas*\n\nPilih teks untuk dibuang:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("ar_tx_del_"))
async def cb_ar_tx_del(callback: CallbackQuery):
    await callback.answer()
    tx_uuid = callback.data.replace("ar_tx_del_", "")
    ok      = await db.delete_autoreply_text(tx_uuid)
    await callback.message.edit_text(
        "✅ *Teks berjaya dibuang.*" if ok else "❌ Gagal membuang teks.",
        parse_mode="Markdown",
        reply_markup=_autoreply_menu_kb(),
    )


@router.callback_query(F.data == "ar_texts_clear_confirm")
async def cb_ar_texts_clear_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🧹 *Kosongkan Semua Teks Balas?*\n\n"
        "Adakah anda pasti mahu memadamkan semua teks balas automatik?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ya, Kosongkan", callback_data="ar_texts_clear_do"),
                InlineKeyboardButton(text="❌ Batal",          callback_data="autoreply_menu"),
            ]
        ]),
    )


@router.callback_query(F.data == "ar_texts_clear_do")
async def cb_ar_texts_clear_do(callback: CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    ub_id = await _get_userbot_id(uid)
    count = await db.clear_autoreply_texts(ub_id) if ub_id else 0
    await callback.message.edit_text(
        f"✅ *{count} teks telah dipadamkan.*",
        parse_mode="Markdown",
        reply_markup=_autoreply_menu_kb(),
    )
