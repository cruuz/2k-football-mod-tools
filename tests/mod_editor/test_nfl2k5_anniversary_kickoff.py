"""vb3 (2026-09-23): the ESPN 25th Anniversary moments keep the retail kickoff.

Noah's recording of 2026-09-23 [v2 11:21]: "we have the new kickoff in this mode where we're playing an old game".
The owner nfl2k5_anniversary_kickoff tests game mode 8 ([0xE5FF80], stored only by the moment selection at
0x20CB59) in front of each of the four parts of the 2026 kickoff.

The native classes run the gated executable, the ungated one (kick rules + dynamic kickoff) and the retail one
under Unicorn from the same CPU state and compare what each site leaves behind:
* mode 7 (a Franchise game): every gated site reaches the same place with the same registers, flags, x87 stack
  and memory as the ungated executable, so the 2026 kickoff is unchanged outside the 25th Anniversary;
* mode 8: the 20 dynamic kickoff sites run the retail instructions (the retail executable's state), the kickoff
  spot and the touchback use the retail values, the two formation readers return the retail Kickoff and Kick Return
  positions for the 2026 records, and the play store puts the retail return chains into a 2026 return play, saves
  the 2026 ones and restores them when the play is stored outside mode 8.
E1, the kickoff return blocking rule, is a Build option (kickoff_return_blocking, off in every preset) that the
same gate carries: the classes run the gate without it (the default) and with it.
Offline evidence only; nothing here is a played game. Retail-backed classes skip without the private USA disc.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_anniversary_kickoff as gate  # noqa: E402
from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff  # noqa: E402
from mod_editor.core import nfl2k5_kick_rules as kick_rules  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

EXTRACTION = ROOT / "extracted/ESPN NFL 2K5 (USA)"
XBE = EXTRACTION / "default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
RETAIL_READY = XBE.is_file() and (EXTRACTION / "vc_53450030/0").is_file()


class ContractTests(unittest.TestCase):
    """Retail-free."""

    def test_requests_and_mode(self):
        self.assertEqual(gate.REQUESTS, ((gate.OWNER, "code", 3584, 16), (gate.OWNER, "data", 736, 16)))
        self.assertEqual((gate.MODE_VA, gate.ANNIVERSARY_MODE), (0xE5FF80, 8))
        self.assertEqual(gate.MOMENT_SELECT_MODE_STORE[1], bytes.fromhex("c70580ffe50008000000"))
        self.assertEqual(gate.DATA_SIZE, (gate.SAVE_ENTRIES * gate.SAVE_ENTRY + 15) // 16 * 16)

    def test_all_twenty_kickoff_hooks_and_seven_spot_sites_are_gated(self):
        self.assertEqual([h[0] for h in gate.kickoff_hooks()], list(kickoff.HOOKS))
        self.assertEqual(len(gate.kickoff_hooks()), 20)
        self.assertEqual(len(gate.kick_rule_sites()), 7)
        self.assertEqual(set(kick_rules.GATED_SITE_VAS),
                         {label for label, _va, _kind in gate.kick_rule_sites()} | {"touchback_hook"})

    def test_signatures_are_the_alignment_tools_2026_values(self):
        from tools import nfl2k5_kickoff_alignment as alignment
        kickoff_xz = alignment.kickoff_xz_2026()
        self.assertEqual(kickoff_xz[1][1], gate.COVERAGE_Z)
        self.assertEqual(kickoff_xz[2][1], gate.COVERAGE_Z)
        self.assertEqual(alignment.KICK_RETURN_XZ_2026[0][1], gate.RETURNER_Z)
        self.assertEqual(alignment.KICK_RETURN_XZ_2026[2][1], gate.RESTRAINING_Z)
        # The retail tables never carry the signatures (Kickoff slot 1/2 behind the ball, returners at 69 yd).
        self.assertNotEqual(alignment.RETAIL_KICKOFF_XZ[1][1], gate.COVERAGE_Z)
        self.assertNotEqual(alignment.RETAIL_KICK_RETURN_XZ[0][1], gate.RETURNER_Z)


class WiringTests(unittest.TestCase):
    """Retail-free: the owner rides with the dynamic kickoff on disc images and reserves with every union."""

    def test_requests_are_in_every_owner_union_and_the_budget(self):
        import json
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_xbe_space as space
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0] == gate.OWNER], list(gate.REQUESTS))
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(set(gate.REQUESTS) <= set(REQUESTS))
        self.assertTrue(set(gate.REQUESTS) <= set(space.dormant_union()))
        space.plan(rows)                                       # the whole documented union still fits
        self.assertEqual(tt._selected_space_requests(anniversary_kickoff=True), gate.REQUESTS)
        self.assertEqual(tt._selected_space_requests(), ())
        self.assertIn("anniversary_kickoff", tt.R62_SPACE_KEYS)
        self.assertIn("anniversary_kickoff_tables", tt.R62_RUNTIME_KEYS)

    def test_the_build_decides_it_from_the_dynamic_kickoff_on_images(self):
        from mod_editor.core import mod_build as build
        plan = build.BuildPlan(source="in.iso", target="out.iso", dynamic_kickoff=True)
        self.assertTrue(build._anniversary_kickoff_wanted(plan, True))
        self.assertFalse(build._anniversary_kickoff_wanted(plan, False))
        self.assertFalse(build._anniversary_kickoff_wanted(build.BuildPlan(source="in.iso", target="out.iso"), True))
        options = build._r62_plan_options(plan)
        self.assertIsNone(options["anniversary_kickoff"])
        self.assertIsNone(options["anniversary_kickoff_tables"])
        from mod_editor.core import nfl2k5_throw_tuning as tt
        tt._validate_r62_options(**{k: v for k, v in options.items() if k != "my_career_setup"})
        with self.assertRaises(ValueError):
            tt._validate_r62_options(anniversary_kickoff=True, anniversary_kickoff_tables=b"not tables")

    def test_the_return_blocking_rule_is_its_own_build_option_off_in_every_preset(self):
        from mod_editor.core import mod_build as build
        from mod_editor.core import nfl2k5_kickoff_blocking as blocking
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.gui import beta62_options
        self.assertFalse(build.BuildPlan(source="in.iso", target="out.iso").kickoff_return_blocking)
        for name, preset in build.PRESETS.items():
            self.assertIs(preset["kickoff_return_blocking"], False, name)
        self.assertIn("kickoff_return_blocking", tt.R62_RUNTIME_KEYS)
        self.assertIn("kickoff_return_blocking", beta62_options.KEYS)
        self.assertEqual(blocking.UI_LABEL, "Return blockers claim distinct men after the catch (test)")
        plan = build.BuildPlan(source="in.iso", target="out.iso", dynamic_kickoff=True, kickoff_return_blocking=True)
        self.assertIs(build._r62_plan_options(plan)["kickoff_return_blocking"], True)
        with self.assertRaises(ValueError):
            tt._validate_r62_options(kickoff_return_blocking=1)
        # the rule rides with the 25th Anniversary gate: without it (an .xbe build, or no dynamic kickoff) it refuses
        with self.assertRaises(ValueError):
            tt._validate_r62_options(kickoff_return_blocking=True, anniversary_kickoff=False)
        tt._validate_r62_options(kickoff_return_blocking=True)          # None: the build decides the gate later
        with self.assertRaises(ValueError):
            build._validated_r62_plan_options(build.BuildPlan(source="in.iso", target="out.iso",
                                                              kickoff_return_blocking=1))


def _ready():
    if not (HAVE_UC and RETAIL_READY):
        raise unittest.SkipTest("the private USA extraction and Unicorn are required")
    from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
    require_nfl_retail_packs(EXTRACTION)


class Machine:
    """The executable's sections, a heap, a stack and a stop page; every page read/write/execute."""

    HEAP, STACK, STOP = 0x4000000, 0x5000000, 0x5010000

    def __init__(self, payload):
        import unicorn as uc
        from unicorn import x86_const as x
        self.uc, self.x = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32), x
        image = XbeImage(payload)
        pages = sorted({page for s in image.sections for page in range(s.start & -4096, (s.end + 4095) & -4096, 4096)}
                       | {page for page in range(image.base, image.base + image.headers_size + 4095, 4096)})
        runs = []
        for page in pages:
            if runs and runs[-1][1] == page:
                runs[-1][1] += 4096
            else:
                runs.append([page, page + 4096])
        for start, end in runs:
            self.uc.mem_map(start, end - start)
        self.uc.mem_write(image.base, payload[:image.headers_size])
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, payload[s.raw:s.raw + min(s.raw_size, s.size)])
        self.uc.mem_map(self.HEAP, 0x100000)
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.cursor = self.HEAP

    def alloc(self, data, align=16):
        at = (self.cursor + align - 1) & -align
        self.uc.mem_write(at, bytes(data))
        self.cursor = at + len(data)
        return at

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def run(self, start, stops, regs, *, limit=20000):
        """Run from ``start`` until EIP reaches one of ``stops``.

        Returns (stop, registers incl. ST0, {address: final byte} of every byte the run wrote)."""
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        hit, written = [], set()

        def stop(uc, address, size, data):
            hit.append(address)
            uc.emu_stop()

        def write(uc, access, address, size, value, data):
            written.update(range(address, address + size))
        hooks = [self.uc.hook_add(UC_HOOK_CODE, stop, begin=address, end=address) for address in stops]
        hooks.append(self.uc.hook_add(UC_HOOK_MEM_WRITE, write))
        try:
            for name, value in regs.items():
                self.uc.reg_write(getattr(self.x, "UC_X86_REG_" + name.upper()), value)
            self.uc.emu_start(start, self.STOP, count=limit)
        finally:
            for hook in hooks:
                self.uc.hook_del(hook)
        if not hit and self.uc.reg_read(self.x.UC_X86_REG_EIP) in stops:
            hit.append(self.uc.reg_read(self.x.UC_X86_REG_EIP))    # emu_start's own stop at STOP
        return (hit[0] if hit else None), self.registers(), {a: self.uc.mem_read(a, 1)[0] for a in written}

    def registers(self):
        x = self.x
        names = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi", "eflags")
        regs = {n: self.uc.reg_read(getattr(x, "UC_X86_REG_" + n.upper())) for n in names}
        top = (self.uc.reg_read(x.UC_X86_REG_FPSW) >> 11) & 7
        regs["fpsw_top"] = top
        regs["st0"] = self.uc.reg_read(x.UC_X86_REG_FP0 + top)    # FPn are physical registers; ST(0) is FP[TOP]
        return regs


