import hashlib
import logging

logger = logging.getLogger(__name__)


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


def format_notice(title: str, url: str, date: str = "") -> str:
    lines = [f"📄 *{title}*"]
    if date:
        lines.append(f"📅 {date}")
    lines.append(f"🔗 [Open Notice]({url})")
    return "\n\n".join(lines)
