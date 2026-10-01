#!/usr/bin/env python3
"""Drive a built disc through Quick Game and say whether it survives the Berman intro.

The beta 61-69 "Berman freeze" was root-caused on 2026-09-15 in this same
harness: a kernel bugcheck (code 0x1E, a null read buffer in the resource
loader after an allocation failure) during the intro, triggered by the volume
of appended HUD resources. Beta 73 reports say it is back. This probe is the
reproduction, made unattended: the same Quick Game route, then a watch on the
screen and on the guest CPU until either the coin toss / kickoff is on screen
(PASS), the CPU sits in the kernel with the screen frozen (BUGCHECK), the
picture holds one frame (FROZEN), xemu itself dies on the nv2a pushbuffer
assert (PFIFO_ABORT) or any other exit (XEMU_EXIT), or the time runs out
(TIMEOUT). A run that never reaches the intro is ERROR with a ``route_error``
reason. One line of result and a JSON ledger per run.

Outcome classes, and what each one measured:

  PASS         a coin-toss / kickoff word was read on screen after the intro.
  FROZEN       the intro showed motion, then one identical frame held for
               FREEZE_SECONDS; the gdb sample did not show the 0x1E bugcheck.
  BUGCHECK     as FROZEN, and the halted CPU sat in the 2026-09-15 kernel loop.
  PFIFO_ABORT  the xemu process exited during the intro on an nv2a pfifo.c
               assert: "pfifo_run_pusher: ... Reserved pb command" (line 426,
               the guest handed the GPU an invalid pushbuffer command) or
               "ramht_lookup: ... hash * 8 < ramht_size" (line 518, a command
               named an object handle outside the hash table); ``xemu_exit``
               keeps the line and its ``site``. Every "xemu window vanished"
               ERROR of the 2026-09-20/21 series was the line 426 assert (11
               of 48 probe attempts), the same signature as the one run that
               session called the freeze. The probe measured only the xemu
               abort; it has no hardware witness of what that command does on
               a console.
  XEMU_EXIT    xemu exited during the intro without that assert.
  TIMEOUT      neither of the above within --minutes.
  ERROR        the route never reached the intro; ``route_error`` says why:
               boot-stall, boot-freeze (one identical frame for 90 s with
               xemu alive), attract-demo, title-stuck, settings-load-stuck,
               settings-box-stuck, menu-unreadable, main-menu-stuck,
               team-select-ocr, team-select-freeze (five pulses in a row left
               the frame unchanged while QMP says the VM is running; a VM
               that is not running is resumed and logged as ``vm_paused``,
               see resume_if_paused), coach-matchup-stuck (the game never
               started), xemu-pfifo-abort / xemu-exit (died before the intro),
               or the harness gate that failed. ``route`` says
               which route variant ran (``--route retail`` for the untouched
               retail disc); a route difference is never an outcome.

Headless by construction: the nested display is Xvfb (nothing appears on the
desktop), audio is the dummy driver, and the caller is expected to wrap this
in ``nice -n 19``. It refuses to start while another xemu is running.

  tools/xemu_berman_probe.py --xiso DISC --run-dir DIR [--minutes 8] [--label NAME]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import xemu_playbook_create_runtime as xr  # noqa: E402
from xemu_practice_runtime import (  # noqa: E402
    dismiss_prompt, hold, is_prompt, quick_game_route, screen_text, tap)

xr.FIRMWARE_SOURCE = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu"
log = xr.log

#: Words that only appear once the intro is over and the game is being set up.
REACHED = ("COIN", "TOSS", "HEADS", "TAILS", "KICKOFF", "KICK OFF", "RECEIVE", "1ST & 10",
           "1ST&10", "1ST AND 10", "CALL IT")
#: A screen counts as reached only when it shows at least this many different REACHED words. One word alone can be
#: OCR noise: on 2026-09-22 (z2, run proof-10) a lone "COIN" read over the pregame stadium flyover at +41 s ended the
#: watch mid-intro, while every genuine coin-toss screen reads two or more ("COIN TOSS", "TOSS ... RECEIVE",
#: "HEADS ... RECEIVE").
REACHED_MIN = 2


def reached(text: str) -> bool:
    """True when the OCR text shows at least REACHED_MIN different words from REACHED."""
    return sum(1 for word in REACHED if word in text) >= REACHED_MIN
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
    code = [line.strip() for line in done.stdout.splitlines() if re.match(r"\s*(=>)?\s*0x[0-9a-fA-F]+:", line)]
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


# --------------------------------------------------------------------------
# Screen states on the way to the menu
# --------------------------------------------------------------------------

#: Static words of the ESPN title card. Its "PRESS START" line blinks and the
#: full-screen OCR never read it in any 2026-09-21 PASS run (01-press-start.png
#: of each one reads "MPEG SOFDEC ... 2K5 ... PLAYERS (c) SEGA CORPORATION,
#: 2004"); the old gate matched the blink by luck, and a run that missed it
#: idled into the attract demo (A-3, 2026-09-21).
TITLE_MARKS = ("SOFDEC", "SEGA CORPORATION", "2K5")
#: The legal card shares "SEGA CORPORATION, 2004" and "PLAYERS" with the title.
LEGAL_MARKS = ("PROPERTIES", "TRADEMARK", "LICENSED")
#: The Visual Concepts logo reads "WVISUAG CEPTS" (D1-2, 2026-09-21).
LOGO_MARKS = ("VISUA", "CEPTS", "CONCEPTS")
#: The main menu's rows; FEATURES, OPTIONS, XBOXLIVE and EXTRAS read in every
#: 02-main-menu frame of 2026-09-21 even when the header did not.
MENU_MARKS = ("QUICKGAME", "QUICK GAME", "GAMEMODES", "GAME MODES", "MAINMENU", "MAIN MENU",
              "PLAYNOW", "PLAY NOW", "THECRIB", "THE CRIB", "XBOXLIVE", "XBOX LIVE", "EXTRAS", "FEATURES")
TEAM_SELECT_MARKS = ("TEAM SELECT", "TEAMSELECT", "CURRENT UNIFORM", "PRESS L R", "RANDOM TEAM")
#: Team Select's ratings panel. Its header OCRs only some of the time (A-2,
#: 2026-09-21; test-1, 2026-09-22, read "... GIANTS ... OFFENSE ... DEFENSE"
#: and was taken for the attract demo, whose START then began a game with the
#: default teams); two of these three words read in every Team Select frame.
RATING_MARKS = ("OFFENSE", "DEFENSE", "OVERALL")
#: The screen after Team Select's START; A here starts the game.
COACH_MARKS = ("COACHMATCHUP", "COACH MATCHUP", "PLAYCALLING")
#: "Loading Settings Settings1 from Xbox Hard Disk. Please do not turn the
#: power off." has no button; it is waited out, never pressed (D2-8 held A at
#: it eight times, 2026-09-21).
LOADING_MARKS = ("LOADING SETTINGS", "TURN THE POWER", "DO NOT TURN")
#: "Successfully loaded Settings Settings1 from Xbox Hard Disk." with one OK.
LOADED_MARKS = ("SUCCESSFULLY LOADED",)

#: Every PASS run of 2026-09-21 held START at the title 138-140 s after xemu
#: came up; the boot is that regular. START is tapped from here on so the
#: title cannot idle into the attract demo.
TAP_START_AFTER = 100.0
#: A boot still on the legal card, the logo or a blank screen this long is a
#: stalled or starved guest (B-7, B-8, D1-2 sat there for eight minutes).
BOOT_STALL_SECONDS = 300.0
#: ... or one that has shown nothing but those screens for this long without
#: a break. A healthy boot leaves them for the intro movie by +57 s at the
#: latest (its longest unbroken stretch on 2026-09-22 was 34 s); test-4 went
#: black at +12 s, before any input, and stayed black.
BOOT_QUIET_SECONDS = 150.0
#: A picture that holds one identical frame this long before the menu is a
#: frozen guest, not a slow one: C-ne-1 (2026-09-22) sat on one frame of the
#: ESPN boot movie from before +151 s to +482 s through sixty presses, with
#: xemu alive, and the old route called it the attract demo. Every screen on
#: the way to the menu animates or changes within a few seconds.
BOOT_FREEZE_SECONDS = 90.0
#: The whole boot-to-menu budget.
BOOT_DEADLINE_SECONDS = 480.0
#: The Settings1 load box normally lasts under two seconds.
SETTINGS_LOAD_SECONDS = 90.0
#: The attract-demo escape ladder, one press per rung every ESCAPE_EVERY seconds.
#: It runs only before the title or a settings box has been seen: after that
#: the screens are the box, the menu and Team Select, where a blind START or A
#: starts a game with the default teams (test-1, 2026-09-22).
ESCAPE_LADDER = ("START", "START", "START", "B", "A", "START_HOLD", "BACK")
ESCAPE_EVERY = 3.0
#: After the title, an unreadable screen is a transition or a misread menu;
#: it gets this long untouched, then one B (back, never forward) every
#: POST_TITLE_BACK_EVERY seconds.
POST_TITLE_GRACE = 30.0
POST_TITLE_BACK_EVERY = 6.0
#: The settings box fades for a few seconds after its A: test-1 still read the
#: box 3 s after the press that closed it, and the next A then chose PLAY NOW
#: on the menu behind it. Each press is given this long to take effect.
BOX_SETTLE_SECONDS = 9.0


def screen_state(text: str) -> str:
    """Name the screen from its OCR line. The settings boxes sit on the title,
    so they are tested before the title words."""
    if any(m in text for m in LOADING_MARKS):
        return "settings-loading"
    if any(m in text for m in LOADED_MARKS):
        return "settings-loaded"
    if is_prompt(text):
        return "prompt"
    if any(m in text for m in TEAM_SELECT_MARKS) or sum(m in text for m in RATING_MARKS) >= 2:
        return "team-select"
    if any(m in text for m in COACH_MARKS):
        return "coach-matchup"
    if any(m in text for m in MENU_MARKS):
        return "menu"
    if any(m in text for m in LEGAL_MARKS):
        return "legal"
    if any(m in text for m in LOGO_MARKS):
        return "logo"
    if any(m in text for m in TITLE_MARKS) or ("PRESS" in text and "START" in text):
        return "title"
    if not text.strip():
        return "blank"
    return "other"


def settle_modal(run: xr.XemuRun, pad: xr.Gamepad, text: str, state: str, label: str) -> str:
    """Clear one box on the way to the menu and return the text that replaced it.

    The load box is waited out. The "successfully loaded" box takes A; if the
    same box is still there BOX_SETTLE_SECONDS later it is tried again with
    A, then B, then START, then the old three-second A hold (B-2 held A
    fourteen times at a box that never went, 2026-09-21: after these six
    presses it is a stuck guest and the run says so instead of spending four
    minutes). Each press is re-read every 1.5 s until the box has gone, so a
    box that is only fading never takes a second press. The Crib call and
    catalog boxes go through the practice route's dismiss_prompt.
    """
    if state == "settings-loading":
        deadline = time.monotonic() + SETTINGS_LOAD_SECONDS
        while time.monotonic() < deadline:
            time.sleep(2.0)
            text = screen_text(run)
            if screen_state(text) != "settings-loading":
                return text
        raise xr.GateError("settings-load", f"the Settings1 load box never finished; saw {text[:120]!r}")
    if state == "settings-loaded":
        presses = (("A", 0.3), ("A", 0.3), ("B", 0.3), ("START", 0.3), ("A", xr.MODAL_A_HOLD), ("A", 0.3))
        for index, (button, secs) in enumerate(presses):
            log(f"{label}: settings box -> {button} {secs:.1f}s (press {index + 1}/{len(presses)})")
            if secs >= 1.0:
                hold(pad, button, secs)
            else:
                tap(pad, button, secs=secs, settle=0.0)
            deadline = time.monotonic() + BOX_SETTLE_SECONDS
            while True:
                time.sleep(1.5)
                text = screen_text(run)
                if screen_state(text) != "settings-loaded":
                    return text
                if time.monotonic() >= deadline:
                    break
        raise xr.GateError("settings-box", f"the settings box ignored {len(presses)} presses; saw {text[:120]!r}")
    dismiss_prompt(run, pad, text, label)
    return screen_text(run)


def stall_samples(run: xr.XemuRun, notes: dict) -> None:
    """Two register samples two seconds apart when a boot stalls, kept in the
    ledger as ``stall_cpu``: an EIP that moves is a guest that runs but draws
    nothing, one that holds is a stuck guest."""
    # Ask the run state first: attaching gdb pauses the VM and its detach resumes it.
    notes["vm_status_before_gdb"] = xr.vm_status(run)
    samples = []
    for index in range(2):
        try:
            sample = sample_cpu(run.gdb_port, run.logs / f"gdb-stall-{index}.log")
        except Exception as exc:  # noqa: BLE001
            sample = dict(error=f"{type(exc).__name__}: {exc}")
        samples.append(sample)
        log(f"boot stall cpu {index}: " + ", ".join(f"{k}={v:#x}" if isinstance(v, int) else f"{k}={v}"
                                                    for k, v in sample.items()))
        if index == 0:
            time.sleep(2.0)
    notes["stall_cpu"] = samples


def read_screen(run: xr.XemuRun) -> tuple[str, str]:
    """(OCR line, frame digest) from one capture, the digest for the frozen
    picture check; ("", "") when the capture fails."""
    try:
        image = run._frame()
    except Exception:  # noqa: BLE001
        return "", ""
    try:
        text = xr.normalized(xr._ocr_image(image, 11))
    except Exception:  # noqa: BLE001
        text = ""
    return text, hashlib.sha256(image.tobytes()).hexdigest()[:16]


def check_alive(run: xr.XemuRun) -> None:
    """Stop the route the moment xemu has gone (test-1, 2026-09-22, died on a
    pfifo assert and the route kept reading a blank screen for 8 s more)."""
    if run.xemu is not None and run.xemu.poll() is not None:
        raise xr.GateError("xemu", "xemu exited during the route")


def reach_menu(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path, notes: dict) -> tuple[str, str]:
    """Boot -> title -> settings box -> main menu (or Team Select); returns
    (state, OCR line) with state "menu" or "team-select".

    The title is recognised by its static words, START is tapped every few
    seconds once the boot is past TAP_START_AFTER so the title cannot idle
    into the attract demo, and if the picture is already the demo (moving,
    no readable words, past the title time) the escape ladder runs: START
    taps, then B, A, a long START hold and BACK, each checked against the
    title / box / menu words. Once the title or a settings box has been seen
    the ladder is off: an unreadable screen is left alone for
    POST_TITLE_GRACE and then only backed out of with B, because START or A
    there can start a game from a misread Team Select (test-1, 2026-09-22).
    A coach matchup reached by mistake is backed out of the same way. A boot
    that has shown only the legal card, the logo or black for
    BOOT_QUIET_SECONDS, or is still on one of them at BOOT_STALL_SECONDS, is
    reported as a stall rather than waited on, with two register samples.
    ``notes`` collects the states seen and the presses tried for the ledger.
    """
    started = time.monotonic()
    last_press = 0.0
    starts_at_title = 0
    escapes = 0
    backs = 0
    past_title = False
    other_since: float | None = None
    quiet_since: float | None = None
    held_digest, held_since = "", time.monotonic()
    seen: dict[str, int] = {}
    last_state = ""
    while True:
        check_alive(run)
        elapsed = time.monotonic() - started
        text, digest = read_screen(run)
        state = screen_state(text)
        if not digest or digest != held_digest:
            held_digest, held_since = digest, time.monotonic()
        elif time.monotonic() - held_since >= BOOT_FREEZE_SECONDS and resume_if_paused(run, f"boot +{elapsed:.0f}s"):
            held_digest, held_since = "", time.monotonic()
            continue
        elif time.monotonic() - held_since >= BOOT_FREEZE_SECONDS:
            held = time.monotonic() - held_since
            notes["frozen_picture"] = dict(state=state, since=round(elapsed - held, 1), seconds=round(held, 1),
                                           presses_before=escapes + backs + starts_at_title,
                                           past_title=past_title, text=text[:120])
            run.screenshot("zz-held-frame", out_dir)
            stall_samples(run, notes)
            gate = "boot" if state in ("legal", "logo", "blank") else "boot-freeze"
            raise xr.GateError(gate, f"one identical {state} frame for {held:.0f}s from +{elapsed - held:.0f}s; "
                                     f"saw {text[:120]!r}")
        seen[state] = seen.get(state, 0) + 1
        notes["boot_states"] = seen
        if state != last_state:
            log(f"boot +{elapsed:.0f}s {state}: {text[:100]!r}")
            last_state = state
        if state != "other":
            other_since = None
        elif other_since is None:
            other_since = time.monotonic()
        if state not in ("legal", "logo", "blank") or past_title:
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.monotonic()
        if state == "menu":
            # The Crib phone rings a few seconds after the menu appears; let it.
            time.sleep(5.0)
            text = screen_text(run)
            state = screen_state(text)
            if state in ("menu", "team-select"):
                return state, text
            if state in ("prompt", "settings-loaded", "settings-loading"):
                settle_modal(run, pad, text, state, "menu modal")
            continue
        if state == "team-select":
            return state, text
        if state == "coach-matchup":
            past_title = True
            log(f"boot +{elapsed:.0f}s coach matchup before the teams were chosen; B back to Team Select")
            tap(pad, "B", secs=0.3, settle=3.0)
            continue
        if state in ("settings-loading", "settings-loaded", "prompt"):
            past_title = True
            settle_modal(run, pad, text, state, f"boot +{elapsed:.0f}s")
            continue
        if state == "title":
            past_title = True
            if starts_at_title == 0:
                run.screenshot("01-title", out_dir)
                notes["title_at"] = round(elapsed, 1)
            if starts_at_title >= 6:
                raise xr.GateError("title-start", f"the title took {starts_at_title} START holds and stayed; saw {text[:120]!r}")
            starts_at_title += 1
            hold(pad, "START", xr.START_HOLD)
            time.sleep(4.0)
            continue
        if elapsed >= BOOT_DEADLINE_SECONDS:
            gate = "boot" if state in ("legal", "logo", "blank") else ("menu" if past_title else "title")
            if gate == "boot":
                stall_samples(run, notes)
            raise xr.GateError(gate, f"no menu after {elapsed:.0f}s; last {state}: {text[:120]!r}")
        if quiet_since is not None and (elapsed >= BOOT_STALL_SECONDS
                                        or time.monotonic() - quiet_since >= BOOT_QUIET_SECONDS):
            stall_samples(run, notes)
            raise xr.GateError("boot", f"only legal/logo/black for {time.monotonic() - quiet_since:.0f}s, "
                                       f"now {state} at +{elapsed:.0f}s; saw {text[:120]!r}")
        if (past_title and other_since is not None and time.monotonic() - other_since >= POST_TITLE_GRACE
                and time.monotonic() - last_press >= POST_TITLE_BACK_EVERY):
            backs += 1
            notes["post_title_backs"] = backs
            log(f"boot +{elapsed:.0f}s unreadable for {time.monotonic() - other_since:.0f}s after the title; B ({backs})")
            if backs == 1:
                run.screenshot("00-post-title-other", out_dir)
            tap(pad, "B", secs=0.3, settle=0.0)
            last_press = time.monotonic()
        elif (not past_title and elapsed >= TAP_START_AFTER and state == "other"
                and time.monotonic() - last_press >= ESCAPE_EVERY):
            rung = ESCAPE_LADDER[escapes % len(ESCAPE_LADDER)]
            escapes += 1
            notes["escapes"] = escapes
            if escapes == 1 or rung != "START":
                log(f"boot +{elapsed:.0f}s no title words; escape press {escapes}: {rung}")
            if rung == "START_HOLD":
                hold(pad, "START", 1.5)
            else:
                tap(pad, rung, secs=0.3, settle=0.0)
            last_press = time.monotonic()
            if escapes == 12:
                run.screenshot("00-attract", out_dir)
        time.sleep(1.0)


def wait_state(run: xr.XemuRun, pad: xr.Gamepad, want: tuple[str, ...], timeout: float,
               label: str) -> tuple[str, str]:
    """Re-read the screen until its state is one of ``want``; boxes on the way
    are settled, a coach matchup is backed out of with B. Returns the last
    (state, text) whether or not it matched."""
    deadline = time.monotonic() + timeout
    state, text = "", ""
    while time.monotonic() < deadline:
        check_alive(run)
        text = screen_text(run)
        state = screen_state(text)
        if state in want:
            return state, text
        if state in ("prompt", "settings-loaded", "settings-loading"):
            settle_modal(run, pad, text, state, label)
            continue
        if state == "coach-matchup":
            log(f"{label}: coach matchup before the teams were chosen; B back to Team Select")
            tap(pad, "B", secs=0.3, settle=3.0)
            continue
        time.sleep(1.5)
    return state, text


def open_quick_game(run: xr.XemuRun, pad: xr.Gamepad) -> str:
    """Main menu -> Team Select. START opens Quick Game (every PASS run); when
    the menu is still on screen afterwards (D1-4, 2026-09-21: the Crib call
    ate the press) A on the highlighted PLAY NOW row and then START again are
    tried, each with its own wait. A press is only made on a readable menu:
    a screen that stays unreadable after a press is backed out of with B
    (never START or A, which could start a game from a misread Team Select)
    and the next press waits for the menu to come back."""
    text = ""
    for attempt, (button, secs) in enumerate((("START", xr.START_HOLD), ("A", 0.3), ("START", xr.START_HOLD))):
        if secs >= 1.0:
            hold(pad, button, secs)
        else:
            tap(pad, button, secs=secs, settle=0.0)
        time.sleep(4.0)
        state, text = wait_state(run, pad, ("team-select",), 25.0, "quick game")
        if state == "team-select":
            return text
        log(f"quick game press {attempt + 1} ({button}): no Team Select; screen is {state}: {text[:100]!r}")
        if state != "menu":
            tap(pad, "B", secs=0.3, settle=0.0)
            time.sleep(3.0)
            state, text = wait_state(run, pad, ("menu", "team-select"), 15.0, "quick game back")
            if state == "team-select":
                return text
            if state != "menu":
                break
    raise xr.GateError("quick-game", f"the main menu never opened Quick Game; saw {text[:120]!r}")


#: The name bar on Team Select, in the 1280x720 capture: "AWAY AT HOME" at y 104..132,
#: the away name in the left slot and the home name in the right slot.
HOME_SLOT = (690, 104, 960, 132)
AWAY_SLOT = (330, 104, 600, 132)
#: The retail disc draws Team Select wider than the widescreen mod discs (its
#: name bar spans x 192..1088, theirs about 262..1018); in its home slot the
#: boxes above read PATRIOTS, RAIDERS, REDSKINS and SEAHAWKS as nothing at all
#: (test-R2, 2026-09-22). A slot the first box cannot name is read again in a
#: wider box, which reads every retail miss frame and all 20 mod frames tried.
SLOT_ALTERNATES = {HOME_SLOT: ((690, 102, 1000, 134),), AWAY_SLOT: ((280, 102, 610, 134),)}


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


#: A name slot that OCRs as nothing at all is mid-change, not a name the OCR
#: cannot read: on the retail disc (R-ne-1, 2026-09-22) PATRIOTS, RAIDERS,
#: REDSKINS and SEAHAWKS read blank for the second or two the slot used to be
#: read, while the names beside them read at once. A blank slot is read again
#: for up to this long; the mod discs have not needed it.
SLOT_BLANK_SECONDS = 8.0
#: The retail list has more entries after VIKINGS (ALUMNI teams and others), so
#: a full lap is longer than the 32 nicknames.
SLOT_MAX_PULSES = 50
#: Per-run counters for the ledger (one route per process).
SLOT_NOTES = {"blank_reads": 0, "miss_frames": 0, "alt_reads": 0}


def slot_team(raw: str) -> str:
    """The nickname a slot OCR line names: an exact nickname first (the longest,
    if two), then the first one-miss match. The bracket glyph before the name
    OCRs as "JE", "JC", "SE" and the like, and a fuzzy pass in list order took
    "JE SESE PATRIOTS" for JETS."""
    exact = [name for name in TEAMS if name in raw]
    if exact:
        return max(exact, key=len)
    return next((name for name in TEAMS if slot_has(raw, name)), "")


def read_slot(run: xr.XemuRun, box, tries: int = 4) -> tuple[str, str]:
    """(raw OCR line, the team it names or '') from up to ``tries`` frames.

    One read per pulse missed REDSKINS on two full laps of the list (2026-09-20):
    the slot is read again a few times before it counts as unknown, and a
    blank read keeps being retried for SLOT_BLANK_SECONDS.
    """
    raw = ""
    attempts = 0
    blank_until: float | None = None
    while True:
        raw = slot_name(run, box)
        team = slot_team(raw)
        if team:
            return raw, team
        for alternate in SLOT_ALTERNATES.get(tuple(box), ()):
            wide = slot_name(run, alternate)
            team = slot_team(wide)
            if team:
                SLOT_NOTES["alt_reads"] += 1
                return wide, team
        attempts += 1
        if not raw.strip():
            SLOT_NOTES["blank_reads"] += 1
            if blank_until is None:
                blank_until = time.monotonic() + SLOT_BLANK_SECONDS
            if time.monotonic() < blank_until:
                time.sleep(0.35)
                continue
        if attempts >= tries:
            return raw, ""
        time.sleep(0.35)


def keep_slot_miss(run: xr.XemuRun, side: str) -> None:
    """The frame of the first few unknown slot reads, for the route record."""
    if SLOT_NOTES["miss_frames"] < 6:
        SLOT_NOTES["miss_frames"] += 1
        try:
            run.screenshot(f"slot-miss-{SLOT_NOTES['miss_frames']}-{side}", run.run_dir / "screens")
        except Exception:  # noqa: BLE001
            pass


#: Route variant for the disc under test; main() sets it from --route and the
#: ledger records it. "retail" is the untouched retail disc (R, 2026-09-22).
ROUTE = {"name": "default"}
#: The retail list has entries after VIKINGS that are not NFL teams (ALUMNI
#: teams and others), and test-R3 hung at Team Select after 27 quick pulses
#: carried the away slot through them. The retail route never wraps the list:
#: RT toward a later nickname, LT toward an earlier one, one pulse per
#: RETAIL_PULSE_SETTLE seconds.
RETAIL_PULSE_SETTLE = 1.2
#: This many pulses in a row that leave the whole frame unchanged mean the game
#: is not taking input (test-R3 held one frame from 15:12:49 to 15:15:01 through
#: 37 pulses and two RIGHTs, xemu alive).
SLOT_FREEZE_PULSES = 5


def safe_digest(run: xr.XemuRun) -> str:
    try:
        return frame_digest(run)
    except Exception:  # noqa: BLE001
        return ""


#: A held picture is not always the game. QEMU's gdb server stops the VM when any TCP client opens the
#: stub's port and starts it only on a gdb detach, and the xemu UI can pause it too; the guest then shows
#: its last frame and reads no pad input while the UI keeps drawing. Lab run x1-v6-1 (2026-09-23): one
#: such hold at Team Select lasted 97 s with the guest vCPU, the APU and QEMU's timers all idle, and one
#: gdb halt/resume released it in 1 s; retail test-R3 held 132 s with no gdb at all. Before a hold is
#: reported, the run state is asked over QMP; a VM that is not running is resumed (at most this many
#: times per run) and noted in the ledger as ``vm_paused``, never counted as a game result.
VM_RESUMES_MAX = 3


def resume_if_paused(run: xr.XemuRun, where: str) -> bool:
    """True when QMP says the VM is not running and a QMP cont was accepted."""
    status = xr.vm_status(run)
    if not status or status.get("running", True):
        return False
    pauses = SLOT_NOTES.setdefault("vm_paused", [])
    if len(pauses) >= VM_RESUMES_MAX:
        return False
    resumed = xr.vm_resume(run)
    pauses.append(dict(where=where, status=status.get("status"), resumed=resumed, at=time.strftime("%H:%M:%S")))
    log(f"{where}: the VM was not running (QMP status {status.get('status')!r}), not a game hold; "
        f"QMP cont {'accepted' if resumed else 'FAILED'}")
    return resumed


def cycle_slot_to(run: xr.XemuRun, pad: xr.Gamepad, box, team: str, side: str) -> str:
    """Cycle one Team Select slot until it names ``team``; the OCR line.

    The current name gives the number of pulses (the list order is known), the
    slot is read again at the end, and a miss falls back to single pulses with a
    read after each one, so one bad read never costs a lap of the list. The
    default route pulses RT and may wrap; the retail route (ROUTE) never wraps
    and pulses slower, backing off to RT if LT turns out to do nothing. On any
    route SLOT_FREEZE_PULSES unchanged frames in a row end the route as
    ``team-select-freeze``, with a kept frame and two register samples.
    """
    require = team in TEAMS
    if not require:
        raise xr.GateError("team-select", f"{team} is not a Team Select nickname")
    retail = ROUTE["name"] == "retail"
    settle = RETAIL_PULSE_SETTLE if retail else 0.6
    lt_works = True

    def aim(current: str) -> str:
        if not retail or not current or current == team:
            return "RT"
        return "RT" if TEAMS.index(team) > TEAMS.index(current) or not lt_works else "LT"

    raw, current = read_slot(run, box)
    log(f"{side} slot reads {raw!r} -> {current or 'unknown'}")
    button = aim(current)
    if current:
        start, goal = TEAMS.index(current), TEAMS.index(team)
        steps = abs(goal - start) if retail else (goal - start) % len(TEAMS)
        for _ in range(steps):
            tap(pad, button, secs=xr.TRIGGER_PULSE, settle=settle)
        raw, current = read_slot(run, box)
        log(f"{side} slot after {steps} computed {button} pulses reads {raw!r} -> {current or 'unknown'}")
        if not current:
            keep_slot_miss(run, side)
        if current:
            button = aim(current)
    pulses = 0
    still = 0
    last = safe_digest(run)
    while current != team and pulses < SLOT_MAX_PULSES:
        tap(pad, button, secs=xr.TRIGGER_PULSE, settle=settle if retail else 0.7)
        pulses += 1
        raw, current = read_slot(run, box, tries=3)
        log(f"{side} slot after single {button} pulse {pulses}: {raw!r} -> {current or 'unknown'}")
        if not current:
            keep_slot_miss(run, side)
        digest = safe_digest(run)
        still = still + 1 if digest and digest == last else 0
        last = digest
        if still >= SLOT_FREEZE_PULSES and resume_if_paused(run, f"{side} slot"):
            still, last = 0, safe_digest(run)
            continue
        if still >= SLOT_FREEZE_PULSES:
            if button == "LT":
                log(f"{side} slot: {still} LT pulses changed nothing; RT from here on")
                lt_works, button, still = False, "RT", 0
                continue
            SLOT_NOTES["freeze"] = dict(side=side, pulses=pulses, button=button, text=raw[:80])
            try:
                run.screenshot(f"zz-team-select-held-{side}", run.run_dir / "screens")
            except Exception:  # noqa: BLE001
                pass
            stall_samples(run, SLOT_NOTES)
            raise xr.GateError("team-select-freeze",
                               f"{still} {button} pulses left the {side} slot frame unchanged; last {raw!r}")
        if current and current != team:
            button = aim(current)
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


def quick_game_home(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path, *, home_team: str, away_team: str = "",
                    explore: bool = False, notes: dict | None = None):
    """Main Menu -> Quick Game -> Team Select with a chosen HOME team -> coach matchup -> game.

    The right trigger cycles the right slot, which is the home team; the
    practice route's "away" naming had that backwards. andrethealchemist
    (2026-09-20): the freeze depends on which team is at home, so the probe has
    to choose it. Returns the team-select OCR line for the ledger.
    """
    notes = notes if notes is not None else {}
    state, text = reach_menu(run, pad, out_dir, notes)
    notes["menu_reached"] = state
    if state != "team-select":
        run.screenshot("02-main-menu", out_dir)
        text = open_quick_game(run, pad)
    run.screenshot("03-team-select", out_dir)
    if explore:
        return explore_team_select(run, pad, out_dir)
    slot = cycle_slot_to(run, pad, HOME_SLOT, home_team, "home")
    text = slot
    if away_team:
        # Read from the frames (explore rounds one and two, 2026-09-20): the
        # controller starts assigned to the HOME side, where the triggers cycle
        # the home slot; one D-pad LEFT makes it neutral (highlighted icon, the
        # triggers do nothing); a second LEFT puts it on the AWAY side, where
        # RT cycles the away slot (Browns -> Buccaneers -> Cardinals). Two
        # RIGHTs put it back on the home side so the rest of the route matches
        # every earlier run. The left stick moves it the same way.
        tap(pad, "LEFT", settle=1.0)
        tap(pad, "LEFT", settle=1.0)
        try:
            left = cycle_slot_to(run, pad, AWAY_SLOT, away_team, "away")
        finally:
            tap(pad, "RIGHT", settle=1.0)
            tap(pad, "RIGHT", settle=1.0)
        home_after, home_read = read_slot(run, HOME_SLOT)
        if home_read != home_team:
            raise xr.GateError("team-select", f"home slot changed while choosing the away team: {home_after!r}")
        text = f"{left} AT {home_after}"
    else:
        # The away slot is whatever the game picked; the ledger keeps its name.
        away_raw, away_read = read_slot(run, AWAY_SLOT, tries=2)
        notes["away_slot"] = away_read or away_raw
        log(f"away slot left as the game picked it: {away_raw!r} -> {away_read or 'unknown'}")
        text = f"{away_raw} AT {slot}"
    run.screenshot("04-team-select-home", out_dir)
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    run.screenshot("05-coach-matchup", out_dir)
    start_game(run, pad, notes)
    log("game starting")
    return text[:200]


#: R-ne-1-r2 (2026-09-22): the A hold at the coach matchup did not take on the
#: retail disc and the watch sat on COACH MATCHUP / START GAME until its eight
#: minutes ran out, which would have counted as a TIMEOUT in the intro. Each
#: press now has to clear the screen within COACH_WAIT_SECONDS.
COACH_PRESSES = (("A", xr.MODAL_A_HOLD), ("A", 0.3), ("START", xr.START_HOLD))
COACH_WAIT_SECONDS = 20.0


def start_game(run: xr.XemuRun, pad: xr.Gamepad, notes: dict) -> None:
    """Coach matchup -> game: the A hold of every earlier run, then A and
    START, each checked; a coach matchup that outlasts all three is the route
    error ``coach-matchup-stuck``, never an intro outcome."""
    for index, (button, secs) in enumerate(COACH_PRESSES):
        if secs >= 1.0:
            hold(pad, button, secs)
        else:
            tap(pad, button, secs=secs, settle=0.0)
        deadline = time.monotonic() + COACH_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(2.0)
            if screen_state(screen_text(run)) != "coach-matchup":
                if index:
                    notes["coach_presses"] = index + 1
                return
        log(f"coach matchup still up {COACH_WAIT_SECONDS:.0f}s after press {index + 1} ({button})")
    raise xr.GateError("coach-matchup", "the coach matchup never started the game")


# --------------------------------------------------------------------------
# The watch
# --------------------------------------------------------------------------

def xemu_exit(run: xr.XemuRun, wait: float = 0.0) -> dict | None:
    """None while xemu lives; otherwise its exit code and the assert line, if
    any, from logs/xemu.stderr.log. ``wait`` gives a dying process a moment
    to be reaped after its window has already gone."""
    if run.xemu is None:
        return None
    code = run.xemu.poll()
    if code is None and wait > 0:
        try:
            code = run.xemu.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            return None
    if code is None:
        return None
    tail = ""
    try:
        tail = (run.logs / "xemu.stderr.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    lines = [line for line in tail.splitlines() if line.strip()]
    assertion = next((line for line in lines if "Assertion" in line or "assert" in line.casefold()), "")
    site = re.search(r"([\w./-]+\.c:\d+): (\w+):", assertion)
    return dict(exit_code=code, assertion=assertion[:300], pfifo="pfifo" in assertion.casefold(),
                site=f"{site.group(1).rsplit('/', 1)[-1]} {site.group(2)}" if site else "",
                stderr_tail=lines[-3:])


def keep_frame(image, out_dir: Path, name: str) -> None:
    """JPEG frames for the watch: a 1280x720 PNG is 400-600 KB, forty runs of
    ten frames each would be a quarter gigabyte on the main drive."""
    try:
        image.convert("RGB").save(out_dir / f"{name}.jpg", quality=85)
    except Exception as exc:  # noqa: BLE001
        log(f"frame {name} not saved: {type(exc).__name__}: {exc}")


def watch(run: xr.XemuRun, out_dir: Path, port: int, minutes: float, *,
          frame_seconds: float = 10.0, cpu_seconds: float = 30.0) -> dict:
    """Classify from the picture; gdb registers are a best-effort corroboration only.

    The screen is the trustworthy signal here: reaching the coin toss / kickoff
    is PASS, and a full-motion intro that then holds one identical frame past
    ``FREEZE_SECONDS`` is the freeze. The gdb sample is attempted and its EIP
    recorded when it works (the 2026-09-15 bugcheck sat at 0x800151EF), but the
    attach is unreliable under this xemu build, so a freeze is never gated on
    it -- a run with no CPU data still returns FROZEN on the frozen picture.
    xemu dying is read from the process and its stderr, not from the lost
    window: the nv2a "Reserved pb command" assert is PFIFO_ABORT.
    One capture per loop feeds the OCR, the digest and the kept frame.
    """
    started = time.monotonic()
    wall_started = time.time()
    deadline = started + minutes * 60
    samples: list[dict] = []
    frames: list[tuple[float, str]] = []
    seen_motion_at: float | None = None
    frozen_since: float | None = None
    last_shot = -frame_seconds
    last_cpu = 0.0
    seen_text = ""
    last_image = None
    coach_reads = 0

    def died(elapsed: float, info: dict) -> dict:
        if last_image is not None:
            keep_frame(last_image, out_dir, "zz-last-frame")
        outcome = "PFIFO_ABORT" if info.get("pfifo") else "XEMU_EXIT"
        # The assert is the stderr log's last write, so its mtime dates the
        # abort to the second; ``elapsed`` is only when this loop noticed it.
        try:
            info["stderr_at"] = round((run.logs / "xemu.stderr.log").stat().st_mtime - wall_started, 1)
        except OSError:
            pass
        log(f"+{elapsed:.0f}s xemu exited ({info.get('exit_code')}): {info.get('assertion') or 'no assert line'}")
        return dict(outcome=outcome, elapsed=round(elapsed, 1), text=seen_text[:300], cpu=samples,
                    xemu_exit=info, saw_motion=seen_motion_at is not None,
                    last_frame_at=round(frames[-1][0], 1) if frames else None)

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        info = xemu_exit(run)
        if info is not None:
            return died(elapsed, info)
        try:
            image = run._frame()
        except xr.GateError as exc:
            info = xemu_exit(run, wait=5.0)
            if info is not None:
                return died(elapsed, info)
            raise exc
        last_image = image
        try:
            text = xr.normalized(xr._ocr_image(image, 11))
        except Exception:  # noqa: BLE001
            text = ""
        if text and text != seen_text:
            seen_text = text
            log(f"+{elapsed:.0f}s screen: {text[:120]!r}")
        if reached(text):
            run.screenshot(f"reached-{elapsed:.0f}s", out_dir)
            return dict(outcome="PASS", elapsed=round(elapsed, 1), text=text[:300], cpu=samples)
        coach_reads = coach_reads + 1 if screen_state(text) == "coach-matchup" else 0
        if coach_reads >= 3:
            # The game never started (start_game's check can only miss a screen
            # that comes back); this is a route error, not an intro outcome.
            raise xr.GateError("coach-matchup", f"the watch still reads the coach matchup at +{elapsed:.0f}s")
        digest = hashlib.sha256(image.tobytes()).hexdigest()[:16]
        if frames and digest != frames[-1][1]:
            if elapsed >= MOTION_GRACE_SECONDS and seen_motion_at is None:
                seen_motion_at = elapsed
            frozen_since = None
        elif frames and digest == frames[-1][1] and frozen_since is None:
            frozen_since = elapsed
        frames.append((elapsed, digest))
        if elapsed - last_shot >= frame_seconds:
            keep_frame(image, out_dir, f"watch-{elapsed:03.0f}s")
            last_shot = elapsed
        if elapsed - last_cpu >= cpu_seconds:
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
                and elapsed - frozen_since >= FREEZE_SECONDS
                and resume_if_paused(run, f"watch +{elapsed:.0f}s")):
            frozen_since = None
            time.sleep(10.0)
            continue
        if (seen_motion_at is not None and frozen_since is not None
                and elapsed - frozen_since >= FREEZE_SECONDS):
            run.screenshot(f"frozen-{elapsed:.0f}s", out_dir)
            run.screenshot("zz-freeze", out_dir)
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
    info = xemu_exit(run)
    if info is not None:
        return died(minutes * 60, info)
    run.screenshot("timeout", out_dir)
    return dict(outcome="TIMEOUT", elapsed=round(minutes * 60, 1),
                saw_motion=seen_motion_at is not None, text=seen_text[:300], cpu=samples)


def explore_team_select(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path) -> list[dict]:
    """Diagnostic: from Team Select, press each control once and record both slots.

    Which slot the triggers act on, and what the D-pad does, is not documented
    anywhere the probe can read; forty pulses that changed nothing (2026-09-20)
    cost more than one look at the frames after each press.
    """
    # Round one (22:40): in the middle LT/RT cycle the HOME slot (prev/next);
    # one D-pad LEFT highlights the icon with a yellow arrow and the hint
    # "Press L R for Random Team", and there the triggers change nothing;
    # RIGHT returns to the middle; UP/DOWN do nothing readable. Round two
    # tries a second LEFT, A after LEFT, the left stick, and the bumpers.
    steps = [("start", None), ("LEFT", ("LEFT", False)), ("LEFT-LEFT", ("LEFT", False)),
             ("LEFT-LEFT-RT", ("RT", True)), ("LEFT-LEFT-RT-RT", ("RT", True)),
             ("RIGHT", ("RIGHT", False)), ("RIGHT-RIGHT", ("RIGHT", False)),
             ("LS_LEFT", ("LS_LEFT", False)), ("LS_LEFT-RT", ("RT", True)), ("LS_LEFT-RT-RT", ("RT", True)),
             ("LS_RIGHT", ("LS_RIGHT", False)), ("LS_RIGHT-RT", ("RT", True)),
             ("LEFT-again", ("LEFT", False)), ("LEFT-A", ("A", False)), ("LEFT-A-RT", ("RT", True)),
             ("LEFT-A-RT-RT", ("RT", True)), ("B", ("B", False)), ("B-RT", ("RT", True)),
             ("RIGHT-home", ("RIGHT", False)), ("LEFT-mid", ("LEFT", False)), ("RB", ("RB", False)),
             ("LB", ("LB", False)), ("RIGHT-end", ("RIGHT", False))]
    rows = []
    for index, (name, press) in enumerate(steps):
        if press is not None:
            button, trigger = press
            if trigger:
                tap(pad, button, secs=xr.TRIGGER_PULSE, settle=1.2)
            else:
                tap(pad, button, settle=1.2)
        run.screenshot(f"e{index:02d}-{name}", out_dir)
        away, away_team = read_slot(run, AWAY_SLOT, tries=2)
        home, home_team = read_slot(run, HOME_SLOT, tries=2)
        row = dict(step=name, away=away, away_team=away_team, home=home, home_team=home_team)
        log(f"explore {name}: away {away!r} -> {away_team or '?'} | home {home!r} -> {home_team or '?'}")
        rows.append(row)
    return rows


#: Gate name -> the ledger's route_error reason.
ROUTE_REASONS = {
    "boot": "boot-stall", "title": "attract-demo", "title-start": "title-stuck",
    "settings-load": "settings-load-stuck", "settings-box": "settings-box-stuck",
    "menu": "menu-unreadable", "quick-game": "main-menu-stuck", "team-select": "team-select-ocr",
    "xemu": "xemu-exit", "boot-freeze": "boot-freeze", "team-select-freeze": "team-select-freeze",
    "coach-matchup": "coach-matchup-stuck",
}


def route_error_reason(exc: BaseException, run: xr.XemuRun, ledger: dict) -> str:
    """The short reason for a run that never reached the intro, with the xemu
    exit (and its assert) recorded when the process is gone."""
    info = xemu_exit(run, wait=3.0)
    if info is not None:
        ledger["xemu_exit"] = info
        return "xemu-pfifo-abort" if info.get("pfifo") else "xemu-exit"
    gate = getattr(exc, "gate", "")
    if gate == "title" and ledger.get("boot_states", {}).get("other", 0) == 0:
        return "boot-stall"
    return ROUTE_REASONS.get(gate, gate or type(exc).__name__)


def load_average() -> list[float]:
    try:
        return [round(v, 2) for v in os.getloadavg()]
    except (OSError, AttributeError):
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xiso", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--away-team", default="FALCONS")
    ap.add_argument("--home-team", default="", help="cycle Team Select until this team is at home")
    ap.add_argument("--away-team-slot", default="", help="with --home-team: also cycle the left slot to this away team")
    ap.add_argument("--minutes", type=float, default=8.0)
    ap.add_argument("--frame-seconds", type=float, default=10.0, help="keep a JPEG frame of the watch this often")
    ap.add_argument("--cpu-seconds", type=float, default=30.0, help="batch-gdb register sample this often")
    ap.add_argument("--label", default="")
    ap.add_argument("--route", choices=("default", "retail"), default="default",
                    help="route variant: retail = the untouched retail disc (no list wrap, slower pulses)")
    ap.add_argument("--explore-team-select", action="store_true",
                    help="diagnostic: press each Team Select control once, record both slots, stop")
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
    qmp_port = 4455
    while not xr.port_free(qmp_port) or qmp_port == port:
        qmp_port += 1
    run.qmp_port = qmp_port
    pad = None
    watch_started: float | None = None
    ROUTE["name"] = args.route
    ledger = dict(label=args.label, xiso=str(xiso), outcome="ERROR", started=time.strftime("%Y-%m-%d %H:%M:%S"),
                  load_start=load_average(), route=args.route)
    try:
        run.start_display()
        pad = xr.Gamepad()
        run.start_xemu(xiso)
        log(f"xemu up on Xvfb :{display}, gdb tcp:127.0.0.1:{port}, qmp 127.0.0.1:{run.qmp_port}")
        route_started = time.monotonic()
        if args.explore_team_select:
            ledger["explore"] = quick_game_home(run, pad, out_dir, home_team="", away_team="", explore=True,
                                               notes=ledger)
            ledger["outcome"] = "EXPLORED"
            ledger["elapsed"] = round(time.monotonic() - route_started, 1)
            return 0
        if args.home_team:
            ledger["home_team"] = args.home_team.upper()
            if args.away_team_slot:
                ledger["away_team"] = args.away_team_slot.upper()
            ledger["team_select"] = quick_game_home(run, pad, out_dir, home_team=args.home_team.upper(),
                                                    away_team=args.away_team_slot.upper(), notes=ledger)
        else:
            quick_game_route(run, pad, out_dir, away_team=args.away_team.upper())
        ledger["route_seconds"] = round(time.monotonic() - route_started, 1)
        watch_started = time.monotonic()
        ledger.update(watch(run, out_dir, port, args.minutes, frame_seconds=args.frame_seconds,
                            cpu_seconds=args.cpu_seconds))
    except Exception as exc:  # noqa: BLE001
        ledger["error"] = f"{type(exc).__name__}: {exc}"
        info = xemu_exit(run, wait=3.0) if watch_started is not None else None
        if info is not None:
            # xemu died inside the watch on a path the watch does not catch
            # (a screenshot at that instant): the run reached the intro, so
            # this is an outcome, not a route error.
            ledger["xemu_exit"] = info
            ledger["outcome"] = "PFIFO_ABORT" if info.get("pfifo") else "XEMU_EXIT"
            ledger["elapsed"] = round(time.monotonic() - watch_started, 1)
            log(f"xemu exited during the watch ({info.get('exit_code')}): {info.get('assertion') or 'no assert line'}")
        else:
            ledger["route_error"] = route_error_reason(exc, run, ledger)
            log(f"FAILED ({ledger['route_error']}): {ledger['error']}")
        try:
            run.screenshot("zz-failure", out_dir)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if pad is not None:
            pad.quit()
        ledger["shutdown"] = run.shutdown()
        ledger["load_end"] = load_average()
        if SLOT_NOTES["blank_reads"] or SLOT_NOTES["miss_frames"] or SLOT_NOTES["alt_reads"]:
            ledger["slot_blank_reads"] = SLOT_NOTES["blank_reads"]
            ledger["slot_miss_frames"] = SLOT_NOTES["miss_frames"]
            ledger["slot_alt_reads"] = SLOT_NOTES["alt_reads"]
        if SLOT_NOTES.get("vm_paused"):
            ledger["vm_paused"] = SLOT_NOTES["vm_paused"]
        if "freeze" in SLOT_NOTES:
            ledger["slot_freeze"] = SLOT_NOTES["freeze"]
            ledger.setdefault("stall_cpu", SLOT_NOTES.get("stall_cpu"))
        (run_dir / "berman-probe.json").write_text(json.dumps(ledger, indent=1) + "\n",
                                                   encoding="utf-8", newline="\n")
        print(f"BERMAN_PROBE label={args.label or '-'} away={ledger.get('away_team', ledger.get('away_slot', '?'))} "
              f"home={ledger.get('home_team', '-')} outcome={ledger['outcome']} "
              f"elapsed={ledger.get('elapsed', 0):.0f}s route_error={ledger.get('route_error', '-')}", flush=True)
    return 0 if ledger["outcome"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
