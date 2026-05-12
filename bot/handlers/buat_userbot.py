"""
handlers/buat_userbot.py — 📚 Buat Userbot:
  • Sambung akaun Telegram via Telethon OTP
  • Aktifkan pelan PLUS / PRO
  • Pindah / putus sambungan userbot
"""

import logging
import string
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from config import COIN_PLANS
from keyboards import (
    buat_userbot_kb, plan_confirm_kb,
    back_to_menu_kb, cancel_kb,
    request_phone_kb, remove_kb,
    main_menu_kb,
)
from services.telethon_service import (
    create_client, send_code, sign_in, get_session_string,
)

router = Router()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────

class BuatUserbotFSM(StatesGroup):
    waiting_phone = State()
    waiting_otp   = State()
    waiting_2fa   = State()


class TransferUserbotFSM(StatesGroup):
    waiting_target = State()


_pending: dict = {}   # uid → {"client", "phone", "hash"}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]


def _generate_userbot_id(user_id: int) -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"UB-{user_id}-{suffix}"


async def _ask_for_phone(message: Message, state: FSMContext):
    await message.answer(
        "📚 *Buat Userbot — Sambung Akaun*\n\n"
        "📱 Sila hantar nombor Telegram anda.\n"
        "Contoh: `+60123456789`\n\n"
        "Atau tekan butang *📱 Hantar Nombor* di bawah.",
        parse_mode="Markdown",
        reply_markup=request_phone_kb(),
    )
    await state.set_state(BuatUserbotFSM.waiting_phone)


# ─────────────────────────────────────────────
# 📚 Buat Userbot — Entry Point
# ─────────────────────────────────────────────

@router.message(F.text == "📚 Buat Userbot")
async def msg_buat_userbot(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    session = await db.get_session(uid)
    sub = await db.get_active_subscription(uid)

    if session:
        phone_masked = _mask_phone(session.get("phone_number", ""))
        tg_user = session.get("tg_username") or ""
        acc_line = f"@{tg_user}" if tg_user else f"`{phone_masked}`"
        userbot_id = session.get("userbot_id") or "—"
        plan_name = sub["plan"] if sub else "Tiada (belum diaktifkan)"

        text = (
            "📚 *Userbot Anda*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🆔 ID Userbot: `{userbot_id}`\n"
            f"📱 Akaun: {acc_line}\n"
            f"📋 Pelan: *{plan_name}*\n\n"
            "_Simpan ID Userbot untuk pindah akses jika akaun anda limit/banned._"
        )
        if not sub:
            text += (
                "\n\n━━━━━━━━━━━━━━━\n"
                "⭐ *PLUS — 300 Syiling (RM3)*\n"
                "• Auto promote ke kumpulan pilihan\n"
                "• Footer wajib @berryrcr\n\n"
                "🔥 *PRO — 600 Syiling (RM6)*\n"
                "• Auto promote ke kumpulan pilihan\n"
                "• Boleh tutup footer\n"
                "• Keutamaan sokongan"
            )
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=buat_userbot_kb(has_userbot=True, has_plan=sub is not None, has_session=True),
        )
        return

    await _ask_for_phone(message, state)


# Inline button "Sambung Akaun" dari dalam menu Buat Userbot
@router.callback_query(F.data == "buat_sambung_akaun")
async def cb_buat_sambung_akaun(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "📱 *Sambung Akaun Telegram*\n\n"
        "Sila hantar nombor Telegram anda.\n"
        "Contoh: `+60123456789`\n\n"
        "Atau tekan butang *📱 Hantar Nombor* di bawah.",
        parse_mode="Markdown",
        reply_markup=request_phone_kb(),
    )
    await state.set_state(BuatUserbotFSM.waiting_phone)
    await callback.answer()


# ─────────────────────────────────────────────
# Batal semasa FSM
# ─────────────────────────────────────────────

