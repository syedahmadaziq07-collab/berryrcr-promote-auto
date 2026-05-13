import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import InputPeerChannel, InputPeerChat
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError,
    ChannelPrivateError, ChatAdminRequiredError, SlowModeWaitError,
    AuthKeyUnregisteredError, UserDeactivatedBanError,
)
import database as db
from config import MANDATORY_FOOTER, MIN_DELAY_MINUTES, API_ID, API_HASH

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_bot_instance = None


async def _resolve_peer(client: TelegramClient, gid: str, target_type: str,
                        access_hash: str, username: str, user_id: int, gname: str):
    """
    Resolve entity untuk Telethon send_message.

    Keutamaan:
      1. @username  — API resolve, paling selamat untuk channel/group
      2. InputPeerChannel(id, access_hash) — untuk channel/supergroup tanpa username
      3. InputPeerChat(id) — untuk regular group
      4. Raw int(gid)  — last resort (gagal jika tiada dalam session cache)
    """
    # ── Kaedah 1: @username ──
    if username:
        clean = username.lstrip("@").strip()
        if clean:
            try:
                entity = await client.get_entity(f"@{clean}")
                logger.info("[PEER] uid=%s | resolved via @%s", user_id, clean)
                return entity
            except Exception as e:
                logger.warning("[PEER] uid=%s | gagal @%s: %s — cuba cara lain", user_id, clean, e)

    # ── Kaedah 2: InputPeerChannel + access_hash (channel/supergroup) ──
    if access_hash and target_type in ("channel", "supergroup"):
        try:
            peer = InputPeerChannel(int(gid), int(access_hash))
            logger.info("[PEER] uid=%s | resolved via InputPeerChannel id=%s", user_id, gid)
            return peer
        except Exception as e:
            logger.warning("[PEER] uid=%s | gagal InputPeerChannel id=%s: %s", user_id, gid, e)

    # ── Kaedah 3: InputPeerChat (regular group) ──
    if target_type == "group" and not access_hash:
        try:
            peer = InputPeerChat(int(gid))
            logger.info("[PEER] uid=%s | resolved via InputPeerChat id=%s", user_id, gid)
            return peer
        except Exception as e:
            logger.warning("[PEER] uid=%s | gagal InputPeerChat id=%s: %s", user_id, gid, e)

    # ── Kaedah 4: Raw int — last resort ──
    logger.warning(
        "[PEER] uid=%s | guna raw int id=%s type=%s (tiada username/access_hash — mungkin gagal untuk channel)",
        user_id, gid, target_type,
    )
    return int(gid)

# Rotation index: {user_id: next_message_index}
_promo_rotation: dict[int, int] = {}


def set_bot(bot):
    global _bot_instance
    _bot_instance = bot


def get_job_id(user_id: int) -> str:
    return f"promo_{user_id}"


