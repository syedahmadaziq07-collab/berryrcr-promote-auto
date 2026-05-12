from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import back_to_menu_kb

router = Router()


async def _build_status_text(uid: int) -> str:
    sub      = await db.get_active_subscription(uid)
    wallet   = await db.get_wallet(uid)
    session  = await db.get_session(uid)
    groups   = await db.get_selected_groups(uid)
    settings = await db.get_promo_settings(uid)

    plan_name    = sub["plan"] if sub else "Tiada"
    session_info = f"`{session['phone_number']}`" if session else "Tidak disambungkan"
    group_count  = len(groups)

    if settings:
        msg_text    = settings.get("message_text") or ""
        msg_preview = (msg_text[:50] + "...") if len(msg_text) > 50 else (msg_text or "Tiada")
        delay       = settings.get("delay_minutes", 60)
        hours       = delay // 60
        mins        = delay % 60
        delay_str   = f"{hours}j {mins}m" if hours > 0 else f"{mins}m"
        is_running  = settings.get("is_running", False)
    else:
        msg_preview = "Tiada"
        delay_str   = "Tiada"
        is_running  = False

    status_icon = "🟢 Berjalan" if is_running else "🔴 Berhenti"

    return (
        f"📊 *Dashboard Status*\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔑 Status Promote: *{status_icon}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📋 Pelan: *{plan_name}*\n"
        f"💰 Baki Syiling: *{wallet} Syiling*\n"
        f"📱 Akaun: {session_info}\n"
        f"👥 Kumpulan Dipilih: *{group_count} kumpulan*\n"
        f"📝 Mesej Aktif: `{msg_preview}`\n"
        f"⏱️ Jarak Masa: *Setiap {delay_str}*\n"
    )


# ─────────────────────────────────────────────
# Reply keyboard trigger
# ─────────────────────────────────────────────

@router.message(F.text == "📊 Status")
async def msg_status(message: Message):
    text = await _build_status_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())


# ─────────────────────────────────────────────
# Inline callback handler
# ─────────────────────────────────────────────

@router.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery):
    text = await _build_status_text(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())
    await callback.answer()
