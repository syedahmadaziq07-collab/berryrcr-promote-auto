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
    """
    Tambah syiling ke wallet secara ATOM menggunakan Supabase RPC.
    Elak race condition — gunakan SQL: coins = coins + amount.
    Fallback ke kaedah lama jika RPC belum dibuat.
    """
    client = await get_client()
    try:
        await client.rpc("add_coins", {"p_user_id": user_id, "p_amount": amount}).execute()
        logger.info("add_coins RPC OK uid=%s amount=%s", user_id, amount)
    except Exception as e:
        logger.warning("add_coins RPC gagal uid=%s — guna fallback: %s", user_id, e)
        balance = await get_wallet(user_id)
        await client.table("wallets").upsert(
            {"user_id": user_id, "coins": balance + amount},
            on_conflict="user_id",
        ).execute()
    try:
        await client.table("transactions").insert({
            "user_id": user_id,
            "type": "credit",
            "amount": amount,
            "description": description,
        }).execute()
    except Exception as e:
        logger.warning("transactions log skip uid=%s: %s", user_id, e)


async def deduct_coins(user_id: int, amount: int, description: str = "Tolak syiling") -> bool:
    """
    Tolak syiling dari wallet secara ATOM menggunakan Supabase RPC.
    Elak race condition — RPC akan raise exception jika baki tidak cukup.
    Fallback ke kaedah lama jika RPC belum dibuat.
    """
    client = await get_client()
    try:
        await client.rpc("deduct_coins", {"p_user_id": user_id, "p_amount": amount}).execute()
        logger.info("deduct_coins RPC OK uid=%s amount=%s", user_id, amount)
    except Exception as e:
        err_str = str(e).lower()
        if "baki tidak mencukupi" in err_str or "insufficient" in err_str:
            logger.info("deduct_coins RPC: baki tidak cukup uid=%s amount=%s", user_id, amount)
            return False
        logger.warning("deduct_coins RPC gagal uid=%s — guna fallback: %s", user_id, e)
        balance = await get_wallet(user_id)
        if balance < amount:
            return False
        await client.table("wallets").update(
            {"coins": balance - amount}
        ).eq("user_id", user_id).execute()
    try:
        await client.table("transactions").insert({
            "user_id": user_id,
            "type": "debit",
            "amount": amount,
            "description": description,
        }).execute()
    except Exception as e:
        logger.warning("transactions log skip uid=%s: %s", user_id, e)
    return True


async def transfer_coins(from_id: int, to_id: int, amount: int, description: str = "Pindah syiling") -> bool:
    """
    Pindah syiling antara dua wallet secara atomic menggunakan RPC.
    Fallback kepada 3-langkah berasingan jika RPC belum dibuat.
    """
    client = await get_client()
    try:
        result = await client.rpc(
            "transfer_coins",
            {
                "p_from_user_id": from_id,
                "p_to_user_id": to_id,
                "p_amount": amount,
                "p_description": description,
            },
        ).execute()
        if result.data and result.data.get("success"):
            logger.info("transfer_coins RPC berjaya: %s → %s (%d syiling)", from_id, to_id, amount)
            return True
        error_msg = result.data.get("error", "Tidak diketahui") if result.data else "RPC tiada data"
        logger.error("transfer_coins RPC gagal: %s", error_msg)
        return False
    except Exception as rpc_err:
        logger.warning("transfer_coins RPC tidak tersedia (%s) — guna fallback 3-langkah", rpc_err)
    # ── Fallback: 3 DB calls berasingan (tidak atomic) ──
    from_balance = await get_wallet(from_id)
    if from_balance < amount:
        return False
    await client.table("wallets").update({"coins": from_balance - amount}).eq("user_id", from_id).execute()
    to_balance = await get_wallet(to_id)
    await client.table("wallets").upsert(
        {"user_id": to_id, "coins": to_balance + amount}, on_conflict="user_id"
    ).execute()
    try:
        await client.table("transactions").insert({
            "user_id": from_id, "type": "debit", "amount": amount,
            "description": f"Hantar ke {to_id} — {description}",
        }).execute()
        await client.table("transactions").insert({
            "user_id": to_id, "type": "credit", "amount": amount,
            "description": f"Terima dari {from_id} — {description}",
        }).execute()
    except Exception as e:
        logger.warning("transactions log skip transfer (schema mungkin tidak lengkap): %s", e)
    return True


