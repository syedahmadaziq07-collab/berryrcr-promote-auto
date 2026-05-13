"""
handlers/admin.py — Panel admin penuh untuk bot Promote Auto by @berryrcr.
Hanya ADMIN_ID boleh menggunakan semua arahan di sini.
"""

import asyncio
import functools
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
import database as db
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)

ACCESS_DENIED = "❌ Anda tidak mempunyai akses admin."


def admin_only(handler):
    """Decorator — tolak mesej jika bukan admin."""
    @functools.wraps(handler)
    async def wrapper(message: Message, **kwargs):
        if message.from_user.id != ADMIN_ID:
            await message.answer(ACCESS_DENIED)
            return
        return await handler(message, **kwargs)
    return wrapper


# ──────────────────────────────────────────────────────────────
# /admin — Dashboard
# ──────────────────────────────────────────────────────────────

@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message):
    total_users = await db.get_user_count()
    sessions = await db.get_all_sessions()
    running = await db.get_all_running_promos()
    sales = await db.get_sales_summary()
    logs = await db.get_admin_logs(limit=1)
    last_action = logs[0]["action"] if logs else "Tiada"

    text = (
        "🛡️ *Panel Admin — Promote Auto*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"👥 Jumlah Pengguna: *{total_users}*\n"
        f"📱 Akaun Disambung: *{len(sessions)}*\n"
        f"🚀 Promote Aktif: *{len(running)}*\n\n"
        f"💰 Jualan Hari Ini: *{sales['coins_today']} syiling (RM{sales['rm_today']})*\n"
        f"📅 Jualan Bulan Ini: *{sales['coins_month']} syiling (RM{sales['rm_month']})*\n"
        f"📊 Jualan Keseluruhan: *{sales['coins_all']} syiling (RM{sales['rm_all']})*\n\n"
        f"🕓 Tindakan Terakhir: `{last_action}`\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Senarai Arahan Admin:*\n"
        "/addcoin `<user_id> <jumlah>` — Tambah syiling\n"
        "/removecoin `<user_id> <jumlah>` — Tolak syiling\n"
        "/users — Senarai pengguna\n"
        "/sessions — Senarai akaun disambung\n"
        "/sales — Laporan jualan\n"
        "/reports — Laporan harian\n"
        "/broadcast `<mesej>` — Hantar ke semua user\n"
        "/topup_pending — Senarai topup menunggu\n"
        "/approve\\_topup `<id>` — Lulus topup\n"
        "/reject\\_topup `<id>` — Tolak topup\n"
    )
    await message.answer(text, parse_mode="Markdown")
    await db.write_admin_log(ADMIN_ID, "view_dashboard")


# ──────────────────────────────────────────────────────────────
# /addcoin <user_id> <amount>
# ──────────────────────────────────────────────────────────────

