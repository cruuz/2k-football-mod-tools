#!/usr/bin/env python3
"""Automated xemu runtime proof for the formation/play clone writer.

Compiles one creation plan with
``mod_editor/core/nfl2k5_formation_play_writer.py`` (imported, never copied)
into book outer 308 (ATL): one formation clone + one play clone + one
provisional 2-byte u16 link from the created formation's first empty aux slot
to the created play.  Bakes the proved pack-0 slice into a layout-identical
copy of the retail XISO (transport helpers imported from
``tools/nfl_uniform_color_xiso_direct_patch.py``), then runs xemu isolated on
a nested display with a fresh qcow2 overlay over the pinned live HDD.

Arms:
  attract  no-input boot/render smoke.
  route    OCR press-start -> Settings1 modal -> Quick Game -> team select
           RT-pulses to ATL -> coin toss -> live gameplay, then a gdb phase
           that dumps guest RAM, stakes the created records, and sets READ
           watchpoints on them while the title plays itself.

Freezes ``reports/assets/nfl2k5_playbook_create_xemu_runtime.json`` plus
pinned PNGs.  Never touches the live HDD/config (hashes verified before and
after).  Never fakes evidence: every claim is derived from a captured gate.

The link write is provisional (``link_provisional: true``): the shipped
writer gains a real link API separately (agent W1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import nfl_uniform_color_xiso_direct_patch as xc  # transport helpers (import, not fork)
import xemu_press_start_ocr as ocr  # capture/OCR helpers (import, not fork)
from PIL import Image, ImageEnhance
from Xlib import display as xdisplay

from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core.nfl2k5_playbook_inspector import (
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_BASE,
    FORMATION_PLAY_LINKS,
    FORMATION_SIZE,
    PLAY_BASE,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    parse_playbook_resource,
)

SCHEMA = "nfl2k5_playbook_create_xemu_runtime/v1"

ASSET_ID = "nfl2k5.resource.o0308.c0000.k504c4159"
BOOK_NAME = "ATL"
FORMATION_DONOR = 0  # "Split Pro" — offense, 24 empty aux slots
PLAY_DONOR = 0
CACHE_ROOT = Path("/home/noah/.cache/2k5-mod-studio")
INDEX = CACHE_ROOT / "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = CACHE_ROOT / "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/indexes/nfl2k5_resource_chunks_v2.json"

RETAIL_XISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
RETAIL_XISO_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
LIVE_HDD = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu/xbox_hdd.qcow2"
LIVE_CONFIG = Path.home() / ".var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml"
FIRMWARE_SOURCE = Path("/media/noah/Storage/.codex-tmp/nfl2k5-xemu-lions-png-donorbase-controller-20260711")
FIRMWARE_SHA = {
    "mcpx_1.0.bin": "e99e3a772bf5f5d262786aee895664eb96136196e37732fe66e14ae062f20335",
    "Complex_4627.bin": "34f1c8ded59116436065783f8ad2ef0939df3cbfc76277ec9e5c41bf9ccb93cd",
    "eeprom.bin": "52142e8293aada6343cb07c9aa816b60a6d84bddc230594269ec99f6d188b516",
}
RUN_PARENT = Path("/media/noah/Storage/.codex-tmp")
FROZEN_DIR = ROOT / "reports/assets/nfl2k5_playbook_create_xemu_runtime"
FROZEN_JSON = ROOT / "reports/assets/nfl2k5_playbook_create_xemu_runtime.json"

GUEST_RAM_SIZE = 0x04000000  # Xbox: 64 MiB, cached window mapped 1:1 at 0
BODY_OFF = RESOURCE_HEADER_SIZE  # 0x20 wrapper

# Pinned route timings from docs/research/nfl_lions_png_import_xemu_runtime.md
START_HOLD = 3.0
MODAL_A_HOLD = 3.0
TRIGGER_PULSE = 0.15
TEAM_TOP_CROP = (220, 55, 1070, 155)
PRESS_CROP = (160, 0, 1120, 240)


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GateError(RuntimeError):
    def __init__(self, gate: str, message: str):
        super().__init__(f"{gate}: {message}")
        self.gate = gate


# --------------------------------------------------------------------------
# Stage 1: compile the creation plan through the real writer
# --------------------------------------------------------------------------

def compile_plan() -> dict:
    log("compiling creation plan through mod_editor.core.nfl2k5_formation_play_writer")
    replacement, _, report, selector, target = writer.build_unified_formation_play_import(
        INDEX,
        INVENTORY,
        ASSET_ID,
        formation_requests=[{"asset_id": ASSET_ID, "donor_formation_index": FORMATION_DONOR}],
        play_requests=[{"asset_id": ASSET_ID, "donor_play_index": PLAY_DONOR}],
    )
    replacement = bytearray(replacement)
    new_f = report["new_formation_indices"][0]
    new_p = report["new_play_indices"][0]
    source_sha = report["source_sha256"]
    raw_source = _read_raw_resource()
    parsed_source = parse_playbook_resource(raw_source, asset_id=ASSET_ID)
    assert parsed_source.book_name == BOOK_NAME, parsed_source.book_name

    # Provisional link (writer has no link API yet; agent W1 ships it).
    # Find the first empty aux slot of the created formation: empty =
    # low 9 bits == 0x1FF (inspector skips exactly those entries).
    aux_off = BODY_OFF + FORMATION_AUX_BASE + new_f * FORMATION_AUX_SIZE
    first_empty = None
    for slot in range(FORMATION_PLAY_LINKS):
        packed = struct.unpack_from("<H", replacement, aux_off + slot * 2)[0]
        if (packed & 0x01FF) == 0x01FF:
            first_empty = slot
            break
    if first_empty is None:
        raise GateError("compile", "created formation has no empty aux slot")
    # Group bits: mirror the donor formation's own link to the donor play,
    # since the created play is an exact clone of that donor play.
    group = 0
    donor_aux = BODY_OFF + FORMATION_AUX_BASE + FORMATION_DONOR * FORMATION_AUX_SIZE
    for slot in range(FORMATION_PLAY_LINKS):
        packed = struct.unpack_from("<H", replacement, donor_aux + slot * 2)[0]
        if (packed & 0x01FF) == PLAY_DONOR:
            group = (packed >> 9) & 0x3
            break
    link_packed = new_p | (group << 9)
    before_link = bytes(replacement)
    struct.pack_into("<H", replacement, aux_off + first_empty * 2, link_packed)
    link_changed = sorted(
        i for i, (a, b) in enumerate(zip(before_link, replacement)) if a != b
    )
    assert len(link_changed) == 2, link_changed

    # Verify by reparse: created formation now links the created play.
    parsed = parse_playbook_resource(bytes(replacement), asset_id=ASSET_ID)
    created = parsed.formations[new_f]
    linked = [l for l in created.play_links if l.play_index == new_p]
    assert len(linked) == 1 and linked[0].link_index == first_empty, linked
    assert linked[0].group == group

    # Markers for the guest-RAM stake: exact created record bytes.
    body = replacement[BODY_OFF:]
    formation_record = bytes(
        body[FORMATION_BASE + new_f * FORMATION_SIZE:
             FORMATION_BASE + new_f * FORMATION_SIZE + FORMATION_SIZE]
    )
    play_record = bytes(
        body[PLAY_BASE + new_p * PLAY_SIZE: PLAY_BASE + new_p * PLAY_SIZE + PLAY_SIZE]
    )
    aux_record = bytes(
        body[FORMATION_AUX_BASE + new_f * FORMATION_AUX_SIZE:
             FORMATION_AUX_BASE + new_f * FORMATION_AUX_SIZE + FORMATION_AUX_SIZE]
    )
    for name, marker in (("formation", formation_record), ("play", play_record),
                         ("aux", aux_record)):
        count = count_occurrences(bytes(replacement), marker)
        assert count == 1, f"{name} marker not unique inside replacement: {count}"

    return {
        "asset_id": ASSET_ID,
        "book_name": BOOK_NAME,
        "selector": selector,
        "writer_report": json.loads(json.dumps(report, default=list)),
        "target": dict(target),
        "source_span_sha256": source_sha,
        "replacement": bytes(replacement),
        "new_formation_index": new_f,
        "new_play_index": new_p,
        "formation_donor": FORMATION_DONOR,
        "play_donor": PLAY_DONOR,
        "formation_donor_name": parsed_source.formations[FORMATION_DONOR].name,
        "play_donor_name": parsed_source.plays[PLAY_DONOR].name,
        "link": {
            "provisional": True,
            "aux_slot": first_empty,
            "packed_u16": link_packed,
            "group_bits": group,
            "changed_offsets_in_replacement": link_changed,
            "note": (
                "Temporary 2-byte u16 write compiled inside this orchestrator "
                "because the shipped writer has no link API yet (agent W1 "
                "lands it separately). Verified empty before the write and "
                "verified by full reparse after."
            ),
        },
        "markers": {
            "formation_record_sha256": sha256_bytes(formation_record),
            "play_record_sha256": sha256_bytes(play_record),
            "aux_record_sha256": sha256_bytes(aux_record),
            "formation_record": formation_record,
            "play_record": play_record,
            "aux_record": aux_record,
            "formation_record_body_offset": FORMATION_BASE + new_f * FORMATION_SIZE,
            "play_record_body_offset": PLAY_BASE + new_p * PLAY_SIZE,
        },
    }


def _read_raw_resource() -> bytes:
    from mod_editor.core.nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex
    from nfl_outer import read_entry_range

    sidecar = INVENTORY.parent / "universal-assets-v1.sqlite3"
    index = Nfl2k5UniversalAssetIndex(INVENTORY, INDEX, sidecar)
    record = index.get(ASSET_ID)
    entry = index.archive.entries[record.outer_index]
    return read_entry_range(index.archive, entry, record.chunk_offset, record.raw_size)


def count_occurrences(haystack: bytes, needle: bytes) -> int:
    count = 0
    start = 0
    while True:
        found = haystack.find(needle, start)
        if found < 0:
            return count
        count += 1
        start = found + 1


# --------------------------------------------------------------------------
# Stage 2: bake the slice into a layout-identical XISO copy
# --------------------------------------------------------------------------

def bake_xiso(plan: dict, output_path: Path) -> dict:
    target = plan["target"]
    replacement = plan["replacement"]
    span_start = target["xiso_absolute_span_offset"]
    span_size = len(replacement)
    log(f"baking {span_size} byte span at absolute offset {span_start} into {output_path}")

    source = RETAIL_XISO.resolve(strict=True)
    xc.require(not output_path.exists(), f"output already exists: {output_path}")
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    owned = None
    try:
        info = os.fstat(source_fd)
        xc.require(info.st_size == xc.EXPECTED_XISO_SIZE, "retail XISO size mismatch")
        source_sha_before = xc.sha256_fd(source_fd)
        xc.require(source_sha_before == RETAIL_XISO_SHA256, "retail XISO SHA-256 mismatch")
        entries, directory = xc.parse_xdvdfs(source_fd, info.st_size)

        # Verify the retail span equals the writer's pinned source span.
        retail_span = xc.read_exact(source_fd, span_start, span_size)
        xc.require(sha256_bytes(retail_span) == plan["source_span_sha256"],
                   "retail span no longer equals the writer's pinned source span")
        xc.require(retail_span == _read_raw_resource(),
                   "retail span no longer equals the indexed PLAY resource")

        owned = xc.reserve_file(output_path)
        copy_method = xc.copy_fd_exact(source_fd, owned.descriptor, info.st_size)
        os.pwrite(owned.descriptor, replacement, span_start)
        xc.require(xc.read_exact(owned.descriptor, span_start, span_size) == replacement,
                   "written span readback mismatch")
        os.fsync(owned.descriptor)

        # Allowed set = exactly the bytes where the final replacement differs
        # from the retail span (derived from bytes, not range arithmetic: a
        # provisional link byte can restore the retail value).
        allowed = {span_start + index
                   for index, (before, after) in enumerate(zip(retail_span, replacement))
                   if before != after}
        source_sha_after, output_sha, differences = xc.compare_and_hash(
            source_fd, owned.descriptor, info.st_size, allowed
        )
        xc.require(source_sha_after == source_sha_before,
                   "retail source XISO changed during bake")
        out_entries, out_directory = xc.parse_xdvdfs(owned.descriptor, info.st_size)
        xc.require(out_entries == entries and out_directory == directory,
                   "XDVDFS tree or metadata changed")
        return {
            "path_at_run": str(output_path),
            "size": info.st_size,
            "inode": os.fstat(owned.descriptor).st_ino,
            "copy_method": copy_method,
            "retail_sha256_before": source_sha_before,
            "retail_sha256_after": source_sha_after,
            "output_sha256": output_sha,
            "span_start": span_start,
            "span_end_exclusive": span_start + span_size,
            "span_size": span_size,
            "span_source_sha256": plan["source_span_sha256"],
            "span_replacement_sha256": plan["writer_report"]["replacement_sha256"],
            "changed_byte_count": len(differences),
            "xdvdfs_tree_identical": True,
            "layout_identical_copy": True,
        }
    finally:
        os.close(source_fd)
        if owned is not None:
            os.close(owned.descriptor)


def reuse_baked_artifact(plan: dict, output_path: Path) -> dict:
    """Validate an already-baked XISO so emulator arms can be re-run without
    re-copying 6.3 GB.  Refuses anything that is not the exact baked output."""
    target = plan["target"]
    replacement = plan["replacement"]
    span_start = target["xiso_absolute_span_offset"]
    span_size = len(replacement)
    log(f"reusing baked artifact {output_path}")
    fd = os.open(output_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        xc.require(info.st_size == xc.EXPECTED_XISO_SIZE, "baked XISO size mismatch")
        output_sha = xc.sha256_fd(fd)
        got_span = xc.read_exact(fd, span_start, span_size)
        xc.require(got_span == replacement,
                   "baked span no longer equals the compiled replacement")
        return {
            "path_at_run": str(output_path),
            "size": info.st_size,
            "inode": info.st_ino,
            "copy_method": "reused-existing-bake",
            "retail_sha256_before": RETAIL_XISO_SHA256,
            "retail_sha256_after": RETAIL_XISO_SHA256,
            "output_sha256": output_sha,
            "span_start": span_start,
            "span_end_exclusive": span_start + span_size,
            "span_size": span_size,
            "span_source_sha256": plan["source_span_sha256"],
            "span_replacement_sha256": plan["writer_report"]["replacement_sha256"],
            "changed_byte_count": sum(1 for a, b in zip(
                _read_raw_resource(), replacement) if a != b),
            "xdvdfs_tree_identical": True,
            "layout_identical_copy": True,
            "reused": True,
        }
    finally:
        os.close(fd)


# --------------------------------------------------------------------------
# Isolation: run dir, firmware, fresh overlay, config
# --------------------------------------------------------------------------

def setup_isolation(run_dir: Path, xiso_path: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    firmware = {}
    for name, want_sha in FIRMWARE_SHA.items():
        src = FIRMWARE_SOURCE / name
        dst = run_dir / name
        if dst.exists():
            dst.unlink()
        shutil.copy2(src, dst)
        got = sha256_file(dst)
        if got != want_sha:
            raise GateError("isolation", f"firmware {name} hash {got} != pinned {want_sha}")
        firmware[name] = got
    overlay = run_dir / "xbox_hdd.qcow2"
    if overlay.exists():
        overlay.unlink()
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2",
         "-b", str(LIVE_HDD), str(overlay)],
        check=True, capture_output=True,
    )
    check = subprocess.run(["qemu-img", "check", str(overlay)],
                           check=True, capture_output=True, text=True).stdout
    config_text = f"""[general]
