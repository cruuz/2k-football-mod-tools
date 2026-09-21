#!/usr/bin/env python3
"""Drive a built disc through Quick Game and say whether it survives the Berman intro.

The beta 61-69 "Berman freeze" was root-caused on 2026-09-15 in this same
harness: a kernel bugcheck (code 0x1E, a null read buffer in the resource
loader after an allocation failure) during the intro, triggered by the volume
of appended HUD resources. Beta 73 reports say it is back. This probe is the
reproduction, made unattended: the same Quick Game route, then a watch on the
screen and on the guest CPU until either the coin toss / kickoff is on screen
(PASS), the CPU sits in the kernel with the screen frozen (BUGCHECK), or the
time runs out (TIMEOUT). One line of result and a JSON ledger per run.

Headless by construction: the nested display is Xvfb (nothing appears on the
desktop), audio is the dummy driver, and the caller is expected to wrap this
in ``nice -n 19``. It refuses to start while another xemu is running.

  tools/xemu_berman_probe.py --xiso DISC --run-dir DIR [--minutes 8] [--label NAME]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import xemu_playbook_create_runtime as xr  # noqa: E402
from xemu_practice_runtime import (  # noqa: E402
    dismiss_prompt, hold, is_prompt, quick_game_route, screen_text, tap, wait_text)

xr.FIRMWARE_SOURCE = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu"
log = xr.log

#: Words that only appear once the intro is over and the game is being set up.
REACHED = ("COIN", "TOSS", "HEADS", "TAILS", "KICKOFF", "KICK OFF", "RECEIVE", "1ST & 10",
           "1ST&10", "1ST AND 10", "CALL IT")
#: The Xbox kernel lives at 0x80000000; the bugcheck loop of 2026-09-15 sat at 0x800151EF.
KERNEL = (0x80000000, 0x80080000)


class HeadlessRun(xr.XemuRun):
    """XemuRun on Xvfb instead of Xephyr: no window on the desktop."""

    def start_display(self):
        self.xephyr = subprocess.Popen(
            ["Xvfb", f":{self.display}", "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)
        import os
        env = dict(os.environ, DISPLAY=f":{self.display}")
        self.metacity = subprocess.Popen(
            ["metacity", "--sm-disable"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)
        self.window = xr.Window(self.display)


#: The 2026-09-15 bugcheck: the kernel loop at 0x800151EF with eax = 0x1E
#: (KMODE_EXCEPTION_NOT_HANDLED). A lone in-kernel EIP proves nothing; the
#: guest is in a kernel prologue most of the time it is sampled.
BUGCHECK_EIP = (0x80015100, 0x80015300)
BUGCHECK_CODE = 0x1E


def sample_cpu(port: int, log_path: Path) -> dict:
    """One-shot batch gdb: attach, read eip/eax/ecx/esp and the next three
    instructions, detach so the guest runs on. The shared interactive session
    never sees gdb's newline-less prompt under this xemu build; a batch run
    has no prompt to wait for. Proved live on 2026-09-20 (sub-second halt)."""

    command = ["gdb", "-q", "-nx", "-batch", "-ex", "set pagination off", "-ex", "set confirm off",
               "-ex", f"target remote 127.0.0.1:{port}", "-ex", "info registers eip eax ecx esp",
               "-ex", "x/3i $eip", "-ex", "detach"]
    done = subprocess.run(command, capture_output=True, text=True, timeout=45)
    log_path.write_text(done.stdout + done.stderr, encoding="utf-8", newline="\n")
    values: dict = {}
    for line in done.stdout.splitlines():
        found = re.match(r"\s*(eip|eax|ecx|esp)\s+0x([0-9a-fA-F]+)", line)
        if found:
            values[found.group(1)] = int(found.group(2), 16)
    code = [line.strip() for line in done.stdout.splitlines() if re.match(r"\s*(=>)?\s*0x8", line) and ":" in line]
    if code:
        values["at"] = code[:3]
    if not values:
        values["error"] = (done.stderr.strip().splitlines() or ["no registers"])[-1][:120]
    return values


def frame_digest(run: xr.XemuRun) -> str:
    return hashlib.sha256(run._frame().tobytes()).hexdigest()[:16]


#: How long the picture may sit perfectly still, once the intro has started
#: moving, before it is called frozen. The Berman intro is full-motion video,
#: so a run that has shown motion and then holds one identical frame this long
#: is not a slow load; it is the hang.
FREEZE_SECONDS = 75.0
#: The first frames are the black boot and the attract loop; motion before this
#: does not count as "the intro started".
MOTION_GRACE_SECONDS = 20.0


#: The name bar on Team Select, in the 1280x720 capture: "AWAY AT HOME" at y 104..132,
#: the away name in the left slot and the home name in the right slot.
HOME_SLOT = (690, 104, 960, 132)
AWAY_SLOT = (330, 104, 600, 132)


def slot_name(run: xr.XemuRun, box) -> str:
    from PIL import ImageEnhance
    image = run._frame().convert("L").crop(box)
    image = image.resize((image.width * 4, image.height * 4))
    image = ImageEnhance.Contrast(image).enhance(2.0)
    return xr.normalized(xr._ocr_image(image, 7))


def slot_has(slot: str, name: str) -> bool:
    """The name is in the slot, allowing one OCR miss: "BILLS" read as "BIILS"
    or "B1LLS" forty pulses running (B/Bills, 2026-09-20) while the longer
    names read cleanly. Exact substring first, then a close alphabetic token."""
    if name in slot:
        return True
    import difflib
    letters = re.sub(r"[^A-Z0-9]", "", slot)
    for width in (len(name) - 1, len(name), len(name) + 1):
        for start in range(0, max(0, len(letters) - width) + 1):
            if difflib.SequenceMatcher(None, name, letters[start:start + width]).ratio() >= 0.8:
                return True
    return False


#: Team Select cycles the nicknames in alphabetical order (Giants -> Patriots
#: took six RT pulses: Jaguars, Jets, Lions, Packers, Panthers, Patriots).
TEAMS = ("49ERS", "BEARS", "BENGALS", "BILLS", "BRONCOS", "BROWNS", "BUCCANEERS", "CARDINALS",
         "CHARGERS", "CHIEFS", "COLTS", "COWBOYS", "DOLPHINS", "EAGLES", "FALCONS", "GIANTS",
         "JAGUARS", "JETS", "LIONS", "PACKERS", "PANTHERS", "PATRIOTS", "RAIDERS", "RAMS",
         "RAVENS", "REDSKINS", "SAINTS", "SEAHAWKS", "STEELERS", "TEXANS", "TITANS", "VIKINGS")


def read_slot(run: xr.XemuRun, box, tries: int = 4) -> tuple[str, str]:
    """(raw OCR line, the team it names or '') from up to ``tries`` frames.

    One read per pulse missed REDSKINS on two full laps of the list (2026-09-20):
    the slot is read again a few times before it counts as unknown.
    """
    raw = ""
    for attempt in range(tries):
        raw = slot_name(run, box)
        for team in TEAMS:
            if slot_has(raw, team):
                return raw, team
        time.sleep(0.35)
    return raw, ""


def cycle_slot_to(run: xr.XemuRun, pad: xr.Gamepad, box, team: str, side: str) -> str:
    """Cycle one Team Select slot with RT until it names ``team``; the OCR line.

    The current name gives the number of pulses (the list order is known), the
    slot is read again at the end, and a miss falls back to single pulses with a
    read after each one, so one bad read never costs a lap of the list.
    """
    require = team in TEAMS
    if not require:
        raise xr.GateError("team-select", f"{team} is not a Team Select nickname")
    raw, current = read_slot(run, box)
    log(f"{side} slot reads {raw!r} -> {current or 'unknown'}")
    if current:
        for _ in range((TEAMS.index(team) - TEAMS.index(current)) % len(TEAMS)):
            tap(pad, "RT", secs=xr.TRIGGER_PULSE, settle=0.6)
        raw, current = read_slot(run, box)
        log(f"{side} slot after the computed pulses reads {raw!r} -> {current or 'unknown'}")
    pulses = 0
    while current != team and pulses < 40:
        tap(pad, "RT", secs=xr.TRIGGER_PULSE, settle=0.7)
        pulses += 1
        raw, current = read_slot(run, box, tries=3)
        log(f"{side} slot after single pulse {pulses}: {raw!r} -> {current or 'unknown'}")
    if current != team:
        raise xr.GateError("team-select", f"{team} never read in the {side} slot; last {raw!r}")
    return raw


def home_slot_name(run: xr.XemuRun) -> str:
    """OCR only the right slot of the Team Select name bar: the home team.

    Full-screen OCR read "FALCONS" once by luck and then never read "PATRIOTS"
    in forty pulses (2026-09-20, disc B), so the check is on the slot alone,
    upscaled and read as one line. The L/R arrow glyphs leak a few letters
    ("SEFALCONS"), so the caller tests the name as a substring.
    """
    from PIL import ImageEnhance
    image = run._frame().convert("L").crop(HOME_SLOT)
    image = image.resize((image.width * 4, image.height * 4))
    image = ImageEnhance.Contrast(image).enhance(2.0)
    return xr.normalized(xr._ocr_image(image, 7))


def quick_game_home(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path, *, home_team: str, away_team: str = "") -> str:
    """Main Menu -> Quick Game -> Team Select with a chosen HOME team -> coach matchup -> game.

    The right trigger cycles the right slot, which is the home team; the
    practice route's "away" naming had that backwards. andrethealchemist
    (2026-09-20): the freeze depends on which team is at home, so the probe has
    to choose it. Returns the team-select OCR line for the ledger.
    """
    main_menu = ("QUICKGAME", "QUICK GAME", "GAMEMODES", "GAME MODES", "MAINMENU", "MAIN MENU")
    # The title screen hands off to an attract-mode highlight demo after a short
    # idle; a run that misses the "PRESS START" window then reads the demo for
    # the whole wait (B/Giants, 2026-09-20). A START press leaves the demo, so
    # on each shorter timeout press it and accept either the title or the menu.
    deadline = time.monotonic() + 480.0
    at_menu = False
    while True:
        try:
            text = wait_text(run, ("PRESS", "START") + main_menu, 120.0, "press-start")
            at_menu = any(m in text for m in main_menu) and not is_prompt(text)
            break
        except xr.GateError:
            if time.monotonic() > deadline:
                raise
            log("no title screen yet (attract demo?); pressing START to leave it")
            tap(pad, "START", secs=0.3, settle=3.0)
    run.screenshot("01-press-start", out_dir)
    if not at_menu:
        hold(pad, "START", xr.START_HOLD)
        time.sleep(4.0)
    for attempt in range(8):
        text = screen_text(run)
        if any(m in text for m in main_menu) and not is_prompt(text):
            time.sleep(5.0)
            if not is_prompt(screen_text(run)):
                break
            continue
        dismiss_prompt(run, pad, text, f"modal {attempt}")
    run.screenshot("02-main-menu", out_dir)
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    text = wait_text(run, ("TEAM SELECT", "TEAMSELECT", "CURRENT UNIFORM", "PRESS L R"), 40.0,
                     "team-select", pad=pad)
    run.screenshot("03-team-select", out_dir)
    slot = cycle_slot_to(run, pad, HOME_SLOT, home_team, "home")
    text = slot
    if away_team:
        # The triggers cycle the slot the controller sits on, and it starts in
        # the middle where they cycle the home side (forty LT pulses left the
        # away slot untouched, 2026-09-20). D-pad LEFT moves the controller to
        # the away side, RT cycles that slot, D-pad RIGHT puts it back in the
        # middle so the rest of the route matches every earlier run.
        tap(pad, "LEFT", settle=1.0)
        try:
            left = cycle_slot_to(run, pad, AWAY_SLOT, away_team, "away")
        finally:
            tap(pad, "RIGHT", settle=1.0)
        home_after, home_read = read_slot(run, HOME_SLOT)
        if home_read != home_team:
            raise xr.GateError("team-select", f"home slot changed while choosing the away team: {home_after!r}")
        text = f"{left} AT {home_after}"
    run.screenshot("04-team-select-home", out_dir)
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    run.screenshot("05-coach-matchup", out_dir)
    hold(pad, "A", xr.MODAL_A_HOLD)
    log("game starting")
    return text[:200]


def watch(run: xr.XemuRun, out_dir: Path, port: int, minutes: float) -> dict:
    """Classify from the picture; gdb registers are a best-effort corroboration only.

    The screen is the trustworthy signal here: reaching the coin toss / kickoff
    is PASS, and a full-motion intro that then holds one identical frame past
    ``FREEZE_SECONDS`` is the freeze. The gdb sample is attempted and its EIP
    recorded when it works (the 2026-09-15 bugcheck sat at 0x800151EF), but the
    attach is unreliable under this xemu build, so a freeze is never gated on
    it -- a run with no CPU data still returns FROZEN on the frozen picture.
    """
    started = time.monotonic()
    deadline = started + minutes * 60
    samples: list[dict] = []
    frames: list[tuple[float, str]] = []
    seen_motion_at: float | None = None
    frozen_since: float | None = None
    last_shot = 0.0
    last_cpu = 0.0
    seen_text = ""
    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        text = screen_text(run)
        if text and text != seen_text:
            seen_text = text
            log(f"+{elapsed:.0f}s screen: {text[:120]!r}")
        if any(n in text for n in REACHED):
            run.screenshot(f"reached-{elapsed:.0f}s", out_dir)
            return dict(outcome="PASS", elapsed=round(elapsed, 1), text=text[:300], cpu=samples)
        digest = frame_digest(run)
        if frames and digest != frames[-1][1]:
            if elapsed >= MOTION_GRACE_SECONDS and seen_motion_at is None:
                seen_motion_at = elapsed
            frozen_since = None
        elif frames and digest == frames[-1][1] and frozen_since is None:
            frozen_since = elapsed
        frames.append((elapsed, digest))
        if elapsed - last_shot >= 30:
            run.screenshot(f"watch-{elapsed:03.0f}s", out_dir)
            last_shot = elapsed
        if elapsed - last_cpu >= 30:
            last_cpu = elapsed
            try:
                cpu = sample_cpu(port, run.logs / f"gdb-{elapsed:03.0f}s.log")
            except Exception as exc:  # noqa: BLE001
                cpu = dict(error=f"{type(exc).__name__}: {exc}")
            cpu["elapsed"] = round(elapsed, 1)
            samples.append(cpu)
            log(f"+{elapsed:.0f}s cpu: " + ", ".join(f"{k}={v:#x}" if isinstance(v, int) else f"{k}={v}"
                                                    for k, v in cpu.items() if k != "elapsed"))
        # A full-motion intro that then holds one frame past the freeze window,
        # having shown motion first, is the hang. The kernel EIP, when a sample
        # landed, says whether it is the 2026-09-15 bugcheck specifically.
        if (seen_motion_at is not None and frozen_since is not None
                and elapsed - frozen_since >= FREEZE_SECONDS):
            run.screenshot(f"frozen-{elapsed:.0f}s", out_dir)
            try:
                halted = sample_cpu(port, run.logs / "gdb-frozen.log")
            except Exception as exc:  # noqa: BLE001
                halted = dict(error=f"{type(exc).__name__}: {exc}")
            halted["elapsed"] = round(elapsed, 1)
            samples.append(halted)
            log("frozen; cpu: " + ", ".join(f"{k}={v:#x}" if isinstance(v, int) else f"{k}={v}"
                                          for k, v in halted.items() if k != "elapsed"))
            bugcheck = (BUGCHECK_EIP[0] <= halted.get("eip", 0) < BUGCHECK_EIP[1]
                        and halted.get("eax") == BUGCHECK_CODE)
            return dict(outcome="BUGCHECK" if bugcheck else "FROZEN",
                        elapsed=round(elapsed, 1), frozen_since=round(frozen_since, 1),
                        text=seen_text[:300], cpu=samples)
        time.sleep(10.0)
    run.screenshot("timeout", out_dir)
    return dict(outcome="TIMEOUT", elapsed=round(minutes * 60, 1),
                saw_motion=seen_motion_at is not None, text=seen_text[:300], cpu=samples)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xiso", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--away-team", default="FALCONS")
    ap.add_argument("--home-team", default="", help="cycle Team Select until this team is at home")
    ap.add_argument("--away-team-slot", default="", help="with --home-team: also cycle the left slot to this away team")
    ap.add_argument("--minutes", type=float, default=8.0)
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    xiso = Path(args.xiso)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "screens"
    out_dir.mkdir(exist_ok=True)
    xr.abort_if_xemu_running()
    isolation = xr.setup_isolation(run_dir, xiso)
    log(json.dumps(isolation, indent=1))
    display = xr.pick_display()
    port = 1234
    while not xr.port_free(port):
        port += 1
    run = HeadlessRun(run_dir, display, port)
    pad = None
    ledger = dict(label=args.label, xiso=str(xiso), outcome="ERROR", started=time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        run.start_display()
        pad = xr.Gamepad()
        run.start_xemu(xiso)
        log(f"xemu up on Xvfb :{display}, gdb tcp::{port}")
        route_started = time.monotonic()
        if args.home_team:
            ledger["home_team"] = args.home_team.upper()
            if args.away_team_slot:
                ledger["away_team"] = args.away_team_slot.upper()
            ledger["team_select"] = quick_game_home(run, pad, out_dir, home_team=args.home_team.upper(),
                                                    away_team=args.away_team_slot.upper())
        else:
            quick_game_route(run, pad, out_dir, away_team=args.away_team.upper())
        ledger["route_seconds"] = round(time.monotonic() - route_started, 1)
        ledger.update(watch(run, out_dir, port, args.minutes))
    except Exception as exc:  # noqa: BLE001
        ledger["error"] = f"{type(exc).__name__}: {exc}"
        log(f"FAILED: {ledger['error']}")
        try:
            run.screenshot("zz-failure", out_dir)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if pad is not None:
            pad.quit()
        ledger["shutdown"] = run.shutdown()
        (run_dir / "berman-probe.json").write_text(json.dumps(ledger, indent=1) + "\n",
                                                   encoding="utf-8", newline="\n")
        print(f"BERMAN_PROBE label={args.label or '-'} away={ledger.get('away_team', '?')} home={ledger.get('home_team', '-')} "
              f"outcome={ledger['outcome']} elapsed={ledger.get('elapsed', 0):.0f}s", flush=True)
    return 0 if ledger["outcome"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
