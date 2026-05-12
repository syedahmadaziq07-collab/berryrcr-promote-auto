import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

SESSIONS_DIR = BASE_DIR / "sessions"
MEDIA_DIR = BASE_DIR / "media"

for _d in (SESSIONS_DIR, MEDIA_DIR):
    _d.mkdir(exist_ok=True)

COIN_PLANS = {
    "PLUS": {
        "name": "PLUS",
        "coins": 300,
        "price_rm": 3.0,
        "footer_required": True,
    },
    "PRO": {
        "name": "PRO",
        "coins": 600,
        "price_rm": 6.0,
        "footer_required": False,
    },
}

COIN_TOPUP_PACKAGES = [
    {"coins": 300,  "price_rm": 3.0,  "label": "300 Syiling — RM3"},
    {"coins": 600,  "price_rm": 6.0,  "label": "600 Syiling — RM6"},
    {"coins": 1200, "price_rm": 12.0, "label": "1,200 Syiling — RM12"},
]

USERBOT_PRICE = 50

WEBSITE_URL = "https://t.me/berryrcr"

MIN_DELAY_MINUTES = 30

MANDATORY_FOOTER = (
    "\n━━━━━━━━━━━━━━━\n"
    "🤖 Auto Promote by @berryrcr"
)
