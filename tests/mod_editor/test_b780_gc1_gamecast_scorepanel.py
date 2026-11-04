"""b780 gc1: the franchise Gamecast's score panel draws again under the 2026 scorebug.

Report (#2k5-bugs, 2026-11-03): the franchise Gamecast (a simulated game) showed no score or time. Cause: beta 76 sb
B1 turned 0x8C450 off (0x8C465 je -> jmp) as a second "retail play-call bar" draw. It is not one. Its only caller is
0xEC555 inside 0xEC550, the draw event of the visualsimulatormenu menu, and it fills the franchise IFF's "scorepanel"
(teams, scores, quarter, clock, down and distance, ball spot) from the simulator's own state. The released v0.8 and
the beta-80 v0.9 RC both carry the jump. The fix leaves 0x8C450 retail in every build and moves the sprite engine's
play-call guard to the jump that remains (0x8CA18, the in-game play-call bar 0x8CA00).

Proof level: offline. The ownership is read from the retail executable; 0x8C450 itself runs natively under Unicorn on
the owner's applied executable. The simulator state it reads and the MRKS/render boundary it calls are explicit
fixtures. Nothing here is an in-game capture.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/mod_editor")]
from mod_editor.core import nfl2k5_scorebug_runtime as owner  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite_code as engine  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from test_nfl2k5_franchise_records import XBE, _retail  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
PANEL_DRAW, PANEL_DRAW_END, PANEL_GATE, PANEL_EXIT = 0x8C450, 0x8C988, 0x8C465, 0x8C982
PLAYCALL_DRAW, PLAYCALL_GATE = 0x8CA00, 0x8CA18
SIM_DRAW_EVENT, SIM_EVENT_SLOT, SIM_EVENT_TABLE, SIM_MENU = 0xEC550, 0x51C230, 0x51C3E0, 0x51C460
V08_JUMP = bytes.fromhex("e91805000090")      # what beta 76 to beta 80 wrote at 0x8C465
V08_XBE_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"   # SOFTDRINK 2K28 v0.8 default.xbe
# The eight MRKS text nodes of both "scorepanel" resources (franchise IFF outer 23 chunk 21, GAMEDATA outer 346 chunk
# 44), by the name hash 0x8C450 switches on, with the position each record carries (scene units).
NODES = {0x4858AE2A: "clock", 0x97EE8607: "quarter", 0x9488666B: "ball_spot", 0xC89ED29D: "down",
         0x265885E8: "home_score", 0x51C65718: "away_score", 0xD77D84E6: "home_team", 0x3C4A3FE5: "away_team"}


def _calls_to(image: XbeImage, target: int) -> list[int]:
    """Every E8 rel32 in .text that lands on target."""
    text = next(s for s in image.sections if s.name == ".text")
    data = image.read(text.start, text.end - text.start)
    out, i = [], data.find(b"\xe8")
    while i != -1:
        if i + 5 <= len(data) and text.start + i + 5 + struct.unpack_from("<i", data, i + 1)[0] == target:
            out.append(text.start + i)
        i = data.find(b"\xe8", i + 1)
    return out


def _words_equal_to(payload: bytes, image: XbeImage, value: int) -> list[int]:
    """Virtual addresses of every aligned or unaligned 4-byte word in a mapped section that equals value."""
    pattern, out = struct.pack("<I", value), []
    for s in image.sections:
        blob = payload[s.raw:s.raw + s.raw_size]
        i = blob.find(pattern)
        while i != -1:
            out.append(s.start + i)
            i = blob.find(pattern, i + 1)
    return out


def _utf16_at(image: XbeImage, va: int) -> str:
    raw = image.read(va, 80)
    end = next(i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0")
    return raw[:end].decode("utf-16le")


class StaticTests(unittest.TestCase):
    """Runs everywhere: what the owner writes and what its engine reads."""

    def test_the_owner_never_edits_the_gamecast_panel_draw(self):
        rows = [(va, len(new)) for va, _old, new, _label in owner.PLAYCALL_EDITS]
        rows += [(va, len(original)) for va, original in owner.hooks().values()]
        rows += [(va, len(new)) for va, _old, new, _label in owner.override_edits()]
        for va, size in rows:
            self.assertFalse(va < PANEL_DRAW_END and PANEL_DRAW < va + size, hex(va))
        self.assertEqual([va for va, *_ in owner.PLAYCALL_EDITS], [PLAYCALL_GATE])
        self.assertEqual(owner.GAMECAST_PANEL_GATE, (PANEL_GATE, bytes.fromhex("0f8417050000")))
        je_target = PANEL_GATE + 6 + struct.unpack("<i", owner.GAMECAST_PANEL_GATE[1][2:])[0]
        self.assertEqual(je_target, PANEL_EXIT)                 # the retail mode gate, kept as it is

    def test_the_engine_guard_reads_the_play_call_jump(self):
        code = engine.CODE
        # mov al, byte [0x8CA18]; cmp al, 0xE9 inside playcall_keep
        at = code.find(b"\xa0" + struct.pack("<I", PLAYCALL_GATE) + b"\x3c\xe9")
        self.assertGreaterEqual(at, engine.LABELS["playcall_keep"])
        self.assertLess(at, engine.LABELS["sprite_playcall_hide"])
        self.assertEqual(code.find(struct.pack("<I", PANEL_GATE)), -1)
        source = (ROOT / "tools/scorebug_sprite/runtime.c").read_text(encoding="utf-8")
        self.assertIn("*(volatile u8 *)0x8ca18==0xe9", source)
        self.assertNotIn("0x8c465==", source)

    def test_revision(self):
        self.assertEqual(owner.REVISION, 16)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail XBE required")
class RetailOwnershipTests(unittest.TestCase):
    """0x8C450 belongs to the franchise Gamecast (visualsimulatormenu), 0x8CA00 to in-game screens."""

    @classmethod
    def setUpClass(cls):
        cls.payload = _retail()
        if cls.payload is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.image = XbeImage(cls.payload)

    def test_the_panel_draw_has_one_caller_the_visual_simulator_draw_event(self):
        image = self.image
        self.assertEqual(_calls_to(image, PANEL_DRAW), [SIM_DRAW_EVENT + 5])
        # 0xEC550: call 0x6C080; call 0x8C450; jmp 0xEC330 (decoded, not stored)
        body = image.read(SIM_DRAW_EVENT, 15)
        self.assertEqual((body[0], body[5], body[10]), (0xE8, 0xE8, 0xE9))
        self.assertEqual(SIM_DRAW_EVENT + 10 + struct.unpack_from("<i", body, 6)[0], PANEL_DRAW)
        # The callback is stored once, in the event-8 slot of the visualsimulatormenu event table.
        self.assertEqual(_words_equal_to(self.payload, image, SIM_DRAW_EVENT), [SIM_EVENT_SLOT + 4])
        self.assertEqual(struct.unpack("<I", image.read(SIM_EVENT_SLOT, 4))[0], 1)
        table = struct.unpack("<20I", image.read(SIM_EVENT_TABLE, 80))
        self.assertIn((8, SIM_EVENT_SLOT), list(zip(table[0::2], table[1::2])))
        self.assertEqual(struct.unpack("<I", image.read(SIM_MENU + 4, 4))[0], SIM_EVENT_TABLE)
        name = struct.unpack("<I", image.read(SIM_MENU + 0x18, 4))[0]
        self.assertEqual(_utf16_at(image, name), "visualsimulatormenu")

    def test_the_panel_reads_the_simulator_and_the_play_call_bar_reads_the_live_game(self):
        image = self.image

        def targets(start, end):
            code = image.read(start, end - start)
            return {start + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
                    for i in range(len(code) - 4) if code[i] == 0xE8}
        # 0x105470 / 0x105490: mov eax, 0xA96B68 / 0xA96E80 (the simulator's two team blocks), then the box score.
        for getter, block in ((0x105470, 0xA96B68), (0x105490, 0xA96E80)):
            self.assertEqual(image.read(getter, 5), b"\xb8" + struct.pack("<I", block))
        self.assertTrue({0x105470, 0x105490} <= targets(PANEL_DRAW, PANEL_DRAW_END))
        self.assertFalse({0x105470, 0x105490} & targets(PLAYCALL_DRAW, 0x8CF46))
        self.assertEqual(_calls_to(image, PLAYCALL_DRAW), [0x54F4F, 0x646F0, 0x65092])

    def test_the_owner_leaves_the_panel_retail_and_keeps_the_play_call_bar_off(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        patched, receipt = owner.apply(self.payload)
        self.assertEqual((owner.status(patched), receipt["binding_revision"]), ("applied", 16))
        at = lambda va, n: patched[scene.layout.sbpos.va_to_off(patched, va):scene.layout.sbpos.va_to_off(patched, va) + n]
        self.assertEqual(at(PANEL_DRAW, PANEL_DRAW_END - PANEL_DRAW), self.image.read(PANEL_DRAW, PANEL_DRAW_END - PANEL_DRAW))
        self.assertEqual(at(PLAYCALL_GATE, 6), bytes.fromhex("e92205000090"))
        stale = bytearray(patched)
        off = scene.layout.sbpos.va_to_off(patched, PANEL_GATE)
        stale[off:off + 6] = V08_JUMP
        self.assertEqual(owner.status(bytes(stale)), "foreign")


class _Machine:
    """The executable mapped section by section; stubs record the calls 0x8C450 makes across its boundary."""

    HEAP, STACK, STOP = 0x6000000, 0x6200000, 0x6300000

    def __init__(self, payload: bytes):
        import unicorn as uc
        from unicorn import x86_const as x
        self.x, self.uc = x, uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({p for s in image.sections for p in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096)})
        regions: list[list[int]] = []
        for page in pages:
            if regions and regions[-1][1] == page:
                regions[-1][1] += 4096
            else:
                regions.append([page, page + 4096])
        for start, end in regions:
            self.uc.mem_map(start, end - start)
        for s in image.sections:
            self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for base, size in ((self.HEAP, 0x100000), (self.STACK, 0x10000), (self.STOP, 0x1000)):
            self.uc.mem_map(base, size)
        self.cursor, self.stubs, self.calls = self.HEAP, {}, []
        self.uc.hook_add(uc.UC_HOOK_CODE, self._code)

    def alloc(self, size: int) -> int:
        at = (self.cursor + 15) & ~15
        self.cursor = at + size
        return at

    def put(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put_float(self, va: int, value: float) -> None:
        self.uc.mem_write(va, struct.pack("<f", value))

    def text(self, value: str) -> int:
        data = (value + "\0").encode("utf-16le")
        at = self.alloc(len(data))
        self.uc.mem_write(at, data)
        return at

    def read_text(self, at: int) -> str:
        out = bytearray()
        for i in range(128):
            unit = bytes(self.uc.mem_read(at + 2 * i, 2))
            if unit == b"\0\0":
                return out.decode("utf-16le")
            out += unit
        raise AssertionError("unterminated text")

    def stub(self, va: int, fn) -> None:
        self.stubs[va] = fn

    def _code(self, u, va, _size, _data):
        fn = self.stubs.get(va)
        if fn is None:
            return
        x = self.x
        esp = u.reg_read(x.UC_X86_REG_ESP)
        result = fn(u.reg_read(x.UC_X86_REG_ECX), u.reg_read(x.UC_X86_REG_EDX))
        if result is not None:
            u.reg_write(x.UC_X86_REG_EAX, result & 0xFFFFFFFF)
        u.reg_write(x.UC_X86_REG_ESP, esp + 4)
        u.reg_write(x.UC_X86_REG_EIP, struct.unpack("<I", u.mem_read(esp, 4))[0])

    def run(self, va: int) -> None:
        sp = self.STACK + 0xF000
        self.uc.mem_write(sp, struct.pack("<I", self.STOP))
        self.uc.reg_write(self.x.UC_X86_REG_ESP, sp)
        self.uc.emu_start(va, self.STOP, count=400_000)
        if self.uc.reg_read(self.x.UC_X86_REG_EIP) != self.STOP:
            raise AssertionError("0x8C450 did not return inside its instruction budget")
        if self.uc.reg_read(self.x.UC_X86_REG_ESP) != sp + 4:
            raise AssertionError("0x8C450 left the stack unbalanced")


def draw_gamecast_panel(payload: bytes, *, final: bool = False) -> dict:
    """Run 0x8C450 on payload with the report's game: PIT 14, NYG 7, 2nd quarter, 4:27, NYG 1st & 10 at their 23."""
    m = _Machine(payload)
    m.put(0xB30864 + 0x13C, m.text("PIT"))          # 0x61C50's team context +0x13C
    m.put(0xB30A58 + 0x13C, m.text("NYG"))          # 0x61C60's team context +0x13C
    scores = {0: 14, 1: 7}                           # 0x250DD0(side): side 0 is the 0xA96B68 block
    m.stub(0x250DD0, lambda ecx, _edx: scores[ecx])
    m.put(0xE6000C, 15)                              # quarter length in minutes
    m.put_float(0xA971F8, (4 * 60 + 27) / (15 * 60.0))   # fraction of the quarter left
    m.put(0xA971F0, 1)                               # quarter index: 2nd
    m.put(0xA971E8, 0)                               # down index: 1st
    m.put_float(0xA971FC, 10.0)                      # yards to go
    m.put_float(0xA97200, 77.0)                      # yards to the goal: NYG 23
    m.put(0xA971C0, 0)
    m.put(0xA971B8, 0x12 if final else 0)           # 0x105550: the game is over
    m.put(0xB9C25C, 0)
    offense, defense = m.alloc(4), m.alloc(4)
    m.put(offense, 0xB30A58); m.put(defense, 0xB30864)
    m.put(0xA9719C, offense); m.put(0xA971A0, defense)
    handle, scene = m.alloc(64), m.alloc(64)
    nodes = []
    for name_hash in NODES:
        node = m.alloc(0x100)
        m.put(node + 0x80, name_hash)
        nodes.append(node)
    m.put(0xB641B0, handle); m.put(0xB641B4, 1)     # loaded and shown, as 0x8BF10 and 0x8BEA0 leave them
    calls, texts = m.calls, {}
    m.stub(0x2AD80, lambda ecx, _edx: calls.append(("render list", ecx)))
    m.stub(0x2AC80, lambda ecx, _edx: calls.append(("current render list", ecx)))
    m.stub(0x151530, lambda ecx, _edx: (calls.append(("scene of", ecx)), scene)[1])
    m.stub(0x2DE60, lambda ecx, _edx: calls.append(("draw scene", ecx)))
    m.stub(0x151580, lambda _ecx, _edx: len(nodes))
    m.stub(0x151570, lambda _ecx, edx: nodes[edx])

    def set_text(ecx, edx):
        texts[NODES[m.get(ecx + 0x80)]] = m.read_text(edx)
    m.stub(0x1513D0, set_text)
    m.run(PANEL_DRAW)
    return {"calls": calls, "texts": texts, "scene": scene}


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA retail XBE and Unicorn required")
class GamecastPanelDrawTests(unittest.TestCase):
    """0x8C450 natively, on the owner's applied executable and on the jump beta 76 to beta 80 shipped."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.applied, _receipt = owner.apply(retail)
        stale = bytearray(cls.applied)
        off = scene.layout.sbpos.va_to_off(cls.applied, PANEL_GATE)
        stale[off:off + 6] = V08_JUMP
        cls.stale = bytes(stale)

    def test_the_applied_build_draws_teams_scores_quarter_clock_and_down(self):
        result = draw_gamecast_panel(self.applied)
        self.assertIn(("current render list", 0xB63F00), result["calls"])         # the panel's own camera
        self.assertEqual([c for c in result["calls"] if c[0] == "draw scene"], [("draw scene", result["scene"])])
        self.assertEqual(result["texts"], {"home_team": "PIT", "away_team": "NYG", "home_score": "14",
                                           "away_score": "7", "quarter": "2nd", "clock": "4:27",
                                           "down": "1st & 10", "ball_spot": "NYG 23"})

    def test_the_end_of_the_game_reads_final(self):
        texts = draw_gamecast_panel(self.applied, final=True)["texts"]
        self.assertEqual((texts["down"], texts["quarter"], texts["clock"], texts["ball_spot"]), ("Final", "", "", ""))
        self.assertEqual((texts["home_score"], texts["away_score"]), ("14", "7"))

    def test_the_shipped_jump_drew_nothing(self):
        result = draw_gamecast_panel(self.stale)
        self.assertEqual((result["calls"], result["texts"]), ([], {}))

    def test_the_released_v08_executable_draws_nothing(self):
        path = Path(os.environ.get("NFL2K5_V08_XBE", ""))
        if not path.is_file() or path.stat().st_size > 16 * 1024 ** 2:
            self.skipTest("released v0.8 default.xbe fixture (NFL2K5_V08_XBE) not available")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != V08_XBE_SHA256:
            self.skipTest("NFL2K5_V08_XBE is not the released v0.8 executable")
        self.assertEqual(owner.status(payload), "previous")
        result = draw_gamecast_panel(payload)
        self.assertEqual((result["calls"], result["texts"]), ([], {}))


if __name__ == "__main__":
    unittest.main()
