"""Hair styles (b775 job hs1): added hair models in new slots, proved offline.

* the catalogue, the shipped geometry, art and pins agree, and the roster field labels match;
* the two player scenes grow by exactly the added materials, submeshes, push words, vertices and names: removing the
  insertions gives back every retail byte except the relocated pointer fields and three counts, ``strip_scene``
  restores the input exactly, and the game's own scene loader (0x45BC0, run under Unicorn) relocates the grown scene
  to the original's result moved by the growth;
* outer 3 keeps every other resource byte for byte and appends the nine hair textures (they read back as the art);
* the executable owner is placed last (no other owner moves), and the patched player builder block (run under
  Unicorn) leaves style 0 exactly retail, forces the dreads for style 1, shows the right added mesh and texture for
  styles 2..12, shows nothing for style 13 and for hi_body or an ungrown scene;
* the 2026 assignments touch only +0x0D and every one carries a source;
* the disc step grows pack 0 on a synthetic image and replays as already applied.

Nothing here is an in-game result. The classes that need the private USA data skip without it.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")]

from mod_editor.core import nfl2k5_hair_styles as hs  # noqa: E402
from mod_editor.core import nfl2k5_models as models  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
GAME = EXTRACTION / "ESPN NFL 2K5 (USA)"
PACK0 = GAME / "vc_53450030" / "0"
XBE = GAME / "default.xbe"
INVENTORY = ROOT / "reports" / "assets" / "nfl2k5_resource_chunks_v2.json"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_CS = importlib.util.find_spec("capstone") is not None
EDITS = ROOT / "data" / "nfl2k5_hair_styles_2026_roster_edits.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_OUTER3 = None


def retail_outer3() -> bytes:
    global _OUTER3
    if _OUTER3 is None:
        if not (PACK0.is_file() and INVENTORY.is_file()):
            raise unittest.SkipTest("private USA pack 0 required")
        from nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACK0.parents[1])
        src = models.ModelSource(PACK0, INVENTORY)
        entry = src.archive.entries[hs.OUTER]
        _OUTER3 = src._outer.read_entry_range(src.archive, entry, 0, entry.size)
    return _OUTER3


def retail_xbe() -> bytes:
    if not XBE.is_file():
        raise unittest.SkipTest("private USA default.xbe required")
    data = XBE.read_bytes()
    if sha(data) != RETAIL_SHA256:
        raise unittest.SkipTest("the USA default.xbe pin differs")
    return data


def scene(key: str) -> bytes:
    outer3 = retail_outer3()
    chunk = hs._chunks(outer3)[models.parse_model_key(key)[1]]
    return hs.decode_span(hs._chunk_span(outer3, chunk))


class CatalogueTests(unittest.TestCase):
    """Runs everywhere."""

    def test_styles_meshes_textures_and_labels(self):
        self.assertEqual([s.index for s in hs.STYLES], list(range(2, hs.MAX_STYLE + 1)))
        self.assertEqual(len({s.key for s in hs.STYLES}), len(hs.STYLES))
        self.assertTrue(all(s.mesh in hs.MESHES and s.texture in hs.TEXTURES for s in hs.STYLES))
        self.assertEqual(set(hs.MESHES), {s.mesh for s in hs.STYLES})
        self.assertEqual(set(hs.TEXTURES), {s.texture for s in hs.STYLES})
        self.assertEqual(hs.STYLE_LABELS, rr.HAIR_STYLES)
        self.assertEqual(len(hs.STYLE_LABELS), 16)
        self.assertEqual(rr.ENUMS["hair_style"], rr.HAIR_STYLES)
        self.assertEqual(hs.NONE_STYLE, hs.MAX_STYLE + 1)

    def test_shipped_data_agrees_with_pins(self):
        self.assertTrue(hs.available())
        pins = hs.load_pins()
        self.assertEqual(set(pins["textures"]), set(hs.TEXTURES))
        document = hs.load_geometry()
        for key in hs.KEYS:
            parts = document["scenes"][key]["parts"]
            self.assertEqual(set(parts), set(hs.MESHES))
            for mesh in hs.MESHES:
                records, strip = hs._part(document, key, mesh)
                stride = sum(document["scenes"][key]["strides"])
                self.assertEqual(len(records) % stride, 0)
                self.assertLess(max(strip), len(records) // stride)
                # polycount in line with the retail dreads (80 close-up, 52 distant vertices): at most 176 / 64
                self.assertLessEqual(len(records) // stride, 176 if key == hs.HI else 64)

    def test_roster_field_is_the_low_nibble_of_0x0d(self):
        record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE))
        record.set("hair_style", 11)
        record.set("unknown_0d_high", 6)
        self.assertEqual(record.encode()[0x0D], 0x6B)
        self.assertEqual(rr.PlayerRecord.decode(record.encode()).get("hair_style"), 11)
        self.assertEqual(rr.field_coverage()[0x0D], 8)

    def test_code_layout_and_table(self):
        code = hs.code_for(0x14EB200)
        self.assertEqual(len(code), hs.CODE_SIZE)
        table = code[hs.TABLE_OFFSET:hs.NAMES_OFFSET]
        for style in hs.STYLES:
            slot, pointer = struct.unpack_from("<B3xI", table, 8 * style.index)
            self.assertEqual(slot, hs.MESHES.index(style.mesh))
            at = pointer - 0x14EB200
            name = code[at:code.index(b"\0\0", at) + 1].decode("utf-16le").rstrip("\0")
            self.assertEqual(name, hs.texture_name(style.texture))
        self.assertEqual(hs.REQUESTS, (("nfl2k5_hair_styles", "code", 768, 16),))
        # b776-ai2, b776-pa2, b776-ns1, b777-ol1 and b777-qb3 code owners follow the hair styles (int7 order; none moves this allocation)
        self.assertEqual(space.LATE_OWNERS[-10:], (hs.OWNER, "nfl2k5_cpu_qb_reads", "nfl2k5_db_ball_play", "nfl2k5_play_art_routes", "nfl2k5_team_number_scale", "nfl2k5_run_blocking", "nfl2k5_qb_accuracy", "nfl2k5_formation_art_spacing", "nfl2k5_force_out", "nfl2k5_star_retention"))  # b778-fo1 last

    def test_assignments_only_set_hair_style_and_carry_sources(self):
        document = json.loads(EDITS.read_text(encoding="utf-8"))
        rr.read_edits(document)
        keys = set()
        for edit in document["edits"]:
            self.assertEqual(set(edit["fields"]), {"hair_style"})
            self.assertIn(edit["fields"]["hair_style"], range(1, hs.NONE_STYLE + 1))
            self.assertTrue(edit["research"]["sources"])
            self.assertIn(edit["research"]["confidence"], ("high", "medium"))
            key = (edit["pool"], edit["index"])
            self.assertNotIn(key, keys)
            keys.add(key)
        by_name = {(e["first"], e["last"]): e["fields"]["hair_style"] for e in document["edits"]}
        self.assertEqual(by_name[("Trevor", "Lawrence")], 4)
        self.assertEqual(by_name[("Cam", "Ward")], 3)
        self.assertEqual(by_name[("Isaac", "TeSlaa")], 4)


class AssignmentPlanTests(unittest.TestCase):
    """The build step writes the 2026 assignments only into a roster that holds those players (runs everywhere)."""

    class Doc:
        def __init__(self, rows, rename=0, preset=None):
            from types import SimpleNamespace
            self.players = []
            for k, row in enumerate(rows):
                record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE))
                if preset is not None and k == 0:
                    record.set("hair_style", preset)
                last = "Someone" if k < rename else row["last"]
                self.players.append(SimpleNamespace(pool=row["pool"], index=row["index"], last=last,
                                                    offset=0x54 * k, record=record))

    def test_league_roster_gets_every_listed_player(self):
        rows = hs.load_assignments()
        plan = hs.plan_assignments(self.Doc(rows))
        self.assertTrue(plan["league"])
        self.assertEqual(len(plan["writes"]), len(rows))
        self.assertTrue(all(offset % 0x54 == 0x0D for offset, _style, _name in plan["writes"]))

    def test_other_rosters_and_user_choices_are_left_alone(self):
        rows = hs.load_assignments()
        self.assertFalse(hs.plan_assignments(self.Doc(rows, rename=len(rows) // 2))["league"])
        plan = hs.plan_assignments(self.Doc(rows, preset=hs.NONE_STYLE if rows[0]["fields"]["hair_style"] != hs.NONE_STYLE else 2))
        self.assertEqual(len(plan["kept"]), 1)


@unittest.skipUnless(PACK0.is_file(), "private USA pack 0 required")
class SceneTests(unittest.TestCase):
    def test_growth_keeps_every_retail_byte_and_round_trips(self):
        fields = hs.load_pointer_fields()
        for key in hs.KEYS:
            with self.subTest(key=key):
                original = scene(key)
                self.assertEqual(hs.scene_state(key, original), "retail")
                grown, receipt = hs.grow_scene(key, original)
                self.assertEqual(hs.scene_state(key, grown), "grown")
                self.assertEqual(hs.strip_scene(key, grown), original)
                self.assertEqual(hs.retail_shaped(key, grown), original)
                # remove the insertions: only pointer fields and the three counts may differ from retail
                pieces, cursor, shift = [], 0, 0
                for row in receipt["inserts"]:
                    pieces.append(grown[cursor:row["at"] + shift])
                    cursor = row["at"] + shift + row["bytes"]
                    shift += row["bytes"]
                pieces.append(grown[cursor:])
                folded = b"".join(pieces)
                self.assertEqual(len(folded), len(original))
                lay = hs.layout(key, original)
                allowed = set(fields[key]) | {lay.descriptor + 0x1C, lay.shape + 0x4C, lay.shape + 0x54}
                changed = {o - o % 4 for o in range(len(original)) if folded[o] != original[o]}
                self.assertTrue(changed <= allowed, sorted(changed - allowed)[:8])
                # the retail dreads keep their material, submesh and vertices
                names = hs.layout(key, grown).names
                self.assertIn("HAIR_dreads", names.values())
                self.assertEqual([names[hs.RETAIL[key]["materials"] + k] for k in range(hs.K)],
                                 [hs.material_name(m) for m in hs.MESHES])

    def test_grown_scene_parses_with_every_index_in_bounds(self):
        inventory = models._tools_module("nfl_scne_inventory")
        probe = models._tools_module("nfl_scene_probe")
        for key in hs.KEYS:
            grown, receipt = hs.grow_scene(key, scene(key))
            outer, chunk = models.parse_model_key(key)
            record = probe.ResourceRecord(outer, "resource-bytes", 0, chunk, 0, "SCNE", 0, len(grown), 0, 0xFEEDBEEF, 0,
                                          source="resource-bytes")
            parsed = inventory.parse_scene(outer * 100_000 + chunk, record, grown, {})[0]
            added = [s for s in parsed["submeshes"] if s["material_name"] in {hs.material_name(m) for m in hs.MESHES}]
            self.assertEqual(len(added), hs.K)
            self.assertTrue(all(s["all_vertex_references_in_bounds"] for s in parsed["submeshes"]))
            self.assertEqual(parsed["shapes"][0]["vertex_count"], hs.RETAIL[key]["vertices"] + receipt["added_vertices"])

    @unittest.skipUnless(HAVE_UC and XBE.is_file(), "unicorn and the USA default.xbe required")
    def test_game_loader_relocates_the_grown_scene_like_the_original(self):
        loader = Loader(retail_xbe())
        for key in hs.KEYS:
            original = scene(key)
            grown, receipt = hs.grow_scene(key, original)
            a, base_a = loader.relocate(original)
            b, base_b = loader.relocate(grown)
            inserts = [(r["at"], r["bytes"]) for r in receipt["inserts"]]
            shift = lambda o: o + sum(n for at, n in inserts if at <= o)  # noqa: E731
            lay = hs.layout(key, original)
            counts = {lay.descriptor + 0x1C, lay.shape + 0x4C, lay.shape + 0x54, lay.shape + 0x58}
            straddle = {at - at % 4 for at, _n in inserts if at % 4}
            moved = mismatched = 0
            for o in range(0, len(original) - 3, 4):
                if o in counts or o in straddle:
                    continue
                va = struct.unpack_from("<I", a, o)[0]
                vb = struct.unpack_from("<I", b, shift(o))[0]
                if base_a <= va <= base_a + len(original) and va != struct.unpack_from("<I", original, o)[0]:
                    want = base_b + shift(va - base_a)
                    moved += 1
                else:
                    want = va
                mismatched += vb != want
            self.assertEqual(mismatched, 0, key)
            self.assertEqual(moved, len(hs.load_pointer_fields()[key]) + 2, key)   # + the two node links the loader computes


class Loader:
    """The game's scene loader (0x45BC0 -> 0x2F140 and its record relocators) under Unicorn."""

    SCENE = 0x03000000

    def __init__(self, xbe: bytes):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        self.xbe = xbe
        self.Uc, self.arch, self.mode = Uc, UC_ARCH_X86, UC_MODE_32

    def relocate(self, decoded: bytes) -> tuple[bytes, int]:
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP
        mu = self.Uc(self.arch, self.mode)
        map_xbe(mu, self.xbe)
        block = struct.pack("<4s7I", b"SCNE", 0, len(decoded), 0, 0, 0, 0, 0) + decoded
        mu.mem_map(self.SCENE, (len(block) + 0xFFFF) & ~0xFFFF)
        mu.mem_write(self.SCENE, block)
        mu.mem_map(0x02E00000, 0x1000)
        mu.mem_map(0x02EF0000, 0x20000)
        mu.mem_write(0x02F00000 - 4, struct.pack("<I", 0x02E00000))
        mu.reg_write(UC_X86_REG_ESP, 0x02F00000 - 4)
        mu.reg_write(UC_X86_REG_ECX, self.SCENE)
        mu.emu_start(0x45BC0, 0x02E00000, count=50_000_000)
        return bytes(mu.mem_read(self.SCENE + 32, len(decoded))), self.SCENE + 32


