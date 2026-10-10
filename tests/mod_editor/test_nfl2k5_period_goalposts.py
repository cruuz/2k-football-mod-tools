"""Period goalposts (beta 77 v1b): 30 ft uprights for the Anniversary moments before the 2014 season.

Always on: the data table, the assembled cave (budget, tables, branch targets) and the cave RUN under Unicorn on modern
goalpost scene images (synthetic ones, and the real compiled scenes when the retail files are present): the vertex words
it rewrites, the two site stubs, every game-mode / moment-row combination, and the line stubs. With the retail files
(NFL2K5_GAME_DIR) and a SOFTDRINK 2K28 v0.5 executable (B77_V05_DIR holding default.xbe): the allocator extension and the
four executable sites, idempotence, and that no other owner's address or bytes move.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_modern_goalposts as goal  # noqa: E402
from mod_editor.core import nfl2k5_period_goalposts as pg  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACK0 = GAME / "vc_53450030" / "0"
HAVE_GAME = PACK0.is_file()
V05 = Path(os.environ.get("B77_V05_DIR", "/nonexistent")) / "default.xbe"
HAVE_V05 = V05.is_file()

CODE_VA, RO_VA = 0x014EB150, 0x014F8000          # any VAs do for the cave (the v0.5 directory puts the owner elsewhere)
PAGE = 0x1000


def synthetic_modern(scene: str) -> bytes:
    """A decoded modern-form scene: uprights topped at the modern word, a few other vertices below the crossbar."""
    spec = goal.SCENES[scene]
    buf = bytearray(spec["size"])
    rec = spec["record"]
    scale, off_y = 687.1715698242188, 685.7999877929688
    struct.pack_into("<4f", buf, rec + 0x10, scale, scale, scale, 0.0)
    struct.pack_into("<4f", buf, rec + 0x20, 0.0, off_y, -102.4, 1.0)
    struct.pack_into("<H", buf, rec + 0x4C, spec["vertices"])
    for k in range(spec["vertices"]):
        top = k < spec["tops"]
        y = pg.WORD_MODERN if top else -32702 + (k * 131) % 9000
        struct.pack_into("<3h", buf, spec["positions"] + 6 * k, (k * 97) % 2000 - 1000, y, (k * 53) % 600 - 300)
    return bytes(buf)


class Cpu:
    """The period goalposts cave under Unicorn on a small fake game: two scenes, the globals, the engine's lookup."""

    SCENE_BASE = {"goalpost": 0x03000000, "goalpost_shadow": 0x03010000}
    STACK, SENTINEL = 0x02000000, 0x02800000

    def __init__(self, images: dict[str, bytes], mode: int, row: int):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX
        self.uc, self.regs = Uc(UC_ARCH_X86, UC_MODE_32), (UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX)
        uc = self.uc
        for base, size in ((CODE_VA & ~(PAGE - 1), 2 * PAGE), (RO_VA & ~(PAGE - 1), PAGE), (0x00097000, PAGE),
                           (0x00044000, PAGE), (0x00E5F000, PAGE), (0x00BF1000, PAGE), (0x00E66000, PAGE),
                           (0x00098000, PAGE), (0x02000000, 2 * PAGE), (0x02800000, PAGE),
                           (0x03000000, 0x20000)):
            uc.mem_map(base, size)
        uc.mem_write(0x00097B50, b"\xc3")                                    # the displaced callee: ret
        uc.mem_write(NAMES["goalpost"], "goalpost".encode("utf-16le") + b"\0\0")
        uc.mem_write(NAMES["goalpost_shadow"], "goalpost_shadow".encode("utf-16le") + b"\0\0")
        uc.mem_write(pg.MODE_VA, struct.pack("<I", mode))
        uc.mem_write(pg.ROW_VA, struct.pack("<I", row))
        uc.mem_write(CODE_VA, pg.code_for(CODE_VA, RO_VA))
        uc.mem_write(RO_VA, pg.tables())
        self.scenes = {}
        for name, image in images.items():
            spec = goal.SCENES[name]
            base = self.SCENE_BASE[name]
            uc.mem_write(base, image)
            s = base + 0x100                                                 # the scene struct (body + 0x100)
            uc.mem_write(s + 0x2C, struct.pack("<I", 1))                     # one node
            uc.mem_write(s + 0x30, struct.pack("<I", base + spec["record"]))  # abs pointer, as the loader's fix-up leaves it
            uc.mem_write(base + spec["record"] + 0xD4, struct.pack("<I", base + spec["positions"]))
            self.scenes[name] = (s, base, spec)
        self.lookups = []

        def find(uc_, address, size, _user):
            if address == pg.FIND_VA:
                esp = struct.unpack("<I", uc_.mem_read(uc_.reg_read(UC_X86_REG_ESP), 4))[0], \
                    struct.unpack("<I", uc_.mem_read(uc_.reg_read(UC_X86_REG_ESP) + 4, 4))[0]
                self.lookups.append(esp[1])
                found = 0
                for name, va in NAMES.items():
                    if esp[1] == va and name in self.scenes:
                        found = self.scenes[name][0]
                uc_.reg_write(UC_X86_REG_EAX, found)
                sp = uc_.reg_read(UC_X86_REG_ESP)
                uc_.reg_write(UC_X86_REG_EIP, esp[0])
                uc_.reg_write(UC_X86_REG_ESP, sp + 8)                         # ret 4
        uc.hook_add(UC_HOOK_CODE, find, begin=pg.FIND_VA, end=pg.FIND_VA)

    def run(self, entry: int, stop: int | None = None):
        uc = self.uc
        esp = self.STACK + PAGE
        uc.mem_write(esp, struct.pack("<I", self.SENTINEL))
        uc.reg_write(self.regs[0], esp)
        uc.emu_start(entry, self.SENTINEL if stop is None else stop, count=20000)

    def positions(self, name: str) -> bytes:
        s, base, spec = self.scenes[name]
        return bytes(self.uc.mem_read(base + spec["positions"], 6 * spec["vertices"]))

    def line_top(self) -> float:
        """Run the line stub as the `push <top>` site does: the value it leaves on the stack, eax and the return kept."""
        from unicorn.x86_const import UC_X86_REG_EAX
        uc = self.uc
        esp = self.STACK + PAGE
        uc.mem_write(esp, struct.pack("<I", 0x00098700))              # the return address the call pushed
        uc.mem_write(0x00098700, b"\x90")
        uc.reg_write(self.regs[0], esp)
        uc.reg_write(UC_X86_REG_EAX, 0xCAFEBABE)
        uc.emu_start(pg.labels(CODE_VA, RO_VA)["line"], 0x00098700, count=200)
        assert uc.reg_read(self.regs[0]) == esp, "the stub must leave exactly the pushed value (the return address consumed)"
        assert uc.reg_read(UC_X86_REG_EAX) == 0xCAFEBABE, "eax must be restored"
        return struct.unpack("<f", uc.mem_read(esp, 4))[0]

    def collision_top(self) -> float:
        """Run the collision stub as `fadd [top]` does on an empty x87 stack (a driver: fldz ; call coll ; fstp [mem])."""
        from unicorn.x86_const import UC_X86_REG_EAX
        uc = self.uc
        driver = 0x00098800
        coll = pg.labels(CODE_VA, RO_VA)["coll"]
        code = b"\xd9\xee" + b"\xe8" + struct.pack("<i", coll - (driver + 7)) + b"\xd9\x1d" + struct.pack("<I", 0x00098900) + b"\x90"
        uc.mem_write(driver, code)
        uc.reg_write(self.regs[0], self.STACK + PAGE)
        uc.reg_write(UC_X86_REG_EAX, 0x1234)
        uc.emu_start(driver, driver + len(code) - 1, count=200)
        assert uc.reg_read(UC_X86_REG_EAX) == 0x1234
        return struct.unpack("<f", uc.mem_read(0x00098900, 4))[0]


