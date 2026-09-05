"""Community playbook packs (``.2k5book``): schema, budget, the six offline rules,
retargeting by name, the export/import round trip and the real dry compile.

Everything in :class:`OfflinePackTests` runs with **no game data at all** -- that is
the point of the format: a contributor, a reviewer or a CI job needs only the JSON
and the codec.  :class:`RetailPackTests` is gated on the extracted retail archive
and proves the seed pack compiles into a real book.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402

YD = codec.YD_CM
EXTRACT = pathlib.Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
SEED = ROOT / "data" / "playbooks" / "modern_gun_core.2k5book"
#: one real retail offensive pass header (ATL play 141 "TE Y Outs"); a constant, not data.
PASS_HEADER = 0x0000640E
RUN_HEADER = 0x0000840E


def _has_extract() -> bool:
    return (EXTRACT / "vc_53450030" / "0").is_file()


def _fit_offline(template: str):
    """The slot order ``fit_template`` produces, without needing a book."""

    _blurb, players = lib.FORMATION_TEMPLATES[template]
    qbs = [p for p in players if p.kind == lib.QB]
    tackles = sorted([p for p in players if p.kind == lib.T], key=lambda p: -p.x)
    guards = sorted([p for p in players if p.kind == lib.G], key=lambda p: -p.x)
    centers = [p for p in players if p.kind == lib.C]
    skill = sorted([p for p in players if p.kind not in lib.OL_KINDS and p.kind != lib.QB],
                   key=lambda p: (p.x, p.z))
    ordered = [qbs[0], tackles[0], tackles[1], centers[0], guards[0], guards[1], *skill]
    codes = lib.ranked_codes([p.kind for p in ordered], [p.x for p in ordered])
    positions = [(int(round(p.x * YD)), int(round(p.z * YD))) for p in ordered]
    return positions, codes, [p.kind for p in ordered]


def synthetic_pack(concepts=("Mesh", "Dagger"), *, template="Gun Trips Right") -> pk.PlaybookPack:
    """A valid pack built from the library's own concepts, with no game data."""

    positions, codes, kinds = _fit_offline(template)
    plays = []
    for n, concept in enumerate(concepts, 1):
        spec = lib.PlaySpec(name=f"Gun {concept}", play_type="pass", positions=list(positions),
                            kinds=list(kinds), assignments={})
        lib.default_assignments(spec, concept=concept)
        chains = lib.build_chains(spec)
        plays.append(pk.PackPlay(
            f"gun-{concept.lower().replace(' ', '-')}", f"Gun {concept}", "pass",
            tuple(tuple((int(op), tuple(float(v) for v in vals)) for op, vals in chain)
                  for chain in chains),
            pk.PackDonor(88, "RO F Dump", PASS_HEADER, "pass"),
            PASS_HEADER, 100 + n, f"Stock Play {n}", concept, "gun-trips", None,
        ))
    formation = pk.PackFormation(
        "gun-trips", "Gun Trips Rt", tuple(positions), tuple(codes),
        pk.PackDonor(10, "Ace"), 4, "Split Jokers", 4, None,
    )
    return pk.PlaybookPack(
        pk.PackBook("ATL", "Synthetic", "tests", "1.0.0", "CC0-1.0"),
        pk.PackBase("a" * 64, 39, 254, 2438),
        (formation,), tuple(plays),
    )


def _mutate(pack: pk.PlaybookPack, **changes) -> dict:
    document = pack.to_json()
    for key, value in changes.items():
        document[key] = value
    return document


