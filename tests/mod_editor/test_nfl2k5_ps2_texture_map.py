"""The PS2-to-Xbox texture map: its GS maths, its schema and its evidence.

Everything here runs without a disc and without a byte of retail data. The GS
layouts are exercised against a synthetic PS2 image the module builds itself,
the join is exercised against a synthetic Xbox inventory, and the shipped
manifest is checked as data.

The two runs that do need the retail image -- the full 12,958-identity
reproduction and the 1.2M-hash oracle -- are gated on ``NFL2K5_PS2_ISO``
(the oracle lives in ``test_xxh3.py``, next to the implementation it proves).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402
import nfl2k5_ps2_texture_map as mapper  # noqa: E402
from xxh3 import xxh3_64  # noqa: E402

_MANIFEST = _REPO_ROOT / "mod_editor" / "data" / "nfl2k5-xbox-map.v1.json"
_SIDECAR = (_REPO_ROOT / "reports" / "gameplay_tuning"
            / "nfl2k5-xbox-map.unresolved.v1.json")

# What the retail disc must keep producing. These are the numbers the M1 plan
# is built on; if the builder stops reproducing them, the premise has moved.
_RETAIL_TEXTURES = 120_779
_RETAIL_FULL_IDENTITIES = 12_958
_PACK_IDENTITIES = 15_104

_NFL2K5_PS2_ISO = os.environ.get("NFL2K5_PS2_ISO")
_PACK_HASHES = os.environ.get("NFL2K5_PACK_HASHES")
_XBOX_INVENTORY = os.environ.get("NFL2K5_XBOX_INVENTORY")


def _tiny_png(width: int = 4, height: int = 4) -> bytes:
    """A structurally valid 4x4 RGBA PNG. Synthetic; no game pixel involved."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes([(x * 17) & 0xFF] * 4 * width)
                   for x in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


class SelfTestTests(unittest.TestCase):
    def test_the_selftest_passes(self) -> None:
        buffer = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = buffer
        try:
            code = mapper.selftest()
        finally:
            sys.stdout = real_stdout
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("NFL2K5_PS2_TEXTURE_MAP_SELFTEST_PASS", buffer.getvalue())


