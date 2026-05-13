import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import database as db
from keyboards import main_menu_kb
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """
🤖 *Selamat datang ke Promote Auto by @berryrcr!*

Platform ini membantu anda mengurus auto promote Telegram menggunakan akaun anda sendiri.

*Cara guna:*

1️⃣ Topup Syiling melalui menu *Kedai*
2️⃣ Beli Userbot untuk dapatkan ID Userbot anda
3️⃣ Aktifkan pelan *PLUS* atau *PRO*
4️⃣ Sambungkan akaun Telegram anda
5️⃣ Pilih kumpulan yang anda sudah sertai
6️⃣ Tetapkan mesej & jarak masa
7️⃣ Tekan 🚀 Mula Promote

⚠️ *Nota:*
• Userbot dan pelan langganan ialah dua perkara berbeza
• ID Userbot boleh digunakan untuk pindah akses ke akaun lain
• Bot hanya hantar ke kumpulan yang anda pilih sendiri
• Bot tidak auto join atau scrape kumpulan rawak

Sila pilih menu di bawah.
"""


async def _notify_admin_new_user(bot: Bot, user_id: int, username: str, full_name: str):
    if not ADMIN_ID:
        return
    try:
        uname = f"@{username}" if username else "tiada username"
        text = (
            "👤 *Pengguna Baru!*\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Nama: {full_name}\n"
            f"🔗 Username: {uname}"
        )
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
        await db.write_admin_log(
            admin_id=ADMIN_ID,
            action="new_user_joined",
            target_user_id=user_id,
            notes=f"{full_name} ({uname})",
        )
    except Exception as e:
        logger.warning(f"Gagal hantar notifikasi admin: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await message.answer(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )

    user = message.from_user
    try:
        is_new = await db.is_new_user(user.id)
        await db.ensure_user(user.id, user.username or "", user.full_name or "")

        if is_new:
            await _notify_admin_new_user(bot, user.id, user.username or "", user.full_name or "")

            # ── Semak kod rujukan ──
            args = message.text.split(maxsplit=1)
            ref_param = args[1].strip() if len(args) > 1 else ""
            if ref_param.startswith("REF-"):
                try:
                    referrer_id_str = ref_param.replace("REF-", "").split("-")[0]
                    referrer_id = int(referrer_id_str)
                    if referrer_id != user.id:
                        created = await db.create_referral(referrer_id, user.id, ref_param)
                        if created:
                            await db.finalize_referral_coins(referrer_id, user.id)
                            await message.answer(
                                "🎁 *Tahniah!* Anda menerima *50 syiling* bonus kerana menggunakan kod rujukan!",
                                parse_mode="Markdown",
                            )
                            try:
                                await bot.send_message(
                                    referrer_id,
                                    f"🎉 Rakan baru telah menyertai menggunakan kod rujukan anda!\n"
                                    f"Anda menerima *100 syiling* bonus!",
                                    parse_mode="Markdown",
                                )
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning("Referral processing error: %s", e)
    except Exception as e:
        logger.error(f"DB error dalam cmd_start untuk user {user.id}: {e}")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "🏠 *Menu Utama*\n\nSila pilih tindakan:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
