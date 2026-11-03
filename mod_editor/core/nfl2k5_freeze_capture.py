"""Freeze capture: when the game freezes in xemu, write down where it stopped (b780 n4).

Why.  Every freeze report so far reads the same from outside ("the game froze and the commentators repeat lines"):
on the Xbox all game code runs in one loop, so whether the cause is a crash stop in the kernel or a loop that never
ends, the picture stops and the sound card keeps cycling its last buffer.  What tells the causes apart is the address
the processor is stuck at and the calls that led there, which a player cannot see.  xemu has a built-in debugger port
(the ``-gdb`` option).  This module connects to that port, samples the processor a dozen times, reads the registers,
the return addresses on the stack and the game's own play state (game mode, play phase, down, which team has the
ball, the play counter, the play-calling option), lets the game run on, and writes a short plain-text report the
player can post.

Opt in only.  Nothing is added to a normal launch.  The Studio's "Play latest disc in xemu" adds
``-gdb tcp:127.0.0.1:PORT`` only when the player turned freeze capture on with this command (or set the
``NFL2K5_FREEZE_CAPTURE_PORT`` environment variable)::

    python3 -m mod_editor.core.nfl2k5_freeze_capture --enable 1234     (turn on; --disable turns it off)
    python3 -m mod_editor.core.nfl2k5_freeze_capture --port 1234       (when frozen: write the report)

Players who start xemu themselves add ``-gdb tcp:127.0.0.1:1234`` to its command line (see
docs/mod_editor/freeze_capture_and_disc_check.md).  The port listens on this computer only.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Any

SETTINGS = Path.home() / ".config" / "2k5-mod-studio" / "freeze-capture.json"
SCHEMA = "2k5_mod_studio_freeze_capture/v1"
ENV = "NFL2K5_FREEZE_CAPTURE_PORT"
DEFAULT_PORT = 1234
REGS = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi", "eip", "eflags")

# ESPN NFL 2K5 (retail layout; the Studio keeps these addresses): the game's play-state block and counters.
PLAY_BLOCK = 0xE60280         # +0 offense team, +4 defense team, +0x34 phase, +0x38 play state, +0x3C kind, +0x44 quarter,
                              # +0x6C situation (down at +4)
DRIVE_COUNTER = 0xE53800      # drive number; the play count follows it
PLAY_COUNTER = 0xE53804
GAME_MODE = 0xE5FF80
PLAYCALL_OPTION = 0xE60018    # 0 By Package, 1 By Formation, 2 Let Coach Pick
HOME_TEAM, AWAY_TEAM = 0xE5FC20, 0xE5FC60
GAME_TEXT = (0x11000, 0x4E0000)   # retail .text and its neighbours
CAVES = (0x1400000, 0x1600000)    # the Studio's added code sections
MODES = {1: "Practice", 3: "Practice", 4: "Play Now", 5: "Season", 6: "Franchise", 7: "Franchise / playoffs",
         8: "Situation or Anniversary moment"}
PLAYCALL = {0: "By Package", 1: "By Formation", 2: "Let Coach Pick"}


class CaptureError(RuntimeError):
    pass


# --------------------------------------------------------------------------------------------- opt-in (launch side)

def launch_port(settings: Path | None = None, environ: dict[str, str] | None = None) -> int | None:
    """The debugger port to add to a Studio xemu launch, or None (the default: no -gdb)."""
    env = os.environ if environ is None else environ
    raw = env.get(ENV, "").strip()
    if raw:
        return _port(raw)
    path = SETTINGS if settings is None else settings
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or not document.get("enabled"):
        return None
    return _port(document.get("port", DEFAULT_PORT))


def _port(value: Any) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1024 <= port <= 65535 else None


def set_enabled(port: int | None, settings: Path | None = None) -> Path:
    path = SETTINGS if settings is None else settings
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"schema": SCHEMA, "enabled": port is not None, "port": port or DEFAULT_PORT}
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path


def with_debug_port(argv: tuple[str, ...], port: int) -> tuple[str, ...]:
    """xemu's argv with ``-gdb tcp:127.0.0.1:PORT`` (listening on this computer only), after the app id of a Flatpak."""
    option = ("-gdb", f"tcp:127.0.0.1:{int(port)}")
    if "-gdb" in argv:
        return tuple(argv)
    return (*argv, *option)


# --------------------------------------------------------------------------------------------- the gdb remote client

