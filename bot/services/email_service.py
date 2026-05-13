"""
services/email_service.py — SMTP recovery + confirmation email sender.

Env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
Rules:
- Jangan crash bot kalau SMTP gagal.
- Jangan log password/token.
- Hantar Userbot ID sahaja untuk recovery — tiada session string, API key, dsb.
"""

import asyncio
import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


# ─────────────────────────────────────────────
# Config helper
# ─────────────────────────────────────────────

def _smtp_config() -> dict | None:
    host = os.getenv("SMTP_HOST", "").strip()
    port = os.getenv("SMTP_PORT", "587").strip()
    user = os.getenv("SMTP_USER", "").strip()
    pwd  = os.getenv("SMTP_PASS", "").strip()
    frm  = os.getenv("SMTP_FROM", "").strip() or user

    if not all([host, user, pwd]):
        return None

    try:
        port_int = int(port)
    except ValueError:
        port_int = 587

    return {"host": host, "port": port_int, "user": user, "password": pwd, "from": frm}


def _is_smtp_configured() -> bool:
    return _smtp_config() is not None


def smtp_status() -> str:
    if _is_smtp_configured():
        cfg = _smtp_config()
        return f"✅ SMTP configured ({cfg['host']}:{cfg['port']}, user={cfg['user']})"
    return "❌ SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASS not set)"


# ─────────────────────────────────────────────
# Low-level SMTP send (blocking — run in executor)
# ─────────────────────────────────────────────

