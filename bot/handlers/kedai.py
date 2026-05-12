"""
handlers/kedai.py — Menu Kedai.
Main menu guna Reply Keyboard. Topup guna Inline Keyboard (5 langkah).
"""

import os
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db
from config import ADMIN_ID, USERBOT_PRICE, WEBSITE_URL
from keyboards import (
    kedai_menu_kb,
    beli_userbot_confirm_reply_kb,
    main_menu_kb,
    topup_packages_inline_kb,
    topup_order_summary_kb,
    topup_payment_kb,
    topup_request_admin_kb,
)

router = Router()
logger = logging.getLogger(__name__)

_HERE   = os.path.dirname(os.path.dirname(__file__))
QR_PATH = os.path.join(_HERE, "media", "qr_payment.jpg")


# ─────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────

class TopupFSM(StatesGroup):
    waiting_receipt = State()


class BeliUserbotFSM(StatesGroup):
    waiting_confirm = State()


class SendCoinsFSM(StatesGroup):
    waiting_target = State()
    waiting_amount = State()


class GiftUserbotFSM(StatesGroup):
    waiting_target = State()


# ─────────────────────────────────────────────
# Helper — bina teks info Kedai
# ─────────────────────────────────────────────

async def _kedai_text(uid: int) -> str:
    try:
        balance = await db.get_wallet(uid)
    except Exception as e:
        logger.error("get_wallet gagal uid=%s: %s", uid, e)
        balance = 0

    try:
        session    = await db.get_session(uid)
        ub_id      = session.get("userbot_id", "") if session else ""
        ub_display = f"`{ub_id}`" if ub_id else "Tiada"
    except Exception as e:
        logger.error("get_session gagal uid=%s: %s", uid, e)
        ub_display = "Tiada"

    try:
        sub  = await db.get_active_subscription(uid)
        plan = sub["plan"] if sub else "Tiada"
    except Exception as e:
        logger.error("get_active_subscription gagal uid=%s: %s", uid, e)
        plan = "Tiada"

    return (
        "🛒 *Kedai*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"🪙 Baki Syiling: *{balance:,} Syiling*\n"
        f"🤖 ID Userbot: {ub_display}\n"
        f"📋 Pelan Aktif: *{plan}*"
    )


# ─────────────────────────────────────────────
# ⬅️ KEMBALI — dari FSM state → balik ke Kedai
# ─────────────────────────────────────────────

@router.message(TopupFSM.waiting_receipt,       F.text == "⬅️ Kembali")
@router.message(BeliUserbotFSM.waiting_confirm, F.text == "⬅️ Kembali")
@router.message(SendCoinsFSM.waiting_target,    F.text == "⬅️ Kembali")
@router.message(SendCoinsFSM.waiting_amount,    F.text == "⬅️ Kembali")
@router.message(GiftUserbotFSM.waiting_target,  F.text == "⬅️ Kembali")
async def cancel_kedai_fsm(message: Message, state: FSMContext):
    await state.clear()
    text = await _kedai_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())