def assert_equivalent(test, gated, other, start_esp, *, allowed=(), ignore=(), msg=None):
    """Same stop, same registers (minus ``ignore``), the same final value at every byte the other run wrote, and
    gated-only writes nowhere but dead stack below the entry ESP (the trampolines' pushfd/pushad/call scratch)
    or an ``allowed`` range. Below the final ESP the stack is dead: there both runs may leave different scratch
    (for example the return address of a helper call made from a different place)."""
    (stop_a, regs_a, writes_a), (stop_b, regs_b, writes_b) = gated, other
    test.assertEqual(stop_a, stop_b, msg)
    test.assertIsNotNone(stop_a, msg)
    test.assertEqual({k: v for k, v in regs_a.items() if k not in ignore},
                     {k: v for k, v in regs_b.items() if k not in ignore}, msg)
    dead = (start_esp - 0x100, regs_b.get("esp", start_esp))
    for address, value in writes_b.items():
        test.assertIn(address, writes_a, (msg, hex(address)))
        if not dead[0] <= address < dead[1]:
            test.assertEqual(writes_a.get(address, value), value, (msg, hex(address)))
    for address in set(writes_a) - set(writes_b):
        ok = start_esp - 0x100 <= address < start_esp or any(lo <= address < hi for lo, hi in allowed)
        test.assertTrue(ok, (msg, "gated-only write", hex(address)))


