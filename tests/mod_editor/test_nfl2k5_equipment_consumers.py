"""Equipment imports reach every uniform package the game actually samples.

maumau78 (beta 63): an imported Style 1 shoe showed on the Edit Player preview
model but players wore the stock shoe in a game.  The player texture binding
table in default.xbe (0x004EEAF8) marks ``shoes01``/``04``/``02``/``03`` (and
gloves 1-4, elbow pads 1-4, long sleeves 1-2, wristbands 1-2) as *global*
lookups: ``FUN_0008E580`` skips the HOME/AWAY context and ``FUN_000449E0``
walks the loaded contexts newest-first, so every player wears the copy inside
the most recently loaded uniform package -- the away team's package in a game
(``FUN_00062BE0`` loads HOME, then AWAY) and the viewed team's ``h0``/``a0``
package on the front-end Edit Player screen (``FUN_00091940``).  Staging one
package therefore only ever changed the preview.

These tests pin that chain on the private retail executable (skipped when it
is absent), prove the catalog-only consumer resolution, and reproduce the
facade behaviour on a bounded synthetic multi-package archive.
"""

from __future__ import annotations

from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_nfl2k5_equipment_texture_chain import Fixture, artwork, digest
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_equipment_import import (
    ALL_TEAMS, SELECTED_PACKAGE, GLOBAL_RULE, equipment_import_scope,
    revert_equipment_import, stage_equipment_import,
)
from mod_editor.core.nfl2k5_equipment_import_intent import OWN_TEXTURE, PALETTE_ONLY, import_mode
from mod_editor.studio.session import StudioSession
from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import decode_chunk, encode_rgba_png, parse_chunks, texture_to_rgba


XBE = Path(os.environ.get(
    "NFL2K5_RETAIL_XBE",
    "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe",
))
INDEX = Path(os.environ.get(
    "NFL2K5_RETAIL_INDEX",
    "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
))
RETAIL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
# (virtual address, size, SHA-256) of the retail bytes each claim rests on.
XBE_EVIDENCE = {
    "binding_table_0x4EEAF8": (0x004EEAF8, 768, "741711f3dbd900dad93b25e7839f8c194485dd4665e915644367a620d34fb95d"),
    "shoe_style_table_0x4EF7C0": (0x004EF7C0, 56, "ed74aebdaf8e580db1e264024b12830f2e746dbb152ff74502caa856942e8994"),
    "FUN_0008E5C0_mud_name": (0x0008E5C0, 92, "b847eeff99ac1aad29cec8c7f8460743393c5da7e8693f4fc0ac11ad83165bf7"),
    "FUN_0008E580_context_first_or_global": (0x0008E580, 49, "1e196cf2a1d8dbbc1635eafe652992ca0633903e0f1b4014dce2cd6cbc9673a9"),
    "FUN_0008E620_cache_fill": (0x0008E620, 368, "2b0e4ffdd9d7865789b9acac0cb0cbf6e26ac1f733d29aab5ecca8ab6e6e70e6"),
    "FUN_0008EF20_shoe_material_bind": (0x0008EF20, 115, "e40fd870c9059813b0749448ef0b22a9b4beed5d78358ccb58feed1388931dfe"),
    "FUN_0008EFA0_shoe_style_tail": (0x0008F74A, 154, "d895ee7cd0816d619a66bb3ed109d92c5ea765ef4cad9590a6b68da238405728"),
    "FUN_00062BE0_home_then_away": (0x00063261, 67, "d9146ccfa6ef00e68d81a2bf10930a7864f3f1d8c65c51c94b7b68dc205ca541"),
    "FUN_00043DB0_context_head_insert": (0x00043DB0, 82, "ff3dc1dcdc4aa3695e767a387b4c5bb46c034504d827261f2a54f5d5a788d3f8"),
    "FUN_000449E0_named_or_global_lookup": (0x000449E0, 104, "710fd5ba9fd2a147042dd4c5f133cc2a8d36dcdc10b47417d17ec65df9b46191"),
    "FUN_00091940_front_end_preview_package": (0x00091940, 248, "080729cfe555f976dfcabd18806186bb89a7970f6c5c4516a711daad3b59c205"),
}
# (virtual address, raw size, raw offset) for the retail .text and .rdata sections.
XBE_SECTIONS = ((0x00011000, 0x0040F114, 0x00001000), (0x004E3AE0, 0x00585E88, 0x004D9000),
                (0x00E60320, 0x0005D3A0, 0x00AEF000))


