"""The overtime patch must stay pattern-driven, fail-closed and byte-exact.

Fixtures are synthetic: a minimal XBE with a valid 22-section table whose `.text` section
carries the retail bytes at every hook site plus the two dead functions that host the caves,
with a correct section digest.  No game file is touched; a retail-XBE smoke test runs only when
the private copy exists.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_overtime as ot  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x200
HEADER_SIZE = 0xCC4
TEXT_VA = 0x11000
TEXT_RAW = 0x2000
TEXT_SIZE = 0x320000
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None


def _section_digest(payload: bytes, raw: int, raw_size: int) -> bytes:
    return hashlib.sha1(  # nosec B324 - XBE section scheme, not security
        struct.pack("<I", raw_size) + payload[raw: raw + raw_size]
    ).digest()


def _text_off(va: int) -> int:
    return TEXT_RAW + (va - TEXT_VA)


def _retail_sites() -> list[tuple[int, bytes]]:
    return [(ot.MAIN_CAVE_VA, ot.RETAIL_MAIN_CAVE), (ot.AUX_CAVE_VA, ot.RETAIL_AUX_CAVE),
            (ot.INIT_SITE_VA, ot.RETAIL_INIT), (ot.OT_KICKOFF_SITE_VA, ot.RETAIL_OT_KICKOFF),
            (ot.KICKOFF_SITE_VA, ot.RETAIL_KICKOFF), (ot.SITUATION_SITE_VA, ot.RETAIL_SITUATION),
            (ot.PRED_SITE_VA, ot.RETAIL_PRED),
            (ot.EXPIRY_SITE_VA, ot.RETAIL_EXPIRY), (ot.EXPIRY2_SITE_VA, ot.RETAIL_EXPIRY2),
            (ot.SIM_RESET_SITE_VA, ot.RETAIL_SIM_RESET), (ot.SIM_ROLL_SITE_VA, ot.RETAIL_SIM_ROLL),
            (ot.SIM_TIE_SITE_VA, ot.RETAIL_SIM_TIE), (ot.SIM_PERIOD_SITE_VA, ot.RETAIL_SIM_PERIOD)]


def _build_synthetic_xbe() -> bytes:
    buf = bytearray(TEXT_RAW + TEXT_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<I", buf, 0x108, HEADER_SIZE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index == 0:
            fields[1] = TEXT_VA
            fields[3] = TEXT_RAW
            fields[4] = TEXT_SIZE
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    for va, retail in _retail_sites():
        buf[_text_off(va): _text_off(va) + len(retail)] = retail
    header = TABLE_OFF
    buf[header + 36: header + 56] = _section_digest(bytes(buf), TEXT_RAW, TEXT_SIZE)
    return bytes(buf)


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


class ScaleTests(unittest.TestCase):
    def test_scale_is_nfl_minutes_over_a_quarter(self) -> None:
        self.assertAlmostEqual(ot.scale_for(10), 10 / 15)
        self.assertAlmostEqual(ot.scale_for(15), 1.0)
        self.assertEqual(ot.overtime_clock_seconds(15, 10), 600.0)      # 15-minute quarters: 10:00
        self.assertEqual(ot.overtime_clock_seconds(5, 10), 200.0)       # retail default 5-minute quarters: 3:20
        self.assertEqual(ot.overtime_clock_seconds(5, 15), 300.0)       # retail behaviour

    def test_minutes_are_validated(self) -> None:
        for bad in (0, 0.5, 16, -3, "x"):
            with self.assertRaises((ot.OvertimeError, ValueError, TypeError)):
                ot.scale_for(bad)


class CaveShapeTests(unittest.TestCase):
    def test_caves_fit_their_dead_functions(self) -> None:
        main = ot.main_cave_bytes()
        aux = ot.aux_cave_bytes()
        self.assertEqual(len(main), ot.MAIN_CAVE_SIZE)
        self.assertEqual(len(aux), ot.AUX_CAVE_SIZE)
        self.assertEqual(len(ot.RETAIL_MAIN_CAVE), ot.MAIN_CAVE_SIZE)
        self.assertEqual(len(ot.RETAIL_AUX_CAVE), ot.AUX_CAVE_SIZE)
        self.assertTrue(main.endswith(b"\xcc"))
        self.assertTrue(aux.endswith(b"\xcc"))
        for retail in (ot.RETAIL_MAIN_CAVE, ot.RETAIL_AUX_CAVE):
            self.assertEqual(retail[:3], bytes.fromhex("558bec"), "cave hosts start with push ebp / mov ebp, esp")
        self.assertEqual(ot.RETAIL_MAIN_CAVE[-1:], b"\xc3")
        self.assertEqual(ot.RETAIL_AUX_CAVE[-3:], bytes.fromhex("c20400"))

    def test_scale_float_is_the_only_setting_dependent_byte_run(self) -> None:
        default = ot.main_cave_bytes(10)
        other = ot.main_cave_bytes(12)
        self.assertNotEqual(default[:4], other[:4])
        self.assertEqual(default[4:], other[4:])
        self.assertEqual(struct.unpack("<f", default[:4])[0], _f32(10 / 15))
        self.assertEqual(ot.aux_cave_bytes(), ot.aux_cave_bytes())

    def test_labels_and_cross_cave_calls_resolve(self) -> None:
        labels = ot.cave_labels()
        for name in ("init", "flag_team", "ot_check", "not_over", "over", "ot_expiry", "exp_tied", "exp_differ"):
            self.assertTrue(ot.MAIN_CODE_VA <= labels[name] < ot.MAIN_CAVE_VA + ot.MAIN_CAVE_SIZE, name)
        for name in ("ot_kickoff", "kickoff_flag", "situation", "sim_reset", "sim_roll", "sim_tie", "sim_period"):
            self.assertTrue(ot.AUX_CAVE_VA <= labels[name] < ot.AUX_CAVE_VA + ot.AUX_CAVE_SIZE, name)
        aux = ot.aux_cave_bytes()
        # every call in the aux cave targets flag_team in the main cave; the tail jumps land on the
        # displaced kick-setup / possession routines
        calls = []
        i = 0
        while i < len(aux) - 5:
            if aux[i] in (0xE8, 0xE9):
                rel = struct.unpack_from("<i", aux, i + 1)[0]
                target = ot.AUX_CAVE_VA + i + 5 + rel
                if target in (labels["flag_team"], ot.FN_KICK_SETUP, ot.FN_SET_POSSESSION):
                    calls.append((aux[i], target))
            i += 1
        self.assertIn((0xE8, labels["flag_team"]), calls)
        self.assertIn((0xE9, ot.FN_KICK_SETUP), calls)
        self.assertIn((0xE9, ot.FN_SET_POSSESSION), calls)
        self.assertGreaterEqual(sum(1 for op, t in calls if op == 0xE9 and t == ot.FN_KICK_SETUP), 2)
        # the two kickoff stubs mark the receiver PENDING (dl = 4), never possessed (dl = 1)
        for name in ("ot_kickoff", "kickoff_flag"):
            off = labels[name] - ot.AUX_CAVE_VA
            body = aux[off: off + 0x60]
            self.assertIn(bytes([0xB2, ot.FLAG_PENDING]) + b"\xe8", body, f"{name} passes the pending mask")
            self.assertNotIn(bytes([0xB2, ot.FLAG_POSSESSED]) + b"\xe8", body, name)
        situation = labels["situation"] - ot.AUX_CAVE_VA
        self.assertEqual(aux[situation: situation + 7], bytes.fromhex("c605") + struct.pack("<I", ot.STATE_GLOBAL) + b"\x00",
                         "the situation seed clears the possession flags")
        self.assertEqual(aux[situation + 7], 0xE9)

    def test_main_cave_entry_points_have_the_expected_shape(self) -> None:
        labels = ot.cave_labels()
        main = ot.main_cave_bytes()
        init = labels["init"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[init: init + 6], ot.RETAIL_INIT, "init replays the displaced fstp")
        self.assertEqual(main[init + 6: init + 16], bytes.fromhex("c705") + struct.pack("<I", ot.STATE_GLOBAL) + b"\0\0\0\0")
        self.assertEqual(main[init + 16], 0xC3)
        check = labels["ot_check"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[check: check + 8], b"\xa1" + struct.pack("<I", ot.PERIOD_GLOBAL) + bytes.fromhex("83f805"))
        # bookkeeping is skipped while a kickoff is pending (phase 2): the receiver's opportunity is still ahead
        self.assertEqual(main[check + 10: check + 17], bytes.fromhex("833d") + struct.pack("<I", ot.PHASE_GLOBAL) + b"\x02")
        self.assertEqual(main[check + 17], 0x74)
        self.assertEqual(labels["ot_check"] + 19 + main[check + 18], labels["scores"])
        # then the pending bits (2/3) are promoted into the possession bits (0/1) before the possessor is flagged
        promote = main[check + 19: check + 38]
        self.assertEqual(promote, b"\xa0" + struct.pack("<I", ot.STATE_FLAGS) + bytes.fromhex("8ac8c0e9020ac12403")
                         + b"\xa2" + struct.pack("<I", ot.STATE_FLAGS))
        self.assertEqual(main[check + 48: check + 50], bytes([0xB2, ot.FLAG_POSSESSED]), "the possessor gets the possessed mask")
        flag = labels["flag_team"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[flag + 12: flag + 18], bytes.fromhex("0815") + struct.pack("<I", ot.STATE_FLAGS), "or [flags], dl")
        self.assertEqual(main[flag + 19: flag + 27], bytes.fromhex("00d20815") + struct.pack("<I", ot.STATE_FLAGS), "away: dl doubled")
        not_over = labels["not_over"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[not_over: not_over + 9], b"\xa1" + struct.pack("<I", ot.PERIOD_GLOBAL) + bytes.fromhex("83fc00c3"))
        over = labels["over"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[over: over + 8], b"\xa1" + struct.pack("<I", ot.PERIOD_GLOBAL) + bytes.fromhex("39c0c3"))
        expiry = labels["ot_expiry"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[expiry: expiry + 3], bytes.fromhex("505152"), "expiry preserves eax/ecx/edx")
        tied = labels["exp_tied"] - ot.MAIN_CAVE_VA
        self.assertEqual(main[tied: tied + 6], bytes.fromhex("5a595839c0c3"))
        aux = ot.aux_cave_bytes()
        period = labels["sim_period"] - ot.AUX_CAVE_VA
        self.assertEqual(aux[period], 0x9C, "sim_period saves the flags of the compare it interrupts (pushfd)")
        self.assertEqual(aux[period + 1: period + 11], ot.RETAIL_SIM_PERIOD, "and replays the displaced 1.0 store")
        done = labels["sp_done"] - ot.AUX_CAVE_VA
        self.assertEqual(aux[done: done + 2], bytes.fromhex("9dc3"), "popfd; ret")
        for name in ("sim_reset", "sim_roll", "sim_tie"):
            off = labels[name] - ot.AUX_CAVE_VA
            self.assertNotEqual(aux[off], 0x9C, f"{name} has no flag consumer after it and stays cheap")


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_status_apply_round_trip(self) -> None:
        self.assertEqual(ot.status(self.payload), "retail")
        patched, receipt = ot.apply(self.payload)
        self.assertEqual(ot.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        settings = ot.read_settings(patched)
        self.assertEqual(settings, {"status": "applied", "regular_minutes": 10.0, "both_possessions": True,
                                    "postseason_no_ties": True, "sim_engine": True})
        with self.assertRaises(ot.OvertimeError):
            ot.apply(patched)

    def test_only_the_sites_and_the_text_digest_change(self) -> None:
        patched, receipt = ot.apply(self.payload)
        labels = ot.cave_labels()
        expected = {
            _text_off(ot.MAIN_CAVE_VA): ot.main_cave_bytes(10),
            _text_off(ot.AUX_CAVE_VA): ot.aux_cave_bytes(),
            _text_off(ot.INIT_SITE_VA): ot._rel32_call(ot.INIT_SITE_VA, labels["init"]) + b"\x90",
            _text_off(ot.OT_KICKOFF_SITE_VA): ot._rel32_call(ot.OT_KICKOFF_SITE_VA, labels["ot_kickoff"]),
            _text_off(ot.KICKOFF_SITE_VA): ot._rel32_call(ot.KICKOFF_SITE_VA, labels["kickoff_flag"]),
            _text_off(ot.SITUATION_SITE_VA): ot._rel32_call(ot.SITUATION_SITE_VA, labels["situation"]),
            _text_off(ot.SIM_RESET_SITE_VA): ot._rel32_call(ot.SIM_RESET_SITE_VA, labels["sim_reset"]) + b"\x90",
            _text_off(ot.SIM_ROLL_SITE_VA): ot._rel32_call(ot.SIM_ROLL_SITE_VA, labels["sim_roll"]) + b"\x90\x90",
            _text_off(ot.SIM_PERIOD_SITE_VA): ot._rel32_call(ot.SIM_PERIOD_SITE_VA, labels["sim_period"]) + b"\x90" * 5,
        }
        # the three multi-instruction sites: call + conditional jump to the retail targets + nops
        pred = patched[_text_off(ot.PRED_SITE_VA): _text_off(ot.PRED_SITE_VA) + len(ot.RETAIL_PRED)]
        self.assertEqual(pred[:5], ot._rel32_call(ot.PRED_SITE_VA, labels["ot_check"]))
        self.assertEqual(pred[5], 0x74)
        self.assertEqual(ot.PRED_SITE_VA + 7 + struct.unpack_from("<b", pred, 6)[0], ot.PRED_GAME_OVER_VA)
        self.assertEqual(pred[7:10], bytes.fromhex("83f804"))
        self.assertEqual(pred[10], 0x75)
        self.assertEqual(ot.PRED_SITE_VA + 12 + struct.unpack_from("<b", pred, 11)[0], ot.PRED_CONTINUE_VA)
        self.assertEqual(pred[12:], b"\x90" * (len(ot.RETAIL_PRED) - 12))
        for site, retail, target in ((ot.EXPIRY_SITE_VA, ot.RETAIL_EXPIRY, ot.EXPIRY_DIFFER_VA),
                                     (ot.EXPIRY2_SITE_VA, ot.RETAIL_EXPIRY2, ot.EXPIRY2_DIFFER_VA)):
            got = patched[_text_off(site): _text_off(site) + len(retail)]
            self.assertEqual(got[:5], ot._rel32_call(site, labels["ot_expiry"]))
            self.assertEqual(got[5], 0x75)
            self.assertEqual(site + 7 + struct.unpack_from("<b", got, 6)[0], target)
            self.assertEqual(got[7:], b"\x90" * (len(retail) - 7))
            expected[_text_off(site)] = got
        tie = patched[_text_off(ot.SIM_TIE_SITE_VA): _text_off(ot.SIM_TIE_SITE_VA) + len(ot.RETAIL_SIM_TIE)]
        self.assertEqual(tie[:5], ot._rel32_call(ot.SIM_TIE_SITE_VA, labels["sim_tie"]))
        self.assertEqual(tie[5], 0x75)
        self.assertEqual(ot.SIM_TIE_SITE_VA + 7 + struct.unpack_from("<b", tie, 6)[0], ot.SIM_TIE_CONTINUE_VA)
        self.assertEqual(tie[7:], b"\x90\x90")
        expected[_text_off(ot.PRED_SITE_VA)] = pred
        expected[_text_off(ot.SIM_TIE_SITE_VA)] = tie
        allowed = set()
        for off, blob in expected.items():
            self.assertEqual(patched[off: off + len(blob)], blob, hex(off))
            allowed.update(range(off, off + len(blob)))
        allowed.update(range(TABLE_OFF + 36, TABLE_OFF + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= allowed, sorted(hex(i) for i in changed - allowed)[:10])
        self.assertEqual(patched[TABLE_OFF + 36: TABLE_OFF + 56], _section_digest(patched, TEXT_RAW, TEXT_SIZE))
        self.assertEqual(receipt["changed_bytes"], len(changed))

    def test_hook_lengths_match_the_displaced_retail_bytes(self) -> None:
        for _g, label, off, before, after in ot._sites(self.payload, 10, True, True, True):
            self.assertEqual(len(before), len(after), label)

    def test_optional_groups_can_stay_retail(self) -> None:
        patched, receipt = ot.apply(self.payload, 10, both_possessions=False, postseason_no_ties=False, sim_engine=False)
        self.assertEqual(ot.status(patched), "applied")
        settings = ot.read_settings(patched)
        self.assertEqual(settings["both_possessions"], False)
        self.assertEqual(settings["postseason_no_ties"], False)
        self.assertEqual(settings["sim_engine"], False)
        for va, retail in ((ot.PRED_SITE_VA, ot.RETAIL_PRED), (ot.KICKOFF_SITE_VA, ot.RETAIL_KICKOFF),
                           (ot.EXPIRY_SITE_VA, ot.RETAIL_EXPIRY), (ot.EXPIRY2_SITE_VA, ot.RETAIL_EXPIRY2),
                           (ot.SIM_RESET_SITE_VA, ot.RETAIL_SIM_RESET), (ot.SIM_ROLL_SITE_VA, ot.RETAIL_SIM_ROLL),
                           (ot.SIM_TIE_SITE_VA, ot.RETAIL_SIM_TIE), (ot.SIM_PERIOD_SITE_VA, ot.RETAIL_SIM_PERIOD)):
            self.assertEqual(patched[_text_off(va): _text_off(va) + len(retail)], retail, hex(va))
        labels = {e["label"] for e in receipt["edits"]}
        self.assertEqual(labels, {"main_cave", "aux_cave", "init_hook", "ot_kickoff_hook", "situation_hook"})

    def test_other_minutes_change_only_the_scale_float(self) -> None:
        default, _ = ot.apply(self.payload, 10)
        other, _ = ot.apply(self.payload, 12)
        diff = {i for i, (a, b) in enumerate(zip(default, other)) if a != b}
        scale = set(range(_text_off(ot.SCALE_VA), _text_off(ot.SCALE_VA) + 4))
        digest = set(range(TABLE_OFF + 36, TABLE_OFF + 56))
        self.assertTrue(diff <= scale | digest)
        self.assertEqual(ot.read_settings(other)["regular_minutes"], 12.0)
        retail_length, _ = ot.apply(self.payload, 15)
        self.assertEqual(struct.unpack_from("<f", retail_length, _text_off(ot.SCALE_VA))[0], 1.0)

    def test_foreign_bytes_are_refused(self) -> None:
        for va, _retail in _retail_sites():
            broken = bytearray(self.payload)
            broken[_text_off(va)] ^= 0xFF
            self.assertEqual(ot.status(bytes(broken)), "foreign", hex(va))
            with self.assertRaises(ot.OvertimeError):
                ot.apply(bytes(broken))
        self.assertEqual(ot.status(b"\x00" * 0x1000), "foreign")

    def test_half_applied_group_is_foreign(self) -> None:
        patched, _ = ot.apply(self.payload)
        broken = bytearray(patched)
        off = _text_off(ot.KICKOFF_SITE_VA)
        broken[off: off + len(ot.RETAIL_KICKOFF)] = ot.RETAIL_KICKOFF
        self.assertEqual(ot.status(bytes(broken)), "foreign")

    def test_settings_are_validated(self) -> None:
        for bad in (0, 20, -1):
            with self.assertRaises(ot.OvertimeError):
                ot.apply(self.payload, bad)


@unittest.skipUnless(RETAIL_XBE.exists(), "private retail default.xbe not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_image_is_recognised_and_patches_cleanly(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(ot.status(payload), "retail")
        patched, receipt = ot.apply(payload)
        self.assertEqual(ot.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        self.assertLess(receipt["changed_bytes"], 700)
        self.assertEqual(ot.read_settings(patched)["regular_minutes"], 10.0)
        # the state dword lives in .data's BSS tail: mapped at runtime, absent from the file
        sizes = {s.virtual_address: (s, struct.unpack_from("<I", payload, s.header_offset + 8)[0])
                 for s in strength._sections(payload)}
        data, vsize = next((s, v) for s, v in sizes.values() if s.virtual_address <= ot.STATE_GLOBAL < s.virtual_address + v)
        self.assertGreaterEqual(ot.STATE_GLOBAL - data.virtual_address, data.raw_size)
        self.assertLess(ot.STATE_GLOBAL + 4, data.virtual_address + vsize)


# --- unicorn: the real score / kickoff-build / post-play evaluator code of the patched image -------------------
SCRATCH = 0x00F00000
DESC, DRIVE, CTX, CLOCK, TSTATE, DIR, PARAMS = (SCRATCH, SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x3000,
                                                SCRATCH + 0x3100, SCRATCH + 0x3200, SCRATCH + 0x5000)
STACK_TOP, SENTINEL = SCRATCH + 0x1F000, 0x00DEAD00
HOME, AWAY = 0xE5FC20, 0xE5FC60                      # the two team objects (BSS)
HOME_SCORE, AWAY_SCORE = 0xB25E30, 0xB25E48          # the two score objects
FN_APPLY_DESCRIPTOR = 0x0022E4D0                     # FUN_0022e4d0: score dispatch + next-play build (kickoff hook inside)
FN_SCORE_DISPATCH, FN_TD, FN_SAFETY, FN_FG, FN_PAT = 0x0022E2D0, 0x000B8400, 0x000B84F0, 0x000B85C0, 0x000B8420
FN_TO_INT, FN_SITUATION, FN_SITUATION_TAIL = 0x000B4950, 0x0010BD80, 0x000E7C50
GAME_STATE, KICKOFF_TEAM = 0x00E602B8, 0x00E60288
KIND_TD, KIND_SAFETY, KIND_FG, KIND_PAT = 1, 2, 3, 4  # descriptor +0x74 as FUN_0022e2d0 switches on it


class _Game:
    """A patched retail image in unicorn with a mocked game state; every call outside the allow-list is
    skipped (eax := 0, stack arguments popped), the routines the caves tail-jump into return at once."""

    def __init__(self, patched: bytes) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc

        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x00010000, 0x00E61000 - 0x00010000)
        for section in strength._sections(patched):
            if section.virtual_address in (0x11000, 0x4E3AE0, 0xA69980):
                uc.mem_write(section.virtual_address, patched[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_map(SCRATCH, 0x20000)
        self.allow = {FN_SCORE_DISPATCH, ot.FN_SET_POSSESSION, FN_TO_INT, FN_TD, FN_SAFETY, FN_FG, FN_PAT}
        self.caves = (range(ot.MAIN_CAVE_VA, ot.MAIN_CAVE_VA + ot.MAIN_CAVE_SIZE),
                      range(ot.AUX_CAVE_VA, ot.AUX_CAVE_VA + ot.AUX_CAVE_SIZE))
        self.cache: dict[int, tuple[str, int, int | None]] = {}
        self.pops: dict[int, int] = {}
        self.calls: list[tuple[int, int | None]] = []
        self.stopped_at: int | None = None
        uc.hook_add(UC_HOOK_CODE, self._on_code)
        u32 = self._u32
        for team, other, score, state in ((HOME, AWAY, HOME_SCORE, TSTATE), (AWAY, HOME, AWAY_SCORE, TSTATE + 0x40)):
            uc.mem_write(team, u32(other))                  # [team+0] = opponent
            uc.mem_write(team + 8, u32(score))              # [team+8] = score object
            uc.mem_write(team + 0xC, u32(state))
            uc.mem_write(score, b"\0" * 0x20)
            uc.mem_write(score + 0xC, u32(DIR))             # direction object read by the score handlers
        uc.mem_write(DIR + 4, struct.pack("<f", 1.0))
        uc.mem_write(ot.HOME_SCORE_PTR, u32(HOME_SCORE))
        uc.mem_write(ot.AWAY_SCORE_PTR, u32(AWAY_SCORE))
        uc.mem_write(0x00E602EC, u32(CTX))
        uc.mem_write(ot.CLOCK_OBJECT_GLOBAL, u32(CLOCK))
        uc.mem_write(0x00E60268, u32(0))
        uc.mem_write(0x00B616C0, u32(0))
        uc.mem_write(KICKOFF_TEAM, u32(HOME))
        self.set(period=5, home=0, away=0, phase=2, flags=0, mode=4)

    @staticmethod
    def _u32(value: int) -> bytes:
        return struct.pack("<I", value & 0xFFFFFFFF)

    def w(self, va: int, value: int) -> None:
        self.uc.mem_write(va, self._u32(value))

    def r(self, va: int) -> int:
        return struct.unpack("<I", bytes(self.uc.mem_read(va, 4)))[0]

    def set(self, *, period=None, home=None, away=None, poss=None, phase=None, flags=None, mode=None) -> None:
        if period is not None:
            self.w(ot.PERIOD_GLOBAL, period)
        if home is not None:
            self.w(HOME_SCORE, home)
        if away is not None:
            self.w(AWAY_SCORE, away)
        if poss is not None:
            self.w(ot.POSSESSION_GLOBAL, poss)
            self.w(ot.DEFENSE_GLOBAL, AWAY if poss == HOME else HOME)
        if phase is not None:
            self.w(ot.PHASE_GLOBAL, phase)
        if flags is not None:
            self.w(ot.STATE_GLOBAL, flags)
        if mode is not None:
            self.w(ot.MODE_GLOBAL, mode)

    @property
    def flags(self) -> int:
        return self.r(ot.STATE_GLOBAL) & 0xFF

    @property
    def scores(self) -> tuple[int, int]:
        return self.r(HOME_SCORE), self.r(AWAY_SCORE)

    @property
    def poss(self) -> int:
        return self.r(ot.POSSESSION_GLOBAL)

    @property
    def phase(self) -> int:
        return self.r(ot.PHASE_GLOBAL)

    # ---- tracer
    def _decode(self, address: int):
        if address not in self.cache:
            ins = next(self.md.disasm(bytes(self.uc.mem_read(address, 16)), address, count=1))
            target = int(ins.op_str, 16) if ins.mnemonic == "call" and ins.op_str.startswith("0x") else None
            self.cache[address] = (ins.mnemonic, ins.size, target)
        return self.cache[address]

    def _pop(self, target: int) -> int:
        if target not in self.pops:
            self.pops[target] = 0
            for ins in self.md.disasm(bytes(self.uc.mem_read(target, 0x1000)), target):
                if ins.mnemonic == "ret":
                    self.pops[target] = int(ins.op_str, 16) if ins.op_str else 0
                    break
        return self.pops[target]

    def _on_code(self, uc, address, size, _user) -> None:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

        if address in (ot.PRED_GAME_OVER_VA, ot.PRED_CONTINUE_VA):
            self.stopped_at = address
            uc.emu_stop()
            return
        if address in (ot.FN_KICK_SETUP, FN_SITUATION_TAIL):   # reached by tail jumps: return to the caller at once
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, self.r(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
            return
        mnemonic, insn_size, target = self._decode(address)
        if mnemonic != "call":
            return
        self.calls.append((address, target))
        if target is None or not (target in self.allow or any(target in cave for cave in self.caves)):
            uc.reg_write(UC_X86_REG_EAX, 0)
            uc.reg_write(UC_X86_REG_ESP, uc.reg_read(UC_X86_REG_ESP) + (self._pop(target) if target else 0))
            uc.reg_write(UC_X86_REG_EIP, address + insn_size)

    def run(self, start: int, **regs) -> None:
        from unicorn import x86_const

        uc = self.uc
        uc.mem_write(STACK_TOP - 4, self._u32(SENTINEL))
        uc.reg_write(x86_const.UC_X86_REG_ESP, STACK_TOP - 4)
        for name, value in regs.items():
            uc.reg_write(getattr(x86_const, f"UC_X86_REG_{name.upper()}"), value)
        self.stopped_at = None
        uc.emu_start(start, SENTINEL, count=200_000)

    # ---- game actions
    def ot_kickoff(self, kicker: int) -> None:
        """FUN_001587f0's hooked call with the kicking team in possession: runs the ot_kickoff cave."""
        self.set(poss=kicker)
        self.run(ot.cave_labels()["ot_kickoff"], ecx=CTX + 0x40)

    def kick_fielded(self, receiver: int) -> None:
        """The kick dead-ball evaluator's swap plus the next scrimmage descriptor: receiver in possession, phase 4."""
        self.set(poss=receiver, phase=4)

    def score(self, kind: int, team: int, next_phase: int) -> None:
        """Apply a scoring descriptor through the real FUN_0022e4d0: the score dispatch (FUN_0022e2d0 -> the
        TD / safety / FG / PAT handler, FUN_000e9460 for the kicking team) and the next-play build whose
        kickoff branch holds the hooked FUN_000e9380 call.  `team` scores; a safety's descriptor names the
        conceding team as the next possessor (it kicks)."""
        uc = self.uc
        uc.mem_write(DESC, b"\0" * 0x100)
        uc.mem_write(DRIVE, b"\0" * 0x80)
        self.w(DESC, next_phase)
        self.w(DESC + 0x14, self.poss if kind != KIND_SAFETY else self.r(team))
        self.w(DESC + 0x74, kind)
        self.w(DESC + 0x78, DRIVE)
        self.w(DESC + 0x7C, team)
        self.w(DRIVE + 0x38, team)
        self.run(FN_APPLY_DESCRIPTOR, ecx=DESC, edx=1)

    def evaluate(self) -> str:
        """The post-play evaluator's overtime block (game state 0xb at entry, esi = 3 as in retail)."""
        from unicorn.x86_const import UC_X86_REG_EIP

        self.w(GAME_STATE, 0xB)
        self.run(ot.PRED_SITE_VA, esi=3)
        assert self.stopped_at in (ot.PRED_GAME_OVER_VA, ot.PRED_CONTINUE_VA), hex(self.uc.reg_read(UC_X86_REG_EIP))
        return "over" if self.stopped_at == ot.PRED_GAME_OVER_VA else "continue"

    def situation(self, period_index: int, flags_before: int) -> None:
        """The Situation screen's game seed FUN_0010bd80 (params: +0x18 = period index, 4 -> OT1)."""
        self.set(flags=flags_before)
        self.uc.mem_write(PARAMS, b"\0" * 0x60)
        self.w(PARAMS + 0x18, period_index)
        self.run(FN_SITUATION, ecx=PARAMS, edx=0)


