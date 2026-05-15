import logging
import time
from datetime import datetime

import pytz
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import database as db
from keyboards import main_menu_kb
from config import ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)

# In-memory cooldown — elak spam notify admin (5 minit per user)
_start_notify_cache: dict[int, float] = {}
_NOTIFY_COOLDOWN_SECONDS = 300  # 5 minit

MY_TZ = pytz.timezone("Asia/Kuala_Lumpur")

WELCOME_MESSAGE = """
🤖 *Welcome to Promote Auto by @berryrcr\\_bot*
━━━━━━━━━━━━━━━

⚡️ *Quick Start Guide*

1️⃣ Topup syiling dekat 🛒 Kedai
2️⃣ Buy Userbot untuk unlock access
3️⃣ Activate plan korang (PLUS / PRO) dekat 🛠️ Setup Month & Plan
4️⃣ Connect akaun Telegram dekat 📚 Buat Userbot
5️⃣ Masuk ⚙️ Tetapan
6️⃣ Setup 👥 Manage Group
7️⃣ Setup 📝 Edit Message
8️⃣ Setup ⏱️ Delay Timer
9️⃣ Tekan 🚀 Start Promote

Done ✅
Bot akan auto running ikut timer yang korang set 💨

━━━━━━━━━━━━━━━

🧠 *Apa yang bot ni boleh buat?*

• Auto promote group & channel
• Rotate multiple message auto
• 🤖 Auto Reply system
• 🧪 Advanced Mode features
• ⏱️ Custom delay timer
• 📩 Backup login recovery
• 🎁 Referral reward system
• 📡 Live status monitoring

━━━━━━━━━━━━━━━

⚠️ *Heads Up:*

• Userbot & subscription plan ialah benda berbeza
• Bot hanya send ke group/channel yang korang pilih sendiri
• Bot TAK auto join atau scrape random group
• Simpan ID Userbot korang untuk backup access kalau account logout/limit

━━━━━━━━━━━━━━━

🌐 Promote Auto by @berryrcr\\_bot
"""


async def _notify_admin_start(
    bot: Bot,
    user_id: int,
    username: str,
    full_name: str,
    is_new: bool,
):
    """Hantar notifikasi admin bila user tekan /start.
    - Cooldown 5 minit per user — elak spam.
    - Title & label berbeza untuk pengguna baru vs aktif.
    """
    if not ADMIN_ID:
        return

    # ── Cooldown check ──
    now = time.monotonic()
    last = _start_notify_cache.get(user_id, 0)
    if now - last < _NOTIFY_COOLDOWN_SECONDS:
        logger.debug("[START] notify cooldown active uid=%s", user_id)
        return
    _start_notify_cache[user_id] = now

    # ── Format masa Malaysia ──
    masa = datetime.now(MY_TZ).strftime("%d/%m/%Y %H:%M")

    uname_display = f"@{username}" if username else "Tiada"

    if is_new:
        title = "👤 PELANGGAN BARU MASUK!"
        label = "🆕 Pengguna baru!"
    else:
        title = "👤 PELANGGAN AKTIF MASUK!"
        label = "♻️ Pengguna aktif kembali!"

    text = (
        f"*{title}*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"• Nama: {full_name}\n"
        f"• Username: {uname_display}\n"
        f"• ID: `{user_id}`\n"
        f"• Masa: {masa} (MY)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{label}"
    )

    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
        logger.info("[START] admin notified | uid=%s is_new=%s", user_id, is_new)
    except Exception as e:
        logger.warning("[START] gagal notify admin uid=%s: %s", user_id, e)

    # ── Log ke admin_logs (best-effort) ──
    try:
        action = "new_user_joined" if is_new else "returning_user_start"
        await db.write_admin_log(
            admin_id=ADMIN_ID,
            action=action,
            target_user_id=user_id,
            notes=f"{full_name} ({uname_display})",
        )
    except Exception as e:
        logger.debug("[START] write_admin_log skip: %s", e)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    # ── Hantar welcome kepada customer dulu ──
    await message.answer(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )

    user = message.from_user
    try:
        is_new = await db.is_new_user(user.id)
        await db.ensure_user(user.id, user.username or "", user.full_name or "")

        # ── Notify admin (new & returning, dengan cooldown) ──
        await _notify_admin_start(
            bot,
            user_id=user.id,
            username=user.username or "",
            full_name=user.full_name or "",
            is_new=is_new,
        )

        # ── Proses referral (pengguna baru sahaja) ──
        if is_new:
            args = message.text.split(maxsplit=1)
            ref_param = args[1].strip() if len(args) > 1 else ""
            if ref_param.startswith("REF-"):
                try:
                    referrer_id_str = ref_param.replace("REF-", "").split("-")[0]
                    referrer_id = int(referrer_id_str)
                    if referrer_id != user.id:
                        created = await db.create_referral(referrer_id, user.id, ref_param)
                        if created:
                            logger.info(
                                "[REFERRAL] referral_registered | referrer=%s referred=%s",
                                referrer_id, user.id,
                            )
                            await message.answer(
                                "🎁 *Jemputan berjaya!*\n\n"
                                "Korang akan dapat *100 Syiling* apabila activate plan *PLUS* atau *PRO*.\n"
                                "Kawan yang jemput korang pun akan dapat 100 Syiling sekali! 🤑",
                                parse_mode="Markdown",
                            )
                        else:
                            logger.info(
                                "[REFERRAL] referral_duplicate_blocked | referrer=%s referred=%s",
                                referrer_id, user.id,
                            )
                    else:
                        logger.info(
                            "[REFERRAL] referral_duplicate_blocked (self-refer) | user_id=%s",
                            user.id,
                        )
                except Exception as e:
                    logger.warning("Referral processing error: %s", e)

    except Exception as e:
        logger.error("DB error dalam cmd_start untuk user %s: %s", user.id, e)


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "🏠 *Menu Utama*\n\nSila pilih tindakan:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