def _xbe_bytes(image: bytes, address: int, size: int) -> bytes:
    for base, raw_size, raw in XBE_SECTIONS:
        if base <= address and address + size <= base + raw_size:
            start = raw + address - base
            return image[start:start + size]
    raise AssertionError(f"0x{address:08x} is outside the pinned sections")


def _utf16(image: bytes, address: int) -> str:
    chars = []
    for base, raw_size, raw in XBE_SECTIONS:
        if base <= address < base + raw_size:
            cursor = raw + address - base
            while image[cursor:cursor + 2] != b"\0\0":
                chars.append(image[cursor:cursor + 2])
                cursor += 2
            return b"".join(chars).decode("utf-16le")
    raise AssertionError(f"0x{address:08x} is outside the pinned sections")


@unittest.skipUnless(XBE.is_file(), "Private retail default.xbe is absent")
class RetailBindingTableTests(unittest.TestCase):
    """The consumer chain pinned on retail bytes; no emulator, no disc build."""

    @classmethod
    def setUpClass(cls):
        if not 0 < XBE.stat().st_size <= 16 * 1024 * 1024:
            raise unittest.SkipTest("Retail executable has an unexpected size")
        cls.image = XBE.read_bytes()
        if hashlib.sha256(cls.image).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest("Not the pinned retail default.xbe")

    def test_every_evidence_range_is_the_pinned_retail_bytes(self):
        for label, (address, size, expected) in XBE_EVIDENCE.items():
            with self.subTest(label=label):
                self.assertEqual(hashlib.sha256(_xbe_bytes(self.image, address, size)).hexdigest(),
                                 expected)

    def test_binding_table_rows_match_the_classification(self):
        rows = {}
        for index in range(96):
            pointer, context_first = struct.unpack_from(
                "<II", self.image, 0x004D9000 + (0x004EEAF8 + index * 8) - 0x004E3AE0)
            rows[index] = (_utf16(self.image, pointer), context_first)
        for name, index in writer.BINDING_TABLE_ROWS.items():
            with self.subTest(name=name):
                self.assertEqual(rows[index][0], name)
                self.assertEqual(rows[index][1],
                                 0 if name in writer.GLOBAL_LOOKUP_NAMES else 1)
        # Every catalog name the studio can import resolves through one row.
        by_id, _groups = writer.load_targets()
        names = {target.name.removesuffix("_mud") for target in by_id.values()}
        self.assertEqual(names, set(writer.BINDING_TABLE_ROWS))
        self.assertEqual(names, writer.GLOBAL_LOOKUP_NAMES | writer.CONTEXT_FIRST_NAMES)
        # The shoe style selector (player byte +0x0C, 3 bits per shoe) picks
        # these rows; row 90 is the global-pack shoes_taped, not a package.
        table = [struct.unpack_from("<II", self.image, 0x004D9000 + (0x004EF7C0 + i * 8) - 0x004E3AE0)
                 for i in range(7)]
        self.assertEqual([entry[0] for entry in table], [84, 85, 86, 87, 88, 89, 90])
        self.assertEqual([rows[entry[0]][0] for entry in table],
                         ["shoes01", "shoes04", "shoes09", "shoes02", "shoes03", "shoes10", "shoes_taped"])
        self.assertEqual(writer.SHOE_STYLE_NAMES, ("shoes01", "shoes04", "shoes09", "shoes02", "shoes03", "shoes10"))

    def test_decision_and_load_order_instructions(self):
        # FUN_0008E580: TEST EAX,EAX / JZ global -> flag 0 never consults HOME/AWAY.
        self.assertEqual(_xbe_bytes(self.image, 0x0008E580, 4), bytes.fromhex("85c0741a"))
        # Global lookup: XOR ECX,ECX before JMP FUN_000449E0.
        self.assertEqual(_xbe_bytes(self.image, 0x0008E5A7, 7), bytes.fromhex("33c9e93264fbff"))
        # FUN_00043DB0 makes the new context the list head that FUN_000449E0 walks first.
        self.assertEqual(_xbe_bytes(self.image, 0x00043DE0, 6), bytes.fromhex("8935" + struct.pack("<I", 0xB09578).hex()))
        # In a game HOME (0x0006327A) is created before AWAY (0x00063298).
        self.assertEqual(_xbe_bytes(self.image, 0x00063275, 5), b"\xb9" + struct.pack("<I", 0xE6162C))
        self.assertEqual(_utf16(self.image, 0xE6162C), "HOME")
        self.assertEqual(_xbe_bytes(self.image, 0x00063293, 5), b"\xb9" + struct.pack("<I", 0xE61638))
        self.assertEqual(_utf16(self.image, 0xE61638), "AWAY")
        # The front-end preview loads exactly one package: <code>h0.iff or <code>a0.iff.
        self.assertEqual(_utf16(self.image, 0xE65750), "%sh0.iff")
        self.assertEqual(_utf16(self.image, 0xE65728), "%sa0.iff")


