"""Playbook research boundaries, plain 3rd-and-long status, and copied 0A."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.apf_studio.source import (  # noqa: E402
    COPIED_0A_REFUSAL,
    EXPECTED_0A_SHA256,
    EXPECTED_GAME_FILES,
    STUDIO_BUILD_SCHEMA,
    STUDIO_BUILD_SIDECAR_NAME,
    STUDIO_BUILT_0A_REFUSAL,
    SourceError,
    SourceManager,
    classify_non_retail_0a,
    inspect_studio_build_sidecar,
)
from mod_editor.core.errors import ValidationError  # noqa: E402


def _sidecar_document(digest: str) -> dict[str, object]:
    return {
        "schema": STUDIO_BUILD_SCHEMA,
        "source": {
            "0a_sha256_before": EXPECTED_0A_SHA256,
            "0a_sha256_after": EXPECTED_0A_SHA256,
            "opened_read_only": True,
            "source_modified": False,
        },
        "output": {
            "type": "complete_extracted_game_directory",
            "0a_sha256": digest,
        },
    }


class CopiedZeroARefusalTests(unittest.TestCase):
    def test_arbitrary_modified_0a_is_refused(self) -> None:
        digest = "ab" * 32
        with tempfile.TemporaryDirectory() as directory:
            error = classify_non_retail_0a(Path(directory), digest)
        self.assertIsInstance(error, SourceError)
        self.assertEqual(str(error), COPIED_0A_REFUSAL)
        self.assertIn("Beta 44", str(error))
        self.assertIn("retail entry hashes", str(error))
        self.assertIn("last folder", str(error))

    def test_studio_built_sidecar_from_retail_is_still_refused(self) -> None:
        digest = "cd" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / STUDIO_BUILD_SIDECAR_NAME).write_text(
                json.dumps(_sidecar_document(digest)), encoding="utf-8"
            )
            self.assertIsNotNone(inspect_studio_build_sidecar(root, digest))
            error = classify_non_retail_0a(root, digest)
        self.assertEqual(str(error), STUDIO_BUILT_0A_REFUSAL)
        self.assertIn("Beta 44", str(error))
        self.assertIn("Rebuild into the last folder", str(error))
        self.assertIn("retail entry hashes", str(error))

    def test_a_sidecar_for_a_different_hash_is_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / STUDIO_BUILD_SIDECAR_NAME).write_text(
                json.dumps(_sidecar_document("11" * 32)), encoding="utf-8"
            )
            self.assertIsNone(inspect_studio_build_sidecar(root, "22" * 32))
            error = classify_non_retail_0a(root, "22" * 32)
        self.assertEqual(str(error), COPIED_0A_REFUSAL)

    def test_a_sidecar_that_does_not_name_retail_source_is_not_trusted(self) -> None:
        digest = "ee" * 32
        document = _sidecar_document(digest)
        document["source"]["0a_sha256_before"] = "00" * 32  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / STUDIO_BUILD_SIDECAR_NAME).write_text(
                json.dumps(document), encoding="utf-8"
            )
            self.assertIsNone(inspect_studio_build_sidecar(root, digest))
            self.assertEqual(
                str(classify_non_retail_0a(root, digest)), COPIED_0A_REFUSAL
            )

    def test_a_symlinked_sidecar_is_ignored(self) -> None:
        digest = "ff" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "decoy.json"
            real.write_text(json.dumps(_sidecar_document(digest)), encoding="utf-8")
            (root / STUDIO_BUILD_SIDECAR_NAME).symlink_to(real)
            self.assertIsNone(inspect_studio_build_sidecar(root, digest))
            self.assertEqual(
                str(classify_non_retail_0a(root, digest)), COPIED_0A_REFUSAL
            )

    def test_validate_root_raises_the_studio_build_refusal(self) -> None:
        digest = "ab" * 32
        tiny = {name: 1 for name in EXPECTED_GAME_FILES}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in tiny:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
            (root / STUDIO_BUILD_SIDECAR_NAME).write_text(
                json.dumps(_sidecar_document(digest)), encoding="utf-8"
            )
            manager = SourceManager(cache_root=root / "cache")
            with patch(
                "mod_editor.apf_studio.source.EXPECTED_GAME_FILES", tiny
            ), patch(
                "mod_editor.apf_studio.source.sha256_file", return_value=digest
            ):
                with self.assertRaises(SourceError) as caught:
                    manager._validate_root(
                        root,
                        root,
                        lambda *_args: None,
                        extracted_from_iso=False,
                        source_iso_sha256=None,
                    )
        self.assertEqual(str(caught.exception), STUDIO_BUILT_0A_REFUSAL)


class G12PanelHonestyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_status_button_is_clickable_and_raw_research_export_is_withdrawn(self) -> None:
        from mod_editor.apf_studio.playbook_membership_qt import (
            ApfPlaybookMembershipPanel,
        )

        facade = MagicMock()
        facade.source_ready = False
        facade.source = None
        panel = ApfPlaybookMembershipPanel(facade, lambda *_a, **_k: None)
        try:
            self.assertFalse(hasattr(panel, "export_g12_pack_button"))
            self.assertTrue(panel.third_long_button.isEnabled())
            self.assertIn("3rd-and-long", panel.third_long_button.text().casefold())
            self.assertIn("plain-language", panel.third_long_button.toolTip())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_status_button_can_be_clicked_twice_without_the_crash_reporter(self) -> None:
        from mod_editor.apf_studio.playbook_membership_qt import (
            ApfPlaybookMembershipPanel,
        )

        facade = MagicMock()
        facade.source_ready = False
        facade.source = None
        panel = ApfPlaybookMembershipPanel(facade, lambda *_a, **_k: None)
        try:
            with patch(
                "mod_editor.apf_studio.playbook_membership_qt.QMessageBox.information"
            ) as information, patch.object(sys, "excepthook") as excepthook:
                panel.third_long_button.click()
                panel.third_long_button.click()
            self.assertEqual(information.call_count, 2)
            excepthook.assert_not_called()
            for call in information.call_args_list:
                title, body = call.args[1:3]
                self.assertEqual(title, "3rd-and-long editing is not available")
                self.assertIn("default.xex", body)
                self.assertIn("Nothing was changed", body)
                self.assertNotIn("data-side", body.casefold())
                self.assertNotIn("refuses a writer", body.casefold())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_boundary_does_not_claim_third_and_long_is_fixed(self) -> None:
        from mod_editor.apf_studio.playbook_membership_qt import BOUNDARY

        self.assertNotIn("put TEs on", BOUNDARY)
        self.assertIn("does not change the personnel", BOUNDARY)
        self.assertNotIn("data-side", BOUNDARY.casefold())
        self.assertNotIn("0x84", BOUNDARY)

    def test_facade_does_not_offer_an_unusable_raw_export(self) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade

        self.assertFalse(
            hasattr(ApfStudioFacade, "export_g12_wr3_te_package_map_pack")
        )
        self.assertFalse(
            hasattr(ApfStudioFacade, "refuse_apf_3rd_and_long_user_logic_writer")
        )


def _synthetic_apf_master() -> bytes:
    import struct

    from mod_editor.core.playbook_package_rule_spike import (
        APF_ACE_EMPTY_PACKAGE_MAP,
        APF_ACE_PACKAGE_MAP,
        APF_FORMATION_BASE,
        APF_FORMATION_COUNT_OFFSET,
        APF_FORMATION_SIZE,
        APF_MASTER_BODY_SIZE,
        APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
    )

    body = bytearray(APF_MASTER_BODY_SIZE)
    struct.pack_into(">I", body, APF_FORMATION_COUNT_OFFSET, 3)
    names = ("Ace", "Ace Empty", "Nickel")
    maps = (
        APF_ACE_PACKAGE_MAP,
        APF_ACE_EMPTY_PACKAGE_MAP,
        (4, 5, 0, 2, 3, 1, 7, 8, 9, 6, 10),
    )
    pool = 0x22384
    for index, (name, pmap) in enumerate(zip(names, maps, strict=True)):
        field = APF_FORMATION_BASE + index * APF_FORMATION_SIZE
        encoded = name.encode("utf-16be") + b"\0\0"
        body[pool : pool + len(encoded)] = encoded
        struct.pack_into(">i", body, field, pool - field + 1)
        pool += len(encoded)
        offset = field + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
        body[offset : offset + 11] = bytes(pmap)
    return bytes(body)


class G12LibraryHonestyTests(unittest.TestCase):
    def test_pack_is_experimental_ace_named_8_9_not_ace_empty_copy(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_3RD_AND_LONG_PLAY_CHOICE_PROVED,
            APF_ACE_EMPTY_PACKAGE_MAP,
            APF_ACE_PACKAGE_MAP,
            APF_G12_PACK_EXPERIMENTAL,
            APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE,
            APF_WR3_TE_PACKAGE_SUB_PROVED,
            build_g12_wr3_te_package_map_pack,
            swap_apf_package_map_wr3_te,
        )

        self.assertTrue(APF_G12_PACK_EXPERIMENTAL)
        self.assertFalse(APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE)
        self.assertFalse(APF_WR3_TE_PACKAGE_SUB_PROVED)
        self.assertFalse(APF_3RD_AND_LONG_PLAY_CHOICE_PROVED)
        pack = build_g12_wr3_te_package_map_pack(_synthetic_apf_master())
        self.assertTrue(pack.manifest["experimental"])
        self.assertFalse(pack.manifest["ace_empty_used_as_source"])
        self.assertFalse(pack.manifest["wr3_te_package_sub_proved"])
        self.assertIn("experimental", pack.honesty.casefold())
        self.assertIn("ace-named", pack.honesty.casefold())
        self.assertIn("not used as a source", pack.honesty.casefold())
        ace = next(t for t in pack.targets if t.formation_name == "Ace")
        self.assertEqual(ace.new_map, swap_apf_package_map_wr3_te(APF_ACE_PACKAGE_MAP))
        self.assertNotEqual(ace.new_map, APF_ACE_EMPTY_PACKAGE_MAP)
        self.assertTrue(all("ace" in t.formation_name.casefold() for t in pack.targets))

    def test_library_refusal_is_typed_and_names_executable(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_3RD_AND_LONG_PLAY_CHOICE_PROVED,
            APF_3RD_AND_LONG_USER_LOGIC_REFUSAL,
            ApfThirdAndLongUserLogicRefusal,
            refuse_apf_3rd_and_long_user_logic_writer,
        )

        self.assertFalse(APF_3RD_AND_LONG_PLAY_CHOICE_PROVED)
        with self.assertRaises(ApfThirdAndLongUserLogicRefusal) as caught:
            refuse_apf_3rd_and_long_user_logic_writer()
        self.assertIsInstance(caught.exception, ValidationError)
        self.assertEqual(str(caught.exception), APF_3RD_AND_LONG_USER_LOGIC_REFUSAL)
        self.assertIn("default.xex", str(caught.exception))
        self.assertIn("0x8486CE88", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