@router.message(F.text == "⬅️ Kembali")
async def msg_kembali(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 *Menu Utama*\n\nSila pilih tindakan:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


# ─────────────────────────────────────────────
# 🛒 KEDAI — Entry Point
# ─────────────────────────────────────────────

@router.message(F.text == "🛒 Kedai")
async def msg_kedai(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    try:
        text = await _kedai_text(uid)
        await message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())
    except Exception as e:
        logger.error("msg_kedai error uid=%s: %s", uid, e)
        await message.answer("⚠️ Sistem bermasalah. Sila cuba lagi.", reply_markup=main_menu_kb())


# ─────────────────────────────────────────────
# 🏆 PAPAN PENDAHULU
# ─────────────────────────────────────────────

@router.message(F.text == "🏆 Papan Pendahulu")
async def msg_leaderboard(message: Message):
    leaders = await db.get_leaderboard(limit=10)

    if not leaders:
        await message.answer(
            "🏆 *Papan Pendahulu*\n\nBelum ada data lagi.",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines  = []
    for i, entry in enumerate(leaders):
        user_id = entry["user_id"]
        total   = entry["total"]
        user    = await db.get_user_by_id(user_id)
        name    = user["full_name"] if user else str(user_id)
        lines.append(f"{medals[i]} {i + 1}. {name} — *{total:,} syiling*")

    text = "🏆 *Papan Pendahulu*\n━━━━━━━━━━━━━━━\n\n" + "\n".join(lines)
    await message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())


# ─────────────────────────────────────────────
# 💳 TOPUP SYILING — Langkah 1: Papar pakej (Inline Keyboard)
# ─────────────────────────────────────────────

@router.message(F.text == "💳 Topup Syiling")
async def msg_topup(message: Message, state: FSMContext):
    # BUG 1 FIX: Jika user sudah dalam proses topup, jangan buka baru
    current_state = await state.get_state()
    if current_state == TopupFSM.waiting_receipt.state:
        await message.answer(
            "⚠️ *Anda masih dalam proses topup yang belum selesai.*\n\n"
            "Sila hantar screenshot resit pembayaran anda.\n"
            "Atau tekan butang *❌ Batal* untuk batalkan.",
            parse_mode="Markdown",
        )
        return

    await state.clear()
    # BUG 2 FIX: Reply segera dulu, DB call lepas itu
    try:
        balance = await db.get_wallet(message.from_user.id)
    except Exception:
        balance = 0
    text = (
        "💳 *Topup Syiling*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"Baki semasa: *{balance:,} Syiling*\n\n"
        "Pilih pakej topup:"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=topup_packages_inline_kb())


# ─────────────────────────────────────────────
# 💳 TOPUP — Langkah 2: ORDER SUMMARY
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("topup_pkg:"))
async def cb_topup_pkg(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # BUG 2 FIX: WAJIB baris pertama

    # BUG 1 FIX: Guard double-tap — jika sudah dalam state lain, abaikan
    current_state = await state.get_state()
    if current_state == TopupFSM.waiting_receipt.state:
        return

    try:
        _, coins_str, amount_str = callback.data.split(":")
        coins  = int(coins_str)
        amount = float(amount_str)
    except Exception as e:
        logger.error("topup_pkg parse error: %s", e)
        await callback.message.answer("⚠️ Ralat. Sila cuba lagi.")
        return

    await state.update_data(coins=coins, amount=amount)

    text = (
        "🧾 *ORDER SUMMARY*\n"
        "━━━━━━━━━━━━━━━\n"
        f"- Produk   : Topup Syiling\n"
        f"- Pakej    : {coins:,} Syiling\n"
        f"- Harga    : RM{amount:.2f}\n"
        f"- Total    : RM{amount:.2f}\n\n"
        "Sila teruskan ke pembayaran."
    )
    try:
        await callback.message.edit_text(
            text, parse_mode="Markdown",
            reply_markup=topup_order_summary_kb(coins, amount),
        )
    except Exception as e:
        logger.error("topup_pkg edit_text error: %s", e)
        await callback.message.answer(text, parse_mode="Markdown",
                                      reply_markup=topup_order_summary_kb(coins, amount))


# ─────────────────────────────────────────────
# 💳 TOPUP — Langkah 3: Proceed to Payment → Generate order_id → QR
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("topup_proceed:"))
async def cb_topup_proceed(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()  # BUG 2 FIX: WAJIB baris pertama

    # BUG 1 FIX: Guard double-tap — jika sudah dalam waiting_receipt, abaikan
    current_state = await state.get_state()
    if current_state == TopupFSM.waiting_receipt.state:
        return

    try:
        _, coins_str, amount_str = callback.data.split(":")
        coins  = int(coins_str)
        amount = float(amount_str)
    except Exception as e:
        logger.error("topup_proceed parse error: %s", e)
        await callback.message.answer("⚠️ Ralat data. Sila pilih pakej semula.")
        return

    uid      = callback.from_user.id
    username = callback.from_user.username or str(uid)

    # BUG 3 FIX: Jana order_id DULU sebelum DB call
    import random as _random
    order_id = f"ORD{_random.randint(10000000, 99999999)}"

    # Cuba simpan ke DB — jika gagal, tunjuk error dan stop
    try:
        await db.create_topup_request(
            order_id=order_id,
            user_id=uid,
            username=username,
            coins=coins,
            amount_rm=amount,
        )
    except Exception as db_error:
        logger.error("create_topup_request gagal uid=%s: %s", uid, db_error)
        await callback.message.answer(
            "⚠️ Ralat pangkalan data. Sila cuba lagi atau hubungi @berryrcr."
        )
        return

    await state.update_data(order_id=order_id, coins=coins, amount=amount)

    caption = (
        "💳 *PAYMENT DETAILS*\n"
        "━━━━━━━━━━━━━━━\n"
        f"Order ID: `{order_id}`\n"
        f"Amount: RM{amount:.2f}\n\n"
        "Scan QR code untuk bayar 👇\n\n"
        "Selepas bayar, tekan butang di bawah:"
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        if os.path.exists(QR_PATH):
            qr_file = FSInputFile(QR_PATH)
            await bot.send_photo(
                uid, qr_file, caption=caption,
                parse_mode="Markdown",
                reply_markup=topup_payment_kb(order_id),
            )
        else:
            await bot.send_message(
                uid, caption,
                parse_mode="Markdown",
                reply_markup=topup_payment_kb(order_id),
            )
    except Exception as e:
        logger.error("topup_proceed send msg error uid=%s: %s", uid, e)
        await bot.send_message(
            uid,
            f"⚠️ Gagal hantar QR. Sila hubungi @berryrcr.\n\nOrder ID anda: `{order_id}`",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────────
# 💳 TOPUP — Langkah 4: I Have Paid → tunggu resit
# ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("topup_paid:"))
async def cb_topup_paid(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  # BUG 2 FIX: WAJIB baris pertama

    # BUG 1 FIX: Guard double-tap — jika sudah dalam waiting_receipt, abaikan
    current_state = await state.get_state()
    if current_state == TopupFSM.waiting_receipt.state:
        return

    order_id = callback.data[len("topup_paid:"):]
    data     = await state.get_data()
    if not data.get("order_id"):
        await state.update_data(order_id=order_id)

    await state.set_state(TopupFSM.waiting_receipt)

    try:
        await callback.message.edit_caption(
            caption="📎 Sila hantar screenshot resit pembayaran anda.",
            reply_markup=None,
        )
    except Exception:
        try:
            await callback.message.answer("📎 Sila hantar screenshot resit pembayaran anda.")
        except Exception as e:
            logger.error("topup_paid answer error: %s", e)


# ─────────────────────────────────────────────
# 💳 TOPUP — Langkah 5: Terima resit → simpan → notify admin
# ─────────────────────────────────────────────

@router.message(TopupFSM.waiting_receipt, F.photo)
async def process_topup_receipt(message: Message, state: FSMContext, bot: Bot):
    data     = await state.get_data()
    order_id = data.get("order_id", "—")
    coins    = data.get("coins", 0)
    amount   = data.get("amount", 0.0)
    uid      = message.from_user.id
    username = message.from_user.username or str(uid)

    receipt_file_id = message.photo[-1].file_id

    try:
        await db.update_topup_receipt(order_id, receipt_file_id)
    except Exception as e:
        logger.error("update_topup_receipt gagal uid=%s: %s", uid, e)
        await message.answer(
            "⚠️ Ralat sistem. Sila cuba lagi atau hubungi @berryrcr.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await state.clear()

    await message.answer(
        f"✅ Resit diterima. Pesanan anda sedang disemak oleh admin.\n"
        f"Order ID: `{order_id}`",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )

    try:
        uname_display = f"@{username}" if message.from_user.username else str(uid)
        caption = (
            "🔔 *TOPUP REQUEST BARU*\n"
            "━━━━━━━━━━━━━━━\n"
            f"👤 Username : {uname_display}\n"
            f"🆔 User ID  : `{uid}`\n"
            f"📋 Order ID : `{order_id}`\n"
            f"💰 Amount   : RM{amount:.2f}\n"
            f"🪙 Syiling  : {coins:,}"
        )
        await bot.send_photo(
            ADMIN_ID,
            receipt_file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=topup_request_admin_kb(order_id),
        )
    except Exception as e:
        logger.warning("Gagal notifikasi admin resit: %s", e)


@router.message(TopupFSM.waiting_receipt)
async def process_topup_receipt_invalid(message: Message):
    await message.answer(
        "⚠️ Sila *upload gambar resit* pembayaran anda.\n\n"
        "Hantar screenshot bukti pembayaran sebagai gambar.",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# 💳 TOPUP — Batal (inline button)
# ─────────────────────────────────────────────

@router.callback_query(F.data == "topup_cancel")
async def cb_topup_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("❌ Dibatalkan.")
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    uid  = callback.from_user.id
    try:
        text = await _kedai_text(uid)
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())
    except Exception as e:
        logger.error("topup_cancel kedai_text error uid=%s: %s", uid, e)
        await callback.message.answer("🛒 Kembali ke Kedai.", reply_markup=kedai_menu_kb())


# ─────────────────────────────────────────────
# 🛍 BELI USERBOT
# ─────────────────────────────────────────────

@router.message(F.text == "🛍 Beli Userbot")
async def msg_beli_userbot(message: Message, state: FSMContext):
    await state.clear()
    uid     = message.from_user.id
    balance = await db.get_wallet(uid)
    session = await db.get_session(uid)
    ub_id   = session.get("userbot_id", "") if session else ""

    if ub_id:
        await message.answer(
            "🤖 *Anda Sudah Mempunyai Userbot*\n\n"
            f"ID Userbot anda: `{ub_id}`\n\n"
            "Setiap akaun hanya boleh mempunyai satu userbot.\n"
            "Gunakan menu *📚 Buat Userbot* untuk urus userbot anda.",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    text = (
        "🛍 *Beli Userbot*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"Kos: *{USERBOT_PRICE} Syiling*\n"
        f"Baki anda: *{balance:,} Syiling*\n\n"
        "Selepas beli, sistem akan hasilkan *ID Userbot* unik untuk anda.\n"
        "ID ini boleh digunakan untuk pindah userbot ke akaun lain.\n\n"
        "Adakah anda ingin meneruskan?"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=beli_userbot_confirm_reply_kb())
    await state.set_state(BeliUserbotFSM.waiting_confirm)


@router.message(BeliUserbotFSM.waiting_confirm, F.text == "✅ Ya, Beli Userbot")
async def process_confirm_beli_userbot(message: Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()

    if USERBOT_PRICE > 0:
        ok = await db.deduct_coins(uid, USERBOT_PRICE, "Beli Userbot")
        if not ok:
            balance = await db.get_wallet(uid)
            await message.answer(
                f"⚠️ *Baki tidak mencukupi!*\n\n"
                f"Kos: *{USERBOT_PRICE} Syiling*\n"
                f"Baki anda: *{balance:,} Syiling*\n\n"
                "Topup syiling dahulu melalui 💳 Topup Syiling.",
                parse_mode="Markdown",
                reply_markup=kedai_menu_kb(),
            )
            return

    userbot_id = await db.create_userbot(uid)
    await message.answer(
        "✅ *Userbot Berjaya Dicipta!*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"🤖 ID Userbot anda:\n`{userbot_id}`\n\n"
        "⚠️ *Simpan ID ini dengan baik!*\n"
        "ID ini boleh digunakan untuk memindahkan userbot ke akaun lain.\n\n"
        "Langkah seterusnya:\n"
        "• Aktifkan pelan PLUS atau PRO\n"
        "• Sambungkan akaun Telegram\n\n"
        "Guna menu *📚 Buat Userbot* untuk langkah seterusnya.",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )


# ─────────────────────────────────────────────
# 📤 HANTAR SYILING
# ─────────────────────────────────────────────

@router.message(F.text == "📤 Hantar Syiling")
async def msg_hantar_syiling(message: Message, state: FSMContext):
    await state.clear()
    uid     = message.from_user.id
    balance = await db.get_wallet(uid)

    if balance == 0:
        await message.answer(
            "⚠️ Baki syiling anda kosong!\n\nTopup dahulu melalui 💳 Topup Syiling.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await message.answer(
        "📤 *Hantar Syiling*\n\n"
        f"Baki anda: *{balance:,} Syiling*\n\n"
        "Sila masukkan *ID Telegram* penerima:\n"
        "_(Penerima mesti pernah guna bot ini)_\n\n"
        "_Tekan ⬅️ Kembali untuk batal._",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )
    await state.set_state(SendCoinsFSM.waiting_target)


@router.message(SendCoinsFSM.waiting_target)
async def process_send_target(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    if not text.isdigit():
        await message.answer(
            "⚠️ Sila masukkan ID Telegram yang sah (nombor sahaja).\n"
            "Contoh: `123456789`\n\n"
            "_Tekan ⬅️ Kembali untuk batal._",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    target_id = int(text)
    if target_id == message.from_user.id:
        await message.answer(
            "⚠️ Anda tidak boleh hantar syiling kepada diri sendiri.",
            reply_markup=kedai_menu_kb(),
        )
        return

    target = await db.get_user_by_id(target_id)
    if not target:
        await message.answer(
            "⚠️ Pengguna tidak ditemui. Pastikan penerima pernah guna bot ini.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await state.update_data(target_id=target_id, target_name=target["full_name"])
    await state.set_state(SendCoinsFSM.waiting_amount)
    await message.answer(
        f"✅ Penerima: *{target['full_name']}* (`{target_id}`)\n\n"
        "Sila masukkan *jumlah syiling* yang ingin dihantar:\n\n"
        "_Tekan ⬅️ Kembali untuk batal._",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )


@router.message(SendCoinsFSM.waiting_amount)
async def process_send_amount(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) <= 0:
        await message.answer(
            "⚠️ Sila masukkan jumlah yang sah (nombor positif):",
            reply_markup=kedai_menu_kb(),
        )
        return

    amount  = int(text)
    uid     = message.from_user.id
    balance = await db.get_wallet(uid)

    if amount > balance:
        await message.answer(
            f"⚠️ Baki tidak mencukupi!\n\nBaki anda: *{balance:,} Syiling*",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    data        = await state.get_data()
    target_id   = data["target_id"]
    target_name = data["target_name"]

    ok = await db.transfer_coins(uid, target_id, amount, "Hadiah syiling")
    await state.clear()

    if ok:
        await message.answer(
            f"✅ *{amount:,} Syiling berjaya dihantar!*\n\n"
            f"Penerima: *{target_name}* (`{target_id}`)\n"
            f"Baki anda sekarang: *{balance - amount:,} Syiling*",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
    else:
        await message.answer(
            "❌ Gagal hantar syiling. Sila cuba lagi.",
            reply_markup=kedai_menu_kb(),
        )


# ─────────────────────────────────────────────
# 🎁 GIFT USERBOT
# ─────────────────────────────────────────────

@router.message(F.text == "🎁 Gift Userbot")
async def msg_gift_userbot(message: Message, state: FSMContext):
    await state.clear()
    uid     = message.from_user.id
    session = await db.get_session(uid)
    ub_id   = session.get("userbot_id", "") if session else ""

    if not ub_id:
        await message.answer(
            "⚠️ Anda tiada userbot untuk dihadiahkan!\n\n"
            "Beli userbot dahulu melalui 🛍 Beli Userbot.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await message.answer(
        "🎁 *Gift Userbot*\n\n"
        f"ID Userbot anda: `{ub_id}`\n\n"
        "Sila masukkan *ID Telegram* penerima:\n"
        "_(Penerima mesti pernah guna bot ini)_\n\n"
        "_Tekan ⬅️ Kembali untuk batal._",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )
    await state.set_state(GiftUserbotFSM.waiting_target)


@router.message(GiftUserbotFSM.waiting_target)
async def process_gift_target(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer(
            "⚠️ Sila masukkan ID Telegram yang sah (nombor sahaja).\n\n"
            "_Tekan ⬅️ Kembali untuk batal._",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    target_id = int(text)
    uid       = message.from_user.id

    if target_id == uid:
        await message.answer(
            "⚠️ Anda tidak boleh hadiahkan userbot kepada diri sendiri.",
            reply_markup=kedai_menu_kb(),
        )
        return

    target = await db.get_user_by_id(target_id)
    if not target:
        await message.answer(
            "⚠️ Pengguna tidak ditemui. Pastikan penerima pernah guna bot ini.",
            reply_markup=kedai_menu_kb(),
        )
        return

    target_session = await db.get_session(target_id)
    if target_session and target_session.get("userbot_id"):
        await message.answer(
            f"⚠️ Penerima *{target['full_name']}* sudah mempunyai userbot.",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        await state.clear()
        return

    my_session = await db.get_session(uid)
    ub_id      = my_session.get("userbot_id", "—") if my_session else "—"

    await db.transfer_userbot_session(uid, target_id)
    await state.clear()

    await message.answer(
        f"🎁 *Userbot Berjaya Dihadiahkan!*\n\n"
        f"🆔 ID Userbot: `{ub_id}`\n"
        f"Pemilik baharu: *{target['full_name']}* (`{target_id}`)\n\n"
        "Userbot anda telah dipindahkan.",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )


# ─────────────────────────────────────────────
# 🌐 LAMAN UTAMA
# ─────────────────────────────────────────────

@router.message(F.text == "🌐 Laman Utama")
async def msg_laman_utama(message: Message):
    await message.answer(
        "🌐 *Laman Utama*\n\n"
        f"Layari atau hubungi kami di:\n{WEBSITE_URL}\n\n"
        "Untuk sokongan: @berryrcr",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )
