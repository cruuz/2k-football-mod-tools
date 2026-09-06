"""The Madden 09 (PS2) container inventory lane, on synthetic discs only.

Nothing here needs a game: the source is built by
``mod_editor.games.madden09_ps2.containers.build_synthetic_disc`` out of the
container writer's own rules.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games._formats import ea_terf  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import containers, inventory_lane  # noqa: E402
from mod_editor.games.madden09_ps2.disc_identity import Madden09DiscIdentifier  # noqa: E402
from mod_editor.games.madden09_ps2 import IDENTITY  # noqa: E402


class SyntheticDiscTests(unittest.TestCase):
    """The fixture the whole module is proved on."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-inventory-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.source = self.work / "synthetic.iso"
        self.source.write_bytes(containers.build_synthetic_disc())

    def test_the_synthetic_disc_boots_the_module_s_serial(self) -> None:
        identity = Madden09DiscIdentifier(IDENTITY).identify(self.source)
        self.assertEqual(identity.serial, containers.SERIAL)
        self.assertTrue(identity.serial_matches)
        self.assertFalse(identity.retail_executable,
                         "a synthetic disc must never pass as retail")
        self.assertIn("unknown edition", identity.headline)

    def test_a_disc_with_another_serial_is_refused_by_sentence(self) -> None:
        import ps2_iso9660 as iso_lib

        other = self.work / "other.iso"
        other.write_bytes(iso_lib.build_synthetic_iso(files=[
            (b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.00\r\n"),
            (b"SLUS_209.19;1", b"\x7fELF" + bytes(4092)),
        ]))
        with self.assertRaises(Refusal) as caught:
            Madden09DiscIdentifier(IDENTITY).identify(other)
        self.assertIn("SLUS-21770", str(caught.exception))
        self.assertIn("choose that image", str(caught.exception))

    def test_both_containers_walk_to_their_declared_shape(self) -> None:
        image = containers.open_disc(self.source)
        names = {entry.name for entry in containers.data_files(image)}
        self.assertEqual(names, set(containers.SYNTHETIC_CONTAINERS))
        report, container = containers.describe_container(
            image, next(e for e in containers.data_files(image)
                        if e.name == containers.UNIFORM_CONTAINER))
        self.assertEqual(report.chunk_chain, "TERF -> DIR1 -> COMP -> DATA")
        self.assertEqual(report.member_count, 4)
        self.assertEqual(report.layout_violations, ())
        self.assertEqual(report.format_histogram.get("MMAP"), 3)
        self.assertIsNotNone(container)

    def test_a_file_with_no_data_directory_is_refused(self) -> None:
        import ps2_iso9660 as iso_lib

        flat = self.work / "flat.iso"
        flat.write_bytes(iso_lib.build_synthetic_iso(sub_name=b"OTHER", sub_files=[
            (b"NOTHING.BIN;1", bytes(64)),
        ]))
        image = containers.open_disc(flat)
        with self.assertRaises(containers.DiscError) as caught:
            containers.data_files(image)
        self.assertIn("/DATA", str(caught.exception))

    def test_a_container_over_the_limit_is_named_not_truncated(self) -> None:
        image = containers.open_disc(self.source)
        entry = next(e for e in containers.data_files(image)
                     if e.name == containers.UNIFORM_CONTAINER)
        with self.assertRaises(containers.DiscError) as caught:
            containers.read_file(image, entry, limit=16)
        self.assertIn("left unread", str(caught.exception))

    def test_load_container_refuses_a_name_the_disc_does_not_have(self) -> None:
        image = containers.open_disc(self.source)
        with self.assertRaises(containers.DiscError) as caught:
            containers.load_container(image, "NOSUCH.DAT")
        self.assertIn("NOSUCH.DAT", str(caught.exception))
        self.assertIn(containers.SERIAL, str(caught.exception))


class InventoryLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-inventory-lane-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = inventory_lane.InventoryLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_the_lane_is_read_only_and_lands_on_the_textures_page(self) -> None:
        self.assertTrue(self.lane.read_only)
        self.assertEqual(self.lane.page, "textures")
        self.assertEqual(self.lane.classification, "read-only-mapped")

    def test_the_catalogue_names_containers_and_members(self) -> None:
        keys = [target.key for target in self.catalogue.targets]
        self.assertIn(f"container:{containers.UNIFORM_CONTAINER}", keys)
        self.assertIn(f"member:{containers.UNIFORM_CONTAINER}:0", keys)
        document = self.catalogue.document
        self.assertEqual(document["containers"], 2)
        self.assertEqual(document["members"], 6)
        self.assertEqual(document["format_totals"].get("MMAP"), 3)

    def test_every_field_on_every_target_is_read_only(self) -> None:
        editable = [target.key for target in self.catalogue.targets
                    if any(not field.read_only for field in target.fields)]
        self.assertEqual(editable, [])

    def test_the_document_is_json_and_carries_no_payload(self) -> None:
        from mod_editor.games.conformance import contains_payload

        text = json.dumps(self.catalogue.document, default=dict)
        self.assertFalse(contains_payload(json.loads(text)))

    def test_the_three_writing_methods_refuse_with_the_same_sentence(self) -> None:
        recipe = self.lane.compose_recipe(())
        for call in (
            lambda: self.lane.plan(self.source, recipe, self.catalogue),
            lambda: self.lane.build(self.source, self.work / "never.out", recipe,
                                    self.catalogue),
            lambda: self.lane.verify(self.source, self.work / "never.out", None),
            lambda: self.lane.conformance_edits(self.catalogue),
        ):
            with self.assertRaises(Refusal) as caught:
                call()
            self.assertEqual(str(caught.exception), self.lane.REFUSAL)
        self.assertFalse((self.work / "never.out").exists())

    def test_check_edit_says_no_to_every_value(self) -> None:
        target = self.catalogue.targets[0]
        self.assertEqual(self.lane.check_edit(target, {"anything": 1}), self.lane.REFUSAL)

    def test_a_member_whose_codec_this_reader_lacks_is_named_not_hidden(self) -> None:
        """An unopenable member is a state of its own, never 'unclassified'."""

        payload = containers.synthetic_mmap(8, 8)
        container = ea_terf.parse_terf(ea_terf.build_terf([payload], chunk="COMP"))
        # Rewrite the member's codec id to one nothing implements.
        raw = bytearray(container._data)  # noqa: SLF001 - the fixture pokes its own bytes
        comp = container.chunk("COMP")
        assert comp is not None
        raw[comp.offset + 8:comp.offset + 12] = (ea_terf.CODEC_HUFF).to_bytes(4, "little")
        poked = ea_terf.parse_terf(bytes(raw))
        self.assertEqual(inventory_lane.InventoryLane._member_format(poked, 0),
                         "unsupported codec")

    def test_the_command_line_selftest_runs_without_a_disc(self) -> None:
        self.assertEqual(inventory_lane._main(["--source", "unused", "--selftest"]), 0)


if __name__ == "__main__":
    unittest.main()
