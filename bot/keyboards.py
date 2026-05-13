from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from config import COIN_TOPUP_PACKAGES


# ─────────────────────────────────────────────
# MAIN MENU — Reply Keyboard
# ─────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Kedai"),           KeyboardButton(text="⚠️ Bantuan")],
            [KeyboardButton(text="🔑 Log Masuk Token"), KeyboardButton(text="📚 Buat Userbot")],
            [KeyboardButton(text="⚙️ Tetapan")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ─────────────────────────────────────────────
# KEDAI — Reply Keyboard (persistent bawah)
# ─────────────────────────────────────────────

def kedai_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏆 Papan Pendahulu"), KeyboardButton(text="📤 Hantar Syiling")],
            [KeyboardButton(text="🛍 Beli Userbot"),    KeyboardButton(text="💳 Topup Syiling")],
            [KeyboardButton(text="🎁 Gift Userbot")],
            [KeyboardButton(text="🌐 Laman Utama")],
            [KeyboardButton(text="⬅️ Kembali")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ─────────────────────────────────────────────
# TOPUP — Reply Keyboard (pakej pilihan)
# ─────────────────────────────────────────────

def topup_packages_reply_kb() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=f"🪙 {pkg['label']}")] for pkg in COIN_TOPUP_PACKAGES]
    rows.append([KeyboardButton(text="⬅️ Kembali")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ─────────────────────────────────────────────
# BELI USERBOT — Pilih Pelan (Inline)
# ─────────────────────────────────────────────

def beli_userbot_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⭐ PLUS — 300 Syiling (RM3)",
            callback_data="buy_plan_select:PLUS",
        )],
        [InlineKeyboardButton(
            text="🔥 PRO — 600 Syiling (RM6)",
            callback_data="buy_plan_select:PRO",
        )],
        [InlineKeyboardButton(
            text="💎 PREMIUM — 1,000 Syiling (RM10)",
            callback_data="buy_plan_select:PREMIUM",
        )],
        [InlineKeyboardButton(text="❌ Batal", callback_data="beli_userbot_cancel")],
    ])


def beli_userbot_confirm_kb(plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Ya, Beli Sekarang",
            callback_data=f"buy_plan_confirm:{plan_key}",
        )],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data="beli_userbot_back")],
    ])


# ─────────────────────────────────────────────
# TOPUP — Inline Keyboard: Pilih Pakej
# ─────────────────────────────────────────────

def topup_packages_inline_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"🪙 {pkg['label']}",
            callback_data=f"topup_pkg:{pkg['coins']}:{pkg['price_rm']:.2f}",
        )]
        for pkg in COIN_TOPUP_PACKAGES
    ]
    buttons.append([InlineKeyboardButton(text="❌ Batal", callback_data="topup_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def topup_order_summary_kb(coins: int, amount: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Teruskan Pembayaran", callback_data=f"topup_proceed:{coins}:{amount:.2f}")],
        [InlineKeyboardButton(text="❌ Batal Pesanan",       callback_data="topup_cancel")],
    ])


def topup_payment_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Saya Sudah Bayar",  callback_data=f"topup_paid:{order_id}")],
        [InlineKeyboardButton(text="❌ Batal Pesanan",     callback_data="topup_cancel")],
    ])


def topup_request_admin_kb(
    order_id: str,
    user_id: int,
    coins: int,
    amount_rm: float,
) -> InlineKeyboardMarkup:
    """
    Encode user_id, coins, amount_rm dalam callback_data supaya admin boleh
    approve/reject TANPA bergantung pada table topup_requests di DB.
    Format: tr_approve:{user_id}:{coins}:{amount_rm:.2f}:{order_id}
    """
    approve_data = f"tr_approve:{user_id}:{coins}:{amount_rm:.2f}:{order_id}"
    reject_data  = f"tr_reject:{user_id}:{order_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=approve_data),
            InlineKeyboardButton(text="❌ Reject",  callback_data=reject_data),
        ]
    ])


# ─────────────────────────────────────────────
# TETAPAN — Inline Keyboard
# ─────────────────────────────────────────────

