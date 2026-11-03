"""Freeze capture (b780 n4): read where a frozen game stopped through xemu's debugger port; opt in only.

Smuzz's freezes ("the game freezes at this exact screen and commentators repeat lines") could not be reproduced on the
released disc. The next one should arrive as an address, not a sentence. These tests run the capture against a fake
GDB stub (no xemu), and check that the Studio's xemu launch gets ``-gdb`` only when the player turned capture on."""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from mod_editor.core import nfl2k5_freeze_capture as fc  # noqa: E402


class FakeStub(threading.Thread):
    """A tiny GDB remote stub: answers ?, g, m, c, D and the 0x03 interrupt from a memory map."""

    def __init__(self, memory: dict[int, bytes], eips: list[int], esp: int):
        super().__init__(daemon=True)
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.memory, self.eips, self.esp = memory, eips, esp
        self.index = 0
        self.log: list[str] = []
        self.detached = False

    def read(self, address: int, size: int) -> bytes | None:
        for base, blob in self.memory.items():
            if base <= address and address + size <= base + len(blob):
                return blob[address - base:address - base + size]
        return None

    def reply(self, conn, body: str) -> None:
        data = body.encode("latin1")
        conn.sendall(b"$" + data + b"#" + f"{sum(data) & 0xFF:02x}".encode())

    def registers(self) -> str:
        eip = self.eips[min(self.index, len(self.eips) - 1)]
        regs = [0x11, 0x22, 0x33, 0x44, self.esp, 0x66, 0x77, 0x88, eip, 0x202] + [0] * 6
        return struct.pack("<16I", *regs).hex()

    def run(self) -> None:
        conn, _ = self.server.accept()
        self.server.close()
        buffer = b""
        with conn:
            while True:
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    return
                if not chunk:
                    return
                buffer += chunk
                while buffer:
                    if buffer[:1] in (b"+", b"-"):
                        buffer = buffer[1:]
                        continue
                    if buffer[:1] == b"\x03":
                        buffer = buffer[1:]
                        self.index += 1
                        self.log.append("interrupt")
                        self.reply(conn, "S02")
                        continue
                    start = buffer.find(b"$")
                    end = buffer.find(b"#", start)
                    if start < 0 or end < 0 or len(buffer) < end + 3:
                        break
                    body = buffer[start + 1:end].decode("latin1")
                    buffer = buffer[end + 3:]
                    conn.sendall(b"+")
                    self.log.append(body[:1])
                    if body == "?":
                        self.reply(conn, "S05")
                    elif body == "g":
                        self.reply(conn, self.registers())
                    elif body.startswith("m"):
                        address, size = (int(x, 16) for x in body[1:].split(","))
                        data = self.read(address, size)
                        self.reply(conn, data.hex() if data is not None else "E14")
                    elif body == "c":
                        pass
                    elif body == "D":
                        self.detached = True
                        self.reply(conn, "OK")
                        return
                    else:
                        self.reply(conn, "")


def game_memory(stack_values: list[int]) -> tuple[dict[int, bytes], int]:
    block = bytearray(0x80)
    struct.pack_into("<II", block, 0, fc.HOME_TEAM, fc.AWAY_TEAM)
    struct.pack_into("<IIII", block, 0x34, 4, 11, 5, 0)
    struct.pack_into("<I", block, 0x44, 1)
    struct.pack_into("<I", block, 0x6C, 0xB28080)
    situation = bytearray(0x10)
    struct.pack_into("<I", situation, 4, 3)
    esp = 0xD0001000
    stack = bytearray(0x200)
    for i, value in enumerate(stack_values):
        struct.pack_into("<I", stack, 8 + 4 * i, value)
    code = bytearray(0x100)
    code[0x80 - 5] = 0xE8          # a call rel32 that ends at 0x20B880
    memory = {fc.PLAY_BLOCK: bytes(block), 0xB28080: bytes(situation), esp: bytes(stack),
              fc.PLAY_COUNTER: struct.pack("<I", 7), fc.GAME_MODE: struct.pack("<I", 4),
              fc.PLAYCALL_OPTION: struct.pack("<I", 0), 0x20B800: bytes(code)}
    return memory, esp


