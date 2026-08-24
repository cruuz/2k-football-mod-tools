"""Keep Beta 45's research limits honest in later releases."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import validate_apf_field_art_product as field_gate  # noqa: E402


class Beta45HonestyFreezeTests(unittest.TestCase):
    def test_product_identity_is_beta_47(self) -> None:
        import mod_editor
        from mod_editor.apf_studio import __version__ as apf_version
        from mod_editor.core.update_check import BUILD_RELEASE_TAG

        self.assertEqual(mod_editor.__version__, "1.0.0rc75")
        self.assertEqual(apf_version, "0.1.0-alpha.82")
        self.assertEqual(BUILD_RELEASE_TAG, "beta-51")

    def test_ci_hydrate_tag_is_a_published_beta(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("gh release download beta-", workflow)
        self.assertRegex(workflow, r"2K5-Mod-Studio-v1.0-RC[0-9]{2}-")
        self.assertRegex(workflow, r"apf2k8-mod-studio-0.1.0-alpha\.[0-9]+-")

    def test_live_copy_does_not_make_the_four_forbidden_claims(self) -> None:
        from mod_editor.apf_studio.gui import CATEGORY_BLURBS
        from mod_editor.apf_studio.models import ApfCategory

        surfaces = (
            (ROOT / "docs/mod_editor/apf2k8_mod_studio_changelog.md")
            .read_text(encoding="utf-8")
            .split("## 0.1.0-alpha.76", 1)[0],
            (ROOT / "docs/mod_editor/apf2k8_mod_studio_getting_started.md").read_text(
                encoding="utf-8"
            ),
            CATEGORY_BLURBS[ApfCategory.FIELD_ART],
        )
        forbidden = (
            "parity spec done",
            "runtime_visibility_proved = True",
            "all 12 weaves are 8_8_8_8 64×64",
            "all 12 weaves are 8_8_8_8 64x64",
            "all 235 endzones writable",
        )
        for text in surfaces:
            folded = text.casefold()
            for claim in forbidden:
                self.assertNotIn(claim.casefold(), folded)
            self.assertNotIn("all 12 weaves", folded)
            self.assertNotIn("all 235 endzones writable", folded)

    def test_field_art_gate_prints_core_six_and_writable_extras_only(self) -> None:
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = field_gate.main([])
        self.assertEqual(code, 0)
        printed = buffer.getvalue()
        self.assertIn("core=6", printed)
        self.assertIn("extras=215", printed)
        extra_keys = field_gate._writable_extra_keys()
        self.assertEqual(len(extra_keys), 215)
        for key in extra_keys:
            contract = field_gate.patch._CONTRACTS[key]
            self.assertIn(contract.format, {6, 18, 20})
            self.assertIn(contract.codec, {"rgba8888", "dxt1", "bc3"})

    def test_weave_skin_weights_are_bc3_256_not_lossless_64(self) -> None:
        import apf_field_art_patch as writer

        head = writer._CONTRACTS[(659, 104)]
        arm = writer._CONTRACTS[(659, 227)]
        self.assertEqual(head.name, "weave_skin_weights_head")
        self.assertEqual(arm.name, "weave_skin_weights_arm")
        for contract in (head, arm):
            self.assertEqual(contract.codec, "bc3")
            self.assertEqual(contract.format, 20)
            self.assertEqual((contract.width, contract.height), (256, 256))
            self.assertNotEqual((contract.codec, contract.width), ("rgba8888", 64))

    def test_format_59_endzones_stay_out_of_the_writer(self) -> None:
        import json

        import apf_field_art_patch as writer

        extra = json.loads(
            (ROOT / "mod_editor/data/apf2k8_field_extra_targets.v1.json").read_text(
                encoding="utf-8"
            )
        )
        refused = [
            (int(row["entry_index"]), int(row["file_index"]))
            for row in extra["endzones"]
            if int(row["format"]) == 59
        ]
        self.assertEqual(len(refused), 39)
        for key in refused:
            self.assertNotIn(key, writer._CONTRACTS)

    def test_third_and_long_writer_refuses_and_names_executable(self) -> None:
        from mod_editor.core.errors import ValidationError
        from mod_editor.core.playbook_package_rule_spike import (
            APF_3RD_AND_LONG_PLAY_CHOICE_PROVED,
            ApfThirdAndLongUserLogicRefusal,
            refuse_apf_3rd_and_long_user_logic_writer,
        )

        self.assertFalse(APF_3RD_AND_LONG_PLAY_CHOICE_PROVED)
        with self.assertRaises(ApfThirdAndLongUserLogicRefusal) as caught:
            refuse_apf_3rd_and_long_user_logic_writer()
        self.assertIsInstance(caught.exception, ValidationError)
        self.assertIn("default.xex", str(caught.exception))

    def test_copied_and_studio_built_0a_are_refused_as_source(self) -> None:
        import json
        import tempfile

        from mod_editor.apf_studio.source import (
            COPIED_0A_REFUSAL,
            EXPECTED_0A_SHA256,
            STUDIO_BUILD_SCHEMA,
            STUDIO_BUILD_SIDECAR_NAME,
            STUDIO_BUILT_0A_REFUSAL,
            classify_non_retail_0a,
        )

        digest = "ab" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = classify_non_retail_0a(root, digest)
            self.assertEqual(str(copied), COPIED_0A_REFUSAL)
            (root / STUDIO_BUILD_SIDECAR_NAME).write_text(
                json.dumps(
                    {
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
                ),
                encoding="utf-8",
            )
            studio = classify_non_retail_0a(root, digest)
            self.assertEqual(str(studio), STUDIO_BUILT_0A_REFUSAL)


if __name__ == "__main__":
    unittest.main()