@router.message(Command("addcoin"))
@admin_only
async def cmd_addcoin(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
        await message.answer(
            "⚠️ Format salah.\n\nGuna: `/addcoin <user_id> <jumlah>`\nContoh: `/addcoin 123456789 300`",
            parse_mode="Markdown",
        )
        return

    target_id = int(parts[1])
    amount = int(parts[2])

    if amount <= 0:
        await message.answer("⚠️ Jumlah mesti lebih dari 0.")
        return

    user = await db.get_user_info(target_id)
    if not user:
        await message.answer(f"⚠️ Pengguna `{target_id}` tidak dijumpai dalam database.", parse_mode="Markdown")
        return

    await db.add_coins(target_id, amount, f"Topup admin — +{amount} syiling")

    new_balance = await db.get_wallet(target_id)
    uname = f"@{user['username']}" if user.get("username") else user.get("full_name", str(target_id))

    await message.answer(
        f"✅ *Berjaya Tambah Syiling*\n\n"
        f"👤 Pengguna: {uname} (`{target_id}`)\n"
        f"➕ Ditambah: *{amount} Syiling*\n"
        f"💰 Baki Baru: *{new_balance} Syiling*",
        parse_mode="Markdown",
    )
    await db.write_admin_log(ADMIN_ID, "add_coin", target_user_id=target_id, notes=f"+{amount} syiling")

    rm_value = round(new_balance / 100, 2)
    try:
        await message.bot.send_message(
            target_id,
            f"💰 *Syiling Ditambah!*\n\n"
            f"Admin telah menambah *{amount:,} syiling* ke wallet anda.\n"
            f"Baki semasa: *{new_balance:,} syiling* (RM{rm_value:.2f})\n\n"
            f"Terima kasih kerana menggunakan Promote Auto! 🚀",
            parse_mode="Markdown",
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# /removecoin <user_id> <amount>
# ──────────────────────────────────────────────────────────────

@router.message(Command("removecoin"))
@admin_only
async def cmd_removecoin(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
        await message.answer(
            "⚠️ Format salah.\n\nGuna: `/removecoin <user_id> <jumlah>`\nContoh: `/removecoin 123456789 300`",
            parse_mode="Markdown",
        )
        return

    target_id = int(parts[1])
    amount = int(parts[2])

    if amount <= 0:
        await message.answer("⚠️ Jumlah mesti lebih dari 0.")
        return

    user = await db.get_user_info(target_id)
    if not user:
        await message.answer(f"⚠️ Pengguna `{target_id}` tidak dijumpai.", parse_mode="Markdown")
        return

    current = await db.get_wallet(target_id)
    success = await db.deduct_coins(target_id, amount, f"Tolak admin — -{amount} syiling")

    if not success:
        await message.answer(
            f"⚠️ Baki tidak mencukupi.\n\nBaki semasa pengguna: *{current} syiling*",
            parse_mode="Markdown",
        )
        return

    new_balance = await db.get_wallet(target_id)
    uname = f"@{user['username']}" if user.get("username") else user.get("full_name", str(target_id))

    await message.answer(
        f"✅ *Berjaya Tolak Syiling*\n\n"
        f"👤 Pengguna: {uname} (`{target_id}`)\n"
        f"➖ Ditolak: *{amount} Syiling*\n"
        f"💰 Baki Baru: *{new_balance} Syiling*",
        parse_mode="Markdown",
    )
    await db.write_admin_log(ADMIN_ID, "remove_coin", target_user_id=target_id, notes=f"-{amount} syiling")


# ──────────────────────────────────────────────────────────────
# /users — Senarai pengguna
# ──────────────────────────────────────────────────────────────

@router.message(Command("users"))
@admin_only
async def cmd_users(message: Message):
    total = await db.get_user_count()
    users = await db.get_recent_users(limit=10)

    lines = []
    for u in users:
        uname = f"@{u['username']}" if u.get("username") else u.get("full_name", "?")
        joined = str(u.get("created_at", ""))[:10]
        lines.append(f"• `{u['id']}` — {uname} ({joined})")

    user_list = "\n".join(lines) if lines else "Tiada pengguna lagi."

    text = (
        f"👥 *Senarai Pengguna*\n\n"
        f"Jumlah: *{total} pengguna*\n\n"
        f"*10 Pengguna Terbaru:*\n{user_list}"
    )
    await message.answer(text, parse_mode="Markdown")
    await db.write_admin_log(ADMIN_ID, "view_users")


# ──────────────────────────────────────────────────────────────
# /sessions — Senarai akaun Telegram disambung
# ──────────────────────────────────────────────────────────────

@router.message(Command("sessions"))
@admin_only
async def cmd_sessions(message: Message):
    sessions = await db.get_all_sessions()

    if not sessions:
        await message.answer("📱 Tiada akaun Telegram yang disambungkan lagi.")
        return

    def _mask(p: str) -> str:
        if not p or len(p) < 7:
            return p
        return p[:4] + "*" * (len(p) - 6) + p[-2:]

    lines = []
    for s in sessions:
        phone = _mask(s.get("phone_number", "?"))
        uid = s.get("user_id", "?")
        date = str(s.get("created_at", ""))[:10]
        lines.append(f"• `{uid}` — {phone} ({date})")

    text = (
        f"📱 *Akaun Telegram Disambungkan*\n\n"
        f"Jumlah: *{len(sessions)} akaun*\n\n"
        + "\n".join(lines)
    )
    await message.answer(text, parse_mode="Markdown")
    await db.write_admin_log(ADMIN_ID, "view_sessions")


# ──────────────────────────────────────────────────────────────
# /sales — Laporan jualan
# ──────────────────────────────────────────────────────────────

@router.message(Command("sales"))
@admin_only
async def cmd_sales(message: Message):
    s = await db.get_sales_summary()

    text = (
        "💰 *Laporan Jualan*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📅 *Hari Ini:*\n"
        f"  • Transaksi: *{s['tx_today']}*\n"
        f"  • Syiling: *{s['coins_today']}*\n"
        f"  • Nilai: *RM {s['rm_today']}*\n\n"
        f"🗓️ *Bulan Ini:*\n"
        f"  • Transaksi: *{s['tx_month']}*\n"
        f"  • Syiling: *{s['coins_month']}*\n"
        f"  • Nilai: *RM {s['rm_month']}*\n\n"
        f"📊 *Keseluruhan:*\n"
        f"  • Transaksi: *{s['tx_all']}*\n"
        f"  • Syiling: *{s['coins_all']}*\n"
        f"  • Nilai: *RM {s['rm_all']}*"
    )
    await message.answer(text, parse_mode="Markdown")
    await db.write_admin_log(ADMIN_ID, "view_sales")


# ──────────────────────────────────────────────────────────────
# /reports — Laporan harian
# ──────────────────────────────────────────────────────────────

@router.message(Command("reports"))
@admin_only
async def cmd_reports(message: Message):
    reports = await db.get_daily_reports(limit=7)

    if not reports:
        await message.answer("📊 Tiada laporan harian lagi.")
        return

    lines = []
    for r in reports:
        date = str(r.get("report_date", ""))
        new_u = r.get("new_users", 0)
        msgs = r.get("total_messages_sent", 0)
        coins = r.get("total_coins_added", 0)
        rm = round(coins / 300 * 3, 2) if coins else 0
        lines.append(
            f"📅 *{date}*\n"
            f"  👤 Pengguna baru: {new_u}\n"
            f"  📤 Mesej dihantar: {msgs}\n"
            f"  💰 Syiling ditambah: {coins} (RM{rm})"
        )

    text = "📊 *Laporan Harian (7 Hari Terakhir)*\n\n" + "\n\n".join(lines)
    await message.answer(text, parse_mode="Markdown")
    await db.write_admin_log(ADMIN_ID, "view_reports")


# ──────────────────────────────────────────────────────────────
# /broadcast <message>
# ──────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
@admin_only
async def cmd_broadcast(message: Message, bot: Bot):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "⚠️ Format salah.\n\nGuna: `/broadcast <mesej>`\nContoh: `/broadcast Bot akan penyelenggaraan pukul 12 malam.`",
            parse_mode="Markdown",
        )
        return

    broadcast_msg = parts[1].strip()
    full_msg = (
        f"📢 *Pengumuman dari Admin*\n\n"
        f"{broadcast_msg}"
    )

    user_ids = await db.get_all_user_ids()
    if not user_ids:
        await message.answer("⚠️ Tiada pengguna untuk dihantar.")
        return

    status_msg = await message.answer(f"⏳ Menghantar ke *{len(user_ids)}* pengguna...", parse_mode="Markdown")

    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, full_msg, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            exc_name = type(exc).__name__
            if exc_name == "TelegramRetryAfter":
                wait = getattr(exc, "retry_after", 5)
                logger.warning("Broadcast: flood limit — tunggu %ss", wait)
                await asyncio.sleep(wait)
                try:
                    await bot.send_message(uid, full_msg, parse_mode="Markdown")
                    success += 1
                except Exception:
                    failed += 1
            else:
                failed += 1

    await status_msg.edit_text(
        f"✅ *Broadcast Selesai*\n\n"
        f"📤 Berjaya: *{success}* pengguna\n"
        f"❌ Gagal: *{failed}* pengguna",
        parse_mode="Markdown",
    )
    await db.write_admin_log(
        ADMIN_ID,
        "broadcast",
        notes=f"Sent to {success}/{len(user_ids)} users — {broadcast_msg[:80]}",
    )


# ──────────────────────────────────────────────────────────────
# /topup_pending — Senarai permintaan topup menunggu
# ──────────────────────────────────────────────────────────────

@router.message(Command("topup_pending"))
@admin_only
async def cmd_topup_pending(message: Message):
    pending = await db.get_pending_topup_requests(limit=20)

    if not pending:
        await message.answer("✅ Tiada permintaan topup yang menunggu kelulusan.")
        return

    lines = []
    for r in pending:
        uid      = r["user_id"]
        order_id = r.get("order_id", "—")
        coins    = r.get("coins", 0)
        amount   = r.get("amount_rm", 0)
        date     = str(r.get("created_at", ""))[:16].replace("T", " ")
        lines.append(
            f"🔹 *{order_id}* — `{uid}`\n"
            f"   {coins:,} Syiling | RM{amount:.2f} — {date}\n"
            f"   `/approve_topup {order_id}` | `/reject_topup {order_id}`"
        )

    text = (
        f"⏳ *Topup Menunggu Kelulusan* ({len(pending)} permintaan)\n"
        "━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(lines)
    )
    await message.answer(text, parse_mode="Markdown")
    await db.write_admin_log(ADMIN_ID, "view_topup_pending")


# ──────────────────────────────────────────────────────────────
# Helper — approve / reject topup_request
# ──────────────────────────────────────────────────────────────

async def _do_approve_request(order_id: str, admin_id: int, bot: Bot) -> tuple[bool, str]:
    req = await db.approve_topup_request(order_id, admin_id)
    if not req:
        return False, f"⚠️ Order *{order_id}* tidak dijumpai atau sudah diproses."

    user_id  = req["user_id"]
    coins    = req["coins"]
    amount   = req.get("amount_rm", 0)

    await db.add_coins(user_id, coins, f"Topup {order_id} diluluskan")
    new_balance = await db.get_wallet(user_id)

    try:
        await bot.send_message(
            user_id,
            f"✅ *Topup Berjaya!*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🪙 *{coins:,} Syiling* telah dikreditkan ke wallet anda.\n"
            f"Order ID: `{order_id}`\n"
            f"Baki semasa: *{new_balance:,} Syiling*",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Gagal notify user approve uid=%s: %s", user_id, e)

    await db.write_admin_log(
        admin_id, f"approve_topup_{order_id}",
        target_user_id=user_id, notes=f"{coins} syiling RM{amount:.2f}"
    )
    user  = await db.get_user_info(user_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(user_id)
    return True, (
        f"✅ *{order_id} Diluluskan*\n\n"
        f"👤 {uname} (`{user_id}`)\n"
        f"🪙 {coins:,} Syiling | RM{amount:.2f}\n"
        f"Baki baru: *{new_balance:,} syiling*"
    )


async def _do_reject_request(order_id: str, admin_id: int, bot: Bot) -> tuple[bool, str]:
    req = await db.reject_topup_request(order_id, admin_id)
    if not req:
        return False, f"⚠️ Order *{order_id}* tidak dijumpai atau sudah diproses."

    user_id = req["user_id"]
    coins   = req.get("coins", 0)

    try:
        await bot.send_message(
            user_id,
            f"❌ *Topup Ditolak*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"Order ID: `{order_id}`\n"
            "Sila hubungi admin jika ada masalah.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Gagal notify user reject uid=%s: %s", user_id, e)

    await db.write_admin_log(
        admin_id, f"reject_topup_{order_id}",
        target_user_id=user_id, notes=f"{coins} syiling"
    )
    user  = await db.get_user_info(user_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(user_id)
    return True, (
        f"❌ *{order_id} Ditolak*\n\n"
        f"👤 {uname} (`{user_id}`)\n"
        f"🪙 {coins:,} Syiling"
    )


# ──────────────────────────────────────────────────────────────
# INLINE CALLBACK — ✅ Approve / ❌ Reject (dari butang pada resit)
# Format callback_data:
#   tr_approve:{user_id}:{coins}:{amount_rm}:{order_id}
#   tr_reject:{user_id}:{order_id}
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tr_approve:"))
async def cb_approve_topup_request(callback: CallbackQuery, bot: Bot):
    await callback.answer()  # WAJIB baris pertama

    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Akses ditolak.", show_alert=True)
        return

    # Parse: tr_approve:{user_id}:{coins}:{amount_rm}:{order_id}
    try:
        parts    = callback.data.split(":")
        user_id  = int(parts[1])
        coins    = int(parts[2])
        amount   = float(parts[3])
        order_id = parts[4]
    except Exception as e:
        logger.error("tr_approve parse error: %s | data=%s", e, callback.data)
        await callback.answer("⚠️ Ralat data callback.", show_alert=True)
        return

    # Tambah syiling ke wallet user
    try:
        await db.add_coins(user_id, coins, f"Topup {order_id} diluluskan")
        new_balance = await db.get_wallet(user_id)
    except Exception as e:
        logger.error("approve add_coins gagal uid=%s: %s", user_id, e)
        await callback.answer("⚠️ Gagal tambah syiling.", show_alert=True)
        return

    # Kemaskini status dalam DB jika table wujud (optional)
    try:
        await db.approve_topup_request(order_id, callback.from_user.id)
    except Exception as e:
        logger.warning("approve_topup_request DB skip (table mungkin belum wujud): %s", e)

    # Notify user
    try:
        await bot.send_message(
            user_id,
            f"✅ *Topup Berjaya!*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🪙 *{coins:,} Syiling* telah dikreditkan ke wallet anda.\n"
            f"Order ID: `{order_id}`\n"
            f"Baki semasa: *{new_balance:,} Syiling*",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Gagal notify user approve uid=%s: %s", user_id, e)

    # Log admin action
    await db.write_admin_log(
        ADMIN_ID, f"approve_topup_{order_id}",
        target_user_id=user_id, notes=f"{coins} syiling RM{amount:.2f}"
    )

    # Update caption mesej admin
    user  = await db.get_user_info(user_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(user_id)
    msg   = (
        f"✅ *{order_id} DILULUSKAN*\n\n"
        f"👤 {uname} (`{user_id}`)\n"
        f"🪙 {coins:,} Syiling | RM{amount:.2f}\n"
        f"Baki baru: *{new_balance:,} syiling*"
    )
    try:
        await callback.message.edit_caption(caption=msg, parse_mode="Markdown", reply_markup=None)
    except Exception:
        try:
            await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=None)
        except Exception:
            pass


@router.callback_query(F.data.startswith("tr_reject:"))
async def cb_reject_topup_request(callback: CallbackQuery, bot: Bot):
    await callback.answer()  # WAJIB baris pertama

    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Akses ditolak.", show_alert=True)
        return

    # Parse: tr_reject:{user_id}:{order_id}
    try:
        parts    = callback.data.split(":")
        user_id  = int(parts[1])
        order_id = parts[2]
    except Exception as e:
        logger.error("tr_reject parse error: %s | data=%s", e, callback.data)
        await callback.answer("⚠️ Ralat data callback.", show_alert=True)
        return

    # Kemaskini status dalam DB jika table wujud (optional)
    try:
        await db.reject_topup_request(order_id, callback.from_user.id)
    except Exception as e:
        logger.warning("reject_topup_request DB skip (table mungkin belum wujud): %s", e)

    # Notify user
    try:
        await bot.send_message(
            user_id,
            f"❌ *Topup Ditolak*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"Order ID: `{order_id}`\n"
            "Sila hubungi admin jika ada masalah.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Gagal notify user reject uid=%s: %s", user_id, e)

    # Log admin action
    await db.write_admin_log(
        ADMIN_ID, f"reject_topup_{order_id}", target_user_id=user_id
    )

    # Update caption mesej admin
    user  = await db.get_user_info(user_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(user_id)
    msg   = (
        f"❌ *{order_id} DITOLAK*\n\n"
        f"👤 {uname} (`{user_id}`)"
    )
    try:
        await callback.message.edit_caption(caption=msg, parse_mode="Markdown", reply_markup=None)
    except Exception:
        try:
            await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=None)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────
# /approve_topup <order_id> — command fallback
# ──────────────────────────────────────────────────────────────

@router.message(Command("approve_topup"))
@admin_only
async def cmd_approve_topup(message: Message, bot: Bot):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "⚠️ Format salah.\n\nGuna: `/approve_topup <order_id>`\nContoh: `/approve_topup ORD12345678`",
            parse_mode="Markdown",
        )
        return
    order_id = parts[1].strip()
    ok, msg  = await _do_approve_request(order_id, message.from_user.id, bot)
    await message.answer(msg, parse_mode="Markdown")


# ──────────────────────────────────────────────────────────────
# /reject_topup <order_id> — command fallback
# ──────────────────────────────────────────────────────────────

@router.message(Command("reject_topup"))
@admin_only
async def cmd_reject_topup(message: Message, bot: Bot):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "⚠️ Format salah.\n\nGuna: `/reject_topup <order_id>`\nContoh: `/reject_topup ORD12345678`",
            parse_mode="Markdown",
        )
        return
    order_id = parts[1].strip()
    ok, msg  = await _do_reject_request(order_id, message.from_user.id, bot)
    await message.answer(msg, parse_mode="Markdown")
