"""Owned BASE/TU witnesses; no retail fixture bytes are emitted."""
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import apf2k8_charge_abilities as p
from mod_editor.core.apf2k8_xex import reconstruct_tu
from tools.apf_charge_abilities_probe import ChargeMachine, load_owned_image, ROSTER

ROOT = Path(__file__).resolve().parents[2]
XEX = Path(os.environ.get("APF_RETAIL_XEX", ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"))
TU = Path(os.environ.get("APF_RETAIL_TU", "/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082"))


class ChargeNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(f"Optional native dependency absent: {exc}")
        if not XEX.is_file():
            raise unittest.SkipTest("Owned APF_RETAIL_XEX absent")
        base, cls.metadata = load_owned_image(XEX)
        cls.images = [base]
        if TU.is_file():
            updated, _ = reconstruct_tu(base, XEX.read_bytes(), TU.read_bytes())
            cls.images.append(updated)

    def test_reserved_code_page_and_exact_revert(self):
        source = XEX.read_bytes()
        security = int.from_bytes(source[16:20], "big")
        page = (p.CAVE - p.IMAGE_BASE) // 65536
        self.assertEqual(struct.unpack_from(">I", source, security + 0x184 + page * 24)[0], 0x11)
        for image, profile in zip(self.images, p.PROFILES):
            doc = p.PatchDocument(profile, True)
            self.assertEqual(p.revert_image(p.apply_image(image, doc), doc), image)
            self.assertFalse(any(image[p.CAVE-p.IMAGE_BASE:p.CAVE_LIMIT-p.IMAGE_BASE]))
            references = [offset * 4 + p.IMAGE_BASE for offset, (word,) in enumerate(struct.iter_unpack(">I", image))
                          if p.CAVE <= word < p.CAVE_LIMIT]
            self.assertEqual(references, [])
            print("CHARGE_PINS", json.dumps(doc.receipt, sort_keys=True), flush=True)

    def test_retail_and_patched_full_charge_state_machine(self):
        for image, profile in zip(self.images, p.PROFILES):
            original, patched = ChargeMachine(image), ChargeMachine(image, patched=True)
            rows = []
            for tier in (0, 2, 4, 6):
                for abilities in ((), ("finesse",), ("ankle_breaker",), ("club",)):
                    results = []
                    for m in (original, patched):
                        m.configure_player(tier, abilities)
                        result = m.charge()
                        self.assertLess(result["peak_instructions"], 2_000)
                        results.append(result["maximum"])
                    self.assertEqual(results, [2 if tier == 2 else 1, 2 if abilities else 1])
                    rows.append({"tier": tier, "abilities": abilities, "before_after": results})
            print("CHARGE_TABLE", profile.name, json.dumps(rows), flush=True)

    def test_every_packed_ability_and_unrelated_bit(self):
        selected = {(offset, bit) for _, offset, bit in p.CHARGED_ABILITIES}
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            for tier in (0, 2, 4, 6):
                for offset in range(23, 45):
                    for bit in range(8):
                        m.configure_player(tier)
                        m.cpu.mem_write(ROSTER + offset, bytes([1 << bit]))
                        expected = 2 if (offset, bit) in selected else 1
                        self.assertEqual(m.charge()["maximum"], expected, (profile.name, tier, offset, bit))

    def test_qb_gate_and_passing_mode_qualification(self):
        for image, profile in zip(self.images, p.PROFILES):
            for patched in (False, True):
                m = ChargeMachine(image, patched=patched)
                for tier in (0, 2, 4, 6):
                    for abilities in ((), ("finesse",), ("laser_arm",), ("rocket_arm",), ("laser_arm", "rocket_arm")):
                        record = m.configure_player(tier, abilities, qb=True)
                        expected = p.maximum_charge(record, qb_passing=True) if patched else (1 if record[43] & 12 else 0)
                        self.assertEqual(m.charge()["maximum"], expected)
                        m.configure_player(tier, abilities, qb=True, passing=False)
                        expected = p.maximum_charge(record) if patched else (2 if tier == 2 else 1)
                        self.assertEqual(m.charge()["maximum"], expected)
            print("CHARGE_QB", profile.name, "passing retail arms=1/no-arms=0; patched arms=2/no-arms=0; runner mode separately verified", flush=True)

    def test_real_caller_cpu_bypass(self):
        for image, profile in zip(self.images, p.PROFILES):
            for patched in (False, True):
                m = ChargeMachine(image, patched=patched)
                for controller, selected, expected in ((0, False, True), (-1, False, False), (-1, True, True)):
                    m.configure_player(4, ("club",))
                    self.assertEqual(m.caller(controller=controller, selected_auto=selected), expected)
            print("CHARGE_CALLER", profile.name, "controller!=-1 enters; CPU -1 skips unless selected automation helper is true", flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
