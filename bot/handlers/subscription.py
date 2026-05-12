from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import userbot_plans_kb, confirm_kb, back_to_menu_kb
from config import COIN_PLANS

router = Router()


async def _buy_userbot_text(uid: int) -> str:
    sub = await db.get_active_subscription(uid)
    balance = await db.get_wallet(uid)
    current = f"Pelan semasa: *{sub['plan']}*\n\n" if sub else "Anda belum mempunyai pelan aktif.\n\n"
    return (
        f"🛒 *Beli Userbot*\n\n"
        f"{current}"
        f"Sila pilih pelan:\n\n"
        f"⭐ *PLUS — 300 Syiling (RM3)*\n"
        f"  ✅ Auto promote ke group pilihan\n"
        f"  ✅ Footer wajib @berryrcr\n\n"
        f"🔥 *PRO — 600 Syiling (RM6)*\n"
        f"  ✅ Auto promote ke group pilihan\n"
        f"  ✅ Boleh tutup footer\n"
        f"  ✅ Keutamaan sokongan\n\n"
        f"💰 Baki anda: *{balance} Syiling*"
    )


# ─────────────────────────────────────────────
# Reply keyboard trigger
# ─────────────────────────────────────────────

@router.message(F.text == "🛒 Beli Userbot")
async def msg_buy_userbot(message: Message):
    text = await _buy_userbot_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown", reply_markup=userbot_plans_kb())


# ─────────────────────────────────────────────
# Inline callback handlers
# ─────────────────────────────────────────────

@router.callback_query(F.data == "buy_userbot")
async def cb_buy_userbot(callback: CallbackQuery):
    # Jawab PERTAMA — ada DB call selepas ini
    await callback.answer()
    text = await _buy_userbot_text(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=userbot_plans_kb())


@router.callback_query(F.data.in_({"buy_plus", "buy_pro"}))
async def cb_confirm_plan(callback: CallbackQuery):
    plan_key = "PLUS" if callback.data == "buy_plus" else "PRO"
    plan = COIN_PLANS[plan_key]
    uid = callback.from_user.id
    balance = await db.get_wallet(uid)

    if balance < plan["coins"]:
        await callback.answer(
            f"⚠️ Baki tidak mencukupi! Perlu {plan['coins']} syiling, ada {balance}.",
            show_alert=True,
        )
        return

    # Jawab SEBELUM edit_text
    await callback.answer()
    text = (
        f"🛒 *Sahkan Pembelian*\n\n"
        f"Pelan: *{plan['name']}*\n"
        f"Kos: *{plan['coins']} Syiling*\n"
        f"Baki semasa: *{balance} Syiling*\n"
        f"Baki selepas: *{balance - plan['coins']} Syiling*\n\n"
        f"Adakah anda ingin meneruskan?"
    )
    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=confirm_kb(f"confirm_buy_{plan_key.lower()}")
    )


@router.callback_query(F.data.in_({"confirm_buy_plus", "confirm_buy_pro"}))
async def cb_process_buy(callback: CallbackQuery):
    plan_key = "PLUS" if "plus" in callback.data else "PRO"
    plan = COIN_PLANS[plan_key]
    uid = callback.from_user.id

    # Jawab SEBELUM deduct_coins (DB call)
    await callback.answer("⏳ Memproses pembelian...")
    success = await db.deduct_coins(uid, plan["coins"], f"Beli pelan {plan['name']}")
    if not success:
        await callback.message.edit_text(
            "⚠️ *Baki tidak mencukupi!*\n\nSila topup syiling dahulu.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    await db.create_subscription(uid, plan_key)

    text = (
        f"✅ *Berjaya! Pelan {plan['name']} diaktifkan.*\n\n"
        f"Anda kini boleh menyambungkan akaun Telegram dan mula promote.\n\n"
        f"Langkah seterusnya: tekan 📱 *Sambung Akaun*"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=back_to_menu_kb())
