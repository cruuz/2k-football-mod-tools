"""Job b780 n8-histcompose: the History screen composes with MyCareer, Career Home, Player Progress, the on-demand Career
Home loader, the music playlist and the franchise footer. EXPERIMENTAL / UNWITNESSED in game.

The collision (found by n6): the History screen pins the retail bytes of the screen push (0x6E390, 0x63 bytes) and the
menu dispatcher (0x6E4E0, 0x118 bytes). MyCareer hooks the push prologue (0x6E390, 10 bytes), the module loader the
push right after it (0x6E39A, 5 bytes) and the playlist the dispatcher prologue (0x6E4E0, 5 bytes), so any build with
MyCareer or Music shuffle and the History screen stopped late with "foreign history screen dependency". No shared cave,
pool or text: the guard was too strict. ``nfl2k5_history_screen.COMPANION_HOOKS`` now accepts exactly those three hooks
of complete current installs.

Static (the retail USA ``default.xbe``): every owner reads applied in the build's order and with the History screen
first; the companion hooks are exact; replay is a no-op; a hook without its owner, a changed hook and a changed native
byte are refused; an unreserved History screen after the loader is refused before any write; the build preflight
accepts the composed source.

Native (Unicorn, the composed executable, the real menu manager of ``tests.nfl2k5_my_career_mode_fixture`` with its
named hardware and layout seams): ESPN.com > TEAM HISTORY opens through the live MyCareer push hook, the loader gate and
the playlist dispatcher hook (History's own enter and input run; B goes back); Schedule X opens the box score through
the same hooks; MyCareer's entry loads Career Home once (``XeLoadSection`` is a stand-in kernel routine), MyCareer's
own reroute still works, and with a career active the History screen still opens; MyCareer boots its M3 progress menu
and quits natively; the playlist queues music on events 1 and 3 of the History screens; the playlist's 24 named native
routes (``test_nfl2k5_music_playlist_contexts``) run in the composed executable.

``NFL2K5_N8_BUILT_XBE`` (optional): the default.xbe of a real Studio build; the same status and native checks run on it.
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_history_screen as hist  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.nfl2k5_my_career_fixture import HAVE_UC  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit  # noqa: E402

BUILD_ORDER = ("my_career", "playlist", "honors", "career_home", "player_progress", "module_loader", "footer", "capture",
               "history")
_CACHE: dict = {}


def _modules():
    from mod_editor.core import (nfl2k5_my_career_mode as mode, nfl2k5_music_playlist as playlist,
                                 nfl2k5_my_career_home as home, nfl2k5_player_progress_screen as progress,
                                 nfl2k5_module_loader as loader, nfl2k5_franchise_footer as footer,
                                 nfl2k5_history as capture, nfl2k5_honors as honors)
    return dict(my_career=mode, playlist=playlist, honors=honors, career_home=home, player_progress=progress,
                module_loader=loader, footer=footer, capture=capture, history=hist)


def compose(order=BUILD_ORDER, *, reserve_history=None) -> bytes:
    """The retail executable with the build's first space pass (``_selected_space_requests``) and then each owner in
    ``order``, exactly as the build applies them (Player Progress hosted when the footer is selected)."""
    key = (tuple(order), reserve_history)
    if key in _CACHE:
        return _CACHE[key]
    from mod_editor.core import nfl2k5_throw_tuning as tt
    m = _modules()
    flags = dict(music_shuffle="playlist" in order, my_career="my_career" in order, my_career_home="career_home" in order,
                 module_loader="module_loader" in order, player_progress="player_progress" in order,
                 history_screen=("history" in order) if reserve_history is None else reserve_history,
                 franchise_history="footer" in order, franchise_history_static_body=True, honors_page="honors" in order)
    payload = space.apply(retail_xbe(), tt._selected_space_requests(**flags), scaleout=True)[0]
    for name in order:
        if name == "player_progress":
            payload = m[name].apply(payload, hosted="footer" in order)[0]
        elif name == "footer":
            payload = m[name].apply(payload, static_body=True)[0]
        elif name == "capture":
            payload = m[name].apply(payload, seeds=())[0]
        elif name == "history":
            payload = hist.install(payload, seed=hist.load_seed(), xtnd_ptr_va=hist.footer_pointer_va(payload))[0]
        else:
            payload = m[name].apply(payload)[0]
    _CACHE[key] = payload
    return payload


def expected_status(name, order):
    return "hosted" if name == "player_progress" and "footer" in order else "applied"


def built_xbe() -> bytes:
    path = os.environ.get("NFL2K5_N8_BUILT_XBE", "")
    if not path:
        raise unittest.SkipTest("NFL2K5_N8_BUILT_XBE (a real build's default.xbe) is not set")
    with open(path, "rb") as stream:
        data = stream.read(16 * 1024 ** 2 + 1)
    if len(data) > 16 * 1024 ** 2:
        raise AssertionError("NFL2K5_N8_BUILT_XBE must be a default.xbe, not a disc image")
    return data


class CompositionTests(unittest.TestCase):
    """The owners on the retail executable, in the build's order and in another order."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.full = compose()

    def statuses(self, payload, order=BUILD_ORDER):
        m = _modules()
        return {name: m[name].status(payload) for name in order}

    def test_every_owner_reads_applied_in_the_build_order(self):
        self.assertEqual(space.status(self.full), "applied")
        self.assertEqual(self.statuses(self.full), {n: expected_status(n, BUILD_ORDER) for n in BUILD_ORDER})
        self.assertEqual(hist.footer_pointer_va(self.full), struct.unpack_from(
            "<I", XbeImage(self.full).read(hist.allocations(self.full)["read_only"]["va"] + hist.RO_HEADER - 12, 4))[0])

    def test_the_history_screen_first_then_every_companion(self):
        order = ("history",) + BUILD_ORDER[:-1]
        other = compose(order)
        self.assertEqual(self.statuses(other, order), {n: expected_status(n, order) for n in order})
        image = XbeImage(other)
        for label, va, _retail, after in hist.companion_sites(self.full):
            self.assertEqual(image.read(va, len(after)), after, label)

    def test_each_option_pair_composes(self):
        # Music shuffle + History, MyCareer + History, MyCareer + Career Home + Player Progress + History
        for order in (("playlist", "history"), ("my_career", "history"),
                      ("my_career", "career_home", "player_progress", "history")):
            with self.subTest(" + ".join(order)):
                payload = compose(order)
                self.assertEqual(self.statuses(payload, order), {n: expected_status(n, order) for n in order})
                self.assertEqual(len(hist.companion_sites(payload)), ("playlist" in order) + ("my_career" in order))

    def test_the_three_companion_hooks_are_exact(self):
        self.assertEqual(hist.companion_sites(self.retail), [])
        found = hist.companion_sites(self.full)
        self.assertEqual([(label, hex(va), len(before)) for label, va, before, _after in found],
                         [("mycareer_screen_push", "0x6e390", 10), ("module_loader_screen_push", "0x6e39a", 5),
                          ("playlist_screen_event", "0x6e4e0", 5)])
        image = XbeImage(self.full)
        for label, va, before, after in found:
            self.assertEqual(image.read(va, len(after)), after, label)
            self.assertNotEqual(before, after, label)
            self.assertIn(after[0], (0xE9,), label)                   # a jump into the companion's own code
        m = _modules()
        code, data = m["my_career"].legacy.allocations(self.full)
        self.assertIn(("mode_dispatch", 0x6E390, found[0][2], found[0][3]),
                      [tuple(s) for s in m["my_career"].sites(code["va"], data["va"])])
        self.assertEqual(m["module_loader"].sites(m["module_loader"].allocation(self.full)[0]["va"])[0][1:],
                         found[1][1:])
        # the guarded spans hold nothing else that differs from retail
        retail = XbeImage(self.retail)
        own = [(label, va, before, None) for label, va, before, _kind in hist.SITE_TABLE]
        for name, va, size in hist.GUARDS:
            raw = bytearray(image.read(va, size))
            for _label, at, before, _after in found + own:
                if va <= at < va + size:
                    raw[at - va:at - va + len(before)] = before
            self.assertEqual(bytes(raw), retail.read(va, size), name)

    def test_replay_is_a_no_op(self):
        again, receipt = hist.install(self.full, seed=hist.load_seed(), xtnd_ptr_va=hist.footer_pointer_va(self.full))
        self.assertEqual(again, self.full)
        self.assertTrue(receipt["already_applied"])

    def test_a_companion_hook_without_its_owner_is_refused(self):
        alone = compose(("history",))
        self.assertEqual(hist.status(alone), "applied")
        for label, va, _before, after in hist.companion_sites(self.full):
            with self.subTest(label):
                stray = repin_edit(alone, va, after)
                self.assertEqual(space.status(stray), "applied")
                self.assertEqual(hist.status(stray), "foreign")
                with self.assertRaisesRegex(hist.HistoryScreenError, label + ".*Rebuild from your retail game"):
                    hist.owned_state(stray)

    def test_a_changed_hook_or_native_byte_is_refused(self):
        image = XbeImage(self.full)
        # a changed jump target or native byte is refused by this owner's span digest or, first, by a companion that
        # pins the same bytes (MyCareer's context check covers the loader's and the playlist's hooks and the dispatcher)
        cases = [("mycareer_screen_push", 0x6E391)] + [("foreign history screen dependency", va)
                                                        for va in (0x6E39B, 0x6E4E1, 0x6E3A0, 0x6E4E5, 0x6E5F0)]
        for expected, va in cases:
            with self.subTest(hex(va)):
                changed = repin_edit(self.full, va, bytes([image.read(va, 1)[0] ^ 1]))
                self.assertEqual(hist.status(changed), "foreign")
                with self.assertRaisesRegex(hist.HistoryScreenError, expected):
                    hist.owned_state(changed)

    def test_an_unreserved_history_screen_after_the_loader_is_refused_before_any_write(self):
        order = ("my_career", "playlist", "career_home", "module_loader")
        base = compose(order, reserve_history=False)
        self.assertEqual(hist.status(base), "retail")
        with self.assertRaisesRegex(hist.HistoryScreenError, "not reserved before the on-demand Career Home loader"):
            hist.install(base, seed=hist.load_seed())

    def test_the_build_preflight_accepts_the_composed_source(self):
        from mod_editor.core import mod_build
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "default.xbe"
            path.write_bytes(self.full)
            mod_build._history_screen_preflight(path, lambda *a: None)
            alone = compose(("history",))
            path.write_bytes(repin_edit(alone, 0x6E4E0, hist.companion_sites(self.full)[2][3]))
            # the refusal names the hook and its owner (b780 n8), before any write
            with self.assertRaisesRegex(ValueError, r"not retail \(foreign history screen dependency: playlist_screen_event "
                                                    r"\(0x6e4e0\): the music playlist hooks this screen entry"):
                mod_build._history_screen_preflight(path, lambda *a: None)
        self.assertIsNone(hist.refusal(self.full))
        self.assertIsNone(hist.refusal(self.retail))


