"""The universal browser hands a row to the workspace that can write it.

Beta 29 and Beta 30 answered *"logo_l0 is not an editable PNG slot in this
browser"* to a modder who had followed the browser's own search hint.  The
sentence described the browser and not the product: the Team Logo editor writes
every one of the 118 crest packages, Uniforms writes the 96 material slots,
Wordmarks writes all 206, and Field Art writes its six base textures.

These tests pin the behaviour that replaced the refusal -- the row is routed,
the action button offers the hand-off, a chosen image travels with it, and a row
that genuinely has no writer anywhere still says so honestly.
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.apf_studio.models import (  # noqa: E402
    ApfAsset,
    ApfCategory,
    ApfStatus,
    UniformAsset,
)
from mod_editor.apf_studio.workspace_routes import (  # noqa: E402
    TEAM_LOGO_TAB,
    UNIFORM_MATERIALS_TAB,
    WORDMARK_TAB,
    WorkspaceHandoff,
    route_for_asset,
)


def _asset(
    *,
    name: str,
    outer_index: int,
    inner_index: int | None = 0,
    type_name: str = "TXTR",
) -> ApfAsset:
    return ApfAsset(
        asset_id=(
            f"apf:outer:{outer_index}"
            if inner_index is None
            else f"apf:outer:{outer_index}:inner:{inner_index}"
        ),
        outer_index=outer_index,
        inner_index=inner_index,
        name=name,
        type_name=type_name,
        asset_class="texture",
        category=ApfCategory.LOGOS,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=704_736,
        outer_size=83_968,
        part_count=2,
    )


def _uniform(
    family: str, asset_index: int, outer_index: int, inner_index: int
) -> UniformAsset:
    width, height = {
        "jersey": (1024, 1024),
        "pants": (512, 512),
        "helmet": (256, 1024),
        "shoulder": (1024, 1024),
        "textlogo": (512, 128),
    }[family]
    return UniformAsset(
        family=family,
        asset_index=asset_index,
        asset_id=f"apf:uniform:{family}:{asset_index:02d}",
        title=f"{family.title()} {asset_index:02d}",
        width=width,
        height=height,
        png_contract="Synthetic contract.",
        status=ApfStatus.EDITABLE,
        outer_index=outer_index,
        inner_index=inner_index,
    )


class WorkspaceRouteTests(unittest.TestCase):
    """The pure routing table, with no Qt and no archive."""

    def test_both_crest_layers_route_to_team_logo_by_outer_entry(self) -> None:
        for layer in ("logo_l0", "logo_l1"):
            with self.subTest(layer=layer):
                route = route_for_asset(_asset(name=layer, outer_index=1133))
                self.assertIsNotNone(route)
                assert route is not None
                self.assertIs(route.category, ApfCategory.LOGOS)
                self.assertEqual(route.tab, TEAM_LOGO_TAB)
                # The key is the archive location, which is all the browser
                # knows and all the crest picker needs.
                self.assertEqual(route.key, "1133")
                self.assertIn("Team Logo", route.action_label)
                self.assertEqual(
                    route.destination, "Logos & Team Art → Team Logo"
                )

    def test_a_crest_named_row_of_another_type_is_not_routed(self) -> None:
        # Only the TXTR crest layers are crest layers. Routing on the name
        # alone would claim authorship over anything that happened to share it.
        self.assertIsNone(
            route_for_asset(_asset(name="logo_l0", outer_index=1133, type_name="SCNE"))
        )

    def test_uniform_material_rows_route_to_the_uniforms_workspace(self) -> None:
        uniforms = (_uniform("shoulder", 6, 400, 2),)
        route = route_for_asset(
            _asset(name="shoulder_color", outer_index=400, inner_index=2),
            uniform_assets=uniforms,
        )
        self.assertIsNotNone(route)
        assert route is not None
        self.assertIs(route.category, ApfCategory.UNIFORMS)
        self.assertEqual(route.tab, UNIFORM_MATERIALS_TAB)
        self.assertEqual(route.key, "apf:uniform:shoulder:06")
        self.assertIn("1024×1024", route.summary)

    def test_wordmarks_route_to_logos_rather_than_uniforms(self) -> None:
        # textlogo rows share the uniform transport but are authored in
        # Logos → Wordmarks, and a crest is never squeezed into that family.
        route = route_for_asset(
            _asset(name="textlogo_color", outer_index=770, inner_index=1),
            uniform_assets=(_uniform("textlogo", 42, 770, 1),),
        )
        self.assertIsNotNone(route)
        assert route is not None
        self.assertIs(route.category, ApfCategory.LOGOS)
        self.assertEqual(route.tab, WORDMARK_TAB)
        self.assertEqual(route.key, "42")

    def test_field_art_rows_route_by_pinned_archive_location(self) -> None:
        route = route_for_asset(
            _asset(name="endzone_l0", outer_index=6, inner_index=0),
            field_art_targets={(6, 0): "endzone_l0"},
        )
        self.assertIsNotNone(route)
        assert route is not None
        self.assertIs(route.category, ApfCategory.FIELD_ART)
        self.assertEqual(route.key, "endzone_l0")

    def test_a_row_with_no_proved_writer_anywhere_is_not_routed(self) -> None:
        self.assertIsNone(
            route_for_asset(
                _asset(name="helmet_normal", outer_index=901, inner_index=3),
                uniform_assets=(_uniform("helmet", 0, 400, 0),),
                field_art_targets={(6, 0): "endzone_l0"},
            )
        )

    def test_an_outer_only_record_is_never_matched_by_location(self) -> None:
        # inner_index None must not collide with a uniform row at inner 0.
        self.assertIsNone(
            route_for_asset(
                _asset(name="outer_0400", outer_index=400, inner_index=None, type_name="NON_IFF"),
                uniform_assets=(_uniform("jersey", 0, 400, 0),),
            )
        )


class FieldArtWriterTableTests(unittest.TestCase):
    def test_writable_locations_match_the_editor_panel_pins(self) -> None:
        from mod_editor.apf_studio import gui
        from mod_editor.apf_studio.backend import ensure_tools_importable

        ensure_tools_importable()
        import apf_field_art_patch  # type: ignore

        self.assertEqual(
            apf_field_art_patch.writable_locations(),
            {target.key: target.name for target in gui.FIELD_ART_COVERED_TARGETS},
        )


class CatalogNoteTests(unittest.TestCase):
    def test_a_workspace_owned_row_stops_claiming_nothing_owns_it(self) -> None:
        from mod_editor.apf_studio import catalog

        owned = {(400, 2): "Uniforms & Equipment → Editable Materials"}
        crest = catalog._notes_for(1133, 0, "TXTR", "logo_l0", ApfStatus.EXPORT_ONLY, owned)
        material = catalog._notes_for(
            400, 2, "TXTR", "shoulder_color", ApfStatus.EXPORT_ONLY, owned
        )
        unowned = catalog._notes_for(
            901, 3, "TXTR", "helmet_normal", ApfStatus.EXPORT_ONLY, owned
        )
        for notes in (crest, material):
            joined = " ".join(notes)
            self.assertIn("A proved writer owns this target", joined)
            self.assertNotIn("no validated replacement writer", joined.casefold())
        self.assertIn(
            "No validated replacement writer owns this target yet.", unowned
        )


class _RoutingFacade:
    """Enough catalog for a browser to route rows, with no archive at all."""

    def __init__(self) -> None:
        from mod_editor.apf_studio.catalog import ApfCatalog

        self._uniforms = (
            _uniform("shoulder", 6, 400, 2),
            _uniform("textlogo", 42, 770, 1),
        )
        self.assets = (
            _asset(name="logo_l0", outer_index=36, inner_index=1),
            _asset(name="shoulder_color", outer_index=400, inner_index=2),
            _asset(name="textlogo_color", outer_index=770, inner_index=1),
            _asset(name="helmet_normal", outer_index=901, inner_index=3),
        )
        self.catalog = ApfCatalog(
            source_sha256="e" * 64,
            outer_count=4,
            iff_count=4,
            non_iff_count=0,
            inner_count=4,
            assets=self.assets,
            uniform_assets=self._uniforms,
            capabilities=(),
            audio_selection_manifest=Path("synthetic-inner-selection.json"),
        )
        self.source_ready = True
        self.modified_asset_ids: frozenset[str] = frozenset()

    def require_catalog(self):
        return self.catalog

    def uniform_assets(self, family: str | None = None):
        values = self.catalog.uniform_assets
        return values if family is None else tuple(
            item for item in values if item.family == family
        )

    def browse_assets(self, **kwargs):
        return self.catalog.browse(**kwargs)

    def capability_cards(self, _category=None):
        return ()

    def preview_texture(self, *_args, **_kwargs):
        raise RuntimeError("previews are not exercised here")


class BrowserActionTests(unittest.TestCase):
    """What the Replace control does now, on the rows that were refused."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _browser(self):
        from mod_editor.apf_studio.gui import AssetBrowser

        facade = _RoutingFacade()
        browser = AssetBrowser(
            facade,  # type: ignore[arg-type]
            ApfCategory.ALL_ASSETS,
            lambda *_a, **_k: None,  # type: ignore[arg-type]
        )
        browser.refresh()
        self.app.processEvents()
        return facade, browser

    def _select(self, browser, name: str):
        from PyQt5.QtCore import Qt

        for row in range(browser.table.rowCount()):
            if browser.table.item(row, 1).text() == name:
                browser.table.selectRow(row)
                self.app.processEvents()
                browser._selection_changed()
                return browser._selected_asset()
        raise AssertionError(f"no row named {name}")

    def test_a_crest_row_offers_the_handoff_instead_of_refusing(self) -> None:
        _facade, browser = self._browser()
        try:
            asset = self._select(browser, "logo_l0")
            self.assertEqual(asset.name, "logo_l0")
            self.assertIsNotNone(browser._route)
            # The exact regression: this button used to be a wall.
            self.assertEqual(browser.replace_button.text(), "Edit in Team Logo…")
            self.assertEqual(
                str(browser.replace_button.property("disableReason") or ""), ""
            )
            self.assertTrue(browser.replace_button.isEnabled())
            # A drop is admitted too, because the workspace can finish it.
            self.assertTrue(browser.preview.acceptDrops())
            self.assertIn("Team Logo editor owns it", browser.detail_notes.text())
        finally:
            browser.deleteLater()
            self.app.processEvents()

    def test_a_dropped_image_is_emitted_with_the_route(self) -> None:
        _facade, browser = self._browser()
        seen: list[WorkspaceHandoff] = []
        browser.openWorkspaceRequested.connect(seen.append)
        try:
            self._select(browser, "logo_l0")
            dropped = Path("/tmp/some-crest.png")
            browser._replace_from_drop(dropped)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].route.tab, TEAM_LOGO_TAB)
            self.assertEqual(seen[0].route.key, "36")
            self.assertEqual(seen[0].asset_name, "logo_l0")
            # str(Path(...)), not a POSIX literal: this same assertion with a
            # hard-coded "/tmp/..." passed on Linux and failed on Windows,
            # where str(Path) renders backslashes.
            self.assertEqual(seen[0].image, str(dropped))
        finally:
            browser.deleteLater()
            self.app.processEvents()

    def test_uniform_and_wordmark_rows_name_their_own_workspaces(self) -> None:
        _facade, browser = self._browser()
        try:
            self._select(browser, "shoulder_color")
            self.assertEqual(browser.replace_button.text(), "Edit in Uniforms…")
            self._select(browser, "textlogo_color")
            self.assertEqual(browser.replace_button.text(), "Edit in Wordmarks…")
        finally:
            browser.deleteLater()
            self.app.processEvents()

    def test_an_unowned_row_still_states_the_honest_boundary(self) -> None:
        _facade, browser = self._browser()
        try:
            self._select(browser, "helmet_normal")
            self.assertIsNone(browser._route)
            self.assertEqual(browser.replace_button.text(), "Replace PNG…")
            self.assertIn(
                "No proved writer owns",
                str(browser.replace_button.property("disableReason") or ""),
            )
            self.assertFalse(browser.preview.acceptDrops())
        finally:
            browser.deleteLater()
            self.app.processEvents()

    def test_refresh_never_leaves_a_stale_asset_in_the_detail_panel(self) -> None:
        """A search that keeps row 0 selected must still update the detail.

        ``selectRow(0)`` on an already-selected row emits no signal, so the
        panel used to keep describing the asset that was there before -- and
        Export/Replace would then act on that stale row.
        """

        _facade, browser = self._browser()
        try:
            first = self._select(browser, "logo_l0")
            self.assertEqual(browser.detail_title.text(), first.name)
            browser.search.setText("helmet_normal")
            browser.refresh()
            self.app.processEvents()
            self.assertEqual(browser.table.rowCount(), 1)
            self.assertEqual(browser.detail_title.text(), "helmet_normal")
            self.assertEqual(browser._selected_asset().name, "helmet_normal")
            self.assertIsNone(browser._route)
        finally:
            browser.deleteLater()
            self.app.processEvents()