def map_xbe(mu, data: bytes) -> None:
    base = struct.unpack_from("<I", data, 0x104)[0]
    count = struct.unpack_from("<I", data, 0x11C)[0]
    table = struct.unpack_from("<I", data, 0x120)[0] - base
    headers = struct.unpack_from("<I", data, 0x108)[0]
    pages = set(range(base >> 12, (base + headers + 0xFFF) >> 12))
    sections = []
    for i in range(count):
        _flags, va, vsize, raw, rsize = struct.unpack_from("<IIIII", data, table + 56 * i)
        pages |= set(range(va >> 12, (va + max(vsize, rsize) + 0xFFF) >> 12))
        sections.append((va, raw, min(rsize, vsize)))
    runs = []
    for page in sorted(pages):
        if runs and runs[-1][1] == page:
            runs[-1][1] = page + 1
        else:
            runs.append([page, page + 1])
    for lo, hi in runs:
        mu.mem_map(lo << 12, (hi - lo) << 12)
    mu.mem_write(base, data[:headers])
    for va, raw, size in sections:
        mu.mem_write(va, data[raw:raw + size])


@unittest.skipUnless(PACK0.is_file(), "private USA pack 0 required")
class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = retail_outer3()
        cls.after, cls.receipt = hs.compile_collection(cls.before)

    def test_states_and_replay(self):
        self.assertEqual(hs.collection_status(self.before), "retail")
        self.assertEqual(hs.collection_status(self.after), "applied")
        self.assertEqual(hs.compile_collection(self.after)[1]["status"], "already_applied")
        self.assertLess(self.receipt["memory_growth"], 96 * 1024)

    def test_every_other_resource_is_byte_identical_and_textures_are_appended(self):
        a, b = hs._chunks(self.before), hs._chunks(self.after)
        self.assertEqual(len(b), len(a) + len(hs.TEXTURES))
        for x, y in zip(a, b):
            if models.model_key(hs.OUTER, x.index) in hs.KEYS:
                self.assertEqual(hs.retail_shaped(models.model_key(hs.OUTER, x.index),
                                                  hs.decode_span(hs._chunk_span(self.after, y))),
                                 hs.decode_span(hs._chunk_span(self.before, x)))
                continue
            self.assertEqual(hs._chunk_span(self.before, x), hs._chunk_span(self.after, y), x.index)
        textures = hs._texture_spans(self.after)
        tx = models._tools_module("nfl_txtr")
        for key, (_index, span) in textures.items():
            chunk = tx.parse_chunks(span)[0]
            out, _ = tx.decode_chunk(span, chunk)
            info = tx.parse_texture(out, chunk)
            self.assertEqual(info.name, hs.texture_name(key))
            self.assertEqual(tx.texture_to_rgba(out, chunk, info), hs.art_rgba(key))

    def test_modern_helmets_still_judges_its_own_bytes(self):
        from mod_editor.core import nfl2k5_modern_helmets as helmets
        self.assertEqual(helmets.collection_status(self.after), helmets.collection_status(self.before))

    def test_strip_collection_gives_back_the_retail_resources(self):
        stripped = hs.strip_collection(self.after)
        self.assertEqual(hs.collection_status(stripped), "retail")
        a, b = hs._chunks(self.before), hs._chunks(stripped)
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            self.assertEqual(hs.decode_span(hs._chunk_span(self.before, x)), hs.decode_span(hs._chunk_span(stripped, y)))


