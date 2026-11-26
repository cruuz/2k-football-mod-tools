"""Combined calibration levers (beta 81, pos3/COMBINED_PLAN.md sections 1 and 8), built at today's values.

Lever 1, sacks: the simulated pass-pressure centre is nfl2k5_pass_protection's own float (SIM_CENTRE at 0x1083B0, in
its sim_event_chance site, behind a two-byte jump). v0.8, v0.9 and beta 80 pointed the operand at 0x1083F8 to the retail
.rdata float 0x4E73E4 instead; the owner reads that form as "legacy", updates it in place and restores Retail from it.
Lever 2, the quarterback's supplemental chance: QB_CHANCE_SCALE multiplies the two quarterback threshold tables only.
Lever 3, slice 1's passing level: PASSING_LEVEL drives the accuracy gain table and the base multiplier together.

The lever was built at 0.866, where every byte the simulation reads was unchanged (the float held exactly the bits at
0x4E73E4; Unicorn still checks a 0.866 build against the legacy forms). The fitted centre 0.890 is the module default since
the coordinator accepted it (2026-11-21). At the default lever 2 and 3 values the quarterback bank is unchanged.
The retail executable comes from the private fixtures (skipped when absent); the shipped legacy installs are the
slice 1 base bda1e4a4 (NFL2K5_B81_STABILITY_FIXTURES), the v0.8 executable (NFL2K5_V08_XBE) and the v0.9 release
candidate (NFL2K5_V09_XBE). No game boot is claimed.
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_pass_protection as pp  # noqa: E402
from mod_editor.core import nfl2k5_sim_qb_injuries_code as code  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe  # noqa: E402

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

BASE_XBE = "bda1e4a408f19cc30f0916e03b158b0accc46e0ccb6a39e134c1ce79ba3ab6ea"         # slice 1 base, shared base disc
# Realistic on it, revision 4, levers unfrozen: 12f2776dd's own (lever-free) result. It was dff6cbc5 before the 7c64ec2ca merge, which
# adds scoring's bytes and the 0.35 floor immediates only (pos3/work/combined-A/merge/classify.txt).
LEVER_FREE_XBE = "33cd2a36a81b20d86ddd50417bbb71212be933fc20bee68d58645d4e3e01eb50"
# The freeze (bb5a408b1: QB_CHANCE_SCALE 1.06, breakaway stop 68) moves exactly the two QB tables (606 bytes), one byte of
# the breakaway site and integrity fields (pos3/work/combined-A/freeze/classify.txt).
REALISTIC_XBE = "aa1e29e1846ae8e094631283b1a122f3cf3a6dc95a5f617bbf7a19a6eb9669c7"
LEGACY_INSTALLS = (("NFL2K5_B81_STABILITY_FIXTURES", "default.xbe", BASE_XBE),
                   ("NFL2K5_V08_XBE", None, "5f987568"),
                   ("NFL2K5_V09_XBE", None, "1a476d94"))
# Written by the code at 15d592f28 (before the levers): _configure_tables(bytearray(CODE_SIZE), rate).
TABLES_BEFORE = {310: "8d76ebe2c4300175675fdc0b1d1800b14ad3141b66483968dbb99cd6dcaef052",
                 0: "e3084db496e8b4b36abb25f1c9113502c1ef925338f9ce3935aaa2653443730b",
                 155: "ce734c48047952574fa0c163da99c715cc3245d6a2d5bf04c7294ba42bfaf8ff",
                 100000: "a584336e16d801ede952ec21794a94bef38f1ae75b522d7619d1142e09a63a2b"}
EVENT_SITE = (0x108398, 0x1083D6)
CENTRE_ADD = (0x1083F2, 0x108400)        # fld [esp+0x18]; fadd [operand]; fstp [esp+0x14] (v before the clamp)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def legacy_installs():
    """(name, payload) of every shipped legacy executable present on this machine."""
    out = []
    for variable, member, digest in LEGACY_INSTALLS:
        root = os.environ.get(variable)
        path = Path(root) / member if root and member else Path(root) if root else None
        if path is None or not path.is_file():
            continue
        payload = path.read_bytes()
        if _sha(payload).startswith(digest):
            out.append((variable, payload))
    return out


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _emulate(payload, start, stop, frame):
    """Run the executable's own bytes from start to stop with ESP at a 0x40-byte frame; returns (EIP, frame after)."""
    image = XbeImage(payload)
    machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
    for page in (0x108000, 0x4E6000, 0x4E7000, 0x4F6000):
        machine.mem_map(page, 0x1000)
        machine.mem_write(page, image.read(page, 0x1000))
    stack = 0x7F000000
    machine.mem_map(stack, 0x10000)
    esp = stack + 0x8000
    machine.mem_write(esp, bytes(frame))
    machine.reg_write(x86.UC_X86_REG_ESP, esp)
    machine.emu_start(start, stop, count=200)
    return machine.reg_read(x86.UC_X86_REG_EIP), bytes(machine.mem_read(esp, len(frame)))


