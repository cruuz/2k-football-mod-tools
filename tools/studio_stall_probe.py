#!/usr/bin/env python3
"""Read-only retail-cache replay of Open Disc -> first Uniforms -> two idle minutes.

No disc/cache payloads are copied. Existing authenticated cache packs and inventory
are read in place; new session, derived metadata and previews live in a temporary
directory. Requires a previously indexed retail disc, otherwise exits precisely.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MOD_STUDIO_NO_UPDATE_CHECK"] = "1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(
        "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/2k5-mod-studio")
    parser.add_argument("--seconds", type=float, default=120, help="Idle duration after startup workers settle")
    parser.add_argument("--max-ui-gap", type=float, default=.25)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pending-wiring", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file():
        print(f"SKIP: retail disc is absent: {args.source}")
        return 77
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QEvent
    from mod_editor.gui.stall_watchdog import StallWatchdog
    from mod_editor.gui.studio_qt import StudioMainWindow
    if args.pending_wiring:
        from mod_editor.gui import studio_qt as shell
        sys.path.insert(0, str(ROOT / "tests/mod_editor"))
        from b661_wiring import install
        install(shell)
    from mod_editor.studio.facade import Nfl2k5StudioFacade
    from mod_editor.studio.session import StudioSession
    from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache
    from mod_editor.core.model import GameId

    errors = []
    sys.excepthook = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
    with tempfile.TemporaryDirectory(prefix="studio-stall-probe-") as folder:
        scratch = Path(folder)
        os.environ["XDG_CACHE_HOME"] = str(scratch / "metadata")
        os.environ["XDG_STATE_HOME"] = str(scratch / "logs")

        class ReadOnlyCache(Nfl2k5SourceCache):
            def index(self, source_xiso, progress):
                source = self.inspector.inspect(source_xiso, GameId.NFL2K5,
                    lambda done, total: progress("Authenticating retail source", done, total))
                existing = self.cache_root / source.sha256
                if not (existing / "originals").is_dir():
                    raise RuntimeError("SKIP: retail source needs an existing indexed cache with originals/")
                cache = self._load_existing(existing, source)
                if cache is None:
                    raise RuntimeError("SKIP: existing retail cache is missing or incompatible")
                self._verify_cached_source(source_xiso, cache, progress)
                private = scratch / "cache"
                private.mkdir()
                for name in ("extracted", "indexes"):
                    (private / name).symlink_to(existing / name, target_is_directory=True)
                originals = private / "originals"
                originals.mkdir()
                return replace(cache, root=private, originals=originals)

        app = QApplication.instance() or QApplication([])
        facade = Nfl2k5StudioFacade(source_cache=ReadOnlyCache(args.cache), xemu_command=(),
            # The relocated scratch root intentionally cannot own the old
            # stadium cache. Stadium preparation is outside this first-page replay.
            stadium_cache_coordinator=SimpleNamespace(load_existing=lambda cache: None),
            session_factory=lambda cache, catalog: StudioSession(cache, catalog, root=scratch / "sessions"))
        window = StudioMainWindow(facade=facade, offer_recovery=False)
        window._show_error = errors.append
        window.show()
        app.processEvents()
        log = args.output.with_suffix(".jsonl")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        log.unlink(missing_ok=True)
        watch = StallWatchdog(window, path=log)
        watch.inventory(window)
        start = time.monotonic()
        window._load_source_path(args.source)
        deadline = start + 240
        while window._blocking and time.monotonic() < deadline and not errors:
            app.processEvents()
            time.sleep(.005)
        opened = time.monotonic()
        row = next(i for i in range(window.navigation.count())
                   if window._navigation_key(i) == "uniforms_equipment")
        window.navigation.setCurrentRow(row)
        def preview_arrived():
            return getattr(getattr(window, "preview", None), "_pixmap", None) is not None

        while (row in window._page_factories or not preview_arrived()) \
                and time.monotonic() < deadline and not errors:
            app.processEvents()
            time.sleep(.005)
        ready = time.monotonic()
        app.processEvents()
        watch.beat()
        open_max = watch.max_gap
        while window.thread_pool.activeThreadCount() and time.monotonic() < deadline and not errors:
            app.processEvents()
            time.sleep(.005)
        app.processEvents()
        watch.beat()
        if window._source_state is None and not errors:
            errors.append("Source inspection did not complete: " + window.statusBar().currentMessage())
        if window.thread_pool.activeThreadCount():
            errors.append("Startup workers did not settle within 240 seconds")
        settled = time.monotonic()
        settling_max = watch.max_gap
        watch.record("idle-start", workers=len(window._workers))
        watch.max_gap = 0
        while time.monotonic() - settled < args.seconds and not errors:
            app.processEvents()
            time.sleep(.005)
        watch.inventory(window)
        watch.stop()
        result = dict(source_ready=facade.source_ready, open_seconds=opened-start,
                      content_seconds=ready-opened, content_arrived=row not in window._page_factories,
                      preview_arrived=preview_arrived(),
                      inspection_ready=window._source_state is not None,
                      visible_row=window.pages.currentIndex(), expected_row=row,
                      open_max_gap_seconds=open_max, settling_seconds=settled-ready,
                      settling_max_gap_seconds=settling_max, idle_seconds=time.monotonic()-settled,
                      idle_max_gap_seconds=watch.max_gap, stalls=len(watch.stalls), errors=errors)
        result["within_budget"] = max(settling_max, watch.max_gap) <= args.max_ui_gap
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        # Drain queued deliveries before deleting QObject receivers and scratch
        # paths, including an error run that still has an inspection in flight.
        while window.thread_pool.activeThreadCount():
            app.processEvents()
            time.sleep(.01)
        app.processEvents()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    if any("SKIP:" in message for message in errors):
        return 77
    return 1 if errors or not result["preview_arrived"] or not result["within_budget"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
