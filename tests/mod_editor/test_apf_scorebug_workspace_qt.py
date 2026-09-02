"""The Scorebug workspace has to show the scorebug, and label what it cannot edit.

The shipped page named an inventory it never displayed: APF's field scorebug art
lives inside the ``scorebug_*`` SCNE parts, which the inner-file catalog cannot
address, so the workspace offered three tables and one 128x128 digit mask.  These
tests pin the revamp: the artwork is listed, every row without a proved writer
says so in words, the one row with a writer routes to it, and the whole page
still fits the 1040-wide shell minimum.
"""

from __future__ import annotations

import os
import struct
from types import SimpleNamespace
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QTabWidget  # noqa: E402

from mod_editor.apf_studio.catalog import _category_for  # noqa: E402
from mod_editor.apf_studio.gui import (  # noqa: E402
    SCENE_TEXTURE_NO_WRITER_REASON,
    ScorebugStudioPage,
)
from mod_editor.apf_studio.models import ApfAsset, ApfCategory, ApfStatus  # noqa: E402
from mod_editor.apf_studio import scene_textures  # noqa: E402
from mod_editor.apf_studio.workspace_routes import (  # noqa: E402
    DIGITAL_FONT_TAB,
    TEAM_LOGO_TAB,
    route_for_asset,
)


#: The shell's own floor.  A page that pushes past this forces the window wider
#: than a small laptop, which is exactly the complaint this revamp answers.
SHELL_MINIMUM_WIDTH = 1040

SYSTEM_TABLE_OFFSET = 0x100