def _frame(**floats):
    frame = bytearray(0x40)
    for name, value in floats.items():
        struct.pack_into("<f", frame, int(name[1:], 16), value)
    return frame


class SackCentreBytes(unittest.TestCase):
    """Lever 1 on the retail executable: where the float lives and what the operand reads."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.fresh, cls.receipt = pp.apply(cls.retail)

    def test_operand_reads_the_owners_float_which_holds_the_constant(self):
        image = XbeImage(self.fresh)
        self.assertEqual(image.read(0x1083F8, 4), struct.pack("<I", pp.SIM_CENTRE_VA))
        self.assertEqual(image.read(pp.SIM_CENTRE_VA, 4), struct.pack("<f", pp.SIM_CENTRE))
        # the default is exactly the float v0.8, v0.9 and beta 80 read, which stays untouched in .rdata
        # the fitted centre (accepted 2026-11-21); earlier releases read 0.866 at 0x4E73E4, which stays untouched in .rdata
        self.assertEqual(pp.SIM_CENTRE, 0.890)
        self.assertEqual(XbeImage(self.retail).read(pp.LEGACY_CENTRE_VA, 4), struct.pack("<f", 0.866))
        self.assertEqual(image.read(pp.LEGACY_CENTRE_VA, 4), XbeImage(self.retail).read(pp.LEGACY_CENTRE_VA, 4))
        # the float sits in the owner's own site, after its code and a jump over it
        start, end = EVENT_SITE
        self.assertTrue(start + len(pp.SIM_EVENT_CODE) + 2 == pp.SIM_CENTRE_VA and pp.SIM_CENTRE_VA + 4 <= end)
        self.assertEqual(image.read(pp.SIM_CENTRE_VA - 2, 2), b"\xeb\x04")
        self.assertEqual(image.read(pp.SIM_CENTRE_VA + 4, end - pp.SIM_CENTRE_VA - 4), b"\x90" * (end - pp.SIM_CENTRE_VA - 4))
        self.assertEqual(pp.read_settings(self.fresh), {"status": "applied", "sim_centre": _f32(pp.SIM_CENTRE)})
        self.assertEqual(self.receipt["sim_centre"], _f32(pp.SIM_CENTRE))
        self.assertEqual(pp.REQUESTS, ((pp.OWNER, "code", 352, 16),))      # no new or larger allocation

    def test_operand_points_into_the_owners_own_site(self):
        # literal addresses only: the release before the lever pointed the operand at the retail .rdata float 0x4E73E4
        image, retail = XbeImage(self.fresh), XbeImage(self.retail)
        target = struct.unpack("<I", image.read(0x1083F8, 4))[0]
        self.assertTrue(EVENT_SITE[0] <= target and target + 4 <= EVENT_SITE[1], hex(target))
        self.assertEqual(image.read(target, 4), struct.pack("<f", 0.890))   # the fitted centre
        self.assertEqual(image.read(target - 2, 2), b"\xeb\x04")

    def test_the_constant_is_what_gets_written(self):
        with mock.patch.object(pp, "SIM_CENTRE", 0.891, create=True):
            tuned, receipt = pp.apply(self.retail)
            self.assertEqual(pp.status(tuned), "applied")
            self.assertEqual(pp.status(self.fresh), "foreign")       # another centre is not this release's install
            self.assertEqual(receipt["sim_centre"], _f32(0.891))
        self.assertEqual(XbeImage(tuned).read(pp.SIM_CENTRE_VA, 4), struct.pack("<f", 0.891))
        changed = [i for i, (a, b) in enumerate(zip(self.fresh, tuned)) if a != b]
        image = XbeImage(tuned)
        float_offset = image.offset(pp.SIM_CENTRE_VA, 4)
        text = next(s for s in image.sections if s.name == ".text")
        digest = range(text.header + 36, text.header + 56)
        self.assertTrue(set(changed) <= set(range(float_offset, float_offset + 4)) | set(digest), changed)
        for bad in (0.8, 0.95, float("nan"), True, "0.87"):
            with self.subTest(centre=bad), mock.patch.object(pp, "SIM_CENTRE", bad), \
                    self.assertRaises(pp.PassProtectionError):
                pp.sim_edits()

    def test_retail_from_both_forms(self):
        legacy = pp._write_sim(pp.restore_sim(self.fresh)[0], "retail", "legacy")[0]
        self.assertEqual(pp.status(legacy), "legacy")
        played_only = pp._apply_owner(self.retail)[0]
        for form, payload in (("applied", self.fresh), ("legacy", legacy)):
            with self.subTest(form=form):
                restored, receipt = pp.restore_sim(payload)
                self.assertEqual(receipt["restored_from"], form)
                self.assertEqual(restored, played_only)
                self.assertEqual(pp.status(restored), "partial")
                image, retail = XbeImage(restored), XbeImage(self.retail)
                for _name, va, before, _after in pp.sim_sites(pp._owner_va(restored)):
                    self.assertEqual(image.read(va, len(before)), retail.read(va, len(before)))
                self.assertEqual(pp.apply(restored)[0], self.fresh)
                self.assertEqual(pp.restore_sim(restored)[0], restored)


class SackCentreLegacyInstalls(unittest.TestCase):
    """Lever 1 on the executables v0.8, v0.9 and the beta 81 base actually shipped or built (old form)."""

    @classmethod
    def setUpClass(cls):
        cls.installs = legacy_installs()
        if not cls.installs:
            raise unittest.SkipTest("no shipped legacy pass-protection executable is present")

    def test_old_form_is_recognised_upgraded_in_place_and_restored(self):
        for name, old in self.installs:
            with self.subTest(source=name):
                image = XbeImage(old)
                self.assertEqual(image.read(0x1083F8, 4), struct.pack("<I", pp.LEGACY_CENTRE_VA))
                self.assertEqual(pp.status(old), "legacy")
                self.assertEqual(pp.read_settings(old)["sim_centre"], _f32(0.866))
                # LEGACY_SIM_EDITS is exactly what that release wrote: restore and rewrite give the same bytes
                partial = pp.restore_sim(old)[0]
                self.assertEqual(pp._write_sim(partial, "retail", "legacy")[0], old)
                new, receipt = pp.apply(old)
                self.assertEqual((pp.status(new), receipt["upgraded_from"]), ("applied", "legacy"))
                self.assertEqual(sorted(e["label"] for e in receipt["edits"]), ["sim_event_centre", "sim_event_chance"])
                self.assertEqual(pp.apply(new)[1]["status"], "already_applied")
                # only the jump, the float and the operand change, plus the .text digest
                changed = {i for i, (a, b) in enumerate(zip(old, new)) if a != b}
                text = next(s for s in image.sections if s.name == ".text")
                allowed = set(range(image.offset(0x1083AE, 6), image.offset(0x1083AE, 6) + 6))
                allowed |= set(range(image.offset(0x1083F8, 3), image.offset(0x1083F8, 3) + 3))
                self.assertEqual(changed - set(range(text.header + 36, text.header + 56)), allowed)
                self.assertEqual(len(new), len(old))
                self.assertEqual(pp.restore_sim(new)[0], partial)          # Retail from either form


@unittest.skipUnless(uc is not None, "unicorn is not installed")
class SackCentreSimulation(unittest.TestCase):
    """The game's own instructions on both forms: the event site runs past the float, and v = o + centre is bit-equal."""

    @classmethod
    def setUpClass(cls):
        retail = retail_xbe()
        cls.new = pp.apply(retail)[0]
        cls.legacy = pp._write_sim(pp.restore_sim(cls.new)[0], "retail", "legacy")[0]
        shipped = legacy_installs()
        cls.shipped = shipped[0][1] if shipped else None
        with mock.patch.object(pp, "SIM_CENTRE", 0.891):
            cls.tuned = pp.apply(retail)[0]
        with mock.patch.object(pp, "SIM_CENTRE", 0.866):     # the lever as built: the legacy value
            cls.at_legacy = pp.apply(retail)[0]

    def test_event_site_reaches_the_retail_continuation_with_the_same_frame(self):
        for x in (-0.31, -0.07, 0.0, 0.0425, 0.19):
            frame = _frame(x18=x, x28=1.5)
            results = {name: _emulate(payload, *EVENT_SITE, frame)
                       for name, payload in (("new", self.new), ("legacy", self.legacy), ("tuned", self.tuned))}
            self.assertEqual(results["new"], results["legacy"], x)
            self.assertEqual(results["tuned"], results["new"], x)
            eip, after = results["new"]
            self.assertEqual(eip, EVENT_SITE[1])
            self.assertEqual(struct.unpack_from("<f", after, 0x18)[0], _f32(_f32(x) * 0.75))

    def test_centre_value_is_bit_identical_at_0866_and_follows_the_constant(self):
        moved = 0
        for k in range(-200, 201, 9):
            o = k / 1000
            frame = _frame(x18=o)
            built = _emulate(self.at_legacy, *CENTRE_ADD, frame)[1]
            self.assertEqual(built, _emulate(self.legacy, *CENTRE_ADD, frame)[1], o)
            if self.shipped is not None:
                self.assertEqual(built, _emulate(self.shipped, *CENTRE_ADD, frame)[1], o)
            self.assertEqual(struct.unpack_from("<f", built, 0x14)[0], _f32(_f32(o) + _f32(0.866)), o)
            new = _emulate(self.new, *CENTRE_ADD, frame)[1]
            v = struct.unpack_from("<f", new, 0x14)[0]
            self.assertEqual(v, _f32(_f32(o) + _f32(0.890)), o)        # the fitted default
            tuned = struct.unpack_from("<f", _emulate(self.tuned, *CENTRE_ADD, frame)[1], 0x14)[0]
            self.assertEqual(tuned, _f32(_f32(o) + _f32(0.891)), o)
            moved += tuned != v
        self.assertEqual(moved, len(range(-200, 201, 9)))


