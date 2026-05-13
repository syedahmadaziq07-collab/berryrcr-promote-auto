"""
handlers/buat_userbot.py — 📚 Buat Userbot:
  • Sambung akaun Telegram via Telethon OTP
  • Aktifkan pelan PLUS / PRO
  • Pindah / putus sambungan userbot
"""

import logging
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
from services import scheduler_service

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

async def _cleanup_pending(uid: int):
    """Putuskan sambungan Telethon client dan buang dari _pending dict."""
    if uid in _pending:
        try:
            client = _pending[uid].get("client")
            if client and client.is_connected():
                await client.disconnect()
        except Exception:
            pass
        finally:
            _pending.pop(uid, None)


def _mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]


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
    userbot_rec = await db.get_userbot(uid)   # canonical source — userbots table
    session     = await db.get_session(uid)
    sub         = await db.get_active_subscription(uid)

    if userbot_rec:
        userbot_id = userbot_rec.get("userbot_id", "—")
        plan_name  = sub["plan"] if sub else "Tiada (belum diaktifkan)"

        if session:
            phone_masked = _mask_phone(session.get("phone_number", ""))
            tg_user      = session.get("tg_username") or ""
            acc_line     = f"@{tg_user}" if tg_user else f"`{phone_masked}`"
            has_session  = True
        else:
            acc_line    = "_Belum disambung_"
            has_session = False

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
            reply_markup=buat_userbot_kb(
                has_userbot=True,
                has_plan=sub is not None,
                has_session=has_session,
            ),
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
    await _cleanup_pending(uid)
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
        await _cleanup_pending(uid)
        await state.clear()
        await msg.edit_text(
            "❌ Gagal menghantar kod OTP.\n\n"
            "Sila semak nombor telefon anda dan cuba lagi.\n"
            "Pastikan nombor bermula dengan `+` dan kod negara.",
            parse_mode="Markdown",
        )
        await message.answer("Kembali ke menu:", reply_markup=main_menu_kb())


# ─────────────────────────────────────────────
# FSM: OTP
# ─────────────────────────────────────────────

@router.message(BuatUserbotFSM.waiting_otp)
async def process_otp(message: Message, state: FSMContext):
    uid = message.from_user.id
    otp = message.text.strip().replace(" ", "") if message.text else ""
    pending = _pending.get(uid)

    if not pending:
        await state.clear()
        await message.answer(
            "⚠️ Sesi anda telah tamat.\n"
            "Sila mulakan semula proses sambung akaun.",
            reply_markup=main_menu_kb(),
        )
        return

    if not otp.isdigit():
        await message.answer(
            "❌ Kod OTP tidak sah.\n"
            "Sila masukkan nombor sahaja.\n\n"
            "Contoh jika OTP `12345`:\n`1 2 3 4 5` (dengan jarak)",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
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
                "❌ Kod OTP tidak sah. Sila masukkan semula.\n\n"
                "Contoh jika OTP `12345`: taip `1 2 3 4 5` (dengan jarak)",
                reply_markup=cancel_kb(),
            )
        elif "PHONE_CODE_EXPIRED" in err:
            await _cleanup_pending(uid)
            await state.clear()
            await msg.edit_text("❌ Kod OTP telah tamat tempoh. Sila mula semula.")
            await message.answer("Kembali ke menu:", reply_markup=main_menu_kb())
        else:
            await _cleanup_pending(uid)
            await state.clear()
            await msg.edit_text(
                "❌ Pengesahan gagal. Sila cuba lagi atau hubungi @berryrcr untuk bantuan."
            )
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
                "❌ Kata laluan 2FA tidak betul. Sila cuba lagi:"
            )
        else:
            await msg.edit_text(
                "❌ Pengesahan 2FA gagal. Sila cuba lagi atau hubungi @berryrcr untuk bantuan."
            )


# ─────────────────────────────────────────────
# Finalise Login — simpan session & papar ID Userbot
# ─────────────────────────────────────────────

