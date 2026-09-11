"""Bounded installed live-engine proofs; no console, display or disc build.

Run with --output to record derived evidence, never retail bytes. Grouping
inner updates measures update/poll/present cadence, not console wall-clock speed.
"""
from pathlib import Path
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Function/dispatch spans used by the research. The executable itself
# is hash-pinned by retail_bytes(); these coordinates are NOT reservations.
SPANS = {
    "main_frame": (0x74790, 0x10f), "input_rng": (0x74730, 0x55),
    "manager_update": (0x6e6a0, 0x38), "manager_render": (0x6e6e0, 0x58),
    "outer_update": (0x64cd0, 0x1a4), "inner_update": (0x11a7c0, 0x128),
    "game_descriptor": (0x4e7ec0, 44), "game_events": (0x4e7e88, 56),
    "game_update_command": (0x4e7df8, 72), "late_modal": (0x11ef60, 0x1c8),
    "render": (0x64f80, 0x60), "player_render": (0x11a8f0, 0x2d),
    "replay_screen": (0x13610, 0x580), "highlight_screen": (0x1124e0, 0xa17),
    "skip_request": (0xa2120, 0x34d), "skip_table": (0xa2470, 0x40),
    "skip_pending": (0x89780, 0x43), "period_ready": (0xb8db0, 0xc0),
    "dialog": (0x14e070, 0x328), "present_region": (0x27ca0, 0x590),
}


