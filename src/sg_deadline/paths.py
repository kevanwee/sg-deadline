"""Locate bundled data (rules, holidays) relative to the package.

Kept in one place so a packaging change (e.g. moving data into the wheel) touches one file.
"""

from __future__ import annotations

from pathlib import Path

_PKG = Path(__file__).resolve().parent
# Repo layout: src/sg_deadline/paths.py -> repo root is three levels up.
_ROOT = _PKG.parent.parent

RULES_DIR = _ROOT / "rules"
HOLIDAYS_DIR = _ROOT / "data" / "holidays"
