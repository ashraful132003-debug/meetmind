"""Email delivery.

Two transports, chosen by EMAIL_TRANSPORT in .env:

* `local` (default) — renders the real MIME message and writes it to ./outbox as
  a viewable .eml + .html. The full compose/render/deliver path runs; only the
  final TCP hop is replaced. No credentials needed, nothing leaves the machine.
* `smtp` — genuinely sends over SMTP with STARTTLS.

The point of `local` is that it's honest: the app reports "captured locally", not
"sent", and the UI links to the actual rendered email. Nothing pretends.
"""

from __future__ import annotations

import logging
import re
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from pathlib import Path

from ..config import BASE_DIR, settings

log = logging.getLogger(__name__)

OUTBOX = BASE_DIR / "outbox"


@dataclass
class DeliveryResult:
    status: str          # "sent" | "captured" | "failed"
    detail: str
    preview_path: str | None = None


def _md_to_html(markdown: str) -> str:
    """Small Markdown subset renderer for the summary body.

    Escapes first, then applies formatting — so transcript content can never
    inject HTML into an email we send on the user's behalf.
    """
    html_parts: list[str] = []
    in_list = False

    for raw_line in markdown.split("\n"):
        line = escape(raw_line.rstrip())
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h2 style="{_H2}">{stripped[3:]}</h2>')
        elif stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h1 style="{_H1}">{stripped[2:]}</h1>')
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                html_parts.append(f'<ul style="{_UL}">')
                in_list = True
            html_parts.append(f'<li style="{_LI}">{_inline(stripped[2:])}</li>')
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p style="{_P}">{_inline(stripped)}</p>')

    if in_list:
        html_parts.append("</ul>")
    return "\n".join(html_parts)


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r'<code style="background:#f1f5f9;padding:2px 5px;border-radius:4px;font-size:13px">\1</code>', text)
    return text


_H1 = "margin:0 0 12px;font-size:22px;font-weight:650;color:#0f172a;letter-spacing:-0.02em"
_H2 = "margin:28px 0 10px;font-size:13px;font-weight:650;color:#6366f1;text-transform:uppercase;letter-spacing:0.08em"
_P = "margin:0 0 12px;font-size:15px;line-height:1.65;color:#334155"
_UL = "margin:0 0 16px;padding-left:20px"
_LI = "margin:0 0 8px;font-size:15px;line-height:1.6;color:#334155"


