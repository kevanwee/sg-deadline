"""Use wheel resources when installed, canonical repository data when editable."""
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_BUNDLED = _PKG / "_resources"
_ROOT = _BUNDLED if _BUNDLED.is_dir() else _PKG.parent.parent
RULES_DIR = _ROOT / "rules"
HOLIDAYS_DIR = _ROOT / "data" / "holidays"
