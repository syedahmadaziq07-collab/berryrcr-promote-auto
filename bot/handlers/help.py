from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from keyboards import back_to_menu_kb

router = Router()

HELP_TEXT = """
⚠️ *Bantuan — Promote Auto by @berryrcr*

━━━━━━━━━━━━━━━
*Cara guna (ikut urutan):*

1️⃣ *Topup Syiling*
   🛒 Kedai → 💳 Topup Syiling
   Hubungi @berryrcr dengan bukti bayaran.

2️⃣ *Beli Userbot*
   🛒 Kedai → 🛍 Beli Userbot
   Sistem janakan ID Userbot unik untuk anda.

3️⃣ *Aktifkan Pelan*
   📚 Buat Userbot → pilih PLUS atau PRO.

4️⃣ *Sambung Akaun*
   🔑 Log Masuk Token → masukkan nombor & OTP.

5️⃣ *Pilih Kumpulan*
   ⚙️ Tetapan → 👥 Pilih Kumpulan.

6️⃣ *Tetapkan Mesej & Jarak Masa*
   ⚙️ Tetapan → 📝 Tetapkan Mesej & ⏱️ Tetapkan Jarak Masa.

7️⃣ *Mula Promote*
   ⚙️ Tetapan → 🚀 Mula Promote.

━━━━━━━━━━━━━━━
*Perbezaan Userbot & Pelan:*

🤖 *Userbot* = akaun robot anda (ID unik)
📋 *Pelan* = langganan untuk aktifkan ciri promote

Userbot dan pelan adalah *dua perkara berbeza*.
Anda perlu beli userbot dahulu, kemudian aktifkan pelan.

━━━━━━━━━━━━━━━
*Pelan yang Tersedia:*

⭐ *PLUS — 300 Syiling (RM3)*
• Auto promote ke group pilihan
• Footer wajib @berryrcr

🔥 *PRO — 600 Syiling (RM6)*
• Auto promote ke group pilihan
• Boleh tutup footer
• Keutamaan sokongan

━━━━━━━━━━━━━━━
*Harga Syiling:*
• 300 Syiling = RM3
• 600 Syiling = RM6
• 900 Syiling = RM8
• 1,200 Syiling = RM11

━━━━━━━━━━━━━━━
⚠️ *Risiko Auto-Promote:*

• Akaun boleh dihadkan sementara (flood wait)
• Akaun boleh diblok dari hantar mesej ke group
• Dalam kes teruk, akaun boleh dibanned

Gunakan dengan berhati-hati:
• Jangan tetapkan jarak masa terlalu pendek (min. 30 minit)
• Jangan pilih terlalu banyak group sekaligus

*Kami tidak bertanggungjawab atas tindakan Telegram.*

━━━━━━━━━━━━━━━
📞 *Sokongan:* @berryrcr
"""


@router.message(F.text == "⚠️ Help Center")
async def msg_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="Markdown", reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(HELP_TEXT, parse_mode="Markdown", reply_markup=back_to_menu_kb())
    await callback.answer()
