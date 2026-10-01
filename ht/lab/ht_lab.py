#!/usr/bin/env python3
"""DESIGN: main-only historic smoke driver, adapted from h1_lab.py.

Quick Game mixed (49ers 81 versus current Giants) or pair (49ers 81 versus
Giants 90), coin-toss watch, then an operator-controlled player-card capture.
Never run by the ht agent. Pad commands are appended to card-commands.txt.
The coin-toss PASS is separate from the pending human names/equipment review.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

STACK = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(STACK / "tools"), str(STACK)]
import xemu_berman_probe as probe  # noqa: E402
from xemu_practice_runtime import hold, tap  # noqa: E402

xr = probe.xr
log = probe.log
HOME, AWAY = 0xACF63C, 0xACF640
MATCH = {"home": 0xB30864, "away": 0xB30A58}
PULSE_SETTLE = 1.6          # a historic step loads a file inside the handler; give each pulse its own frames
MAX_PULSES = 132  # covers the 52 residents plus 75 descriptors, including wraparound


def gdb_read(port: int, lines: list[str], log_path: Path) -> str:
    command = ["gdb", "-q", "-nx", "-batch", "-ex", "set pagination off", "-ex", "set confirm off",
               "-ex", f"target remote 127.0.0.1:{port}"]
    for line in lines:
        command += ["-ex", line]
    command += ["-ex", "detach"]
    done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    with open(log_path, "a", encoding="utf-8") as stream:
        stream.write(done.stdout + done.stderr + "\n----\n")
    return done.stdout


def team_lines(expr: str, tag: str) -> list[str]:
    return [f"echo {tag}-ptr\\n", f"x/1wx {expr}",
            f"echo {tag}-name\\n", f"x/16hx *(unsigned int*)({expr}+0x104)",
            f"echo {tag}-cat\\n", f"x/1wx {expr}+0x128",
            f"echo {tag}-count\\n", f"x/1bx {expr}+0x11c"]


def parse(output: str) -> dict:
    """Pull the tagged values out of the gdb x/ dumps."""
    result, tag, words = {}, None, []

    def flush():
        if tag is None:
            return
        side, field = tag.rsplit("-", 1)
        entry = result.setdefault(side, {})
        if field == "name":
            chars = []
            for value in words:
                if value == 0:
                    break
                chars.append(chr(value))
            entry["name"] = "".join(chars)
        elif words:
            entry[field] = words[0]

    for line in output.splitlines():
        found = re.fullmatch(r"(\w+-(?:ptr|name|cat|count))", line.strip())
        if found:
            flush()
            tag, words = found.group(1), []
            continue
        if ":" in line and tag is not None:
            words += [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)", line.split(":", 1)[1])]
    flush()
    return result


def read_selection(port: int, log_path: Path) -> dict:
    lines = ["set $h = *(unsigned int*)0xacf63c", "set $a = *(unsigned int*)0xacf640"]
    lines += team_lines("$h", "home") + team_lines("$a", "away")
    return parse(gdb_read(port, lines, log_path))


def read_match(port: int, log_path: Path) -> dict:
    lines = []
    for side, at in MATCH.items():
        lines += [f"echo {side}-name\\n", f"x/16hx *(unsigned int*)({at:#x}+0x104)",
                  f"echo {side}-cat\\n", f"x/1wx {at:#x}+0x128",
                  f"echo {side}-count\\n", f"x/1bx {at:#x}+0x11c"]
    return parse(gdb_read(port, lines, log_path))


def step_to(run, pad, port: int, side: str, target: str, button: str, notes: dict, out_dir: Path,
            shots: tuple[str, ...] = ()) -> list[dict]:
    """Pulse ``button`` until ``side`` shows ``target`` (a nickname read from RAM); every read is kept."""
    trail = []
    for pulse in range(MAX_PULSES + 1):
        now = read_selection(port, run.logs / "h1-gdb.log")
        mine = now.get(side, {})
        trail.append({"pulse": pulse, "name": mine.get("name"), "category": mine.get("cat"),
                      "players": mine.get("count"), "at": time.strftime("%H:%M:%S")})
        log(f"{side} pulse {pulse}: {mine.get('name')!r} category {mine.get('cat')} players {mine.get('count')}")
        name = mine.get("name") or ""
        if name in shots:
            run.screenshot(f"ts-{side}-{re.sub(r'[^A-Za-z0-9]+', '', name)}", out_dir)
        if name.casefold() == target.casefold():
            return trail
        if pulse == MAX_PULSES:
            break
        tap(pad, button, secs=xr.TRIGGER_PULSE, settle=PULSE_SETTLE)
    notes["step_trail_" + side] = trail
    raise xr.GateError("team-select", f"{side} never reached {target!r} in {MAX_PULSES} {button} pulses")


def team_select(run, pad, port: int, out_dir: Path, plan: str, notes: dict) -> str:
    state, _text = probe.reach_menu(run, pad, out_dir, notes)
    notes["menu_reached"] = state
    if state != "team-select":
        run.screenshot("02-main-menu", out_dir)
        probe.open_quick_game(run, pad)
    run.screenshot("03-team-select", out_dir)
    start = read_selection(port, run.logs / "h1-gdb.log")
    notes["team_select_start"] = start
    log(f"Team Select opened: {start}")
    if plan in ("pair", "mixed"):
        notes["home_trail"] = step_to(run, pad, port, "home", "49ers '81", "RT", notes, out_dir,
                                      shots=("49ers '81",))
        run.screenshot("04-home-49ers-81", out_dir)
        tap(pad, "LEFT", settle=1.0)
        tap(pad, "LEFT", settle=1.0)
        try:
            notes["away_trail"] = step_to(run, pad, port, "away", "Giants '90" if plan == "pair" else "GIANTS", "RT", notes, out_dir,
                                          shots=("49ers '81", "Giants '90"))
        finally:
            tap(pad, "RIGHT", settle=1.0)
            tap(pad, "RIGHT", settle=1.0)
    final = read_selection(port, run.logs / "h1-gdb.log")
    notes["team_select_final"] = final
    run.screenshot("04-team-select-final", out_dir)
    log(f"Team Select final: {final}")
    hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    run.screenshot("05-coach-matchup", out_dir)
    probe.start_game(run, pad, notes)
    log("game starting")
    return f"{final.get('away', {}).get('name')} AT {final.get('home', {}).get('name')}"


def card_phase(run, pad, out_dir, run_dir, seconds):
    """DESIGN: observable operator route, never an invented automatic card PASS.

    Main appends UP/DOWN/LEFT/RIGHT/A/B/X/Y/START/LT/RT, one pulse per line.
    NOTE text records the visible player name, jersey, position and equipment.
    DONE ends capture. Every command gets its own screenshot and ledger entry.
    """
    commands = run_dir / 'card-commands.txt'
    commands.touch(exist_ok=True)
    log(f'PLAYER CARD: append pad commands, NOTE observations and DONE to {commands}')
    tap(pad, 'START', settle=2.0)
    run.screenshot('card-000-pause', out_dir)
    deadline, seen, events = time.monotonic()+seconds, 0, []
    allowed = {'UP','DOWN','LEFT','RIGHT','A','B','X','Y','START','LT','RT'}
    while time.monotonic() < deadline:
        lines = commands.read_text().splitlines()
        for line in lines[seen:]:
            seen += 1
            command = line.strip()
            if not command:
                continue
            event = dict(command=command, at=time.strftime('%H:%M:%S'))
            events.append(event)
            if command == 'DONE':
                return dict(status='operator_capture_finished', reviewed=False, events=events)
            if command in allowed:
                tap(pad, command, settle=1.2)
                run.screenshot(f'card-{seen:03d}-{command}', out_dir)
            elif command.startswith('NOTE '):
                run.screenshot(f'card-{seen:03d}-observation', out_dir)
            else:
                event['error'] = 'Unsupported command; no input sent'
        time.sleep(0.5)
    return dict(status='operator_capture_timeout', reviewed=False, events=events)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xiso", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--plan", choices=("pair", "mixed"), required=True)
    ap.add_argument("--minutes", type=float, default=6.0)
    ap.add_argument("--label", default="")
    ap.add_argument("--card-seconds", type=float, default=240)
    args = ap.parse_args()
    xiso, run_dir = Path(args.xiso), Path(args.run_dir)
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
    run = probe.HeadlessRun(run_dir, display, port)
    qmp_port = 4455
    while not xr.port_free(qmp_port) or qmp_port == port:
        qmp_port += 1
    run.qmp_port = qmp_port
    pad = None
    watch_started = None
    ledger = dict(label=args.label, plan=args.plan, xiso=str(xiso), outcome="ERROR",
                  started=time.strftime("%Y-%m-%d %H:%M:%S"), load_start=probe.load_average(), route="ht", visual_review="PENDING: names, player card, classic equipment")
    try:
        run.start_display()
        pad = xr.Gamepad()
        run.start_xemu(xiso)
        log(f"xemu up on Xvfb :{display}, gdb tcp:127.0.0.1:{port}, qmp 127.0.0.1:{run.qmp_port}")
        route_started = time.monotonic()
        ledger["team_select"] = team_select(run, pad, port, out_dir, args.plan, ledger)
        ledger["route_seconds"] = round(time.monotonic() - route_started, 1)
        watch_started = time.monotonic()
        ledger.update(probe.watch(run, out_dir, port, args.minutes, frame_seconds=10.0, cpu_seconds=60.0))
        if ledger.get("outcome") == "PASS":
            ledger["match_teams"] = read_match(port, run.logs / "h1-gdb.log")
            log(f"match teams: {ledger['match_teams']}")
            ledger["player_card"] = card_phase(run, pad, out_dir, run_dir, args.card_seconds)
    except Exception as exc:  # noqa: BLE001
        ledger["error"] = f"{type(exc).__name__}: {exc}"
        info = probe.xemu_exit(run, wait=3.0) if watch_started is not None else None
        if info is not None:
            ledger["xemu_exit"] = info
            ledger["outcome"] = "PFIFO_ABORT" if info.get("pfifo") else "XEMU_EXIT"
        else:
            ledger["route_error"] = probe.route_error_reason(exc, run, ledger)
            log(f"FAILED ({ledger['route_error']}): {ledger['error']}")
        try:
            run.screenshot("zz-failure", out_dir)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if pad is not None:
            pad.quit()
        ledger["shutdown"] = run.shutdown()
        ledger["load_end"] = probe.load_average()
        if probe.SLOT_NOTES.get("vm_paused"):
            ledger["vm_paused"] = probe.SLOT_NOTES["vm_paused"]
        (run_dir / "ht-lab.json").write_text(json.dumps(ledger, indent=1, default=str) + "\n", encoding="utf-8")
        print(f"HT_LAB label={args.label or '-'} plan={args.plan} outcome={ledger['outcome']} "
              f"elapsed={ledger.get('elapsed', 0):.0f}s route_error={ledger.get('route_error', '-')} "
              f"teams={ledger.get('team_select', '-')}", flush=True)
    return 0 if ledger["outcome"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