def _tables(rate=code.DEFAULT_RATE):
    bank = bytearray(code.CODE_SIZE)
    code._configure_tables(bank, rate)
    return bank


def _floats(bank, label):
    return struct.unpack_from("<256f", bank, code.LABELS[label])


class QuarterbackChanceScale(unittest.TestCase):
    """Lever 2: a quarterback-only multiplier; every other byte of the bank stays."""

    QB_TABLES = ("ordinary_thresholds", "special_thresholds")

    def test_default_scale_leaves_the_tables_exactly_as_before(self):
        # The shipped scale is the combined calibration's fitted 1.06 (pos3/COMBINED_PLAN.md section 12); at 1.0 the
        # tables are exactly the ones before the lever existed.
        self.assertEqual(code.QB_CHANCE_SCALE, 1.06)
        with mock.patch.object(code, "QB_CHANCE_SCALE", 1.0):
            for rate, digest in TABLES_BEFORE.items():
                self.assertEqual(_sha(_tables(rate)), digest, rate)

    def test_only_the_quarterback_tables_scale(self):
        spans = set()
        for label in self.QB_TABLES:
            spans |= set(range(code.LABELS[label], code.LABELS[label] + 1024))
        for rate in (310, 155):
            with mock.patch.object(code, "QB_CHANCE_SCALE", 1.0, create=True):   # unscaled: the shipped scale is 1.06
                before = _tables(rate)
            for scale in (0.8, 0.25 / 0.31, 1.3):
                with self.subTest(rate=rate, scale=scale), mock.patch.object(code, "QB_CHANCE_SCALE", scale, create=True):
                    after = _tables(rate)
                    for label in self.QB_TABLES:
                        for old, new in zip(_floats(before, label), _floats(after, label)):
                            self.assertAlmostEqual(new, old * scale, delta=abs(old * scale) * 2e-7 + 1e-30)
                    self.assertNotEqual(_floats(before, "ordinary_thresholds"), _floats(after, "ordinary_thresholds"))
                    other = [i for i in range(len(after)) if before[i] != after[i] and i not in spans]
                    # positions (Custom's X / 0.310 included), stability, gain and length tables unchanged
                    self.assertEqual(other, [])


