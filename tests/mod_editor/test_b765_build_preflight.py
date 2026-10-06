"""Recipe and scene refusals precede expensive source indexing and disc builds."""
import json
import struct
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from mod_editor.core import mod_build, modpack_sources as sources
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildService
from test_mod_build_performance import synthetic_disc


def document(edits=None):
    return dict(schema="nfl2k5_visual_mod_project/v1", purpose="Synthetic authoring recipe",
                edits=[] if edits is None else edits)


class RecipePreflightTests(unittest.TestCase):
    def test_duplicate_json_fields_are_refused_instead_of_losing_authored_edits(self):
        for payload in (
            '{"schema":"nfl2k5_visual_mod_project/v1","purpose":"test","edits":[],"edits":[]}',
            '{"schema":"nfl2k5_visual_mod_project/v1","purpose":"test","edits":[{"kind":"p8_texture","asset_id":"p8:17:0","png":"first.png","png":"second.png"}]}',
        ):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as td:
                project = Path(td) / "duplicate.json"
                project.write_text(payload)
                with self.assertRaisesRegex(ValidationError, "repeats the field"):
                    Nfl2k5BuildService().preflight_project(project)

    def test_legacy_source_bundle_format_normalizes_without_changing_custom_edits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            png = root / "my custom art.png"
            png.write_bytes(b"user art")
            authored = document([dict(kind="p8_texture", asset_id="p8:17:0", png=png.name)])
            project = root / "SOFTDRINK-league-project.json"
            # Source capture, extraction and artwork selection in 76.4 wrote
            # this exact noncanonical format; CRLF is a legitimate Windows edit.
            project.write_bytes(json.dumps(authored, indent=1).replace("\n", "\r\n").encode())
            original = project.read_bytes()
            checked = Nfl2k5BuildService().preflight_project(project)
            self.assertEqual(checked["edits"], [dict(authored["edits"][0], png=str(png))])
            self.assertEqual(project.read_bytes(), original)

    def test_real_source_bundle_roundtrip_writes_backend_accepted_custom_recipe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            png = root / "original.png"
            png.write_bytes(b"original user art")
            project = root / "project.json"
            project.write_text(json.dumps(document([dict(kind="p8_texture", asset_id="p8:17:0", png=str(png))])))
            recipe = root / "recipe.json"
            recipe.write_text(json.dumps(dict(preset="softdrink_experimental", overrides={},
                                             freeze=dict(project=dict(path=str(project))))))
            portable, assets = sources.prepare(recipe, root / "capture")
            bundle = root / "sources.2k5sources"
            identity = sources.write_bundle(bundle, portable, assets)
            extracted = sources.extract_bundle(bundle, root / "customize", identity)
            local = sources.materialize(extracted, root / "customize")
            path = Path(local["project"])
            value = json.loads(path.read_bytes())
            self.assertEqual(path.read_bytes(), (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
            art = Path(value["edits"][0]["png"])
            art.write_bytes(b"my replacement")
            checked = Nfl2k5BuildService().preflight_project(path)
            self.assertEqual(checked, value)
            self.assertEqual(art.read_bytes(), b"my replacement")
            self.assertEqual(project.read_text(), json.dumps(document([dict(kind="p8_texture", asset_id="p8:17:0", png=str(png))])))

    def test_invalid_envelope_refuses_before_source_index_or_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            project = root / "wrong.json"
            project.write_text('{"schema": "wrong", "edits": []}')
            plan = mod_build.BuildPlan(str(root / "unread.iso"), str(root / "output.iso"))
            with mock.patch("mod_editor.core.nfl2k5_source_cache.Nfl2k5SourceCache.index",
                            side_effect=AssertionError("source indexed")), \
                    mock.patch.object(Nfl2k5BuildService, "build", side_effect=AssertionError("textures built")), \
                    self.assertRaisesRegex(ValidationError, "Select SOFTDRINK-league-project.json"):
                sources.build_project(plan, project, None)
            self.assertFalse(Path(plan.target).exists())

    def test_invalid_edit_refuses_before_source_index(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "wrong-edit.json"
            project.write_text(json.dumps(document([dict(kind="p8_texture", asset_id="p8:17:0")]), indent=1))
            with mock.patch("mod_editor.core.nfl2k5_source_cache.Nfl2k5SourceCache.index",
                            side_effect=AssertionError("source indexed")), \
                    self.assertRaisesRegex(ValidationError, "before building"):
                sources.build_project(mod_build.BuildPlan("unread.iso", "out.iso"), project, None)

    def test_settings_only_source_recipe_uses_the_plan_builder(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "empty.json"
            project.write_text(json.dumps(document(), indent=1))
            plan = mod_build.BuildPlan("source.iso", "output.iso", throw=True)
            with mock.patch("mod_editor.core.nfl2k5_source_cache.Nfl2k5SourceCache.index",
                            side_effect=AssertionError("unused artwork cache indexed")), \
                    mock.patch.object(mod_build, "build", return_value={"settings_only": True}) as build:
                self.assertEqual(sources.build_project(plan, project, None), {"settings_only": True})
            self.assertIs(build.call_args.args[0], plan)

    def test_settings_only_open_session_builds_a_real_synthetic_disc(self):
        class Session:
            def write_canonical_project(self, destination):
                destination.write_text(json.dumps(document(), indent=1))
                return destination
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            source, target = root / "source.iso", root / "built.iso"
            synthetic_disc(source)
            service = Nfl2k5BuildService()
            with mock.patch.object(service, "build", side_effect=AssertionError("empty texture backend called")), \
                    mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
                receipt = mod_build.build_with_project(mod_build.BuildPlan(str(source), str(target)),
                                                      service, None, Session())
            self.assertTrue(target.is_file())
            self.assertEqual(receipt["target"], str(target))


class BoardPreflightTests(unittest.TestCase):
    def test_fast_board_recognition_validates_scene_without_decoding_preview_pixels(self):
        from mod_editor.core import nfl2k5_board_kit as boards, nfl2k5_scne_builder as scene
        tx, inventory, *_ = boards._ml()._tools()
        shape = bytearray(256)
        struct.pack_into("<I", shape, 0x44, 2)
        texture = bytearray(32)
        struct.pack_into("<I", texture, 0x0C, (2 << 4) | (11 << 8) | (1 << 16) | (2 << 20) | (2 << 24))
        authored = scene.Scene("stadium", [scene.Texture(texture, bytes(16), bytes(1024))], [], [],
                               [scene.Shape(shape, "bk_test", [], [], [None] * 8)], [])
        decoded, system, video = scene.serialize(authored)
        field, field_system, field_video = scene.serialize(scene.Scene("field", [], [], [], [], []))
        field_chunk = tx.HEADER.pack(b"SCNE", len(field), field_system, field_video, 0, len(field), 0, 0) + field
        def bundle(payload, prefix=field_chunk):
            return prefix + tx.HEADER.pack(b"SCNE", len(payload), system, video, 0, len(payload), 0, 0) + payload
        data = bundle(decoded)
        pin = {"offset": len(field_chunk), "length": len(data) - len(field_chunk)}
        self.assertEqual({shape.name for shape in scene.parse(decoded, system).shapes}, {"bk_test"})
        with mock.patch.object(boards, "_pin", return_value=pin), \
                mock.patch.object(boards, "spec", return_value={"boards": [{"name": "bk_test"}]}), \
                mock.patch.object(inventory, "texture_to_rgba", side_effect=AssertionError("preview pixels decoded")):
            self.assertTrue(boards._renovated(data, "s13dd.iff"))
            self.assertFalse(boards._renovated(bundle(decoded, b""), "s13dd.iff"))
            corrupt_field = bytearray(field_chunk)
            struct.pack_into("<i", corrupt_field, tx.HEADER.size + 0x14, 0)
            self.assertFalse(boards._renovated(bundle(decoded, corrupt_field), "s13dd.iff"))
            city, city_system, city_video = scene.serialize(scene.Scene("cityscape", [], [], [], [], []))
            city_chunk = tx.HEADER.pack(b"SCNE", len(city), city_system, city_video, 0, len(city), 0, 0) + city
            self.assertTrue(boards._renovated(data + city_chunk, "s13dd.iff"))
            corrupt_city = bytearray(city_chunk)
            struct.pack_into("<i", corrupt_city, tx.HEADER.size + 0x14, 0)
            self.assertFalse(boards._renovated(data + corrupt_city, "s13dd.iff"))
            corrupt = bytearray(decoded)
            struct.pack_into("<i", corrupt, 0x14, 0)
            self.assertFalse(boards._renovated(bundle(corrupt), "s13dd.iff"))
            corrupt = bytearray(decoded)
            descriptor = scene._rel(corrupt, 0x14)
            shape_at = scene._rel(corrupt, descriptor + 0x30)
            struct.pack_into("<H", corrupt, shape_at + 0xC4, 2)
            struct.pack_into("<i", corrupt, shape_at + 0xD4, len(decoded) + 4097)
            self.assertFalse(boards._renovated(bundle(corrupt), "s13dd.iff"))
        with mock.patch.object(boards, "_pin", return_value={"offset": 1, "length": len(data)}):
            self.assertFalse(boards._renovated(data, "s13dd.iff"))

    def test_foreign_source_refuses_before_recipe_plan_and_texture_work(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            source, target = root / "source.iso", root / "out.iso"
            synthetic_disc(source)
            boards = mock.Mock()
            boards.check_request.side_effect = ValueError("Choose your unmodified USA retail image, or turn off Modern stadium boards")
            with mock.patch.object(mod_build, "_core_module", return_value=boards), \
                    mock.patch.object(mod_build, "preflight_plan", side_effect=AssertionError("expensive plan work started")), \
                    self.assertRaisesRegex(ValueError, "unmodified USA retail image"):
                mod_build.build(mod_build.BuildPlan(str(source), str(target), modern_board_kit=True),
                                _project_builder=mock.Mock(side_effect=AssertionError("texture work started")))
            boards.check_request.assert_called_once_with(source)
            self.assertFalse(target.exists())
            self.assertFalse(list(root.glob(".studio-build-*")))

    def test_project_scene_conflict_reports_the_bundle_and_solution(self):
        from mod_editor.core import nfl2k5_board_kit as boards
        outer = boards._venue_pins("s13")["s13dd.iff"]["outer"]
        value = document([dict(kind="stadium_texture", target=f"nfl2k5.stadium.o{outer:04}.c0005.scene0000.texture0002", png="art.png")])
        with self.assertRaisesRegex(ValueError, r"s13dd.iff.*Turn off Modern stadium boards"):
            mod_build.preflight_project_options(mod_build.BuildPlan("source", "out", modern_board_kit=True), value)
        mod_build.preflight_project_options(mod_build.BuildPlan("source", "out"), value)

    def test_unrelated_standalone_textures_do_not_conflict_with_boards(self):
        value = document([dict(kind="p8_texture", asset_id="p8:3149:0", png="art.png")])
        mod_build.preflight_project_options(mod_build.BuildPlan("source", "out", modern_board_kit=True), value)

    def test_foreign_scene_message_lists_files_and_keeps_recognized_venue_art(self):
        from mod_editor.core import nfl2k5_board_kit as boards
        with mock.patch.object(boards, "bundle_states", return_value={"s13dd.iff": "foreign", "s13dr.iff": "retail"}), \
                self.assertRaisesRegex(ValueError, r"s13dd.iff.*unmodified USA retail image.*turn off Modern stadium boards"):
            boards.check_request("source.iso")
        with mock.patch.object(boards, "bundle_states", return_value={"s13dd.iff": "venues", "s13dr.iff": "retail"}):
            self.assertEqual(boards.check_request("source.iso"), {"state": "retail"})

    def test_renovated_scene_takes_precedence_over_matching_venue_receipt(self):
        from mod_editor.core import nfl2k5_board_kit as boards
        data = b"repainted renovated scene"
        archive = mock.Mock()
        archive.read.return_value = data
        pin = {"size": len(data), "offset": 0, "length": len(data),
               "model_sha256": "model", "retail_sha256": "retail"}
        receipt = {"bundles": {"s13dd.iff": {"applied_sha256": boards.sha(data)}}}
        with mock.patch.object(boards, "_pin", return_value=pin), \
                mock.patch.object(boards, "_venue_pins", return_value={"s13dd.iff": {}}), \
                mock.patch.object(boards, "_entry", return_value=mock.Mock(size=len(data), virtual_offset=0)), \
                mock.patch.object(boards, "_renovated", return_value=True):
            self.assertEqual(boards.bundle_state(archive, "s13dd.iff", receipt), "applied")


if __name__ == "__main__":
    unittest.main()
