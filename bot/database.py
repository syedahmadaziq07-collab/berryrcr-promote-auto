"""
database.py — Semua operasi database menggunakan Supabase (async).

NOTE: Jadual pengguna dinamakan 'bot_users' (bukan 'users') untuk
elak konflik dengan jadual auth.users bawaan Supabase.

Jadual tambahan diperlukan (jalankan dalam Supabase SQL Editor):

CREATE TABLE userbots (
  id          BIGSERIAL PRIMARY KEY,
  userbot_id  TEXT UNIQUE NOT NULL,
  owner_id    BIGINT REFERENCES bot_users(id),
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  is_active   BOOLEAN DEFAULT TRUE
);
"""

import logging
import string
import random
from services.supabase_service import get_client

logger = logging.getLogger(__name__)

_USERS = "bot_users"


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

async def is_new_user(user_id: int) -> bool:
    client = await get_client()
    res = await client.table(_USERS).select("id").eq("id", user_id).execute()
    return len(res.data) == 0


async def ensure_user(user_id: int, username: str, full_name: str):
    client = await get_client()
    await client.table(_USERS).upsert(
        {"id": user_id, "username": username, "full_name": full_name},
        on_conflict="id",
    ).execute()
    await client.table("wallets").upsert(
        {"user_id": user_id, "coins": 0, "total_topup_rm": 0},
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()
    await client.table("promo_settings").upsert(
        {"user_id": user_id, "delay_minutes": 60, "is_running": False},
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()


async def get_user_by_id(user_id: int):
    client = await get_client()
    res = await client.table(_USERS).select("id, username, full_name").eq("id", user_id).execute()
    return res.data[0] if res.data else None


# ─────────────────────────────────────────────
# WALLETS
# ─────────────────────────────────────────────

async def get_wallet(user_id: int) -> int:
    try:
        client = await get_client()
        res = await client.table("wallets").select("coins").eq("user_id", user_id).execute()
        if not res.data:
            await client.table("wallets").upsert(
                {"user_id": user_id, "coins": 0, "total_topup_rm": 0},
                on_conflict="user_id",
            ).execute()
            return 0
        return res.data[0]["coins"]
    except Exception as e:
        logger.warning("get_wallet error uid=%s: %s", user_id, e)
        return 0


async def add_coins(user_id: int, amount: int, description: str = "Tambah syiling"):
    client = await get_client()
    balance = await get_wallet(user_id)
    await client.table("wallets").upsert(
        {"user_id": user_id, "coins": balance + amount},
        on_conflict="user_id",
    ).execute()
    await client.table("transactions").insert({
        "user_id": user_id,
        "type": "credit",
        "amount": amount,
        "description": description,
    }).execute()


async def deduct_coins(user_id: int, amount: int, description: str = "Tolak syiling") -> bool:
    client = await get_client()
    balance = await get_wallet(user_id)
    if balance < amount:
        return False
    await client.table("wallets").update(
        {"coins": balance - amount}
    ).eq("user_id", user_id).execute()
    await client.table("transactions").insert({
        "user_id": user_id,
        "type": "debit",
        "amount": amount,
        "description": description,
    }).execute()
    return True


async def transfer_coins(from_id: int, to_id: int, amount: int, description: str = "Pindah syiling") -> bool:
    client = await get_client()
    from_balance = await get_wallet(from_id)
    if from_balance < amount:
        return False
    await client.table("wallets").update({"coins": from_balance - amount}).eq("user_id", from_id).execute()
    to_balance = await get_wallet(to_id)
    await client.table("wallets").upsert(
        {"user_id": to_id, "coins": to_balance + amount}, on_conflict="user_id"
    ).execute()
    await client.table("transactions").insert({
        "user_id": from_id, "type": "debit", "amount": amount,
        "description": f"Hantar ke {to_id} — {description}",
    }).execute()
    await client.table("transactions").insert({
        "user_id": to_id, "type": "credit", "amount": amount,
        "description": f"Terima dari {from_id} — {description}",
    }).execute()
    return True


# ─────────────────────────────────────────────
# SUBSCRIPTIONS (Pelan PLUS/PRO)
# ─────────────────────────────────────────────

async def get_active_subscription(user_id: int):
    client = await get_client()
    res = (
        await client.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def create_subscription(user_id: int, plan: str):
    client = await get_client()
    await client.table("subscriptions").update({"active": False}).eq("user_id", user_id).execute()
    await client.table("subscriptions").insert(
        {"user_id": user_id, "plan": plan, "active": True}
    ).execute()


# ─────────────────────────────────────────────
# USERBOTS
# ─────────────────────────────────────────────

def _generate_userbot_id(user_id: int) -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"UB-{user_id}-{suffix}"


async def get_userbot(user_id: int):
    client = await get_client()
    try:
        res = await client.table("userbots").select("*").eq("owner_id", user_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.warning(f"get_userbot error: {e}")
        return None


async def create_userbot(user_id: int) -> str:
    client = await get_client()
    existing = await get_userbot(user_id)
    if existing:
        return existing["userbot_id"]

    userbot_id = _generate_userbot_id(user_id)
    for _ in range(10):
        try:
            check = await client.table("userbots").select("id").eq("userbot_id", userbot_id).execute()
            if not check.data:
                break
        except Exception:
            break
        userbot_id = _generate_userbot_id(user_id)

    await client.table("userbots").insert({
        "userbot_id": userbot_id,
        "owner_id": user_id,
        "is_active": True,
    }).execute()
    return userbot_id


async def get_userbot_by_id(userbot_id: str):
    client = await get_client()
    try:
        res = await client.table("userbots").select("*").eq("userbot_id", userbot_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.warning(f"get_userbot_by_id error: {e}")
        return None


async def transfer_userbot(userbot_id: str, new_owner_id: int):
    client = await get_client()
    await client.table("userbots").update({"owner_id": new_owner_id}).eq("userbot_id", userbot_id).execute()


# ─────────────────────────────────────────────
# LEADERBOARD
# ─────────────────────────────────────────────

async def get_leaderboard(limit: int = 10) -> list:
    client = await get_client()
    res = await client.table("transactions").select("user_id, amount").eq("type", "debit").execute()
    totals: dict = {}
    for row in (res.data or []):
        uid = row["user_id"]
        totals[uid] = totals.get(uid, 0) + row["amount"]
    sorted_users = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"user_id": uid, "total": total} for uid, total in sorted_users]


# ─────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────

async def get_session(user_id: int):
    client = await get_client()
    res = await client.table("sessions").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


async def save_session(
    user_id: int,
    phone: str,
    session_string: str,
    tg_username: str = "",
    userbot_id: str = "",
):
    """
    Simpan atau kemaskini session dalam Supabase.

    Migration SQL diperlukan (jalankan dalam Supabase SQL Editor jika belum ada):
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS userbot_id TEXT;
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS tg_username TEXT;
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;
    """
    from datetime import datetime, timezone
    client = await get_client()
    payload = {
        "user_id": user_id,
        "phone_number": phone,
        "session_string": session_string,
        "tg_username": tg_username,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "userbot_id": userbot_id,
    }
    try:
        await client.table("sessions").upsert(payload, on_conflict="user_id").execute()
    except Exception:
        # Fallback: simpan tanpa kolum optional jika belum wujud
        await client.table("sessions").upsert(
            {"user_id": user_id, "phone_number": phone, "session_string": session_string},
            on_conflict="user_id",
        ).execute()


async def delete_session(user_id: int):
    client = await get_client()
    await client.table("sessions").delete().eq("user_id", user_id).execute()


async def get_session_by_userbot_id(userbot_id: str):
    """Cari session berdasarkan userbot_id."""
    client = await get_client()
    try:
        res = await client.table("sessions").select("*").eq("userbot_id", userbot_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.warning("get_session_by_userbot_id error: %s", e)
        return None


async def transfer_userbot_session(from_user_id: int, to_user_id: int):
    """Pindah session (termasuk userbot_id) dari satu user ke user lain."""
    client = await get_client()
    session = await get_session(from_user_id)
    if not session:
        return
    await delete_session(from_user_id)
    await client.table("sessions").upsert(
        {
            "user_id": to_user_id,
            "phone_number": session.get("phone_number", ""),
            "session_string": session.get("session_string", ""),
            "tg_username": session.get("tg_username", ""),
            "userbot_id": session.get("userbot_id", ""),
            "connected_at": session.get("connected_at"),
        },
        on_conflict="user_id",
    ).execute()


# ─────────────────────────────────────────────
# SELECTED GROUPS
# ─────────────────────────────────────────────

async def get_selected_groups(user_id: int):
    client = await get_client()
    res = await client.table("selected_groups").select("*").eq("user_id", user_id).execute()
    return res.data or []


async def save_selected_groups(user_id: int, groups: list):
    client = await get_client()
    await client.table("selected_groups").delete().eq("user_id", user_id).execute()
    if groups:
        rows = [
            {
                "user_id": user_id,
                "group_id": str(g["id"]),
                "group_title": g["title"],
                "group_username": g.get("username"),
            }
            for g in groups
        ]
        await client.table("selected_groups").insert(rows).execute()


# ─────────────────────────────────────────────
# PROMO SETTINGS
# ─────────────────────────────────────────────

async def get_promo_settings(user_id: int):
    client = await get_client()
    res = await client.table("promo_settings").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


async def update_promo_message(user_id: int, message_text: str):
    client = await get_client()
    await client.table("promo_settings").upsert(
        {"user_id": user_id, "message_text": message_text},
        on_conflict="user_id",
    ).execute()


async def update_promo_delay(user_id: int, delay_minutes: int):
    client = await get_client()
    await client.table("promo_settings").upsert(
        {"user_id": user_id, "delay_minutes": delay_minutes},
        on_conflict="user_id",
    ).execute()


async def set_promo_running(user_id: int, running: bool):
    client = await get_client()
    await client.table("promo_settings").update(
        {"is_running": running}
    ).eq("user_id", user_id).execute()


async def get_all_running_promos():
    client = await get_client()
    res = await client.table("promo_settings").select("*").eq("is_running", True).execute()
    return res.data or []


# ─────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────

async def get_transactions(user_id: int, limit: int = 10):
    client = await get_client()
    res = (
        await client.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────
# ADMIN — USERS
# ─────────────────────────────────────────────

async def get_user_count() -> int:
    client = await get_client()
    res = await client.table(_USERS).select("id", count="exact").execute()
    return res.count or 0


async def get_recent_users(limit: int = 10) -> list:
    client = await get_client()
    res = (
        await client.table(_USERS)
        .select("id, username, full_name, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def get_user_info(user_id: int):
    client = await get_client()
    u = await client.table(_USERS).select("*").eq("id", user_id).execute()
    if not u.data:
        return None
    user = u.data[0]
    w = await client.table("wallets").select("coins").eq("user_id", user_id).execute()
    user["balance"] = w.data[0]["coins"] if w.data else 0
    s = (
        await client.table("subscriptions")
        .select("plan")
        .eq("user_id", user_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    user["plan"] = s.data[0]["plan"] if s.data else "Tiada"
    return user


async def get_all_user_ids() -> list:
    client = await get_client()
    res = await client.table(_USERS).select("id").execute()
    return [row["id"] for row in res.data] if res.data else []


# ─────────────────────────────────────────────
# ADMIN — SESSIONS
# ─────────────────────────────────────────────

async def get_all_sessions() -> list:
    client = await get_client()
    res = (
        await client.table("sessions")
        .select("user_id, phone_number, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────
# ADMIN — SALES
# ─────────────────────────────────────────────

async def get_sales_summary() -> dict:
    from datetime import date
    client = await get_client()

    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    res_today = (
        await client.table("transactions")
        .select("amount")
        .eq("type", "credit")
        .gte("created_at", today)
        .execute()
    )
    res_month = (
        await client.table("transactions")
        .select("amount")
        .eq("type", "credit")
        .gte("created_at", month_start)
        .execute()
    )
    res_all = (
        await client.table("transactions")
        .select("amount")
        .eq("type", "credit")
        .execute()
    )

    def _total(rows):
        return sum(r["amount"] for r in rows) if rows else 0

    def _rm(coins):
        return round(coins / 300 * 3, 2)

    coins_today = _total(res_today.data)
    coins_month = _total(res_month.data)
    coins_all   = _total(res_all.data)

    return {
        "coins_today": coins_today, "rm_today": _rm(coins_today),
        "tx_today": len(res_today.data or []),
        "coins_month": coins_month, "rm_month": _rm(coins_month),
        "tx_month": len(res_month.data or []),
        "coins_all": coins_all, "rm_all": _rm(coins_all),
        "tx_all": len(res_all.data or []),
    }


# ─────────────────────────────────────────────
# ADMIN LOGS
# ─────────────────────────────────────────────

async def write_admin_log(admin_id: int, action: str, target_user_id: int = None, notes: str = None):
    client = await get_client()
    await client.table("admin_logs").insert({
        "admin_id": admin_id,
        "action": action,
        "target_user_id": target_user_id,
        "notes": notes,
    }).execute()


async def get_admin_logs(limit: int = 20):
    client = await get_client()
    res = (
        await client.table("admin_logs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────
# DAILY REPORTS
# ─────────────────────────────────────────────

async def upsert_daily_report(date_str: str, new_users: int = 0,
                               total_messages_sent: int = 0, total_coins_added: int = 0):
    client = await get_client()
    await client.table("daily_reports").upsert(
        {
            "report_date": date_str,
            "new_users": new_users,
            "total_messages_sent": total_messages_sent,
            "total_coins_added": total_coins_added,
        },
        on_conflict="report_date",
    ).execute()


async def get_daily_reports(limit: int = 7):
    client = await get_client()
    res = (
        await client.table("daily_reports")
        .select("*")
        .order("report_date", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────
# TOPUP REQUESTS (topup_requests table)
# ─────────────────────────────────────────────

def _generate_order_id() -> str:
    """Generate order_id format: ORDxxxxxxxx (8 random digits)."""
    return "ORD" + "".join([str(random.randint(0, 9)) for _ in range(8)])


async def create_topup_request(
    user_id: int,
    username: str,
    coins: int,
    amount_rm: float,
) -> str:
    """Simpan topup_request baru dengan status pending. Pulangkan order_id."""
    client = await get_client()
    order_id = _generate_order_id()
    for _ in range(5):
        try:
            check = await client.table("topup_requests").select("order_id").eq("order_id", order_id).execute()
            if not check.data:
                break
        except Exception:
            break
        order_id = _generate_order_id()

    await client.table("topup_requests").insert({
        "order_id": order_id,
        "user_id": user_id,
        "username": username,
        "coins": coins,
        "amount_rm": amount_rm,
        "status": "pending",
    }).execute()
    return order_id


async def update_topup_receipt(order_id: str, receipt_file_id: str):
    """Simpan receipt_file_id dan set status = waiting_approval."""
    client = await get_client()
    await client.table("topup_requests").update({
        "receipt_file_id": receipt_file_id,
        "status": "waiting_approval",
    }).eq("order_id", order_id).execute()


async def get_topup_request(order_id: str):
    client = await get_client()
    res = await client.table("topup_requests").select("*").eq("order_id", order_id).execute()
    return res.data[0] if res.data else None


async def approve_topup_request(order_id: str, admin_id: int):
    """Approve topup_request. Pulangkan data atau None jika tiada/sudah diproses."""
    from datetime import datetime, timezone
    client = await get_client()
    res = (
        await client.table("topup_requests")
        .update({
            "status": "approved",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": admin_id,
        })
        .eq("order_id", order_id)
        .eq("status", "waiting_approval")
        .execute()
    )
    return res.data[0] if res.data else None


async def reject_topup_request(order_id: str, admin_id: int):
    """Reject topup_request. Pulangkan data atau None jika tiada/sudah diproses."""
    from datetime import datetime, timezone
    client = await get_client()
    res = (
        await client.table("topup_requests")
        .update({
            "status": "rejected",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": admin_id,
        })
        .eq("order_id", order_id)
        .eq("status", "waiting_approval")
        .execute()
    )
    return res.data[0] if res.data else None


async def get_pending_topup_requests(limit: int = 20) -> list:
    client = await get_client()
    res = (
        await client.table("topup_requests")
        .select("*")
        .eq("status", "waiting_approval")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return res.data or []
