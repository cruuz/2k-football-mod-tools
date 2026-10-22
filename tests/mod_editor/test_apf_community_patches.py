"""Basileus Maximus' TU 1.1 Xenia patches: relocation, reservations, canonical export, no overlap with ours.

The upstream files are kept verbatim as fixtures.  The relocation proof decodes every
upstream and relocated word with Capstone here, independently of the module's own check.
The optional retail check needs APF_RETAIL_XEX and APF_RETAIL_TU (skipped otherwise).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import apf2k8_community_patches as cp
from mod_editor.core import apf2k8_playcall_patch as pp
from mod_editor.core import apf2k8_fourth_down as fd
from mod_editor.core import apf2k8_charge_abilities as ch
from mod_editor.core import apf2k8_playcall_curves_patch as cv
from mod_editor.core import apf2k8_situation_mask as sm
from mod_editor.core.apf2k8_playcall_model import OFFENSE_CURVE, DEFENSE_CURVE
from mod_editor.core.errors import ValidationError

UPSTREAM = Path(__file__).resolve().parent / "fixtures" / "apf2k8_community_patches_upstream"
XEX = Path(os.environ.get("APF_RETAIL_XEX", ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"))
TU = Path(os.environ.get("APF_RETAIL_TU", ""))
TU_TOP = ROOT / "extracted/All-Pro Football 2K8 (USA)"


def upstream_toml(key):
    return UPSTREAM / f"{key}.patch.toml"


def our_tu_writes():
    """Every address the Studio's own APF Xenia patch generators write on TU 1.1."""
    profile = pp.PROFILES[1]
    out = {}
    def add(owner, words):
        for address, _ in words:
            out.setdefault(address, set()).add(owner)
    add("pass_fetch", pp.PlaycallPatch(profile, pp.assemble_cave(profile.hook), {}).words)
    add("fourth_down", fd.PatchDocument(profile).words)
    for revision in sorted({1, 2, 3, ch.CURRENT_REVISION}):
        add(f"charge_r{revision}", ch.PatchDocument(profile, False, revision).words)
    add("curves", cv.PatchDocument(profile, OFFENSE_CURVE, DEFENSE_CURVE).words)
    for mask_profile in sm.PROFILES:
        document = sm.SituationPatch(mask_profile, sm.encode_data({"O-ManBlock": [[] for _ in range(12)]}))
        if profile.module_hash in document.as_toml():
            add("situations", document.words)
    return out


class UpstreamFixtureTests(unittest.TestCase):
    def test_definitions_are_the_authors_words(self):
        rows = cp.load_definitions()
        self.assertEqual([r.key for r in rows], list(cp.KEYS))
        for row in rows:
            path = upstream_toml(row.key)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row.upstream_sha256)
            parsed = tomllib.loads(path.read_text())
            self.assertEqual((parsed["title_id"], parsed["hash"]), ("54540807", "CEA825F7C2012F5A"))
            patch, = parsed["patch"]
            self.assertEqual(patch["author"], "Basileus Maximus")
            self.assertEqual(patch["name"], row.name)
            self.assertEqual([(w["address"], w["value"]) for w in patch["be32"]], list(row.upstream_words))

    def test_upstream_caves_collide_with_charge_abilities(self):
        """Why the Studio relocates: shipped as-is, two of them overwrite charge revision 4."""
        ours = our_tu_writes()
        hits = {row.key: sum(a in ours for a, _ in row.upstream_words) for row in cp.load_definitions()}
        self.assertEqual(hits, {"play_calling_by_package": 70, "all_packages_in_substitution": 62,
                                "hidden_formations_revealed": 0})
        ranges = cp.reservation_ranges()
        charge = next((s, e) for o, s, e in ranges if o == "apf2k8_charge_abilities_code")
        inside = {row.key: sum(charge[0] <= a < charge[1] for a, _ in row.upstream_words) for row in cp.load_definitions()}
        self.assertEqual(inside, {"play_calling_by_package": 70, "all_packages_in_substitution": 139,
                                  "hidden_formations_revealed": 0})


