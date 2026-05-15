import logging
from datetime import timezone
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import back_to_menu_kb
from services.telethon_service import check_account_health

router = Router()
logger = logging.getLogger(__name__)


async def _build_status_text(uid: int) -> str:
    sub      = await db.get_active_subscription(uid)
    session  = await db.get_session(uid)
    groups   = await db.get_selected_groups(uid)
    settings = await db.get_promo_settings(uid)
    userbot  = await db.get_userbot(uid)

    ub_id = "Not Set"
    acc_health = "⚫ Belum Connect"

    if session:
        ub_id = session.get("userbot_id", "") or (userbot["userbot_id"] if userbot else "Not Set")
        health = await check_account_health(session.get("session_string", ""))
        if health == "aktif":
            acc_health = "🟢 Active"
        elif health == "flood":
            acc_health = "⚠️ FloodWait"
        elif health == "banned":
            acc_health = "🔴 Banned / Restricted"
        elif health == "sesi_tamat":
            acc_health = "🔴 Session Expired"
        else:
            acc_health = "🔴 Unknown Error"

    # ── Delay & promote status ──
    if settings:
        is_running = settings.get("is_running", False)
        delay      = settings.get("delay_minutes", 60)
        hours      = delay // 60
        mins       = delay % 60
        delay_str  = f"{hours}j {mins}m" if hours > 0 else f"{mins}m"
    else:
        is_running = False
        delay_str  = "Not Set"

    bot_status = "Running Smooth 🚀" if is_running else "Standby 💤"

    # ── Auto Timer (schedule) ──
    auto_timer = "None"
    if ub_id and ub_id != "Not Set":
        try:
            sched = await db.get_schedule(ub_id)
            if sched and sched.get("aktif"):
                mula  = sched.get("waktu_mula", "?")
                tamat = sched.get("waktu_tamat", "?")
                auto_timer = f"{mula} – {tamat}"
        except Exception:
            pass

    # ── Auto Reply count ──
    auto_reply_count = 0
    if ub_id and ub_id != "Not Set":
        try:
            ar_channels = await db.get_autoreply_channels(ub_id)
            auto_reply_count = len(ar_channels)
        except Exception:
            pass

    # ── Channel vs Group count ──
    channel_count = sum(1 for g in groups if g.get("target_type") == "channel")
    group_count   = len(groups)

    # ── Safe Mode ──
    safe_mode_label = "OFF"
    try:
        sm = await db.get_safe_mode(uid)
        if sm and sm.get("safe_mode_active"):
            from utils.safe_mode import format_cooldown_remaining
            baki = format_cooldown_remaining(sm.get("cooldown_until", ""))
            risk = sm.get("risk_level", "medium")
            risk_icon = "🔴" if risk == "high" else "🟡"
            safe_mode_label = f"{risk_icon} ON — restore dalam {baki}"
        elif sm and not sm.get("safe_mode_active"):
            safe_mode_label = "✅ Restored"
    except Exception:
        pass

    # ── Expert mode ──
    expert_on    = await db.get_expert_mode(uid)
    mode_label   = "Lanjutan 🧠" if expert_on else "Normal"

    # ── Notification ──
    notif_aktif  = await db.get_notif_status(uid)
    notif_label  = "ON - Send To Me 📩" if notif_aktif else "OFF"

    # ── Backup Email ──
    email = None
    try:
        email = await db.get_backup_email(uid)
    except Exception:
        pass
    email_label = email if email else "Not Set"

    # ── Subscription expiry ──
    from datetime import datetime, timezone, timedelta
    _MY_TZ = timezone(timedelta(hours=8))

    plan_str    = "No Active Plan"
    expired_str = "—"
    days_left_str = ""

    if sub:
        plan_str = sub.get("plan", "—")
        exp = sub.get("expires_at")
        if exp:
            try:
                if hasattr(exp, "strftime"):
                    exp_dt = exp.astimezone(_MY_TZ)
                else:
                    exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00")).astimezone(_MY_TZ)
                expired_str = exp_dt.strftime("%d %b %Y")
                days_left = (exp_dt.date() - datetime.now(_MY_TZ).date()).days
                if days_left > 0:
                    days_left_str = f" ({days_left} days left)"
                elif days_left == 0:
                    days_left_str = " (expires today!)"
                else:
                    days_left_str = " (expired)"
            except Exception:
                expired_str = str(exp)[:10]

    return (
        f"🪪 *STATUS ACCOUNT*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🪪 ID Korang: `{ub_id}`\n"
        f"\n"
        f"⌛ Delay Send: *{delay_str}*\n"
        f"🧠 Auto Timer: {auto_timer}\n"
        f"💬 Auto Reply: {auto_reply_count}\n"
        f"📡 Channel Active: {channel_count}\n"
        f"✨ Extra Feature: 0\n"
        f"👥 Group Joined: {group_count}\n"
        f"🗂️ Saved List: {group_count}\n"
        f"\n"
        f"🦾 Mode Sekarang: {mode_label}\n"
        f"🛡️ Safe Mode: {safe_mode_label}\n"
        f"🚦 Status Bot: {bot_status}\n"
        f"💎 Plan: {plan_str}\n"
        f"⏳ Expired On: {expired_str}{days_left_str}\n"
        f"📣 Notification: {notif_label}\n"
        f"📩 Backup Email: {email_label}\n"
        f"🧑‍💻 Admin Backup: 0\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Account Health: {acc_health}"
    )


@router.message(F.text == "📊 Status")
async def msg_status(message: Message):
    uid = message.from_user.id
    wait = await message.answer("⏳ Loading Status Account...")
    text = await _build_status_text(uid)
    await wait.delete()
    await message.answer(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await callback.message.edit_text("⏳ Loading Status Account...")
    text = await _build_status_text(uid)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())
