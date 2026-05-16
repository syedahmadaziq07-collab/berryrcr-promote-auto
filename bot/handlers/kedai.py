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
from config import ADMIN_ID, USERBOT_PRICE, WEBSITE_URL, COIN_PLANS
from services.order_notifier import notify_new_order
from keyboards import (
    kedai_menu_kb,
    buy_userbot_lifetime_kb,
    beli_userbot_plans_kb,
    tambah_bulan_plans_kb,
    beli_userbot_confirm_kb,
    main_menu_kb,
    topup_packages_inline_kb,
    topup_order_summary_kb,
    topup_payment_kb,
    topup_request_admin_kb,
    plan_duration_kb,
)

router = Router()
logger = logging.getLogger(__name__)

# _HERE  = bot/
# _ROOT  = project root  (workspace/)
_HERE   = os.path.dirname(os.path.dirname(__file__))
_ROOT   = os.path.dirname(_HERE)
QR_PATH = os.path.join(_ROOT, "assets", "payment", "qr.jpg")


def _ensure_qr_dir() -> None:
    """Pastikan folder assets/payment wujud. Log amaran jika QR belum diupload."""
    os.makedirs(os.path.join(_ROOT, "assets", "payment"), exist_ok=True)
    if not os.path.exists(QR_PATH):
        logger.warning(
            "QR image tidak dijumpai: %s — admin perlu upload gambar QR ke assets/payment/qr.jpg",
            QR_PATH,
        )


_ensure_qr_dir()


# ─────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────

class TopupFSM(StatesGroup):
    waiting_receipt = State()


class BeliUserbotFSM(StatesGroup):
    pass   # Tidak digunakan lagi — flow kini sepenuhnya inline callback


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
        userbot_rec = await db.get_userbot(uid)   # canonical source
        ub_id       = userbot_rec.get("userbot_id", "") if userbot_rec else ""
        ub_display  = f"`{ub_id}`" if ub_id else "Tiada"
    except Exception as e:
        logger.error("get_userbot gagal uid=%s: %s", uid, e)
        ub_display = "Tiada"

    try:
        sub  = await db.get_active_subscription(uid)
        plan = sub["plan"] if sub else "Tiada"
    except Exception as e:
        logger.error("get_active_subscription gagal uid=%s: %s", uid, e)
        plan = "Tiada"

    return (
        "🛒 *Shop Zone*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"🪙 Coin Balance:\n*{balance:,} Syiling*\n\n"
        f"🤖 Your Userbot ID:\n{ub_display}\n\n"
        f"📦 Active Plan:\n*{plan}*\n\n"
        "━━━━━━━━━━━━━━━\n\n"
        "⚡ Semua purchase & manage system korang dekat sini.\n\n"
        "Boleh:\n"
        "• Reload syiling\n"
        "• Buy/Gift Userbot\n"
        "• Send syiling\n"
        "• Check leaderboard\n\n"
        "━━━━━━━━━━━━━━━"
    )


# ─────────────────────────────────────────────
# ⬅️ KEMBALI — dari FSM state → balik ke Kedai
# ─────────────────────────────────────────────

