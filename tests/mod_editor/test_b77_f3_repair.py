"""Job F3 native repair (tools/b77/f3_repair.py): scope, pins, refusals, idempotence.

Synthetic images always run; the exact v0.5 executable (read from the private v0.5 disc) runs when the disc is present.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_team_column as tc  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402
from test_nfl2k5_team_column import _legacy_cave  # noqa: E402
from tools.b77 import f3_native_scenario as scenario  # noqa: E402
from tools.b77 import f3_repair as repair  # noqa: E402

V05_DISC = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso")


def legacy_image() -> bytes:
    """The synthetic image as the v0.5 disc carries the TEAM column (revision 1)."""

    payload = _build_synthetic_xbe()
    buf = bytearray(payload)
    for _label, off, _before, after in tc._sites(payload, legacy=True):
        buf[off: off + len(after)] = after
    cave = tc._offset(payload, tc.CAVE_VA)
    buf[cave: cave + tc.CAVE_SIZE] = _legacy_cave()
    for section in strength._sections(payload):
        end = section.raw_offset + section.raw_size
        if section.raw_size and end <= len(buf) and bytes(buf[section.raw_offset: end]) != payload[section.raw_offset: end]:
            d = section.header_offset + 36
            buf[d: d + 20] = strength.section_digest(bytes(buf), section)
    return bytes(buf)


class RepairFunctionTests(unittest.TestCase):
    def test_legacy_image_is_repaired_inside_its_three_scopes_only(self) -> None:
        before = legacy_image()
        self.assertEqual((tc.status(before), tc.revision(before)), ("applied", 1))
        after, receipt = repair.repair_xbe(before)
        self.assertEqual((tc.status(after), tc.revision(after)), ("applied", 2))
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(receipt["upgraded_from_revision"], 1)
        self.assertTrue(receipt["outside_scope_identical"])
        self.assertEqual([s["name"] for s in receipt["scopes"]], ["cave", "post_hook", "text_section_digest"])
        scopes = repair.declared_scopes(before)
        allowed = set()
        for scope in scopes:
            allowed.update(range(scope["file_offset"], scope["file_offset"] + scope["size"]))
        changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        self.assertTrue(changed <= allowed, sorted(changed - allowed)[:8])
        self.assertEqual(receipt["changed_bytes"], len(changed))
        self.assertEqual(receipt["before_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(receipt["after_sha256"], hashlib.sha256(after).hexdigest())
        # the rollover hook and the six lists are verified identical, not rewritten
        names = [item["name"] for item in receipt["verified_identical_not_rewritten"]]
        self.assertEqual(names, ["rollover_hook"] + [f"list_{label}" for label, _v, _p in tc.COLUMN_LISTS])
        # the receipt scope hashes describe the bytes
        cave = receipt["scopes"][0]
        off = int(cave["file_offset"], 16)
        self.assertEqual(cave["before_sha256"], tc.LEGACY_CAVE_SHA256)
        self.assertEqual(cave["after_sha256"], hashlib.sha256(after[off: off + 512]).hexdigest())
        self.assertEqual(cave["after_sha256"], hashlib.sha256(tc.cave_bytes()).hexdigest())

    def test_repair_is_deterministic_and_idempotent(self) -> None:
        before = legacy_image()
        a, receipt_a = repair.repair_xbe(before)
        b, receipt_b = repair.repair_xbe(before)
        self.assertEqual(a, b)
        self.assertEqual(receipt_a, receipt_b)
        again, receipt = repair.repair_xbe(a)
        self.assertEqual(again, a)
        self.assertEqual(receipt["status"], "already_applied")
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_retail_and_foreign_images_are_refused(self) -> None:
        retail = _build_synthetic_xbe()
        with self.assertRaises(ValueError):
            repair.repair_xbe(retail)                       # the retail layout is the Studio's job, not this repair's
        for va in (tc.HOOK_VA + 2, tc.CAVE_VA + 100, tc.COLUMN_LISTS[1][1] + tc.LIST_POINTERS_OFF + 4):
            buf = bytearray(legacy_image())
            buf[tc._offset(bytes(buf), va)] ^= 0x5A
            with self.assertRaises(ValueError):
                repair.repair_xbe(bytes(buf))

    def test_prove_scope_detects_a_stray_byte(self) -> None:
        before = legacy_image()
        after, _receipt = repair.repair_xbe(before)
        bad = bytearray(after)
        bad[0x2000 + 10] ^= 0x01                           # somewhere in the synthetic .text, outside every scope
        proof = repair.prove_scope(before, bytes(bad), repair.declared_scopes(before))
        self.assertFalse(proof["outside_scope_identical"])
        self.assertTrue(proof["stray_runs"])


class RepairCliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> int:
        old = sys.argv
        sys.argv = ["f3_repair.py", *argv]
        try:
            return repair.main()
        finally:
            sys.argv = old

    def test_cli_hash_gate_outputs_and_refusals(self) -> None:
        before = legacy_image()
        digest = hashlib.sha256(before).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "default.xbe"
            source.write_bytes(before)
            out, receipt = tmp_path / "out.xbe", tmp_path / "receipt.json"
            # the default gate only accepts the exact v0.5 executable, so a synthetic image is refused with no files written
            with self.assertRaises(SystemExit):
                self._run([str(source), str(out), "--receipt", str(receipt)])
            self.assertFalse(out.exists() or receipt.exists())
            # an explicit expected hash accepts a stacked input
            self.assertEqual(self._run([str(source), str(out), "--receipt", str(receipt), "--expected-input-sha256", digest]), 0)
            self.assertEqual(tc.status(out.read_bytes()), "applied")
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], repair.SCHEMA)
            self.assertEqual(data["before_sha256"], digest)
            self.assertFalse(data["gameplay_witness"])
            self.assertNotIn(b"\r\n", receipt.read_bytes())
            # outputs are never overwritten
            with self.assertRaises(SystemExit):
                self._run([str(source), str(out), "--receipt", str(tmp_path / "r2.json"), "--expected-input-sha256", digest])
            # a symlinked source is refused
            link = tmp_path / "link.xbe"
            try:
                os.symlink(source, link)
            except (OSError, NotImplementedError):
                link = None
            if link is not None:
                with self.assertRaises(SystemExit):
                    self._run([str(link), str(tmp_path / "o3.xbe"), "--receipt", str(tmp_path / "r3.json"),
                               "--expected-input-sha256", digest])
            # the repaired file is idempotent through the CLI too
            out2, receipt2 = tmp_path / "out2.xbe", tmp_path / "receipt2.json"
            repaired = hashlib.sha256(out.read_bytes()).hexdigest()
            self.assertEqual(self._run([str(out), str(out2), "--receipt", str(receipt2), "--expected-input-sha256", repaired]), 0)
            self.assertEqual(out2.read_bytes(), out.read_bytes())
            self.assertEqual(json.loads(receipt2.read_text(encoding="utf-8"))["status"], "already_applied")


@unittest.skipUnless(V05_DISC.is_file(), "private v0.5 disc not present")
class RealV05ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tools = str(ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import nfl_uniform_color_xiso_direct_patch as xc

        fd = os.open(V05_DISC, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            entries, _ = xc.parse_xdvdfs(fd, size)
            entry = xc.file_extent(fd, size, "default.xbe", entries=entries)
            cls.xbe = xc.read_exact(fd, entry.byte_offset, entry.size)
        finally:
            os.close(fd)

    def test_the_exact_v0_5_executable_repairs_to_its_pinned_hash(self) -> None:
        self.assertEqual(hashlib.sha256(self.xbe).hexdigest(), repair.V05_SHA256)
        self.assertEqual((tc.status(self.xbe), tc.revision(self.xbe)), ("applied", 1))
        after, receipt = repair.repair_xbe(self.xbe)
        self.assertEqual(hashlib.sha256(after).hexdigest(), repair.V05_REPAIRED_SHA256)
        self.assertEqual(receipt["changed_bytes"], 301)
        self.assertTrue(receipt["outside_scope_identical"])
        self.assertEqual(len(after), len(self.xbe))
        # the sealed XBE-space allocator, the other owners' digests and every other byte are untouched
        again, second = repair.repair_xbe(after)
        self.assertEqual(again, after)
        self.assertEqual(second["status"], "already_applied")

    def test_no_other_owner_changes_state_when_the_column_is_upgraded(self) -> None:
        """Every patch that consults the TEAM column (defensive try, the Player Card star, the allocator owners) must read
        the v0.5 image and the repaired image identically, or a repair that runs before this one would see "foreign"."""

        from mod_editor.core import nfl2k5_throw_tuning as tt

        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before.xbe"
            after_path = Path(tmp) / "after.xbe"
            before.write_bytes(self.xbe)
            after_path.write_bytes(repair.repair_xbe(self.xbe)[0])
            a, b = tt.read_any(before), tt.read_any(after_path)
        changed = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
        self.assertEqual(set(changed), {"path", "xbe_sha256"}, changed)

    @unittest.skipUnless(importlib.util.find_spec("unicorn") is not None, "unicorn not installed")
    def test_the_native_franchise_scenario_before_and_after_on_the_real_roster(self) -> None:
        """The cause and the cure on the v0.5 roster, through the game's own code (see tools/b77/f3_native_scenario.py):
        before, every current-season row reads "--" and nothing is recorded; after, a trade, a signing, a release and an
        injured-reserve move all show the right club, and the rollover records nothing of its own."""

        body = scenario._rost_body(V05_DISC)
        legacy = scenario.run_scenario(self.xbe, body)
        self.assertEqual(scenario.check(legacy, "legacy"), [])
        self.assertEqual(legacy["plus_0x30_nonzero_records"], 0)
        self.assertEqual(legacy["players"], 2619)
        after, _receipt = repair.repair_xbe(self.xbe)
        fixed = scenario.run_scenario(after, body)
        self.assertEqual(scenario.check(fixed, "fixed"), [])
        steps = {row["step"]: row for row in fixed["rows"]}
        self.assertEqual(steps["traded, before he plays for the new club"]["trade"]["bank11"],
                         fixed["clubs"][scenario.CLUB_CHOICES["trade_to"]])
        self.assertEqual(fixed["pool_after"], fixed["pool_before_rollover"], "the rollover writes nothing")
        # the unrepaired executable fails the same checks, which is the bug
        self.assertTrue(scenario.check(legacy, "fixed"))


if __name__ == "__main__":
    unittest.main()