class _Images:
    @classmethod
    def build(cls):
        _ready()
        cls.retail = XBE.read_bytes()
        ungated, _ = kick_rules.apply(cls.retail)
        cls.ungated, _ = kickoff.apply(ungated)
        cls.tables = gate.disc_tables(EXTRACTION)
        cls.gated, cls.receipt = gate.apply(cls.ungated, cls.tables)
        code = [a for a in gate.space.layout(cls.gated)["allocations"] if a["owner"] == gate.OWNER]
        cls.code_va = next(a["va"] for a in code if a["kind"] == "code")
        cls.data_va = next(a["va"] for a in code if a["kind"] == "data")
        forwards, touchback = gate._forwards(cls.ungated)
        cls.forwards, cls.touchback_label = forwards, touchback
        _content, cls.labels = gate.build_code(cls.code_va, cls.data_va, forwards, touchback, cls.tables)

    @classmethod
    def build_e1(cls):
        """The same gate with the return blocking option (E1) on."""
        cls.gated_e1, cls.receipt_e1 = gate.apply(cls.ungated, cls.tables, blocking=True)
        _content, cls.labels_e1 = gate.build_code(cls.code_va, cls.data_va, cls.forwards, cls.touchback_label,
                                                  cls.tables, e1=True)


POOL, POOL_SIZE = Machine.HEAP + 0x80000, 0x80000     # dereferenceable pointer soup for register-based operands


