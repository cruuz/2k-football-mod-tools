"""The studio's Qt-free half: catalogues, staging, the chained build, receipts.

`mod_editor/games/studio_service.py` is what the shell does when nobody is
looking, so all of it is provable without a display.  The module under test
here is a synthetic game written into a scratch games root: two lanes over a
toy "image" format -- one fixed-allocation writer that stamps bytes in place,
one export lane that publishes a folder -- each with its own synthetic source,
its own independent verifier and real refusals.  Nothing retail is read and
nothing is stubbed: the service really shells out to
``python -m mod_editor.games lane`` for every catalogue, plan, build and
verify, which is the thing worth proving.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import studio_service as service  # noqa: E402
from mod_editor.games.contract import Edit  # noqa: E402

from games_fakes import manifest as fake_manifest, write_fake_game  # noqa: E402

#: A two-lane game over a toy container: 64 bytes, a 16-byte header of ASCII
#: slot names and a 16-byte body of values.  Small enough that a build is
#: instant, real enough that a declared range, a verifier and a refusal all
#: mean what they mean on a disc.
TOY_GAME_SOURCE = textwrap.dedent(
    '''
    from __future__ import annotations

    import hashlib
    import json
    from pathlib import Path
    from typing import Any, Mapping, Optional, Sequence

    from mod_editor.games.contract import (
        Artifact, CONTRACT_SCHEMA, Catalogue, DeclaredRange, Edit, Field, GameIdentity,
        GameModule, Plan, Receipt, Refusal, SourceIdentity, Target, Verdict, WindowSpec,
        load_manifest, require,
    )

    HERE = Path(__file__).resolve().parent
    SLOTS = ("alpha", "beta", "gamma", "delta")
    HEADER = b"TOY1"


    def _synthetic() -> bytes:
        body = bytearray(HEADER)
        for index, _slot in enumerate(SLOTS):
            body += bytes([0x10 + index] * 4)
        return bytes(body.ljust(64, b"\\0"))


    class Identifier:
        accepted_suffixes = (".toy",)

        def identify(self, path):
            path = Path(path)
            data = path.read_bytes() if path.is_file() else b""
            return SourceIdentity(
                "toy", str(path), len(data), "TOY-00001", None,
                data[:4] == HEADER, False,
                f"{path.name} — a toy source of {len(data)} bytes",
            )


    class _Base:
        validators = ()
        page = None

        def _offset(self, index: int) -> int:
            return len(HEADER) + index * 4

        def build_catalogue(self, source, *, progress=None):
            data = Path(source).read_bytes()
            require(data[:4] == HEADER, f"{source} is not a toy source; its first four bytes are not TOY1.")
            targets = []
            for index, slot in enumerate(SLOTS):
                if progress is not None:
                    progress(f"{index + 1} of {len(SLOTS)} slots catalogued...")
                targets.append(Target(
                    key=slot,
                    label=f"slot {slot}",
                    detail=f"4 bytes at 0x{self._offset(index):x}",
                    budget="exactly 4 bytes, never longer",
                    searchable=slot,
                    raw={"index": index, "offset": self._offset(index)},
                    fields=self.FIELDS,
                ))
            return Catalogue("toy_catalogue/v1", self.lane_id, str(source), tuple(targets),
                             {"schema": "toy_catalogue/v1", "slots": list(SLOTS)})

        def synthetic_source(self, work_dir):
            path = Path(work_dir) / f"{self.lane_id.replace('.', '-')}.toy"
            path.write_bytes(_synthetic())
            return path


    class StampLane(_Base):
        lane_id = "colors.stamp"
        capability_id = "toygame.colors.stamp"
        surface = "colors"
        title = "Stamp a slot"
        classification = "offline-writer-proved"
        recipe_schema = "toy_recipe/v1"
        fixed_allocation = True
        FIELDS = (
            Field("value", "int", "New value", "0 to 255; every byte of the slot takes it.",
                  minimum=0, maximum=255),
            Field("colour", "colour_argb", "Tint", "Optional; ignored by the writer."),
        )

        def check_edit(self, target, values):
            unknown = sorted(set(values) - {"value", "colour"})
            if unknown:
                return f"{target.key}: {', '.join(unknown)} is not a value this lane takes; give value."
            if "value" not in values:
                return f"{target.key}: give a value from 0 to 255."
            if not 0 <= int(values["value"]) <= 255:
                return f"{target.key}: a slot byte is one byte, so value must be 0 to 255."
            return None

        def compose_recipe(self, edits):
            return {"schema": self.recipe_schema,
                    "edits": [{"slot": edit.target_key, "value": int(edit.values["value"])}
                              for edit in edits]}

        def _resolved(self, recipe, catalogue):
            require(recipe.get("schema") == self.recipe_schema,
                    f"recipe schema is {recipe.get('schema')!r}, expected {self.recipe_schema}")
            rows = []
            for row in recipe.get("edits", ()):
                target = catalogue.target(str(row["slot"]))
                rows.append((target, int(row["value"])))
            return rows

        def plan(self, source, recipe, catalogue):
            rows = self._resolved(recipe, catalogue)
            return Plan(self.lane_id, tuple(target.key for target, _v in rows),
                        tuple(DeclaredRange(int(target.raw["offset"]), 4, f"stamp:{target.key}")
                              for target, _v in rows),
                        {"slots": [target.key for target, _v in rows]})

        def build(self, source, destination, recipe, catalogue, *, work_dir=None):
            source, destination = Path(source), Path(destination)
            require(destination.resolve() != source.resolve(),
                    f"{destination} is the source; a build writes a NEW file and never the source.")
            require(not destination.exists(),
                    f"destination {destination} already exists; refusing to overwrite it")
            rows = self._resolved(recipe, catalogue)
            data = bytearray(source.read_bytes())
            for target, value in rows:
                start = int(target.raw["offset"])
                data[start:start + 4] = bytes([value]) * 4
            destination.write_bytes(bytes(data))
            return Receipt("toy_receipt/v1", self.lane_id, str(source), str(destination),
                           tuple(DeclaredRange(int(target.raw["offset"]), 4, f"stamp:{target.key}")
                                 for target, _v in rows),
                           {"slots": {target.key: value for target, value in rows}})

        def verify(self, source, destination, receipt):
            left, right = Path(source).read_bytes(), Path(destination).read_bytes()
            if len(left) != len(right):
                return Verdict(False, "the new file is a different length from the source.")
            declared = {offset for item in receipt.declared_ranges
                        for offset in range(item.start, item.start + item.length)}
            stray = [index for index in range(len(left))
                     if left[index] != right[index] and index not in declared]
            if stray:
                return Verdict(False, f"byte 0x{stray[0]:x} changed but no declared range covers it.")
            return Verdict(True, f"{len(receipt.declared_ranges)} declared range(s) verified; "
                                 f"{len(left) - len(declared)} unchanged bytes compared.")

        def conformance_edits(self, catalogue):
            return (Edit("alpha", {"value": 7}, note="conformance"),)


    class NoteExportLane(_Base):
        lane_id = "uniforms.notes"
        capability_id = "toygame.uniforms.notes"
        surface = "uniforms"
        title = "Publish slot notes"
        classification = "extract-only"
        recipe_schema = "toy_notes/v1"
        fixed_allocation = False
        FIELDS = (Field("note", "text", "Note", "One line published beside the slot."),)

        def check_edit(self, target, values):
            if not str(values.get("note", "")).strip():
                return f"{target.key}: write a note to publish, or remove this edit."
            return None

        def compose_recipe(self, edits):
            return {"schema": self.recipe_schema,
                    "notes": [{"slot": edit.target_key, "note": str(edit.values["note"])}
                              for edit in edits]}

        def plan(self, source, recipe, catalogue):
            rows = [catalogue.target(str(row["slot"])) for row in recipe.get("notes", ())]
            return Plan(self.lane_id, tuple(target.key for target in rows), (),
                        {"files": [f"{target.key}.txt" for target in rows]})

        def build(self, source, destination, recipe, catalogue, *, work_dir=None):
            destination = Path(destination)
            require(not destination.exists(),
                    f"destination {destination} already exists; refusing to overwrite it")
            destination.mkdir(parents=True)
            artifacts = []
            for row in recipe.get("notes", ()):
                target = catalogue.target(str(row["slot"]))
                path = destination / f"{target.key}.txt"
                path.write_text(str(row["note"]) + "\\n", encoding="utf-8", newline="\\n")
                artifacts.append(Artifact(str(path),
                                          hashlib.sha256(path.read_bytes()).hexdigest(), "note"))
            return Receipt("toy_notes_receipt/v1", self.lane_id, str(source), str(destination),
                           (), {"files": [item.path for item in artifacts]},
                           artifacts=tuple(artifacts))

        def verify(self, source, destination, receipt):
            stale = [item.path for item in receipt.artifacts
                     if not Path(item.path).is_file()
                     or hashlib.sha256(Path(item.path).read_bytes()).hexdigest() != item.sha256]
            if stale:
                return Verdict(False, f"{len(stale)} published file(s) do not match the receipt.")
            return Verdict(True, f"{len(receipt.artifacts)} published file(s) match the receipt.")

        def conformance_edits(self, catalogue):
            return (Edit("beta", {"note": "hello"}, note="conformance"),)


    def _window(parent=None, **context):
        return {"opened": True}


    GAME = GameModule(
        contract=CONTRACT_SCHEMA,
        identity=GameIdentity("toygame", "Toy Game", "Test Console", ("TOY-00001",), (), ()),
        identifier=Identifier(),
        lanes=(StampLane(), NoteExportLane()),
        windows=(WindowSpec("studio", "Toy studio…", "The toy studio.", "toygame", _window),
                 WindowSpec("side", "Toy side window…", "A side window.", "toygame-side", _window)),
        manifest=load_manifest(HERE),
        package=__name__,
        studio_window="studio",
    )
    '''
)


def _write_toy_game(root: Path) -> None:
    write_fake_game(
        root, "toygame", TOY_GAME_SOURCE,
        fake_manifest("toygame", title="Toy Game", game="Toy"),
        with_fragments=True, title="Toy Game",
    )


class _Fixture(unittest.TestCase):
    """One toy module, one source, one service, per test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="studio-service-")).resolve()
        cls.games_root = cls.root / "games"
        cls.games_root.mkdir()
        _write_toy_game(cls.games_root)
        cls.module = games.load("toygame", cls.games_root)
        cls.source = cls.root / "source.toy"
        cls.source.write_bytes(cls.module.lane("colors.stamp").synthetic_source(cls.root).read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.root, ignore_errors=True)

    def service(self) -> service.GameStudioService:
        room = Path(tempfile.mkdtemp(prefix="studio-cache-", dir=str(self.root))).resolve()
        self.addCleanup(shutil.rmtree, room, True)
        studio = service.GameStudioService(
            self.module, cache_root=room / "cache", poll_seconds=0.02,
            games_root=self.games_root,
        )
        studio.open(self.source)
        return studio