@unittest.skipUnless(XBE.is_file(), "private USA default.xbe required")
class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = hs.apply(cls.retail)

    def test_states_idempotence_and_hook(self):
        self.assertEqual(hs.status(self.retail), "retail")
        self.assertEqual(hs.status(self.patched), "applied")
        self.assertEqual(hs.apply(self.patched)[0], self.patched)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(XbeImage(self.retail).read(hs.HOOK_VA, len(hs.HOOK_RETAIL)), hs.HOOK_RETAIL)
        va = hs.allocation(self.patched)["va"]
        self.assertEqual(XbeImage(self.patched).read(hs.HOOK_VA, 5), b"\xe9" + struct.pack("<i", va - hs.HOOK_VA - 5))

    def test_late_owner_moves_no_other_owner(self):
        base, _ = space.apply(self.retail, (("nfl2k5_honors", "code", 2560, 16), ("nfl2k5_honors", "data", 16, 16)),
                              scaleout=True)
        grown, _ = hs.apply(base)
        before = {(r["owner"], r["kind"]): r["va"] for r in space.layout(base)["allocations"]}
        after = {(r["owner"], r["kind"]): r["va"] for r in space.layout(grown)["allocations"]}
        self.assertEqual({k: after[k] for k in before}, before)
        self.assertIn((hs.OWNER, "code"), after)

    @unittest.skipUnless(HAVE_UC, "unicorn required")
    def test_patched_builder_block_under_unicorn(self):
        emu = Builder(self.patched)
        retail = Builder(self.retail)
        textures = {hs.texture_name(k): 0x7000 + i for i, k in enumerate(hs.TEXTURES)}
        lo, hi = hs.ROWS[0], hs.ROWS[2]
        for dreads in (0, 1):
            for row, count in ((0, lo), (2, hi), (1, 90)):
                self.assertEqual(emu.run(0, dreads, row, count, textures), retail.run(0, dreads, row, count, textures))
                self.assertEqual(emu.run(1, dreads, row, count, textures), [(25, 0xD7EAD)])
                self.assertEqual(emu.run(hs.NONE_STYLE, dreads, row, count, textures), [])
                for reserved in (14, 15):
                    self.assertEqual(emu.run(reserved, dreads, row, count, textures),
                                     retail.run(0, dreads, row, count, textures))
            for style in hs.STYLES:
                slot = hs.MESHES.index(style.mesh)
                handle = textures[hs.texture_name(style.texture)]
                self.assertEqual(emu.run(style.index, dreads, 0, lo, textures), [(lo - hs.K + slot, handle)])
                self.assertEqual(emu.run(style.index, dreads, 2, hi, textures), [(hi - hs.K + slot, handle)])
                self.assertEqual(emu.run(style.index, dreads, 1, 90, textures), [])        # hi_body: no hair
                self.assertEqual(emu.run(style.index, dreads, 0, lo - hs.K, textures), [])  # ungrown scene
                self.assertEqual(emu.run(style.index, dreads, 0, lo, {}), [])             # texture missing


