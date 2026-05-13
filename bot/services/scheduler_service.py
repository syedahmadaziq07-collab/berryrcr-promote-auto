import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import database as db
from config import MANDATORY_FOOTER, COIN_PLANS, MIN_DELAY_MINUTES
from services.telethon_service import send_message_to_group

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_bot_instance = None


def set_bot(bot):
    global _bot_instance
    _bot_instance = bot


def get_job_id(user_id: int) -> str:
    return f"promo_{user_id}"


def start_promo_job(user_id: int, delay_minutes: int = MIN_DELAY_MINUTES):
    if delay_minutes < MIN_DELAY_MINUTES:
        delay_minutes = MIN_DELAY_MINUTES
    job_id = get_job_id(user_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _run_promo,
        trigger=IntervalTrigger(minutes=delay_minutes),
        id=job_id,
        args=[user_id],
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Promo job dimulakan untuk user {user_id} (jarak masa: {delay_minutes} minit)")


def stop_promo_job(user_id: int):
    job_id = get_job_id(user_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    logger.info(f"Promo job dihentikan untuk user {user_id}")


async def _run_promo(user_id: int):
    try:
        settings = await db.get_promo_settings(user_id)
        if not settings or not settings.get("is_running"):
            stop_promo_job(user_id)
            return

        session = await db.get_session(user_id)
        if not session:
            logger.warning(f"Tiada session untuk user {user_id}, hentikan promo")
            await db.set_promo_running(user_id, False)
            stop_promo_job(user_id)
            return

        sub = await db.get_active_subscription(user_id)
        if not sub:
            logger.warning(f"Tiada langganan untuk user {user_id}, hentikan promo")
            await db.set_promo_running(user_id, False)
            stop_promo_job(user_id)
            return

        # ── Semak jadual aktif ──
        userbot = await db.get_userbot(user_id)
        ub_id   = (session.get("userbot_id") or (userbot["userbot_id"] if userbot else None))
        if ub_id:
            from handlers.schedule import is_schedule_active
            sched = await db.get_schedule(ub_id)
            if not is_schedule_active(sched):
                logger.info(f"User {user_id} diluar waktu jadual — promote dilangkau")
                return

        plan         = COIN_PLANS.get(sub["plan"], {})
        message_text = settings.get("message_text", "")

        # ── Semak mod lanjutan ──
        expert_on  = await db.get_expert_mode(user_id)
        group_msgs = await db.get_all_group_messages(user_id) if expert_on else {}

        if not message_text and not expert_on:
            return

        add_footer   = plan.get("footer_required", True)
        full_message = message_text + (MANDATORY_FOOTER if add_footer else "") if message_text else ""

        groups = await db.get_selected_groups(user_id)
        if not groups:
            return

        success_count = 0
        fail_count    = 0

        for group in groups:
            gid = group["group_id"]
            # Pilih mesej: mod lanjutan > mesej umum
            if expert_on and gid in group_msgs:
                grp_msg = group_msgs[gid] + (MANDATORY_FOOTER if add_footer else "")
            elif full_message:
                grp_msg = full_message
            else:
                continue

            try:
                await send_message_to_group(
                    session["session_string"],
                    int(gid),
                    grp_msg,
                )
                success_count += 1
                await asyncio.sleep(3)
            except Exception as e:
                fail_count += 1
                logger.error(f"Gagal hantar ke group {gid}: {e}")

        logger.info(f"Promo selesai user {user_id}: {success_count} berjaya, {fail_count} gagal")

        # ── Notifikasi (semak pilihan user) ──
        notif_aktif = await db.get_notif_status(user_id)
        if _bot_instance and success_count > 0 and notif_aktif:
            try:
                delay = settings.get("delay_minutes", MIN_DELAY_MINUTES)
                await _bot_instance.send_message(
                    user_id,
                    f"✅ *Promosi Berjaya Dihantar!*\n\n"
                    f"📤 Berjaya: *{success_count}* kumpulan\n"
                    f"❌ Gagal: *{fail_count}* kumpulan\n\n"
                    f"Jarak masa seterusnya: *{delay} minit*",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Ralat promo job user {user_id}: {e}")


async def restore_running_promos():
    running = await db.get_all_running_promos()
    count = 0
    for row in running:
        uid = row["user_id"]
        delay = row.get("delay_minutes", MIN_DELAY_MINUTES)
        session = await db.get_session(uid)
        sub = await db.get_active_subscription(uid)
        if session and sub:
            start_promo_job(uid, delay_minutes=delay)
            count += 1
        else:
            await db.set_promo_running(uid, False)
    logger.info(f"Dipulihkan {count} promo job(s) yang berjalan")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