NAMES = {"goalpost": pg.NAME_POST_VA, "goalpost_shadow": pg.NAME_SHADOW_VA}


def y_words(stream: bytes) -> list[int]:
    return [struct.unpack_from("<h", stream, 6 * k + 2)[0] for k in range(len(stream) // 6)]


class DataTable(unittest.TestCase):
    def test_the_table_follows_the_2014_rule(self):
        rows = pg.moments()
        self.assertEqual([r["row"] for r in rows], list(range(1, 52)))
        for r in rows:
            self.assertEqual(r["uprights_above_crossbar_ft"], 30 if r["season"] < 2014 else 35, r["title"])
            self.assertEqual(r["upright_top_above_field_ft"], r["uprights_above_crossbar_ft"] + 10)
        self.assertEqual(sum(1 for r in rows if r["uprights_above_crossbar_ft"] == 30), 38)
        self.assertEqual(sum(1 for r in rows if r["uprights_above_crossbar_ft"] == 35), 13)
        by_row = {r["row"]: r for r in rows}
        self.assertEqual((by_row[40]["season"], by_row[40]["uprights_above_crossbar_ft"]), (2012, 30))   # Feb 2013 game
        self.assertEqual((by_row[41]["season"], by_row[41]["uprights_above_crossbar_ft"]), (2014, 35))   # Jan 2015 game
        self.assertEqual((by_row[26]["date"], by_row[26]["season"]), ("1999-01-17", 1998))               # a January game

    def test_the_file_is_the_generated_document(self):
        self.assertEqual(json.loads(pg.DATA.read_text()), json.loads(json.dumps(pg.document())))
        self.assertTrue(all(s.startswith("https://") for s in pg.document()["rule"]["sources"]))

    def test_the_flags_follow_the_table_in_physical_order(self):
        flags = pg.period_flags()
        self.assertEqual(len(flags), 51)
        self.assertEqual([i + 1 for i, f in enumerate(flags) if not f], [30, 31] + list(range(41, 52)))


class Cave(unittest.TestCase):
    def test_budget_tables_and_branches(self):
        code = pg.code_for(CODE_VA, RO_VA)
        self.assertEqual(len(code), pg.CODE_SIZE)
        tables = pg.tables()
        self.assertEqual(len(tables), pg.RO_SIZE)
        self.assertEqual(struct.unpack_from("<Q", tables, pg.TABLE_MASK)[0], sum(1 << i for i, f in enumerate(pg.period_flags()) if f))
        self.assertEqual(struct.unpack_from("<2f", tables, pg.TABLE_TOPS), struct.unpack("<2f", struct.pack("<2f", pg.TOP_MODERN, pg.TOP_PERIOD)))
        self.assertEqual(struct.unpack_from("<IH", tables, pg.TABLE_POST), (pg.NAME_POST_VA, 243))
        self.assertEqual(struct.unpack_from("<IH", tables, pg.TABLE_SHADOW), (pg.NAME_SHADOW_VA, 174))
        self.assertEqual(code, pg.code_for(CODE_VA, RO_VA))
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        end = pg.labels(CODE_VA, RO_VA)["coll"] + 17 - CODE_VA
        decoded = list(md.disasm(code[:end], CODE_VA))
        self.assertEqual(sum(i.size for i in decoded), end)                  # the code part decodes cleanly to its end
        self.assertTrue(code[end:] == b"\xcc" * (pg.CODE_SIZE - end))
        for i in decoded:
            if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
                target = int(i.op_str, 16)
                self.assertTrue(CODE_VA <= target < CODE_VA + pg.CODE_SIZE or target in (pg.LOAD_CALLEE_VA, pg.FIND_VA), hex(target))
        self.assertLessEqual(end, 176)

    def test_it_fits_the_allocators_worst_case(self):
        """Every owner installed at once leaves 192 code bytes and no writable page: the owner asks for no data at all."""
        union = [r for r in space.dormant_union() if r[0] != pg.OWNER]
        self.assertTrue(all(kind != "data" for _owner, kind, _size, _align in pg.REQUESTS))
        allocations = space._scale_allocations(union + list(pg.REQUESTS))
        mine = [a for a in allocations if a["owner"] == pg.OWNER]
        self.assertEqual(sorted(a["kind"] for a in mine), ["code", "read_only"])
        before = {(a["owner"], a["kind"], a["va"]) for a in space._scale_allocations(union)}
        self.assertEqual(before - {(a["owner"], a["kind"], a["va"]) for a in allocations}, set())

    def test_the_four_sites(self):
        sites = pg.sites(CODE_VA, RO_VA)
        self.assertEqual([s[0] for s in sites], ["stadium_load_hook", "upright_line_left_top", "upright_line_right_top",
                                                 "upright_collision_top"])
        lab = pg.labels(CODE_VA, RO_VA)
        for (label, va, accepted, after), target in zip(sites, ("stub", "line", "line", "coll")):
            self.assertEqual(after[0], 0xE8, label)
            self.assertEqual(struct.unpack_from("<i", after, 1)[0] + va + 5, lab[target], label)
            self.assertTrue(all(len(a) == len(after) for a in accepted), label)
        self.assertEqual(sites[3][3][5:], b"\x90")                          # the 6-byte fadd becomes a call and a nop


class CaveRun(unittest.TestCase):
    """Run the stub as the stadium loader would, on scene images of the modern form."""

    def images(self):
        return {name: synthetic_modern(name) for name in goal.SCENES}

    def run_case(self, mode, row, images=None):
        cpu = Cpu(images or self.images(), mode, row)
        cpu.run(pg.labels(CODE_VA, RO_VA)["stub"])
        return cpu

    def test_a_normal_game_keeps_the_35_ft_posts(self):
        base = self.images()
        for mode, row in ((0, 0), (3, 12), (7, 5), (8, 51), (8, 0xFFFFFFFF), (8, 40), (8, 50), (8, 29), (8, 30)):
            cpu = self.run_case(mode, row)
            for name in goal.SCENES:
                with self.subTest(mode=mode, row=row, scene=name):
                    spec = goal.SCENES[name]
                    self.assertEqual(cpu.positions(name), base[name][spec["positions"]:spec["positions"] + 6 * spec["vertices"]])
            self.assertAlmostEqual(cpu.line_top(), pg.TOP_MODERN, places=3)
            self.assertAlmostEqual(cpu.collision_top(), pg.TOP_MODERN, places=3)

    def test_a_pre_2014_moment_gets_the_30_ft_posts_and_nothing_else_moves(self):
        base = self.images()
        for index in (0, 20, 25, 28, 31, 38, 39):                           # rows 1, 21, 26, 29, 32, 39, 40 (all before 2014)
            cpu = self.run_case(8, index)
            self.assertAlmostEqual(cpu.line_top(), pg.TOP_PERIOD, places=3)
            self.assertAlmostEqual(cpu.collision_top(), pg.TOP_PERIOD, places=3)
            for name in goal.SCENES:
                spec = goal.SCENES[name]
                before = base[name][spec["positions"]:spec["positions"] + 6 * spec["vertices"]]
                after = cpu.positions(name)
                with self.subTest(row=index + 1, scene=name):
                    changed = [k for k in range(spec["vertices"]) if before[6 * k:6 * k + 6] != after[6 * k:6 * k + 6]]
                    self.assertEqual(len(changed), spec["tops"])
                    self.assertEqual(set(y_words(after)[k] for k in changed), {pg.WORD_PERIOD})
                    for k in changed:                                       # only the Y word of a top vertex
                        self.assertEqual(before[6 * k:6 * k + 2], after[6 * k:6 * k + 2])
                        self.assertEqual(before[6 * k + 4:6 * k + 6], after[6 * k + 4:6 * k + 6])
                    self.assertEqual(sum(a != b for a, b in zip(before, after)), 2 * spec["tops"])
                    height = lambda w, scale=687.1715698242188, off=685.7999877929688: w / 32767.0 * scale + off
                    self.assertAlmostEqual(height(pg.WORD_PERIOD), 1219.2, delta=0.01)       # 40 ft above the field
                    self.assertAlmostEqual(height(pg.WORD_MODERN), 1371.6, delta=0.01)       # 45 ft

    def test_a_modern_moment_keeps_35_ft(self):
        for index in (29, 30, 40, 45, 50):                                  # rows 30, 31, 41, 46, 51
            cpu = self.run_case(8, index)
            self.assertAlmostEqual(cpu.line_top(), pg.TOP_MODERN, places=3)
            self.assertAlmostEqual(cpu.collision_top(), pg.TOP_MODERN, places=3)
            for name in goal.SCENES:
                self.assertEqual(set(y_words(cpu.positions(name))) & {pg.WORD_PERIOD}, set(), (index, name))

    def test_the_height_follows_every_stadium_load(self):
        """The same scene memory: a moment, then a normal game, then another moment (the patch runs both ways)."""
        images = self.images()
        cpu = Cpu(images, 8, 3)
        stub = pg.labels(CODE_VA, RO_VA)["stub"]
        original = cpu.positions("goalpost")
        seen = []
        for mode, row in ((8, 3), (0, 0), (8, 45), (8, 3), (8, 3), (8, 12), (1, 12)):
            cpu.uc.mem_write(pg.MODE_VA, struct.pack("<I", mode))
            cpu.uc.mem_write(pg.ROW_VA, struct.pack("<I", row))
            cpu.run(stub)
            seen.append((cpu.positions("goalpost") == original, round(cpu.line_top(), 1)))
        self.assertEqual(seen, [(False, 1219.2), (True, 1371.6), (True, 1371.6), (False, 1219.2), (False, 1219.2),
                                (False, 1219.2), (True, 1371.6)])

    def test_foreign_scenes_are_left_alone(self):
        images = self.images()
        spec = goal.SCENES["goalpost"]
        wrong_count = bytearray(images["goalpost"])
        struct.pack_into("<H", wrong_count, spec["record"] + 0x4C, 242)
        retail_tops = bytearray(images["goalpost"])                         # a scene the v1 repair never touched (retail words)
        for k in range(spec["tops"]):
            struct.pack_into("<h", retail_tops, spec["positions"] + 6 * k + 2, 32767)
        for label, image in (("count", bytes(wrong_count)), ("retail", bytes(retail_tops))):
            with self.subTest(label):
                cpu = self.run_case(8, 0, {**images, "goalpost": image})
                self.assertEqual(cpu.positions("goalpost"), image[spec["positions"]:spec["positions"] + 6 * spec["vertices"]])
                after = cpu.positions("goalpost_shadow")            # the other, valid scene is still patched
                self.assertIn(pg.WORD_PERIOD, y_words(after))

    def test_a_missing_scene_is_skipped(self):
        cpu = self.run_case(8, 0, {"goalpost": synthetic_modern("goalpost")})
        self.assertIn(pg.WORD_PERIOD, y_words(cpu.positions("goalpost")))
        self.assertEqual(cpu.lookups, [pg.NAME_POST_VA, pg.NAME_SHADOW_VA])

    def test_the_site_stubs_follow_the_state_without_any_stored_cell(self):
        for mode, row, top in ((0, 0, pg.TOP_MODERN), (8, 3, pg.TOP_PERIOD), (8, 29, pg.TOP_MODERN), (8, 51, pg.TOP_MODERN),
                               (7, 3, pg.TOP_MODERN), (8, 39, pg.TOP_PERIOD), (8, 40, pg.TOP_MODERN)):
            cpu = Cpu(self.images(), mode, row)                              # no stadium load ran: nothing stored anywhere
            self.assertAlmostEqual(cpu.line_top(), top, places=3)
            self.assertAlmostEqual(cpu.collision_top(), top, places=3)


@unittest.skipUnless(HAVE_GAME, "needs the extracted retail files (NFL2K5_GAME_DIR)")
class RealScenes(unittest.TestCase):
    """The cave on the real compiled modern goalpost scenes: the decoded read-back gives 40 ft and 45 ft."""

    @classmethod
    def setUpClass(cls):
        pack0 = PACK0.read_bytes()
        at, size = goal.locate_outer(pack0)
        outer = pack0[at:at + size]
        where = goal.locate_chunks(outer)
        rows = {r["scene"]: r for r in goal.pins()["resources"]}
        cls.images = {}
        for scene in goal.SCENES:
            off, length = where[scene]
            span, _detail = goal.compile_span(outer[off:off + length], rows[scene])
            cls.images[scene] = goal.decode_span(span)

    def test_the_real_images_have_the_layout_the_cave_reads(self):
        for scene, image in self.images.items():
            spec = goal.SCENES[scene]
            u = lambda o: struct.unpack_from("<I", image, o)[0]
            self.assertEqual(u(0x14) + 0x14 - 1, 0x100)                      # the scene struct sits at body + 0x100
            self.assertEqual(u(0x12C), 1)                                    # one node
            self.assertEqual(0x130 + u(0x130) - 1, spec["record"])           # [scene+0x30] -> the node
            self.assertEqual(spec["record"] + 0xD4 + u(spec["record"] + 0xD4) - 1, spec["positions"])   # [node+0xd4] -> the stream
            self.assertEqual(struct.unpack_from("<H", image, spec["record"] + 0x4C)[0], spec["vertices"])
            # the engine's own node search (0x2EBB0 reads [scene+0x2C] nodes of 0x100 bytes at [scene+0x30], name = [node+0x40])
            at = spec["record"] + 0x40 + u(spec["record"] + 0x40) - 1
            self.assertEqual(image[at:at + 24].decode("utf-16le").split("\0")[0], {"goalpost": "goal", "goalpost_shadow": "goal_shadow"}[scene])
            words = y_words(image[spec["positions"]:spec["positions"] + 6 * spec["vertices"]])
            self.assertEqual(words.count(pg.WORD_MODERN), spec["tops"])
            self.assertEqual(words.count(pg.WORD_PERIOD), 0)

    def test_period_game_reads_back_as_40_ft_tops_and_the_modern_game_as_45_ft(self):
        for mode, row, feet in ((8, 25, 40.0), (8, 45, 45.0), (0, 0, 45.0)):
            cpu = Cpu(self.images, mode, row)
            cpu.run(pg.labels(CODE_VA, RO_VA)["stub"])
            for scene, spec in goal.SCENES.items():
                with self.subTest(mode=mode, row=row, scene=scene):
                    stream = cpu.positions(scene)
                    scale = struct.unpack_from("<f", self.images[scene], spec["record"] + 0x10)[0]
                    off = struct.unpack_from("<f", self.images[scene], spec["record"] + 0x24)[0]
                    heights = [w / 32767.0 * scale + off if w >= 0 else w / 32768.0 * scale + off for w in y_words(stream)]
                    self.assertAlmostEqual(max(heights) / 30.48, feet, delta=0.01)
                    self.assertAlmostEqual(sorted(heights)[0], 0.0, delta=0.05)         # the foot of the post is unchanged
                    self.assertEqual(sum(1 for h in heights if abs(h - 1219.2) < 0.05 or abs(h - 1371.6) < 0.05), spec["tops"])


@unittest.skipUnless(HAVE_V05, "needs a v0.5 default.xbe (B77_V05_DIR)")
class V05Executable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = V05.read_bytes()
        cls.new, cls.receipt = pg.apply(cls.xbe)

    def test_extension_adds_one_owner_and_moves_no_other(self):
        self.assertEqual(self.receipt["status"], "applied")
        self.assertTrue(self.receipt["directory_extended"])
        key = lambda a: (a["owner"], a["kind"], a["va"], a["raw"], a["size"])
        before = {key(a) for a in space.layout(self.xbe)["allocations"]}
        after = {key(a) for a in space.layout(self.new)["allocations"]}
        self.assertEqual(before - after, set())
        self.assertEqual({a[0] for a in after - before}, {pg.OWNER})
        self.assertEqual(len(after - before), 2)
        self.assertEqual(space.status(self.new), "applied")
        self.assertEqual(pg.status(self.new), "applied")
        self.assertEqual(pg.status(self.xbe), "retail")

    def test_idempotent_and_the_v1_route_converges(self):
        again, receipt = pg.apply(self.new)
        self.assertEqual((again, receipt["status"]), (self.new, "already_applied"))

    def test_the_cave_in_the_installed_executable_is_the_assembled_code(self):
        a = pg.allocations(self.new)
        self.assertEqual(self.new[a["code"]["raw"]:a["code"]["raw"] + pg.CODE_SIZE], pg.code_for(a["code"]["va"], a["read_only"]["va"]))
        self.assertEqual(self.new[a["read_only"]["raw"]:a["read_only"]["raw"] + pg.RO_SIZE], pg.tables())


class StudioWiring(unittest.TestCase):
    def test_requests_ride_with_the_flag_and_the_owner_is_placed_last(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        self.assertNotIn(pg.REQUESTS[0], tt._selected_space_requests())
        self.assertEqual([r for r in tt._selected_space_requests(period_goalposts=True) if r[0] == pg.OWNER], list(pg.REQUESTS))
        self.assertIn(pg.OWNER, space.LATE_OWNERS)
        self.assertEqual(space.LATE_OWNER, "nfl2k5_k128")
        self.assertTrue(set(pg.REQUESTS) <= set(space.dormant_union()))

    def test_the_build_derives_the_flag_from_modern_goalposts_on_images(self):
        from types import SimpleNamespace
        from mod_editor.core import mod_build
        self.assertTrue(mod_build._period_goalposts_wanted(SimpleNamespace(modern_goalposts=True), True))
        self.assertFalse(mod_build._period_goalposts_wanted(SimpleNamespace(modern_goalposts=True), False))
        self.assertFalse(mod_build._period_goalposts_wanted(SimpleNamespace(modern_goalposts=False), True))
        self.assertIn("period_goalposts", mod_build.tt.R62_SPACE_KEYS)
        self.assertIsNone(mod_build._r62_plan_options(SimpleNamespace(**{k: None for k in mod_build.tt.R62_RUNTIME_KEYS}))["period_goalposts"])

    def test_the_manifest_generator_knows_the_owner(self):
        text = (ROOT / "mod_editor/core/nfl2k5_cave_manifest.py").read_text()
        self.assertGreaterEqual(text.count("nfl2k5_period_goalposts"), 2)
        self.assertIn("+ period.REQUESTS", text)
        self.assertIn("final, _ = period.apply(final)", text)


@unittest.skipUnless(HAVE_GAME, "needs the extracted retail files (NFL2K5_GAME_DIR)")
class RetailStudioAssembly(unittest.TestCase):
    def test_the_studio_xbe_pass_installs_the_owner_and_the_v1_module_reads_it_as_applied(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        retail = (GAME / "default.xbe").read_bytes()
        out, receipt = tt._apply_all(retail, None, False, xbe_space=True, period_goalposts=True)
        self.assertEqual((space.status(out), pg.status(out), goal.xbe_status(out)), ("applied", "applied", "applied"))
        self.assertEqual(receipt["period_goalposts_patch"]["status"], "applied")
        self.assertEqual(pg.apply(out)[0], out)
        with self.assertRaises(goal.ModernGoalpostsError):
            goal.restore_xbe(out)
        rows = goal.xbe_reservations(out)
        self.assertEqual([r["size"] for r in rows], [4, 5, 5, 6])
        self.assertEqual(rows[0]["start"], hex(pg.LOAD_CALL_VA + 1))


@unittest.skipUnless(HAVE_V05, "needs a v0.5 default.xbe (B77_V05_DIR)")
class V05Stacking(unittest.TestCase):
    def test_v1_then_v1b_equals_v1b_alone(self):
        xbe = V05.read_bytes()
        v1, _ = goal.apply_xbe(xbe)
        self.assertEqual(pg.status(v1), "modern")
        self.assertEqual(pg.apply(v1)[0], pg.apply(xbe)[0])

    def test_the_repair_script_scope_and_idempotence(self):
        import importlib.util, tempfile
        spec = importlib.util.spec_from_file_location("v1b_repair", ROOT / "tools/b77/v1b_repair.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        xbe = V05.read_bytes()
        new, receipt = mod.repair(xbe)
        self.assertEqual(receipt["status"], "OK")
        scope = receipt["files"]["default.xbe"]["scope"]
        self.assertEqual(scope["bytes_changed_outside"], 0)
        self.assertGreater(scope["bytes_changed_inside"], 300)
        again, receipt2 = mod.repair(new)
        self.assertEqual((again, receipt2["status"]), (new, "ALREADY_APPLIED"))
        broken = bytearray(xbe)
        broken[mod.XbeImage(xbe).offset(pg.LINE_LEFT_VA, 5)] = 0x90          # a foreign byte at an owned site
        with self.assertRaises(ValueError):
            mod.repair(bytes(broken))


if __name__ == "__main__":
    unittest.main()