class ConsumerResolutionTests(unittest.TestCase):
    """Catalog-only: which package copies the game can bind for one name."""

    @classmethod
    def setUpClass(cls):
        cls.by_id, cls.groups = writer.load_targets()

    def test_global_style_reaches_every_away_and_home_current_package(self):
        target = self.by_id["tset:3850:8:0:shoes01"]  # Tennessee 28H0
        consumers = writer.consumer_targets(target, self.by_id)
        selectors = {item.set_selector for item in consumers}
        self.assertIn("28H0", selectors)
        away = {item.set_selector for item in self.by_id.values() if item.set_selector[2] == "A"}
        home_current = {item.set_selector for item in self.by_id.values()
                        if item.set_selector[2] == "H" and item.set_selector[3:] == "0"}
        self.assertEqual(selectors, away | home_current)
        self.assertEqual((len(away), len(home_current), len(consumers)), (317, 85, 402))
        self.assertTrue(all(item.name == "shoes01" and item.chunk_index == 8
                            and item.reference_index == 0 for item in consumers))
        self.assertEqual([item.outer_index for item in consumers],
                         sorted(item.outer_index for item in consumers))
        # A never-sampled alternate home package is still staged for its own preview.
        alternate = next(item for item in self.by_id.values()
                         if item.name == "shoes01" and item.set_selector[2] == "H"
                         and item.set_selector[3:] != "0")
        with_alternate = writer.consumer_targets(alternate, self.by_id)
        self.assertEqual(len(with_alternate), 403)
        self.assertIn(alternate.asset_id, {item.asset_id for item in with_alternate})

    def test_mud_and_other_global_families_follow_the_same_row(self):
        for asset_id in ("tset:3850:8:1:shoes01_mud", "tset:3850:9:0:shoes02", "tset:3850:6:2:glove03",
                         "tset:3850:5:0:elbowpad01", "tset:3850:7:3:longsleeve02_mud",
                         "tset:3850:10:1:wristband02"):
            with self.subTest(asset_id=asset_id):
                target = self.by_id[asset_id]
                self.assertEqual(writer.in_game_lookup(target.name), "global")
                consumers = writer.consumer_targets(target, self.by_id)
                self.assertEqual(len(consumers), 402)
                self.assertEqual({(item.chunk_index, item.reference_index, item.name) for item in consumers},
                                 {(target.chunk_index, target.reference_index, target.name)})

    def test_team_specific_names_stay_inside_the_selected_package(self):
        for asset_id in ("tset:3850:8:4:shoes09", "tset:3850:9:5:shoes10_mud", "tset:3850:6:4:glove05",
                         "tset:3850:5:8:elbowpad05", "tset:3850:7:4:longsleeve03",
                         "tset:3850:10:2:wristband09", "tset:3850:4:0:socks00"):
            with self.subTest(asset_id=asset_id):
                target = self.by_id[asset_id]
                self.assertEqual(writer.in_game_lookup(target.name), "context_first")
                self.assertEqual(writer.consumer_targets(target, self.by_id), (target,))

    def test_scope_offers_only_all_teams_for_global_rows_including_mud(self):
        for target in self.by_id.values():
            if target.outer_index != 3850:
                continue
            choices, rule = equipment_import_scope(target.asset_id)
            if writer.in_game_lookup(target.name) == "global":
                self.assertEqual(choices, ((ALL_TEAMS, "All teams"),))
                self.assertEqual(rule, GLOBAL_RULE)
            else:
                self.assertEqual(choices, ((SELECTED_PACKAGE, "Selected uniform package"),))


