"""Execute the catch-slider cave under unicorn on the real (patched) executable.

Maps the patched retail ``default.xbe`` at its image base, replaces the game's ``rand``
(``FUN_00048b90``) with a stub that loads a chosen float, fills the per-side factor table
(``0xAAB8C0``, read through the game's own ``FUN_0017b8f0``) and the Interception slider, builds
a fake catcher and team, enters the cave exactly as the hook does (``call`` with ebx = catcher) and
checks the float the cave leaves in st0.  Skipped when unicorn or the private retail XBE is absent.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_catch_slider as cs  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402

try:
    from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
    from unicorn.x86_const import UC_X86_REG_EBX, UC_X86_REG_EIP, UC_X86_REG_ESP
except ImportError:  # pragma: no cover - optional dependency
    Uc = None  # type: ignore[assignment]

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
IMAGE_BASE = 0x10000
SCRATCH = 0x00F00000
RAND_FLOAT = SCRATCH
RESULT_FLOAT = SCRATCH + 4
SENTINEL = SCRATCH + 0x100
STACK_TOP = SCRATCH + 0x18000
TEAM_A, TEAM_B, PLAYER = SCRATCH + 0x20000, SCRATCH + 0x20100, SCRATCH + 0x20200


def _load(payload: bytes) -> "Uc":
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    header_size = struct.unpack_from("<I", payload, 0x108)[0]
    uc.mem_map(IMAGE_BASE, ((header_size + 0xFFF) // 0x1000) * 0x1000)
    uc.mem_write(IMAGE_BASE, payload[:header_size])
    for section in _sections(payload):
        if not section.raw_size:
            continue
        start = section.virtual_address & ~0xFFF
        end = (section.virtual_address + section.raw_size + 0xFFF) & ~0xFFF
        for page in range(start, end, 0x1000):
            try:
                uc.mem_map(page, 0x1000)
            except Exception:  # noqa: BLE001 - shared page with the previous section
                pass
        uc.mem_write(section.virtual_address, payload[section.raw_offset: section.raw_offset + section.raw_size])
    uc.mem_map(SCRATCH, 0x40000)
    return uc


def _run(payload: bytes, rand: float, *, human_catching: float, cpu_catching: float, interception: float,
         catcher_on_offense: bool, offense_is_human: bool) -> tuple[float, list[int]]:
    uc = _load(payload)
    uc.mem_write(cs.RAND_FN, b"\xd9\x05" + struct.pack("<I", RAND_FLOAT) + b"\xc3")      # fld dword [RAND]; ret
    uc.mem_write(RAND_FLOAT, struct.pack("<f", rand))
    uc.mem_write(SENTINEL, b"\xd9\x1d" + struct.pack("<I", RESULT_FLOAT) + b"\xf4")     # fstp dword [RESULT]; hlt
    uc.mem_write(0xAAB8C0 + 4 * 4, struct.pack("<f", cpu_catching))        # side 0 (CPU), index 4 = Catching
    uc.mem_write(0xAAB8C0 + 14 * 4, struct.pack("<f", human_catching))     # side 1 (Human)
    uc.mem_write(cs.INT_SLIDER_GLOBAL, struct.pack("<f", interception))
    uc.mem_write(TEAM_A + 0x30, struct.pack("<I", 0x00F30000 if offense_is_human else 0))
    uc.mem_write(TEAM_B + 0x30, struct.pack("<I", 0))
    uc.mem_write(cs.OFFENSE_TEAM_GLOBAL, struct.pack("<I", TEAM_A))
    uc.mem_write(PLAYER + 0x38, struct.pack("<I", TEAM_A if catcher_on_offense else TEAM_B))
    uc.reg_write(UC_X86_REG_EBX, PLAYER)
    esp = STACK_TOP - 0x100
    uc.mem_write(esp, struct.pack("<I", SENTINEL))
    uc.reg_write(UC_X86_REG_ESP, esp)
    trace: list[int] = []
    uc.hook_add(UC_HOOK_CODE, lambda _u, address, _size, _d: trace.append(address))
    uc.emu_start(cs.CAVE_VA, SENTINEL + 7, timeout=2_000_000, count=200)
    assert uc.reg_read(UC_X86_REG_EIP) in (SENTINEL + 6, SENTINEL + 7), [hex(a) for a in trace[-8:]]
    return struct.unpack("<f", uc.mem_read(RESULT_FLOAT, 4))[0], trace


@unittest.skipUnless(Uc is not None and RETAIL_XBE.exists(), "unicorn or the private retail XBE is absent")
class CatchCaveEmulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = RETAIL_XBE.read_bytes()
        cls.patched, _receipt = cs.apply(payload)

    def test_offense_catcher_uses_its_side_and_never_drops_below_retail(self) -> None:
        for rand in (0.05, 0.5, 0.99):
            for slider in (0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
                for human in (True, False):
                    got, trace = _run(self.patched, rand, human_catching=slider if human else 9.0,
                                      cpu_catching=slider if not human else 9.0, interception=0.5,
                                      catcher_on_offense=True, offense_is_human=human)
                    expected = min(rand, rand / (2 * slider)) if slider > 0 else rand
                    self.assertAlmostEqual(got, expected, places=6, msg=(rand, slider, human))
                    self.assertIn(cs.FACTOR_FN, trace, "the game's own ReadFactor must be called")
                    self.assertEqual(trace[0], cs.CAVE_VA)
        # the Pro defaults: the human side gets x1.5 odds, the CPU side stays retail
        human, _ = _run(self.patched, 0.6, human_catching=0.75, cpu_catching=0.25, interception=0.5,
                        catcher_on_offense=True, offense_is_human=True)
        cpu, _ = _run(self.patched, 0.6, human_catching=0.75, cpu_catching=0.25, interception=0.5,
                      catcher_on_offense=True, offense_is_human=False)
        self.assertAlmostEqual(human, 0.6 / 1.5, places=6)
        self.assertAlmostEqual(cpu, 0.6, places=6)

    def test_defender_uses_the_interception_slider_over_its_full_range(self) -> None:
        for rand in (0.05, 0.5, 0.99):
            for slider, expected in ((0.0, float("inf")), (0.25, rand * 2), (0.5, rand), (1.0, rand / 2)):
                got, trace = _run(self.patched, rand, human_catching=9.0, cpu_catching=9.0, interception=slider,
                                  catcher_on_offense=False, offense_is_human=True)
                if expected == float("inf"):
                    self.assertEqual(got, float("inf"))
                else:
                    self.assertAlmostEqual(got, expected, places=6, msg=(rand, slider))
                self.assertNotIn(cs.FACTOR_FN, trace)

    def test_odds_multiplier_matches_the_cave(self) -> None:
        for slider in (0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
            got, _ = _run(self.patched, 0.4, human_catching=slider, cpu_catching=9.0, interception=0.5,
                          catcher_on_offense=True, offense_is_human=True)
            self.assertAlmostEqual(0.4 / got, cs.odds_multiplier(slider), places=5)


if __name__ == "__main__":
    unittest.main()