class Remote:
    """A minimal GDB remote-serial-protocol client for QEMU's (xemu's) stub."""

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        try:
            self.s = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise CaptureError(
                f"Nothing answered on {host}:{port}. Start xemu with -gdb tcp:127.0.0.1:{port} (or turn freeze capture "
                f"on and launch from the Studio), then capture while the game is frozen. Detail: {exc}") from exc
        self.s.settimeout(timeout)
        self.buffer = b""

    def close(self) -> None:
        try:
            self.s.close()
        except OSError:
            pass

    def _recv(self) -> bytes:
        chunk = self.s.recv(65536)
        if not chunk:
            raise CaptureError("xemu closed the debugger connection")
        return chunk

    def _packet(self) -> str:
        while True:
            start = self.buffer.find(b"$")
            if start >= 0:
                end = self.buffer.find(b"#", start)
                if end >= 0 and len(self.buffer) >= end + 3:
                    body = self.buffer[start + 1:end]
                    self.buffer = self.buffer[end + 3:]
                    self.s.sendall(b"+")
                    return body.decode("latin1")
            self.buffer += self._recv()

    def send(self, body: str) -> None:
        data = body.encode("latin1")
        self.s.sendall(b"$" + data + b"#" + f"{sum(data) & 0xFF:02x}".encode())

    def command(self, body: str) -> str:
        self.send(body)
        while True:
            reply = self._packet()
            if reply.startswith("O") and len(reply) > 1 and all(c in "0123456789abcdefABCDEF" for c in reply[1:]):
                continue   # console output packets
            return reply

    def interrupt(self) -> str:
        self.s.sendall(b"\x03")
        return self._packet()

    def resume(self) -> None:
        self.send("c")

    def registers(self) -> dict[str, int]:
        reply = self.command("g")
        raw = bytes.fromhex(reply[:80])
        return dict(zip(REGS, struct.unpack("<10I", raw)))

    def read(self, address: int, size: int) -> bytes | None:
        out = bytearray()
        while len(out) < size:
            n = min(0x800, size - len(out))
            reply = self.command(f"m{address + len(out):x},{n:x}")
            if not reply or reply.startswith("E") and len(reply) == 3:
                return None
            try:
                out += bytes.fromhex(reply)
            except ValueError:
                return None
        return bytes(out)

    def detach(self) -> None:
        try:
            self.send("D")
            self.s.settimeout(2.0)
            self._packet()
        except (OSError, CaptureError):
            pass


# --------------------------------------------------------------------------------------------- the capture

def _u32(blob: bytes | None, offset: int = 0) -> int | None:
    if blob is None or len(blob) < offset + 4:
        return None
    return struct.unpack_from("<I", blob, offset)[0]


def _region(address: int) -> str:
    if GAME_TEXT[0] <= address < GAME_TEXT[1]:
        return "game code"
    if CAVES[0] <= address < CAVES[1]:
        return "Studio-added code"
    if address >= 0x80000000:
        return "Xbox kernel"
    return "other"


def _return_addresses(remote: Remote, stack: bytes | None) -> list[dict[str, str]]:
    """Dwords on the stack that point just after a call instruction in game or Studio code."""
    found = []
    if not stack:
        return found
    for offset in range(0, len(stack) - 3, 4):
        value = struct.unpack_from("<I", stack, offset)[0]
        if _region(value) not in ("game code", "Studio-added code"):
            continue
        before = remote.read(value - 7, 7)
        if before and (before[2] == 0xE8 or before[1] == 0xFF and before[2] & 0x38 == 0x10
                       or before[5] == 0xFF and before[6] & 0x38 == 0x10 or before[4] == 0xFF and before[5] & 0x38 == 0x10):
            found.append(dict(stack_offset=hex(offset), address=hex(value), where=_region(value)))
        if len(found) >= 24:
            break
    return found


def capture(host: str = "127.0.0.1", port: int = DEFAULT_PORT, *, samples: int = 12, interval: float = 0.25,
            timeout: float = 10.0) -> dict[str, Any]:
    """Sample the stopped (or running) game, read its play state, and let it run on. Returns the report data."""
    remote = Remote(host, port, timeout)
    result: dict[str, Any] = dict(schema="nfl2k5_freeze_capture/v1", time=time.strftime("%Y-%m-%d %H:%M:%S"),
                                  host=host, port=port)
    try:
        remote.command("?")            # QEMU stops the machine when a debugger attaches
        eips = []
        for _ in range(max(1, samples)):
            regs = remote.registers()
            eips.append(regs["eip"])
            remote.resume()
            time.sleep(interval)
            remote.interrupt()
        regs = remote.registers()
        result["eip_samples"] = [hex(e) for e in eips]
        result["distinct_eips"] = len(set(eips))
        result["registers"] = {k: hex(v) for k, v in regs.items()}
        stack = remote.read(regs["esp"], 0x200)
        result["stack_hex"] = stack.hex() if stack else None
        result["return_addresses"] = _return_addresses(remote, stack)
        block = remote.read(PLAY_BLOCK, 0x80)
        state: dict[str, Any] = {}
        if block:
            off, dfn = _u32(block, 0), _u32(block, 4)
            state.update(offense={HOME_TEAM: "home", AWAY_TEAM: "away"}.get(off, hex(off or 0)),
                         defense={HOME_TEAM: "home", AWAY_TEAM: "away"}.get(dfn, hex(dfn or 0)),
                         phase=_u32(block, 0x34), play_state=_u32(block, 0x38), kind=_u32(block, 0x3C),
                         quarter=_u32(block, 0x44))
            situation = _u32(block, 0x6C)
            if situation and 0x10000 < situation < 0x4000000:
                state["down"] = _u32(remote.read(situation + 4, 4))
        mode = _u32(remote.read(GAME_MODE, 4))
        option = _u32(remote.read(PLAYCALL_OPTION, 4))
        state.update(play_count=_u32(remote.read(PLAY_COUNTER, 4)), drive=_u32(remote.read(DRIVE_COUNTER, 4)), game_mode=mode,
                     game_mode_name=MODES.get(mode, "other"), play_calling=PLAYCALL.get(option, option))
        result["game_state"] = state
        result["verdict"] = _verdict(eips)
    finally:
        try:
            remote.detach()        # QEMU lets the machine run on when the debugger detaches
        finally:
            remote.close()
    return result


