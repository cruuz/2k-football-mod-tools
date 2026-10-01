"""Beta 76 (job f1): the1wam's lineman rating composes with the generic in-game MyCareer.

The lineman rating (``nfl2k5_lineman_rating``) retargets the one blend call inside the native
overall dispatch at 0x246D60 to a wrapper at 0x1D2400. The generic MyCareer owner hashes the native
player-rating context 0x246060..0x246DE1 (``nfl2k5_my_career_mode.GUARDS``), so it read that hook as
foreign: it refused to install on a lineman executable ("foreign/mixed generic MyCareer") and an
installed MyCareer stopped recognising itself once the lineman patch landed, which took every
companion that validates MyCareer down with it. ``check_context`` now accepts the hook only after
the lineman owner reads applied, and restores its exact bytes in the private hash view, the same
pattern as the defensive try, dynamic kickoff, overtime and kick rules companions.

MyCareer's prospect tiers (74/70/64/59) are reached by an in-game sweep over the native overall
(``tools/mycareer_mode/runtime.c`` ``mode_created`` calls 0x246D90), so on a lineman executable the
created C/G/T lands on the adjusted overall. The retail-backed classes run that sweep in emulation
and prove the Python model of the adjusted overall against the executed routine. The Studio's
prepared-save tiers are rated in Python against the retail overall, so the build refuses a prepared
tier the lineman rule would move off its floor.

The cave reservations manifest model (``nfl2k5_cave_manifest.build_manifest``) applies the lineman
rating in its dormant-owner probe, so the regenerated manifest reserves the dispatch site and the
wrapper cave and the cave oracle refuses to allocate either to a later owner. The Edit Player elbow
rows (``nfl2k5_elbow_options``, the other beta 75 fixed-span opt-in in the ultimate recipe) are
reserved the same way, and so are the 16 .data fields of the music policy the recipe selects
(``nfl2k5_music_policy``: jukebox menus, every collection unlocked, the jukebox UserList).

Retail-backed classes skip without the private USA default.xbe (and ROST); no retail bytes here.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_elbow_options as elbow  # noqa: E402
from mod_editor.core import nfl2k5_lineman_rating as lineman  # noqa: E402
from mod_editor.core import nfl2k5_my_career as career  # noqa: E402
from mod_editor.core import nfl2k5_my_career_mode as mode  # noqa: E402
from mod_editor.core import nfl2k5_my_career_prospects as prospects  # noqa: E402
from mod_editor.core import nfl2k5_music_policy as music_policy  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as roster  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from tests.nfl2k5_my_career_fixture import HAVE_UC, XBE, prepared  # noqa: E402

LINE = lineman.LINE_POSITION_CODES
HOOK_SPAN = (lineman.HOOK_VA, lineman.HOOK_VA + len(lineman.RETAIL_HOOK))
CAVE_SPAN = (lineman.CAVE_VA, lineman.CAVE_VA + lineman.CAVE_SIZE)
NATIVE_CONTEXT = (0x246060, 0xD81)
WEIGHTS = (250, 305, 306, 329, 330, 339, 340, 349, 350, 360)


def _record(position: int, weight: int, *, height: int = 76, rating: int = 70) -> roster.PlayerRecord:
    record = roster.PlayerRecord.decode(bytes(84))
    record.set("position", position)
    record.set("height", height)
    record.set("weight", weight)
    for field in roster.RATING_BYTE_ORDER:
        record.set(field, rating)
    return record


def _with_weight(record: roster.PlayerRecord, weight: int) -> roster.PlayerRecord:
    copy = record.copy()
    copy.set("weight", weight)
    return copy


class ShapeTests(unittest.TestCase):
    """Why the rule is needed and why it is enough: one guard holds the hook, none the cave."""

    def test_the_dispatch_lies_wholly_inside_exactly_one_mycareer_guard(self) -> None:
        holders = [(va, size) for va, size, _digest in mode.GUARDS
                   if va <= HOOK_SPAN[0] and HOOK_SPAN[1] <= va + size]
        self.assertEqual(holders, [NATIVE_CONTEXT])
        # a partial overlap could not be normalised (the hash view restores whole hook spans)
        for va, size, _digest in (*mode.GUARDS, *career.GUARDS):
            overlaps = va < HOOK_SPAN[1] and HOOK_SPAN[0] < va + size
            self.assertEqual(overlaps, (va, size) == NATIVE_CONTEXT, hex(va))

    def test_the_cave_lies_outside_every_mycareer_guard(self) -> None:
        for va, size, _digest in (*mode.GUARDS, *career.GUARDS):
            self.assertFalse(va < CAVE_SPAN[1] and CAVE_SPAN[0] < va + size, hex(va))

    def test_no_mycareer_edit_touches_either_lineman_span(self) -> None:
        edits = mode.sites(mode.space.CODE_VA, mode.space.DATA_VA) + list(career.sites(0, 0))
        self.assertGreater(len(edits), 40)
        for name, va, before, _after in edits:
            for lo, hi in (HOOK_SPAN, CAVE_SPAN):
                self.assertFalse(va < hi and lo < va + len(before), f"{name} at {va:#x}")


class ModelTests(unittest.TestCase):
    """``native_overall(record, lineman=True)``: the overall a lineman executable computes."""

    def test_only_the_offensive_line_moves_and_it_reads_the_substituted_weight(self) -> None:
        for position in range(17):
            for weight in (150, 250, 294, 300, 317, 325, 326, 360, 405):
                record = _record(position, weight)
                stored = record.encode()
                adjusted = prospects.native_overall(record, lineman=True)
                if position in LINE:
                    expected = prospects.native_overall(
                        _with_weight(record, lineman.substituted_weight(position, weight)))
                else:
                    expected = prospects.native_overall(record)
                self.assertEqual(adjusted, expected, (position, weight))
                self.assertEqual(record.encode(), stored, "the model must never change the record")

    def test_each_adjusted_band_is_flat_and_the_middle_band_keeps_retail(self) -> None:
        for position in LINE:
            for lo, hi, effective in ((150, 305, 317), (330, 339, 327),
                                      (340, 349, 307), (350, 405, 293)):
                values = {prospects.native_overall(_record(position, w, height=h), lineman=True)
                          for w in (lo, hi) for h in (68, 80)}
                self.assertEqual(values, {prospects.native_overall(_record(position, effective))})
            for w in range(306, 330):
                record = _record(position, w)
                self.assertEqual(prospects.native_overall(record, lineman=True),
                                 prospects.native_overall(record))

    def test_default_is_the_retail_overall(self) -> None:
        record = _record(13, 360)
        self.assertEqual(prospects.native_overall(record), prospects.native_overall(record, lineman=False))
        self.assertNotEqual(prospects.native_overall(record), prospects.native_overall(record, lineman=True))


class PreparedTierGuardTests(unittest.TestCase):
    """The Studio's prepared tier is rated against the retail overall; the build checks it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.room = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.room.cleanup()

    def _setup(self, position: int, weight: int, tier: int) -> tuple[Path, bytes]:
        _result, setup, _receipt = prepared(position, prospect_tier=tier, weight=weight)
        path = Path(self.room.name) / f"MyCareer_{position}_{weight}_{tier}.json"
        path.write_text(json.dumps(setup), encoding="utf-8", newline="\n")
        return path, bytes.fromhex(setup["state"])

    def _check(self, path: Path, lineman_on: bool) -> None:
        plan = mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"), my_career=True,
                                   my_career_setup=str(path), the1wam_lineman_rating=lineman_on)
        mod_build._validated_r62_plan_options(plan)

    def test_the_prepared_overall_is_the_sealed_recipe_record(self) -> None:
        for position, weight in ((12, 360), (14, 250), (0, 220)):
            result, setup, receipt = prepared(position, prospect_tier=2, weight=weight)
            document = roster.RosterDocument(result, base=roster.find_block_base(result))
            chosen = document.by_offset[receipt["record_offset"]].record
            state = bytes.fromhex(setup["state"])
            self.assertEqual(prospects.prepared_overall(state), prospects.native_overall(chosen))
            self.assertEqual(prospects.prepared_overall(state), prospects.TIERS[2][1])
            self.assertEqual(prospects.prepared_overall(state, lineman=True),
                             prospects.native_overall(chosen, lineman=True))

    def test_a_lineman_the_rule_moves_off_his_floor_is_refused_only_with_the_rule(self) -> None:
        for position, weight, tier, shown in ((12, 360, 1, 64), (13, 250, 4, 63)):
            path, state = self._setup(position, weight, tier)
            self.assertEqual(prospects.prepared_overall(state, lineman=True), shown)
            self._check(path, False)
            with self.assertRaisesRegex(ValueError, rf"overall {prospects.TIERS[tier][1]} .* reads {shown}\."):
                self._check(path, True)

    def test_what_the_rule_leaves_on_its_floor_still_builds(self) -> None:
        # 317 lb reads 317 lb under the rule; a quarterback is not a lineman; tier 0 has no floor.
        for position, weight, tier in ((12, 317, 1), (0, 360, 1), (14, 330, 0)):
            path, _state = self._setup(position, weight, tier)
            self._check(path, False)
            self._check(path, True)


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class CompositionTests(unittest.TestCase):
    """Retail executable + lineman rating + generic MyCareer: both orders, replay, exact revert."""

    @classmethod
    def setUpClass(cls) -> None:
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.retail = retail_bytes()
        cls.lineman_only = lineman.apply(cls.retail)[0]
        cls.career_only = mode.apply(cls.retail)[0]
        cls.lineman_first = mode.apply(cls.lineman_only)[0]
        cls.career_first = lineman.apply(cls.career_only)[0]

    def test_both_orders_build_the_same_bytes_and_every_owner_reads_applied(self) -> None:
        self.assertEqual(self.lineman_first, self.career_first)
        for payload in (self.lineman_first, self.career_first):
            self.assertEqual(mode.status(payload), "applied")
            self.assertEqual(career.status(payload), "applied")
            self.assertEqual(lineman.status(payload), "applied")
        self.assertEqual(mode.status(self.lineman_only), "retail")

    def test_replaying_either_owner_is_a_no_op(self) -> None:
        composed = self.lineman_first
        again, receipt = mode.apply(composed)
        self.assertEqual(again, composed)
        self.assertTrue(receipt["already_applied"])
        again, receipt = lineman.apply(composed)
        self.assertEqual(again, composed)
        self.assertTrue(receipt["already_applied"])

    def test_reverting_the_lineman_rating_is_exact_and_leaves_mycareer_applied(self) -> None:
        reverted, receipt = lineman.revert(self.lineman_first)
        self.assertTrue(receipt["reverted"])
        self.assertEqual(reverted, self.career_only)
        self.assertEqual(mode.status(reverted), "applied")
        self.assertEqual(lineman.revert(self.lineman_only)[0], self.retail)

    def test_the_composition_adds_only_the_lineman_spans_and_the_section_digest(self) -> None:
        allowed = []
        for lo, hi in (HOOK_SPAN, CAVE_SPAN):
            at = rdata.offset_of(self.career_only, lo)
            allowed.append((at, at + hi - lo))
        count, table = struct.unpack_from("<II", self.career_only, 0x11C)
        base = struct.unpack_from("<I", self.career_only, 0x104)[0]
        allowed += [(table - base + i * 56 + 36, table - base + i * 56 + 56) for i in range(count)]
        self.assertEqual(len(self.lineman_first), len(self.career_only))
        changed = [i for i, (a, b) in enumerate(zip(self.career_only, self.lineman_first)) if a != b]
        self.assertTrue(changed)
        for index in changed:
            self.assertTrue(any(lo <= index < hi for lo, hi in allowed), f"byte {index:#x}")

    def test_the_hook_is_accepted_only_from_a_complete_lineman_install(self) -> None:
        hook = [("overall_dispatch", lineman.HOOK_VA, lineman.RETAIL_HOOK, lineman.PATCHED_HOOK)]
        cave = [("lineman_weight_cave", lineman.CAVE_VA, lineman.RETAIL_CAVE, lineman.PATCHED_CAVE)]
        # the retargeted call without its wrapper: the lineman owner is foreign, so MyCareer is too
        hook_only = rdata.apply(self.career_only, hook, "hook only")[0]
        self.assertEqual(lineman.status(hook_only), "foreign")
        self.assertEqual(mode.status(hook_only), "foreign")
        # any other dispatch bytes (here the call aimed one byte later) stay foreign
        stray = bytearray(lineman.PATCHED_HOOK)
        struct.pack_into("<i", stray, lineman.HOOK_CALL_OFFSET + 1,
                         struct.unpack_from("<i", stray, lineman.HOOK_CALL_OFFSET + 1)[0] + 1)
        aimed = rdata.apply(self.career_first, [("dispatch", lineman.HOOK_VA, lineman.PATCHED_HOOK, bytes(stray))],
                            "stray dispatch")[0]
        self.assertEqual(mode.status(aimed), "foreign")
        with self.assertRaises(mode.legacy.MyCareerError):
            mode.apply(rdata.apply(self.retail, hook, "hook only")[0])
        # a dead cave with the retail dispatch is not MyCareer's context (the inspector flags it)
        cave_only = rdata.apply(self.career_only, cave, "cave only")[0]
        self.assertEqual(lineman.status(cave_only), "foreign")
        self.assertEqual(mode.status(cave_only), "applied")

    def test_the_build_dispatcher_composes_them_in_one_call_and_in_the_builds_two_steps(self) -> None:
        # dry run 1 (b76-u1) failed on exactly this call: the xbe step, then the extra-space step
        first, _ = tt._apply_all(self.retail, None, catch_slider=False, the1wam_lineman_rating=True)
        second, receipt = tt._apply_all(first, None, catch_slider=False, xbe_space=True, my_career=True)
        self.assertFalse(receipt["my_career_patch"]["already_applied"])
        one, _ = tt._apply_all(self.retail, None, catch_slider=False, the1wam_lineman_rating=True,
                               xbe_space=True, my_career=True)
        self.assertEqual(one, second)
        self.assertEqual((mode.status(one), lineman.status(one)), ("applied", "applied"))
        with tempfile.TemporaryDirectory() as room:
            path = Path(room) / "default.xbe"
            path.write_bytes(one)
            rows = tt.read_xbe(path)
        self.assertEqual((rows["my_career"], rows["the1wam_lineman_rating"]), ("applied", "applied"))

    def test_the_gate_allocator_union_composes_too(self) -> None:
        union = json.loads((REPO / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        allocated = mode.apply(mode.space.apply(self.retail, union, scaleout=True)[0])[0]
        composed = lineman.apply(allocated)[0]
        self.assertEqual((mode.status(composed), lineman.status(composed)), ("applied", "applied"))
        self.assertEqual(lineman.revert(composed)[0], allocated)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "the private USA default.xbe and Unicorn are required")
class TierFloorTests(unittest.TestCase):
    """The tier floors hold on the adjusted overall: executed routine, model and in-game sweep."""

    @classmethod
    def setUpClass(cls) -> None:
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.retail = retail_bytes()
        cls.patched = lineman.apply(cls.retail)[0]
        cls.composed = mode.apply(cls.patched)[0]

    def test_the_executed_adjusted_overall_is_the_model_and_leaves_the_record_alone(self) -> None:
        from tests.nfl2k5_supersim_draft_fixture import Machine
        machine = Machine(self.patched, trace_writes=False)
        records = []
        for template in roster.create_player_templates():
            for weight in WEIGHTS:
                record = roster.PlayerRecord.decode(bytes(84))
                roster.apply_template(record, template)
                record.set("position", template.position_code)
                record.set("height", 76)
                record.set("weight", weight)
                records.append(record)
        rng = random.Random(76)
        for index in range(300):
            record = roster.PlayerRecord.decode(bytes(84))
            record.set("position", rng.choice(LINE) if index % 2 else rng.randrange(17))
            record.set("height", rng.randrange(67, 81))
            record.set("weight", rng.randrange(150, 406))
            for field in roster.RATING_BYTE_ORDER:
                record.set(field, rng.randrange(101))
            records.append(record)
        moved = 0
        for record in records:
            raw = record.encode()
            machine.uc.mem_write(machine.ARENA, raw)
            shown = machine.call(0x246D90, ecx=machine.ARENA, edx=0, budget=100000)
            self.assertEqual(shown, prospects.native_overall(record, lineman=True))
            self.assertEqual(bytes(machine.uc.mem_read(machine.ARENA, 84)), raw)
            moved += shown != prospects.native_overall(record)
        self.assertGreater(moved, 100)

    def test_the_in_game_sweep_lands_every_line_tier_on_the_adjusted_floor(self) -> None:
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        from tests.nfl2k5_my_career_mode_fixture import Machine
        source = retail_roster()
        off_retail = 0
        for position in LINE:
            for tier in range(1, 5):
                goal = prospects.TIERS[tier][1]
                for weight in WEIGHTS:
                    with self.subTest(position=position, tier=tier, weight=weight), Machine(self.composed) as m:
                        m.frontend(source)
                        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
                        m.select(1)
                        for _ in range(tier):
                            m.select(4)
                        self.assertEqual(m.get(m.state + 2744), tier)
                        m.select(1)
                        player = m.get(0xCB8B14)
                        m.uc.mem_write(player + 0x35, bytes((position,)))
                        m.call(0x343460)
                        m.uc.mem_write(player + lineman.WEIGHT_FIELD, bytes((weight - lineman.WEIGHT_BIAS,)))
                        for _ in range(4):
                            m.frame(0x10)
                        self.assertEqual(m.get(m.state + 2680), 2)
                        self.assertEqual(m.top(), m.labels["team_menu"])
                        self.assertEqual([e for e in m.events if e[0] == "notice"], [])
                        record = roster.PlayerRecord.decode(bytes(m.uc.mem_read(player, 84)))
                        self.assertEqual(record.get("weight"), weight)
                        self.assertEqual(m.call(0x246D90, ecx=player, edx=0), goal)
                        self.assertEqual(prospects.native_overall(record, lineman=True), goal)
                        off_retail += prospects.native_overall(record) != goal
        # the same ratings on a retail executable would miss the floor: the sweep followed the rule
        self.assertGreater(off_retail, 50)


LINEMAN_OWNER = "nfl2k5_lineman_rating"
ELBOW_OWNER = "nfl2k5_elbow_options"
# The four Edit Player elbow handler spans (next/previous, left/right), each a declared receipt edit.
ELBOW_SPANS = tuple((label, (va, va + len(before))) for label, va, before, _after in elbow.sites())
MUSIC_OWNER = "nfl2k5_music_policy"
# The 16 .data fields of the recipe's music policy: the menu policy dword, fourteen collection
# unlock dwords (collection record +0x14) and the 12-byte jukebox UserList.
MUSIC_FIELDS = tuple((site.option, (site.va, site.va + len(site.before))) for site in music_policy.SITES)
# The exact rows the manifest Recorder declares from the lineman's own names and receipt: the
# CAVE_VA/CAVE_SIZE capacity and the two receipt edits (observed byte diffs lie inside these).
DECLARED_ROWS = {("0x1d2400", "0x1d2440", 64, LINEMAN_OWNER, "declared capacity: CAVE_VA"),
                 ("0x246d60", "0x246d77", 23, LINEMAN_OWNER, "declared edit: overall_dispatch"),
                 ("0x1d2400", "0x1d2440", 64, LINEMAN_OWNER, "declared edit: lineman_weight_cave")}


class ManifestModelWiringTests(unittest.TestCase):
    """Retail-free: the manifest model runs the opt-in owners, and they declare what it reads."""

    @staticmethod
    def _model_lists() -> tuple[str, list[str], list[str]]:
        """``build_manifest``'s source, its explicitly wrapped modules and its extra_owners entries."""

        import ast
        from mod_editor.core import nfl2k5_cave_manifest as model
        source = inspect.getsource(model.build_manifest)
        wrapped, owners = [], []
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "modules"):
                wrapped += [ast.unparse(element) for comp in ast.walk(node) if isinstance(comp, ast.comprehension)
                            and isinstance(comp.iter, ast.Tuple) for element in comp.iter.elts]
            if isinstance(node, ast.Dict):
                owners += [ast.unparse(element) for key, value in zip(node.keys, node.values)
                           if isinstance(key, ast.Constant) and key.value == "extra_owners" for element in value.elts]
        return source, wrapped, owners

    @staticmethod
    def _owner_entry(name: str) -> str:
        import ast
        return ast.unparse(ast.parse(f'{name}.__name__.rsplit(".", 1)[-1]', mode="eval"))

    def test_the_dormant_owner_probe_applies_the_lineman_and_lists_it(self) -> None:
        source, wrapped, owners = self._model_lists()
        self.assertIn("from . import nfl2k5_lineman_rating as lineman", source)
        self.assertIn("final, _ = lineman.apply(final)", source)
        self.assertIn(self._owner_entry("lineman"), owners)       # extra_owners
        self.assertIn("lineman", wrapped)       # observed only if its apply is wrapped
        self.assertEqual(lineman.__name__.rsplit(".", 1)[-1], LINEMAN_OWNER)

    def test_the_dormant_owner_probe_applies_the_elbow_rows_and_lists_them(self) -> None:
        source, wrapped, owners = self._model_lists()
        self.assertIn("from . import nfl2k5_elbow_options as elbow", source)
        self.assertIn("final, _ = elbow.apply(final)", source)
        self.assertIn(self._owner_entry("elbow"), owners)
        self.assertIn("elbow", wrapped)
        self.assertEqual(elbow.__name__.rsplit(".", 1)[-1], ELBOW_OWNER)
        # after MyCareer and the lineman, like the other late opt-ins; both take no settings
        self.assertLess(source.index("final, _ = lineman.apply(final)"), source.index("final, _ = elbow.apply(final)"))

    def test_the_dormant_owner_probe_applies_the_recipes_music_policy_after_the_elbow_rows(self) -> None:
        import ast
        source, wrapped, owners = self._model_lists()
        self.assertIn("from . import nfl2k5_music_policy as music_policy", source)
        self.assertIn("music_policy", wrapped)
        self.assertEqual(owners[-3:], [self._owner_entry(name) for name in ("lineman", "elbow", "music_policy")])
        calls = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Call) and ast.unparse(node.func) == "music_policy.apply"]
        self.assertEqual(len(calls), 1)
        self.assertEqual({k.arg: ast.literal_eval(k.value) for k in calls[0].keywords},
                         {"music_policy": "jukebox_menus", "music_unlock": True, "music_userlist": True})
        # after the elbow rows, and before the music metadata, whose library copies the policy headers
        at = source.index("final, _ = music_policy.apply(")
        self.assertLess(source.index("final, _ = elbow.apply(final)"), at)
        self.assertLess(at, source.index("final, _ = music.apply(final"))
        # the selection the gate union composes (policy.apply defaults to jukebox_menus)
        union = (REPO / "tests" / "nfl2k5_allocator_stack.py").read_text(encoding="utf-8")
        self.assertIn("policy.apply(payload, music_unlock=True, music_userlist=True)", union)
        self.assertEqual(inspect.signature(music_policy.apply).parameters["music_policy"].default, "jukebox_menus")
        self.assertEqual(music_policy.__name__.rsplit(".", 1)[-1], MUSIC_OWNER)
        self.assertEqual(len(MUSIC_FIELDS), 16)

    def test_the_elbow_rows_declare_their_four_handler_spans_in_the_receipt(self) -> None:
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        receipt = elbow.apply(_build_synthetic_xbe(elbow=True))[1]
        self.assertEqual([(e["label"], int(e["va"], 0), e["bytes"]) for e in receipt["edits"]],
                         [(label, lo, hi - lo) for label, (lo, hi) in ELBOW_SPANS])

    def test_the_lineman_declares_the_names_and_receipt_the_recorder_reads(self) -> None:
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        self.assertEqual((lineman.CAVE_VA, lineman.CAVE_SIZE), (0x1D2400, 0x40))   # declared capacity
        receipt = lineman.apply(_build_synthetic_xbe(lineman=True))[1]
        self.assertEqual([(e["label"], int(e["va"], 0), e["bytes"]) for e in receipt["edits"]],
                         [("overall_dispatch", HOOK_SPAN[0], HOOK_SPAN[1] - HOOK_SPAN[0]),
                          ("lineman_weight_cave", CAVE_SPAN[0], CAVE_SPAN[1] - CAVE_SPAN[0])])


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class ManifestReservationTests(unittest.TestCase):
    """The manifest Recorder turns the lineman's writes into reservations the cave oracle obeys.

    ``build_manifest`` observes each probe owner with this same ``Recorder.wrapper``; here it
    observes the lineman alone (on retail and on the MyCareer executable) and a cave oracle over
    those reservations is asked to allocate on, across and beside both spans.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.retail = retail_bytes()
        cls.rows = {}
        for name, base in (("retail", cls.retail), ("mycareer", mode.apply(cls.retail)[0])):
            recorder = Recorder(cls.retail)
            recorder.wrapper(lineman, "apply")(base)
            cls.rows[name] = [dict(row) for row in recorder.spans]

    def _oracle(self, rows):
        from mod_editor.core.nfl2k5_cave_oracle import (MANIFEST_SCHEMA, CaveOracle, ReservationManifest,
                                                        XbeImage)
        document = {"schema": MANIFEST_SCHEMA, "retail_sha256": hashlib.sha256(self.retail).hexdigest(),
                    "complete": True, "spans": rows}
        manifest = ReservationManifest(document, XbeImage(self.retail))
        # Reservations take precedence over the (deliberately tiny) static analysis budget.
        return CaveOracle(self.retail, manifest=manifest, instruction_budget=1, reference_budget=1)

    def test_the_recorder_declares_the_dispatch_and_the_whole_wrapper_cave(self) -> None:
        for name, rows in self.rows.items():
            with self.subTest(base=name):
                self.assertEqual({row["owner"] for row in rows}, {LINEMAN_OWNER})
                self.assertTrue(DECLARED_ROWS <= {(r["start"], r["end"], r["size"], r["owner"], r["basis"])
                                                  for r in rows})
                # every observed byte lies in the two spans or the .text section digest (header)
                for row in rows:
                    lo, hi = int(row["start"], 0), int(row["end"], 0)
                    inside = any(a <= lo and hi <= b for a, b in (HOOK_SPAN, CAVE_SPAN))
                    self.assertTrue(inside or (row["basis"] == "observed byte diff" and hi <= 0x11000), row)

    def test_no_allocation_can_land_on_or_across_either_span(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import OracleError
        oracle = self._oracle(self.rows["retail"])
        windows = [(va, 1) for lo, hi in (HOOK_SPAN, CAVE_SPAN) for va in range(lo, hi)]
        windows += [(HOOK_SPAN[0], HOOK_SPAN[1] - HOOK_SPAN[0]), (CAVE_SPAN[0], CAVE_SPAN[1] - CAVE_SPAN[0]),
                    (CAVE_SPAN[0] - 0x10, 0x20), (CAVE_SPAN[1] - 0x10, 0x20),        # straddling the cave
                    (HOOK_SPAN[0] - 0x10, 0x20), (HOOK_SPAN[1] - 0x10, 0x20),        # straddling the dispatch
                    (0x1D23C1, 0x1D2591 - 0x1D23C1)]                                 # the whole dead run
        for kind in ("code", "data"):
            for start, size in windows:
                with self.subTest(kind=kind, start=hex(start), size=size):
                    row = oracle.assess(start, size, kind=kind)
                    self.assertEqual(row["verdict"], "reserved")
                    self.assertFalse(row["allocatable"])
                    self.assertTrue(all(w["detail"].startswith(LINEMAN_OWNER + ":") for w in row["witnesses"]))
                    with self.assertRaisesRegex(OracleError, "reserved"):
                        oracle.require_cave(start, size, kind=kind)

    def test_the_reservation_is_exact_and_names_the_owner(self) -> None:
        oracle = self._oracle(self.rows["retail"])
        # the bytes just outside each span are not claimed by the lineman
        for start, size in ((CAVE_SPAN[1], 0x10), (CAVE_SPAN[0] - 0x10, 0x10),
                            (HOOK_SPAN[1], 0x09), (HOOK_SPAN[0] - 0x10, 0x10)):
            with self.subTest(start=hex(start)):
                self.assertNotEqual(oracle.assess(start, size)["verdict"], "reserved")
        # excluding the owner itself (how an owner re-checks its own cave) frees exactly its bytes
        self.assertNotEqual(oracle.assess(CAVE_SPAN[0], 0x40, exclude_owner=LINEMAN_OWNER)["verdict"], "reserved")

    def test_scan_never_offers_the_spans(self) -> None:
        report = self._oracle(self.rows["retail"]).scan(min_size=1, kind="code")
        for row in report["ranges"]:
            lo, hi = int(row["start"], 0), int(row["end"], 0)
            for a, b in (HOOK_SPAN, CAVE_SPAN):
                if lo < b and a < hi:
                    self.assertEqual(row["verdict"], "reserved", row["start"])
                    self.assertFalse(row["allocatable"])
        text = next(s for s in report["sections"] if s["name"] == ".text")
        self.assertEqual(text["coverage"]["reserved"], (HOOK_SPAN[1] - HOOK_SPAN[0]) + (CAVE_SPAN[1] - CAVE_SPAN[0]))


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class ElbowManifestReservationTests(unittest.TestCase):
    """The same Recorder turns the elbow rows' four handler edits into reservations the oracle obeys."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.retail = retail_bytes()
        recorder = Recorder(cls.retail)
        recorder.wrapper(elbow, "apply")(cls.retail)
        cls.rows = [dict(row) for row in recorder.spans]

    def test_the_recorder_declares_each_whole_handler_span(self) -> None:
        self.assertEqual({row["owner"] for row in self.rows}, {ELBOW_OWNER})
        declared = {(int(r["start"], 0), int(r["end"], 0), r["basis"]) for r in self.rows
                    if r["basis"].startswith("declared edit: ")}
        self.assertEqual(declared, {(lo, hi, "declared edit: " + label) for label, (lo, hi) in ELBOW_SPANS})
        for row in self.rows:
            lo, hi = int(row["start"], 0), int(row["end"], 0)
            inside = any(a <= lo and hi <= b for _label, (a, b) in ELBOW_SPANS)
            self.assertTrue(inside or (row["basis"] == "observed byte diff" and hi <= 0x11000), row)
        observed = sum(int(r["end"], 0) - int(r["start"], 0) for r in self.rows
                       if r["basis"] == "observed byte diff" and int(r["start"], 0) >= 0x11000)
        self.assertEqual(observed, sum(a != b for _l, _va, a_span, b_span in elbow.sites()
                                       for a, b in zip(a_span, b_span)))       # the ten changed bytes

    def test_no_allocation_can_land_on_or_across_a_handler_and_the_gaps_stay_free(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import (MANIFEST_SCHEMA, CaveOracle, OracleError,
                                                        ReservationManifest, XbeImage)
        document = {"schema": MANIFEST_SCHEMA, "retail_sha256": hashlib.sha256(self.retail).hexdigest(),
                    "complete": True, "spans": self.rows}
        oracle = CaveOracle(self.retail, manifest=ReservationManifest(document, XbeImage(self.retail)),
                            instruction_budget=1, reference_budget=1)
        for label, (lo, hi) in ELBOW_SPANS:
            for start, size in [(va, 1) for va in range(lo, hi)] + [(lo, hi - lo), (lo - 8, 16), (hi - 8, 16)]:
                with self.subTest(span=label, start=hex(start), size=size):
                    row = oracle.assess(start, size)
                    self.assertEqual(row["verdict"], "reserved")
                    self.assertTrue(all(w["detail"].startswith(ELBOW_OWNER + ":") for w in row["witnesses"]))
                    with self.assertRaisesRegex(OracleError, "reserved"):
                        oracle.require_cave(start, size)
        # the bytes between the handlers belong to other code, not to this owner
        for (_a, (_lo, end)), (_b, (start, _hi)) in zip(ELBOW_SPANS, ELBOW_SPANS[1:]):
            self.assertNotEqual(oracle.assess(end, start - end)["verdict"], "reserved", hex(end))


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class MusicPolicyManifestReservationTests(unittest.TestCase):
    """The Recorder turns the music policy's 16 .data fields into reservations the oracle obeys.

    Observed as the manifest probe runs it (on the gate allocator union, then the music metadata
    that follows it), so the neighbours are judged against the real owner beside them: each
    collection record's count and record pointer (+0x18..+0x20) belong to the metadata.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from mod_editor.core.nfl2k5_cave_oracle import MANIFEST_SCHEMA, CaveOracle, ReservationManifest, XbeImage
        from tests import nfl2k5_allocator_stack as stack
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        retail = retail_bytes()
        allocated = mode.space.apply(retail, stack.REQUESTS, scaleout=True)[0]
        recorder = Recorder(retail)
        policed = recorder.wrapper(music_policy, "apply")(allocated, music_policy="jukebox_menus",
                                                           music_unlock=True, music_userlist=True)[0]
        final = recorder.wrapper(stack.music, "apply")(policed, song_records=stack.SONGS)[0]
        cls.rows = [dict(row) for row in recorder.spans]
        document = {"schema": MANIFEST_SCHEMA, "retail_sha256": hashlib.sha256(final).hexdigest(),
                    "complete": True, "spans": cls.rows}
        cls.oracle = CaveOracle(final, manifest=ReservationManifest(document, XbeImage(final)),
                                instruction_budget=1, reference_budget=1)

    @staticmethod
    def _owners(row) -> set[str]:
        return {w["detail"].split(":", 1)[0] for w in row["witnesses"]}

    def test_the_recorder_declares_every_field_and_nothing_beside_them(self) -> None:
        mine = [row for row in self.rows if row["owner"] == MUSIC_OWNER]
        self.assertEqual({(int(r["start"], 0), int(r["end"], 0)) for r in mine if r["basis"].startswith("declared edit")},
                         {span for _option, span in MUSIC_FIELDS})
        for row in mine:
            lo, hi = int(row["start"], 0), int(row["end"], 0)
            inside = any(a <= lo and hi <= b for _option, (a, b) in MUSIC_FIELDS)
            self.assertTrue(inside or (row["basis"] == "observed byte diff" and hi <= 0x11000), row)

    def test_no_allocation_can_land_on_or_across_a_field(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import OracleError
        for option, (lo, hi) in MUSIC_FIELDS:
            windows = [(va, 1) for va in range(lo, hi)] + [(lo, hi - lo), (lo - 2, 4), (hi - 2, 4)]
            for kind in ("data", "code"):
                for start, size in windows:
                    with self.subTest(field=option, kind=kind, start=hex(start), size=size):
                        row = self.oracle.assess(start, size, kind=kind)
                        self.assertEqual(row["verdict"], "reserved")
                        self.assertFalse(row["allocatable"])
                        self.assertIn(MUSIC_OWNER, self._owners(row))
                        with self.assertRaisesRegex(OracleError, "reserved"):
                            self.oracle.require_cave(start, size, kind=kind)

    def test_the_neighbours_stay_free_where_they_really_are_free(self) -> None:
        # nothing owns a record's word before its unlock dword (+0x10..+0x14), the gap before the
        # menu field, the word between the menu and UserList fields, or the words after the UserList
        free = [(lo - 4, 4) for option, (lo, _hi) in MUSIC_FIELDS if option == "music_unlock"]
        free += [(0xAC9EC0, 0x0C), (0xAC9ED0, 0x04), (0xAC9EE0, 0x40)]
        for start, size in free:
            with self.subTest(free=hex(start)):
                self.assertNotEqual(self.oracle.assess(start, size, kind="data")["verdict"], "reserved")
        # after each unlock dword sit the metadata's count and record pointer: reserved, never by the policy
        for option, (_lo, hi) in MUSIC_FIELDS:
            if option == "music_unlock":
                with self.subTest(metadata=hex(hi)):
                    row = self.oracle.assess(hi, 8, kind="data")
                    self.assertEqual(row["verdict"], "reserved")
                    self.assertEqual(self._owners(row), {"nfl2k5_music_metadata"})


if __name__ == "__main__":       # pragma: no cover - CI runs this file directly too
    unittest.main()
