#!/usr/bin/env python3
"""Grab PNGs of 2K5 Mod Studio panels without a display (QT_QPA_PLATFORM=offscreen).

usage: studio_screenshots_offscreen.py OUT_DIR [--source DISC_OR_XBE]
Writes studio_home.png (the window as it opens) and one PNG per workspace tab of the reworked
shell: gameplay_throw_tab, gameplay_patches_tab, presentation_scorebug_tab,
presentation_commentary_tab, team_identity_edge_tab, build_tab, share_tab, sounds_tab (each with the source
loaded when --source is given).  Purely local; nothing is written to the source.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QCoreApplication, QEventLoop, Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QStackedWidget, QTabWidget, QWidget  # noqa: E402

from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.gui.studio_qt import StudioMainWindow  # noqa: E402
from mod_editor.gui.throw_tuning_panel_qt import ThrowTuningPanel  # noqa: E402


def reveal(widget: QWidget, window: StudioMainWindow | None = None) -> None:
    """Make every tab/stack ancestor show the page that contains ``widget``.

    The studio's page stack is driven by the sidebar list, so when the stack is the window's
    ``pages`` the sidebar row is selected instead (header title and row highlight follow).
    """

    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QTabWidget):
            # Always go through the QTabWidget (never its internal stack) so the
            # tab bar highlight moves with the page.
            for i in range(parent.count()):
                if parent.widget(i) is widget or parent.widget(i).isAncestorOf(widget):
                    parent.setCurrentIndex(i)
                    break
        elif isinstance(parent, QStackedWidget) and not isinstance(parent.parentWidget(), QTabWidget):
            for i in range(parent.count()):
                if parent.widget(i) is widget or parent.widget(i).isAncestorOf(widget):
                    if window is not None and parent is getattr(window, "pages", None):
                        window.navigation.setCurrentRow(i)
                    else:
                        parent.setCurrentIndex(i)
                    break
        parent = parent.parentWidget()


def spin(ms: int = 300) -> None:
    loop = QEventLoop()
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_dir")
    ap.add_argument("--source")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication([])
    window = StudioMainWindow()
    window.resize(1500, 950)
    window.show()
    spin(500)
    written = []

    def shot(widget: QWidget, name: str) -> None:
        reveal(widget, window)
        spin(300)
        window.grab().save(str(out / f"{name}.png"))
        written.append(out / f"{name}.png")

    window.grab().save(str(out / "studio_home.png"))
    written.append(out / "studio_home.png")
    source = Path(args.source) if args.source else None
    report = tt.read_any(source) if source else None

    panel = window.findChild(ThrowTuningPanel)
    if panel is None:
        print("no ThrowTuningPanel in the window")
        return 1
    if report is not None:
        panel.apply_report(report)
        panel.target_field.setText(str(source.with_name("ESPN NFL 2K5 (modded copy).xiso.iso")))
        panel._refresh_controls()
    shot(panel, "gameplay_throw_tab")
    panel.grab().save(str(out / "throw_panel.png"))

    from mod_editor.core import mod_build
    from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
    state = mod_build.inspect(source) if source else None
    for patches_panel, name in ((window._gameplay_patches_panel, "gameplay_patches_tab"),
                                (window._edge_panel, "team_identity_edge_tab")):
        if not isinstance(patches_panel, GameplayPatchesPanel):
            continue
        if state is not None:
            patches_panel.apply_state(state)
            patches_panel.target_field.setText(str(source.with_name("ESPN NFL 2K5 (patched copy).xiso.iso")))
            patches_panel._refresh()
        shot(patches_panel, name)

    from mod_editor.gui.presentation_panel_qt import PresentationPanel
    pres = window.findChild(PresentationPanel)
    if pres is not None:
        if source is not None:
            import importlib
            tools = ROOT / "tools"
            if str(tools) not in sys.path:
                sys.path.insert(0, str(tools))
            layout = importlib.import_module("nfl2k5_scorebug_layout")
            try:
                pres.apply_state(source, layout.status(source))
                pres.target_field.setText(str(source.with_name("ESPN NFL 2K5 (ESPN scorebug).xiso.iso")))
                pres._refresh()
            except Exception as exc:  # noqa: BLE001 - a bare default.xbe has no scorebug mesh
                print("scorebug state skipped:", exc)
        shot(pres, "presentation_scorebug_tab")

    from mod_editor.gui.commentary_panel_qt import CommentaryPanel
    comm = window.findChild(CommentaryPanel)
    if comm is not None:
        shot(comm, "presentation_commentary_tab")

    from mod_editor.gui.build_panel_qt import BuildPanel
    build = window.findChild(BuildPanel)
    if build is not None:
        if state is not None and hasattr(build, "apply_state"):
            try:
                build.apply_state(state)
            except Exception as exc:  # noqa: BLE001
                print("build state skipped:", exc)
        shot(build, "build_tab")

    from mod_editor.gui.share_panel_qt import SharePanel
    share = window.findChild(SharePanel)
    if share is not None:
        shot(share, "share_tab")

    from mod_editor.gui import sounds_panel_qt
    from mod_editor.gui.sounds_panel_qt import SoundsPanel
    sounds = window.findChild(SoundsPanel)
    if sounds is not None:
        if source is not None:
            try:
                sounds.apply_catalog(source, sounds_panel_qt.read_catalog(source))
                sounds.select_sound("sfx_safe", "whistleshort_01")
                sounds.target_field.setText(str(source.with_name("ESPN NFL 2K5 (sounds).xiso.iso")))
            except Exception as exc:  # noqa: BLE001 - a bare default.xbe has no sound banks
                print("sounds catalog skipped:", exc)
        shot(sounds, "sounds_tab")

    print("wrote", *[str(p) for p in written])
    print("panel visible:", panel.isVisible(), "status:", panel.source_status.text()[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
