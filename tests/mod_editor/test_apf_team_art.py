"""Package resolution, private preview caching and atomic Team Art staging."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from mod_editor.apf_studio import team_art as art
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio.session import ApfSession

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)"


def package(family="logo"):
    names = {"logo": ("logo_l0", "logo_l1"), "endzone": ("endzone_l0", "endzone_l1"),
             "number": ("number_0_color", "number_0_normal")}.get(family, (family + "_color",))
    return art.ArtPackage(family, 836, f"uniform_{family}_12.iff", 12, "Entry 836", (),
                          tuple(art.ArtLayer(name, f"raw:{i}", i, 4, 4, "test", True,
                                             f"uniform:{family}" if family in ("jersey", "shoulder", "pants", "textlogo") else None)
                                for i, name in enumerate(names)))


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first, self.second = self.root / "first.png", self.root / "second.png"
        Image.new("RGBA", (4, 4), "red").save(self.first)
        Image.new("RGBA", (4, 4), "blue").save(self.second)
        self.session = ApfSession.__new__(ApfSession)
        self.session.source = SimpleNamespace(index_0a=Path("read-only-source"))
        self.session.catalog = object()
        self.session._modifications, self.session._audio_annotations, self.session._undo = {}, {}, []

    def test_crest_requires_both_masks_and_resolves_catalog_and_outer(self):
        selected = package()
        self.session.replace_helmet_crest_design = Mock(return_value="staged")
        with patch.object(art, "inventory", return_value=(selected,)):
            with self.assertRaisesRegex(ValueError, "every layer"):
                art.stage_package(self.session, selected, {"logo_l0": self.first})
            self.session.replace_helmet_crest_design.assert_not_called()
            result = art.stage_package(self.session, selected, {"logo_l0": self.first, "logo_l1": self.second})
        self.assertEqual(result, ("staged",))
        self.session.replace_helmet_crest_design.assert_called_once_with(
            self.first, profile=art.RETAIL_CREST_PROFILE, crest_asset_index=12,
            crest_outer_entry_index=836, detail_png=self.second)

    def test_source_change_wrong_size_and_unknown_layers_never_stage(self):
        selected = package()
        self.session.replace_helmet_crest_design = Mock()
        with patch.object(art, "inventory", return_value=()):
            with self.assertRaisesRegex(ValueError, "changed"):
                art.stage_package(self.session, selected, {"logo_l0": self.first})
        with patch.object(art, "inventory", return_value=(selected,)):
            with self.assertRaisesRegex(ValueError, "named layers"):
                art.stage_package(self.session, selected, {"wrong": self.first})
            Image.new("RGBA", (8, 8), "red").save(self.first)
            with self.assertRaisesRegex(ValueError, "4×4"):
                art.stage_package(self.session, selected, {"logo_l0": self.first, "logo_l1": self.second})
        self.session.replace_helmet_crest_design.assert_not_called()

    def test_second_layer_failure_rolls_back_and_success_is_one_undo(self):
        selected = package("endzone")
        def write(key, path):
            mod = Modification(str(key), "field_art_texture", path, "a" * 64, {})
            self.session._set(str(key), mod)
            if key[1] == 1 and fail:
                raise ValueError("second layer rejected")
            return mod
        self.session.replace_field_art = write
        fail = True
        with patch.object(art, "inventory", return_value=(selected,)):
            with self.assertRaisesRegex(ValueError, "second layer"):
                art.stage_package(self.session, selected, dict(zip((l.name for l in selected.layers), (self.first, self.second))))
            self.assertEqual(self.session.modifications, ())
            self.assertEqual(self.session._undo, [])
            fail = False
            art.stage_package(self.session, selected, dict(zip((l.name for l in selected.layers), (self.first, self.second))))
        self.assertEqual(len(self.session.modifications), 2)
        self.assertEqual(len(self.session._undo), 1)
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.modifications, ())

    def test_uniform_families_route_to_writer_ids_and_staged_filter(self):
        for family in ("jersey", "shoulder", "pants", "textlogo"):
            with self.subTest(family=family):
                selected = package(family)
                self.session.replace_uniform = Mock()
                with patch.object(art, "inventory", return_value=(selected,)):
                    art.stage_package(self.session, selected, {family + "_color": self.first})
                self.session.replace_uniform.assert_called_once_with("uniform:" + family, self.first)
                mod = Modification("uniform:" + family, "uniform", self.first, "a" * 64, {})
                self.assertEqual(art.package_modifications(selected, (mod,)), (mod,))

    def test_digits_preflight_existing_and_new_layers_before_staging(self):
        selected = package("number")
        previous = Modification("old", "number_texture", self.second, "b" * 64,
                                {"entry_index": 836, "name": "number_8_color"})
        self.session._modifications["old"] = previous
        self.session.replace_number = Mock()
        with patch.object(art, "inventory", return_value=(selected,)), patch.object(art.number_writer, "build_package_patch") as preflight:
            art.stage_package(self.session, selected, {"number_0_color": self.first})
            preflight.assert_called_once_with(self.session.source.index_0a, 836,
                                              {"number_8_color": self.second, "number_0_color": self.first})
        self.session.replace_number.assert_called_once_with("raw:0", self.first)

    def test_thumbnail_versions_corruption_and_detail_edit_invalidation(self):
        selected = package()
        io = SimpleNamespace(originals_root=self.root / "private", PREVIEW_CACHE_VERSION="decoder-v7",
                             preview_texture=Mock(side_effect=lambda identity: self.first if identity == "raw:0" else self.second))
        first = art.thumbnail(io, selected)
        self.assertIn("decoder-v7", first.parts)
        self.assertIn(art.THUMBNAIL_VERSION, first.parts)
        self.assertEqual(io.preview_texture.call_count, 2)
        self.assertEqual(art.thumbnail(io, selected), first)
        self.assertEqual(io.preview_texture.call_count, 2)
        first.write_bytes(b"broken png")
        art.thumbnail(io, selected)
        self.assertEqual(io.preview_texture.call_count, 4)
        digest = hashlib.sha256(self.second.read_bytes()).hexdigest()
        (self.root / (digest + ".png")).write_bytes(self.second.read_bytes())
        mod = Modification("crest", "helmet_crest_design", self.first, "a" * 64,
                           {"crest_outer_entry_index": 836, "detail_sha256": digest})
        staged = art.thumbnail(io, selected, (mod,))
        self.assertNotEqual(staged, first)
        self.assertEqual(io.preview_texture.call_count, 4)
        with Image.open(staged) as image:
            self.assertEqual(image.size, (208, 128))
            self.assertNotEqual(image.getpixel((52, 64)), image.getpixel((156, 64)))


@unittest.skipUnless((SOURCE / "0A").is_file(), "Retail APF 0A is absent")
class RetailInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.facade = ApfStudioFacade(cache_root=Path(cls.temp.name))
        cls.facade.load_source(SOURCE)
        cls.packages = cls.facade.team_art_packages()

    @classmethod
    def tearDownClass(cls):
        cls.facade.close()
        cls.temp.cleanup()

    def test_every_family_is_reachable_and_has_complete_dimensions_and_writer(self):
        from mod_editor.apf_studio.field_art import build_field_art_inventory
        field = build_field_art_inventory(self.facade.catalog)
        self.assertEqual(len(field.records), 258)
        self.assertEqual(Counter(p.family for p in self.packages),
                         {"logo": 118, "endzone": 118, "textlogo": 206, "jersey": 24, "shoulder": 24, "pants": 24, "number": 24})
        for p in self.packages:
            with self.subTest(package=p.key):
                self.assertTrue(p.writable)
                self.assertTrue(all(l.width > 0 and l.height > 0 for l in p.layers))
                for layer in p.layers:
                    if p.family in ("jersey", "shoulder", "pants", "textlogo"):
                        target = self.facade.session.catalog.uniform(layer.writer_asset_id)
                        self.assertEqual((target.outer_index, target.inner_index), (p.outer_index, layer.inner_index))

    def test_crest_semantics_and_retail_labels_are_proved_selector_mappings(self):
        american = next(p for p in self.packages if p.family == "logo" and p.catalog_index == 30)
        self.assertEqual((american.outer_index, american.package_name, american.label), (1133, "uniform_logo_30.iff", "Americans"))
        self.assertEqual({l.name: l.inner_index for l in american.layers}, {"logo_l0": 1, "logo_l1": 0})
        for family in ("logo", "textlogo"):
            proved = [p for p in self.packages if p.family == family and p.retail_teams]
            self.assertEqual(len(proved), 24)
            self.assertEqual(len(art.labels(family)), 24)
            for p in proved:
                self.assertIn(p.label, p.retail_teams)
        self.assertEqual(len([p for p in self.packages if p.family == "logo" and not p.retail_teams]), 94)

    def test_endzone_confirmed_and_tentative_labels(self):
        names = art.labels("endzone")
        for entry, name in ((190, "Flames"), (205, "Phoenix"), (225, "Cannons"),
                            (268, "Gunslingers"), (334, "Sunspots"), (368, "Owls")):
            self.assertEqual(names[entry], name)
        self.assertEqual(names[48], "Swashbucklers?")
        self.assertEqual(names[683], "bird (matches crest 836)?")

    def test_nonretail_crest_project_build_routes_both_masks_and_linked_cache(self):
        from mod_editor.apf_studio.build import ApfBuildService
        selected = next(p for p in self.packages if p.family == "logo" and not p.retail_teams)
        root = Path(self.temp.name)
        base, detail = root / "base.png", root / "detail.png"
        Image.new("RGBA", (512, 512), (255, 0, 0, 255)).save(base)
        Image.new("RGBA", (512, 512), (0, 0, 255, 255)).save(detail)
        session = self.facade.session
        try:
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.facade.replace_team_art(selected, {"logo_l0": base, "logo_l1": detail}, expected_session=object())
            staged = self.facade.replace_team_art(selected, {"logo_l0": base, "logo_l1": detail}, expected_session=session)
            self.assertEqual(len(staged), 1)
            self.assertNotEqual(staged[0].replacement_sha256, staged[0].metadata["detail_sha256"])
            destination = root / "nonretail-crest.apf2k8mod"
            self.facade.save_project(destination)
            self.assertTrue(self.facade.revert_team_art(selected, expected_session=session))
            self.assertEqual(session.modifications, ())
            self.assertTrue(self.facade.undo())
            self.assertEqual(session.modifications, staged)
            self.facade.revert_all()
            self.facade.load_project(destination)
            session = self.facade.session
            self.assertEqual(session.modifications[0].metadata["detail_sha256"], staged[0].metadata["detail_sha256"])
            # Compile only bounded package/cache entries in memory, never a disc.
            entries, receipt = ApfBuildService(session.source)._compile_helmet_crests(session.modifications)
            self.assertEqual(set(entries), {selected.outer_index, 171, 213})
            self.assertTrue(all(payload for payload in entries.values()))
            self.assertIn("writer_schema", receipt)
        finally:
            self.facade.revert_all()


if __name__ == "__main__":
    unittest.main()