def render_summary_email(
    *,
    meeting_title: str,
    sender_name: str,
    summary_md: str,
    action_items: list[dict],
    speakers: list[dict],
    duration_seconds: float,
    note: str = "",
    transcript: str | None = None,
) -> tuple[str, str]:
    """Return (html, plaintext). Both are built — a text/plain alternative is
    what keeps this out of spam folders and readable in any client."""
    mins = int(duration_seconds // 60)
    secs = int(duration_seconds % 60)
    duration_label = f"{mins}m {secs}s" if mins else f"{secs}s"

    action_rows = ""
    for item in action_items:
        priority_color = {"high": "#dc2626", "medium": "#d97706", "low": "#059669"}.get(
            item.get("priority", "medium"), "#64748b"
        )
        due = escape(str(item["due_text"])) if item.get("due_text") else "—"
        action_rows += f"""
        <tr>
          <td style="padding:12px 14px;border-bottom:1px solid #e2e8f0;font-size:14px;color:#0f172a;line-height:1.5">{escape(item['task'])}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #e2e8f0;font-size:14px;color:#475569;white-space:nowrap">{escape(item['owner_label'])}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;white-space:nowrap">{due}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #e2e8f0;white-space:nowrap">
            <span style="display:inline-block;padding:3px 9px;border-radius:99px;background:{priority_color}14;color:{priority_color};font-size:11px;font-weight:650;text-transform:uppercase;letter-spacing:0.04em">{escape(item.get('priority','medium'))}</span>
          </td>
        </tr>"""

    actions_block = (
        f"""
      <h2 style="{_H2}">Action Items</h2>
      <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:8px">
        <thead>
          <tr style="background:#f8fafc">
            <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:650;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0">Task</th>
            <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:650;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0">Owner</th>
            <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:650;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0">Due</th>
            <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:650;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0">Priority</th>
          </tr>
        </thead>
        <tbody>{action_rows}</tbody>
      </table>"""
        if action_items
        else f'<h2 style="{_H2}">Action Items</h2><p style="{_P}">No action items were identified in this meeting.</p>'
    )

    speaker_chips = "".join(
        f'<span style="display:inline-block;padding:5px 11px;margin:0 6px 6px 0;border-radius:99px;'
        f'background:{escape(s["color"])}12;color:{escape(s["color"])};font-size:12px;font-weight:600;'
        f'border:1px solid {escape(s["color"])}28">{escape(s["display_name"])} · {int(s["talk_seconds"] // 60)}m</span>'
        for s in speakers
    )

    note_block = (
        f'<div style="margin:0 0 24px;padding:14px 16px;background:#f8fafc;border-left:3px solid #6366f1;border-radius:0 8px 8px 0">'
        f'<p style="margin:0;font-size:14px;line-height:1.6;color:#475569;white-space:pre-wrap">{escape(note)}</p></div>'
        if note.strip()
        else ""
    )

    transcript_block = ""
    if transcript:
        transcript_block = f"""
      <h2 style="{_H2}">Full Transcript</h2>
      <div style="padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;max-height:none">
        <pre style="margin:0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;line-height:1.7;color:#334155;white-space:pre-wrap;word-break:break-word">{escape(transcript)}</pre>
      </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,sans-serif">
  <table role="presentation" style="width:100%;border-collapse:collapse;background:#f1f5f9">
    <tr><td align="center" style="padding:32px 16px">
      <table role="presentation" style="width:100%;max-width:640px;border-collapse:collapse;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,0.08)">
        <tr><td style="padding:28px 32px;background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%)">
          <div style="font-size:12px;font-weight:650;color:rgba(255,255,255,0.75);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px">MeetMind · Meeting Summary</div>
          <div style="font-size:24px;font-weight:680;color:#ffffff;letter-spacing:-0.02em;line-height:1.25">{escape(meeting_title)}</div>
          <div style="font-size:13px;color:rgba(255,255,255,0.8);margin-top:8px">{duration_label} · {len(speakers)} speaker{'s' if len(speakers) != 1 else ''} · shared by {escape(sender_name)}</div>
        </td></tr>
        <tr><td style="padding:28px 32px">
          {note_block}
          <div style="margin-bottom:20px">{speaker_chips}</div>
          {_md_to_html(summary_md)}
          {actions_block}
          {transcript_block}
        </td></tr>
        <tr><td style="padding:18px 32px;background:#f8fafc;border-top:1px solid #e2e8f0">
          <p style="margin:0;font-size:12px;color:#94a3b8;line-height:1.6">
            Generated by MeetMind — transcription and analysis run locally on the sender's machine.
            This recording was never uploaded to any third-party service.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""

    text_lines = [
        f"{meeting_title}",
        f"{duration_label} · {len(speakers)} speakers · shared by {sender_name}",
        "",
    ]
    if note.strip():
        text_lines += [note.strip(), ""]
    text_lines += [re.sub(r"[*#`]", "", summary_md), ""]
    if action_items:
        text_lines.append("ACTION ITEMS")
        for item in action_items:
            due = f" (due {item['due_text']})" if item.get("due_text") else ""
            text_lines.append(f"  - [{item['owner_label']}] {item['task']}{due}")
        text_lines.append("")
    if transcript:
        text_lines += ["FULL TRANSCRIPT", transcript, ""]
    text_lines.append("Generated by MeetMind — processed locally, never uploaded.")

    return html, "\n".join(text_lines)


def _build_message(subject: str, recipients: list[str], html: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="meetmind.local")
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send_email(subject: str, recipients: list[str], html: str, text: str) -> DeliveryResult:
    msg = _build_message(subject, recipients, html, text)
    transport = settings.email_transport.lower()

    if transport == "smtp":
        if not settings.smtp_host or not settings.smtp_username:
            return DeliveryResult(
                status="failed",
                detail="EMAIL_TRANSPORT=smtp but SMTP_HOST/SMTP_USERNAME are not configured in .env",
            )
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                if settings.smtp_starttls:
                    server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
            return DeliveryResult(status="sent", detail=f"Delivered to {len(recipients)} recipient(s) via {settings.smtp_host}")
        except smtplib.SMTPAuthenticationError:
            return DeliveryResult(
                status="failed",
                detail="SMTP rejected the credentials. For Gmail you need an App Password, not your normal password.",
            )
        except Exception as e:
            log.exception("SMTP send failed")
            return DeliveryResult(status="failed", detail=f"{type(e).__name__}: {e}"[:300])

    # local transport
    OUTBOX.mkdir(parents=True, exist_ok=True)
    stamp = uuid.uuid4().hex[:10]
    eml_path = OUTBOX / f"{stamp}.eml"
    html_path = OUTBOX / f"{stamp}.html"
    try:
        eml_path.write_bytes(bytes(msg))
        html_path.write_text(html, encoding="utf-8")
    except OSError as e:
        return DeliveryResult(status="failed", detail=f"Could not write to outbox: {e}")

    return DeliveryResult(
        status="captured",
        detail=(
            f"Captured locally for {len(recipients)} recipient(s). The message was fully composed "
            f"but not transmitted, because EMAIL_TRANSPORT=local. Set EMAIL_TRANSPORT=smtp in .env to send for real."
        ),
        preview_path=str(html_path),
    )
