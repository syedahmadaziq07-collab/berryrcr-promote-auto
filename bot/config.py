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
        "name": "PLUS ⭐",
        "coins": 300,
        "price_rm": 3.0,
        "footer_required": True,
        "features": [
            "Auto promote ke kumpulan pilihan",
            "Footer wajib @berryrcr",
            "Sokongan biasa",
        ],
    },
    "PRO": {
        "name": "PRO 🔥",
        "coins": 600,
        "price_rm": 6.0,
        "footer_required": False,
        "features": [
            "Auto promote ke kumpulan pilihan",
            "Boleh tutup footer",
            "Keutamaan sokongan",
        ],
    },
    "PREMIUM": {
        "name": "PREMIUM 💎",
        "coins": 1000,
        "price_rm": 10.0,
        "footer_required": False,
        "features": [
            "Auto promote ke kumpulan pilihan",
            "Boleh tutup footer",
            "Sokongan VIP 24/7",
            "Keutamaan tertinggi",
        ],
    },
}

COIN_TOPUP_PACKAGES = [
    {"coins": 300,  "price_rm": 3.0,  "label": "300 Syiling — RM3"},
    {"coins": 600,  "price_rm": 6.0,  "label": "600 Syiling — RM6"},
    {"coins": 900,  "price_rm": 9.0,  "label": "900 Syiling — RM9"},
    {"coins": 1200, "price_rm": 12.0, "label": "1,200 Syiling — RM12"},
    {"coins": 3000, "price_rm": 30.0, "label": "3,000 Syiling — RM30"},
]

# Bayaran pendaftaran userbot (disatukan dalam harga pelan)
USERBOT_PRICE = 0

WEBSITE_URL = "https://t.me/berryrcr"

MIN_DELAY_MINUTES = 30

MANDATORY_FOOTER = (
    "\n\n━━━━━━━━━━━━━━\n"
    "🌐 Promote Auto by @berryrcr_bot"
)
