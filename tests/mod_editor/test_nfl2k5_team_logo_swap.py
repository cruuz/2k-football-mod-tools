"""The practicing team's logo at the practice field's midfield (job pf, P1): the xbe_space owner (status, apply, exact
revert, guards, its place after every existing read-only owner) and the game's own field swap loop run under Unicorn on
the retail and the patched executable (the eighth pair reaches a material named teamlogo, only that material, and only
when a logo is loaded)."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_team_logo_swap as tl  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

XBE = ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "default.xbe"
RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"


def _retail():
    data = XBE.read_bytes()
    assert tl._sha(data) == RETAIL_SHA256
    return data


@unittest.skipUnless(XBE.is_file(), "needs the hydrated retail default.xbe")
class Owner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.applied, cls.receipt = tl.apply(cls.retail)

    def test_retail_applied_and_the_bounds(self):
        self.assertEqual(tl.status(self.retail), "retail")
        self.assertEqual(tl.status(self.applied), "applied")
        image = XbeImage(self.applied)
        table = tl.allocation(self.applied)["va"]
        self.assertEqual(image.read(table, 64), tl.TABLE)
        self.assertEqual(struct.unpack("<I", image.read(tl.START_SITE, 4))[0], table + 4)
        self.assertEqual(struct.unpack("<I", image.read(tl.END_SITE, 4))[0], table + 0x44)
        # the eight pairs: the retail seven as they are, then teamlogo -> logo
        self.assertEqual(image.read(table, 56), XbeImage(self.retail).read(tl.RETAIL_TABLE_VA, 56))
        pair = struct.unpack("<II", image.read(table + 56, 8))
        self.assertEqual([image.read(va, 18 if i == 0 else 10).decode("utf-16le") for i, va in enumerate(pair)],
                         ["teamlogo\0", "logo\0"])

    def test_apply_is_idempotent_and_revert_is_exact(self):
        again, receipt = tl.apply(self.applied)
        self.assertEqual(again, self.applied)
        self.assertEqual(receipt["changed_bytes"], 0)
        reserved, _ = space.apply(self.retail, tl.REQUESTS, scaleout=True)
        self.assertEqual(tl.status(reserved), "retail")
        back, _ = tl.revert(self.applied)
        self.assertEqual(back, reserved)
        self.assertEqual(tl.apply(reserved)[0], self.applied)
        self.assertEqual(tl.revert(self.retail)[0], self.retail)

    def test_foreign_bytes_are_refused(self):
        place = tl.allocation(self.applied)
        bad = bytearray(self.applied)
        bad[place["raw"] + 60] ^= 1
        self.assertEqual(tl.status(bytes(bad)), "foreign")
        for site in (tl.START_SITE, tl.END_SITE, 0x9C5F4, tl.RETAIL_TABLE_VA + 8, tl.TEAM_LOGO_MATERIAL_VA,
                     tl.LOGO_TXTR_VA, 0x9C186):
            bad = bytearray(self.retail)
            bad[rdata.offset_of(self.retail, site)] ^= 1
            self.assertEqual(tl.status(bytes(bad)), "foreign", hex(site))
        with self.assertRaises(ValueError):
            tl.apply(bytes(bad))

    def test_it_sorts_after_every_read_only_owner_in_the_union(self):
        """In the dormant union the table lands after every existing read-only owner, and no other owner moves."""
        union = space.dormant_union()
        self.assertIn(tl.REQUESTS[0], union)
        without = [r for r in union if r[0] != tl.OWNER]
        before = {(a["owner"], a["kind"]): a["va"] for a in space._scale_allocations(without)}
        after = {(a["owner"], a["kind"]): a["va"] for a in space._scale_allocations(union)}
        mine = after.pop((tl.OWNER, "read_only"))
        self.assertEqual(before, after)
        ro = [va for (owner, kind), va in after.items() if kind == "read_only" and owner != space.DIRECTORY_OWNER]
        self.assertGreater(mine, max(ro))

    def test_a_union_build_installs_into_its_reserved_table(self):
        """The builder reserves the whole selected union first; the owner then installs into its own place."""
        from mod_editor.core import nfl2k5_coin_defer as coin_defer
        union = coin_defer.REQUESTS + tl.REQUESTS
        reserved, _ = space.apply(self.retail, union, scaleout=True)
        out, _ = tl.apply(reserved)
        self.assertEqual(tl.status(out), "applied")
        self.assertEqual(coin_defer.status(out), "retail")
        out, _ = coin_defer.apply(out)
        self.assertEqual((tl.status(out), coin_defer.status(out)), ("applied", "applied"))

    def test_reservations_name_the_table_and_the_two_bounds(self):
        rows = tl.reservations(self.applied)
        self.assertEqual(sorted(r["size"] for r in rows), [4, 4, 64])
        self.assertTrue(all(r["owner"] == tl.OWNER for r in rows))


# --- the game's own swap loop under Unicorn ---------------------------------------------------------------------

LOOP_START, LOOP_END = 0x9C5DE, 0x9C66B
COMPARE, LOOKUP = 0x30C40, 0x449E0
SCENE_SLOT = 0xA87334
HEAP, STACK = 0x3000000, 0x3800000


def _field_scene_run(payload, materials, loaded):
    """Run 0x9C5DE..0x9C66B of ``payload`` over a field scene whose materials are ``materials`` (names; each with a
    placeholder texture), the loaded TXTRs ``loaded`` ({name: pointer}). The two boundaries are substituted: the
    name compare 0x30C40 (fastcall ecx, edx; non-zero when equal) and the typed lookup 0x449E0 (ecx 0, edx 'TXTR', the
    name pushed; ret 4). Returns ({material: texture after}, [looked-up names])."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EIP
    image = XbeImage(payload)
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    pages = set()
    for s in image.sections:
        pages.update(range(s.start & ~0xFFF, (s.end + 0xFFF) & ~0xFFF, 0x1000))
    run = sorted(pages)
    start = run[0]
    for a, b in zip(run, run[1:] + [None]):
        if b != a + 0x1000:
            uc.mem_map(start, a + 0x1000 - start)
            start = b
    for s in image.sections:
        if s.raw_size:
            uc.mem_write(s.start, bytes(payload[s.raw:s.raw + min(s.size, s.raw_size)]))
    uc.mem_map(HEAP, 0x100000)
    uc.mem_map(STACK - 0x10000, 0x20000)

    def wstr(at, text):
        uc.mem_write(at, (text + "\0").encode("utf-16le"))

    def rstr(at):
        out = b""
        while True:
            unit = bytes(uc.mem_read(at, 2))
            if unit == b"\0\0":
                return out.decode("utf-16le")
            out += unit
            at += 2
    scene, table, names = HEAP, HEAP + 0x1000, HEAP + 0x8000
    uc.mem_write(scene + 0x1C, struct.pack("<II", len(materials), table))
    placeholder = {}
    for i, name in enumerate(materials):
        wstr(names + 0x80 * i, name)
        placeholder[name] = 0x7000000 + i
        uc.mem_write(table + 0x80 * i, struct.pack("<I", names + 0x80 * i))
        uc.mem_write(table + 0x80 * i + 0x30, struct.pack("<I", placeholder[name]))
    uc.mem_write(SCENE_SLOT, struct.pack("<I", scene))
    looked = []

    def ret(pop):
        esp = uc.reg_read(UC_X86_REG_ESP)
        back = struct.unpack("<I", uc.mem_read(esp, 4))[0]
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
        uc.reg_write(UC_X86_REG_EIP, back)

    def compare(uc_, at, size, data):
        same = rstr(uc.reg_read(UC_X86_REG_ECX)) == rstr(uc.reg_read(UC_X86_REG_EDX))
        uc.reg_write(UC_X86_REG_EAX, 1 if same else 0)
        ret(0)

    def lookup(uc_, at, size, data):
        assert uc.reg_read(UC_X86_REG_EDX) == 0x52545854 and uc.reg_read(UC_X86_REG_ECX) == 0
        esp = uc.reg_read(UC_X86_REG_ESP)
        name = rstr(struct.unpack("<I", uc.mem_read(esp + 4, 4))[0])
        looked.append(name)
        uc.reg_write(UC_X86_REG_EAX, loaded.get(name, 0))
        ret(4)
    uc.hook_add(UC_HOOK_CODE, compare, begin=COMPARE, end=COMPARE)
    uc.hook_add(UC_HOOK_CODE, lookup, begin=LOOKUP, end=LOOKUP)
    uc.reg_write(UC_X86_REG_ESP, STACK - 0x100)
    uc.emu_start(LOOP_START, LOOP_END, count=200000)
    after = {name: struct.unpack("<I", uc.mem_read(table + 0x80 * i + 0x30, 4))[0] for i, name in enumerate(materials)}
    return {name: (None if v == placeholder[name] else v) for name, v in after.items()}, looked


