"""Native C2 repair (tools/b77/c2_repair.py) on synthetic loose packs in the real outer-archive layout.

Pack 0 holds a players cue table (outer entry 3) and a classic-style roster, pack E a roster that still holds the retired
double-zero id, pack F a clean roster. Nothing here needs the game or its data.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_commentary_final as cf  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE  # noqa: E402
from test_nfl2k5_commentary_final import roster_resource, synthetic_spci  # noqa: E402
from tools.b77 import c2_repair as repair  # noqa: E402

BLOCK = ALIGNMENT


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blocks_for(*parts: bytes) -> int:
    return -(-sum(len(p) for p in parts) // BLOCK)


class Fixture:
    """Three loose packs (0, E, F) and the outer directory that describes them."""

    def __init__(self, directory: Path, *, classic_ids=None, e_ids=None, f_ids=None) -> None:
        self.classic = roster_resource(classic_ids if classic_ids is not None else {i: 9000 + (i + 1) for i in range(8)})
        self.e_team = roster_resource(e_ids if e_ids is not None else {0: 9100, 1: 3593, 2: 9100})
        # the synthetic players wear 18, 88, 32, 7, 28, 84, 24 and 99; a roster whose ids already say so needs nothing
        self.f_team = roster_resource(f_ids if f_ids is not None else
                                      {i: 9000 + n for i, n in enumerate((18, 88, 32, 7, 28, 84, 24, 99))})
        self.spci_container = bytes(0x800) + synthetic_spci() + bytes(0x800)
        names = (101, 102, 103)
        pack0, self.offsets0 = bytearray(), {}
        head_blocks = 1 + -(-(12 * 8) // BLOCK)
        pack0.extend(bytes(head_blocks * BLOCK))
        for index, payload in ((3, self.spci_container), (4, self.classic)):
            while len(pack0) % BLOCK:
                pack0.append(0)
            self.offsets0[index] = len(pack0)
            pack0.extend(payload)
        while len(pack0) % BLOCK:
            pack0.append(0)
        self.pack0 = pack0
        self.pack_e = bytearray(self.e_team + bytes(-len(self.e_team) % BLOCK))
        self.pack_f = bytearray(self.f_team + bytes(-len(self.f_team) % BLOCK))
        blocks = [len(self.pack0) // BLOCK] + [1] * 13 + [len(self.pack_e) // BLOCK, len(self.pack_f) // BLOCK]
        starts = [0]
        for b in blocks[:-1]:
            starts.append(starts[-1] + b * BLOCK)
        rows = []
        for index in range(8):
            if index in self.offsets0:
                payload = {3: self.spci_container, 4: self.classic}[index]
                rows.append((200 + index, len(payload), self.offsets0[index] // BLOCK))
            elif index == 5:
                rows.append((200 + index, len(self.e_team), starts[14] // BLOCK))
            elif index == 6:
                rows.append((200 + index, len(self.f_team), starts[15] // BLOCK))
            else:
                rows.append((200 + index, 16, starts[1 + index % 3] // BLOCK))
        header = bytearray(HEADER_SIZE + 12 * 8)
        struct.pack_into("<3I", header, 0, 8, 0, 16)
        struct.pack_into("<16I", header, 12, *blocks)
        for i, row in enumerate(rows):
            struct.pack_into("<3I", header, HEADER_SIZE + 12 * i, *row)
        self.pack0[:len(header)] = header
        self.paths = {}
        for ordinal, name, data in ((0, "0", self.pack0), (14, "E", self.pack_e), (15, "F", self.pack_f)):
            path = Path(directory) / f"in_{name}"
            path.write_bytes(bytes(data))
            self.paths[ordinal] = path
        self.hashes = [sha(p.read_bytes()) for p in self.paths.values()]

    def run(self, out: Path, *extra: str, paths: dict | None = None) -> dict:
        paths = paths or self.paths
        argv = ["c2_repair.py", "--pack0", str(paths[0]), "--pack-e", str(paths[14]), "--pack-f", str(paths[15]),
                "--out-dir", str(out), *extra]
        with mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            self.code = repair.main()
        return json.loads((out / "c2_scope_receipt.json").read_text()) if (out / "c2_scope_receipt.json").exists() else {}


class RepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        patches = [
            mock.patch.object(cf, "RETAIL_SPCI_SHA256", sha(synthetic_spci())),
            mock.patch.object(cf, "APPLIED_SPCI_SHA256", sha(synthetic_spci(retired=True))),
            mock.patch.object(repair, "V05_PACK_SHA256", {0: "0" * 64, 14: "0" * 64, 15: "0" * 64}),
            mock.patch.object(repair, "F12_PACK_SHA256", {14: "0" * 64, 15: "0" * 64}),
            mock.patch.object(repair, "C2_PACK_SHA256", {0: "0" * 64, 14: "0" * 64, 15: "0" * 64}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.fx = Fixture(self.dir)
        self.approve = [a for h in self.fx.hashes for a in ("--approved-input-sha256", h)]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unknown_inputs_are_refused_without_approval(self) -> None:
        with self.assertRaises(repair.RepairRefused):
            self.fx.run(self.dir / "refused")
        self.assertFalse((self.dir / "refused").exists())

    def test_edits_are_exactly_the_id_words_and_the_one_cue_byte(self) -> None:
        receipt = self.fx.run(self.dir / "out", *self.approve)
        resources = (self.fx.classic, self.fx.e_team, self.fx.f_team)
        expected = [rr.repair_commentary_resource(r)[1]["players_changed"] for r in resources]
        self.assertEqual(expected[2], 0)                                   # pack F is already final
        self.assertEqual((receipt["state"], receipt["players_changed"], receipt["resources_changed"]),
                         ("applied", sum(expected), 2))
        out = {o: (self.dir / "out" / "vc_53450030" / n).read_bytes() for o, n in ((0, "0"), (14, "E"), (15, "F"))}
        for ordinal, path in self.fx.paths.items():
            name = repair.PACK_NAMES[ordinal]
            before, after = path.read_bytes(), out[ordinal]
            self.assertEqual(len(before), len(after))
            changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
            declared = {offset + k for offset, size in receipt["files"][name]["edit_spans"] for k in range(size)}
            self.assertTrue(changed <= declared, name)
            self.assertTrue(receipt["files"][name]["outside_scope_identical"])
            self.assertEqual(sha(after), receipt["files"][name]["after_sha256"])
        # pack 0: the cue byte plus the classic roster's number words
        table_at = self.fx.offsets0[3] + 0x800
        self.assertEqual(out[0][table_at: table_at + cf.SPCI_SIZE], synthetic_spci(retired=True))
        classic = rr.repair_commentary_resource(self.fx.classic)[0]
        at = self.fx.offsets0[4]
        self.assertEqual(out[0][at: at + len(classic)], classic)
        self.assertEqual(receipt["files"]["0"]["declared_edits"], expected[0] + 1)
        # pack E: the retired double zero is gone; the recorded name is kept
        e_doc = rr.load_body(out[14][rr.RESOURCE_HEADER_SIZE:len(self.fx.e_team)])
        ids = {p.index: p.record.values["pbp_id"] for p in e_doc.players}
        self.assertNotIn(9100, ids.values())
        self.assertEqual(ids[1], 3593)
        # pack F: nothing to do
        self.assertEqual(out[15], self.fx.paths[15].read_bytes())
        self.assertEqual(receipt["files"]["F"]["declared_edits"], 0)

    def test_replay_is_a_no_op_and_an_existing_output_is_not_replaced(self) -> None:
        first = self.fx.run(self.dir / "out", *self.approve)
        outputs = {n: (self.dir / "out" / "vc_53450030" / n) for n in "0EF"}
        again_paths = {0: outputs["0"], 14: outputs["E"], 15: outputs["F"]}
        approve = [a for p in again_paths.values() for a in ("--approved-input-sha256", sha(p.read_bytes()))]
        second = self.fx.run(self.dir / "out2", *approve, paths=again_paths)
        self.assertEqual((second["state"], second["players_changed"]), ("already_applied", 0))
        for n in "0EF":
            self.assertEqual((self.dir / "out2" / "vc_53450030" / n).read_bytes(), outputs[n].read_bytes())
        self.assertEqual({k: v["after_sha256"] for k, v in first["files"].items()},
                         {k: v["after_sha256"] for k, v in second["files"].items()})
        with self.assertRaises(repair.RepairRefused):
            self.fx.run(self.dir / "out", *self.approve)

    def test_a_cue_table_that_is_neither_retail_nor_applied_is_refused(self) -> None:
        data = bytearray(self.fx.paths[0].read_bytes())
        data[self.fx.offsets0[3] + 0x800 + 300] ^= 0xFF
        bad = self.dir / "bad0"
        bad.write_bytes(bytes(data))
        paths = {**self.fx.paths, 0: bad}
        approve = [a for p in paths.values() for a in ("--approved-input-sha256", sha(p.read_bytes()))]
        with self.assertRaises(cf.CommentaryFinalError):
            self.fx.run(self.dir / "out", *approve, paths=paths)

    def test_composes_with_another_jobs_field_in_either_order(self) -> None:
        def other_job(raw: bytes) -> bytes:
            """Another owner's field: years pro (+0x25) of every player of the pack E roster."""
            data = bytearray(raw)
            document = rr.load_body(bytes(data[rr.RESOURCE_HEADER_SIZE:len(self.fx.e_team)]))
            for p in document.players:
                data[rr.RESOURCE_HEADER_SIZE + p.offset + 0x25] ^= 0x01
            return bytes(data)

        # c2 then the other job
        first = self.fx.run(self.dir / "ab", *self.approve)
        e_ab = other_job((self.dir / "ab" / "vc_53450030" / "E").read_bytes())
        # the other job then c2
        modified = self.dir / "e_mod"
        modified.write_bytes(other_job(self.fx.paths[14].read_bytes()))
        paths = {**self.fx.paths, 14: modified}
        approve = [a for p in paths.values() for a in ("--approved-input-sha256", sha(p.read_bytes()))]
        self.fx.run(self.dir / "ba", *approve, paths=paths)
        e_ba = (self.dir / "ba" / "vc_53450030" / "E").read_bytes()
        self.assertEqual(e_ab, e_ba)
        self.assertEqual(first["state"], "applied")

    def test_a_pack_of_the_wrong_size_is_refused(self) -> None:
        short = self.dir / "short_e"
        short.write_bytes(self.fx.paths[14].read_bytes() + bytes(BLOCK))
        paths = {**self.fx.paths, 14: short}
        approve = [a for p in paths.values() for a in ("--approved-input-sha256", sha(p.read_bytes()))]
        with self.assertRaises(repair.RepairRefused):
            self.fx.run(self.dir / "out", *approve, paths=paths)

    def test_dry_run_writes_nothing(self) -> None:
        self.fx.run(self.dir / "dry", *self.approve, "--dry-run")
        self.assertFalse((self.dir / "dry").exists())


if __name__ == "__main__":
    unittest.main()
