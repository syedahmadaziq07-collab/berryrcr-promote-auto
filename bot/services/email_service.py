"""
services/email_service.py — SMTP recovery + confirmation email sender.

Env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
Rules:
- Jangan crash bot kalau SMTP gagal.
- Jangan log SMTP_PASS.
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

    loaded = {
        "SMTP_HOST": bool(host),
        "SMTP_PORT": port or "587 (default)",
        "SMTP_USER": bool(user),
        "SMTP_PASS": "SET" if pwd else "NOT SET",
        "SMTP_FROM": frm if frm else "NOT SET",
    }
    logger.info(
        "[EMAIL] smtp_env_loaded | host_set=%s port=%s user_set=%s pass=%s from=%s",
        loaded["SMTP_HOST"], loaded["SMTP_PORT"],
        loaded["SMTP_USER"], loaded["SMTP_PASS"],
        loaded["SMTP_FROM"],
    )

    if not all([host, user, pwd]):
        logger.warning(
            "[EMAIL] smtp_env_incomplete | missing=%s",
            [k for k, v in {"host": host, "user": user, "pass": pwd}.items() if not v],
        )
        return None

    try:
        port_int = int(port)
    except ValueError:
        port_int = 587

    return {"host": host, "port": port_int, "user": user, "password": pwd, "from": frm}


def _is_smtp_configured() -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    pwd  = os.getenv("SMTP_PASS", "").strip()
    return all([host, user, pwd])


def smtp_status() -> str:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    pwd  = os.getenv("SMTP_PASS", "").strip()
    if all([host, user, pwd]):
        port = os.getenv("SMTP_PORT", "587").strip()
        return f"✅ SMTP configured ({host}:{port}, user={user})"
    missing = [k for k, v in {"SMTP_HOST": host, "SMTP_USER": user, "SMTP_PASS": pwd}.items() if not v]
    return f"❌ SMTP not configured — missing: {', '.join(missing)}"


# ─────────────────────────────────────────────
# Low-level SMTP send (blocking — run in executor)
# ─────────────────────────────────────────────

def _send_smtp(cfg: dict, to_email: str, msg: MIMEMultipart):
    """Blocking SMTP send. Never log the password."""
    host = cfg["host"]
    port = cfg["port"]
    logger.info(
        "[EMAIL] smtp_connect_start | host=%s port=%s user=%s to=%s",
        host, port, cfg["user"], to_email,
    )
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                logger.info("[EMAIL] smtp_connect_success | host=%s port=%s mode=SSL", host, port)
                server.sendmail(cfg["from"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                logger.info("[EMAIL] smtp_connect_success | host=%s port=%s mode=STARTTLS", host, port)
                server.sendmail(cfg["from"], [to_email], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        logger.error(
            "[EMAIL] smtp_connect_failed | host=%s port=%s | exception_class=%s | exception_message=%s",
            host, port, type(e).__name__, str(e),
        )
        raise
    except smtplib.SMTPConnectError as e:
        logger.error(
            "[EMAIL] smtp_connect_failed | host=%s port=%s | exception_class=%s | exception_message=%s",
            host, port, type(e).__name__, str(e),
        )
        raise
    except smtplib.SMTPException as e:
        logger.error(
            "[EMAIL] smtp_connect_failed | host=%s port=%s | exception_class=%s | exception_message=%s",
            host, port, type(e).__name__, str(e),
        )
        raise
    except Exception as e:
        logger.error(
            "[EMAIL] smtp_connect_failed | host=%s port=%s | exception_class=%s | exception_message=%s",
            host, port, type(e).__name__, str(e),
        )
        raise


async def _dispatch(cfg: dict, to_email: str, msg: MIMEMultipart, tag: str, user_id: int) -> bool:
    """
    Run blocking SMTP in executor. Return True on success.
    Never raises — bot won't crash.
    """
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp, cfg, to_email, msg)
        logger.info(
            "[EMAIL] confirmation_email_sent | tag=%s | user_id=%s | recipient_email=%s",
            tag, user_id, to_email,
        )
        return True
    except Exception as e:
        logger.error(
            "[EMAIL] confirmation_email_failed | tag=%s | user_id=%s | recipient_email=%s | "
            "exception_class=%s | exception_message=%s",
            tag, user_id, to_email, type(e).__name__, str(e),
        )
        return False


# ─────────────────────────────────────────────
# Email builders
# ─────────────────────────────────────────────

def _build_confirmation_email(
    to_email: str,
    user_id: int,
    userbot_id: str = "",
    username: str = "",
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ Backup Email Successfully Connected"
    msg["From"]    = (_smtp_config() or {}).get("from", os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")))
    msg["To"]      = to_email

    ub_display  = userbot_id if userbot_id else "Not Set"
    tg_display  = f"@{username}" if username else str(user_id)

    text = (
        f"Hi !!!\n\n"
        f"Backup email untuk userbot korang dah berjaya connected ✅\n\n"
        f"🆔 Userbot ID: {ub_display}\n"
        f"📱 Telegram: {tg_display}\n\n"
        f"Email ni akan digunakan untuk:\n"
        f"• Recovery token\n"
        f"• Login backup\n"
        f"• Session restore\n"
        f"• Security alert notification 🛡\n\n"
        f"Kalau account logout / session problem, sistem akan auto hantar recovery info ke email ni 📩\n\n"
        f"🚀 Promote Auto by @berryrcr_bot"
    )

    html = f"""
