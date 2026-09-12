# Beta 66.1 H1: protected integration (2026-09-11)

Apply this section before release. The later sections are historical handoffs.
`tests/mod_editor/b661_wiring.py` exercises these exact method replacements in
memory on the real `StudioMainWindow`; it never edits protected source files.
The retail probe uses `--pending-wiring` for the same integration and startup policy.

## Already applied one-line fix

In `mod_editor/gui/studio_qt.py::StudioMainWindow._ensure_workspace`, immediately
after `self.pages.insertWidget(row, self._page_scroll_host(page))`, the sole
hand-edited protected source line is already present:

```python
        self.pages.setCurrentIndex(self.navigation.currentRow())
```

This restores the selected page after QStackedWidget removes its current
placeholder, including the cached/synchronous path (which has no worker callback).

## Startup hook

In `mod_editor/gui/studio_qt.py`, beside the task-delivery import, add:

```python
from mod_editor.gui.workspace_runtime import install as install_workspace_runtime
```

In `StudioMainWindow.__init__`, immediately after `self._build_ui()`, add:

```python
        self._stall_watchdog = install_workspace_runtime(self)
```

This keeps young-cycle GC unchanged and increases the old-generation collection
interval to at least 100. Measured full-heap collections otherwise repeatedly hold
the GIL while scanning long-lived metadata. It does not disable GC or freeze objects.
With `MOD_STUDIO_STALL_LOG=1`, the diagnostic writes `stalls.jsonl` in
`crash_report.log_directory("2K5 Mod Studio")`, beside `errors.log`. With no flag,
there is no watchdog thread, timer, or file. A background sampler writes bounded
rotating logs with Python stacks, worker stacks, GC durations and active timers.
Timer discovery walks at most 64 objects / 5 ms per event; recursive
`findChildren(QTimer)` itself caused a measured 470 ms stall. A heartbeat gap
also retains a clearly labelled recovery stack if a C extension held the GIL
and prevented a sample during the stall.

## Complete replacement methods

Replace these `StudioMainWindow` methods in `mod_editor/gui/studio_qt.py` in full.
The tests apply these blocks in memory, including failure/retry and the page heartbeat.

### `_show_workspace`

```python
    def _show_workspace(self, row, *, select=True):
        if select:
            self.pages.setCurrentIndex(row)
        if row not in self._page_factories or row in self._page_loads:
            return
        key = self._navigation_key(row)
        needs_uniforms = key == "uniforms_equipment" and self._uniform_catalog is None
        needs_visuals = key in {"rosters_players", "field_art_create_team", "scorebug_presentation", "textures"} and self._extended_visual_catalog is None
        needs_build = key in {"sliders_gameplay", "build_share"} and self._available_build_options is None
        if not (needs_uniforms or needs_visuals or needs_build):
            self._ensure_workspace(row)
            return
        self._page_loads.add(row)
        placeholder = self.pages.widget(row)
        loading = placeholder.findChild(QLabel)
        started = time.monotonic()
        heartbeat = QTimer(placeholder)
        heartbeat.setInterval(1000)
        heartbeat.timeout.connect(bound(self, lambda: loading.setText(
            f"Loading workspace… {int(time.monotonic() - started)} s")))
        heartbeat.start()

        def failed(message):
            heartbeat.stop()
            self._page_loads.discard(row)
            self._set_status(f"Could not load workspace: {message}")
            if row not in self._page_factories:
                return
            loading.setText(f"Could not load this workspace: {message}")
            loading.setWordWrap(True)
            retry = QPushButton("Retry loading workspace", placeholder)
            retry.clicked.connect(bound(self, lambda _checked=False: self._show_workspace(row)))
            placeholder.layout().addWidget(retry)

        def prepare(_progress):
            return (load_nfl2k5_uniform_catalog() if needs_uniforms else None,
                    load_nfl2k5_extended_visual_catalog() if needs_visuals else None,
                    mod_build.availability() if needs_build else None)
        def ready(values):
            uniform, visual, available = values
            if uniform is not None:
                self._uniform_catalog = uniform
            if visual is not None:
                self._extended_visual_catalog = visual
            if available is not None:
                self._available_build_options = available
            heartbeat.stop()
            try:
                self._ensure_workspace(row)
            except Exception as exc:
                failed(str(exc))
                return
            if self.navigation.currentRow() == row:
                self.pages.setCurrentIndex(row)
                self._refresh_entered_page(row)
            elif key == "build_share" and self._navigation_key(self.navigation.currentRow()) == "rosters":
                self._prefill_roster_if_pending()
        worker = _BackgroundTask(prepare)
        self._workers.add(worker)
        worker.signals.result.connect(bound(self, ready))
        worker.signals.error.connect(bound(self, failed))
        worker.signals.finished.connect(bound(self, lambda: (self._workers.discard(worker), self._page_loads.discard(row))))
        self.thread_pool.start(worker)
```

