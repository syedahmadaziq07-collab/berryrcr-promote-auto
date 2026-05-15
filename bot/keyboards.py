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
            [KeyboardButton(text="🛒 Shop Zone"),      KeyboardButton(text="⚠️ Help Center")],
            [KeyboardButton(text="🔑 Recover Token"),  KeyboardButton(text="📚 Create Userbot")],
            [KeyboardButton(text="🎁 Get Free 100 Syiling")],
            [KeyboardButton(text="⚙️ Control Panel")],
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
            [KeyboardButton(text="🛍 Buy Userbot"),      KeyboardButton(text="💳 Reload Syiling")],
            [KeyboardButton(text="🛠️ Setup Month & Plan"),     KeyboardButton(text="📤 Send Syiling")],
            [KeyboardButton(text="🎁 Gift Userbot"),     KeyboardButton(text="🏆 Top Leaderboard")],
            [KeyboardButton(text="🏠 Back To Home")],
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
            text="⚡ PLUS — 300 Syiling / bulan",
            callback_data="buy_plan_select:PLUS",
        )],
        [InlineKeyboardButton(
            text="👑 PRO — 600 Syiling / bulan",
            callback_data="buy_plan_select:PRO",
        )],
        [InlineKeyboardButton(text="❌ Batal", callback_data="beli_userbot_cancel")],
    ])


def tambah_bulan_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚡ PLUS — 300 Syiling / bulan",
            callback_data="buy_plan_select_renew:PLUS",
        )],
        [InlineKeyboardButton(
            text="👑 PRO — 600 Syiling / bulan",
            callback_data="buy_plan_select_renew:PRO",
        )],
        [InlineKeyboardButton(text="❌ Batal", callback_data="tambah_bulan_cancel")],
    ])


def plan_duration_kb(plan_key: str, context: str) -> InlineKeyboardMarkup:
    """Keyboard pilih tempoh 1-12 bulan, 3 button setiap baris."""
    buttons = []
    row = []
    for m in range(1, 13):
        row.append(InlineKeyboardButton(
            text=f"{m} bulan",
            callback_data=f"plan_dur:{context}:{plan_key}:{m}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    back_map = {
        "buy":    "beli_userbot_back",
        "act":    "act_plan_select",
        "sub":    "buy_userbot",
        "renew":  "tambah_bulan_plan_back",
    }
    buttons.append([InlineKeyboardButton(text="⬅️ Kembali", callback_data=back_map.get(context, "main_menu"))])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plan_confirm_final_kb(context: str, plan_key: str, months: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Confirm",
            callback_data=f"plan_final:{context}:{plan_key}:{months}",
        )],
        [InlineKeyboardButton(
            text="⬅️ Back",
            callback_data=f"plan_dur_back:{context}:{plan_key}",
        )],
    ])


def activate_plan_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ PLUS",  callback_data="activate_plus"),
            InlineKeyboardButton(text="👑 PRO",   callback_data="activate_pro"),
        ],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data="main_menu")],
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
            InlineKeyboardButton(text="👥 Manage Group",        callback_data="groups_manage"),
            InlineKeyboardButton(text="📝 Message List",        callback_data="bcast_menu"),
        ],
        [
            InlineKeyboardButton(text="✏️ Edit Message",        callback_data="set_message"),
            InlineKeyboardButton(text="⏱️ Delay Timer",         callback_data="set_delay"),
        ],
        [
            InlineKeyboardButton(text="🪪 Status Account",      callback_data="status"),
            InlineKeyboardButton(text="🤖 Auto Reply",          callback_data="autoreply_menu"),
        ],
        [
            InlineKeyboardButton(text="🕒 Active Schedule",     callback_data="schedule_menu"),
            InlineKeyboardButton(text="🧪 Advanced Mode",       callback_data="expert_menu"),
        ],
        [
            InlineKeyboardButton(text="🔔 Notification",        callback_data="notif_menu"),
            InlineKeyboardButton(text="📩 Backup Email",        callback_data="email_menu"),
        ],
        [
            InlineKeyboardButton(text="🚀 Start Promote",       callback_data="start_promote"),
            InlineKeyboardButton(text="🛑 Stop Promote",        callback_data="stop_promote"),
        ],
        [InlineKeyboardButton(text="⬅️ Back",                   callback_data="main_menu")],
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

    # ── Live counter row (non-clickable info) ──
    count = len(selected_ids)
    if count == 0:
        counter_text = "◻️ Belum pilih kumpulan"
    elif count == 1:
        counter_text = "✅ Dipilih: 1 kumpulan"
    else:
        counter_text = f"✅ Dipilih: {count} kumpulan"
    buttons.append([
        InlineKeyboardButton(text=counter_text, callback_data="groups_counter_noop"),
    ])

    # ── Group list ──
    for g in groups:
        gid   = g["id"]
        title = g["title"][:30]
        check = "✅" if gid in selected_ids else "◻️"
        ttype = g.get("target_type", "group")
        icon  = "📢" if ttype == "channel" else ("👥" if ttype == "supergroup" else "💬")
        buttons.append([
            InlineKeyboardButton(
                text=f"{check} {icon} {title}",
                callback_data=f"toggle_group_{gid}",
            )
        ])

    # ── Action buttons ──
    buttons.append([
        InlineKeyboardButton(text="💾 Save Selection", callback_data="save_groups"),
    ])
    buttons.append([
        InlineKeyboardButton(text="↩️ Back", callback_data="groups_manage"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def delay_timer_kb(current: int = 0) -> InlineKeyboardMarkup:
    """Grid butang timer 5m–300m, gandaan 5 minit, 6 butang setiap baris."""
    buttons = []
    row = []
    for m in range(5, 305, 5):
        label = f"✅ {m}m" if m == current else f"{m}m"
        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"delay_set:{m}",
        ))
        if len(row) == 6:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="⬅️ Kembali", callback_data="set_delay_back")])
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


def schedule_preset_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 24 Jam Running",  callback_data="schedule_preset_24jam")],
        [InlineKeyboardButton(text="🔥 Peak Hour (20:00–00:30)",   callback_data="schedule_preset_peak")],
        [InlineKeyboardButton(text="🌙 Night Seller (22:00–02:00)", callback_data="schedule_preset_night")],
        [InlineKeyboardButton(text="☀️ Day Time (09:00–17:00)",     callback_data="schedule_preset_day")],
        [InlineKeyboardButton(text="✏️ Custom Time",    callback_data="schedule_custom")],
        [InlineKeyboardButton(text="❌ Cancel",          callback_data="schedule_menu")],
    ])
