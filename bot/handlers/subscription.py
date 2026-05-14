from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import activate_plan_kb, plan_duration_kb, back_to_menu_kb

router = Router()

_PLAN_ICON  = {"PLUS": "⭐ PLUS", "PRO": "👑 PRO"}
_PLAN_COINS = {"PLUS": 300, "PRO": 600}


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
