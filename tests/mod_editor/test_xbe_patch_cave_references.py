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
        from mod_editor.core import nfl2k5_penalties as penalties, nfl2k5_throw_arc as flight
        # Standalone toggle composes before the bundled profile; flight preserves 80 yd.
        seed, _ = penalties.apply_chop_block(cls.retail)
        seed, _ = tt.plan_patch(seed, tt.curves_for(tt.TuningSettings(80)))
        seed, _ = flight.apply(seed)
        cls.sec = sections(cls.retail)
        flags = {name: True for name in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "returner_fix", "progression",
                                          "scheme_labels", "camera", "kick_rules", "widescreen", "overtime", "team_column", "seven_on_seven")}
        cls.patched, _receipt = tt._apply_all(seed, None, **flags, arc_table=False, kick_power=False, penalties="nfl", uniform_choice="choice", kick_laces=True, franchise_practice=True, prospect_names="modern", player_star=True, dynamic_kickoff=True)
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        cls.patched, _ = pools.apply(cls.patched)
        cls.patched, cls.rows_receipt = rows.apply(cls.patched)
        if rows.status(cls.patched) != "applied":
            raise AssertionError("SPECIAL rows and summary spacing did not compose")
        cls.stack = cls.patched
        from mod_editor.core import nfl2k5_practice_squad as ps
        cls.patched, _ps_receipt = ps.apply(cls.stack)
        from mod_editor.core import nfl2k5_depth_locks as locks
        cls.before_depth_locks = cls.patched
        cls.patched, _ = locks.apply(cls.patched)
        from mod_editor.core import nfl2k5_practice_reserves as practice_reserves
        cls.patched, _ = practice_reserves.apply(cls.patched)
        from mod_editor.core import nfl2k5_season_cap as season_cap
        cls.patched, _ = season_cap.apply(cls.patched)
        if season_cap.status(cls.patched) != "applied":
            raise AssertionError("season-cap owner missing from the composed XBE")
        from tests.nfl2k5_allocator_stack import compose
        cls.before_allocator = cls.patched
        cls.patched, cls.music_receipt = compose(cls.patched, reverse=getattr(cls, "reverse_owners", False), scaleout=getattr(cls, "scaleout", False))
        from mod_editor.core import nfl2k5_momentum as momentum
        settings = momentum.read_settings(cls.patched)
        if not settings.get("momentum_collisions") or settings.get("momentum_collision_level") != 100:
            raise AssertionError("collision momentum missing from the composed XBE")
        from mod_editor.core import nfl2k5_calendar_engine as calendar
        if calendar.status(cls.patched) != "applied":
            raise AssertionError("calendar owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        if defensive_try.status(cls.patched) != "applied":
            raise AssertionError("defensive conversion stat extension missing from the composed XBE")
        defensive_try._stats_sites(cls.patched)  # both named RX/RO reservations
        from mod_editor.core import nfl2k5_roster_storage as roster_storage
        if roster_storage.status(cls.patched) != "applied":
            raise AssertionError("stadium-list owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_music_playlist as playlist
        if playlist.status(cls.patched) != "applied":
            raise AssertionError("playlist owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_practice_squad_screen as practice_screen
        if practice_screen.status(cls.patched) != "applied":
            raise AssertionError("Practice Squad screen missing from the composed XBE")
        from mod_editor.core import nfl2k5_abilities_runtime as abilities
        if abilities.status(cls.patched) != "applied":
            raise AssertionError("abilities owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_qb_spy_runtime as qb_spy
        if qb_spy.status(cls.patched) != "applied":
            raise AssertionError("QB spy owner missing from the composed XBE")
        # This audit allocates nothing. It verifies that neither deferred CB
        # tier has displaced Spy's recognized hooks or the reaction owners.
        from mod_editor.core import nfl2k5_zone_facing as zone_facing
        cls.zone_evidence = zone_facing.assess(cls.patched)
        if cls.zone_evidence["states"]["initial_drop"] != "applied":
            raise AssertionError("Initial zone-drop owner missing from tier evidence")
        from mod_editor.core import nfl2k5_widescreen as wide
        if wide.status(cls.patched) != "applied" or wide.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("widescreen v3 sites/context did not compose and replay")
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
        # Calendar composes the existing complete-function preseason rewrite.
        # Its retained eight-byte retail island must not turn displaced internal
        # branches into "external" callers. Conversely, never merge the playoff
        # seeder across the independently called builder entry at 0x2A7E50.
        ranges = set()
        for a, b in merged:
            if a < 0x2BF1B0 and b > 0x2BEC20:
                a, b = 0x2BEC20, 0x2BF1B0
            if a < 0x2A7E50 < b:
                ranges.add((a, 0x2A7E50))
                a = 0x2A7E50
            if b - a >= CAVE_MIN:
                ranges.add((a, b))
        return sorted((a, b) for a, b in ranges if b - a >= CAVE_MIN)

    def _calendar_noninstruction(self, source, target):
        """A single pinned E9 is the displacement of JG, not a rel32 opcode.

        This is an instruction-boundary proof, not an oracle unknown/free
        exemption. The generic oracle and its raw candidate inventory stay intact.
        """
        if (source, target) != (0x2A268D, 0x2BEDF8):
            return False
        start, end = 0x2A2640, 0x2A2693
        raw = self.retail[start - BASE:end - BASE]
        self.assertEqual(self.patched[start - BASE:end - BASE], raw)
        import hashlib
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "2420e43e3b55e9d3d4ef952cb9ea881178ce98a2f6915d356ae5b287bf491f08")
        instructions = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(raw, start))
        self.assertEqual(instructions[0].address, start)
        self.assertEqual(instructions[-1].address + instructions[-1].size, end)
        self.assertNotIn(source, {i.address for i in instructions})
        branch = next(i for i in instructions if i.address == source - 1)
        self.assertEqual((branch.bytes.hex(), branch.mnemonic, branch.op_str),
                         ("7fe9", "jg", "0x2a2677"))
        return True

    def test_stadium_patch_changes_only_existing_instruction_operands(self) -> None:
        from mod_editor.core import nfl2k5_roster_storage as storage
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, old, new in storage.sites(storage.site(self.patched)["va"]):
            before, after = list(md.disasm(old, va)), list(md.disasm(new, va))
            self.assertEqual(len(before), 1)
            self.assertEqual(len(after), 1)
            self.assertEqual((before[0].id, before[0].size), (after[0].id, after[0].size))
            self.assertEqual(image.read(va, len(new)), new)

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
                           and not (isinstance(r, tuple) and r[1] == ".text" and a <= r[2] + BASE < b)
                           and not self._calendar_noninstruction(r, t)]
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
        self.assertEqual(season.group_status(self.patched, "playoffs_14"), "applied")
        dependency = self.patched
        patched, _ = picture.apply(dependency)
        self.assertEqual(picture.status(patched), "applied")
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
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
            self.assertEqual([r for r in legacy_external_references(targets, start, end)
                              if not self._calendar_noninstruction(r.source, r.start)], [], hex(start))

    def test_current_owners_are_reserved_for_new_allocations(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        # The supplied manifest predates this rebase. The relocation brief permits
        # inspecting its reservations without source_root; current stack bytes
        # are checked separately below. Keep the oracle's drift guard unchanged.
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        for start in (0x1AFDF0, 0x28B410, 0x1D82D0, 0x325E70, 0x2979F0, 0xB4A60, 0x2BA840):
            self.assertTrue(manifest.overlaps(start, start + 1), hex(start))

    def test_practice_squad_spans_preserve_stack_owners(self) -> None:
        from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff
        from mod_editor.core import nfl2k5_practice_squad as ps
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        retail = XbeImage(self.retail)
        stack = XbeImage(self.stack)
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), retail)
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
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), image)
        evidence = storage.allocation_evidence(self.retail, manifest)
        self.assertEqual(evidence["encoded_references"], [])
        self.assertEqual(evidence["manifest_overlaps"], [])
        self.assertEqual(XbeImage(self.patched).read(storage.SECTION_VA, storage.RETAIL_SIZE),
                         image.read(storage.SECTION_VA, storage.RETAIL_SIZE))

    def test_special_spacing_reuses_its_live_descriptor_without_a_new_cave(self) -> None:
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        entry = next(e for e in self.rows_receipt["edits"] if e["label"] == "summary_row_spacing")
        self.assertEqual(int(entry["va"], 16), rows.SUMMARY_STYLE_VA)
        self.assertEqual(entry["size"], len(rows.RETAIL_SUMMARY_STYLE))
        self.assertTrue(self.sec[".data"][0] <= rows.SUMMARY_SPACING_VA < self.sec[".data"][1])
        self.assertEqual(rows._read(self.patched, rows.SUMMARY_SPACING_VA, 4), struct.pack("<f", 1))
        self.assertTrue(self.sec[".rdata"][0] <= rows.SUMMARY_LABEL_WIDTH_VA < self.sec[".rdata"][1])
        self.assertTrue(any(e["label"] == "summary_label_width" and e["size"] == 4
                            for e in self.rows_receipt["edits"]))

    def test_depth_locks_use_only_in_place_routine_rewrites(self) -> None:
        from mod_editor.core import nfl2k5_depth_locks as locks
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        # the regenerated manifest records the lock rewrites as their own owner; exclude them so the
        # check below only sees reservations that belong to OTHER owners (rows' chain test)
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        self.assertEqual(locks.CAVES, ())
        self.assertEqual(locks.RUNTIME_GLOBALS, ())
        self.assertEqual(locks.status(self.before_depth_locks), "retail")
        self.assertEqual(locks.status(self.patched), "applied")
        for site in locks.sites("special"):
            # The only shared reservation is rows' two-byte chain test. It
            # remains unchanged; no byte belonging to another owner is used.
            for va in range(site.va, site.va + len(site.before)):
                if manifest.overlaps(va, va + 1, exclude_owner="nfl2k5_depth_locks"):
                    self.assertEqual(self.patched[va - BASE], self.before_depth_locks[va - BASE], hex(va))

    def test_grown_owner_pages_have_no_retail_reference_encoding(self) -> None:
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_dynamic_kickoff_relocated as relocated
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        proof = space.allocation_evidence(self.retail, manifest, allocated=self.patched)
        self.assertEqual(proof["legacy_encoded_references"], [])
        # Calendar requires v3 even when the caller does not force scale-out.
        if space.layout(self.patched)["version"] == 3:
            self.assertEqual(proof["retail_mapping_overlaps"], [])
            self.assertEqual(len(proof["pages"]), 52)
            self.assertTrue(proof["encoded_references"])  # raw candidates stay visible
        else:
            self.assertEqual(proof["encoded_references"], [])
        self.assertEqual(relocated.status(self.patched), "applied")
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        self.assertEqual(runtime.status(self.patched), "applied")
        for va, original in runtime.HOOKS.values():
            self.assertEqual(manifest.overlaps(va, va + len(original), exclude_owner=runtime.OWNER), [])
        for r in space.reservations(self.patched):
            self.assertGreaterEqual(int(r["start"], 0), space.CODE_VA)

    def test_momentum_owns_named_children_and_pinned_live_spans_without_new_caves(self) -> None:
        from mod_editor.core import nfl2k5_momentum as momentum
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        self.assertEqual(momentum.status(self.patched), "applied")
        for r in momentum.reservations(self.patched):
            start, end = int(r["start"], 0), int(r["end"], 0)
            if start >= space.CODE_VA:
                self.assertEqual(r["parent_owner"], space.OWNER)
            else:
                self.assertEqual(manifest.overlaps(start, end, exclude_owner=momentum.OWNER), [], r)
        from mod_editor.core import nfl2k5_abilities_runtime as abilities
        self.assertEqual(abilities.status(self.patched), "applied")  # the Speedster wrapper owns the 0x75CC8 call
    def test_zone_drop_owns_only_a_complete_call_and_reserved_grown_code(self) -> None:
        from mod_editor.core import nfl2k5_zone_drop as zone_drop
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        self.assertEqual(zone_drop.status(self.patched), "applied")
        self.assertEqual(relocated.status(self.patched), "applied")
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        self.assertEqual(manifest.overlaps(zone_drop.HOOK_VA, zone_drop.CONTINUE_VA,
                                           exclude_owner=zone_drop.OWNER), [])
        site = zone_drop.site(self.patched)
        self.assertGreaterEqual(site["va"], space.CODE_VA)
        self.assertTrue(XbeImage(self.patched).section(site["va"], site["size"]).executable)
        self.assertEqual({va: refs for va, refs in self.targets.items()
                          if site["va"] <= va < site["va"] + site["size"]}, {})
        self.assertEqual(space.allocation_evidence(self.retail, manifest,
                                                   allocated=self.patched)["legacy_encoded_references"], [])
        instructions = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(
            XbeImage(self.patched).read(zone_drop.HOOK_VA, 5), zone_drop.HOOK_VA))
        self.assertEqual([(i.mnemonic, i.size) for i in instructions], [("call", 5)])
        self.assertTrue(any(r["owner"] == zone_drop.OWNER and r["size"] == 80
                            and int(r["start"], 0) == site["va"]
                            for r in space.reservations(self.patched)))

    def test_playlist_owns_pinned_hooks_and_allocator_children(self):
        from mod_editor.core import nfl2k5_music_playlist as playlist
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        self.assertEqual(playlist.status(self.patched), "applied")
        for row in playlist.reservations(self.patched):
            start, end = int(row["start"], 0), int(row["end"], 0)
            if start < 0x14BA000:
                self.assertEqual(manifest.overlaps(start, end, exclude_owner=playlist.OWNER), [], row)
        code, data, ro = playlist.sites(self.patched)
        self.assertEqual({code["kind"], data["kind"], ro["kind"]}, {"code", "data", "read_only"})

    def test_abilities_have_only_pinned_hooks_and_named_grown_code(self):
        from mod_editor.core import nfl2k5_abilities_runtime as abilities
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        self.assertEqual(abilities.status(self.patched), "applied")
        owner = abilities.allocation(self.patched)
        self.assertGreaterEqual(owner["va"], space.CODE_VA)
        for record in abilities.reservations(self.patched):
            start, end = int(record["start"], 0), int(record["end"], 0)
            if start < space.CODE_VA:
                self.assertLess(end - start, CAVE_MIN)
                self.assertEqual(manifest.overlaps(start, end, exclude_owner=abilities.OWNER), [])
                self.assertTrue(any(r.detail.startswith(abilities.OWNER + ":") for r in manifest.overlaps(start, end)))
            else:
                self.assertEqual(record["parent_owner"], space.OWNER)

    def test_qb_spy_hooks_are_complete_instructions_and_have_no_foreign_owner(self) -> None:
        from mod_editor.core import nfl2k5_qb_spy_runtime as spy, nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        image = XbeImage(self.patched)
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(self.retail))
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, old) in spy.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(old, va)), len(old), name)
            self.assertEqual(manifest.overlaps(va, va+len(old), exclude_owner=spy.OWNER), [], name)
        for row in spy.reservations(self.patched):
            if int(row["start"], 0) >= space.CODE_VA:
                self.assertEqual(row["parent_owner"], space.OWNER)
        self.assertEqual(spy.status(self.patched), "applied")