def _regs(seed, stack_top):
    """Registers that point into the pointer pool (so displaced ``mov r, [r+d]`` operands read mapped memory),
    a stack frame, and a mix of arithmetic flags."""
    rng = random.Random(seed)
    base = Machine.STACK + 0xF000
    regs = {name: POOL + rng.randrange(0, POOL_SIZE // 2, 4) for name in ("eax", "ecx", "edx", "ebx", "esi", "edi")}
    regs.update(esp=base - 0x400, ebp=base - 0x100,
                eflags=0x202 | (rng.getrandbits(1) * 0x801) | (rng.getrandbits(1) * 0x40)
                | (rng.getrandbits(1) * 0x80) | (rng.getrandbits(1) * 0x1))
    regs.update(stack_top)
    return regs


def _prime(machine, mode, seed):
    machine.put(gate.MODE_VA, mode)
    rng = random.Random(seed)
    # Stack words and pool words are pointers into the pool's lower half, so two-level operands stay mapped.
    words = [POOL + rng.randrange(0, POOL_SIZE // 2, 4) for _ in range(0x2000 // 4)]
    machine.uc.mem_write(Machine.STACK + 0xE000, struct.pack("<%dI" % len(words), *words))
    words = [POOL + rng.randrange(0, POOL_SIZE // 2, 4) for _ in range(POOL_SIZE // 4)]
    machine.uc.mem_write(POOL, struct.pack("<%dI" % len(words), *words))
    machine.uc.mem_write(Machine.STOP, b"\xf4" * 0x1000)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class OwnerTests(_Images, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build()
        cls.build_e1()

    def test_the_return_blocking_option_is_carried_only_when_asked_and_never_switched_in_place(self):
        from mod_editor.core import nfl2k5_kickoff_blocking as blocking
        self.assertEqual(gate.status(self.gated_e1), "applied")
        self.assertIs(gate.installed_blocking(self.gated), False)
        self.assertIs(gate.installed_blocking(self.gated_e1), True)
        self.assertIsNone(gate.installed_blocking(self.ungated))
        self.assertIs(self.receipt["kickoff_return_blocking"], False)
        self.assertIs(self.receipt_e1["kickoff_return_blocking"], True)
        # off: no rule code at all, and block_target forwards to the dynamic kickoff's own rule like every hook
        self.assertNotIn(blocking.ENTRY, self.labels)
        self.assertIn(blocking.ENTRY, self.labels_e1)
        image = XbeImage(self.gated)
        trampoline = self.labels["k_block_target"]
        self.assertEqual(image.read(trampoline, 1), b"\x9c")
        jump = image.read(trampoline + 11, 5)
        self.assertEqual(jump[0], 0xE9)
        self.assertEqual(trampoline + 16 + struct.unpack_from("<i", jump, 1)[0], self.forwards["block_target"])
        # the recognizers read the same sites either way, and both carry the same disc tables
        self.assertEqual(gate.gate_views(self.gated_e1), gate.gate_views(self.gated))
        self.assertEqual(gate.installed_tables(self.gated_e1), self.tables)
        for name, module in (("kickoff", kickoff), ("kick rules", kick_rules)):
            self.assertEqual(module.status(self.gated_e1), "applied", name)
        # replay keeps each; switching the option needs a rebuild from the base disc
        self.assertEqual(gate.apply(self.gated_e1, self.tables, blocking=True)[0], self.gated_e1)
        with self.assertRaises(gate.AnniversaryKickoffError):
            gate.apply(self.gated_e1, self.tables)
        with self.assertRaises(gate.AnniversaryKickoffError):
            gate.apply(self.gated, self.tables, blocking=True)

    def test_install_replay_and_the_gated_owners_still_read_as_applied(self):
        self.assertEqual(gate.status(self.gated), "applied")
        self.assertEqual(kickoff.status(self.gated), "applied")
        self.assertEqual(kick_rules.status(self.gated), "applied")
        self.assertEqual(kick_rules.read_settings(self.gated)["kickoff_yard"], 35.0)
        again, receipt = gate.apply(self.gated, self.tables)
        self.assertEqual(again, self.gated)
        self.assertEqual(receipt["status"], "already_applied")
        self.assertLessEqual(self.receipt["code_bytes"], gate.CODE_SIZE)
        self.assertEqual(len(self.receipt["edits"]), 31 + 2)

    def test_views_read_every_gated_site_as_its_owners_bytes(self):
        views = gate.gate_views(self.gated)
        self.assertEqual(len(views), 28)
        image = XbeImage(self.ungated)
        for va, view in views.items():
            self.assertEqual(view, image.read(va, len(view)), hex(va))
        self.assertEqual(gate.gate_views(self.ungated), {})

    def test_refuses_without_the_kickoff_or_on_mixed_sites(self):
        with self.assertRaises(gate.AnniversaryKickoffError):
            gate.apply(self.retail, self.tables)
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        image = XbeImage(self.gated)
        for va, value in ((0x190520, gate.READER_ENTRY), (0x18B8D0, gate.PLAY_SITE[2]),
                          (kickoff.HOOKS["lineup"][0], kickoff.HOOKS["lineup"][1])):
            broken = bytearray(self.gated)
            at = image.offset(va, len(value))
            broken[at:at + len(value)] = value            # one gated site back to its retail bytes
            for section in _sections(broken):
                broken[section.header_offset + 36:section.header_offset + 56] = section_digest(broken, section)
            self.assertEqual(gate.status(bytes(broken)), "foreign", hex(va))
        unsealed = bytearray(self.gated)
        unsealed[image.offset(0x190520, 1)] = 0x51
        self.assertEqual(gate.status(bytes(unsealed)), "foreign")

    def test_replaying_the_gated_owners_leaves_the_gate_in_place(self):
        # A rebuild over a built disc replays every owner; the kickoff reads its gated sites through gate_views, so
        # it reports already applied and writes nothing. (The kick rules never replay: the build checks their
        # status first and records "already applied", which the gated image reads as.)
        self.assertEqual(kickoff.apply(self.gated)[0], self.gated)
        self.assertEqual(kick_rules.status(self.gated), "applied")
        # ...and the build reuses the tables the installed gate carries (the built disc's plays are not retail).
        self.assertEqual(gate.installed_tables(self.gated), self.tables)
        self.assertIsNone(gate.installed_tables(self.ungated))

    def test_the_relocated_kickoff_is_gated_the_same_way(self):
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        # The build reserves the complete union first, relocates the kickoff, then installs the gate last.
        allocated, _ = gate.space.apply(self.ungated, relocated.REQUESTS + gate.REQUESTS)
        moved, _ = relocated.apply(allocated)
        gated, receipt = gate.apply(moved, self.tables)
        for name, module in (("gate", gate), ("relocated", relocated), ("kickoff", kickoff), ("kick rules", kick_rules)):
            self.assertEqual(module.status(gated), "applied", name)
        views = gate.gate_views(gated)
        self.assertEqual(len(views), 28)
        image = XbeImage(moved)
        for va, view in views.items():
            self.assertEqual(view, image.read(va, len(view)), hex(va))
        code = next(a for a in gate.space.layout(moved)["allocations"]
                    if a["owner"] == relocated.OWNER and a["kind"] == "code")
        forwards, _touchback = gate._forwards(moved)
        self.assertTrue(all(code["va"] <= target < code["va"] + code["size"]
                            for name, target in forwards.items() if name != gate.KICK_FLAGS_KEY))
        # E1 reads the kicking-direction byte from the relocated kickoff's own state, not the legacy data
        state = next(a for a in gate.space.layout(moved)["allocations"]
                     if a["owner"] == relocated.OWNER and a["kind"] == "data")
        self.assertEqual(forwards[gate.KICK_FLAGS_KEY], state["va"])
        self.assertEqual(relocated.apply(gated)[0], gated)
        self.assertEqual(gate.apply(gated, self.tables)[1]["status"], "already_applied")
        with_e1, _ = gate.apply(moved, self.tables, blocking=True)
        self.assertIs(gate.installed_blocking(with_e1), True)
        self.assertEqual(relocated.status(with_e1), "applied")
        self.assertEqual(gate.gate_views(with_e1), views)
        # The legacy-cave gate cannot be relocated afterwards: relocation would orphan the trampolines.
        with self.assertRaises(ValueError):
            relocated.apply(self.gated)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class KickoffHookTests(_Images, unittest.TestCase):
    """Part 1: the 20 dynamic kickoff sites, with the return blocking option off (the default) and on."""

    @classmethod
    def setUpClass(cls):
        cls.build()
        cls.build_e1()

    def compare(self, name, va, original, mode, e1=False, moment=0):
        seed = sum(map(ord, name)) * 10 + mode
        gated = Machine(self.gated_e1 if e1 else self.gated)
        historical = mode == 8 and moment != gate.MODERN_MOMENT
        other = Machine(self.retail if historical else self.ungated)
        for m in (gated, other):
            _prime(m, mode, seed)
            m.put(gate.MOMENT_VA, moment)
        if historical:
            end = (va + 5 + struct.unpack_from("<i", original, 1)[0]) if original[0] == 0xE9 else va + len(original)
        elif name == "block_target" and e1:
            # E1 on: outside mode 8 this site enters the return blocking rule, not the cave label. Out of the
            # blocking scope (this state) both paths replay the retail selector prologue and continue at 0x2FAFF6.
            end = va + len(original)
        else:
            end = self.forwards[name]
        regs = _regs(seed, {})
        a = gated.run(va, [end], regs)
        b = other.run(va, [end], regs)
        self.assertEqual(a[0], end, (name, mode, e1))
        assert_equivalent(self, a, b, regs["esp"], msg=(name, mode, e1))

    def test_mode_seven_forwards_to_the_same_cave_label_with_the_same_state(self):
        for e1 in (False, True):
            for name, va, original in gate.kickoff_hooks():
                with self.subTest(hook=name, e1=e1):
                    self.compare(name, va, original, 7, e1)

    def test_mode_eight_runs_the_retail_instructions(self):
        for e1 in (False, True):
            for name, va, original in gate.kickoff_hooks():
                with self.subTest(hook=name, e1=e1):
                    self.compare(name, va, original, 8, e1)

    def test_unc_bowl_keeps_every_dynamic_kickoff_path(self):
        for e1 in (False, True):
            for name, va, original in gate.kickoff_hooks():
                with self.subTest(hook=name, e1=e1):
                    self.compare(name, va, original, 8, e1, moment=50)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class KickRulesTests(_Images, unittest.TestCase):
    """Part 2: the seven kickoff-spot operands and the touchback call."""

    @classmethod
    def setUpClass(cls):
        cls.build()

    def spot(self, payload, va, mode, value=-1.0, *, moment=0):
        m = Machine(payload)
        _prime(m, mode, va)
        m.put(gate.MOMENT_VA, moment)
        # fld1 then fchs gives ST0 = -1.0 (the kicking direction sign); run the site after it.
        pre = m.alloc(b"\xd9\xe8\xd9\xe0" + b"\xe9" + struct.pack("<i", va - (Machine.HEAP + 9)))
        result = m.run(pre, [va + 6], _regs(va, {}))
        self.assertEqual(result[0], va + 6)
        return result

    def test_mode_seven_keeps_the_35_and_mode_eight_gives_the_retail_30(self):
        esp = _regs(0, {})["esp"]
        for label, va, kind in gate.kick_rule_sites():
            with self.subTest(site=label):
                assert_equivalent(self, self.spot(self.gated, va, 7), self.spot(self.ungated, va, 7), esp, msg=label)
                assert_equivalent(self, self.spot(self.gated, va, 8), self.spot(self.retail, va, 8), esp, msg=label)
                self.assertNotEqual(self.spot(self.gated, va, 8)[1]["st0"], self.spot(self.gated, va, 7)[1]["st0"])

    def touchback(self, payload, mode, phase, *, moment=0):
        m = Machine(payload)
        _prime(m, mode, phase)
        m.put(gate.MOMENT_VA, moment)
        m.uc.mem_write(kick_rules.PHASE_GLOBAL, bytes((phase,)))
        va = kick_rules.TOUCHBACK_SITE_VA
        pre = m.alloc(b"\xd9\xe8" + b"\xe9" + struct.pack("<i", va - (Machine.HEAP + 7)))
        result = m.run(pre, [va + 6], _regs(phase, {}))
        self.assertEqual(result[0], va + 6)
        return result

    def test_touchback_is_the_35_after_a_kickoff_outside_mode_eight_and_the_20_in_it(self):
        esp = _regs(0, {})["esp"]
        for phase in (1, 2, 4):
            with self.subTest(phase=phase):
                assert_equivalent(self, self.touchback(self.gated, 7, phase), self.touchback(self.ungated, 7, phase), esp)
                assert_equivalent(self, self.touchback(self.gated, 8, phase), self.touchback(self.retail, 8, phase), esp)
        self.assertNotEqual(self.touchback(self.gated, 8, 2)[1]["st0"], self.touchback(self.gated, 7, 2)[1]["st0"])
        # Outside a kickoff (phase 1, a safety kick) the 20 holds in both modes.
        self.assertEqual(self.touchback(self.gated, 8, 1)[1]["st0"], self.touchback(self.gated, 7, 1)[1]["st0"])

    def test_unc_bowl_uses_modern_spots_and_touchback(self):
        esp = _regs(0, {})['esp']
        for _label, va, _kind in gate.kick_rule_sites():
            assert_equivalent(self, self.spot(self.gated, va, 8, moment=50), self.spot(self.ungated, va, 8, moment=50), esp)
        for phase in (1, 2, 4):
            assert_equivalent(self, self.touchback(self.gated, 8, phase, moment=50), self.touchback(self.ungated, 8, phase, moment=50), esp)


def _record(tables, name, xz):
    from tools import nfl2k5_kickoff_alignment as alignment
    base = tables.kickoff_record if name == alignment.KICKOFF_NAME else tables.return_record
    slots = alignment.with_xz(base[gate.SLOT_BASE:], xz)
    return base[:gate.SLOT_BASE] + slots


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class ReaderTests(_Images, unittest.TestCase):
    """Part 3: the line-up reader 0x190520 and the diagram reader 0x17FE60."""

    @classmethod
    def setUpClass(cls):
        cls.build()
        from tools import nfl2k5_kickoff_alignment as alignment
        cls.alignment = alignment

    def read(self, payload, entry, record, mode, slot, column, mirror, *, moment=0):
        m = Machine(payload)
        _prime(m, mode, slot * 7 + column)
        m.put(gate.MOMENT_VA, moment)
        rec = m.alloc(record)
        out = m.alloc(bytes(16))
        esp = Machine.STACK + 0xF000 - 0x400
        m.put(esp, Machine.STOP)             # return address
        m.put(esp + 4, mirror)               # the reader's stack argument
        stop, regs, _writes = m.run(entry, [Machine.STOP], dict(_regs(slot, {}), esp=esp, ecx=slot, edx=rec, esi=column, eax=out))
        self.assertEqual(stop, Machine.STOP)
        return struct.unpack("<4f", bytes(m.uc.mem_read(out, 16))), regs

    def cases(self):
        a = self.alignment
        yield "Kickoff", _record(self.tables, a.KICKOFF_NAME, a.kickoff_xz_2026()), \
            _record(self.tables, a.KICKOFF_NAME, a.RETAIL_KICKOFF_XZ)
        yield "Kick Return", _record(self.tables, a.KICK_RETURN_NAME, a.KICK_RETURN_XZ_2026), \
            _record(self.tables, a.KICK_RETURN_NAME, a.RETAIL_KICK_RETURN_XZ)

    def test_mode_eight_reads_the_retail_positions_and_mode_seven_the_2026_ones(self):
        for label, entry in gate.READER_SITES:
            for name, modern, retail in self.cases():
                for slot in range(11):
                    for column, mirror in ((0, 0), (1, 1), (2, 0)):
                        with self.subTest(reader=label, formation=name, slot=slot, column=column):
                            self.assertEqual(self.read(self.gated, entry, modern, 8, slot, column, mirror)[0],
                                             self.read(self.retail, entry, retail, 8, slot, column, mirror)[0])
                            self.assertEqual(self.read(self.gated, entry, modern, 7, slot, column, mirror),
                                             self.read(self.ungated, entry, modern, 7, slot, column, mirror))

    def test_other_records_are_never_swapped(self):
        a = self.alignment
        safety = bytearray(_record(self.tables, a.KICKOFF_NAME, a.RETAIL_KICKOFF_XZ))
        struct.pack_into("<h", safety, 0x30, -530)       # a type 8 record without the 2026 coverage line
        offense = bytearray(safety)
        struct.pack_into("<I", offense, 4, struct.unpack_from("<I", offense, 4)[0] & ~(0x3F << 8))  # type 0
        struct.pack_into("<h", offense, 0x30, gate.COVERAGE_Z)
        struct.pack_into("<h", offense, 0x3E, gate.COVERAGE_Z)
        for label, entry in gate.READER_SITES:
            for record in (bytes(safety), bytes(offense)):
                for slot in (0, 1, 2, 10):
                    with self.subTest(reader=label, slot=slot):
                        self.assertEqual(self.read(self.gated, entry, record, 8, slot, 0, 0),
                                         self.read(self.ungated, entry, record, 8, slot, 0, 0))

    def test_unc_bowl_keeps_modern_lineup_and_diagram_positions(self):
        for _label, entry in gate.READER_SITES:
            for _name, modern, _retail in self.cases():
                for slot in range(11):
                    self.assertEqual(self.read(self.gated, entry, modern, 8, slot, 0, 0, moment=50),
                                     self.read(self.ungated, entry, modern, 8, slot, 0, 0, moment=50))


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class PlayStoreTests(_Images, unittest.TestCase):
    """Part 4: the play store 0x18B8D0 and the three return plays."""

    @classmethod
    def setUpClass(cls):
        cls.build()
        from tools import nfl2k5_kickoff_alignment as alignment
        from mod_editor.core import nfl2k5_kickoff_returns as returns
        from mod_editor.core import nfl2k5_play_library as lib
        from mod_editor.core.nfl2k5_playbook_inspector import RESOURCE_HEADER_SIZE, parse_playbook_resource
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTION)
        with alignment.recode.OuterImage(EXTRACTION) as archive:
            book, _refs = alignment._load(archive)[0]
            raw = archive.read_entry(book.entry_index)
        modern, _ = returns.apply(raw)
        body = modern[RESOURCE_HEADER_SIZE:]
        parsed = parse_playbook_resource(modern)
        form = next(f for f in parsed.formations if f.name == "Kick Return")
        cls.modern = {}
        for play in parsed.plays_for_formation(form):
            flags, chains = lib.play_chains(body, play.index)
            cls.modern[play.name] = (flags, chains)

    def machine(self, payload, name):
        """A play record as the loader leaves it: absolute name and chain pointers into the heap."""
        m = Machine(payload)
        flags, chains = self.modern[name]
        name_at = m.alloc((name + "\0").encode("utf-16le"))
        pointers = [m.alloc(b"".join(nodes), 8) for _desc, nodes in chains]
        record = struct.pack("<II", name_at, flags) + b"".join(
            struct.pack("<II", desc, pointer) for (desc, _nodes), pointer in zip(chains, pointers))
        return m, m.alloc(record, 16), record

    def store(self, m, record, mode, seed):
        _prime(m, mode, seed)
        return m.run(0x18B8D0, [0x18B8D5], dict(_regs(seed, {}), edx=record, ecx=Machine.HEAP))

    def test_mode_eight_puts_the_retail_chains_in_and_mode_seven_restores_the_2026_ones(self):
        for p, name in enumerate(gate.RETURN_PLAYS):
            with self.subTest(play=name):
                m, at, original = self.machine(self.gated, name)
                stop, _regs_after, _writes = self.store(m, at, 8, p)
                self.assertEqual(stop, 0x18B8D5)
                live = bytes(m.uc.mem_read(at, gate.PLAY_SIZE))
                self.assertEqual(live[:8], original[:8])             # name and flags untouched
                table = self.tables.plays[p]
                for slot in range(11):
                    desc, pointer = struct.unpack_from("<II", live, 8 + 8 * slot)
                    self.assertEqual(desc, table.descriptors[slot])
                    self.assertTrue(self.code_va <= pointer < self.code_va + gate.CODE_SIZE)
                    self.assertEqual(bytes(m.uc.mem_read(pointer, 8 * (desc & 0xF))), table.chains[slot])
                self.assertEqual(m.get(self.data_va), at)            # saved under the record's address
                self.assertEqual(bytes(m.uc.mem_read(self.data_va + 4, 88)), original[8:])
                # The same record in mode 8 again: unchanged.
                self.store(m, at, 8, p + 10)
                self.assertEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), live)
                # Stored outside mode 8: the 2026 chains come back and the entry is freed.
                self.store(m, at, 7, p + 20)
                self.assertEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), original)
                self.assertEqual(m.get(self.data_va), 0)

    def test_unc_bowl_keeps_return_chains_and_restores_prior_historical_replacements(self):
        for p, name in enumerate(gate.RETURN_PLAYS):
            m, at, original = self.machine(self.gated, name)
            m.put(gate.MOMENT_VA, 50)
            self.store(m, at, 8, p)
            self.assertEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), original)
            m.put(gate.MOMENT_VA, 49)
            self.store(m, at, 8, p)
            self.assertNotEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), original)
            m.put(gate.MOMENT_VA, 50)
            self.store(m, at, 8, p)
            self.assertEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), original)

    def test_registers_flags_and_stack_match_the_retail_prologue(self):
        for mode in (7, 8):
            for p, name in enumerate(gate.RETURN_PLAYS):
                with self.subTest(mode=mode, play=name):
                    m, at, _ = self.machine(self.gated, name)
                    r, at_r, _ = self.machine(self.retail, name)
                    self.assertEqual(at, at_r)
                    a = self.store(m, at, mode, p)
                    b = self.store(r, at_r, mode, p)
                    allowed = ((at, at + gate.PLAY_SIZE), (self.data_va, self.data_va + gate.DATA_SIZE))
                    assert_equivalent(self, a, b, _regs(p, {})["esp"], allowed=allowed, msg=(mode, name))

    def test_mode_seven_leaves_a_2026_play_alone_and_mode_eight_leaves_other_plays_alone(self):
        m, at, original = self.machine(self.gated, "Return Left")
        self.store(m, at, 7, 1)
        self.assertEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), original)
        for other in ("Return Lef", "Kickoff Left", "Onside Return"):
            m = Machine(self.gated)
            flags, chains = self.modern["Return Left"]
            name_at = m.alloc((other + "\0").encode("utf-16le"))
            pointers = [m.alloc(b"".join(nodes), 8) for _desc, nodes in chains]
            record = struct.pack("<II", name_at, flags) + b"".join(
                struct.pack("<II", desc, pointer) for (desc, _nodes), pointer in zip(chains, pointers))
            at = m.alloc(record, 16)
            self.store(m, at, 8, 3)
            self.assertEqual(bytes(m.uc.mem_read(at, gate.PLAY_SIZE)), record, other)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class CompositionTests(unittest.TestCase):
    """The gate installed last over the complete owner union leaves every owner recognizable.

    Some owners hash whole native routines that contain gated sites: MyCareer pins 0x1FF940 (the kickoff "ready"
    hook), CPU money downs pins FUN_0017FE60 (the diagram reader) and deep zone pins 0x183F60 (the kickoff "lineup"
    hook). The first lab build of this gate stopped on MyCareer reading as foreign; this class keeps that closed."""

    @classmethod
    def setUpClass(cls):
        _ready()
        from tests.nfl2k5_allocator_stack import compose, owner_calls
        base, _ = kick_rules.apply(XBE.read_bytes())
        cls.full, _ = compose(base, scaleout=True)
        cls.tables = gate.disc_tables(EXTRACTION)
        cls.gated, _ = gate.apply(cls.full, cls.tables)
        cls.gated_e1, _ = gate.apply(cls.full, cls.tables, blocking=True)
        cls.owners = owner_calls()

    def test_every_owner_of_the_union_still_reads_applied(self):
        for e1, payload in ((False, self.gated), (True, self.gated_e1)):
            self.assertEqual(gate.status(payload), "applied")
            self.assertIs(gate.installed_blocking(payload), e1)
            self.assertEqual(kick_rules.status(payload), "applied")
            self.assertEqual(kickoff.status(payload), "applied")
            for module, _kwargs in self.owners:
                with self.subTest(owner=module.OWNER, e1=e1):
                    self.assertEqual(module.status(payload), "applied")

    def test_the_three_pinned_neighbors_normalize_only_the_gated_bytes(self):
        from mod_editor.core import nfl2k5_cpu_money_downs as money_downs
        from mod_editor.core import nfl2k5_my_career_mode as my_career
        from mod_editor.core import nfl2k5_deep_zone as deep_zone
        for module in (money_downs, my_career, deep_zone):
            self.assertEqual(module.status(self.gated), "applied", module.__name__)
            self.assertEqual(module.status(self.gated_e1), "applied", module.__name__)
        # A foreign byte in the gated diagram-reader trampoline is not normalized away.
        image = XbeImage(self.gated)
        broken = bytearray(self.gated)
        broken[image.offset(0x17FE60 + 5, 1)] = 0xCC
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for section in _sections(broken):
            broken[section.header_offset + 36:section.header_offset + 56] = section_digest(broken, section)
        self.assertEqual(money_downs.status(bytes(broken)), "foreign")


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class ReturnBlockingTests(unittest.TestCase):
    """E1 (Noah [v2 5:33-5:38]: "They could block better"): the native return replay of kickoff v5 (native drive
    tasks, target refresh, pursuit, steering, root motion and collisions; coverage lanes and the carrier's straight
    run are the only decoded inputs), on the ungated 2026 kickoff and on the gated one outside mode 8, with the
    return blocking option off (the default: the 2026 rule, unchanged) and on."""

    @classmethod
    def setUpClass(cls):
        _ready()
        from tests.mod_editor.test_nfl2k5_kickoff_v5 import return_replay
        base, _ = kick_rules.apply(XBE.read_bytes())
        legacy, _ = kickoff.apply(base)
        tables = gate.disc_tables(EXTRACTION)
        off, _ = gate.apply(legacy, tables)
        on, _ = gate.apply(legacy, tables, blocking=True)
        cls.runs = {name: return_replay(unittest.TestCase(), payload, kickoff.FLAGS, 1, carrier_slot=0)
                    for name, payload in (("ungated", legacy), ("off", off), ("on", on))}

    @staticmethod
    def summary(run):
        metrics = run["metrics"].values()
        shared = 0
        for row in run["states"]:
            targets = [row[p][4] for p in range(11, 22) if row[p][4] > 0]
            shared += len(targets) - len(set(targets))
        return dict(waiting=sum(m["waiting_ticks"] for m in metrics), shared=shared,
                    contacts=sum(1 for m in metrics if m["contact_peers"]),
                    idle=sum(1 for m in metrics if m["waiting_ticks"] > 60 and not m["contact_peers"]))

    def test_the_2026_rule_leaves_blockers_waiting_and_doubled_up(self):
        before = self.summary(self.runs["ungated"])
        self.assertGreater(before["waiting"], 600)        # setup blockers park from frame 17 on
        self.assertGreater(before["shared"], 0)           # two blockers on one coverage player
        self.assertEqual(before["idle"], 5)               # five of nine setup blockers wait and touch nobody

    def test_with_the_option_off_the_return_is_the_2026_rule_exactly(self):
        self.assertEqual(self.runs["off"]["states"], self.runs["ungated"]["states"])
        self.assertEqual(self.runs["off"]["metrics"], self.runs["ungated"]["metrics"])
        self.assertEqual(self.summary(self.runs["off"]), self.summary(self.runs["ungated"]))

    def test_one_blocker_per_man_and_nobody_waits(self):
        before, after = self.summary(self.runs["ungated"]), self.summary(self.runs["on"])
        self.assertEqual(after["waiting"], 0)
        self.assertEqual(after["shared"], 0)
        self.assertEqual(after["idle"], 0)
        self.assertGreaterEqual(after["contacts"], before["contacts"] + 1)
        run = self.runs["on"]
        self.assertEqual(run["metrics"]["16"]["waiting_ticks"], 0)
        # every pursued coverage target is a real coverage player (slots 1..10), never the kicker
        for _frame, who, target in run["pursuits"]:
            self.assertIn(target, range(1, 11), who)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class NothingChangesBeforeTheTouchTests(unittest.TestCase):
    """Noah (2026-09-23): "remember new kickoff means they don't move until ball is caught". E1 must change nothing
    before the ball first touches a player or the ground.

    The rule is reached only through the dynamic kickoff's own block_scope, which requires a first-contact class in
    the kickoff state (FLAGS & 7 != 0: landing zone, end zone, short or out). Before that every blocker's selector
    call replays the retail selector, on both executables. Here the v5 return fixture keeps its native drive-block
    tasks but launches without a touch: 40 flight frames, then the touch and 30 frames more. The gate runs with the
    return blocking option off (the default) and on."""

    FLIGHT, AFTER = 40, 30

    @classmethod
    def setUpClass(cls):
        _ready()
        from tests.mod_editor.test_nfl2k5_kickoff_v5 import ReturnMachine
        from mod_editor.core import nfl2k5_kickoff_blocking as blocking

        class Flight(ReturnMachine):
            def begin_catch(self):               # the test drives launch, flight and touch itself
                pass

        base, _ = kick_rules.apply(XBE.read_bytes())
        legacy, _ = kickoff.apply(base)
        tables = gate.disc_tables(EXTRACTION)
        off, _ = gate.apply(legacy, tables)
        gated, _ = gate.apply(legacy, tables, blocking=True)
        code = next(a for a in gate.space.layout(gated)["allocations"] if a["owner"] == gate.OWNER and a["kind"] == "code")
        data = next(a for a in gate.space.layout(gated)["allocations"] if a["owner"] == gate.OWNER and a["kind"] == "data")
        forwards, touchback = gate._forwards(legacy)
        _content, labels = gate.build_code(code["va"], data["va"], forwards, touchback, tables, e1=True)
        cls.e1_in_scope = labels["e1_pass"]
        cls.runs = {}
        for name, payload in (("ungated", legacy), ("off", off), ("gated", gated)):
            for direction in (1, -1):
                m = Flight(payload, state_va=kickoff.FLAGS, direction=direction, carrier_slot=0)
                hits = []
                if name == "gated":
                    import unicorn as uc
                    m.uc.hook_add(uc.UC_HOOK_CODE, lambda _u, _a, _s, _d, h=hits: h.append(m.return_frame),
                                  begin=cls.e1_in_scope, end=cls.e1_in_scope)
                m.put(kickoff.PLAY_STATE, 14)
                m.launch()
                frames, flags = [], []
                for frame in range(cls.FLIGHT + cls.AFTER):
                    m.return_frame = frame
                    if frame == cls.FLIGHT:
                        m.position(m.readf(m.RETURNER + 0xB30), m.readf(m.RETURNER + 0xB38), m.RETURNER)
                        m.event("touch")
                        m.put(kickoff.POSSESSION, m.RECEIVE_TEAM)
                        m.put(m.BALL + 0x14, m.RETURNER + 0xB30)
                    m.frame()
                    frames.append({key: raw for key, raw in m.snapshot().items()})
                    flags.append(m.flags() & 7)
                positions = [[(m.readf(who + 0xB30), m.readf(who + 0xB38)) for who in m.players]]
                cls.runs[name, direction] = dict(frames=frames, flags=flags, hits=hits, players=m.players)

    def test_every_frame_before_the_touch_is_identical_with_and_without_e1(self):
        for state in ("off", "gated"):
            for direction in (1, -1):
                a, b = self.runs["ungated", direction], self.runs[state, direction]
                for frame in range(self.FLIGHT + 1):          # every flight frame and the touch frame itself
                    self.assertEqual(a["frames"][frame], b["frames"][frame], (state, direction, frame))
                self.assertEqual(a["flags"][:self.FLIGHT], [0] * self.FLIGHT)   # no first contact during the flight

    def test_with_the_option_off_nothing_changes_after_the_touch_either(self):
        for direction in (1, -1):
            self.assertEqual(self.runs["off", direction]["frames"], self.runs["ungated", direction]["frames"])
            self.assertEqual(self.runs["off", direction]["flags"], self.runs["ungated", direction]["flags"])

    def test_setup_blockers_do_not_move_before_the_touch(self):
        for state in ("off", "gated"):
            for direction in (1, -1):
                run = self.runs[state, direction]
                first = run["frames"][0]
                for frame in range(1, self.FLIGHT):
                    for (player, kind), raw in run["frames"][frame].items():
                        if kind == "transform" and 13 <= player <= 21:     # the nine setup-zone blockers
                            self.assertEqual(raw, first[player, kind], (state, direction, frame, player))

    def test_the_rule_runs_only_after_the_touch(self):
        for direction in (1, -1):
            hits = self.runs["gated", direction]["hits"]
            self.assertTrue(hits, direction)                   # it does run once the ball has touched
            self.assertGreaterEqual(min(hits), self.FLIGHT, direction)


if __name__ == "__main__":  # pragma: no cover - the capability registry runs this module directly
    unittest.main()
