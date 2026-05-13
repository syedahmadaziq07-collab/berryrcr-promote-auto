"""
services/subscription_checker.py — Auto-deactivate subscription tamat tempoh.
Dijalankan sebagai asyncio task setiap jam.
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def check_expired_subscriptions() -> None:
    """
    Semak semua subscription yang aktif dan matikan yang sudah tamat tempoh.
    Dijalankan setiap 1 jam secara berterusan.
    """
    from services.supabase_service import get_client

    while True:
        try:
            client = await get_client()
            now_iso = datetime.now(timezone.utc).isoformat()

            expired = (
                await client.table("subscriptions")
                .select("user_id, plan, expires_at")
                .eq("active", True)
                .lt("expires_at", now_iso)
                .execute()
            )

            if expired.data:
                for sub in expired.data:
                    try:
                        await (
                            client.table("subscriptions")
                            .update({"active": False})
                            .eq("user_id", sub["user_id"])
                            .eq("plan", sub["plan"])
                            .eq("active", True)
                            .execute()
                        )
                        logger.info(
                            "subscription_checker: user=%s plan=%s — dinyahaktifkan (tamat %s)",
                            sub["user_id"], sub["plan"], sub.get("expires_at", "?"),
                        )
                    except Exception as e:
                        logger.error(
                            "subscription_checker: gagal nyahaktif user=%s plan=%s: %s",
                            sub["user_id"], sub["plan"], e,
                        )
            else:
                logger.debug("subscription_checker: tiada subscription tamat tempoh")

        except Exception as e:
            logger.error("subscription_checker: ralat semasa semak: %s", e)

        await asyncio.sleep(3600)