class OpeningTests(_Fixture):
    def test_a_source_is_identified_by_the_module_and_never_written(self) -> None:
        before = self.source.read_bytes()
        studio = self.service()
        identity = studio.identity()
        self.assertEqual(identity.serial, "TOY-00001")
        self.assertIn("toy source", identity.headline)
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_missing_source_is_one_sentence(self) -> None:
        studio = service.GameStudioService(self.module, cache_root=self.root / "c",
                                           games_root=self.games_root)
        with self.assertRaises(service.StudioError) as caught:
            studio.open(self.root / "nothing-here.toy")
        self.assertIn("not a file this studio can open", str(caught.exception))

    def test_nothing_is_offered_before_a_source(self) -> None:
        studio = service.GameStudioService(self.module, cache_root=self.root / "c",
                                           games_root=self.games_root)
        self.assertFalse(studio.is_open)
        with self.assertRaises(service.StudioError):
            studio.identity()

    def test_the_open_filter_is_composed_from_the_modules_own_suffixes(self) -> None:
        self.assertIn("*.toy", service.open_filter(self.module))


class CatalogueTests(_Fixture):
    def test_a_catalogue_is_built_in_a_child_process_and_then_cached(self) -> None:
        studio = self.service()
        self.assertFalse(studio.catalogue_state("colors.stamp").built)
        lines: list[str] = []
        state = studio.build_catalogue("colors.stamp", progress=lines.append)
        self.assertTrue(state.built)
        self.assertEqual(state.targets, 4)
        self.assertTrue(studio.catalogue_path("colors.stamp").is_file())
        catalogue = studio.catalogue("colors.stamp")
        self.assertEqual([target.key for target in catalogue.targets],
                         ["alpha", "beta", "gamma", "delta"])
        self.assertEqual(catalogue.targets[0].fields[0].kind, "int")

    def test_the_command_is_one_a_user_could_run(self) -> None:
        studio = self.service()
        command = studio.lane_command("colors.stamp", "catalogue", ["--source", "x", "--out", "y"])
        self.assertIn("-m", command)
        self.assertIn("mod_editor.games", command)
        self.assertEqual(command[-6:], ["colors.stamp", "catalogue", "--source", "x",
                                        "--out", "y"])
        self.assertEqual(command[-8:-6], ["lane", "toygame"])

    def test_a_catalogue_from_an_earlier_session_is_found_again(self) -> None:
        first = self.service()
        first.build_catalogue("colors.stamp")
        second = service.GameStudioService(
            self.module, cache_root=first.cache_root, poll_seconds=0.02,
            games_root=self.games_root)
        second.open(self.source)
        self.assertTrue(second.catalogue_state("colors.stamp").built)
        self.assertEqual(len(second.targets("colors.stamp")), 4)

    def test_asking_for_a_catalogue_nobody_built_says_what_to_do(self) -> None:
        studio = self.service()
        with self.assertRaises(service.StudioError) as caught:
            studio.targets("colors.stamp")
        self.assertIn("Build catalogue", str(caught.exception))


