from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path

from fpdf import FPDF
from jinja2 import Environment, FileSystemLoader, select_autoescape

# fpdf2 logs one warning per glyph a font lacks (emoji, box-drawing, ...); the
# characters are simply dropped, which is fine here.
logging.getLogger("fpdf").setLevel(logging.ERROR)

DATE_FORMAT = "%-m/%d/%Y, %-I:%M %p"    # e.g. 8/10/2026, 12:03 AM
HEADER_GAP = timedelta(minutes=3)       # silence needed before a new name/timestamp row

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

_FONT_DIRS = (
    os.path.expanduser("~/.local/share/fonts/courier-prime"),
    "/usr/share/fonts/truetype/courier-prime",
    "/usr/share/fonts/TTF",
)
PAGE_BACKGROUND = (0xFB, 0xFB, 0xFB)    # #FBFBFB

# --- view-model helpers ------------------------------------------------

def _parse(ts) -> datetime | None:
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def format_dt(ts) -> str:
    """ISO string or ``datetime`` -> the display format (UTC)."""
    dt = _parse(ts)
    if dt is None:
        return ts if isinstance(ts, str) else "—"
    return dt.astimezone(timezone.utc).strftime(DATE_FORMAT)


def build_message_list(messages, guild_names: dict, channel_names: dict) -> list[dict]:
    result: list[dict] = []
    last_shown: datetime | None = None
    last_gid = last_cid = None
    for m in messages:
        gid, cid = m["guild_id"], m["channel_id"]
        show_guild = gid != last_gid
        show_channel = show_guild or cid != last_cid
        if show_channel:
            last_shown = None   # a new channel segment always shows its header row
        last_gid, last_cid = gid, cid

        dt = _parse(m["created_at"])
        show_header = last_shown is None or dt is None or dt - last_shown > HEADER_GAP
        if show_header and dt is not None:
            last_shown = dt

        result.append({
            "timestamp": format_dt(m["created_at"]),
            "author": m.get("author_name") or "",
            "guild": guild_names.get(gid, str(gid)),
            "channel": channel_names.get(cid, str(cid)),
            "show_guild": show_guild,
            "show_channel": show_channel,
            "content": m.get("content") or "",
            "is_reply": bool(m.get("reply_to_message_id")),
            "show_header": show_header,
        })
    return result


def build_profile_context(subject: dict, activity_score, messages, guild_names: dict, generated_at=None) -> dict:
    """Assemble the ``user_profile`` view model from raw-ish inputs.

    ``subject``: ``{name, id, account_created, is_member, joined_at}`` where the
    two date fields may be ``datetime``, ISO string, or ``None``.
    ``messages``: dicts as returned by the bot's ``get_messages`` (only
    ``guild_id`` and ``created_at`` are used here, to total up records and
    first/last-seen timestamps).
    ``guild_names``: ``{id: display name}``.
    ``generated_at``: defaults to now (UTC).
    """
    messages = list(messages)
    times = sorted(m["created_at"] for m in messages)

    counts: dict = {}
    for m in messages:
        counts[m["guild_id"]] = counts.get(m["guild_id"], 0) + 1

    joined = subject.get("joined_at")
    return {
        "subject": {
            "name": subject["name"],
            "id": subject["id"],
            "account_created": format_dt(subject.get("account_created")),
            "is_member": bool(subject.get("is_member")),
            "joined_server": format_dt(joined) if joined else "",
        },
        "generated_at": format_dt(generated_at or datetime.now(timezone.utc)),
        "activity_score": activity_score,
        "total_messages": len(messages),
        "first_logged": format_dt(times[0]) if times else "—",
        "last_logged": format_dt(times[-1]) if times else "—",
        "records": [
            {"guild": guild_names.get(gid, str(gid)), "count": n}
            for gid, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        ],
    }

# --- rendering -------------------------------------------------------

def user_profile(subject: dict, activity_score, messages, guild_names: dict, generated_at=None) -> str:
    context = build_profile_context(subject, activity_score, messages, guild_names, generated_at)
    return _env.get_template("user_profile.html").render(**context)


def message_log(messages, guild_names, channel_names) -> str:
    context = {"messages": build_message_list(messages, guild_names, channel_names)}
    return _env.get_template("message_log.html").render(**context)


def _find_font(name: str) -> str | None:
    for directory in _FONT_DIRS:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


def make_pdf(html: str) -> bytes:
    """Render an HTML string (e.g. concatenated template fragments) to PDF bytes."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_page_background(PAGE_BACKGROUND)   # before add_page(); a str would be read as a path

    regular = _find_font("CourierPrime-Regular.ttf")
    if regular:
        italic = _find_font("CourierPrime-Italic.ttf") or regular
        pdf.add_font("Courier Prime", "", regular)
        pdf.add_font("Courier Prime", "B", regular)   # normal weight everywhere, incl. bold contexts
        pdf.add_font("Courier Prime", "I", italic)
        pdf.add_font("Courier Prime", "BI", italic)
        pdf.set_font("Courier Prime", size=11)
    else:
        pdf.set_font("Courier", size=11)

    pdf.add_page()
    pdf.write_html(html)
    return bytes(pdf.output())
