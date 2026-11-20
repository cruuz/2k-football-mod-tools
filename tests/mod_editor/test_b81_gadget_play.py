"""Beta 81 Q62: the SPECIAL GAD player on gadget plays (``nfl2k5_gadget_play``).

Noah (11/03): "sometimes gadget player should be in the halfback position ... just make sure that every movement in the
special part of the depth chart does something accurately, and it doesn't permanently make someone in a special
position a starter somewhere else." Approved default: the gadget player is only in for gadget plays.

What these tests hold the owner to:
- Without any fixture: the runtime template, its five link-time fields, the fixed release slots and the hook bytes;
  ``code_for`` with the qualified candidate's values reproduces the qualified code (XBE 7963a1db, the executable that
  ran Codex's 20 CPU games, the attract game and the MyCareer game) byte for byte; the build-time classifier on
  synthetic plays.
- With the private preview disc and the qualified candidate (``NFL2K5_B81_OWNERSHIP_FIXTURES``): the Studio owner,
  applied to the preview's own executable and books, IS the qualified executable.
- With the released v0.9 disc (``NFL2K5_V09_XISO``): placement, order independence with the Backfield cards, refresh
  when the books change, removal, refusals.
- With Python unicorn and the released v0.9 disc: the game's own play selection, lineup builder, picker and gate
  under Unicorn, before and after the owner. A gadget play puts a healthy, faster, off-field GAD in the carrier's slot
  and changes nothing else; every other play, an injured or slower GAD, a GAD already on the field, a user
  substitution, the punt set-up frames that froze FC1 and the Gun Empty formation that froze FC2 keep the game's
  lineup; malformed selections are refused by the classifier.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_gadget_play as gadget  # noqa: E402
from mod_editor.core import nfl2k5_gadget_play_code as template  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

FIXTURES = Path(os.environ.get("NFL2K5_B81_OWNERSHIP_FIXTURES", "") or "missing")
PREVIEW_DISC = FIXTURES / "test-disc/previews/303b97d10750/SOFTDRINK 2K28 beta 81 PRIVATE TEST 128.xiso.iso"
QUALIFIED_XBE = FIXTURES / "evidence/q62-gadget/nov19/runtime/speed/candidate/default.xbe"
V09_DISC = Path(os.environ.get("NFL2K5_V09_XISO", "") or "missing")
PREVIEW_XBE_SHA256 = "f416b7e8da3c842329e4f6d3a4352c6cf3d2936a9c6572d54bca5271c6a01a16"
QUALIFIED_XBE_SHA256 = "7963a1db3d3a061717caec3eaa36168543db26666fb52ce8c430e06c8ba1235c"
V09_XBE_SHA256 = "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866"
# The qualified candidate's link-time values (its receipt) and the sha256 of its whole 2,048-byte code allocation.
QUALIFIED_OFFSETS = {"book_rows": 0, "links": 592, "blobs": 2368, "pair_info": 12796}
QUALIFIED_GATE = 0x14F13E0
QUALIFIED_CODE_SHA256 = "b6d4c7fd6005d2bf892d88c01d99f4c1e01a306f3d9605e28d2082448705bd0f"
QUALIFIED_TABLE_SHA256 = "5e71503f18a514faa70e70d1e1373c0d098d941440f5efe967beb7b6782e9c24"
# The qualified code's classifier (select_slot) and the scoped tail after the builder (scope_return), by offset.
QUALIFIED_SELECT_SLOT, QUALIFIED_ASSIGN, QUALIFIED_SCOPE_RETURN, QUALIFIED_TAPPED = 0x173, 0x502, 0xAD, 0xD6
# Review F1 added the one-snap restore; this is the whole 2,048-byte allocation with the qualified link values.
RUNTIME_CODE_SHA256 = "5e8cf63a508578911056d5144f025c0beaac1af06c52adf3adc6c200615c3a07"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=None)
def _disc(path: str) -> tuple[bytes, dict[str, bytes]]:
    from mod_editor.core import mod_build, nfl2k5_depth_roles as depth
    resources = depth._resources(Path(path))
    return mod_build._xbe_bytes(Path(path)), {k: resources[k] for k in gadget.BOOK_ASSETS}


def _require_disc(path: Path, sha: str) -> tuple[bytes, dict[str, bytes]]:
    if not path.is_file():
        raise unittest.SkipTest(f"private disc fixture absent: {path}")
    xbe, books = _disc(str(path))
    if _sha(xbe) != sha:
        raise unittest.SkipTest(f"{path} is not the pinned disc")
    return xbe, books


class TemplateTests(unittest.TestCase):
    def test_the_slots_are_the_release_reservation(self):
        self.assertEqual(gadget.REQUESTS, space.GADGET_REQUESTS)
        self.assertEqual((gadget.CODE_VA, gadget.CODE_SIZE, gadget.TABLE_SIZE), (0x151F680, 2048, 12800))
        self.assertEqual(gadget.TABLE_VA + gadget.TABLE_SIZE, space.BACKFIELD_VA)
        self.assertEqual(space.LINEUP_SLOT_VA[space.GADGET_REQUESTS[1][:2]], gadget.TABLE_VA)
        self.assertEqual(template.CODE_VA, gadget.CODE_VA)
        self.assertIn(gadget.OWNER, space.LATE_OWNERS)

    def test_the_classifier_is_the_qualified_one_byte_for_byte(self):
        """The qualified runtime (XBE 7963a1db, its code allocation sha b6d4c7fd) plus review F1's restore: the
        classifier and the post-builder substitution tail are the qualified bytes; only the restore marker's two
        stores, the restore routine and the position of the native jumps differ."""
        code = gadget.code_for(QUALIFIED_OFFSETS, QUALIFIED_GATE)
        self.assertEqual(len(code), gadget.CODE_SIZE)
        self.assertEqual(_sha(code), RUNTIME_CODE_SHA256)
        self.assertEqual(code[len(template.TEMPLATE):], bytes(gadget.CODE_SIZE - len(template.TEMPLATE)))
        if QUALIFIED_XBE.is_file():
            from mod_editor.core.nfl2k5_cave_oracle import XbeImage
            qualified = XbeImage(QUALIFIED_XBE.read_bytes()).read(gadget.CODE_VA, gadget.CODE_SIZE)
            self.assertEqual(_sha(qualified), QUALIFIED_CODE_SHA256)
            labels = template.LABELS
            self.assertEqual(code[labels["select_slot"]:labels["assign_if_fast"]],
                             qualified[QUALIFIED_SELECT_SLOT:QUALIFIED_ASSIGN])
            self.assertEqual(code[labels["scope_return"]:labels["tapped_ordinal"]],
                             qualified[QUALIFIED_SCOPE_RETURN:QUALIFIED_TAPPED])
        # The restore marker sits in the code allocation, zero on disc.
        at = template.LABELS["gadget_team"]
        self.assertEqual(code[at:at + 4], bytes(4))

    def test_only_the_recorded_fields_move_with_their_symbol(self):
        base = gadget.code_for(QUALIFIED_OFFSETS, QUALIFIED_GATE)
        for name, sites in template.SITES.items():
            with self.subTest(symbol=name):
                if name == "native_gate":
                    moved = gadget.code_for(QUALIFIED_OFFSETS, QUALIFIED_GATE + 0x40)
                else:
                    moved = gadget.code_for({**QUALIFIED_OFFSETS, name: QUALIFIED_OFFSETS[name] + 0x40},
                                            QUALIFIED_GATE)
                changed = {i for i in range(len(base)) if base[i] != moved[i]}
                self.assertTrue(changed and changed <= {at + k for at in sites for k in range(4)})
                for at in sites:
                    delta = (int.from_bytes(moved[at:at + 4], "little") - int.from_bytes(base[at:at + 4], "little"))
                    self.assertEqual(delta & 0xFFFFFFFF, 0x40)

    def test_hooks_enter_the_runtime_from_the_five_native_sites(self):
        (_, builder, builder_retail, builder_new), (_, ordinal, ordinal_retail, ordinal_new), \
            (_, store, store_retail, store_new), (_, audible, audible_retail, audible_new), \
            (_, check, check_retail, check_new) = gadget._hooks()
        self.assertEqual(audible, 0x9FB10)
        self.assertEqual(audible_retail, bytes.fromhex("e8bb8c0100"))      # call 0xB87D0 inside the audible 0x9FAF0
        self.assertEqual(audible + 5 + struct.unpack_from("<i", audible_new, 1)[0],
                         gadget.CODE_VA + template.LABELS["restore_after_audible"])
        self.assertEqual(check, 0x18A6EE)
        self.assertEqual(check_retail, bytes.fromhex("e84dddffff"))          # call 0x188440 in the snap path
        self.assertEqual(check + 5 + struct.unpack_from("<i", check_new, 1)[0],
                         gadget.CODE_VA + template.LABELS["available_or_kept"])
        self.assertEqual(store, 0x9F9CB)
        self.assertEqual(store_retail, bytes.fromhex("e8c08d0100"))          # call 0xB8790 inside 0x9F990
        self.assertEqual(store + 5 + struct.unpack_from("<i", store_new, 1)[0],
                         gadget.CODE_VA + template.LABELS["restore_after_store"])
        self.assertEqual((builder, ordinal), (0x18A641, 0xE7760))
        self.assertEqual(builder_retail, bytes.fromhex("e8aae3f5ff"))          # call 0xE89F0
        self.assertEqual(ordinal_retail, bytes.fromhex("53558b6c2410"))
        self.assertEqual(builder + 5 + struct.unpack_from("<i", builder_new, 1)[0],
                         gadget.CODE_VA + template.LABELS["scoped_builder"])
        self.assertEqual(ordinal_new[0], 0xE9)
        self.assertEqual(ordinal + 5 + struct.unpack_from("<i", ordinal_new, 1)[0],
                         gadget.CODE_VA + template.LABELS["tapped_ordinal"])
        self.assertEqual(ordinal_new[5:], b"\x90")

    @unittest.skipUnless(sys.platform.startswith("linux") and all(shutil.which(t) for t in ("as", "gcc", "ld", "nm", "objcopy")),
                         "GNU gcc/binutils (development only)")
    def test_the_checked_in_template_matches_its_sources(self):
        import subprocess
        if " 13.3" not in subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout.splitlines()[0]:
            self.skipTest("the template is pinned to gcc 13.3")
        import importlib.util
        spec = importlib.util.spec_from_file_location("gadget_play_build", ROOT / "tools/gadget_play/build.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        text = generator.generate()
        self.assertEqual((ROOT / "mod_editor/core/nfl2k5_gadget_play_code.py").read_text(encoding="utf-8"), text)


class ClassifierTests(unittest.TestCase):
    """The build-time test of 'this play hands one receiver slot the ball' (Codex's candidate tests)."""

    def body(self, recipient, taken_by=None):
        body = bytearray(ip.BODY_SIZE)
        field = ip.PLAY_BASE + 12
        body[ip.NODE_BASE:ip.NODE_BASE + 8] = bytes([0x13, 0, 0, 0, recipient, 0, 0, 0])
        struct.pack_into("<Ii", body, field - 4, 1, ip.NODE_BASE - field + 1)
        if taken_by is not None:
            field += 8 * taken_by
            body[ip.NODE_BASE + 8:ip.NODE_BASE + 16] = bytes([0x16, 0, 0, 0, 1, 2, 3, 4])
            struct.pack_into("<Ii", body, field - 4, 1, ip.NODE_BASE + 8 - field + 1)
        return bytes(body)

    def test_a_handoff_counts_only_with_a_take_in_the_receivers_own_script(self):
        for target, taker, expected in ((8, 8, {8}), (0x58, 8, {8}), (8, 7, set()), (8, None, set()),
                                        (255, 8, set())):
            with self.subTest(target=target, taker=taker):
                self.assertEqual(gadget._choose(self.body(target, taker), 0)[1], expected)

    def test_the_table_copy_keeps_every_assignment_and_operand(self):
        body = self.body(10, 10)
        _, carriers, program = gadget._choose(body, 0)
        self.assertEqual(carriers, {10})
        expected = struct.pack("<II", 0, 1) + body[ip.NODE_BASE:ip.NODE_BASE + 8]
        expected += bytes(9 * 4) + struct.pack("<I", 1) + body[ip.NODE_BASE + 8:ip.NODE_BASE + 16]
        self.assertEqual(program, expected)
        damaged = bytearray(body)
        damaged[ip.NODE_BASE + 15] ^= 1
        self.assertNotEqual(gadget._choose(bytes(damaged), 0)[2], program)


class QualifiedCandidateTests(unittest.TestCase):
    """The Studio owner on the preview the 20 CPU games used: the qualified table, classifier and hook entries, plus
    the restore."""

    def test_the_owner_on_the_preview_carries_the_qualified_table_and_classifier(self):
        if not QUALIFIED_XBE.is_file():
            self.skipTest("the qualified candidate executable is absent")
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        source, books = _require_disc(PREVIEW_DISC, PREVIEW_XBE_SHA256)
        qualified = QUALIFIED_XBE.read_bytes()
        self.assertEqual(_sha(qualified), QUALIFIED_XBE_SHA256)
        self.assertEqual(gadget.status(source), "retail")
        result, receipt = gadget.apply(source, books)
        self.assertEqual((receipt["table_bytes"], receipt["eligible_links"], receipt["left_out_books"]), (12800, 111, []))
        self.assertEqual(gadget.read_settings(result, books)["status"], "applied")
        mine, theirs = XbeImage(result), XbeImage(qualified)
        self.assertEqual(_sha(mine.read(gadget.TABLE_VA, gadget.TABLE_SIZE)), QUALIFIED_TABLE_SHA256)
        self.assertEqual(theirs.read(gadget.TABLE_VA, gadget.TABLE_SIZE), mine.read(gadget.TABLE_VA, gadget.TABLE_SIZE))
        labels = template.LABELS
        self.assertEqual(mine.read(gadget.CODE_VA + labels["select_slot"], QUALIFIED_ASSIGN - QUALIFIED_SELECT_SLOT),
                         theirs.read(gadget.CODE_VA + QUALIFIED_SELECT_SLOT, QUALIFIED_ASSIGN - QUALIFIED_SELECT_SLOT))
        # Outside the code allocation and the hook sites, the two executables differ only in the section digests and
        # the allocator seals (the code bytes changed): every other byte of the 12 MB file is the same.
        changed = [i for i in range(len(result)) if result[i] != qualified[i]]
        code = mine.offset(gadget.CODE_VA, gadget.CODE_SIZE)
        sites = [mine.offset(va, len(retail)) for _l, va, retail, _p in gadget._hooks()]
        outside = [i for i in changed if not code <= i < code + gadget.CODE_SIZE
                   and not any(at <= i < at + 6 for at in sites)]
        self.assertLess(len(outside), 200)
        # Off again: the sites are retail, the slots stay reserved and empty; on again: the same executable.
        off, _ = gadget.remove(result)
        self.assertEqual(gadget.status(off), "retail")
        self.assertEqual(gadget.apply(off, books)[0], result)


class ReleasedV09Tests(unittest.TestCase):
    def setUp(self):
        self.source, self.books = _require_disc(V09_DISC, V09_XBE_SHA256)

    def test_v09_takes_the_fixed_slots_before_or_after_the_cards(self):
        from mod_editor.core import nfl2k5_backfield_cards as cards, nfl2k5_lineup_roles as lineup
        self.assertEqual((gadget.status(self.source), cards.status(self.source), lineup.status(self.source)),
                         ("retail", "retail", "applied"))
        gadget.preflight(self.source)
        first, receipt = gadget.apply(self.source, self.books)
        rows = {(r["owner"], r["kind"]): r["va"] for r in space.layout(first)["allocations"]}
        self.assertEqual(rows[(gadget.OWNER, "code")], 0x151F680)
        self.assertEqual(rows[(gadget.OWNER, "read_only")], 0x151FE80)
        gadget_then_cards, _ = cards.apply(first)
        cards_then_gadget, _ = gadget.apply(cards.apply(self.source)[0], self.books)
        self.assertEqual(gadget_then_cards, cards_then_gadget)
        self.assertEqual((gadget.status(gadget_then_cards, self.books), cards.status(gadget_then_cards),
                          lineup.status(gadget_then_cards)), ("applied", "applied", "applied"))
        for row in space.layout(self.source)["allocations"]:
            if row["owner"] != space.DIRECTORY_OWNER:
                self.assertIn(row, space.layout(gadget_then_cards)["allocations"])
        self.assertEqual(receipt["eligible_links"], 111)

    def test_changed_books_make_it_stale_and_a_rebuild_refreshes_it_in_place(self):
        installed, _ = gadget.apply(self.source, self.books)
        rows = gadget.compile_table(self.books, 0)[2]
        cle = next(r for r in rows if r["name"] == "CLE")
        form, play, _slot = cle["eligible_links"][0]
        raw = bytearray(self.books[str(cle["asset"])])
        # Change one operand byte of the carrier's own take-handoff node (still a 0x16 take, so still a gadget play,
        # but no longer the script in the table). Chain fields are self-relative: node = field + value - 1.
        field = 32 + ip.PLAY_BASE + play * ip.PLAY_SIZE + 12 + 8 * _slot
        chain = field + struct.unpack_from("<i", raw, field)[0] - 1
        count = struct.unpack_from("<I", raw, field - 4)[0] & 15
        take = next(chain + 8 * k for k in range(count) if raw[chain + 8 * k] == 0x16)
        raw[take + 5] ^= 1
        books = {**self.books, str(cle["asset"]): bytes(raw)}
        self.assertEqual(gadget.read_settings(installed, books)["stale"], ["books"])
        refreshed, receipt = gadget.apply(installed, books)
        self.assertTrue(receipt["refreshed"])
        self.assertEqual(gadget.status(refreshed, books), "applied")
        self.assertEqual(refreshed, gadget.apply(self.source, books)[0])
        self.assertEqual(space.layout(refreshed)["allocations"], space.layout(installed)["allocations"])

    def test_a_full_table_leaves_out_whole_shared_books_first(self):
        with mock.patch.object(gadget, "TABLE_SIZE", 12000):
            table, _offsets, _rows, left = gadget.fit_table(self.books, 0)
        self.assertLessEqual(len(table), 12000)
        self.assertEqual(left, ["reference"])

    def test_refusals(self):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        try:
            retail = retail_bytes()
        except unittest.SkipTest:
            retail = None
        if retail is not None:
            with self.assertRaisesRegex(gadget.GadgetPlayError, "SPECIAL situational lineup roles|scale-out"):
                gadget.apply(retail, self.books)
        installed, _ = gadget.apply(self.source, self.books)
        # Another owner rewrote one hook site (and resealed the section): refused before any write.
        foreign = gadget._write_sites(installed, [("other", gadget.ORDINAL_SITE, gadget.ORDINAL_RETAIL)])
        self.assertEqual(gadget.status(foreign), "foreign")
        with self.assertRaises(gadget.GadgetPlayError):
            gadget.apply(foreign, self.books)
        with self.assertRaises(gadget.GadgetPlayError):
            gadget.preflight(foreign)
        with self.assertRaises(gadget.GadgetPlayError):
            gadget.remove(foreign)
        # Native lineup code the runtime's stack offsets rely on, changed by someone else: refused before any write.
        changed = gadget._write_sites(self.source, [("other", 0x18A62E, b"\x90")])
        with self.assertRaisesRegex(gadget.GadgetPlayError, "native lineup code"):
            gadget.apply(changed, self.books)
        with self.assertRaisesRegex(gadget.GadgetPlayError, "native lineup code"):
            gadget.preflight(changed)


class BuildWiringTests(unittest.TestCase):
    """The option rides with the SPECIAL rows in the presets and recipes; the build refuses what it cannot do."""

    def test_presets_turn_it_on_with_the_special_rows_only(self):
        from mod_editor.core import mod_build as build
        for name in build.PRESETS:
            with self.subTest(preset=name):
                plan = build.apply_preset(build.BuildPlan("a.iso", "b.iso"), name)
                self.assertEqual(plan.gadget_play, plan.depth_chart_rows)
        self.assertTrue(build.apply_preset(build.BuildPlan("a.iso", "b.iso"), "softdrink_experimental").gadget_play)
        self.assertFalse(build.apply_preset(build.BuildPlan("a.iso", "b.iso", console_memory=64),
                                            "softdrink_experimental").gadget_play)
        self.assertIn("gadget_play", build.V09_UPDATE_CHOICES)
        self.assertTrue(build.v09_disc_update("a.iso", "b.iso", gadget_play=True).gadget_play)
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("gadget_play", settings.FEATURE_KEYS)

    def test_the_build_refuses_it_without_the_special_rows(self):
        from dataclasses import replace
        from mod_editor.core import mod_build as build
        source = Path(os.environ.get("NFL2K5_RETAIL_XISO", "") or "missing")
        if not source.is_file():
            self.skipTest("the retail disc is absent")
        plan = build.apply_preset(build.BuildPlan(str(source), str(ROOT / "never-written.xiso.iso")), "softdrink_experimental")
        with self.assertRaisesRegex(ValueError, "needs the SPECIAL depth chart rows"):
            build.preflight_plan(replace(plan, depth_chart_rows=False))
        self.assertFalse((ROOT / "never-written.xiso.iso").exists())

    def test_the_single_setting_edit_of_a_built_disc(self):
        """Add the rule to a copy of an already-built standard disc (CLI edit-gadget-play, as edit-sim-qb does for
        the QB option): only default.xbe changes, its table from the books on that disc. Preflight writes nothing."""
        from mod_editor.core import mod_build as build
        from tools import nfl2k5_modpack as cli
        plan = build.gadget_disc_edit("built.iso", "copy.iso")
        self.assertIs(type(plan), build._InstalledGadgetEdit)
        self.assertTrue(plan.gadget_play and build._only_gadget_changes(plan))
        self.assertFalse(build._only_gadget_changes(build.BuildPlan("built.iso", "copy.iso", gadget_play=True)))
        with mock.patch.object(build, "build", return_value={}) as run, \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
            self.assertEqual(cli.main(["edit-gadget-play", "--source", "a.iso", "--out", "b.iso", "--mode", "on", "--json"]), 0)
        self.assertIs(type(run.call_args.args[0]), build._InstalledGadgetEdit)
        disc = Path(os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC", "") or "missing")
        if not disc.is_file():
            self.skipTest("the reviewed private standard disc is absent")
        source, books = _disc(str(disc))
        target = ROOT / "never-written-gadget.xiso.iso"
        receipt = build.preflight_plan(build.gadget_disc_edit(str(disc), str(target)))
        self.assertFalse(target.exists())
        expected, _ = gadget.apply(source, books)
        self.assertEqual(receipt["gadget_source_update"]["result_sha256"], _sha(expected))
        self.assertEqual(receipt["gadget_source_update"]["source_state"], "retail")

    def test_an_installed_rule_is_replayed_and_an_executable_only_target_is_refused(self):
        """As with every installed owner, a rebuild keeps the rule (the Build tab greys it out); a build that cannot
        read the disc's books never installs it."""
        import tempfile
        from dataclasses import replace
        from mod_editor.core import mod_build as build
        source, books = _require_disc(V09_DISC, V09_XBE_SHA256)
        installed, _ = gadget.apply(source, books)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "default.xbe"
            target.write_bytes(installed)
            plan = build.apply_preset(build.BuildPlan(str(V09_DISC), str(target)), "softdrink_experimental")
            receipt = {"steps": [], "result": {}}
            build._apply_gadget_play(replace(plan, gadget_play=False), target, receipt, lambda *_: None)
            self.assertEqual((target.read_bytes(), receipt["result"]), (installed, {}))
            target.write_bytes(source)
            build._apply_gadget_play(replace(plan, gadget_play=False), target, receipt, lambda *_: None)
            self.assertEqual(target.read_bytes(), source)
            with self.assertRaisesRegex(ValueError, "build a disc image"):
                build._apply_gadget_play(plan, target, receipt, lambda *_: None)
        # Review F6: the Studio says so where the box is.
        self.assertIn("keeps it when you build on it again with this box unticked", gadget.HELP_TEXT)
        self.assertIn("edit-gadget-play --mode off", gadget.HELP_TEXT)
        # On a disc the installed rule is refreshed for the disc's books even when the plan does not ask for it.
        with mock.patch.object(build.tt, "is_disc_image", return_value=True), \
                mock.patch.object(build, "_xbe_bytes", return_value=installed), \
                mock.patch.object(build, "_gadget_resources", return_value=books), \
                mock.patch.object(build, "_write_xbe_bytes") as write:
            receipt = {"steps": [], "result": {}}
            build._apply_gadget_play(replace(plan, gadget_play=False), Path("disc.iso"), receipt, lambda *_: None)
            self.assertEqual(receipt["result"]["gadget_play"], "applied")
            self.assertTrue(receipt["steps"][-1]["replayed_installed_option"])
            write.assert_not_called()


# ---------------------------------------------------------------------------------------------------------------------
# The game's own selection and lineup code under Unicorn (Codex's native_proof/guard_proof harness, condensed).

BOOKS = (0xB75A40, 0xB88DD0)
SIDES = (0xE5FC20, 0xE5FC60)
DEPTH = (0xB336F4, 0xB33A28)
CHOICE = (0xAABCE0, 0xAABDB0)
SOURCE = 0x2110000
SIT, DRIVE, MARK = 0x2190000, 0x2191000, 0x2192000


def _have_unicorn() -> bool:
    try:
        import unicorn  # noqa: F401
        return True
    except ImportError:
        return False


class Native:
    def __init__(self, payload: bytes, body: bytes):
        from tests.mod_editor.test_b780_sub1_lineup_roles import machine
        m = machine(payload, body)
        m.put(0xE5FF80, 6)
        m.put(0xE602B4, 4)
        m.put(0xE602B8, 12)
        m.put(0xE602EC, SIT)
        m.put(SIT + 4, 1)
        m.f32(SIT + 0x28, 10 * 91.44)
        m.put(DRIVE + 12, MARK)
        m.f32(MARK + 4, 1)
        for i, side in enumerate(SIDES):
            m.put(side, SIDES[1 - i])
            m.put(side + 8, DRIVE)
            m.put(side + 12, CHOICE[i])
            m.put(side + 0x20, BOOKS[i])
        self.m = m
        self.observe_slot, self.observations = None, []

        def pick(_uc, _pc, _size, _user):
            if self.observe_slot is None:
                return
            sp = m.reg("ESP")
            if m.get(sp + 4) == self.observe_slot:
                self.observations.append((m.get(sp), m.get(sp + 16), m.get(sp + 20)))

        m.uc.hook_add(m.u.UC_HOOK_CODE, pick, begin=0xE8B20, end=0xE8B20)

    def words(self, va, n):
        return struct.unpack("<" + "I" * n, self.m.uc.mem_read(va, n * 4))

    def club(self, club, side, human):
        m = self.m
        team = m.team_base + club * 500
        s = SIDES[side]
        m.put(s + 0x1C, team)
        m.put(s + 0x30, int(human))
        m.put(s + 0x38, 0)
        m.put(0xE5775C + 4 * club, int(human))
        m.put(0xE60280, s)
        m.put(0xE60284, SIDES[1 - side])
        m.call(0xE80D0, ecx=team, edx=DEPTH[side], args=(0, 0), budget=2000000)
        assert m.call(0x1891B0, ecx=s) == int(human), "controller mode did not reach the native predicate"

    def load(self, raw, side):
        self.m.uc.mem_write(SOURCE, raw[32:])
        self.m.call(0x161E30, ecx=SOURCE, edx=side, budget=1500000)
        self.m.call((0x777E0, 0x77800)[side], ecx=BOOKS[side])

    def menu(self, side, form, link):
        m, book = self.m, BOOKS[side]
        f = m.call(0xE0660, ecx=book, edx=form.index, budget=32)
        aux = m.call(0xE0830, ecx=book, edx=form.index, budget=32)
        c = m.call(0xE05E0, ecx=book, edx=m.get(aux + 72) & 63, budget=32)
        p = m.call(0xE13F0, ecx=book, edx=link.link_index, args=(f,), budget=300)
        assert p == book + ip.PLAY_BASE + link.play_index * ip.PLAY_SIZE, "native menu returned another play"
        return c, f, p

    def commit(self, side, c, f, p, *, human=False, secondary=None, offense=True):
        """Publish the selection the way the game does: the user's play call, the CPU's offense choice, or (for kicking
        and defensive formations, offense=False) the defensive chooser's publication at 0x20B977."""
        m, s = self.m, SIDES[side]
        m.put(0xE602B8, 11)
        m.put(0xE60280, s if offense else SIDES[1 - side])
        m.put(0xE60284, SIDES[1 - side] if offense else s)
        second = p if secondary is None else secondary
        if not offense:
            m.reg("ESP", m.STACK)
            m.reg("EBX", s)
            m.reg("EBP", second)
            m.reg("EDI", c)
            m.reg("ESI", f)
            m.put(m.STACK + 0x10, p)
            m.put(m.STACK + 0x14, 0)
            m.uc.emu_start(0x20B977, 0x20B9A0, count=100)
            assert m.reg("EIP") == 0x20B9A0, "defensive selection did not publish"
        elif human:
            menu = MARK + 0x400
            for off, value in ((0x4C, c), (0x50, f), (0x54, p), (0x58, p), (0x5C, second)):
                m.put(menu + off, value)
            m.call(0xAE65C, esi=menu, stop=0x2074A8, budget=1000)
            second = p
        else:
            for i, value in enumerate((c, f, p, second)):
                m.put(0xBD8094 + 4 * i, value)
            m.call(0x15318E, esi=s, stop=0x2074A8, budget=1000)
        assert self.words(CHOICE[side] + 4, 4) == (c, f, p, second), "native commit mismatch"

    def line(self, side, offense=True):
        """The snap path: 0x9F3B7 -> 0x89624 -> 0x18AD10 -> 0x18A5D0 -> the builder call 0x18A641 (the offense's build);
        offense=False: the defense's build, entered at 0x89624 with the sides swapped."""
        m = self.m
        m.put(0xE602B8, 12)
        m.put(0xE60280, SIDES[side] if offense else SIDES[1 - side])
        m.put(0xE60284, SIDES[1 - side] if offense else SIDES[side])
        m.call(0x9F3B7 if offense else 0x89624, ecx=1, ebx=1, stop=0x18A646, budget=300000)
        return self.words(m.reg("ESP") + 0x74, 11)

    def line_with_picker(self, side, slot, offense=True):
        self.observe_slot, self.observations = slot, []
        try:
            return self.line(side, offense), list(self.observations)
        finally:
            self.observe_slot = None

    def gad(self, side):
        m = self.m
        temp = MARK + 32
        list_id = m.call(0xE7530, eax=9, edx=7, esi=temp, budget=100)
        row = m.get(temp)
        if row >= m.call(0xE75A0, ecx=list_id, edx=DEPTH[side], budget=100):
            return 0
        return m.call(0xE7810, eax=list_id, ecx=BOOKS[side], args=(DEPTH[side], row), budget=15000)


def expectation(n: Native, side, slot, normal, observations, gate, player):
    """What the rule must produce from the game's own lineup (Codex's oracle)."""
    m = n.m
    if not observations:
        return normal, "already_filled"
    category, voluntary, kind = observations[0]
    if voluntary or kind != 9:
        return normal, "voluntary_substitution"
    if not player:
        return normal, "no_gadget"
    if m.get(player + 32) & 0x80000000:
        return normal, "injured"
    if not m.call(gate, ecx=DEPTH[side], edx=player, args=(category, slot, 3), budget=5000):
        return normal, "gate_denied"
    if not all(normal):
        return normal, "incomplete_line"
    if player == normal[slot]:
        return normal, "already_carrier"
    if player in normal:
        return normal, "on_field_elsewhere"
    if m.uc.mem_read(player + 0x36, 1)[0] < m.uc.mem_read(normal[slot] + 0x36, 1)[0]:
        return normal, "slower_than_original"
    expected = list(normal)
    expected[slot] = player
    return tuple(expected), "changed"


@contextmanager
def poke(native: Native, address, data):
    old = bytes(native.m.uc.mem_read(address, len(data)))
    native.m.uc.mem_write(address, data)
    try:
        yield
    finally:
        native.m.uc.mem_write(address, old)


@unittest.skipUnless(_have_unicorn(), "Python unicorn")
class NativeLineupTests(unittest.TestCase):
    """Before (the released v0.9 executable) and after (the same with the gadget rule), same roster and books."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_coach_staff as staff, nfl2k5_roster_records as roster
        source, books = _require_disc(V09_DISC, V09_XBE_SHA256)
        with roster._outer_image()(V09_DISC) as image:
            body = image.read_entry(5)[32:]
        installed, cls.receipt = gadget.apply(source, books)
        cls.books, cls.gate = books, int(cls.receipt["native_gate"], 16)
        cls.links = {b["asset"]: {(f, p): s for f, p, s in b["eligible_links"]} for b in cls.receipt["books"]}
        cls.before, cls.after = Native(source, body), Native(installed, body)
        cls.clubs = {c.book: c.index for c in staff.clubs()}

    def setup_book(self, asset, side=0, human=False):
        book = ip.parse_playbook_resource(self.books[str(asset)], asset_id=str(asset))
        for n in (self.before, self.after):
            n.load(self.books[str(asset)], side)
            n.club(self.clubs.get(book.book_name, self.clubs["CLE"]), side, human)
        return book

    def select(self, book, form, play, side=0, human=False, secondary=None, offense=True):
        f = book.formations[form]
        link = next(i for i in f.play_links if i.play_index == play)
        chosen = self.before.menu(side, f, link)
        self.assertEqual(chosen, self.after.menu(side, f, link))
        for n in (self.before, self.after):
            n.commit(side, *chosen, human=human if offense else False, secondary=secondary, offense=offense)
        return chosen

    def outcome(self, side, slot):
        normal, observations = self.before.line_with_picker(side, slot)
        want, reason = expectation(self.before, side, slot, normal, observations, self.gate, self.before.gad(side))
        got = self.after.line(side)
        self.assertEqual(got, want, reason)
        return normal, got, reason

    def test_every_link_of_four_books_on_both_controls(self):
        """ATL (the live insertion), CLE (five gadget links), GB (WB sweeps) and TEN (the FC2 book), home side:
        every formation-play link, CPU and user. Only a table link may change a lineup, and only its carrier slot."""
        reasons = {}
        for asset in (308, 314, 319, 341):
            for human in (False, True):
                book = self.setup_book(asset, 0, human)
                lib_type = __import__("mod_editor.core.nfl2k5_play_library", fromlist=["x"])
                for form in book.formations:
                    typ = lib_type.formation_record(self.books[str(asset)][32:], form.index).type_code
                    if typ in (4, 5, 6, 7, 9, 11, 13):
                        continue  # kicking and defensive formations: never offense on this path
                    for link in form.play_links:
                        self.select(book, form.index, link.play_index, 0, human)
                        slot = self.links[asset].get((form.index, link.play_index))
                        if slot is None:
                            normal = self.before.line(0)
                            got = self.after.line(0)
                            self.assertEqual(got, normal, (asset, form.index, link.play_index))
                            reasons["ineligible"] = reasons.get("ineligible", 0) + 1
                            continue
                        normal, got, reason = self.outcome(0, slot)
                        delta = [j for j in range(11) if normal[j] != got[j]]
                        self.assertIn(delta, ([], [slot]))
                        reasons[reason] = reasons.get(reason, 0) + 1
        self.assertGreater(reasons.get("ineligible", 0), 1000)
        self.assertGreater(sum(v for k, v in reasons.items() if k != "ineligible"), 0)

    @unittest.skipUnless(os.environ.get("NFL2K5_GADGET_FULL_SWEEP") == "1", "slow (about 10 min): set NFL2K5_GADGET_FULL_SWEEP=1")
    def test_every_link_of_all_37_books_home_and_away_cpu_and_user(self):
        """Review F4: the all-books sweep, in the repo. Every formation-play link of the 37 books, both sides, CPU and
        user; offensive formations through the offense's snap build, kicking and defensive formations through the
        defense's (Codex's convention). Only a table link may change a lineup, only at its carrier slot, exactly as the
        oracle says; everything else is the game's lineup byte for byte."""
        from collections import Counter
        from mod_editor.core import nfl2k5_play_library as lib
        totals = Counter()
        for b in self.receipt["books"]:
            asset = b["asset"]
            raw = self.books[str(asset)]
            for side in (0, 1):
                for human in (False, True):
                    book = self.setup_book(asset, side, human)
                    for form in book.formations:
                        offense = lib.formation_record(raw[32:], form.index).type_code not in (4, 5, 6, 7, 9, 11, 13)
                        for link in form.play_links:
                            self.select(book, form.index, link.play_index, side, human, offense=offense)
                            slot = self.links[asset].get((form.index, link.play_index)) if offense else None
                            if slot is None:
                                self.assertEqual(self.after.line(side, offense), self.before.line(side, offense),
                                                 (asset, form.index, link.play_index, side, human))
                                totals["unchanged" if offense else "kick_or_defense_unchanged"] += 1
                                continue
                            normal, observations = self.before.line_with_picker(side, slot)
                            want, reason = expectation(self.before, side, slot, normal, observations, self.gate,
                                                       self.before.gad(side))
                            got = self.after.line(side)
                            self.assertEqual(got, want, (asset, form.index, link.play_index, side, human, reason))
                            self.assertIn([j for j in range(11) if normal[j] != got[j]], ([], [slot]))
                            totals[reason] += 1
        self.assertEqual(totals["changed"] + totals["on_field_elsewhere"] + totals["voluntary_substitution"]
                         + totals["already_carrier"] + totals["slower_than_original"], 444)
        self.assertGreater(totals["changed"], 200)
        self.assertGreater(totals["unchanged"], 60000)
        self.assertGreater(totals["kick_or_defense_unchanged"], 1000)

    def test_the_gadget_player_takes_the_carrier_slot_and_the_rules_limits_hold(self):
        """Cleveland's play 147 in formation 3 hands slot 8 the ball; the GAD's Speed decides, an injury refuses."""
        book = self.setup_book(314)
        self.select(book, 3, 147)
        slot = self.links[314][(3, 147)]
        normal, observations = self.before.line_with_picker(0, slot)
        player = self.before.gad(0)
        self.assertTrue(player and all(normal) and player not in normal and observations and not observations[0][1])
        for normal_speed, gad_speed in ((64, 63), (64, 64), (64, 65), (0, 0), (255, 254), (128, 127), (127, 128)):
            with self.subTest(normal=normal_speed, gad=gad_speed), ExitStack() as stack:
                for n in (self.before, self.after):
                    stack.enter_context(poke(n, normal[slot] + 0x36, bytes([normal_speed])))
                    stack.enter_context(poke(n, player + 0x36, bytes([gad_speed])))
                _, got, reason = self.outcome(0, slot)
                self.assertEqual(reason, "changed" if gad_speed >= normal_speed else "slower_than_original")
                self.assertEqual(got[slot] == player, gad_speed >= normal_speed)
        with ExitStack() as stack:
            for n in (self.before, self.after):
                stack.enter_context(poke(n, normal[slot] + 0x36, b"\x00"))
                stack.enter_context(poke(n, player + 32, struct.pack("<I", n.m.get(player + 32) | 1 << 31)))
            self.assertEqual(self.outcome(0, slot)[2], "injured")
        # A different secondary play (the CPU's fallback differs from its primary) keeps the game's lineup.
        c, f, p = self.select(book, 3, 147)
        for n in (self.before, self.after):
            n.commit(0, c, f, p, secondary=p + 96)
        self.assertEqual(self.after.line(0), self.before.line(0))

    def _memory(self, native):
        """Every mapped byte except the stack page (where the builder's output array lives)."""
        out = {}
        for begin, end, _perms in native.m.uc.mem_regions():
            if not 0x3000000 <= begin < 0x3010000:
                out[begin] = bytes(native.m.uc.mem_read(begin, end - begin + 1))
        return out

    def _differences(self):
        import numpy
        a, b = self._memory(self.before), self._memory(self.after)
        self.assertEqual(sorted(a), sorted(b))
        found = set()
        for begin in a:
            size = min(len(a[begin]), len(b[begin]))   # the image region grows by the gadget pool pages
            left, right = numpy.frombuffer(a[begin][:size], numpy.uint8), numpy.frombuffer(b[begin][:size], numpy.uint8)
            found.update(int(begin + i) for i in numpy.nonzero(left != right)[0])
            found.update(range(begin + size, begin + max(len(a[begin]), len(b[begin]))))
        return found - set(range(MARK + 32, MARK + 36))   # the harness's own scratch word (Native.gad, before only)

    def test_a_substitution_lasts_one_snap_and_leaves_no_state_behind(self):
        """Review F1: the rule writes only into one builder call's output (on the stack). After a substituted snap,
        nothing the game keeps (team and player records, depth contexts, the published selection, the books) differs
        from the same game without the rule; so the next normal huddle snap, the same gadget play called again, and the
        type-12 set-up path (used outside the snap path) all come from a fresh build with the game's own result."""
        book = self.setup_book(314)
        baseline = self._differences()          # the installed rule's own bytes (code, table, hooks, allocator)
        self.select(book, 3, 147)
        slot = self.links[314][(3, 147)]
        normal, got, reason = self.outcome(0, slot)
        self.assertEqual(reason, "changed")
        self.assertEqual(got[slot], self.before.gad(0))
        # Nothing outside the stack was written differently, except the restore marker (review F1), which now names
        # the offense side and is cleared by its next play-call build.
        marker = gadget.CODE_VA + template.LABELS["gadget_team"]
        self.assertLessEqual(self._differences() - baseline, self._runtime_words())
        self.assertEqual(self._marker(self.after), SIDES[0])
        # The next snap through a normal huddle: a non-gadget play in the same formation, then another formation.
        others = [link.play_index for link in book.formations[3].play_links if (3, link.play_index) not in self.links[314]]
        for play in others[:3]:
            self.select(book, 3, play)
            self.assertEqual(self.after.line(0), self.before.line(0))
            self.assertEqual(self._marker(self.after), 0)
        self.select(book, 0, book.formations[0].play_links[0].play_index)
        self.assertEqual(self.after.line(0), self.before.line(0))
        # The same gadget play called again: a fresh decision, the GAD in again; then a normal snap again.
        self.select(book, 3, 147)
        self.assertEqual(self.outcome(0, slot)[2], "changed")
        self.select(book, 3, others[0])
        self.assertEqual(self.after.line(0), self.before.line(0))
        # The type-12 set-up build right after a substituted snap keeps the game's lineup.
        self.select(book, 3, 147)
        self.assertEqual(self.outcome(0, slot)[2], "changed")
        lines = []
        for n in (self.before, self.after):
            m, root = n.m, BOOKS[0]
            form = m.call(0xE0660, ecx=root, edx=3)
            category = m.call(0xE05E0, ecx=root, edx=m.get(m.call(0xE0830, ecx=root, edx=3, budget=32) + 72) & 63)
            m.reg("ESP", m.STACK)
            m.reg("ECX", SIDES[0])
            m.reg("EDX", category)
            m.uc.mem_write(m.STACK, struct.pack("<6I", form, m.STACK + 0x80, 0, 0, 1, 0))
            m.uc.emu_start(0x18B184, 0x18A646, count=300000)
            self.assertEqual(m.reg("EIP"), 0x18A646)
            lines.append(n.words(m.reg("ESP") + 0x74, 11))
        self.assertEqual(lines[0], lines[1])
        self.assertLessEqual(self._differences() - baseline, self._runtime_words())

    def _marker(self, native):
        return native.m.get(gadget.CODE_VA + template.LABELS["gadget_team"])

    def _word(self, native, label):
        return native.m.get(gadget.CODE_VA + template.LABELS[label])

    @staticmethod
    def _runtime_words():
        """The runtime's three RAM words (restore marker, benched receiver, his one-build grace)."""
        return set(range(gadget.CODE_VA + template.LABELS["gadget_team"], gadget.CODE_VA + template.LABELS["gadget_grace"] + 4))

    def test_the_restore_marker_follows_the_substitution(self):
        """Review F1: a substitution marks the offense side; the next play-call offense build clears the mark; a
        slower GAD (no substitution) leaves no mark."""
        book = self.setup_book(314)
        slot = self.links[314][(3, 147)]
        others = [link.play_index for link in book.formations[3].play_links if (3, link.play_index) not in self.links[314]]
        self.select(book, 3, 147)
        self.assertEqual(self.outcome(0, slot)[2], "changed")
        self.assertEqual(self._marker(self.after), SIDES[0])
        benched = self.before.line(0)[slot]
        self.assertEqual(self._word(self.after, "gadget_benched"), benched)
        self.select(book, 3, others[0])
        self.after.line(0)
        self.assertEqual(self._marker(self.after), 0)
        # The next play-call build of that side spends the benched receiver too and grants no grace: it judges every
        # pick the game's own way (only the restore's rebuild, with the offense on the field, graces him).
        self.assertEqual((self._word(self.after, "gadget_benched"), self._word(self.after, "gadget_grace")), (0, 0))
        self.select(book, 3, 147)
        native = self.before.line(0)
        player = self.before.gad(0)
        with ExitStack() as stack:
            for n in (self.before, self.after):
                stack.enter_context(poke(n, native[slot] + 0x36, b"\x50"))
                stack.enter_context(poke(n, player + 0x36, b"\x4f"))
            self.assertEqual(self.outcome(0, slot)[2], "slower_than_original")
            self.assertEqual(self._marker(self.after), 0)

    def _skip(self, native, address, pop=0, record=None):
        """Make a native routine return at once (callee pops ``pop`` bytes); ``record`` gets its registers and args."""
        m = native.m

        def hook(_uc, _pc, _size, _user):
            sp = m.reg("ESP")
            if record is not None:
                record.append(dict(pc=_pc, ecx=m.reg("ECX"), edx=m.reg("EDX"), esp=sp,
                                   args=struct.unpack("<4I", bytes(m.uc.mem_read(sp + 4, 16)))))
            m.reg("EIP", m.get(sp))
            m.reg("ESP", sp + 4 + pop)

        return m.uc.hook_add(m.u.UC_HOOK_CODE, hook, begin=address, end=address)

    def test_the_restore_rebuilds_the_offense_lineup_after_a_substitution_only(self):
        """Review F1: when 0x9F990 stores the next play for the offense whose last build substituted (no-huddle,
        CPU re-pick), or the offense audible 0x9FAF0 sets it, the restore runs the play-call offense build exactly as 0x89590 does (0x18AD10 with
        the side, its record +4 and the two packed situation values) and that build gives the game's own eleven for
        the new play. The marked side's first store spends the mark. Any other store (no mark, another side's mark,
        the marked side on defense, the huddle play call 0x2074BC that 0x89590 follows) only runs 0xB8790."""
        book = self.setup_book(314)
        slot = self.links[314][(3, 147)]
        others = [link.play_index for link in book.formations[3].play_links if (3, link.play_index) not in self.links[314]]
        restore = gadget.CODE_VA + template.LABELS["restore_after_store"]
        audible = gadget.CODE_VA + template.LABELS["restore_after_audible"]
        marker = gadget.CODE_VA + template.LABELS["gadget_team"]
        m = self.after.m
        sync, builds = [], []
        hooks = [self._skip(self.after, 0xB8790, record=sync), self._skip(self.after, 0xB87D0, record=sync),
                 self._skip(self.after, 0x18AD10, pop=0x10, record=builds)]
        try:
            no_huddle, huddle = 0xA24EC, 0x2074C1   # 0x9F990's return from the no-huddle handler / the play call
            cases = [(mark, offense, caller, expect, left, entry, displaced)
                     for mark, offense, caller, expect, left in (
                         (SIDES[0], SIDES[0], no_huddle, True, 0), (SIDES[0], SIDES[0], 0xA33F9, True, 0),
                         (0, SIDES[0], no_huddle, False, 0), (SIDES[1], SIDES[0], no_huddle, False, SIDES[1]),
                         (SIDES[0], SIDES[1], no_huddle, False, 0), (SIDES[0], SIDES[0], huddle, False, 0))
                     for entry, displaced in ((restore, 0xB8790), (audible, 0xB87D0))
                     if not (entry == audible and caller == huddle)]   # the huddle play call never reaches the audible
            for mark, offense, caller, expect, left, entry, displaced in cases:
                with self.subTest(mark=hex(mark), offense=hex(offense), caller=hex(caller), entry=hex(displaced)):
                    sync.clear(), builds.clear()
                    m.put(marker, mark)
                    m.put(0xE60280, offense)
                    # 0x9F990's (and 0x9FAF0's) frame at the hooked call: EDI, ESI, EBX pushed, then its return address.
                    m.call(entry, ecx=SIDES[0], edx=0x1234, esi=SIDES[0], args=(0x1234, SIDES[0], 0x11111111, caller))
                    self.assertEqual([call["pc"] for call in sync], [displaced])
                    self.assertEqual(len(sync), 1)
                    self.assertEqual((sync[0]["ecx"], sync[0]["edx"]), (SIDES[0], 0x1234))
                    self.assertEqual(m.reg("ESI"), SIDES[0])
                    self.assertEqual(len(builds), int(expect))
                    self.assertEqual(m.get(marker), left)
                    self.assertEqual(self._word(self.after, "gadget_grace"), 0)
                    if expect:
                        record = m.get(SIDES[0] + 0xC)
                        packed = m.get(record + 0xC8)
                        signed = lambda v: struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0]
                        build = builds[0]
                        self.assertEqual((build["ecx"], build["edx"]), (SIDES[0], record + 4))
                        self.assertEqual(build["args"][:3], (0, 0, 1))
                        self.assertEqual(struct.unpack("<2i", bytes(m.uc.mem_read(build["args"][3], 8))),
                                         (signed(packed << 0x16) >> 0x1D, signed(packed << 0x13) >> 0x1D))
        finally:
            for h in hooks:
                m.uc.hook_del(h)
        # The real rebuild: after a substituted End Around, a no-huddle-style store of another play rebuilds the
        # offense with the game's own eleven for that play (the build's output, read where line() reads it).
        for entry, displaced in ((restore, 0xB8790), (audible, 0xB87D0)):
            with self.subTest(real_rebuild=hex(displaced)):
                sync_only = self._skip(self.after, displaced)
                try:
                    self.select(book, 3, 147)
                    self.assertEqual(self.outcome(0, slot)[2], "changed")
                    self.select(book, 3, 147)
                    benched = self.before.line(0)[slot]
                    self.assertEqual(self._marker(self.after), SIDES[0])
                    self.select(book, 3, others[0])
                    m.put(0xE602B8, 12)
                    m.put(0xE60280, SIDES[0])
                    m.put(0xE60284, SIDES[1])
                    caller = 0xA24EC if entry == restore else 0x18B090    # no-huddle store / the offense audible
                    m.call(entry, ecx=SIDES[0], edx=0, esi=SIDES[0], args=(0, SIDES[0], 0, caller), stop=0x18A646,
                           budget=300000)
                    rebuilt = self.after.words(m.reg("ESP") + 0x74, 11)
                    # During the rebuild the receiver the substitution benched is under the field threshold once.
                    self.assertEqual(self._word(self.after, "gadget_grace"), benched)
                    self.assertEqual(self._word(self.after, "gadget_benched"), 0)
                finally:
                    m.uc.hook_del(sync_only)
                    m.put(gadget.CODE_VA + template.LABELS["gadget_grace"], 0)
                self.assertEqual(rebuilt, self.before.line(0))
                self.assertEqual(self._marker(self.after), 0)

    def test_from_the_native_sites_a_store_or_audible_after_a_substitution_rebuilds_the_game_lineup(self):
        """Review F1, behaviour only (no runtime labels, so this fails on code without the restore): after an End
        Around put the GAD in, execution from the play store's call 0x9F9CB (no-huddle, re-pick) and from the offense
        audible's call 0x9FB10 must rebuild the offense through 0x18AD10, and that build must give the game's own
        picks for the new play (no GAD at the carrier slot). Without the restore both sites just run their displaced
        call and return, leaving the substituted eleven on the field."""
        book = self.setup_book(314)
        slot = self.links[314][(3, 147)]
        others = [link.play_index for link in book.formations[3].play_links if (3, link.play_index) not in self.links[314]]
        m = self.after.m
        u = m.u
        for site, displaced, back, caller in ((0x9F9CB, 0xB8790, 0x9F9D0, 0xA24EC), (0x9FB10, 0xB87D0, 0x9FB15, 0x18B090)):
            with self.subTest(site=hex(site)):
                self.select(book, 3, 147)
                self.assertEqual(self.outcome(0, slot)[2], "changed")
                self.select(book, 3, others[0])
                m.put(0xE602B8, 12)
                m.put(0xE60280, SIDES[0])
                m.put(0xE60284, SIDES[1])
                seen = {}

                def stop(_uc, pc, _size, _user):
                    if pc == 0x18A646:
                        seen["line"] = self.after.words(m.reg("ESP") + 0x74, 11)
                    else:
                        seen["returned"] = True
                    m.uc.emu_stop()

                hooks = [self._skip(self.after, displaced),
                         m.uc.hook_add(u.UC_HOOK_CODE, stop, begin=0x18A646, end=0x18A646),
                         m.uc.hook_add(u.UC_HOOK_CODE, stop, begin=back, end=back)]
                try:
                    # The routine's frame at its call: EDI, ESI, EBX pushed, then its own return address.
                    m.uc.mem_write(m.STACK, struct.pack("<4I", 0, SIDES[0], 0, caller))
                    for name, value in dict(ECX=SIDES[0], EDX=0, ESI=SIDES[0], EDI=0, EBX=0, EBP=0x44444444,
                                            ESP=m.STACK, EFLAGS=0x202).items():
                        m.reg(name, value)
                    m.uc.emu_start(site, 0xFFFFFFFF, count=400000)
                finally:
                    for h in hooks:
                        m.uc.hook_del(h)
                    for label in ("gadget_team", "gadget_benched", "gadget_grace"):
                        if label in template.LABELS:
                            m.put(gadget.CODE_VA + template.LABELS[label], 0)
                self.assertNotIn("returned", seen, "the site returned without rebuilding the offense lineup")
                self.assertEqual(seen.get("line"), self.before.line(0))
                self.assertNotEqual(seen["line"][slot], self.before.gad(0))

    def test_the_benched_receiver_is_judged_once_as_if_he_had_stayed_on_the_field(self):
        """Review F1, fatigue: the snap path's availability call 0x18A6EE goes through available_or_kept. For the
        receiver the last substitution benched (gadget_grace, set only during the restore's rebuild) it runs the game's
        own test 0x188440 with the bench threshold set to the field threshold for that one call, then restores both
        thresholds and spends the grace; for every other player it is the game's test unchanged."""
        m = self.after.m
        kept = gadget.CODE_VA + template.LABELS["available_or_kept"]
        grace = gadget.CODE_VA + template.LABELS["gadget_grace"]
        base = MARK + 0x800
        player, obj, record = base, base + 0x100, base + 0x200
        m.uc.mem_write(player, bytes(0x80))
        m.uc.mem_write(obj, bytes(0x40))
        m.uc.mem_write(record, bytes(0x10))
        m.put(player + 0x30, obj)
        m.put(obj + 4, record)
        m.uc.mem_write(player + 0x34, bytes([1, 3]))     # home side; a position the stamina test applies to
        m.put(player + 0x24, 0)                          # healthy
        thresholds = {0xE60194: 5, 0xE60198: 16, 0xE601A4: 5, 0xE601A8: 16, 0xE6019C: 0, 0xE601AC: 0}
        for address, value in thresholds.items():
            m.put(address, value)

        def check(address, stamina, on_field, graced):
            m.f32(record + 4, stamina)
            m.put(obj + 0x10, 0x1234 if on_field else 0)
            m.put(grace, player if graced else 0)
            result = m.call(address, edx=player, args=(1,), budget=5000)
            self.assertEqual({a: m.get(a) for a in thresholds}, thresholds)   # the game's thresholds are untouched
            self.assertEqual(m.get(grace), 0 if graced else 0)
            return bool(result)

        for stamina, on_field, native in ((0.5, False, False), (0.9, False, True), (0.5, True, True), (0.2, True, False),
                                          (0.2, False, False)):
            with self.subTest(stamina=stamina, on_field=on_field):
                self.assertEqual(check(0x188440, stamina, on_field, False), native)
                self.assertEqual(check(kept, stamina, on_field, False), native)
                # The benched receiver comes back at the field threshold (0.25), exactly as if he were on the field.
                self.assertEqual(check(kept, stamina, on_field, True), stamina >= 0.25)
        m.put(player + 0x24, 7 << 28)                    # an injury status over the side's limit still refuses him
        self.assertFalse(check(kept, 0.9, False, True))
        m.put(player + 0x24, 0)
        # Another player while the grace is set: the game's test, and the grace stays for its receiver.
        m.put(grace, player + 4)
        m.f32(record + 4, 0.5)
        m.put(obj + 0x10, 0)
        self.assertFalse(m.call(kept, edx=player, args=(1,), budget=5000))
        self.assertEqual(m.get(grace), player + 4)
        m.put(grace, 0)

    def test_the_classifier_refuses_malformed_selections(self):
        book = self.setup_book(314)
        c, f, p = self.select(book, 3, 147)
        lookup = gadget.CODE_VA + template.LABELS["select_slot"]
        choice = CHOICE[0] + 4
        n = self.after

        def direct():
            return n.m.call(lookup, args=(BOOKS[0], choice, c, f), budget=20000)

        self.assertEqual(direct(), self.links[314][(3, 147)])
        for label, address, value in (("null play", choice + 8, 0), ("FC2 coordinate as a play", choice + 8, 0xFED2),
                                      ("misaligned play", choice + 8, p + 4),
                                      ("other side's play", choice + 8, BOOKS[1] + ip.PLAY_BASE),
                                      ("other category", choice, c + 16), ("other formation", choice + 4, f + 180),
                                      ("different secondary", choice + 12, p + 96),
                                      ("formation table moved", BOOKS[0] + 0x44, 0xFED2),
                                      ("play count over 270", BOOKS[0] + 0x38, 271),
                                      ("book name pointer moved", BOOKS[0] + 0x30, 0xFED2),
                                      ("play flags changed", p + 4, n.m.get(p + 4) ^ 2)):
            with self.subTest(label), poke(n, address, struct.pack("<I", value)):
                self.assertEqual(direct(), 0xFFFFFFFF)
        self.assertEqual(direct(), self.links[314][(3, 147)])

    def test_the_six_unresolved_attract_selections_are_not_gadget_plays(self):
        """Q62's six attract-game snaps whose field showed the GAD at WR slot 9 (ATL 45/105; ARZ 47/132, 47/151,
        47/104, 23/100, 47/109): none is a table link, so the classifier refuses them and the lineup is the game's,
        on both controls. Whatever put the GAD there, it was not this rule's snap-time decision."""
        lookup = gadget.CODE_VA + template.LABELS["select_slot"]
        # Review F3: the attract game ran the preview disc (303b97d10750); these are its ARZ and ATL books (sha256 from
        # the qualified candidate's receipt). The v0.9 books used here must be those same bytes.
        for asset, sha in ((307, "07af112c13b4a59ae3f87b3e10f3c954f9d246cca53ee21461a0bfaaac43943a"),
                           (308, "d5b334229980ec4972f1fa7b4bf840191d6d3c6306dcd629ba9e2216bbcf85d5")):
            self.assertEqual(_sha(self.books[str(asset)]), sha)
        for asset, form, play in ((308, 45, 105), (307, 47, 132), (307, 47, 151), (307, 47, 104), (307, 23, 100),
                                  (307, 47, 109)):
            self.assertNotIn((form, play), self.links[asset])
            for human in (False, True):
                with self.subTest(asset=asset, formation=form, play=play, human=human):
                    book = self.setup_book(asset, 0, human)
                    c, f, _p = self.select(book, form, play, 0, human)
                    self.assertEqual(self.after.m.call(lookup, args=(BOOKS[0], CHOICE[0] + 4, c, f), budget=20000),
                                     0xFFFFFFFF)
                    self.assertEqual(self.after.line(0), self.before.line(0))

    def test_fc1_punt_set_up_frames_keep_the_games_lineup(self):
        """The type-12 set-up (0x18B184) with the punt formations recovered from FC1's crash frames."""
        for asset, fi, ci in ((312, 38, 14), (315, 38, 14), (325, 40, 15)):
            for side in (0, 1):
                self.setup_book(asset, side, False)
                lines = []
                for n in (self.before, self.after):
                    m, root = n.m, BOOKS[side]
                    form = m.call(0xE0660, ecx=root, edx=fi)
                    category = m.call(0xE05E0, ecx=root, edx=ci)
                    m.reg("ESP", m.STACK)
                    m.reg("ECX", SIDES[side])
                    m.reg("EDX", category)
                    m.uc.mem_write(m.STACK, struct.pack("<6I", form, m.STACK + 0x80, 0, 0, 1, 0))
                    m.uc.emu_start(0x18B184, 0x18A646, count=300000)
                    self.assertEqual(m.reg("EIP"), 0x18A646)
                    lines.append(n.words(m.reg("ESP") + 0x74, 11))
                self.assertEqual(lines[0], lines[1], (asset, side))

    def test_fc2_tennessee_gun_empty_keeps_the_games_lineup(self):
        """Formation 43 of resource 341, whose -302 cm alignment (0xFED2) the beta-80 rule took for a pointer."""
        for side, human in ((0, False), (1, True)):
            book = self.setup_book(341, side, human)
            form = book.formations[43]
            for link in form.play_links:
                self.select(book, 43, link.play_index, side, human)
                if (43, link.play_index) in self.links[341]:
                    continue
                self.assertEqual(self.after.m.get(self.after.words(CHOICE[side] + 8, 1)[0] + 12 + 8 * 6), 0xFED2)
                self.assertEqual(self.after.line(side), self.before.line(side))


if __name__ == "__main__":
    unittest.main()
