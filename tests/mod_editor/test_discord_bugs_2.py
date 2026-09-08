"""Bounded editor regressions. No emulator, display, disc or pack copies."""
from contextlib import nullcontext
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from PIL import Image
from mod_editor.core.errors import ValidationError
from mod_editor.core import nfl2k5_digit_sheet as digits
from mod_editor.apf_studio.session import ApfSession, SessionError
from mod_editor.apf_studio import build as apfbuild
from mod_editor.apf_studio.helmet_crest_design import RETAIL_CREST_PROFILE
from tests.mod_editor.test_apf_build_raw_span_overlays import _source, _complete_tree, _archive


@dataclass(frozen=True)
class Target:
    digit: int
    family: str = "arm"
    set_selector: str = "28H0"
    width: int = 16
    height: int = 16

    @property
    def asset_id(self):
        return f"28H0:arm_digit:{self.digit}"


class DigitLayoutTests(unittest.TestCase):
    def test_explicit_grids_preserve_order_alpha_and_source(self):
        for columns, rows, layout in ((5, 2, "grid_5x2"), (2, 5, "grid_2x5"),
                                      (10, 1, "horizontal"), (1, 10, "vertical")):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sheet.png"
                image = Image.new("RGBA", (columns * 16, rows * 16))
                for d in range(10):
                    x, y = d % columns * 16, d // columns * 16
                    image.paste((d * 20, 30, 40, d * 20), (x, y, x + 16, y + 16))
                image.save(path)
                before = path.read_bytes()
                result = digits.split_digit_sheet(path, map(Target, range(10)), orientation=layout)
                self.assertEqual(path.read_bytes(), before)
                for d, row in enumerate(result):
                    with Image.open(BytesIO(row.png)) as decoded:
                        self.assertEqual(decoded.size, (16, 16))
                        self.assertEqual(decoded.getpixel((8, 8)), (d * 20, 30, 40, d * 20))

    def test_ambiguous_and_unequal_cells_refuse_with_exact_reason(self):
        for size, reason in (((80, 32), "layout"), ((161, 16), "divisible")):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sheet.png"
                Image.new("RGBA", size).save(path)
                with self.assertRaisesRegex(ValidationError, reason):
                    digits.split_digit_sheet(path, map(Target, range(10)))


class ApfCompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        game = self.root / "game"
        game.mkdir()
        self.source = _source(game)
        self.tree = _complete_tree(game)
        self.session = ApfSession(self.source, Mock(), cache_root=self.root / "cache")
        self.addCleanup(self.session.close)
        self.png = self.root / "crest.png"
        Image.new("RGBA", (512, 512), (255, 0, 0, 255)).save(self.png)

    def crest(self, slot):
        with patch.object(self.session, "_require_helmet_crest_slot"):
            return self.session.replace_helmet_crest_design(self.png, profile=RETAIL_CREST_PROFILE,
                crest_asset_index=slot, crest_outer_entry_index=36 + slot)

    def test_crests_for_two_teams_survive_replace_undo_and_project(self):
        self.crest(0)
        self.crest(1)
        self.assertEqual(self.session.modified_count, 2)
        self.crest(0)
        self.assertEqual(self.session.modified_count, 2)
        self.assertEqual({m.metadata["crest_asset_index"] for m in self.session.modifications}, {0, 1})
        self.assertTrue(self.session.undo())
        from mod_editor.apf_studio import project
        for m in self.session.modifications:
            self.assertEqual(project._validated_metadata(m.asset_id, m.kind, m.metadata), m.metadata)

    def test_field_art_is_session_work_and_two_layers_compile_together(self):
        import apf_field_art_patch as writer
        contracts = [c for c in writer._CONTRACTS.values() if c.entry_index == 659][:2]
        self.assertEqual(len(contracts), 2)
        for c in contracts:
            path = self.root / f"field-{c.file_index}.png"
            Image.new("RGBA", (c.width, c.height), (10, 20, 30, 255)).save(path)
            self.session.replace_field_art((c.entry_index, c.file_index), path)
        self.assertEqual(self.session.modified_count, 2)
        mods = self.session.modifications
        with patch.object(writer, "build_field_art_patch_many", return_value=SimpleNamespace(
                entry_bytes=b"synthetic", manifest={"schema": writer.SCHEMA})) as compile_many:
            entries = apfbuild.ApfBuildService(self.source)._compile_field_art(mods)
        self.assertEqual(entries[0][0:2], (659, b"synthetic"))
        self.assertEqual(len(compile_many.call_args.args[2]), 2)
        self.assertEqual(set(entries[0][2]["asset_ids"]), {m.asset_id for m in mods})
        from mod_editor.apf_studio import project
        for m in mods:
            self.assertEqual(project._validated_metadata(m.asset_id, m.kind, m.metadata), m.metadata)

    def test_crests_and_field_art_round_trip_real_project_archive(self):
        import apf_field_art_patch as writer
        self.crest(0)
        self.crest(1)
        c = next(iter(writer._CONTRACTS.values()))
        png = self.root / "field.png"
        Image.new("RGBA", (c.width, c.height), (80, 40, 20, 255)).save(png)
        self.session.replace_field_art((c.entry_index, c.file_index), png)
        expected = [(m.asset_id, m.replacement_sha256, m.metadata) for m in self.session.modifications]
        project = self.root / "movie-teams.apf2k8mod"
        self.session.save_project(project)
        self.session.revert_all()
        with patch.object(self.session, "_require_helmet_crest_slot"):
            self.session.load_project(project)
        self.assertEqual([(m.asset_id, m.replacement_sha256, m.metadata) for m in self.session.modifications], expected)

    def test_two_crests_compile_packages_and_shared_cache_once(self):
        self.crest(0)
        self.crest(1)
        service = apfbuild.ApfBuildService(self.source)
        with patch.object(apfbuild.apf_team_crests, "crest_slots", return_value=[
                SimpleNamespace(asset_index=i, outer_entry_index=36+i) for i in range(2)]), \
             patch.object(apfbuild.apf_logo_patch, "build_patch", side_effect=lambda *a, **kw:
                SimpleNamespace(entry_bytes=bytes([kw["entry_index"]]), manifest={"schema": "package"})) as packages, \
             patch.object(apfbuild.apf_logocache_patch, "build_cache_patch_many", return_value=
                SimpleNamespace(directory_bytes=b"dir", payload_bytes=b"cache", manifest={"schema": "cache"})) as cache:
            entries, row = service._compile_helmet_crests(self.session.modifications)
        self.assertEqual(packages.call_count, 2)
        cache.assert_called_once()
        self.assertEqual({s.catalog_index for s in cache.call_args.args[1]}, {0, 1})
        self.assertEqual((entries[36], entries[37]), (b"$", b"%"))
        self.assertEqual(len(row["asset_ids"]), 2)

    def test_full_shell_plus_second_team_refuses_without_losing_first(self):
        from mod_editor.apf_studio.helmet_crest_design import FULL_SHELL_CREST_PROFILE
        self.crest(0)
        before = self.session.modifications
        with patch.object(self.session, "_require_helmet_crest_slot"):
            with self.assertRaisesRegex(SessionError, "Multiple team crests"):
                self.session.replace_helmet_crest_design(self.png, profile=FULL_SHELL_CREST_PROFILE,
                    crest_asset_index=1, crest_outer_entry_index=37)
        self.assertEqual(self.session.modifications, before)

    def test_build_publishes_crest_and_field_layers_in_one_copy(self):
        self.crest(0)
        import apf_field_art_patch as writer
        for c in [c for c in writer._CONTRACTS.values() if c.entry_index == 659][:2]:
            png = self.root / f"field-{c.file_index}.png"
            Image.new("RGBA", (c.width, c.height), (80, 40, 20, 255)).save(png)
            self.session.replace_field_art((c.entry_index, c.file_index), png)
        crest = [m for m in self.session.modifications if m.kind == "helmet_crest_design"]
        fields = [m for m in self.session.modifications if m.kind == "field_art_texture"]
        before = self.source.index_0a.read_bytes()
        service = apfbuild.ApfBuildService(self.source)
        with patch.object(apfbuild, "EXPECTED_TREE", self.tree), \
             patch.object(apfbuild, "EXPECTED_0A_SHA256", self.tree["0A"][1]), \
             patch.object(apfbuild.apf_outer, "parse_archive", side_effect=_archive), \
             patch.object(apfbuild.apf_inner, "parse_iff", return_value=SimpleNamespace(warnings=[])), \
             patch.object(service, "_compile_helmet_crests", return_value=({0: b"C" * 0x1800},
                {"asset_ids": [m.asset_id for m in crest], "kind": "helmet_crest_design", "writer_schema": "test"})), \
             patch.object(service, "_compile_field_art", return_value=[(1, b"F" * 0x1000,
                {"asset_ids": [m.asset_id for m in fields], "kind": "field_art_texture", "writer_schema": "test"})]) as compile_fields:
            receipt = service.build(self.session.modifications, self.root / "output")
        self.assertEqual(len(compile_fields.call_args.args[0]), 2)
        expected = bytearray(before)
        expected[:0x1800] = b"C" * 0x1800
        expected[0x1800:0x2800] = b"F" * 0x1000
        self.assertEqual(receipt.output_0a.read_bytes(), expected)
        self.assertEqual(self.source.index_0a.read_bytes(), before)
        self.assertEqual(len(receipt.modified_assets), 3)