class RelocationTests(unittest.TestCase):
    def setUp(self):
        from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
        self.md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)

    def text(self, address, word):
        insn, = self.md.disasm(struct.pack(">I", word), address)
        return insn.mnemonic, insn.op_str

    def test_side_by_side_capstone_equivalence(self):
        expected_moves = {"play_calling_by_package": 70, "all_packages_in_substitution": 139,
                          "hidden_formations_revealed": 0}
        for row in cp.load_definitions():
            words = cp.relocate(row)
            moved = 0
            for (a, v), (na, nv) in zip(row.upstream_words, words):
                self.assertEqual(na, row.map(a))
                moved += na != a
                region = row.region(a)
                if region is not None and region.kind == "data":
                    self.assertEqual(nv, v, f"{row.key} data {a:08X}")
                    continue
                (m0, o0), (m1, o1) = self.text(a, v), self.text(na, nv)
                self.assertEqual(m0, m1, f"{row.key} {a:08X}")
                op = v >> 26
                if op in (16, 18) and not v & 2:
                    old_target = int(o0.split(",")[-1].strip(), 16)
                    new_target = int(o1.split(",")[-1].strip(), 16)
                    self.assertEqual(new_target, row.map(old_target), f"{row.key} branch {a:08X}")
                    self.assertEqual(o0.split(",")[:-1], o1.split(",")[:-1])
                elif any(a in pair for pair in row.absolute_pairs):
                    self.assertEqual(o0.split(",")[:-1], o1.split(",")[:-1])
                else:
                    self.assertEqual((v, o0), (nv, o1), f"{row.key} {a:08X} must be byte-identical")
            self.assertEqual(moved, expected_moves[row.key])
            receipt = cp.verify_relocation(row)
            self.assertTrue(receipt["capstone_redecoded"])

    def test_absolute_table_pairs(self):
        row = cp.definition("all_packages_in_substitution")
        words = dict(cp.relocate(row))
        hi, lo = words[0x84D0DC38], words[0x84D0DC3C]  # upstream 0x84D0D5B8/BC: lis r30 / addi r30 (rank table)
        self.assertEqual(self.text(0x84D0DC38, hi), ("lis", "r30, -0x7b2f"))  # 0x84D1
        self.assertEqual(self.text(0x84D0DC3C, lo), ("addi", "r30, r30, -0x2300"))
        self.assertEqual(((hi & 0xFFFF) << 16) - 0x2300 & 0xFFFFFFFF, 0x84D0DD00)
        self.assertEqual(words[0x84D0DD00], 0x01020503)  # first rank-table word moved with it
        family = (words[0x84D0DD68], words[0x84D0DD6C])  # lis r23 / addi r23 -> family table, not moved
        self.assertEqual(((family[0] & 0xFFFF) << 16) + struct.unpack(">h", struct.pack(">H", family[1] & 0xFFFF))[0]
                         & 0xFFFFFFFF, 0x84D0DB00)
        hidden = dict(cp.relocate(cp.definition("hidden_formations_revealed")))
        self.assertEqual(hidden, dict(cp.definition("hidden_formations_revealed").upstream_words))

    def test_hooks_reach_the_relocated_caves(self):
        row = cp.definition("play_calling_by_package")
        words = dict(cp.relocate(row))
        def target(address):
            word = words[address]
            offset = word & 0x03FFFFFC
            return address + (offset - (1 << 26) if offset & (1 << 25) else offset)
        self.assertEqual({a: target(a) for a in (0x84A2DD30, 0x84A2D3E8, 0x84A2DDB4, 0x84A2D428)},
                         {0x84A2DD30: 0x84D0D980, 0x84A2D3E8: 0x84D0D980, 0x84A2DDB4: 0x84D0DA00, 0x84A2D428: 0x84D0DA00})
        self.assertEqual(target(0x84D0D9BC), 0x84A8C4B0)  # cave bl back into the game, unchanged callee
        self.assertEqual(target(0x84D0DAC4), 0x84D0DA80)  # internal stub branch kept its relative offset
        self.assertEqual(words[0x84D0DAC4], 0x4BFFFFBC)

    def test_undeclared_cave_reference_and_stray_words_refused(self):
        from dataclasses import replace
        row = cp.definition("all_packages_in_substitution")
        with self.assertRaisesRegex(ValidationError, "Undeclared absolute"):
            cp.relocate(replace(row, absolute_pairs=row.absolute_pairs[1:]))
        with self.assertRaisesRegex(ValidationError, "no declared region"):
            cp.relocate(replace(row, regions=row.regions[:-1]))
        broken = list(cp.relocate(row))
        index = next(i for i, (a, _) in enumerate(row.upstream_words) if a == 0x84A70468)
        broken[index] = (broken[index][0], broken[index][1] + 4)
        with self.assertRaisesRegex(ValidationError, "wrong target"):
            cp.verify_relocation(row, broken)


class ReservationAndOverlapTests(unittest.TestCase):
    def test_reservations_are_disjoint_and_own_every_cave_word(self):
        spans = sorted((s, e) for _, s, e in cp.reservation_ranges())
        self.assertFalse(any(a[1] > b[0] for a, b in zip(spans, spans[1:])))
        for row in cp.load_definitions():
            receipt = cp.check_reservations(row)
            self.assertEqual(receipt["owners"], list(row.reservation_owners))

    def test_no_write_overlaps_ours_or_each_other(self):
        ours = our_tu_writes()
        seen = {}
        for row in cp.load_definitions():
            for address, _ in cp.relocate(row):
                self.assertNotIn(address, ours, f"{row.key} {address:08X} overlaps {ours.get(address)}")
                self.assertNotIn(address, seen, f"{row.key} and {seen.get(address)} both write {address:08X}")
                seen[address] = row.key
        # Their hook sites are far from every one of our .text hook sites.
        hooks = [a for a in seen if not cp.PADDING_START <= a < cp.PADDING_LIMIT]
        our_text = [a for a in ours if 0x84630000 <= a < cp.PADDING_START]
        self.assertGreater(min(abs(a - b) for a in hooks for b in our_text), 0x1000)