class EditingTests(_Fixture):
    def _ready(self):
        studio = self.service()
        studio.build_catalogue("colors.stamp")
        return studio, studio.catalogue("colors.stamp").target("alpha")

    def test_the_lanes_own_refusal_is_surfaced_verbatim(self) -> None:
        studio, target = self._ready()
        self.assertIsNone(studio.check_edit("colors.stamp", target, {"value": 3}))
        self.assertEqual(studio.check_edit("colors.stamp", target, {"value": 900}),
                         "alpha: a slot byte is one byte, so value must be 0 to 255.")
        self.assertIn("is not a value this lane takes",
                      studio.check_edit("colors.stamp", target, {"nope": 1}))

    def test_staging_a_refused_edit_raises_that_same_sentence(self) -> None:
        studio, target = self._ready()
        with self.assertRaises(service.StudioError) as caught:
            studio.stage("colors.stamp", target, {"value": 900})
        self.assertIn("0 to 255", str(caught.exception))

    def test_the_recipe_preview_is_the_document_the_patcher_gets(self) -> None:
        studio, target = self._ready()
        recipe = studio.compose("colors.stamp", [studio.stage("colors.stamp", target, {"value": 9})])
        self.assertEqual(recipe["schema"], "toy_recipe/v1")
        self.assertEqual(json.loads(studio.recipe_preview(recipe)), dict(recipe))

    def test_a_dry_run_resolves_the_edits_and_writes_nothing(self) -> None:
        studio, target = self._ready()
        before = self.source.read_bytes()
        plan = studio.plan_lane("colors.stamp", [Edit("alpha", {"value": 9})])
        self.assertEqual(plan.target_keys, ("alpha",))
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_dry_run_on_an_unknown_target_is_the_lanes_refusal(self) -> None:
        studio, _target = self._ready()
        with self.assertRaises(service.StudioError) as caught:
            studio.plan_lane("colors.stamp", [Edit("no-such-slot", {"value": 9})])
        self.assertIn("no-such-slot", str(caught.exception))