### `_prefill_panels_from_source`

```python
    def _prefill_panels_from_source(self, source: Path | None) -> None:
        """Feed the disc that was just opened to every page that has its own source field.

        The header said "Disc: …" while eleven pages still said "choose a disc".  Each page
        is filled through its own existing load / inspect path, off the UI thread where the
        page already works that way; nothing here writes a file, opens a chooser, or resets a
        roster somebody has edited.  A later open supersedes an earlier one (generation).
        """

        self._animations_panel.image_field.setText(str(source or ""))
        self._my_career_panel.set_source(source)
        if self._senior_bowl_panel is not None:
            self._senior_bowl_panel.set_players((), source="")
        self._source_state = None
        if source is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        source = Path(source)
        self._source_generation += 1
        generation = self._source_generation
        self._last_prefilled_source = source
        self._refresh_welcome_state()
        # 1. one inspection for Build, Game Fixes and Position names
        self._source_inspect_pending = True
        for panel in (self._build_panel, self._gameplay_patches_panel, self._edge_panel):
            if panel is not None and hasattr(panel, "begin_reading"):
                panel.begin_reading(source)

        def inspected(state: object) -> None:
            if generation != self._source_generation:
                return
            self._source_inspect_pending = False
            if not isinstance(state, dict):
                return
            self._source_state = state
            self._restoring_music_playlist = True
            try:
                for panel in (self._build_panel, self._gameplay_patches_panel, self._edge_panel):
                    if panel is not None:
                        panel.apply_state(state)
            finally:
                self._restoring_music_playlist = False
            self._sync_uniform_helmet_finish()
            self._music_playlist_catalog = state.get("music_playlist_catalog")
            self._restore_music_build_settings(keep_current_when_empty=True)
            if state.get("music_playlist_catalog_error"):
                self.statusBar().showMessage(f"Playlist library unavailable: {state['music_playlist_catalog_error']}", 8000)
            self._describe_source_pill(state)
            self._sync_mycareer_position_scheme()
            self._refresh_welcome_state()

        def inspect_failed(message: str) -> None:
            if generation != self._source_generation:
                return
            self._source_inspect_pending = False
            self._set_status(f"Could not read build options: {message}")
            for panel in (self._build_panel, self._gameplay_patches_panel, self._edge_panel):
                if panel is not None and hasattr(panel, "reading_failed"):
                    panel.reading_failed(message)

        def inspect_source(progress):
            from mod_editor.core.studio_inspection import inspect_source
            state = inspect_source(source)
            if state.get("container") == "xiso" and state.get("music_library") == "available":
                from mod_editor.core import nfl2k5_music_banks
                try:
                    state["music_playlist_catalog"] = nfl2k5_music_banks.read_playlist_catalog(source)
                except (OSError, ValueError) as exc:
                    state["music_playlist_catalog_error"] = str(exc)
            return state

        worker = _BackgroundTask(inspect_source)
        self._workers.add(worker)
        worker.signals.result.connect(bound(self, inspected))
        worker.signals.error.connect(bound(self, inspect_failed))
        worker.signals.finished.connect(bound(self, lambda: self._workers.discard(worker)))
        self.thread_pool.start(worker)
        # 2. pages with their own background readers
        if self._throw_tuning_panel is not None:
            self._throw_tuning_panel.load_source(source, quiet=True)
        if self._presentation_panel is not None:
            self._presentation_panel.load_source(source)
        if self._commentary_panel is not None:
            self._commentary_panel.load_source(source)
        if self._sounds_panel is not None:
            self._sounds_panel.load_source(source)
        if self._bump_panel is not None:
            self._bump_panel.load_source(source)
        if self._models_panel is not None and self._navigation_key(self.navigation.currentRow()) == "models":
            self._models_panel.reload()
        paths = getattr(self.facade, "models_source_paths", None)
        if paths:
            self._animations_panel.set_source_paths(*paths)
            if self._navigation_key(self.navigation.currentRow()) == "animations":
                self._animations_panel.reload()
        # 3. Share: the export "Starting disc" only while no build owns the pair; the
        #    install "Your disc" whenever it is empty or still following the last disc
        if self._share_panel is not None:
            self._share_panel.follow_source(source)
        # 4. ★ Rosters: only an empty or auto-filled, unedited session follows the disc,
        #    and only when the page is entered (an edited roster is never reset)
        self._roster_prefill_pending = True
        if self._navigation_key(self.navigation.currentRow()) == "rosters":
            self._prefill_roster_if_pending()
        self._refresh_player_assets_hint()
```

