from handlers.admin import router as admin_router
from handlers.start import router as start_router
from handlers.kedai import router as kedai_router
from handlers.buat_userbot import router as buat_userbot_router
from handlers.plan_flow import router as plan_flow_router
from handlers.account import router as account_router
from handlers.tetapan import router as tetapan_router
from handlers.promote import router as promote_router
from handlers.help import router as help_router
from handlers.status import router as status_router
from handlers.groups import router as groups_router
from handlers.messages import router as messages_router
from handlers.autoreply import router as autoreply_router
from handlers.schedule import router as schedule_router
from handlers.settings import router as settings_router
from handlers.referral import router as referral_router
from handlers.expert import router as expert_router
from handlers.subscription import router as subscription_router
from handlers.fallback import router as fallback_router

all_routers = [
    admin_router,           # Admin commands first
    start_router,           # /start + main_menu callback
    kedai_router,           # 🛒 Kedai + semua transaksi
    buat_userbot_router,    # 📚 Buat Userbot + aktif pelan
    plan_flow_router,       # 🗓️ Shared plan duration & purchase flow
    subscription_router,    # 🛒 Beli Userbot reply kb + sub context
    account_router,         # 🔑 Log Masuk Token (FSM OTP)
    status_router,          # 🪪 Status Account
    groups_router,          # 👥 Urus Kumpulan (view/add/remove/clear)
    messages_router,        # 📋 Senarai Mesej Sebarkan
    autoreply_router,       # 🤖 Balas Automatik
    schedule_router,        # 🕐 Jadual Aktif
    settings_router,        # 🔕 Pemberitahuan + 📧 Emel Sandaran
    referral_router,        # 🎁 Kod Rujukan
    expert_router,          # 🔬 Mod Lanjutan
    promote_router,         # 🚀 Mula/Henti Promote (reply kb + inline cb)
    tetapan_router,         # ⚙️ Tetapan (mesej, jarak masa)
    help_router,            # ⚠️ Bantuan
    fallback_router,        # MESTI terakhir — catch-all
]
