"""b778-xs1: scale-out v4, the growable pool section (the second scale-out).

Proves on synthetic (invented) section geometry, no game bytes:
* a request set that fits the v3 runs still builds exactly the v3 image (same bytes, same 28 sections);
* a set that does not fit places every v3 owner at its v3 address and only the overflow in the pool;
* a late owner appended to a sealed v3 image converts it to v4 and moves no byte that is already placed;
  a second append grows the pool without moving the first;
* music and Career Home move from descriptor index 6 to 7 on conversion and still validate, install and unwrap;
* every pool invariant (directory page, data zero, gaps zero, digest, version, extent) refuses tampering;
* the pool executes and writes under Unicorn with the flags the loader gets (0x07);
* the request list is no longer capped at 96 (v4 keeps the document in the pool's first page).
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_music_storage as music
from mod_editor.core import nfl2k5_depth_chart_storage as storage
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_xbe_space import synthetic
from tests.nfl2k5_allocator_stack import REQUESTS

LATE = ("nfl2k5_xs1_probe_code", "nfl2k5_xs1_probe_data", "nfl2k5_xs1_probe_ro", "nfl2k5_xs1_probe_more")
BIG_CODE = ("nfl2k5_xs1_probe_code", "code", 20000, 16)
BIG_DATA = ("nfl2k5_xs1_probe_data", "data", 6000, 16)
BIG_RO = ("nfl2k5_xs1_probe_ro", "read_only", 3000, 16)
MORE = ("nfl2k5_xs1_probe_more", "code", 9000, 16)


def rows(layout):
    return {(a["owner"], a["kind"], a["va"], a["raw"], a["size"]) for a in layout["allocations"]
            if a["owner"] != space.DIRECTORY_OWNER}


class PoolPlannerTests(unittest.TestCase):
    def setUp(self):
        late = patch.object(space, "LATE_OWNERS", space.LATE_OWNERS + LATE)
        late.start()
        self.addCleanup(late.stop)

    def test_v3_sets_stay_v3_and_overflow_lands_whole_in_the_pool(self):
        v3 = space.plan(REQUESTS)
        self.assertEqual(v3["version"], 3)
        self.assertEqual(v3["file_size"], space.SCALE3_FILE_SIZE)
        self.assertFalse([r for r in v3["regions"] if r["kind"] == "pool"])
        v4 = space.plan(REQUESTS + (BIG_CODE, BIG_DATA, BIG_RO))
        self.assertEqual(v4["version"], 4)
        old = [a for a in v3["allocations"]]
        for row in old:
            self.assertIn(row, v4["allocations"])  # every v3 owner keeps its VA, raw offset and size
        pool = sorted((a for a in v4["allocations"] if a["va"] >= space.POOL_VA), key=lambda a: a["va"])
        self.assertEqual(pool[0]["owner"], space.DIRECTORY_OWNER)
        self.assertEqual((pool[0]["va"], pool[0]["raw"], pool[0]["size"]), (space.POOL_VA, space.POOL_RAW, space.PAGE))
        names = [a["owner"] for a in pool[1:]]
        self.assertEqual(sorted(names), sorted(r[0] for r in (BIG_CODE, BIG_DATA, BIG_RO)))
        for a in pool[1:]:
            self.assertEqual(a["owner_offset"], 0)  # never split
        region = next(r for r in v4["regions"] if r["kind"] == "pool")
        self.assertEqual((region["va"], region["raw"], region["flags"]), (space.POOL_VA, space.POOL_RAW, 0x07))
        self.assertEqual(region["size"] % space.PAGE, 0)
        self.assertEqual(v4["file_size"], space.POOL_RAW + region["size"])
        self.assertEqual(v4["image_size"], space.POOL_VA + region["size"] - 0x10000)
        cap = v4["capacity"]["pool"]
        self.assertEqual(cap["requested_bytes"], 29000)
        self.assertEqual(cap["pages"], region["size"] // space.PAGE)
        self.assertEqual(cap["max_pages"], space.MAX_POOL_PAGES)
        # the v3 rows of the table are the v3 runs only
        for kind in ("code", "data", "read_only"):
            self.assertEqual(v4["capacity"][kind]["capacity_bytes"], v3["capacity"][kind]["capacity_bytes"])

    def test_late_owner_appended_after_the_pool_moves_nothing(self):
        first = space.plan(REQUESTS + (BIG_CODE, BIG_DATA, BIG_RO))
        second = space.plan(REQUESTS + (BIG_CODE, BIG_DATA, BIG_RO, MORE))
        for row in first["allocations"]:
            self.assertIn(row, second["allocations"])
        more = next(a for a in second["allocations"] if a["owner"] == MORE[0])
        self.assertGreater(more["va"], max(a["va"] for a in first["allocations"]))

    def test_pool_limits_and_request_count(self):
        space.plan([("nfl2k5_xs1_probe_code", "code", space.MAX_REQUEST_BYTES, 4096)])
        many = [("owner_" + hashlib.sha256(str(i).encode()).hexdigest()[:8], "code", 1 + i * 37 % 500, 16) for i in range(200)]
        report = space.plan(many + list(space.DIRECTORY_CODE_REQUESTS))
        self.assertEqual(report["version"], 4)  # 200 requests: the v3 directory page cannot hold the list
        with self.assertRaisesRegex(ValueError, "count"):
            space.plan([(f"owner_{i:03d}", "code", 1, 1) for i in range(space.MAX_REQUESTS)])
        with patch.object(space, "MAX_POOL_PAGES", 4), self.assertRaisesRegex(ValueError, "pool"):
            space.plan(REQUESTS + (BIG_CODE,))

    def test_pool_document_capacity_is_bounded(self):
        with patch.object(space.zlib, "compress", return_value=b"x" * (space.PAGE - 12)):
            self.assertEqual(len(space._pool_document([BIG_CODE])), space.PAGE)
        with patch.object(space.zlib, "compress", return_value=b"x" * (space.PAGE - 11)):
            with self.assertRaisesRegex(ValueError, "document capacity"):
                space._pool_document([BIG_CODE])

    def test_header_budget_holds_the_pool_and_one_extra_section(self):
        self.assertLessEqual(space.META_START + (space.POOL_INDEX + 2) * 56, space.SCALE_HEADER_END)
        self.assertEqual(space.EXTRA4_NAME + 12, space.SCALE_NAMES)
        self.assertEqual(space.POOL_VA, 0x150B000)
        self.assertEqual(space.POOL_RAW, space.SCALE3_FILE_SIZE)
        sizes = space.accepted_file_sizes()
        self.assertIn(space.SCALE3_FILE_SIZE, sizes)
        self.assertIn(space.POOL_RAW + 3 * space.PAGE, sizes)
        self.assertEqual(max(sizes), space.SCALE_FILE_SIZE)


class PoolSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = bytearray(synthetic())
        for at, va in space.DEBUG_POINTERS:
            struct.pack_into("<I", retail, at, va)
        struct.pack_into("<II", retail, 0x178, 0x10994, 1)
        cls.retail = bytes(retail)
        pins = ExitStack()
        cls.addClassCleanup(pins.close)
        for module, name, value in (
            (space, "METADATA_SHA256", space._sha(cls.retail[space.META_START:space.META_END])),
            (space, "GEOMETRY_SHA256", space._sha(b"".join(cls.retail[space.TABLE + i*56:space.TABLE + i*56 + 36] for i in range(22)))),
            (space, "LIB_SHA256", space._sha(cls.retail[space.LIB_START:space.LIB_END])),
            (space, "DEBUG_SHA256", space._sha(cls.retail[space.DEBUG_START:space.DEBUG_END])),
            (storage, "RETAIL_CONTENT_SHA256", space._sha(bytes(storage.RETAIL_SIZE))),
            (space, "LATE_OWNERS", space.LATE_OWNERS + LATE),
        ):
            pins.enter_context(patch.object(module, name, value))
        cls.v3, _ = space.apply(cls.retail, REQUESTS)
        cls.v4, cls.receipt = space.apply(cls.retail, REQUESTS + (BIG_CODE, BIG_DATA, BIG_RO))

    def test_fresh_v4_image_validates_with_29_sections(self):
        self.assertEqual(space.status(self.v3), "applied")
        self.assertEqual(space.scale_version(self.v3), 3)
        self.assertEqual(len(self.v3), space.SCALE3_FILE_SIZE)
        self.assertEqual(space.status(self.v4), "applied")
        self.assertEqual(space.scale_version(self.v4), 4)
        image = XbeImage(self.v4)
        self.assertEqual(len(image.sections), space.SCALE_COUNT + 1)
        pool = image.sections[-1]
        self.assertEqual((pool.start, pool.raw, pool.flags), (space.POOL_VA, space.POOL_RAW, 0x07))
        self.assertEqual(pool.raw + pool.raw_size, len(self.v4))
        self.assertEqual(struct.unpack_from("<I", self.v4, 0x10C)[0], pool.start + pool.raw_size - 0x10000)
        # Everything below the pool is the same as the v3 build except the header page and the v3 directory page.
        differs = [i for i in range(0, space.SCALE3_FILE_SIZE, space.PAGE)
                   if self.v3[i:i + space.PAGE] != self.v4[i:i + space.PAGE]]
        self.assertEqual(differs, [0, space.SCALE_DIRECTORY])
        self.assertEqual(self.v4[space.POOL_RAW:space.POOL_RAW + 8], space.POOL_DOC_MAGIC)
        self.assertEqual(space._scale_directory_requests(self.v4), space._requests(REQUESTS + (BIG_CODE, BIG_DATA, BIG_RO)))

    def test_extend_converts_v3_to_v4_and_grows_without_moving(self):
        before = space.layout(self.v3)
        once, receipt = space.extend_scaleout(self.v3, [BIG_CODE, BIG_DATA, BIG_RO])
        self.assertEqual(space.status(once), "applied")
        self.assertEqual(space.scale_version(once), 4)
        self.assertTrue(receipt["existing_feature_allocations_unchanged"])
        self.assertLessEqual(rows(before), rows(space.layout(once)))
        self.assertEqual(once, self.v4)  # appending equals a fresh build of the same set
        twice, _ = space.extend_scaleout(once, [MORE])
        self.assertEqual(space.status(twice), "applied")
        self.assertLessEqual(rows(space.layout(once)), rows(space.layout(twice)))
        self.assertGreater(len(twice), len(once))
        self.assertEqual(twice[space.PAGE:space.SCALE_DIRECTORY], once[space.PAGE:space.SCALE_DIRECTORY])
        # an owner's installed bytes survive the growth
        code = bytes(range(256)) * 78 + bytes(32)
        filled, _ = space.install_code(once, BIG_CODE[0], code)
        grown, _ = space.extend_scaleout(filled, [MORE])
        owner = next(a for a in space.layout(grown)["allocations"] if a["owner"] == BIG_CODE[0])
        self.assertEqual(grown[owner["raw"]:owner["raw"] + owner["size"]], code)
        self.assertEqual(space.install_code(grown, BIG_CODE[0], code)[0], grown)  # exact replay

    def test_pool_tamper_refusals(self):
        layout = space.layout(self.v4)
        pool = next(r for r in layout["regions"] if r["kind"] == "pool")
        data = next(a for a in layout["allocations"] if a["owner"] == BIG_DATA[0])
        code = next(a for a in layout["allocations"] if a["owner"] == BIG_CODE[0])
        end = max(a["raw"] + a["size"] for a in layout["allocations"] if a["va"] >= space.POOL_VA)
        for label, at in (("document", space.POOL_RAW + 20), ("data owner", data["raw"] + 3),
                          ("code owner", code["raw"] + 5), ("gap", end + 1 if end + 1 < pool["raw"] + pool["size"] else None),
                          ("pool descriptor", space.META_START + space.POOL_INDEX * 56 + 8),
                          ("tag", space.DIRECTORY + 11)):
            if at is None:
                continue
            bad = bytearray(self.v4)
            bad[at] ^= 1
            with self.subTest(label=label):
                self.assertEqual(space.status(bytes(bad)), "foreign")
        self.assertEqual(space.status(self.v4 + bytes(space.PAGE)), "foreign")
        self.assertEqual(space.status(self.v4[:-space.PAGE]), "foreign")
        v3_tag = bytearray(self.v4)
        v3_tag[space.DIRECTORY:space.DIRECTORY + 12] = space.SCALE_TAG
        self.assertEqual(space.status(bytes(v3_tag)), "foreign")
        with self.assertRaisesRegex(ValueError, "rebuild"):
            space.apply(self.v4, REQUESTS + (BIG_CODE,))
        self.assertEqual(space.apply(self.v4, REQUESTS + (BIG_CODE, BIG_DATA, BIG_RO))[0], self.v4)

    def test_music_moves_to_index_7_both_orders(self):
        data = b"synthetic music metadata"
        v3_music, _ = music.install(self.v3, data)
        self.assertEqual(struct.unpack_from("<I", v3_music, 0x11C)[0], space.SCALE_COUNT + 1)
        converted, _ = space.extend_scaleout(v3_music, [BIG_CODE, BIG_DATA, BIG_RO])
        direct, _ = music.install(self.v4, data)
        self.assertEqual(converted, direct)
        self.assertEqual(space.status(direct), "applied")
        self.assertTrue(space.has_music(direct))
        self.assertEqual(struct.unpack_from("<I", direct, 0x11C)[0], space.SCALE_COUNT + 2)
        header, name, refs = space.scale_music_slots(direct)
        self.assertEqual((header, name), (space.META_START + 7 * 56, space.EXTRA4_NAME))
        self.assertEqual(direct[name:name + 8], b".ASTRAr\0")
        self.assertEqual(direct[space.SCALE_NAMES + 72:space.SCALE_NAMES + 80], b".AS0006\0")  # the pool's name
        base, back = music.unwrap(direct)
        self.assertEqual((base, back), (self.v4, data))
        self.assertEqual(music.install(direct, data)[0], direct)
        starts = [struct.unpack_from("<I", direct, space.META_START + i * 56 + 4)[0] for i in (6, 7)]
        self.assertEqual(starts, [space.POOL_VA, music.VA])  # descriptor order: the pool, then the music section

    @unittest.skipUnless(importlib.util.find_spec("unicorn"), "Unicorn absent")
    def test_pool_executes_and_writes_with_loader_flags(self):
        import unicorn as uc
        from unicorn import x86_const as x86
        layout = space.layout(self.v4)
        code = next(a for a in layout["allocations"] if a["owner"] == BIG_CODE[0])
        data = next(a for a in layout["allocations"] if a["owner"] == BIG_DATA[0])
        body = bytearray(b"\xcc" * code["size"])
        body[:6] = b"\xa3" + struct.pack("<I", data["va"] + 8) + b"\xc3"   # mov [data+8], eax ; ret
        grown, _ = space.install_code(self.v4, BIG_CODE[0], bytes(body))
        machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for section in XbeImage(grown).sections:
            if section.start < space.POOL_VA:
                continue
            size = (section.raw_size + 4095) & -4096
            machine.mem_map(section.start, size)
            machine.mem_write(section.start, grown[section.raw:section.raw + section.raw_size])
            perms = uc.UC_PROT_READ | (uc.UC_PROT_WRITE if section.flags & 1 else 0) | (uc.UC_PROT_EXEC if section.flags & 4 else 0)
            machine.mem_protect(section.start, size, perms)
        stack, stop = 0x3000000, 0x3010000
        machine.mem_map(stack, 4096)
        machine.mem_map(stop, 4096, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        machine.mem_write(stack, struct.pack("<I", stop))
        machine.reg_write(x86.UC_X86_REG_ESP, stack)
        machine.reg_write(x86.UC_X86_REG_EAX, 0x5EC0DD00)
        machine.emu_start(code["va"], stop, count=4)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EIP), stop)
        self.assertEqual(bytes(machine.mem_read(data["va"] + 8, 4)), struct.pack("<I", 0x5EC0DD00))


class PoolCareerHomeTests(unittest.TestCase):
    """Career Home (the optional extra section) on a real MyCareer image survives the v3 -> v4 conversion."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_my_career_fixture import XBE
        if not XBE.is_file():
            raise unittest.SkipTest("pinned USA XBE required")
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career_home as home
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.mode, cls.home = mode, home
        late = patch.object(space, "LATE_OWNERS", space.LATE_OWNERS + LATE)
        late.start()
        cls.addClassCleanup(late.stop)
        cls.v3 = home.apply(mode.apply(retail_bytes())[0])[0]
        cls.v4, cls.receipt = space.extend_scaleout(cls.v3, [(BIG_CODE[0], "code", 98304, 16)])  # more than the whole v3 run

    def test_home_moves_to_index_7_and_every_owner_still_validates(self):
        v3, v4, home = self.v3, self.v4, self.home
        self.assertEqual((space.scale_version(v3), space.scale_version(v4)), (3, 4))
        self.assertEqual((space.status(v4), self.mode.status(v4), home.status(v4)), ("applied",) * 3)
        self.assertTrue(space.has_home_section(v4))
        self.assertFalse(space.has_music(v4))
        self.assertEqual(struct.unpack_from("<I", v4, 0x11C)[0], space.SCALE_COUNT + 2)
        old, new = space.META_START + 6 * 56, space.META_START + 7 * 56
        self.assertEqual(struct.unpack_from("<I", v4, new + 4)[0], home.VA)
        self.assertEqual(v3[old:old + 20], v4[new:new + 20])          # flags, VA, sizes, raw: unchanged
        self.assertEqual(v3[old + 36:old + 56], v4[new + 36:new + 56])  # digest: the section bytes are unchanged
        self.assertEqual(v4[space.EXTRA4_NAME:space.EXTRA4_NAME + 8], b".AS0007\0")
        self.assertEqual(v3[home.RAW:home.RAW + home.SIZE], v4[home.RAW:home.RAW + home.SIZE])
        self.assertEqual(home.check_static(v4), home.check_static(v3))
        self.assertLessEqual(rows(space.layout(v3)), rows(space.layout(v4)))
        self.assertEqual(home.apply(v4)[0], v4)  # exact replay on v4


if __name__ == "__main__":
    unittest.main()
