import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import back_to_menu_kb
from services.telethon_service import check_account_health

router = Router()
logger = logging.getLogger(__name__)


async def _build_status_text(uid: int) -> str:
    sub      = await db.get_active_subscription(uid)
    wallet   = await db.get_wallet(uid)
    session  = await db.get_session(uid)
    groups   = await db.get_selected_groups(uid)
    settings = await db.get_promo_settings(uid)
    userbot  = await db.get_userbot(uid)

    nama      = "Tiada"
    nombor    = "Tiada"
    ub_id     = "Tiada"
    acc_status = "⚫ Belum Disambungkan"

    if session:
        tg_user = session.get("tg_username", "")
        phone   = session.get("phone_number", "")
        ub_id   = session.get("userbot_id", "") or (userbot["userbot_id"] if userbot else "Tiada")
        nama    = f"@{tg_user}" if tg_user else "Tiada"
        nombor  = phone or "Tiada"

        health = await check_account_health(session.get("session_string", ""))
        if health == "aktif":
            acc_status = "🟢 Aktif"
        elif health == "flood":
            acc_status = "⚠️ FloodWait — Tunggu sebentar"
        elif health == "banned":
            acc_status = "🔴 Dihadkan / Diblok"
        elif health == "sesi_tamat":
            acc_status = "🔴 Sesi Tamat — Sila log masuk semula"
        else:
            acc_status = "🔴 Ralat Tidak Diketahui"

    if settings:
        is_running  = settings.get("is_running", False)
        delay       = settings.get("delay_minutes", 60)
        hours       = delay // 60
        mins        = delay % 60
        delay_str   = f"{hours}j {mins}m" if hours > 0 else f"{mins}m"
    else:
        is_running = False
        delay_str  = "Tiada"

    promote_status = "🟢 Sedang Berjalan" if is_running else "🔴 Berhenti"

    plan_name = sub["plan"] if sub else "Tiada"

    return (
        "📋 *STATUS AKAUN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama        : {nama}\n"
        f"📱 Nombor      : `{nombor}`\n"
        f"🤖 ID Userbot  : `{ub_id}`\n"
        f"📋 Pelan       : *{plan_name}*\n"
        f"💰 Baki        : *{wallet:,} Syiling*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Akaun       : {acc_status}\n"
        f"📊 Promote     : {promote_status}\n"
        f"👥 Kumpulan    : *{len(groups)} dipilih*\n"
        f"⏸️ Jarak Masa  : *{delay_str}*\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


@router.message(F.text == "📊 Status")
async def msg_status(message: Message):
    uid = message.from_user.id
    wait = await message.answer("⏳ Menyemak status akaun...")
    text = await _build_status_text(uid)
    await wait.delete()
    await message.answer(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await callback.message.edit_text("⏳ Menyemak status akaun...")
    text = await _build_status_text(uid)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())
