"""Depth roles: generated books/XISO offline, plus optional private retail gates."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_depth_roles as d
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core.nfl2k5_formation_play_writer import compile_personnel_categories
from nfl2k5_xiso_fixture import SyntheticXiso

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
RETAIL = EXTRACTION / "ESPN NFL 2K5 (USA)"
XBE = RETAIL / "default.xbe"
YD = codec.YD_CM


def fixture(xs=((-15, 15, 9),), *, ordinals=(2, 0, 1), kind=d.WR) -> bytes:
    """Entirely authored PLAY resource: one group, one codec-built pass.

    xs is each formation's selected role-slot x coordinates in yards. The
    pass is independently valid; CB fixtures only vary the personnel/geometry.
    """
    body = bytearray(insp.BODY_SIZE)
    body[0x0C:0x10] = b"PLAY"
    body[0x20:0x28] = b"p\0l\0b\0\0\0"
    pool = insp.STRING_BASE

    def relative(field, target):
        struct.pack_into("<i", body, field, target - field + 1)

    def name(field, value):
        nonlocal pool
        raw = value.encode("utf-16le") + b"\0\0"
        relative(field, pool)
        body[pool:pool + len(raw)] = raw
        pool += len(raw)

    for field, target in ((0x44, insp.FORMATION_BASE), (0x48, insp.FORMATION_AUX_BASE),
                          (0x60, insp.PLAY_BASE), (0x64, insp.CATEGORY_BASE), (0x68, insp.NODE_BASE)):
        relative(field, target)
    name(0x30, "SYNTHETIC")
    name(insp.CATEGORY_BASE, "Role Group")
    codes = [0, 5, 37, 6, 7, 39, 9, 41, 73, 8, 10]
    slots = list(range(6, 6 + len(ordinals)))
    for slot, ordinal in zip(slots, ordinals):
        codes[slot] = kind | (ordinal << 5)
    body[insp.CATEGORY_BASE + 5:insp.CATEGORY_BASE + 16] = bytes(codes)
    for i, coords in enumerate(xs):
        off = insp.FORMATION_BASE + i * insp.FORMATION_SIZE
        name(off, f"Formation {i}")
        rec = codec.FormationRecord.from_bytes(bytes(body[off:off + insp.FORMATION_SIZE]))
        for slot, x in zip(slots, coords):
            rec.set_position(slot, round(x * YD), 0)
        body[off:off + insp.FORMATION_SIZE] = rec.to_bytes()
        aux = insp.FORMATION_AUX_BASE + i * insp.FORMATION_AUX_SIZE
        for j in range(36):
            struct.pack_into("<H", body, aux + j * 2, 0x7FF)
        for group in range(4):
            struct.pack_into("<H", body, aux + group * 2, 0x8000 | (group << 9))
        # Intentionally nontrivial mask: a category-only writer must preserve it.
        struct.pack_into("<II", body, aux + 0x48, 0xC0, 0x12345)
    positions = [(0, -450), (300, 0), (-300, 0), (0, 0), (150, 0), (-150, 0),
                 (-1400, 0), (1400, 0), (800, -150), (-400, 0), (0, -700)]
    kinds = [0, 5, 5, 6, 7, 7, 9, 9, 9, 8, 10]
    spec = lib.PlaySpec(name="Synthetic Mesh", play_type="pass", positions=positions, kinds=kinds, assignments={})
    lib.default_assignments(spec, concept="Mesh")
    chains = []
    for chain in lib.build_chains(spec):
        nodes = [codec.Node(op, 0, list(values)) for op, values in chain]
        codec.assign_node_flags(nodes)
        chains.append((0, [n.to_bytes() for n in nodes]))
    flags = 0x640E
    for s in range(11):
        chains[s] = (codec.build_descriptor(flags, chains, s, 0), chains[s][1])
    assert codec.validate_play(flags, chains) is None
    name(insp.PLAY_BASE, "Synthetic Mesh")
    struct.pack_into("<I", body, insp.PLAY_BASE + 4, flags)
    count = 0
    for s, (descriptor, nodes) in enumerate(chains):
        struct.pack_into("<I", body, insp.PLAY_BASE + 8 + s * 8, descriptor)
        relative(insp.PLAY_BASE + 12 + s * 8, insp.NODE_BASE + count * 8)
        for node in nodes:
            body[insp.NODE_BASE + count * 8:insp.NODE_BASE + (count + 1) * 8] = node
            count += 1
    struct.pack_into("<IIII", body, 0x34, len(xs), 1, 1, count)
    return struct.pack("<4s7I", b"PLAY", insp.BODY_SIZE, insp.BODY_SIZE, 0, 0, 0, 0, 0) + body


class MemoryArchive:
    def __init__(self, resources):
        self.entries = [type("Entry", (), {"index": i, "size": len(raw), "virtual_offset": i * d.RESOURCE_SIZE})()
                        for i, raw in enumerate(resources)]
        self.payload = bytearray(b"".join(resources))
        self.writes = 0

    def entries_with_head(self, head):
        return [e for e in self.entries if self.read(e.virtual_offset, len(head)) == head]

    def read_entry(self, index):
        entry = self.entries[index]
        return self.read(entry.virtual_offset, entry.size)

    def read(self, offset, size):
        return bytes(self.payload[offset:offset + size])

    def write(self, offset, raw):
        self.writes += 1
        self.payload[offset:offset + len(raw)] = raw
        return len(raw)


class OfflineDepthRolesTests(unittest.TestCase):
    def test_x_z_slot_and_fourth_fifth_outside_in(self):
        for xs, ordinals, expected in [
            ((-15, 15, 9), (2, 0, 1), (0, 1, 2)),
            ((15, -15, -9), (1, 2, 0), (1, 0, 2)),
            ((-15, 15, 12, 9), (3, 2, 0, 1), (0, 1, 3, 2)),
            ((-15, 15, -12, 11, 5), (4, 3, 2, 1, 0), (0, 1, 3, 4, 2)),
        ]:
            with self.subTest(xs=xs):
                raw = fixture((xs,), ordinals=ordinals)
                result = d.normalise(raw)
                codes = lib.category_positions(result.replacement[32:], 0)
                self.assertEqual(tuple(codes[s] >> 5 for s in range(6, 6 + len(xs))), expected)
                self.assertTrue(result.report["gate"]["ok"])
                self.assertEqual(d.normalise(result.replacement).replacement, result.replacement)

    def test_nickel_dime_and_tie_determinism(self):
        for xs, ordinals, expected in [
            ((-15, 15, -10), (0, 1, 3), (0, 1, 2)),
            ((-15, 15, -9, 10), (0, 1, 2, 3), (0, 1, 3, 2)),
            ((-15, 15, -9, 9), (0, 1, 2, 3), (0, 1, 3, 2)),
        ]:
            result = d.normalise(fixture((xs,), ordinals=ordinals, kind=d.CB))
            codes = lib.category_positions(result.replacement[32:], 0)
            self.assertEqual(tuple(codes[s] >> 5 for s in range(6, 6 + len(xs))), expected)
            self.assertEqual(result.report["gate"]["checked"], 1)

    def test_mean_geometry_shared_group_and_tied_formations(self):
        result = d.normalise(fixture(((-9, -15, 15, 9), (-15, 12, 15, 9)), ordinals=(0, 1, 2, 3)))
        codes = lib.category_positions(result.replacement[32:], 0)
        self.assertEqual(codes[9] >> 5, 2)
        self.assertEqual(result.report["gate"]["checked"], 1)
        self.assertEqual(result.report["gate"]["excluded"], 1)
        self.assertTrue(result.report["ambiguous_groups"])

    def test_disagreement_refuses_entire_group_even_ordinary_formations(self):
        raw = fixture(((-9, -15, 15), (-15, 12, 15), (-9, -15, 15)))
        result = d.normalise(raw)
        self.assertEqual(result.replacement, raw)
        self.assertEqual(result.report["refused_groups"][0]["refused_reason"], "disagreeing_inner_slot")
        self.assertGreater(result.report["refused_groups"][0]["max_disagreement_yd"], 2)
        self.assertEqual(result.report["gate"]["excluded"], 3)

    def test_two_yard_tolerance_is_not_rounded_to_whole_yards(self):
        for other, refused in ((10.01, False), (9.98, True)):
            result = d.normalise(fixture(((-5, -15, 15), (-12, other, 15))))
            self.assertEqual(bool(result.report["refused_groups"]), refused)

    def test_special_teams_and_single_sided_groups_are_preserved(self):
        raw = bytearray(fixture())
        raw[32 + insp.CATEGORY_BASE + 5] = 4  # a returner, not a QB
        result = d.normalise(raw)
        self.assertEqual(result.replacement, raw)
        self.assertEqual(result.report["refused_groups"][0]["refused_reason"], "non_offensive_wr_group")
        raw = fixture(((15, 12, 5),))
        result = d.normalise(raw)
        self.assertEqual(result.replacement, raw)
        self.assertEqual(result.report["refused_groups"][0]["refused_reason"], "no_distinct_outside_left_and_right")

    def test_only_role_ordinal_bytes_change_and_link_words_are_exact(self):
        raw = fixture()
        result = d.normalise(raw)
        allowed = {32 + insp.CATEGORY_BASE + 5 + s for s in (6, 7, 8)}
        changed = {i for i, (a, b) in enumerate(zip(raw, result.replacement)) if a != b}
        self.assertEqual(changed, allowed)
        for i in changed:
            self.assertEqual(raw[i] & 31, result.replacement[i] & 31)
        self.assertEqual(d._parse(raw), d._parse(result.replacement))
        self.assertEqual(result.report["all_plays_validated"], 1)

    def test_bad_links_groups_nodes_and_wrappers_fail_before_writing(self):
        mutations = [
            (32 + insp.FORMATION_AUX_BASE, struct.pack("<H", 0)),
            (32 + insp.FORMATION_AUX_BASE, struct.pack("<H", 0x8001)),
            (32 + insp.FORMATION_AUX_BASE + 0x48, struct.pack("<I", 26)),
            (32 + insp.NODE_BASE, b"\xff"),
            (8, struct.pack("<I", 0)),
        ]
        for offset, change in mutations:
            with self.subTest(offset=offset, change=change):
                bad = bytearray(fixture())
                bad[offset:offset + len(change)] = change
                archive = MemoryArchive([fixture(), bad])
                with self.assertRaises((ValueError, d.ValidationError)):
                    d.apply_to_archive(archive, allow_custom=True)
                self.assertEqual(archive.writes, 0)

    def test_category_writer_rejects_out_of_range_or_malformed_requests(self):
        raw = fixture()
        for changes in ({-1: [0] * 11}, {True: [0] * 11}, {1: [0] * 11}, {0: [0] * 10}, {0: [31] * 11}):
            with self.assertRaises(d.ValidationError):
                compile_personnel_categories(raw, changes)

    def test_custom_requires_explicit_opt_in_and_is_idempotent(self):
        raw = fixture()
        self.assertEqual(d.book_status(raw), "foreign")
        archive = MemoryArchive([raw])
        with self.assertRaisesRegex(d.DepthRolesError, "foreign"):
            d.apply_to_archive(archive)
        self.assertEqual(archive.writes, 0)
        self.assertEqual(d.apply_to_archive(archive, allow_custom=True)["changed_bytes"], 3)
        archive.writes = 0
        self.assertEqual(d.apply_to_archive(archive, allow_custom=True)["changed_bytes"], 0)
        self.assertEqual(archive.writes, 0)
        self.assertEqual(d.book_status(archive.read_entry(0)), "foreign", "custom fixed points are not retail pins")

    def test_short_write_rolls_back_previously_written_books(self):
        archive = MemoryArchive([fixture(), fixture()])
        original = bytes(archive.payload)
        write = archive.write
        attempted = 0

        def failing_write(offset, raw):
            nonlocal attempted
            attempted += 1
            return write(offset, raw[:1] if attempted == 2 else raw)

        with patch.object(archive, "write", side_effect=failing_write):
            with self.assertRaisesRegex(d.DepthRolesError, "short write"):
                d.apply_to_archive(archive, allow_custom=True)
        self.assertEqual(archive.payload, original)

    def test_readback_failure_rolls_back_and_failed_rollback_is_reported(self):
        for rollback_fails in (False, True):
            archive = MemoryArchive([fixture()])
            original = bytes(archive.payload)
            write = archive.write

            def corrupt_write(offset, raw):
                result = write(offset, raw)
                if archive.writes == 1 or rollback_fails:
                    archive.payload[offset] ^= 32
                return result

            with patch.object(archive, "write", side_effect=corrupt_write):
                with self.assertRaisesRegex(d.DepthRolesError, "rollback failed" if rollback_fails else "read-back differs"):
                    d.apply_to_archive(archive, allow_custom=True)
            if not rollback_fails:
                self.assertEqual(archive.payload, original)

    def test_synthetic_xiso_and_loose_pack_access_and_windows_io_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = SyntheticXiso(Path(tmp), [(1, fixture()), (2, fixture()), (3, b"tail")],
                                  pack_sizes=(0xA000, 0x12000, 0x10000), pack_sectors=(64, 90, 132))
            # Exercise the real archive reader/writer without pread/pwrite.
            with patch.object(os, "pread", None, create=True), patch.object(os, "pwrite", None, create=True):
                before = d.audit(image.path)
                self.assertEqual(before["totals"]["books"], 2)
                self.assertEqual(before["totals"], d.audit(image.retail_packs)["totals"])
                receipt = d.apply(image.path, allow_custom=True)
                self.assertEqual(receipt["changed_bytes"], 6)
                self.assertTrue(d.audit(image.path)["totals"]["gate_ok"])
                self.assertEqual(d.apply(image.path, allow_custom=True)["changed_bytes"], 0)
                # The complete XISO differs only at reported role ordinals;
                # this also protects default.xbe, directory, links and nodes.
                updated = image.path.read_bytes()
                offsets = {image.virtual_to_image(image.entry_offsets[b["outer_index"]] + off)
                           for b in receipt["books"] for off in b["changed_resource_offsets"]}
                self.assertEqual({i for i, (a, b) in enumerate(zip(image.image, updated)) if a != b}, offsets)

    def test_cli_book_export_audit_status_and_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.PLAY"
            source.write_bytes(fixture())
            output = Path(tmp) / "out.PLAY"
            command = [sys.executable, str(ROOT / "tools/nfl2k5_depth_roles.py")]
            result = subprocess.run(command + ["normalise", str(source), "-o", str(output), "--allow-custom", "--json", "-"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["changed_bytes"], 3)
            result = subprocess.run(command + ["audit", str(output), "--json", "-"], capture_output=True, text=True)
            self.assertTrue(json.loads(result.stdout)["totals"]["gate_ok"])
            result = subprocess.run(command + ["status", str(output), "--json", "-"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            result = subprocess.run(command + ["normalise", str(source), "-o", str(source), "--allow-custom"], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(source.read_bytes(), fixture())
            result = subprocess.run(command + ["normalise", str(source), "-o", str(Path(tmp) / "never.PLAY"),
                                                "--allow-custom", "--json", str(source)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse((Path(tmp) / "never.PLAY").exists())
            self.assertEqual(source.read_bytes(), fixture())

    def test_cli_loose_pack_export_can_be_audited_without_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = SyntheticXiso(Path(tmp), [(1, fixture()), (2, b"tail")],
                                  pack_sizes=(0x10000, 0x10000, 0x2000), pack_sectors=(64, 100, 136))
            output = Path(tmp) / "books"
            command = [sys.executable, str(ROOT / "tools/nfl2k5_depth_roles.py")]
            result = subprocess.run(command + ["normalise", str(image.retail_packs), "-o", str(output), "--allow-custom"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = d.audit(output)
            self.assertEqual(report["totals"]["books"], 1)
            self.assertTrue(report["totals"]["gate_ok"])


@unittest.skipUnless((RETAIL / "vc_53450030" / "0").is_file(),
                     "private retail NFL 2K5 vc_53450030 packs absent; set NFL2K5_RETAIL_EXTRACTION to their parent extraction root")
class RetailDepthRolesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with d._outer_image().OuterImage(RETAIL) as archive:
            cls.raws = {str(e.index): raw for e, raw in d._archive_resources(archive)}
        cls.results = {k: d.normalise(raw) for k, raw in cls.raws.items()}

    def test_full_retail_census_pins(self):
        totals = d.audit(self.raws)["totals"]
        self.assertEqual(totals["histograms"], d.RETAIL_TOTALS)
        self.assertEqual((totals["books"], totals["formations"], totals["plays"], totals["nodes"]), (37, 1533, 9251, 91833))
        self.assertEqual(d.status(self.raws)["status"], "retail")

    def test_every_output_passes_audit_and_all_nonexcluded_roles(self):
        audit = d.audit({k: r.replacement for k, r in self.results.items()})
        self.assertTrue(audit["totals"]["gate_ok"])
        self.assertEqual(audit["totals"]["gate_checked"], 402)
        self.assertEqual(audit["totals"]["gate_excluded"], 173)
        self.assertEqual(audit["totals"]["histograms"]["nickel_inner"], {"2": 71})
        self.assertEqual(audit["totals"]["histograms"]["dime_inner"], {"3": 38})
        reasons = Counter()
        for book in audit["books"].values():
            self.assertEqual(book["status"], "applied")
            for group in book["groups"]:
                for form in group["formations"]:
                    reasons[form["excluded_reason"]] += 1
                    if form["excluded_reason"]:
                        continue
                    self.assertEqual(form["inner_ordinal"], 3 if group["kind"] == d.CB and len(group["slots"]) == 4 else 2)
        self.assertEqual(reasons, {"": 402, "bunch_or_tied": 85, "disagreeing_inner_slot": 53, "non_offensive_wr_group": 35})

    def test_idempotence_byte_ownership_counts_and_validator_for_all_books(self):
        for key, result in self.results.items():
            raw = self.raws[key]
            self.assertEqual(d.normalise(result.replacement).replacement, result.replacement)
            self.assertEqual(d._parse(raw), d._parse(result.replacement))
            self.assertEqual(result.report["counts"]["plays"], result.report["all_plays_validated"])
            allowed = set(result.report["changed_resource_offsets"])
            self.assertEqual(sum(a != b for a, b in zip(raw, result.replacement)), len(allowed))
            for offset in allowed:
                self.assertEqual(raw[offset] & 31, result.replacement[offset] & 31)
                self.assertTrue(32 + insp.CATEGORY_BASE <= offset < 32 + insp.NODE_BASE)
            for g in result.report["refused_groups"]:
                offset = 32 + insp.CATEGORY_BASE + g["index"] * insp.CATEGORY_SIZE
                self.assertEqual(raw[offset:offset + 16], result.replacement[offset:offset + 16])

    def test_geometry_and_ordinal_edits_are_foreign_but_names_are_not_owned(self):
        raw = bytearray(self.raws["308"])
        raw[32 + insp.CATEGORY_BASE + 4 * 16 + 5 + 7] ^= 32
        self.assertEqual(d.book_status(raw), "foreign")
        raw = bytearray(self.raws["308"])
        raw[32 + insp.FORMATION_BASE + 6 * insp.FORMATION_SIZE + codec.FORMATION_SLOT_BASE + 6 * 14 + 2] ^= 1
        self.assertEqual(d.book_status(raw), "foreign")
        raw = bytearray(self.raws["308"])
        field = 32 + insp.FORMATION_BASE
        target = field - 1 + struct.unpack_from("<i", raw, field)[0]
        struct.pack_into("<H", raw, target, ord("Q"))
        self.assertEqual(d.book_status(raw), "retail")

    def test_position_recode_composes_in_both_orders(self):
        recode = d._outer_image()
        for key, raw in self.raws.items():
            def front(data):
                body = data[32:]
                book = d._parse(data)
                codes = {cat.index: recode.recode_codes(lib.category_positions(body, cat.index),
                         body[insp.CATEGORY_BASE + cat.index * 16 + 4])[0] for cat in book.categories}
                return compile_personnel_categories(data, codes)
            recoded = front(raw)
            self.assertEqual(d.book_status(recoded), "retail")
            self.assertEqual(d.normalise(recoded).replacement, front(self.results[key].replacement))
            self.assertEqual(d.book_status(front(self.results[key].replacement)), "applied")

    def test_community_pack_compiles_then_normalises_with_explicit_custom_policy(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        pack = packs.load_pack(ROOT / "data/playbooks/modern_gun_core.2k5book")
        raw = self.raws["308"]
        compiled = packs.apply_pack_to_resource(raw, pack, asset_id="book:ATL")
        archive = MemoryArchive([compiled.replacement])
        receipt = d.apply_to_archive(archive, allow_custom=True)
        self.assertTrue(receipt["gate_ok"])
        self.assertEqual(d._parse(compiled.replacement), d._parse(archive.read_entry(0)))


try:
    import unicorn
    from unicorn import x86_const as ux
except ImportError:
    unicorn = None


@unittest.skipUnless(XBE.is_file() and unicorn is not None,
                     "bounded ordinal proof requires the private retail default.xbe and Python unicorn")
class RetailOrdinalExecutionTests(unittest.TestCase):
    def test_actual_retail_resolver_returns_chain_and_row_for_all_role_ordinals(self):
        raw = XBE.read_bytes()
        self.assertEqual(hashlib.md5(raw).hexdigest(), "444064a9ec984dd29d2c05a43f5c96e8")
        for kind, chains in ((9, (4, 5)), (18, (21, 22))):
            for ordinal in range(8):
                uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
                uc.mem_map(0xE7000, 0x1000)
                uc.mem_write(0xE7530, raw[0xD7530:0xD7564])
                uc.mem_protect(0xE7000, 0x1000, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
                uc.mem_map(0x4F5000, 0x1000)
                off = 0x4F5930 - 0xAAE0
                uc.mem_write(0x4F5930, raw[off:off + 19 * 8])
                uc.mem_protect(0x4F5000, 0x1000, unicorn.UC_PROT_READ)
                uc.mem_map(0x1000000, 0x2000)
                uc.mem_write(0x1001000, struct.pack("<I", 0xE7564))
                for reg, value in ((ux.UC_X86_REG_EAX, kind), (ux.UC_X86_REG_EDX, ordinal),
                                   (ux.UC_X86_REG_ESI, 0x1000000), (ux.UC_X86_REG_ESP, 0x1001000),
                                   (ux.UC_X86_REG_EBX, 0x1234), (ux.UC_X86_REG_EDI, 0x5678)):
                    uc.reg_write(reg, value)
                uc.emu_start(0xE7530, 0xE7564, count=32)
                self.assertEqual(uc.reg_read(ux.UC_X86_REG_EIP), 0xE7564, "bounded execution must return")
                self.assertEqual(uc.reg_read(ux.UC_X86_REG_EAX), chains[ordinal & 1])
                self.assertEqual(struct.unpack("<I", uc.mem_read(0x1000000, 4))[0], ordinal >> 1)
                self.assertEqual(uc.reg_read(ux.UC_X86_REG_EBX), 0x1234)
                self.assertEqual(uc.reg_read(ux.UC_X86_REG_EDI), 0x5678)


if __name__ == "__main__":
    unittest.main()