def frame_probe(payload):
    """Eight identical fixed updates, grouped 1/2/4/8, with declared leaves.

    All 27 phase functions execute. Synthetic looping clips, skeletons and
    kickoff actors cannot establish a full drive, audio queue capacity or a
    console performance claim. The inherited fixture substitutes random draws.
    """
    if importlib.util.find_spec("capstone") is None:
        raise unittest.SkipTest("Capstone is absent; kickoff frame probe requires it")
    from tests.nfl2k5_kickoff_frame import FrameMachine, PHASES
    from tests.mod_editor.test_nfl2k5_dynamic_kickoff import uni
    class ProbeMachine(FrameMachine):
        def __init__(self, *args, **kwargs):
            self.boundaries = defaultdict(Counter)
            super().__init__(*args, **kwargs)

        def _hook(self, uc, address, size, data):
            if address in self.stub_pops or address in self.fpu_stubs:
                self.boundaries[self.phase][address] += 1
            super()._hook(uc, address, size, data)

    rows = []
    for group in (1, 2, 4, 8):
        m = ProbeMachine(payload)
        phase_writes = Counter()
        def observe(_uc, _access, _address, _size, _value, _data):
            # Tags follow the latest phase entry. Dispatcher stack stores
            # between phases retain that tag; this is not a purity analysis.
            phase_writes[m.phase] += 1
        handle = m.uc.hook_add(uni.UC_HOOK_MEM_WRITE, observe)
        start = time.perf_counter()
        for _ in range(8 // group):
            for _ in range(group):
                m.frame()
        seconds = time.perf_counter() - start
        m.uc.hook_del(handle)
        snapshot = m.snapshot()
        rows.append(dict(
            updates_per_group=group, updates=8, groups=8 // group,
            host_seconds=round(seconds, 6), presented_frames=0,
            state_sha256=hashlib.sha256(b"".join(snapshot[k] for k in sorted(snapshot))).hexdigest(),
            clock_seconds=m.readf(m.CLOCK + 16),
            phase_entries=[dict(va=hex(p), calls=m.visited[p], writes=phase_writes[p],
                                substituted_calls={hex(a): n for a, n in sorted(m.boundaries[p].items())})
                           for p in PHASES],
            substituted_calls={hex(p): m.calls.count(p) for p in sorted(set(m.calls))},
        ))
    return rows


def pins(payload):
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    im = XbeImage(payload)
    return {name: dict(va=hex(va), size=size,
                       sha256=hashlib.sha256(im.read(va, size)).hexdigest())
            for name, (va, size) in SPANS.items()}


def series_probe(payload, progress=None):
    """Installed eight-update scheduler, native series and animated handoff.

    The snapshot remains in memory. Identity is a scenario input selected
    from native personnel; no readiness, alignment or task is manufactured.
    Presentation calls are counted at the main-frame call site.
    """
    from tests.nfl2k5_supersim_series import Machine
    result = dict(cadence=[], handoffs=[], positions=[], renders=[])
    positions = set()
    def say(value):
        if progress:
            progress(value)

    def handoff(m, actor, scenario):
        position = m.adopt_native_player(actor)
        for _ in range(192):
            m.presented_frame()
            if not m.get(m.state + 2712):
                break
        else:
            raise AssertionError('native appearance did not settle within 1536 updates')
        m.assert_settled()
        # BD8210 is the first controller object, not a global port register.
        # A defender normally owns a later object in that native pool.
        controller=m.get(actor+0xC)
        if (m.get(m.state+2716) or m.get(m.state+2568) != actor or
                m.get(controller) != 0 or m.get(0xBE4D60) != actor):
            raise AssertionError(f'settled appearance: expected actor {actor:#x}, bound {m.get(m.state+2568):#x}, controller {controller:#x} port {m.get(controller):#x}, fast {m.get(m.state+2716)}')
        row = dict(scenario=scenario, position=position, updates=m.counts['complete_updates'],
                   frames=m.counts['presents'], phase=m.get(0xE602B8),
                   clock=m.f32(m.get(0xE60294)+16))
        result['handoffs'].append(row)
        say(row)
        return m.checkpoint()

    def selected_positions(m, checkpoint):
        # Reuse the fully animated settled lineup for every native selected
        # position. This is a boundary admission matrix, not 17 new careers.
        for actor in m.actors:
            m.restore(checkpoint)
            position = m.adopt_native_player(actor)
            m.presented_frame()
            m.assert_settled()
            if (m.get(m.state+2712) or m.counts['updates'] or m.get(m.state+2568) != actor or
                    m.get(m.get(actor+0xC)) != 0 or m.get(0xBE4D60) != actor):
                raise AssertionError('ready appearance advanced before its presented handoff')
            positions.add(position)

    with Machine(payload) as m:
        m.series_scene();m.presentation_services()
        initial = m.checkpoint()
        for group in (1,2,4,8):
            m.restore(initial)
            if group == 8:
                m.presented_frame()
            else:
                for _ in range(8//group):
                    m.call(0x74730,args=(0x3C888889,),budget=1000000)
                    m.put(m.state+2716,m.call('mode_ff_ready',ecx=m.manager))
                    for i in range(group):
                        if i:m.call(0x48B50,ecx=0xE5FCA0)
                        m.call(0x6E6A0,ecx=m.manager,args=(0x3C888889,),budget=100000000)
                        m.put(m.state+2716,m.call('mode_ff_ready',ecx=m.manager))
                    m.call(0x7488D,stop=0x74892)
            # Native match RNG and the actual evolving world/phase objects.
            state = bytes(m.uc.mem_read(0xE5FCA0,64))
            state += bytes(m.uc.mem_read(0xE60280,96))
            state += b''.join(bytes(m.uc.mem_read(m.get(a+0x18),64)) for a in m.actors)
            result['cadence'].append(dict(group=group, state_sha256=hashlib.sha256(state).hexdigest(),
                                          **dict(m.counts)))
        say(dict(cadence=result['cadence']))
        m.restore(initial)
        for frame in range(512):
            m.presented_frame()
            if frame % 32 == 0:say(dict(frame=frame+1,plays=m.get(0xE53804),phase=m.get(0xE602B8)))
            if m.get(0xE53804)>=3:break
        else:
            raise AssertionError('three native plays did not complete within 4096 updates')
        result.update(plays=m.get(0xE53804),presented_frames=m.counts['presents'],
                      transitions=m.transitions.copy(),**{k:m.counts[k] for k in ('updates','complete_updates','polls','match_rng_draws')})
        say(dict(series={k:v for k,v in result.items() if k not in ('cadence','handoffs','positions')}))
        m.restore(initial)
        cb=next(a for a in m.actors if m.uc.mem_read(m.get(a+0x3C)+0x35,1)==b'\x04')
        settled=handoff(m,cb,'scrimmage CB')
        selected_positions(m,settled)
        m.restore(initial)
        qb=next(a for a in m.actors if m.uc.mem_read(m.get(a+0x3C)+0x35,1)==b'\0')
        injured=m.get(qb+0x3C)
        injury=m.call(0x13E270,ecx=0,edx=3)
        m.call(0x136B10,eax=0,args=(qb,m.actors[-1],injury,0,0,0),budget=2000000)
        m.call(0xA0320,ecx=0,budget=2000000)
        m.call(0x189080,budget=2000000)
        for depth in (0x61C70,0x61C80):
            m.call(0xE7C50,ecx=m.call(depth),budget=2000000)
        m.cpu_choice()
        replacement=m.get(qb+0x3C)
        if replacement==injured or any(m.get(a+0x3C)==injured for a in m.actors):
            raise AssertionError('native injury did not substitute the starting QB')
        handoff(m,qb,'native injury replacement QB')
        result['substitution']=dict(injured_position=0,replacement_position=m.uc.mem_read(replacement+0x35,1)[0],
                                    native_record_changed=True)
        m.render_services()
        result['renders'].append(dict(scenario='replacement scrimmage',**m.render_frame()))
        m.assert_settled()
    with Machine(payload) as m:
        m.series_scene(kickoff=True);m.presentation_services()
        initial=m.checkpoint()
        kicker=next(a for a in m.actors if m.uc.mem_read(m.get(a+0x3C)+0x35,1)==b'\x01')
        settled=handoff(m,kicker,'native kickoff K')
        selected_positions(m,settled)
        m.restore(initial)
        # Declared fourth-down punt situation, native role/personnel picker.
        # This proves actual P membership, not a CPU go-for-it decision.
        m.put(0xE602B4,1);m.put(m.get(0xE602EC)+4,4)
        m.cpu_choice()
        punter=next(a for a in m.actors if m.uc.mem_read(m.get(a+0x3C)+0x35,1)==b'\x02')
        settled=handoff(m,punter,'native punt P')
        selected_positions(m,settled)
        m.restore(settled)
        m.render_services()
        result['renders'].append(dict(scenario='punt',**m.render_frame()))
        m.assert_settled()
    result['positions']=sorted(positions)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes
    if not HAVE_UC:
        raise unittest.SkipTest("Unicorn is absent; native live-engine probe requires it")
    payload = retail_bytes()
    from mod_editor.core import nfl2k5_my_career_mode as mode
    result = dict(schema="nfl2k5.supersim-live.v2", runtime_witnessed=False,
                  accelerated_runtime_ready=True, shipped_stage=3, shipped_updates_per_frame=8,
                  spans=pins(payload), series=series_probe(mode.apply(payload)[0],progress=print),
                  limitations=["GPU submissions counted; no rasterizer, console, display or audio device",
                               "Declared actor/model, initial clip, collision sphere and empty overlay inputs; retail skeletons and native clip tables",
                               "Native E5FCA0 match RNG; inherited general entropy service 48BC0 returns zero",
                               "Eight updates per presented frame is not measured eightfold console speed",
                               "Fixed zero-input cadence equivalence does not promise identical 1x outcomes",
                               "Toss, challenge, pause, tips and disconnect use installed normal-speed guards",
                               "Native injury input is supplied; collision injury probability is not proved"])
    args.output.write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    print("Recorded installed eight-update native series and settled appearance proofs; hardware remains unwitnessed")


if __name__ == "__main__":
    main()