def _verdict(eips: list[int]) -> str:
    regions = {_region(e) for e in eips}
    if len(set(eips)) == 1 and regions == {"Xbox kernel"}:
        return ("The processor is parked at one address inside the Xbox kernel: this looks like a crash stop "
                "(the game hit an error and the system halted). The return addresses show which game code called it.")
    if regions <= {"Xbox kernel"}:
        return ("The processor is inside the Xbox kernel: either a crash stop or the game waiting on the system "
                "(for example a disc read that never finishes). A disc check of the image tells a bad copy apart.")
    if len(set(eips)) <= 4:
        return "The game is stuck in a small loop of its own code (see the addresses)."
    return ("The game code is still running: it may be stuck in a larger loop, or the freeze was over when the capture "
            "ran. Capture again while the picture is frozen.")


def report_text(result: dict[str, Any]) -> str:
    s = result.get("game_state", {})
    lines = [
        "ESPN NFL 2K5 / SOFTDRINK freeze capture",
        f"Taken: {result.get('time')}  (xemu debugger port {result.get('port')})",
        "",
        result.get("verdict", ""),
        "",
        "Where the processor was (12 samples): " + ", ".join(result.get("eip_samples", [])),
        "Registers: " + ", ".join(f"{k}={v}" for k, v in result.get("registers", {}).items()),
        "Calls that led there (return addresses on the stack, nearest first):",
    ]
    lines += [f"  {r['address']}  ({r['where']}, stack +{r['stack_offset']})" for r in result.get("return_addresses", [])] \
        or ["  (none found)"]
    lines += [
        "",
        f"Game: {s.get('game_mode_name')} (mode {s.get('game_mode')}), play calling: {s.get('play_calling')}",
        f"Play: phase {s.get('phase')}, play state {s.get('play_state')}, kind {s.get('kind')}, quarter {s.get('quarter')}, "
        f"down {s.get('down')}, plays so far {s.get('play_count')}, drive {s.get('drive')}",
        f"Offense: {s.get('offense')}  Defense: {s.get('defense')}",
        "",
        "Please post this whole file with your report, plus what was on screen and which disc you play.",
    ]
    return "\n".join(lines) + "\n"


def write_report(result: dict[str, Any], directory: Path | None = None) -> Path:
    folder = Path(directory) if directory else Path.home()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime("2k5-freeze-capture-%Y%m%d-%H%M%S.txt")
    path.write_text(report_text(result) + "\nRaw data:\n" + json.dumps(result, indent=1) + "\n", encoding="utf-8",
                    newline="\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture where a frozen ESPN NFL 2K5 game stopped (xemu -gdb port).")
    parser.add_argument("--port", type=int, default=None, help=f"xemu's debugger port (default {DEFAULT_PORT})")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--out", default=None, help="folder for the report (default: your home folder)")
    parser.add_argument("--enable", type=int, nargs="?", const=DEFAULT_PORT, default=None, metavar="PORT",
                        help="turn freeze capture on for the Studio's xemu launches (adds -gdb on this port)")
    parser.add_argument("--disable", action="store_true", help="turn freeze capture off again")
    args = parser.parse_args(argv)
    if args.enable is not None or args.disable:
        if args.enable is not None and _port(args.enable) is None:
            parser.error("choose a port from 1024 to 65535")
        path = set_enabled(None if args.disable else args.enable)
        state = "off" if args.disable else f"on (port {args.enable})"
        print(f"Freeze capture is {state} for the Studio's xemu launches. Setting: {path}")
        return 0
    port = args.port or launch_port() or DEFAULT_PORT
    try:
        result = capture(args.host, port)
    except CaptureError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    path = write_report(result, args.out)
    print(report_text(result))
    print(f"Report written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