def _send_smtp(cfg: dict, to_email: str, msg: MIMEMultipart):
    """Blocking SMTP send. Never log the password."""
    host = cfg["host"]
    port = cfg["port"]
    try:
        logger.info("[EMAIL] smtp_connecting | host=%s port=%s user=%s", host, port, cfg["user"])
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                logger.info("[EMAIL] smtp_connected | host=%s port=%s", host, port)
                server.sendmail(cfg["from"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                logger.info("[EMAIL] smtp_connected | host=%s port=%s", host, port)
                server.sendmail(cfg["from"], [to_email], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        logger.error("[EMAIL] smtp_failed | reason=auth_error | host=%s port=%s | error=%s", host, port, e)
        raise
    except smtplib.SMTPConnectError as e:
        logger.error("[EMAIL] smtp_failed | reason=connect_error | host=%s port=%s | error=%s", host, port, e)
        raise
    except smtplib.SMTPException as e:
        logger.error("[EMAIL] smtp_failed | reason=smtp_error | host=%s port=%s | error=%s", host, port, e)
        raise
    except Exception as e:
        logger.error("[EMAIL] smtp_failed | reason=unexpected | host=%s port=%s | error=%s", host, port, e)
        raise


async def _dispatch(cfg: dict, to_email: str, msg: MIMEMultipart, tag: str, user_id: int) -> bool:
    """
    Run blocking SMTP in executor. Return True on success.
    Never raises — bot won't crash.
    """
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp, cfg, to_email, msg)
        logger.info("[EMAIL] email_sent | tag=%s | user_id=%s | to=%s", tag, user_id, to_email)
        return True
    except Exception as e:
        logger.error("[EMAIL] email_failed | tag=%s | user_id=%s | to=%s | error=%s", tag, user_id, to_email, e)
        return False


# ─────────────────────────────────────────────
# Email builders
# ─────────────────────────────────────────────

def _build_confirmation_email(to_email: str, user_id: int) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Promote Auto - Backup Email Confirmed ✅"
    msg["From"]    = _smtp_config().get("from", "")
    msg["To"]      = to_email

    text = (
        f"Hi!\n\n"
        f"Backup email kau dah berjaya disimpan dalam sistem Promote Auto.\n\n"
        f"Email   : {to_email}\n"
        f"User ID : {user_id}\n\n"
        f"Kalau userbot kau ada masalah session/login, kami akan hantar recovery notice ke email ni automatik.\n\n"
        f"---\n"
        f"Promote Auto by @berryrcr\n"
        f"Jangan balas email ini."
    )

    html = f"""
<html>
<body style="font-family:Arial,sans-serif;color:#222;max-width:520px;margin:auto;padding:24px">
  <h2 style="color:#27ae60">✅ Backup Email Confirmed!</h2>
  <p>Hi!</p>
  <p>Backup email kau dah berjaya disimpan dalam sistem <strong>Promote Auto</strong>.</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold;width:35%">Email</td>
      <td style="padding:8px;background:#f9f9f9;font-family:monospace">{to_email}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold">User ID</td>
      <td style="padding:8px;background:#f9f9f9;font-family:monospace">{user_id}</td>
    </tr>
  </table>
  <p>
    Kalau userbot kau ada masalah <strong>session / login</strong>, kami akan hantar
    recovery notice ke email ni <em>secara automatik</em>.
  </p>
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="font-size:12px;color:#888">Promote Auto by @berryrcr &mdash; Jangan balas email ini.</p>
</body>
</html>"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def _build_recovery_email(to_email: str, userbot_id: str, user_id: int, error_reason: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Promote Auto - Userbot Recovery ⚠️"
    msg["From"]    = _smtp_config().get("from", "")
    msg["To"]      = to_email

    text = (
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

    html = f"""
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
  <p style="font-size:12px;color:#888">Promote Auto by @berryrcr &mdash; Jangan balas email ini.</p>
</body>
</html>"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

async def send_confirmation_email(to_email: str, user_id: int) -> bool:
    """
    Hantar confirmation email bila user save backup email.
    Return True kalau berjaya, False kalau gagal / SMTP tidak set.
    """
    if not to_email or not EMAIL_REGEX.match(to_email):
        logger.warning("[EMAIL] email_failed | tag=confirmation | reason=invalid_email | user_id=%s", user_id)
        return False

    cfg = _smtp_config()
    if not cfg:
        logger.warning("[EMAIL] email_failed | tag=confirmation | reason=smtp_not_configured | user_id=%s", user_id)
        return False

    msg = _build_confirmation_email(to_email, user_id)
    return await _dispatch(cfg, to_email, msg, "confirmation", user_id)


async def send_recovery_email(
    to_email: str,
    userbot_id: str,
    user_id: int,
    error_reason: str,
) -> bool:
    """
    Hantar recovery email bila session/userbot ada masalah.
    Selamat: tiada password/token/session_string dalam email.
    """
    if not to_email or not EMAIL_REGEX.match(to_email):
        logger.warning(
            "[EMAIL] email_failed | tag=recovery | reason=invalid_email | user_id=%s | email=%s",
            user_id, to_email or "TIADA",
        )
        return False

    cfg = _smtp_config()
    if not cfg:
        logger.warning(
            "[EMAIL] email_failed | tag=recovery | reason=smtp_not_configured | user_id=%s", user_id,
        )
        return False

    msg = _build_recovery_email(to_email, userbot_id, user_id, error_reason)
    return await _dispatch(cfg, to_email, msg, "recovery", user_id)


async def send_backup_email(
    to_email: str,
    user_id: int,
    tag: str = "confirmation",
    userbot_id: str = "",
    error_reason: str = "",
) -> bool:
    """
    Unified helper — entry point untuk semua email backup.

    tag="confirmation" → hantar confirmation email bila user save email.
    tag="recovery"     → hantar recovery email bila session ada masalah.

    Selamat: tak crash bot, tak log password/token.
    """
    if tag == "recovery":
        return await send_recovery_email(
            to_email=to_email,
            userbot_id=userbot_id or "UNKNOWN",
            user_id=user_id,
            error_reason=error_reason or "Session / login problem",
        )
    return await send_confirmation_email(to_email=to_email, user_id=user_id)


async def notify_session_error(user_id: int, userbot_id: str, error_reason: str):
    """
    Helper: ambil backup_email dari DB dan hantar recovery email.
    Selamat dipanggil dari mana-mana — tak crash kalau email tak set atau SMTP gagal.
    """
    try:
        import database as db
        email = await db.get_backup_email(user_id)
        if not email:
            logger.info("[EMAIL] email_skipped | tag=recovery | reason=no_backup_email | user_id=%s", user_id)
            return
        await send_backup_email(
            to_email=email,
            user_id=user_id,
            tag="recovery",
            userbot_id=userbot_id or "UNKNOWN",
            error_reason=error_reason,
        )
    except Exception as e:
        logger.error("[EMAIL] email_failed | tag=recovery | user_id=%s | exception=%s", user_id, e)
