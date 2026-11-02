"""b780 b-clock: modern CPU clock management (nfl2k5_cpu_clock2), the owner's bytes, refusals and Studio wiring.

The game behaviour (the native clock routines replayed before and after the owner) is in
``test_nfl2k5_cpu_clock2_unicorn.py``. Tests that need the pinned USA retail default.xbe skip without it.
"""
from pathlib import Path
import hashlib
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_clock2 as clock2  # noqa: E402
from mod_editor.core import nfl2k5_cpu_clock2_code as assembly  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit, retail_xbe  # noqa: E402


class TemplateTests(unittest.TestCase):
    def test_owner_is_the_last_late_owner_with_one_code_allocation(self):
        self.assertEqual(clock2.OWNER, "nfl2k5_cpu_clock2")
        self.assertEqual(clock2.REQUESTS, ((clock2.OWNER, "code", clock2.CODE_SIZE, 16),))
        self.assertEqual(space.LATE_OWNERS[-1], clock2.OWNER)
        self.assertLessEqual(len(assembly.CODE), clock2.CODE_SIZE)
        self.assertEqual(clock2.CODE_SIZE % 16, 0)

    def test_relocations_and_labels_are_complete(self):
        names = {r[2] for r in assembly.RELOCATIONS} - {"code"}
        self.assertEqual(names, set(clock2.SYMBOLS))
        for _, _, _, _, label in clock2.SITES + (clock2.OT_SITE,):
            self.assertIn(label, assembly.LABELS)
        for offset, kind, _, _ in assembly.RELOCATIONS:
            self.assertIn(kind, (1, 2))
            self.assertLessEqual(offset + 4, len(assembly.CODE))

    def test_code_relocates_to_each_call_target(self):
        va = 0x14DA000
        code = clock2.code_for(va)
        self.assertEqual(len(code), clock2.CODE_SIZE)
        self.assertEqual(code[len(assembly.CODE):], b"\xcc" * (clock2.CODE_SIZE - len(assembly.CODE)))
        symbols = dict(clock2.SYMBOLS, code=va)
        for offset, kind, symbol, _ in assembly.RELOCATIONS:
            value = struct.unpack_from("<I", code, offset)[0]
            if kind == 2:
                target = (va + offset + 4 + struct.unpack("<i", struct.pack("<I", value))[0]) & 0xFFFFFFFF
                self.assertEqual(target, symbols[symbol], (offset, symbol))
            else:
                self.assertTrue(va <= value < va + len(assembly.CODE) or value == symbols[symbol], (offset, symbol))
        # the constants block at the end of the template
        tail = struct.unpack("<8f", assembly.CODE[-32:])
        self.assertEqual(tail[:6], (600.0, 300.0, 120.0, 60.0, 15.0, 0.0))

    def test_sites_are_jumps_or_calls_into_the_allocation(self):
        va = 0x14DA000
        rows = clock2.sites(va, overtime=True)
        self.assertEqual([r[0] for r in rows], [s[0] for s in clock2.SITES] + ["overtime_window"])
        for (name, site, before, after), (_, _, pin, opcode, label) in zip(rows, clock2.SITES + (clock2.OT_SITE,)):
            self.assertEqual(before, bytes.fromhex(pin))
            self.assertEqual(len(after), len(before))
            self.assertEqual(after[0], opcode, name)
            self.assertEqual(site + 5 + struct.unpack_from("<i", after, 1)[0], va + assembly.LABELS[label], name)
            self.assertEqual(after[5:], b"\x90" * (len(before) - 5), name)
        self.assertEqual(len(clock2.sites(va)), len(clock2.SITES))

    def test_template_matches_the_assembler_when_available(self):
        if shutil.which("as") is None:
            self.skipTest("GNU as is a development tool only")
        result = subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_cpu_clock2_assemble.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = clock2.apply(cls.retail)
        cls.overtime, cls.ot_receipt = clock2.apply(cls.retail, overtime=True)

    def test_site_bytes_and_guards_match_retail(self):
        image = XbeImage(self.retail)
        for _, site, pin, _, _ in clock2.SITES + (clock2.OT_SITE,):
            self.assertEqual(image.read(site, len(pin) // 2), bytes.fromhex(pin), hex(site))
        for va, size, digest in clock2.GUARDS:
            self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest, hex(va))
        self.assertEqual(clock2.status(self.retail), "retail")
        self.assertIsNone(clock2.read_settings(self.retail))

    def test_apply_status_settings_and_idempotence(self):
        self.assertEqual(clock2.status(self.patched), "applied")
        self.assertEqual(clock2.read_settings(self.patched), {"overtime": False})
        self.assertEqual(clock2.read_settings(self.overtime), {"overtime": True})
        self.assertEqual([e["label"] for e in self.receipt["edits"]], [s[0] for s in clock2.SITES])
        self.assertEqual(self.ot_receipt["edits"][-1]["label"], "overtime_window")
        again, receipt = clock2.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(clock2.verify(self.overtime, overtime=True)["settings"], {"overtime": True})
        with self.assertRaises(clock2.CpuClock2Error):
            clock2.verify(self.patched, overtime=True)

    def test_overtime_choice_needs_a_clean_base(self):
        with self.assertRaises(clock2.CpuClock2Error):
            clock2.apply(self.patched, overtime=True)
        with self.assertRaises(clock2.CpuClock2Error):
            clock2.apply(self.overtime, overtime=False)

    def test_only_the_sites_and_the_allocation_change(self):
        row = clock2.allocations(self.overtime)
        image, base = XbeImage(self.overtime), XbeImage(self.retail)
        self.assertEqual(image.read(row["va"], clock2.CODE_SIZE), clock2.code_for(row["va"]))
        for name, site, before, after in clock2.sites(row["va"], overtime=True):
            self.assertEqual(image.read(site, len(after)), after, name)
        # every guarded routine outside the sites is still byte-identical to retail
        for va, size, _ in clock2.GUARDS:
            blob, retail = bytearray(image.read(va, size)), base.read(va, size)
            for _, site, before, _ in clock2.sites(row["va"], overtime=True):
                if va <= site < va + size:
                    blob[site - va:site - va + len(before)] = before
            self.assertEqual(bytes(blob), retail, hex(va))

    def test_foreign_site_guard_or_code_refuses(self):
        row = clock2.allocations(self.patched)
        cases = {"site": (0x206ED9, b"\x90" * 5),                      # a hook site
                 "guard": (0x2D3420, b"\x90"),                        # inside a guarded routine, not a site
                 "code": (row["va"] + 3, b"\x90"),                    # the owner's own code
                 "late window": (0x205FE0, bytes.fromhex("e9fbffffff"))}   # an overtime hook that is not ours
        for label, (va, content) in cases.items():
            bad = repin_edit(self.patched, va, content)
            self.assertEqual(clock2.status(bad), "foreign", label)
            with self.assertRaises(ValueError, msg=label):   # CpuClock2Error, or the allocator's own seal refusal
                clock2.apply(bad)
        half = repin_edit(self.retail, 0x188614, clock2.sites(0x14DA000)[6][3])
        self.assertEqual(clock2.status(half), "foreign")
        mixed = repin_edit(self.patched, 0x20A79B, bytes.fromhex("e840b8ffff"))   # one hook back to retail
        self.assertEqual(clock2.status(mixed), "foreign")

    def test_normalized_sites(self):
        self.assertEqual(clock2.normalized_sites(self.retail), [])
        rows = clock2.normalized_sites(self.overtime)
        self.assertEqual(len(rows), len(clock2.SITES) + 1)

    def test_cli_status(self):
        import io
        import contextlib
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default.xbe"
            path.write_bytes(self.patched)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(clock2.main(["status", str(path)]), 0)
        self.assertIn('"applied"', out.getvalue())


class CompositionTests(unittest.TestCase):
    """The clock neighbours: Modern 2 (and its late companion), the coach AI, the third-down owner, Decided clock and
    Accelerated clock. One canonical request union; every order leaves every owner applied and replays exactly."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_cpu_money_downs as money
        from mod_editor.core import nfl2k5_coach_ai as coach_ai
        from mod_editor.core import nfl2k5_cpu_third_down as third_down
        from mod_editor.core import nfl2k5_decided_clock as decided
        from mod_editor.core import nfl2k5_accelerated_clock as accelerated
        retail = retail_xbe()
        union = (money.REQUESTS + money.LATE_REQUESTS + coach_ai.REQUESTS + third_down.REQUESTS + decided.REQUESTS
                 + accelerated.REQUESTS + clock2.REQUESTS)
        cls.seed, _ = space.apply(retail, union, scaleout=True)

        class Money:
            OWNER = money.OWNER
            status = staticmethod(money.status)

            @staticmethod
            def apply(payload):
                return money.apply(payload, level="modern2")

        class Accelerated:
            OWNER = accelerated.OWNER
            status = staticmethod(accelerated.status)

            @staticmethod
            def apply(payload):
                return accelerated.apply(payload, enabled=True, minimum_seconds=20)

        class Clock:
            OWNER = clock2.OWNER
            status = staticmethod(clock2.status)

            @staticmethod
            def apply(payload):
                return clock2.apply(payload, overtime=True)

        cls.owners = (Money, coach_ai, third_down, decided, Accelerated, Clock)

    def compose(self, order):
        result = self.seed
        for owner in order:
            result, _ = owner.apply(result)
        for owner in self.owners:
            self.assertEqual(owner.status(result), "applied", owner.OWNER)
            self.assertEqual(owner.apply(result)[0], result, owner.OWNER)
        return result

    def test_clock_owner_first_or_last_gives_the_same_image(self):
        first = self.compose(self.owners[-1:] + self.owners[:-1])
        last = self.compose(self.owners)
        self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(last).digest())
        self.assertEqual(clock2.read_settings(last), {"overtime": True})


class StudioWiringTests(unittest.TestCase):
    def test_presets_settings_and_validation(self):
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("cpu_clock2", settings.FEATURE_KEYS)
        self.assertIn("cpu_clock2_overtime", settings.FEATURE_KEYS)
        values = {name: (preset["cpu_clock2"], preset["cpu_clock2_overtime"]) for name, preset in mod_build.PRESETS.items()}
        self.assertEqual(values, {"softdrink_basic": (False, False), "softdrink_advanced": (True, True),
                                  "softdrink_experimental": (True, True)})
        self.assertIn(("nfl2k5_cpu_clock2", "Modern CPU clock management"),
                      [(m, label) for m, label, _ in mod_build._LATE_OWNER_OPTIONS])
        plan = mod_build.BuildPlan(Path("in.iso"), Path("out.iso"), cpu_clock2=False, cpu_clock2_overtime=True)
        self.assertEqual(mod_build.validate_plan(plan),
                         ["Modern CPU clock management in overtime needs Modern CPU clock management: turn it on too."])
        self.assertEqual(mod_build.validate_plan(mod_build.BuildPlan(Path("in.iso"), Path("out.iso"), cpu_clock2=True,
                                                                     cpu_clock2_overtime=True)), [])
        state = settings.build_settings(dict(cpu_clock2=True, cpu_clock2_overtime=False))
        self.assertEqual((state["cpu_clock2"], state["cpu_clock2_overtime"]), (True, False))

    def test_build_panel_offers_both_choices(self):
        try:
            from mod_editor.gui import build_panel_qt as panel
        except ImportError as exc:      # pragma: no cover - Qt missing
            self.skipTest(f"Qt build panel unavailable: {exc}")
        options = {key: (caption, text) for key, caption, text in panel.BUILD_OPTIONS}
        self.assertEqual(options["cpu_clock2"], (clock2.BUILD_CAPTION, clock2.HELP_TEXT))
        self.assertEqual(options["cpu_clock2_overtime"], (clock2.OT_CAPTION, clock2.OT_HELP_TEXT))
        self.assertEqual(panel.ANNIVERSARY_DEPENDENCIES["cpu_clock2_overtime"], ("cpu_clock2",))
        for caption, text in options.values():
            self.assertNotIn("—", caption + text)

    def test_plain_text_has_no_em_dash(self):
        for text in (clock2.BUILD_CAPTION, clock2.HELP_TEXT, clock2.OT_CAPTION, clock2.OT_HELP_TEXT):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)


if __name__ == "__main__":
    unittest.main()
