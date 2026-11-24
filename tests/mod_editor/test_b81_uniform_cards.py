"""Build-order, protected-pixel and rollback cases for the 128 MB Team Select uniform card payload."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b81_uniforms import apply_cards, cards_unif

BOTH_CHANGED = {
    'old': {'jersey': 'old_jersey', 'pants': 'old_pants'},
    'new': {'jersey': 'new_jersey', 'pants': 'new_pants'},
}


class ProjectInputs(unittest.TestCase):
    def test_project_relative_paths_stay_in_the_explicit_reviewed_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'selected' / 'project.json'
            project.parent.mkdir()
            pic = project.parent / 'card.png'
            Image.new('RGBA', (2, 2)).save(pic)
            row = {
                'kind': 'team_select',
                'family': 'unif',
                'resolution': 256,
                'asset_code': '27',
                'style': 0,
                'side': 'home',
                'png': 'card.png',
            }
            project.write_text(json.dumps({'edits': [row]}))
            # The temporary root is deliberately left unresolved (macOS /var is a symlink, Windows TEMP can be an
            # 8.3 name); project_cards returns the card's canonical path.
            self.assertEqual(cards_unif.project_cards(project, project.parent), {'27H0': pic.resolve()})
            other = root / 'other.png'
            Image.new('RGBA', (2, 2)).save(other)
            project.write_text(json.dumps({'edits': [dict(row, png='../other.png')]}))
            with self.assertRaisesRegex(ValueError, 'leaves'):
                cards_unif.project_cards(project, project.parent)
            project.write_text(json.dumps({'edits': [row, row]}))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                cards_unif.project_cards(project, project.parent)

    def test_catalog_matches_the_entire_approved_uniform_manifest(self):
        rows = apply_cards.load_pins()
        docs = [
            json.loads((ROOT / 'data' / f'nfl2k5_{kind}_2026_b81u.json').read_text())
            for kind in ('kit_fixes', 'glyph_fixes', 'relief')
        ]
        requested = {row['selector'] for doc in docs for row in doc.get('textures', doc.get('slots', []))}
        # b81-uniform-pass2 (11/24): the shoulder-top number rows name two alternates no other row touched (05H6/05A6):
        # a data field only, their cards do not change
        self.assertEqual(len(requested), 180)
        self.assertTrue({'05A6', '05H6'} <= requested)
        drawn = {row['selector'] for doc in docs for row in doc.get('textures', doc.get('slots', [])) if row.get('kind') != 'unif'}
        self.assertEqual(len(drawn), 178)                   # kits whose look the pass draws: each has its card
        self.assertEqual(len(rows), 190)
        self.assertTrue({cards_unif.card_name(sel) for sel in drawn} <= rows.keys())
        for name, row in rows.items():
            self.assertEqual(len(row['stored_rgba_sha256']), 64)
            self.assertEqual(
                row['changed_pixels'] > 0, row['stored_rgba_sha256'] != row['source_native_sha256']
            )
            self.assertEqual(bool(row['replacement_sha256']), row['changed_pixels'] > 0)
            if row['selector'] not in requested:
                self.assertIsNone(row['replacement_sha256'], name)
                self.assertEqual(row['new_slot_sha256'], row['reviewed_slot_sha256'], name)


STANDARD_SOURCES = Path(os.environ.get("NFL2K5_B81_STANDARD_SOURCES", "") or "missing-NFL2K5_B81_STANDARD_SOURCES")


@unittest.skipUnless((STANDARD_SOURCES / "SOFTDRINK-league-project.json").is_file(),
                     "private release sources absent: NFL2K5_B81_STANDARD_SOURCES")
class StandardSources(unittest.TestCase):
    """The release build's league project (b81/env.sh NFL2K5_B81_STANDARD_SOURCES) references, for each of the 190 uniform
    card slots, exactly the pinned picture, by pixels and by file. Added 11/21, when 22 round 2 cards were missing from the
    release folder although every pin was right; a stale release folder fails here."""

    def test_every_uniform_card_of_the_release_sources_is_its_pinned_file(self):
        project = json.loads((STANDARD_SOURCES / "SOFTDRINK-league-project.json").read_text(encoding="utf-8"))
        rows = apply_cards.load_pins()
        seen = set()
        for edit in project["edits"]:
            if edit.get("kind") != "team_select" or edit.get("family") != "unif":
                continue
            side = "h" if edit["side"] == "home" else "a"
            name = f"unif_{side}{edit['asset_code']}_{int(edit['style'])}_{int(edit['resolution'])}"
            path = Path(edit["png"].replace("@pack/", f"{STANDARD_SOURCES}/"))
            row = rows[name]
            with self.subTest(card=name), Image.open(path) as image:
                pixels = np.ascontiguousarray(np.asarray(image.convert("RGBA"), dtype=np.uint8)).tobytes()
                self.assertEqual(hashlib.sha256(pixels).hexdigest(), row["new_rgba_sha256"])
                # a card the uniform pass left unchanged keeps the art lane's file (its pin has no new file)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 row["new_file_sha256"] or row["source_file_sha256"])
            seen.add(name)
        self.assertEqual(seen, set(rows))


class NativeColors(unittest.TestCase):
    def test_single_changed_view_leaves_the_other_garment_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jersey = np.zeros((8, 8, 4), dtype=np.uint8)
            jersey[:, :4, 3] = 255
            jersey[0, 4, 3] = 128
            for name in ('shirt1', 'shirt2', 'pants1', 'pants2'):
                pixels = jersey if name.startswith('shirt') else np.full_like(jersey, 255)
                Image.fromarray(pixels).save(root / (name + '.png'))
            old = {'jersey': root / 'shirt1.png', 'pants': root / 'pants1.png'}
            self.assertFalse(cards_unif.garment_support({'old': old, 'new': dict(old)}, (4, 4)).any())
            shirt = cards_unif.garment_support(
                {'old': old, 'new': dict(old, jersey=root / 'shirt2.png')}, (4, 4)
            )
            pants = cards_unif.garment_support(
                {'old': old, 'new': dict(old, pants=root / 'pants2.png')}, (4, 4)
            )
        self.assertTrue(shirt[:, :2].all())
        self.assertFalse(shirt[:, 3].any())
        self.assertTrue(shirt[0, 2])
        self.assertFalse(pants[:, :2].any())
        self.assertTrue(pants[:, 2:].all())

    def test_flat_interiors_of_a_changed_material_follow_the_physical_kit(self):
        source = np.full((64, 64, 4), [254, 196, 0, 255], dtype=np.uint8)
        source[:, 4:10, :3] = 0
        old = np.full_like(source, [254, 196, 0, 255])
        old[:, 32:38, :3] = 0
        new = old.copy()
        new[10:13, 50:53, :3] = [196, 70, 25]
        with patch.object(
            cards_unif, 'garment', side_effect=[cards_unif.premul(old), cards_unif.premul(new)]
        ):
            master, native, _ = cards_unif.make_output(
                '22A5', BOTH_CHANGED, source, source, np.zeros(source.shape[:2], dtype=bool)
            )
        self.assertTrue(np.array_equal(master, new))
        self.assertTrue(np.array_equal(native, new))

    def test_old_card_with_a_displaced_number_takes_the_new_garment_inside_a_real_edit(self):
        source = np.full((24, 24, 4), [220, 220, 220, 255], dtype=np.uint8)
        old = source.copy()
        new = source.copy()
        source[:, 7:9, :3] = [20, 100, 170]
        old[:, 9:11, :3] = [20, 100, 170]
        new[:, 13:15, :3] = [24, 112, 180]
        source[:, 0, :3] = [200, 30, 20]
        old[:, 0, 3] = new[:, 0, 3] = 0
        protected = np.zeros((24, 24), dtype=bool)
        with patch.object(
            cards_unif, 'garment', side_effect=[cards_unif.premul(old), cards_unif.premul(new)]
        ):
            master, native, _ = cards_unif.make_output('24H0', BOTH_CHANGED, source, source, protected)
        for result in (master, native):
            self.assertTrue(np.array_equal(result[:, 7:15], new[:, 7:15]))
            self.assertTrue(np.array_equal(result[:, 0], source[:, 0]))

    def test_free_palette_entry_keeps_the_visible_orange_detail(self):
        original = np.zeros((2, 510, 4), dtype=np.uint8)
        original[..., 3] = 255
        grey = np.repeat(np.arange(255, dtype=np.uint8), 2)
        original[0, :, :3] = grey[:, None]
        desired = original.copy()
        desired[1, :500, :3] = [246, 246, 246]
        desired[1, 500:, :3] = [218, 92, 37]
        mask = np.zeros(original.shape[:2], dtype=bool)
        mask[1] = True
        self.assertTrue(np.array_equal(cards_unif.native_palette(desired, original, mask), desired))

    def test_helmet_mask_covers_both_silhouettes_and_antialiasing_without_clipping_the_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for stage in ('old', 'new'):
                (root / stage).mkdir()
                layer = np.zeros((1024, 1024, 4), dtype=np.uint8)
                # Shell with a wide open visor, plus an isolated old/new facemask bar.
                layer[200:400, 200:400, 3] = 255
                layer[240:360, 240:360, 3] = 0
                x = 600 if stage == 'old' else 680
                layer[503, x + 3, 3] = 1
                Image.fromarray(layer).save(root / stage / '27H0_unif.png')
            mask, pins = cards_unif.protected_area(root, '27H0')
        self.assertEqual(set(pins), {'old', 'new'})
        self.assertTrue(mask[50, 50])
        for x in (150, 170):
            self.assertTrue(mask[125, x])
            self.assertTrue(mask[127, x + 2])
            self.assertFalse(mask[128, x])
        self.assertFalse(mask[75, 75])
        self.assertFalse(mask[95, 142])
        # A jersey outside the silhouette can change on both sides of the old enclosing rectangle.
        cloth = np.full((256, 256, 4), 70, np.uint8)
        cloth[..., 3] = 255
        before = cards_unif.premul(cloth)
        after = before.copy()
        after[..., 1] += 55
        with patch.object(cards_unif, 'garment', side_effect=[before, after]):
            master, native, _ = cards_unif.make_output('27H0', BOTH_CHANGED, cloth, cloth, mask)
        for colors in (master, native):
            self.assertTrue(np.array_equal(colors[mask], cloth[mask]))
            self.assertTrue(np.array_equal(colors[95, 170], [70, 125, 70, 255]))
            self.assertTrue(np.array_equal(colors[95, 174], colors[95, 170]))

    def test_delta_over_the_same_colored_helmet_never_changes_it(self):
        base = np.full((8, 8, 4), 75, np.uint8)
        base[..., 3] = 255
        stored = base.copy()
        stored[..., :3] = 71
        old = cards_unif.premul(base)
        new = old.copy()
        new[..., 0] += 60
        protected = np.zeros((8, 8), bool)
        protected[2:5, 2:5] = True
        with patch.object(cards_unif, 'garment', side_effect=[old, new]):
            master, imported, counts = cards_unif.make_output('27H0', BOTH_CHANGED, base, stored, protected)
        self.assertTrue(np.array_equal(master[protected], base[protected]))
        self.assertTrue(np.array_equal(imported[protected], stored[protected]))
        self.assertEqual(counts['changed_pixels'], 55)
        self.assertEqual(counts['protected_native_changed'], 0)
        self.assertTrue(np.array_equal(imported[..., 3], stored[..., 3]))

    def test_full_native_palette_preserves_every_pinned_color_and_the_alpha(self):
        original = np.empty((16, 32, 4), dtype=np.uint8)
        grey = np.arange(256, dtype=np.uint8).reshape(16, 16)
        original[:, :16, :3] = grey[..., None]
        original[:, :16, 3] = np.where(grey % 2, 128, 255)
        original[:, 16:] = original[:, :16]
        mask = np.zeros(original.shape[:2], bool)
        mask[:, 16:] = True
        desired = original.copy()
        desired[mask, 1] = 90
        desired[mask, 2] = 24
        candidate = cards_unif.native_palette(desired, original, mask)
        self.assertTrue(np.array_equal(candidate[~mask], original[~mask]))
        self.assertTrue(np.array_equal(candidate[..., 3], original[..., 3]))
        self.assertGreater(np.any(candidate != original, axis=2).sum(), 0)
        level = cards_unif.palette_tools.MipLevel(0, 32, 16, candidate.tobytes())
        colors, indices, _ = cards_unif.palette_tools.quantize_levels([level])
        self.assertEqual(cards_unif.palette_tools.rgba_from_indices(indices[0], colors), candidate.tobytes())


class StagedDisc(unittest.TestCase):
    def test_complete_preflight_accepts_resume_and_restores_after_partial_write(self):
        class Archive:
            def __init__(self):
                self.parts = {i: b'HEADaaaaPAD' for i in range(3)}
                self.truncate_at = None

            def read(self, at, size):
                return self.parts[at][:size]

            def write(self, at, data):
                if self.truncate_at == at:
                    self.truncate_at = None
                    self.parts[at] = data[:6] + self.parts[at][6:]
                    return 6
                self.parts[at] = data
                return len(data)

        archive = Archive()
        old = dict(archive.parts)
        names = ['unif_h00_0_256', 'unif_h01_0_256', 'unif_h02_0_256']

        def locate(arc, group, name):
            index = names.index(name + '_256')
            return index, arc.parts[index]

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(apply_cards.slots, 'locate', locate),
            patch.object(apply_cards, 'stored', lambda b: (apply_cards.sha(b[4:8]), 4)),
        ):
            root = Path(directory)
            (root / 'native').mkdir()
            pins = {}
            for i, name in enumerate(names):
                target = b'HEADbbbb' if i < 2 else None
                pins[name] = {
                    'source_native_sha256': apply_cards.sha(b'aaaa'),
                    'stored_rgba_sha256': apply_cards.sha(b'bbbb' if target else b'aaaa'),
                    'replacement_sha256': apply_cards.sha(target) if target else None,
                    'replacement_size': len(target) if target else 0,
                    'reviewed_slot_sha256': apply_cards.sha(old[i]),
                    'new_slot_sha256': apply_cards.sha(target + b'PAD' if target else old[i]),
                }
                if target:
                    (root / 'native' / (name + '.txtr.bin')).write_bytes(target)
            archive.parts[2] = b'HEAD???APAD'
            with self.assertRaisesRegex(ValueError, 'foreign stored'):
                apply_cards.update_archive(archive, root, pins, write=True)
            self.assertEqual(archive.parts[0], old[0])
            archive.parts[2] = b'HEADaaaaBAD'
            with self.assertRaisesRegex(ValueError, 'full card slot'):
                apply_cards.update_archive(archive, root, pins, write=True)
            self.assertEqual(archive.parts[0], old[0])
            archive.parts[2] = old[2]
            archive.truncate_at = 1
            with self.assertRaises(OSError):
                apply_cards.update_archive(archive, root, pins, write=True)
            self.assertEqual(archive.parts, old)
            archive.parts[0] = b'HEADbbbbPAD'
            self.assertEqual(apply_cards.update_archive(archive, root, pins)['pending'], 1)
            result = apply_cards.update_archive(archive, root, pins, write=True)
            self.assertEqual((result['written'], result['checked'], len(result['final'])), (1, 3, 3))
            self.assertEqual(archive.parts, {0: b'HEADbbbbPAD', 1: b'HEADbbbbPAD', 2: old[2]})
            self.assertEqual(apply_cards.update_archive(archive, root, pins, write=True)['written'], 0)


class RendererChoice(unittest.TestCase):
    """R2-F: the renders come from the NVIDIA driver, or with --software-gl from Mesa llvmpipe on a private display;
    never llvmpipe by accident, never the owner's own display, and the renderer is part of every cache key."""

    def render(self, renderer, display, software):
        def check_output(cmd, text=True):
            return 'Blender 4.0.2\n' if cmd[0] == 'blender' else f'OpenGL renderer string: {renderer}\n'

        with tempfile.TemporaryDirectory() as folder, \
                patch.object(cards_unif.subprocess, 'check_output', side_effect=check_output), \
                patch.dict(cards_unif.os.environ, {'DISPLAY': display}), \
                patch.object(cards_unif, 'sha', return_value='0' * 64), \
                patch.object(cards_unif.Path, 'read_bytes', return_value=b''):
            return cards_unif.render_layers({}, Path(folder), Path(folder), 16, software)

    def test_llvmpipe_is_refused_unless_asked_for(self):
        with self.assertRaises(ValueError):
            self.render('llvmpipe (LLVM 20.1.2, 256 bits)', ':187', False)

    def test_software_needs_a_private_display_and_llvmpipe(self):
        for renderer, display in (('llvmpipe (LLVM 20.1.2, 256 bits)', ':0'),
                                  ('llvmpipe (LLVM 20.1.2, 256 bits)', ''),
                                  ('NVIDIA GeForce RTX 2080 Ti/PCIe/SSE2', ':187')):
            with self.subTest(renderer=renderer, display=display), self.assertRaises(ValueError):
                self.render(renderer, display, True)

    def test_software_on_a_private_display_is_recorded(self):
        _layers, meta = self.render('llvmpipe (LLVM 20.1.2, 256 bits)', ':187', True)
        self.assertTrue(meta['software_gl'])
        self.assertIn('llvmpipe', meta['opengl'])
        _layers, meta = self.render('NVIDIA GeForce RTX 2080 Ti/PCIe/SSE2', ':187', False)
        self.assertNotIn('software_gl', meta)


if __name__ == '__main__':
    unittest.main()
