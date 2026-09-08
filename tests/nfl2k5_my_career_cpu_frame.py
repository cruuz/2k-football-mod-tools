"""Complete frame dispatch with native career rosters and bounded scene inputs.

Retail 25/62-bone hierarchies and SKEL vectors replace the kickoff fixture's
star rig, which is degenerate for normal football hand/head aim. Initial
three-key clips and collision spheres remain synthetic. Native planners may
also select embedded retail clips. No frame phase is replaced; this is not
a complete scene loader or snap/drive acceptance.
"""
import hashlib
import struct
import unittest

from tests.nfl2k5_my_career_cpu_fixture import Machine as ChoiceMachine
from tests.nfl2k5_my_career_fixture import XBE

PHASES = (
    0xAF2C0, 0x28DFE0, 0x217C90, 0xA28C0, 0x75BD0, 0x5D830, 0x190D00,
    0x18C1F0, 0x156A80, 0x89BA0, 0xE9210, 0x214FC0, 0xF7C10, 0x1E08D0,
    0x2180D0, 0x28ECF0, 0x28CC30, 0x1CCFA0, 0x28F4F0, 0x1DFAA0,
    0x1D30F0, 0x17C2E0, 0xA7930, 0x1D1B80, 0x94AB0, 0x5DA70, 0x125BC0,
)


def retail_skeletons():
    """Read three fixed spans in outer 3, never a whole archive pack."""
    from mod_editor.core import nfl2k5_roster_records as roster
    from tools import nfl_scene_probe as probe, nfl_scne_inventory as scene
    from tools.nfl_txtr import HEADER
    if not (XBE.parent / "vc_53450030/0").is_file():
        raise unittest.SkipTest("private USA player skeleton evidence is absent")
    rows = (
        (113, 854096, 135808, b'SCNE', '2a89df4b2e83dee4c7937194e5cd885c4b3662720bf976d8440ab5c3fb423e56'),
        (114, 989936, 202240, b'SCNE', '43c95e150c72805b419e05db3cff6cacc69c56791c349caa2f0456782775893b'),
        (116, 1462576, 480, b'SKEL', 'd057905e5848bb89df1d4ec766f598ae56bc4664c9bc6bbd3bc1493b1ce7f463'),
    )
    result = []
    with roster._outer_image()(XBE.parent) as archive:
        entry = archive.entries[3]
        if entry.size != 2387424:
            raise unittest.SkipTest("USA player package span differs")
        for index, offset, stored, kind, digest in rows:
            raw = archive.read(entry.virtual_offset + offset, 32 + stored)
            fields = HEADER.unpack_from(raw)
            if fields[0] != kind or fields[1] != stored or sum(fields[2:4]) > 512 * 1024:
                raise unittest.SkipTest("fixed player skeleton resource header differs")
            record = probe.ResourceRecord(3, hex(entry.name_id), entry.size, index,
                                          offset, kind.decode(), *fields[1:6])
            body, _ = probe.decode_resource(raw, record)
            if hashlib.sha256(body).hexdigest() != digest:
                raise unittest.SkipTest("USA player skeleton resource pin differs")
            if kind == b'SKEL':
                decoded = probe.probe_skel(body, record)
                if decoded['name'] != 'skeleton' or decoded['record_count'] != 25:
                    raise AssertionError("pinned SKEL shape differs")
                result.append([r['values'] for r in decoded['records']])
                continue
            parsed, *_ = scene.parse_scene(0, record, body, {})
            shape = next(s for s in parsed['shapes']
                         if s['name'] == ('LO_res' if index == 113 else 'HI_res'))
            at = shape['record_offset']
            count = struct.unpack_from('<H', body, at + 0x50)[0]
            start = scene.resolve_relative(body, at + 0x64, len(body), 'transforms')
            if count != (25 if index == 113 else 62) or start is None or start + count * 112 > len(body):
                raise AssertionError("pinned player hierarchy differs")
            result.append([
                (scene.pointer_name(body, start + n * 112 + 0x60, len(body), 'joint')[1],
                 struct.unpack_from('<i', body, start + n * 112 + 0x64)[0],
                 struct.unpack_from('<3f', body, start + n * 112 + 0x50))
                for n in range(count)])
    return result


