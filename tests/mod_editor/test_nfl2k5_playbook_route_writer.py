from __future__ import annotations

import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_playbook_inspector import PLAY_BASE, parse_playbook_resource
from mod_editor.core.nfl2k5_playbook_route_writer import (
    PlayRouteCloneRequest,
    compile_play_route_clones,
)
from tests.mod_editor.test_nfl2k5_playbook_inspector import _fixture


class Nfl2k5PlaybookRouteWriterTests(unittest.TestCase):
    def test_copies_descriptor_and_retargets_relative_pointer_only(self) -> None:
        source = _fixture()
        compiled = compile_play_route_clones(source, (
            PlayRouteCloneRequest(
                "nfl2k5.resource.test.PLAY", 0, 3, 1, 7
            ),
        ))
        before = parse_playbook_resource(source)
        after = parse_playbook_resource(compiled.replacement)
        donor = before.plays[1].assignments[7]
        actual = after.plays[0].assignments[3]
        self.assertEqual(actual.descriptor_word, donor.descriptor_word)
        self.assertEqual(actual.chain_start_index, donor.chain_start_index)
        self.assertGreater(compiled.changed_byte_count, 0)
        self.assertLessEqual(compiled.changed_byte_count, 8)
        self.assertTrue(compiled.report["claims"]["source_and_replacement_fully_reparsed"])

        allowed = set()
        descriptor = 0x20 + PLAY_BASE + 8 + 3 * 8
        for start in (descriptor, descriptor + 4):
            allowed.update(range(start, start + 4))
        changed = {
            index for index, (left, right) in enumerate(
                zip(source, compiled.replacement)
            ) if left != right
        }
        self.assertTrue(changed)
        self.assertLessEqual(changed, allowed)

    def test_multiple_targets_compile_from_retail_donors_in_one_pass(self) -> None:
        compiled = compile_play_route_clones(_fixture(), (
            PlayRouteCloneRequest("book", 0, 0, 1, 0),
            PlayRouteCloneRequest("book", 1, 1, 0, 1),
        ))
        result = compiled.parsed_replacement
        self.assertEqual(result.plays[0].assignments[0].chain_start_index, 2)
        self.assertEqual(result.plays[1].assignments[1].chain_start_index, 0)
        self.assertTrue(compiled.selector.startswith("play-route-bundle:"))

    def test_duplicate_target_and_noop_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "repeats"):
            compile_play_route_clones(_fixture(), (
                PlayRouteCloneRequest("book", 0, 0, 1, 0),
                PlayRouteCloneRequest("book", 0, 0, 1, 1),
            ))
        with self.assertRaisesRegex(ValidationError, "different donor"):
            compile_play_route_clones(
                _fixture(), (PlayRouteCloneRequest("book", 0, 0, 0, 0),)
            )

    def test_malformed_indices_fail_before_any_output(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Donor play"):
            compile_play_route_clones(
                _fixture(), (PlayRouteCloneRequest("book", 0, 0, 99, 0),)
            )


if __name__ == "__main__":
    unittest.main()