class DestinationTests(_Fixture):
    def test_an_existing_destination_is_refused_before_any_lane_is_asked(self) -> None:
        studio = self.service()
        taken = self.root / "taken.toy"
        taken.write_bytes(b"x")
        self.addCleanup(taken.unlink)
        with self.assertRaises(service.StudioError) as caught:
            studio.check_destination(taken)
        self.assertIn("already exists", str(caught.exception))

    def test_the_source_is_refused_as_its_own_destination(self) -> None:
        studio = self.service()
        with self.assertRaises(service.StudioError) as caught:
            studio.check_destination(self.source)
        self.assertIn("must not be the source", str(caught.exception))

    def test_a_missing_folder_is_named(self) -> None:
        studio = self.service()
        with self.assertRaises(service.StudioError) as caught:
            studio.check_destination(self.root / "nowhere" / "out.toy")
        self.assertIn("folder is missing", str(caught.exception))

    def test_the_free_space_check_asks_for_the_image_plus_one_intermediate(self) -> None:
        studio = self.service()
        estimate = studio.estimate(2, self.root / "out.toy")
        self.assertEqual(estimate.needed_bytes,
                         studio.identity().size_bytes * 2 + service.STAGING_RESERVE)
        self.assertIn("intermediate", estimate.sentence)

    def test_a_volume_without_room_refuses_the_build_with_that_sentence(self) -> None:
        studio = self.service()
        studio.build_catalogue("colors.stamp")
        original = service.platform_compat.available_bytes
        service.platform_compat.available_bytes = lambda _path: 1
        self.addCleanup(setattr, service.platform_compat, "available_bytes", original)
        with self.assertRaises(service.StudioError) as caught:
            studio.build({"colors.stamp": [Edit("alpha", {"value": 9})]}, self.root / "small.toy")
        self.assertIn("Free some space", str(caught.exception))
        self.assertFalse((self.root / "small.toy").exists())


