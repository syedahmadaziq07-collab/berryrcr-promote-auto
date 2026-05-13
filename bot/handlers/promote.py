from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
import database as db
from keyboards import back_to_menu_kb
from services import scheduler_service

router = Router()


async def _do_start_promote(uid: int, send_fn):
    sub = await db.get_active_subscription(uid)
    if not sub:
        await send_fn(
            "⚠️ *Sila aktifkan pelan PLUS/PRO dahulu melalui 📚 Buat Userbot!*",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    session = await db.get_session(uid)
    if not session:
        await send_fn(
            "⚠️ *Sila sambungkan akaun Telegram dahulu melalui 📚 Buat Userbot!*",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    settings = await db.get_promo_settings(uid)
    if not settings or not settings.get("message_text"):
        await send_fn(
            "⚠️ *Sila tetapkan mesej promosi dahulu melalui 📝 Tetapkan Mesej!*",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    groups = await db.get_selected_groups(uid)
    if not groups:
        await send_fn(
            "⚠️ *Sila pilih kumpulan dahulu melalui 👥 Pilih Kumpulan!*",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    if settings.get("is_running"):
        await send_fn(
            "ℹ️ *Promote sudah berjalan!*\n\nTekan 📊 Status untuk semak status semasa.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    await db.set_promo_running(uid, True)
    scheduler_service.start_promo_job(uid, delay_minutes=settings["delay_minutes"])

    plan_name   = sub["plan"]
    delay       = settings["delay_minutes"]
    hours       = delay // 60
    mins        = delay % 60
    human_delay = f"{hours}j {mins}m" if hours > 0 else f"{mins}m"

    await send_fn(
        f"🚀 *Promote Dimulakan!*\n\n"
        f"📋 Pelan: *{plan_name}*\n"
        f"👥 Kumpulan: *{len(groups)} kumpulan*\n"
        f"⏱️ Jarak Masa: *setiap {human_delay}*\n\n"
        f"Bot akan menghantar mesej anda ke semua kumpulan yang dipilih secara automatik.\n\n"
        f"⚠️ _Auto-promote boleh menyebabkan akaun anda dihadkan oleh Telegram. "
        f"Gunakan dengan berhati-hati._",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )


async def _do_stop_promote(uid: int, send_fn):
    settings = await db.get_promo_settings(uid)

    if not settings or not settings.get("is_running"):
        await send_fn(
            "ℹ️ *Promote tidak sedang berjalan.*\n\nTekan 🚀 Mula Promote untuk mulakan.",
            parse_mode="Markdown",
            reply_markup=back_to_menu_kb(),
        )
        return

    await db.set_promo_running(uid, False)
    scheduler_service.stop_promo_job(uid)

    await send_fn(
        "⏹️ *Promote Dihentikan*\n\n"
        "Semua promosi automatik telah dihentikan.\n"
        "Tekan 🚀 Mula Promote untuk memulakan semula.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_kb(),
    )


# ─────────────────────────────────────────────
# Reply keyboard triggers
# ─────────────────────────────────────────────

@router.message(F.text == "🚀 Mula Promote")
async def msg_start_promote(message: Message):
    await _do_start_promote(message.from_user.id, message.answer)


@router.message(F.text == "⏹️ Henti Promote")
async def msg_stop_promote(message: Message):
    await _do_stop_promote(message.from_user.id, message.answer)


# ─────────────────────────────────────────────
# Inline callback handlers
# ─────────────────────────────────────────────

@router.callback_query(F.data == "start_promote")
async def cb_start_promote(callback: CallbackQuery):
    await callback.answer()
    await _do_start_promote(callback.from_user.id, callback.message.answer)


@router.callback_query(F.data == "stop_promote")
async def cb_stop_promote(callback: CallbackQuery):
    await callback.answer()
    await _do_stop_promote(callback.from_user.id, callback.message.answer)
