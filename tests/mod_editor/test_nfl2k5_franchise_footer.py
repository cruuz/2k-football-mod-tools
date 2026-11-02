"""b780 j23: the franchise extension footer host (nfl2k5_franchise_footer) and its format (nfl2k5_franchise_extension).

Native tests run the installed host blob under Unicorn with the game's globals and the displaced call targets mocked:
size, save, load and admission must follow the published size family; a load keeps good blocks, rebuilds a bad one,
starts fresh on a bad header; the body comes from the executable (static), the K128 extra region, or nowhere (paused);
the Player Progress footer it hosts keeps that owner's old-save rule. Static tests install it on the pinned retail
executable (alone, beside Auto Save) and check that every companion owner still reads its own bytes.
"""

from __future__ import annotations

import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_extension as ext  # noqa: E402
from mod_editor.core import nfl2k5_franchise_footer as footer  # noqa: E402
from mod_editor.core import nfl2k5_player_progression as record  # noqa: E402
from mod_editor.core import nfl2k5_roster_arena as arena  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe  # noqa: E402

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

CODE, DATA = 0x03000000, 0x03010000
FILE, META, BUFFER = 0x05000000, 0x07000000, 0x06100000
TARGETS, PP_DATA, PP_BASELINE = 0x06000000, 0x08000000, 0x06000100
REGION, ALLOC_HEAP = 0x09000000, 0x0A000000
STACK, SENTINEL = 0x04000000, 0x04080000
SEEDS = 0x0B000000


def _native_save(arena_size: int) -> bytes:
    """A minimal franchise-shaped native save of this arena: the ROST wrapper words the loaders read."""
    size = arena.save_size(arena_size)
    out = bytearray(size)
    growth = size - arena.RETAIL_SAVE_SIZE
    out[0x2E0:0x2E4] = b"ROST"
    struct.pack_into("<I", out, 0x2E4, 0x91020 + growth)
    out[0x30C:0x310] = b"ROST"
    struct.pack_into("<II", out, 0x310, int(bool(growth)), 13)
    out[0x91320 + growth] = 2
    return bytes(out)


