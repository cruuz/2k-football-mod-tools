#!/usr/bin/env python3
# DESIGN: main-only lab; derived from m1 wave-E driver, SHA256 5b6102792c0b967fc72e7bb1b7b0a9de7343d5bdb0b48888e9ed7c94c02fbfc4
"""e2 candidate-E lab driver: one headless xemu (stock flatpak), boot to the main menu with the committed Berman probe's
route, then take orders from a command file until `quit` or the hard deadline.

  flock LOCK nice -n 19 taskset -c 24-31 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
      python3 e2/lab_probe.py --xiso DISC --run-dir DIR [--minutes 25]

Commands (one per line, appended to DIR/cmds.txt; lines starting with # are ignored):
  shot NAME                 screenshot + OCR text
  ocr                       log the OCR line
  tap BTN [SECS] [SETTLE]   press a pad button
  hold BTN SECS             hold a pad button
  down N / up N             N taps of DOWN / UP (0.35 s apart)
  wait SECS
  gdb NAME                  batch gdb: all registers, x/96wx $esp, x/16i $eip
  peek NAME ADDR WORDS      checked batch gdb: EIP and x/WORDSwx ADDR (guest virtual)
  witness NAME [PHASE]      one stopped-state capture: preview, books (default), or selection
  snap NAME                 HMP stop + info registers, 64 MiB guest RAM from /proc/<xemu>/mem, HMP cont
  watch NAME SECS           frame digest every 2 s, OCR every 8 s, for SECS; a picture held for 45 s gets
                            two gdb samples and one retained book witness, then the watch ends
  reboot                    (m1) HMP system_reset, then the boot route to the main menu again
  quit

Headless by construction (Xvfb). Refuses to start while another xemu runs. Never retries anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

from lab_memory import capture_gdb, run_gdb

STACK = Path(os.environ["E2_STACK"])
sys.path[:0] = [str(STACK / "tools"), str(STACK)]
import xemu_berman_probe as bp  # noqa: E402
import xemu_playbook_create_runtime as xr  # noqa: E402
from xemu_practice_runtime import hold, screen_text, tap  # noqa: E402

xr.FIRMWARE_SOURCE = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu"
log = xr.log
STATE: dict = {"hmp": None, "ram_base": None, "snaps": [], "captures": [], "errors": []}


class Hmp:
    def __init__(self, path: Path, logfile: Path):
        self.path, self.logfile, self.sock = path, logfile, None

    def connect(self, timeout: float = 90.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(str(self.path))
                self.sock = s
                self._read(20.0)
                return True
            except OSError:
                time.sleep(0.5)
        return False

    def _read(self, timeout: float) -> str:
        self.sock.settimeout(timeout)
        buf = b""
        deadline = time.monotonic() + timeout
        while not buf.rstrip().endswith(b"(qemu)") and time.monotonic() < deadline:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        return buf.decode("utf-8", "replace")

    def cmd(self, command: str, timeout: float = 60.0) -> str:
        self.sock.sendall(command.encode() + b"\n")
        out = self._read(timeout)
        with self.logfile.open("a") as f:
            f.write(f"### {time.strftime('%H:%M:%S')} {command}\n{out}\n")
        return out


def xemu_pid(run) -> int:
    found = subprocess.run(["pgrep", "-x", "xemu"], capture_output=True, text=True).stdout.split()
    return int(found[0]) if len(found) == 1 else run.xemu.pid


def find_guest_ram(pid: int, size: int = 0x4000000):
    cands = []
    with open(f"/proc/{pid}/maps") as maps:
        for line in maps:
            parts = line.split()
            lo, hi = (int(v, 16) for v in parts[0].split("-"))
            if parts[1].startswith("rw") and hi - lo >= size:
                cands.append((hi - lo, lo, hi))
    cands.sort()
    with open(f"/proc/{pid}/mem", "rb", buffering=0) as mem:
        for _, lo, hi in cands:
            for off in range(0, hi - lo - size + 1, 0x1000):
                try:
                    mem.seek(lo + off + 0xF000 + 0x300 * 4)
                    if struct.unpack("<I", mem.read(4))[0] != 0x0000F063:
                        continue
                    mem.seek(lo + off + 0x10000)
                    if mem.read(2) == b"MZ":
                        return lo + off
                except OSError:
                    break
    return None


def snap(run, name: str) -> None:
    hmp = STATE["hmp"]
    if hmp is None:
        log("snap: no HMP monitor")
        return
    path = run.run_dir / "snaps" / f"{len(STATE['snaps']):02d}-{name}.bin"
    path.parent.mkdir(exist_ok=True)
    t1 = time.monotonic()
    try:
        hmp.cmd("stop", 20.0)
        regs = hmp.cmd("info registers", 20.0)
        pid = xemu_pid(run)
        if STATE["ram_base"] is None:
            STATE["ram_base"] = find_guest_ram(pid)
        base = STATE["ram_base"]
        if base is None:
            raise RuntimeError("guest RAM block not found")
        with open(f"/proc/{pid}/mem", "rb", buffering=0) as mem, path.open("wb") as out:
            mem.seek(base)
            left = 0x4000000
            while left:
                chunk = mem.read(min(left, 8 << 20))
                if not chunk:
                    raise RuntimeError("short read")
                out.write(chunk)
                left -= len(chunk)
        path.with_suffix(".regs.txt").write_text(regs)
        STATE["snaps"].append(dict(name=name, file=path.name, paused=round(time.monotonic() - t1, 2)))
        log(f"snap {path.name} ok ({time.monotonic() - t1:.2f}s paused)")
    except Exception as exc:  # noqa: BLE001
        log(f"snap {name} failed: {type(exc).__name__}: {exc}")
    finally:
        try:
            hmp.cmd("cont", 20.0)
        except Exception:  # noqa: BLE001
            pass


def gdb(run, name: str, extra: list[str] | None = None) -> str:
    ex = extra or ["info registers", "x/96wx $esp", "x/16i $eip"]
    result = run_gdb(run.gdb_port, run.logs / f"gdb-{name}.log", ex, resume=resume)
    log(f"gdb {name}: ok=true eip={result['eip']:#x}")
    return result["output"]


def resume():
    if STATE["hmp"] is not None:
        STATE["hmp"].cmd("cont", 10.0)


def witness(run, name, phase="books"):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("invalid witness name")
    directory = run.run_dir / "witnesses" / f"{len(STATE['captures']):03d}-{name}"
    result = capture_gdb(run.gdb_port, directory, phase, catalog=os.environ.get("E2_CATALOG"), resume=resume)
    STATE["captures"].append(dict(name=name, phase=phase, directory=str(directory)))
    log(f"witness {name}: eip={result['eip']:#x} mode={result.get('mode')} ordinal={result.get('ordinal')} "
        f"venue={result.get('historic_venue')!r} books=" +
        json.dumps({k: dict(filename=v['filename'], pointer=hex(v['pointer']), matches=v['content_matches'])
                    for k, v in result.get('books', {}).items()}))
    return result


def mixed_route(run, pad, out_dir):
    """Local copy of h1's single-pulse route, using E2's checked atomic reader."""
    bp.open_quick_game(run, pad)
    for pulse in range(61):
        selected = witness(run, f"mixed-selection-{pulse:02d}", "selection")["selection"]
        home, away = selected["home"], selected["away"]
        log(f"mixed pulse {pulse}: home={home['name']!r} away={away['name']!r}")
        if home["name"] == "Bears '85" and home["category"] == 4 and away["category"] != 4:
            run.screenshot("mixed-team-select", out_dir)
            hold(pad, "START", xr.START_HOLD)
            time.sleep(4.0)
            bp.start_game(run, pad, {})
            return
        if pulse < 60:
            tap(pad, "RT", secs=xr.TRIGGER_PULSE, settle=1.6)
    raise RuntimeError("mixed route did not reach historic Bears against a current opponent")


def digest(run) -> str:
    try:
        return hashlib.sha256(run._frame().tobytes()).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        return ""


def watch(run, out_dir: Path, name: str, secs: float, freeze: float = 45.0) -> None:
    start = time.monotonic()
    last, since, last_ocr = digest(run), time.monotonic(), 0.0
    run.screenshot(f"{name}-start", out_dir)
    frozen = False
    while time.monotonic() - start < secs:
        if run.xemu is not None and run.xemu.poll() is not None:
            log(f"watch {name}: xemu exited rc={run.xemu.returncode}")
            return
        d = digest(run)
        if d != last:
            last, since = d, time.monotonic()
        elif time.monotonic() - since >= freeze and not frozen:
            frozen = True
            log(f"watch {name}: picture held {time.monotonic() - since:.0f}s at +{time.monotonic() - start:.0f}s")
            run.screenshot(f"{name}-held", out_dir)
            gdb(run, f"{name}-held-1")
            time.sleep(2.0)
            gdb(run, f"{name}-held-2")
            witness(run, f"{name}-held")
            return
        if time.monotonic() - last_ocr >= 8.0:
            last_ocr = time.monotonic()
            log(f"watch {name} +{time.monotonic() - start:.0f}s held {time.monotonic() - since:.0f}s: "
                f"{screen_text(run)[:140]!r}")
        time.sleep(2.0)
    run.screenshot(f"{name}-end", out_dir)


def start_xemu(self, xiso_path):
    mon = self.run_dir / "hmp.sock"
    if mon.exists():
        mon.unlink()
    env = dict(os.environ, DISPLAY=f":{self.display}", SDL_VIDEODRIVER="x11", SDL_AUDIODRIVER="dummy",
               LIBGL_ALWAYS_SOFTWARE="1")
    command = ["flatpak", "run", f"--filesystem={self.run_dir}:rw", f"--filesystem={xiso_path}:ro",
               "app.xemu.xemu", "-config_path", str(self.run_dir / "xemu.toml"), "-dvd_path", str(xiso_path),
               "-gdb", f"tcp:127.0.0.1:{self.gdb_port}", "-monitor", f"unix:{mon},server=on,wait=off"]
    with (self.logs / "xemu.stderr.log").open("w") as err:
        self.xemu = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=err,
                                     cwd=str(self.run_dir))
    self.window = xr.Window(self.display)
    self.window.wait(60.0)
    hmp = Hmp(mon, self.run_dir / "hmp.log")
    if hmp.connect(90.0):
        STATE["hmp"] = hmp
        log("HMP monitor connected")
    else:
        log("HMP monitor NOT connected")


bp.HeadlessRun.start_xemu = start_xemu


def command_loop(run, pad, run_dir: Path, out_dir: Path, deadline: float) -> None:
    cmd_file = run_dir / "cmds.txt"
    cmd_file.touch()
    seen = 0
    log(f"command loop on {cmd_file}")
    while time.monotonic() < deadline:
        if run.xemu is not None and run.xemu.poll() is not None:
            log(f"xemu exited rc={run.xemu.returncode}; command loop ends")
            return
        lines = cmd_file.read_text().splitlines()
        for line in lines[seen:]:
            seen += 1
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            log(f"CMD {line}")
            p = line.split()
            try:
                if p[0] == "quit":
                    return
                if p[0] == "shot":
                    run.screenshot(p[1], out_dir)
                    txt = screen_text(run)
                    (out_dir / f"{p[1]}.txt").write_text(txt)
                    log(f"shot {p[1]}: {txt[:160]!r}")
                elif p[0] == "ocr":
                    log("OCR: " + screen_text(run)[:300])
                elif p[0] == "tap":
                    tap(pad, p[1], secs=float(p[2]) if len(p) > 2 else 0.15,
                        settle=float(p[3]) if len(p) > 3 else 0.6)
                elif p[0] == "hold":
                    hold(pad, p[1], float(p[2]))
                elif p[0] in ("down", "up"):
                    for _ in range(int(p[1])):
                        tap(pad, p[0].upper(), settle=0.35)
                elif p[0] == "wait":
                    time.sleep(float(p[1]))
                elif p[0] == "mixed":
                    mixed_route(run, pad, out_dir)
                elif p[0] == "reboot":
                    # m1: HMP system_reset, then the same boot route to the main menu as at start
                    hmp = STATE["hmp"]
                    if hmp is None:
                        log("reboot: no HMP monitor")
                    else:
                        hmp.cmd("system_reset", 20.0)
                        # m1a (17:14): `notes` is main()'s local; the reboot keeps its boot notes in STATE instead
                        state, text = bp.reach_menu(run, pad, out_dir, STATE.setdefault("reboot_notes", {}))
                        log(f"reboot reached {state}: {text[:120]!r}")
                        run.screenshot(f"reboot-{len(STATE['snaps'])}-{int(time.monotonic())}", out_dir)
                elif p[0] == "gdb":
                    gdb(run, p[1])
                elif p[0] == "peek":
                    gdb(run, p[1], [f"x/{int(p[3])}wx {p[2]}"])
                elif p[0] == "witness":
                    witness(run, p[1], p[2] if len(p) > 2 else "books")
                elif p[0] == "snap":
                    snap(run, p[1])
                elif p[0] == "watch":
                    watch(run, out_dir, p[1], float(p[2]))
                elif p[0] == "watchx":
                    # watch, and if the picture never held, still capture both full bound books at the end
                    before = len(STATE["captures"])
                    watch(run, out_dir, p[1], float(p[2]))
                    if len(STATE["captures"]) == before:
                        gdb(run, f"{p[1]}-end-1")
                        time.sleep(2.0)
                        gdb(run, f"{p[1]}-end-2")
                        witness(run, f"{p[1]}-end")
                else:
                    log(f"unknown command {line!r}")
            except Exception as exc:  # noqa: BLE001
                log(f"command failed: {type(exc).__name__}: {exc}")
                STATE["errors"].append(dict(command=line, error=f"{type(exc).__name__}: {exc}"))
                raise
        time.sleep(0.5)
    log("hard deadline reached")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xiso", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--minutes", type=float, default=25.0)
    a = ap.parse_args()
    started = time.monotonic()
    deadline = started + a.minutes * 60
    xiso, run_dir = Path(a.xiso), Path(a.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "screens"
    out_dir.mkdir(exist_ok=True)
    xr.abort_if_xemu_running()
    iso = xr.setup_isolation(run_dir, xiso)
    log(json.dumps(iso))
    display = xr.pick_display()
    port = 1234
    while not xr.port_free(port):
        port += 1
    run = bp.HeadlessRun(run_dir, display, port)
    pad = None
    notes: dict = {}
    result = {"xiso": str(xiso), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        run.start_display()
        pad = xr.Gamepad()
        run.start_xemu(xiso)
        log(f"xemu up on :{display}, gdb tcp:127.0.0.1:{port}")
        try:
            state, text = bp.reach_menu(run, pad, out_dir, notes)
        except Exception as exc:  # noqa: BLE001
            # x1 (2026-09-23): a stray connection to the gdb port can leave the VM paused. Check once, and if the VM
            # is paused, resume it and try the boot route one more time. A running VM is a real hang: re-raise.
            hmp = STATE["hmp"]
            status = hmp.cmd("info status", 10.0) if hmp is not None else "no HMP"
            log(f"boot gate failed ({type(exc).__name__}); HMP info status: {status!r}")
            if hmp is None or "paused" not in str(status):
                raise
            log("VM was paused: HMP cont, one more boot route")
            hmp.cmd("cont", 10.0)
            notes["harness_pause_at_boot"] = str(status)
            state, text = bp.reach_menu(run, pad, out_dir, notes)
        log(f"reached {state}: {text[:120]!r}")
        run.screenshot("02-main-menu", out_dir)
        result["menu"] = state
        command_loop(run, pad, run_dir, out_dir, deadline)
    except Exception as exc:  # noqa: BLE001
        log(f"FAILED: {type(exc).__name__}: {exc}")
        result["error"] = f"{type(exc).__name__}: {exc}"
        try:
            run.screenshot("zz-failure", out_dir)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if pad is not None:
            pad.quit()
        result["shutdown"] = run.shutdown()
        result["notes"] = notes
        result["snaps"] = STATE["snaps"]
        result["captures"] = STATE["captures"]
        result["command_errors"] = STATE["errors"]
        result["seconds"] = round(time.monotonic() - started, 1)
        (run_dir / "e2-lab.json").write_text(json.dumps(result, indent=1, default=str))
        log("E2_LAB_DONE " + json.dumps({k: result.get(k) for k in ("menu", "error", "seconds")}))
    return 1 if result.get("error") or STATE["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