@router.message(BuatUserbotFSM.waiting_phone, F.text == "❌ Batal")
@router.message(BuatUserbotFSM.waiting_otp, F.text == "❌ Batal")
@router.message(BuatUserbotFSM.waiting_2fa, F.text == "❌ Batal")
async def cancel_flow(message: Message, state: FSMContext):
    uid = message.from_user.id
    _pending.pop(uid, None)
    await state.clear()
    await message.answer(
        "❌ Dibatalkan. Kembali ke menu utama.",
        reply_markup=main_menu_kb(),
    )


# ─────────────────────────────────────────────
# FSM: Nombor Telefon (teks atau contact)
# ─────────────────────────────────────────────

@router.message(BuatUserbotFSM.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    uid = message.from_user.id

    # Ambil nombor dari contact atau teks
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        phone = message.text.strip()
        if not phone.startswith("+") or len(phone) < 8:
            await message.answer(
                "⚠️ Format nombor tidak sah.\n\n"
                "Contoh: `+60123456789`\n\n"
                "Atau tekan butang *📱 Hantar Nombor*.",
                parse_mode="Markdown",
                reply_markup=request_phone_kb(),
            )
            return
    else:
        await message.answer(
            "⚠️ Sila hantar nombor telefon atau tekan butang *📱 Hantar Nombor*.",
            parse_mode="Markdown",
            reply_markup=request_phone_kb(),
        )
        return

    msg = await message.answer(
        "⏳ Menghantar kod OTP...",
        reply_markup=remove_kb(),
    )
    try:
        client = await create_client(uid)
        phone_code_hash = await send_code(client, phone)
        _pending[uid] = {"client": client, "phone": phone, "hash": phone_code_hash}
        await state.update_data(phone=phone)
        await state.set_state(BuatUserbotFSM.waiting_otp)
        await msg.edit_text(
            "📨 Kod OTP telah dihantar melalui Telegram rasmi.\n\n"
            "Sila hantar kod OTP anda *dengan jarak*.\n"
            "Contoh jika OTP `12345`:\n`1 2 3 4 5`",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("send_code error uid=%s: %s", uid, e)
        await msg.edit_text(
            f"❌ Gagal hantar OTP.\n\nRalat: `{str(e)}`\n\nSila semak nombor dan cuba lagi.",
            parse_mode="Markdown",
        )
        _pending.pop(uid, None)
        await state.clear()
        await message.answer("Kembali ke menu:", reply_markup=main_menu_kb())


# ─────────────────────────────────────────────
# FSM: OTP
# ─────────────────────────────────────────────

@router.message(BuatUserbotFSM.waiting_otp)
async def process_otp(message: Message, state: FSMContext):
    uid = message.from_user.id
    otp = message.text.strip().replace(" ", "")
    pending = _pending.get(uid)

    if not pending:
        await message.answer(
            "❌ Sesi tamat. Sila mula semula.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    msg = await message.answer("⏳ Mengesahkan OTP...")
    try:
        client = pending["client"]
        phone  = pending["phone"]
        result = await sign_in(client, phone, otp, pending["hash"])

        if result == "2fa_required":
            await state.set_state(BuatUserbotFSM.waiting_2fa)
            await msg.edit_text(
                "🔐 Akaun anda mempunyai pengesahan dua langkah.\n\n"
                "Sila hantar kata laluan 2FA anda.",
            )
        else:
            await _finalise_login(uid, client, phone, msg, state)

    except Exception as e:
        err = str(e)
        logger.error("sign_in error uid=%s: %s", uid, err)
        if "PHONE_CODE_INVALID" in err:
            await msg.edit_text(
                "❌ Kod OTP tidak sah. Sila masukkan semula (dengan jarak):"
            )
        elif "PHONE_CODE_EXPIRED" in err:
            await msg.edit_text("❌ Kod OTP tamat tempoh. Sila mula semula.")
            _pending.pop(uid, None)
            await state.clear()
            await message.answer("Kembali ke menu:", reply_markup=main_menu_kb())
        else:
            await msg.edit_text(
                f"❌ Gagal log masuk.\n\nRalat: `{err}`\n\nSila cuba lagi.",
                parse_mode="Markdown",
            )
            _pending.pop(uid, None)
            await state.clear()
            await message.answer("Kembali ke menu:", reply_markup=main_menu_kb())


# ─────────────────────────────────────────────
# FSM: 2FA Password
# ─────────────────────────────────────────────

@router.message(BuatUserbotFSM.waiting_2fa)
async def process_2fa(message: Message, state: FSMContext):
    uid = message.from_user.id
    password = message.text.strip()
    pending = _pending.get(uid)

    if not pending:
        await message.answer(
            "❌ Sesi tamat. Sila mula semula.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    msg = await message.answer("⏳ Mengesahkan kata laluan...")
    try:
        client = pending["client"]
        phone  = pending["phone"]
        await client.sign_in(password=password)
        await _finalise_login(uid, client, phone, msg, state)
    except Exception as e:
        err = str(e)
        logger.error("2fa error uid=%s (masked)", uid)
        if "PASSWORD_HASH_INVALID" in err or "The password is invalid" in err.lower():
            await msg.edit_text(
                "❌ Kata laluan 2FA salah. Sila masukkan semula:"
            )
        else:
            await msg.edit_text(
                f"❌ Ralat pengesahan.\n\n`{err}`\n\nSila cuba lagi.",
                parse_mode="Markdown",
            )


# ─────────────────────────────────────────────
# Finalise Login — simpan session & papar ID Userbot
# ─────────────────────────────────────────────

async def _finalise_login(uid: int, client, phone: str, msg, state: FSMContext):
    try:
        me = await client.get_me()
        tg_username = me.username or ""
        session_str = await get_session_string(client)
        await client.disconnect()
        _pending.pop(uid, None)

        userbot_id = _generate_userbot_id(uid)

        await db.save_session(
            uid, phone, session_str,
            tg_username=tg_username,
            userbot_id=userbot_id,
        )

        acc_display = f"@{tg_username}" if tg_username else f"`{_mask_phone(phone)}`"

        await msg.edit_text(
            "✅ *Userbot berjaya dipasang!*\n\n"
            f"🆔 ID Userbot:\n`{userbot_id}`\n\n"
            f"📱 Akaun:\n{acc_display}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "_Simpan ID Userbot ini untuk pindah akses jika akaun anda limit/banned._\n\n"
            "Langkah seterusnya:\n"
            "• Aktifkan pelan PLUS/PRO\n"
            "• Guna ⚙️ Tetapan untuk konfigurasi mesej & jarak masa",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()

    except Exception as e:
        logger.error("_finalise_login error uid=%s: %s", uid, e)
        await msg.edit_text(
            f"❌ Gagal simpan sesi.\n\nRalat: `{str(e)}`\n\nSila cuba lagi.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()


# ─────────────────────────────────────────────
# Putuskan Sambungan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "disconnect_account")
async def cb_disconnect(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    await db.delete_session(uid)
    await db.set_promo_running(uid, False)
    await state.clear()
    await callback.message.answer(
        "✅ *Akaun Berjaya Diputuskan*\n\n"
        "Semua promosi telah dihentikan.\n"
        "Tekan *📚 Buat Userbot* untuk sambung semula.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )
    await callback.answer()


# ─────────────────────────────────────────────
# Aktifkan Pelan PLUS / PRO
# ─────────────────────────────────────────────

@router.callback_query(F.data.in_({"activate_plus", "activate_pro"}))
async def cb_activate_plan(callback: CallbackQuery):
    plan_key = "PLUS" if callback.data == "activate_plus" else "PRO"
    plan = COIN_PLANS[plan_key]
    uid = callback.from_user.id

    session = await db.get_session(uid)
    if not session:
        await callback.answer("⚠️ Sambung akaun dahulu!", show_alert=True)
        return

    balance = await db.get_wallet(uid)
    if balance < plan["coins"]:
        await callback.answer(
            f"⚠️ Baki tidak mencukupi! Perlu {plan['coins']} syiling, ada {balance}.",
            show_alert=True,
        )
        return

    # Jawab SEBELUM edit_text
    await callback.answer()
    text = (
        f"📋 *Sahkan Aktivasi Pelan*\n\n"
        f"Pelan: *{plan['name']}*\n"
        f"Kos: *{plan['coins']} Syiling*\n"
        f"Baki semasa: *{balance:,} Syiling*\n"
        f"Baki selepas: *{balance - plan['coins']:,} Syiling*\n\n"
        f"Teruskan?"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown",
        reply_markup=plan_confirm_kb(plan_key),
    )


@router.callback_query(F.data.in_({"confirm_activate_plus", "confirm_activate_pro"}))
async def cb_confirm_activate(callback: CallbackQuery):
    plan_key = "PLUS" if "plus" in callback.data else "PRO"
    plan = COIN_PLANS[plan_key]
    uid = callback.from_user.id

    # Jawab SEBELUM deduct_coins (DB call berat)
    await callback.answer("⏳ Memproses...")
    ok = await db.deduct_coins(uid, plan["coins"], f"Aktif pelan {plan['name']}")
    if not ok:
        await callback.message.edit_text(
            "⚠️ *Baki tidak mencukupi!*\n\nSila topup syiling dahulu.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    await db.create_subscription(uid, plan_key)
    await callback.message.edit_text(
        f"✅ *Pelan {plan['name']} Berjaya Diaktifkan!*\n\n"
        "Gunakan *⚙️ Tetapan* untuk konfigurasi kumpulan, mesej & jarak masa.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )


# ─────────────────────────────────────────────
# Pindah Userbot
# ─────────────────────────────────────────────

@router.callback_query(F.data == "transfer_userbot_start")
async def cb_transfer_userbot_start(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    session = await db.get_session(uid)
    if not session or not session.get("userbot_id"):
        await callback.answer("⚠️ Anda tiada userbot untuk dipindahkan!", show_alert=True)
        return

    userbot_id = session["userbot_id"]
    await callback.message.edit_text(
        "📤 *Pindah Userbot*\n\n"
        f"ID Userbot anda: `{userbot_id}`\n\n"
        "⚠️ Userbot akan dipindahkan kepada pengguna lain.\n"
        "Anda *tidak lagi* mempunyai akses selepas pindah.\n\n"
        "Masukkan *ID Telegram* penerima:",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    await state.set_state(TransferUserbotFSM.waiting_target)
    await callback.answer()


@router.message(TransferUserbotFSM.waiting_target)
async def process_transfer_target(message: Message, state: FSMContext):
    uid = message.from_user.id
    text = message.text.strip()

    if not text.isdigit():
        await message.answer(
            "⚠️ Masukkan ID Telegram yang sah (nombor sahaja).",
            reply_markup=cancel_kb(),
        )
        return

    target_id = int(text)
    if target_id == uid:
        await message.answer(
            "⚠️ Anda tidak boleh pindahkan userbot kepada diri sendiri.",
            reply_markup=cancel_kb(),
        )
        return

    target = await db.get_user_by_id(target_id)
    if not target:
        await message.answer(
            "⚠️ Pengguna tidak ditemui. Pastikan penerima pernah guna bot ini.",
            reply_markup=cancel_kb(),
        )
        return

    target_session = await db.get_session(target_id)
    if target_session and target_session.get("userbot_id"):
        await message.answer(
            f"⚠️ Penerima *{target['full_name']}* sudah mempunyai userbot.",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
        await state.clear()
        return

    my_session = await db.get_session(uid)
    userbot_id = my_session["userbot_id"] if my_session else "—"

    await db.transfer_userbot_session(uid, target_id)
    await state.clear()

    await message.answer(
        f"✅ *Userbot Berjaya Dipindahkan!*\n\n"
        f"🆔 ID Userbot: `{userbot_id}`\n"
        f"Pemilik baharu: *{target['full_name']}* (`{target_id}`)",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
