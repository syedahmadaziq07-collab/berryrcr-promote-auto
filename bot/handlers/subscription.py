import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import activate_plan_kb, plan_duration_kb, back_to_menu_kb, tambah_bulan_plans_kb

router = Router()
logger = logging.getLogger(__name__)

_PLAN_ICON  = {"PLUS": "⭐ PLUS", "PRO": "👑 PRO"}
_PLAN_COINS = {"PLUS": 300, "PRO": 600}
_MY_TZ      = timezone(timedelta(hours=8))


async def _plan_select_text(uid: int) -> str:
    sub     = await db.get_active_subscription(uid)
    balance = await db.get_wallet(uid)
    current = f"Pelan semasa: *{sub['plan']}*\n\n" if sub else "Pelan aktif: Tiada\n\n"
    return (
        f"🛒 *Pilih Plan*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"{current}"
        "⚡ *PLUS — 300 Syiling / bulan*\n"
        "  ✅ Auto promote ke group pilihan\n"
        "  ✅ Footer wajib @berryrcr\n"
        "  ✅ 📩 Backup Email & Recovery Notice\n"
        "  ✅ 🔑 Recover Token\n\n"
        "👑 *PRO — 600 Syiling / bulan*\n"
        "  ✅ Semua feature PLUS, ditambah:\n"
        "  ✅ Boleh tutup footer\n"
        "  ✅ Lower delay limit\n"
        "  ✅ Lebih slot group/channel\n"
        "  ✅ Smart rotate & Advanced Mode\n"
        "  ✅ Priority support\n\n"
        f"💰 Balance: *{balance:,} Syiling*"
    )


@router.message(Command("setupplan"))
async def cmd_setupplan(message: Message):
    uid = message.from_user.id
    logger.info("[SETUPPLAN] command_invoked | user_id=%s", uid)

    try:
        userbot_rec = await db.get_userbot(uid)

        if not userbot_rec:
            logger.info("[SETUPPLAN] no_userbot | user_id=%s", uid)
            await message.answer(
                "⚠️ *Korang belum ada Userbot!*\n\n"
                "Beli userbot dulu sebelum activate plan.\n\n"
                "Tekan 🛒 *Kedai* → 🛍 *Buy Userbot* untuk beli sekarang.",
                parse_mode="Markdown",
            )
            return

        balance = await db.get_wallet(uid)
        sub     = await db.get_active_subscription(uid)

        if sub:
            plan_now = sub.get("plan", "—")
            expires  = sub.get("expires_at", "")
            if expires:
                try:
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
        logger.info("[SETUPPLAN] showing_plan_menu | user_id=%s | current_plan=%s", uid, sub["plan"] if sub else "none")
        await message.answer(text, parse_mode="Markdown", reply_markup=tambah_bulan_plans_kb())

    except Exception as e:
        logger.exception("[SETUPPLAN] error | user_id=%s | error=%s", uid, e)
        await message.answer(
            "❌ *Ralat semasa load menu.*\n\nSila cuba lagi atau hubungi @berryrcr.",
            parse_mode="Markdown",
        )


@router.message(F.text == "🛒 Beli Userbot")
async def msg_buy_userbot(message: Message):
    text = await _plan_select_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=activate_plan_kb())


@router.callback_query(F.data == "buy_userbot")
async def cb_buy_userbot(callback: CallbackQuery):
    await callback.answer()
    text = await _plan_select_text(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=activate_plan_kb())


@router.callback_query(F.data.in_({"buy_plus", "buy_pro"}))
async def cb_buy_plan_dur(callback: CallbackQuery):
    plan_key        = "PLUS" if callback.data == "buy_plus" else "PRO"
    icon            = _PLAN_ICON[plan_key]
    coins_per_month = _PLAN_COINS[plan_key]

    await callback.answer()
    text = (
        f"🗓️ *Pilih Tempoh*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"Plan: *{icon}*\n"
        f"Rate: *{coins_per_month:,} Syiling / bulan*\n\n"
        "Berapa bulan korang nak aktifkan? 👇"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown",
        reply_markup=plan_duration_kb(plan_key, "act"),
    )