async def _finalise_login(uid: int, client, phone: str, msg, state: FSMContext):
    try:
        me = await client.get_me()
        tg_username = me.username or ""
        session_str = await get_session_string(client)
        await _cleanup_pending(uid)

        # ── Jana atau guna semula UB-ID yang sedia ada ──
        existing_ub = await db.get_userbot(uid)
        if existing_ub and existing_ub.get("userbot_id"):
            userbot_id = existing_ub["userbot_id"]
            logger.info("_finalise_login REUSE UB-ID uid=%s userbot_id=%s", uid, userbot_id)
        else:
            userbot_id = db._generate_userbot_id(uid)
            logger.info("_finalise_login GENERATE uid=%s userbot_id=%s", uid, userbot_id)

        # ── Step 1: Simpan session (termasuk userbot_id) ──
        await db.save_session(
            uid, phone, session_str,
            tg_username=tg_username,
            userbot_id=userbot_id,
        )
        logger.info("_finalise_login SAVE SESSION uid=%s", uid)

        # ── Step 2: Daftar dalam userbots table (WAJIB — backup lookup) ──
        registered = await db.ensure_userbot_registered(uid, userbot_id)
        if registered:
            logger.info("_finalise_login REGISTER USERBOTS OK uid=%s userbot_id=%s", uid, userbot_id)
        else:
            logger.error("_finalise_login REGISTER USERBOTS GAGAL uid=%s userbot_id=%s", uid, userbot_id)

        # ── Step 3: Verify — semak semula dari DB ──
        saved = await db.get_session(uid)
        if saved:
            saved_ub = saved.get("userbot_id", "")
            if saved_ub == userbot_id:
                logger.info("_finalise_login VERIFY sessions.userbot_id OK: %s", saved_ub)
            else:
                logger.warning(
                    "_finalise_login VERIFY MISMATCH — sessions.userbot_id='%s' expected='%s' "
                    "(column mungkin belum wujud — userbots table digunakan sebagai backup)",
                    saved_ub, userbot_id
                )
        else:
            logger.error("_finalise_login VERIFY — session tidak dijumpai selepas save! uid=%s", uid)

        acc_display = f"@{tg_username}" if tg_username else f"`{_mask_phone(phone)}`"

        await msg.edit_text(
            "✅ *Userbot berjaya dipasang!*\n\n"
            f"🆔 ID Userbot:\n`{userbot_id}`\n\n"
            f"📱 Akaun:\n{acc_display}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "⚠️ _Simpan ID Userbot ini! Gunakan untuk Log Masuk Token jika akaun anda kena limit/banned._\n\n"
            "Langkah seterusnya:\n"
            "• Aktifkan pelan PLUS/PRO\n"
            "• Guna ⚙️ Tetapan untuk konfigurasi mesej & jarak masa",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()

    except Exception as e:
        logger.error("_finalise_login error uid=%s: %s", uid, e)
        await _cleanup_pending(uid)
        await msg.edit_text(
            "❌ Gagal menyimpan sesi. Sila cuba lagi atau hubungi @berryrcr untuk bantuan.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()


# ─────────────────────────────────────────────
# Putuskan Sambungan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "disconnect_account")
async def cb_disconnect(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    await callback.answer("⏳ Memutuskan sambungan...")
    scheduler_service.stop_promo_job(uid)
    await db.set_promo_running(uid, False)
    await db.delete_session(uid)
    await state.clear()
    await callback.message.answer(
        "✅ *Akaun Berjaya Diputuskan*\n\n"
        "Semua promosi telah dihentikan.\n"
        "Tekan *📚 Buat Userbot* untuk sambung semula.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )


# ─────────────────────────────────────────────
# Aktifkan Pelan PLUS / PRO
# ─────────────────────────────────────────────

_ACTIVATE_MAP = {
    "activate_plus":    "PLUS",
    "activate_pro":     "PRO",
    "activate_premium": "PREMIUM",
}
_CONFIRM_MAP = {
    "confirm_activate_plus":    "PLUS",
    "confirm_activate_pro":     "PRO",
    "confirm_activate_premium": "PREMIUM",
}


@router.callback_query(F.data.in_(set(_ACTIVATE_MAP.keys())))
async def cb_activate_plan(callback: CallbackQuery):
    plan_key = _ACTIVATE_MAP[callback.data]
    plan     = COIN_PLANS[plan_key]
    uid      = callback.from_user.id

    logger.info("cb_activate_plan: uid=%s plan=%s", uid, plan_key)

    balance = await db.get_wallet(uid)
    if balance < plan["coins"]:
        await callback.answer(
            f"⚠️ Baki tidak mencukupi! Perlu {plan['coins']} syiling, ada {balance}.",
            show_alert=True,
        )
        return

    await callback.answer()
    text = (
        f"📋 *Sahkan Naiktaraf Pelan*\n\n"
        f"Pelan: *{plan['name']}*\n"
        f"Kos: *{plan['coins']:,} Syiling*\n"
        f"Baki semasa: *{balance:,} Syiling*\n"
        f"Baki selepas: *{balance - plan['coins']:,} Syiling*\n\n"
        f"Teruskan?"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown",
        reply_markup=plan_confirm_kb(plan_key),
    )


@router.callback_query(F.data.in_(set(_CONFIRM_MAP.keys())))
async def cb_confirm_activate(callback: CallbackQuery):
    plan_key = _CONFIRM_MAP[callback.data]
    plan     = COIN_PLANS[plan_key]
    uid      = callback.from_user.id

    logger.info("cb_confirm_activate: uid=%s plan=%s — mula proses", uid, plan_key)
    await callback.answer("⏳ Memproses...")

    ok = await db.deduct_coins(uid, plan["coins"], f"Naiktaraf pelan {plan['name']}")
    if not ok:
        balance = await db.get_wallet(uid)
        logger.warning("cb_confirm_activate: uid=%s baki tidak cukup — ada %d perlu %d", uid, balance, plan["coins"])
        await callback.message.edit_text(
            "⚠️ *Baki tidak mencukupi!*\n\nSila topup syiling dahulu.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    await db.create_subscription(uid, plan_key)
    logger.info("cb_confirm_activate: uid=%s pelan=%s BERJAYA diaktifkan", uid, plan_key)
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
    userbot_rec = await db.get_userbot(uid)   # canonical source
    if not userbot_rec or not userbot_rec.get("userbot_id"):
        await callback.answer("⚠️ Anda tiada userbot untuk dipindahkan!", show_alert=True)
        return

    userbot_id = userbot_rec["userbot_id"]
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

    target_ub = await db.get_userbot(target_id)  # canonical check
    if target_ub:
        await message.answer(
            f"⚠️ Penerima *{target['full_name']}* sudah mempunyai userbot.",
            parse_mode="Markdown",
            reply_markup=cancel_kb(),
        )
        await state.clear()
        return

    my_ub    = await db.get_userbot(uid)
    userbot_id = my_ub["userbot_id"] if my_ub else "—"

    await db.transfer_userbot_session(uid, target_id)
    await state.clear()

    await message.answer(
        f"✅ *Userbot Berjaya Dipindahkan!*\n\n"
        f"🆔 ID Userbot: `{userbot_id}`\n"
        f"Pemilik baharu: *{target['full_name']}* (`{target_id}`)",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