class _MultiPackageArchive:
    """Four synthetic uniform packages sharing one retail-shaped TSET span."""

    SELECTORS = ("10H0", "10A0", "11A1", "11H2")

    def __init__(self, root, names=("shoes01", "shoes09", "shoes02")):
        self.fixture = Fixture(root, names=names)
        self.rows = {}
        for outer, selector in enumerate(self.SELECTORS):
            self.rows[outer] = tuple(
                writer.EquipmentTarget(outer, selector, row.chunk_index, row.reference_index, row.name,
                                       row.width, row.height, row.pixel_offset, row.palette_offset,
                                       row.packed_format, row.packed_size, row.descriptor_flags,
                                       row.base_pixel_sha256, row.palette_bgra_sha256)
                for row in self.fixture.rows)
        self.by_id = {row.asset_id: row for rows in self.rows.values() for row in rows}
        self.groups = {(outer, self.fixture.chunk.index): rows for outer, rows in self.rows.items()}

    def context(self):
        stack = ExitStack()
        span = self.fixture.span
        segment = SimpleNamespace(pack_ordinal=0, pack_offset=128, size=len(span))
        archive = SimpleNamespace(
            entries=[SimpleNamespace(size=len(span), segments=[segment]) for _ in self.SELECTORS],
            packs=[SimpleNamespace(name="pack", path=self.fixture.pack, size=len(span))])
        stack.enter_context(patch.object(writer, "load_targets", return_value=(self.by_id, self.groups)))
        stack.enter_context(patch.object(writer, "parse_archive", return_value=archive))
        stack.enter_context(patch.object(writer, "read_entry_bytes", side_effect=lambda *args: span))
        actual_parse = writer.parse_chunks
        stack.enter_context(patch.object(writer, "parse_chunks", side_effect=lambda data, **kw: (
            [self.fixture.chunk] if kw.get("allow_trailing") else actual_parse(data, **kw))))
        stack.enter_context(patch.object(writer, "_chain_pins", return_value={
            key: digest(span) for key in self.groups}))
        return stack


