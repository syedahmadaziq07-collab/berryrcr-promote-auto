from handlers.admin import router as admin_router
from handlers.start import router as start_router
from handlers.kedai import router as kedai_router
from handlers.buat_userbot import router as buat_userbot_router
from handlers.account import router as account_router
from handlers.tetapan import router as tetapan_router
from handlers.help import router as help_router
from handlers.fallback import router as fallback_router

all_routers = [
    admin_router,           # Admin commands first
    start_router,           # /start + main_menu callback
    kedai_router,           # 🛒 Kedai + semua transaksi
    buat_userbot_router,    # 📚 Buat Userbot + aktif pelan
    account_router,         # 🔑 Log Masuk Token (FSM OTP)
    tetapan_router,         # ⚙️ Tetapan (groups, mesej, jarak masa, promote, status)
    help_router,            # ⚠️ Bantuan
    fallback_router,        # MESTI terakhir — catch-all
]
