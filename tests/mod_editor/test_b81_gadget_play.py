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

    def test_code_for_reproduces_the_qualified_runtime_byte_for_byte(self):
        code = gadget.code_for(QUALIFIED_OFFSETS, QUALIFIED_GATE)
        self.assertEqual(len(code), gadget.CODE_SIZE)
        self.assertEqual(_sha(code), QUALIFIED_CODE_SHA256)
        self.assertEqual(code[len(template.TEMPLATE):], bytes(gadget.CODE_SIZE - len(template.TEMPLATE)))

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

    def test_hooks_enter_the_runtime_from_the_two_native_sites(self):
        (_, builder, builder_retail, builder_new), (_, ordinal, ordinal_retail, ordinal_new) = gadget._hooks()
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
    """The Studio owner on the preview the 20 CPU games used is the qualified executable itself."""

    def test_the_owner_on_the_preview_is_the_qualified_executable(self):
        if not QUALIFIED_XBE.is_file():
            self.skipTest("the qualified candidate executable is absent")
        source, books = _require_disc(PREVIEW_DISC, PREVIEW_XBE_SHA256)
        qualified = QUALIFIED_XBE.read_bytes()
        self.assertEqual(_sha(qualified), QUALIFIED_XBE_SHA256)
        self.assertEqual(gadget.status(source), "retail")
        result, receipt = gadget.apply(source, books)
        self.assertEqual(_sha(result), QUALIFIED_XBE_SHA256)
        self.assertEqual((receipt["table_bytes"], receipt["eligible_links"], receipt["left_out_books"]), (12800, 111, []))
        self.assertEqual(gadget.read_settings(result, books)["status"], "applied")
        # Off again: the sites are retail, the slots stay reserved and empty; on again: the same executable.
        off, _ = gadget.remove(result)
        self.assertEqual(gadget.status(off), "retail")
        self.assertEqual(gadget.apply(off, books)[0], qualified)


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

    def commit(self, side, c, f, p, *, human=False, secondary=None):
        """Publish the selection the way the game does: the user's play call or the CPU's offense choice."""
        m, s = self.m, SIDES[side]
        m.put(0xE602B8, 11)
        m.put(0xE60280, s)
        m.put(0xE60284, SIDES[1 - side])
        second = p if secondary is None else secondary
        if human:
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

    def line(self, side):
        """The snap path: 0x9F3B7 -> 0x89624 -> 0x18AD10 -> 0x18A5D0 -> the builder call 0x18A641."""
        m = self.m
        m.put(0xE602B8, 12)
        m.put(0xE60280, SIDES[side])
        m.put(0xE60284, SIDES[1 - side])
        m.call(0x9F3B7, ecx=1, ebx=1, stop=0x18A646, budget=300000)
        return self.words(m.reg("ESP") + 0x74, 11)

    def line_with_picker(self, side, slot):
        self.observe_slot, self.observations = slot, []
        try:
            return self.line(side), list(self.observations)
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

    def select(self, book, form, play, side=0, human=False, secondary=None):
        f = book.formations[form]
        link = next(i for i in f.play_links if i.play_index == play)
        chosen = self.before.menu(side, f, link)
        self.assertEqual(chosen, self.after.menu(side, f, link))
        for n in (self.before, self.after):
            n.commit(side, *chosen, human=human, secondary=secondary)
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
