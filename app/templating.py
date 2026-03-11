import hashlib
import re
from pathlib import Path

from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _static_url(filename: str) -> str:
    """Return /static/{filename}?v={hash} for cache-busting."""
    filepath = STATIC_DIR / filename
    if filepath.exists():
        digest = hashlib.md5(filepath.read_bytes()).hexdigest()[:8]
        return f"/static/{filename}?v={digest}"
    return f"/static/{filename}"


def _strip_signature(text: str) -> str:
    """Remove email signature block.

    Matches the standard ``-- `` delimiter, common "Kind regards" / "Best"
    style sign-offs, and explicit "Sent from" lines.
    """
    result = re.split(
        r"\n-- ?\n"
        r"|\n(?:Kind regards|Best regards|Best wishes|Regards|Thanks|Cheers|Many thanks|All the best|Best),?\s*\n",
        text, maxsplit=1, flags=re.IGNORECASE,
    )
    return result[0]


_AVATAR_COLORS = [
    "#4f46e5", "#0d9488", "#7c3aed", "#d97706", "#059669",
    "#dc2626", "#2563eb", "#9333ea", "#0891b2", "#c026d3",
]


def _avatar_color(name: str) -> str:
    """Deterministic colour from a name hash."""
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return _AVATAR_COLORS[h % len(_AVATAR_COLORS)]


def _initials(name: str) -> str:
    """First letter of first and last name, uppercased."""
    parts = name.strip().split()
    if not parts:
        return "?"
    first = parts[0][0] if parts[0] else ""
    last = parts[-1][0] if len(parts) > 1 and parts[-1] else ""
    return (first + last).upper()


def _strip_sig(text: str) -> str:
    """Strip email signature for body preview."""
    idx = text.find("\n--\n")
    return text[:idx].strip() if idx > 0 else text.strip()


templates.env.globals["static_url"] = _static_url
templates.env.globals["avatar_color"] = _avatar_color
templates.env.globals["initials"] = _initials
templates.env.globals["strip_sig"] = _strip_sig
templates.env.filters["strip_signature"] = _strip_signature
