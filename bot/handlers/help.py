from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from keyboards import back_to_menu_kb

router = Router()

HELP_TEXT = """
⚠️ *Help Center — Promote Auto by @berryrcr*

━━━━━━━━━━━━━━━

⚡️ *Cara Guna \\(ikut flow latest\\)*

1️⃣ *Topup syiling*
🛒 Shop Zone → 💳 Reload Syiling💸

2️⃣ *Buy Userbot*
🛒 Shop Zone → 🛍 Buy Userbot

• 300 Syiling
• Lifetime access
• 1 account only

3️⃣ *Activate Plan*
🛠️ Setup Month & Plan

Pilih:
💎 PLUS atau 🚀 PRO

4️⃣ *Connect Telegram Account*
📚 Create Userbot

Masukkan nombor Telegram & OTP/login code 🔐

5️⃣ *Setup Group*
⚙️ Control Panel → 👥 Manage Group

Pilih group/channel korang sendiri untuk promote\.

6️⃣ *Setup Promote Message*
⚙️ Control Panel → 📝 Edit Message

7️⃣ *Setup Delay Timer*
⚙️ Control Panel → ⏱️ Delay Timer

Recommended:
30–60 minit untuk lebih selamat 🛡️

8️⃣ *Start Promote*
⚙️ Control Panel → 🚀 Start Promote

Done ✅
Bot akan auto running ikut timer & schedule korang 💨

━━━━━━━━━━━━━━━

🧩 *Userbot vs Subscription Plan*

🧩 *Userbot*
= Lifetime access untuk connect Telegram account

💎 *Subscription Plan*
= Unlock feature & auto promote system

Userbot dan plan ialah dua benda berbeza\.

━━━━━━━━━━━━━━━

💎 *PLAN PLUS*

Perfect untuk normal daily promote 🔥

• Max 3 saved promote message
• Basic auto promote system
• Standard safe mode protection
• Smooth untuk casual seller
• Easy & simple setup

━━━━━━━━━━━━━━━

🚀 *PLAN PRO*

Built untuk serious seller & heavy promote ⚡

• Unlimited rotate message
• Smarter auto promote system
• Better anti\\-flood & safe mode
• More stable untuk banyak group
• Faster & cleaner promote performance
• Future premium feature unlock 🔥

━━━━━━━━━━━━━━━

🛡️ *Auto Safe Mode*

Sistem akan auto protect account korang jika detect:
• FloodWait
• PeerFlood
• Too many failed sends

Bot akan auto:
• naikkan delay sementara
• protect account
• restore balik setting asal bila stable ✅

━━━━━━━━━━━━━━━

⚠️ *Heads Up*

• Bot hanya send ke group/channel yang korang pilih sendiri
• Bot TAK auto join atau scrape random group
• Simpan ID Userbot korang untuk backup access
• Elakkan delay terlalu rendah untuk kurangkan risiko limit

━━━━━━━━━━━━━━━
"""


@router.message(F.text == "⚠️ Help Center")
async def msg_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="MarkdownV2", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(HELP_TEXT, parse_mode="MarkdownV2", reply_markup=back_to_menu_kb())
    await callback.answer()
