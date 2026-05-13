import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    InputPeerChannel, InputPeerChat,
    Channel, Chat,
)
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError,
    UserDeactivatedBanError, AuthKeyUnregisteredError,
    PhoneNumberBannedError, UserRestrictedError,
)
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)


async def create_client(user_id: int) -> TelegramClient:
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    return client


async def create_client_from_session(session_string: str) -> TelegramClient:
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()
    return client


async def send_code(client: TelegramClient, phone: str) -> str:
    masked = phone[:4] + "****" if len(phone) > 4 else "****"
    logger.info("send_code_request → phone=%s", masked)
    result = await client.send_code_request(phone)
    logger.info("send_code_request OK → phone=%s hash_prefix=%s", masked, result.phone_code_hash[:6])
    return result.phone_code_hash


async def sign_in(client: TelegramClient, phone: str, code: str, phone_code_hash: str):
    masked = phone[:4] + "****" if len(phone) > 4 else "****"
    logger.info("sign_in attempt → phone=%s", masked)
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        logger.info("sign_in SUCCESS → phone=%s", masked)
        return "success"
    except SessionPasswordNeededError:
        logger.info("sign_in → 2FA diperlukan phone=%s", masked)
        return "2fa_required"


async def get_session_string(client: TelegramClient) -> str:
    return client.session.save()


def _entity_type(entity) -> str:
    """
    Kenal pasti jenis target dari Telethon entity.
    Pulangkan: 'channel' | 'supergroup' | 'group'
    """
    if isinstance(entity, Channel):
        if entity.megagroup or entity.gigagroup:
            return "supergroup"
        return "channel"
    return "group"


async def fetch_user_groups(session_string: str) -> list:
    """
    Ambil semua dialog (kumpulan + channel) dari akaun userbot.
    Pulangkan list dict dengan keys: id, title, username, target_type, access_hash.
    """
    client = await create_client_from_session(session_string)
    try:
        dialogs = await client.get_dialogs()
        targets = []
        for dialog in dialogs:
            entity = dialog.entity
            username = getattr(entity, "username", None)
            access_hash = getattr(entity, "access_hash", None)

            if isinstance(entity, Channel):
                # Supergroup (megagroup=True) atau broadcast channel
                ttype = "supergroup" if (entity.megagroup or getattr(entity, "gigagroup", False)) else "channel"
                targets.append({
                    "id": entity.id,
                    "title": dialog.name or str(entity.id),
                    "username": username,
                    "target_type": ttype,
                    "access_hash": access_hash,
                })
            elif isinstance(entity, Chat) or dialog.is_group:
                # Regular group (chat biasa)
                targets.append({
                    "id": entity.id,
                    "title": dialog.name or str(entity.id),
                    "username": None,
                    "target_type": "group",
                    "access_hash": None,
                })
        return targets
    finally:
        await client.disconnect()


async def build_peer(client: TelegramClient, group_id: str, target_type: str, access_hash: str, username: str):
    """
    Bina entity yang betul untuk Telethon send_message.

    Keutamaan:
      1. @username  — paling selamat, API resolve sendiri
      2. InputPeerChannel / InputPeerChat + access_hash
      3. Raw int(group_id) — last resort, mungkin gagal jika tiada cache

    Pulangkan entity atau None jika gagal.
    """
    # ── Kaedah 1: @username ──
    if username:
        clean = username.lstrip("@").strip()
        if clean:
            try:
                entity = await client.get_entity(f"@{clean}")
                logger.info("[PEER] Resolved via @%s", clean)
                return entity
            except Exception as e:
                logger.warning("[PEER] Gagal resolve @%s: %s — cuba cara lain", clean, e)

    # ── Kaedah 2: InputPeer + access_hash ──
    if access_hash:
        try:
            ah = int(access_hash)
            gid_int = int(group_id)
            if target_type in ("channel", "supergroup"):
                peer = InputPeerChannel(gid_int, ah)
            else:
                peer = InputPeerChat(gid_int)
            logger.info("[PEER] Resolved via InputPeer (type=%s id=%s)", target_type, group_id)
            return peer
        except Exception as e:
            logger.warning("[PEER] Gagal bina InputPeer (type=%s id=%s): %s", target_type, group_id, e)

    # ── Kaedah 3: Raw int — mungkin OK kalau ada dalam session cache ──
    logger.warning(
        "[PEER] Tiada username/access_hash untuk id=%s type=%s — guna raw int (mungkin gagal utk channel)",
        group_id, target_type,
    )
    return int(group_id)


async def send_message_to_group(session_string: str, group_id: int, message: str) -> bool:
    """Legacy helper — masih dipakai oleh kod luar scheduler."""
    client = await create_client_from_session(session_string)
    try:
        await client.send_message(group_id, message)
        return True
    except FloodWaitError as e:
        logger.warning("send_message_to_group FloodWait: group_id=%s — tunggu %ss", group_id, e.seconds)
        raise
    except Exception as e:
        raise e
    finally:
        await client.disconnect()


async def check_account_health(session_string: str) -> str:
    """
    Semak kesihatan akaun Telegram.
    Pulangkan: 'aktif' | 'flood' | 'banned' | 'sesi_tamat' | 'ralat'
    """
    if not session_string:
        return "sesi_tamat"
    client = await create_client_from_session(session_string)
    try:
        me = await client.get_me()
        if me is None:
            return "sesi_tamat"
        return "aktif"
    except FloodWaitError as e:
        logger.warning("check_account_health FloodWait: %s saat", e.seconds)
        return "flood"
    except (UserDeactivatedBanError, PhoneNumberBannedError):
        return "banned"
    except (AuthKeyUnregisteredError,):
        return "sesi_tamat"
    except UserRestrictedError:
        return "banned"
    except Exception as e:
        logger.warning("check_account_health ralat: %s", e)
        return "ralat"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def resolve_entity(session_string: str, identifier: str) -> dict | None:
    """
    Sahkan dan dapatkan maklumat kumpulan/saluran menggunakan ID atau username.
    Pulangkan dict {id, title, username, target_type, access_hash} atau None jika tidak dijumpai.
    """
    if not session_string:
        return None
    client = await create_client_from_session(session_string)
    try:
        raw = identifier.strip()
        if raw.lstrip("-").isdigit():
            # ID — boleh jadi positif (Telethon) atau negatif (Bot API format)
            raw_int = int(raw)
            # Tukar format Bot API (-100xxxxxxxxx) → Telethon positif ID
            if raw_int < -1000000000000:
                raw_int = int(str(abs(raw_int))[3:])  # buang prefix -100
            target = raw_int
        else:
            target = raw.lstrip("@")

        entity = await client.get_entity(target)
        access_hash = getattr(entity, "access_hash", None)
        username = getattr(entity, "username", None)
        ttype = _entity_type(entity)

        logger.info(
            "resolve_entity OK: id=%s title=%s type=%s username=%s",
            entity.id, getattr(entity, "title", "?"), ttype, username,
        )
        return {
            "id": entity.id,
            "title": getattr(entity, "title", str(entity.id)),
            "username": username,
            "target_type": ttype,
            "access_hash": access_hash,
        }
    except Exception as e:
        logger.warning("resolve_entity gagal identifier=%s: %s", identifier, e)
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