class OfflinePackTests(unittest.TestCase):
    """Stages 1-6 with no disc, no cache, no retail bytes."""

    def setUp(self) -> None:
        self.pack = synthetic_pack()

    # -- 1. schema ---------------------------------------------------------------
    def test_valid_pack_passes_every_offline_stage(self) -> None:
        report = pk.check_pack(self.pack)
        self.assertTrue(report.ok, report.text())
        names = [stage.name for stage in report.stages]
        self.assertEqual(names, [name for name, _title in pk.CHECK_ORDER])
        self.assertTrue(report.stages[-1].skipped, "the dry compile needs a book body")
        self.assertEqual(report.totals["net_play_growth"], 0)

    def test_json_round_trip_is_byte_stable(self) -> None:
        text = self.pack.dumps()
        again = pk.loads_pack(text)
        self.assertEqual(again.dumps(), text)
        self.assertEqual(again.plays[0].assignments, self.pack.plays[0].assignments)
        with tempfile.TemporaryDirectory() as tmp:
            path = pk.save_pack(self.pack, pathlib.Path(tmp) / "x")
            self.assertEqual(path.suffix, ".2k5book")
            self.assertEqual(pk.load_pack(path).dumps(), text)

    def test_schema_gate_refuses_foreign_documents(self) -> None:
        for document, needle in (
            ({"schema": "something/v9"}, "schema"),
            (_mutate(self.pack, schema="nfl2k5_playbook_pack/v2"), "schema"),
            (_mutate(self.pack, surprise=1), "unsupported top-level"),
            ([], "JSON object"),
        ):
            with self.assertRaises(pk.PlaybookPackError) as ctx:
                pk.pack_from_json(document)
            self.assertIn(needle, str(ctx.exception))

    def test_schema_gate_refuses_bad_field_types(self) -> None:
        document = self.pack.to_json()
        document["formations"][0]["slot_positions"] = [[0, 0]] * 10
        with self.assertRaisesRegex(pk.PlaybookPackError, "eleven"):
            pk.pack_from_json(document)
        document = self.pack.to_json()
        document["plays"][0]["play_type"] = "wildcat"
        with self.assertRaisesRegex(pk.PlaybookPackError, "play type"):
            pk.pack_from_json(document)
        document = self.pack.to_json()
        document["plays"][0]["custom_name"] = "x" * 41
        with self.assertRaisesRegex(pk.PlaybookPackError, "41 characters"):
            pk.pack_from_json(document)
        document = self.pack.to_json()
        document["plays"][0]["id"] = document["formations"][0]["id"]
        with self.assertRaisesRegex(pk.PlaybookPackError, "share the id"):
            pk.pack_from_json(document)
        document = self.pack.to_json()
        document["plays"][0]["link_formation"] = "no-such-formation"
        with self.assertRaisesRegex(pk.PlaybookPackError, "does not define"):
            pk.pack_from_json(document)
        document = self.pack.to_json()
        document["base"]["book_fingerprint"] = "nope"
        with self.assertRaisesRegex(pk.PlaybookPackError, "SHA-256"):
            pk.pack_from_json(document)
        document = self.pack.to_json()
        document["budget"]["plays"] = 999
        with self.assertRaisesRegex(pk.PlaybookPackError, "engine's limit"):
            pk.pack_from_json(document)

    # -- 2. budget ---------------------------------------------------------------
    def test_budget_refuses_growth_past_the_caps(self) -> None:
        document = self.pack.to_json()
        document["base"]["donor_play_count"] = 270
        for play in document["plays"]:
            play["replace_index"] = None
            play["replace_name"] = ""
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "budget")
        self.assertFalse(stage.ok)
        self.assertTrue(any("exceeds the 270" in e for e in stage.errors), stage.errors)

    def test_budget_refuses_two_entries_replacing_the_same_slot(self) -> None:
        document = self.pack.to_json()
        document["plays"][1]["replace_index"] = document["plays"][0]["replace_index"]
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "budget")
        self.assertFalse(stage.ok)
        self.assertIn("replace stock play", stage.errors[0])

    def test_budget_refuses_a_chain_past_fifteen_nodes(self) -> None:
        document = self.pack.to_json()
        node = document["plays"][0]["assignments"][6][0]
        document["plays"][0]["assignments"][6] = [node] * 16
        with self.assertRaisesRegex(pk.PlaybookPackError, "1 through 15 nodes"):
            pk.pack_from_json(document)

    def test_budget_refuses_more_links_than_the_menu_holds(self) -> None:
        document = self.pack.to_json()
        template = document["plays"][0]
        document["plays"] = []
        for n in range(40):
            row = copy.deepcopy(template)
            row["id"] = f"filler-{n}"
            row["custom_name"] = f"Filler {n}"
            row["replace_index"] = 100 + n
            document["plays"].append(row)
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "budget")
        self.assertFalse(stage.ok)
        self.assertTrue(any("menu table holds 36" in e for e in stage.errors), stage.errors)

    # -- 3. the ported retail validator ------------------------------------------
    def test_validator_rejects_a_handoff_nobody_takes(self) -> None:
        document = self.pack.to_json()
        document["plays"][0]["assignments"][0] = [
            [0x01, [1, 4, 0, 0.0, 0.0, 0.0]], [0x03, [0]], [0x13, [10, 0]],
        ]
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "validator")
        self.assertFalse(stage.ok)
        self.assertIn("Handoff To must be matched", stage.errors[0])

    def test_validator_is_skipped_and_said_so_when_a_slot_keeps_the_donor(self) -> None:
        document = self.pack.to_json()
        document["plays"][0]["assignments"][6] = None
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "validator")
        self.assertTrue(stage.ok)
        self.assertTrue(any("keeps the donor's chain" in n for n in stage.notes), stage.notes)

    # -- 4. class flags ----------------------------------------------------------
    def test_class_flags_catch_a_pass_staged_under_a_run_header(self) -> None:
        document = self.pack.to_json()
        document["plays"][0]["play_flags"] = RUN_HEADER
        document["plays"][0]["donor"]["flags"] = RUN_HEADER
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "class_flags")
        self.assertFalse(stage.ok)
        self.assertIn("played as a run", stage.errors[0])

    def test_class_flags_catch_a_changed_family_or_type_code(self) -> None:
        document = self.pack.to_json()
        document["plays"][0]["play_flags"] = PASS_HEADER ^ 0x1
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "class_flags")
        self.assertFalse(stage.ok)
        self.assertIn("bits 0-8", stage.errors[0])

    # -- 5. legality -------------------------------------------------------------
    def test_legality_catches_an_illegal_alignment(self) -> None:
        document = self.pack.to_json()
        document["formations"][0]["slot_positions"][6] = [-460, -400]   # TE off the line
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "legality")
        self.assertFalse(stage.ok)
        self.assertTrue(any("on the line of scrimmage" in e for e in stage.errors), stage.errors)

    def test_legality_catches_personnel_codes_that_disagree(self) -> None:
        document = self.pack.to_json()
        codes = list(document["formations"][0]["position_codes"])
        document["formations"][0]["category_positions"] = codes[:10] + [lib.FB]
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "legality")
        self.assertFalse(stage.ok)
        self.assertTrue(any("disagree about who lines up" in e for e in stage.errors), stage.errors)

    # -- 6. donor-header rule ----------------------------------------------------
    def test_donor_rule_catches_the_books_first_play(self) -> None:
        """The wizard's original bug: a pass cloned from the first offensive play,
        which is a run in every retail book."""

        document = self.pack.to_json()
        document["plays"][0]["donor"] = {"index": 0, "name": "Strong Dive",
                                         "flags": RUN_HEADER, "signature": "run"}
        document["plays"][0]["play_flags"] = PASS_HEADER
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "donor")
        self.assertFalse(stage.ok)
        self.assertIn("reference_play_for", stage.errors[0])

    def test_donor_rule_refuses_a_special_donor(self) -> None:
        document = self.pack.to_json()
        document["plays"][0]["donor"]["flags"] = PASS_HEADER | lib.PLAY_FLAG_SPECIAL
        document["plays"][0]["play_flags"] = PASS_HEADER | lib.PLAY_FLAG_SPECIAL
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "donor")
        self.assertFalse(stage.ok)
        self.assertTrue(any("Take Knee" in e for e in stage.errors), stage.errors)

    def test_donor_rule_needs_the_recorded_header(self) -> None:
        document = self.pack.to_json()
        document["plays"][0]["donor"].pop("flags")
        document["plays"][0]["donor"].pop("signature")
        report = pk.check_pack(pk.pack_from_json(document))
        stage = next(s for s in report.stages if s.name == "donor")
        self.assertFalse(stage.ok)
        self.assertIn("cannot be checked offline", stage.errors[0])

    # -- writer request rows -----------------------------------------------------
    def test_request_rows_are_exactly_what_the_writer_accepts(self) -> None:
        from mod_editor.core import nfl2k5_formation_play_writer as writer

        formations, plays, links = pk.pack_requests(self.pack, "asset-1")
        for row in formations:
            writer.formation_request_from_mapping(dict(row))
        for row in plays:
            writer.play_request_from_mapping(dict(row))
        for row in links:
            writer.link_request_from_mapping(dict(row))
        self.assertEqual(len(links), len(self.pack.plays))
        self.assertEqual({row["formation_index"] for row in links}, {4})

    def test_permuting_slots_moves_the_chains_and_renumbers_slot_references(self) -> None:
        """A target book's personnel group may order its skill players differently.
        The chains must follow their players, and every operand naming a slot must be
        renumbered with them — otherwise the tight end runs the split end's route and
        the handoff points at nobody."""

        chains = [None] * 11
        chains[0] = ((0x01, (1, 4, 0, 0.0, 0.0, 0.0)), (0x03, (0,)), (0x13, (10, 0)))
        chains[3] = ((0x01, (1, 2, 0, 0.0, 0.0, 0.0)), (0x02, (0,)))
        chains[9] = ((0x01, (1, 3, 0, 0.0, 0.0, 0.0)), (0x12, (0, 0, 10 * YD, 15)))
        chains[10] = ((0x01, (1, 3, 0, 0.0, 0.0, 0.0)), (0x16, (0, 0.0, 8)))
        order = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 9]        # the last two skill slots swap
        moved = pk.permute_assignments(chains, order)
        self.assertEqual([op for op, _ in moved[9]], [0x01, 0x16], "slot 10's chain moved to 9")
        self.assertEqual([op for op, _ in moved[10]], [0x01, 0x12], "slot 9's chain moved to 10")
        self.assertEqual(int(moved[0][2][1][0]), 9, "the handoff follows the back to his new slot")
        self.assertEqual(int(moved[3][1][1][0]), 0, "Snap To still names the QB (slot 0 did not move)")
        self.assertEqual(pk.permute_assignments(chains, list(range(11))), tuple(chains))
        with self.assertRaisesRegex(pk.PlaybookPackError, "eleven"):
            pk.permute_assignments(chains, [0, 1])

    def test_permutation_leaves_a_conditional_slot_alone_when_it_is_not_a_slot(self) -> None:
        # 0x15 operand 5 is a follow slot only in mode 2; 0x1A operand 3 only for kinds 2/3/5/6.
        chains = [None] * 11
        chains[6] = ((0x01, (1, 3, 0, 0.0, 0.0, 0.0)), (0x15, (0, 0.0, 0.0, 2, 15, 10, 0)))
        chains[7] = ((0x01, (1, 3, 0, 0.0, 0.0, 0.0)), (0x15, (2, 0.0, 0.0, 2, 15, 10, 0)))
        order = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 9]
        moved = pk.permute_assignments(chains, order)
        self.assertEqual(int(moved[6][1][1][5]), 10, "mode 0 keeps its raw field")
        self.assertEqual(int(moved[7][1][1][5]), 9, "mode 2 really is a follow slot")

    def test_install_plan_flags_conflicts_and_over_budget(self) -> None:
        book = _fake_book(formations=39, plays=254)
        plan = pk.install_plan(self.pack, book, b"", staged_play_targets=[101])
        statuses = {row.name: row.status for row in plan.rows}
        self.assertEqual(statuses["Gun Mesh"], "conflict")
        self.assertEqual(statuses["Gun Dagger"], "ok")
        self.assertFalse(plan.ok)
        self.assertIn("plays 254/270", plan.budget_line())


