"""Bounded native CPU proofs. No game boot, rendered play or catch witness.

Optional --write-evidence emits source-free numerical replay results after
the complete suite succeeds. Retail archive reads use indexed descriptors.
"""
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_money_downs as patch
from mod_editor.core import nfl2k5_playbook_inspector as book
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.mod_editor.test_nfl2k5_screen_timing import retail_books
from tests.nfl2k5_cpu_money_downs_native import Machine, uc, x86

EVIDENCE = {"experimental": True, "runtime_witnessed": False,
            "scope": "Bounded USA native instructions with supplied game state, no disc build or played-game evidence"}


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.payloads = {level: patch.apply(cls.retail, level=level)[0] for level in patch.LEVELS}
        EVIDENCE["retail_sha256"] = hashlib.sha256(cls.retail).hexdigest()
        EVIDENCE["owner_code_bytes"] = len(patch.assembly.CODE)

    def machine(self, level="modern"):
        return Machine(self.payloads[level])

    def test_all_policy_cells_native_in_both_directions(self):
        contexts = (
            dict(quarter=1, seconds=600, score_margin=0),
            dict(quarter=2, seconds=30, score_margin=0),
            dict(quarter=4, seconds=301, score_margin=9),
            dict(quarter=4, seconds=300, score_margin=9),
            dict(quarter=4, seconds=300, score_margin=-9),
            dict(quarter=4, seconds=120, score_margin=-4),
            dict(quarter=4, seconds=120, score_margin=-3),
        )
        distances = (.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 20)
        evidence = []
        for level in patch.LEVELS[1:]:
            m = self.machine(level)
            for direction, own, context in itertools.product((-1, 1), (10, 30, 50, 70, 87.5, 97.5), contexts):
                state = dict(context, own_yard=own)
                accepted = []
                for distance in distances:
                    result = m.policy(**state, distance=distance, direction=direction)
                    self.assertEqual(result, int(patch.decision(level=level, **state, distance=distance) == "go"),
                                     (level, direction, state, distance))
                    self.assertTrue(all(m.STACK-160 <= a < m.STACK for a, _ in m.writes), m.writes)
                    if result:
                        accepted.append(distance)
                evidence.append(dict(state, level=level, direction=direction, accepted_distances=accepted))
        EVIDENCE["policy"] = dict(cases=len(evidence)*len(distances), distances=distances, cells=evidence)

    def test_policy_boundaries_and_controls(self):
        m = self.machine()
        for own, distance, direction in itertools.product(
                (0, 19.99, 20, 39.99, 40, 59.99, 60, 79.99, 80, 94.99, 95, 100),
                (1, 1.01, 2, 2.01, 3, 3.01), (-1, 1)):
            self.assertEqual(m.policy(own_yard=own, distance=distance, direction=direction),
                             int(patch.decision(own_yard=own, distance=distance) == "go"), (own, distance, direction))
        for state in ({"down": 1}, {"down": 2}, {"down": 3}, {"cpu": False}, {"phase": 3},
                      {"quarter": 0}, {"quarter": 5}, {"distance": 0}, {"distance": 21},
                      {"distance": float("nan")}, {"own_yard": float("nan")},
                      {"own_yard": -1}, {"own_yard": 101}, {"seconds": 10001},
                      {"direction": 0}, {"direction": 2}, {"direction": float("nan")}):
            self.assertEqual(m.policy(**state), 0, state)
        for seconds, margin in itertools.product((30, 120, 121, 300, 301), (-10, -9, -4, -3, 0, 8, 9)):
            state = dict(quarter=4, seconds=seconds, score_margin=margin, distance=3)
            self.assertEqual(m.policy(**state), int(patch.decision(**state) == "go"), state)

    def test_native_punt_field_goal_go_and_difficulty_presets(self):
        states = [dict(own_yard=50, distance=2), dict(own_yard=70, distance=2),
                  dict(own_yard=30, distance=7),
                  dict(own_yard=80, distance=2, quarter=4, seconds=100, score_margin=-3)]
        expected = {"retail": [17, 19, 17, 19], "modern": [5, 5, 17, 19], "aggressive": [5, 5, 17, 19]}
        rows = []
        for level in patch.LEVELS:
            m = self.machine(level)
            m.supply_fg_range(40)
            for difficulty in range(4):
                sliders = m.difficulty(difficulty)
                self.assertEqual(sliders, (difficulty*.25, 1-difficulty*.25))
                for direction in (-1, 1):
                    results = [m.category(**state, direction=direction) for state in states]
                    self.assertEqual(results, expected[level], (level, difficulty, direction))
                    rows.append(dict(level=level, difficulty=difficulty, cpu_human_sliders=sliders,
                                     direction=direction, categories=results))
        EVIDENCE["native_category"] = dict(states=states, rows=rows, kicker_range_yards=40,
            substituted_helpers=["18B120 kicker/roster-derived range only"],
            difficulty_limit="Native preset writer executed; fixed roster-derived range. This does not prove difficulty independence of all upstream player state.")

    def test_loaded_primary_classifier_matches_bounded_book_in_both_buffers(self):
        resources = retail_books()
        resource = resources[307]
        parsed = book.parse_playbook_resource(resource)
        m = self.machine()
        supported, checked = set(), 0
        for buffer, mirrored in itertools.product((0, 1), (False, True)):
            m.load_book(resource, buffer)
            for formation in parsed.formations:
                for link in formation.play_links:
                    play = link.play_index
                    want = patch.primary_depth_cm(resource[32:], play, formation.index, mirrored=mirrored)
                    got = m.primary_loaded(play, formation.index, buffer=buffer, mirrored=mirrored)
                    self.assertEqual(got, want, (buffer, mirrored, play, formation.index))
                    checked += 1
                    if got is not None:
                        supported.add((play, formation.index))
        self.assertGreater(len(supported), 0)
        EVIDENCE["classifier"] = dict(archive_index=307, resource_sha256=hashlib.sha256(resource).hexdigest(),
                                      comparisons=checked, supported_formation_play_links=len(supported))
        coverage = []
        for index, raw in resources.items():
            parsed_book = book.parse_playbook_resource(raw)
            links = {(link.play_index, formation.index) for formation in parsed_book.formations
                     for link in formation.play_links}
            count = sum(patch.primary_depth_cm(raw[32:], *row) is not None for row in links)
            coverage.append(dict(archive_index=index, book=parsed_book.book_name,
                resource_sha256=hashlib.sha256(raw).hexdigest(),
                distinct_formation_play_links=len(links), supported_links=count))
        EVIDENCE["book_coverage"] = dict(scope="Host grammar census; native relocation comparison above is ARI only",
                                         books=coverage)

    def test_classifier_refuses_misaligned_foreign_and_truncated_descriptors(self):
        m = self.machine()
        m.load_book(retail_books()[307])
        base = 0xB75A40
        play = base+0x33FC+61*96
        form = base+0x134+8*180
        m.u32(m.FRAME+8, form)
        m.u32(m.FRAME-0x28, 0)
        for address in (0, base, play+1, base+0x33FC+270*96, 0xB75A40+2*0x13390+0x33FC):
            m.run(m.owner+patch.assembly.LABELS["primary_depth"], esi=address, ebp=m.FRAME)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0xFFFF8000)
        for pointer, count in ((0, 2), (base+0x9ADC+1, 2), (base+0x9ADC+3500*8-8, 2),
                               (base+0x9ADC, 1)):
            m.u32(play+8, count)
            m.u32(play+12, pointer)
            self.assertIsNone(m.primary_loaded(61, 8))
        self.assertIsNone(patch.primary_depth_cm(bytes(100), 0, 0))

    def test_native_play_selection_and_seeded_samples_at_three_markers(self):
        resource = retail_books()[307]
        parsed = book.parse_playbook_resource(resource)
        names = {p.index: p.name for p in parsed.plays}
        evidence, mass = [], {}
        for level in patch.LEVELS:
            m = self.machine(level)
            m.prepare_selection(resource)
            for marker, down, direction in itertools.product((3, 7, 12), (3, 4), (-1, 1)):
                rows = m.selection_weights(distance=marker, down=down, direction=direction)
                self.assertEqual(len(rows), 12)
                qualified = []
                for row in rows:
                    depth = patch.primary_depth_cm(resource[32:], row["play_index"], 8, mirrored=row["mirrored"])
                    qualified.append(depth is not None and depth >= marker*91.44)
                total = sum(r["weight"]**3 for r in rows)
                reach_mass = sum(r["weight"]**3 for r, good in zip(rows, qualified) if good)/total
                key = (level, marker)
                if key in mass:
                    self.assertAlmostEqual(mass[key], reach_mass, places=6)
                    continue
                mass[key] = reach_mass
                counts = Counter(m.sample_weights(rows, seed) for seed in range(256))
                self.assertTrue(all(0 <= index < len(rows) for index in counts))
                reaches = sum(counts[i] for i, good in enumerate(qualified) if good)
                evidence.append(dict(level=level, marker_yards=marker, down=down,
                    native_reach_probability=reach_mass, reaches_in_256=reaches,
                    candidates=[dict(row, name=names[row["play_index"]], reaches=qualified[i], samples=counts[i])
                                for i, row in enumerate(rows)]))
        for marker in (3, 7, 12):
            self.assertLess(mass[("retail", marker)], mass[("modern", marker)])
            self.assertLess(mass[("modern", marker)], mass[("aggressive", marker)])
        EVIDENCE["play_selection"] = dict(formation=8, category=4, archive_index=307,
            native_selector="2096A0 through candidate normalization, then 203440 cubed-weight roulette",
            supplied_state="Zero tendency/history tables; fixed formation and category; native loader and validator",
            direction_down_controls="All markers, both directions, downs 3 and 4", samples=evidence)

    def test_play_hook_preserves_abi_and_human_early_down_weights(self):
        m = self.machine()
        m.load_book(retail_books()[307])
        for down, cpu in itertools.product((1, 2, 3, 4), (False, True)):
            m.configure(down=down, cpu=cpu, distance=7)
            for i in range(8):
                m.uc.reg_write(getattr(x86, f"UC_X86_REG_XMM{i}"), 0x123456789ABCDEF0+i)
            weight = m.play_weight(61, 8)
            self.assertEqual(weight, 1.5 if cpu and down in (3, 4) else 1)
            for name, value in dict(ECX=m.P, EDX=0x2345, EBX=0x3456, ESI=0xB75A40+0x33FC+61*96,
                                    EDI=0x5678, EBP=m.FRAME, ESP=m.STACK, EFLAGS=0x202).items():
                self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_"+name)), value, name)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0x37F)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPTAG), 0xFFFF)
            for i in range(8):
                self.assertEqual(m.uc.reg_read(getattr(x86, f"UC_X86_REG_XMM{i}")), 0x123456789ABCDEF0+i)
            self.assertTrue(all(m.STACK-200 <= a < m.STACK or a == m.FRAME-0x18 for a, _ in m.writes))
        m.configure(distance=20)
        self.assertEqual(m.play_weight(61, 8), 1)

    def test_native_targets_retain_catchability_and_human_controls(self):
        rows = []
        for level in patch.LEVELS:
            m = self.machine(level)
            for down, marker, direction in itertools.product((3, 4), (3, 7, 12), (-1, 1)):
                candidates = [dict(yards=marker-1, score=.8), dict(yards=marker, score=.7)]
                winner = m.targets(candidates, down=down, distance=marker, direction=direction)
                self.assertEqual(winner, 0 if level == "retail" else 1)
                rows.append(dict(level=level, down=down, marker=marker, direction=direction, winner=winner))
                for bad in (dict(available=False), dict(viable=False), dict(score=.49)):
                    self.assertEqual(m.targets([candidates[0], dict(candidates[1], **bad)], distance=marker,
                                               down=down, direction=direction), 0)
                self.assertEqual(m.targets(candidates, distance=marker, human_passer=True), 0)
                self.assertEqual(m.targets(candidates, distance=marker, cpu=False), 0)
                for early in (1, 2):
                    self.assertEqual(m.targets(candidates, distance=marker, down=early), 0)
            self.assertIsNone(m.targets([]))
            self.assertIsNone(m.targets([dict(yards=15, score=.1)]))
            self.assertEqual(m.targets([dict(yards=6, score=1.3), dict(yards=7, score=.7)], distance=7), 0)
        EVIDENCE["target_selection"] = dict(rows=rows,
            native_routine="1985E0 including native attribute helper 17AE80; no substituted helpers",
            supplied_state="Viability and projected catch scores/locations; trajectory generation, actual throws and catches are not replayed",
            controls=["Unavailable", "Nonviable", "Below native threshold", "Human team", "Human passer",
                      "Downs 1 and 2", "No candidates", "No viable candidates", "Much stronger short target"])


if __name__ == "__main__":
    output = None
    if "--write-evidence" in sys.argv:
        index = sys.argv.index("--write-evidence")
        output = Path(sys.argv[index+1]).resolve()
        del sys.argv[index:index+2]
    result = unittest.main(exit=False).result
    if output and result.wasSuccessful() and not result.skipped:
        if not {"policy", "classifier", "book_coverage", "native_category", "play_selection", "target_selection"} <= EVIDENCE.keys():
            raise SystemExit("Run the complete suite to write the full replay evidence")
        output.write_text(json.dumps(EVIDENCE, indent=2)+"\n", encoding="utf-8")
        print(f"Wrote bounded replay evidence: {output}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