class Machine(ChoiceMachine):
    ASSETS = 0x2800000

    def f32(self, address, value=None):
        if value is None:
            return struct.unpack('<f', self.uc.mem_read(address, 4))[0]
        self.uc.mem_write(address, struct.pack('<f', value))

    def scene_assets(self):
        a = self.ASSETS
        low, high, vectors = retail_skeletons()
        self.uc.mem_map(a, 0x100000)
        self.put(0xB65B78, a)
        self.put(a + 4, a + 0x1000)
        self.uc.mem_write(a + 0x10, b''.join(struct.pack('<4f', *v) for v in vectors))
        high_names = [row[0] for row in high]
        # The high rig has no separate wrist nodes. Native lookup represents
        # absent names as signed -1, and 92140 skips those mappings.
        self.uc.mem_write(0xB65BFC, bytes(high_names.index(row[0])
                          if row[0] in high_names else 255 for row in low))
        # Head/hand aim references normally come from native 90570's loaded
        # scene nodes. Zero vectors are invalid for its quaternion builder.
        for address, joint in ((0xB65B80, 12), (0xB65BA0, 17), (0xB65BC0, 22)):
            _, parent, vector = low[joint]
            self.uc.mem_write(address, struct.pack('<4fII', *vector, 0, joint, parent))
        self.put(0xB65288, a + 0x2000)
        self.put(a + 0x202C, 1)
        self.put(a + 0x2030, a + 0x3000)
        for shape, hierarchy, nodes in ((a + 0x1000, low, a + 0x4000),
                                        (a + 0x3000, high, a + 0x5000)):
            self.uc.mem_write(shape + 0x50, struct.pack('<H', len(hierarchy)))
            self.put(shape + 0x64, nodes)
            for n, (_, parent, position) in enumerate(hierarchy):
                self.put(nodes + n * 0x70 + 0x64, parent)
                self.uc.mem_write(nodes + n * 0x70 + 0x50, struct.pack('<3f', *position))
        for i, body in enumerate(self.actors):
            base = a + 0x10000 + i * 0x8000
            clip, animation = base + 0x100, self.get(body + 0x14)
            self.put(animation + 0x1C4, clip)
            self.uc.mem_write(clip, struct.pack('<BBH', 25, 0, 3))
            self.put(clip + 4, 1)
            self.uc.mem_write(clip + 0xC, b'\x3c')
            self.f32(clip + 0x10, 1)
            self.f32(clip + 0x14, 2 / 60)
            for field, offset in ((0x24, 0x200), (0x28, 0x400), (0x2C, 0x420)):
                self.put(clip + field, base + offset)
            self.put(base + 0x420, -1)
            # Retail quaternions store the scalar first. Largest-component
            # index 0 encodes identity; index 3 is a half turn around Z.
            keys = [0x20080200] * 25 + [0x2008020A] * 25 + [0x20080200] * 25
            self.uc.mem_write(base + 0x200, struct.pack('<75I', *keys))
            self.uc.mem_write(base + 0x400, struct.pack('<12h',
                              0, 100, 0, 0, 200, 140, 300, 1024, 0, 100, 0, 0))
            for n, (field, offset) in enumerate(((0x58, 0), (0x5C, 0x40),
                                                (0x74, 0x80), (0x78, 0xC0))):
                channel = base + offset
                self.put(animation + field, channel)
                self.put(channel, clip)
                self.f32(channel + 8, 1)
                for ptr, delta in ((0x24, 0), (0x28, 0x100), (0x2C, 0x2A0)):
                    self.put(channel + ptr, base + 0x500 + n * 0x500 + delta)
            self.put(animation + 0x34, base + 0x1900)
            self.f32(animation + 0x2C, 0)
            self.f32(animation + 0x30, 1)
            self.uc.mem_write(base + 0x1900, struct.pack('<4f', 1, 0, 0, 0) * 25)
            self.put(animation + 4, 0x1FFFFFF)
            self.put(animation + 8, 0x1FFFFFF)
            self.put(animation + 0x1C, 1)
            # The choice fixture needs only world positions. Full matrix
            # math also requires an orthonormal initial transform basis.
            self.uc.mem_write(self.get(body + 0x18), struct.pack(
                '<12f', 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0))
            # Native motion scaling constructor also disables the unused
            # height envelope with +infinity/-infinity endpoints. Merely
            # supplying scale=1 leaves a zero-width envelope and produces NaN.
            self.call(0x1E21D0, eax=self.get(body + 0x18))
            self.put(body + 4, base + 0x2000)
            collision = self.get(body + 0x24)
            self.put(collision + 0x38, 4)
            self.put(collision, base + 0x3C00)
            self.put(collision + 4, base + 0x3C10)
            self.put(base + 0x3C00, 1)
            self.put(base + 0x3C04, base + 0x3C20)
            self.put(base + 0x3C14, base + 0x3C40)
            self.f32(base + 0x3C30, 30)
        self.call(0x17AF60, budget=2000000)
        self.call(0x17B8A0, budget=2000000)
        self.put(0xE5FFA8, 1)
        self.put(0xBA99DC, 0)
        self.put(0xB6FF64, -1)
        self.put(0xC168B0, self.actors[0])
        self.put(0xC16BD0, self.actors[0])
        # Final audio gain submissions are hardware ABI leaves, as in the
        # kickoff frame fixture. Native planners, samplers and physics run.
        for va in (0x1C3E10, 0x1C3E70, 0x1C3ED0, 0x1C3F30):
            self.replace_stub(va, lambda: self.ret(pop=4))
        self.put(0xE602C4, 1)
        self.f32(self.get(0xE6028C) + 16, 300)
        self.put(self.get(0xE602EC) + 4, 1)
        self.frame_phases = []
        for va in PHASES:
            self.stubs.append(self.uc.hook_add(
                self.u.UC_HOOK_CODE, lambda _uc, address, *_args: self.frame_phases.append(address),
                begin=va, end=va))

    def engine_frame(self, *, budget=2000000):
        self.frame_phases.clear()
        self.call(0x11A7C0, args=(0x3C888889,), budget=budget)
        if tuple(self.frame_phases) != PHASES:
            raise AssertionError("native frame did not execute every phase in order")
