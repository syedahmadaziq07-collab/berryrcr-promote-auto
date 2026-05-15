import asyncio
import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    InputPeerChannel, InputPeerChat,
    PeerChannel, PeerChat,
    User, InputPeerUser,
)
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError,
    ChannelPrivateError, ChatAdminRequiredError, SlowModeWaitError,
    AuthKeyUnregisteredError, UserDeactivatedBanError,
    UserNotParticipantError, PeerIdInvalidError, UsernameInvalidError,
    UsernameNotOccupiedError, InviteHashInvalidError,
)
import database as db
from config import MANDATORY_FOOTER, MIN_DELAY_MINUTES, API_ID, API_HASH
from services.email_service import notify_session_error
from utils.id_normalizer import normalize_telegram_id

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_bot_instance = None


def _to_telethon_id(gid: str) -> int:
    """
    Tukar group_id kepada Telethon internal channel ID (integer positif).

    Kendalikan kedua-dua format:
      Telegram Bot API:  -1001156883698  → 1156883698
      Telethon internal: 1156883698      → 1156883698 (unchanged)
      Legacy group:      -123456789      → 123456789  (abs)
    """
    raw = str(gid).strip()
    try:
        _, telethon_id = normalize_telegram_id(raw)
        return abs(telethon_id)
    except Exception:
        raw_int = int(raw)
        if raw_int < 0 and raw.startswith("-100"):
            return int(raw[4:])
        return abs(raw_int)


def _sanitize_target_type(raw_gid: str, stored_type: str) -> str:
    """
    Pastikan target_type sah. Jika kosong/tidak diketahui, detect dari format ID.

    -100xxxxxxxxxx → supergroup
    -xxxxxxxxxx    → group
    xxxxxxxxxx     → supergroup (Telethon internal channel ID)
    """
    if stored_type in ("channel", "supergroup", "group"):
        return stored_type

    raw = str(raw_gid).strip()
    if raw.startswith("-100"):
        return "supergroup"
    if raw.startswith("-"):
        return "group"
    # Positif tanpa prefix — Telethon internal channel ID
    return "supergroup"


def _entity_is_user(entity) -> bool:
    """Return True jika entity yang di-resolve adalah User — ini tidak sah untuk promote target."""
    return isinstance(entity, (User, InputPeerUser))