@unittest.skipUnless(RETAIL_XBE.exists() and HAVE_UNICORN and HAVE_CAPSTONE, "retail default.xbe, unicorn and capstone needed")
class UnicornScenarioTests(unittest.TestCase):
    """Noah's 2026-09-04 scenario (Situation, OT1 tied 0-0, field goal -> the game ended) and the rulebook
    cases, replayed through the real code: the overtime kickoff cave, FUN_0022e4d0 with each scoring
    descriptor (score applied, kicking team set, kickoff built through the hooked call) and then the hooked
    sudden-death block of FUN_000a11f0 - in that order, which is the order the game runs them in
    (FUN_000b95f0 applies the descriptor and sets state 0xb; the evaluator switches on that 0xb)."""

    HOME_POSSESSED, AWAY_POSSESSED, HOME_PENDING, AWAY_PENDING = 1, 2, 4, 8

    @classmethod
    def setUpClass(cls) -> None:
        cls.patched, _receipt = ot.apply(RETAIL_XBE.read_bytes())

    def _overtime(self, kicker=HOME):
        """OT1 0-0, `kicker` kicks off, the other team fields it and has run one scrimmage play."""
        g = _Game(self.patched)
        receiver = AWAY if kicker == HOME else HOME
        g.ot_kickoff(kicker)
        g.kick_fielded(receiver)
        self.assertEqual(g.evaluate(), "continue")
        self.assertEqual(g.evaluate(), "continue")
        return g

    def test_ot_kickoff_marks_the_receiver_pending_only(self) -> None:
        g = _Game(self.patched)
        g.set(flags=0x0F)
        g.ot_kickoff(HOME)
        self.assertEqual(g.flags, self.AWAY_PENDING, "flags cleared, the receiver pending, nobody has possessed")
        self.assertEqual(g.poss, HOME)
        g.kick_fielded(AWAY)
        self.assertEqual(g.evaluate(), "continue")
        self.assertEqual(g.flags, self.AWAY_POSSESSED, "the kickoff was played: the receiver has possessed")

    def test_first_possession_field_goal_plays_on_and_the_other_team_receives(self) -> None:
        g = self._overtime(kicker=HOME)                    # AWAY received
        g.score(KIND_FG, AWAY, next_phase=2)
        self.assertEqual(g.scores, (0, 3))
        self.assertEqual(g.phase, 2, "a kickoff is pending")
        self.assertEqual(g.poss, AWAY, "the scoring team kicks off")
        self.assertEqual(g.flags, self.AWAY_POSSESSED | self.HOME_PENDING, "HOME's opportunity is pending, not possessed")
        self.assertEqual(g.evaluate(), "continue", "the 2026-09-04 bug: retail's 'first score wins' must not fire")
        self.assertEqual(g.flags, self.AWAY_POSSESSED | self.HOME_PENDING)
        g.kick_fielded(HOME)
        self.assertEqual(g.evaluate(), "continue", "HOME trails on its first possession")
        self.assertEqual(g.flags, self.HOME_POSSESSED | self.AWAY_POSSESSED)

    def test_answering_field_goal_ties_then_sudden_death(self) -> None:
        g = self._overtime(kicker=HOME)
        g.score(KIND_FG, AWAY, next_phase=2)
        self.assertEqual(g.evaluate(), "continue")
        g.kick_fielded(HOME)
        self.assertEqual(g.evaluate(), "continue")
        g.score(KIND_FG, HOME, next_phase=2)
        self.assertEqual(g.scores, (3, 3))
        self.assertEqual(g.evaluate(), "continue", "tied after both possessions: play on")
        g.kick_fielded(AWAY)
        self.assertEqual(g.evaluate(), "continue")
        g.score(KIND_FG, AWAY, next_phase=2)
        self.assertEqual(g.scores, (3, 6))
        self.assertEqual(g.evaluate(), "over", "sudden death: the next score wins")

    def test_first_possession_field_goal_then_a_stop_ends_the_game(self) -> None:
        g = self._overtime(kicker=HOME)
        g.score(KIND_FG, AWAY, next_phase=2)
        self.assertEqual(g.evaluate(), "continue")
        g.kick_fielded(HOME)
        self.assertEqual(g.evaluate(), "continue")
        g.set(poss=AWAY, phase=4)                          # HOME punts / turns it over
        self.assertEqual(g.evaluate(), "over", "the leader has the ball and its opponent has possessed")

    def test_first_possession_touchdown_and_pat_play_on(self) -> None:
        g = self._overtime(kicker=HOME)
        g.score(KIND_TD, AWAY, next_phase=3)
        self.assertEqual(g.scores, (0, 6))
        self.assertEqual(g.phase, 3)
        self.assertEqual(g.evaluate(), "continue", "a first-possession touchdown does not end the game (2025 rule)")
        g.score(KIND_PAT, AWAY, next_phase=2)
        self.assertEqual(g.scores, (0, 7))
        self.assertEqual(g.flags, self.AWAY_POSSESSED | self.HOME_PENDING)
        self.assertEqual(g.evaluate(), "continue", "kickoff to HOME")
        g.kick_fielded(HOME)
        self.assertEqual(g.evaluate(), "continue")
        g.score(KIND_TD, HOME, next_phase=3)
        self.assertEqual(g.evaluate(), "continue", "6-7: HOME still trails, the PAT is played")
        g.score(KIND_PAT, HOME, next_phase=2)
        self.assertEqual(g.scores, (7, 7))
        self.assertEqual(g.evaluate(), "continue", "tied after both possessions")

    def test_answering_touchdown_that_takes_the_lead_ends_the_game_before_the_pat(self) -> None:
        g = self._overtime(kicker=HOME)
        g.score(KIND_FG, AWAY, next_phase=2)
        self.assertEqual(g.evaluate(), "continue")
        g.kick_fielded(HOME)
        g.score(KIND_TD, HOME, next_phase=3)
        self.assertEqual(g.scores, (6, 3))
        self.assertEqual(g.evaluate(), "over", "HOME leads after both possessions")

    def test_first_possession_safety_ends_the_game(self) -> None:
        g = self._overtime(kicker=HOME)                    # AWAY is driving
        g.score(KIND_SAFETY, HOME, next_phase=1)
        self.assertEqual(g.scores, (2, 0))
        self.assertEqual(g.phase, 1)
        self.assertEqual(g.evaluate(), "over", "Art. 3(a): a safety on the first possession wins it")

    def test_onside_recovery_counts_as_the_receivers_opportunity(self) -> None:
        g = self._overtime(kicker=HOME)
        g.score(KIND_FG, AWAY, next_phase=2)
        self.assertEqual(g.evaluate(), "continue")
        g.set(poss=AWAY, phase=4)                          # AWAY recovers its own kickoff
        self.assertEqual(g.evaluate(), "over", "Art. 5(c): the receiving team has had its opportunity")
        self.assertEqual(g.flags, self.HOME_POSSESSED | self.AWAY_POSSESSED)

    def test_situation_seed_clears_stale_flags(self) -> None:
        g = _Game(self.patched)
        g.situation(period_index=4, flags_before=0x0F)
        self.assertEqual(g.r(ot.PERIOD_GLOBAL), 5, "period index 4 seeds OT1")
        self.assertEqual(g.flags, 0)
        self.assertEqual(g.poss, HOME, "FUN_000e9460 still ran: possession seeded")
        self.assertEqual(g.r(ot.DEFENSE_GLOBAL), AWAY)
        # Noah's exact game from that seed: AWAY kicks, HOME receives, HOME kicks a field goal
        g.set(poss=AWAY, phase=2)
        g.kick_fielded(HOME)
        self.assertEqual(g.evaluate(), "continue")
        g.score(KIND_FG, HOME, next_phase=2)
        self.assertEqual(g.scores, (3, 0))
        self.assertEqual(g.evaluate(), "continue", "play on: AWAY receives the kickoff")
        g.kick_fielded(AWAY)
        self.assertEqual(g.evaluate(), "continue")
        self.assertEqual(g.flags, self.HOME_POSSESSED | self.AWAY_POSSESSED)

    def test_regulation_keeps_the_retail_path(self) -> None:
        g = _Game(self.patched)
        g.set(period=4, home=7, away=0, poss=HOME, phase=4, flags=0)
        g.uc.mem_write(CLOCK + 0x10, struct.pack("<f", 1.0))
        self.assertEqual(g.evaluate(), "continue", "Q4 with time left: next play")
        self.assertEqual(g.flags, 0, "no overtime bookkeeping before period 5")


if __name__ == "__main__":
    unittest.main()