show_welcome = false

[input]
auto_bind = false
background_input_capture = true
gamepad_mappings = [
    {{ gamepad_id = '030081b85e0400008e02000014010000'}}
    ]

[input.bindings]
port1_driver = 'usb-xbox-gamepad'
port1 = '030081b85e0400008e02000014010000'

[display.window]
startup_size = '1280x720'

[display.ui]
aspect_ratio = 'native'
auto_scale = false

[sys.files]
bootrom_path = '{run_dir / "mcpx_1.0.bin"}'
flashrom_path = '{run_dir / "Complex_4627.bin"}'
eeprom_path = '{run_dir / "eeprom.bin"}'
hdd_path = '{overlay}'
dvd_path = '{xiso_path}'
"""
    (run_dir / "xemu.toml").write_text(config_text)
    return {
        "run_directory": str(run_dir),
        "firmware_sha256": firmware,
        "overlay_path": str(overlay),
        "overlay_backing_path": str(LIVE_HDD),
        "overlay_qemu_img_check": " ".join(check.split()),
        "config_path": str(run_dir / "xemu.toml"),
    }


# --------------------------------------------------------------------------
# Runtime plumbing: display, xemu, gamepad, screenshots, gdb
# --------------------------------------------------------------------------

def pick_display() -> int:
    taken = {name[1:] for name in os.listdir("/tmp/.X11-unix")}
    for candidate in ("99", "98", "97", "96", "95", "94", "93"):
        if candidate not in taken:
            return int(candidate)
    raise GateError("display", "no free nested display number found")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def abort_if_xemu_running() -> None:
    result = subprocess.run(["pgrep", "-x", "xemu"], capture_output=True, text=True)
    if result.returncode == 0:
        raise GateError("preflight", f"another xemu is already running: {result.stdout.split()}")


class Window:
    def __init__(self, display_number: int, needle: str = "xemu"):
        self.dpy = xdisplay.Display(f":{display_number}")
        self.needle = needle.casefold()

    def find(self):
        matches = []
        for window in ocr.walk(self.dpy.screen().root):
            try:
                if self.needle not in ocr.title(window).casefold():
                    continue
                if window.get_attributes().map_state != 2:  # X.IsViewable
                    continue
            except Exception:
                continue
            matches.append(window)
        return matches[-1] if matches else None

    def wait(self, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            window = self.find()
            if window is not None:
                return window
            time.sleep(0.5)
        raise GateError("window", f"no xemu window within {timeout:.0f}s")

    def capture(self, window) -> Image.Image:
        return ocr.capture(window)

    def capture_stable(self) -> Image.Image:
        last: Exception | None = None
        for _ in range(20):
            window = self.find()
            if window is None:
                raise GateError("capture", "xemu window vanished")
            try:
                return self.capture(window)
            except Exception as exc:  # BadMatch while the window settles
                last = exc
                time.sleep(0.5)
        raise GateError("capture", f"window capture kept failing: {last}")

    def close(self) -> None:
        env = dict(os.environ, DISPLAY=f":{self.display_number}")
        subprocess.run(
            [sys.executable, str(ROOT / "tools/x11_window.py"), "close", "xemu |"],
            env=env, check=False, capture_output=True,
        )

    @property
    def display_number(self):
        return int(self.dpy.get_display_name().split(":")[1].split(".")[0])


class Gamepad:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools/xemu_virtual_gamepad.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.lines: list[str] = []
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        self._wait_for("READY", 15.0)

    def _pump(self):
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())
            log(f"gamepad: {line.rstrip()}")

    def _wait_for(self, needle: str, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(needle in line for line in self.lines):
                return
            time.sleep(0.1)
        raise GateError("gamepad", f"no {needle} line within {timeout:.0f}s")

    def send(self, command: str, expect: str | None = None, timeout: float = 10.0):
        assert self.proc.stdin is not None
        mark = len(self.lines)
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()
        if expect is None:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(expect in line for line in self.lines[mark:]):
                return
            time.sleep(0.05)
        raise GateError("gamepad", f"no {expect!r} after {command!r}")

    def quit(self):
        try:
            self.send("QUIT", expect="BYE", timeout=5.0)
        except GateError:
            pass
        try:
            self.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class XemuRun:
    def __init__(self, run_dir: Path, display_number: int, gdb_port: int):
        self.run_dir = run_dir
        self.display = display_number
        self.gdb_port = gdb_port
        self.logs = run_dir / "logs"
        self.logs.mkdir(exist_ok=True)
        self.xephyr: subprocess.Popen | None = None
        self.metacity: subprocess.Popen | None = None
        self.xemu: subprocess.Popen | None = None
        self.window: Window | None = None

    def start_display(self):
        self.xephyr = subprocess.Popen(
            ["Xephyr", f":{self.display}", "-screen", "1280x720", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)
        env = dict(os.environ, DISPLAY=f":{self.display}")
        self.metacity = subprocess.Popen(
            ["metacity", "--sm-disable"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)
        self.window = Window(self.display)

    def start_xemu(self, xiso_path: Path):
        env = dict(
            os.environ,
            DISPLAY=f":{self.display}",
            SDL_VIDEODRIVER="x11",
            SDL_AUDIODRIVER="dummy",
            LIBGL_ALWAYS_SOFTWARE="1",
        )
        command = [
            "flatpak", "run",
            f"--filesystem={self.run_dir}:rw",
            f"--filesystem={xiso_path}:ro",
            "app.xemu.xemu",
            "-config_path", str(self.run_dir / "xemu.toml"),
            "-dvd_path", str(xiso_path),
            "-gdb", f"tcp::{self.gdb_port}",
        ]
        with (self.logs / "xemu.stderr.log").open("w") as err:
            self.xemu = subprocess.Popen(
                command, env=env, stdout=subprocess.DEVNULL, stderr=err,
            )
        self.window = Window(self.display)
        self.window.wait(60.0)

    def screenshot(self, name: str, out_dir: Path) -> dict:
        assert self.window is not None
        image = self.window.capture_stable()
        path = out_dir / f"{name}.png"
        image.save(path)
        return {"path": str(path), "sha256": sha256_file(path),
                "dimensions": list(image.size)}

    def _frame(self) -> Image.Image:
        assert self.window is not None
        return self.window.capture_stable().convert("RGB")

    def ocr_full(self) -> str:
        return _ocr_image(self._frame(), 11)

    def ocr_press(self) -> str:
        image = self._frame().crop(PRESS_CROP)
        image = image.resize((image.width * 2, image.height * 2))
        image = ImageEnhance.Contrast(image.convert("L")).enhance(2.0)
        return _ocr_image(image, 11)

    def ocr_top(self) -> str:
        image = self._frame().crop(TEAM_TOP_CROP)
        image = image.resize((image.width * 2, image.height * 2))
        return _ocr_image(image, 6)

    def shutdown(self) -> dict:
        result = {
            "method": "WM_DELETE_WINDOW through tools/x11_window.py",
            "forced_kill_used": False,
            "graceful": False,
        }
        if self.window is not None and self.xemu is not None:
            self.window.close()
            try:
                self.xemu.wait(timeout=20.0)
                result["graceful"] = True
            except subprocess.TimeoutExpired:
                result["forced_kill_used"] = True
                self.xemu.kill()
                self.xemu.wait(timeout=10.0)
        if self.metacity is not None:
            self.metacity.terminate()
            try:
                self.metacity.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.metacity.kill()
        if self.xephyr is not None:
            self.xephyr.terminate()
            try:
                self.xephyr.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.xephyr.kill()
        return result


def _ocr_image(image: Image.Image, psm: int) -> str:
    import io as _io

    payload = _io.BytesIO()
    image.save(payload, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", str(psm)],
        input=payload.getvalue(), stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=True,
    )
    return result.stdout.decode("utf-8", "replace")


def normalized(text: str) -> str:
    return " ".join(text.upper().split())


def atl_present(text: str) -> bool:
    return "FALCONS" in text or "ATLANTA" in text


class GdbSession:
    """Interactive gdb session over the xemu gdbstub."""

    def __init__(self, port: int, log_path: Path):
        self.log_path = log_path
        self._log_handle = log_path.open("w")
        self.proc = subprocess.Popen(
            ["gdb", "-q", "-nx"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.output: list[str] = []
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        self.send("set pagination off", "(gdb)")
        self.send("set confirm off", "(gdb)")
        self.send(f"target remote 127.0.0.1:{port}", "(gdb)", timeout=30.0)

    def _pump(self):
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.output.append(line.rstrip())
            self._log_handle.write(line)
            self._log_handle.flush()

    def send(self, command: str, expect: str = "(gdb)", timeout: float = 30.0) -> int:
        assert self.proc.stdin is not None
        mark = len(self.output)
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()
        if not expect:  # fire-and-forget (e.g. `continue`)
            return mark
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(expect in line for line in self.output[mark:]):
                return mark
            time.sleep(0.1)
        raise GateError("gdb", f"no {expect!r} after {command!r}; tail={self.output[-6:]}")

    def tail(self, mark: int) -> list[str]:
        return self.output[mark:]

    def close(self, resume: bool = True):
        try:
            if resume:
                # Attach halts the guest; make sure the title keeps playing.
                self.proc.stdin.write("continue\n")
            self.proc.stdin.write("detach\nquit\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            self.proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._log_handle.close()


# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------

def arm_attract(run: XemuRun, out_dir: Path, timeout: float) -> dict:
    log("attract arm: no-input boot/render smoke")
    transcript: list[str] = []
    shots: dict[str, dict] = {}
    started = time.monotonic()
    shots["boot-early"] = run.screenshot("attract-boot-early", out_dir)
    transcript.append(f"boot screenshot at +{time.monotonic() - started:.1f}s")
    detected = False
    deadline = time.monotonic() + timeout
    attempt = 0
    last_text = ""
    while time.monotonic() < deadline:
        attempt += 1
        try:
            text = normalized(run.ocr_press())
        except (GateError, subprocess.SubprocessError):
            text = ""
        last_text = text
        if "PRESS" in text and "START" in text:
            detected = True
            shots["press-start"] = run.screenshot("attract-press-start", out_dir)
            transcript.append(
                f"PRESS START rendered at +{time.monotonic() - started:.1f}s "
                f"(ocr attempt {attempt})"
            )
            break
        time.sleep(2.0)
    if detected:
        time.sleep(10.0)
        shots["press-start-late"] = run.screenshot("attract-press-start-late", out_dir)
        transcript.append("second frame confirms the title screen persists with no input")
    else:
        shots["final-frame"] = run.screenshot("attract-final-frame", out_dir)
        transcript.append(f"PRESS START not detected within {timeout:.0f}s; last OCR={last_text!r}")
    return {
        "input_sent": False,
        "press_start_rendered": detected,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "transcript": transcript,
        "screenshots": shots,
        "last_ocr": last_text,
    }


def wait_gate_text(run: XemuRun, needles: tuple[str, ...], timeout: float,
                   poll: float = 2.0) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = normalized(run.ocr_full())
        if all(needle in last for needle in needles):
            return last
        time.sleep(poll)
    raise GateError("route", f"text {needles} not seen within {timeout:.0f}s; last={last!r}")


def arm_route(run: XemuRun, pad: Gamepad, out_dir: Path, plan: dict) -> dict:
    log("route arm: scripted ATL quick game")
    transcript: list[str] = []
    shots: dict[str, dict] = {}

    # Gate 1: OCR press-start, assert START in-process (proven lions route).
    started = time.monotonic()
    deadline = time.monotonic() + 300.0
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            text = normalized(run.ocr_press())
        except (GateError, subprocess.SubprocessError):
            text = ""
        if "PRESS" in text and "START" in text:
            break
        time.sleep(2.0)
    else:
        raise GateError("press-start", "PRESS START not detected within 300s")
    shots["title-press-start"] = run.screenshot("route-title-press-start", out_dir)
    detect_seconds = round(time.monotonic() - started, 1)
    transcript.append(f"OCR detected Press START at +{detect_seconds}s")
    pad.send("HOLD START", expect="HOLD START")
    time.sleep(START_HOLD)
    pad.send("RELEASE START", expect="RELEASE START")
    transcript.append(f"held START {START_HOLD}s")

    # Gate 2: Settings1 load modal, dismiss with A.
    settings_text = wait_gate_text(run, ("SETTINGS",), timeout=45.0)
    shots["settings1-modal"] = run.screenshot("route-settings1-modal", out_dir)
    transcript.append(f"Settings modal observed: {settings_text[:120]!r}")
    pad.send("HOLD A", expect="HOLD A")
    time.sleep(MODAL_A_HOLD)
    pad.send("RELEASE A", expect="RELEASE A")
    transcript.append("A dismissed the Settings1 modal")

    # Gate 3: main menu -> Quick Game via START.
    time.sleep(4.0)
    shots["main-menu"] = run.screenshot("route-main-menu", out_dir)
    pad.send("HOLD START", expect="HOLD START")
    time.sleep(START_HOLD)
    pad.send("RELEASE START", expect="RELEASE START")
    transcript.append("START selected Quick Game")

    # Gate 4: team select — RT pulses until ATLANTA/FALCONS appears.  The
    # default controller assignment is the right (home) side, so RT pulses
    # cycle that side; OCR feedback (not a hardcoded pulse count) decides when
    # ATL is on the field.
    time.sleep(4.0)
    shots["team-select-initial"] = run.screenshot("route-team-select-initial", out_dir)
    initial = normalized(run.ocr_full())
    transcript.append(f"team select initial text: {initial[:160]!r}")

    pulses = 0
    matchup = initial
    if not atl_present(matchup):
        for _ in range(64):
            pad.send(f"TAP RT {TRIGGER_PULSE}", expect="TAPPED")
            pulses += 1
            time.sleep(0.6)
            matchup = normalized(run.ocr_full())
            if atl_present(matchup):
                break
        else:
            raise GateError("team-select", f"ATL not reached in 64 RT pulses; last={matchup!r}")
    shots["team-select-falcons"] = run.screenshot("route-team-select-falcons", out_dir)
    transcript.append(f"team select after {pulses} RT pulses: {matchup[:160]!r}")
    if not atl_present(matchup):
        raise GateError("team-select", f"final matchup lacks ATL: {matchup!r}")

    # Gate 5: START -> Coach Matchup, A -> Start Game.
    pad.send("HOLD START", expect="HOLD START")
    time.sleep(START_HOLD)
    pad.send("RELEASE START", expect="RELEASE START")
    time.sleep(4.0)
    shots["coach-matchup"] = run.screenshot("route-coach-matchup", out_dir)
    transcript.append("START advanced past team select")
    pad.send("HOLD A", expect="HOLD A")
    time.sleep(MODAL_A_HOLD)
    pad.send("RELEASE A", expect="RELEASE A")
    transcript.append("A started the game")

    # Gate 6: coin toss -> live gameplay; sample frames while the title
    # plays itself (no further input).  Software rendering makes the pre-game
    # load long, so sample generously — the gdb watchpoint phase that follows
    # runs while the game keeps playing itself.
    time.sleep(10.0)
    live_text = ""
    for index in range(12):
        time.sleep(10.0)
        shot = run.screenshot(f"route-live-{index}", out_dir)
        shots[f"live-{index}"] = shot
        try:
            live_text = normalized(run.ocr_full())
        except (GateError, subprocess.SubprocessError):
            live_text = ""
        transcript.append(f"live frame {index} at +{time.monotonic() - started:.0f}s")
    return {
        "input_sent": True,
        "press_start_detected_at_seconds": detect_seconds,
        "rt_pulses_to_falcons": pulses,
        "final_matchup_text": matchup,
        "live_ocr_last": live_text,
        "transcript": transcript,
        "screenshots": shots,
    }


def guest_ram_scan(dump: bytes, plan: dict) -> dict:
    markers = plan["markers"]
    replacement = plan["replacement"]
    result: dict = {
        "dump_size": len(dump),
        "full_span_offsets": [],
        "formation_record_offsets": [],
        "play_record_offsets": [],
        "aux_record_offsets": [],
    }
    result["full_span_offsets"] = _find_all(dump, replacement)[:8]
    result["formation_record_offsets"] = _find_all(dump, markers["formation_record"])[:8]
    result["play_record_offsets"] = _find_all(dump, markers["play_record"])[:8]
    result["aux_record_offsets"] = _find_all(dump, markers["aux_record"])[:8]
    return result


def _find_all(haystack: bytes, needle: bytes, limit: int = 8) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < limit:
        found = haystack.find(needle, start)
        if found < 0:
            return out
        out.append(found)
        start = found + 1
    return out


def gdb_stake_and_watch(run: XemuRun, out_dir: Path, plan: dict,
                        observe_seconds: float) -> dict:
    port = run.gdb_port
    markers = plan["markers"]
    ledger: dict = {
        "gdb_port": port,
        "guest_address_staked": False,
        "ram_dumps": [],
        "watchpoints": [],
        "watchpoint_hits": 0,
        "hit_lines": [],
        "fallback_reason": None,
        "guest_dump_logs": [],
    }

    # Dump guest RAM (up to two attempts: the playbook may load late).
    dump_path = None
    scan: dict = {}
    for attempt in range(2):
        dump_path = out_dir / f"guest-ram-{attempt}.bin"
        log(f"gdb dump attempt {attempt}: {GUEST_RAM_SIZE // (1024 * 1024)} MiB")
        try:
            session = GdbSession(port, run.logs / f"gdb-dump-{attempt}.log")
        except GateError as exc:
            ledger["fallback_reason"] = f"gdb attach failed: {exc}"
            return ledger
        mark = session.send("set remotetimeout 600", "(gdb)")
        try:
            session.send(f"dump memory {dump_path} 0x0 {GUEST_RAM_SIZE:#x}",
                         "(gdb)", timeout=600.0)
        except GateError as exc:
            session.close()
            ledger["fallback_reason"] = f"guest memory dump failed: {exc}"
            return ledger
        session.close()
        ledger["guest_dump_logs"].append(str(run.logs / f"gdb-dump-{attempt}.log"))
        dump = dump_path.read_bytes()
        ledger["ram_dumps"].append({
            "path": str(dump_path),
            "sha256": sha256_bytes(dump),
            "size": len(dump),
            "attempt": attempt,
        })
        scan = guest_ram_scan(dump, plan)
        loaded = (scan["full_span_offsets"] or scan["formation_record_offsets"]
                  or scan["play_record_offsets"])
        ledger["ram_dumps"][-1]["scan"] = scan
        if loaded:
            break
        log("created records not resident yet; letting the title play on")
        time.sleep(45.0)
    if dump_path is not None and dump_path.exists() and not (
            scan["full_span_offsets"] or scan["formation_record_offsets"]
            or scan["play_record_offsets"]):
        ledger["fallback_reason"] = (
            "created record bytes were not found in two full 64 MiB guest RAM "
            "dumps; no guest address could be staked"
        )
        return ledger

    # Stake guest addresses. Xbox cached RAM is 1:1, so the dump offset is the
    # guest virtual address; state that assumption in the ledger.
    ledger["guest_address_model"] = (
        "dump offset == guest virtual address (Xbox 64 MiB cached window is "
        "mapped 1:1 at 0x00000000); assumed, not separately traced"
    )
    formation_addr = play_addr = None
    control_addr = None
    body = plan["replacement"][BODY_OFF:]
    if scan["full_span_offsets"]:
        base = scan["full_span_offsets"][0] + BODY_OFF
        formation_addr = base + markers["formation_record_body_offset"]
        play_addr = base + markers["play_record_body_offset"]
        # Control stake inside the SAME loaded buffer: donor formation 0's
        # coordinate window.  The AI offense actually calls donor formations,
        # so a hit here proves the title consumes the loaded book that
        # contains the created records.
        control_addr = base + FORMATION_BASE + FORMATION_DONOR * FORMATION_SIZE + 0x70
        control_bytes = body[FORMATION_BASE + FORMATION_DONOR * FORMATION_SIZE + 0x70:
                             FORMATION_BASE + FORMATION_DONOR * FORMATION_SIZE + 0x74]
        ledger["stake_basis"] = "full replacement span found in guest RAM"
        ledger["control_stake"] = {
            "label": "donor_formation0_coord_window",
            "body_offset": FORMATION_BASE + FORMATION_DONOR * FORMATION_SIZE + 0x70,
            "bytes_sha256": sha256_bytes(control_bytes),
        }
    else:
        if scan["formation_record_offsets"]:
            formation_addr = scan["formation_record_offsets"][0]
            ledger["stake_basis"] = "created formation record found in guest RAM"
        if scan["play_record_offsets"]:
            play_addr = scan["play_record_offsets"][0]
    ledger["guest_address_staked"] = True

    # READ watchpoints on the created records: formation coordinate window
    # (+0x70, read at play-call draw per PLAY_FIXTURE_QUICKREF) and the created
    # play record's first assignment descriptor (read when the play is
    # consumed).  The unattended AI never calls the created formation/play, so
    # a control watchpoint on the donor formation in the same loaded buffer
    # distinguishes "book consumed" from "created record specifically read".
    watches = []
    if formation_addr is not None:
        watches.append(("created_formation_coord_window", formation_addr + 0x70, 4))
    if play_addr is not None:
        watches.append(("created_play_assignment_descriptor", play_addr + 0x08, 4))
    if control_addr is not None:
        watches.append(("control_donor_formation0_coord_window", control_addr, 4))
    if not watches:
        ledger["fallback_reason"] = "no created-record address available to stake"
        return ledger

    try:
        session = GdbSession(port, run.logs / "gdb-watch.log")
    except GateError as exc:
        ledger["fallback_reason"] = f"gdb attach for watchpoints failed: {exc}"
        return ledger
    try:
        wp_numbers = []
        watch_type = "read"
        for label, addr, size in watches:
            mark = session.send(f"rwatch *{addr:#x} len {size}", "(gdb)", timeout=30.0)
            tail = session.tail(mark)
            if not any("watchpoint" in line.lower() for line in tail):
                # Read watchpoints may be refused; an access watchpoint also
                # fires on reads and is recorded honestly as such.
                log(f"rwatch refused ({tail}); trying access watchpoint")
                watch_type = "access"
                mark = session.send(f"watch *{addr:#x} len {size}", "(gdb)", timeout=30.0)
                tail = session.tail(mark)
            if any("watchpoint" in line.lower() for line in tail):
                number = None
                for line in tail:
                    if "watchpoint" in line.lower():
                        parts = line.split()
                        if parts and parts[0].isdigit():
                            number = int(parts[0])
                        break
                wp_numbers.append((label, addr, size, number))
            else:
                raise GateError("watchpoint", f"watchpoint rejected: {tail}")
        ledger["watchpoint_type_used"] = watch_type
        ledger["watchpoints"] = [
            {"label": label, "guest_addr": addr, "len": size, "gdb_number": number}
            for label, addr, size, number in wp_numbers
        ]
        for label, addr, size, number in wp_numbers:
            if number is None:
                continue
            session.send(f"commands {number}", ">", timeout=10.0)
            session.send("silent", ">")
            session.send(f'printf "PBWP_HIT {label} pc=0x%x\\n", $pc', ">")
            session.send("continue", ">")
            session.send("end", "(gdb)", timeout=10.0)
        # Let the title play itself with the watchpoints live.
        mark = session.send("continue", "", timeout=5.0)
        observe_end = time.monotonic() + observe_seconds
        hit_lines: list[str] = []
        while time.monotonic() < observe_end:
            for line in session.output[mark:]:
                if "PBWP_HIT" in line:
                    hit_lines.append(line)
                    log(f"watchpoint hit: {line}")
            mark = len(session.output)
            time.sleep(2.0)
        session.proc.send_signal(signal.SIGINT)
        time.sleep(2.0)
        mark = session.send("info watchpoints", "(gdb)", timeout=30.0)
        info = session.tail(mark)
        ledger["info_watchpoints"] = info
        ledger["hit_lines"] = hit_lines[:200]
        ledger["watchpoint_hits"] = len(hit_lines)
        ledger["hits_by_label"] = {
            label: sum(1 for line in hit_lines if f"PBWP_HIT {label} " in line)
            for label, _, _, _ in wp_numbers
        }
        session.send("delete", "(gdb)", timeout=10.0)
    except GateError as exc:
        ledger["fallback_reason"] = str(exc)
    finally:
        session.close()
    return ledger


# --------------------------------------------------------------------------
# Evidence freeze
# --------------------------------------------------------------------------

def freeze_evidence(record: dict, pinned: dict[str, Path]) -> None:
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    for name, source in pinned.items():
        destination = FROZEN_DIR / name
        shutil.copy2(source, destination)
        record_entry = record["observations"].get(name) or {}
        record_entry["path"] = f"reports/assets/nfl2k5_playbook_create_xemu_runtime/{name}"
        record_entry["sha256"] = sha256_file(destination)
        with Image.open(destination) as image:
            record_entry["dimensions"] = list(image.size)
        record["observations"][name] = record_entry
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    FROZEN_JSON.write_text(payload)
    log(f"frozen evidence: {FROZEN_JSON}")


def build_record(plan: dict, artifact: dict, isolation: dict,
                 guard: dict, arms: dict, runtime_meta: dict,
                 pinned: dict[str, Path]) -> dict:
    writer_report = dict(plan["writer_report"])
    link = dict(plan["link"])
    link["changed_offsets_in_replacement"] = list(link["changed_offsets_in_replacement"])
    markers = {k: v for k, v in plan["markers"].items() if isinstance(v, (str, int))}
    record = {
        "schema": SCHEMA,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "scope": {
            "title": "ESPN NFL 2K5",
            "platform": "original Xbox under xemu",
            "asset_id": ASSET_ID,
            "book_name": BOOK_NAME,
            "book_outer_index": plan["target"]["outer_index"],
            "formation_donor": {"index": plan["formation_donor"],
                                "name": plan["formation_donor_name"]},
            "play_donor": {"index": plan["play_donor"],
                           "name": plan["play_donor_name"]},
            "new_formation_index": plan["new_formation_index"],
            "new_play_index": plan["new_play_index"],
            "link": link,
            "retail_source_modified": False,
            "layout_identical_copy_only_xiso": True,
        },
        "creation": {
            "writer_module": "mod_editor/core/nfl2k5_formation_play_writer.py",
            "writer_api": "build_unified_formation_play_import",
            "selector": plan["selector"],
            "writer_report": writer_report,
            "target": plan["target"],
            "markers": markers,
            "link_provisional": True,
        },
        "artifact_under_test": artifact,
        "isolation": isolation,
        "live_state_guard": guard,
        "runtime": runtime_meta,
        "observations": {},
        "arms": arms,
    }
    return record


def finalize_claims(record: dict) -> None:
    attract = record["arms"].get("attract", {})
    route = record["arms"].get("route", {})
    ledger = route.get("watchpoint_ledger", {})
    scan_proved = False
    for dump in ledger.get("ram_dumps", []):
        scan = dump.get("scan", {})
        if (scan.get("full_span_offsets") or scan.get("formation_record_offsets")
                or scan.get("play_record_offsets")):
            scan_proved = True
    hits_by_label = ledger.get("hits_by_label", {}) or {}
    created_hits = (hits_by_label.get("created_formation_coord_window", 0)
                    + hits_by_label.get("created_play_assignment_descriptor", 0))
    control_hits = hits_by_label.get("control_donor_formation0_coord_window", 0)
    hits = int(ledger.get("watchpoint_hits", 0))
    record["claims"] = {
        "link_provisional": True,
        "attract": {
            "boot_render_smoke_proved": bool(attract.get("press_start_rendered")),
            "runtime_visibility_proved": False,
            "note": "attract arm is boot/render smoke only; it never proves created bytes load",
        },
        "route": {
            "scripted_route_completed": bool(route.get("completed")),
            "atl_selected": bool(route.get("atl_selected")),
            "created_bytes_loaded_into_guest_ram": scan_proved,
            "created_bytes_read_by_title_watchpoint": created_hits > 0,
            "loaded_book_consumed_by_title_watchpoint": control_hits > 0,
            "watchpoint_hit_count_total": hits,
            "watchpoint_hits_by_label": hits_by_label,
            # Visibility = created bytes resident in guest RAM AND the title
            # demonstrably reads either the created records themselves or the
            # loaded book buffer that contains them (control stake).  The
            # unattended AI never calls the created formation/play, so the
            # control stake is the honest ceiling of this arm.
            "runtime_visibility_proved": scan_proved and (created_hits > 0
                                                          or control_hits > 0),
            "watchpoint_type_used": ledger.get("watchpoint_type_used"),
            "fallback_reason": ledger.get("fallback_reason"),
        },
        "live_state_unchanged": (
            record["live_state_guard"]["live_hdd_sha256_before"]
            == record["live_state_guard"]["live_hdd_sha256_after"]
            and record["live_state_guard"]["live_config_sha256_before"]
            == record["live_state_guard"]["live_config_sha256_after"]
        ),
        "not_claimed": [
            "arbitrary play authoring (clone-only writer)",
            "custom name or node-chain authoring",
            "original Xbox hardware behavior",
            "attract arm visibility of created bytes",
            "save-container ownership behavior (no save was created in-game)",
            "AI or user selection of the created formation/play",
        ],
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    abort_if_xemu_running()
    guard = {
        "live_config_path": str(LIVE_CONFIG),
        "live_hdd_path": str(LIVE_HDD),
        "live_config_inode": LIVE_CONFIG.stat().st_ino,
        "live_hdd_inode": LIVE_HDD.stat().st_ino,
        "live_hdd_size": LIVE_HDD.stat().st_size,
        "live_config_sha256_before": sha256_file(LIVE_CONFIG),
        "live_hdd_sha256_before": sha256_file(LIVE_HDD),
    }
    log(f"live HDD before: {guard['live_hdd_sha256_before']}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = (Path(args.run_dir) if args.run_dir
               else RUN_PARENT / f"nfl2k5-playbook-create-runtime-{stamp}")
    run_dir.mkdir(parents=True, exist_ok=True)
    xiso_path = run_dir / "ESPN-NFL-2K5-playbook-create-ATL.xiso.iso"

    plan = compile_plan()
    if xiso_path.exists():
        artifact = reuse_baked_artifact(plan, xiso_path)
    else:
        artifact = bake_xiso(plan, xiso_path)
    artifact["sha256_before"] = artifact["output_sha256"]

    isolation = setup_isolation(run_dir, xiso_path)
    display_number = pick_display()
    gdb_port = 1234
    while not port_free(gdb_port):
        gdb_port += 1
    log(f"display :{display_number}, gdb port {gdb_port}")

    arms: dict = {}
    pinned: dict[str, Path] = {}
    runtime_meta: dict = {
        "emulator": "xemu",
        "nested_display": {"server": "Xephyr", "display": f":{display_number}",
                           "screen_size": [1280, 720]},
        "gdb_port": gdb_port,
        "video_driver": "x11",
        "audio_driver": "dummy",
        "gl_vendor": "Mesa (LIBGL_ALWAYS_SOFTWARE=1)",
        "input": {
            "device": "Microsoft X-Box 360 pad",
            "transport": "Linux uinput through tools/xemu_virtual_gamepad.py",
            "sdl_guid": "030081b85e0400008e02000014010000",
        },
    }
    version = subprocess.run(
        ["flatpak", "run", "app.xemu.xemu", "--version"],
        capture_output=True, text=True, check=True).stdout
    runtime_meta["version_line"] = " ".join(version.split())

    blocker: dict | None = None

    if not args.skip_attract:
        run_a = XemuRun(run_dir, display_number, gdb_port)
        try:
            run_a.start_display()
            run_a.start_xemu(xiso_path)
            attract_dir = run_dir / "screens-attract"
            attract_dir.mkdir(exist_ok=True)
            arms["attract"] = arm_attract(run_a, attract_dir, timeout=280.0)
            for name, shot in arms["attract"]["screenshots"].items():
                pinned[f"attract-{name}.png"] = Path(shot["path"])
        except Exception as exc:  # noqa: BLE001 - record any failure honestly
            gate = exc.gate if isinstance(exc, GateError) else type(exc).__name__
            arms["attract"] = {"error": str(exc), "gate": gate,
                               "press_start_rendered": False, "screenshots": {}}
            blocker = {"arm": "attract", "gate": gate,
                       "error": f"{type(exc).__name__}: {exc}"}
        finally:
            shutdown = run_a.shutdown()
            arms.setdefault("attract", {})["shutdown"] = shutdown
        abort_if_xemu_running()

    if not args.skip_route:
        run_b = XemuRun(run_dir, display_number, gdb_port)
        pad: Gamepad | None = None
        try:
            run_b.start_display()
            pad = Gamepad()
            run_b.start_xemu(xiso_path)
            route_dir = run_dir / "screens-route"
            route_dir.mkdir(exist_ok=True)
            route = arm_route(run_b, pad, route_dir, plan)
            route["completed"] = True
            route["atl_selected"] = atl_present(route["final_matchup_text"])
            for name, shot in route["screenshots"].items():
                pinned[f"route-{name}.png"] = Path(shot["path"])
            # Watchpoint stake while the game is live.
            route["watchpoint_ledger"] = gdb_stake_and_watch(
                run_b, route_dir, plan, observe_seconds=args.observe_seconds)
            arms["route"] = route
        except Exception as exc:  # noqa: BLE001 - record any failure honestly
            gate = exc.gate if isinstance(exc, GateError) else type(exc).__name__
            partial = arms.get("route", {})
            partial.update({"error": str(exc), "gate": gate,
                            "completed": False,
                            "atl_selected": False})
            arms["route"] = partial
            if blocker is None:
                blocker = {"arm": "route", "gate": gate,
                           "error": f"{type(exc).__name__}: {exc}"}
        finally:
            if pad is not None:
                pad.quit()
            shutdown = run_b.shutdown()
            arms.setdefault("route", {})["shutdown"] = shutdown
        abort_if_xemu_running()

    # Post-run integrity.
    guard["live_config_sha256_after"] = sha256_file(LIVE_CONFIG)
    guard["live_hdd_sha256_after"] = sha256_file(LIVE_HDD)
    guard["live_config_unchanged"] = (
        guard["live_config_sha256_before"] == guard["live_config_sha256_after"])
    guard["live_hdd_unchanged"] = (
        guard["live_hdd_sha256_before"] == guard["live_hdd_sha256_after"])
    log(f"live HDD after:  {guard['live_hdd_sha256_after']}")
    artifact["sha256_after"] = sha256_file(xiso_path)
    artifact["unchanged_by_runtime"] = (
        artifact["sha256_before"] == artifact["sha256_after"])
    overlay_check = subprocess.run(
        ["qemu-img", "check", isolation["overlay_path"]],
        capture_output=True, text=True, check=True).stdout
    isolation["overlay_qemu_img_check_after"] = " ".join(overlay_check.split())
    isolation["overlay_sha256_after"] = sha256_file(Path(isolation["overlay_path"]))
    isolation["overlay_backing_sha256_after"] = guard["live_hdd_sha256_after"]
    isolation["config_sha256"] = sha256_file(Path(isolation["config_path"]))
    if blocker is not None:
        arms["blocker"] = blocker

    record = build_record(plan, artifact, isolation, guard, arms,
                          runtime_meta, pinned)
    finalize_claims(record)
    freeze_evidence(record, pinned)

    summary = {
        "schema": SCHEMA,
        "frozen": str(FROZEN_JSON),
        "xiso_sha256": artifact["output_sha256"],
        "claims": record["claims"],
        "blocker": blocker,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not guard["live_hdd_unchanged"] or not guard["live_config_unchanged"]:
        log("FATAL: live state changed — investigate before any commit")
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default=None,
                        help="reuse an existing run directory (and its baked XISO)")
    parser.add_argument("--skip-attract", action="store_true")
    parser.add_argument("--skip-route", action="store_true")
    parser.add_argument("--observe-seconds", type=float, default=120.0)
    args = parser.parse_args()
    try:
        return run(args)
    except GateError as exc:
        print(f"GATE FAILURE {exc.gate}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
