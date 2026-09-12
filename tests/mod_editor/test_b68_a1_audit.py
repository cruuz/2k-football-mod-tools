"""Independent beta-68 integration regressions; synthetic inputs only."""
from contextlib import redirect_stdout
from dataclasses import replace
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
from test_b68_t1_build import backend
from test_nfl2k5_equipment_texture_chain import Fixture, writer, digest
from mod_editor.core.nfl2k5_equipment_import_intent import with_retail_source, with_import_mode
from mod_editor.core.nfl2k5_compile_cache import CompileCache
from nfl_txtr import decode_chunk, parse_chunks, encode_rgba_png, swizzle_2d


def load_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class IntegrationTests(unittest.TestCase):
    def test_runtime_counts_match_the_canonical_registry(self):
        from mod_editor.core.capabilities import CapabilityRegistryLoader
        from mod_editor.core.product_catalog import build_nfl2k5_product_catalog
        registry = CapabilityRegistryLoader().load(allow_sample_fallback=False, check_files=False)
        catalog = build_nfl2k5_product_catalog(registry)
        self.assertEqual(len(registry.capabilities), 161)
        self.assertEqual(len(catalog.capabilities), 91)
        path = ROOT / 'packaging/check_2k5_mod_studio_runtime.py'
        source = path.read_text()
        # Execute the production assertions against the actual registry, without
        # requiring unrelated private catalogs or a staged application tree.
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                expression = ast.get_source_segment(source, node)
                if expression.startswith(('require(len(registry.capabilities)',
                                          'require(len(product_catalog.capabilities)')):
                    with self.subTest(expression=expression):
                        exec(expression, dict(require=self.assertTrue, registry=registry, product_catalog=catalog))
        self.assertTrue('registry=161 sections=12 nfl2k5_capabilities=91' in source)
        self.assertIn('registry=161 sections=12 nfl2k5_capabilities=91',
                      (ROOT / 'tests/mod_editor/test_phase1_packaging.py').read_text())

    def test_new_core_modules_are_in_all_release_closures(self):
        gate = load_path('_a1_runtime', ROOT / 'packaging/check_2k5_mod_studio_runtime.py')
        from mod_editor.core.providers import Nfl2k5UnifiedVisualProvider
        name = 'mod_editor/core/nfl2k5_compile_cache.py'
        self.assertIn(name, gate.REQUIRED_UNIFIED_PROVIDER_CLOSURE)
        self.assertIn(name, (ROOT / 'packaging/release-allowlist.txt').read_text().splitlines())
        self.assertEqual(Nfl2k5UnifiedVisualProvider.module_pins[name],
                         hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
        tree = ast.parse(Path(gate.__file__).read_text())
        assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'product_modules' for t in node.targets))
        self.assertIn('mod_editor.core.nfl2k5_compile_cache', ast.literal_eval(assignment.value))

class PaletteIntentTests(unittest.TestCase):
    def test_unchanged_span_keeps_its_original_stream_and_reports_actual_transport(self):
        from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
        from nfl_txtr import HEADER, minimum_vc_lz_overlap_scratch
        from nfl_vc_lz_fill import fill_stream
        with tempfile.TemporaryDirectory() as folder:
            f = Fixture(Path(folder).resolve())
            optimal = compress_equipment_optimal(f.decoded, stream_tag=1, offset_bits=12,
                                                max_encoded_size=len(f.span))
            # A valid tight transport can fit the original optimal stream while
            # a gratuitous greedy re-encode overflows, despite unchanged pixels.
            tight = HEADER.pack(b'TSET', len(optimal), f.chunk.system_bytes,
                                f.chunk.video_bytes, 0xFEEDBEEF, len(optimal), 0, 0) + optimal
            filled, _ = fill_stream(optimal, f.decoded, f.chunk.stored_size, slack=16)
            expanded = f.span[:32] + filled + bytes(f.chunk.stored_size-len(filled))
            for original in (tight, expanded):
                with self.subTest(stored=len(original)-32):
                    chunk = parse_chunks(original)[0]
                    decoded, transport = decode_chunk(original, chunk)
                    self.assertEqual(decoded, f.decoded)
                    actual, receipt = writer._rebuild_fixed_span(original, decoded, independent=True)
                    self.assertEqual(actual, original)
                    self.assertEqual(receipt.recompressed_bytes, transport.consumed_bytes)
                    self.assertEqual(receipt.rebuilt_overlap_scratch_bytes, chunk.overlap_scratch_bytes)
                    self.assertFalse(receipt.overlap_scratch_changed)
                    self.assertTrue(receipt.compressed_stream_matches_template)
                    self.assertTrue(receipt.complete_span_matches_template)
                    self.assertEqual(receipt.exact_minimum_overlap_scratch_bytes,
                        minimum_vc_lz_overlap_scratch(original[32:32+transport.consumed_bytes],
                                                     chunk.stored_size, len(decoded)))


    def test_palette_only_sock_and_shoe_ignore_retail_chain_hint(self):
        # A donor with different shared indices must never override an explicit
        # palette-only choice. The origin lookup alone is substituted; the
        # production compiler still projects, encodes and checks every byte.
        for family in (4, 8):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                f = Fixture(Path(folder).resolve(), family=family,
                            names=('socks00', 'socks00_mud', 'untouched') if family == 4 else None)
                rgba = bytes((25, 50, 75, 255)) * (f.width * f.height)
                asset_id, path = f.png(independent=False, rgba=rgba)
                expected = f.build([(asset_id, path)])[0]
                _, _, levels = writer._read_png(path, f.rows[0])
                textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
                chain = b''.join(swizzle_2d(bytes(level.width * level.height),
                                level.width, level.height, 1) for level in levels)
                palette = writer.palette_tools.palette_bytes([(25, 50, 75, 255)])
                path.write_bytes(with_retail_source(path.read_bytes(), asset_id, rgba))
                with patch.object(writer, '_retail_artwork', return_value=(textures[0], chain, palette, levels)) as donor:
                    actual, _, receipt, *_ = f.build([(asset_id, path)])
                self.assertEqual(actual, expected, 'palette-only must keep the existing shared index chain')
                self.assertEqual(receipt['allocation']['added_video_bytes'], 0)
                self.assertEqual(receipt['edits'][0]['mip_filter'], 'retail_index_projection')
                donor.assert_not_called()


