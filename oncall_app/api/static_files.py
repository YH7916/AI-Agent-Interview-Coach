"""Static frontend loading."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def read_frontend_shell() -> str:
    """Read the static frontend HTML shell."""
    return (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