def _descriptor(
    *,
    texture_id: int,
    width: int,
    height: int,
    video_offset: int,
    base_length: int,
) -> bytes:
    """One synthetic 0xE0 TXTR descriptor: structure only, no game bytes.

    Encoded as untiled 8_8_8_8 with an identity swizzle so the same buffer
    exercises both the descriptor walk and the decode path.
    """

    raw = bytearray(scene_textures.TEXTURE_RECORD_SIZE)
    struct.pack_into(">I", raw, 0, texture_id)
    struct.pack_into(">HH", raw, 0x60, width, height)
    struct.pack_into(">I", raw, 0x6C, video_offset | 1)
    struct.pack_into(">I", raw, 0x70, base_length)
    struct.pack_into(">I", raw, 0x74, 0)
    pitch_pixels = max(32, ((width + 31) // 32) * 32)
    dword_0 = 2 | ((pitch_pixels >> 5) << 22)
    dword_1 = 6  # format 8_8_8_8, endianness "none"
    dword_2 = (width - 1) | ((height - 1) << 13)
    swizzle = 0 | (1 << 3) | (2 << 6) | (3 << 9)
    dword_3 = swizzle << 1
    dword_5 = 1 << 9  # 2D
    struct.pack_into(">6I", raw, 0x94, dword_0, dword_1, dword_2, dword_3, 0, dword_5)
    return bytes(raw)


def _scene_system(descriptors: tuple[bytes, ...]) -> bytes:
    system = bytearray(SYSTEM_TABLE_OFFSET + len(descriptors) * scene_textures.TEXTURE_RECORD_SIZE)
    struct.pack_into(">I", system, 0x20, len(descriptors))
    struct.pack_into(">I", system, 0x24, SYSTEM_TABLE_OFFSET - 0x24 + 1)
    for index, raw in enumerate(descriptors):
        start = SYSTEM_TABLE_OFFSET + index * scene_textures.TEXTURE_RECORD_SIZE
        system[start : start + len(raw)] = raw
    return bytes(system)


def _asset(
    outer_index: int,
    inner_index: int,
    name: str,
    type_name: str,
    status: ApfStatus = ApfStatus.EXPORT_ONLY,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{outer_index}:inner:{inner_index}",
        outer_index=outer_index,
        inner_index=inner_index,
        name=name,
        type_name=type_name,
        asset_class="test",
        category=ApfCategory.SCOREBUG,
        status=status,
        decoded_size=1024,
        outer_size=4096,
        part_count=2,
    )


def _facade() -> SimpleNamespace:
    """The smallest facade the unloaded page touches."""

    return SimpleNamespace(source_ready=False, modified_asset_ids=frozenset())


class ApfScorebugWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _page(self) -> ScorebugStudioPage:
        page = ScorebugStudioPage(
            _facade(),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
        )
        self.addCleanup(self.application.processEvents)
        self.addCleanup(page.deleteLater)
        return page

    def test_page_leads_with_the_scorebug_art_then_its_components(self) -> None:
        page = self._page()
        self.assertIsNotNone(page.graphics)
        self.assertIsNotNone(page.components)
        self.assertEqual(
            tuple(
                page.graphics.table.horizontalHeaderItem(column).text()
                for column in range(page.graphics.table.columnCount())
            ),
            ("Graphic", "Size", "Format", "Editing"),
        )
        tabs = page.findChild(QTabWidget, "workspaceTabs")
        assert tabs is not None
        self.assertEqual(tabs.tabText(1), DIGITAL_FONT_TAB)
        # The full inventory stays browse/export-only: no writer on this page
        # covers a SCNE, a texture embedded in one, or a separate system.
        self.assertTrue(page.browser.browse_export_only)
        self.assertIn("no proved writer", page.browser.action_lock_reason)

    def test_unloaded_page_says_what_to_do_instead_of_showing_nothing(self) -> None:
        page = self._page()
        page.graphics.set_context()
        self.assertIn("Load", page.graphics.count.text())
        for button in (
            page.graphics.export_png_button,
            page.graphics.export_raw_button,
            page.graphics.edit_button,
        ):
            # Never silent-gray: a blocked control stays clickable and explains.
            self.assertTrue(button.isEnabled())
            self.assertTrue(str(button.property("disableReason") or "").strip())

    def test_component_map_lists_seven_parts_and_names_the_runtime_sampler(self) -> None:
        page = self._page()
        page.components.set_context()
        table = page.components.table
        self.assertEqual(table.rowCount(), 7)
        names = {table.item(row, 0).text() for row in range(table.rowCount())}
        self.assertIn("scorebug_bottombar", names)
        self.assertIn("scorebug_team_logos", names)
        artwork = {
            table.item(row, 0).text(): table.item(row, 3).text()
            for row in range(table.rowCount())
        }
        self.assertEqual(artwork["scorebug_team_logos"], "2 runtime sampler(s)")
        self.assertEqual(artwork["scorebug_bottombar"], "8 embedded texture(s)")
        boundary = {
            table.item(row, 0).text(): table.item(row, 4).text()
            for row in range(table.rowCount())
        }
        self.assertIn("not proved", boundary["scorebug_team_logos"])
        self.assertIn("no writer is proved", boundary["scorebug_bottombar"])
        self.assertIn("read-only", page.components.note.text())

    def test_embedded_graphics_are_listed_and_labelled_unproved(self) -> None:
        page = self._page()
        textures = (
            scene_textures.SceneTexture(
                outer_index=1310,
                inner_index=106,
                scene_name="scorebug_bottombar",
                index=6,
                texture_id=0x62047D29,
                width=128,
                height=128,
                format_name="DXT4_5",
                video_offset=0x9000,
                payload_length=16384,
            ),
            scene_textures.SceneTexture(
                outer_index=1310,
                inner_index=235,
                scene_name="scorebug_infobar",
                index=0,
                texture_id=0x5146477A,
                width=512,
                height=512,
                format_name="DXT1",
                video_offset=0,
                payload_length=131072,
            ),
            scene_textures.SceneTexture(
                outer_index=1310,
                inner_index=360,
                scene_name="scorebug_statbar",
                index=0,
                texture_id=0x5146477A,
                width=512,
                height=512,
                format_name="DXT1",
                video_offset=0,
                payload_length=131072,
            ),
        )
        font = _asset(1310, 246, "digital_font", "TXTR", ApfStatus.EDITABLE)
        page.graphics._populate(textures, (font,))

        table = page.graphics.table
        self.assertEqual(table.rowCount(), 4)
        self.assertEqual(page.graphics.count.text(), "4 graphics · 1 with a proved writer")
        titles = [table.item(row, 0).text() for row in range(table.rowCount())]
        self.assertIn("scorebug_bottombar · embedded 06", titles)
        self.assertIn("digital_font · score digits", titles)
        editing = {
            table.item(row, 0).text(): table.item(row, 3).text()
            for row in range(table.rowCount())
        }
        self.assertEqual(
            editing["scorebug_bottombar · embedded 06"], "Read-only · no writer"
        )
        # One texture id declared by two components is one image reused.
        self.assertEqual(editing["scorebug_infobar · embedded 00"], "Read-only · shared id")
        self.assertEqual(editing["scorebug_statbar · embedded 00"], "Read-only · shared id")
        self.assertEqual(editing["digital_font · score digits"], "Editable · shared atlas")

        rows = {graphic.title: graphic for graphic in page.graphics._graphics}
        self.assertIn(
            "no writer exists", rows["scorebug_bottombar · embedded 06"].detail
        )
        self.assertIn("more than one", rows["scorebug_infobar · embedded 00"].detail)
        self.assertIn(
            "runtime visibility is not proved",
            rows["digital_font · score digits"].detail,
        )
        self.assertIn("no writer exists", SCENE_TEXTURE_NO_WRITER_REASON)

    def test_read_only_row_offers_no_edit_button_and_the_writer_row_does(self) -> None:
        page = self._page()
        embedded = scene_textures.SceneTexture(
            outer_index=1310,
            inner_index=106,
            scene_name="scorebug_bottombar",
            index=0,
            texture_id=0x058A6C2C,
            width=64,
            height=64,
            format_name="DXT1",
            video_offset=0,
            payload_length=4096,
        )
        font = _asset(1310, 246, "digital_font", "TXTR", ApfStatus.EDITABLE)
        page.graphics._populate((embedded,), (font,))

        page.graphics.table.selectRow(0)
        self.assertIn("no writer exists", str(page.graphics.edit_button.property("disableReason")))
        self.assertIn("Read-only", page.graphics.table.item(0, 3).text())

        page.graphics.table.selectRow(1)
        self.assertEqual(str(page.graphics.edit_button.property("disableReason") or ""), "")
        page.graphics._edit_selected()
        tabs = page.findChild(QTabWidget, "workspaceTabs")
        assert tabs is not None
        self.assertEqual(tabs.tabText(tabs.currentIndex()), DIGITAL_FONT_TAB)

    def test_page_minimum_width_survives_a_1040_wide_shell(self) -> None:
        page = self._page()
        page.resize(SHELL_MINIMUM_WIDTH, 600)
        self.application.processEvents()
        minimum = page.minimumSizeHint().width()
        self.assertLess(
            minimum,
            SHELL_MINIMUM_WIDTH,
            f"Scorebug page demands {minimum}px, wider than the {SHELL_MINIMUM_WIDTH}px shell",
        )

    def test_scorebug_team_logos_no_longer_files_under_logos(self) -> None:
        # The generic "logo" token used to win, hiding one of the seven field
        # components in a workspace that cannot show it.
        self.assertIs(_category_for("scorebug_team_logos", "SCNE"), ApfCategory.SCOREBUG)
        self.assertIs(_category_for("uniform_logo_04", "TXTR"), ApfCategory.UNIFORMS)
        self.assertIs(_category_for("logo_l0", "TXTR"), ApfCategory.LOGOS)

    def test_the_two_routable_presentation_rows_name_their_real_owner(self) -> None:
        font_route = route_for_asset(_asset(1310, 246, "digital_font", "TXTR"))
        assert font_route is not None
        self.assertIs(font_route.category, ApfCategory.SCOREBUG)
        self.assertEqual(font_route.tab, DIGITAL_FONT_TAB)
        self.assertIn("runtime visibility is not proved", font_route.summary)

        logo_route = route_for_asset(_asset(1310, 156, "scorebug_team_logos", "SCNE"))
        assert logo_route is not None
        self.assertIs(logo_route.category, ApfCategory.LOGOS)
        self.assertEqual(logo_route.tab, TEAM_LOGO_TAB)
        self.assertIn("not proved", logo_route.summary)

        # A scene with no writer stays unrouted rather than gaining a dead door.
        self.assertIsNone(
            route_for_asset(_asset(1310, 106, "scorebug_bottombar", "SCNE"))
        )

    def test_descriptor_walk_finds_and_decodes_an_embedded_texture(self) -> None:
        system = _scene_system(
            (
                _descriptor(
                    texture_id=0xABCD1234,
                    width=2,
                    height=2,
                    video_offset=0,
                    base_length=256,
                ),
            )
        )
        # A linear 8_8_8_8 base is stored at the descriptor's 32-pixel pitch.
        vram = bytes(range(256))
        found = scene_textures.scene_textures(
            system,
            vram,
            outer_index=1310,
            inner_index=106,
            scene_name="scorebug_bottombar",
        )
        self.assertEqual(len(found), 1)
        texture = found[0]
        self.assertEqual((texture.width, texture.height), (2, 2))
        self.assertEqual(texture.format_name, "8_8_8_8")
        self.assertEqual(texture.key, "apf:scene:1310:106:texture:000")
        width, height, rgba = scene_textures.decode_texture_rgba(
            texture, scene_textures.texture_payload(texture, vram)
        )
        self.assertEqual((width, height, len(rgba)), (2, 2, 16))

    def test_a_scene_without_embedded_art_reports_none(self) -> None:
        system = bytearray(0x200)
        struct.pack_into(">I", system, 0x24, 0x100 - 0x24 + 1)
        self.assertEqual(
            scene_textures.scene_textures(
                bytes(system),
                b"",
                outer_index=1310,
                inner_index=250,
                scene_name="scorebug_messages",
            ),
            (),
        )

    def test_shared_texture_ids_are_detected(self) -> None:
        def make(index: int, texture_id: int) -> scene_textures.SceneTexture:
            return scene_textures.SceneTexture(
                outer_index=1310,
                inner_index=index,
                scene_name=f"scene_{index}",
                index=0,
                texture_id=texture_id,
                width=8,
                height=8,
                format_name="DXT1",
                video_offset=0,
                payload_length=64,
            )

        shared = scene_textures.shared_texture_ids(
            (make(235, 0x5146477A), make(360, 0x5146477A), make(131, 0x4FC831ED))
        )
        self.assertEqual(shared, frozenset({0x5146477A}))


if __name__ == "__main__":
    unittest.main()