### `_refresh_entered_page`

```python
    def _refresh_entered_page(
        self, row: int, *, refresh_embedded: bool = True
    ) -> None:
        if self._navigation_key(row) == "rosters":
            if self._build_panel is None:
                self._show_workspace(self.navigation.count() - 1, select=False)
                if self._build_panel is None:
                    return
            self._prefill_roster_if_pending()
            return
        if self._navigation_key(row) == "models":
            if bool(getattr(self.facade, "source_ready", False)):
                self._models_panel.reload()
            return
        if self._navigation_key(row) == "animations":
            if getattr(self.facade, "models_source_paths", None):
                self._animations_panel.reload()
            return
        if row <= 0 or row - 1 >= len(PRODUCT_CATEGORY_ORDER):
            return
        category = PRODUCT_CATEGORY_ORDER[row - 1]
        if category in self._visual_browsers:
            self._filter_visual_assets(category)
            if category == ProductCategory.ROSTERS_PLAYERS \
                    and self._roster_panel is not None:
                if refresh_embedded and bool(
                    getattr(self.facade, "source_ready", False)
                ):
                    self._roster_panel.reload()
        elif category == ProductCategory.STADIUMS:
            self._load_stadium_scenes()
        elif category == ProductCategory.MENUS_UI:
            self._ensure_universal_browser()
        elif category == ProductCategory.TEAM_IDENTITY \
                and self._text_roster_panel is not None:
            if refresh_embedded and bool(getattr(self.facade, "source_ready", False)):
                self._text_roster_panel.reload()
        elif category == ProductCategory.CRIB and self._crib_panel is not None:
            if refresh_embedded and bool(getattr(self.facade, "source_ready", False)):
                self._crib_panel.refresh()
        elif category == ProductCategory.AUDIO and self._audio_panel is not None:
            if refresh_embedded and bool(
                getattr(self.facade, "source_ready", False)
            ):
                self._audio_panel.refresh()
        elif category == ProductCategory.PLAYBOOKS_PLAYS \
                and self._playbooks_panel is not None:
            if bool(getattr(self.facade, "source_ready", False)):
                self._playbooks_panel.refresh()
```

## Runtime file closure

Add these complete path lines to `packaging/release-allowlist.txt` (no registry
row is needed: this repairs existing operations, not a new capability):

```text
mod_editor/core/responsive_json.py
mod_editor/core/studio_inspection.py
mod_editor/gui/stall_watchdog.py
mod_editor/gui/workspace_runtime.py
```

The probe, test fixtures and reports are development evidence, not runtime files.
`packaging/repin.py --apply` updates existing pins in `providers.py` and the
protected runtime checker mechanically; those pin-only checker changes are in the
commit. The new responsive JSON dependency is already pinned in both provider dependency
dictionaries. In `packaging/check_2k5_mod_studio_runtime.py`, add this exact
line to `REQUIRED_UNIFIED_PROVIDER_CLOSURE`:

```python
        "mod_editor/core/responsive_json.py",
```

New provider pin (re-run repin after integration):

```python
        "mod_editor/core/responsive_json.py": "7fb0241f333733941dab16032bbcd1310fa85a46f850a7d774273ff68dccb18c",
```

The child inspection preserves the `TuningSettings` dataclass on return; it
is tested against real in-process inspection of a synthetic executable. Preview
and uniform-colour preparation release the facade state lock. Private original
PNG/receipt publication has its own lock so simultaneous preview/export stays
consistent. No change is needed in the protected Build panel.

After integration run the standalone checks in `ASTRA_REPORT.md`, the release
allowlist/runtime gates, and the retail watchdog probe without `--pending-wiring`.
No XBE writer sites changed; there is no new cave reservation.

---