def start_promo_job(user_id: int, delay_minutes: int = MIN_DELAY_MINUTES):
    from datetime import timedelta
    if delay_minutes < MIN_DELAY_MINUTES:
        delay_minutes = MIN_DELAY_MINUTES
    job_id = get_job_id(user_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    # next_run_time = selepas delay — mesej pertama dihantar terus dari promote handler
    next_run_time = datetime.now() + timedelta(minutes=delay_minutes)
    scheduler.add_job(
        _run_promo,
        trigger=IntervalTrigger(minutes=delay_minutes),
        id=job_id,
        args=[user_id],
        replace_existing=True,
        max_instances=1,
        next_run_time=next_run_time,
    )
    job = scheduler.get_job(job_id)
    next_run = job.next_run_time if job else "?"
    logger.info(
        "[PROMO] Job DICIPTA — user_id=%s | jarak=%dm | next_scheduled_run=%s",
        user_id, delay_minutes, next_run,
    )


async def run_promo_now(user_id: int, delay_minutes: int = MIN_DELAY_MINUTES):
    """
    Hantar mesej serta-merta — dipanggil dari promote handler sebaik user tekan Start.
    Ini adalah send PERTAMA; scheduler akan kendalikan send seterusnya mengikut interval.
    """
    logger.info("[PROMO] ═══ IMMEDIATE SEND dimulakan — uid=%s ═══", user_id)
    await _run_promo(user_id, is_immediate=True, delay_minutes=delay_minutes)
    logger.info("[PROMO] ═══ IMMEDIATE SEND selesai — uid=%s ═══", user_id)


def stop_promo_job(user_id: int):
    job_id = get_job_id(user_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    _promo_rotation.pop(user_id, None)
    logger.info("[PROMO] Job DIHENTIKAN — user_id=%s", user_id)


async def _notify_user(user_id: int, text: str):
    if _bot_instance:
        try:
            await _bot_instance.send_message(user_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.warning("[PROMO] Gagal notify user %s: %s", user_id, e)


async def _run_promo(user_id: int, is_immediate: bool = False, delay_minutes: int = None):
    label = "IMMEDIATE SEND" if is_immediate else "KITARAN BERKALA"
    logger.info("[PROMO] ══════ MULA %s — user_id=%s ══════", label, user_id)

    try:
        # ── 1. Semak promo_settings ──
        settings = await db.get_promo_settings(user_id)
        if not settings or not settings.get("is_running"):
            logger.warning("[PROMO] is_running=False atau tiada settings — hentikan job uid=%s", user_id)
            stop_promo_job(user_id)
            return

        # ── 2. Semak langganan ──
        sub = await db.get_active_subscription(user_id)
        if not sub:
            logger.warning("[PROMO] Tiada langganan aktif — hentikan promo uid=%s", user_id)
            await db.set_promo_running(user_id, False)
            stop_promo_job(user_id)
            await _notify_user(
                user_id,
                "⚠️ *Promote Dihentikan*\n\n"
                "Langganan anda telah tamat.\n"
                "Sila beli pelan baru melalui 📚 Buat Userbot.",
            )
            return

        # ── 3. Semak session ──
        session = await db.get_session(user_id)
        if not session or not session.get("session_string"):
            logger.warning("[PROMO] Tiada session/session_string — hentikan promo uid=%s", user_id)
            await db.set_promo_running(user_id, False)
            stop_promo_job(user_id)
            await _notify_user(
                user_id,
                "⚠️ *Promote Dihentikan*\n\n"
                "Sesi userbot anda tidak dijumpai atau telah tamat.\n"
                "Sila log masuk semula melalui 📚 Buat Userbot.",
            )
            return

        session_string = session["session_string"]

        # ── 4. Dapatkan userbot_id ──
        userbot_id = session.get("userbot_id") or ""
        if not userbot_id:
            userbot = await db.get_userbot(user_id)
            userbot_id = userbot["userbot_id"] if userbot else ""

        logger.info("[PROMO] uid=%s | userbot_id=%s | pelan=%s", user_id, userbot_id or "TIADA", sub.get("plan"))

        # ── 5. Semak jadual aktif ──
        if userbot_id:
            try:
                from handlers.schedule import is_schedule_active
                sched = await db.get_schedule(userbot_id)
                if not is_schedule_active(sched):
                    logger.info("[PROMO] uid=%s diluar waktu jadual — kitaran dilangkau", user_id)
                    return
            except Exception as e:
                logger.warning("[PROMO] Semak jadual gagal uid=%s: %s — teruskan promote", user_id, e)

        # ── 6. Ambil broadcast_messages (sistem baru) ──
        broadcast_messages = []
        if userbot_id:
            broadcast_messages = await db.get_broadcast_messages(userbot_id)

        logger.info(
            "[PROMO] uid=%s | broadcast_messages=%d mesej",
            user_id, len(broadcast_messages),
        )

        if not broadcast_messages:
            logger.warning(
                "[PROMO] Tiada broadcast_messages untuk uid=%s (userbot_id=%s) — hentikan promo",
                user_id, userbot_id or "KOSONG",
            )
            await db.set_promo_running(user_id, False)
            stop_promo_job(user_id)
            await _notify_user(
                user_id,
                "⚠️ *Promote Dihentikan*\n\n"
                "Tiada mesej dalam senarai Mesej Sebarkan.\n"
                "Sila tambah mesej melalui 📝 Senarai Mesej Sebarkan.",
            )
            return

        # ── 7. Pilih mesej dengan rotation (round-robin) ──
        rotation_idx = _promo_rotation.get(user_id, 0)
        rotation_idx = rotation_idx % len(broadcast_messages)
        chosen_msg = broadcast_messages[rotation_idx]
        _promo_rotation[user_id] = rotation_idx + 1

        logger.info(
            "[PROMO] uid=%s | mesej dipilih: index=%d id=%s jenis=%s",
            user_id, rotation_idx, chosen_msg.get("id"), chosen_msg.get("content_type"),
        )

        # ── 8. Bina teks mesej ──
        content_type = chosen_msg.get("content_type", "text")
        text_content = chosen_msg.get("text_content") or ""

        # Semak mod lanjutan (expert per-group messages)
        expert_on = await db.get_expert_mode(user_id)
        group_msgs = await db.get_all_group_messages(user_id) if expert_on else {}

        if content_type != "text":
            logger.warning(
                "[PROMO] uid=%s | mesej jenis='%s' (bukan teks) — dilangkau buat masa ini. "
                "Guna mesej teks sahaja untuk promote.",
                user_id, content_type,
            )
            # Cuba mesej teks lain dalam senarai
            text_fallback = next(
                (m.get("text_content") for m in broadcast_messages if m.get("content_type") == "text" and m.get("text_content")),
                None,
            )
            if not text_fallback:
                logger.error("[PROMO] uid=%s tiada mesej teks langsung dalam broadcast_messages — berhenti", user_id)
                return
            text_content = text_fallback
            logger.info("[PROMO] uid=%s | guna fallback teks: %s...", user_id, text_content[:40])

        if not text_content and not expert_on:
            logger.warning("[PROMO] uid=%s | text_content kosong dan expert_on=False — langkau kitaran", user_id)
            return

        # Footer wajib semua plan — elak duplicate jika mesej sudah ada footer
        footer_marker = "🌐 Promote Auto by @berryrcr_bot"
        def _with_footer(text: str) -> str:
            if not text:
                return text
            return text if footer_marker in text else text + MANDATORY_FOOTER

        full_message = _with_footer(text_content)

        # ── 9. Ambil kumpulan yang dipilih ──
        groups = await db.get_selected_groups(user_id)
        logger.info("[PROMO] uid=%s | kumpulan dipilih: %d kumpulan", user_id, len(groups))

        if not groups:
            logger.warning("[PROMO] uid=%s tiada kumpulan dipilih — langkau kitaran", user_id)
            return

        # ── 10. Sambung Telethon sekali untuk semua kumpulan ──
        logger.info("[PROMO] uid=%s | menyambung ke Telethon...", user_id)
        client = None
        try:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.connect()

            if not await client.is_user_authorized():
                logger.error("[PROMO] uid=%s | Telethon TIDAK authorized — sesi mungkin tamat", user_id)
                await db.set_promo_running(user_id, False)
                stop_promo_job(user_id)
                await _notify_user(
                    user_id,
                    "⚠️ *Promote Dihentikan*\n\n"
                    "Sesi Telegram anda telah tamat tempoh.\n"
                    "Sila log masuk semula melalui 📚 Buat Userbot.",
                )
                return

            logger.info("[PROMO] uid=%s | Telethon OK — mula menghantar ke %d kumpulan/channel", user_id, len(groups))

            success_count = 0
            fail_count = 0
            flood_wait_total = 0

            for group in groups:
                gid         = group["group_id"]
                gname       = group.get("group_name") or group.get("group_title") or gid
                target_type = group.get("target_type") or "group"
                username    = group.get("group_username") or ""
                access_hash = group.get("access_hash") or ""

                logger.info(
                    "[PROMO] uid=%s | target='%s' id=%s type=%s username=%s",
                    user_id, gname, gid, target_type, f"@{username}" if username else "-",
                )

                # Pilih mesej: expert per-group > mesej umum
                if expert_on and gid in group_msgs and group_msgs[gid]:
                    grp_msg = _with_footer(group_msgs[gid])
                elif full_message:
                    grp_msg = full_message
                else:
                    logger.warning("[PROMO] uid=%s | '%s' tiada mesej — langkau", user_id, gname)
                    continue

                try:
                    # ── Resolve entity dengan keutamaan: username > access_hash > raw int ──
                    peer = await _resolve_peer(client, gid, target_type, access_hash, username, user_id, gname)

                    await client.send_message(peer, grp_msg)
                    success_count += 1
                    logger.info("[PROMO] uid=%s | ✓ BERJAYA hantar ke '%s' (id=%s type=%s)", user_id, gname, gid, target_type)
                    await asyncio.sleep(3)

                except FloodWaitError as e:
                    wait_secs = e.seconds + 5
                    flood_wait_total += wait_secs
                    fail_count += 1
                    logger.warning(
                        "[PROMO] uid=%s | FloodWait ke '%s' (id=%s) — tunggu %ds (jumlah flood: %ds)",
                        user_id, gname, gid, wait_secs, flood_wait_total,
                    )
                    if flood_wait_total > 300:
                        logger.error("[PROMO] uid=%s | FloodWait melebihi 5 minit — hentikan promo", user_id)
                        await db.set_promo_running(user_id, False)
                        stop_promo_job(user_id)
                        await _notify_user(
                            user_id,
                            "⚠️ *Promote Dihentikan Sementara*\n\n"
                            "Akaun anda telah dihadkan oleh Telegram (Flood Wait).\n"
                            "Sila tunggu beberapa jam sebelum mulakan semula.",
                        )
                        return
                    await asyncio.sleep(wait_secs)

                except SlowModeWaitError as e:
                    fail_count += 1
                    logger.warning("[PROMO] uid=%s | SlowMode ke '%s' (id=%s) — %ds", user_id, gname, gid, e.seconds)
                    await asyncio.sleep(min(e.seconds, 60))

                except ChatWriteForbiddenError:
                    fail_count += 1
                    logger.warning(
                        "[PROMO] uid=%s | ✗ ChatWriteForbidden ke '%s' (id=%s type=%s) — "
                        "pastikan userbot admin channel dengan permission 'Post Messages'",
                        user_id, gname, gid, target_type,
                    )
                    if target_type == "channel":
                        await _notify_user(
                            user_id,
                            f"⚠️ Gagal hantar ke channel *{gname}*.\n\n"
                            "Pastikan akaun userbot ialah admin channel dan mempunyai permission *Post Messages*.",
                        )

                except (ChannelPrivateError,):
                    fail_count += 1
                    logger.warning(
                        "[PROMO] uid=%s | ✗ ChannelPrivate '%s' (id=%s) — userbot bukan ahli/admin",
                        user_id, gname, gid,
                    )
                    if target_type == "channel":
                        await _notify_user(
                            user_id,
                            f"⚠️ Gagal hantar ke channel *{gname}*.\n\n"
                            "Pastikan akaun userbot ialah admin channel dan mempunyai permission *Post Messages*.",
                        )

                except ChatAdminRequiredError:
                    fail_count += 1
                    logger.warning(
                        "[PROMO] uid=%s | ✗ AdminRequired ke '%s' (id=%s type=%s) — "
                        "userbot perlu admin untuk hantar mesej",
                        user_id, gname, gid, target_type,
                    )
                    if target_type == "channel":
                        await _notify_user(
                            user_id,
                            f"⚠️ Gagal hantar ke channel *{gname}*.\n\n"
                            "Pastikan akaun userbot ialah admin channel dan mempunyai permission *Post Messages*.",
                        )

                except (UserBannedInChannelError,):
                    fail_count += 1
                    logger.warning("[PROMO] uid=%s | ✗ UserBanned dalam '%s' (id=%s)", user_id, gname, gid)

                except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
                    logger.error("[PROMO] uid=%s | Sesi tidak sah: %s — hentikan promo", user_id, type(e).__name__)
                    await db.set_promo_running(user_id, False)
                    stop_promo_job(user_id)
                    await _notify_user(
                        user_id,
                        "⚠️ *Promote Dihentikan*\n\n"
                        "Sesi Telegram anda telah tamat atau akaun dihadkan.\n"
                        "Sila log masuk semula melalui 📚 Buat Userbot.",
                    )
                    return

                except ValueError as e:
                    fail_count += 1
                    logger.error(
                        "[PROMO] uid=%s | ✗ ValueError '%s' (id=%s type=%s): %s — "
                        "entity tidak dapat diresolve. Pilih semula target dari senarai.",
                        user_id, gname, gid, target_type, e,
                    )

                except Exception as e:
                    fail_count += 1
                    logger.error(
                        "[PROMO] uid=%s | ✗ GAGAL hantar ke '%s' (id=%s type=%s): %s: %s",
                        user_id, gname, gid, target_type, type(e).__name__, e,
                    )

        finally:
            if client:
                try:
                    await client.disconnect()
                    logger.info("[PROMO] uid=%s | Telethon disconnected", user_id)
                except Exception:
                    pass

        logger.info(
            "[PROMO] ══════ SELESAI %s — uid=%s | ✓ %d berjaya | ✗ %d gagal ══════",
            label, user_id, success_count, fail_count,
        )

        # ── 11. Notifikasi user ──
        # is_immediate=True → SENTIASA notify (mesej pertama, wajib tahu)
        # is_immediate=False → ikut notif_aktif setting user
        notif_aktif = await db.get_notif_status(user_id)
        delay = delay_minutes or settings.get("delay_minutes", MIN_DELAY_MINUTES)

        if _bot_instance and (is_immediate or notif_aktif):
            # Kira next run untuk paparan
            job = scheduler.get_job(get_job_id(user_id))
            next_run_str = ""
            if job and job.next_run_time:
                import pytz
                next_run_local = job.next_run_time.astimezone(pytz.timezone("Asia/Kuala_Lumpur"))
                next_run_str = f"\n🕐 Seterusnya: *{next_run_local.strftime('%H:%M')}*"

            if success_count > 0:
                if is_immediate:
                    await _notify_user(
                        user_id,
                        f"🚀 *Promote Dimulakan!*\n\n"
                        f"✅ Mesej pertama telah dihantar ke *{success_count}* kumpulan/channel"
                        + (f"\n❌ Gagal: *{fail_count}* target" if fail_count else "")
                        + f"\n⏱️ Seterusnya setiap *{delay} minit*"
                        + next_run_str,
                    )
                else:
                    await _notify_user(
                        user_id,
                        f"✅ *Promosi Berjaya Dihantar!*\n\n"
                        f"📤 Berjaya: *{success_count}* kumpulan\n"
                        f"❌ Gagal: *{fail_count}* kumpulan"
                        + next_run_str,
                    )
            elif fail_count > 0:
                await _notify_user(
                    user_id,
                    f"⚠️ *Promosi Gagal Dihantar!*\n\n"
                    f"Semua *{fail_count}* kumpulan/channel gagal.\n\n"
                    f"Kemungkinan sebab:\n"
                    f"• Akaun dihadkan Telegram\n"
                    f"• Dikeluarkan dari kumpulan\n"
                    f"• Sesi userbot tamat\n\n"
                    f"Semak Status Account melalui 📚 Buat Userbot.",
                )

    except Exception as e:
        logger.error("[PROMO] Ralat tidak dijangka uid=%s: %s", user_id, e, exc_info=True)


async def restore_running_promos():
    running = await db.get_all_running_promos()
    count = 0
    logger.info("[PROMO] restore_running_promos: jumpa %d rekod is_running=True", len(running))

    for row in running:
        uid = row["user_id"]
        delay = row.get("delay_minutes", MIN_DELAY_MINUTES)
        session = await db.get_session(uid)
        sub = await db.get_active_subscription(uid)

        if session and sub:
            start_promo_job(uid, delay_minutes=delay)
            count += 1
            logger.info("[PROMO] restore: uid=%s dipulihkan (delay=%dm)", uid, delay)
        else:
            await db.set_promo_running(uid, False)
            reason = "Sesi userbot" if not session else "Langganan"
            logger.warning("[PROMO] restore: uid=%s TIDAK dipulihkan — %s tiada", uid, reason)
            if _bot_instance:
                try:
                    await _bot_instance.send_message(
                        uid,
                        f"⚠️ *Promote Auto Dihentikan*\n\n"
                        f"{reason} anda telah tamat tempoh atau tidak aktif.\n\n"
                        f"Sila log masuk semula melalui 📚 Buat Userbot untuk sambung semula.",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

    logger.info("[PROMO] restore selesai: %d/%d job berjaya dipulihkan", count, len(running))


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("[PROMO] APScheduler dimulakan")