class CaptureTests(unittest.TestCase):
    def capture(self, eips, stack_values):
        memory, esp = game_memory(stack_values)
        stub = FakeStub(memory, eips, esp)
        stub.start()
        result = fc.capture("127.0.0.1", stub.port, samples=4, interval=0.0, timeout=5.0)
        stub.join(5)
        return result, stub

    def test_the_report_names_the_play_state_and_the_calls(self):
        result, stub = self.capture([0x20B860, 0x20B864, 0x20B860, 0x20B868, 0x20B860], [0x1234, 0x20B880, 0x80001000])
        self.assertTrue(stub.detached, "the capture must let the game run on (detach)")
        self.assertEqual(len(result["eip_samples"]), 4)
        state = result["game_state"]
        self.assertEqual((state["offense"], state["defense"]), ("home", "away"))
        self.assertEqual((state["phase"], state["play_state"], state["down"], state["play_count"]), (4, 11, 3, 7))
        self.assertEqual(state["game_mode_name"], "Play Now")
        self.assertEqual(state["play_calling"], "By Package")
        self.assertEqual([r["address"] for r in result["return_addresses"]], ["0x20b880"])
        self.assertIn("small loop", result["verdict"])
        text = fc.report_text(result)
        self.assertIn("Offense: home  Defense: away", text)
        self.assertNotIn("—", text)

    def test_a_kernel_stop_is_called_a_crash_stop(self):
        result, _stub = self.capture([0x800151EF] * 6, [0x20B880])
        self.assertIn("crash stop", result["verdict"])

    def test_nothing_listening_says_how_to_start_xemu(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with self.assertRaisesRegex(fc.CaptureError, "-gdb tcp:127.0.0.1"):
            fc.capture("127.0.0.1", port, timeout=1.0)

    def test_the_report_file_is_plain_text_in_the_chosen_folder(self):
        result, _stub = self.capture([0x20B860] * 5, [])
        with tempfile.TemporaryDirectory() as folder:
            path = fc.write_report(result, Path(folder))
            self.assertTrue(path.name.startswith("2k5-freeze-capture-") and path.suffix == ".txt")
            self.assertIn("Raw data:", path.read_text(encoding="utf-8"))


class OptInTests(unittest.TestCase):
    def test_off_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(fc.launch_port(Path(folder) / "none.json", environ={}))

    def test_the_setting_and_the_environment_turn_it_on(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "freeze-capture.json"
            fc.set_enabled(4321, settings)
            self.assertEqual(fc.launch_port(settings, environ={}), 4321)
            fc.set_enabled(None, settings)
            self.assertIsNone(fc.launch_port(settings, environ={}))
            self.assertEqual(fc.launch_port(settings, environ={fc.ENV: "5555"}), 5555)
            self.assertIsNone(fc.launch_port(settings, environ={fc.ENV: "80"}))
            settings.write_text(json.dumps({"schema": "other", "enabled": True, "port": 1234}), encoding="utf-8")
            self.assertIsNone(fc.launch_port(settings, environ={}))

    def test_the_debug_option_listens_on_this_computer_only(self):
        argv = ("flatpak", "run", "--filesystem=/x:ro", "app.xemu.xemu", "-dvd_path", "/x/d.iso")
        out = fc.with_debug_port(argv, 1234)
        self.assertEqual(out[:len(argv)], argv)
        self.assertEqual(out[len(argv):], ("-gdb", "tcp:127.0.0.1:1234"))
        self.assertEqual(fc.with_debug_port(out, 999), out)


class StudioLaunchTests(unittest.TestCase):
    def launch(self, environ: dict[str, str], enabled_port: int | None):
        from mod_editor.studio import facade as studio_facade
        with tempfile.TemporaryDirectory() as folder:
            xiso = Path(folder) / "modded.xiso.iso"
            xiso.write_bytes(b"disc")
            settings = Path(folder) / "freeze-capture.json"
            if enabled_port:
                fc.set_enabled(enabled_port, settings)
            launcher = mock.Mock()
            host = SimpleNamespace(xemu_command=("xemu",), _lock=threading.Lock(),
                                   _last_build=SimpleNamespace(output_xiso=xiso), _process_launcher=launcher)
            xs = "mod_editor.studio.xemu_settings."
            with mock.patch.object(fc, "SETTINGS", settings), mock.patch.dict(os.environ, environ, clear=False), \
                    mock.patch(xs + "config_path", return_value=Path(folder) / "xemu.toml"), \
                    mock.patch(xs + "play_warning", return_value=""), \
                    mock.patch(xs + "grant_build_folder", return_value=""), \
                    mock.patch(xs + "remember_disc", return_value=None), \
                    mock.patch(xs + "disc_help", return_value="disc"), \
                    mock.patch.object(studio_facade, "_validate_xemu_executable", lambda *a, **k: None):
                if fc.ENV not in environ:
                    os.environ.pop(fc.ENV, None)
                studio_facade.Nfl2k5StudioFacade.launch_xemu(host, lambda *a: None)
            return launcher.call_args[0][0]

    def test_a_normal_launch_never_gets_the_debug_port(self):
        argv = self.launch({}, None)
        self.assertNotIn("-gdb", argv)

    def test_a_launch_with_capture_on_gets_it(self):
        argv = self.launch({}, 2345)
        self.assertEqual(argv[-2:], ("-gdb", "tcp:127.0.0.1:2345"))
        argv = self.launch({fc.ENV: "3456"}, None)
        self.assertEqual(argv[-2:], ("-gdb", "tcp:127.0.0.1:3456"))


if __name__ == "__main__":
    unittest.main()
