"""mc2 native repair: pinned inputs only, Studio-equal owner, idempotent replay and declared scope."""
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import mc2_repair as repair, sp1_repair

DISC_1013 = Path(os.environ.get("NFL2K5_IC1_BASE", "/media/noah/Storage/2K5 Discs/"
                                "SOFTDRINK 2K28 v0.6.1 fixes (2026-10-13).xiso.iso"))


def base_xbe():
    """The pinned v0.6.1 (2026-10-13) default.xbe, or None. NFL2K5_V061_XBE names it when it is that file; that variable
    is shared with the sim tests, which take the later (10-20) executable, so any other file there is not used. The
    disc itself (read only; the same variable name mc3 uses for it) is the fallback."""
    candidates = []
    named = os.environ.get("NFL2K5_V061_XBE")
    if named and Path(named).is_file():
        candidates.append(Path(named).read_bytes())
    if DISC_1013.is_file():
        with open(DISC_1013, "rb") as stream:
            candidates.append(repair.disc_xbe(stream))
    return next((raw for raw in candidates if repair.sha(raw) == repair.BASE_XBE_SHA256), None)


SOURCE = base_xbe()


class RefusalTests(unittest.TestCase):
    def test_unknown_input_refuses_before_allocator_or_owner_write(self):
        with patch.object(repair.space, "_seal_scaleout", side_effect=AssertionError("write")):
            with self.assertRaisesRegex(ValueError, "unrecognized"):
                repair.repair(b"not the pinned executable")

    def test_pins_are_complete(self):
        for value in (repair.BASE_XBE_SHA256, repair.REPAIRED_XBE_SHA256, repair.BETA80_XBE_SHA256,
                      repair.OCTOBER17_XBE_SHA256, repair.BASE_DISC_SHA256, repair.BETA80_DISC_SHA256,
                      repair.OCTOBER17_DISC_SHA256):
            self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_replay_authenticates_the_bytes_on_both_sides_of_the_executable(self):
        previous, current = b"old owner", b"new owner"
        prefix, suffix = b"header", b"other files"
        genuine = prefix + current + suffix
        historical = prefix + previous + suffix
        with patch.multiple(repair, XBE_OFFSET=len(prefix), REPAIRED_XBE_SHA256=repair.sha(current),
                            BETA80_XBE_SHA256=repair.sha(previous), BETA80_DISC_SHA256=repair.sha(historical)), \
                patch.object(repair, "build", return_value=(previous, {})), \
                patch.object(sp1_repair, "DISC_SIZE", len(genuine)):
            repair.verify_disc_input(io.BytesIO(genuine), current, repair.sha(genuine))
            for changed in (b"!" + genuine[1:], genuine[:-1] + b"!", genuine + b"!"):
                with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "complete input disc|disc size"):
                    repair.verify_disc_input(io.BytesIO(changed), current, repair.sha(changed))


@unittest.skipUnless(SOURCE is not None, "the private v0.6.1 (2026-10-13) default.xbe is needed (NFL2K5_V061_XBE or the disc, NFL2K5_IC1_BASE)")
class NativeTests(unittest.TestCase):
    def test_repair_matches_studio_owner_and_replays_to_zero(self):
        original = SOURCE
        result, receipt = repair.repair(original)
        self.assertEqual(repair.sha(result), repair.REPAIRED_XBE_SHA256)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        code, state = repair.mode.legacy.allocations(result)
        blob = repair.XbeImage(result).read(code["va"], repair.mode.CODE_SIZE)
        self.assertEqual(blob, repair.studio_owner(result, code, state)[0])
        # The shipped 10-13 executable carries the templates of the neighbouring owners as they were then (draft AI,
        # economy, honors, overtime were revised later), which the whole-image neighbour checks (check_context) cannot
        # recognize; the MyCareer owner itself (allocations, code, state pages, every hook) is validated exactly.
        self.assertEqual(repair.mode.status(result, context=False), "applied")
        again, replay = repair.repair(result)
        self.assertEqual(again, result)
        self.assertEqual(replay["scope"]["changed_bytes"], 0)

    def test_foreign_owner_bytes_refuse(self):
        damaged = bytearray(SOURCE)
        code, _state = repair.mode.legacy.allocations(bytes(damaged))
        damaged[code["raw"]] ^= 1
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            repair.repair(bytes(damaged))

    def test_beta80_repair_upgrades_and_can_authenticate_a_current_disc(self):
        historical, _ = repair.build(SOURCE, previous="beta-80")
        self.assertEqual(repair.sha(historical), repair.BETA80_XBE_SHA256)
        fixed, receipt = repair.repair(historical)
        self.assertEqual(repair.sha(fixed), repair.REPAIRED_XBE_SHA256)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        projected, _ = repair.build(fixed, previous="beta-80")
        self.assertEqual(projected, historical)


class October17Tests(unittest.TestCase):
    def test_original_repair_upgrades_and_requires_its_complete_disc_identity(self):
        path = Path(os.environ.get("B774_MC2_XBE", ""))
        if not path.is_file():
            self.skipTest("B774_MC2_XBE must name the October 17 repaired executable")
        raw = path.read_bytes()
        self.assertEqual(repair.sha(raw), repair.OCTOBER17_XBE_SHA256)
        fixed, receipt = repair.repair(raw)
        self.assertEqual(repair.sha(fixed), repair.REPAIRED_XBE_SHA256)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        repair.verify_disc_input(io.BytesIO(), raw, repair.OCTOBER17_DISC_SHA256)
        with self.assertRaisesRegex(ValueError, "complete input disc"):
            repair.verify_disc_input(io.BytesIO(), raw, repair.BASE_DISC_SHA256)


if __name__ == "__main__":
    unittest.main()