<html>
<body style="font-family:Arial,sans-serif;color:#222;max-width:520px;margin:auto;padding:24px">
  <h2 style="color:#27ae60">✅ Backup Email Successfully Connected</h2>
  <p>Hi !!!</p>
  <p>Backup email untuk userbot korang dah berjaya connected ✅</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold;width:35%">🆔 Userbot ID</td>
      <td style="padding:8px;background:#f9f9f9;font-family:monospace">{ub_display}</td>
    </tr>
    <tr>
      <td style="padding:8px;background:#f5f5f5;font-weight:bold">📱 Telegram</td>
      <td style="padding:8px;background:#f9f9f9;font-family:monospace">{tg_display}</td>
    </tr>
  </table>
  <p>Email ni akan digunakan untuk:</p>
  <ul>
    <li>Recovery token</li>
    <li>Login backup</li>
    <li>Session restore</li>
    <li>Security alert notification 🛡</li>
  </ul>
  <p>
    Kalau account logout / session problem, sistem akan auto hantar
    recovery info ke email ni 📩
  </p>
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="font-size:13px;color:#555">🚀 Promote Auto by @berryrcr_bot</p>
  <p style="font-size:11px;color:#aaa">Jangan balas email ini.</p>
</body>
</html>"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def _build_recovery_email(to_email: str, userbot_id: str, user_id: int, error_reason: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Promote Auto - Userbot Recovery ⚠️"
    msg["From"]    = (_smtp_config() or {}).get("from", os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")))
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

async def send_confirmation_email(
    to_email: str,
    user_id: int,
    userbot_id: str = "",
    username: str = "",
) -> bool:
    """
    Hantar confirmation email bila user save backup email.
    Return True kalau berjaya, False kalau gagal / SMTP tidak set.
    """
    logger.info(
        "[EMAIL] confirmation_email_send_start | user_id=%s | recipient_email=%s | "
        "userbot_id=%s | username=%s",
        user_id, to_email, userbot_id or "NOT SET", username or "NOT SET",
    )

    if not to_email or not EMAIL_REGEX.match(to_email):
        logger.warning(
            "[EMAIL] confirmation_email_failed | reason=invalid_email | user_id=%s | recipient_email=%s",
            user_id, to_email or "EMPTY",
        )
        return False

    cfg = _smtp_config()
    if not cfg:
        logger.warning(
            "[EMAIL] confirmation_email_failed | reason=smtp_not_configured | user_id=%s | recipient_email=%s",
            user_id, to_email,
        )
        return False

    msg = _build_confirmation_email(to_email, user_id, userbot_id=userbot_id, username=username)
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
    logger.info(
        "[EMAIL] confirmation_email_send_start | tag=recovery | user_id=%s | recipient_email=%s",
        user_id, to_email,
    )

    if not to_email or not EMAIL_REGEX.match(to_email):
        logger.warning(
            "[EMAIL] confirmation_email_failed | tag=recovery | reason=invalid_email | "
            "user_id=%s | recipient_email=%s",
            user_id, to_email or "TIADA",
        )
        return False

    cfg = _smtp_config()
    if not cfg:
        logger.warning(
            "[EMAIL] confirmation_email_failed | tag=recovery | reason=smtp_not_configured | "
            "user_id=%s | recipient_email=%s",
            user_id, to_email,
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
    username: str = "",
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
    return await send_confirmation_email(
        to_email=to_email,
        user_id=user_id,
        userbot_id=userbot_id,
        username=username,
    )


async def notify_session_error(user_id: int, userbot_id: str, error_reason: str):
    """
    Helper: ambil backup_email dari DB dan hantar recovery email.
    Selamat dipanggil dari mana-mana — tak crash kalau email tak set atau SMTP gagal.
    """
    try:
        import database as db
        email = await db.get_backup_email(user_id)
        if not email:
            logger.info(
                "[EMAIL] email_skipped | tag=recovery | reason=no_backup_email | user_id=%s", user_id,
            )
            return
        await send_backup_email(
            to_email=email,
            user_id=user_id,
            tag="recovery",
            userbot_id=userbot_id or "UNKNOWN",
            error_reason=error_reason,
        )
    except Exception as e:
        logger.error(
            "[EMAIL] confirmation_email_failed | tag=recovery | user_id=%s | "
            "exception_class=%s | exception_message=%s",
            user_id, type(e).__name__, str(e),
        )
