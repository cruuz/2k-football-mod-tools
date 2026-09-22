"""DL comparison integrity and optional pinned native regression proofs."""
from dataclasses import replace
import os
from pathlib import Path
import unittest

from mod_editor.core import apf2k8_play_codec as codec
from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.core import apf2k8_fourth_down as fourth
from mod_editor.core.apf2k8_playbook_route_writer import (
    read_master_play_body, compile_route_clones, RouteCloneRequest,
)
from mod_editor.core.apf2k8_formation_alignment_writer import (
    swap_formation_slots, compile_formation_alignments,
)
from tests.mod_editor.test_apf_play_designer import synthetic
from tools.apf_dl_instruction_probe import compare_masters, native_proof


class ComparisonTests(unittest.TestCase):
    def test_shared_node_change_detected_without_assignment_pointer_change(self):
        before = synthetic()
        book = codec.Book.from_bytes(before)
        nodes = list(book.nodes)
        node = nodes[7]
        values = list(node.operands)
        values[1] += 30.48
        nodes[7] = replace(node, operands=tuple(values))
        result = compare_masters(before, replace(book, nodes=tuple(nodes)).to_bytes())
        self.assertEqual([p['play'] for p in result['changed']], [2, 3])
        for p in result['changed']:
            self.assertEqual(p['before']['record_sha256'], p['after']['record_sha256'])

    def test_alignment_writer_changes_geometry_without_changing_defensive_assignments(self):
        before = synthetic()
        edit = swap_formation_slots(before, 1, [(0, 1)])
        after, _ = compile_formation_alignments(before, [edit])
        self.assertNotEqual(before, after)
        self.assertEqual(compare_masters(before, after)['changed'], [])

    def test_route_writer_changes_only_explicit_defensive_target(self):
        before = synthetic()
        # Deliberately cross-side donor: this checks scope, not valid gameplay.
        after = compile_route_clones(before, [RouteCloneRequest(2, 0, 0, 0)]).replacement
        diff = compare_masters(before, after)['changed']
        self.assertEqual([p['play'] for p in diff], [2])
        self.assertEqual([a['slot'] for a, b in zip(diff[0]['before']['slots'], diff[0]['after']['slots'])
                          if a != b], [0])


class NativeTests(unittest.TestCase):
    def test_base_and_tu_with_and_without_shipped_runtime_options(self):
        try:
            import unicorn  # noqa: F401
        except ImportError as exc:
            self.skipTest(str(exc))
        index = Path(os.environ.get('APF_RETAIL_INDEX', 'extracted/All-Pro Football 2K8 (USA)/0A'))
        images = [os.environ.get('APF_RETAIL_PE'), os.environ.get('APF_TU_PE')]
        if not index.is_file() or not all(images) or not all(Path(p).is_file() for p in images):
            self.skipTest('Set APF_RETAIL_INDEX, APF_RETAIL_PE and APF_TU_PE to owned pinned inputs')
        master = read_master_play_body(index)
        for i, path in enumerate(images):
            image = Path(path).read_bytes()
            with self.subTest(profile=i):
                stock = native_proof(image, master)
                policies = {'O-ManBlock': [[14] for _ in range(12)]}
                rows = {'O-ManBlock': [{'6': 10} for _ in range(12)]}
                situation = mask.compile_patch(image, policies, rows)
                document = fourth.PatchDocument(fourth.PROFILES[i], fourth.Thresholds(
                    short_yards=3, own_half_limit=75, fallback_threshold=1), enabled=True)
                fourth.verify_image(image, document)
                patched = native_proof(image, master, (*situation.words, *document.words))
                for field in ('pairs', 'operand_reads', 'cpu_lane_resolutions',
                              'human_team_guard_entries', 'shift_distributions'):
                    self.assertEqual(stock[field], patched[field], field)
                self.assertNotEqual(stock['executed_image_sha256'], patched['executed_image_sha256'])


if __name__ == '__main__':
    unittest.main()
