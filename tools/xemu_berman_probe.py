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
from xemu_practice_runtime import quick_game_route, screen_text  # noqa: E402

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


def sample_cpu(port: int, log_path: Path) -> dict:
    """Attach, read eip/eax/ecx, detach with the guest running again."""

    session = xr.GdbSession(port, log_path)
    try:
        mark = session.send("info registers eip eax ecx", "(gdb)")
        lines = session.tail(mark)
    finally:
        session.close(resume=True)
    values = {}
    for line in lines:
        found = re.match(r"\s*(eip|eax|ecx)\s+0x([0-9a-fA-F]+)", line)
        if found:
            values[found.group(1)] = int(found.group(2), 16)
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
            in_kernel = any(KERNEL[0] <= s.get("eip", 0) < KERNEL[1] for s in samples[-3:])
            return dict(outcome="BUGCHECK" if in_kernel else "FROZEN",
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
        print(f"BERMAN_PROBE label={args.label or '-'} outcome={ledger['outcome']} "
              f"elapsed={ledger.get('elapsed', 0):.0f}s", flush=True)
    return 0 if ledger["outcome"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