def tetapan_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Kumpulan",            callback_data="groups_manage"),
            InlineKeyboardButton(text="📋 Senarai Mesej",       callback_data="bcast_menu"),
        ],
        [
            InlineKeyboardButton(text="📝 Tetapkan Mesej",      callback_data="set_message"),
            InlineKeyboardButton(text="⏱️ Jarak Masa",          callback_data="set_delay"),
        ],
        [
            InlineKeyboardButton(text="📋 Status Akaun",        callback_data="status"),
            InlineKeyboardButton(text="🤖 Balas Auto",          callback_data="autoreply_menu"),
        ],
        [
            InlineKeyboardButton(text="🕐 Jadual Aktif",        callback_data="schedule_menu"),
            InlineKeyboardButton(text="🔬 Mod Lanjutan",        callback_data="expert_menu"),
        ],
        [
            InlineKeyboardButton(text="🔕 Pemberitahuan",       callback_data="notif_menu"),
            InlineKeyboardButton(text="📧 Emel Sandaran",       callback_data="email_menu"),
        ],
        [
            InlineKeyboardButton(text="🎁 Kod Rujukan",         callback_data="referral_menu"),
        ],
        [
            InlineKeyboardButton(text="🚀 Mula Promote",        callback_data="start_promote"),
            InlineKeyboardButton(text="⏹️ Henti Promote",       callback_data="stop_promote"),
        ],
        [InlineKeyboardButton(text="🔙 Kembali",                callback_data="main_menu")],
    ])


# ─────────────────────────────────────────────
# BUAT USERBOT — Inline Keyboard
# ─────────────────────────────────────────────

def buat_userbot_kb(has_userbot: bool, has_plan: bool, has_session: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if not has_userbot:
        buttons.append([
            InlineKeyboardButton(text="🛍 Beli Userbot di Kedai", callback_data="goto_kedai"),
        ])
    else:
        if not has_session:
            buttons.append([
                InlineKeyboardButton(text="📱 Sambung Akaun", callback_data="buat_sambung_akaun"),
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text="🔌 Putuskan Sambungan", callback_data="disconnect_account"),
            ])
        if not has_plan:
            buttons.append([
                InlineKeyboardButton(text="⭐ PLUS",    callback_data="activate_plus"),
                InlineKeyboardButton(text="🔥 PRO",     callback_data="activate_pro"),
                InlineKeyboardButton(text="💎 PREMIUM", callback_data="activate_premium"),
            ])
        buttons.append([
            InlineKeyboardButton(text="📤 Pindah Userbot", callback_data="transfer_userbot_start"),
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plan_confirm_kb(plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ya, Aktifkan", callback_data=f"confirm_activate_{plan_key.lower()}"),
            InlineKeyboardButton(text="❌ Batal",         callback_data="main_menu"),
        ]
    ])


# ─────────────────────────────────────────────
# SHARED — Inline
# ─────────────────────────────────────────────

def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Menu Utama", callback_data="main_menu")],
    ])


def confirm_kb(confirm_data: str, cancel_data: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ya, Teruskan", callback_data=confirm_data),
            InlineKeyboardButton(text="❌ Batal",        callback_data=cancel_data),
        ]
    ])


def groups_selection_kb(groups: list, selected_ids: set) -> InlineKeyboardMarkup:
    buttons = []
    for g in groups:
        gid   = g["id"]
        title = g["title"][:30]
        check = "✅ " if gid in selected_ids else "◻️ "
        buttons.append([
            InlineKeyboardButton(
                text=f"{check}{title}",
                callback_data=f"toggle_group_{gid}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="💾 Simpan Pilihan", callback_data="save_groups"),
        InlineKeyboardButton(text="🔙 Kembali",        callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Batal", callback_data="main_menu")],
    ])


def disconnect_account_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔌 Putuskan Sambungan", callback_data="disconnect_account")],
        [InlineKeyboardButton(text="🔙 Kembali",             callback_data="main_menu")],
    ])


def request_phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Hantar Nombor", request_contact=True)],
            [KeyboardButton(text="❌ Batal")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
