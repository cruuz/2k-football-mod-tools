"""Import bridge for the existing evidence-backed APF tools.

The research tools intentionally live as runnable modules in ``tools/``.  The
desktop product imports those exact implementations rather than copying their
binary grammars into a second code path.
"""

from __future__ import annotations

from pathlib import Path
import sys


PRODUCT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PRODUCT_ROOT / "tools"


def ensure_tools_importable() -> Path:
    """Put the product's own tools directory on ``sys.path`` exactly once."""

    value = str(TOOLS_ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)
    return TOOLS_ROOT


ensure_tools_importable()

