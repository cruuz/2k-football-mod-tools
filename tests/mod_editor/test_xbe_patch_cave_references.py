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
    def test_accelerated_clock_hooks_and_owned_children_are_reserved(self):
        from mod_editor.core import nfl2k5_accelerated_clock as patch
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        places = patch.allocations(self.patched)
        self.assertTrue(patch.verify(self.patched, enabled=True, minimum_seconds=20)['enabled'])
        retail, installed = XbeImage(self.retail), XbeImage(self.patched)
        for name, va, before, after in patch.sites(places['code']['va']):
            self.assertEqual(retail.read(va, len(before)), before)
            self.assertEqual(installed.read(va, len(after)), after)
            self.assertEqual(self.manifest.overlaps(va, va+len(before), exclude_owner=patch.OWNER), [], name)
            self.assertTrue(self.manifest.overlaps(va, va+len(before)), name)
        for allocation in places.values():
            start, end = allocation['va'], allocation['va']+allocation['size']
            self.assertTrue(any(r.detail.startswith(patch.OWNER + ':') for r in self.manifest.overlaps(start, end)))
            self.assertTrue(all(r.detail.startswith('nfl2k5_xbe_space:')
                                for r in self.manifest.overlaps(start, end, exclude_owner=patch.OWNER)))

    def test_deep_zone_hooks_have_exclusive_live_ownership(self):
        from mod_editor.core import nfl2k5_deep_zone as patch
        self.assertEqual(patch.status(self.patched), "applied")
        for va, before in patch.HOOKS.values():
            self.assertTrue(self.manifest.overlaps(va, va+len(before)))
            self.assertEqual(self.manifest.overlaps(va, va+len(before), exclude_owner=patch.OWNER), [])

    def test_money_downs_hooks_are_owned_and_code_is_allocated(self):
        from mod_editor.core import nfl2k5_cpu_money_downs as patch, nfl2k5_xbe_space as space
        row = next(a for a in space.layout(self.patched)["allocations"] if a["owner"] == patch.OWNER)
        for va, before in patch.HOOKS.values():
            self.assertEqual(self.manifest.overlaps(va, va + len(before), exclude_owner=patch.OWNER), [])
            self.assertTrue(self.manifest.overlaps(va, va + len(before)))
            self.assertFalse([address for address in self.targets if va < address < va + len(before)])
        self.assertGreaterEqual(row["va"], space.CODE_VA)
        self.assertEqual(patch.status(self.patched), "applied")

    def test_contracts_editor_uses_only_owned_read_only_tables(self):
        from mod_editor.core import nfl2k5_franchise_edit_player as edit
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        row = edit.allocation(self.patched)
        image = XbeImage(self.patched)
        self.assertEqual((row["kind"], row["size"]), ("read_only", 704))
        self.assertFalse(image.section(row["va"]).writable)
        self.assertFalse(image.section(row["va"]).executable)
        self.assertEqual(image.read(row["va"], 704), edit.read_only_bytes())
        for _, va, before, _ in edit.sites(row["va"]):
            self.assertEqual(self.manifest.overlaps(va, va + len(before), exclude_owner=edit.OWNER), [])
            self.assertTrue(self.manifest.overlaps(va, va + len(before)))

    def test_coverage_trail_hook_is_owned_and_code_is_allocated(self):
        from mod_editor.core import nfl2k5_coverage_trail as trail, nfl2k5_xbe_space as space
        row = next(a for a in space.layout(self.patched)["allocations"] if a["owner"] == trail.OWNER)
        self.assertEqual(self.manifest.overlaps(trail.HOOK_VA, trail.HOOK_VA + 6,
                                               exclude_owner=trail.OWNER), [])
        self.assertTrue(self.manifest.overlaps(trail.HOOK_VA, trail.HOOK_VA + 6))
        self.assertGreaterEqual(row["va"], space.CODE_VA)
        self.assertEqual(trail.status(self.patched), "applied")

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
                                          "scheme_labels", "kick_rules", "widescreen", "overtime", "team_column")}
        cls.patched, _receipt = tt._apply_all(seed, None, **flags, arc_table=False, kick_power=False, penalties="nfl", uniform_choice="choice", kick_laces=True, franchise_practice=True, prospect_names="modern", player_star=True, dynamic_kickoff=True)
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        cls.patched, cls.pools_receipt = pools.apply(
            cls.patched, roster_has_olb=bool(getattr(cls, "reverse_owners", False)))
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
        # Camera's code and immutable Broadcast record are in the full union. No
        # allocation may be sealed by the earlier protected dispatcher pass.
        cls.patched, cls.music_receipt = compose(cls.patched, read_option_diagnostic=True, reverse=getattr(cls, "reverse_owners", False), scaleout=getattr(cls, "scaleout", False))
        from mod_editor.core import nfl2k5_seven_on_seven as seven
        if seven.status(cls.patched) != "applied" or seven.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("7-on-7 v2 missing from the complete owner union")
        if getattr(cls, "reverse_owners", False):
            cls.patched, cls.pools_receipt = pools.apply(cls.patched, roster_has_olb=False)
        if pools.filter_list_status(cls.patched) != "applied":
            raise AssertionError("empty OLB selectors survived complete composition")
        from mod_editor.core import nfl2k5_espn25_rosters as espn25
        if espn25.xbe_status(cls.patched) != "applied" or espn25.apply_xbe(cls.patched)[0] != cls.patched:
            raise AssertionError("Historic team reload repair missing from the complete owner union")
        from mod_editor.core import nfl2k5_deep_zone as deep_zone
        if deep_zone.status(cls.patched) != "applied" or deep_zone.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Deep-zone owner failed gate composition/replay")
        from mod_editor.core import nfl2k5_cpu_money_downs as money_downs
        if money_downs.status(cls.patched) != "applied" or money_downs.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("CPU money downs missing from the complete owner union")
        from mod_editor.core import nfl2k5_franchise_edit_player as edit_player
        if edit_player.status(cls.patched) != "applied" or edit_player.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Contracts Edit Player did not compose/replay")
        from mod_editor.core import nfl2k5_coverage_trail as coverage_trail
        if coverage_trail.status(cls.patched) != "applied" or coverage_trail.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Coverage trail missing from the complete owner union")
        from mod_editor.core import nfl2k5_playbook_pair as playbook_pair
        if playbook_pair.status(cls.patched) != "applied" or playbook_pair.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Playbook pair missing from the complete owner union")
        from mod_editor.core import nfl2k5_weekly_prep as weekly_prep
        if weekly_prep.status(cls.patched) != "applied" or weekly_prep.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Weekly prep missing from the complete owner union")
        from mod_editor.core import nfl2k5_franchise_autosave as autosave
        if autosave.status(cls.patched) != "applied" or autosave.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Franchise Auto Save missing from the complete owner union")
        from mod_editor.core import nfl2k5_camera as camera
        if camera.status(cls.patched) != "applied" or camera.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Paired Standard/Far framing and pass limits missing from complete owner union")
        from mod_editor.core import nfl2k5_animation_xbe as animation_xbe
        if animation_xbe.status(cls.patched) != "applied":
            raise AssertionError("Embedded animation owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_guardian_overlay as guardian
        if guardian.status(cls.patched) != "applied":
            raise AssertionError("Guardian overlay missing from the composed XBE")
        from mod_editor.core import nfl2k5_momentum as momentum
        settings = momentum.read_settings(cls.patched)
        if not settings.get("momentum_collisions") or settings.get("momentum_collision_level") != 100:
            raise AssertionError("collision momentum missing from the composed XBE")
        from mod_editor.core import nfl2k5_my_career_mode as my_career, nfl2k5_crib_reclaim as crib_reclaim
        if my_career.status(cls.patched) != "applied" or crib_reclaim.status(cls.patched) != "applied":
            raise AssertionError("MyCareer or Crib movie cut missing from the composed XBE")
        m3_state = [a for a in my_career.space.layout(cls.patched)["allocations"] if a["owner"] == my_career.EXTRA_OWNER]
        if len(m3_state) != 1 or (m3_state[0]["kind"], m3_state[0]["va"], m3_state[0]["size"]) != ("data", my_career.EXTRA_VA, 4096):
            raise AssertionError("MyCareer M3 state missing from the complete owner union")
        from mod_editor.core import nfl2k5_calendar_engine as calendar
        if calendar.status(cls.patched) != "applied":
            raise AssertionError("calendar owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        if defensive_try.status(cls.patched) != "applied":
            raise AssertionError("defensive conversion stat extension missing from the composed XBE")
        defensive_try._stats_sites(cls.patched)  # both named RX/RO reservations
        from mod_editor.core import nfl2k5_read_option_runtime as read_option
        if read_option.status(cls.patched) != "applied":
            raise AssertionError("read option owner missing from the composed XBE")
        if read_option.read_settings(cls.patched)["model_version"] != 5:
            raise AssertionError("read option engagement diagnostic missing from the composed XBE")
        from mod_editor.core import nfl2k5_franchise_2026 as franchise_2026
        if franchise_2026.status(cls.patched) != "applied":
            raise AssertionError("franchise rule proof kernel missing from composed XBE")
        # The owner is dormant: composition is not native franchise enforcement.
        if franchise_2026.RUNTIME_READY:
            raise AssertionError("update the franchise shipping-gate evidence before enabling")
        from mod_editor.core import nfl2k5_senior_bowl as senior_bowl
        if senior_bowl.status(cls.patched) != "applied":
            raise AssertionError("Senior Bowl dormant components missing from the composed XBE")
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
        if abilities.read_settings(cls.patched)["model_version"] != 2:
            raise AssertionError("abilities v2 effects missing from the composed XBE")
        from mod_editor.core import nfl2k5_qb_spy_runtime as qb_spy
        if qb_spy.status(cls.patched) != "applied":
            raise AssertionError("QB spy owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_screen_hooks as screen_hooks
        if screen_hooks.status(cls.patched) != "applied":
            raise AssertionError("screen hooks owner missing from the composed XBE")
            raise AssertionError("Zone/man/rush QB spy owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_modern_naming as modern_naming
        cls.patched, _ = modern_naming.apply(cls.patched)
        if modern_naming.status(cls.patched) != "applied":
            raise AssertionError("Modern mode text missing from the composed XBE")
        from mod_editor.core import nfl2k5_roster_arena_growth as arena_growth
        if arena_growth.status(cls.patched) != "applied":
            raise AssertionError("arena growth missing from the composed XBE")
        from mod_editor.core import nfl2k5_modern_naming as modern_naming
        from mod_editor.core import nfl2k5_screen_hooks as screen
        # This audit allocates nothing. It verifies that neither deferred CB
        # tier has displaced Spy's recognized hooks or the reaction owners.
        from mod_editor.core import nfl2k5_zone_facing as zone_facing
        cls.zone_evidence = zone_facing.assess(cls.patched)
        if cls.zone_evidence["states"]["initial_drop"] != "applied":
            raise AssertionError("Initial zone-drop owner missing from tier evidence")
        from mod_editor.core import nfl2k5_widescreen as wide
        if wide.status(cls.patched) != "applied" or wide.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("widescreen v3 sites/context did not compose and replay")
        from tests.nfl2k5_allocator_stack import manifest_for_allocated_union
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        release_manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), XbeImage(cls.retail))
        cls.manifest = manifest_for_allocated_union(release_manifest, cls.retail, cls.patched)
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

    def test_olb_filter_tables_are_pinned_data_edits_in_existing_owner(self):
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_probowl_order as probowl
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        sites = pools.filter_list_sites(probowl_ordered=probowl.status(self.patched) == "applied")
        edits = [e for e in self.pools_receipt["edits"] if e["group"] == "filter_lists"]
        self.assertEqual(len(edits), 16)
        for site, edit in zip(sites, edits):
            self.assertEqual(image.section(site.va).name, ".rdata")
            self.assertEqual(image.section(site.va).flags, XbeImage(self.retail).section(site.va).flags)
            self.assertEqual(image.read(site.va, site.size), site.after)
            self.assertEqual(edit["after"], site.after.hex())
            self.assertEqual(site.after[-8:], bytes(8))
        self.assertEqual(pools.apply(self.patched, roster_has_olb=False)[0], self.patched)

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
        # The Crib list repair moves the loop entry from 0x32A160 to 0x32A159
        # and retargets its backward branch at 0x32A24F. Treat those two edits
        # as one completely pinned function, including its retained bytes.
        # Otherwise the displaced internal back edge appears external to the
        # first changed run. Every genuinely external entry is still checked.
        from mod_editor.core import nfl2k5_jukebox_list as jukebox
        if jukebox.status(self.patched) == 'applied':
            self.assertEqual(jukebox.status(self.retail), 'retail')
            lo, hi = jukebox.FUNCTION_VA, jukebox.FUNCTION_VA + jukebox.FUNCTION_SIZE
            ranges = {(a, b) for a, b in ranges if not (a < hi and b > lo)}
            ranges.add((lo, hi))
        # Scorebar v3 replaces complete pinned live spans. Split adjacent
        # callbacks at their independently referenced entries, and include
        # retained byte islands so their displaced branches remain internal.
        from mod_editor.core import nfl2k5_scorebar_v3 as v3
        spans=[(va,va+len(old),old,new) for va,old,new,_ in v3.xbe_specs() if va<0x4e0000]
        corrected=set()
        for a,b in ranges:
            cursor=a
            for lo,hi,old,new in sorted(spans):
                if a<hi and b>lo:
                    self.assertEqual(self.retail[lo-BASE:hi-BASE],old)
                    self.assertEqual(self.patched[lo-BASE:hi-BASE],new)
                    if cursor<lo: corrected.add((cursor,lo))
                    corrected.add((lo,hi))
                    cursor=max(cursor,hi)
            if cursor<b: corrected.add((cursor,b))
        return sorted((a,b) for a,b in corrected if b-a>=CAVE_MIN)

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
        manifest = self.manifest
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
        manifest = self.manifest
        for start in (0x1AFDF0, 0x28B410, 0x1D82D0, 0x325E70, 0x2979F0, 0xB4A60, 0x2BA840):
            self.assertTrue(manifest.overlaps(start, start + 1), hex(start))

    def test_practice_squad_spans_preserve_stack_owners(self) -> None:
        from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff
        from mod_editor.core import nfl2k5_practice_squad as ps
        from mod_editor.core import nfl2k5_roster_arena_growth as arena
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        retail = XbeImage(self.retail)
        stack = XbeImage(self.stack)
        manifest = ReservationManifest.load(Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), retail)
        # The larger-roster owner deliberately delegates these stable PS entry
        # points to its sealed RX allocation. Prove each exact bridge, rather
        # than treating the entire original owner's cave as shared/free space.
        self.assertEqual(arena.status(self.patched), 'applied')
        installed = XbeImage(self.patched)
        bridges = {va: (name, before, after)
                   for name, va, before, after in arena.sites(arena.allocation(self.patched)['va'])
                   if name in arena.BRIDGES}
        for start, size, _ in ps.CAVES:
            overlaps = manifest.overlaps(start, start + size, exclude_owner='nfl2k5_practice_squad')
            for hit in overlaps:
                self.assertEqual(hit.detail.split(':', 1)[0], arena.OWNER, hit)
                matching = [(va, name, before, after) for va, (name, before, after) in bridges.items()
                            if va <= hit.start < hit.end <= va + len(before)]
                self.assertEqual(len(matching), 1, hit)
                va, _name, before, after = matching[0]
                self.assertEqual(len(before), 5)
                self.assertEqual(installed.read(va, len(after)), after)
            for va, (name, before, _after) in bridges.items():
                if start <= va < start + size:
                    self.assertTrue(any(hit.start == va and hit.end == va + len(before)
                                        and hit.detail == f'{arena.OWNER}: declared edit: {name}'
                                        for hit in overlaps), name)
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
        manifest = self.manifest
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
        manifest = self.manifest
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
        manifest = self.manifest
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

    def test_kickoff_contact_readiness_and_pose_guards_are_complete_owned_hooks(self) -> None:
        from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        image = XbeImage(self.patched)
        manifest = self.manifest
        code, data = relocated._sites(self.patched)
        expected, labels = relocated.code_for(kickoff._settings(), code["va"], data["va"])
        self.assertEqual(image.read(code["va"], code["size"]), expected)
        for name in ("eligibility", "separation", "ready", "head_pose", "block_tick"):
            va, original = kickoff.HOOKS[name]
            overlaps = manifest.overlaps(va, va + len(original))
            self.assertTrue(overlaps)
            self.assertTrue(all(r.detail.split(":", 1)[0] in
                                ("nfl2k5_dynamic_kickoff", relocated.OWNER) for r in overlaps))
            self.assertEqual(sum(i.size for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(original, va)),
                             len(original))
            self.assertEqual(image.read(va, len(original)), kickoff._hook_bytes(name, labels))

    def test_momentum_owns_named_children_and_pinned_live_spans_without_new_caves(self) -> None:
        from mod_editor.core import nfl2k5_momentum as momentum
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = self.manifest
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
        manifest = self.manifest
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
        manifest = self.manifest
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
        manifest = self.manifest
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

    def test_read_option_hook_has_no_interior_entry_or_foreign_owner(self) -> None:
        from mod_editor.core import nfl2k5_read_option_runtime as read_option
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = self.manifest
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, old) in read_option.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(old, va)), len(old), name)
            self.assertEqual(manifest.overlaps(va, va+len(old), exclude_owner=read_option.OWNER), [])
            # Complete byte-granular direct E8/E9 candidates, including bytes
            # that a linear instruction sweep might misclassify as data.
            for target in range(va+1, va+len(old)):
                self.assertFalse(self.targets.get(target, []), hex(target))
    def test_senior_bowl_dormant_components_claim_only_allocator_children(self):
        from mod_editor.core import nfl2k5_senior_bowl as bowl, nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        self.assertEqual(bowl.status(self.patched), "applied")
        spans = [r for r in space.reservations(self.patched) if r["owner"] == bowl.OWNER]
        self.assertEqual(len(spans), 2)
        for row in spans:
            self.assertEqual(row["parent_owner"], space.OWNER)
            self.assertGreaterEqual(int(row["start"], 0), space.SCALE_RUNS[0][1])
            self.assertNotEqual(image.section(int(row["start"], 0)).name, ".text")
        self.assertFalse(bowl.NATIVE_EVENT_AVAILABLE)

    def test_qb_spy_hooks_are_complete_instructions_and_have_no_foreign_owner(self) -> None:
        from mod_editor.core import nfl2k5_qb_spy_runtime as spy, nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        image = XbeImage(self.patched)
        manifest = self.manifest
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, old) in spy.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(old, va)), len(old), name)
            self.assertEqual(manifest.overlaps(va, va+len(old), exclude_owner=spy.OWNER), [], name)
        for row in spy.reservations(self.patched):
            if int(row["start"], 0) >= space.CODE_VA:
                self.assertEqual(row["parent_owner"], space.OWNER)
        self.assertEqual(spy.status(self.patched), "applied")


    def test_guardian_has_complete_live_hooks_and_only_owned_grown_code(self):
        from mod_editor.core import nfl2k5_guardian_overlay as guardian, nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = self.manifest
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, before) in guardian.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(before, va)), len(before), name)
            self.assertEqual(manifest.overlaps(va, va+len(before), exclude_owner=guardian.OWNER), [], name)
        for row in guardian.reservations(self.patched):
            if int(row["start"], 0) >= space.CODE_VA:
                self.assertEqual(row["parent_owner"], space.OWNER)

    def test_screen_hooks_have_complete_spans_and_no_interior_or_foreign_entry(self) -> None:
        from mod_editor.core import nfl2k5_screen_hooks as screen
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        manifest = self.manifest
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, old) in screen.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(old, va)), len(old), name)
            self.assertEqual(manifest.overlaps(va, va+len(old), exclude_owner=screen.OWNER), [])
            self.assertTrue(any(r.detail.startswith(screen.OWNER+":") for r in manifest.overlaps(va, va+len(old))))
            for target in range(va+1, va+len(old)):
                self.assertFalse(self.targets.get(target, []), hex(target))
        code = screen.allocation(self.patched)
        parents = manifest.overlaps(code["va"], code["va"]+code["size"], exclude_owner=screen.OWNER)
        self.assertTrue(parents)
        self.assertTrue(all(r.detail.split(":", 1)[0] == "nfl2k5_xbe_space" for r in parents), parents)
        self.assertTrue(any(r.start == code["va"] and r.end == code["va"]+code["size"]
                            and r.detail == screen.OWNER+": named code allocation"
                            for r in manifest.overlaps(code["va"], code["va"]+code["size"])))

    def test_camera_hooks_are_complete_and_only_named_rx_is_allocated(self):
        from mod_editor.core import nfl2k5_camera as camera, nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        image = XbeImage(self.patched)
        for name, (va, before) in camera.HOOKS.items():
            self.assertEqual(sum(i.size for i in md.disasm(before, va)), len(before), name)
            after = camera._read(self.patched, va, len(before))
            self.assertEqual(sum(i.size for i in md.disasm(after, va)), len(after), name)
            self.assertEqual(self.manifest.overlaps(va, va+len(before), exclude_owner=camera.OWNER), [])
            for target in range(va+1, va+len(before)):
                self.assertFalse(self.targets.get(target, []), hex(target))
        allocation = camera.allocation(self.patched)
        self.assertEqual((allocation['kind'], allocation['size']), ('code', camera.CODE_SIZE))
        self.assertFalse(image.section(allocation['va']).writable)
        self.assertEqual({va: refs for va, refs in self.targets.items()
                          if allocation['va'] <= va < allocation['va']+camera.CODE_SIZE}, {})
        descriptor = camera.allocation(self.patched, 'read_only')
        self.assertFalse(image.section(descriptor['va']).writable)
        self.assertFalse(image.section(descriptor['va']).executable)
        self.assertEqual(camera._read(self.patched, descriptor['va'], descriptor['size']),
                         camera.broadcast_records(allocation['va']))
        self.assertEqual(camera.status(self.patched), 'applied')
        # Existing descriptors and complete instruction edits allocate no
        # retail cave. Check the expanded v3 edit list against every owner.
        for reservation in camera.reservations(self.patched):
            if reservation['basis'].startswith('declared edit:'):
                self.assertEqual(self.manifest.overlaps(int(reservation['start'],0),
                    int(reservation['end'],0),exclude_owner=camera.OWNER), [], reservation)

    def test_franchise_autosave_hooks_have_no_interior_entry_or_foreign_owner(self):
        from mod_editor.core import nfl2k5_franchise_autosave as autosave
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        owned = autosave.allocations(self.patched)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, va, original, _ in autosave.HOOKS:
            before = bytes.fromhex(original)
            self.assertEqual(sum(i.size for i in md.disasm(before, va)), len(before), name)
            self.assertEqual(sum(i.size for i in md.disasm(image.read(va, len(before)), va)), len(before), name)
            for target in range(va+1, va+len(before)):
                self.assertFalse(self.targets.get(target, []), (name, hex(target)))
        for name, va, before, _ in autosave.sites(owned['code']['va'], owned['read_only']['va']):
            self.assertEqual(self.manifest.overlaps(va, va+len(before), exclude_owner=autosave.OWNER), [], name)
            self.assertTrue(self.manifest.overlaps(va, va+len(before)), name)
        for allocation in owned.values():
            va, end = allocation['va'], allocation['va']+allocation['size']
            self.assertEqual({at: refs for at, refs in self.targets.items() if va <= at < end}, {})
            self.assertTrue(all(r.detail.split(':', 1)[0] == 'nfl2k5_xbe_space'
                                for r in self.manifest.overlaps(va, end, exclude_owner=autosave.OWNER)))

    def test_playbook_pair_hooks_and_tables_have_exclusive_ownership(self):
        from mod_editor.core import nfl2k5_playbook_pair as pair
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        owned = pair.allocations(self.patched)
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, va, original, _ in pair.HOOKS:
            before = bytes.fromhex(original)
            self.assertEqual(sum(i.size for i in md.disasm(before, va)), len(before), name)
            self.assertEqual(sum(i.size for i in md.disasm(image.read(va,len(before)), va)), len(before), name)
            for target in range(va+1, va+len(before)):
                self.assertFalse(self.targets.get(target, []), (name, hex(target)))
        for name, va, before, _ in pair.sites(owned['code']['va'],owned['read_only']['va']):
            self.assertEqual(self.manifest.overlaps(va,va+len(before),exclude_owner=pair.OWNER), [], name)
            self.assertTrue(self.manifest.overlaps(va,va+len(before)), name)
        for allocation in owned.values():
            va, end = allocation['va'], allocation['va']+allocation['size']
            self.assertEqual({at: refs for at, refs in self.targets.items() if va <= at < end}, {})
            self.assertTrue(all(r.detail.split(':',1)[0] == 'nfl2k5_xbe_space'
                                for r in self.manifest.overlaps(va,end,exclude_owner=pair.OWNER)))

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
                from mod_editor.core import nfl2k5_scorebar_v3 as v3
                if va in (v3.VISIBILITY_VA, 0xfc010, 0xfc030, 0xfbe30, 0xfc285, 0xfc305):
                    # Complete live instruction spans, never an allocation in
                    # padding. Every new branch has a native or owned target.
                    offset=scorebug.layout.sbpos.va_to_off(retail,va)
                    self.assertEqual(retail[offset:offset+len(old)],old)
                    self.assertEqual(len(old),len(new))
                    insns=list(md.disasm(new,va))
                    self.assertEqual(sum(i.size for i in insns),len(new))
                    native={0xabe90,0x30ab0,0x30f20,0x68d70,0x68dc0,0x61c50,0x61c60,0xfbb10,0xfbe4e,0x4a400}
                    starts={i.address for i in md.disasm(v3.VISIBILITY_CODE,v3.VISIBILITY_VA)}
                    starts.update(i.address for i in insns)
                    for ins in insns:
                        if ins.mnemonic.startswith('j') or ins.mnemonic=='call':
                            self.assertTrue(ins.op_str.startswith('0x'),ins.op_str)
                            target=int(ins.op_str,16)
                            self.assertTrue(target in starts or target in native,(hex(ins.address),hex(target)))
                    continue
                if va == 0xfc0a6:
                    # This is a replacement of live, guarded quarter cases,
                    # not allocation in padding or a new code cave.
                    self.assertEqual(len(new),48)
                    insns=list(md.disasm(new,va))
                    self.assertEqual(sum(i.size for i in insns),48)
                    self.assertTrue(all(i.mnemonic in ("mov","jmp","call","pop","nop") for i in insns))
                    targets={int(i.op_str,16) for i in insns if i.mnemonic in ("jmp","call")}
                    self.assertEqual(targets,{0xfc0c2,0x30ab0,0x30f20})
                    continue
                if va in (0xfc0f4,0xfc0f8,0xfc0fc):
                    self.assertEqual(len(new),4)
                    target=struct.unpack('<I',new)[0]
                    self.assertIn(target,(0xfc0ad,0xfc0b4,0xfc0bb))
                    self.assertEqual(patched[scorebug.layout.sbpos.va_to_off(patched,target)],0xba)
                    continue
                if va in (0xfc028,0xfc048):
                    insns=list(md.disasm(new,va))
                    self.assertEqual([(i.mnemonic,i.op_str,i.size) for i in insns],[("jmp","0x30f20",5)])
                    continue
                self.assertLess(len(new),CAVE_MIN,label)
                if va == 0xfbe43:
                    # In-place MOV operand, not standalone code or a cave.
                    self.assertEqual(old,struct.pack("<I",0xe6c438))
                    self.assertEqual(new,struct.pack("<I",0xe6c43a))
                    offset=scorebug.layout.sbpos.va_to_off(patched,va-1)
                    insns=list(md.disasm(patched[offset:offset+5],va-1))
                    self.assertEqual([(i.mnemonic,i.op_str,i.size) for i in insns],
                                     [("mov","edx, 0xe6c43a",5)])
                    literal=scorebug.layout.sbpos.va_to_off(retail,0xe6c438)
                    self.assertEqual(retail[literal:literal+12],":%02d\0".encode("utf-16le"))
                    self.assertEqual(patched[literal:literal+12],retail[literal:literal+12])
                    continue
                insns=list(md.disasm(new,va))
                self.assertEqual(sum(i.size for i in insns),len(new),label)
                self.assertTrue(all(i.mnemonic in ("nop","fadd") for i in insns),label)
        self.assertEqual(scorebug.xbe_status(patched),"applied")


class ReverseOwnerOrderTests(CaveReferenceTests):
    """Run every gate against the same complete union installed in reverse."""
    reverse_owners = True

    def test_both_installation_orders_are_byte_identical(self):
        from tests.nfl2k5_allocator_stack import compose
        from mod_editor.core import nfl2k5_modern_naming as modern_naming
        from mod_editor.core import nfl2k5_position_pools as pools
        forward = pools.apply(self.before_allocator, roster_has_olb=False)[0]
        self.assertEqual(modern_naming.apply(compose(forward, read_option_diagnostic=True, scaleout=getattr(self, "scaleout", False))[0])[0], self.patched)


class ScaleoutOwnerTests(CaveReferenceTests):
    """All existing owner gates against the v3 page map."""
    scaleout = True


class ScaleoutReverseOwnerTests(ReverseOwnerOrderTests):
    scaleout = True


if __name__ == "__main__":
    unittest.main()