class Builder:
    """0x8F5B9 -> 0x8F5E6 of the player builder with a fake record, instance and frame; 0x449E0 is stubbed by name."""

    REC, INST, MATS, STACK, FRAME = 0x03000000, 0x03100000, 0x03200000, 0x03400000, 0x033F0000

    def __init__(self, xbe: bytes):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_EIP
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_32)
        map_xbe(mu, xbe)
        for at in (self.REC, self.INST, self.MATS):
            mu.mem_map(at, 0x40000)
        mu.mem_map(self.STACK - 0x20000, 0x30000)
        self.textures = {}

        def lookup(uc, _address, _size, _user):
            esp = uc.reg_read(UC_X86_REG_ESP)
            ret, name = struct.unpack("<II", uc.mem_read(esp, 8))
            text = bytes(uc.mem_read(name, 80)).decode("utf-16le").split("\0")[0]
            uc.reg_write(UC_X86_REG_EAX, self.textures.get(text, 0))
            uc.reg_write(UC_X86_REG_ESP, esp + 8)
            uc.reg_write(UC_X86_REG_EIP, ret)
        mu.hook_add(UC_HOOK_CODE, lookup, begin=hs.FIND_RESOURCE, end=hs.FIND_RESOURCE)

    def run(self, style, dreads, row, count, textures):
        from unicorn.x86_const import (UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI,
                                       UC_X86_REG_ESP)
        mu = self.mu
        self.textures = dict(textures)
        for at in (self.REC, self.INST, self.MATS):
            mu.mem_write(at, bytes(0x40000))
        record = bytearray(0x54)
        record[0x0D], record[0x18] = style, dreads
        mu.mem_write(self.REC, bytes(record))
        mats = bytearray(0x80 * count)
        for i in range(count):
            struct.pack_into("<I", mats, 0x80 * i + 8, 0x80000001)
            struct.pack_into("<I", mats, 0x80 * i + 0x30, 0x1111)
        mu.mem_write(self.MATS, bytes(mats))
        mu.mem_write(self.INST + 0x1C, struct.pack("<II", count, self.MATS))
        mu.mem_write(self.FRAME + 8, struct.pack("<I", row))
        mu.mem_write(self.FRAME + 0x10, struct.pack("<I", 0))
        mu.mem_write(0xB6532D, bytes(3 * 0x3E))
        mu.mem_write(0xB6532D + 0x3E * row, bytes([25]))
        mu.mem_write(0xB655A4, struct.pack("<I", 0xD7EAD))
        for reg, value in ((UC_X86_REG_EBX, self.REC), (UC_X86_REG_EDI, self.INST), (UC_X86_REG_EBP, self.FRAME),
                           (UC_X86_REG_ESI, 0), (UC_X86_REG_ESP, self.STACK)):
            mu.reg_write(reg, value)
        mu.emu_start(hs.HOOK_VA, hs.HOOK_END, count=100_000)
        assert mu.reg_read(UC_X86_REG_EIP) == hs.HOOK_END and mu.reg_read(UC_X86_REG_ESP) == self.STACK
        assert (mu.reg_read(UC_X86_REG_EBX), mu.reg_read(UC_X86_REG_EDI), mu.reg_read(UC_X86_REG_EBP)) == \
            (self.REC, self.INST, self.FRAME)
        after = bytes(mu.mem_read(self.MATS, 0x80 * count))
        shown = []
        for i in range(count):
            flags, texture = struct.unpack_from("<I", after, 0x80 * i + 8)[0], struct.unpack_from("<I", after, 0x80 * i + 0x30)[0]
            if (flags, texture) != (0x80000001, 0x1111):
                assert flags == 0x80000000, "a shown material keeps its other flags"
                shown.append((i, texture))
        return shown


