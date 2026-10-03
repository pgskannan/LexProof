"""Email the team when someone requests a trial or demo.

Uses plain SMTP over SSL with the company mailbox. Configured by environment:
  SMTP_HOST (default mailserver.businessidentity.llc), SMTP_PORT (default 465),
  SMTP_USERNAME, SMTP_PASSWORD (secret), TRIAL_NOTIFY_TO (default SMTP_USERNAME).
If SMTP_USERNAME or SMTP_PASSWORD is missing, sending is skipped and logged.
Only the team is emailed; the requester's address goes in Reply-To.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_SMTP_HOST = "mailserver.businessidentity.llc"
DEFAULT_SMTP_PORT = 465
_ROLE_LABELS = {
    "procurement": "Procurement / source-to-pay",
    "legal": "Legal / legal operations",
    "compliance_audit": "Compliance / internal audit",
    "executive": "Executive",
    "it_security": "IT / security",
    "other": "Other",
}


def _one_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def smtp_config() -> dict[str, Any] | None:
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if not username or not password:
        return None
    return {
        "host": os.getenv("SMTP_HOST", DEFAULT_SMTP_HOST).strip() or DEFAULT_SMTP_HOST,
        "port": int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT)) or DEFAULT_SMTP_PORT),
        "username": username,
        "password": password,
        "to": os.getenv("TRIAL_NOTIFY_TO", "").strip() or username,
    }


def build_message(record: dict[str, Any], sender: str, to: str) -> EmailMessage:
    kind = "Demo" if record.get("request_type") == "demo" else "Trial"
    company = _one_line(record.get("company"))
    name = _one_line(record.get("full_name"))
    message = EmailMessage()
    message["Subject"] = f"New {kind.lower()} request: {company} ({name})"[:200]
    message["From"] = formataddr(("LexProof website", sender))
    message["To"] = to
    reply_to = _one_line(record.get("work_email"))
    if reply_to:
        message["Reply-To"] = reply_to
    lines = [
        f"New {kind.lower()} request from the LexProof website.",
        "",
        f"Name:      {name}",
        f"Email:     {reply_to}",
        f"Company:   {company}",
        f"Role:      {_ROLE_LABELS.get(record.get('role', ''), _one_line(record.get('role')))}",
        f"Team size: {_one_line(record.get('team_size')) or '-'}",
        f"Received:  {_one_line(record.get('created_at'))}",
        f"Request:   {_one_line(record.get('id'))}",
        "",
        "Use case:",
        str(record.get("use_case") or "-"),
        "",
        "Reply to this email to answer them directly. All requests are in Firestore > trial_requests.",
    ]
    message.set_content("\n".join(lines))
    return message


def send_request_notification(
    record: dict[str, Any],
    smtp_factory: Callable[..., Any] = smtplib.SMTP_SSL,
) -> bool:
    config = smtp_config()
    if config is None:
        logger.info("trial notification skipped: SMTP_USERNAME/SMTP_PASSWORD not configured")
        return False
    try:
        message = build_message(record, config["username"], config["to"])
        with smtp_factory(config["host"], config["port"], context=ssl.create_default_context(), timeout=20) as smtp:
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)
        logger.info("trial notification sent id=%s", record.get("id"))
        return True
    except Exception as exc:  # never fail the request because email failed
        logger.warning("trial notification failed id=%s: %s", record.get("id"), exc)
        return False
