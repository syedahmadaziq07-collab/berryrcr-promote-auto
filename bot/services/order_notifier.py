"""
services/order_notifier.py — Admin notification untuk NEW ORDER.

Trigger: apabila QR/payment screen dipaparkan kepada user.
Dedup: satu notification per order_id sahaja (in-memory set).
Fallback: guna bot utama kepada ADMIN_ID jika tiada report bot.
"""

import html
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot

from config import ADMIN_ID

logger = logging.getLogger(__name__)

_MY_TZ = timezone(timedelta(hours=8))

# In-memory dedup — cegah duplicate notification untuk order_id yang sama
_notified_orders: set[str] = set()


def _format_notification(
    full_name: str,
    username: str,
    user_id: int,
    item: str,
    coins: int | None,
    amount_rm: float | None,
    order_id: str,
    status: str = "⏳ Waiting Payment Proof",
) -> str:
    now_my = datetime.now(_MY_TZ).strftime("%d %b %Y, %I:%M %p")
    safe_name = html.escape(full_name) if full_name else "—"
    uname_display = f"@{html.escape(username)}" if username else "—"
    safe_item = html.escape(item)

    lines = [
        "🔔 <b>NEW ORDER CREATED</b>",
        "━━━━━━━━━━━━━━━",
        f"👤 Customer: {safe_name}",
        f"🔗 Username: {uname_display}",
        f"🆔 User ID: <code>{user_id}</code>",
        "",
        f"📦 Item: {safe_item}",
    ]

    if coins is not None:
        lines.append(f"🪙 Syiling: {coins:,}")
    if amount_rm is not None:
        lines.append(f"💰 Amount: RM{amount_rm:.2f}")

    lines += [
        f"🧾 Order ID: <code>{html.escape(order_id)}</code>",
        f"🕒 Time: {now_my} (MY)",
        "",
        f"Status: {html.escape(status)}",
        "━━━━━━━━━━━━━━━",
    ]

    return "\n".join(lines)


async def notify_new_order(
    bot: Bot,
    *,
    order_id: str,
    user_id: int,
    full_name: str,
    username: str,
    item: str,
    coins: int | None = None,
    amount_rm: float | None = None,
    status: str = "⏳ Waiting Payment Proof",
) -> None:
    """
    Hantar notification NEW ORDER kepada admin.

    - Satu notification per order_id sahaja (dedup via in-memory set).
    - Jika ADMIN_ID tidak dikonfigurasi, skip silently.
    - Semua exception ditangkap — tidak sekat payment flow utama.
    """
    if not ADMIN_ID:
        logger.debug("[ORDER_NOTIFY] ADMIN_ID tidak dikonfigurasi — skip")
        return

    # ── Dedup check ──
    if order_id in _notified_orders:
        logger.info(
            "[ORDER_NOTIFY] duplicate_order_notification_blocked | order_id=%s uid=%s",
            order_id, user_id,
        )
        return

    _notified_orders.add(order_id)

    text = _format_notification(
        full_name=full_name,
        username=username,
        user_id=user_id,
        item=item,
        coins=coins,
        amount_rm=amount_rm,
        order_id=order_id,
        status=status,
    )

    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        logger.info(
            "[ORDER_NOTIFY] new_order_notification_sent | order_id=%s uid=%s item=%s",
            order_id, user_id, item,
        )
    except Exception as e:
        # Buang dari dedup set supaya boleh retry pada next trigger
        _notified_orders.discard(order_id)
        logger.warning(
            "[ORDER_NOTIFY] new_order_notification_failed | order_id=%s uid=%s error=%s",
            order_id, user_id, e,
        )