@router.message(TopupFSM.waiting_receipt,      F.text == "⬅️ Kembali")
@router.message(SendCoinsFSM.waiting_target,   F.text == "⬅️ Kembali")
@router.message(SendCoinsFSM.waiting_amount,   F.text == "⬅️ Kembali")
@router.message(GiftUserbotFSM.waiting_target, F.text == "⬅️ Kembali")
async def cancel_kedai_fsm(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 *Home*\n\nPilih menu korang 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "⬅️ Kembali")
async def msg_kembali(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 *Home*\n\nPilih menu korang 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


# ─────────────────────────────────────────────
# 🛒 KEDAI — Entry Point
# ─────────────────────────────────────────────

@router.message(F.text == "🛒 Shop Zone")
async def msg_kedai(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    try:
        text = await _kedai_text(uid)
        await message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())
    except Exception as e:
        logger.error("msg_kedai error uid=%s: %s", uid, e)
        await message.answer("⚠️ Something went wrong. Try again.", reply_markup=main_menu_kb())


# ─────────────────────────────────────────────
# 🏆 PAPAN PENDAHULU
# ─────────────────────────────────────────────

@router.message(F.text == "🏆 Top Leaderboard")
async def msg_leaderboard(message: Message):
    leaders = await db.get_leaderboard(limit=10)

    if not leaders:
        await message.answer(
            "🏆 *Leaderboard*\n\nNo data yet. Be the first! 💪",
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

    text = "🏆 *Leaderboard*\n━━━━━━━━━━━━━━━\n\n" + "\n".join(lines)
    await message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())


# ─────────────────────────────────────────────
# 💳 TOPUP SYILING — Langkah 1: Papar pakej (Inline Keyboard)
# ─────────────────────────────────────────────

@router.message(F.text == "💳 Reload Syiling")
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
        "💳 *Reload Syiling*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"Current balance: *{balance:,} Syiling*\n\n"
        "Pick your reload package:"
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
        "🧾 *Order Summary*\n"
        "━━━━━━━━━━━━━━━\n"
        f"- Item     : Coin Reload\n"
        f"- Package  : {coins:,} Syiling\n"
        f"- Price    : RM{amount:.2f}\n"
        f"- Total    : RM{amount:.2f}\n\n"
        "Proceed to payment?"
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

    uid       = callback.from_user.id
    username  = callback.from_user.username or ""
    full_name = callback.from_user.full_name or ""

    # Jana order_id DULU — tidak bergantung pada DB
    import random as _random
    order_id = f"ORD{_random.randint(10000000, 99999999)}"

    # Cuba simpan ke DB — OPTIONAL: gagal tidak sekat flow
    # (table topup_requests mungkin belum wujud — akan berfungsi setelah SQL dijalankan)
    try:
        await db.create_topup_request(
            order_id=order_id,
            user_id=uid,
            username=username or str(uid),
            coins=coins,
            amount_rm=amount,
        )
        logger.info("topup_request disimpan ke DB: %s uid=%s", order_id, uid)
    except Exception as db_error:
        logger.warning(
            "create_topup_request gagal uid=%s order=%s (table mungkin belum wujud): %s",
            uid, order_id, db_error,
        )

    await state.update_data(order_id=order_id, coins=coins, amount=amount)

    # ── Notify admin: NEW ORDER (sekali per order_id, best-effort) ──
    try:
        await notify_new_order(
            bot,
            order_id=order_id,
            user_id=uid,
            full_name=full_name,
            username=username,
            item=f"Reload Syiling — {coins:,} Syiling",
            coins=coins,
            amount_rm=amount,
            status="⏳ Waiting Payment Proof",
        )
    except Exception as _notify_err:
        logger.warning("[ORDER_NOTIFY] exception dalam notify_new_order: %s", _notify_err)

    caption = (
        "💳 *Payment Details*\n"
        "━━━━━━━━━━━━━━━\n"
        f"Order ID : `{order_id}`\n"
        f"Amount   : RM{amount:.2f}\n\n"
        "Scan QR untuk bayar 👇\n\n"
        "Lepas bayar, tekan button bawah:"
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    if not os.path.exists(QR_PATH):
        logger.warning("QR_PATH tidak wujud semasa topup_proceed uid=%s: %s", uid, QR_PATH)
        await bot.send_message(
            uid,
            "❌ QR payment belum dimuat naik admin.\n\n"
            f"Sila hubungi @berryrcr untuk proses manual.\n\n"
            f"ID Pesanan anda: `{order_id}`",
            parse_mode="Markdown",
            reply_markup=topup_payment_kb(order_id),
        )
        await state.set_state(TopupFSM.waiting_receipt)
        return

    try:
        qr_file = FSInputFile(QR_PATH)
        await bot.send_photo(
            uid, qr_file, caption=caption,
            parse_mode="Markdown",
            reply_markup=topup_payment_kb(order_id),
        )
    except Exception as e:
        logger.error("topup_proceed send photo error uid=%s: %s", uid, e)
        await bot.send_message(
            uid,
            f"⚠️ Gagal hantar QR kod. Sila hubungi @berryrcr.\n\nID Pesanan anda: `{order_id}`",
            parse_mode="Markdown",
            reply_markup=topup_payment_kb(order_id),
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
            caption="📎 Upload screenshot resit pembayaran korang.",
            reply_markup=None,
        )
    except Exception:
        try:
            await callback.message.answer("📎 Upload screenshot resit pembayaran korang.")
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

    # Cuba kemaskini DB — OPTIONAL: gagal tidak sekat flow
    try:
        await db.update_topup_receipt(order_id, receipt_file_id)
    except Exception as e:
        logger.warning("update_topup_receipt gagal uid=%s (table mungkin belum wujud): %s", uid, e)

    await state.clear()

    await message.answer(
        f"✅ Resit diterima! Admin tengah semak pesanan korang.\n"
        f"Order ID: `{order_id}`\n\n"
        "You'll be notified once topup is approved. 🙌",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )

    # Hantar notifikasi admin — sertakan user_id, coins, amount dalam keyboard
    # supaya admin boleh approve/reject TANPA bergantung pada table DB
    try:
        uname_display = f"@{username}" if message.from_user.username else str(uid)
        caption = (
            "🔔 *NEW TOPUP REQUEST*\n"
            "━━━━━━━━━━━━━━━\n"
            f"👤 Username  : {uname_display}\n"
            f"🆔 User ID   : `{uid}`\n"
            f"📋 Order ID  : `{order_id}`\n"
            f"💰 Amount    : RM{amount:.2f}\n"
            f"🪙 Coins     : {coins:,}"
        )
        await bot.send_photo(
            ADMIN_ID,
            receipt_file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=topup_request_admin_kb(order_id, uid, coins, amount),
        )
    except Exception as e:
        logger.warning("Gagal notifikasi admin resit: %s", e)


@router.message(TopupFSM.waiting_receipt)
async def process_topup_receipt_invalid(message: Message):
    await message.answer(
        "⚠️ *Resit kena upload sebagai gambar.*\n\n"
        "Send screenshot bukti payment korang.",
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
        await callback.message.answer("🛒 Back to Shop Zone.", reply_markup=kedai_menu_kb())


# ─────────────────────────────────────────────
# 🛍 BELI USERBOT — Langkah 1: Papar Pilihan Pelan
# ─────────────────────────────────────────────

@router.message(F.text == "🛍 Buy Userbot")
async def msg_beli_userbot(message: Message, state: FSMContext):
    await state.clear()
    uid         = message.from_user.id
    userbot_rec = await db.get_userbot(uid)

    logger.info("beli_userbot: open menu uid=%s has_userbot=%s", uid, bool(userbot_rec))

    if userbot_rec:
        ub_id = userbot_rec.get("userbot_id", "")
        sub   = await db.get_active_subscription(uid)
        plan  = sub["plan"] if sub else "Tiada"
        await message.answer(
            "🤖 *You Already Have a Userbot*\n\n"
            f"🆔 Userbot ID: `{ub_id}`\n"
            f"📦 Active Plan: *{plan}*\n\n"
            "One account, one userbot je.\n"
            "Guna menu *📚 Buat Userbot* untuk manage userbot korang.\n"
            "Nak aktifkan plan? Guna *🛠️ Setup Month & Plan*.",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    balance = await db.get_wallet(uid)
    text = (
        "🛍 *Beli Userbot*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"💰 Balance korang: *{balance:,} Syiling*\n\n"
        "🤖 *Userbot — 300 Syiling (Lifetime)*\n\n"
        "✅ 1 slot userbot kekal\n"
        "✅ Tiada expiry date\n"
        "✅ Bayar sekali, milik selamanya\n"
        "✅ Boleh sambung akaun Telegram sendiri\n\n"
        "━━━━━━━━━━━━━━━\n"
        "💡 _Nak auto promote? Aktifkan PLUS/PRO berasingan_\n"
        "_via 🛠️ Setup Month & Plan selepas beli userbot._"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=buy_userbot_lifetime_kb())


# ─────────────────────────────────────────────
# 🛍 BELI USERBOT — Confirm: Proses Bayaran (Lifetime, no plan)
# In-memory lock: blocks double-tap / concurrent confirm
# ─────────────────────────────────────────────
_processing_buy_confirm: set[int] = set()


@router.callback_query(F.data == "buy_userbot_lifetime_confirm")
async def cb_buy_userbot_lifetime_confirm(callback: CallbackQuery):
    uid = callback.from_user.id

    if uid in _processing_buy_confirm:
        await callback.answer("⚠️ Purchase sedang diproses... sila tunggu.", show_alert=True)
        logger.warning("[BUY_USERBOT] duplicate_click_blocked | uid=%s", uid)
        return

    await callback.answer("⏳ Memproses...")
    _processing_buy_confirm.add(uid)

    logger.info("[BUY_USERBOT] purchase_started | uid=%s", uid)

    try:
        success, userbot_id = await db.buy_userbot_only(uid)

        if not success:
            if userbot_id:
                logger.warning("[BUY_USERBOT] already_has_userbot | uid=%s | ub=%s", uid, userbot_id)
                await callback.message.edit_text(
                    f"⚠️ *Anda sudah ada userbot.*\n\n"
                    f"🆔 Userbot ID: `{userbot_id}`\n\n"
                    "Guna *📚 Buat Userbot* untuk manage userbot korang.",
                    parse_mode="Markdown",
                )
            else:
                balance = await db.get_wallet(uid)
                logger.warning("[BUY_USERBOT] insufficient | uid=%s | balance=%d", uid, balance)
                await callback.message.edit_text(
                    f"❌ *Baki tidak cukup!*\n\n"
                    f"Need: *300 Syiling*\n"
                    f"Balance: *{balance:,} Syiling*\n\n"
                    "Reload dulu via 💳 Reload Syiling.",
                    parse_mode="Markdown",
                )
            return

        logger.info("[BUY_USERBOT] purchase_success | uid=%s | userbot_id=%s", uid, userbot_id)

        await callback.message.edit_text(
            "✅ *Userbot Berjaya Dibeli!*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🤖 Userbot ID:\n`{userbot_id}`\n\n"
            "🔑 *Lifetime* — tiada expiry date\n"
            "🪙 *300 Syiling* ditolak dari wallet\n\n"
            "━━━━━━━━━━━━━━━\n"
            "⚠️ *Simpan Userbot ID korang!*\n"
            "_Gunakan untuk recover akses jika akaun kena limit/banned._\n\n"
            "Next steps:\n"
            "1️⃣ *📚 Buat Userbot* — connect akaun Telegram\n"
            "2️⃣ *🛠️ Setup Month & Plan* — aktifkan PLUS/PRO\n"
            "3️⃣ *⚙️ Control Panel* — setup group & mesej\n"
            "4️⃣ Tekan 🚀 Start Promote!",
            parse_mode="Markdown",
        )
        await callback.message.answer(
            "⚡ You're back at Shop Zone:",
            reply_markup=kedai_menu_kb(),
        )

    except Exception as exc:
        logger.exception("[BUY_USERBOT] purchase_failed (exception) | uid=%s | error=%s", uid, exc)
        try:
            await callback.message.edit_text(
                "⚠️ *Ralat semasa memproses purchase.*\n\nSila cuba lagi atau hubungi @berryrcr.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    finally:
        _processing_buy_confirm.discard(uid)


# ─────────────────────────────────────────────
# 🛍 BELI USERBOT — Batal / Kembali ke senarai pelan
# ─────────────────────────────────────────────

@router.callback_query(F.data == "beli_userbot_cancel")
async def cb_beli_userbot_cancel(callback: CallbackQuery):
    await callback.answer("❌ Dibatalkan.")
    uid = callback.from_user.id
    try:
        await callback.message.delete()
    except Exception:
        pass
    text = await _kedai_text(uid)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())


@router.callback_query(F.data == "beli_userbot_back")
async def cb_beli_userbot_back(callback: CallbackQuery):
    await callback.answer()
    uid     = callback.from_user.id
    balance = await db.get_wallet(uid)
    logger.info("beli_userbot_back: uid=%s kembali ke tawaran userbot", uid)
    text = (
        "🛍 *Beli Userbot*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"💰 Balance korang: *{balance:,} Syiling*\n\n"
        "🤖 *Userbot — 300 Syiling (Lifetime)*\n\n"
        "✅ 1 slot userbot kekal\n"
        "✅ Tiada expiry date\n"
        "✅ Bayar sekali, milik selamanya\n"
        "✅ Boleh sambung akaun Telegram sendiri\n\n"
        "━━━━━━━━━━━━━━━\n"
        "💡 _Nak auto promote? Aktifkan PLUS/PRO berasingan_\n"
        "_via 🛠️ Setup Month & Plan selepas beli userbot._"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=buy_userbot_lifetime_kb())


# ─────────────────────────────────────────────
# 📤 HANTAR SYILING
# ─────────────────────────────────────────────

@router.message(F.text == "📤 Send Syiling")
async def msg_hantar_syiling(message: Message, state: FSMContext):
    await state.clear()
    uid     = message.from_user.id
    balance = await db.get_wallet(uid)

    if balance == 0:
        await message.answer(
            "⚠️ Coin balance korang kosong!\n\nReload dulu via 💳 Topup Syiling.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await message.answer(
        "📤 *Send Syiling*\n\n"
        f"Your balance: *{balance:,} Syiling*\n\n"
        "Enter *Telegram ID* of the receiver:\n"
        "_(Receiver mesti pernah guna bot ni)_\n\n"
        "_Press 🏠 Laman Utama to cancel._",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )
    await state.set_state(SendCoinsFSM.waiting_target)


@router.message(SendCoinsFSM.waiting_target)
async def process_send_target(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    if not text.isdigit():
        await message.answer(
            "⚠️ Masukkan Telegram ID yang valid (nombor je).\n"
            "e.g. `123456789`\n\n"
            "_Press 🏠 Laman Utama to cancel._",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    target_id = int(text)
    if target_id == message.from_user.id:
        await message.answer(
            "⚠️ Tak boleh send dekat diri sendiri lah.",
            reply_markup=kedai_menu_kb(),
        )
        return

    target = await db.get_user_by_id(target_id)
    if not target:
        await message.answer(
            "⚠️ User not found. Make sure penerima pernah guna bot ni.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await state.update_data(target_id=target_id, target_name=target["full_name"])
    await state.set_state(SendCoinsFSM.waiting_amount)
    await message.answer(
        f"✅ Receiver: *{target['full_name']}* (`{target_id}`)\n\n"
        "Enter *amount* to send:\n\n"
        "_Press 🏠 Laman Utama to cancel._",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )


@router.message(SendCoinsFSM.waiting_amount)
async def process_send_amount(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or int(text) <= 0:
        await message.answer(
            "⚠️ Invalid amount — nombor positif je.",
            reply_markup=kedai_menu_kb(),
        )
        return

    amount  = int(text)
    uid     = message.from_user.id
    balance = await db.get_wallet(uid)

    if amount > balance:
        await message.answer(
            f"⚠️ Baki tak cukup!\n\nBalance korang: *{balance:,} Syiling*",
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
            f"✅ *{amount:,} Syiling sent!*\n\n"
            f"To: *{target_name}* (`{target_id}`)\n"
            f"Balance korang: *{balance - amount:,} Syiling*",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
    else:
        await message.answer(
            "❌ Failed to send. Try again.",
            reply_markup=kedai_menu_kb(),
        )


# ─────────────────────────────────────────────
# 🎁 GIFT USERBOT
# ─────────────────────────────────────────────

@router.message(F.text == "🎁 Gift Userbot")
async def msg_gift_userbot(message: Message, state: FSMContext):
    await state.clear()
    uid         = message.from_user.id
    userbot_rec = await db.get_userbot(uid)   # canonical source
    ub_id       = userbot_rec.get("userbot_id", "") if userbot_rec else ""

    if not ub_id:
        await message.answer(
            "⚠️ Korang takde userbot lagi!\n\n"
            "Buy userbot dulu via 🛍 Beli Userbot.",
            reply_markup=kedai_menu_kb(),
        )
        return

    await message.answer(
        "🎁 *Gift Userbot*\n\n"
        f"Your Userbot ID: `{ub_id}`\n\n"
        "Enter *Telegram ID* of the receiver:\n"
        "_(Receiver mesti pernah guna bot ni)_\n\n"
        "_Press 🏠 Laman Utama to cancel._",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )
    await state.set_state(GiftUserbotFSM.waiting_target)


@router.message(GiftUserbotFSM.waiting_target)
async def process_gift_target(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer(
            "⚠️ Masukkan Telegram ID yang valid (nombor je).\n\n"
            "_Press 🏠 Laman Utama to cancel._",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        return

    target_id = int(text)
    uid       = message.from_user.id

    if target_id == uid:
        await message.answer(
            "⚠️ Tak boleh gift dekat diri sendiri lah.",
            reply_markup=kedai_menu_kb(),
        )
        return

    target = await db.get_user_by_id(target_id)
    if not target:
        await message.answer(
            "⚠️ User not found. Make sure penerima pernah guna bot ni.",
            reply_markup=kedai_menu_kb(),
        )
        return

    target_ub = await db.get_userbot(target_id)  # canonical check
    if target_ub:
        await message.answer(
            f"⚠️ *{target['full_name']}* dah ada userbot sendiri.",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )
        await state.clear()
        return

    my_ub = await db.get_userbot(uid)
    ub_id = my_ub.get("userbot_id", "—") if my_ub else "—"

    await db.transfer_userbot_session(uid, target_id)
    await state.clear()

    await message.answer(
        f"🎁 *Userbot Successfully Gifted!*\n\n"
        f"🆔 Userbot ID: `{ub_id}`\n"
        f"New owner: *{target['full_name']}* (`{target_id}`)\n\n"
        "Userbot korang dah dipindahkan. 🙌",
        parse_mode="Markdown",
        reply_markup=kedai_menu_kb(),
    )


# ─────────────────────────────────────────────
# 🏠 LAMAN UTAMA
# ─────────────────────────────────────────────

@router.message(F.text == "🏠 Back To Home")
async def msg_laman_utama(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 *Home*\n\nPilih menu korang 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


# ─────────────────────────────────────────────
# ⏳ TAMBAH BULAN — Langkah 1: Pilih Plan
# ─────────────────────────────────────────────

@router.message(F.text == "🛠️ Setup Month & Plan")
async def msg_tambah_bulan(message: Message, state: FSMContext):
    uid = message.from_user.id
    try:
        await state.clear()
        userbot_rec = await db.get_userbot(uid)

        if not userbot_rec:
            await message.answer(
                "⚠️ *Korang belum ada Userbot!*\n\n"
                "Beli userbot dulu dekat 🛍️ Buy Userbot baru boleh tambah bulan.",
                parse_mode="Markdown",
                reply_markup=kedai_menu_kb(),
            )
            return

        balance = await db.get_wallet(uid)
        sub     = await db.get_active_subscription(uid)

        if sub:
            plan_now = sub.get("plan", "—")
            expires  = sub.get("expires_at", "")
            if expires:
                try:
                    from datetime import datetime, timezone, timedelta
                    _MY_TZ = timezone(timedelta(hours=8))
                    if isinstance(expires, str):
                        expires = expires.replace("Z", "+00:00")
                        exp_dt  = datetime.fromisoformat(expires).astimezone(_MY_TZ)
                    else:
                        exp_dt  = expires.astimezone(_MY_TZ)
                    expires_display = exp_dt.strftime("%d %b %Y")
                except Exception:
                    expires_display = str(expires)[:10]
            else:
                expires_display = "—"
            status_line = (
                f"📦 Plan Semasa: *{plan_now}*\n"
                f"📅 Tamat: *{expires_display}*\n\n"
            )
        else:
            status_line = "📦 Plan Semasa: *Tiada*\n\n"

        text = (
            "🛠️ *Setup Month & Plan*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{status_line}"
            f"💰 Wallet: *{balance:,} Syiling*\n\n"
            "💎 *PLAN PLUS — 300 Syiling / bulan*\n"
            "Perfect untuk normal daily promote 🔥\n"
            "• Max 3 saved promote message\n"
            "• Basic auto promote system\n"
            "• Standard safe mode protection\n"
            "• Smooth untuk casual seller\n"
            "• Easy & simple setup\n\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🚀 *PLAN PRO — 600 Syiling / bulan*\n"
            "Built untuk serious seller & heavy promote ⚡\n"
            "• Unlimited rotate message\n"
            "• Smarter auto promote system\n"
            "• Better anti-flood & safe mode\n"
            "• More stable untuk banyak group\n"
            "• Faster & cleaner promote performance\n"
            "• Future premium feature unlock 🔥\n\n"
            "━━━━━━━━━━━━━━━\n"
            "Pilih plan yang sesuai untuk bisnes kau 👇"
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=tambah_bulan_plans_kb())

    except Exception as e:
        logger.exception("msg_tambah_bulan error uid=%s: %s", uid, e)
        await message.answer(
            "❌ *Ralat semasa load menu.*\n\nSila cuba lagi atau hubungi @berryrcr.",
            parse_mode="Markdown",
            reply_markup=kedai_menu_kb(),
        )


# ─────────────────────────────────────────────
# ⏳ TAMBAH BULAN — Langkah 2: Pilih Plan → Pilih Tempoh
# ─────────────────────────────────────────────

_PLAN_ICON_RENEW  = {"PLUS": "⚡ PLUS", "PRO": "👑 PRO"}
_PLAN_COINS_RENEW = {"PLUS": 300, "PRO": 600}


@router.callback_query(F.data.startswith("buy_plan_select_renew:"))
async def cb_tambah_bulan_plan_select(callback: CallbackQuery):
    await callback.answer()
    plan_key = callback.data.split(":")[1].upper()

    if plan_key not in _PLAN_COINS_RENEW:
        await callback.answer("⚠️ Pelan tidak sah.", show_alert=True)
        return

    icon            = _PLAN_ICON_RENEW.get(plan_key, plan_key)
    coins_per_month = _PLAN_COINS_RENEW[plan_key]

    text = (
        "🗓️ *Pilih Tempoh*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"Plan: *{icon}*\n"
        f"Rate: *{coins_per_month:,} Syiling / bulan*\n\n"
        "Berapa bulan korang nak tambah? 👇"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown",
        reply_markup=plan_duration_kb(plan_key, "renew"),
    )


@router.callback_query(F.data == "tambah_bulan_plan_back")
async def cb_tambah_bulan_plan_back(callback: CallbackQuery):
    await callback.answer()
    uid     = callback.from_user.id
    balance = await db.get_wallet(uid)
    sub     = await db.get_active_subscription(uid)
    plan_now = sub.get("plan", "—") if sub else "Tiada"
    text = (
        "⏳ *Tambah Bulan*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📦 Plan Semasa: *{plan_now}*\n"
        f"💰 Wallet: *{balance:,} Syiling*\n\n"
        "Pilih plan yang korang nak aktifkan:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=tambah_bulan_plans_kb())


@router.callback_query(F.data == "goto_kedai_renew")
async def cb_goto_kedai_renew(callback: CallbackQuery, state: FSMContext):
    """Renew button from expiry notification — send kedai menu directly."""
    await callback.answer()
    await state.clear()
    uid     = callback.from_user.id
    balance = await db.get_wallet(uid)
    sub     = await db.get_active_subscription(uid)

    plan_now = sub.get("plan", "Tiada") if sub else "Tiada"
    expires  = sub.get("expires_at", "") if sub else ""
    if expires:
        try:
            from datetime import datetime, timezone, timedelta
            _MY_TZ = timezone(timedelta(hours=8))
            exp_dt  = datetime.fromisoformat(str(expires).replace("Z", "+00:00")).astimezone(_MY_TZ)
            expires_display = exp_dt.strftime("%d %b %Y")
        except Exception:
            expires_display = str(expires)[:10]
        status_line = f"📦 Plan Semasa: *{plan_now}*\n📅 Tamat: *{expires_display}*\n\n"
    else:
        status_line = "📦 Plan Semasa: *Tiada*\n\n"

    text = (
        "⏳ *Tambah Bulan*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"{status_line}"
        f"💰 Wallet: *{balance:,} Syiling*\n\n"
        "Pilih plan yang korang nak aktifkan:"
    )
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=tambah_bulan_plans_kb())


@router.callback_query(F.data == "tambah_bulan_cancel")
async def cb_tambah_bulan_cancel(callback: CallbackQuery):
    await callback.answer("❌ Dibatalkan.")
    try:
        await callback.message.delete()
    except Exception:
        pass
    uid  = callback.from_user.id
    text = await _kedai_text(uid)
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=kedai_menu_kb())