@unittest.skipUnless(XBE.is_file() and Cs is not None, "retail extraction or capstone not present")
class ScorebugReferenceReservations(unittest.TestCase):
    def test_scorebug_uses_existing_reserved_constants_and_no_new_cave(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as scorebug
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        retail=XBE.read_bytes()
        image=XbeImage(retail)
        manifest=ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)),image)
        reservations=manifest.overlaps(0x10a40,0x10a48)
        self.assertTrue(reservations)
        patched,_=scorebug.apply_xbe(retail)
        md=Cs(CS_ARCH_X86,CS_MODE_32)
        for va,old,new,label in scorebug.xbe_specs():
            section=image.section(va,len(new))
            if section is not None and section.name == ".text":
                self.assertLess(len(new),CAVE_MIN,label)
                insns=list(md.disasm(new,va))
                self.assertEqual(sum(i.size for i in insns),len(new),label)
                self.assertTrue(all(i.mnemonic in ("nop","fadd") for i in insns),label)
        self.assertEqual(scorebug.xbe_status(patched),"applied")


class ReverseOwnerOrderTests(CaveReferenceTests):
    """Run every gate against the same complete union installed in reverse."""
    reverse_owners = True

    def test_both_installation_orders_are_byte_identical(self):
        from tests.nfl2k5_allocator_stack import compose
        self.assertEqual(compose(self.before_allocator, scaleout=getattr(self, "scaleout", False))[0], self.patched)


class ScaleoutOwnerTests(CaveReferenceTests):
    """All existing owner gates against the v3 page map."""
    scaleout = True


class ScaleoutReverseOwnerTests(ReverseOwnerOrderTests):
    scaleout = True


if __name__ == "__main__":
    unittest.main()
