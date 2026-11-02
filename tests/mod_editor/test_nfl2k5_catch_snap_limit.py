"""Defender catch snap limit (nfl2k5_catch_snap_limit): exact bytes, replay, refusal, presets, late-owner placement,
composition with another late owner, and the owner's exit stub run in Unicorn at its real hook on the patched
executable against the retail one. No game boot.

The stub is entered from the selector's success exit (0x1E7B02) with a synthetic frame: the player, his team, the
controller marker, the ball kind, the request and the plan record are supplied inputs; everything else is the owner's
own code and the retail epilogue it resumes into. The real selector and plan setup run in
test_nfl2k5_catch_snap_limit_unicorn.py (needs the repo's tools and the retail extraction).

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import math
import random
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_ball_carrier_ai as bc
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_catch_snap_limit as cs
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import XBE, retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

YARD = 91.44
# The cave as placed at 0x14DA000 (the first code run a retail image gets): 215 bytes, the rest of the allocation is 0xCC.
CAVE_AT_14DA000 = (
    "18a5024548e136428b44241885c074778b4c241083e95583f902776b833dc002e6000475628b0d8002e6003b4e387457"
    "8b4e0c8339ff754f8b4d088b1185d274468379400074408b5204c1ea0883e20383fa017532d94110d8c8d94118d8c8de"
    "c1d81d00a04d01dfe0f6c4047505f6c4417514c7414000000000c741040000803f31c0894424188b4424185fe976dad0"
    "fed95c2418833dc002e6000475308b4424108b0d8002e6003b483874218b400c8338ff7519d90504a04d01d85c2418df"
    "e0f6c4417408c744241848e13642d9442418e9fcbbd0fe")


class StaticTests(unittest.TestCase):
    def test_cave_bytes_and_sites(self):
        code, labels = cs.code_for(0x14DA000)
        self.assertEqual(len(code), cs.CODE_SIZE)
        self.assertEqual(code.hex(), CAVE_AT_14DA000 + "cc" * (cs.CODE_SIZE - len(CAVE_AT_14DA000) // 2))
        self.assertEqual((labels["exit"], labels["cap"]), (8, 145))
        # the two constants: the squared limit (cm squared) and the limit (cm)
        self.assertAlmostEqual(struct.unpack("<f", code[:4])[0], (0.5 * YARD) ** 2, places=2)
        self.assertAlmostEqual(struct.unpack("<f", code[4:8])[0], 0.5 * YARD, places=4)
        # the selector stub starts by re-running the displaced instruction, ends by repeating it and the pop edi, then resumes
        self.assertEqual(code[8:12], cs.HOOK[2][:4])
        exit_end = labels["cap"]
        self.assertEqual(code[exit_end - 10:exit_end - 5], cs.HOOK[2])
        self.assertEqual(code[exit_end - 5], 0xE9)
        self.assertEqual(0x14DA000 + exit_end + struct.unpack("<i", code[exit_end - 4:exit_end])[0], cs.RESUME)
        # the cap stub starts with the displaced fstp, ends with the displaced fld, then resumes after the span
        used = code.rstrip(b"\xcc")
        self.assertEqual(code[labels["cap"]:labels["cap"] + 4], cs.CAP_HOOK[2][:4])
        self.assertEqual(used[-9:-5], cs.CAP_HOOK[2][4:])
        self.assertEqual(used[-5], 0xE9)
        self.assertEqual(0x14DA000 + len(used) + struct.unpack("<i", used[-4:])[0], cs.CAP_RESUME)
        self.assertEqual(cs.RESUME, cs.HOOK[1] + len(cs.HOOK[2]))
        self.assertEqual(cs.CAP_RESUME, cs.CAP_HOOK[1] + len(cs.CAP_HOOK[2]))
        self.assertEqual(cs.sites(0x14DA000), [
            ("exit", 0x1E7B02, bytes.fromhex("8b4424185f"), b"\xe9" + struct.pack("<i", 0x14DA008 - 0x1E7B02 - 5)),
            ("cap", 0x1E5CCB, bytes.fromhex("d95c2418d9442418"),
             b"\xe9" + struct.pack("<i", 0x14DA000 + 145 - 0x1E5CCB - 5) + b"\x90\x90\x90")])
        self.assertEqual(cs.REQUESTS, (("nfl2k5_catch_snap_limit", "code", 224, 16),))
        self.assertLessEqual(len(used), cs.CODE_SIZE)

    def test_presets_options_and_late_owner_order(self):
        self.assertEqual(space.LATE_OWNERS[-1], cs.OWNER)                     # last: it never moves another owner
        self.assertEqual(space.LATE_OWNERS[-2], "nfl2k5_sim_realism_state")
        self.assertEqual(space.LATE_OWNERS.count(cs.OWNER), 1)
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).catch_snap_limit, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["catch_snap_limit"], False, name)            # opt-in everywhere until an emulator witness
        self.assertIn("catch_snap_limit", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_catch_snap_limit", "Defender catch snap limit"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        # like the other late owners it is not a copy-step option: a plan with only this option still builds (see
        # WriterTests.test_a_real_xbe_only_build_applies_the_option_last)
        self.assertFalse(mod_build.BuildPlan(Path("source.iso"), Path("target.iso"), catch_snap_limit=True).wants_xbe_patch())

    def test_text_is_plain_and_the_module_has_no_private_paths(self):
        text = (ROOT / "mod_editor/core/nfl2k5_catch_snap_limit.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        for string in (cs.HELP_TEXT, cs.BUILD_CAPTION):
            self.assertNotIn("—", string)                                   # no em dashes in public text
            self.assertTrue(string.isascii())
        self.assertIn("EXPERIMENTAL", cs.HELP_TEXT)

    def test_limit_is_half_a_yard(self):
        self.assertEqual(cs.LIMIT_YARDS, 0.5)
        self.assertAlmostEqual(cs.LIMIT_CM, 45.72)

    def test_build_settings_accept_the_key_and_reject_a_non_boolean(self):
        self.assertEqual(settings.defaults()["catch_snap_limit"], False)
        self.assertIs(settings.build_settings({"catch_snap_limit": True})["catch_snap_limit"], True)
        with tempfile.TemporaryDirectory(prefix="snap-plan-") as raw:
            xbe = Path(raw) / "default.xbe"
            xbe.write_bytes(b"not an executable")
            for bad in (1, "yes", None):
                with self.assertRaisesRegex(ValueError, "must be Off or On"):
                    mod_build.build(mod_build.BuildPlan(str(xbe), str(Path(raw) / "out.xbe"), catch_snap_limit=bad))
            # a foreign source is refused by the preflight before any write
            with self.assertRaisesRegex(ValueError, "not retail"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(Path(raw) / "out.xbe"), catch_snap_limit=True))
            self.assertFalse((Path(raw) / "out.xbe").exists())


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = cs.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(cs.status(self.retail), "retail")
        self.assertEqual(cs.status(self.final), "applied")
        image = XbeImage(self.final)
        code = cs.allocation(self.final)["va"]
        self.assertEqual(image.read(code, cs.CODE_SIZE), cs.code_for(code)[0])
        for _, va, _, new in cs.sites(code):
            self.assertEqual(image.read(va, len(new)), new)
        self.assertEqual(space.status(self.final), "applied")
        self.assertEqual(self.receipt["status"], "applied")
        self.assertEqual(self.receipt["edits"][0]["va"], "0x1e7b02")

    def test_only_the_hooks_change_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        windows = set(range(0x1E7B02, 0x1E7B07)) | set(range(0x1E5CCB, 0x1E5CD3))
        self.assertIn(0x1E7B02, changed)                                        # the jump opcode replaces the 0x8B
        self.assertIn(0x1E5CCB, changed)                                        # and the 0xD9
        self.assertTrue(set(changed) <= windows, sorted(set(changed) - windows))   # nothing outside the two windows
        code = cs.allocation(self.final)["va"]
        for _, va, _, new in cs.sites(code):
            self.assertEqual(b.read(va, len(new)), new)

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = cs.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = cs.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x1E7B02, b"\xe9\x00\x00\x00\x00"),
                                     "code": (code + 20, b"\x90"),
                                     "constant": (code, b"\x00\x00\x00\x00"),
                                     "selector": (0x1E7A00, b"\x90"),
                                     "jump table": (0x1E7B20, b"\x00"),
                                     "families": (0x1E7500, b"\x90"),
                                     "candidates": (0x1E6700, b"\x90"),
                                     "setup": (0x1E5900, b"\x90"),
                                     "update": (0x1E2D00, b"\x90"),
                                     "alignment helper": (0x1A8950, b"\x90"),
                                     "cap hook": (0x1E5CCB, b"\xe9\x00\x00\x00\x00"),
                                     "cap hook filler": (0x1E5CD0, b"\xcc")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(cs.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                cs.apply(bad)
        for label, (va, content) in {"selector": (0x1E7A00, b"\x90"), "hook next byte": (0x1E7B05, b"\x90"),
                                     "setup": (0x1E5900, b"\x90"), "cap hook span": (0x1E5CCF, b"\x90")}.items():
            retail_bad = repin_edit(self.retail, va, content)
            self.assertEqual(cs.status(retail_bad), "foreign", label)
            with self.assertRaises(ValueError):
                cs.apply(retail_bad)

    def test_begin_callback_is_deliberately_not_pinned(self):
        # the abilities owner may replace the call to 0x2D4740 at 0x1E7BA2 inside the begin callback
        changed = repin_edit(self.retail, 0x1E7BA2, b"\xe8\x00\x00\x00\x00")
        self.assertEqual(cs.status(changed), "retail")
        final, _ = cs.apply(changed)
        self.assertEqual(cs.status(final), "applied")

    def test_a_real_xbe_only_build_applies_the_option_last(self):
        # the whole Build path on the pinned retail default.xbe: the option alone, and with two other late owners
        with tempfile.TemporaryDirectory(prefix="snap-build-") as raw:
            for options, others in ((dict(), ()), (dict(cpu_ball_carriers=True, return_coverage=True), ("cpu_ball_carriers", "return_coverage"))):
                out = Path(raw) / f"out{len(others)}.xbe"
                receipt = mod_build.build(mod_build.BuildPlan(str(XBE), str(out), catch_snap_limit=True, **options))
                built = out.read_bytes()
                self.assertEqual(cs.status(built), "applied")
                self.assertEqual(space.status(built), "applied")
                steps = [row["step"] for row in receipt["steps"]]
                self.assertEqual(steps[-1], "catch_snap_limit", steps)                # LATE_OWNERS order: after the others
                self.assertEqual(receipt["result"]["catch_snap_limit"], "applied")
                for name in others:
                    self.assertIn(name, steps)
                self.assertEqual(mod_build.inspect(out)["catch_snap_limit"], "applied")
                self.assertEqual(mod_build.inspect(XBE)["catch_snap_limit"], "retail")

    def test_composes_with_another_late_owner(self):
        carriers, _ = bc.apply(self.retail)
        first = space.layout(carriers)["allocations"]
        both, _ = cs.apply(carriers)                                              # appended after it, in LATE_OWNERS order
        self.assertEqual((cs.status(both), bc.status(both), space.status(both)), ("applied", "applied", "applied"))
        after = space.layout(both)["allocations"]
        for row in first:
            if row["owner"] != space.DIRECTORY_OWNER:
                self.assertIn(row, after, row["owner"])                          # appending moved nothing
        # an owner that sorts earlier cannot be appended after this last one: refused, as for every late owner
        with self.assertRaises(ValueError):
            bc.apply(self.final)

    def test_the_build_reserves_both_and_either_writer_order_works(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        requests = tt._selected_space_requests(cpu_ball_carriers=True, catch_snap_limit=True)
        self.assertIn(cs.REQUESTS[0], requests)
        installed, _ = space.apply(self.retail, requests, scaleout=True)
        for order in ((bc, cs), (cs, bc)):
            payload = installed
            for module in order:
                payload, _ = module.apply(payload)
            self.assertEqual((cs.status(payload), bc.status(payload), space.status(payload)), ("applied",) * 3)


@unittest.skipIf(uc is None, "unicorn is not installed")
class StubTests(unittest.TestCase):
    """The stub at its real hook. Frame: ESI = player, [ebp+8] = plan record, [esp+0x10] = request, [esp+0x18] = result
    (the selector's locals); the retail epilogue pops the three saved registers and returns."""
    HEAP, STACK, RET = 0x3000000, 0x3100000, 0x3200000
    CLIP_ALIGNED, CLIP_FAMILY0, CLIP_FAMILY2, CLIP_FAMILY3 = 0x100, 0x000, 0x200, 0x300   # descriptor flag bits 8..9

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, _ = cs.apply(cls.retail)

    def machine(self, payload):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({va for s in image.sections for va in range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096)})
        start = prev = None
        for va in pages + [None]:
            if va is not None and prev is not None and va == prev + 4096:
                prev = va
                continue
            if start is not None:
                m.mem_map(start, prev + 4096 - start)
            start = prev = va
        for s in image.sections:
            if s.raw_size:
                m.mem_write(s.start, image.read(s.start, s.raw_size))
        for base in (self.HEAP, self.STACK, self.RET):
            m.mem_map(base, 0x10000)
        m.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        return m

    def stub(self, payload, *, correction=(30.0, 0.0, 40.0), request=0x55, ball_kind=4, cpu=True, defender=True,
            accepted=1, clip=True, family=0x100, result=1, rate=0.9, mutate=None):
        m = self.machine(payload)
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))
        flt = lambda va, v: m.mem_write(va, struct.pack("<f", v))
        player, ctl, team_def, team_off, record, descriptor = (self.HEAP + 0x400 * i for i in range(6))
        put(player + 0x38, team_def if defender else team_off)
        put(player + 0xC, ctl)
        put(ctl, 0xFFFFFFFF if cpu else 0)
        put(0xE60280, team_off)
        put(0xE602C0, ball_kind)
        put(descriptor + 4, family | 0x00A50000)                                 # other flag bits set, family in 8..9
        put(record, descriptor if clip else 0)
        flt(record + 4, rate)
        for offset, value in zip((0x10, 0x14, 0x18), correction):
            flt(record + offset, value)
        put(record + 0x40, accepted)
        if mutate:
            mutate(m, record, descriptor)
        esp, ebp = self.STACK + 0x8000, self.STACK + 0x8100
        m.mem_write(esp, struct.pack("<III", 0xE0E0E0E0, 0x51515151, 0xB0B0B0B0))     # saved edi, esi, ebx
        put(esp + 0x10, request)
        put(esp + 0x18, result)
        m.mem_write(ebp, struct.pack("<III", 0x0B0B0B0B, self.RET, record))             # saved ebp, return, record
        for reg, value in ((x86.UC_X86_REG_ESP, esp), (x86.UC_X86_REG_EBP, ebp), (x86.UC_X86_REG_ESI, player),
                           (x86.UC_X86_REG_EAX, 0xAAAAAAAA), (x86.UC_X86_REG_ECX, 0xCCCCCCCC), (x86.UC_X86_REG_EDX, 0xDDDDDDDD)):
            m.reg_write(reg, value)
        top_before = (m.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7
        m.emu_start(0x1E7B02, self.RET, count=2000)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), self.RET)
        self.assertEqual((m.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7, top_before, "x87 stack left unbalanced")
        # the retail epilogue restored the callee-saved registers from the right slots and cleaned the frame
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EDI), 0xE0E0E0E0)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESI), 0x51515151)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EBX), 0xB0B0B0B0)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EBP), 0x0B0B0B0B)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESP), ebp + 0xC)
        return {"result": m.reg_read(x86.UC_X86_REG_EAX), "accepted": struct.unpack("<I", m.mem_read(record + 0x40, 4))[0],
                "rate": struct.unpack("<f", m.mem_read(record + 4, 4))[0],
                "clip": struct.unpack("<I", m.mem_read(record, 4))[0],
                "correction": struct.unpack("<3f", m.mem_read(record + 0x10, 12)),
                "record": bytes(m.mem_read(record, 80))}

    def both(self, **kw):
        return self.stub(self.retail, **kw), self.stub(self.final, **kw)

    def assertDemoted(self, **kw):
        old, new = self.both(**kw)
        self.assertEqual((old["result"], old["accepted"]), (1, 1))                # retail keeps the plan
        self.assertAlmostEqual(old["rate"], 0.9, places=6)
        self.assertEqual((new["result"], new["accepted"], new["rate"]), (0, 0, 1.0))
        self.assertEqual(new["clip"], old["clip"])                                # the clip stays: a valid unaccepted record
        self.assertEqual(new["record"][0x10:0x1C], old["record"][0x10:0x1C])      # nothing else is rewritten (bytes: NaN != NaN)

    def assertRetail(self, **kw):
        old, new = self.both(**kw)
        self.assertEqual(new, old)

    def test_retail_is_the_control(self):
        old = self.stub(self.retail)
        self.assertEqual((old["result"], old["accepted"]), (1, 1))

    def test_a_long_slide_is_demoted_to_the_non_catch_answer(self):
        for correction in ((30.0, 0.0, 40.0), (46.0, 0.0, 0.0), (0.0, 0.0, -46.0), (-33.0, 9.0, -33.0), (45.0, 0.0, 9.0),
                           (80.0, 0.0, 80.0), (1e6, 0.0, 0.0)):
            self.assertDemoted(correction=correction)

    def test_a_short_slide_keeps_the_retail_plan_byte_for_byte(self):
        for correction in ((0.0, 0.0, 0.0), (20.0, 0.0, 30.0), (45.0, 0.0, 0.0), (-45.0, 0.0, 0.0), (0.0, 0.0, -45.0),
                           (31.0, 0.0, 31.0), (-31.0, 0.0, 31.0)):
            self.assertRetail(correction=correction)

    def test_the_limit_is_half_a_yard_of_horizontal_distance(self):
        for edge in (45.3, 45.6):
            self.assertRetail(correction=(edge, 0.0, 0.0))
        for edge in (45.9, 46.2):
            self.assertDemoted(correction=(edge, 0.0, 0.0))
        self.assertRetail(correction=(32.0, 0.0, 32.0))                           # 45.25
        self.assertDemoted(correction=(33.0, 0.0, 33.0))                          # 46.67

    def test_height_does_not_count(self):
        self.assertRetail(correction=(10.0, 500.0, 10.0))
        self.assertRetail(correction=(10.0, -500.0, 10.0))

    def test_not_a_number_and_infinity_are_too_long(self):
        for bad in (math.nan, math.inf, -math.inf):
            self.assertDemoted(correction=(bad, 0.0, 0.0))
            self.assertDemoted(correction=(0.0, 0.0, bad))

    def test_only_cpu_defenders_on_forward_passes_with_a_real_catch_request(self):
        self.assertRetail(cpu=False)                                              # human-controlled defender
        self.assertRetail(defender=False)                                         # a receiver (his team has the ball)
        for kind in (0, 1, 2, 3, 5):
            self.assertRetail(ball_kind=kind)                                     # kicks, backward passes, loose balls
        for request in (0, 1, 0x54, 0x58, 0x61):
            self.assertRetail(request=request)                                    # the AI's probe (0) and other requests
        for request in (0x55, 0x56, 0x57):
            self.assertDemoted(request=request)

    def test_only_accepted_plans_for_the_aligned_clip_family(self):
        self.assertRetail(accepted=0)                                             # already the non-catch answer
        self.assertRetail(clip=False)
        self.assertRetail(result=0)                                               # nothing selected
        for family in (self.CLIP_FAMILY0, self.CLIP_FAMILY2, self.CLIP_FAMILY3):
            self.assertRetail(family=family)                                      # dives and leaps move him by velocity
        self.assertDemoted(family=self.CLIP_ALIGNED)

    def test_other_record_fields_and_the_rest_of_the_frame_are_untouched(self):
        old, new = self.both(correction=(80.0, 7.0, 80.0))
        self.assertEqual(new["record"][:4], old["record"][:4])
        self.assertEqual(new["record"][8:0x40], old["record"][8:0x40])
        self.assertEqual(new["record"][0x44:], old["record"][0x44:])



    def test_random_frames_match_a_reference_model(self):
        """120 seeded frames over every gate and the slide (including NaN, infinity, signed zero, denormals): the patched
        stub demotes exactly where the written rule says and never changes anything else; retail never changes."""
        rng = random.Random(780)
        limit_sq = cs.LIMIT_SQUARED
        demoted = 0
        for index in range(120):
            gates = dict(request=rng.choice([0, 0x54, 0x55, 0x55, 0x56, 0x57, 0x58]), ball_kind=rng.choice([3, 4, 4, 4, 0]),
                         cpu=rng.random() < 0.8, defender=rng.random() < 0.8, accepted=rng.choice([0, 1, 1, 1]),
                         clip=rng.random() < 0.9, family=rng.choice([0x000, 0x100, 0x100, 0x100, 0x200, 0x300]),
                         result=rng.choice([0, 1, 1, 1]), rate=0.9)
            pick = rng.random()
            if pick < 0.05:
                x, z = rng.choice([math.nan, math.inf, -math.inf, 0.0, -0.0, 1e-42]), rng.choice([0.0, 12.0, math.nan])
            else:
                while True:
                    x, z = rng.uniform(-80, 80), rng.uniform(-80, 80)
                    if abs(x * x + z * z - limit_sq) > 5.0:                 # keep away from the float rounding of the edge
                        break
            y = rng.choice([0.0, 300.0, -300.0])
            gates["correction"] = (x, y, z)
            old = self.stub(self.retail, **gates)
            new = self.stub(self.final, **gates)
            self.assertEqual(old["result"], gates["result"], index)             # retail never changes anything
            long_slide = math.isnan(x) or math.isnan(z) or math.isinf(x) or math.isinf(z) or x * x + z * z > limit_sq
            expect = (gates["result"] != 0 and gates["request"] in (0x55, 0x56, 0x57) and gates["ball_kind"] == 4
                      and gates["defender"] and gates["cpu"] and gates["clip"] and gates["accepted"] != 0
                      and gates["family"] == 0x100 and long_slide)
            if expect:
                demoted += 1
                self.assertEqual((new["result"], new["accepted"], new["rate"]), (0, 0, 1.0), (index, gates))
                self.assertEqual(new["clip"], old["clip"], index)
                self.assertEqual(new["record"][0x10:0x1C], old["record"][0x10:0x1C], index)
            else:
                self.assertEqual({k: v for k, v in new.items() if k != "correction"},
                                 {k: v for k, v in old.items() if k != "correction"}, (index, gates))   # bytes cover NaN
        self.assertGreaterEqual(demoted, 3)


