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
    balance      = await db.get_wallet(uid)
    sub          = await db.get_active_subscription(uid)
    plan_name    = sub["plan"] if sub else "Tiada"
    transactions = await db.get_transactions(uid, limit=5)

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
        f"📋 Pelan Aktif: *{plan_name}*\n\n"
        f"📜 *5 Transaksi Terkini:*{tx_lines}"
    )


@router.message(F.text == "🪙 Wallet Syiling")
async def msg_wallet(message: Message):
    text = await _show_wallet(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=main_menu_kb())