class PackCliTests(unittest.TestCase):
    """The shipped gate a contributor (or a GitHub Action) actually runs."""

    def setUp(self) -> None:
        import nfl2k5_playbook_pack as cli

        self.cli = cli

    def test_check_is_green_on_the_seed_pack_with_no_game_data(self) -> None:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.cli.main(["check", str(SEED)])
        self.assertEqual(code, 0, out.getvalue())
        text = out.getvalue()
        self.assertIn("PACK CHECK: GREEN", text)
        self.assertIn("[skip] 7.", text, "the dry compile needs a book")
        for stage in ("1. Schema", "2. Budget", "3. The ported retail play validator",
                      "4. Class-flag", "5. Formation legality", "6. Donor-header"):
            self.assertIn(stage, text)

    def test_check_reports_a_broken_pack_and_exits_non_zero(self) -> None:
        import contextlib
        import io

        document = synthetic_pack().to_json()
        document["plays"][0]["play_flags"] = RUN_HEADER
        document["plays"][0]["donor"]["flags"] = RUN_HEADER
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "broken.2k5book"
            path.write_text(json.dumps(document), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = self.cli.main(["check", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("PACK CHECK: FAILED", out.getvalue())
        self.assertIn("played as a run", out.getvalue())

    def test_check_refuses_a_foreign_file_without_a_traceback(self) -> None:
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "nope.2k5book"
            path.write_text("{}", encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = self.cli.main(["check", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("schema", err.getvalue())

    def test_the_cli_declares_the_pack_subcommands(self) -> None:
        parser = self.cli.build_parser()
        actions = [a for a in parser._actions if getattr(a, "choices", None)]
        self.assertEqual(sorted(actions[0].choices), ["check", "export", "modern-defense", "retarget"])


class _FakeEntry:
    def __init__(self, name: str) -> None:
        self.name = name


def _fake_book(*, formations: int, plays: int):
    """A minimal ``Nfl2k5Playbook`` stand-in for the plan table (names only)."""

    return insp.Nfl2k5Playbook(
        asset_id="fake", outer_index=308, book_name="ATL",
        formations=tuple(
            insp.PlaybookFormation(i, f"Stock Formation {i}", ()) for i in range(formations)
        ),
        plays=tuple(insp.PlaybookPlay(i, f"Stock Play {i}", 0, 0, "Offense", ())
                    for i in range(plays)),
        categories=(), chains=(), node_count=2438,
    )


class _FakeArchive:
    """Just the three members ``apply_packs_to_archive`` uses."""

    def __init__(self, resources: dict[int, bytes]) -> None:
        self.blobs = dict(resources)
        highest = max(resources) + 1
        self.entries = [
            type("E", (), {"size": len(resources.get(i, b"")), "virtual_offset": i})()
            for i in range(highest)
        ]

    def read_entry(self, index: int) -> bytes:
        return self.blobs[index]

    def write(self, virtual_offset: int, payload: bytes) -> int:
        self.blobs[virtual_offset] = bytes(payload)
        return len(payload)


@unittest.skipUnless(_has_extract(), "extracted retail archive missing")
class RetailPackTests(unittest.TestCase):
    """Gated: the seed pack against real retail books."""

    @classmethod
    def setUpClass(cls) -> None:
        import nfl2k5_playbook_position_recode as recode

        cls.recode = recode
        with recode.OuterImage(EXTRACT) as archive:
            cls.books = {
                team: archive.read_entry(recode.BOOK_ENTRIES[team])
                for team in ("ATL", "GB", "ARZ")
            }

    def _book(self, team: str):
        raw = self.books[team]
        return raw, insp.parse_playbook_resource(raw, asset_id=f"book:{team}"), raw[0x20:]

    def test_seed_pack_checks_clean_on_its_own_team(self) -> None:
        raw, _book, _body = self._book("ATL")
        pack = pk.load_pack(SEED)
        self.assertEqual(pack.book.team, "ATL")
        report = pk.check_pack(pack, resource=raw, asset_id="book:ATL")
        self.assertTrue(report.ok, report.text())
        compile_stage = next(s for s in report.stages if s.name == "compile")
        self.assertTrue(compile_stage.ok and not compile_stage.skipped)
        self.assertEqual(report.totals["net_play_growth"], 0)
        self.assertEqual(report.totals["net_formation_growth"], 0)
        self.assertEqual(report.totals["plays"], report.totals["plays_before"])
        self.assertEqual(len(pack.formations), 4)
        self.assertEqual(len(pack.plays), 11)

    def test_seed_pack_fingerprint_is_the_retail_body(self) -> None:
        raw, _book, body = self._book("ATL")
        pack = pk.load_pack(SEED)
        self.assertEqual(pack.base.book_fingerprint, pk.book_fingerprint(body))
        self.assertEqual(pk.book_fingerprint(raw), pk.book_fingerprint(body))
        with self.assertRaisesRegex(pk.PlaybookPackError, "bytes of body"):
            pk.book_fingerprint(b"short")

    def test_dry_compile_reparses_and_owns_only_its_bytes(self) -> None:
        raw, book, _body = self._book("ATL")
        pack = pk.load_pack(SEED)
        compiled = pk.apply_pack_to_resource(raw, pack, asset_id="book:ATL")
        self.assertEqual(compiled.replacement[:0x20], raw[:0x20], "the wrapper must not move")
        self.assertEqual(len(compiled.replacement), len(raw))
        rebuilt = insp.parse_playbook_resource(compiled.replacement, asset_id="book:ATL")
        self.assertEqual(len(rebuilt.formations), len(book.formations))
        self.assertEqual(len(rebuilt.plays), len(book.plays))
        names = {f.name for f in rebuilt.formations}
        self.assertTrue({"Gun Trips Rt", "Gun Doubles", "Gun Bunch Rt", "Gun Empty"} <= names)
        self.assertIn("Gun Trips Rt Mesh", {p.name for p in rebuilt.plays})
        # every replaced play stays listed exactly where the stock one was
        for entry in pack.plays:
            before = {f.index for f in book.formations
                      if any(l.play_index == entry.replace_index for l in f.play_links)}
            after = {f.index for f in rebuilt.formations
                     if any(l.play_index == entry.replace_index for l in f.play_links)}
            self.assertEqual(before, after, entry.id)

    def test_retarget_resolves_replace_targets_by_name(self) -> None:
        raw, book, body = self._book("GB")
        pack = pk.load_pack(SEED)
        retargeted, resolutions = pk.retarget_pack(pack, "GB", book, body)
        self.assertEqual(retargeted.book.team, "GB")
        self.assertEqual(retargeted.base.book_fingerprint, pk.book_fingerprint(body))
        by_name = [r for r in resolutions if r.field == "replace" and r.how == "name"]
        self.assertTrue(by_name, "GB shares some stock names with ATL")
        for res in by_name:
            entry = next(e for e in (*retargeted.formations, *retargeted.plays)
                         if e.id == res.entry_id)
            table = book.formations if res.kind == "formation" else book.plays
            self.assertEqual(table[entry.replace_index].name, entry.replace_name)
            self.assertEqual(table[entry.replace_index].name, res.name)
        # nothing is silently reused
        for kind, entries in (("formation", retargeted.formations), ("play", retargeted.plays)):
            indices = [e.replace_index for e in entries if e.replace_index is not None]
            self.assertEqual(len(indices), len(set(indices)), kind)
        report = pk.check_pack(retargeted, resource=raw, asset_id="book:GB")
        self.assertTrue(report.ok, report.text())

    def test_retarget_keeps_the_stored_index_only_on_a_name_match(self) -> None:
        _raw, book, body = self._book("ATL")
        pack = pk.load_pack(SEED)
        document = pack.to_json()
        # point one play at an index whose name is somebody else's: the name must win
        wanted = document["plays"][0]["replace_name"]
        document["plays"][0]["replace_index"] = 3
        retargeted, resolutions = pk.retarget_pack(pk.pack_from_json(document), "ATL", book, body)
        self.assertNotEqual(book.plays[3].name, wanted)
        self.assertEqual(book.plays[retargeted.plays[0].replace_index].name, wanted)
        res = next(r for r in resolutions if r.entry_id == retargeted.plays[0].id
                   and r.field == "replace")
        self.assertEqual(res.how, "name")

    def test_retarget_keeps_every_player_on_his_own_route(self) -> None:
        """29 of the 32 books order their skill slots differently from ATL, so this is
        the check that a retargeted pack is still the play its author drew."""

        _raw, book, body = self._book("GB")
        pack = pk.load_pack(SEED)
        retargeted, resolutions = pk.retarget_pack(pack, "GB", book, body)
        self.assertTrue([r for r in resolutions if r.how == "permuted"],
                        "GB's personnel group orders its skill players differently from ATL's")
        source_formation, target_formation = pack.formations[0], retargeted.formations[0]
        self.assertNotEqual(source_formation.position_codes, target_formation.position_codes)
        for play_before, play_after in zip(pack.plays[:3], retargeted.plays[:3]):
            for slot in range(11):
                spot = target_formation.slot_positions[slot]
                kind = target_formation.position_codes[slot] & 0x1F
                origin = next(i for i in range(11)
                              if source_formation.slot_positions[i] == spot
                              and (source_formation.position_codes[i] & 0x1F) == kind)
                self.assertEqual(
                    [op for op, _ in play_before.assignments[origin]],
                    [op for op, _ in play_after.assignments[slot]],
                    f"{play_after.custom_name} slot {slot}",
                )

    def test_retarget_reports_a_ranked_fallback_rather_than_guessing_silently(self) -> None:
        _raw, book, body = self._book("GB")
        pack = pk.load_pack(SEED)
        _retargeted, resolutions = pk.retarget_pack(pack, "GB", book, body)
        ranked = [r for r in resolutions if r.how == "ranked"]
        self.assertTrue(ranked, "GB does not carry every ATL name")
        for res in ranked:
            self.assertIn("this book has no", res.detail)

    def test_export_import_round_trip_from_staged_rows(self) -> None:
        _raw, book, body = self._book("ATL")
        pack = pk.load_pack(SEED)
        formation_rows, play_rows, link_rows = pk.pack_requests(pack, "asset-1", book)
        rebuilt = pk.pack_from_staged_rows(
            team="ATL", book=book, body=body,
            formation_rows=formation_rows, play_rows=play_rows, link_rows=link_rows,
            name=pack.book.name, author=pack.book.author,
        )
        self.assertEqual(rebuilt.base.book_fingerprint, pack.base.book_fingerprint)
        # the export walks the project archive's own row order (asset, kind, canonical
        # JSON) because that is the order Build assigns appended indices in, so entries
        # are compared by name rather than by position
        self.assertEqual(sorted(f.custom_name for f in rebuilt.formations),
                         sorted(f.custom_name for f in pack.formations))
        self.assertEqual(sorted(p.custom_name for p in rebuilt.plays),
                         sorted(p.custom_name for p in pack.plays))
        formations = {f.custom_name: f for f in rebuilt.formations}
        for original in pack.formations:
            mirror = formations[original.custom_name]
            self.assertEqual(mirror.replace_index, original.replace_index)
            self.assertEqual(mirror.replace_name, original.replace_name)
            self.assertEqual(mirror.slot_positions, original.slot_positions)
            self.assertEqual(mirror.position_codes, original.position_codes)
            self.assertEqual(mirror.donor.index, original.donor.index)
        plays = {p.custom_name: p for p in rebuilt.plays}
        for original in pack.plays:
            mirror = plays[original.custom_name]
            self.assertEqual(mirror.replace_index, original.replace_index)
            self.assertEqual(mirror.replace_name, original.replace_name)
            self.assertEqual(mirror.assignments, original.assignments)
            self.assertEqual(mirror.donor.flags, original.donor.flags)
            self.assertEqual(mirror.donor.signature, original.donor.signature)
            self.assertEqual(mirror.play_flags, original.play_flags)
        with tempfile.TemporaryDirectory() as tmp:
            path = pk.save_pack(rebuilt, pathlib.Path(tmp) / "round-trip")
            self.assertEqual(pk.load_pack(path).dumps(), rebuilt.dumps())

    def test_preview_builds_a_plan_and_a_budget_line(self) -> None:
        raw, book, body = self._book("ARZ")
        pack = pk.load_pack(SEED)
        preview = pk.preview_pack(pack, "ARZ", book, body, resource=raw)
        self.assertTrue(preview.retargeted)
        self.assertTrue(preview.ok, preview.check.text())
        self.assertEqual(len(preview.plan.rows), 15)
        self.assertTrue(all(row.status in ("ok", "retargeted") for row in preview.plan.rows))
        self.assertIn("plays 270/270", preview.plan.budget_line())   # ARZ is at the cap

    def test_apply_packs_writes_and_reads_back_each_book(self) -> None:
        entries = {self.recode.BOOK_ENTRIES[t]: self.books[t] for t in ("ATL", "GB")}
        archive = _FakeArchive(entries)
        pack = pk.load_pack(SEED)
        document = pack.to_json()
        document["book"]["targets"] = ["ATL", "GB"]
        messages: list[str] = []
        receipt = pk.apply_packs_to_archive(
            archive, [("modern_gun_core.2k5book", pk.pack_from_json(document))],
            messages.append, self.recode.BOOK_ENTRIES,
        )
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(len(receipt["packs"]), 1)
        rows = receipt["packs"][0]["books"]
        self.assertEqual([row["team"] for row in rows], ["ATL", "GB"])
        self.assertFalse(rows[0]["retargeted"])
        self.assertTrue(rows[1]["retargeted"])
        for team, row in zip(("ATL", "GB"), rows):
            index = self.recode.BOOK_ENTRIES[team]
            self.assertNotEqual(archive.blobs[index], self.books[team])
            self.assertEqual(archive.blobs[index][:0x20], self.books[team][:0x20])
            rebuilt = insp.parse_playbook_resource(archive.blobs[index], asset_id="x")
            self.assertEqual(len(rebuilt.plays), row["plays"])
            self.assertIn("Gun Trips Rt", {f.name for f in rebuilt.formations})
        self.assertTrue(any("Installing" in m for m in messages))

    def test_pack_rows_persist_in_a_2k5mod_with_no_schema_change(self) -> None:
        """A pack stages ordinary project edits: the archive gains no new member and
        no new manifest key, so an older studio still reads the project."""

        import zipfile

        from mod_editor.studio import project_archive as archive_mod

        _raw, book, _body = self._book("ATL")
        pack = pk.load_pack(SEED)
        formations, plays, links = pk.pack_requests(pack, "nfl2k5.resource.o0308.c0000.k504c4159", book)
        with tempfile.TemporaryDirectory() as tmp:
            out = archive_mod.save_project_archive(
                catalog=None, asset_io=None, edits=(),
                destination=pathlib.Path(tmp) / "pack.2k5mod",
                formation_creates=formations, play_creates=plays, formation_links=links,
            )
            with zipfile.ZipFile(out) as zf:
                self.assertEqual(zf.namelist(), ["project.json"])
                document = json.loads(zf.read("project.json"))
        self.assertEqual(sorted(document), ["edits", "game", "payload_policy",
                                            "playbook_creates", "playbook_links", "schema"])
        self.assertEqual(len(document["playbook_creates"]), len(pack.formations) + len(pack.plays))
        self.assertEqual(len(document["playbook_links"]), len(links))
        kinds = {row["kind"] for row in document["playbook_creates"]}
        self.assertEqual(kinds, {"play_formation_create", "play_create"})

    def test_a_book_another_patch_already_touched_is_reported_not_guessed(self) -> None:
        raw, book, body = self._book("ATL")
        pack = pk.load_pack(SEED)
        document = pack.to_json()
        document["base"]["book_fingerprint"] = "b" * 64
        report = pk.check_pack(pk.pack_from_json(document), book, body, resource=raw)
        stage = next(s for s in report.stages if s.name == "schema")
        self.assertTrue(any("not the one this pack was authored on" in n for n in stage.notes),
                        stage.notes)


SRC = pathlib.Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
CACHE = pathlib.Path(
    "/home/noah/.cache/2k5-mod-studio/"
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)


@unittest.skipUnless(SRC.exists() and CACHE.exists(), "retail XISO / private cache missing")
class FacadeInstallTests(unittest.TestCase):
    """The real install path: facade -> session -> the formation/play writer.

    This is also the multi-book proof: one project may now carry designs for more
    than one team, which is what "apply to all 32" needs."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.studio.facade import Nfl2k5StudioFacade

        from mod_editor.core.nfl2k5_uniform_catalog import DEFAULT_REPORT
        if not DEFAULT_REPORT.is_file():
            raise unittest.SkipTest("private uniform catalog report missing; facade requires it")
        from mod_editor.studio.session import StudioSession
        from functools import partial
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.facade = Nfl2k5StudioFacade(
            session_factory=partial(StudioSession, root=pathlib.Path(temporary.name)))
        cls.facade.load_source(SRC, lambda *a: None)

    def test_installing_into_two_teams_stages_ordinary_reversible_edits(self) -> None:
        facade = self.facade
        pack = facade.load_playbook_pack(SEED)
        self.assertIn("ATL", facade.playbook_teams())

        preview = facade.preview_playbook_pack(pack, "ATL")
        self.assertTrue(preview.ok, preview.check.text())
        self.assertFalse(preview.retargeted)
        self.assertEqual(len(preview.plan.rows), 15)

        result = facade.install_playbook_pack(pack, ("ATL", "GB"))
        session = facade._session
        self.assertIn("ATL, GB", str(getattr(result, "message", result)))
        books = {r.asset_id for r in session.formation_creates}
        self.assertEqual(len(books), 2, "a project may hold designs for two books")
        self.assertEqual(len(session.formation_creates), 8)
        self.assertEqual(len(session.play_creates), 22)
        self.assertEqual(
            sorted(r.custom_name for r in session.formation_creates if r.asset_id == sorted(books)[0]),
            ["Gun Bunch Rt", "Gun Doubles", "Gun Empty", "Gun Trips Rt"],
        )

        # the plan for a second install of the same pack now conflicts with itself
        again = facade.preview_playbook_pack(pack, "ATL")
        self.assertTrue(any(row.status == "conflict" for row in again.plan.rows))
        with self.assertRaises(Exception):
            facade.install_playbook_pack(pack, ("ATL",))

        # and every row reverts through the ordinary revert path
        for request in list(session.play_creates):
            facade.revert_play_create(request.selector)
        for request in list(session.formation_links):
            facade.revert_formation_link(request.selector)
        for request in list(session.formation_creates):
            facade.revert_formation_create(request.selector)
        self.assertEqual(session.formation_creates, ())
        self.assertEqual(session.play_creates, ())
        self.assertEqual(session.formation_links, ())

    def test_export_round_trips_a_staged_pack_through_the_facade(self) -> None:
        facade = self.facade
        pack = facade.load_playbook_pack(SEED)
        facade.install_playbook_pack(pack, ("ATL",))
        session = facade._session
        asset_id = session.formation_creates[0].asset_id
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = facade.export_playbook_pack(
                    asset_id, pathlib.Path(tmp) / "mine.2k5book",
                    name="Round Trip", author="tests", notes="exported from the staged rows",
                )
                exported = pk.load_pack(path)
            self.assertEqual(exported.book.team, "ATL")
            self.assertEqual(exported.book.author, "tests")
            # the export walks the project archive's own row order, so compare as sets
            self.assertEqual(sorted(p.custom_name for p in exported.plays),
                             sorted(p.custom_name for p in pack.plays))
            self.assertEqual(sorted(f.replace_index for f in exported.formations),
                             sorted(f.replace_index for f in pack.formations))
            by_name = {p.custom_name: p for p in exported.plays}
            for original in pack.plays:
                mirror = by_name[original.custom_name]
                self.assertEqual(mirror.replace_index, original.replace_index)
                self.assertEqual(mirror.replace_name, original.replace_name)
                self.assertEqual(mirror.assignments, original.assignments)
                self.assertEqual(mirror.donor.index, original.donor.index)
                self.assertEqual(mirror.play_flags, original.play_flags)
        finally:
            for request in list(session.play_creates):
                facade.revert_play_create(request.selector)
            for request in list(session.formation_links):
                facade.revert_formation_link(request.selector)
            for request in list(session.formation_creates):
                facade.revert_formation_create(request.selector)


if __name__ == "__main__":
    unittest.main()