@unittest.skipUnless(HAVE_UC, "Unicorn absent")
class NativeTests(unittest.TestCase):
    """The composed executable under Unicorn: the History screen, MyCareer and playlist entry points."""

    FAKE_KERNEL = 0x2C80000

    @classmethod
    def payload(cls) -> bytes:
        return compose()

    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        cls.image_bytes = cls.payload()
        cls.roster = retail_roster()
        m = _modules()
        found = hist.allocations(cls.image_bytes)
        cls.state = found["data"]["va"]
        cls.at = hist.labels(found["code"]["va"])
        ro = found["read_only"]["va"]
        content = XbeImage(cls.image_bytes).read(ro, hist.RO_SIZE)
        cls.history_descriptor = ro + hist.ro_history_descriptor(content)
        cls.box_descriptor = ro + hist.ro_field(content, "box_descriptor")
        cls.loader_code, cls.loader_data = (a["va"] for a in m["module_loader"].allocation(cls.image_bytes))
        code, data, read_only = m["playlist"].sites(cls.image_bytes)
        cls.playlist_state = data["va"]
        cls.playlist_labels = m["playlist"].code_for(code["va"], data["va"], read_only["va"])[1]
        cls.header = m["module_loader"].header_va(cls.image_bytes)

    def machine(self):
        """The real menu manager on the main menu, the playlist active (its queue routine counted, not run) and a
        stand-in for the kernel's XeLoadSection (returns success)."""
        from tests.nfl2k5_my_career_mode_fixture import Machine
        from mod_editor.core import nfl2k5_module_loader as loader
        m = Machine(self.image_bytes)
        self.addCleanup(m.close)
        m.frontend(self.roster)
        m.hits = {}

        def count(name, va):
            m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: m.hits.__setitem__(name, m.hits.get(name, 0) + 1),
                                         begin=va, end=va))
        count("mycareer_push", m.labels["mode_dispatch"])
        count("loader_gate", self.loader_code)
        count("playlist_event", self.playlist_labels["screen_event"])
        count("hist_enter", self.at["hist_enter"])
        count("hist_input", self.at["hist_input"])
        m.uc.mem_map(self.FAKE_KERNEL, 0x1000)
        m.uc.mem_write(self.FAKE_KERNEL, b"\x31\xc0\xc2\x04\x00")      # xor eax, eax ; ret 4 (STATUS_SUCCESS)
        m.put(loader.XE_LOAD_SECTION, self.FAKE_KERNEL)
        m.loads = []
        m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: m.loads.append(m.get(m.reg("ESP") + 4)),
                                     begin=self.FAKE_KERNEL, end=self.FAKE_KERNEL))
        m.put(self.playlist_state, 1)                                    # the playlist has started
        m.queued = []
        m.replace_stub(self.playlist_labels["enqueue"], lambda: (m.queued.append(m.top()), m.ret()))
        return m

    def test_team_history_row_opens_through_mycareer_the_loader_and_the_playlist(self):
        m = self.machine()
        m.call(0x6E390, ecx=m.manager, edx=hist.ESPN_DESCRIPTOR, budget=5_000_000)
        self.assertEqual((m.depth(), m.top()), (1, hist.ESPN_DESCRIPTOR))
        self.assertEqual((m.hits["mycareer_push"], m.hits["loader_gate"]), (1, 1))
        m.select(hist.ESPN_RETAIL_ROWS, budget=5_000_000)              # A on TEAM HISTORY: the game's own row push
        self.assertEqual((m.depth(), m.top()), (2, self.history_descriptor))
        self.assertEqual((m.hits["mycareer_push"], m.hits["loader_gate"], m.hits["hist_enter"]), (2, 2, 1))
        self.assertEqual(m.queued.count(self.history_descriptor), 2)    # events 1 and 3 of the History screen
        self.assertEqual(m.get(self.state), 0)
        m.frame(0x1000)                                                 # Black: the next page
        self.assertEqual(m.get(self.state), 1)
        self.assertGreaterEqual(m.hits["hist_input"], 1)
        m.frame(0x200)                                                  # B: back to ESPN.com
        self.assertEqual((m.depth(), m.top()), (1, hist.ESPN_DESCRIPTOR))
        self.assertEqual(m.loads, [])                                   # no MyCareer screen: nothing loaded

    def test_schedule_x_opens_the_box_score_through_the_same_hooks(self):
        m = self.machine()
        m.put(0xE576A0, 2)                                              # Franchise
        m.put(0xE576AC, 32)
        for i in range(32):
            m.put(0xE5786C + 4 * i, 0x2B00000 + 0x1F4 * i)
        m.uc.mem_write(0xE57C40 + 8 * (17 * 2 + 3), bytes([3, 0, 1, 9, 14, 26, 13, 0]))   # row 2 slot 3: played
        m.replace_stub(0x24B680, lambda: m.ret(2))                      # the Schedule's selected-game accessors
        m.replace_stub(0x24B6C0, lambda: m.ret(3))
        m.replace_stub(0xF35A0, lambda: m.ret(pop=4))                   # the menu legend
        m.inputs = 0x400                                                # X
        self.assertEqual(m.call(self.at["hist_schedule_x"], ecx=m.manager, edx=0, budget=5_000_000), 1)
        self.assertEqual((m.depth(), m.top()), (1, self.box_descriptor))
        self.assertEqual((m.hits["mycareer_push"], m.hits["loader_gate"]), (1, 1))
        self.assertEqual(m.queued, [self.box_descriptor] * 2)
        self.assertEqual([m.get(self.state + 4 * i) for i in (5, 6, 7)], [2, 3, 0])
        m.frame(0x200)
        self.assertEqual((m.depth(), m.top()), (0, 0x515660))

    def test_mycareer_entry_loads_career_home_once_and_history_still_opens_in_a_career(self):
        m = self.machine()
        m.call(0x6E390, ecx=m.manager, edx=m.labels["entry_menu"], budget=5_000_000)
        self.assertEqual(m.top(), m.labels["entry_menu"])
        self.assertEqual(m.loads, [self.header])
        self.assertEqual(m.uc.mem_read(self.loader_data, 1)[0], 1)      # loaded
        # a career on this manager: MyCareer's push hook is live for every screen
        m.put(m.state + 2672, m.manager)
        m.replace_stub(m.labels["inline_active"], lambda: m.ret(1))
        depth = m.depth()
        m.call(0x6E390, ecx=m.manager, edx=hist.ESPN_DESCRIPTOR, budget=5_000_000)
        m.select(hist.ESPN_RETAIL_ROWS, budget=5_000_000)
        self.assertEqual((m.depth(), m.top()), (depth + 2, self.history_descriptor))
        m.frame(0x200)
        m.frame(0x200)
        self.assertEqual(m.depth(), depth)
        m.call(0x6E390, ecx=m.manager, edx=0x522190, budget=5_000_000)  # MyCareer's own reroute still works
        self.assertEqual(m.top(), m.labels["apartment"])
        self.assertEqual(m.loads, [self.header])                        # loaded once

    def test_mycareer_boots_its_progress_menu_and_quits(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode
        m = self.machine()
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC, budget=5_000_000)
        m.select(1)
        m.select(0, budget=500_000_000)
        self.assertEqual(m.top(), m.labels["m3_progress_menu"])
        self.assertEqual(m.get(mode.EXTRA_VA), 1)
        self.assertEqual(m.loads, [self.header])
        m.select(0)
        self.assertEqual(m.top(), 0x515660)
        self.assertEqual(m.get(mode.EXTRA_VA), 0)


