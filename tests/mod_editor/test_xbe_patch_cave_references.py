"""No code cave may sit on bytes the retail executable references.

A cave is only safe in genuinely dead code. The 7-on-7 cave was placed in what the disassembler
called a 525-byte dead routine; the routine really ended after 240 bytes and the bytes after it were
a live function reached through a pointer, so the game hit the cave's int3 fill the moment a play
started (2026-09-03). This test scans the RETAIL image for every relative call/jump target in .text
and every absolute pointer stored in .text/.rdata/.data, then checks that no patch rewrites 16 or
more contiguous .text bytes (a cave) that any such reference lands in. Small rewrites (hooks placed on
referenced instructions on purpose) are not caves and are not checked here."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

try:
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
except Exception:  # noqa: BLE001
    Cs = None

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
CAVE_MIN = 16


def sections(xbe: bytes):
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    count = struct.unpack_from("<I", xbe, 0x11C)[0]
    header = struct.unpack_from("<I", xbe, 0x120)[0] - base
    out = {}
    for i in range(count):
        flags, vaddr, vsize, raw, rawsize, name_addr = struct.unpack_from("<IIIIII", xbe, header + i * 0x38)
        name = xbe[name_addr - base: name_addr - base + 16].split(b"\0")[0].decode("ascii", "replace")
        out[name] = (vaddr, vaddr + vsize, raw, rawsize)
    return out


@unittest.skipUnless(XBE.is_file() and Cs is not None, "retail extraction or capstone not present")
class CaveReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        cls.retail = XBE.read_bytes()
        cls.sec = sections(cls.retail)
        flags = {name: True for name in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "returner_fix", "progression",
                                          "scheme_labels", "camera", "kick_rules", "widescreen", "overtime", "team_column", "seven_on_seven")}
        cls.patched, _receipt = tt._apply_all(cls.retail, None, **flags, arc_table=False, kick_power=False, penalties="nfl", uniform_choice="choice", kick_laces=True, franchise_practice=True, prospect_names="modern", player_star=True, dynamic_kickoff=True)
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        cls.patched, _ = pools.apply(cls.patched)
        cls.patched, _ = rows.apply(cls.patched)
        cls.stack = cls.patched
        from mod_editor.core import nfl2k5_practice_squad as ps
        cls.patched, _ps_receipt = ps.apply(cls.stack)
        from mod_editor.core import nfl2k5_depth_locks as locks
        cls.before_depth_locks = cls.patched
        cls.patched, _ = locks.apply(cls.patched)
        from mod_editor.core import nfl2k5_practice_reserves as practice_reserves
        cls.patched, _ = practice_reserves.apply(cls.patched)
        text_lo, text_hi, _raw, _rawsize = cls.sec[".text"]
        # relative call/jump targets from a linear sweep of .text (byte-granular so no instruction is missed)
        targets: dict[int, list[int]] = {}
        data = cls.retail
        for off in range(text_lo - BASE, text_hi - BASE - 5):
            op = data[off]
            if op in (0xE8, 0xE9):
                rel = struct.unpack_from("<i", data, off + 1)[0]
                tgt = (BASE + off + 5 + rel) & 0xFFFFFFFF
                if text_lo <= tgt < text_hi:
                    targets.setdefault(tgt, []).append(BASE + off)
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                rel = struct.unpack_from("<i", data, off + 2)[0]
                tgt = (BASE + off + 6 + rel) & 0xFFFFFFFF
                if text_lo <= tgt < text_hi:
                    targets.setdefault(tgt, []).append(BASE + off)
        # absolute pointers: any dword in .rdata/.data (vtables, callback tables), and in .text only the
        # immediate of `push imm32` (68), `mov r32, imm32` (B8..BF) or `mov dword [mem], imm32` (C7 ..),
        # so that constants and float tables that happen to look like addresses are not counted
        for name in (".text", ".rdata", ".data"):
            lo, hi, raw, rawsize = cls.sec[name]
            # pointer tables are dword-aligned; .text immediates can sit at any byte
            step = 1 if name == ".text" else 4
            for off in range(raw, raw + rawsize - 4, step):
                v = struct.unpack_from("<I", data, off)[0]
                if not (text_lo <= v < text_hi):
                    continue
                if name == ".text":
                    prev = data[off - 1]
                    immediate = prev == 0x68 or 0xB8 <= prev <= 0xBF or (data[off - 2] == 0xC7 and prev == 0x05) \
                        or (off >= 6 and data[off - 6] == 0xC7 and data[off - 5] == 0x05)
                    if not immediate:
                        continue
                targets.setdefault(v, []).append(("ptr", name, off))
        cls.targets = targets

    def _caves(self) -> list[tuple[int, int]]:
        text_lo, text_hi, _raw, _rawsize = self.sec[".text"]
        ranges = []
        start = None
        for off in range(text_lo - BASE, text_hi - BASE):
            if self.retail[off] != self.patched[off]:
                if start is None:
                    start = off
            elif start is not None:
                ranges.append((start + BASE, off + BASE))
                start = None
        # merge runs separated by fewer than 8 unchanged bytes (a cave's retail bytes may coincide)
        merged: list[list[int]] = []
        for a, b in ranges:
            if merged and a - merged[-1][1] < 8:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        return [(a, b) for a, b in merged if b - a >= CAVE_MIN]

    def test_no_cave_overlaps_referenced_retail_code(self) -> None:
        caves = self._caves()
        self.assertTrue(caves, "no caves found; the scan is broken")
        offenders = []
        for a, b in caves:
            hits = []
            for t, refs in self.targets.items():
                if not (a <= t < b) or t == a:
                    # a replaced routine keeps its entry: callers may still land on the first byte
                    continue
                outside = [r for r in refs
                           if not (isinstance(r, int) and a <= r < b)                       # a jump inside the range
                           and not (isinstance(r, tuple) and r[1] == ".text" and a <= r[2] + BASE < b)]  # a pointer inside it
                if outside:
                    hits.append((hex(t), outside[:3]))
            if hits:
                offenders.append((f"{a:#x}..{b:#x}", hits[:4]))
        self.assertEqual(offenders, [], "caves on referenced code:\n" + "\n".join(map(str, offenders)))

    def test_the_seven_on_seven_cave_stops_before_the_live_function(self) -> None:
        from mod_editor.core import nfl2k5_seven_on_seven as seven
        self.assertEqual(seven.CAVE_VA + seven.CAVE_SIZE, 0x1AC260)
        self.assertIn(0x1AC260, self.targets)
        self.assertEqual(self.patched[0x1AC260 - BASE: 0x1AC270 - BASE], self.retail[0x1AC260 - BASE: 0x1AC270 - BASE])

    def test_playoff_presentation_rewrites_only_owned_callbacks(self) -> None:
        from mod_editor.core import nfl2k5_playoff_picture as picture, nfl2k5_season_length as season
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        dependency, _ = season.apply(self.patched, groups=("playoffs_14",))
        patched, _ = picture.apply(dependency)
        self.assertEqual(picture.status(patched), "applied")
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        # the regenerated manifest now observes the playoff presentation itself (it rides the season step);
        # nothing ELSE may own its sites
        for site in picture.sites():
            self.assertEqual(manifest.overlaps(site.va, site.va + site.size, exclude_owner="nfl2k5_playoff_picture"), [], site.label)
        for start, size in ((picture.TREE_UPDATE_VA, picture.TREE_UPDATE_SIZE),
                            (picture.TREE_SCORES_VA, picture.TREE_SCORES_SIZE)):
            for target, refs in self.targets.items():
                if start < target < start + size:
                    self.assertEqual([r for r in refs if not (
                        isinstance(r, int) and start <= r < start + size) and not (
                        isinstance(r, tuple) and r[1] == ".text" and start <= r[2] + BASE < start + size)], [], hex(target))
        # Existing entry 0x372C60 remains callable from its retail callback table.
        self.assertIn(picture.TREE_SCORES_VA, self.targets)

    def test_oracle_projection_preserves_the_existing_gate(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, legacy_external_references, legacy_references
        targets = legacy_references(XbeImage(self.retail))
        self.assertEqual(set(targets), set(self.targets))
        for start, end in self._caves():
            self.assertEqual(legacy_external_references(targets, start, end), [], hex(start))

    def test_current_owners_are_reserved_for_new_allocations(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        # The supplied manifest predates this rebase. The relocation brief permits
        # inspecting its reservations without source_root; current stack bytes
        # are checked separately below. Keep the oracle's drift guard unchanged.
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        for start in (0x1AFDF0, 0x28B410, 0x1D82D0, 0x325E70, 0x2979F0, 0xB4A60, 0x2BA840):
            self.assertTrue(manifest.overlaps(start, start + 1), hex(start))

    def test_practice_squad_spans_preserve_stack_owners(self) -> None:
        from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff
        from mod_editor.core import nfl2k5_practice_squad as ps
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        retail = XbeImage(self.retail)
        stack = XbeImage(self.stack)
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, retail)
        for start, size, _ in ps.CAVES:
            # the manifest now observes the practice squad itself; nothing ELSE may own its caves
            self.assertEqual(manifest.overlaps(start, start + size, exclude_owner='nfl2k5_practice_squad'), [], hex(start))
            self.assertEqual(stack.read(start, size), retail.read(start, size), hex(start))
            self.assertEqual({va: refs for va, refs in self.targets.items()
                              if start <= va < start + size and any(
                                  not start <= (r if isinstance(r, int) else r[2] + BASE) < start + size
                                  for r in refs)}, {}, hex(start))
        self.assertEqual(ps.status(self.stack), 'retail')
        self.assertEqual(ps.status(self.patched), 'applied')
        self.assertEqual(kickoff.status(self.patched), 'applied')
        self.assertEqual(XbeImage(self.patched).read(kickoff.CAVE_VA, kickoff.CAVE_SIZE),
                         stack.read(kickoff.CAVE_VA, kickoff.CAVE_SIZE))
    def test_depth_rows_share_the_unreferenced_pools_cave_including_its_entry(self) -> None:
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        self.assertEqual(rows.status(self.patched), "applied")
        self.assertEqual(self.patched[pools.CAVE_VA - BASE:pools.CAVE_VA - BASE + pools.CAVE_SIZE], pools.cave_bytes())
        # Unlike an in-place routine rewrite, this is a cave: even the entry
        # must have no retail callers or pointers.
        self.assertEqual({va: refs for va, refs in self.targets.items()
                          if pools.CAVE_VA <= va < pools.CAVE_VA + pools.CAVE_SIZE}, {})

    def test_special_storage_is_a_fresh_loader_allocation_with_no_retail_reference_encoding(self) -> None:
        from mod_editor.core import nfl2k5_depth_chart_storage as storage
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        image = XbeImage(self.retail)
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, image)
        evidence = storage.allocation_evidence(self.retail, manifest)
        self.assertEqual(evidence["encoded_references"], [])
        self.assertEqual(evidence["manifest_overlaps"], [])
        self.assertEqual(XbeImage(self.patched).read(storage.SECTION_VA, storage.RETAIL_SIZE),
                         image.read(storage.SECTION_VA, storage.RETAIL_SIZE))

    def test_depth_locks_use_only_in_place_routine_rewrites(self) -> None:
        from mod_editor.core import nfl2k5_depth_locks as locks
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        self.assertEqual(locks.CAVES, ())
        self.assertEqual(locks.RUNTIME_GLOBALS, ())
        self.assertEqual(locks.status(self.before_depth_locks), "retail")
        self.assertEqual(locks.status(self.patched), "applied")
        for site in locks.sites("special"):
            # The only shared reservation is rows' two-byte chain test. It
            # remains unchanged; no byte belonging to another owner is used.
            for va in range(site.va, site.va + len(site.before)):
                if manifest.overlaps(va, va + 1):
                    self.assertEqual(self.patched[va - BASE], self.before_depth_locks[va - BASE], hex(va))


if __name__ == "__main__":
    unittest.main()