PRACTICE_FIELD = ["grass_colour_map", "center_logo", "endzone_N_L", "endzone_N_M", "endzone_N_R", "endzone_S_L",
                  "endzone_S_M", "endzone_S_R"]
LOADED = {"center_logo": 0x5100000, "endzone_north_left": 0x5100010, "endzone_north_middle": 0x5100020,
          "endzone_north_right": 0x5100030, "endzone_south_left": 0x5100040, "endzone_south_middle": 0x5100050,
          "endzone_south_right": 0x5100060, "logo": 0x5200000}


@unittest.skipUnless(XBE.is_file(), "needs the hydrated retail default.xbe")
class NativeSwap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("needs unicorn")
        cls.retail = _retail()
        cls.applied, _ = tl.apply(cls.retail)
        # the practice facility's field: the midfield material renamed teamlogo
        cls.practice = [("teamlogo" if m == "center_logo" else m) for m in PRACTICE_FIELD]

    def test_retail_swaps_seven_pairs(self):
        after, looked = _field_scene_run(self.retail, PRACTICE_FIELD, LOADED)
        self.assertEqual(len(looked), 7)
        self.assertEqual(after["center_logo"], LOADED["center_logo"])
        self.assertEqual(after["endzone_S_R"], LOADED["endzone_south_right"])
        self.assertIsNone(after["grass_colour_map"])

    def test_the_eighth_pair_reaches_the_teamlogo_material(self):
        after, looked = _field_scene_run(self.applied, self.practice, LOADED)
        self.assertEqual(looked, ["center_logo", "endzone_north_left", "endzone_north_middle", "endzone_north_right",
                                  "endzone_south_left", "endzone_south_middle", "endzone_south_right", "logo"])
        self.assertEqual(after["teamlogo"], LOADED["logo"])
        self.assertEqual(after["endzone_N_L"], LOADED["endzone_north_left"])
        self.assertIsNone(after["grass_colour_map"])

    def test_no_logo_loaded_keeps_the_fields_own_midfield(self):
        loaded = {k: v for k, v in LOADED.items() if k != "logo"}
        after, looked = _field_scene_run(self.applied, self.practice, loaded)
        self.assertEqual(looked[-1], "logo")
        self.assertIsNone(after["teamlogo"])

    def test_every_other_field_is_unchanged(self):
        """A field without a teamlogo material (every retail field) swaps exactly as on the retail executable."""
        for loaded in (LOADED, {k: v for k, v in LOADED.items() if k != "logo"}):
            retail, _ = _field_scene_run(self.retail, PRACTICE_FIELD, loaded)
            patched, looked = _field_scene_run(self.applied, PRACTICE_FIELD, loaded)
            self.assertEqual(patched, retail)
            self.assertEqual(len(looked), 8)


if __name__ == "__main__":
    unittest.main()
