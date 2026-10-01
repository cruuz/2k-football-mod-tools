"""tools/xemu_berman_probe.py: the parts that need no emulator, on real OCR lines and a real xemu stderr.

The screen classifier is pinned on lines the full-screen OCR read from the 2026-09-20/21/22 probe
frames (title card, the two Settings1 boxes, legal card, Visual Concepts logo, attract demo, main menu,
Team Select with and without its header, coach matchup, blank), and the exit reader on the two nv2a
pfifo asserts seen so far. The route's state machine is replayed against a scripted game on a fake
clock: the 2026-09-22 test-1 failure (a fading settings box, then a Team Select whose header did not
OCR, where the old escape ladder pressed START and began a game with the default teams) must end at
Team Select with no START or A pressed on an unreadable screen after the title. Nothing here starts
xemu, Xvfb or the virtual pad. The probe imports the X11 and PIL capture helpers at module level, so
the file skips where those are not installed.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

try:
    import xemu_berman_probe as probe  # noqa: E402
except ImportError as exc:  # Xlib / PIL / the capture helpers are local-only
    probe = None
    SKIP = f"probe helpers not importable here: {exc}"
else:
    SKIP = ""

TEAM_NO_HEADER = ("\u2014 [ DAT IG GIANTS PT] EECT \u2018= \u2014<\u2014 \u201cI AT EES SS Z& , ' E | .) @\u00b0*'\u00a2 "
                  "YS OM ICE OFFENSE EK} DEFENSE ML")
FMV = "RE 4AE B MAE OF ==, CY MF 2.0\") ESAC SY (SRY, NI JINN, NO 7 2 P) AE SS TAN"
#: C-ne-1 (2026-09-22): the ESPN boot movie frame that held from before +151 s to +482 s.
ESPN_LOGO = "~ = \u201cA! 7 SPORTS NE MRLOWEE LEADER IN EH 2H FABIO: SAY AE"
#: 02-main-menu.png of run-A-1 (2026-09-21): the menu with no MAINMENU header problem, rows only.
MENU = "SMN | T\u2014 PLAYNOW MAINMENU GAMEMODES THECRIB\u2122 FEATURES OPTIONS XBOXLIVE EXTRAS SEGA)"
#: 05-coach-matchup.png of run-A-1 (2026-09-21), and the retail one that ignored the A hold (R-ne-1-r2).
COACH = ("COACHMATCHUP =SPEN 7 J. GIBBS NOAH PT RECORD 124-60-0 YEARS 12 \u20ac RECORD 95-29-0 PLAYCALLING "
         "PLAYCALLING VIP COACHES NFL COACHES RUN _ RUN LINEUP PASS")
COACH_RETAIL = ("=SPEN OACHMATCHUP BBS NOAH START GAN ME 124-60-0 ORD YEARS 12 WE RECORD 95-29-0 PLAYCALLING "
                "PLAYCALLING VIP COACHES NFL")

#: (OCR line as the probe read it, the state it must name). All read on 2026-09-20/21/22.
SCREENS = (
    ("MPEG SOFDEC G Y YG A ADM 2K5 A SY PLAYERS (C) SEGA CORPORATION, 2004", "title"),
    ("STH SUCCESSFULLY LOADED SETTINGS SETTINGS1 MPEG SOFDEC G FROM XBOX HARD DISK. OK", "settings-loaded"),
    # B-2: the loaded box over the title words; the box must win over the title.
    ("STH SUCCESSFULLY LOADED SETTINGS SETTINGS1 MPEG SOFDEC G FROM XBOX HARD DISK. OK Y YG ADM EK P XE I SY "
     "PLAYERS \u00a9 SEGA CORPORATION, 2004", "settings-loaded"),
    ("[TAL OECEUIEES HARD DISK. PLEASE DI G LOADING SETTINGS SETTINGS1 FROM XBOX 0 0 SS TURN THE POWER SEGA UI "
     "2K5 P XE 1 V SY", "settings-loading"),
    ("IF LD \u00a9 2004 NFL PROPERTIES LLC. TEAM NAMES AND LOGOS ARE TRADEMARKS OF THE TEAMS INDICATED, ALL OTHER "
     "(NFL-RELATED MARKS) ARE TRADEMARKS OF THE NATIONAL FOOTBA", "legal"),
    ("WVISUAG CEPTS", "logo"),
    ("*-E. E* LEY ** \u201cF ; 4/ \u2014 AE * 7 2 \\ EE IE,", "other"),
    ("X, MAINMENU \u2014ESPEN | PLAYNOW GAMEMODES THECRIB\u2122 @ FEATURES = OPTIONS XBOXLIVE ES EXTRAS ZI", "menu"),
    ("=SPN [ TEAMSELECT C[Y FALCONS \u00a9) E. \u2014\u2014 A \u201c A EE J 4 5P (3 \u201cSE =, \u2018 \u2014\u2014- 2B {I "
     "== NSE | 8S DEFENSE NM 79 NSE | 8", "team-select"),
    # test-1, 2026-09-22: Team Select with no header words; its ratings panel names it.
    (TEAM_NO_HEADER, "team-select"),
    # run-A-2, 2026-09-21, 03-team-select.png: no header either.
    ("\u2014_ L FY GIANTS EP] <I AK <3 I OF AS \u00bb AE HF VA DY OE NW \\ 4 4 AE = BEA OFFENSE 8S DEFENSE 76 4 "
     "NSE A | RI} DEFENSE R\u00c9} \u00b0 OVERALL 4 85 ( +) OVERAN 77 P", "team-select"),
    (MENU, "menu"),
    (COACH, "coach-matchup"),
    (COACH_RETAIL, "coach-matchup"),
    (ESPN_LOGO, "other"),
    ("", "blank"),
)

#: The stderr of run-A-2 (2026-09-21 23:24), whole: the xemu banner and the nv2a assert.
PFIFO_STDERR = """GL_VERSION: 4.6 (Core Profile) Mesa 26.1.4 (git-6dfbc555b4)
GL_SHADING_LANGUAGE_VERSION: 4.60
GL geometry shader winding: 0, 0, 0, 0
xemu_settings_get_base_path: base path: /home/noah/.var/app/app.xemu.xemu/data/xemu/xemu/
xemu: ../hw/xbox/nv2a/pfifo.c:426: pfifo_run_pusher: Assertion `!"Reserved pb command - invalid GPU command. \
Check logs for more info"' failed.
"""


#: run-test-1 (2026-09-22 13:49), the second pfifo assert seen: an object handle outside the hash table.
RAMHT_STDERR = PFIFO_STDERR.splitlines()[0] + """
xemu: ../hw/xbox/nv2a/pfifo.c:518: ramht_lookup: Assertion `hash * 8 < ramht_size' failed.
"""


class FakeProcess:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return self.code


class FakeRun:
    def __init__(self, logs: Path, code):
        self.logs = logs
        self.xemu = FakeProcess(code)


@unittest.skipIf(probe is None, SKIP)
class ScreenStateTest(unittest.TestCase):
    def test_real_ocr_lines(self):
        for text, want in SCREENS:
            with self.subTest(want=want, text=text[:40]):
                self.assertEqual(probe.screen_state(text), want)

    def test_title_is_never_gated_on_press_start(self):
        # The blinking PRESS START line never OCRed in a PASS run; the static words carry the title.
        self.assertNotIn("PRESS", SCREENS[0][0])
        self.assertEqual(probe.screen_state(SCREENS[0][0]), "title")


#: proof-10-Z (2026-09-22, z2): the pregame stadium flyover at +41 s; a lone "COIN" in OCR noise, mid-intro.
FLYOVER_LONE_COIN = ("= =4 RS ANE X A _\u2014\u2014 EG SS EWE EE = BITE AE 2 NER \u2018S \\ AE ZI SY - I FF AN = OE TN, \\, EF "
                     "{F MY / OY) HE WO A4 IF \\S +4} COIN ONI, AE TI EC IF CRE OMEN II +H = OY")
#: The coin-toss screens of proof-1, proof-2 and proof-3 on disc Z (2026-09-22), as the probe read them.
COIN_TOSS_SCREENS = (
    ", NEAL I 2A AN R, L 4 M LAI OE \u2014 \u2014 GI COIN TOSS REDSKINS CHOOSE TAILS RA \u2014\u2014 \u2014* \u2014 A ZE ~ A 5",
    "SX V EAMES S) 2 \\ Y \u2014 I RR HALES \u201cOD . X IY FL 4 COIN TOSS PATRIOTS WILL DEFEND. WIND 1 MP NORTH (CROSSWIND)",
    "1Q DT 0 SAL EG ET MT) BI =) AY L PAT FT 4 = 4 COIN TOSS REDSKINS CHOOSE HEADS. A \u2014 = JN",
)


@unittest.skipIf(probe is None, SKIP)
class ReachedTest(unittest.TestCase):
    def test_lone_word_in_ocr_noise_is_not_the_coin_toss(self):
        self.assertIn("COIN", FLYOVER_LONE_COIN)
        self.assertFalse(probe.reached(FLYOVER_LONE_COIN))
        for word in probe.REACHED:
            with self.subTest(word=word):
                self.assertFalse(probe.reached(f"AE ZI SY {word} ONI, AE TI"))

    def test_real_coin_toss_screens_are_reached(self):
        for text in COIN_TOSS_SCREENS:
            with self.subTest(text=text[:40]):
                self.assertTrue(probe.reached(text))
        self.assertTrue(probe.reached("TOSS WINNER WILL RECEIVE"))
        self.assertTrue(probe.reached("HEADS OR TAILS CALL IT"))

    def test_menus_and_intro_screens_are_not_reached(self):
        for text, state in SCREENS:
            with self.subTest(state=state, text=text[:40]):
                self.assertFalse(probe.reached(text))


@unittest.skipIf(probe is None, SKIP)
class ExitReaderTest(unittest.TestCase):
    def test_pfifo_abort_is_read_from_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "xemu.stderr.log").write_text(PFIFO_STDERR, encoding="utf-8")
            info = probe.xemu_exit(FakeRun(logs, 134))
        self.assertIsNotNone(info)
        self.assertTrue(info["pfifo"])
        self.assertEqual(info["exit_code"], 134)
        self.assertIn("Reserved pb command", info["assertion"])
        self.assertEqual(info["site"], "pfifo.c:426 pfifo_run_pusher")

    def test_retail_dma_range_assert_is_a_pfifo_abort(self):
        # R-ne-2 (2026-09-22), the untouched retail disc 23.9 s into the intro.
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "xemu.stderr.log").write_text(PFIFO_STDERR.splitlines()[0] + """
xemu: ../hw/xbox/nv2a/pfifo.c:299: pfifo_run_pusher: Assertion `!"Dma value is out of range in PFIFO pusher"' failed.
""", encoding="utf-8")
            info = probe.xemu_exit(FakeRun(logs, 134))
        self.assertTrue(info["pfifo"])
        self.assertEqual(info["site"], "pfifo.c:299 pfifo_run_pusher")

    def test_ramht_assert_is_a_pfifo_abort_with_its_own_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "xemu.stderr.log").write_text(RAMHT_STDERR, encoding="utf-8")
            info = probe.xemu_exit(FakeRun(logs, 134))
        self.assertTrue(info["pfifo"])
        self.assertEqual(info["site"], "pfifo.c:518 ramht_lookup")

    def test_other_exit_is_not_pfifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "xemu.stderr.log").write_text(PFIFO_STDERR.splitlines()[0] + "\n", encoding="utf-8")
            info = probe.xemu_exit(FakeRun(logs, 1))
        self.assertFalse(info["pfifo"])
        self.assertEqual(info["assertion"], "")

    def test_live_process_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(probe.xemu_exit(FakeRun(Path(tmp), None)))


@unittest.skipIf(probe is None, SKIP)
class RouteErrorTest(unittest.TestCase):
    def reason(self, gate: str, ledger: dict | None = None, code=None, stderr: str = "") -> tuple[str, dict]:
        ledger = {} if ledger is None else ledger
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "xemu.stderr.log").write_text(stderr, encoding="utf-8")
            exc = probe.xr.GateError(gate, "test")
            return probe.route_error_reason(exc, FakeRun(logs, code), ledger), ledger

    def test_gate_names_map_to_reasons(self):
        self.assertEqual(self.reason("settings-box")[0], "settings-box-stuck")
        self.assertEqual(self.reason("settings-load")[0], "settings-load-stuck")
        self.assertEqual(self.reason("quick-game")[0], "main-menu-stuck")
        self.assertEqual(self.reason("title", {"boot_states": {"other": 4, "title": 0}})[0], "attract-demo")

    def test_title_gate_with_no_moving_picture_is_a_stall(self):
        self.assertEqual(self.reason("title", {"boot_states": {"legal": 40}})[0], "boot-stall")

    def test_dead_xemu_wins_over_the_gate(self):
        reason, ledger = self.reason("capture", code=134, stderr=PFIFO_STDERR)
        self.assertEqual(reason, "xemu-pfifo-abort")
        self.assertTrue(ledger["xemu_exit"]["pfifo"])


class ScriptedGame:
    """Just enough of the boot-to-Team-Select flow to replay a route on a fake clock.

    Screens change on presses the way they did on 2026-09-22: START during the intro movie shows the
    title, START at the title shows the Settings1 box, A closes the box but the box stays readable
    for ``fade_reads`` more captures, A or START on the menu opens Team Select, START on Team Select
    goes to the coach matchup (and a real game would begin there), B backs out one screen.
    """

    TEXT = {"intro": FMV, "title": SCREENS[0][0], "box": SCREENS[1][0], "menu": MENU,
            "coach": COACH, "black": "", "frozen": ESPN_LOGO}

    def __init__(self, team_text: str, fade_reads: int = 2, phase: str = "intro"):
        self.phase = phase
        self.team_text = team_text
        self.fade = 0
        self.fade_reads = fade_reads
        self.presses: list[tuple[str, str]] = []
        self.now = 0.0
        self.reads = 0

    def digest(self) -> str:
        """Animated screens change every capture; black and a frozen movie hold one frame."""
        self.reads += 1
        return self.phase if self.phase in ("black", "frozen") else f"{self.phase}-{self.reads}"

    def text(self) -> str:
        if self.phase == "fading":
            self.fade -= 1
            if self.fade < 0:
                self.phase = "menu"
            return self.TEXT["box"] if self.phase == "fading" else self.TEXT["menu"]
        if self.phase == "team":
            return self.team_text
        return self.TEXT[self.phase]

    def press(self, button: str) -> None:
        self.presses.append((self.phase, button))
        moves = {("intro", "START"): "title", ("title", "START"): "box", ("box", "A"): "fading",
                 ("menu", "A"): "team", ("menu", "START"): "team", ("team", "START"): "coach",
                 ("team", "B"): "menu", ("coach", "B"): "team", ("coach", "A"): "game"}
        if (self.phase, button) in moves:
            self.phase = moves[(self.phase, button)]
            if self.phase == "fading":
                self.fade = self.fade_reads


class RouteRun:
    def __init__(self):
        self.xemu = FakeProcess(None)
        self.gdb_port = 1234
        self.logs = Path(tempfile.gettempdir())

    def screenshot(self, name, out_dir):
        return {}


@unittest.skipIf(probe is None, SKIP)
class RouteReplayTest(unittest.TestCase):
    def replay(self, game: ScriptedGame):
        from unittest import mock

        def sleep(secs):
            game.now += secs

        def tap(pad, button, secs=0.15, settle=0.6):
            game.press(button)
            game.now += secs + settle

        def hold(pad, button, secs):
            game.press(button)
            game.now += secs

        def screen_text(run):
            game.now += 0.8   # one OCR
            return probe.xr.normalized(game.text())

        def read_screen(run):
            return screen_text(run), game.digest()

        game.now = 95.0   # the intro movie is playing when the route starts reading
        notes: dict = {}
        with mock.patch.object(probe, "tap", tap), mock.patch.object(probe, "hold", hold), \
                mock.patch.object(probe, "screen_text", screen_text), \
                mock.patch.object(probe, "read_screen", read_screen), \
                mock.patch.object(probe.time, "sleep", sleep), \
                mock.patch.object(probe.time, "monotonic", lambda: game.now), \
                mock.patch.object(probe, "log", lambda message: None), \
                mock.patch.object(probe, "sample_cpu", lambda port, path: dict(eip=0x8001A2B3)):
            state, _text = probe.reach_menu(RouteRun(), None, Path("."), notes)
            if state != "team-select":
                probe.open_quick_game(RouteRun(), None)
        return notes

    def assert_no_blind_forward_press(self, game: ScriptedGame):
        after_title = game.presses[[p for p, _ in game.presses].index("title"):]
        for phase, button in after_title:
            if phase in ("team", "coach", "game"):
                self.assertNotIn(button, ("START", "A"), game.presses)
        self.assertEqual(game.phase, "team", game.presses)

    def test_test1_replay_fading_box_then_headerless_team_select(self):
        game = ScriptedGame(TEAM_NO_HEADER)
        self.replay(game)
        self.assert_no_blind_forward_press(game)
        # One A closed the box; the fading box never took a second press.
        self.assertEqual([b for p, b in game.presses if p in ("box", "fading")], ["A"])

    def test_unreadable_team_select_is_backed_out_of_never_started(self):
        # A Team Select no rule can read: after the grace the route only ever presses B.
        game = ScriptedGame("GIANTS PT] EECT", fade_reads=2)
        with self.assertRaises(probe.xr.GateError):
            self.replay(game)
        at_team = [b for p, b in game.presses if p == "team"]
        self.assertTrue(at_team, game.presses)
        self.assertEqual(set(at_team), {"B"}, game.presses)
        # Every forward press was made on the readable menu, each followed by a B back to it.
        self.assertEqual([b for p, b in game.presses if p == "menu"], ["START", "A", "START"], game.presses)
        self.assertNotIn(game.phase, ("coach", "game"))


    def held_frame_replay(self, phase: str):
        from unittest import mock

        game = ScriptedGame(TEAM_NO_HEADER, phase=phase)
        seen: dict = {}
        original = probe.reach_menu

        def keep(run, pad, out_dir, notes):
            seen["notes"] = notes
            return original(run, pad, out_dir, notes)

        with mock.patch.object(probe, "reach_menu", keep), self.assertRaises(probe.xr.GateError) as caught:
            self.replay(game)
        return game, seen["notes"], caught.exception

    def test_black_boot_is_a_stall_with_registers(self):
        # test-4, 2026-09-22: black from +12 s before any input. No button is pressed at a black
        # screen, the held black frame ends the route at BOOT_FREEZE_SECONDS as a boot stall, and
        # the ledger keeps two register samples.
        game, notes, exc = self.held_frame_replay("black")
        self.assertEqual(exc.gate, "boot")
        self.assertEqual(game.presses, [])
        self.assertGreaterEqual(game.now - 95.0, probe.BOOT_FREEZE_SECONDS)
        self.assertLess(game.now - 95.0, probe.BOOT_QUIET_SECONDS)
        self.assertEqual([s.get("eip") for s in notes["stall_cpu"]], [0x8001A2B3, 0x8001A2B3])
        self.assertEqual(notes["frozen_picture"]["state"], "blank")

    def test_frozen_boot_movie_is_a_boot_freeze_not_the_attract_demo(self):
        # C-ne-1, 2026-09-22: one frame of the ESPN boot movie held for minutes with xemu alive.
        game, notes, exc = self.held_frame_replay("frozen")
        self.assertEqual(exc.gate, "boot-freeze")
        self.assertEqual(probe.ROUTE_REASONS[exc.gate], "boot-freeze")
        self.assertEqual(notes["frozen_picture"]["state"], "other")
        self.assertGreaterEqual(notes["frozen_picture"]["seconds"], probe.BOOT_FREEZE_SECONDS)
        self.assertEqual(len(notes["stall_cpu"]), 2)


class ScriptedTeamSelect:
    """One Team Select slot on a list with the retail extras (six ALUMNI teams and three more after
    VIKINGS, test-R2 2026-09-22). RT moves forward and wraps, LT moves back unless ``lt_dead``,
    nothing moves once ``frozen``; the frame digest is the entry index."""

    def __init__(self, start: str, extras: int = 9, lt_dead: bool = False, frozen: bool = False):
        teams = list(probe.TEAMS)
        at = teams.index("VIKINGS") + 1
        self.entries = teams[:at] + [f"EXTRA{i}" for i in range(extras)] + teams[at:]
        self.index = self.entries.index(start)
        self.lt_dead, self.frozen = lt_dead, frozen
        self.presses: list[str] = []
        self.visited = {self.entries[self.index]}

    def press(self, button: str) -> None:
        self.presses.append(button)
        if self.frozen or (button == "LT" and self.lt_dead):
            return
        self.index = (self.index + (1 if button == "RT" else -1)) % len(self.entries)
        self.visited.add(self.entries[self.index])

    def read(self) -> tuple[str, str]:
        name = self.entries[self.index]
        return (name, "") if name.startswith("EXTRA") else (f"SE E{name} EE", name)


@unittest.skipIf(probe is None, SKIP)
class TeamSelectRouteTest(unittest.TestCase):
    def cycle(self, slot: ScriptedTeamSelect, target: str, route: str):
        from unittest import mock

        with mock.patch.object(probe, "tap", lambda pad, button, secs=0.15, settle=0.6: slot.press(button)), \
                mock.patch.object(probe, "read_slot", lambda run, box, tries=4: slot.read()), \
                mock.patch.object(probe, "safe_digest", lambda run: str(slot.index)), \
                mock.patch.object(probe, "keep_slot_miss", lambda run, side: None), \
                mock.patch.object(probe, "stall_samples", lambda run, notes: notes.update(stall_cpu=[{}, {}])), \
                mock.patch.object(probe, "log", lambda message: None), \
                mock.patch.dict(probe.ROUTE, {"name": route}):
            return probe.cycle_slot_to(RouteRun(), None, probe.AWAY_SLOT, target, "away")

    def test_retail_route_goes_back_with_lt_and_never_wraps(self):
        # test-R3: TITANS -> REDSKINS on retail. Five LT pulses, no retail-only entry on the way.
        slot = ScriptedTeamSelect("TITANS")
        self.cycle(slot, "REDSKINS", "retail")
        self.assertEqual(slot.presses, ["LT"] * 5)
        self.assertFalse(any(v.startswith("EXTRA") for v in slot.visited))

    def test_retail_route_forward_when_the_target_is_later(self):
        slot = ScriptedTeamSelect("GIANTS")
        self.cycle(slot, "PATRIOTS", "retail")
        self.assertEqual(slot.presses, ["RT"] * 6)

    def test_retail_route_falls_back_to_rt_when_lt_does_nothing(self):
        slot = ScriptedTeamSelect("TITANS", lt_dead=True)
        self.cycle(slot, "REDSKINS", "retail")
        self.assertEqual(slot.entries[slot.index], "REDSKINS")
        self.assertIn("RT", slot.presses)

    def test_default_route_is_unchanged(self):
        slot = ScriptedTeamSelect("GIANTS", extras=0)
        self.cycle(slot, "PATRIOTS", "default")
        self.assertEqual(slot.presses, ["RT"] * 6)

    def test_frozen_team_select_is_a_freeze_with_registers(self):
        # test-R3: one frame held through 37 pulses and two RIGHTs, xemu alive.
        slot = ScriptedTeamSelect("TITANS", frozen=True)
        with self.assertRaises(probe.xr.GateError) as caught:
            self.cycle(slot, "REDSKINS", "default")
        self.assertEqual(caught.exception.gate, "team-select-freeze")
        self.assertEqual(probe.ROUTE_REASONS["team-select-freeze"], "team-select-freeze")
        self.assertLess(len(slot.presses), 5 + 26 + 3)
        self.assertIn("freeze", probe.SLOT_NOTES)
        probe.SLOT_NOTES.pop("freeze", None)
        probe.SLOT_NOTES.pop("stall_cpu", None)


class FakeQmpServer:
    """A QMP server on 127.0.0.1 that speaks just enough of the protocol: greeting, qmp_capabilities,
    query-status (reporting ``state``), cont (sets running, sends a RESUME event before the reply)."""

    def __init__(self, running: bool):
        import socket
        import threading

        self.state = {"running": running, "status": "running" if running else "paused", "singlestep": False}
        self.commands: list[str] = []
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except PermissionError as exc:
            raise unittest.SkipTest(f"local TCP sockets are unavailable: {exc}") from exc
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(4)
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        import json

        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                reader = conn.makefile("rb")
                conn.sendall(b'{"QMP": {"version": {}, "capabilities": []}}\r\n')
                for line in reader:
                    request = json.loads(line)
                    self.commands.append(request["execute"])
                    if request["execute"] == "query-status":
                        conn.sendall(json.dumps({"return": dict(self.state)}).encode() + b"\r\n")
                    elif request["execute"] == "cont":
                        self.state.update(running=True, status="running")
                        conn.sendall(b'{"event": "RESUME", "timestamp": {"seconds": 1, "microseconds": 0}}\r\n')
                        conn.sendall(b'{"return": {}}\r\n')
                    else:
                        conn.sendall(b'{"return": {}}\r\n')

    def close(self):
        self.server.close()


@unittest.skipIf(probe is None, SKIP)
class VmPausedTest(unittest.TestCase):
    """x1 (2026-09-23): a held frame on a VM that QEMU has paused is a harness event. The gdb stub stops
    the VM when any client opens its port; the harness binds it to localhost and asks QMP before it
    reports team-select-freeze, boot-freeze or FROZEN."""

    def test_gdb_stub_is_localhost_only_and_qmp_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = probe.xr.XemuRun(Path(tmp), 99, 1234)
            command = run.xemu_command(Path("/disc.iso"))
            self.assertEqual(command[command.index("-gdb") + 1], "tcp:127.0.0.1:1234")
            self.assertNotIn("-qmp", command)
            run.qmp_port = 4455
            command = run.xemu_command(Path("/disc.iso"))
            self.assertEqual(command[command.index("-qmp") + 1], "tcp:127.0.0.1:4455,server=on,wait=off")
            self.assertFalse(any("tcp::" in part for part in command))

    def test_status_and_resume_over_qmp(self):
        server = FakeQmpServer(running=False)
        try:
            run = RouteRun()
            run.qmp_port = server.port
            self.assertEqual(probe.xr.vm_status(run)["status"], "paused")
            self.assertTrue(probe.xr.vm_resume(run))
            self.assertTrue(probe.xr.vm_status(run)["running"])
            self.assertEqual(server.commands.count("qmp_capabilities"), 3)
            self.assertIn("cont", server.commands)
        finally:
            server.close()

    def test_no_qmp_means_no_status_and_no_resume(self):
        run = RouteRun()
        self.assertEqual(probe.xr.vm_status(run), {})
        self.assertFalse(probe.xr.vm_resume(run))
        run.qmp_port = 1  # nothing listens there
        self.assertEqual(probe.xr.vm_status(run), {})

    def cycle_frozen(self, running: bool):
        from unittest import mock

        slot = ScriptedTeamSelect("CHIEFS", frozen=True)
        resumed = []

        def resume(run):
            resumed.append(True)
            slot.frozen = False
            return True

        with mock.patch.object(probe, "tap", lambda pad, button, secs=0.15, settle=0.6: slot.press(button)), \
                mock.patch.object(probe, "read_slot", lambda run, box, tries=4: slot.read()), \
                mock.patch.object(probe, "safe_digest", lambda run: str(slot.index)), \
                mock.patch.object(probe, "keep_slot_miss", lambda run, side: None), \
                mock.patch.object(probe, "stall_samples", lambda run, notes: notes.update(stall_cpu=[{}, {}])), \
                mock.patch.object(probe, "log", lambda message: None), \
                mock.patch.object(probe.xr, "vm_status",
                                  lambda run: {"running": running, "status": "running" if running else "paused"}), \
                mock.patch.object(probe.xr, "vm_resume", resume), \
                mock.patch.dict(probe.ROUTE, {"name": "default"}):
            try:
                return probe.cycle_slot_to(RouteRun(), None, probe.HOME_SLOT, "COWBOYS", "home"), slot, resumed
            finally:
                probe.SLOT_NOTES.pop("freeze", None)
                probe.SLOT_NOTES.pop("stall_cpu", None)

    def test_paused_vm_at_team_select_is_resumed_not_a_freeze(self):
        # x1-v6-1: the hold at FW ALUMNI; the COWBOYS route of v5/v6-cowboys-1 held at COLTS.
        probe.SLOT_NOTES.pop("vm_paused", None)
        try:
            raw, slot, resumed = self.cycle_frozen(running=False)
            self.assertEqual(slot.entries[slot.index], "COWBOYS")
            self.assertEqual(resumed, [True])
            self.assertEqual(len(probe.SLOT_NOTES["vm_paused"]), 1)
            self.assertEqual(probe.SLOT_NOTES["vm_paused"][0]["status"], "paused")
        finally:
            probe.SLOT_NOTES.pop("vm_paused", None)

    def test_running_vm_with_a_held_frame_is_still_a_freeze(self):
        probe.SLOT_NOTES.pop("vm_paused", None)
        with self.assertRaises(probe.xr.GateError) as caught:
            self.cycle_frozen(running=True)
        self.assertEqual(caught.exception.gate, "team-select-freeze")
        self.assertNotIn("vm_paused", probe.SLOT_NOTES)

    def test_resumes_are_capped(self):
        from unittest import mock

        probe.SLOT_NOTES["vm_paused"] = [{}] * probe.VM_RESUMES_MAX
        try:
            with mock.patch.object(probe.xr, "vm_status", lambda run: {"running": False, "status": "paused"}), \
                    mock.patch.object(probe.xr, "vm_resume", lambda run: True), \
                    mock.patch.object(probe, "log", lambda message: None):
                self.assertFalse(probe.resume_if_paused(RouteRun(), "home slot"))
        finally:
            probe.SLOT_NOTES.pop("vm_paused", None)


@unittest.skipIf(probe is None, SKIP)
class StartGameTest(unittest.TestCase):
    COACH = COACH_RETAIL

    def start(self, clears_after: int | None):
        """clears_after: the press (1-based) after which the coach matchup goes; None = never."""
        from unittest import mock

        state = {"presses": 0, "now": 0.0}
        pressed: list[str] = []

        def press(button):
            pressed.append(button)
            state["presses"] += 1

        def screen_text(run):
            gone = clears_after is not None and state["presses"] >= clears_after
            return "" if gone else probe.xr.normalized(self.COACH)

        def sleep(secs):
            state["now"] += secs

        notes: dict = {}
        with mock.patch.object(probe, "tap", lambda pad, button, secs=0.15, settle=0.6: press(button)), \
                mock.patch.object(probe, "hold", lambda pad, button, secs: press(button)), \
                mock.patch.object(probe, "screen_text", screen_text), \
                mock.patch.object(probe.time, "sleep", sleep), \
                mock.patch.object(probe.time, "monotonic", lambda: state["now"]), \
                mock.patch.object(probe, "log", lambda message: None):
            probe.start_game(RouteRun(), None, notes)
        return pressed, notes

    def test_first_a_hold_starts_the_game(self):
        pressed, notes = self.start(1)
        self.assertEqual(pressed, ["A"])
        self.assertNotIn("coach_presses", notes)

    def test_a_hold_that_did_not_take_gets_a_second_press(self):
        # R-ne-1-r2, 2026-09-22: the retail coach matchup ignored the A hold.
        pressed, notes = self.start(2)
        self.assertEqual(pressed, ["A", "A"])
        self.assertEqual(notes["coach_presses"], 2)

    def test_coach_matchup_that_never_clears_is_a_route_error(self):
        with self.assertRaises(probe.xr.GateError) as caught:
            self.start(None)
        self.assertEqual(probe.ROUTE_REASONS[caught.exception.gate], "coach-matchup-stuck")


@unittest.skipIf(probe is None, SKIP)
class SlotReadTest(unittest.TestCase):
    def test_one_ocr_miss_still_names_the_team(self):
        self.assertTrue(probe.slot_has("QE EBIILS CD", "BILLS"))
        self.assertTrue(probe.slot_has("SE EREDSKINS FE", "REDSKINS"))
        self.assertFalse(probe.slot_has("JM EPATRIOTS. ID", "BEARS"))

    def read_slot_script(self, reads: list[str], tries: int):
        from unittest import mock

        clock = {"now": 0.0}
        script = iter(reads)

        def slot_name(run, box):
            clock["now"] += 0.3
            return next(script, reads[-1])

        def sleep(secs):
            clock["now"] += secs

        with mock.patch.object(probe, "slot_name", slot_name), mock.patch.object(probe.time, "sleep", sleep), \
                mock.patch.object(probe.time, "monotonic", lambda: clock["now"]):
            return probe.read_slot(None, probe.HOME_SLOT, tries=tries), clock["now"]

    def test_blank_slot_is_read_again_until_the_name_arrives(self):
        # R-ne-1, 2026-09-22: the retail slot read blank for a second or two after a pulse.
        (raw, team), _ = self.read_slot_script(["", "", "", "", "", "JM EPATRIOTS. ID"], tries=1)
        self.assertEqual(team, "PATRIOTS")

    def test_retail_home_slot_needs_the_wide_box(self):
        # test-R2, 2026-09-22: the retail home slot read PATRIOTS as nothing in the first box and
        # as the name in the wider one; the ledger counts the alternate read.
        from unittest import mock

        def slot_name(run, box):
            return "" if tuple(box) == probe.HOME_SLOT else "JE SESE PATRIOTS"

        before = probe.SLOT_NOTES["alt_reads"]
        with mock.patch.object(probe, "slot_name", slot_name):
            raw, team = probe.read_slot(None, probe.HOME_SLOT, tries=1)
        self.assertEqual(team, "PATRIOTS")
        self.assertEqual(probe.SLOT_NOTES["alt_reads"], before + 1)

    def test_unreadable_slot_still_gives_up(self):
        (raw, team), spent = self.read_slot_script(["SE =6ER"], tries=3)
        self.assertEqual(team, "")
        (raw, team), spent = self.read_slot_script([""], tries=3)
        self.assertEqual(team, "")
        self.assertLess(spent, probe.SLOT_BLANK_SECONDS + 2.0)


if __name__ == "__main__":
    unittest.main()