class ExportTests(unittest.TestCase):
    def test_canonical_toml_round_trip_author_and_default_off(self):
        for row in cp.load_definitions():
            document = cp.PatchDocument(row)
            self.assertIs(document.enabled, False)
            payload = document.as_toml().encode()
            parsed = tomllib.loads(payload.decode())
            patch, = parsed["patch"]
            self.assertEqual(patch["author"], "Basileus Maximus")
            self.assertEqual(parsed["hash"], "CEA825F7C2012F5A")
            self.assertNotIn("—", payload.decode())
            self.assertEqual([(w["address"], w["value"]) for w in patch["be32"]], list(cp.relocate(row)))
            self.assertEqual(cp.canonical_payload(payload, row.key)[1], False)
            enabled = cp.PatchDocument(row, True).as_toml().encode()
            self.assertEqual(cp.canonical_payload(enabled, row.key)[1], True)

    def test_upstream_files_are_not_accepted_as_studio_patches(self):
        for row in cp.load_definitions():
            if row.key == "hidden_formations_revealed":
                # Nothing moved: the author's own file is exactly the Studio's enabled copy.
                self.assertIs(cp.parse_payload(upstream_toml(row.key).read_bytes(), row.key).enabled, True)
            else:
                with self.assertRaises(ValidationError):
                    cp.parse_payload(upstream_toml(row.key).read_bytes(), row.key)
            other = next(k for k in cp.KEYS if k != row.key)
            with self.assertRaises(ValidationError):
                cp.parse_payload(cp.PatchDocument(row, True).as_toml().encode(), other)

    def test_upstream_copies_detected_in_a_patches_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "54540807 - x.patch.toml").write_bytes(upstream_toml("play_calling_by_package").read_bytes())
            (folder / "54540807 - y.patch.toml").write_bytes(upstream_toml("hidden_formations_revealed").read_bytes())
            (folder / "ours.patch.toml").write_bytes(cp.PatchDocument(cp.definition("play_calling_by_package"), True).as_toml().encode())
            self.assertEqual(cp.upstream_conflicts(folder), ["54540807 - x.patch.toml"])

    def test_write_patch_receipt(self):
        import tempfile
        row = cp.definition("hidden_formations_revealed")
        with tempfile.TemporaryDirectory() as temp:
            receipt = cp.write_patch(cp.PatchDocument(row, True), Path(temp) / row.filename)
            self.assertEqual(receipt["author"], "Basileus Maximus")
            self.assertEqual(receipt["relocation"]["moved_words"], 0)
            with self.assertRaises(ValidationError):
                cp.write_patch(cp.PatchDocument(row, True), Path(temp) / "wrong.toml")


def _tu_image():
    from mod_editor.core import apf2k8_xex as x
    if not XEX.is_file():
        raise unittest.SkipTest(f"Owned APF default.xex absent: {XEX}; set APF_RETAIL_XEX")
    update = TU if TU.is_file() else x.discover_title_update(XEX.parent) if XEX.parent.is_dir() else None
    if update is None or not Path(update).is_file():
        raise unittest.SkipTest("Owned APF Title Update 1.1 absent; set APF_RETAIL_TU")
    xex = XEX.read_bytes()
    base, _ = x.decode_xex(xex)
    image, _ = x.reconstruct_tu(base, xex, Path(update).read_bytes())
    return image


class RetailImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.image = _tu_image()
        except unittest.SkipTest:
            raise
        except Exception as exc:  # an unreadable optional input is a skip, not a failure
            raise unittest.SkipTest(f"Owned TU 1.1 image unavailable: {exc}")

    def test_hook_originals_match_and_every_cave_is_empty_padding(self):
        self.assertEqual(hashlib.sha256(self.image).hexdigest(), pp.PROFILES[1].sha256)
        for row in cp.load_definitions():
            receipt = cp.verify_image(self.image, cp.PatchDocument(row, True))
            self.assertEqual(receipt["profile"], "tu_1_1")
            for address, _ in cp.relocate(row):
                if cp.PADDING_START <= address < cp.PADDING_LIMIT:
                    self.assertEqual(self.image[address - cp.IMAGE_BASE:address - cp.IMAGE_BASE + 4], bytes(4))
        pe = struct.unpack_from("<I", self.image, 0x3C)[0]
        sections = struct.unpack_from("<H", self.image, pe + 6)[0]
        optional = struct.unpack_from("<H", self.image, pe + 20)[0]
        for i in range(sections):
            at = pe + 24 + optional + 40 * i
            if self.image[at:at + 8].rstrip(b"\0") == b".text":
                size, rva = struct.unpack_from("<2I", self.image, at + 8)
                self.assertEqual(cp.IMAGE_BASE + rva + size, cp.PADDING_START)


if __name__ == "__main__":
    unittest.main()
