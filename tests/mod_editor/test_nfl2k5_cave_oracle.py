"""Synthetic (redistributable) and optional private-retail oracle regressions.

Plain ``unittest`` so the CI runner can execute this file as a script: the
whole class skips when capstone is absent, and the retail-backed tests skip
when the private USA ``default.xbe`` is not on this machine.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from mod_editor.core.nfl2k5_cave_manifest import Recorder, changed_runs
from mod_editor.core.nfl2k5_cave_oracle import (
    DEFAULT_MANIFEST, ENTRY_KEYS, MANIFEST_SCHEMA, RETAIL_SHA256, THUNK_KEYS,
    CaveOracle, OracleError, ReservationManifest, XbeImage, absolute_writes,
    legacy_external_references, legacy_references,
)

ROOT = Path(__file__).resolve().parents[2]
TEXT, DATA = 0x11000, 0x20000
XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"


def synthetic(*, text: bytes = b"\xc3", data: bytes = b"", tls: int = 0,
              imports: int = 0, kernel: int = 0, text_flags: int = 0x16,
              sections=None) -> bytes:
    """Tiny XBE with deliberately non-identity raw/VA mapping. No game bytes."""
    if sections is None:
        sections = [(".text", TEXT, 0x200, 0x600, 0x200, text_flags),
                    (".data", DATA, 0x200, 0xA00, 0x200, 3)]
    size = max(raw + rawsize for _, _, _, raw, rawsize, _ in sections)
    out = bytearray(size)
    out[:4] = b"XBEH"
    struct.pack_into("<3I", out, 0x104, 0x10000, 0x400, 0x30000)
    struct.pack_into("<II", out, 0x11C, len(sections), 0x10180)
    struct.pack_into("<II", out, 0x128, TEXT ^ ENTRY_KEYS["retail"], tls)
    struct.pack_into("<II", out, 0x158, kernel ^ THUNK_KEYS["retail"], imports)
    for i, (name, va, vsize, raw, rawsize, flags) in enumerate(sections):
        name_off = 0x300 + i * 16
        name_bytes = name.encode() + b"\0"
        out[name_off:name_off + len(name_bytes)] = name_bytes
        struct.pack_into("<6I", out, 0x180 + i * 56, flags, va, vsize, raw, rawsize, 0x10000 + name_off)
        content = text if name == ".text" else data if name == ".data" else b""
        assert len(content) <= rawsize
        out[raw:raw + rawsize] = (b"\xcc" if name == ".text" else b"\0") * rawsize
        out[raw:raw + len(content)] = content
    return bytes(out)


def put(payload: bytes, va: int, value: bytes) -> bytes:
    image = XbeImage(payload)
    out = bytearray(payload)
    off = image.offset(va, len(value))
    out[off:off + len(value)] = value
    return bytes(out)


def manifest_for(payload: bytes, spans=None, **extra):
    return {"schema": MANIFEST_SCHEMA, "retail_sha256": hashlib.sha256(payload).hexdigest(), "complete": True,
            "spans": spans or [{"start": hex(TEXT + 0x40), "end": hex(TEXT + 0x80),
                                "owner": "test_owner", "basis": "synthetic allocation"}], **extra}


OCCUPIED = [(0x1AFDF0, 300, "nfl2k5_overtime"), (0x28B410, 233, "nfl2k5_overtime"),
            (0x1D82D0, 352, "nfl2k5_franchise_practice"), (0x325E70, 979, "nfl2k5_playoffs14"),
            (0x2979F0, 143, "nfl2k5_kick_laces"), (0xB4A60, 48, "nfl2k5_penalties"),
            (0x2BA840, 32, "nfl2k5_position_pools")]


class CaveOracleTests(unittest.TestCase):
    # The retail bytes and their analysed oracle are computed once per run, on
    # first use, and shared by every retail-backed test (the analysis is the
    # expensive step). Populated lazily so the class still loads and the
    # synthetic tests still run when the private XBE is absent.
    _retail: dict[str, object] = {}

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import capstone  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(
                "cave analysis requires capstone; install tools/requirements-nfl2k5-cave-oracle.txt") from exc

    # ------------------------------------------------------------ retail fixtures
    def retail(self) -> bytes:
        if not XBE.is_file():
            self.skipTest(f"private USA retail default.xbe absent: {XBE}; set NFL2K5_RETAIL_EXTRACTION")
        if "bytes" not in self._retail:
            data = XBE.read_bytes()
            assert hashlib.sha256(data).hexdigest() == RETAIL_SHA256, "private retail XBE has unexpected identity"
            CaveOracleTests._retail["bytes"] = data
        return self._retail["bytes"]  # type: ignore[return-value]

    def retail_oracle(self) -> CaveOracle:
        if "oracle" not in self._retail:
            CaveOracleTests._retail["oracle"] = CaveOracle(self.retail()).analyze()
        return self._retail["oracle"]  # type: ignore[return-value]

    # ------------------------------------------------------------ synthetic images
    def test_rel8_rel32_entry_fallthrough_and_instruction_interiors(self):
        # jmp +6; skipped bytes; call helper; conditional branch; both returns.
        p = synthetic(text=b"\xeb\x06")
        p = put(p, TEXT + 8, b"\xe8" + struct.pack("<i", 0x30 - 13) + b"\x75\x01\xc3\xc3")
        p = put(p, TEXT + 0x30, b"\xc3")
        oracle = CaveOracle(p).analyze()
        for va in (TEXT, TEXT + 8, TEXT + 10, TEXT + 13, TEXT + 15, TEXT + 16, TEXT + 0x30):
            assert oracle.assess(va, 1)["verdict"] == "reachable"
        candidate = oracle.assess(TEXT + 2, 6)
        assert candidate["verdict"] == "free-under-closed-world"
        assert candidate["allocatable"]
        assert any("jmp" in i["reason"] for i in oracle.neighbour(TEXT + 1)["instructions"])
        assert any("call" in i["reason"] for i in oracle.neighbour(TEXT + 8)["instructions"])

    def test_vtable_and_pointer_loaded_by_rooted_instruction(self):
        p = synthetic(text=b"\xa1" + struct.pack("<I", DATA) + b"\xff\xd0\xc3", data=struct.pack("<I", TEXT + 0x80))
        p = put(p, TEXT + 0x80, b"\xc3")
        oracle = CaveOracle(p)
        assert oracle.assess(DATA, 4, kind="data")["verdict"] == "reachable"
        assert oracle.assess(TEXT + 0x80, 1)["verdict"] == "reachable"
        assert any(e.kind == "possible-read-pointer" for e in oracle.witnesses(TEXT + 0x80, TEXT + 0x81))
        assert oracle.assess(TEXT + 0x100, 64)["verdict"] == "unknown"

    def test_computed_jump_table_preserves_unproved_index_extent(self):
        code = b"\x83\xf8\x01\x77\x0b\xff\x24\x85" + struct.pack("<I", DATA)
        p = synthetic(text=code, data=struct.pack("<2I", TEXT + 0x80, TEXT + 0x90))
        for va in (TEXT + 0x10, TEXT + 0x80, TEXT + 0x90):
            p = put(p, va, b"\xc3")
        oracle = CaveOracle(p).analyze()
        assert any(e.kind == "jump-table-target" for e in oracle.witnesses(TEXT + 0x80, TEXT + 0x81))
        assert any(e.kind == "jump-table-slot" for e in oracle.witnesses(DATA, DATA + 8))
        assert oracle.assess(TEXT + 0x100, 64)["verdict"] == "unknown"
        assert any(e.kind == "unresolved-memory" for e in oracle.unknowns)

    def test_data_embedded_in_code_is_not_padding(self):
        p = synthetic(text=b"\xa1" + struct.pack("<I", TEXT + 0x20) + b"\xc3")
        p = put(p, TEXT + 0x20, struct.pack("<I", 0xDEADBEEF))
        oracle = CaveOracle(p)
        row = oracle.assess(TEXT + 0x20, 4)
        assert row["verdict"] == "reachable"
        assert any(e["kind"] == "data-read" for e in row["witnesses"])

    def test_unaligned_pointer_is_a_speculative_root_not_a_proved_callback(self):
        p = synthetic(data=b"\x11" + struct.pack("<I", TEXT + 0x80))
        p = put(p, TEXT + 0x80, b"\xc3")
        oracle = CaveOracle(p)
        row = oracle.assess(TEXT + 0x80, 1)
        assert row["verdict"] == "unknown"
        assert any(e["kind"] == "possible-pointer" and e["source"] == hex(DATA + 1) for e in row["witnesses"])
        assert oracle.assess(DATA + 2, 1, kind="data")["verdict"] == "unknown"

    def test_callback_store_is_retained_with_source_instruction(self):
        p = synthetic()
        p = put(p, TEXT + 0x40, b"\xc7\x05" + struct.pack("<II", DATA, TEXT + 0x80) + b"\xc3")
        p = put(p, TEXT + 0x80, b"\xc3")
        oracle = CaveOracle(p)
        row = oracle.assess(TEXT + 0x80, 1)
        assert row["verdict"] == "reachable"
        assert row["witnesses"][0]["kind"] == "callback-store"
        assert row["witnesses"][0]["source"] == hex(TEXT + 0x40)

    def test_unresolved_indirect_transfer_never_upgrades_unknown_to_free(self):
        oracle = CaveOracle(synthetic(text=b"\xff\xe0"))
        row = oracle.assess(TEXT + 0x100, 64)
        assert row["verdict"] == "unknown" and not row["allocatable"]
        with self.assertRaisesRegex(OracleError, "unknown"):
            oracle.require_cave(TEXT + 0x100, 64)
        assert not any(r["allocatable"] for r in oracle.scan(min_size=1)["ranges"])

    def test_runtime_write_to_text_is_rejected_and_full_width_checked(self):
        code = b"\xc7\x05" + struct.pack("<II", TEXT + 0x80, 1) + b"\xc3"
        p = synthetic(text=code)
        rows = absolute_writes(p, [(TEXT, TEXT + len(code))])
        assert rows[0]["target"] == hex(TEXT + 0x80)
        assert rows[0]["writable"] is False and rows[0]["size"] == 4
        oracle = CaveOracle(p)
        assert oracle.assess(TEXT + 0x100, 64, kind="data")["eligible"] is False
        assert not any(r["section"] == ".text" and r["allocatable"] for r in oracle.scan(kind="data")["ranges"])
        # A foreign header claiming .text writable still cannot authorize runtime data.
        assert not CaveOracle(synthetic(text_flags=7)).assess(TEXT + 0x100, 64, kind="data")["eligible"]
        p = synthetic(sections=[(".text", TEXT, 0x200, 0x600, 0x200, 0x16),
                                (".data", DATA, 0x20, 0xA00, 0x20, 3),
                                (".ro", DATA + 0x20, 0x20, 0xB00, 0x20, 2)])
        image = XbeImage(p)
        assert image.runtime_writable(DATA + 0x1F, 1) is True
        assert image.runtime_writable(DATA + 0x1F, 4) is False

    def test_write_gate_checks_second_operand_and_undecodable_suffix(self):
        p = synthetic(text=b"\x87\x05" + struct.pack("<I", TEXT + 0x80) + b"\x0f")
        rows = absolute_writes(p, [(TEXT, TEXT + 7)])
        assert any(r["writable"] is False for r in rows)
        assert rows[-1]["detail"] == "undecoded trailing bytes"
        assert rows[-1]["writable"] is None
        indirect = absolute_writes(synthetic(text=b"\x89\x08\xc3"), [(TEXT, TEXT + 3)])
        assert indirect[0]["target"] is None and indirect[0]["writable"] is None

    def test_tls_template_index_and_callbacks_are_roots(self):
        p = synthetic(tls=DATA)
        p = put(p, DATA, struct.pack("<6I", DATA + 0x40, DATA + 0x44, DATA + 0x48, DATA + 0x50, 8, 0))
        p = put(p, DATA + 0x50, struct.pack("<II", TEXT + 0x80, 0))
        p = put(p, TEXT + 0x80, b"\xc3")
        oracle = CaveOracle(p)
        for va, size in ((DATA, 24), (DATA + 0x40, 4), (DATA + 0x48, 4), (DATA + 0x50, 8)):
            assert oracle.assess(va, size, kind="data")["verdict"] == "reachable"
        assert oracle.assess(TEXT + 0x80, 1)["verdict"] == "reachable"
        assert any(e.kind == "tls-callback-target" for e in oracle.witnesses(TEXT + 0x80, TEXT + 0x81))

    def test_decoded_imports_are_reserved_by_reachability_and_external_effects_unknown(self):
        p = synthetic(kernel=DATA, data=struct.pack("<II", 0x80000001, 0))
        oracle = CaveOracle(p)
        assert oracle.assess(DATA, 8, kind="data")["verdict"] == "reachable"
        assert oracle.assess(TEXT + 0x100, 64)["verdict"] == "unknown"
        assert any(e.kind == "external-import" for e in oracle.unknowns)

    def test_nonkernel_import_directory_and_utf16_name(self):
        p = synthetic(imports=DATA)
        p = put(p, DATA, struct.pack("<4I", DATA + 0x20, DATA + 0x40, 0, 0))
        p = put(p, DATA + 0x20, struct.pack("<II", 0x80000003, 0))
        p = put(p, DATA + 0x40, "test.dll\0".encode("utf-16-le"))
        oracle = CaveOracle(p)
        assert oracle.assess(DATA + 0x40, 18, kind="data")["verdict"] == "reachable"
        assert not any(e.kind == "malformed-import" for e in oracle.unknowns)

    def test_bad_headers_refused(self):
        for field, value, reason in [(0x120, 0xFFFFFFFF, "section table"), (0x108, 0xFFFFFF, "SizeOfHeaders"),
                                     (0x10C, 0xFFFFFFFF, "SizeOfImage")]:
            with self.subTest(field=hex(field), reason=reason):
                p = bytearray(synthetic())
                struct.pack_into("<I", p, field, value)
                with self.assertRaisesRegex(OracleError, reason):
                    XbeImage(bytes(p))

    def test_overlapping_mappings_and_truncated_raw_data_refused(self):
        with self.assertRaisesRegex(OracleError, "overlapping virtual"):
            synthetic_image = synthetic(sections=[(".text", TEXT, 0x200, 0x600, 0x200, 6),
                                                 (".data", TEXT + 1, 0x200, 0xA00, 0x200, 3)])
            XbeImage(synthetic_image)
        with self.assertRaisesRegex(OracleError, "truncated"):
            XbeImage(synthetic()[:-1])

    def test_missing_loader_root_and_budgets_fail_closed(self):
        p = bytearray(synthetic())
        struct.pack_into("<I", p, 0x128, 0)
        assert CaveOracle(bytes(p)).assess(TEXT + 0x100, 64)["verdict"] == "unknown"
        for kwargs in ({"instruction_budget": 1}, {"reference_budget": 1}):
            oracle = CaveOracle(synthetic(text=b"\x90\x90\xc3", data=struct.pack("<I", TEXT)), **kwargs)
            assert oracle.assess(TEXT + 0x100, 64)["verdict"] == "unknown"
        p = synthetic(tls=0xFFFFFFFF)
        assert CaveOracle(p).assess(TEXT + 0x100, 64)["verdict"] == "unknown"

    def test_file_mapping_virtual_tail_and_section_gaps_are_not_free_data(self):
        p = synthetic(sections=[(".text", TEXT, 0x200, 0x600, 0x200, 6),
                                (".data", DATA, 0x280, 0xA00, 0x200, 3)])
        oracle = CaveOracle(p)
        assert oracle.image.offset(DATA + 0x10) == 0xA10
        assert oracle.assess(DATA + 0x200, 64, kind="data")["verdict"] == "unknown"
        assert not oracle.assess(DATA + 0x280, 4, kind="data")["eligible"]
        assert not oracle.assess(0x10380, 16, kind="code")["eligible"]

    def test_reservation_precedence_including_coincident_and_zero_bytes(self):
        p = synthetic()
        doc = manifest_for(p, spans=[{"start": hex(TEXT), "end": hex(TEXT + 0x80), "owner": "test_owner", "basis": "full declared capacity"},
                                     {"start": hex(DATA), "end": hex(DATA + 4), "owner": "test_owner", "basis": "unchanged runtime dword"}])
        manifest = ReservationManifest(doc, XbeImage(p))
        oracle = CaveOracle(p, manifest=manifest)
        assert oracle.assess(TEXT, 1)["verdict"] == "reserved"
        assert oracle.assess(TEXT + 0x70, 1)["verdict"] == "reserved"
        assert oracle.assess(DATA, 4, kind="data")["verdict"] == "reserved"
        assert oracle.assess(TEXT, 1, exclude_owner="test_owner")["verdict"] == "reachable"
        with self.assertRaisesRegex(OracleError, "reserved"):
            oracle.require_cave(TEXT + 0x60, 4)

    def test_manifest_hash_completeness_and_source_drift_refused(self):
        p = synthetic()
        with self.assertRaisesRegex(OracleError, "different XBE"):
            ReservationManifest(manifest_for(p, retail_sha256="bad"), XbeImage(p))
        with self.assertRaisesRegex(OracleError, "incomplete"):
            ReservationManifest(manifest_for(p, complete=False), XbeImage(p))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "owner.py").write_text("pass\n")
            doc = manifest_for(p, source_sha256={"owner.py": hashlib.sha256(b"pass\n").hexdigest()})
            ReservationManifest(doc, XbeImage(p), source_root=tmp_path)
            (tmp_path / "owner.py").write_text("changed\n")
            with self.assertRaisesRegex(OracleError, "stale reservation source"):
                ReservationManifest(doc, XbeImage(p), source_root=tmp_path)

    def test_exact_diff_tracks_last_byte_and_unchanged_pages(self):
        before = bytes(9000)
        after = bytearray(before)
        after[4095:4097] = b"xy"
        after[-1] = 1
        assert list(changed_runs(before, bytes(after))) == [(4095, 4097), (8999, 9000)]
        with self.assertRaisesRegex(OracleError, "resized"):
            list(changed_runs(b"a", b"ab"))

    def test_recorder_refuses_unattributed_patch(self):
        p = synthetic()
        recorder = Recorder(p)
        with self.assertRaisesRegex(OracleError, "unattributed"):
            recorder.finish(put(p, TEXT + 0x80, b"\xc3"))

    def test_cli_json_and_twenty_largest_summary_without_mutating_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source, target = tmp_path / "test.xbe", tmp_path / "report.json"
            source.write_bytes(synthetic())
            before = source.read_bytes()
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
            env.pop("DISPLAY", None)
            command = [sys.executable, str(ROOT / "tools/nfl2k5_cave_oracle.py"), "scan", str(source),
                       "--min-size", "64", "--kind", "code", "--range", "0x11100:64", "--json", str(target)]
            done = subprocess.run(command, text=True, capture_output=True, env=env, timeout=30)
            assert done.returncode == 0, done.stderr
            doc = json.loads(target.read_text())
            assert doc["queries"][0]["verdict"] == "free-under-closed-world"
            assert "left:" in done.stdout and "right:" in done.stdout
            assert source.read_bytes() == before
            command[-1] = str(source)
            done = subprocess.run(command, text=True, capture_output=True, env=env, timeout=30)
            assert done.returncode == 2 and "must not overwrite" in done.stderr
            assert source.read_bytes() == before

    def test_scan_coverage_includes_short_runs_and_matches_exact_queries(self):
        oracle = CaveOracle(synthetic())
        report = oracle.scan(min_size=64)
        for s in report["sections"]:
            assert sum(s["coverage"].values()) == s["size"]
        for row in report["ranges"]:
            assert oracle.assess(int(row["start"], 0), row["size"])["verdict"] == row["verdict"]

    def test_summary_limits_each_section_to_twenty_largest_candidates(self):
        from tools.nfl2k5_cave_oracle import summary
        p = synthetic(sections=[(".text", TEXT, 0x2000, 0x600, 0x2000, 6),
                                (".data", DATA, 0x200, 0x3000, 0x200, 3)])
        for i in range(25):
            p = put(p, TEXT + i * 96, b"\xe9" + struct.pack("<i", 91))
        p = put(p, TEXT + 25 * 96, b"\xc3")
        report = CaveOracle(p).scan(min_size=64)
        assert len([r for r in report["ranges"] if r["allocatable"]]) == 26
        assert sum(line.startswith("  0x") for line in summary(report).splitlines()) == 20

    def test_pointer_scan_includes_last_complete_word_and_other_executable_sections(self):
        p = synthetic(sections=[(".text", TEXT, 0x200, 0x600, 0x200, 6),
                                ("LIB", 0x18000, 0x200, 0x900, 0x200, 6),
                                (".data", DATA, 0x200, 0xC00, 0x200, 3)])
        p = put(p, 0x18000, b"\xc3")
        p = put(p, DATA + 0x1FC, struct.pack("<I", 0x18000))
        oracle = CaveOracle(p)
        row = oracle.assess(0x18000, 1)
        assert row["verdict"] == "unknown"
        assert any(e["source"] == hex(DATA + 0x1FC) for e in row["witnesses"])

    # ------------------------------------------------------------ private retail XBE
    def test_retail_callback_and_seven_previously_negative_caves(self):
        retail_oracle = self.retail_oracle()
        row = retail_oracle.assess(0x1AC260, 16)
        assert row["verdict"] == "reachable"
        assert any(e["source"] == "0x1b8777" and e["kind"] == "callback-store" for e in row["witnesses"])
        for start, size, _ in OCCUPIED:
            row = retail_oracle.assess(start, size)
            assert row["verdict"] in ("unknown", "free-under-closed-world"), (hex(start), row)
            assert row["witnesses"] or row["verdict"] == "free-under-closed-world"

    def test_retail_current_stack_owns_every_supplied_cave_and_runtime_flag(self):
        retail = self.retail()
        image = XbeImage(retail)
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, image, source_root=ROOT)
        # Reuse static analysis via a small budget: reservations take precedence even
        # when the analysis is incomplete, and this avoids a second expensive decode.
        oracle = CaveOracle(retail, manifest=manifest, instruction_budget=1, reference_budget=1)
        for start, size, owner in OCCUPIED:
            row = oracle.assess(start, size)
            assert row["verdict"] == "reserved"
            assert any(owner in e["detail"] for e in row["witnesses"])
        for start in (0xA69970, 0xA69974, 0xA69978, 0xA6997C, 0x10A10, 0x10CD0):
            assert oracle.assess(start, 1, kind="data")["verdict"] == "reserved"
        assert manifest.document["section_digests_verified"]
        assert "scorebug" in manifest.document["image_steps"]
        assert "season_2026" in manifest.document["image_steps"]

    def test_legacy_projection_reproduces_gate_targets_and_negative_caves(self):
        retail = self.retail()
        # Load the unchanged gate independently: equality covers EVERY recorded target
        # and source, not merely the seven examples in the brief.
        import importlib.util
        spec = importlib.util.spec_from_file_location("old_cave_gate", ROOT / "tests/mod_editor/test_xbe_patch_cave_references.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        gate.CaveReferenceTests.setUpClass()
        targets = legacy_references(XbeImage(retail))
        expected = {t: {r if isinstance(r, int) else r[2] + gate.BASE if r[1] == ".text"
                        else gate.CaveReferenceTests.sec[r[1]][0] + r[2] - gate.CaveReferenceTests.sec[r[1]][2]
                        for r in refs} for t, refs in gate.CaveReferenceTests.targets.items()}
        actual = {t: {e.source for e in refs} for t, refs in targets.items()}
        assert actual == expected
        instance = gate.CaveReferenceTests()
        for a, b in instance._caves():
            assert legacy_external_references(targets, a, b) == []
        for a, size, _ in OCCUPIED:
            assert legacy_external_references(targets, a, a + size) == []
        assert 0x1AC260 in targets

    def test_retail_data_scan_never_offers_text(self):
        report = self.retail_oracle().scan(kind="data", min_size=64)
        text = next(s for s in report["sections"] if s["name"] == ".text")
        assert text["flags"] == 0x16 and not text["eligible"]
        assert text["coverage"]["free-under-closed-world"] == 0
        assert not any(r["section"] == ".text" and r["allocatable"] for r in report["ranges"])


if __name__ == "__main__":
    unittest.main()
