"""Curve controls use P2's actual installer with fake curves injected via facade."""
from pathlib import Path
import sys
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from mod_editor.apf_studio.launcher import XeniaSettings
from mod_editor.apf_studio.facade import FacadeError
from mod_editor.core.errors import ValidationError


class PatchTests(FacadeFixture):
    def setUp(self):
        super().setUp()
        settings = XeniaSettings(self.root / "settings.json")
        xenia = self.root / "xenia-canary"; xenia.write_bytes(b"synthetic executable"); xenia.chmod(0o755)
        self.facade.launcher.settings = settings
        settings.configure(xenia)

    def test_both_presets_install_status_and_remove_with_consent(self):
        for profile, side in (("base", "offense"), ("tu1", "defense")):
            prepared = self.facade.prepare_playcalling_curve(profile, side)
            path = Path(prepared["patch_path"])
            self.assertFalse(path.exists())
            with self.assertRaises(FacadeError):
                self.facade.install_playcalling_curve(prepared)
            self.assertFalse(path.exists())
            status = self.facade.install_playcalling_curve(prepared, consent=True)
            self.assertTrue(status["installed"]); self.assertTrue(status["enabled"])
            self.assertIn("Changes every book", status["message"])
            config = Path(prepared["config_path"])
            self.assertTrue(tomllib.loads(config.read_text())["Memory"]["apply_patches"])
            unrelated = path.with_name("unrelated.patch.toml"); unrelated.write_bytes(b"leave alone")
            self.assertFalse(self.facade.remove_playcalling_curve()["installed"])
            self.assertEqual(unrelated.read_bytes(), b"leave alone")
            self.assertTrue(tomllib.loads(config.read_text())["Memory"]["apply_patches"])

    def test_presets_match_the_real_core_curve_shapes(self):
        # No retail bytes: build_curve_patch only needs the pinned profile records.
        from mod_editor.apf_studio import playcalling_patches, playcalling_service as service
        from mod_editor.core import apf2k8_playcall_curves_patch as curves
        self.assertEqual(len(service.CURVE_PRESETS["offense"]), 5)
        self.assertEqual(len(service.CURVE_PRESETS["defense"]), 3)
        for side, retail in service.RETAIL_CURVES.items():
            values = service.CURVE_PRESETS[side]
            self.assertEqual(len(values), len(retail))
            self.assertEqual(values[0], 1.0)
            for near, far in zip(values, values[1:]):
                self.assertGreaterEqual(near, far)
            for preset, stock in zip(values[1:], retail[1:]):
                self.assertLessEqual(preset, stock)
        for profile in ("base", "tu1"):
            for side in ("offense", "defense"):
                payload = playcalling_patches.prepare(profile, side, curves=curves)
                document = tomllib.loads(payload.decode())
                self.assertEqual(len(document["patch"][0]["be32"]),
                                 len(service.CURVE_PRESETS[side]))
                self.assertTrue(document["patch"][0]["is_enabled"])
                image, enabled = curves.canonical_curve_payload(payload)
                self.assertTrue(enabled)
                self.assertEqual(image.name, "base" if profile == "base" else "tu_1_1")
                playcalling_patches.validate(payload, curves=curves)

    def test_tampered_curve_and_target_change_refuse_without_writing(self):
        prepared = self.facade.prepare_playcalling_curve("base", "offense")
        broken = dict(prepared, payload=prepared["payload"].replace(b"value = 0", b"value = 1"))
        with self.assertRaises(ValidationError):
            self.facade.install_playcalling_curve(broken, consent=True)
        self.assertFalse(Path(prepared["patch_path"]).exists())
        (self.root / "other.toml").write_bytes(b"[Memory]\napply_patches = false\n")
        self.facade.launcher.settings.configure_patch_config(self.root / "other.toml")
        with self.assertRaisesRegex(FacadeError, "target changed"):
            self.facade.install_playcalling_curve(prepared, consent=True)


if __name__ == "__main__":
    unittest.main()
