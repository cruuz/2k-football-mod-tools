"""Protected wiring rehearsal and optional disposable retail-image acceptance.

Full builds require NFL2K5_PAIRING_REAL_BUILD=1 and enough free space to keep
100 GB free even while a resource writer holds two output copies. They never
place an image/pack in .scratch. The protected module is only read.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_play_intents as intents
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_play_library as library
from mod_editor.core import nfl2k5_depth_roles as roles
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_play_intents import BookArchive, pool_resource, EXTRACT

SOURCE = ROOT / "mod_editor/core/mod_build.py"
IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE",
    "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
OLD_PAIRING = '''    if plan.read_option_runtime or plan.qb_spy:
        _verify_play_intents(target, spy_pairs)
    read_table, read_receipt = (tt.read_option_patch.compile_intent_table(spy_pairs)
                                if plan.read_option_runtime else (None, None))
    if plan.read_option_runtime and not read_receipt["count"]:
        raise ValueError("Read option mesh controls need at least one paired authored read recipe")
'''
NEW_PAIRING = '''    if plan.read_option_runtime or plan.qb_spy:
        resolver = _core_module("nfl2k5_play_intents")
        if resolver is None:
            raise RuntimeError("The final playbook pairing module is not available in this build")
        spy_pairs = resolver.resolve_final_pairs(
            target, spy_pairs, progress=lambda msg: progress(msg, 0, 0))
    read_table, read_receipt = (tt.read_option_patch.compile_intent_table(spy_pairs)
                                if plan.read_option_runtime else (None, None))
    spy_table, spy_table_receipt = (tt.qb_spy_patch.compile_intent_table(spy_pairs)
                                    if plan.qb_spy else (None, None))
    if plan.read_option_runtime and not read_receipt["count"]:
        raise ValueError("Read option mesh controls need at least one paired authored read recipe")
    if plan.read_option_runtime or plan.qb_spy:
        _verify_play_intents(target, spy_pairs)
        receipt["play_intents_final"] = {
            **resolver.resolution_receipt(spy_pairs),
            "read_option_count": read_receipt["count"] if read_receipt else 0,
            "qb_spy_count": spy_table_receipt["count"] if spy_table_receipt else 0,
        }
        counts = receipt["play_intents_final"]
        receipt["play_intents_summary"] = (
            f"Final playbooks paired: {counts['read_option_count']} read option plays, "
            f"{counts['qb_spy_count']} QB spy assignments. EXPERIMENTAL / UNWITNESSED.")
'''
OLD_SPY = '        spy_table, spy_table_receipt = (tt.qb_spy_patch.compile_intent_table(spy_pairs) if plan.qb_spy else (None, None))\n'
OLD_RECEIPT = '                                 "read_option_intent_table": read_receipt, "qb_spy_intent_table": spy_table_receipt, "music_shuffle_preflight": playlist_preflight,\n'
NEW_RECEIPT = OLD_RECEIPT + '                                 "play_intents_final": receipt.get("play_intents_final"),\n'


def wired_source():
    text = SOURCE.read_text(encoding="utf-8")
    if NEW_PAIRING in text and OLD_SPY not in text and NEW_RECEIPT in text:
        return text  # the protected handoff has already landed
    for old, new in ((OLD_PAIRING, NEW_PAIRING), (OLD_SPY, ""), (OLD_RECEIPT, NEW_RECEIPT)):
        if text.count(old) != 1:
            raise AssertionError("Protected Build source moved; review the pairing handoff before rehearsing")
        text = text.replace(old, new, 1)
    return text


def load_wired_build(directory):
    path = Path(directory).resolve() / "mod_build.py"
    path.write_text(wired_source(), encoding="utf-8", newline="\n")
    name = "mod_editor.core._read_option_pairing_build_proof"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.ROOT = ROOT  # the copied module's resource root is still this checkout
    return module


def disk_preflight(parent, image_size):
    """The 100 GB floor applies after two disposable copies plus growth margin."""
    free = shutil.disk_usage(parent).free
    needed = 100_000_000_000 + 2 * image_size + 512_000_000
    return dict(free_bytes=free, required_free_bytes=needed, floor_bytes=100_000_000_000,
                image_bytes=image_size, allowed=free >= needed)


class WiringTests(unittest.TestCase):
    def test_scratch_copy_exactly_matches_reviewable_patch(self):
        text = SOURCE.read_text()
        if OLD_PAIRING in text:
            # Apply the reviewable hunks by context so unrelated line-number
            # changes do not invalidate this integration test.
            patch_text = (ROOT / "tests/fixtures/read_option_pairing_wiring.patch").read_text()
            for hunk in patch_text.split("@@\n")[1:]:
                lines = hunk.split("\n@@", 1)[0].splitlines(keepends=True)
                old = "".join(line[1:] for line in lines if line.startswith((" ", "-")))
                new = "".join(line[1:] for line in lines if line.startswith((" ", "+")))
                self.assertEqual(text.count(old), 1)
                text = text.replace(old, new, 1)
            self.assertEqual(text, wired_source())
        before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="pairing-wiring-") as folder:
            rehearsal = load_wired_build(folder)
            self.assertIsNot(rehearsal, mod_build)
            self.assertEqual(rehearsal.PRESETS, mod_build.PRESETS)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), before)

    def test_disk_floor_accounts_for_writer_rebuild_and_growth(self):
        size = 6_300_499_968
        with patch.object(shutil, "disk_usage", return_value=type("Usage", (), {"free": 110_000_000_000})()):
            self.assertFalse(disk_preflight(ROOT, size)["allowed"])
        with patch.object(shutil, "disk_usage", return_value=type("Usage", (), {"free": 120_000_000_000})()):
            self.assertTrue(disk_preflight(ROOT, size)["allowed"])


class RetailResourceTests(unittest.TestCase):
    def test_actual_pack_pool_depth_writers_and_final_verifier(self):
        if not IMAGE.is_file():
            self.skipTest("retail XISO absent; set NFL2K5_RETAIL_IMAGE")
        recode = packs._outer_image()
        with recode.OuterImage(IMAGE) as source:
            resources = {team: source.read_entry(index) for team, index in recode.BOOK_ENTRIES.items()}
        archive = BookArchive(resources)
        retained = []
        packs.apply_packs_to_archive(archive, [("softdrink_option.2k5book",
            packs.load_pack(ROOT / "data/playbooks/softdrink_option.2k5book"))], collector=retained)
        for index, resource in archive.resources.items():
            archive.resources[index] = pool_resource(resource)
        before = archive.resources[recode.BOOK_ENTRIES["MIN"]]
        role_receipt = roles.apply_to_archive(archive, allow_custom=True)
        final = archive.resources[recode.BOOK_ENTRIES["MIN"]]
        self.assertEqual(len(role_receipt["books"]), 37)
        with patch.object(recode, "OuterImage", return_value=archive):
            with self.assertRaisesRegex(ValueError, "Paired PLAY resource changed"):
                mod_build._verify_play_intents(IMAGE, retained)
            pairs = intents.resolve_final_pairs(IMAGE, retained)
            mod_build._verify_play_intents(IMAGE, pairs)
        table, receipt = read.compile_intent_table(pairs)
        self.assertEqual(receipt["count"], 2)
        for pi in (155, 157):
            self.assertEqual(library.play_chains(before[32:], pi), library.play_chains(final[32:], pi))
        xbe_path = EXTRACT / "default.xbe"
        if not xbe_path.is_file():
            self.skipTest("retail PLAY proof passed; pinned XBE absent for active-table installation")
        xbe = xbe_path.read_bytes()  # 12 MiB, never an image or pack
        if hashlib.sha256(xbe).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail PLAY proof passed; local XBE differs from the supported USA pin")
        outputs = []
        for reverse in (False, True):
            allocated, _ = space.apply(xbe, read.REQUESTS + spy.REQUESTS, scaleout=True)
            owners = [(read, table), (spy, spy.compile_intent_table(pairs)[0])]
            for owner, owner_table in reversed(owners) if reverse else owners:
                allocated, _ = owner.apply(allocated, intent_table=owner_table)
            self.assertEqual((read.status(allocated), spy.status(allocated)), ("applied", "applied"))
            self.assertEqual(read.read_settings(allocated)["authored_reads"], 2)
            installed = XbeImage(allocated).read(read.allocations(allocated)["read_only"]["va"], read.TABLE_SIZE)
            self.assertEqual(installed, table)
            outputs.append(hashlib.sha256(allocated).hexdigest())
        self.assertEqual(outputs[0], outputs[1])


@unittest.skipUnless(os.environ.get("NFL2K5_PAIRING_REAL_BUILD") == "1",
                     "full retail builds require NFL2K5_PAIRING_REAL_BUILD=1")
class RetailBuildTests(unittest.TestCase):
    def build_case(self, with_spy):
        if not IMAGE.is_file():
            self.skipTest("retail XISO absent; set NFL2K5_RETAIL_IMAGE")
        scratch = ROOT / ".scratch/read-option-pairing"
        scratch.mkdir(parents=True, exist_ok=True)
        case = "read-and-spy" if with_spy else "read-only"
        subprocess.run(["df", "-h", "/"], check=True) if os.name == "posix" else None
        guard = disk_preflight(ROOT, IMAGE.stat().st_size)
        (scratch / f"{case}-disk.json").write_text(json.dumps(guard, indent=2) + "\n")
        rehearsal = load_wired_build(scratch)
        if not guard["allowed"]:
            self.skipTest(f"100 GB disk floor: {guard['free_bytes']} free; {guard['required_free_bytes']} required")
        with tempfile.TemporaryDirectory(prefix="read-option-pairing-", dir=ROOT) as folder:
            target = Path(folder).resolve() / "acceptance.iso"
            plan = rehearsal.apply_preset(rehearsal.BuildPlan(str(IMAGE), str(target)), "softdrink_experimental")
            plan = replace(plan, read_option_runtime=True, qb_spy=with_spy,
                           playbook_packs=(str(ROOT / "data/playbooks/softdrink_option.2k5book"),))
            with (scratch / f"{case}-progress.log").open("w") as log:
                def progress(message, *_):
                    log.write(message + "\n")
                    log.flush()
                receipt = rehearsal.build(plan, progress)
            rehearsal.save_receipt(receipt, scratch / f"{case}-receipt.json")
            self.assertEqual(receipt["read_option_preflight"]["count"], 2)
            self.assertEqual(receipt["play_intents_final"]["read_option_count"], 2)
            step = next(s for s in receipt["steps"] if s["step"] == "xbe_space")
            self.assertGreaterEqual(step["read_option_intent_table"]["count"], 2)
            xbe = rehearsal._xbe_bytes(target)
            self.assertEqual(read.status(xbe), "applied")
            self.assertEqual(spy.status(xbe), "applied" if with_spy else "retail")
            recode = packs._outer_image()
            with recode.OuterImage(target) as archive:
                final = archive.read_entry(recode.BOOK_ENTRIES["MIN"])
            book = packs.parse_playbook_resource(final)
            names = {book.plays[r["play_index"]].name for r in step["read_option_intent_table"]["records"]}
            self.assertEqual(names, {"SD Zone Read EXPERIMENTAL", "SD RPO EXPERIMENTAL"})
            self.assertEqual(hashlib.sha256(final).hexdigest(),
                             step["read_option_intent_table"]["records"][0]["resource_sha256"])
        self.assertFalse(target.exists())
        self.assertGreaterEqual(shutil.disk_usage(ROOT).free, guard["floor_bytes"])

    def test_experimental_read_option(self):
        self.build_case(False)

    def test_experimental_read_option_and_qb_spy(self):
        self.build_case(True)


if __name__ == "__main__":
    unittest.main()
