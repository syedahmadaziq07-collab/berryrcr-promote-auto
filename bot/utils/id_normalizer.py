import logging

logger = logging.getLogger(__name__)


def normalize_telegram_id(user_input: str | int) -> tuple[int, int]:
    """
    Normalize Telegram ID to both formats.

    Args:
        user_input: Raw ID from user (e.g. -1001156883698 or "-1001156883698")

    Returns:
        (telegram_id, telethon_id)

        telegram_id  — full Bot API format (-1001156883698 for supergroups/channels)
        telethon_id  — Telethon internal format (1156883698, positive for supergroups)

    Examples:
        Input: -1001156883698  (supergroup with -100 prefix)
        Output: (-1001156883698, 1156883698)

        Input: -123456789  (legacy group, negative without -100)
        Output: (-123456789, -123456789)

        Input: 987654321  (user/bot, positive)
        Output: (987654321, 987654321)
    """
    raw = str(user_input).strip()

    try:
        raw_int = int(raw)
    except ValueError:
        raise ValueError(f"ID tidak sah: '{user_input}'")

    # Supergroup/Channel: string starts with "-100" AND has enough digits
    # Telethon internal ID = strip the "-100" prefix
    if raw.startswith("-100") and len(raw) > 4:
        telethon_id = int(raw[4:])   # remove leading "-100"
        telegram_id = raw_int
    else:
        # Legacy group (negative) or user/bot (positive) — no conversion needed
        telegram_id = raw_int
        telethon_id = raw_int

    logger.debug(
        "[ID_NORM] input=%s → telegram_id=%s telethon_id=%s",
        user_input, telegram_id, telethon_id,
    )
    return telegram_id, telethon_id


def is_group_id(telegram_id: int) -> bool:
    """Return True if the ID looks like a group/supergroup/channel (not a user/bot)."""
    return telegram_id < 0


def telethon_to_telegram(telethon_id: int, entity_type: str) -> int:
    """
    Convert a Telethon internal ID back to full Telegram Bot API format.

    Args:
        telethon_id: Positive internal ID from Telethon entity
        entity_type: 'supergroup', 'channel', or 'group'

    Returns:
        Full Telegram format ID
    """
    if entity_type in ("supergroup", "channel"):
        return int(f"-100{telethon_id}")
    if entity_type == "group":
        return -telethon_id if telethon_id > 0 else telethon_id
    return telethon_id
