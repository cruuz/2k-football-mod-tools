#!/usr/bin/env python3
"""Drive headless xemu into NFL 2K5 Practice → Scrimmage (offense only) and take orders.

Same plumbing as ``tools/xemu_play_author_runtime.py`` (isolated overlay, nested Xephyr,
virtual pad, gdb stub) but the route goes Main Menu → Game Modes → Practice → Scrimmage →
Team Select (RT until the Falcons are the away team) → field, where the offense has
unlimited time at the line.  Noah's tip 2026-09-03: this is the controlled way to test
throws, catches and acceleration — snap when ready, no defense, endless attempts.

Menu facts (from a screen recording of Noah navigating, 2026-09-03):
  GAME MODES rows: FRANCHISE, FIRST PERSON FOOTBALL, ESPN 25TH ANNIVERSARY, PRACTICE,
                   SITUATION, TOURNAMENT          -> PRACTICE is row 4
  PRACTICE rows:   BASIC TRAINING, SCRIMMAGE       -> SCRIMMAGE is row 2
  SCRIMMAGE SETTINGS: Practice Type = Offense Only (default), Scrimmage Line, Yards To Go,
                   Defensive/Offensive AI Playcalling, Power Pocket -> START to continue
  TEAM SELECT:     random pair; RT cycles the away (right) team; START to begin
Cursor memory is unknown, so every menu is entered by pressing UP six times then DOWN n.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import xemu_playbook_create_runtime as xr  # noqa: E402
from xemu_play_author_runtime import command_loop  # noqa: E402

xr.FIRMWARE_SOURCE = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu"
log = xr.log


def tap(pad: xr.Gamepad, button: str, secs: float = 0.15, settle: float = 0.6) -> None:
    pad.send(f"TAP {button} {secs}", expect="TAPPED", timeout=10.0)
    time.sleep(settle)


def hold(pad: xr.Gamepad, button: str, secs: float) -> None:
    pad.send(f"HOLD {button}", expect=f"HOLD {button}")
    time.sleep(secs)
    pad.send(f"RELEASE {button}", expect=f"RELEASE {button}")


def screen_text(run: xr.XemuRun) -> str:
    try:
        return xr.normalized(run.ocr_full())
    except Exception:  # noqa: BLE001
        return ""


PROMPT_MARKS = ("CATALOG", "UNLOCK", "WELCOME BACK", "SUCCESSFULLY LOADED", "PRESS € TO", "PRESS A TO")


def is_prompt(text: str) -> bool:
    """A modal is up (Crib catalog call, Settings1 load box, ...)."""

    return any(m in text for m in PROMPT_MARKS)


_prompt_tries = {"catalog": 0, "unlock": 0, "shots": 0}
# "Unlock this catalog?" lists Cancel (default, highlighted) above OK: DOWN then A unlocks it.
UNLOCK_ANSWERS = (("DOWN", "A"), ("LEFT", "A"), ("RIGHT", "A"), ("UP", "A"), ("B",), ("A",))


def dismiss_prompt(run: xr.XemuRun, pad: xr.Gamepad, text: str, label: str) -> None:
    """Clear one modal.  The Settings1 load box takes A.  The Crib "new catalog available"
    call: B declines it; if it keeps coming back, choose a catalog with A and answer the
    "unlock this catalog?" question by trying each answer position in turn."""

    if _prompt_tries["shots"] < 6:
        run.screenshot(f"prompt-{_prompt_tries['shots']}", run.run_dir / "screens")
        _prompt_tries["shots"] += 1
    if "UNLOCK THIS CATALOG" in text:
        answer = UNLOCK_ANSWERS[_prompt_tries["unlock"] % len(UNLOCK_ANSWERS)]
        log(f"{label}: unlock question -> {' '.join(answer)}")
        for button in answer:
            tap(pad, button, settle=0.8)
        time.sleep(3.0)
        _prompt_tries["unlock"] += 1
        return
    if "CATALOG" in text or "WELCOME BACK" in text:
        button = "B" if _prompt_tries["catalog"] < 2 else "A"
        log(f"{label}: catalog prompt -> {button}")
        tap(pad, button, settle=3.0)
        _prompt_tries["catalog"] += 1
        return
    log(f"{label}: prompt {text[:80]!r} -> A")
    hold(pad, "A", xr.MODAL_A_HOLD)
    time.sleep(4.0)


def wait_text(run: xr.XemuRun, needles: tuple[str, ...], timeout: float, label: str,
              pad: xr.Gamepad | None = None) -> str:
    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        text = screen_text(run)
        if pad is not None and is_prompt(text):
            dismiss_prompt(run, pad, text, label)
            continue
        if any(n in text for n in needles):
            return text
        time.sleep(1.5)
    raise xr.GateError(label, f"none of {needles} on screen; saw {text[:160]!r}")


def choose_row(pad: xr.Gamepad, row: int) -> None:
    """Top the cursor out, then move down to a 1-based row and confirm."""

    for _ in range(6):
        tap(pad, "UP", settle=0.25)
    for _ in range(row - 1):
        tap(pad, "DOWN", settle=0.35)
    tap(pad, "A", settle=2.5)


def practice_route(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path, *, away_team: str = "FALCONS") -> None:
    started = time.monotonic()
    wait_text(run, ("PRESS", "START"), 480.0, "press-start")
    run.screenshot("01-press-start", out_dir)
    log(f"press start at +{time.monotonic() - started:.0f}s")
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    # Modals sit on top of the main menu: the Settings1 "successfully loaded" box right away,
    # then (with the VIP profile) the Crib phone rings a few seconds later with a "new catalog
    # available, press A to choose" prompt.  A clears each; the menu is bare when only its
    # rows are readable.
    main_menu = ("QUICKGAME", "QUICK GAME", "GAMEMODES", "GAME MODES", "MAINMENU", "MAIN MENU")
    for attempt in range(8):
        text = screen_text(run)
        if any(m in text for m in main_menu) and not is_prompt(text):
            time.sleep(5.0)                  # let the Crib call arrive, then look again
            if not is_prompt(screen_text(run)):
                break
            continue
        dismiss_prompt(run, pad, text, f"modal {attempt}")
    run.screenshot("02-main-menu", out_dir)
    choose_row(pad, 2)                       # Main Menu row 2 = GAME MODES
    text = wait_text(run, ("GAME MODES", "GAMEMODES", "FRANCHISE"), 30.0, "game-modes", pad=pad)
    run.screenshot("03-game-modes", out_dir)
    choose_row(pad, 4)                       # PRACTICE
    text = wait_text(run, ("PRACTICE", "SCRIMMAGE", "BASIC TRAINING"), 30.0, "practice-menu", pad=pad)
    run.screenshot("04-practice", out_dir)
    choose_row(pad, 2)                       # SCRIMMAGE
    text = wait_text(run, ("SCRIMMAGE", "PRACTICE TYPE", "OFFENSE ONLY"), 30.0, "scrimmage-settings", pad=pad)
    run.screenshot("05-scrimmage-settings", out_dir)
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    text = wait_text(run, ("TEAM SELECT", "TEAMSELECT", "CURRENT UNIFORM"), 40.0, "team-select", pad=pad)
    run.screenshot("06-team-select", out_dir)
    pulses = 0
    while away_team not in text and pulses < 40:
        tap(pad, "RT", secs=xr.TRIGGER_PULSE, settle=0.7)
        pulses += 1
        text = screen_text(run)
    log(f"team select after {pulses} RT pulses: {text[:100]!r}")
    run.screenshot("07-team-select-away", out_dir)
    hold(pad, "START", xr.START_HOLD)
    time.sleep(6.0)
    # Some builds show a play-call or controller-assign screen before the field: A pushes through.
    for _ in range(3):
        text = screen_text(run)
        if "PAGE" in text or "PLAY" in text or "COACH" in text:
            tap(pad, "A", settle=2.0)
        else:
            break
    run.screenshot("08-field", out_dir)
    log("practice field reached (probably); use 'shot' to confirm")


def quick_game_route(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path, *, away_team: str = "FALCONS") -> None:
    """Main Menu → START (Quick Game) → Team Select (RT until the away team) → START → coach matchup A → game.
    Same prompt handling as the practice route; ends when the game itself is loading."""

    started = time.monotonic()
    wait_text(run, ("PRESS", "START"), 480.0, "press-start")
    run.screenshot("01-press-start", out_dir)
    log(f"press start at +{time.monotonic() - started:.0f}s")
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    main_menu = ("QUICKGAME", "QUICK GAME", "GAMEMODES", "GAME MODES", "MAINMENU", "MAIN MENU")
    for attempt in range(8):
        text = screen_text(run)
        if any(m in text for m in main_menu) and not is_prompt(text):
            time.sleep(5.0)
            if not is_prompt(screen_text(run)):
                break
            continue
        dismiss_prompt(run, pad, text, f"modal {attempt}")
    run.screenshot("02-main-menu", out_dir)
    hold(pad, "START", xr.START_HOLD)          # Quick Game
    time.sleep(4.0)
    text = wait_text(run, ("TEAM SELECT", "TEAMSELECT", "CURRENT UNIFORM", "PRESS L R"), 40.0, "team-select", pad=pad)
    run.screenshot("03-team-select", out_dir)
    pulses = 0
    while away_team not in text and pulses < 40:
        tap(pad, "RT", secs=xr.TRIGGER_PULSE, settle=0.7)
        pulses += 1
        text = screen_text(run)
    log(f"team select after {pulses} RT pulses: {text[:100]!r}")
    run.screenshot("04-team-select-away", out_dir)
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    run.screenshot("05-coach-matchup", out_dir)
    hold(pad, "A", xr.MODAL_A_HOLD)
    log("game starting; use 'wait N' then 'shot' bursts for the kickoff and first plays")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xiso", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--away-team", default="FALCONS")
    ap.add_argument("--skip-route", action="store_true")
    ap.add_argument("--mode", choices=("practice", "quick-game"), default="practice")
    args = ap.parse_args()
    xiso = Path(args.xiso)
    run_dir = Path(args.run_dir); run_dir.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "screens"; out_dir.mkdir(exist_ok=True)
    xr.abort_if_xemu_running()
    isolation = xr.setup_isolation(run_dir, xiso)
    log(json.dumps(isolation, indent=1))
    display = xr.pick_display()
    port = 1234
    while not xr.port_free(port):
        port += 1
    run = xr.XemuRun(run_dir, display, port)
    pad = None
    try:
        run.start_display()
        pad = xr.Gamepad()
        run.start_xemu(xiso)
        log(f"xemu up on :{display}, gdb tcp::{port}")
        if not args.skip_route:
            route = quick_game_route if args.mode == "quick-game" else practice_route
            route(run, pad, out_dir, away_team=args.away_team.upper())
        command_loop(run, pad, run_dir, out_dir)
    except Exception as exc:  # noqa: BLE001
        log(f"FAILED: {type(exc).__name__}: {exc}")
        try:
            run.screenshot("zz-failure", out_dir)
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        if pad is not None:
            pad.quit()
        log(json.dumps(run.shutdown()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