class BuildTests(_Fixture):
    def test_a_one_step_build_writes_verifies_and_receipts(self) -> None:
        studio = self.service()
        studio.build_catalogue("colors.stamp")
        destination = self.root / "one-step.toy"
        self.addCleanup(destination.unlink, True)
        receipt = studio.build({"colors.stamp": [Edit("alpha", {"value": 0x41})]}, destination)
        self.addCleanup(receipt.receipt_path.unlink, True)
        self.assertTrue(receipt.all_verified)
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes()[4:8], b"AAAA")
        self.assertEqual(self.source.read_bytes()[4:8], bytes([0x10] * 4),
                         "the source is never written")
        document = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], service.RECEIPT_SCHEMA)
        self.assertEqual(document["studio"], "TC Toy 1 Studio")
        self.assertEqual(len(document["steps"]), 1)
        self.assertTrue(document["claims"]["every_step_independently_verified"])
        self.assertFalse(document["claims"]["runtime_visibility_proved"])

    def test_an_export_lane_publishes_beside_the_destination_and_is_verified(self) -> None:
        studio = self.service()
        studio.build_catalogue("colors.stamp")
        studio.build_catalogue("uniforms.notes")
        destination = self.root / "with-export.toy"
        receipt = studio.build(
            {"colors.stamp": [Edit("beta", {"value": 2})],
             "uniforms.notes": [Edit("gamma", {"note": "published"})]},
            destination,
        )
        self.addCleanup(receipt.receipt_path.unlink, True)
        self.addCleanup(destination.unlink, True)
        self.assertTrue(receipt.all_verified)
        self.assertEqual(len(receipt.steps), 2)
        [folder] = receipt.exports
        self.addCleanup(shutil.rmtree, folder, True)
        self.assertTrue(Path(folder).is_dir())
        self.assertEqual((Path(folder) / "gamma.txt").read_text(encoding="utf-8"), "published\n")
        self.assertEqual([step.lane_id for step in receipt.steps],
                         ["colors.stamp", "uniforms.notes"],
                         "steps run in the module's own lane order")

    def test_nothing_staged_is_a_sentence_not_an_empty_file(self) -> None:
        studio = self.service()
        with self.assertRaises(service.StudioError) as caught:
            studio.build({}, self.root / "empty.toy")
        self.assertIn("at least one edit", str(caught.exception))
        self.assertFalse((self.root / "empty.toy").exists())

    def test_a_refused_step_leaves_nothing_behind(self) -> None:
        studio = self.service()
        studio.build_catalogue("colors.stamp")
        destination = self.root / "refused.toy"
        with self.assertRaises(service.StudioError) as caught:
            studio.build({"colors.stamp": [Edit("no-such-slot", {"value": 1})]}, destination)
        self.assertIn("no-such-slot", str(caught.exception))
        self.assertFalse(destination.exists())
        self.assertFalse((destination.parent / (destination.name + service.RECEIPT_SUFFIX)).exists())


class GatingTests(unittest.TestCase):
    def test_nothing_but_open_before_a_source(self) -> None:
        state = service.studio_action_state(source_open=False, busy=False, catalogue_built=False,
                                            staged_count=0, plans_ready=False, built=False)
        self.assertTrue(state.can_open)
        self.assertFalse(state.can_build_catalogue or state.can_edit or state.can_check
                         or state.can_build)

    def test_build_waits_for_a_clean_plan_on_every_staged_lane(self) -> None:
        common = dict(source_open=True, busy=False, catalogue_built=True, built=False)
        self.assertFalse(service.studio_action_state(staged_count=2, plans_ready=False, **common).can_build)
        self.assertTrue(service.studio_action_state(staged_count=2, plans_ready=True, **common).can_build)

    def test_busy_withholds_everything_but_cancel(self) -> None:
        state = service.studio_action_state(source_open=True, busy=True, catalogue_built=True,
                                            staged_count=1, plans_ready=True, built=True)
        self.assertTrue(state.can_cancel)
        self.assertFalse(state.can_open or state.can_build or state.can_edit or state.can_open_folder)

    def test_a_lane_without_scopes_still_has_one(self) -> None:
        self.assertEqual(service.lane_scopes(object()), service.DEFAULT_SCOPES)

    def test_a_lane_that_offers_scopes_is_read_as_it_offers_them(self) -> None:
        class Scoped:
            def scopes(self):
                return (service.Scope("proved", "The proved scene", "one scene only"),
                        service.Scope("all", "Every scene", ""))

        self.assertEqual([scope.id for scope in service.lane_scopes(Scoped())], ["proved", "all"])

    def test_a_suggested_destination_is_never_the_source_name(self) -> None:
        self.assertEqual(service.suggested_destination("source.iso"), "source-modded.iso")
        self.assertEqual(service.suggested_destination("plain"), "plain-modded.out")


if __name__ == "__main__":
    unittest.main()
