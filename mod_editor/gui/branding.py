"""Application icon lookup shared by both editors.

The icons are generated, not drawn by hand: ``tools/make_app_icons.py`` emits
every plate from geometry, so the wordmark in the taskbar is the same object as
the ``2K5``/``2K8`` badge in the sidebar and cannot drift away from it.

Load order matters more than it looks.  The multi-resolution ``.ico`` carries a
separately drawn plate for each of 16, 24, 32, 48, 64, 128 and 256 px, and Qt
picks the one matching the size a window actually asks for; the 16 px plate in
particular is a different composition, not a shrunk copy, because a shrunk
three-glyph wordmark is unreadable at that size.  The SVG behind it is a single
scalable plate -- correct, but rendered by Qt at whatever size is requested, so
it loses that hinting.  Falling back to it is better than no icon; leading with
it would throw away the reason the sizes were drawn separately.
"""

from __future__ import annotations

from pathlib import Path

# Repository root as seen from mod_editor/gui/branding.py.  The staged release
# tree keeps the same shape, so one expression serves both.
_PACKAGING = Path(__file__).resolve().parents[2] / "packaging"


def icon_candidates(slug: str) -> tuple[Path, ...]:
    """Return the icon files for *slug*, best first."""
    return (
        _PACKAGING / "icons" / f"{slug}.ico",
        _PACKAGING / f"{slug}.svg",
        _PACKAGING / "icons" / f"{slug}-256.png",
    )


def app_icon(slug: str):
    """Return a :class:`QIcon` for *slug*, or ``None`` if nothing is readable.

    Never raises.  A missing or unreadable icon is a cosmetic problem, and an
    editor that refuses to open because its taskbar picture is absent would be a
    far worse one.
    """
    from PyQt5.QtGui import QIcon  # deferred: importable from non-GUI callers

    for candidate in icon_candidates(slug):
        try:
            if not candidate.is_file():
                continue
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
        except Exception:
            continue
    return None
