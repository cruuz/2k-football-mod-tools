"""The Player Card TEAM column (revision 2): byte-exact, fail-closed, and executed under unicorn.

Revision 1 (beta 57 .. 76.5) read the club from ``player+0x30``, a field that is never populated, so no
franchise-played season ever got a team and the current-season row read ``--``.  Revision 2 finds the
club in the club records' player arrays (``club_of``) and records it in the post-game merge loop
(``FUN_00134dd0``), one dword per player-season.  These tests prove, with the game's own history
writer/reader and (where the private files exist) the real retail roster:

* the cause: ``player+0x30`` is 0 for every roster record, also after the game's own relocation;
* the caves: shapes, decode, budget, intra-cave call, no absolute stores;
* synthetic images: status / apply / revision-1 upgrade / idempotence / foreign refusal / order independence;
* unicorn worlds: the post-game hook for a play, a non-player, a non-club, a repeat, a trade, a release;
  ``club_of`` on every club position; the getter for every bank case; the rollover cave.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as draft  # noqa: E402
from mod_editor.core import nfl2k5_returner_fix as returner  # noqa: E402
from mod_editor.core import nfl2k5_team_column as tc  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
RETAIL_DIR = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_PACK0 = RETAIL_DIR / "vc_53450030" / "0"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None

# the synthesised game world for the emulator (a VA range the image never uses)
SCRATCH = 0x00F00000
ROSTER, TEAMS, ABBRS, PLAYERS, POOL = SCRATCH, SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x3000, SCRATCH + 0x4000
STACK_TOP, RET_SENTINEL = SCRATCH + 0x1F000, SCRATCH + 0x1F800
TEAM_COUNT = 40            # clubs 0..33 are searched; indices 34.. exist so the bound is observable
PLAYER_SIZE = 0x54
PLAYER_COUNT = 12
STAGE_GLOBAL = 0x00E576A4


def _section_digests_consistent(payload: bytes) -> bool:
    for section in strength._sections(payload):
        if section.raw_size == 0 or section.raw_offset + section.raw_size > len(payload):
            continue        # the shared synthetic fixture seeds the arc-table slot over header 5 (a bogus section)
        d = section.header_offset + 36
        if payload[d: d + 20] != strength.section_digest(payload, section):
            return False
    return True


def _legacy_cave() -> bytes:
    """The revision-1 cave, rebuilt from its documented instruction stream (pinned by LEGACY_CAVE_SHA256)."""

    from mod_editor.core.nfl2k5_draft_ai import _Asm

    def imm(v: int) -> str:
        return struct.pack("<I", v).hex()

    roster, klass, player_g = tc.ROSTER_GLOBAL, 0x00BD7F98, tc.PLAYER_GLOBAL
    a = _Asm(tc.CAVE_VA)
    a.label("rollover")
    a.b("8b4630"); a.b("85c0"); a.j8("74", "done"); a.b("8b15" + imm(roster)); a.b("2b421c"); a.j8("78", "done")
    a.b("b9" + imm(tc.TEAM_STRIDE)); a.b("52"); a.b("31d2"); a.b("f7f1"); a.b("59"); a.b("85d2"); a.j8("75", "done")
    a.b("3b4118"); a.j8("73", "done"); a.b("40"); a.b("50"); a.b("a1" + imm(klass)); a.b("50")
    a.b("c705" + imm(klass) + "00000000"); a.b("8b4624"); a.b("c1e808"); a.b("83e01f"); a.b("50"); a.b("31d2")
    a.b("8bce"); a.call(tc.FN_FIND_ENTRY); a.b("85c0"); a.j8("74", "restore"); a.b("8b442404"); a.b("50")
    a.b("ba" + imm(tc.TEAM_FIELD)); a.b("8bce"); a.call(tc.FN_SET_CURRENT)
    a.label("restore"); a.b("58"); a.b("a3" + imm(klass)); a.b("58")
    a.label("done"); a.b(tc.RETAIL_HOOK.hex()); a.b("c3")
    a.label("getter")
    a.b("83f909"); a.j8("75", "rows"); a.b("b8" + imm(tc.STR_EMPTY_VA)); a.b("c3")
    a.label("rows")
    a.b("8b15" + imm(player_g)); a.b("85d2"); a.j8("74", "dash"); a.b("83f90b"); a.j8("75", "past")
    a.b("8b4230"); a.b("85c0"); a.j8("74", "dash"); a.b("8b80" + imm(tc.TEAM_ABBR_OFF)); a.b("85c0"); a.j8("74", "dash")
    a.b("c3")
    a.label("past")
    a.b("8b4224"); a.b("c1e808"); a.b("83e01f"); a.b("2bc1"); a.b("83c00b"); a.j8("78", "dash"); a.b("50")
    a.b("8bca"); a.b("ba" + imm(tc.TEAM_FIELD)); a.call(tc.FN_FIND_ENTRY); a.b("85c0"); a.j8("74", "dash")
    a.b("8b00"); a.b("a900000040"); a.j8("75", "dash"); a.b("0fb7c0"); a.b("48"); a.j8("78", "dash")
    a.b("8b0d" + imm(roster)); a.b("3b4118"); a.j8("73", "dash"); a.b("69c0" + imm(tc.TEAM_STRIDE)); a.b("03411c")
    a.b("8b80" + imm(tc.TEAM_ABBR_OFF)); a.b("85c0"); a.j8("75", "ret")
    a.label("dash"); a.b("b8" + imm(tc.STR_DASH_VA)); a.label("ret"); a.b("c3")
    code = a.assemble()
    assert len(code) == 257, len(code)
    getter_va = tc.CAVE_VA + a.labels["getter"]
    body = code + b"\xcc" * (tc.CODE_LIMIT - len(code))
    strings = bytearray(tc.DESCRIPTOR_VA - tc.STR_EMPTY_VA)
    strings[4:10] = "--".encode("utf-16-le") + b"\x00\x00"
    d = bytearray(tc.RETAIL_YR_DESCRIPTOR)
    struct.pack_into("<I", d, 0x00, 8)
    struct.pack_into("<I", d, 0x08, getter_va)
    struct.pack_into("<I", d, 0x64, 1)
    struct.pack_into("<I", d, 0x70, tc.STR_TEAM_VA)
    struct.pack_into("<I", d, 0x88, tc.STR_TEAM_NAME_VA)
    struct.pack_into("<I", d, 0xA0, 0)
    return body + bytes(strings) + bytes(d)


class TranscriptAndShapeTests(unittest.TestCase):
    def test_legacy_cave_rebuild_matches_its_pin(self) -> None:
        legacy = _legacy_cave()
        self.assertEqual(len(legacy), tc.CAVE_SIZE)
        self.assertEqual(hashlib.sha256(legacy).hexdigest(), tc.LEGACY_CAVE_SHA256)
        self.assertNotEqual(legacy, tc.cave_bytes())

    def test_hook_shapes(self) -> None:
        self.assertEqual(len(tc.RETAIL_HOOK), 25)
        self.assertEqual(len(tc.PATCHED_HOOK), 25)
        self.assertEqual(tc.PATCHED_HOOK[0], 0xE8)
        rel = struct.unpack_from("<i", tc.PATCHED_HOOK, 1)[0]
        self.assertEqual(tc.HOOK_VA + 5 + rel, tc.CAVE_VA)
        self.assertEqual(tc.PATCHED_HOOK[5:], b"\x90" * 20)
        self.assertEqual(tc.HOOK_VA + 25, tc.HOOK_RESUME_VA)
        # the post-game hook: `mov ecx,ebx ; call 0x61b90` -> `jmp post ; nop ; nop`
        self.assertEqual(tc.RETAIL_POST_HOOK, bytes.fromhex("8bcbe87fcdf2ff"))
        self.assertEqual(len(tc.PATCHED_POST_HOOK), 7)
        self.assertEqual(tc.PATCHED_POST_HOOK[0], 0xE9)
        rel = struct.unpack_from("<i", tc.PATCHED_POST_HOOK, 1)[0]
        self.assertEqual(tc.POST_HOOK_VA + 5 + rel, tc.POST_VA)
        self.assertEqual(tc.PATCHED_POST_HOOK[5:], b"\x90\x90")
        self.assertEqual(tc.POST_HOOK_VA + 7, tc.POST_RESUME_VA)

    def test_cave_layout_and_budget(self) -> None:
        self.assertEqual(len(tc.RETAIL_CAVE), tc.CAVE_SIZE)
        cave = tc.cave_bytes()
        self.assertEqual(len(cave), tc.CAVE_SIZE)
        code, labels = tc._build()
        self.assertLessEqual(len(code), tc.CODE_LIMIT)
        self.assertEqual(cave[: len(code)], code)
        # the rollover cave is the displaced retail increment and a ret, at the entry the hook calls
        self.assertEqual(labels["rollover"], 0)
        self.assertEqual(code[: len(tc.RETAIL_HOOK) + 1], tc.RETAIL_HOOK + b"\xc3")
        self.assertEqual(labels["post"], len(tc.RETAIL_HOOK) + 1)
        self.assertEqual(tc.POST_VA, tc.CAVE_VA + labels["post"])
        self.assertLess(labels["post"], labels["club_of"])
        self.assertLess(labels["club_of"], labels["getter"])
        self.assertEqual(tc.GETTER_VA, tc.CAVE_VA + labels["getter"])
        self.assertEqual(tc.CLUB_OF_VA, tc.CAVE_VA + labels["club_of"])
        # strings and descriptor at their fixed offsets
        self.assertEqual(cave[tc.STR_EMPTY_VA - tc.CAVE_VA: tc.STR_EMPTY_VA - tc.CAVE_VA + 2], b"\x00\x00")
        self.assertEqual(cave[tc.STR_DASH_VA - tc.CAVE_VA: tc.STR_DASH_VA - tc.CAVE_VA + 6], "--".encode("utf-16-le") + b"\0\0")
        self.assertEqual(cave[tc.DESCRIPTOR_VA - tc.CAVE_VA:], tc.descriptor_bytes())
        self.assertEqual(tc.DESCRIPTOR_VA % 16, 0)

    def test_descriptor_is_the_yr_clone_with_the_team_getter(self) -> None:
        d = tc.descriptor_bytes()
        self.assertEqual(len(d), 0xB0)
        self.assertEqual(struct.unpack_from("<IIII", d, 0), (8, 3, tc.GETTER_VA, 0x1000A))
        self.assertEqual(struct.unpack_from("<I", d, 0x64)[0], 1)                       # frozen next to Yr
        self.assertEqual(struct.unpack_from("<III", d, 0x68), (0x27CCD0, 0x10000, tc.STR_TEAM_VA))
        self.assertEqual(struct.unpack_from("<III", d, 0x80), (0x27CCD0, 0x10000, tc.STR_TEAM_NAME_VA))
        self.assertEqual(struct.unpack_from("<III", d, 0x98), (0x27CCD0, 0x10000, 0))
        self.assertEqual(d[0x10:0x64], bytes(0x54))
        # only the getter, the two strings and nothing else differ from Yr
        diff = [i for i in range(0xB0) if d[i] != tc.RETAIL_YR_DESCRIPTOR[i]]
        self.assertTrue(all(0x08 <= i < 0x0C or 0x70 <= i < 0x74 or 0x88 <= i < 0x8C for i in diff), diff)

    def test_list_insertions_keep_every_pointer_in_order_and_the_terminators(self) -> None:
        for label, _va, pointers in tc.COLUMN_LISTS:
            retail = struct.unpack(f"<{tc.LIST_SLOTS}I", tc.list_words(pointers, False))
            patched = struct.unpack(f"<{tc.LIST_SLOTS}I", tc.list_words(pointers, True))
            self.assertEqual(retail[: len(pointers)], pointers, label)
            self.assertEqual(retail[len(pointers):], (0,) * (tc.LIST_SLOTS - len(pointers)), label)
            self.assertEqual(patched[0], tc.YR_DESCRIPTOR_VA, label)
            self.assertEqual(patched[1], tc.DESCRIPTOR_VA, label)
            self.assertEqual(patched[2: len(pointers) + 1], pointers[1:], label)
            self.assertEqual(patched[len(pointers) + 1:], (0,) * (tc.LIST_SLOTS - len(pointers) - 1), label)
            self.assertEqual(patched[tc.LIST_SLOTS - 1], 0, f"{label}: the word after the last slot stays a terminator")

    def test_cave_never_uses_the_shared_text_buffer(self) -> None:
        code, _labels = tc._build()
        self.assertNotIn(struct.pack("<I", 0x00C901C8), code)
        self.assertNotIn(struct.pack("<I", 0x00C901C8), tc.descriptor_bytes())

    def test_the_player_plus_0x30_field_is_not_used_any_more(self) -> None:
        """Revision 1 read [player+0x30] (always 0).  No instruction of the new caves may do that."""

        if not HAVE_CAPSTONE:
            self.skipTest("capstone not installed")
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, _labels = tc._build()
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, tc.CAVE_VA):
            self.assertNotRegex(ins.op_str, r"\+ 0x30\]", f"{ins.address:#x} {ins.mnemonic} {ins.op_str}")


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class CaveDecodeTests(unittest.TestCase):
    def test_every_instruction_decodes_and_branches_land_on_instructions(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, labels = tc._build()
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        starts, calls, jumps, total = set(), [], [], 0
        for ins in md.disasm(code, tc.CAVE_VA):
            starts.add(ins.address)
            total += ins.size
            if ins.mnemonic == "call":
                calls.append(int(ins.op_str, 16))
            elif ins.mnemonic.startswith("j") and ins.mnemonic != "jecxz":
                target = int(ins.op_str, 16)
                if ins.mnemonic == "jmp" and not tc.CAVE_VA <= target < tc.CAVE_VA + len(code):
                    jumps.append(target)
                else:
                    self.assertTrue(tc.CAVE_VA <= target < tc.CAVE_VA + len(code), f"branch out of the cave at {ins.address:#x}")
            elif ins.mnemonic == "jecxz":
                self.assertTrue(tc.CAVE_VA <= int(ins.op_str, 16) < tc.CAVE_VA + len(code))
        self.assertEqual(total, len(code), "the whole blob decodes")
        for ins in md.disasm(code, tc.CAVE_VA):
            if ins.mnemonic.startswith("j") and int(ins.op_str, 16) < tc.CAVE_VA + len(code) and int(ins.op_str, 16) >= tc.CAVE_VA:
                self.assertIn(int(ins.op_str, 16), starts, f"branch at {ins.address:#x} lands mid-instruction")
        self.assertEqual(sorted(set(calls)),
                         sorted({tc.FN_FIND_ENTRY, tc.FN_SET_CURRENT, tc.FN_NEXT_PLAYER, tc.CLUB_OF_VA}))
        self.assertEqual(calls.count(tc.FN_SET_CURRENT), 1)
        self.assertEqual(calls.count(tc.CLUB_OF_VA), 1)
        self.assertEqual(jumps, [tc.POST_RESUME_VA], "the only jump out of the cave resumes the post-game loop")
        for name in ("rollover", "post", "post_skip", "post_out", "club_of", "club_next", "club_skip", "club_found",
                     "club_out", "getter", "rows", "past", "lookup", "have", "dash", "ret"):
            self.assertIn(tc.CAVE_VA + labels[name], starts, name)

    def test_no_instruction_stores_to_an_absolute_address(self) -> None:
        """The caves write only through the game's own history writer (the roster pool), never to a fixed
        address (the xbe-patch memory-write gate refuses stores into read-only sections)."""

        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, _labels = tc._build()
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, tc.CAVE_VA):
            if ins.mnemonic in ("mov", "add", "sub", "or", "and", "xor", "inc", "dec", "push", "pop") and ins.op_str.startswith("dword ptr [0x"):
                self.assertIn(ins.mnemonic, ("push",), f"{ins.address:#x} {ins.mnemonic} {ins.op_str}")

    def test_the_stack_is_balanced_on_every_path_of_the_post_cave(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, labels = tc._build()
        post, club_of = labels["post"], labels["club_of"]
        pushes = pops = 0
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code[post:club_of], tc.CAVE_VA + post):
            if ins.mnemonic == "push":
                pushes += 1
            elif ins.mnemonic == "pop":
                pops += 1
        # value, slot (popped by FUN_0014ee20), the dup (popped by FUN_0014f430): 3 pushes; one explicit pop
        self.assertEqual((pushes, pops), (3, 1))


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def _off(self, va: int) -> int:
        return tc._offset(self.payload, va)

    def _legacy_image(self) -> bytes:
        """The synthetic image as the v0.5 disc carries it: revision-1 cave + hook + lists, no post hook."""

        buf = bytearray(self.payload)
        for _label, off, _before, after in tc._sites(self.payload, legacy=True):
            buf[off: off + len(after)] = after
        cave = self._off(tc.CAVE_VA)
        buf[cave: cave + tc.CAVE_SIZE] = _legacy_cave()
        for section in strength._sections(self.payload):        # every owner re-pins the sections it touched
            end = section.raw_offset + section.raw_size
            if section.raw_size and end <= len(buf) and bytes(buf[section.raw_offset: end]) != self.payload[section.raw_offset: end]:
                d = section.header_offset + 36
                buf[d: d + 20] = strength.section_digest(bytes(buf), section)
        return bytes(buf)

    def test_status_apply_applied_and_digests(self) -> None:
        self.assertEqual(tc.status(self.payload), "retail")
        patched, receipt = tc.apply(self.payload)
        self.assertEqual(tc.status(patched), "applied")
        self.assertEqual(receipt["changed_bytes"], sum(1 for a, b in zip(self.payload, patched) if a != b))
        self.assertEqual({e["label"] for e in receipt["edits"]},
                         {"hook", "post_hook", "cave"} | {f"list_{label}" for label, _v, _p in tc.COLUMN_LISTS})
        self.assertEqual(receipt["field"], 87)
        self.assertEqual(receipt["revision"], 2)
        self.assertTrue(_section_digests_consistent(patched))
        hook = self._off(tc.HOOK_VA)
        self.assertEqual(patched[hook: hook + 25], tc.PATCHED_HOOK)
        post = self._off(tc.POST_HOOK_VA)
        self.assertEqual(patched[post: post + 7], tc.PATCHED_POST_HOOK)
        cave = self._off(tc.CAVE_VA)
        self.assertEqual(patched[cave: cave + tc.CAVE_SIZE], tc.cave_bytes())
        for label, va, pointers in tc.COLUMN_LISTS:
            off = self._off(va + tc.LIST_POINTERS_OFF)
            self.assertEqual(patched[off: off + tc.LIST_SLOTS * 4], tc.list_words(pointers, True), label)
        # the Yr descriptor itself is untouched
        yr = self._off(tc.YR_DESCRIPTOR_VA)
        self.assertEqual(patched[yr: yr + 0xB0], tc.RETAIL_YR_DESCRIPTOR)
        # every byte outside the sites is untouched
        sites = [(e["file_offset"], e["bytes"]) for e in receipt["edits"]]
        covered = set()
        for off_hex, size in sites:
            covered.update(range(int(off_hex, 16), int(off_hex, 16) + size))
        headers = set()
        for section in strength._sections(self.payload):
            headers.update(range(section.header_offset + 36, section.header_offset + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= covered | headers, sorted(changed - covered - headers)[:10])

    def test_apply_is_idempotent_and_refuses_foreign_bytes(self) -> None:
        patched, _r = tc.apply(self.payload)
        again, receipt = tc.apply(patched)
        self.assertEqual(again, patched)
        self.assertEqual(receipt, {"already_applied": True, "changed_bytes": 0})
        for label, va in (("hook", tc.HOOK_VA + 3), ("post_hook", tc.POST_HOOK_VA + 2), ("cave", tc.CAVE_VA + 40),
                          ("list", tc.COLUMN_LISTS[0][1] + tc.LIST_POINTERS_OFF + 8), ("yr", tc.YR_DESCRIPTOR_VA + 0x70)):
            for base in (self.payload, patched):
                buf = bytearray(base)
                buf[self._off(va)] ^= 0x55
                self.assertEqual(tc.status(bytes(buf)), "foreign", label)
                with self.assertRaises(tc.TeamColumnError):
                    tc.apply(bytes(buf))

    def test_a_revision_1_image_reads_as_applied_and_upgrades_in_place(self) -> None:
        legacy = self._legacy_image()
        # revision 1 keeps reading "applied" so every other owner that checks the TEAM column still recognises a v0.5 image
        self.assertEqual(tc.status(legacy), "applied")
        self.assertEqual(tc.revision(legacy), 1)
        self.assertEqual((tc.revision(self.payload), tc.revision(tc.apply(self.payload)[0])), (0, 2))
        patched, receipt = tc.apply(legacy)
        self.assertEqual(tc.status(patched), "applied")
        self.assertEqual(tc.revision(patched), 2)
        self.assertEqual(receipt["upgraded_from_revision"], 1)
        # an upgrade rewrites exactly the cave (including the descriptor's getter) and the new hook site
        self.assertEqual({e["label"] for e in receipt["edits"]}, {"post_hook", "cave"})
        self.assertEqual(patched, tc.apply(self.payload)[0], "retail -> applied equals revision 1 -> applied byte for byte")
        self.assertTrue(_section_digests_consistent(patched))
        # a revision-1 image with any other foreign byte is refused
        for va in (tc.HOOK_VA + 1, tc.COLUMN_LISTS[2][1] + tc.LIST_POINTERS_OFF + 4, tc.POST_HOOK_VA):
            buf = bytearray(legacy)
            buf[self._off(va)] ^= 0x55
            self.assertEqual(tc.status(bytes(buf)), "foreign")
            self.assertIsNone(tc.revision(bytes(buf)))
            with self.assertRaises(tc.TeamColumnError):
                tc.apply(bytes(buf))

    def test_order_independence_with_the_returner_fix_and_draft_ai(self) -> None:
        a = tc.apply(returner.apply(draft.apply(self.payload)[0])[0])[0]
        b = draft.apply(returner.apply(tc.apply(self.payload)[0])[0])[0]
        c = returner.apply(tc.apply(draft.apply(self.payload)[0])[0])[0]
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertTrue(_section_digests_consistent(a))
        self.assertEqual((tc.status(a), returner.status(a), draft.status(a)), ("applied", "applied", "applied"))

    def test_read_any_write_copy_and_build_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "default.xbe"
            src.write_bytes(self.payload)
            self.assertEqual(tt.read_any(src)["team_column"], "retail")
            self.assertEqual(mod_build.inspect(src)["team_column"], "retail")
            dst = Path(tmp) / "out.xbe"
            receipt = tt.write_xbe_copy(src, dst, team_column=True)
            self.assertEqual(receipt["team_column"], "applied")
            self.assertEqual(tt.read_any(dst)["team_column"], "applied")
            self.assertEqual(tc.status(dst.read_bytes()), "applied")
            # a revision-1 image reads as applied and is upgraded when the box is ticked
            legacy = Path(tmp) / "legacy.xbe"
            legacy.write_bytes(self._legacy_image())
            self.assertEqual(tt.read_any(legacy)["team_column"], "applied")
            upgraded = Path(tmp) / "upgraded.xbe"
            tt.write_xbe_copy(legacy, upgraded, team_column=True)
            self.assertEqual(tc.revision(upgraded.read_bytes()), 2)
            self.assertEqual(upgraded.read_bytes(), dst.read_bytes())
            # the same flag through the Build pipeline (a bare XBE), with the receipt key
            out = Path(tmp) / "built.xbe"
            plan = mod_build.BuildPlan(source=str(src), target=str(out), team_column=True)
            self.assertTrue(plan.wants_xbe_patch())
            built = mod_build.build(plan, lambda *_a: None)
            self.assertEqual(built["steps"][0]["team_column"], "applied")
            self.assertEqual(tc.status(out.read_bytes()), "applied")
        self.assertTrue(mod_build.availability()["team_column"])
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertTrue(mod_build.PRESETS[name]["team_column"], name)
            self.assertTrue(mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), name).team_column, name)
        self.assertIn("team_column", mod_build.BuildPlan(source="s", target="t").to_recipe())


@unittest.skipUnless(RETAIL_XBE.is_file(), "private retail default.xbe not present")
class RetailImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()

    def test_retail_status_apply_and_order_independence(self) -> None:
        self.assertEqual(tc.status(self.retail), "retail")
        patched, receipt = tc.apply(self.retail)
        self.assertEqual(tc.status(patched), "applied")
        self.assertEqual(receipt["changed_bytes"], 707)
        self.assertTrue(_section_digests_consistent(patched))
        a = tc.apply(returner.apply(draft.apply(self.retail)[0])[0])[0]
        b = draft.apply(returner.apply(tc.apply(self.retail)[0])[0])[0]
        self.assertEqual(a, b)
        self.assertEqual(tt.read_any(RETAIL_XBE)["team_column"], "retail")

    def test_the_post_game_hook_site_is_the_retail_loop_call_site(self) -> None:
        """0x134E05 calls the per-player merge FUN_001334b0; 0x134E0A is the next instruction pair."""

        off = tc._offset(self.retail, tc.POST_HOOK_VA - 5)
        call = self.retail[off: off + 5]
        self.assertEqual(call[0], 0xE8)
        self.assertEqual(tc.POST_HOOK_VA + struct.unpack_from("<i", call, 1)[0], 0x1334B0)
        # push esi ; push ebx directly in front of the call
        self.assertEqual(self.retail[off - 2: off], bytes.fromhex("5653"))


def _stream_words(uc, player: int) -> list[int]:
    head = struct.unpack("<I", bytes(uc.mem_read(player + 0x2C, 4)))[0]
    out = []
    if head == 0:
        return out
    for i in range(64):
        word = struct.unpack("<I", bytes(uc.mem_read(head + i * 4, 4)))[0]
        out.append(word)
        if word & 0x80000000:
            break
    return out


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN and HAVE_CAPSTONE, "retail default.xbe, unicorn and capstone needed")
class UnicornTests(unittest.TestCase):
    """The real history writer/reader of the patched retail image driven through the caves with a
    synthesised roster object: forty clubs, twelve players, a pool with their streams."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.patched, _receipt = tc.apply(RETAIL_XBE.read_bytes())

    # ------------------------------------------------------------------ machine
    def _machine(self):
        from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x00010000, 0x00E61000 - 0x00010000)     # .text .. the end of .data's BSS tail
        for section in strength._sections(self.patched):
            if section.virtual_address in (0x11000, 0x4E3AE0, 0xA69980):
                uc.mem_write(section.virtual_address,
                             self.patched[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_map(SCRATCH, 0x20000)
        self.next_calls = 0

        def hook(emu, address, size, _user):
            if address == tc.FN_NEXT_PLAYER:                  # FUN_00061b90 (the in-game player iterator): stub
                self.next_calls += 1
                from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP
                esp = emu.reg_read(UC_X86_REG_ESP)
                emu.reg_write(UC_X86_REG_EAX, 0x1234)
                emu.reg_write(UC_X86_REG_EIP, struct.unpack("<I", bytes(emu.mem_read(esp, 4)))[0])
                emu.reg_write(UC_X86_REG_ESP, esp + 4)

        uc.hook_add(UC_HOOK_CODE, hook, begin=tc.FN_NEXT_PLAYER, end=tc.FN_NEXT_PLAYER)
        return uc

    @staticmethod
    def _u(uc, va: int) -> int:
        return struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]

    def _world(self, uc, *, count: int = 3, club_of_p0: int | None = 5, games_entry: bool = True) -> None:
        """Roster: TEAM_COUNT clubs with three-letter names, PLAYER_COUNT players.  Player 0 is the subject
        (current slot ``count``); players 1.. are fillers.  ``club_of_p0`` puts player 0 into that club's array."""

        u32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)   # noqa: E731
        uc.mem_write(ROSTER + 0x00, u32(PLAYER_COUNT))
        uc.mem_write(ROSTER + 0x04, u32(PLAYERS))
        uc.mem_write(ROSTER + 0x18, u32(TEAM_COUNT))
        uc.mem_write(ROSTER + 0x1C, u32(TEAMS))
        uc.mem_write(ROSTER + 0x40, u32(1))                 # pool: one dword in use
        uc.mem_write(ROSTER + 0x44, u32(POOL))
        for k in range(TEAM_COUNT):
            abbr = f"C{k:02d}"
            uc.mem_write(ABBRS + k * 0x20, abbr.encode("utf-16-le") + b"\0\0")
            uc.mem_write(TEAMS + k * tc.TEAM_STRIDE + tc.TEAM_ABBR_OFF, u32(ABBRS + k * 0x20))
        for i in range(PLAYER_COUNT):
            player = PLAYERS + i * PLAYER_SIZE
            uc.mem_write(player + 0x24, u32(0x06310004 | (count << 8)))      # the retail bit pattern around the slot count
            uc.mem_write(player + 0x2C, u32(0))
            uc.mem_write(player + 0x30, u32(0))                              # the field revision 1 trusted: it is 0
        player0 = PLAYERS
        uc.mem_write(player0 + 0x2C, u32(POOL))
        field = 0 if games_entry else 5                     # field 0 = games played; 5 = some other counter
        uc.mem_write(POOL, u32(0x80000000 | (count << 23) | (field << 16) | 16))   # one live entry, end of stream
        if club_of_p0 is not None:
            self._club_add(uc, club_of_p0, player0)
        uc.mem_write(tc.ROSTER_GLOBAL, u32(ROSTER))
        uc.mem_write(0x00BD7F98, u32(0))                    # history class 0 (regular season)
        uc.mem_write(tc.PLAYER_GLOBAL, u32(player0))

    def _club_add(self, uc, club: int, player: int) -> None:
        team = TEAMS + club * tc.TEAM_STRIDE
        n = bytes(uc.mem_read(team + tc.TEAM_COUNT_OFF, 1))[0]
        uc.mem_write(team + 4 * n, struct.pack("<I", player))
        uc.mem_write(team + tc.TEAM_COUNT_OFF, bytes([n + 1]))

    def _club_remove(self, uc, club: int, player: int) -> None:
        team = TEAMS + club * tc.TEAM_STRIDE
        n = bytes(uc.mem_read(team + tc.TEAM_COUNT_OFF, 1))[0]
        arr = [self._u(uc, team + 4 * j) for j in range(n)]
        arr.remove(player)
        for j in range(n):
            uc.mem_write(team + 4 * j, struct.pack("<I", arr[j] if j < len(arr) else 0))
        uc.mem_write(team + tc.TEAM_COUNT_OFF, bytes([n - 1]))

    def _player(self, i: int = 0) -> int:
        return PLAYERS + i * PLAYER_SIZE

    def _stream(self, uc, player: int) -> list[int]:
        return _stream_words(uc, player)

    def _field(self, uc, player: int, field: int, slot: int):
        for w in self._stream(uc, player):
            if ((w >> 16) & 0x7F) == field and ((w >> 23) & 0x1F) == slot and not w & 0x30000000:
                return w & 0xFFFF
        return None

    # ------------------------------------------------------------------ calls
    def _rollover(self, uc, player: int) -> dict[str, int]:
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP

        uc.reg_write(UC_X86_REG_ESI, player)
        uc.reg_write(UC_X86_REG_EDI, 0)
        uc.reg_write(UC_X86_REG_EBX, 0x10)
        uc.reg_write(UC_X86_REG_EBP, 0)
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        uc.emu_start(tc.HOOK_VA, tc.HOOK_RESUME_VA, count=500_000)
        return {"esi": uc.reg_read(UC_X86_REG_ESI), "edi": uc.reg_read(UC_X86_REG_EDI),
                "ebx": uc.reg_read(UC_X86_REG_EBX), "ebp": uc.reg_read(UC_X86_REG_EBP),
                "esp": uc.reg_read(UC_X86_REG_ESP)}

    def _post(self, uc, club: int, index: int, *, club_pointer: int | None = None) -> dict[str, int]:
        """Run the post-game hook as FUN_00134dd0 reaches it: esi = club record, ebp = index in its array."""

        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI
        from unicorn.x86_const import UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_ESP

        regs = {UC_X86_REG_ESI: club_pointer if club_pointer is not None else TEAMS + club * tc.TEAM_STRIDE,
                UC_X86_REG_EBP: index, UC_X86_REG_EBX: 0x77770001, UC_X86_REG_EDI: 0x77770002,
                UC_X86_REG_EAX: 0xDEAD0001, UC_X86_REG_ECX: 0xDEAD0002, UC_X86_REG_EDX: 0xDEAD0003,
                UC_X86_REG_ESP: STACK_TOP - 4}
        for reg, value in regs.items():
            uc.reg_write(reg, value)
        self.next_calls = 0
        uc.emu_start(tc.POST_HOOK_VA, tc.POST_RESUME_VA, count=2_000_000)
        out = {"esi": uc.reg_read(UC_X86_REG_ESI), "edi": uc.reg_read(UC_X86_REG_EDI), "ebx": uc.reg_read(UC_X86_REG_EBX),
               "ebp": uc.reg_read(UC_X86_REG_EBP), "esp": uc.reg_read(UC_X86_REG_ESP)}
        self.assertEqual(out["esi"], regs[UC_X86_REG_ESI], "esi preserved")
        self.assertEqual(out["ebp"], index, "ebp preserved")
        self.assertEqual(out["ebx"], 0x77770001, "ebx preserved")
        self.assertEqual(out["edi"], 0x77770002, "edi preserved")
        self.assertEqual(out["esp"], STACK_TOP - 4, "stack balanced")
        self.assertEqual(self.next_calls, 1, "the displaced `call 0x61b90` ran exactly once")
        return out

    def _getter(self, uc, bank: int) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_ESI
        from unicorn.x86_const import UC_X86_REG_ESP

        uc.mem_write(STACK_TOP - 4, struct.pack("<I", RET_SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        uc.reg_write(UC_X86_REG_ECX, bank)
        uc.reg_write(UC_X86_REG_EAX, 0xDEADBEEF)
        for reg, value in ((UC_X86_REG_ESI, 0x5151), (UC_X86_REG_EDI, 0x5252), (UC_X86_REG_EBX, 0x5353)):
            uc.reg_write(reg, value)
        uc.emu_start(tc.GETTER_VA, RET_SENTINEL, count=2_000_000)
        self.assertEqual((uc.reg_read(UC_X86_REG_ESI), uc.reg_read(UC_X86_REG_EDI), uc.reg_read(UC_X86_REG_EBX)),
                         (0x5151, 0x5252, 0x5353), "the getter preserves esi/edi/ebx")
        self.assertEqual(uc.reg_read(UC_X86_REG_ESP), STACK_TOP, "the getter returns with a balanced stack")
        return uc.reg_read(UC_X86_REG_EAX)

    def _club_of(self, uc, player: int) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP

        uc.mem_write(STACK_TOP - 4, struct.pack("<I", RET_SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        uc.reg_write(UC_X86_REG_EAX, player)
        for reg, value in ((UC_X86_REG_ESI, 0x6161), (UC_X86_REG_EDI, 0x6262), (UC_X86_REG_EBX, 0x6363)):
            uc.reg_write(reg, value)
        uc.emu_start(tc.CLUB_OF_VA, RET_SENTINEL, count=2_000_000)
        self.assertEqual((uc.reg_read(UC_X86_REG_ESI), uc.reg_read(UC_X86_REG_EDI), uc.reg_read(UC_X86_REG_EBX)),
                         (0x6161, 0x6262, 0x6363))
        value = uc.reg_read(UC_X86_REG_EAX)
        return value - (1 << 32) if value >= 1 << 31 else value

    def _text(self, uc, va: int) -> str:
        raw = bytes(uc.mem_read(va, 32))
        return raw.decode("utf-16-le").split("\0")[0]

    # ------------------------------------------------------------------ tests
    def test_rollover_cave_is_only_the_retail_slot_count_increment(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=7)
        before_24 = self._u(uc, self._player() + 0x24)
        regs = self._rollover(uc, self._player())
        after_24 = self._u(uc, self._player() + 0x24)
        self.assertEqual((after_24 >> 8) & 0x1F, 4)
        self.assertEqual(after_24 & ~0x1F00, before_24 & ~0x1F00, "only the slot count changed")
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1, "nothing is appended to the pool at the rollover")
        self.assertEqual((regs["esi"], regs["edi"], regs["ebx"], regs["ebp"], regs["esp"]),
                         (self._player(), 0, 0x10, 0, STACK_TOP - 4))

    def test_the_post_hook_records_the_club_in_the_current_slot(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        self._post(uc, club=5, index=0)
        stream = self._stream(uc, self._player())
        self.assertEqual(self._u(uc, ROSTER + 0x40), 2, "one dword appended to the pool")
        self.assertTrue(stream[-1] & 0x80000000)
        expected = (3 << 23) | (tc.TEAM_FIELD << 16) | 6                # slot 3, field 87, club 5 + 1
        self.assertIn(expected, [w & 0x7FFFFFFF for w in stream], [hex(w) for w in stream])
        self.assertIn((3 << 23) | 16, [w & 0x7FFFFFFF for w in stream], "the games entry survives")
        for word in stream:
            self.assertFalse(word & 0x10000000, "no entry is marked deleted")
            self.assertFalse(word & 0x20000000, "regular-season class")
            self.assertFalse(word & 0x40000000)
        self.assertEqual(self._u(uc, 0x00BD7F98), 0, "the history class is untouched")

    def test_a_trade_moves_the_recorded_club_from_the_next_game_on(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        self._post(uc, club=5, index=0)
        self.assertEqual(self._field(uc, self._player(), tc.TEAM_FIELD, 3), 6)
        used = self._u(uc, ROSTER + 0x40)
        self._club_remove(uc, 5, self._player())                         # the trade
        self._club_add(uc, 9, self._player())
        self.assertEqual(self._field(uc, self._player(), tc.TEAM_FIELD, 3), 6, "no game yet: still the old club")
        self._post(uc, club=9, index=self._club_index(uc, 9, self._player()))
        self.assertEqual(self._field(uc, self._player(), tc.TEAM_FIELD, 3), 10, "club 9 + 1 after his first game there")
        self.assertEqual(self._u(uc, ROSTER + 0x40), used, "an update in place: the pool did not grow")

    def _club_index(self, uc, club: int, player: int) -> int:
        team = TEAMS + club * tc.TEAM_STRIDE
        n = bytes(uc.mem_read(team + tc.TEAM_COUNT_OFF, 1))[0]
        return [self._u(uc, team + 4 * j) for j in range(n)].index(player)

    def test_a_player_without_a_games_entry_is_not_recorded(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5, games_entry=False)
        self._post(uc, club=5, index=0)
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1, "no games entry for the season: no team entry")
        self.assertEqual(len(self._stream(uc, self._player())), 1)

    def test_a_player_with_no_history_stream_is_skipped_and_reads_a_dash_in_past_rows(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        rookie = self._player(1)                        # a record the history pool has never seen (+0x2C = 0)
        self._club_add(uc, 5, rookie)
        self._post(uc, club=5, index=self._club_index(uc, 5, rookie))
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1, "no stream: the hook stores nothing and does not crash")
        self.assertEqual(self._u(uc, rookie + 0x2C), 0)
        uc.mem_write(tc.PLAYER_GLOBAL, struct.pack("<I", rookie))
        self.assertEqual(self._text(uc, self._getter(uc, 11)), "C05", "the card of a player with no history still names his club")
        self.assertEqual(self._getter(uc, 12), tc.STR_DASH_VA)
        self.assertEqual(self._getter(uc, 20), tc.STR_DASH_VA)

    def test_a_club_pointer_outside_the_clubs_is_ignored(self) -> None:
        for bad in (34, 35, 39):         # the all-star / classic records, as the Pro Bowl would pass
            uc = self._machine()
            self._world(uc, count=3, club_of_p0=bad)
            self._post(uc, club=bad, index=0)
            self.assertEqual(self._u(uc, ROSTER + 0x40), 1, f"club record {bad} is not a club")
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        self._post(uc, club=5, index=0, club_pointer=TEAMS - 0x1F4)      # below the team array
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1)
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        self._post(uc, club=5, index=0, club_pointer=0)                   # no club at all
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1)

    def test_the_two_user_teams_count_as_clubs(self) -> None:
        for club in (32, 33):
            uc = self._machine()
            self._world(uc, count=3, club_of_p0=club)
            self._post(uc, club=club, index=0)
            self.assertEqual(self._field(uc, self._player(), tc.TEAM_FIELD, 3), club + 1)

    def test_club_of_finds_every_club_position_and_nothing_else(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=None)
        p = self._player(0)
        self.assertEqual(self._club_of(uc, p), -1, "on no club")
        for club in (0, 1, 17, 31, 32, 33):
            self._club_add(uc, club, p)
            self.assertEqual(self._club_of(uc, p), club)
            self._club_remove(uc, club, p)
        self._club_add(uc, 34, p)                       # a classic / all-star record is never searched
        self.assertEqual(self._club_of(uc, p), -1)
        self._club_remove(uc, 34, p)
        # a stale pointer beyond a club's counted array does not count (the game parks reserves and IR players there)
        team = TEAMS + 4 * tc.TEAM_STRIDE
        uc.mem_write(team + 4 * 10, struct.pack("<I", p))
        self.assertEqual(self._club_of(uc, p), -1)
        # the first club wins, and the other players are found at their own clubs
        self._club_add(uc, 20, self._player(1)); self._club_add(uc, 6, self._player(2))
        self.assertEqual(self._club_of(uc, self._player(1)), 20)
        self.assertEqual(self._club_of(uc, self._player(2)), 6)

    def test_getter_rows(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        self._post(uc, club=5, index=0)                                  # season 3 now carries C05
        self._rollover(uc, self._player())                               # count = 4
        self.assertEqual(self._getter(uc, 9), tc.STR_EMPTY_VA)
        self.assertEqual(self._text(uc, tc.STR_EMPTY_VA), "")
        live = self._getter(uc, 11)
        self.assertEqual(live, ABBRS + 5 * 0x20, "bank 11 = the live club's own string")
        self.assertEqual(self._text(uc, live), "C05")
        past = self._getter(uc, 12)                                      # bank 12 -> slot count-1 = 3 -> the stored entry
        self.assertEqual(past, ABBRS + 5 * 0x20)
        self.assertEqual(self._text(uc, past), "C05")
        self.assertEqual(self._getter(uc, 13), tc.STR_DASH_VA, "no entry for that season")
        self.assertEqual(self._text(uc, tc.STR_DASH_VA), "--")
        # a trade: bank 11 follows the array at once, bank 12 keeps the recorded club
        self._club_remove(uc, 5, self._player()); self._club_add(uc, 9, self._player())
        self.assertEqual(self._text(uc, self._getter(uc, 11)), "C09")
        self.assertEqual(self._text(uc, self._getter(uc, 12)), "C05")
        # released / injured reserve (outside every array): bank 11 falls back to the recorded club of that season
        self._club_remove(uc, 9, self._player())
        self.assertEqual(self._getter(uc, 11), tc.STR_DASH_VA, "no club and nothing recorded for the new season")
        self.assertEqual(self._text(uc, self._getter(uc, 12)), "C05")
        # ... and with a recorded entry for the current season the fallback shows it
        uc.mem_write(self._player() + 0x24, struct.pack("<I", (self._u(uc, self._player() + 0x24) & ~0x1F00) | (3 << 8)))
        self.assertEqual(self._text(uc, self._getter(uc, 11)), "C05", "season 3 in progress, player on no club: recorded club")
        uc.mem_write(self._player() + 0x24, struct.pack("<I", (self._u(uc, self._player() + 0x24) & ~0x1F00) | (4 << 8)))
        # a folded ("pre") entry reads "--"
        head = self._u(uc, self._player() + 0x2C)
        for i in range(3):
            word = self._u(uc, head + i * 4)
            if (word >> 16) & 0x7F == tc.TEAM_FIELD:
                uc.mem_write(head + i * 4, struct.pack("<I", word | 0x40000000))
        self.assertEqual(self._getter(uc, 12), tc.STR_DASH_VA)
        # an index that is not a team of this roster
        for i in range(3):
            word = self._u(uc, head + i * 4)
            if (word >> 16) & 0x7F == tc.TEAM_FIELD:
                uc.mem_write(head + i * 4, struct.pack("<I", (word & ~0x4000FFFF) | (TEAM_COUNT + 5)))
        self.assertEqual(self._getter(uc, 12), tc.STR_DASH_VA)
        # no player on the card
        uc.mem_write(tc.PLAYER_GLOBAL, struct.pack("<I", 0))
        self.assertEqual(self._getter(uc, 11), tc.STR_DASH_VA)
        self.assertEqual(self._getter(uc, 12), tc.STR_DASH_VA)
        # the shared text buffer was never written
        self.assertEqual(bytes(uc.mem_read(0x00C901C8, 8)), bytes(8))

    def test_current_season_row_follows_the_array_even_with_an_older_record(self) -> None:
        """The in-progress season shows where he plays NOW; the recorded club is only the fallback."""

        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        self._post(uc, club=5, index=0)
        self._club_remove(uc, 5, self._player()); self._club_add(uc, 12, self._player())
        self.assertEqual(self._text(uc, self._getter(uc, 11)), "C12")
        self.assertEqual(self._field(uc, self._player(), tc.TEAM_FIELD, 3), 6)

    def test_a_season_of_games_for_two_clubs_keeps_the_last_one(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, club_of_p0=5)
        for club in (5, 5, 9, 9, 9):
            if self._club_index_or_none(uc, club, self._player()) is None:
                for other in range(40):
                    if other != club and self._club_index_or_none(uc, other, self._player()) is not None:
                        self._club_remove(uc, other, self._player())
                self._club_add(uc, club, self._player())
            self._post(uc, club=club, index=self._club_index(uc, club, self._player()))
        self.assertEqual(self._field(uc, self._player(), tc.TEAM_FIELD, 3), 10)
        self.assertEqual(self._u(uc, ROSTER + 0x40), 2, "one team dword for the whole season")

    def _club_index_or_none(self, uc, club: int, player: int):
        try:
            return self._club_index(uc, club, player)
        except ValueError:
            return None


@unittest.skipUnless(RETAIL_XBE.is_file() and RETAIL_PACK0.is_file() and HAVE_UNICORN and HAVE_CAPSTONE,
                     "retail default.xbe, retail pack 0, unicorn and capstone needed")
class RetailRosterTests(unittest.TestCase):
    """The cause, on the real retail roster: player+0x30 is 0 for every record also after the game's own
    relocation, and the new club lookup agrees with the club arrays for every player."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_team_history as history

        with history._outer_image()(RETAIL_DIR) as archive:
            entry = history._entry(archive)
            cls.body = archive.read(entry.virtual_offset, entry.size)[history.RESOURCE_HEADER_SIZE:]
        cls.patched, _ = tc.apply(RETAIL_XBE.read_bytes())

    def _world(self):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x00010000, 0x00E61000 - 0x00010000)
        for section in strength._sections(self.patched):
            if section.virtual_address in (0x11000, 0x4E3AE0, 0xA69980):
                uc.mem_write(section.virtual_address, self.patched[section.raw_offset: section.raw_offset + section.raw_size])
        main, stack = 0x02000000, 0x027F0000
        uc.mem_map(main, 0x100000)
        uc.mem_map(stack - 0x1000, 0x10000)
        uc.mem_write(main, self.body)
        root = main + 0x40
        uc.mem_write(tc.ROSTER_GLOBAL, struct.pack("<I", root))
        stop = stack + 0x800
        uc.mem_write(stack, struct.pack("<I", stop))
        uc.reg_write(UC_X86_REG_ECX, root)
        uc.reg_write(UC_X86_REG_ESP, stack)
        uc.emu_start(0xC0500, stop, count=5_000_000)             # FUN_000c0500: the game's own relocation, in place
        return uc, root, main, stack

    def test_player_plus_0x30_is_zero_for_every_record_and_club_of_matches_the_arrays(self) -> None:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP

        uc, root, _main, stack = self._world()
        u32 = lambda va: struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]   # noqa: E731
        players, base = u32(root), u32(root + 4)
        teams = u32(root + 0x1C)
        self.assertEqual(players, 2479)
        self.assertEqual([u32(base + i * 0x54 + 0x30) for i in range(players)].count(0), players,
                         "the field revision 1 trusted holds 0 in every retail record, after relocation too")
        member: dict[int, int] = {}
        for club in range(34):
            team = teams + club * 0x1F4
            for j in range(bytes(uc.mem_read(team + 0x11C, 1))[0]):
                member.setdefault(u32(team + 4 * j), club)
        sentinel = stack + 0x700
        checked = 0
        for i in range(0, players, 7):               # every 7th record keeps the test fast
            p = base + i * 0x54
            uc.mem_write(stack, struct.pack("<I", sentinel))
            uc.reg_write(UC_X86_REG_ESP, stack)
            uc.reg_write(UC_X86_REG_EAX, p)
            for reg in (UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBX):
                uc.reg_write(reg, 0x4242)
            uc.emu_start(tc.CLUB_OF_VA, sentinel, count=2_000_000)
            got = uc.reg_read(UC_X86_REG_EAX)
            got = got - (1 << 32) if got >= 1 << 31 else got
            self.assertEqual(got, member.get(p, -1), f"record {i}")
            checked += 1
        self.assertGreater(checked, 300)
        self.assertGreater(len(member), 1500)


if __name__ == "__main__":
    unittest.main()