async def _resolve_peer(client: TelegramClient, gid: str, target_type: str,
                        access_hash: str, username: str, user_id: int, gname: str):
    """
    Resolve entity untuk send_message. Sentiasa kembalikan InputPeerChannel
    atau InputPeerChat — TIDAK PERNAH PeerUser/InputPeerUser.

    Keutamaan:
      1. InputPeerChannel(id, access_hash)        — direct, tiada API call
      2. @username via get_input_entity()          — API resolve username
      3. get_input_entity(PeerChannel(id))         — explicit PeerChannel wrapper
      4. get_input_entity(PeerChat(id))            — untuk basic group sahaja

    TIDAK ADA raw int fallback — sebab Telethon boleh tafsir
    int sebagai PeerUser jika ID itu wujud dalam session cache.
    """
    raw_gid = str(gid).strip()
    effective_type = _sanitize_target_type(raw_gid, target_type)
    telethon_id = _to_telethon_id(raw_gid)

    logger.info(
        "[PEER] uid=%s | '%s' | raw_gid=%s → telethon_id=%s | "
        "stored_type='%s' → effective_type='%s' | username=%s | has_hash=%s",
        user_id, gname, raw_gid, telethon_id,
        target_type, effective_type,
        f"@{username}" if username else "–",
        "ya" if access_hash else "tidak",
    )

    # ── Kaedah 1: InputPeerChannel + access_hash — tiada API call, terus construct ──
    # Ini paling selamat untuk supergroup/channel yang ada access_hash
    if access_hash and effective_type in ("channel", "supergroup"):
        try:
            peer = InputPeerChannel(channel_id=telethon_id, access_hash=int(access_hash))
            logger.info(
                "[PEER] uid=%s | '%s' | ✓ Kaedah 1: InputPeerChannel(id=%s, hash=...)",
                user_id, gname, telethon_id,
            )
            return peer
        except Exception as e:
            logger.warning(
                "[PEER] uid=%s | '%s' | Kaedah 1 gagal: %s(%s) — cuba kaedah 2",
                user_id, gname, type(e).__name__, e,
            )

    # ── Kaedah 2: @username via get_input_entity ──
    if username:
        clean = username.lstrip("@").strip()
        if clean:
            try:
                peer = await client.get_input_entity(f"@{clean}")
                if _entity_is_user(peer):
                    logger.error(
                        "[PEER] uid=%s | '%s' | ✗ @%s resolve jadi User — "
                        "target bukan group/channel, langkau",
                        user_id, gname, clean,
                    )
                    raise ValueError(f"Stored target '@{clean}' is a user, not group/channel")
                logger.info(
                    "[PEER] uid=%s | '%s' | ✓ Kaedah 2: get_input_entity(@%s) → %s",
                    user_id, gname, clean, type(peer).__name__,
                )
                return peer
            except ValueError:
                raise
            except Exception as e:
                logger.warning(
                    "[PEER] uid=%s | '%s' | Kaedah 2 gagal @%s: %s(%s) — cuba kaedah 3",
                    user_id, gname, clean, type(e).__name__, e,
                )

    # ── Kaedah 3: get_input_entity(PeerChannel(id)) — explicit, bukan raw int ──
    if effective_type in ("channel", "supergroup"):
        try:
            peer = await client.get_input_entity(PeerChannel(telethon_id))
            if _entity_is_user(peer):
                logger.error(
                    "[PEER] uid=%s | '%s' | ✗ PeerChannel(%s) resolve jadi User — ID salah",
                    user_id, gname, telethon_id,
                )
                raise ValueError(
                    f"PeerChannel({telethon_id}) resolved as User — "
                    f"stored group_id '{raw_gid}' mungkin salah atau bukan channel/supergroup"
                )
            logger.info(
                "[PEER] uid=%s | '%s' | ✓ Kaedah 3: get_input_entity(PeerChannel(%s)) → %s",
                user_id, gname, telethon_id, type(peer).__name__,
            )
            return peer
        except ValueError:
            raise
        except Exception as e:
            logger.warning(
                "[PEER] uid=%s | '%s' | Kaedah 3 gagal PeerChannel(%s): %s(%s) — cuba kaedah 4",
                user_id, gname, telethon_id, type(e).__name__, e,
            )

    # ── Kaedah 4: get_input_entity(PeerChat(id)) — untuk basic group sahaja ──
    if effective_type == "group":
        try:
            peer = await client.get_input_entity(PeerChat(telethon_id))
            if _entity_is_user(peer):
                logger.error(
                    "[PEER] uid=%s | '%s' | ✗ PeerChat(%s) resolve jadi User — ID salah",
                    user_id, gname, telethon_id,
                )
                raise ValueError(
                    f"PeerChat({telethon_id}) resolved as User — "
                    f"stored group_id '{raw_gid}' mungkin salah"
                )
            logger.info(
                "[PEER] uid=%s | '%s' | ✓ Kaedah 4: get_input_entity(PeerChat(%s)) → %s",
                user_id, gname, telethon_id, type(peer).__name__,
            )
            return peer
        except ValueError:
            raise
        except Exception as e:
            logger.warning(
                "[PEER] uid=%s | '%s' | Kaedah 4 gagal PeerChat(%s): %s(%s)",
                user_id, gname, telethon_id, type(e).__name__, e,
            )

    # ── Semua kaedah gagal ──
    raise ValueError(
        f"Tidak dapat resolve '{gname}' (raw_gid={raw_gid}, type={effective_type}) "
        f"— pastikan userbot sudah join kumpulan dan Cuba pilih semula kumpulan."
    )

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
                await notify_session_error(user_id, userbot_id, "Session Expired — userbot tidak authorized")
                return

            logger.info("[PROMO] uid=%s | Telethon OK — mula menghantar ke %d kumpulan/channel", user_id, len(groups))

            success_count = 0
            fail_count = 0
            flood_wait_total = 0
            fail_reasons: list[str] = []

            for idx, group in enumerate(groups, 1):
                gid         = group["group_id"]
                gname       = group.get("group_name") or group.get("group_title") or gid
                target_type = group.get("target_type") or "supergroup"
                username    = group.get("group_username") or ""
                access_hash = group.get("access_hash") or ""

                # ── Debug: log semua maklumat tersimpan untuk kumpulan ini ──
                logger.info(
                    "[PROMO] ── Group %d/%d ──────────────────────",
                    idx, len(groups),
                )
                logger.info(
                    "[PROMO] uid=%s | name='%s' | stored_id=%s | type='%s' | "
                    "username=%s | has_access_hash=%s",
                    user_id, gname, gid, target_type,
                    f"@{username}" if username else "–",
                    "ya" if access_hash else "tidak",
                )

                # Semak format ID yang tersimpan
                raw_id_str = str(gid).strip()
                if raw_id_str.startswith("-100"):
                    id_format = "Telegram(-100 prefix)"
                elif raw_id_str.startswith("-"):
                    id_format = "Telegram(legacy group)"
                elif raw_id_str.isdigit():
                    id_format = "Telethon(internal positif)"
                else:
                    id_format = f"tidak diketahui: '{raw_id_str}'"
                logger.info("[PROMO] uid=%s | id_format=%s", user_id, id_format)

                # Pilih mesej: expert per-group > mesej umum
                if expert_on and gid in group_msgs and group_msgs[gid]:
                    grp_msg = _with_footer(group_msgs[gid])
                    logger.info("[PROMO] uid=%s | '%s' guna expert message", user_id, gname)
                elif full_message:
                    grp_msg = full_message
                else:
                    logger.warning("[PROMO] uid=%s | '%s' tiada mesej — langkau", user_id, gname)
                    continue

                try:
                    # ── Resolve entity ──
                    logger.info("[PROMO] uid=%s | '%s' resolving peer...", user_id, gname)
                    peer = await _resolve_peer(
                        client, gid, target_type, access_hash, username, user_id, gname
                    )
                    logger.info(
                        "[PROMO] uid=%s | '%s' peer resolved → %s",
                        user_id, gname, type(peer).__name__,
                    )

                    # ── Hantar mesej ──
                    await client.send_message(peer, grp_msg)
                    success_count += 1
                    logger.info(
                        "[PROMO] uid=%s | ✓ BERJAYA hantar ke '%s' "
                        "(stored_id=%s type=%s peer=%s)",
                        user_id, gname, gid, target_type, type(peer).__name__,
                    )
                    await asyncio.sleep(3)

                except FloodWaitError as e:
                    wait_secs = e.seconds + 5
                    flood_wait_total += wait_secs
                    fail_count += 1
                    reason = f"FloodWait {e.seconds}s"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ FloodWait ke '%s' (id=%s) — "
                        "tunggu %ds | jumlah flood: %ds",
                        user_id, gname, gid, wait_secs, flood_wait_total,
                    )
                    if flood_wait_total > 300:
                        logger.error(
                            "[PROMO] uid=%s | FloodWait melebihi 5 minit — hentikan promo",
                            user_id,
                        )
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
                    reason = f"SlowMode {e.seconds}s"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ SlowMode ke '%s' (id=%s) — "
                        "kumpulan ada slow mode %ds",
                        user_id, gname, gid, e.seconds,
                    )
                    await asyncio.sleep(min(e.seconds, 60))

                except ChatWriteForbiddenError:
                    fail_count += 1
                    reason = "ChatWriteForbidden — tiada permission hantar mesej"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ ChatWriteForbidden ke '%s' (id=%s type=%s) — "
                        "userbot perlu permission 'Post Messages'",
                        user_id, gname, gid, target_type,
                    )
                    await _notify_user(
                        user_id,
                        f"⚠️ *Gagal hantar ke* `{gname}`\n\n"
                        f"Sebab: Tiada permission untuk hantar mesej.\n"
                        f"Penyelesaian: Jadikan userbot sebagai admin dengan permission *Post Messages*.",
                    )

                except ChannelPrivateError:
                    fail_count += 1
                    reason = "ChannelPrivate — userbot bukan ahli/admin"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ ChannelPrivate '%s' (id=%s) — "
                        "userbot bukan ahli atau kumpulan private",
                        user_id, gname, gid,
                    )
                    await _notify_user(
                        user_id,
                        f"⚠️ *Gagal hantar ke* `{gname}`\n\n"
                        f"Sebab: Kumpulan/channel private atau userbot bukan ahli.\n"
                        f"Penyelesaian: Pastikan userbot sudah join kumpulan.",
                    )

                except ChatAdminRequiredError:
                    fail_count += 1
                    reason = "AdminRequired — perlu admin untuk hantar mesej"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ AdminRequired ke '%s' (id=%s type=%s) — "
                        "kumpulan ini memerlukan admin untuk hantar mesej",
                        user_id, gname, gid, target_type,
                    )
                    await _notify_user(
                        user_id,
                        f"⚠️ *Gagal hantar ke* `{gname}`\n\n"
                        f"Sebab: Kumpulan memerlukan admin untuk post.\n"
                        f"Penyelesaian: Jadikan userbot sebagai admin.",
                    )

                except UserBannedInChannelError:
                    fail_count += 1
                    reason = "UserBanned — userbot diharamkan dalam kumpulan ini"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ UserBanned dalam '%s' (id=%s) — "
                        "userbot telah diharamkan",
                        user_id, gname, gid,
                    )
                    await _notify_user(
                        user_id,
                        f"⚠️ *Gagal hantar ke* `{gname}`\n\n"
                        f"Sebab: Userbot telah diharamkan (banned) dalam kumpulan ini.\n"
                        f"Penyelesaian: Buang kumpulan ini dari senarai promote.",
                    )

                except UserNotParticipantError:
                    fail_count += 1
                    reason = "UserNotParticipant — userbot belum join kumpulan"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ UserNotParticipant '%s' (id=%s) — "
                        "userbot belum join kumpulan",
                        user_id, gname, gid,
                    )
                    await _notify_user(
                        user_id,
                        f"⚠️ *Gagal hantar ke* `{gname}`\n\n"
                        f"Sebab: Userbot belum join kumpulan ini.\n"
                        f"Penyelesaian: Join kumpulan melalui akaun userbot dahulu.",
                    )

                except PeerIdInvalidError:
                    fail_count += 1
                    reason = f"PeerIdInvalid — ID tidak sah (stored_id={gid} type={target_type})"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.error(
                        "[PROMO] uid=%s | ✗ PeerIdInvalid '%s' (stored_id=%s type=%s) — "
                        "ID tidak dapat dikenalpasti oleh Telegram. "
                        "Kemungkinan: format ID salah atau kumpulan sudah dipadam.",
                        user_id, gname, gid, target_type,
                    )

                except (UsernameInvalidError, UsernameNotOccupiedError) as e:
                    fail_count += 1
                    reason = f"{type(e).__name__} — username @{username} tidak sah/wujud"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.warning(
                        "[PROMO] uid=%s | ✗ %s '%s' (username=@%s id=%s) — "
                        "username tidak sah atau sudah berubah",
                        user_id, type(e).__name__, gname, username, gid,
                    )

                except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
                    err_name = type(e).__name__
                    logger.error(
                        "[PROMO] uid=%s | ✗ Sesi tidak sah: %s — hentikan promo serta-merta",
                        user_id, err_name,
                    )
                    await db.set_promo_running(user_id, False)
                    stop_promo_job(user_id)
                    await _notify_user(
                        user_id,
                        "⚠️ *Promote Dihentikan*\n\n"
                        "Sesi Telegram anda telah tamat atau akaun dihadkan.\n"
                        "Sila log masuk semula melalui 📚 Buat Userbot.",
                    )
                    await notify_session_error(
                        user_id, userbot_id,
                        f"Auth Key Invalid / Account Restricted ({err_name})",
                    )
                    return

                except ValueError as e:
                    fail_count += 1
                    reason = f"ValueError: {e} — entity tidak dapat diresolve"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.error(
                        "[PROMO] uid=%s | ✗ ValueError '%s' (stored_id=%s type=%s): %s — "
                        "Cuba pilih semula kumpulan dari senarai untuk refresh access_hash.",
                        user_id, gname, gid, target_type, e,
                    )

                except Exception as e:
                    fail_count += 1
                    reason = f"{type(e).__name__}: {e}"
                    fail_reasons.append(f"'{gname}': {reason}")
                    logger.error(
                        "[PROMO] uid=%s | ✗ GAGAL hantar ke '%s' "
                        "(stored_id=%s type=%s peer_type=%s): %s",
                        user_id, gname, gid, target_type,
                        type(peer).__name__ if 'peer' in dir() else "–",
                        reason,
                        exc_info=True,
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
            next_promote_str = "–"
            if job and job.next_run_time:
                import pytz
                next_run_local = job.next_run_time.astimezone(pytz.timezone("Asia/Kuala_Lumpur"))
                next_promote_str = next_run_local.strftime("%H:%M")

            if success_count > 0:
                if is_immediate:
                    await _notify_user(
                        user_id,
                        f"✅ *Promote Success!*\n\n"
                        f"📦 Sent: *{success_count}* groups\n"
                        f"💀 Failed: *{fail_count}*\n"
                        f"🕒 Next Promote: *{next_promote_str}*\n\n"
                        f"⚡ Auto running...",
                    )
                else:
                    await _notify_user(
                        user_id,
                        f"✅ *Promote Success!*\n\n"
                        f"📦 Sent: *{success_count}* groups\n"
                        f"💀 Failed: *{fail_count}*\n"
                        f"🕒 Next Promote: *{next_promote_str}*\n\n"
                        f"⚡ Auto running...",
                    )
            elif fail_count > 0:
                reasons_text = ""
                if fail_reasons:
                    shown = fail_reasons[:5]
                    reasons_text = "\n\n*Failure reasons:*\n" + "\n".join(f"• {r}" for r in shown)
                    if len(fail_reasons) > 5:
                        reasons_text += f"\n• ...and {len(fail_reasons) - 5} more"
                await _notify_user(
                    user_id,
                    f"✅ *Promote Success!*\n\n"
                    f"📦 Sent: *0* groups\n"
                    f"💀 Failed: *{fail_count}*\n"
                    f"🕒 Next Promote: *{next_promote_str}*"
                    + reasons_text +
                    f"\n\n⚡ Auto running...",
                )

    except Exception as e:
        logger.error("[PROMO] Ralat tidak dijangka uid=%s: %s", user_id, e, exc_info=True)


_MY_TZ = pytz.timezone("Asia/Kuala_Lumpur")
_LEADERBOARD_RESET_JOB_ID = "leaderboard_monthly_reset"


async def _run_monthly_leaderboard_reset():
    """Job bulanan: reset leaderboard pada 1 haribulan, 00:00 waktu Malaysia."""
    logger.info("[LEADERBOARD] leaderboard_reset_started")
    try:
        # Kira jumlah user aktif dalam leaderboard semasa (untuk log)
        leaders = await db.get_leaderboard(limit=999)
        total_users = len(leaders)
        logger.info("[LEADERBOARD] total_users_reset=%d", total_users)

        # Reset: mulakan tempoh baru
        success = await db.reset_leaderboard_period(reset_by="auto_monthly")

        if success:
            logger.info("[LEADERBOARD] leaderboard_reset_success | total_users_reset=%d", total_users)
            # Notify admin
            if _bot_instance:
                import pytz as _pytz
                from datetime import datetime as _dt
                from config import ADMIN_ID
                masa = _dt.now(_MY_TZ).strftime("%d/%m/%Y %H:%M")
                try:
                    await _bot_instance.send_message(
                        ADMIN_ID,
                        f"🔄 *Leaderboard Bulanan Direset!*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"• Tarikh: {masa} (MY)\n"
                        f"• Pengguna terjejas: *{total_users}* orang\n"
                        f"• Status: ✅ Berjaya\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"Tempoh baru bermula sekarang.",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning("[LEADERBOARD] gagal notify admin: %s", e)
        else:
            logger.error("[LEADERBOARD] leaderboard_reset_failed | total_users_reset=%d", total_users)

    except Exception as e:
        logger.error("[LEADERBOARD] leaderboard_reset_failed | ralat: %s", e, exc_info=True)


def register_leaderboard_reset_job():
    """Daftarkan atau pulihkan job reset leaderboard bulanan.
    Dipanggil pada setiap bot startup — selamat untuk dipanggil berulang kali.
    """
    if scheduler.get_job(_LEADERBOARD_RESET_JOB_ID):
        scheduler.remove_job(_LEADERBOARD_RESET_JOB_ID)

    trigger = CronTrigger(
        day=1, hour=0, minute=0, second=0,
        timezone=_MY_TZ,
    )
    scheduler.add_job(
        _run_monthly_leaderboard_reset,
        trigger=trigger,
        id=_LEADERBOARD_RESET_JOB_ID,
        name="Leaderboard Monthly Reset",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        "[LEADERBOARD] Job reset bulanan didaftarkan — setiap 1 haribulan, 00:00 MY"
    )


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
    register_leaderboard_reset_job()