class PassingLevel(unittest.TestCase):
    """Lever 3: one constant drives the accuracy gain table and the base multiplier."""

    def test_default_is_the_slice_1_level_and_bytes_are_unchanged(self):
        self.assertEqual(code.PASSING_LEVEL, .982)
        with mock.patch.object(code, "QB_CHANCE_SCALE", 1.0):   # lever 2's frozen 1.06 moves only the two QB tables
            bank = _tables()
        self.assertEqual(_sha(bank), TABLES_BEFORE[310])
        self.assertEqual(struct.unpack_from("<f", bank, code.GAIN_CONSTANTS + 4)[0], _f32(.982))
        self.assertEqual(struct.unpack_from("<f", bank, code.GAIN_TABLE + 4 * 100)[0], _f32(.982 * 1.065))

    def test_the_constant_drives_both_places_and_nothing_else(self):
        before = _tables()
        with mock.patch.object(code, "PASSING_LEVEL", 1.0, create=True):
            after = _tables()
        table = set(range(code.GAIN_TABLE, code.GAIN_TABLE + 4 * 101)) | set(range(code.GAIN_CONSTANTS + 4, code.GAIN_CONSTANTS + 8))
        self.assertEqual([i for i in range(len(after)) if before[i] != after[i] and i not in table], [])
        self.assertEqual(struct.unpack_from("<f", after, code.GAIN_CONSTANTS + 4)[0], 1.0)
        self.assertEqual(struct.unpack_from("<f", after, code.GAIN_CONSTANTS)[0], _f32(.77))   # red-zone value stays
        for accuracy in (0, 92, 95, 98, 100):
            position = min(1.0, max(0.0, (accuracy - 92) / 6))
            self.assertEqual(struct.unpack_from("<f", after, code.GAIN_TABLE + 4 * accuracy)[0],
                             _f32(1.0 * (.935 + .130 * position ** 4)))
            self.assertEqual(struct.unpack_from("<f", before, code.GAIN_TABLE + 4 * accuracy)[0],
                             _f32(.982 * (.935 + .130 * position ** 4)))


