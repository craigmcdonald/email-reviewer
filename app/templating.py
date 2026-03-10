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
    """Remove email signature block starting at a common delimiter line."""
    return re.split(r"\n-- ?\n", text, maxsplit=1)[0]


templates.env.globals["static_url"] = _static_url
templates.env.filters["strip_signature"] = _strip_signature