@unittest.skipIf(uc is None, "unicorn is not installed")
class CapStubTests(unittest.TestCase):
    """The setup's reach-cap stub at its real hook (0x1E5CCB), entered with the retail cap on the x87 stack and
    the player at [esp+0x10]; run to the span's end (0x1E5CD3), where the retail comparison would follow."""
    HEAP, STACK = 0x3000000, 0x3100000
    CAP_ADDRESS = 0x3000F00

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, _ = cs.apply(cls.retail)
        cls.helper = StubTests("test_retail_is_the_control")

    def cap_after(self, payload, cap, *, cpu=True, defender=True, ball_kind=4):
        m = self.helper.machine(payload)
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))
        player, ctl, team_def, team_off = (self.HEAP + 0x400 * i for i in range(4))
        put(player + 0x38, team_def if defender else team_off)
        put(player + 0xC, ctl)
        put(ctl, 0xFFFFFFFF if cpu else 0)
        put(0xE60280, team_off)
        put(0xE602C0, ball_kind)
        m.mem_write(self.CAP_ADDRESS, struct.pack("<f", cap))
        esp = self.STACK + 0x8000
        put(esp + 0x10, player)
        put(esp + 0x18, 0x7F7F7F7F)
        scratch = self.HEAP + 0x8000                       # fld dword [cap]; jmp 0x1E5CCB
        m.mem_write(scratch, b"\xd9\x05" + struct.pack("<I", self.CAP_ADDRESS) + b"\xe9" +
                    struct.pack("<i", 0x1E5CCB - (scratch + 11)))
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        m.emu_start(scratch, 0x1E5CD3, count=500)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), 0x1E5CD3)
        self.assertEqual((m.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7, 7, "x87 stack: the cap only, as retail leaves it")
        return struct.unpack("<f", m.mem_read(esp + 0x18, 4))[0]

    def both(self, cap, **kw):
        return self.cap_after(self.retail, cap, **kw), self.cap_after(self.final, cap, **kw)

    def test_retail_is_the_control(self):
        for cap in (10.0, 45.72, 76.2, 91.44, 500.0):
            self.assertAlmostEqual(self.cap_after(self.retail, cap), cap, places=3)

    def test_a_cpu_defender_cap_never_exceeds_the_limit(self):
        for cap in (45.8, 60.0, 76.2, 91.44, 91.6, 500.0, math.inf):
            old, new = self.both(cap)
            self.assertAlmostEqual(new, cs.LIMIT_CM, places=3, msg=str(cap))
            self.assertAlmostEqual(old, cap, places=3)

    def test_a_smaller_cap_stays(self):
        for cap in (0.0, 10.0, 30.0, 45.0, 45.72):
            old, new = self.both(cap)
            self.assertAlmostEqual(new, min(cap, cs.LIMIT_CM), places=3)

    def test_not_a_number_takes_the_limit(self):
        self.assertAlmostEqual(self.cap_after(self.final, math.nan), cs.LIMIT_CM, places=3)

    def test_everyone_else_keeps_the_retail_cap(self):
        for kw in (dict(cpu=False), dict(defender=False), dict(ball_kind=3), dict(ball_kind=0), dict(ball_kind=5)):
            old, new = self.both(91.44, **kw)
            self.assertEqual(new, old, kw)
            self.assertAlmostEqual(new, 91.44, places=3)

    def test_random_caps_match_a_reference_model(self):
        rng = random.Random(781)
        lowered = 0
        for index in range(80):
            kw = dict(cpu=rng.random() < 0.8, defender=rng.random() < 0.8, ball_kind=rng.choice([3, 4, 4, 4, 0]))
            cap = rng.choice([math.nan, math.inf, 0.0, 91.44, 76.2, 45.72, 45.7, 45.8]) if rng.random() < 0.25 else rng.uniform(0.0, 120.0)
            if not (math.isnan(cap) or math.isinf(cap)) and abs(cap - cs.LIMIT_CM) < 0.01:
                cap += 0.5                                                   # keep away from the float rounding of the edge
            old, new = self.both(cap, **kw)
            if not math.isnan(cap):
                self.assertAlmostEqual(old, cap, places=3, msg=(index, kw)) if math.isfinite(cap) else self.assertEqual(old, cap)
            applies = kw["ball_kind"] == 4 and kw["defender"] and kw["cpu"]
            if applies and (math.isnan(cap) or cap >= cs.LIMIT_CM):
                lowered += 1
                self.assertAlmostEqual(new, cs.LIMIT_CM, places=3, msg=(index, kw, cap))
            elif math.isnan(cap):
                self.assertTrue(math.isnan(new), (index, kw))
            else:
                self.assertAlmostEqual(new, old, places=3, msg=(index, kw, cap)) if math.isfinite(cap) else self.assertEqual(new, old)
        self.assertGreaterEqual(lowered, 10)


if __name__ == "__main__":
    unittest.main()
