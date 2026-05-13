"""
services/email_service.py — SMTP recovery email sender.

Hantar email recovery kepada user bila session/userbot ada masalah.
Guna environment variables: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM.

Rules:
- Jangan crash bot kalau SMTP belum set.
- Jangan hantar OTP, session_string, API_HASH, BOT_TOKEN.
- Hantar Userbot ID sahaja untuk recovery reference.
"""

import asyncio
import logging
import os
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _smtp_config() -> dict | None:
    """
    Baca SMTP config dari env.
    Return None kalau mana-mana field kritikal hilang — bot tak crash.
    """
    host  = os.getenv("SMTP_HOST", "").strip()
    port  = os.getenv("SMTP_PORT", "587").strip()
    user  = os.getenv("SMTP_USER", "").strip()
    pwd   = os.getenv("SMTP_PASS", "").strip()
    frm   = os.getenv("SMTP_FROM", "").strip() or user

    if not all([host, user, pwd]):
        return None

    try:
        port_int = int(port)
    except ValueError:
        port_int = 587

    return {"host": host, "port": port_int, "user": user, "password": pwd, "from": frm}


def _is_smtp_configured() -> bool:
    return _smtp_config() is not None


def _build_recovery_email(userbot_id: str, user_id: int, error_reason: str) -> MIMEMultipart:
    """Bina email recovery — selamat, tiada sensitive data."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Promote Auto - Userbot Recovery"
    msg["From"]    = _smtp_config().get("from", "")

    body_text = (
        f"Hi,\n\n"
        f"Userbot korang ada masalah login/session.\n\n"
        f"Userbot ID : {userbot_id}\n"
        f"Telegram ID: {user_id}\n"
        f"Status     : {error_reason}\n\n"
        f"Sila buka @berryrcr_bot dan guna 🔑 Recover Token untuk sambung semula.\n\n"
        f"---\n"
        f"Promote Auto by @berryrcr\n"
        f"Jangan balas email ini."
    )

    body_html = f"""
<html>
<body style="font-family:Arial,sans-serif;color:#222;max-width:520px;margin:auto;padding:24px">
  <h2 style="color:#d9534f">⚠️ Promote Auto — Userbot Recovery</h2>
  <p>Hi,</p>
  <p>Userbot korang ada masalah <strong>login / session</strong>.</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold;width:40%">Userbot ID</td>
      <td style="padding:8px;background:#f9f9f9;font-family:monospace">{userbot_id}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold">Telegram ID</td>
      <td style="padding:8px;background:#f9f9f9;font-family:monospace">{user_id}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold">Status</td>
      <td style="padding:8px;background:#f9f9f9">{error_reason}</td>
    </tr>
  </table>
  <p>
    Sila buka <strong>@berryrcr_bot</strong> dan guna
    <strong>🔑 Recover Token</strong> untuk sambung semula.
  </p>
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="font-size:12px;color:#888">
    Promote Auto by @berryrcr &mdash; Jangan balas email ini.
  </p>
</body>
</html>
"""

    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))
    return msg


async def send_recovery_email(
    to_email: str,
    userbot_id: str,
    user_id: int,
    error_reason: str,
) -> bool:
    """
    Hantar recovery email kepada user.

    Return True kalau berjaya, False kalau gagal / SMTP belum set.
    Tak raise exception — bot mesti terus jalan walaupun email gagal.
    """
    if not to_email or not EMAIL_REGEX.match(to_email):
        logger.warning(
            "[EMAIL] email tidak sah atau kosong — skip | user_id=%s email=%s",
            user_id, to_email or "TIADA",
        )
        return False

    cfg = _smtp_config()
    if not cfg:
        logger.warning(
            "[EMAIL] SMTP belum diset (SMTP_HOST/SMTP_USER/SMTP_PASS kosong) — "
            "skip recovery email | user_id=%s", user_id,
        )
        return False

    try:
        msg     = _build_recovery_email(userbot_id, user_id, error_reason)
        msg["To"] = to_email

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp, cfg, to_email, msg)

        logger.info(
            "[EMAIL] recovery email dihantar | user_id=%s | userbot_id=%s | to=%s | reason=%s",
            user_id, userbot_id, to_email, error_reason,
        )
        return True

    except Exception as e:
        logger.error(
            "[EMAIL] gagal hantar email | user_id=%s | userbot_id=%s | to=%s | error=%s",
            user_id, userbot_id, to_email, e,
        )
        return False


def _send_smtp(cfg: dict, to_email: str, msg: MIMEMultipart):
    """Blocking SMTP send — dijalankan dalam executor supaya tak block event loop."""
    host = cfg["host"]
    port = cfg["port"]

    # Cuba STARTTLS (port 587) dulu, fallback ke SSL (port 465)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], [to_email], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], [to_email], msg.as_string())


async def notify_session_error(user_id: int, userbot_id: str, error_reason: str):
    """
    Helper: ambil backup_email dari DB dan hantar recovery email.
    Selamat dipanggil dari mana-mana — tak crash kalau email tak set.
    """
    try:
        import database as db
        email = await db.get_backup_email(user_id)
        if not email:
            logger.info(
                "[EMAIL] backup_email tiada untuk user_id=%s — skip recovery email", user_id,
            )
            return
        await send_recovery_email(
            to_email=email,
            userbot_id=userbot_id or "UNKNOWN",
            user_id=user_id,
            error_reason=error_reason,
        )
    except Exception as e:
        logger.error("[EMAIL] notify_session_error exception uid=%s: %s", user_id, e)


def smtp_status() -> str:
    """Return status string — untuk admin info."""
    if _is_smtp_configured():
        cfg = _smtp_config()
        return f"✅ SMTP configured ({cfg['host']}:{cfg['port']}, user={cfg['user']})"
    return "❌ SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASS not set)"