class ConsumerFanoutSessionTests(unittest.TestCase):
    """The facade stages every sampled copy as one undoable transaction."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="equipment-consumers-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = _MultiPackageArchive(self.root)
        self.cache = SimpleNamespace(root=self.root / "cache", pack0=self.root / "0",
                                     source=SimpleNamespace(sha256="a" * 64))
        fixture = self.archive.fixture
        textures, _ = writer._validate_layout(fixture.decoded, fixture.chunk, fixture.rows)
        originals = {row.reference_index: texture_to_rgba(fixture.decoded, fixture.chunk, textures[row.reference_index])
                     for row in fixture.rows}
        self.assets = {}
        for asset_id, row in self.archive.by_id.items():
            self.assets[asset_id] = SimpleNamespace(
                asset_id=asset_id, width=row.width, height=row.height, dimensions=(row.width, row.height),
                kind="uniform_equipment_texture", label=f"{row.name} {row.set_selector}", editable=True,
                reference_index=row.reference_index,
                provider_edit=lambda path, target=asset_id: {
                    "kind": "uniform_equipment_texture", "asset_id": target, "png": str(path)})
        self.catalog = SimpleNamespace(get_asset=lambda asset_id: self.assets[asset_id])
        original_dir = self.root / "originals"
        original_dir.mkdir()

        class AssetIO:
            def __init__(self, cache):
                pass

            def ensure_original(self, asset):
                path = original_dir / f"{asset.label}.png"
                if not path.exists():
                    path.write_bytes(encode_rgba_png(asset.width, asset.height, originals[asset.reference_index]))
                return path

            def validate_replacement(self, asset, path):
                payload = Path(path).read_bytes()
                _, _, rgba = decode_rgba_png(payload, asset.dimensions)
                import_mode(payload, asset.asset_id, rgba)
                return payload, rgba

        with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", AssetIO):
            self.session = StudioSession(self.cache, self.catalog, root=self.root / "sessions", session_id="a")
        self.session.attach_visual_catalog(self.catalog)

    def ids(self, name):
        return tuple(sorted(asset_id for asset_id, row in self.archive.by_id.items() if row.name == name))

    def staged(self):
        return tuple(edit.asset_id for edit in self.session.iter_edits())

    def stage(self, asset_id, *, independent=False, scale=1, rgba=None):
        asset = self.assets[asset_id]
        row = self.archive.by_id[asset_id]
        rgba = artwork(row.width, row.height) if rgba is None else rgba
        png = self.root / f"import-{asset_id.replace(':', '-')}.png"
        png.write_bytes(encode_rgba_png(row.width, row.height, rgba))
        with self.archive.context():
            return stage_equipment_import(self.session, asset, png, independent=independent, scale=scale)

    def test_global_style_is_staged_in_every_sampled_package(self):
        result = self.stage("tset:0:8:0:shoes01")
        expected = ("tset:0:8:0:shoes01", "tset:1:8:0:shoes01", "tset:2:8:0:shoes01")
        self.assertEqual(self.staged(), expected)  # 11H2 is never sampled for shoes01
        self.assertEqual(result.changed_asset_ids, expected)
        self.assertEqual(result.consumer_asset_ids, expected)
        self.assertTrue(result.modified)
        consumers = result.receipt["consumers"]
        self.assertEqual(consumers["in_game_lookup"], "global")
        self.assertEqual(consumers["staged_asset_ids"], list(expected))
        self.assertEqual(consumers["package_counts"], {"away": 2, "home_current": 1, "selected_only": 0})
        self.assertIn("3 uniform packages", result.message)
        self.assertEqual(len(self.session._undo), 1)
        for asset_id in expected:
            payload, rgba = self.session.asset_io.validate_replacement(
                self.assets[asset_id], self.session.current_path(self.assets[asset_id]))
            self.assertEqual(rgba, artwork(32, 32))
            self.assertEqual(import_mode(payload, asset_id, rgba), PALETTE_ONLY)
        self.session.undo()
        self.assertEqual(self.staged(), ())

    def test_per_team_global_import_refuses_before_reading_or_mutating(self):
        from mod_editor.core.errors import ValidationError

        asset = self.assets["tset:0:8:0:shoes01"]
        for scope in (SELECTED_PACKAGE, "per-team", "Giants"):
            with self.archive.context(), self.assertRaises(ValidationError) as caught:
                stage_equipment_import(self.session, asset, self.root / "absent.png", scope=scope)
            self.assertEqual(str(caught.exception), GLOBAL_RULE)
        self.assertEqual(self.staged(), ())
        self.assertEqual(len(self.session._undo), 0)

    def test_selected_alternate_home_package_is_kept_with_the_sampled_copies(self):
        self.stage("tset:3:8:0:shoes01")
        self.assertEqual(self.staged(), self.ids("shoes01"))

    def test_team_specific_style_stays_in_one_package(self):
        result = self.stage("tset:0:8:1:shoes09")
        self.assertEqual(self.staged(), ("tset:0:8:1:shoes09",))
        self.assertEqual(result.receipt["consumers"]["in_game_lookup"], "context_first")
        self.assertEqual(result.consumer_asset_ids, ("tset:0:8:1:shoes09",))

    def test_own_texture_choice_travels_to_every_copy_with_its_own_intent(self):
        result = self.stage("tset:1:8:0:shoes01", independent=True, scale=2)
        self.assertEqual(self.staged(), ("tset:0:8:0:shoes01", "tset:1:8:0:shoes01", "tset:2:8:0:shoes01"))
        self.assertEqual(result.changed_asset_ids, self.staged())
        for asset_id in self.staged():
            payload, rgba = self.session.asset_io.validate_replacement(
                self.assets[asset_id], self.session.current_path(self.assets[asset_id]))
            self.assertEqual(import_mode(payload, asset_id, rgba), OWN_TEXTURE)

    def test_restoring_the_original_and_revert_remove_every_copy(self):
        self.stage("tset:0:8:0:shoes01")
        original = self.session.asset_io.ensure_original(self.assets["tset:0:8:0:shoes01"])
        with self.archive.context():
            result = stage_equipment_import(self.session, self.assets["tset:0:8:0:shoes01"], original)
        self.assertFalse(result.modified)
        self.assertEqual(self.staged(), ())
        self.assertEqual(len(self.session._undo), 2)
        self.session.undo()
        self.assertEqual(self.staged(), ("tset:0:8:0:shoes01", "tset:1:8:0:shoes01", "tset:2:8:0:shoes01"))
        with self.archive.context():
            reverted = revert_equipment_import(self.session, self.assets["tset:2:8:0:shoes01"])
        self.assertEqual(reverted, ("tset:0:8:0:shoes01", "tset:1:8:0:shoes01", "tset:2:8:0:shoes01"))
        self.assertEqual(self.staged(), ())
        with self.archive.context():
            self.assertEqual(revert_equipment_import(self.session, self.assets["tset:2:8:0:shoes01"]), ())

    def test_repeat_import_is_a_no_op_and_a_second_style_shares_nothing(self):
        self.stage("tset:0:8:0:shoes01")
        again = self.stage("tset:1:8:0:shoes01")
        self.assertEqual(again.changed_asset_ids, ())
        self.assertEqual(len(self.session._undo), 1)
        self.stage("tset:0:8:2:shoes02", rgba=bytes(reversed(artwork(32, 32))))
        self.assertEqual(self.staged(), tuple(sorted(self.ids("shoes01")[:3] + self.ids("shoes02")[:3])))


class SharedSpanCompileTests(unittest.TestCase):
    """Identical retail spans compile once; every sharer gets identical bytes."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="equipment-shared-span-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = _MultiPackageArchive(self.root)
        self.cache = writer.EquipmentCompileCache()

    def test_second_package_reuses_the_compiled_span_and_names_its_own_target(self):
        png = self.root / "shoe.png"
        png.write_bytes(encode_rgba_png(32, 32, artwork(32, 32)))
        with self.archive.context():
            first = writer.build_unified_uniform_equipment_imports(
                self.root / "0", [("tset:0:8:0:shoes01", png)], pack_hashes={"pack": "b" * 64},
                compile_cache=self.cache)
            self.assertEqual(self.cache.statistics(), {"hits": 0, "misses": 1, "entries": 1, "artwork_entries": 1})
            uncached = writer.build_unified_uniform_equipment_imports(
                self.root / "0", [("tset:2:8:0:shoes01", png)], pack_hashes={"pack": "b" * 64})
            second = writer.build_unified_uniform_equipment_imports(
                self.root / "0", [("tset:2:8:0:shoes01", png)], pack_hashes={"pack": "b" * 64},
                compile_cache=self.cache)
        self.assertEqual(self.cache.statistics(), {"hits": 1, "misses": 1, "entries": 1, "artwork_entries": 1})
        self.assertEqual(uncached[0], second[0])
        self.assertEqual(uncached[2], second[2])
        self.assertEqual(uncached[1], second[1])
        self.assertEqual(first[0], second[0])
        self.assertEqual([name for name, _ in first[1]], ["equipment_0_8_0_shoes01.png"])
        self.assertEqual([name for name, _ in second[1]], ["equipment_2_8_0_shoes01.png"])
        self.assertEqual(first[1][0][1], second[1][0][1])
        self.assertEqual(first[3], "uniform-equipment-tset:0:8")
        self.assertEqual(second[3], "uniform-equipment-tset:2:8")
        self.assertEqual(second[2]["edits"][0]["asset_id"], "tset:2:8:0:shoes01")
        self.assertEqual(second[2]["edits"][0]["set_selector"], "11A1")
        self.assertEqual(second[2]["input_pngs"][0]["target"], "tset:2:8:0:shoes01")
        self.assertEqual(second[4]["outer_index"], 2)
        scrub = lambda report: {key: value for key, value in report.items()
                                if key not in {"edits", "input_pngs", "target"}}
        self.assertEqual(scrub(first[2]), scrub(second[2]))
        identity = {"asset_id", "set_selector", "preview_file"}
        first_edit = {k: v for k, v in first[2]["edits"][0].items() if k not in identity}
        second_edit = {k: v for k, v in second[2]["edits"][0].items() if k not in identity}
        self.assertEqual(first_edit, second_edit)
        actual, _ = decode_chunk(second[0], parse_chunks(second[0])[0])
        start = self.archive.fixture.chunk.system_bytes + self.archive.fixture.rows[0].palette_offset
        self.assertNotEqual(actual[start:start + 1024], self.archive.fixture.decoded[start:start + 1024])
        self.assertEqual(actual[:start], self.archive.fixture.decoded[:start])

    def test_different_artwork_or_span_never_hits(self):
        png = self.root / "shoe.png"
        png.write_bytes(encode_rgba_png(32, 32, artwork(32, 32)))
        other = self.root / "other.png"
        other.write_bytes(encode_rgba_png(32, 32, bytes(reversed(artwork(32, 32)))))
        with self.archive.context():
            writer.build_unified_uniform_equipment_imports(
                self.root / "0", [("tset:0:8:0:shoes01", png)], pack_hashes={"pack": "b" * 64},
                compile_cache=self.cache)
            writer.build_unified_uniform_equipment_imports(
                self.root / "0", [("tset:1:8:0:shoes01", other)], pack_hashes={"pack": "b" * 64},
                compile_cache=self.cache)
            writer.build_unified_uniform_equipment_imports(
                self.root / "0", [("tset:1:8:2:shoes02", png)], pack_hashes={"pack": "b" * 64},
                compile_cache=self.cache)
        self.assertEqual(self.cache.statistics(), {"hits": 0, "misses": 3, "entries": 3, "artwork_entries": 2})