# ─────────────────────────────────────────────
# SUBSCRIPTIONS (Pelan PLUS/PRO/PREMIUM)
# ─────────────────────────────────────────────

async def get_active_subscription(user_id: int):
    """
    Dapatkan pelan aktif user.
    Resilient: Cuba filter by active=True dulu; jika column tiada, ambil rekod terbaru sahaja.
    """
    client = await get_client()
    try:
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
    except Exception as e:
        # Column 'active' atau 'created_at' mungkin tidak wujud — fallback ke rekod terbaru
        logger.warning("get_active_subscription fallback (schema lama) uid=%s: %s", user_id, e)
        try:
            res = (
                await client.table("subscriptions")
                .select("user_id,plan")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e2:
            logger.error("get_active_subscription gagal sepenuhnya uid=%s: %s", user_id, e2)
            return None


PLAN_DURATION_DAYS: dict[str, int] = {
    "PLUS": 30,
    "PRO": 30,
    "PREMIUM": 30,
}


async def create_subscription(user_id: int, plan: str):
    """
    Simpan subscription baru dengan expires_at dikira secara automatik.
    Resilient: Cuba set active=False pada rekod lama dulu; jika gagal (column tiada), teruskan insert.
    """
    from datetime import datetime, timezone, timedelta
    client = await get_client()
    try:
        await client.table("subscriptions").update({"active": False}).eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning("create_subscription: update active=False gagal uid=%s: %s (column mungkin tiada)", user_id, e)

    now = datetime.now(timezone.utc)
    duration_days = PLAN_DURATION_DAYS.get(plan.upper(), 30)
    expires_at = now + timedelta(days=duration_days)

    try:
        await client.table("subscriptions").insert({
            "user_id": user_id,
            "plan": plan,
            "active": True,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }).execute()
    except Exception as e:
        logger.warning("create_subscription: insert penuh gagal uid=%s: %s — cuba tanpa active/expires", user_id, e)
        await client.table("subscriptions").insert(
            {"user_id": user_id, "plan": plan}
        ).execute()
    logger.info("create_subscription: uid=%s plan=%s tamat=%s", user_id, plan, expires_at.strftime("%Y-%m-%d"))


# ─────────────────────────────────────────────
# USERBOTS
# ─────────────────────────────────────────────

def _generate_userbot_id(user_id: int) -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"UB-{user_id}-{suffix}"


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


async def get_userbot(user_id: int):
    """Ambil maklumat userbot user dari userbots table (canonical source untuk UB-ID)."""
    client = await get_client()
    try:
        res = await client.table("userbots").select("*").eq("owner_id", user_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.warning("get_userbot error uid=%s: %s", user_id, e)
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

    Jika sessions.userbot_id column belum wujud, jalankan dalam Supabase SQL Editor:
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS userbot_id    TEXT;
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS tg_username   TEXT;
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS connected_at  TIMESTAMPTZ;
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
        logger.info("save_session OK uid=%s userbot_id=%s", user_id, userbot_id or "kosong")
    except Exception as e:
        # Column optional (userbot_id/tg_username/connected_at) mungkin belum wujud
        logger.error(
            "save_session PENUH gagal uid=%s: %s\n"
            "  ⚠️  KRITIS: sessions.userbot_id TIDAK DISIMPAN!\n"
            "  Jalankan migration SQL dalam Supabase:\n"
            "    ALTER TABLE sessions ADD COLUMN IF NOT EXISTS userbot_id   TEXT;\n"
            "    ALTER TABLE sessions ADD COLUMN IF NOT EXISTS tg_username  TEXT;\n"
            "    ALTER TABLE sessions ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;\n"
            "  Fallback: menyimpan session tanpa userbot_id...",
            user_id, e,
        )
        try:
            await client.table("sessions").upsert(
                {"user_id": user_id, "phone_number": phone, "session_string": session_string},
                on_conflict="user_id",
            ).execute()
            logger.warning("save_session FALLBACK OK uid=%s — USERBOT_ID HILANG dari sessions", user_id)
        except Exception as e2:
            logger.error("save_session FALLBACK juga gagal uid=%s: %s", user_id, e2)
            raise


async def ensure_userbot_registered(user_id: int, userbot_id: str) -> bool:
    """
    Pastikan userbot_id disimpan dalam userbots table.
    Ini adalah penyimpanan BACKUP supaya Log Masuk Token berfungsi
    walaupun sessions.userbot_id column gagal disimpan.
    Returns True jika berjaya.
    """
    client = await get_client()
    try:
        existing = await client.table("userbots").select("id, userbot_id").eq("owner_id", user_id).execute()
        if existing.data:
            current_ub_id = existing.data[0].get("userbot_id", "")
            if current_ub_id != userbot_id:
                await client.table("userbots").update(
                    {"userbot_id": userbot_id, "is_active": True}
                ).eq("owner_id", user_id).execute()
                logger.info("ensure_userbot_registered UPDATE uid=%s ub_id=%s (ganti: %s)", user_id, userbot_id, current_ub_id)
            else:
                logger.info("ensure_userbot_registered SUDAH ADA uid=%s ub_id=%s", user_id, userbot_id)
        else:
            await client.table("userbots").insert({
                "userbot_id": userbot_id,
                "owner_id": user_id,
                "is_active": True,
            }).execute()
            logger.info("ensure_userbot_registered INSERT uid=%s ub_id=%s", user_id, userbot_id)
        return True
    except Exception as e:
        logger.error("ensure_userbot_registered GAGAL uid=%s ub_id=%s: %s", user_id, userbot_id, e)
        return False


async def delete_session(user_id: int):
    client = await get_client()
    await client.table("sessions").delete().eq("user_id", user_id).execute()


async def get_session_by_userbot_id(userbot_id: str):
    """
    Cari session berdasarkan userbot_id — dual-lookup:
      Kaedah 1: sessions.userbot_id (jika column wujud)
      Kaedah 2: userbots.owner_id → sessions (backup jika sessions column kosong)
    """
    client = await get_client()

    # ── Kaedah 1: sessions.userbot_id ──
    try:
        res = await client.table("sessions").select("*").eq("userbot_id", userbot_id).execute()
        if res.data:
            logger.info("get_session_by_userbot_id FOUND (kaedah 1 — sessions): ub_id=%s uid=%s",
                        userbot_id, res.data[0].get("user_id"))
            return res.data[0]
        logger.info("get_session_by_userbot_id kaedah 1 — tiada result untuk ub_id=%s", userbot_id)
    except Exception as e:
        logger.warning("get_session_by_userbot_id kaedah 1 gagal (column mungkin belum wujud): %s", e)

    # ── Kaedah 2: userbots registry → sessions ──
    try:
        ub_res = await client.table("userbots").select("owner_id").eq("userbot_id", userbot_id).execute()
        if ub_res.data:
            owner_id = ub_res.data[0]["owner_id"]
            logger.info("get_session_by_userbot_id kaedah 2 — userbots registry: ub_id=%s → uid=%s",
                        userbot_id, owner_id)
            session = await get_session(owner_id)
            if session:
                # Patch userbot_id ke dalam dict jika column sessions tidak simpan ia
                if not session.get("userbot_id"):
                    session["userbot_id"] = userbot_id
                    logger.info("get_session_by_userbot_id PATCH userbot_id ke session uid=%s", owner_id)
                return session
            logger.warning("get_session_by_userbot_id kaedah 2 — userbots ada tapi session tiada uid=%s", owner_id)
        else:
            logger.warning("get_session_by_userbot_id kaedah 2 — userbots tiada ub_id=%s", userbot_id)
    except Exception as e:
        logger.warning("get_session_by_userbot_id kaedah 2 gagal: %s", e)

    logger.error("get_session_by_userbot_id TIDAK DIJUMPAI: ub_id=%s — semua kaedah gagal", userbot_id)
    return None


async def transfer_userbot_session(from_user_id: int, to_user_id: int):
    """Pindah session (termasuk userbot_id) dari satu user ke user lain."""
    client = await get_client()
    session = await get_session(from_user_id)
    if not session:
        return
    new_session_payload = {
        "user_id": to_user_id,
        "phone_number": session.get("phone_number", ""),
        "session_string": session.get("session_string", ""),
        "tg_username": session.get("tg_username", ""),
        "userbot_id": session.get("userbot_id", ""),
        "connected_at": session.get("connected_at"),
    }
    try:
        await client.table("sessions").upsert(new_session_payload, on_conflict="user_id").execute()
        logger.info("transfer_userbot_session: upsert baru OK from=%s to=%s", from_user_id, to_user_id)
    except Exception as e:
        logger.error("transfer_userbot_session: upsert gagal — session TIDAK dipindah! from=%s to=%s: %s",
                     from_user_id, to_user_id, e)
        raise
    await delete_session(from_user_id)
    logger.info("transfer_userbot_session: session lama dipadam from=%s", from_user_id)
    # Kemaskini userbots.owner_id supaya canonical source konsisten
    try:
        await client.table("userbots").update(
            {"owner_id": to_user_id}
        ).eq("owner_id", from_user_id).execute()
        logger.info("transfer_userbot_session: userbots.owner_id %s → %s", from_user_id, to_user_id)
    except Exception as e:
        logger.warning("transfer_userbot_session: userbots update gagal: %s", e)


# ─────────────────────────────────────────────
# SELECTED GROUPS
# ─────────────────────────────────────────────

async def get_selected_groups(user_id: int):
    client = await get_client()
    res = await client.table("selected_groups").select("*").eq("user_id", user_id).execute()
    return res.data or []


async def save_selected_groups(user_id: int, groups: list):
    client = await get_client()
    backup = await get_selected_groups(user_id)
    await client.table("selected_groups").delete().eq("user_id", user_id).execute()
    if groups:
        rows = [
            {
                "user_id": user_id,
                "group_id": str(g["id"]),
                "group_name": g.get("title") or g.get("group_name") or "",
                "group_username": g.get("username") or "",
                "target_type": g.get("target_type", "group"),
                "access_hash": str(g["access_hash"]) if g.get("access_hash") else None,
            }
            for g in groups
        ]
        try:
            await client.table("selected_groups").insert(rows).execute()
            logger.info("save_selected_groups OK uid=%s count=%d", user_id, len(rows))
        except Exception as e:
            # Column target_type/access_hash mungkin belum wujud — cuba tanpa column baru
            logger.warning(
                "save_selected_groups penuh gagal uid=%s: %s — cuba tanpa target_type/access_hash",
                user_id, e,
            )
            rows_minimal = [
                {
                    "user_id": user_id,
                    "group_id": str(g["id"]),
                    "group_name": g.get("title") or g.get("group_name") or "",
                    "group_username": g.get("username") or "",
                }
                for g in groups
            ]
            try:
                await client.table("selected_groups").insert(rows_minimal).execute()
                logger.info("save_selected_groups minimal OK uid=%s count=%d", user_id, len(rows_minimal))
            except Exception as e2:
                # Cuba lagi tanpa group_username
                logger.warning("save_selected_groups minimal gagal uid=%s: %s — cuba bare minimum", user_id, e2)
                rows_bare = [
                    {
                        "user_id": user_id,
                        "group_id": str(g["id"]),
                        "group_name": g.get("title") or g.get("group_name") or "",
                    }
                    for g in groups
                ]
                try:
                    await client.table("selected_groups").insert(rows_bare).execute()
                except Exception as e3:
                    logger.error("save_selected_groups INSERT gagal uid=%s — pulihkan backup: %s", user_id, e3)
                    if backup:
                        restore_rows = [
                            {
                                "user_id": user_id,
                                "group_id": b["group_id"],
                                "group_name": b.get("group_name") or "",
                            }
                            for b in backup
                        ]
                        try:
                            await client.table("selected_groups").insert(restore_rows).execute()
                            logger.info("save_selected_groups: backup dipulihkan uid=%s", user_id)
                        except Exception as e4:
                            logger.error("save_selected_groups: pulih backup gagal uid=%s: %s", user_id, e4)
                    raise


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
        {"user_id": user_id, "message": message_text},
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
        .select("user_id, phone_number, connected_at")
        .order("connected_at", desc=True)
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
    order_id: str = None,
) -> str:
    """Simpan topup_request baru dengan status pending. Pulangkan order_id.
    
    BUG 3 FIX: Terima order_id dari luar supaya handler boleh jana
    order_id DULU sebelum DB call — DB error tidak akan block user.
    """
    client = await get_client()
    if not order_id:
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


# ─────────────────────────────────────────────
# GROUPS — operasi tambahan
# ─────────────────────────────────────────────

async def remove_single_group(user_id: int, group_id: str) -> bool:
    try:
        client = await get_client()
        await client.table("selected_groups").delete().eq("user_id", user_id).eq("group_id", group_id).execute()
        return True
    except Exception as e:
        logger.warning("remove_single_group error uid=%s gid=%s: %s", user_id, group_id, e)
        return False


async def clear_all_groups(user_id: int) -> int:
    try:
        client = await get_client()
        existing = await client.table("selected_groups").select("id").eq("user_id", user_id).execute()
        count = len(existing.data or [])
        await client.table("selected_groups").delete().eq("user_id", user_id).execute()
        return count
    except Exception as e:
        logger.warning("clear_all_groups error uid=%s: %s", user_id, e)
        return 0


async def add_single_group(
    user_id: int,
    group_id: str,
    group_title: str,
    group_username: str = None,
    target_type: str = "group",
    access_hash: str = None,
) -> bool:
    try:
        client = await get_client()
        existing = await client.table("selected_groups").select("group_id").eq("user_id", user_id).eq("group_id", group_id).execute()
        if existing.data:
            return False
        # Cuba insert penuh dengan semua field
        full_row = {
            "user_id": user_id,
            "group_id": group_id,
            "group_name": group_title or "",
            "group_username": group_username or "",
            "target_type": target_type,
            "access_hash": str(access_hash) if access_hash else None,
        }
        try:
            await client.table("selected_groups").insert(full_row).execute()
            logger.info("add_single_group OK uid=%s gid=%s type=%s", user_id, group_id, target_type)
            return True
        except Exception as e:
            # Column baru mungkin belum wujud — fallback
            logger.warning("add_single_group full gagal uid=%s: %s — cuba minimal", user_id, e)
            await client.table("selected_groups").insert({
                "user_id": user_id,
                "group_id": group_id,
                "group_name": group_title or "",
            }).execute()
            logger.info("add_single_group minimal OK uid=%s gid=%s", user_id, group_id)
            return True
    except Exception as e:
        logger.warning("add_single_group error uid=%s gid=%s: %s", user_id, group_id, e)
        return False


# ─────────────────────────────────────────────
# BROADCAST MESSAGES (senarai mesej berbilang)
# ─────────────────────────────────────────────

async def get_broadcast_messages(userbot_id: str) -> list:
    try:
        client = await get_client()
        res = (
            await client.table("broadcast_messages")
            .select("*")
            .eq("userbot_id", userbot_id)
            .order("urutan", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.warning("get_broadcast_messages error ub=%s: %s", userbot_id, e)
        return []


async def count_broadcast_messages(userbot_id: str) -> int:
    try:
        client = await get_client()
        res = await client.table("broadcast_messages").select("id", count="exact").eq("userbot_id", userbot_id).execute()
        return res.count or 0
    except Exception as e:
        logger.warning("count_broadcast_messages error: %s", e)
        return 0


async def add_broadcast_message(
    userbot_id: str, user_id: int,
    content_type: str, text_content: str = None, file_id: str = None
) -> bool:
    try:
        client = await get_client()
        count = await count_broadcast_messages(userbot_id)
        if count >= 10:
            return False
        await client.table("broadcast_messages").insert({
            "userbot_id": userbot_id,
            "user_id": user_id,
            "content_type": content_type,
            "text_content": text_content,
            "file_id": file_id,
            "urutan": count,
        }).execute()
        return True
    except Exception as e:
        logger.warning("add_broadcast_message error ub=%s: %s", userbot_id, e)
        return False


async def delete_broadcast_message(msg_id: str) -> bool:
    try:
        client = await get_client()
        await client.table("broadcast_messages").delete().eq("id", msg_id).execute()
        return True
    except Exception as e:
        logger.warning("delete_broadcast_message error id=%s: %s", msg_id, e)
        return False


async def clear_broadcast_messages(userbot_id: str) -> int:
    try:
        client = await get_client()
        existing = await client.table("broadcast_messages").select("id").eq("userbot_id", userbot_id).execute()
        count = len(existing.data or [])
        await client.table("broadcast_messages").delete().eq("userbot_id", userbot_id).execute()
        return count
    except Exception as e:
        logger.warning("clear_broadcast_messages error ub=%s: %s", userbot_id, e)
        return 0


# ─────────────────────────────────────────────
# AUTOREPLY CHANNELS
# ─────────────────────────────────────────────

async def get_autoreply_channels(userbot_id: str) -> list:
    try:
        client = await get_client()
        res = await client.table("autoreply_channels").select("*").eq("userbot_id", userbot_id).execute()
        return res.data or []
    except Exception as e:
        logger.warning("get_autoreply_channels error: %s", e)
        return []


async def add_autoreply_channel(userbot_id: str, user_id: int, channel_id: str, channel_name: str = "") -> bool:
    try:
        client = await get_client()
        existing = await client.table("autoreply_channels").select("id").eq("userbot_id", userbot_id).eq("channel_id", channel_id).execute()
        if existing.data:
            return False
        await client.table("autoreply_channels").insert({
            "userbot_id": userbot_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "channel_name": channel_name,
        }).execute()
        return True
    except Exception as e:
        logger.warning("add_autoreply_channel error: %s", e)
        return False


async def delete_autoreply_channel(channel_uuid: str) -> bool:
    try:
        client = await get_client()
        await client.table("autoreply_channels").delete().eq("id", channel_uuid).execute()
        return True
    except Exception as e:
        logger.warning("delete_autoreply_channel error: %s", e)
        return False


async def clear_autoreply_channels(userbot_id: str) -> int:
    try:
        client = await get_client()
        existing = await client.table("autoreply_channels").select("id").eq("userbot_id", userbot_id).execute()
        count = len(existing.data or [])
        await client.table("autoreply_channels").delete().eq("userbot_id", userbot_id).execute()
        return count
    except Exception as e:
        logger.warning("clear_autoreply_channels error: %s", e)
        return 0


# ─────────────────────────────────────────────
# AUTOREPLY TEXTS
# ─────────────────────────────────────────────

async def get_autoreply_texts(userbot_id: str) -> list:
    try:
        client = await get_client()
        res = await client.table("autoreply_texts").select("*").eq("userbot_id", userbot_id).execute()
        return res.data or []
    except Exception as e:
        logger.warning("get_autoreply_texts error: %s", e)
        return []


async def add_autoreply_text(userbot_id: str, user_id: int, teks: str) -> bool:
    try:
        client = await get_client()
        await client.table("autoreply_texts").insert({
            "userbot_id": userbot_id,
            "user_id": user_id,
            "teks": teks,
        }).execute()
        return True
    except Exception as e:
        logger.warning("add_autoreply_text error: %s", e)
        return False


async def delete_autoreply_text(text_uuid: str) -> bool:
    try:
        client = await get_client()
        await client.table("autoreply_texts").delete().eq("id", text_uuid).execute()
        return True
    except Exception as e:
        logger.warning("delete_autoreply_text error: %s", e)
        return False


async def clear_autoreply_texts(userbot_id: str) -> int:
    try:
        client = await get_client()
        existing = await client.table("autoreply_texts").select("id").eq("userbot_id", userbot_id).execute()
        count = len(existing.data or [])
        await client.table("autoreply_texts").delete().eq("userbot_id", userbot_id).execute()
        return count
    except Exception as e:
        logger.warning("clear_autoreply_texts error: %s", e)
        return 0


# ─────────────────────────────────────────────
# SCHEDULES (jadual aktif)
# ─────────────────────────────────────────────

async def get_schedule(userbot_id: str):
    try:
        client = await get_client()
        res = await client.table("schedules").select("*").eq("userbot_id", userbot_id).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.warning("get_schedule error: %s", e)
        return None


async def set_schedule(userbot_id: str, user_id: int, waktu_mula: str, waktu_tamat: str) -> bool:
    try:
        client = await get_client()
        await client.table("schedules").upsert({
            "userbot_id": userbot_id,
            "user_id": user_id,
            "waktu_mula": waktu_mula,
            "waktu_tamat": waktu_tamat,
            "aktif": True,
        }, on_conflict="userbot_id").execute()
        return True
    except Exception as e:
        logger.warning("set_schedule error: %s", e)
        return False


async def toggle_schedule(userbot_id: str, aktif: bool) -> bool:
    try:
        client = await get_client()
        await client.table("schedules").update({"aktif": aktif}).eq("userbot_id", userbot_id).execute()
        return True
    except Exception as e:
        logger.warning("toggle_schedule error: %s", e)
        return False


async def delete_schedule(userbot_id: str) -> bool:
    try:
        client = await get_client()
        await client.table("schedules").delete().eq("userbot_id", userbot_id).execute()
        return True
    except Exception as e:
        logger.warning("delete_schedule error: %s", e)
        return False


# ─────────────────────────────────────────────
# NOTIFICATIONS (pemberitahuan)
# ─────────────────────────────────────────────

async def get_notif_status(user_id: int) -> bool:
    try:
        client = await get_client()
        res = await client.table("promo_settings").select("notif_aktif").eq("user_id", user_id).execute()
        if not res.data:
            return True
        val = res.data[0].get("notif_aktif")
        return val if val is not None else True
    except Exception as e:
        logger.warning("get_notif_status error uid=%s: %s", user_id, e)
        return True


async def set_notif_status(user_id: int, aktif: bool) -> bool:
    try:
        client = await get_client()
        await client.table("promo_settings").upsert(
            {"user_id": user_id, "notif_aktif": aktif},
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as e:
        logger.warning("set_notif_status error uid=%s: %s", user_id, e)
        return False


# ─────────────────────────────────────────────
# EMAIL SANDARAN
# ─────────────────────────────────────────────

async def get_backup_email(user_id: int):
    try:
        client = await get_client()
        res = await client.table("sessions").select("backup_email").eq("user_id", user_id).execute()
        if not res.data:
            return None
        return res.data[0].get("backup_email")
    except Exception as e:
        logger.warning("get_backup_email error uid=%s: %s", user_id, e)
        return None


async def set_backup_email(user_id: int, email: str) -> bool:
    try:
        client = await get_client()
        await client.table("sessions").update({"backup_email": email}).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        logger.warning("set_backup_email error uid=%s: %s", user_id, e)
        return False


# ─────────────────────────────────────────────
# REFERRALS
# ─────────────────────────────────────────────

def _make_ref_code(user_id: int) -> str:
    return f"REF-{user_id}"


async def get_referral_code(user_id: int) -> str:
    return _make_ref_code(user_id)


async def has_been_referred(referred_id: int) -> bool:
    try:
        client = await get_client()
        res = await client.table("referrals").select("id").eq("referred_id", referred_id).execute()
        return bool(res.data)
    except Exception as e:
        logger.warning("has_been_referred error: %s", e)
        return False


async def create_referral(referrer_id: int, referred_id: int, ref_code: str) -> bool:
    try:
        client = await get_client()
        already = await has_been_referred(referred_id)
        if already:
            return False
        await client.table("referrals").insert({
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "ref_code": ref_code,
            "coins_given": 0,
        }).execute()
        return True
    except Exception as e:
        logger.warning("create_referral error: %s", e)
        return False


async def get_referral_stats(user_id: int) -> dict:
    try:
        client = await get_client()
        res = await client.table("referrals").select("*").eq("referrer_id", user_id).execute()
        rows = res.data or []
        total_coins = sum(r.get("coins_given", 0) for r in rows)
        return {"count": len(rows), "total_coins": total_coins}
    except Exception as e:
        logger.warning("get_referral_stats error: %s", e)
        return {"count": 0, "total_coins": 0}


async def finalize_referral_coins(referrer_id: int, referred_id: int) -> bool:
    """Kredit syiling kepada kedua-dua pihak. Dipanggil selepas user baru /start."""
    try:
        client = await get_client()
        REFERRER_COINS = 100
        REFERRED_COINS = 50
        await add_coins(referrer_id, REFERRER_COINS, f"Bonus rujukan — user baru {referred_id}")
        await add_coins(referred_id, REFERRED_COINS, "Bonus selamat datang — kod rujukan")
        await client.table("referrals").update(
            {"coins_given": REFERRER_COINS + REFERRED_COINS}
        ).eq("referrer_id", referrer_id).eq("referred_id", referred_id).execute()
        logger.info("finalize_referral_coins referrer=%s referred=%s OK", referrer_id, referred_id)
        return True
    except Exception as e:
        logger.warning("finalize_referral_coins error: %s", e)
        return False


# ─────────────────────────────────────────────
# EXPERT MODE (mesej khusus per kumpulan)
# ─────────────────────────────────────────────

async def get_expert_mode(user_id: int) -> bool:
    try:
        client = await get_client()
        res = await client.table("promo_settings").select("expert_mode").eq("user_id", user_id).execute()
        if not res.data:
            return False
        val = res.data[0].get("expert_mode")
        return bool(val) if val is not None else False
    except Exception as e:
        logger.warning("get_expert_mode error: %s", e)
        return False


async def set_expert_mode(user_id: int, aktif: bool) -> bool:
    try:
        client = await get_client()
        await client.table("promo_settings").upsert(
            {"user_id": user_id, "expert_mode": aktif},
            on_conflict="user_id",
        ).execute()
        return True
    except Exception as e:
        logger.warning("set_expert_mode error: %s", e)
        return False


async def get_group_message(user_id: int, group_id: str):
    try:
        client = await get_client()
        res = await client.table("group_messages").select("message_text").eq("user_id", user_id).eq("group_id", group_id).execute()
        return res.data[0]["message_text"] if res.data else None
    except Exception as e:
        logger.warning("get_group_message error: %s", e)
        return None


async def set_group_message(user_id: int, group_id: str, message_text: str) -> bool:
    try:
        client = await get_client()
        await client.table("group_messages").upsert({
            "user_id": user_id,
            "group_id": group_id,
            "message_text": message_text,
        }, on_conflict="user_id,group_id").execute()
        return True
    except Exception as e:
        logger.warning("set_group_message error: %s", e)
        return False


async def get_all_group_messages(user_id: int) -> dict:
    try:
        client = await get_client()
        res = await client.table("group_messages").select("group_id, message_text").eq("user_id", user_id).execute()
        return {row["group_id"]: row["message_text"] for row in (res.data or [])}
    except Exception as e:
        logger.warning("get_all_group_messages error: %s", e)
        return {}


async def delete_group_message(user_id: int, group_id: str) -> bool:
    try:
        client = await get_client()
        await client.table("group_messages").delete().eq("user_id", user_id).eq("group_id", group_id).execute()
        return True
    except Exception as e:
        logger.warning("delete_group_message error: %s", e)
        return False