class ImageUseTests(unittest.TestCase):
    def test_other_process_reader_refuses_copy_and_launch_probe_without_changes(self):
        from mod_editor.core import image_use
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source, target = root / "source.iso", root / "target.iso"
            source.write_bytes(b"new disc bytes")
            target.write_bytes(b"old disc bytes")
            child = subprocess.Popen([sys.executable, "-c",
                "import sys; f=open(sys.argv[1],'rb'); print('ready',flush=True); sys.stdin.read()",
                str(target)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                for operation in (lambda: image_use.assert_image_available(target),
                                  lambda: image_use.copy_image(source, target, overwrite=True)):
                    with self.assertRaisesRegex(ValidationError, "Eject.*close"):
                        operation()
                from mod_editor.core.nfl2k5_build_service import _new_output_path
                with self.assertRaisesRegex(ValidationError, "Eject.*close"):
                    _new_output_path(target)
                from mod_editor.studio.facade import Nfl2k5StudioFacade
                launcher = Mock()
                host = SimpleNamespace(xemu_command=['xemu'], _lock=nullcontext(),
                    _last_build=SimpleNamespace(output_xiso=target), _process_launcher=launcher)
                with self.assertRaisesRegex(ValidationError, "Eject.*close"):
                    Nfl2k5StudioFacade.launch_xemu(host, Mock())
                launcher.assert_not_called()
                self.assertEqual(target.read_bytes(), b"old disc bytes")
            finally:
                child.communicate(timeout=10)
            image_use.copy_image(source, target, overwrite=True)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertEqual(list(root.glob(".*.copying")), [])

    def test_copy_never_replaces_source_or_existing_without_permission(self):
        from mod_editor.core import image_use
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.iso"
            source.write_bytes(b"retail")
            with self.assertRaises(ValidationError):
                image_use.copy_image(source, source, overwrite=True)
            target = Path(tmp) / "target.iso"
            target.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                image_use.copy_image(source, target)
            self.assertEqual(target.read_bytes(), b"keep")

    def test_changed_destination_and_symlink_refuse_without_publication(self):
        from mod_editor.core import image_use
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target, stage = root / 'target.iso', root / 'stage.iso'
            target.write_bytes(b'old'); stage.write_bytes(b'new')
            previous = image_use.check_image_destination(target, overwrite=True)
            target.write_bytes(b'changed by someone else')
            with self.assertRaisesRegex(ValidationError, 'changed during copying'):
                image_use.publish_image(stage, target, previous)
            self.assertEqual(target.read_bytes(), b'changed by someone else')
            link = root / 'link.iso'
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f'Symlink creation unavailable: {exc}')
            with self.assertRaisesRegex(ValidationError, 'symbolic link'):
                image_use.copy_image(stage, link, overwrite=True)
            self.assertEqual(target.read_bytes(), b'changed by someone else')


if __name__ == "__main__":
    unittest.main()
