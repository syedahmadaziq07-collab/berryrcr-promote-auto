"""
handlers/wallet.py — Wallet, baki syiling.
Topup kini diuruskan sepenuhnya dalam kedai.py via Reply Keyboard.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
import database as db
from keyboards import main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


def _rm(coins: int) -> str:
    return f"RM{coins / 100:.2f}"


async def _show_wallet(uid: int) -> str:
    from datetime import datetime, timezone, timedelta
    _MY_TZ = timezone(timedelta(hours=8))

    balance      = await db.get_wallet(uid)
    sub          = await db.get_active_subscription(uid)
    transactions = await db.get_transactions(uid, limit=5)

    if sub:
        plan_name = sub.get("plan", "Tiada")
        exp = sub.get("expires_at")
        if exp:
            try:
                if hasattr(exp, "strftime"):
                    exp_dt = exp.astimezone(_MY_TZ)
                else:
                    exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00")).astimezone(_MY_TZ)
                days_left = (exp_dt.date() - datetime.now(_MY_TZ).date()).days
                exp_str = exp_dt.strftime("%d %b %Y")
                plan_line = f"📋 Pelan Aktif: *{plan_name}* — tamat {exp_str} ({days_left}h lagi)"
            except Exception:
                plan_line = f"📋 Pelan Aktif: *{plan_name}*"
        else:
            plan_line = f"📋 Pelan Aktif: *{plan_name}*"
    else:
        plan_line = "📋 Pelan Aktif: *Tiada*"

    tx_lines = ""
    for t in transactions:
        sign      = "+" if t["type"] == "credit" else "-"
        tx_lines += f"\n  {sign}{t['amount']} syiling — {t['description']}"
    if not tx_lines:
        tx_lines = "\n  Tiada transaksi lagi."

    return (
        "🪙 *Wallet Syiling Anda*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"💰 Baki Semasa: *{balance:,} Syiling*\n"
        f"💵 Nilai Setara: *{_rm(balance)}*\n"
        f"{plan_line}\n\n"
        f"📜 *5 Transaksi Terkini:*{tx_lines}"
    )


@router.message(F.text == "🪙 Wallet Syiling")
async def msg_wallet(message: Message):
    text = await _show_wallet(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=main_menu_kb())
