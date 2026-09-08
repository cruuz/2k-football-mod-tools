"""Native CPU play choice with a complete retail PLAY resource.

Actors, transforms and the ball are synthetic scene inputs. Native match,
personnel, role, task, play choice and assignment functions execute unchanged.
This fixture does not yet provide a complete animation/physics scene or prove
that a drive snaps and finishes. The additional substituted function is the
sideline coach placement leaf, since there are no coach actors in this scene.
"""
from collections import Counter
import hashlib
import struct
import unittest

from tests.nfl2k5_my_career_played_fixture import Machine as PlayedMachine
from tests.nfl2k5_my_career_fixture import XBE


def retail_playbook():
    from mod_editor.core import nfl2k5_roster_records as roster
    if not (XBE.parent / "vc_53450030/0").is_file():
        raise unittest.SkipTest("private USA PLAY archive is absent")
    with roster._outer_image()(XBE.parent) as archive:
        if len(archive.entries) <= 308 or archive.entries[308].size != 78768:
            raise unittest.SkipTest("fixed 78,768-byte ATL PLAY evidence differs")
        resource = archive.read_entry(308)
    if hashlib.sha256(resource).hexdigest() != "7963263b71c0a7a2de4798afa8053b59647f6773c2cf76b6f902288217bd62d5":
        raise unittest.SkipTest("USA ATL PLAY evidence pin differs")
    return resource


class Machine(PlayedMachine):
    ACTORS = 0x2A40000

    def cpu_scene(self, resource):
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
        parse_playbook_resource(resource, outer_index=308)
        self.launch()
        self.match_player = self.get(self.state + 2564)
        if not self.match_player:
            raise AssertionError("CPU trial must be the actual career fixture")
        career_side = 0xE5FC20 if self.match_player < 0xB321A0 else 0xE5FC60
        self.offense = 0xE5FC60 if career_side == 0xE5FC20 else 0xE5FC20
        self.defense = career_side
        for va in (0xAF290, 0x136DB0, 0x1D30A0, 0x1F1D70, 0x164000, 0x161460):
            self.call(va, budget=20000000)
        for team, depth, settings in ((0x61C50, 0x61C70, 0xE6019C),
                                      (0x61C60, 0x61C80, 0xE601AC)):
            self.call(0xE80D0, ecx=self.call(team), edx=self.call(depth),
                      args=(self.get(settings), 0), budget=2000000)
        self.uc.mem_write(self.OUT, resource[32:])
        for side in (0, 1):
            self.call(0x161E30, ecx=self.OUT, edx=side, budget=500000)
        self.call(0x777E0, ecx=0xB75A40)
        self.call(0x77800, ecx=0xB88DD0)
        # The resource loader copies and fixes up each complete book. No
        # individual opcode or null role pointer is replaced by the harness.
        self.actors = [self.ACTORS + i * 0x4000 for i in range(22)]
        for i, body in enumerate(self.actors):
            base = 0xB30C4C if i < 11 else 0xB321A0
            for off, value in ((0x3C, base + 84 * (i % 11)),
                               (0x30, self.actors[i+1] if i < 21 else 0),
                               (0x18, body + 0xB00), (0x24, body + 0x1000),
                               (4, body + 0x1800)):
                self.put(body + off, value)
            self.uc.mem_write(body + 0x2C, bytes((i % 11, 0, i % 11, i)))
            self.uc.mem_write(body + 0xB00, struct.pack('<4f', 0, 0, 0, 1) * 4)
        self.put(0xE60268, self.actors[0])
        self.call(0x87160, ecx=11, edx=11)
        self.call(0x1561C0, args=(0,))
        # Execute the whole actor phase-state constructor prefix, including
        # its native spare-script pointer. Animation table constructors after
        # 1DF8B8 remain outside this bounded scene fixture.
        self.call(0x1DF860, stop=0x1DF8B8, budget=1000000)
        # The scene seam omits match-settings import. Supply the retail
        # five-minute-quarter input before native clock construction, so
        # later period transitions restore a real duration through 55DD0.
        self.put(0xE6000C, 5)
        for va in (0x218090, 0x214A90, 0x55DD0, 0x1F1D70, 0xA7860,
                   0x188870, 0xF7B30, 0xB15E0):
            self.call(va, budget=20000000)
        self.call(0xE9460, ecx=self.offense,
                  edx=1 if self.offense == 0xE5FC20 else -1)
        self.call(0x48BE0, ecx=0xE5FCA0, edx=12345)
        self.put(0xE602B4, 4)
        self.put(0xE602B8, 11)
        self.put(0xE60280, self.offense)
        self.put(0xE60284, self.defense)
        self.put(0xE5FC00, self.BODIES + 0x18000)
        self.put(self.BODIES + 0x18014, self.BODIES + 0x18100)
        self.replace_stub(0x2CD170, lambda: self.ret())  # coach placement only
        self.cpu_visits, self.phases = Counter(), []
        for va in (0x20B670, 0x20B820, 0x1A8E60, 0x18AD10):
            self.stubs.append(self.uc.hook_add(
                self.u.UC_HOOK_CODE, lambda *_args, address=va: self.cpu_visits.update([address]),
                begin=va, end=va))
        self.stubs.append(self.uc.hook_add(
            self.u.UC_HOOK_CODE, lambda *_: self.phases.append(self.reg("ECX")),
            begin=0x89260, end=0x89260))

    def cpu_choice(self):
        self.call(0xA11F0, budget=20000000)
        self.call(0x20B820, ecx=self.defense, edx=0, args=(0,), budget=20000000)
        return {
            "unit_present": self.call("mode_unit_present"),
            "offense_human": self.call(0x1891B0, ecx=self.offense),
            "defense_human": self.call(0x1891B0, ecx=self.defense),
            "visits": dict(self.cpu_visits), "phases": self.phases.copy(),
            "phase": self.get(0xE602B8),
            "chosen_flags": [self.get(self.get(t + 12) + 36)
                             for t in (self.offense, self.defense)],
        }