class GsTableTests(unittest.TestCase):
    """Every swizzle table must be a permutation, or bytes vanish silently."""

    def test_column_tables_are_permutations(self) -> None:
        self.assertEqual(
            sorted(v for row in mapper.COLUMN_TABLE8 for v in row),
            list(range(256)))
        self.assertEqual(
            sorted(v for row in mapper.COLUMN_TABLE4 for v in row),
            list(range(512)))
        self.assertEqual(
            sorted(v for row in mapper.COLUMN_TABLE32 for v in row),
            list(range(64)))

    def test_block_tables_are_permutations(self) -> None:
        for table, size in ((mapper.BLOCK_TABLE8, 32), (mapper.BLOCK_TABLE4, 32),
                            (mapper.BLOCK_TABLE32, 32)):
            self.assertEqual(sorted(v for row in table for v in row),
                             list(range(size)))

    def test_clut_permutations_are_permutations(self) -> None:
        self.assertEqual(sorted(mapper.SWAP34), list(range(256)))
        self.assertEqual(sorted(mapper.VRAMREAD), list(range(256)))
        self.assertEqual(sorted(mapper.VRAMREAD4), list(range(16)))

    def test_swizzle8_moves_every_byte_exactly_once(self) -> None:
        image = bytes((index * 7 + 3) & 0xFF for index in range(64 * 32))
        swizzled = mapper.swizzle8_blocks(image, 64, 32)
        self.assertEqual(len(swizzled), len(image))
        self.assertEqual(sorted(swizzled), sorted(image))
        self.assertNotEqual(swizzled, image)

    def test_swizzle4_packs_low_nibble_first(self) -> None:
        indices = bytes(index & 0x0F for index in range(64 * 16))
        packed = mapper.swizzle4_blocks(indices, 64, 16)
        self.assertEqual(len(packed), 64 * 16 // 2)
        self.assertEqual(mapper.unpack4(
            bytes([0x21, 0x43]), 4, 1), bytes([1, 2, 3, 4]))

    def test_the_c32_inverse_is_a_bijection_over_one_page(self) -> None:
        self.assertEqual(
            sorted(mapper.c32_source_words(slot, 64, 1) for slot in range(2048)),
            list(range(2048)))

    def test_a_partial_c32_page_is_refused_not_guessed(self) -> None:
        # The reference implementation scattered into uninitialised memory, so
        # a partial page is either an error or unreproducible. Both refuse.
        with self.assertRaises(mapper.TextureMapError):
            mapper._c32_check(64, 64)
        self.assertEqual(mapper._c32_check(2048, 64), 1)


class NamingTests(unittest.TestCase):
    def test_bits_packs_psm_tw_th_and_tcc(self) -> None:
        self.assertEqual(mapper.texture_bits(0x13, 6, 5, 1),
                         0x13 | (6 << 6) | (5 << 10) | (1 << 14))

    def test_disc_tcc_is_emitted_as_bit_14(self) -> None:
        self.assertTrue(mapper.texture_bits(0x13, 8, 8, 1) & 0x4000)
        self.assertFalse(mapper.texture_bits(0x13, 8, 8, 0) & 0x4000)

    def test_the_hash_fields_are_unpadded_and_bits_is_eight_digits(self) -> None:
        name = mapper.replacement_name(0x1, 0x2, 0x5DD3)
        self.assertEqual(name, "1-2-00005dd3.png")
        wide = mapper.replacement_name(0xFEDCBA9876543210, 0x0F, 0x4000)
        self.assertEqual(wide, "fedcba9876543210-f-00004000.png")

    def test_a_palette_free_texture_names_with_two_fields(self) -> None:
        self.assertEqual(mapper.replacement_name(0xAB, None, 0x10),
                         "ab-00000010.png")

    def test_names_round_trip_through_the_parser(self) -> None:
        for tex0, clut, bits in ((1, 2, 0x5DD3), (0xFFFFFFFFFFFFFFFF, 0, 0x4013),
                                 (0x10, None, 0x0013)):
            name = mapper.replacement_name(tex0, clut, bits)
            self.assertEqual(mapper.parse_replacement_name(name), (bits, clut))

    def test_a_mip_suffix_does_not_shift_the_bits_field(self) -> None:
        self.assertEqual(
            mapper.parse_replacement_name("aa-bb-00005dd3-mip3.png"),
            (0x5DD3, 0xBB))

    def test_every_generated_name_satisfies_the_audit_regex(self) -> None:
        for tex0, clut, bits in ((1, 2, 0x5DD3), (0xFEDCBA9876543210, 0xF, 0x4000)):
            name = mapper.replacement_name(tex0, clut, bits)
            self.assertIsNotNone(audit.PCSX2_HASH_NAME.fullmatch(name), name)


class SyntheticImageTests(unittest.TestCase):
    """The three on-disc layouts, round-tripped hash -> name."""

    def test_a_linear_psmt8_texture_hashes_by_the_block_path(self) -> None:
        width, height = 64, 32
        image = mapper._pattern(width * height, 11)
        palette = mapper._pattern(1024, 12)
        video = image + palette
        tex0 = mapper._make_tex0(mapper.PSMT8, 6, 5, 1, len(image) // 256)
        record = mapper.analyse(
            mapper._descriptor(tex0, 0, width, height), video, True)
        self.assertEqual(record["l0"]["lin"],
                         xxh3_64(mapper.swizzle8_blocks(image, width, height)))
        self.assertEqual(record["mips"], 1)
        self.assertEqual(
            record["clut"]["cbp/swap34"],
            xxh3_64(mapper.permute_clut(palette, mapper.SWAP34, "swap34")))

    def test_a_c32_mipped_texture_hashes_by_the_upload_path(self) -> None:
        width, height = 64, 32
        level0 = mapper._pattern(width * height, 13)
        vram = bytearray(8192)
        blocks = mapper.swizzle8_blocks(level0, width, height)
        for index, start in enumerate(
                mapper.vram_block_offsets(width, height, 1, mapper.PSMT8)):
            vram[start:start + 256] = blocks[index * 256:(index + 1) * 256]
        region = mapper._c32_upload(bytes(vram), 64)
        tex0 = mapper._make_tex0(mapper.PSMT8, 6, 5, 1, 16)
        record = mapper.analyse(
            mapper._descriptor(tex0, 0, width, height, mip_tbps=(1, 2)),
            region, False)
        self.assertEqual(record["mips"], 3)
        self.assertEqual(record["l0"]["c32"],
                         xxh3_64(mapper.swizzle8_blocks(level0, width, height)))
        # The linear reading of the same bytes must NOT collide with it; that
        # is why both layouts are always tried.
        self.assertNotEqual(record["l0"]["c32"], record["l0"].get("lin"))

    def test_a_non_indexed_format_is_not_a_texture_we_name(self) -> None:
        tex0 = mapper._make_tex0(0x00, 6, 5, 1, 0)
        self.assertIsNone(mapper.analyse(
            mapper._descriptor(tex0, 0, 64, 32), bytes(65536), True))

    def test_a_truncated_descriptor_is_refused(self) -> None:
        self.assertIsNone(mapper.analyse(b"\x00" * 8, bytes(1024), True))


class XboxJoinTests(unittest.TestCase):
    """Fan-out is the shipping question, so the join rules are pinned here."""

    HEADER = "pack\tentry_index\tname\tname_key\tfourcc\tsize\twidth\theight\tformat\textra\n"

    def _side(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "xbox.tsv"
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(self.HEADER)
                for row in rows:
                    stream.write("\t".join(row) + "\n")
            return mapper.XboxSide.load(str(path))

    def test_a_unique_object_name_resolves_to_one_p8_id(self) -> None:
        side = self._side([
            ("vc", "7", "helmet", "HELMET", "HITX", "1", "", "", "P8",
             "role=object;chunk=3;id=0xabc"),
        ])
        ids, namespace = mapper.xbox_ids(side, {"src": "chunk", "name_key": "HELMET"})
        self.assertEqual(namespace, "p8")
        self.assertEqual(ids, ["p8:7:helmet"])

    def test_a_shared_object_name_fans_out_and_is_not_shippable(self) -> None:
        side = self._side([
            ("vc", "7", "logo", "LOGO", "HITX", "1", "", "", "P8",
             "role=object;chunk=3;id=0xabc"),
            ("vc", "9", "logo", "LOGO", "HITX", "1", "", "", "P8",
             "role=object;chunk=4;id=0xdef"),
        ])
        ids, _namespace = mapper.xbox_ids(side, {"src": "chunk", "name_key": "LOGO"})
        self.assertEqual(len(ids), 2)
        document, counts = mapper.manifest_document(
            {"proved": {"a-b-00004013.png": {
                "ids": set(ids), "capped": False, "namespaces": {"p8"},
                "layouts": set(), "sources": 2}},
             "tex0_only": {}, "no_xbox": {}, "identity": {},
             "textures_scanned": 1}, "2026-01-01T00:00:00Z")
        self.assertEqual(document["entries"], [])
        self.assertEqual(counts["fanout_by_namespace"]["p8"]["pngs"], 1)

    def test_tset_children_join_at_the_set_level_on_id_and_chunk(self) -> None:
        side = self._side([
            ("vc", "5", "", "", "TSET", "1", "", "", "",
             "role=object;chunk=12;id=0x1234"),
            ("vc", "5", "jersey_a", "JERSEY_A", "TXTR", "", "", "", "P8",
             "role=tset_child;chunk=12;child=0"),
            ("vc", "5", "jersey_b", "JERSEY_B", "TXTR", "", "", "", "P8",
             "role=tset_child;chunk=12;child=1"),
        ])
        ids, namespace = mapper.xbox_ids(side, {
            "src": "tset", "id": "0x1234", "chunk": 12, "idx": 1,
            "name_key": "JERSEY_B"})
        self.assertEqual(namespace, "tset")
        self.assertEqual(ids, ["tset:5:12:1:jersey_b"])

    def test_an_unnamed_tset_child_falls_back_to_its_index(self) -> None:
        side = self._side([
            ("vc", "5", "", "", "TSET", "1", "", "", "",
             "role=object;chunk=12;id=0x1234"),
            ("vc", "5", "piece", "PIECE", "TXTR", "", "", "", "P8",
             "role=tset_child;chunk=12;child=2"),
        ])
        ids, _namespace = mapper.xbox_ids(side, {
            "src": "tset", "id": "0x1234", "chunk": 12, "idx": 2, "name_key": ""})
        self.assertEqual(ids, ["tset:5:12:2:piece"])

    def test_an_unmatched_set_key_yields_nothing_rather_than_a_guess(self) -> None:
        side = self._side([
            ("vc", "5", "", "", "TSET", "1", "", "", "",
             "role=object;chunk=12;id=0x1234"),
            ("vc", "5", "piece", "PIECE", "TXTR", "", "", "", "P8",
             "role=tset_child;chunk=12;child=0"),
        ])
        ids, _namespace = mapper.xbox_ids(side, {
            "src": "tset", "id": "0x9999", "chunk": 12, "idx": 0,
            "name_key": "PIECE"})
        self.assertEqual(ids, [])

    def test_the_crib_scene_namespace_is_used_for_entry_4248(self) -> None:
        side = self._side([
            ("vc", "4248", "crib", "CRIB", "SCNE", "1", "", "", "",
             "role=object;chunk=7;id=0x1"),
            ("vc", "4248", "", "", "TXTR", "", "", "", "P8",
             "role=scne_texture;chunk=7;child=0"),
            ("vc", "11", "stadium", "STADIUM", "SCNE", "1", "", "", "",
             "role=object;chunk=2;id=0x2"),
            ("vc", "11", "", "", "TXTR", "", "", "", "P8",
             "role=scne_texture;chunk=2;child=0"),
        ])
        ids, namespace = mapper.xbox_ids(
            side, {"src": "scne", "scene": "CRIB", "idx": 5})
        self.assertEqual(namespace, "scene")
        self.assertEqual(ids, ["nfl2k5.crib.scene.c0007.t005"])
        other, _ = mapper.xbox_ids(
            side, {"src": "scne", "scene": "STADIUM", "idx": 3})
        self.assertEqual(other, ["nfl2k5.scene.o0011.c0002.t003"])

    def test_every_namespace_the_audit_accepts_is_one_we_emit(self) -> None:
        for identifier in ("p8:7:helmet", "tset:5:12:1:jersey_b",
                           "nfl2k5.crib.scene.c0007.t005",
                           "nfl2k5.scene.o0011.c0002.t003"):
            self.assertTrue(identifier.startswith(("p8:", "tset:", "nfl2k5.")))


class ManifestShapeTests(unittest.TestCase):
    def _document(self):
        result = {
            "proved": {
                "aa-bb-00005dd3.png": {"ids": {"p8:7:helmet"}, "capped": False,
                                       "namespaces": {"p8"},
                                       "layouts": {"lin"}, "sources": 1},
                "cc-dd-00005dd3.png": {"ids": {"tset:5:12:1:jersey"},
                                       "capped": False, "namespaces": {"tset"},
                                       "layouts": {"c32"}, "sources": 1},
            },
            "tex0_only": {"ee-ff-00005dd3.png": 4},
            "no_xbox": {"11-22-00005dd3.png": 2},
            "identity": {"boot_sha256": "b" * 64, "image_sha256": "c" * 64},
            "textures_scanned": 3,
        }
        return result, mapper.manifest_document(result, "2026-01-01T00:00:00Z")

    def test_entries_carry_exactly_the_two_keys_the_audit_allows(self) -> None:
        _result, (document, _counts) = self._document()
        self.assertEqual(document["schema"], audit.MAPPING_SCHEMA)
        for entry in document["entries"]:
            self.assertEqual(set(entry), {"pcsx2_png", "xbox_asset_id"})
            self.assertTrue(entry["xbox_asset_id"].startswith(
                ("p8:", "tset:", "nfl2k5.")))

    def test_provenance_sits_at_the_top_level_not_in_the_entries(self) -> None:
        _result, (document, _counts) = self._document()
        self.assertEqual(document["disc"]["serial"], "SLUS-20919")
        self.assertEqual(document["disc"]["boot_sha256"], "b" * 64)
        self.assertEqual(document["disc"]["content_sha256"], "c" * 64)
        self.assertEqual(document["method"], "hop1/v5")
        self.assertEqual(document["emulator"]["hash_convention"],
                         "classic-tcc-bit14")
        self.assertEqual(document["counts"]["entries"], 2)

    def test_the_emulator_pin_is_the_rig_verified_build(self) -> None:
        self.assertEqual(mapper.EMULATOR["commit"],
                         "8226182aabe19640c6e676331678612f257356dd")
        self.assertEqual(mapper.EMULATOR["commit_status"], "rig-verified")
        self.assertEqual(mapper.EMULATOR["requires_setting"],
                         "ClassicTextureNames=true")
        # The provisional dev-box pin must never reach shipped provenance.
        self.assertNotIn("f5f473479d", json.dumps(mapper.EMULATOR))

    def test_entries_are_sorted_so_the_file_is_reproducible(self) -> None:
        _result, (document, _counts) = self._document()
        keys = [(row["pcsx2_png"], row["xbox_asset_id"])
                for row in document["entries"]]
        self.assertEqual(keys, sorted(keys))

    def test_the_sidecar_counts_every_reason(self) -> None:
        result, (_document, counts) = self._document()
        result["corpus"] = mapper.PackCorpus({1: ["99-88-00005dd3.png"]})
        sidecar = mapper.sidecar_document(result, "2026-01-01T00:00:00Z", counts)
        self.assertEqual(sidecar["reasons"]["tex0_only"]["pngs"], 1)
        self.assertEqual(sidecar["reasons"]["no_xbox_id"]["pngs"], 1)
        self.assertEqual(sidecar["reasons"]["unexplained"]["pngs"], 1)
        for reason in sidecar["reasons"].values():
            self.assertTrue(reason["reason"])


def _names_by_asset(entries):
    """``{xbox_asset_id: [pcsx2_png, ...]}`` the way the builder indexes it."""
    out: dict = {}
    for entry in entries:
        out.setdefault(entry["xbox_asset_id"], []).append(entry["pcsx2_png"])
    return out


class ResolveClaimsTests(unittest.TestCase):
    """One Xbox asset per filename, because the export service demands it.

    ``ps2_export_service.plan_export`` marks a target ambiguous when the
    manifest lets a second asset claim any of its filenames, so a row that
    shares a name with another row does not add a way in -- it takes both
    away. These tests pin the tie-break and prove nothing is dropped silently.
    """

    def test_an_uncontested_name_ships_unchanged(self) -> None:
        rows = [{"pcsx2_png": "a-b-00004013.png", "xbox_asset_id": "p8:1:x"}]
        kept, dropped = mapper.resolve_claims(rows)
        self.assertEqual(kept, rows)
        self.assertEqual(dropped, [])

    def test_a_logical_uniform_id_supersedes_the_physical_one(self) -> None:
        # The same texture named twice. The logical id is the one a Studio
        # uniform edit carries, so it is the one that survives.
        kept, dropped = mapper.resolve_claims([
            {"pcsx2_png": "a-b-00004013.png", "xbox_asset_id": "tset:3851:1:1:j"},
            {"pcsx2_png": "a-b-00004013.png",
             "xbox_asset_id": "nfl2k5.uniform.28h1.torso"},
        ])
        self.assertEqual(kept, [{"pcsx2_png": "a-b-00004013.png",
                                 "xbox_asset_id": "nfl2k5.uniform.28h1.torso"}])
        self.assertEqual(dropped, [{"pcsx2_png": "a-b-00004013.png",
                                    "xbox_asset_id": "tset:3851:1:1:j",
                                    "reason": mapper.DROP_SUPERSEDED}])

    def test_art_several_kits_share_belongs_to_no_kit(self) -> None:
        # Three Bills away kits carry one sleeve texture on the PS2 disc.
        # Editing one would repaint the others, so none may claim it.
        rows = [{"pcsx2_png": "a-b-00005dd3.png",
                 "xbox_asset_id": "nfl2k5.uniform.03a%d.sleeve" % n}
                for n in (3, 4, 5)]
        kept, dropped = mapper.resolve_claims(rows)
        self.assertEqual(kept, [])
        self.assertEqual([row["reason"] for row in dropped],
                         [mapper.DROP_SHARED] * 3)

    def test_shared_art_falls_back_to_its_unambiguous_texture_id(self) -> None:
        # A texture id still names the thing itself without ambiguity, so it
        # ships even when no logical target can own it.
        kept, dropped = mapper.resolve_claims([
            {"pcsx2_png": "a-b-00005dd3.png", "xbox_asset_id": "tset:9:0:0:s"},
            {"pcsx2_png": "a-b-00005dd3.png",
             "xbox_asset_id": "nfl2k5.uniform.03a3.sleeve"},
            {"pcsx2_png": "a-b-00005dd3.png",
             "xbox_asset_id": "nfl2k5.uniform.03a4.sleeve"},
        ])
        self.assertEqual(kept, [{"pcsx2_png": "a-b-00005dd3.png",
                                 "xbox_asset_id": "tset:9:0:0:s"}])
        self.assertEqual(sorted(row["xbox_asset_id"] for row in dropped),
                         ["nfl2k5.uniform.03a3.sleeve",
                          "nfl2k5.uniform.03a4.sleeve"])

    def test_two_physical_assets_on_one_name_leave_it_unshipped(self) -> None:
        # Defensive: the unique-join filter upstream should make this
        # unreachable, and the retail run confirms it never fires. If a future
        # canonicalisation ever collapses two proved names onto one filename,
        # the answer is still to ship neither rather than pick one.
        kept, dropped = mapper.resolve_claims([
            {"pcsx2_png": "a-b-00004013.png", "xbox_asset_id": "p8:1:x"},
            {"pcsx2_png": "a-b-00004013.png", "xbox_asset_id": "p8:2:y"},
        ])
        self.assertEqual(kept, [])
        self.assertEqual([row["reason"] for row in dropped],
                         [mapper.DROP_CONTESTED] * 2)

    def test_a_duplicate_row_is_not_a_contest(self) -> None:
        rows = [{"pcsx2_png": "a-b-00004013.png", "xbox_asset_id": "p8:1:x"}] * 2
        kept, dropped = mapper.resolve_claims(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_every_input_row_is_either_kept_or_reported(self) -> None:
        rows = [
            {"pcsx2_png": "a-b-00004013.png", "xbox_asset_id": "p8:1:x"},
            {"pcsx2_png": "c-d-00004013.png", "xbox_asset_id": "tset:2:0:0:y"},
            {"pcsx2_png": "c-d-00004013.png",
             "xbox_asset_id": "nfl2k5.uniform.00a0.torso"},
            {"pcsx2_png": "e-f-00004013.png",
             "xbox_asset_id": "nfl2k5.uniform.01a0.pants"},
            {"pcsx2_png": "e-f-00004013.png",
             "xbox_asset_id": "nfl2k5.uniform.02a0.pants"},
        ]
        kept, dropped = mapper.resolve_claims(rows)
        accounted = {(row["pcsx2_png"], row["xbox_asset_id"]) for row in kept}
        accounted |= {(row["pcsx2_png"], row["xbox_asset_id"]) for row in dropped}
        self.assertEqual(accounted,
                         {(row["pcsx2_png"], row["xbox_asset_id"])
                          for row in rows})
        self.assertEqual(len(kept) + len(dropped), len(rows))

    def test_the_result_is_sorted_so_the_manifest_is_reproducible(self) -> None:
        rows = [{"pcsx2_png": "z-z-00004013.png", "xbox_asset_id": "p8:2:z"},
                {"pcsx2_png": "a-a-00004013.png", "xbox_asset_id": "p8:1:a"}]
        kept, _dropped = mapper.resolve_claims(rows)
        self.assertEqual([row["pcsx2_png"] for row in kept],
                         ["a-a-00004013.png", "z-z-00004013.png"])


class UniformCoverageTests(unittest.TestCase):
    """The demo-team question, answered from the Xbox side a user edits."""

    def _side(self, entries):
        side = mapper.XboxSide()
        for entry, children in entries.items():
            for chunk, child, name in children:
                side.children_by_entry.setdefault(entry, []).append(
                    (chunk, child, name))
        return side

    def test_a_kit_is_fully_mappable_only_when_every_piece_is(self) -> None:
        side = self._side({
            100: [(0, 0, "jersey"), (0, 1, "pant")],
            200: [(0, 0, "jersey"), (0, 1, "pant")],
        })
        selectors = {
            100: {"abbreviation": "DET", "team": "Detroit Lions", "side": "A",
                  "style": "Current Uniform", "selector": "00A0"},
            200: {"abbreviation": "TEN", "team": "Tennessee Titans", "side": "H",
                  "style": "1999 Alternate 1", "selector": "01H0"},
        }
        shipped = {"tset:100:0:0:jersey", "tset:100:0:1:pant",
                   "tset:200:0:0:jersey"}
        per_team, per_selector = mapper.uniform_coverage(side, selectors, shipped)
        self.assertTrue(per_team["DET"]["fully_mappable"])
        self.assertFalse(per_team["TEN"]["fully_mappable"])
        self.assertEqual(per_team["TEN"]["mapped"], 1)
        self.assertEqual(per_team["TEN"]["pieces"], 2)
        self.assertTrue(per_selector["DET/A/Current Uniform"]["fully_mappable"])
        self.assertEqual(per_team["TEN"]["unmapped_selectors"][0]["mapped"], 1)

    def test_the_chosen_team_must_be_mappable_and_in_a_dump(self) -> None:
        # Two kits, both fully mapped at the logical level; only DET is on
        # screen in a dump the rig already holds, so only DET can be witnessed.
        side = self._side({100: [(0, 0, "jersey")], 200: [(0, 0, "jersey")]})
        side.containers[(100, 0)] = ("jersey", "TSET", "0xaaa")
        side.containers[(200, 0)] = ("jersey", "TSET", "0xbbb")
        side.tset_children[(100, 0)] = [(0, "jersey")]
        side.tset_children[(200, 0)] = [(0, "jersey")]
        selectors = {
            100: {"abbreviation": "DET", "team": "Detroit Lions", "side": "A",
                  "style": "Current Uniform", "selector": "00A0"},
            # ARZ is fully mappable but no dump on the rig shows it.
            200: {"abbreviation": "ARZ", "team": "Arizona Cardinals",
                  "side": "H", "style": "Current Uniform", "selector": "01H0"},
        }
        result = {
            "proved": {
                "aa-bb-00004013.png": {"ids": {"tset:100:0:0:jersey"},
                                       "capped": False, "namespaces": {"tset"},
                                       "layouts": {"lin"}, "sources": 1,
                                       "canonical": "aa-bb-00004013.png"},
                "cc-dd-00004013.png": {"ids": {"tset:200:0:0:jersey"},
                                       "capped": False, "namespaces": {"tset"},
                                       "layouts": {"lin"}, "sources": 1,
                                       "canonical": "cc-dd-00004013.png"},
            },
            "tex0_only": {}, "no_xbox": {}, "identity": {},
            "textures_scanned": 2, "corpus": mapper.PackCorpus({}),
            "side": side, "selectors": selectors,
            "logical_targets": {
                "nfl2k5.uniform.00a0.torso": [(100, 0)],
                "nfl2k5.uniform.01h0.torso": [(200, 0)],
            },
            "ps2_by_id_chunk": {},
        }
        document, counts = mapper.manifest_document(
            result, "2026-01-01T00:00:00Z")
        shipped = {row["xbox_asset_id"] for row in document["entries"]}
        self.assertIn("nfl2k5.uniform.00a0.torso", shipped)
        sidecar = mapper.sidecar_document(
            result, "2026-01-01T00:00:00Z", counts, shipped)
        demo = sidecar["demo_team"]
        self.assertEqual(sorted(demo["fully_mappable_teams"]), ["ARZ", "DET"])
        self.assertEqual(demo["fully_mappable_and_witnessable"], ["DET"])
        self.assertEqual(demo["chosen"], "DET")
        self.assertEqual(demo["chosen_kit"], "DET/A/Current Uniform")

    def test_a_logical_target_maps_through_the_shared_id_and_chunk_key(self) -> None:
        # A PS2 texture called HELMET00 exists in all 634 kits, so the name
        # join alone fans out to nothing; the (outer id, chunk) key names one.
        side = mapper.XboxSide()
        side.containers[(7, 11)] = ("helmet00", "HITX", "0x341ecd96")
        targets = {"nfl2k5.uniform.00h0.helmet.helmet00": [(7, 11)]}
        ps2 = {("0x341ecd96", 11): [(0, "HELMET00", ("aa-bb-00004013.png",))]}
        entries, detail = mapper.logical_uniform_rows(side, targets, {}, ps2)
        self.assertEqual(entries, [{
            "pcsx2_png": "aa-bb-00004013.png",
            "xbox_asset_id": "nfl2k5.uniform.00h0.helmet.helmet00"}])
        kept, dropped = mapper.resolve_claims(entries)
        self.assertEqual(dropped, [])
        coverage, _per_selector = mapper.logical_coverage(
            detail, _names_by_asset(kept))
        self.assertEqual(coverage["logical_targets_mapped"], 1)

    def test_a_name_mismatch_on_that_key_maps_nothing(self) -> None:
        # Xbox stores ten 64x64 digits per kit where PS2 has one atlas, so the
        # chunk matches but no piece does. Reporting unmapped is the answer;
        # pointing a digit at an atlas would be a lie an exporter acts on.
        side = mapper.XboxSide()
        side.containers[(7, 13)] = ("48", "HITX", "0x341ecd96")
        targets = {"nfl2k5.uniform.00h0.digit.jersey.0": [(7, 13)]}
        ps2 = {("0x341ecd96", 13): [(0, "JERSEY_NUMBERS", ("aa-bb-00004013.png",))]}
        entries, detail = mapper.logical_uniform_rows(side, targets, {}, ps2)
        self.assertEqual(entries, [])
        coverage, _per_selector = mapper.logical_coverage(detail, {})
        self.assertEqual(coverage["logical_targets_mapped"], 0)
        self.assertEqual(
            coverage["by_component"]["digit.jersey.0"]["no_matching_texture"], 1)

    def test_the_structural_components_are_the_digits_and_the_nameplate(self) -> None:
        self.assertEqual(len(mapper.STRUCTURAL_COMPONENTS), 31)
        self.assertIn("nameplate", mapper.STRUCTURAL_COMPONENTS)
        self.assertIn("digit.jersey.0", mapper.STRUCTURAL_COMPONENTS)
        self.assertNotIn("torso", mapper.STRUCTURAL_COMPONENTS)
        self.assertEqual(mapper.MAPPABLE_COMPONENTS_PER_SET, 8)

    def test_a_report_row_names_its_selector_however_it_spells_it(self) -> None:
        # The team-select inventory's own `selector` field is a different
        # string entirely, and variants run past nine.
        self.assertEqual(mapper._selector_of(
            {"selector": {"asset_code": "00", "side": "A", "variant": 0}}), "00A0")
        self.assertEqual(mapper._selector_of(
            {"selector": "unif:01:away:10:256", "uniform_package": "01A10.IFF"}),
            "01A10")
        self.assertEqual(mapper._selector_of({"selector": "unif:00:away:0:256"}), "")

    def test_a_selector_with_no_pieces_is_not_counted_as_mappable(self) -> None:
        side = self._side({})
        selectors = {100: {"abbreviation": "DET", "team": "Detroit Lions",
                           "side": "A", "style": "Current", "selector": "00A0"}}
        per_team, per_selector = mapper.uniform_coverage(side, selectors, set())
        self.assertEqual(per_team, {})
        self.assertEqual(per_selector, {})

    def test_selectors_load_from_the_shipped_sharing_report(self) -> None:
        report = (_REPO_ROOT / "reports" / "assets"
                  / "uniform_texture_sharing.v2.json")
        if not report.exists():
            self.skipTest("the uniform sharing report is not in this checkout")
        selectors = mapper.load_uniform_selectors(str(report))
        self.assertEqual(len(selectors), 634)
        self.assertTrue(all(isinstance(key, int) for key in selectors))
        self.assertIn("DET", {row["abbreviation"] for row in selectors.values()})


class PackAuditIntegrationTests(unittest.TestCase):
    """A pack carrying our manifest must satisfy the shipped audit tool."""

    def test_a_synthetic_pack_reports_xbox_mapping_ready(self) -> None:
        entries = []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "pack"
            replacements = root / "textures" / "SLUS-20919" / "replacements"
            replacements.mkdir(parents=True)
            for index, (tex0, clut) in enumerate(
                    ((0x1234ABCD, 0xFEDC), (0xAB, 0x1), (0x99887766554433, 0x2))):
                name = mapper.replacement_name(
                    tex0, clut, mapper.texture_bits(mapper.PSMT8, 6, 5, 1))
                (replacements / name).write_bytes(_tiny_png())
                entries.append({"pcsx2_png": name,
                                "xbox_asset_id": "p8:%d:asset%d" % (index, index)})
            document = {
                "schema": audit.MAPPING_SCHEMA,
                "disc": {"serial": "SLUS-20919", "boot_sha256": "b" * 64,
                         "content_sha256": "c" * 64},
                "emulator": dict(mapper.EMULATOR),
                "method": mapper.METHOD,
                "generated": "2026-01-01T00:00:00Z",
                "counts": {"entries": len(entries)},
                "entries": entries,
            }
            mapper.write_json(str(root / audit.MAPPING_MANIFEST), document)
            report = audit.audit(root)
        self.assertTrue(report["xbox_mapping_ready"], report["blocking_reasons"])
        self.assertEqual(report["blocking_reasons"], [])
        self.assertEqual(report["summary"]["mapping_entry_count"], len(entries))
        self.assertEqual(report["summary"]["canonical_pcsx2_hash_png_count"],
                         len(entries))
        self.assertTrue(report["serial_directory_present"])

    def test_an_extra_key_in_an_entry_is_refused_by_the_audit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "pack"
            (root / "textures").mkdir(parents=True)
            name = mapper.replacement_name(1, 2, 0x5DD3)
            (root / "textures" / name).write_bytes(_tiny_png())
            mapper.write_json(str(root / audit.MAPPING_MANIFEST), {
                "schema": audit.MAPPING_SCHEMA,
                "entries": [{"pcsx2_png": name, "xbox_asset_id": "p8:1:x",
                             "note": "provenance does not belong here"}],
            })
            with self.assertRaises(audit.PackAuditError):
                audit.audit(root)


@unittest.skipUnless(_MANIFEST.exists(), "the manifest has not been built yet")
class ShippedManifestTests(unittest.TestCase):
    """The committed manifest is data, and data gets checked like code."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(_MANIFEST.read_text(encoding="utf-8"))

    def test_no_filename_is_claimed_by_two_xbox_assets(self) -> None:
        # The invariant the export service turns into "ambiguous". A manifest
        # that breaks it does not merely lose the contested row -- it makes
        # every target that touches the row unexportable.
        owners: dict = {}
        for entry in self.document["entries"]:
            owners.setdefault(entry["pcsx2_png"], set()).add(
                entry["xbox_asset_id"])
        contested = {name: sorted(ids) for name, ids in owners.items()
                     if len(ids) > 1}
        self.assertEqual(contested, {})
        self.assertEqual(len(owners), len(self.document["entries"]))

    def test_the_logical_uniform_ids_are_the_studio_catalog_shape(self) -> None:
        # `nfl2k5.uniform.{selector}.{component}`, lowercased selector, as
        # `nfl2k5_uniform_catalog._assets_for_seed` builds it. A row the studio
        # cannot name is a row no edit ever reaches.
        logical = sorted({entry["xbox_asset_id"]
                          for entry in self.document["entries"]
                          if entry["xbox_asset_id"].startswith(
                              mapper.LOGICAL_PREFIX)})
        self.assertTrue(logical, "the manifest carries no logical uniform rows")
        for asset_id in logical:
            selector, _, component = asset_id[
                len(mapper.LOGICAL_PREFIX):].partition(".")
            self.assertRegex(selector, r"^[0-9a-z]{2}[ah][0-9]{1,2}$", asset_id)
            self.assertTrue(component, asset_id)
            self.assertNotIn(component, mapper.STRUCTURAL_COMPONENTS, asset_id)

    def test_it_passes_the_audit_tools_schema_check(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / audit.MAPPING_MANIFEST).write_bytes(_MANIFEST.read_bytes())
            present, count, digest = audit._mapping_manifest(root)
        self.assertTrue(present)
        self.assertEqual(count, len(self.document["entries"]))
        self.assertEqual(len(digest), 64)

    def test_provenance_names_the_disc_the_emulator_and_the_method(self) -> None:
        self.assertEqual(self.document["disc"]["serial"], "SLUS-20919")
        self.assertEqual(len(self.document["disc"]["boot_sha256"]), 64)
        self.assertEqual(len(self.document["disc"]["content_sha256"]), 64)
        self.assertEqual(self.document["emulator"], dict(mapper.EMULATOR))
        self.assertEqual(self.document["method"], "hop1/v5")
        self.assertTrue(self.document["generated"].endswith("Z"))

    def test_every_filename_is_canonical_and_every_id_namespaced(self) -> None:
        for entry in self.document["entries"]:
            self.assertIsNotNone(
                audit.PCSX2_HASH_NAME.fullmatch(entry["pcsx2_png"]),
                entry["pcsx2_png"])
            self.assertTrue(entry["xbox_asset_id"].startswith(
                ("p8:", "tset:", "nfl2k5.")), entry["xbox_asset_id"])

    def test_no_png_is_claimed_by_two_different_physical_assets(self) -> None:
        # A PNG legitimately appears twice: once under its physical texture id
        # and once under the logical uniform target that composes it. What must
        # never happen is one PNG claimed by two different *textures*, which
        # would mean a fanned-out row reached the manifest.
        physical = [entry["pcsx2_png"] for entry in self.document["entries"]
                    if not entry["xbox_asset_id"].startswith("nfl2k5.uniform.")]
        self.assertEqual(len(physical), len(set(physical)))

    def test_no_entry_is_duplicated(self) -> None:
        pairs = [(entry["pcsx2_png"], entry["xbox_asset_id"])
                 for entry in self.document["entries"]]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_logical_uniform_rows_are_present_and_counted(self) -> None:
        logical = [entry for entry in self.document["entries"]
                   if entry["xbox_asset_id"].startswith("nfl2k5.uniform.")]
        self.assertTrue(logical, "a uniform edit carries a logical target id, "
                                 "so the manifest must key on them too")
        self.assertEqual(self.document["counts"]["logical_uniform_entries"],
                         len(logical))
        self.assertEqual(self.document["counts"]["physical_entries"],
                         len(self.document["entries"]) - len(logical))
        coverage = self.document["counts"]["logical_uniform_coverage"]
        self.assertEqual(coverage["logical_targets"],
                         mapper.UNIFORM_SET_COUNT
                         * mapper.UNIFORM_COMPONENTS_PER_SET)
        self.assertEqual(sorted(coverage["structurally_unmappable_components"]),
                         sorted(mapper.STRUCTURAL_COMPONENTS))
        self.assertTrue(coverage["structurally_unmappable_reason"])

    def test_every_shipped_name_carries_the_classic_tcc_bit(self) -> None:
        for entry in self.document["entries"]:
            bits, _clut = mapper.parse_replacement_name(entry["pcsx2_png"])
            self.assertTrue(bits & 0x4000,
                            "%s does not set bit 14" % entry["pcsx2_png"])

    def test_the_counts_block_agrees_with_the_entries(self) -> None:
        self.assertEqual(self.document["counts"]["entries"],
                         len(self.document["entries"]))
        self.assertEqual(self.document["counts"]["textures_scanned"],
                         _RETAIL_TEXTURES)
        self.assertEqual(self.document["counts"]["png_full_identity"],
                         _RETAIL_FULL_IDENTITIES)


@unittest.skipUnless(_SIDECAR.exists(), "the sidecar has not been built yet")
class ShippedSidecarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(_SIDECAR.read_text(encoding="utf-8"))

    def test_it_accounts_for_the_pack_corpus(self) -> None:
        reasons = self.document["reasons"]
        proved = self.document["counts"]["png_full_identity"]
        unexplained = reasons["unexplained"]["pngs"]
        tex0_only = reasons["tex0_only"]["pngs"]
        self.assertEqual(proved + unexplained + tex0_only, _PACK_IDENTITIES)

    def test_every_reason_carries_a_sentence_and_a_count(self) -> None:
        for name, reason in self.document["reasons"].items():
            self.assertIn("pngs", reason, name)
            self.assertTrue(reason["reason"], name)

    def test_the_fanout_is_reported_per_namespace(self) -> None:
        namespaces = {name.split(":", 1)[1]
                      for name in self.document["reasons"] if name.startswith("fanout:")}
        self.assertTrue(namespaces <= {"p8", "tset", "scene", "mixed", "unknown"},
                        namespaces)
        self.assertTrue(namespaces)

    def test_the_demo_team_question_is_answered_either_way(self) -> None:
        # The plan expected a fully-mappable kit to exist. Once one Xbox asset
        # per filename is enforced -- which the export service requires -- none
        # does, because a team's era variants share their torso, sleeve, pants
        # and helmet art on the PS2 disc. The sidecar has to say so plainly
        # and still hand WP7 the best kit it has, rather than assert a demo
        # that would plan as ambiguous.
        demo = self.document["demo_team"]
        if demo["chosen"]:
            self.assertIn(demo["chosen"], demo["fully_mappable_teams"])
            self.assertIn(demo["chosen"], demo["dump_teams"])
            self.assertIn(demo["chosen"], demo["fully_mappable_and_witnessable"])
            kit = demo["chosen_kit"]
            self.assertTrue(kit.startswith(demo["chosen"] + "/"), kit)
            row = demo["logical"]["kits"][kit]
            self.assertTrue(row["fully_mappable"])
            self.assertEqual(row["mapped"], row["components"])
            return
        self.assertEqual(demo["chosen_kit"], "")
        self.assertEqual(demo["fully_mappable_and_witnessable"], [])
        self.assertIn("shares", demo["chosen_reason"])
        best = demo["logical"]["best_covered_kit"]
        self.assertTrue(best["kit"], "no kit is named for WP7 to witness")
        self.assertGreater(best["mapped"], 0)
        self.assertLess(best["mapped"], best["components"])
        self.assertEqual(demo["logical"]["kits"][best["kit"]]["mapped"],
                         best["mapped"])

    def test_the_tcc_bit_divergences_are_named_not_just_counted(self) -> None:
        # The reference pack spells a few identities without bit 14. We always
        # publish it set, so the difference has to be visible: if WP7 finds a
        # texture that will not load, this list is the first place to look.
        divergence = self.document["tcc_bit_divergence"]
        self.assertTrue(divergence)
        self.assertEqual(len(divergence),
                         self.document["reasons"]["tcc_bit_divergence"]["pngs"])
        for pack_name, computed in divergence.items():
            pack_bits = int(pack_name.rsplit("-", 1)[1].split(".")[0], 16)
            our_bits = int(computed.rsplit("-", 1)[1].split(".")[0], 16)
            self.assertEqual(our_bits ^ pack_bits, 1 << 14,
                             "%s -> %s differs by more than the TCC bit"
                             % (pack_name, computed))
            self.assertTrue(our_bits & (1 << 14))

    def test_the_physical_view_is_kept_as_supporting_evidence(self) -> None:
        physical = self.document["demo_team"]["physical"]
        self.assertTrue(physical["note"])
        self.assertIn("per_selector", physical)
        self.assertIn("per_team", physical)


@unittest.skipUnless(_NFL2K5_PS2_ISO and _PACK_HASHES and _XBOX_INVENTORY,
                     "set NFL2K5_PS2_ISO, NFL2K5_PACK_HASHES and "
                     "NFL2K5_XBOX_INVENTORY to reproduce the retail run")
class RetailReproductionTests(unittest.TestCase):
    def test_the_disc_reproduces_the_recorded_identity_counts(self) -> None:
        result = mapper.build(_NFL2K5_PS2_ISO, _XBOX_INVENTORY, _PACK_HASHES,
                              jobs=0, limit=0, progress=None)
        self.assertEqual(result["textures_scanned"], _RETAIL_TEXTURES)
        self.assertEqual(len(result["proved"]), _RETAIL_FULL_IDENTITIES)
        self.assertEqual(result["bits_mismatched"], 0)


if __name__ == "__main__":
    unittest.main()