class CacheKeyTests(unittest.TestCase):
    def test_compile_cache_discards_structurally_corrupt_envelopes(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = CompileCache(Path(folder))
            key = 'a' * 64
            for envelope in ([], 0, {}, {'payload': 123}, {'payload': []}, {'payload': {}}):
                with self.subTest(envelope=envelope):
                    (cache.root / (key + '.json')).write_text(json.dumps(envelope))
                    self.assertIsNone(cache.get(key))
            self.assertEqual(cache.misses, 6)


    def test_every_cached_selector_option_and_input_changes_the_production_key(self):
        tool = backend()
        class StopLookup(Exception):
            pass
        class ObservedCache(CompileCache):
            def get(cache, key):
                observed.append((key, super().get(key)))
                raise StopLookup
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            png = root / 'art.png'
            png.write_bytes(encode_rgba_png(8, 8, bytes((30, 60, 90, 255)) * 64))
            (root / 'other.png').write_bytes(png.read_bytes())
            (root / 'recipe.json').write_bytes(b'{"positions":[0,1,2]}')
            (root / 'other.json').write_bytes(b'{"positions":[0,1,3]}')
            pin = SimpleNamespace(path=root / '0', sha256='index')
            report = SimpleNamespace(payload=b'{}', sha256='report')
            observed = []
            def lookup(edit, *, index=pin, inventory=pin, reports=None):
                project = tool.ProjectFile(root / 'project.json', b'{}', {'edits': [edit]}, (0, 0))
                with patch.object(tool, 'CompileCache', ObservedCache), self.assertRaises(StopLookup):
                    tool.prepare_project(project, index, inventory, reports or {'test': report},
                                         root, -1, {}, parallelism=1)
                return observed[-1]
            cache = CompileCache(root / '.nfl2k5-compile-cache')
            # All fields admitted by the cached kinds, including every selector
            # axis. Stop only after the real persistent cache lookup: no catalog
            # or encoder is mocked into claiming these tiny PNGs are retail art.
            cases = []
            for kind in ('torso', 'sleeve', 'pants'):
                cases.append((dict(kind=kind, asset_code='18', side='H', variant=0,
                                   clean_png='art.png', mud_png=None, mud_mode='darken_60'),
                              dict(asset_code='19', side='A', variant=1, clean_png='other.png',
                                   mud_png='other.png', mud_mode='supplied')))
            cases += [
                (dict(kind='live_helmet', asset_code='18', side='H', variant=0, family='helmet00', png='art.png'),
                 dict(asset_code='19', side='A', variant=1, family='helmet00_mud', png='other.png')),
                (dict(kind='live_number_nameplate', asset_code='18', side='H', variant=0, family='jersey', digit=0, png='art.png'),
                 dict(asset_code='19', side='A', variant=1, family='pants', digit=1, png='other.png')),
                (dict(kind='team_select', asset_code='18', side='home', style=0, family='unif', resolution=256, png='art.png'),
                 dict(asset_code='19', side='away', style=1, family='helmet', resolution=128, png='other.png')),
                (dict(kind='live_face', face_id=0, family='p001', png='art.png'),
                 dict(face_id=1, family='p002', png='other.png')),
                (dict(kind='create_team_field_art', logo_code='01', weather='clear', texture='center_logo', png='art.png'),
                 dict(logo_code='02', weather='snow', texture='endzone', png='other.png')),
                (dict(kind='player_portrait', portrait_id=1, png='art.png'), dict(portrait_id=2, png='other.png')),
                (dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id='tset:0:8:0:shoes01', png='art.png'),
                 dict(asset_id='tset:0:8:1:shoes04', png='other.png')),
            ]
            for kind, field, first, second in (
                (tool.P8_TEXTURE_KIND, 'asset_id', 'p8:first', 'p8:second'),
                (tool.SCOREBUG_TEXTURE_KIND, 'target', 'first', 'second'),
                (tool.CRIB_TEAM_PHOTO_KIND, 'selector', 'first', 'second'),
                (tool.CRIB_STANDALONE_TEXTURE_KIND, 'selector', 'first', 'second'),
                (tool.STADIUM_TEXTURE_KIND, 'target', 'scene.texture0001', 'scene.texture0002'),
                (tool.CRIB_SCENE_TEXTURE_KIND, 'selector', *list(tool.crib_scene_adapter.TARGETS)[:2]),
            ):
                cases.append((dict(kind=kind, png='art.png', **{field:first}), {field:second, 'png':'other.png'}))
            for kind in (tool.STADIUM_GEOMETRY_KIND, tool.CRIB_SCENE_GEOMETRY_KIND):
                cases.append((dict(kind=kind, target='scene.c0001.mesh', recipe='recipe.json'),
                              dict(target='scene.c0002.mesh', recipe='other.json')))
            for base, options in cases:
                key, value = lookup(base)
                self.assertIsNone(value)
                cache.put(key, {'cached': True})
                self.assertEqual(lookup(base), (key, {'cached': True}))
                self.assertEqual(set(options), set(base) - {'kind'})
                for name, changed in options.items():
                    with self.subTest(kind=base['kind'], option=name):
                        new_key, value = lookup(dict(base, **{name: changed}))
                        self.assertNotEqual(new_key, key)
                        self.assertIsNone(value)
            base = dict(kind='p8_texture', asset_id='pixels', png='art.png')
            original = png.read_bytes()
            key, _ = lookup(base); cache.put(key, {'cached': True})
            for name, width, height, color in (
                    ('red', 8, 8, (31,60,90,255)), ('green', 8, 8, (30,61,90,255)),
                    ('blue', 8, 8, (30,60,91,255)), ('alpha', 8, 8, (30,60,90,254)),
                    ('dimensions', 4, 16, (30,60,90,255))):
                with self.subTest(input=name):
                    png.write_bytes(encode_rgba_png(width,height,bytes(color)*(width*height)))
                    changed, value = lookup(base)
                    self.assertNotEqual(changed,key); self.assertIsNone(value)
            png.write_bytes(original)
            for name, kwargs in (('index', {'index':SimpleNamespace(path=pin.path,sha256='changed')}),
                                 ('inventory', {'inventory':SimpleNamespace(path=pin.path,sha256='changed')}),
                                 ('report', {'reports':{'test':SimpleNamespace(payload=b'[]',sha256='changed')}})):
                with self.subTest(input=name):
                    changed, value = lookup(base, **kwargs)
                    self.assertNotEqual(changed,key); self.assertIsNone(value)
            recipe_edit = dict(kind=tool.STADIUM_GEOMETRY_KIND, target='scene', recipe='recipe.json')
            key, _ = lookup(recipe_edit); cache.put(key, {'cached': True})
            (root/'recipe.json').write_bytes(b'{"positions":[0,1,4]}')
            changed,value = lookup(recipe_edit)
            self.assertNotEqual(changed,key); self.assertIsNone(value)
            compiler = root / 'compiler'
            for relative in ('tools/codec.py', 'mod_editor/core/writer.py',
                             'tools/nfl2k5_equipment_optimal', 'tools/nfl2k5_equipment_optimal.c'):
                path = compiler / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original')
            with patch.object(tool, 'ROOT', compiler):
                key, _ = lookup(base); cache.put(key, {'cached': True})
                for relative in ('tools/codec.py', 'mod_editor/core/writer.py',
                                 'tools/nfl2k5_equipment_optimal', 'tools/nfl2k5_equipment_optimal.c'):
                    with self.subTest(compiler=relative):
                        path = compiler / relative
                        path.write_bytes(b'changed')
                        changed, value = lookup(base)
                        self.assertNotEqual(changed, key); self.assertIsNone(value)
                        path.write_bytes(b'original')

    def test_equipment_cache_misses_for_mode_scale_pixels_target_and_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Fixture(Path(folder).resolve())
            cache = writer.EquipmentCompileCache()
            def compile(reference=0, independent=True, scale=1, rgba=None, origin=None):
                target,path = f.png(reference,independent=independent,scale=scale,rgba=rgba)
                if origin is not None:
                    payload,pixels,_ = writer._read_png(path,f.rows[reference])
                    path.write_bytes(with_retail_source(payload,origin,pixels))
                with f.context():
                    return writer.build_unified_uniform_equipment_imports(
                        f.root/'0', [(target,path)],compile_cache=cache,
                        pack_hashes={'pack':digest(f.span)})
            compile(); self.assertEqual((cache.hits,cache.misses),(0,1))
            compile(); self.assertEqual((cache.hits,cache.misses),(1,1))
            for options in ({'independent':False},{'scale':2},{'scale':4},
                            {'reference':1},{'rgba':bytes((1,2,3,255))*1024}):
                before=cache.misses
                compile(**options)
                self.assertEqual(cache.misses,before+1,options)
            textures,_=writer._validate_layout(f.decoded,f.chunk,f.rows)
            rgba=writer.decode_equipment_levels(f.decoded,f.chunk,textures[0])[0]
            compile(rgba=rgba)
            before=cache.misses
            compile(rgba=rgba,origin=f.rows[0].asset_id)
            self.assertEqual(cache.misses,before+1)


