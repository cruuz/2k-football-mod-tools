#!/usr/bin/env python3
"""Drive xemu on a nested display with a baked play-author XISO and take orders from a command file.

Boots the isolated profile (fresh qcow2 overlay over the live HDD, pinned
firmware copied from the flatpak data dir), walks the proven press-start ->
Quick Game -> ATL route from ``tools/xemu_playbook_create_runtime.py`` (imported,
never copied), then loops on ``<run_dir>/cmds.txt``: each new line is one order:

  shot NAME            save a screenshot screens/NAME.png (+ full OCR text)
  ocr                  print OCR of the current frame to the log
  pad <GAMEPAD CMD>    forward a raw command (TAP A 0.15 / HOLD START / RELEASE START ...)
  tap BTN [SECS]       TAP shorthand
  wait SECS
  quit                 shut everything down
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import xemu_playbook_create_runtime as xr  # noqa: E402

xr.FIRMWARE_SOURCE = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu"
log = xr.log


def boot_route(run: xr.XemuRun, pad: xr.Gamepad, out_dir: Path) -> None:
    started = time.monotonic()
    deadline = started + 420.0
    while time.monotonic() < deadline:
        try:
            text = xr.normalized(run.ocr_press())
        except Exception:  # noqa: BLE001
            text = ""
        if "PRESS" in text and "START" in text:
            break
        time.sleep(2.0)
    else:
        raise xr.GateError("press-start", "PRESS START not detected")
    run.screenshot("01-press-start", out_dir)
    log(f"press start at +{time.monotonic() - started:.0f}s")
    pad.send("HOLD START", expect="HOLD START"); time.sleep(xr.START_HOLD); pad.send("RELEASE START", expect="RELEASE START")
    xr.wait_gate_text(run, ("SETTINGS",), timeout=60.0)
    run.screenshot("02-settings", out_dir)
    pad.send("HOLD A", expect="HOLD A"); time.sleep(xr.MODAL_A_HOLD); pad.send("RELEASE A", expect="RELEASE A")
    time.sleep(4.0)
    run.screenshot("03-main-menu", out_dir)
    pad.send("HOLD START", expect="HOLD START"); time.sleep(xr.START_HOLD); pad.send("RELEASE START", expect="RELEASE START")
    time.sleep(4.0)
    run.screenshot("04-team-select", out_dir)
    matchup = xr.normalized(run.ocr_full())
    pulses = 0
    if not xr.atl_present(matchup):
        for _ in range(64):
            pad.send(f"TAP RT {xr.TRIGGER_PULSE}", expect="TAPPED"); pulses += 1
            time.sleep(0.6)
            matchup = xr.normalized(run.ocr_full())
            if xr.atl_present(matchup):
                break
    log(f"team select after {pulses} RT pulses: {matchup[:120]!r}")
    run.screenshot("05-team-select-atl", out_dir)
    pad.send("HOLD START", expect="HOLD START"); time.sleep(xr.START_HOLD); pad.send("RELEASE START", expect="RELEASE START")
    time.sleep(4.0)
    run.screenshot("06-coach-matchup", out_dir)
    pad.send("HOLD A", expect="HOLD A"); time.sleep(xr.MODAL_A_HOLD); pad.send("RELEASE A", expect="RELEASE A")
    log("game starting")


def command_loop(run: xr.XemuRun, pad: xr.Gamepad, run_dir: Path, out_dir: Path) -> None:
    cmd_file = run_dir / "cmds.txt"
    cmd_file.touch()
    seen = 0
    log(f"command loop on {cmd_file}")
    while True:
        lines = cmd_file.read_text().splitlines()
        for line in lines[seen:]:
            seen += 1
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            log(f"CMD {line}")
            try:
                parts = line.split()
                if parts[0] == "quit":
                    return
                if parts[0] == "shot":
                    name = parts[1] if len(parts) > 1 else f"shot-{int(time.time())}"
                    shot = run.screenshot(name, out_dir)
                    try:
                        (out_dir / f"{name}.txt").write_text(run.ocr_full())
                    except Exception as exc:  # noqa: BLE001
                        log(f"ocr failed: {exc}")
                    log(f"saved {shot['path']}")
                elif parts[0] == "ocr":
                    log("OCR: " + xr.normalized(run.ocr_full())[:400])
                elif parts[0] == "pad":
                    cmd = " ".join(parts[1:])
                    pad.send(cmd, expect=None)
                elif parts[0] == "tap":
                    secs = parts[2] if len(parts) > 2 else "0.15"
                    pad.send(f"TAP {parts[1]} {secs}", expect="TAPPED", timeout=10.0)
                elif parts[0] == "hold":
                    pad.send(f"HOLD {parts[1]}", expect="HOLD")
                elif parts[0] == "release":
                    pad.send(f"RELEASE {parts[1]}", expect="RELEASE")
                elif parts[0] == "wait":
                    time.sleep(float(parts[1]))
                else:
                    log(f"unknown command {line!r}")
            except Exception as exc:  # noqa: BLE001
                log(f"command failed: {exc}")
        time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bake-dir", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--skip-route", action="store_true")
    ap.add_argument("--user-pad", help="SDL GUID of the human's controller; it takes port 1 and the virtual pad moves to port 2")
    args = ap.parse_args()
    bake = Path(args.bake_dir)
    plan = json.loads((bake / "plan.json").read_text())
    xiso = Path(plan["xiso_path"])
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "screens"
    out_dir.mkdir(exist_ok=True)
    xr.abort_if_xemu_running()
    isolation = xr.setup_isolation(run_dir, xiso)
    if args.user_pad:
        toml = Path(isolation["config_path"])
        text = toml.read_text()
        text = text.replace("gamepad_mappings = [\n    { gamepad_id = '030081b85e0400008e02000014010000'}\n    ]",
                            "gamepad_mappings = [\n    { gamepad_id = '030081b85e0400008e02000014010000'},\n    { gamepad_id = '%s'}\n    ]" % args.user_pad)
        text = text.replace("port1 = '030081b85e0400008e02000014010000'",
                            "port1 = '%s'\nport2_driver = 'usb-xbox-gamepad'\nport2 = '030081b85e0400008e02000014010000'" % args.user_pad)
        toml.write_text(text)
        log("user pad on port 1; virtual pad on port 2")
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
            boot_route(run, pad, out_dir)
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