class DestinationPageTests(unittest.TestCase):
    """The receiving half: a route actually preselects its target."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_a_crest_route_preselects_the_package_at_that_outer_entry(self) -> None:
        from mod_editor.apf_studio.gui import LogosStudioPage

        page = LogosStudioPage(
            _RoutingFacade(),  # type: ignore[arg-type]
            lambda *_a, **_k: None,  # type: ignore[arg-type]
        )
        try:
            # 1133 is the Americans' crest package; the picker starts on the
            # historical default, so a successful route has to move it.
            route = route_for_asset(_asset(name="logo_l0", outer_index=1133))
            assert route is not None
            self.assertTrue(page.focus_workspace_route(route, None))
            self.assertEqual(page.tabs.tabText(page.tabs.currentIndex()), "Team Logo")
            self.assertEqual(
                page.team_logo.slot.currentData().outer_entry_index, 1133
            )
            # A package this game does not carry is refused rather than
            # silently landing the user on somebody else's crest.
            missing = route_for_asset(_asset(name="logo_l0", outer_index=999_999))
            assert missing is not None
            self.assertFalse(page.focus_workspace_route(missing, None))
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_a_wordmark_route_preselects_its_slot(self) -> None:
        from mod_editor.apf_studio.gui import LogosStudioPage

        page = LogosStudioPage(
            _RoutingFacade(),  # type: ignore[arg-type]
            lambda *_a, **_k: None,  # type: ignore[arg-type]
        )
        try:
            route = route_for_asset(
                _asset(name="textlogo_color", outer_index=770, inner_index=1),
                uniform_assets=(_uniform("textlogo", 42, 770, 1),),
            )
            assert route is not None
            self.assertTrue(page.focus_workspace_route(route, None))
            self.assertEqual(
                page.tabs.tabText(page.tabs.currentIndex()), "Wordmarks (206)"
            )
            self.assertEqual(page.wordmarks.slot.value(), 42)
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_a_material_route_clears_filters_and_selects_the_slot(self) -> None:
        from mod_editor.apf_studio.gui import UniformStudioPage

        page = UniformStudioPage(
            _RoutingFacade(),  # type: ignore[arg-type]
            lambda *_a, **_k: None,  # type: ignore[arg-type]
        )
        page.set_context()
        self.app.processEvents()
        try:
            # A filter and a search that both exclude the target: the hand-off
            # must clear them, or it lands on an empty list.
            page.family_filter.setCurrentIndex(
                page.family_filter.findData("jersey")
            )
            page.search.setText("nothing matches this")
            self.app.processEvents()
            route = route_for_asset(
                _asset(name="shoulder_color", outer_index=400, inner_index=2),
                uniform_assets=(_uniform("shoulder", 6, 400, 2),),
            )
            assert route is not None
            self.assertTrue(page.focus_workspace_route(route, None))
            self.assertEqual(page.tabs.currentIndex(), 0)
            self.assertEqual(page.search.text(), "")
            self.assertIsNone(page.family_filter.currentData())
            selected = page._selected_asset()
            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.asset_id, "apf:uniform:shoulder:06")
        finally:
            page.deleteLater()
            self.app.processEvents()


class HandoffPayloadTests(unittest.TestCase):
    def test_a_handoff_carries_the_users_chosen_image(self) -> None:
        route = route_for_asset(_asset(name="logo_l0", outer_index=36))
        assert route is not None
        handoff = WorkspaceHandoff(
            route=route,
            asset_name="logo_l0",
            asset_id="apf:outer:36:inner:1",
            image=str(Path("/tmp/crest.png")),
        )
        self.assertEqual(handoff.image, str(Path("/tmp/crest.png")))
        self.assertEqual(handoff.route.key, "36")

    def test_a_handoff_without_an_image_is_navigation_only(self) -> None:
        route = route_for_asset(_asset(name="logo_l1", outer_index=36))
        assert route is not None
        handoff = WorkspaceHandoff(
            route=route, asset_name="logo_l1", asset_id="apf:outer:36:inner:0"
        )
        self.assertEqual(handoff.image, "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