@unittest.skipUnless(PACK0.is_file() and XBE.is_file(), "private USA pack 0 and default.xbe required")
class DiscTests(unittest.TestCase):
    """A ~10 MiB synthetic XISO: the real outer 3 and default.xbe, synthetic neighbouring packs."""

    def fixture(self, path: Path) -> int:
        from nfl2k5_xiso_fixture import dir_node, xiso
        archive = hs._archive()
        outer3, xbe = retail_outer3(), retail_xbe()
        count = 6
        cursor = archive.align_up(0x9C + count * 12)
        entries = []
        for i in range(count - 1):
            length = len(outer3) if i == hs.OUTER else 32
            entries.append((hs.OUTER_ID if i == hs.OUTER else i + 1, length, cursor // 2048))
            cursor = archive.align_up(cursor + length)
        sizes = [cursor] + [2048] * 14 + [0x10000]
        entries.append((0x5150, sum(sizes[1:]), cursor // 2048))
        table = struct.pack("<3I36I", count, 0, 16, *[s // 2048 for s in sizes], *([0] * 20))
        table += b"".join(struct.pack("<3I", *e) for e in entries)
        sector, sectors = 64, []
        for size in sizes:
            sectors.append(sector)
            sector += size // 2048
        xsector = sector
        neighbour = xsector + (len(xbe) + 2047) // 2048
        sub = dir_node([(s, n, 0x80, name) for s, n, name in zip(sectors, sizes, "0123456789ABCDEF")])
        root = dir_node([(xsector, len(xbe), 0x80, "default.xbe"), (34, len(sub), 0x10, "vc_53450030"),
                         (neighbour, 8, 0x80, "neighbor")])
        with path.open("wb") as f:
            f.seek(0x10000)
            f.write(xiso.XDVDFS_MAGIC + struct.pack("<II", 33, len(root)))
            f.seek(0x107EC)
            f.write(xiso.XDVDFS_MAGIC)
            f.seek(33 * 2048)
            f.write(root)
            f.seek(34 * 2048)
            f.write(sub)
            f.seek(sectors[0] * 2048)
            f.write(table)
            f.seek(sectors[0] * 2048 + entries[hs.OUTER][2] * 2048)
            f.write(outer3)
            f.write(b"\x9f" * (archive.align_up(len(outer3)) - len(outer3)))
            f.seek(xsector * 2048)
            f.write(xbe)
            f.seek(neighbour * 2048)
            f.write(b"KEEPTHIS")
        return neighbour * 2048

    def test_pack0_growth_status_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (Path(tmp) / "fixture.iso").resolve()
            neighbour = self.fixture(path)
            self.assertEqual(hs.image_status(path), "retail")
            receipt = hs.apply_to_image(path)
            self.assertEqual(receipt["status"], "applied")
            self.assertEqual(hs.resource_status(path), "applied")
            self.assertEqual(hs.image_status(path), "partial")      # the executable owner is the other half
            with path.open("rb") as f:
                f.seek(neighbour)
                self.assertEqual(f.read(8), b"KEEPTHIS")
            archive = hs._archive()
            with archive.Disc(path, descriptors=()) as disc:
                entry = disc.archive_entries[hs.OUTER]
                self.assertEqual(entry.size, len(retail_outer3()) + receipt["growth"])
            self.assertEqual(hs.apply_to_image(path)["status"], "already_applied")


    def test_final_gate_refuses_an_image_that_lost_half_of_the_hair(self):
        """b778-hr3: the build's publication gate re-reads the finished image."""
        with tempfile.TemporaryDirectory() as tmp:
            path = (Path(tmp) / "fixture.iso").resolve()
            self.fixture(path)
            with self.assertRaisesRegex(hs.HairStylesError, "'retail'"):
                hs.verify_final(path)
            hs.apply_to_image(path)
            with self.assertRaisesRegex(hs.HairStylesError, "'partial'"):
                hs.verify_final(path)      # resources without the executable owner


#: b778-hr3: the released v0.6.1 disc (read only; private, the test skips without it)
V061_DISC = Path(os.environ.get("NFL2K5_V061_DISC",
                                "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 (2026-10-20).xiso.iso"))


class FinalGateTests(unittest.TestCase):
    """b778-hr3: verify_final, the publication gate mod_build runs after every step."""

    def test_roster_loss_after_the_hair_step_is_refused(self):
        lost = {"league": True, "listed": 259, "carried": 258, "lost": ["Trevor Lawrence"]}
        with mock.patch.object(hs, "image_status", return_value="applied"), \
                mock.patch.object(hs, "roster_status", return_value=lost):
            with self.assertRaisesRegex(hs.HairStylesError, "lost the 2026 hair assignments.*Trevor Lawrence"):
                hs.verify_final("image.iso", {"status": "applied"})
            # a user's own league roster (the step skipped the assignments) is not judged by the 2026 list
            self.assertEqual(hs.verify_final("image.iso", {"status": "skipped"}), {"status": "applied"})
            self.assertEqual(hs.verify_final("image.iso"), {"status": "applied"})

    @unittest.skipUnless(V061_DISC.is_file(), "the released v0.6.1 disc is private")
    def test_released_disc_carries_every_assignment_and_a_cleared_byte_is_seen(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        resource = hs.main_roster(V061_DISC)
        status = hs.roster_status(V061_DISC, resource)
        self.assertEqual((status["league"], status["carried"], status["lost"]), (True, 259, []))
        document = rr.RosterDocument(resource[rr.RESOURCE_HEADER_SIZE:], base=0, source="image",
                                     resource_header=resource[:rr.RESOURCE_HEADER_SIZE])
        lawrence = next(p for p in document.players if (p.pool, p.index) == ("primary", 669))
        self.assertEqual(lawrence.last, "Lawrence")
        cleared = bytearray(resource)
        cleared[rr.RESOURCE_HEADER_SIZE + lawrence.offset + 0x0D] &= 0xF0
        status = hs.roster_status(V061_DISC, bytes(cleared))
        self.assertEqual((status["carried"], status["lost"]), (258, ["Trevor Lawrence"]))


# ------------------------------------------------------------------------------------------------ b776 hr2: riding hair
#: the five meshes hr2 leaves alone, byte for byte as b775 shipped them (records | strip, base64)
B775_PARTS = {
    "o3c113": {"long_locs": "aad13afaac2cd953a2548cf825a40a8747d79448c9b6f1b98123ca77dc08382e",
               "afro_puff": "58c0c3ce42b45ce142ad08c570a88a2a337a8d7666b1a0882e3f9d953c421906",
               "braids": "6b8020dc93109b1ff3e611230f7269716e8a8a7b91d01cf9664a0a16bae063b0",
               "bun": "f5becfc08637842c99702f806dd75d1bf67ac5e8983a0be32955a05d1f8e3529",
               "mullet": "ede16e2d7bfbd92c61cc8a8c39471d36e2648cea4c50ae7c89d1e1bce5eeb726"},
    "o3c115": {"long_locs": "4c7432b64d6a6e2ee66a79d31cda54cfb35f4af6565e329037ea0ec0b40e1a9a",
               "afro_puff": "eddb6de13e632fcb532ef97a7a165b0518ba586fb224b00d0141560a0f864874",
               "braids": "fd2d2bebb6e5760c80ab4fd083704bd646b4fead84c909b2db69ab902cb27241",
               "bun": "923d93d2004b152432673a13746383fc31e393229975f5b5b6f7d3ba187d525e",
               "mullet": "a4d5980f6615ec8081b583899dfe3793becadc08e2c7dabdb46a7ba26c31d5db"}}
RIDING = ("long_flow", "short_twists")
#: joints a riding entry may use: hi_head thorax/neck/head; lo_body thorax/neck/head and the two shoulder pads
RIDING_JOINTS = {hs.HI: {0, 1, 2}, hs.LO: {10, 11, 12, 23, 24}}
THORAX = {hs.HI: 0, hs.LO: 10}
HEAD = {hs.HI: 2, hs.LO: 12}
JERSEY = ("UNIF_jersey", "UNIF_sleeve", "PLAYERNAME", "PLAYERNAME_long", "NUMBER_L", "NUMBER_M", "NUMBER_R",
          "NUMBER_shoulder_A_L", "NUMBER_shoulder_A_M", "NUMBER_shoulder_A_R", "NUMBER_shoulder_B_L",
          "NUMBER_shoulder_B_M", "NUMBER_shoulder_B_R")
BODY_FROM_HEAD = (0.0, 33.9, -4.6)


def part_entries(document, key, mesh):
    """Per vertex of a part: its palette entry's [(joint, weight)] (base slots or the part's riding slots)."""
    records, _strip = hs._part(document, key, mesh)
    stride = sum(document["scenes"][key]["strides"])
    base = {slot: [(joint, 1.0)] for _name, (slot, joint) in hs.PALETTE[key].items()}
    extra = {int(slot): [(int(j), float(w)) for j, w in parts] for slot, _entry, parts in
             document["scenes"][key]["parts"][mesh].get("palette", [])}
    out = []
    for v in range(len(records) // stride):
        selector = struct.unpack_from("<h", records, v * stride + document["scenes"][key]["strides"][0] + 4)[0]
        slot = selector // 3
        out.append((selector % 3, base.get(slot) or extra.get(slot)))
    return out


class RidingCatalogueTests(unittest.TestCase):
    """b776 hr2. Runs everywhere."""

    def test_the_other_meshes_keep_their_b775_bytes(self):
        document = hs.load_geometry()
        for key, parts in B775_PARTS.items():
            for mesh, digest in parts.items():
                item = document["scenes"][key]["parts"][mesh]
                self.assertEqual(sha((item["records"] + "|" + item["strip"]).encode()), digest, (key, mesh))
                self.assertNotIn("palette", item)

    def test_riding_palettes_are_well_formed(self):
        document = hs.load_geometry()
        self.assertTrue(all(document["scenes"][key]["parts"][mesh].get("palette") for key, mesh in
                            ((hs.HI, "long_flow"), (hs.LO, "long_flow"), (hs.LO, "short_twists"))))
        for key in hs.KEYS:
            base_slots = {slot for slot, _joint in hs.PALETTE[key].values()}
            for mesh in RIDING:
                with self.subTest(key=key, mesh=mesh):
                    palette = document["scenes"][key]["parts"][mesh].get("palette", [])
                    slots = [int(s) for s, _e, _p in palette]
                    self.assertEqual(len(slots), len(set(slots)))
                    self.assertFalse(set(slots) & base_slots)
                    self.assertTrue(all(0 <= s < models.PALETTE_SLOTS - 1 for s in slots))
                    for _slot, _entry, parts in palette:
                        self.assertTrue({int(j) for j, _w in parts} <= RIDING_JOINTS[key])
                        self.assertAlmostEqual(sum(float(w) for _j, w in parts), 1.0, places=5)
                    for remainder, parts in part_entries(document, key, mesh):
                        self.assertEqual(remainder, 0)
                        self.assertIsNotNone(parts)

    def test_hair_below_the_rim_rides_with_the_thorax(self):
        """Every vertex rides the head (the roots under the helmet) or carries at least a fifth of the thorax, the
        way the lower neck skin and the jersey do; before hr2 the rows on the collar followed the neck alone."""
        document = hs.load_geometry()
        for key in hs.KEYS:
            for mesh in RIDING:
                entries = part_entries(document, key, mesh)
                head = sum(1 for _r, parts in entries if parts == [(HEAD[key], 1.0)])
                thorax = [sum(w for j, w in parts if j == THORAX[key]) for _r, parts in entries]
                self.assertTrue(all(t >= 0.19 or parts == [(HEAD[key], 1.0)]
                                    for t, (_r, parts) in zip(thorax, entries)), (key, mesh))
                self.assertGreater(head, 0)
                self.assertGreater(sum(1 for t in thorax if t >= 0.19), len(entries) // 4, (key, mesh))


@unittest.skipUnless(PACK0.is_file(), "private USA pack 0 required")
class RidingSceneTests(unittest.TestCase):
    """b776 hr2, on the retail scenes."""

    def test_a_scene_whose_blend_differs_is_refused(self):
        original = bytearray(scene(hs.HI))
        lay = hs.layout(hs.HI, original)
        entry = int(hs.load_geometry()["scenes"][hs.HI]["parts"]["long_flow"]["palette"][0][1])
        transforms = struct.unpack_from("<H", original, lay.shape + 0x50)[0]
        at = hs._rel(bytes(original), lay.shape + 0x60) + 0x1C * (entry - transforms)
        struct.pack_into("<f", original, at + 8, 0.75)            # first source weight of that blend
        with self.assertRaises(hs.HairStylesError):
            hs.grow_scene(hs.HI, bytes(original))

    def test_grown_riding_submeshes_carry_their_slots(self):
        document = hs.load_geometry()
        for key in hs.KEYS:
            grown, _receipt = hs.grow_scene(key, scene(key))
            lay = hs.layout(key, grown)
            table = hs.palette_entries(lay, grown)
            for row in lay.submesh_rows:
                mesh = row["name"][len("HAIR_"):]
                if mesh not in RIDING:
                    continue
                mapping = struct.unpack_from("<56H", grown, row["record"] + 8)
                first, last = struct.unpack_from("<HH", grown, row["record"] + 4)
                for slot, entry, parts in document["scenes"][key]["parts"][mesh].get("palette", []):
                    self.assertEqual(mapping[slot], entry)
                    self.assertTrue(first <= slot <= last)
                    self.assertEqual([(int(j), round(w, 5)) for j, w in table[entry]],
                                     [(int(j), round(float(w), 5)) for j, w in parts])

    def test_riding_hair_clears_the_jersey_nameplate_and_numbers_in_the_bind_pose(self):
        """No sample of the two rebuilt meshes lies behind the jersey surface (nameplate and numbers included) in the
        bind pose; b775's long hair passed under the nameplate and dipped into the collar."""
        import numpy as np
        gen = __import__("nfl2k5_hair_styles_generate")
        outer3 = retail_outer3()
        rig = gen.Rig(outer3)
        bodies = {hs.HI: rig.body, hs.LO: rig.lo}
        for key in hs.KEYS:
            grown, receipt = hs.grow_scene(key, scene(key))
            sc = gen.Scene(key, grown)
            body = bodies[key]
            tris = body.tris(list(JERSEY))
            tris = tris[body.pos[tris].mean(axis=1)[:, 1] > 38.0]
            raw = models.read_lane_u32(body.d, body.shape, body.lanes.normal, body.n)
            normals = np.array([models.decode_normpacked3(w) for w in raw])
            corners = body.pos[tris]
            bary = [(1 - i / 6 - j / 6, i / 6, j / 6) for i in range(7) for j in range(7 - i)]
            js = np.concatenate([corners[:, 0] * a + corners[:, 1] * b + corners[:, 2] * c for a, b, c in bary])
            ns = np.concatenate([normals[tris[:, 0]] * a + normals[tris[:, 1]] * b + normals[tris[:, 2]] * c
                                 for a, b, c in bary])
            ns /= np.linalg.norm(ns, axis=1, keepdims=True)
            shift = np.array(BODY_FROM_HEAD) if key == hs.HI else np.zeros(3)     # hi_head is in the thorax frame
            for part in receipt["parts"]:
                if part["mesh"] not in RIDING:
                    continue
                hair_tris = sc.tris([hs.material_name(part["mesh"])])
                hp = sc.pos + shift
                pts = np.concatenate([hp[hair_tris[:, 0]] * a + hp[hair_tris[:, 1]] * b + hp[hair_tris[:, 2]] * c
                                      for a, b, c in bary[::4]])
                worst = 0.0
                for chunk in range(0, len(pts), 512):
                    p = pts[chunk:chunk + 512]
                    d2 = ((p[:, None, :] - js[None, :, :]) ** 2).sum(-1)
                    i = d2.argmin(1)
                    d = np.sqrt(d2[np.arange(len(p)), i])
                    sd = ((p - js[i]) * ns[i]).sum(1)
                    inside = (d < 5.0) & (sd < -0.1) & (np.abs(sd) >= 0.5 * d)
                    if inside.any():
                        worst = max(worst, float(-sd[inside].min()))
                self.assertEqual(worst, 0.0, (key, part["mesh"]))


if __name__ == "__main__":
    unittest.main()