class RevisionFourBank(unittest.TestCase):
    """Unfrozen, the quarterback owner writes the lever-free head's executable byte for byte; frozen, it differs only in
    the levers' bytes."""

    def test_realistic_on_the_base_is_the_lever_free_build_plus_the_frozen_levers(self):
        root = os.environ.get("NFL2K5_B81_STABILITY_FIXTURES")
        path = Path(root or "") / "default.xbe"
        if not root or not path.is_file():
            self.skipTest("the slice 1 base executable bda1e4a4 is absent")
        base = path.read_bytes()
        self.assertEqual(_sha(base), BASE_XBE)
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_sim_scoring as scoring
        self.assertEqual((code.QB_CHANCE_SCALE, code.PASSING_LEVEL, scoring.BREAKAWAY_STOP_BEYOND), (1.06, .982, 68.0))
        with mock.patch.object(code, "QB_CHANCE_SCALE", 1.0), mock.patch.object(scoring, "BREAKAWAY_STOP_BEYOND", 72.0):
            free = qb.apply(base, "realistic")[0]
        self.assertEqual(_sha(free), LEVER_FREE_XBE)
        realistic = qb.apply(base, "realistic")[0]
        self.assertEqual(_sha(realistic), REALISTIC_XBE)
        image = XbeImage(realistic)
        bank = next(r for r in space.layout(realistic)["allocations"] if r["owner"] == qb.OWNER and r["kind"] == "code")["va"]
        allowed = set()
        for va, size in ((bank + code.LABELS["ordinary_thresholds"], 1024), (bank + code.LABELS["special_thresholds"], 1024),
                         (scoring.BREAKAWAY_VA, scoring.BREAKAWAY_SIZE), (0x150604C, 32)):
            at = image.offset(va, size)
            allowed |= set(range(at, at + size))
        allowed |= set(range(0xDB4, 0xDB4 + 32))
        for section in image.sections:
            allowed |= set(range(section.header + 36, section.header + 56))
        changed = {i for i, (a, b) in enumerate(zip(free, realistic)) if a != b}
        self.assertTrue(changed and changed <= allowed, sorted(changed - allowed)[:10])
        # and the in-place route's extra step changes only pass protection's own bytes
        upgraded = pp.apply(realistic)[0]
        self.assertEqual(qb.read_settings(upgraded), qb.read_settings(realistic))
        self.assertEqual(pp.restore_sim(upgraded)[0], pp.restore_sim(realistic)[0])


