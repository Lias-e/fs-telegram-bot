import hashlib
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

MONTH_MAP = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    "decembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "جانفي": 1, "فيفري": 2, "مارس": 3, "أفريل": 4, "ماي": 5,
    "جوان": 6, "جويلية": 7, "أوت": 8, "سبتمبر": 9, "أكتوبر": 10,
    "نوفمبر": 11, "ديسمبر": 12,
    "يناير": 1, "فبراير": 2, "أبريل": 4, "يونيو": 6,
    "يوليو": 7, "أغسطس": 8,
}

DATE_RE = re.compile(
    r"(\d{1,2})\s+(%s)\s+(\d{4})" % "|".join(MONTH_MAP.keys()),
    re.IGNORECASE,
)


def sha256_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def split_text(text: str, max_length: int = 4000):
    if len(text) <= max_length:
        return [text]
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = text.rfind(" ", 0, max_length)
        if split_at == -1:
            split_at = max_length
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    return parts


def extract_date(text: str) -> str:
    match = DATE_RE.search(text)
    if match:
        day, month_str, year = match.group(1), match.group(2), match.group(3)
        month = MONTH_MAP.get(month_str.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return ""


def format_notice(title: str, url: str, date: str = "") -> str:
    lines = [f"📄 *{title}*"]
    if date:
        lines.append(f"📅 {date}")
    lines.append(f"🔗 [Open Notice]({url})")
    return "\n\n".join(lines)


def format_notice_with_seen(title: str, url: str, date: str = "", seen_at: str = "") -> str:
    lines = [f"📄 *{title}*"]
    parts = []
    if date:
        parts.append(f"📅 {date}")
    if seen_at and not date:
        parts.append(f"🕐 Detected: {seen_at}")
    if parts:
        lines.append("\n".join(parts))
    lines.append(f"🔗 [Open Notice]({url})")
    return "\n\n".join(lines)