@unittest.skipUnless(INDEX.is_file(), "Private retail pack index is absent")
class RetailSharedSpanTests(unittest.TestCase):
    """Real packages: a fan-out copy reparses, and shared spans compile once."""

    @classmethod
    def setUpClass(cls):
        cls.by_id, _groups = writer.load_targets()
        cls.pins = writer._chain_pins()

    def test_two_away_packages_sharing_a_retail_span_get_identical_bytes(self):
        selected = self.by_id["tset:3850:8:0:shoes01"]
        consumers = writer.consumer_targets(selected, self.by_id)
        by_span = {}
        for item in consumers:
            by_span.setdefault(self.pins[(item.outer_index, item.chunk_index)], []).append(item)
        shared = next(items for items in by_span.values() if len(items) >= 2)[:2]
        distinct = next(items for span, items in by_span.items()
                        if self.pins[(shared[0].outer_index, 8)] != span)[0]
        temporary = tempfile.TemporaryDirectory(prefix="equipment-retail-span-")
        self.addCleanup(temporary.cleanup)
        png = Path(temporary.name) / "shoe.png"
        png.write_bytes(encode_rgba_png(256, 256, b"".join(
            bytes((255, 110, 20, 255)) if (x // 32 + y // 32) % 2 else bytes((240, 90, 10, 255))
            for y in range(256) for x in range(256))))
        cache = writer.EquipmentCompileCache()
        hashes = {}
        results = [writer.build_unified_uniform_equipment_imports(
            INDEX, [(item.asset_id, png)], pack_hashes=hashes, compile_cache=cache)
            for item in (*shared, distinct)]
        statistics = cache.statistics()
        self.assertEqual((statistics["hits"], statistics["misses"]), (1, 2))
        self.assertEqual(results[0][0], results[1][0])
        self.assertNotEqual(results[0][0], results[2][0])
        for item, (span, _previews, receipt, _selector, target) in zip((*shared, distinct), results):
            with self.subTest(asset_id=item.asset_id):
                self.assertEqual(target["outer_index"], item.outer_index)
                self.assertEqual(receipt["edits"][0]["asset_id"], item.asset_id)
                self.assertEqual(len(span), target["span_size"])
                chunk = parse_chunks(span)[0]
                decoded, info = decode_chunk(span, chunk)
                self.assertIsNotNone(info)
                self.assertEqual(hashlib.sha256(decoded).hexdigest(), receipt["replacement"]["decoded_sha256"])
                palette = decoded[chunk.system_bytes + item.palette_offset:][:1024]
                self.assertNotEqual(hashlib.sha256(palette).hexdigest(), item.palette_bgra_sha256)


    def test_tight_retail_slot_takes_the_lossless_fallback_and_reparses(self):
        # Tennessee 17H0 chunk 8: 55,776 stored / 55,772 consumed, 13-bit distances,
        # shared by 91 packages. Its sibling palettes match against shoes01's, so a
        # replaced palette overflows the retail greedy stream; the optimal parse fits.
        temporary = tempfile.TemporaryDirectory(prefix="equipment-tight-slot-")
        self.addCleanup(temporary.cleanup)
        png = Path(temporary.name) / "shoe.png"
        png.write_bytes(encode_rgba_png(256, 256, b"".join(
            bytes((255, 110, 20, 255)) if (x // 32 + y // 32) % 2 else bytes((240, 90, 10, 255))
            for y in range(256) for x in range(256))))
        target = self.by_id["tset:3753:8:0:shoes01"]
        self.assertEqual(target.set_selector, "17H0")
        span, _previews, receipt, _selector, record = writer.build_unified_uniform_equipment_imports(
            INDEX, [(target.asset_id, png)], pack_hashes={})
        compression = receipt["compression"]
        self.assertEqual(compression["strategy"], "optimal_token_parse")
        self.assertEqual((compression["stored_size"], compression["original_consumed_bytes"]), (55776, 55772))
        self.assertLess(compression["recompressed_bytes"], 55776)
        self.assertEqual(receipt["bounded_palette_fit"]["attempts"][-1]["maximum_palette_entries"], 256)
        self.assertEqual(receipt["lossless_offset_bit_candidates"], [13, 10, 11, 12])
        self.assertEqual(len(span), record["span_size"])
        chunk = parse_chunks(span)[0]
        decoded, info = decode_chunk(span, chunk)
        self.assertIsNotNone(info)
        self.assertEqual(hashlib.sha256(decoded).hexdigest(), receipt["replacement"]["decoded_sha256"])
        self.assertTrue(compression["loader_in_place_alias_guard"])
        self.assertTrue(compression["loader_in_place_end_guard"])

    def test_every_sampled_copy_lies_inside_one_pack_extent(self):
        from nfl_outer import parse_archive, read_entry_bytes

        archive = parse_archive(INDEX)
        straddling = [index for index, entry in enumerate(archive.entries)
                      if 3613 <= index <= 4246 and len(entry.segments) != 1]
        self.assertEqual(straddling, [3625, 3832, 4136])
        sampled = {}
        for target in self.by_id.values():
            if (target.outer_index in straddling and writer.in_game_lookup(target.name) == "global"
                    and writer.sampled_package(target.set_selector)):
                sampled.setdefault(target.outer_index, set()).add(target.chunk_index)
        self.assertEqual(set(sampled), {4136})  # 01H11 and 25H3 are never sampled for global rows
        for outer, chunks in sampled.items():
            entry = archive.entries[outer]
            package = read_entry_bytes(archive, entry)
            first = entry.segments[0].size
            for chunk in parse_chunks(package, allow_trailing=True):
                if chunk.kind == "TSET" and chunk.index in chunks:
                    self.assertLessEqual(chunk.end_offset, first, f"{outer} chunk {chunk.index}")
        # The straddling away package is writable at its real pack offset.
        temporary = tempfile.TemporaryDirectory(prefix="equipment-extent-")
        self.addCleanup(temporary.cleanup)
        png = Path(temporary.name) / "shoe.png"
        png.write_bytes(encode_rgba_png(256, 256, bytes((30, 200, 90, 255)) * 65536))
        _span, _previews, _receipt, _selector, record = writer.build_unified_uniform_equipment_imports(
            INDEX, [("tset:4136:8:0:shoes01", png)], pack_hashes={})
        self.assertEqual(record["xiso_pack_path"], "vc_53450030/B")
        pack = next(item for item in archive.packs if item.name == "B")
        with pack.path.open("rb") as stream:
            stream.seek(record["pack_offset"])
            raw = stream.read(record["span_size"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), record["span_sha256"])
        with self.assertRaisesRegex(ValueError, "crosses pack extents"):
            writer.build_unified_uniform_equipment_imports(
                INDEX, [("tset:3625:8:0:shoes01", png)], pack_hashes={})


if __name__ == "__main__":
    unittest.main()