@unittest.skipIf(uc is None, "Unicorn is required")
class NativeTests(unittest.TestCase):
    def machine(self, *, static=True, pp=False, main_heap=False, region=False, seeds=None):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for base, size in ((CODE, 0x2000), (DATA, 0x20000), (FILE, 0x200000), (META, 0xC00000), (BUFFER, 0x200000),
                           (TARGETS, 0x1000), (PP_DATA, 0x10000), (REGION, 0x40000), (ALLOC_HEAP, 0x40000),
                           (SEEDS, 0x10000), (0xB01000, 0x1000), (0xB04000, 0x1000), (0xB72000, 0x1000),
                           (0xE57000, 0x1000), (0x48000, 0x1000), (STACK, 0x10000)):
            m.mem_map(base, size)
        config = {"state": DATA, "static_body": DATA + footer.STATE_SIZE if static else 0,
                  "pp_footer": PP_DATA + 16 if pp else 0, "pp_baseline": PP_BASELINE if pp else 0,
                  "chain_size": TARGETS, "chain_save": TARGETS + 0x10, "chain_load": TARGETS + 0x20,
                  "chain_franchise": TARGETS + 0x30, "flags": footer.FLAG_MAIN_HEAP if main_heap else 0,
                  "seeds": SEEDS if seeds else 0}
        self.blob = footer.code_for(CODE, config, bytes.fromhex("e856feffffeb13"))
        m.mem_write(CODE, self.blob)
        m.mem_write(0xE576A0, struct.pack("<I", 2))            # franchise
        m.mem_write(0xE576A4, struct.pack("<I", 8))
        m.mem_write(0xE576B4, struct.pack("<I", 5))
        m.mem_write(0xE576B8, struct.pack("<I", 3))
        m.mem_write(0xB72808, struct.pack("<I", 0xCA000))
        if region:
            m.mem_write(0xB018B8, struct.pack("<II", REGION, REGION + 0x40000))
            m.mem_write(REGION + 0x98, struct.pack("<I", 0x50414548))
        # 0x48700 (ecx heap, edx size): a bump allocator over ALLOC_HEAP that records the heap it was asked for
        m.mem_write(0x48700, bytes.fromhex(
            "890d00080400"                 # mov [0x40800],ecx (the heap asked for)
            "a104080400"                   # mov eax,[0x40804] (next)
            "85c0" "7505"                  # test eax,eax ; jnz +5
            "b8" + struct.pack("<I", ALLOC_HEAP).hex() +
            "01c2"                         # add edx,eax
            "891504080400"                 # mov [0x40804],edx
            "c3"))
        m.mem_map(0x40000, 0x1000)
        ret_imm = lambda va, value: m.mem_write(va, b"\xb8" + struct.pack("<I", value) + b"\xc3")
        ret_imm(TARGETS, 0x165B0)                               # displaced size: the front office
        m.mem_write(TARGETS + 0x10, b"\xc3")                    # displaced writer
        ret_imm(TARGETS + 0x20, 0x165B0)                        # displaced load-end call
        m.mem_write(TARGETS + 0x30, b"\xc7\x05" + struct.pack("<I", TARGETS + 0x800) + struct.pack("<I", 0x13ED70) + b"\xc3")
        m.mem_write(PP_BASELINE, b"\xc7\x05" + struct.pack("<I", PP_DATA) + b"BASE" + b"\xc3")
        if seeds:
            table = bytearray(64)
            at = SEEDS + 64
            for block_id, content in seeds.items():
                m.mem_write(at, content)
                struct.pack_into("<I", table, 4 * (block_id - 1), at)
                at += (len(content) + 15) & ~15
            m.mem_write(SEEDS, bytes(table))
        return m

    def call(self, m, label, ecx=0, edx=0, esi=0, ebp=0, ebx=0, stack=()):
        sp = STACK + 0x8000
        for value in reversed(stack):
            sp -= 4
            m.mem_write(sp, struct.pack("<I", value))
        sp -= 4
        m.mem_write(sp, struct.pack("<I", SENTINEL))
        for reg, value in ((x86.UC_X86_REG_ESP, sp), (x86.UC_X86_REG_ECX, ecx), (x86.UC_X86_REG_EDX, edx),
                           (x86.UC_X86_REG_ESI, esi), (x86.UC_X86_REG_EBP, ebp), (x86.UC_X86_REG_EBX, ebx),
                           (x86.UC_X86_REG_EAX, 0), (x86.UC_X86_REG_EDI, 0x1234)):
            m.reg_write(reg, value)
        start = CODE + footer.runtime.LABELS[label]
        try:
            m.emu_start(start, SENTINEL, count=20_000_000, timeout=60_000_000)
        except uc.UcError as exc:
            self.fail(f"{label} faulted at 0x{m.reg_read(x86.UC_X86_REG_EIP):x}: {exc}")
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), SENTINEL, label)
        return m.reg_read(x86.UC_X86_REG_EAX)

    def body(self, m):
        pointer = struct.unpack("<I", m.mem_read(DATA + 4, 4))[0]
        return pointer, (bytes(m.mem_read(pointer, ext.BODY_SIZE)) if pointer else None)

    def size(self, m):
        return self.call(m, "xt_size_hook")

    def save(self, m, total, native=b""):
        m.mem_write(BUFFER, bytes(native) + bytes(total - len(native)))
        self.call(m, "xt_save_hook", ecx=BUFFER + 0x1000, esi=BUFFER, ebx=total)
        return bytes(m.mem_read(BUFFER, total))

    def load(self, m, payload):
        """Run the load-end hook on this file; returns the host's load result (the hook itself returns the
        displaced call's eax)."""
        m.mem_write(FILE, payload)
        m.mem_write(META + 0xBDC1CC, struct.pack("<I", len(payload)))
        self.assertEqual(self.call(m, "xt_load_hook", esi=FILE, ebp=META), 0x165B0)
        return struct.unpack("<I", m.mem_read(DATA + footer.STATE_FIELDS["load_result"], 4))[0]

    # ---------------------------------------------------------------- size and save
    def test_static_body_is_made_at_the_first_size_and_saved_sealed(self):
        m = self.machine(static=True)
        self.assertEqual(self.body(m)[0], 0)
        self.assertEqual(self.size(m), 0x165B0 + ext.BODY_SIZE)
        pointer, body = self.body(m)
        self.assertEqual(pointer, DATA + footer.STATE_SIZE)
        view = ext.read_body(body)
        self.assertTrue(view["header_ok"])
        self.assertEqual(view["bad"], [])
        self.assertEqual(view["info"]["fresh_reason"], 4)          # first use
        self.assertEqual(view["info"]["source"], 1)                # executable memory
        native = _native_save(0xCA000)
        total = len(native) + ext.BODY_SIZE
        saved = self.save(m, total)
        written = saved[len(native):]
        again = ext.read_body(written)
        self.assertTrue(again["header_ok"])
        self.assertEqual(again["bad"], [])
        self.assertEqual(again["header"]["saves"], 1)
        self.assertEqual((again["header"]["year_index"], again["header"]["stage"], again["header"]["week"]), (3, 8, 5))
        self.assertFalse(again["header"]["pp_follows"])
        self.assertEqual(saved[:len(native)], bytes(len(native)))  # nothing before the footer was touched
        # the Studio's seal of the same content is the same bytes (block and header checksums)
        self.assertEqual(ext.seal(written), written)

    def test_outside_franchise_the_size_hook_never_allocates(self):
        m = self.machine(static=True)
        m.mem_write(0xE576A0, struct.pack("<I", 0))
        self.assertEqual(self.size(m), 0x165B0)
        self.assertEqual(self.body(m)[0], 0)

    def test_hosted_player_progress_footer_is_always_last(self):
        m = self.machine(static=True, pp=True)
        roster = [{"pbp_id": 10 + i, "position": 0, "jersey": i, "overall": 70,
                   "ratings": [50] * record.RATING_COUNT} for i in range(record.TEAM_SLOTS)]
        progress = record.baseline(roster, year=2027, team=3)
        m.mem_write(PP_DATA + 16, progress)
        self.assertEqual(self.size(m), 0x165B0 + ext.BODY_SIZE + ext.PP_SIZE)
        native = _native_save(0xCA000)
        payload = native + bytes(ext.BODY_SIZE + ext.PP_SIZE)
        saved = self.save(m, len(payload), native)
        found = ext.layout(saved)
        self.assertIsNotNone(found)
        self.assertEqual((found.body_offset, found.pp_offset), (len(native), len(native) + ext.BODY_SIZE))
        self.assertEqual(saved[-ext.PP_SIZE:], progress)
        self.assertEqual(record.footer_start(saved), len(saved) - ext.PP_SIZE)
        self.assertTrue(ext.read_body(ext.body_of(saved))["header"]["pp_follows"])

    def test_extra_memory_and_paused_history(self):
        # K128 build (no static body): the extra region's heap gives the body
        m = self.machine(static=False, region=True)
        self.assertEqual(self.size(m), 0x165B0 + ext.BODY_SIZE)
        self.assertEqual(struct.unpack("<I", m.mem_read(0x40800, 4))[0], REGION)   # asked the extra heap
        self.assertEqual(self.body(m)[0], ALLOC_HEAP)
        self.assertEqual(struct.unpack("<I", m.mem_read(DATA + 12, 4))[0], 2)
        # xemu at 64 MB: no region, no main heap: the history pauses, saves carry no body
        m = self.machine(static=False, region=False)
        self.assertEqual(self.size(m), 0x165B0)
        self.assertEqual(self.body(m)[0], 0)
        self.assertEqual(struct.unpack("<I", m.mem_read(DATA + 8, 4))[0] & 1, 1)
        native = _native_save(0xCA000)
        self.assertEqual(self.load(m, native + ext.empty_body()), 5)                 # dropped: no memory
        self.assertEqual(struct.unpack("<I", m.mem_read(DATA + 8, 4))[0] & 2, 2)
        # the main-heap fallback, only when the build allows it
        m = self.machine(static=False, region=False, main_heap=True)
        self.assertEqual(self.size(m), 0x165B0 + ext.BODY_SIZE)
        self.assertEqual(struct.unpack("<I", m.mem_read(0x40800, 4))[0], 0xB04E24)

    # ---------------------------------------------------------------- load
    def test_load_keeps_good_blocks_rebuilds_bad_ones_and_restarts_on_a_bad_header(self):
        native = _native_save(0xCA000)
        body = ext.empty_body()
        lines = [ext.season_club_line(10, 7, 0, place=2, points_for=400, points_against=350,
                                      coach=ext.pack_person("Andy", "Reid")) for _ in range(32)]
        seasons = ext.encode_seasons([ext.season_record(2026, lines, champion=9, runner_up=3, champion_points=31,
                                                        runner_points=17)])
        body = ext.with_block(body, "seasons", seasons)
        totals = ext.encode_totals(2026, 1, [{"wins": 10, "losses": 7} for _ in range(32)])
        body = ext.with_block(body, "totals", totals)
        m = self.machine(static=True)
        self.assertEqual(self.load(m, native + body), 2)
        pointer, ram = self.body(m)
        self.assertEqual(ext.block_of(ram, "seasons"), seasons)
        self.assertEqual(ext.decode_seasons(ext.block_of(ram, "seasons"))[0]["clubs"][0]["coach"]["last"], "REID")
        info = ext.read_body(ram)["info"]
        self.assertEqual((info["load_result"], info["repaired_mask"], info["loads"]), (2, 0, 1))
        # one damaged block (bit flip inside totals): only that block is rebuilt
        bad = bytearray(body)
        bad[ext.BLOCK_BY_NAME["totals"].offset + 20] ^= 0x40
        self.assertEqual(self.load(m, native + bytes(bad)), 4)
        _p, ram = self.body(m)
        view = ext.read_body(ram)
        self.assertEqual(view["bad"], [])
        self.assertEqual(view["blocks"][1], seasons)
        self.assertEqual(view["blocks"][2], bytes(ext.BLOCK_BY_NAME["totals"].size))
        self.assertEqual(view["info"]["repaired_mask"], 1 << 1)
        # a damaged header: a fresh body
        bad = bytearray(body)
        bad[3] ^= 1
        self.assertEqual(self.load(m, native + bytes(bad)), 3)
        _p, ram = self.body(m)
        self.assertEqual(ext.read_body(ram)["blocks"][1], bytes(ext.BLOCK_BY_NAME["seasons"].size))
        self.assertEqual(ext.read_body(ram)["info"]["fresh_reason"], 3)
        # a save without a body resets an allocated body (another franchise's history never leaks)
        self.load(m, native + body)
        self.assertEqual(self.load(m, native), 1)
        _p, ram = self.body(m)
        self.assertEqual(ext.read_body(ram)["blocks"][1], bytes(ext.BLOCK_BY_NAME["seasons"].size))
        self.assertEqual(ext.read_body(ram)["info"]["fresh_reason"], 2)

    def test_unknown_blocks_of_a_newer_build_survive_a_round_trip(self):
        native = _native_save(0xCA000)
        body = bytearray(ext.empty_body())
        payload = b"newer build block" * 4
        at = ext.FREE_OFFSET
        body[at:at + len(payload)] = payload
        struct.pack_into("<HBBIII", body, ext.DIRECTORY_OFFSET + 6 * 16, 7, 1, 1, at, len(payload),
                         zlib.adler32(payload))
        struct.pack_into("<I", body, ext.CHECKSUM_AT, ext._header_sum(body))
        self.assertEqual(ext.read_body(bytes(body))["unknown"], [7])
        m = self.machine(static=True)
        self.assertEqual(self.load(m, native + bytes(body)), 2)
        saved = self.save(m, len(native) + ext.BODY_SIZE, native)
        again = ext.read_body(saved[len(native):])
        self.assertEqual(again["unknown"], [7])
        self.assertEqual(saved[len(native) + at:len(native) + at + len(payload)], payload)

    def test_v08_player_progress_save_converts(self):
        roster = [{"pbp_id": 10 + i, "position": 0, "jersey": i, "overall": 70,
                   "ratings": [55] * record.RATING_COUNT} for i in range(record.TEAM_SLOTS)]
        progress = record.baseline(roster, year=2026, team=9)
        native = _native_save(0xCA000)
        for career in (False, True):
            m = self.machine(static=True, pp=True)
            v08 = native + (bytes(128) if career else b"") + progress     # 987,836 / 987,964
            self.assertEqual(len(v08), 987836 + 128 * career)
            self.assertEqual(self.load(m, v08), 1)                          # no body yet: history starts empty
            self.assertEqual(bytes(m.mem_read(PP_DATA + 16, ext.PP_SIZE)), progress)
            self.assertEqual(bytes(m.mem_read(PP_DATA, 4)), bytes(4))       # no fresh baseline was needed
            total = len(native) + 128 * career + ext.BODY_SIZE + ext.PP_SIZE
            self.assertEqual(self.size(m), 0x165B0 + ext.BODY_SIZE + ext.PP_SIZE)
            saved = self.save(m, total, native + (bytes(128) if career else b""))
            self.assertEqual(saved[-ext.PP_SIZE:], progress)
            self.assertTrue(ext.read_body(ext.body_of(saved))["header_ok"])
        # a v0.7 save (the all-zero progress footer) and a save without one: the progress owner's fresh baseline
        for payload in (native + bytes(ext.PP_SIZE), native):
            m = self.machine(static=True, pp=True)
            m.mem_write(PP_DATA + 16, b"\xff" * ext.PP_SIZE)
            self.load(m, payload)
            self.assertEqual(bytes(m.mem_read(PP_DATA, 4)), b"BASE")
            self.assertEqual(bytes(m.mem_read(PP_DATA + 16, ext.PP_SIZE)), bytes(ext.PP_SIZE))

    def test_seeds_fill_a_fresh_body(self):
        hall = ext.encode_hall(candidates=[ext.candidate_entry(ext.pack_person("Tom", "Brady", "QB"), 20, 2022,
                                                               score=900, flags=ext.HALL_REAL)])
        m = self.machine(static=True, seeds={5: hall})
        self.size(m)
        _p, ram = self.body(m)
        self.assertEqual(ext.block_of(ram, "hall"), hall)
        self.assertEqual(ext.decode_hall(hall)["candidates"][0]["person"]["last"], "BRADY")
        self.assertEqual(ext.read_body(ram)["blocks"][5], hall)
        self.assertEqual(ext.empty_body(seeds={5: hall}, stamp=footer.STAMP)[:ext.INFO_OFFSET], ram[:ext.INFO_OFFSET])

    # ---------------------------------------------------------------- admission and new franchise
    def test_admission_is_the_published_family(self):
        m = self.machine(static=True)
        m.mem_write(META, bytes(0xC00000))
        for arena_size in (0x91000, 0x92000, 0xB0000, 0xCA000):
            m.mem_write(0xB72808, struct.pack("<I", arena_size))
            accepted = set(ext.admitted_sizes(arena_size))
            probes = set()
            for size in accepted:
                probes.update((size - 1, size, size + 1, size + 16, size - 128, size + 4096))
            for native in ext.NATIVE_SIZES:
                for extra in (0, 64, 128, 256, 4096, 34320, 98288, 132608, 132736, 132864):
                    probes.add(native + extra)
            for size in sorted(probes):
                m.mem_write(META + 0xBDC1CC, struct.pack("<I", size))
                got = self.call(m, "xt_admission", esi=META, stack=(SENTINEL,))
                self.assertEqual(got, 0 if size in accepted else 1, (hex(arena_size), size))

    def test_new_franchise_starts_fresh_and_chains(self):
        native = _native_save(0xCA000)
        m = self.machine(static=True)
        body = ext.with_block(ext.empty_body(), "totals", ext.encode_totals(2026, 3, [{"wins": 30}] * 32))
        self.load(m, native + body)
        self.call(m, "xt_franchise_hook", ecx=1)
        _p, ram = self.body(m)
        self.assertEqual(ext.read_body(ram)["blocks"][2], bytes(ext.BLOCK_BY_NAME["totals"].size))
        self.assertEqual(ext.read_body(ram)["info"]["fresh_reason"], 1)
        self.assertEqual(struct.unpack("<I", m.mem_read(TARGETS + 0x800, 4))[0], 0x13ED70)   # the chain ran