def _j4():
    from tests.mod_editor import test_b780_j4_history_screen as j4
    return j4


class HistoryScreenInTheComposedExecutable(_j4().NativeTests):
    """j4's Unicorn tests of every History page, the input, the box score, the footer reads and the Player Card's
    four-page cycle through the champions owner, run with the History screen installed on the composed executable
    (MyCareer, the playlist, honors, Career Home, Player Progress, the loader and the footer installed first)."""

    @classmethod
    def setUpClass(cls):
        j4 = _j4()
        cls.retail = compose(BUILD_ORDER[:-1], reserve_history=True)    # the composed base the j4 tests install on
        cls.payload, cls.receipt = hist.install(cls.retail, seed=j4.seed_document(), xtnd_ptr_va=cls.WORDS)
        cls.at = hist.labels(int(cls.receipt["code_va"], 16))
        cls.ro = int(cls.receipt["ro_va"], 16)
        cls.state = int(cls.receipt["data_va"], 16)
        cls.content = XbeImage(cls.payload).read(cls.ro, hist.RO_SIZE)
        assert [label for label, *_ in hist.companion_sites(cls.payload)] == [
            "mycareer_screen_push", "module_loader_screen_push", "playlist_screen_event"]


def _playlist_routes():
    from tests.mod_editor import test_nfl2k5_music_playlist_contexts as contexts
    return contexts.ContextTests


class PlaylistRoutesInTheComposedExecutable(_playlist_routes()):
    """The playlist's own 24 named native routes, run on the composed executable."""

    @classmethod
    def setUpClass(cls):
        cls.patched = compose()


class BuiltExecutableTests(unittest.TestCase):
    """A real Studio build's default.xbe (NFL2K5_N8_BUILT_XBE): every owner of the group reads applied."""

    @classmethod
    def setUpClass(cls):
        cls.payload = built_xbe()

    def test_every_owner_of_the_group_reads_applied(self):
        m = _modules()
        got = {name: m[name].status(self.payload) for name in BUILD_ORDER}
        self.assertEqual(got, {n: expected_status(n, BUILD_ORDER) for n in BUILD_ORDER})
        self.assertEqual([label for label, *_ in hist.companion_sites(self.payload)],
                         ["mycareer_screen_push", "module_loader_screen_push", "playlist_screen_event"])


class BuiltNativeTests(NativeTests):
    @classmethod
    def payload(cls) -> bytes:
        return built_xbe()


class BuiltPlaylistRoutes(_playlist_routes()):
    @classmethod
    def setUpClass(cls):
        cls.patched = built_xbe()


if __name__ == "__main__":
    unittest.main()
