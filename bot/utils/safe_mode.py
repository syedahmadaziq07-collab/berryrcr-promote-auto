"""
safe_mode.py — Konstanta dan pengiraan untuk Auto Safe Mode.

Safe mode diaktifkan apabila Telegram returns FloodWait atau PeerFlood
semasa promote. Delay ditingkatkan sementara, kemudian auto-restore
selepas cooldown 2 jam.
"""

import math
from datetime import datetime, timedelta
import pytz

MY_TZ = pytz.timezone("Asia/Kuala_Lumpur")

COOLDOWN_HOURS = 2
SAFE_MODE_TABLE = "safe_mode_status"


def calc_safe_delay_flood(flood_seconds: int) -> int:
    """
    FloodWait: safe_delay = ceil(flood_seconds * 1.2 / 60), minimum 10 minit.
    Contoh: FloodWait(2700s) → ceil(2700 * 1.2 / 60) = ceil(54) = 54 minit
    """
    return max(10, math.ceil(flood_seconds * 1.2 / 60))


def calc_safe_delay_peerflood(original_delay: int) -> int:
    """
    PeerFlood: safe_delay = original_delay * 5, minimum 30 minit.
    Contoh: 20min → 100min
    """
    return max(30, original_delay * 5)


def cooldown_until_dt() -> datetime:
    """Kembalikan datetime UTC untuk 2 jam dari sekarang."""
    return datetime.utcnow().replace(tzinfo=pytz.utc) + timedelta(hours=COOLDOWN_HOURS)


def is_cooldown_expired(cooldown_until_str: str) -> bool:
    """
    Semak sama ada cooldown_until (ISO string dari DB) sudah tamat.
    """
    try:
        dt = datetime.fromisoformat(str(cooldown_until_str).replace("Z", "+00:00"))
        return datetime.now(pytz.utc) >= dt
    except Exception:
        return True


def format_cooldown_remaining(cooldown_until_str: str) -> str:
    """Kembalikan string 'Xj Ym' baki cooldown untuk paparan kepada user."""
    try:
        dt = datetime.fromisoformat(str(cooldown_until_str).replace("Z", "+00:00"))
        remaining = dt - datetime.now(pytz.utc)
        if remaining.total_seconds() <= 0:
            return "0m"
        total_mins = int(remaining.total_seconds() // 60)
        h, m = divmod(total_mins, 60)
        return f"{h}h {m}m" if h > 0 else f"{m}m"
    except Exception:
        return "?"