class FormatTests(unittest.TestCase):
    def test_sizes_never_collide_and_layout_splits_every_combination(self):
        sizes = ext.franchise_sizes()
        self.assertEqual(len(sizes), len(set(sizes)))
        for native in ext.NATIVE_SIZES:
            arena_size = native - arena.RETAIL_SAVE_SIZE + arena.RETAIL_SIZE
            base = _native_save(arena_size if arena_size != arena.RETAIL_SIZE else arena.RETAIL_SIZE)
            for career in (False, True):
                for body in (None, ext.empty_body()):
                    for pp in (None, record.empty_footer(year=2026, team=1)):
                        payload = base + (bytes(128) if career else b"") + (body or b"") + (pp or b"")
                        found = ext.layout(payload)
                        self.assertIsNotNone(found)
                        self.assertEqual(found.native_size, native)
                        self.assertEqual(found.career_offset is not None, career)
                        self.assertEqual(found.body_offset is not None, body is not None)
                        self.assertEqual(found.pp_offset is not None, pp is not None)
                        self.assertEqual(ext.native_length(payload), native + 128 * career)
                        self.assertIn(len(payload), ext.admitted_sizes(max(arena_size, 0x91000)))
                        if pp is not None:
                            self.assertEqual(record.footer_start(payload), len(payload) - ext.PP_SIZE)

    def test_mycareer_career_bit_rule_holds_for_every_footer(self):
        # tools/mycareer_mode/runtime.c inline_stage/admit_one: the career block is present exactly when bit 7 of
        # (rest + 16) is set, for rest = footer or footer + 128
        for footer_size in ext.FOOTER_SIZES:
            self.assertEqual((footer_size + 16) & 128, 0, footer_size)
            self.assertEqual((footer_size + 128 + 16) & 128, 128, footer_size)

    def test_with_body_round_trips_and_keeps_every_other_byte(self):
        native = bytearray(_native_save(0xCA000))
        native[100:110] = b"native!!!!"
        progress = record.empty_footer(year=2026, team=4)
        payload = bytes(native) + bytes(range(128)) + progress
        body = ext.with_block(ext.empty_body(), "totals", ext.encode_totals(2026, 1, [{"wins": 1}] * 32))
        out = ext.with_body(payload, body)
        self.assertEqual(out[:len(native) + 128], payload[:len(native) + 128])
        self.assertEqual(out[-ext.PP_SIZE:], progress)
        self.assertEqual(ext.body_of(out), body)
        self.assertEqual(ext.with_body(out, None), payload)

    def test_block_codecs_round_trip(self):
        person = ext.pack_person("Patrick", "Mahomes", "QB")
        records = ext.encode_records({(9, "passing_yards", "season"): ext.record_entry(person, 9, 5250, 2027)},
                                     {("passing_td", "game"): ext.record_entry(person, 9, 7, 2028, 4)})
        view = ext.decode_records(records)
        self.assertEqual(view["clubs"][(9, "passing_yards", "season")]["value"], 5250)
        self.assertEqual(view["league"][("passing_td", "game")]["week_row"], 4)
        leaders = ext.encode_leaders({(9, "passing_yards"): [ext.leader_entry(person, 41000, flags=ext.LEADER_REAL
                                                                              | ext.LEADER_LINKED, player=1234)]})
        lv = ext.decode_leaders(leaders)
        self.assertEqual(lv["clubs"][(9, "passing_yards")][0]["value"], 41000)
        self.assertTrue(lv["clubs"][(9, "passing_yards")][0]["linked"])
        hall = ext.decode_hall(ext.encode_hall([ext.inductee_entry(person, 9, 2040, 2034, flags=ext.HALL_NEW)]))
        self.assertEqual(hall["inductees"][0]["inducted"], 2040)
        self.assertEqual(sum(b.size for b in ext.BLOCKS) + ext.BLOCK_AREA + ext.FREE_BYTES, ext.BODY_SIZE)


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def test_retail_reads_retail_and_a_bare_install_round_trips(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertEqual(footer.status(self.retail), "retail")
        payload, _ = space.apply(self.retail, (), scaleout=True)
        installed, receipt = footer.apply(payload, static_body=True)
        self.assertEqual(footer.status(installed), "applied")
        self.assertEqual(receipt["chains"], {"chain_size": "0x2d0780", "chain_save": "0x2d0790",
                                             "chain_load": "0x2d0780", "chain_franchise": "0x13ed70"})
        self.assertEqual(footer.apply(installed, static_body=True)[1]["status"], "already_applied")
        view = footer.underlying_view(installed)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(view)
        for _label, va, before, *_rest in footer.SITE_TABLE:
            self.assertEqual(image.read(va, len(before)), before)
        # a foreign byte in a guarded context is refused
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        self.assertEqual(footer.status(repin_edit(installed, 0x16AA2B, b"\x90")), "foreign")

    def test_beside_auto_save_and_the_progress_row(self):
        from mod_editor.core import nfl2k5_franchise_autosave as autosave
        from mod_editor.core import nfl2k5_player_progress_screen as progress
        payload, _ = autosave.apply(self.retail)
        payload, _ = progress.apply(payload, visible_only=True)
        payload, _ = footer.apply(payload, static_body=True)
        self.assertEqual(footer.status(payload), "applied")
        self.assertEqual(autosave.status(payload), "applied")
        self.assertEqual(progress.variant(payload), "visible")
        # the full Player Progress owner keeps its own footer: the host refuses to stack on it
        full, _ = progress.apply(autosave.apply(self.retail)[0])
        with self.assertRaises(ValueError):
            footer.apply(full, static_body=True)


if __name__ == "__main__":
    unittest.main()