class WindowsFallbackTests(unittest.TestCase):
    def test_windows_platform_uses_the_byte_identical_python_path(self):
        from mod_editor.core import nfl2k5_equipment_lz as lz
        corpus = [b'x', bytes(4096), b'aabaaaaabaaaaaababbaaba' * 80, bytes(range(256)) * 64]
        for bits in range(10, 14):
            for source in corpus:
                options = dict(stream_tag=0xFFFFFFFF, offset_bits=bits, max_encoded_size=65536)
                expected = lz.compress_equipment_optimal(source, **options)
                with patch.object(lz, 'sys', SimpleNamespace(platform='win32')), \
                     patch.object(lz.subprocess, 'run', side_effect=AssertionError('Windows invoked Linux helper')):
                    self.assertIsNone(lz._optimal_helper())
                    actual = lz.compress_equipment_optimal(source, **options)
                self.assertEqual(actual, expected)


class WrittenSpanTests(unittest.TestCase):
    def test_receipt_verification_rejects_a_corrupt_written_span_without_recompiling(self):
        import b661_build_fixture as fixture
        tool=backend()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            equipment,_=fixture.create(root)
            fixture.configure(tool,root)
            asset,png=equipment.png(independent=False,rgba=bytes((20,150,80,255))*1024)
            project=root/'project.json'
            project.write_bytes(tool.canonical_json(dict(schema=tool.SCHEMA,purpose='A1 span proof',
                edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND,asset_id=asset,png=str(png))])))
            output,manifest,artifacts=root/'out.iso',root/'manifest.json',root/'artifacts'
            with redirect_stdout(io.StringIO()):
                tool.build(project,root/'source.iso',output,manifest,artifacts,root/'0',root/'inventory.json')
            receipt_hash=tool.file_digest(manifest)
            data=json.loads(manifest.read_bytes())
            offset=data['edits'][0]['target']['absolute_span_offset']+32
            with output.open('r+b') as stream:
                stream.seek(offset); value=stream.read(1); stream.seek(offset); stream.write(bytes([value[0]^1]))
            with self.assertRaisesRegex(tool.ProjectError,'changed since'):
                tool.verify_written(project,root/'source.iso',output,manifest,artifacts,receipt_hash)
            # Bypass only the stat guard to prove that independent byte readback
            # also refuses the corruption, even on a coarse timestamp filesystem.
            output_inode=output.stat().st_ino
            def snapshot(fd):
                return data['written_receipt']['output_stat' if os.fstat(fd).st_ino==output_inode else 'source_stat']
            with patch.object(tool,'file_snapshot',side_effect=snapshot), \
                 patch.object(tool,'prepare_project',side_effect=AssertionError('recompiled')), \
                 patch.object(tool,'verify_union',side_effect=AssertionError('full scan')), \
                 self.assertRaisesRegex(tool.ProjectError,'written span hash changed'):
                tool.verify_written(project,root/'source.iso',output,manifest,artifacts,receipt_hash)


if __name__ == '__main__':
    unittest.main()