class StudioRoutes(unittest.TestCase):
    """The single-setting edit route upgrades a legacy pass protection for Realistic and Custom, never for Retail."""

    def test_edit_route_upgrades_the_legacy_owner_for_realistic_and_custom_only(self):
        from mod_editor.core import mod_build, nfl2k5_sim_qb_injuries as qb, nfl2k5_sim_realism as simulator
        from mod_editor.core import nfl2k5_cpu_kick_aim as aim
        root = os.environ.get("NFL2K5_B81_STABILITY_FIXTURES")
        path = Path(root or "") / "default.xbe"
        if not root or not path.is_file():
            self.skipTest("the slice 1 base executable bda1e4a4 is absent")
        base = path.read_bytes()
        self.assertEqual(pp.status(base), "legacy")
        for mode, rate in (("realistic", .310), ("custom", 0.155), ("retail", .310)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                plan = mod_build.sim_qb_disc_edit(str(Path(folder) / "in.iso"), str(Path(folder) / "out.iso"), mode,
                                                  custom_rate=rate)
                receipt = {"steps": []}
                self.assertTrue(mod_build._edit_installed_sim_qb(plan, plan.source, plan.target, base, receipt,
                                                                  lambda *_: None, preflight=True, consume=False,
                                                                  reference=None))
                update = receipt["sim_qb_source_update"]
                upgrade = mode != "retail"
                self.assertEqual(update["pass_protection_upgraded"], upgrade)
                expected = simulator.apply(base)[0] if simulator.status(base) == "legacy" and upgrade else base
                expected = pp.apply(expected)[0] if upgrade else expected
                expected = qb.apply(expected, mode, custom_rate=rate)[0]
                # since 7c64ec2ca the route adds the CPU kick aim repair in every mode (the base carries the kicking fixes)
                self.assertEqual(aim.status(expected), "retail")
                expected = aim.apply(expected)[0]
                # b81 rookie-faces: and rookie faces' current revision (the base has the v0.9 one), before the pool
                expected, faces = mod_build._rookie_faces_upgrade(expected)
                self.assertEqual(update["rookie_faces_upgraded"], faces is not None)
                # b81 history-pool: and this release's career history pool in every mode (the base has the v0.9 one)
                expected, history = mod_build._history_pool_upgrade(expected)
                self.assertIsNotNone(history)
                self.assertTrue(update["history_pool_upgraded"])
                self.assertEqual(update["result_sha256"], _sha(expected))
                self.assertEqual(pp.status(expected), "applied" if upgrade else "legacy")

    def test_build_panel_offers_the_legacy_owner_as_an_update(self):
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui import build_panel_qt
        app = QApplication.instance() or QApplication([])
        self.assertEqual(build_panel_qt.LEGACY_UPGRADE_KEYS.get("pass_protection"), "pass protection")
        panel = build_panel_qt.BuildPanel()
        try:
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "v09.xiso.iso"
                source.write_bytes(b"x" * 4096)
                state = {key: "retail" for key in panel._boxes()}
                state.update(path=str(source), container="xiso", throw=None, speed_threshold="retail",
                             pass_protection="legacy")
                panel.apply_state(state)
                app.processEvents()
                box = panel._boxes()["pass_protection"]
                self.assertTrue(box.isEnabled())
                self.assertEqual(panel._badges["pass_protection"].text(), "Needs update")
                self.assertIn("pass protection: older revision (needs update)", panel.source_status.text())
        finally:
            panel.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
