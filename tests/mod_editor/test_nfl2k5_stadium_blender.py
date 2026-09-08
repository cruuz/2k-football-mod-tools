"""Blender glue tests with injected bpy; no display or Blender dependency."""
from __future__ import annotations
from array import array
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "tools"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
from tools.blender import nfl2k5_stadium as bridge
from mod_editor.core.nfl2k5_stadium_studio import stadium_gltf_texture_slots
from nfl_txtr import encode_rgba_png

ID = "nfl2k5.stadium.o0042.c0003.scene0077.texture0000"


class Pixels:
    def __init__(self, values):
        self.values = array("f", values)
    def foreach_get(self, output):
        output[:] = self.values
    def foreach_set(self, values):
        self.values = array("f", values)


class Image(dict):
    def __init__(self, rgba=(11, 22, 33, 255), size=(1, 1)):
        super().__init__()
        self.size, self.source, self.is_float = size, "FILE", False
        self.colorspace_settings = NS(name="sRGB")
        self.alpha_mode = "STRAIGHT"
        self.pixels = Pixels([n / 255 for n in rgba] * (size[0] * size[1]))
        self.filepath_raw, self.file_format = "original.png", "PNG"
        self.updates = 0
    def update(self):
        self.updates += 1
    def save(self):
        Path(self.filepath_raw).write_bytes(encode_rgba_png(*self.size,
            bytes(round(n * 255) for n in self.pixels.values)))


class Material(dict):
    def __init__(self, image, identity=ID):
        super().__init__({bridge.ID_KEY: identity, bridge.SIZE_KEY: list(image.size)})
        self.name = "wall"
        texture = NS(type="TEX_IMAGE", image=image)
        self.node_tree = NS(nodes=[NS(type="BSDF_PRINCIPLED",
            inputs={"Base Color": NS(links=[NS(from_node=texture)])})])


class Images:
    def __init__(self):
        self.live = []
    def new(self, name, *, width, height, alpha, float_buffer):
        image = Image(size=(width, height))
        self.live.append(image)
        return image
    def remove(self, image):
        self.live.remove(image)


class BlenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.image = Image()
        self.material = Material(self.image)
        self.bpy = NS(data=NS(images=Images(), materials=[self.material]))

    def test_live_paint_exports_without_mutating_original_or_geometry(self):
        self.image.pixels.values = array('f', [1, 0, 0.5, 1])
        before = dict(vars(self.image))
        path = self.root / 'textures.gltf'
        self.assertEqual(bridge.export_textures(path, [self.material], self.bpy), 1)
        self.assertEqual(vars(self.image), before)
        self.assertEqual(self.bpy.data.images.live, [])
        slots = stadium_gltf_texture_slots(path)
        self.assertEqual(slots[0].texture_id, ID)
        self.assertEqual(slots[0].payload, encode_rgba_png(1, 1, bytes((255, 0, 128, 255))))
        document = json.loads(path.read_text())
        for key in ('nodes', 'meshes', 'buffers', 'accessors'):
            self.assertNotIn(key, document)

    def test_duplicate_materials_deduplicate_one_image(self):
        path = self.root / 'textures.gltf'
        self.assertEqual(bridge.export_textures(path, [self.material, Material(self.image)], self.bpy), 1)

    def test_conflicting_linked_images_refuse_without_output(self):
        path = self.root / 'textures.gltf'
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'disagree'):
            bridge.export_textures(path, [self.material, Material(Image((9, 8, 7, 255)))], self.bpy)
        self.assertFalse(path.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.bpy.data.images.live, [])

    def test_changed_dimensions_and_mixed_scenes_refuse(self):
        self.material[bridge.SIZE_KEY] = [2, 2]
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'dimensions'):
            bridge.export_textures(self.root/'bad.gltf', [self.material], self.bpy)
        self.material[bridge.SIZE_KEY] = [1, 1]
        foreign = Material(Image(), ID.replace('scene0077', 'scene0078'))
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'one Stadium scene'):
            bridge.export_textures(self.root/'bad.gltf', [self.material, foreign], self.bpy)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_save_failure_cleans_temporary_image_and_files(self):
        with patch.object(Image, 'save', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                bridge.export_textures(self.root/'bad.gltf', [self.material], self.bpy)
        self.assertEqual(self.bpy.data.images.live, [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_does_not_overwrite_an_existing_export(self):
        path = self.root / 'textures.gltf'
        path.write_bytes(b'keep')
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'already exists'):
            bridge.export_textures(path, [self.material], self.bpy)
        self.assertEqual(path.read_bytes(), b'keep')

    def test_import_uses_stock_gltf_import_and_binds_only_new_materials(self):
        document = {'images': [{'extras': {bridge.ID_KEY: ID, 'width': 1, 'height': 1}}],
                    'extras': {'nfl2k5_texcoord_contract': {'v_flipped': False}}}
        path = self.root/'original.gltf'
        path.write_text(json.dumps(document))
        added = Material(Image())
        calls = []
        def load(**kwargs):
            calls.append(kwargs)
            self.bpy.data.materials.append(added)
            return {'FINISHED'}
        self.bpy.ops = NS(import_scene=NS(gltf=load))
        self.assertEqual(bridge.import_stadium(path, self.bpy), 1)
        self.assertEqual(calls, [{'filepath': str(path), 'import_pack_images': True}])
        self.assertEqual(bridge._base_image(added)[bridge.ID_KEY], ID)
        self.assertNotIn(bridge.ID_KEY, self.image)

    def test_missing_ids_and_procedural_materials_refuse(self):
        self.material[bridge.ID_KEY] = 'wall'
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'ID'):
            bridge.export_textures(self.root/'bad.gltf', [self.material], self.bpy)
        self.material[bridge.ID_KEY] = ID
        self.material.node_tree.nodes[0].inputs['Base Color'].links = []
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'directly'):
            bridge.export_textures(self.root/'bad.gltf', [self.material], self.bpy)

    def test_menu_registration_and_unregistration_are_repeatable(self):
        registered, import_menu, export_menu = [], [], []
        self.bpy.types = NS(Operator=type('Operator', (), {}),
                            TOPBAR_MT_file_import=import_menu,
                            TOPBAR_MT_file_export=export_menu)
        self.bpy.props = NS(StringProperty=lambda **kwargs: kwargs)
        self.bpy.utils = NS(register_class=registered.append, unregister_class=registered.remove)
        bridge.register(self.bpy)
        self.assertEqual(len(registered), 2)
        self.assertEqual(len(import_menu), 1)
        bridge.register(self.bpy)
        self.assertEqual(len(registered), 2)
        bridge.unregister(self.bpy)
        self.assertEqual((registered, import_menu, export_menu), ([], [], []))

    def test_two_native_texture_ids_cannot_share_one_blender_image(self):
        second = ID[:-4] + '0001'
        document = {'images': [{'extras': {bridge.ID_KEY: identity, 'width': 1, 'height': 1}}
                               for identity in (ID, second)]}
        other = Material(self.image, second)
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'separate image copies'):
            bridge.bind_materials([self.material, other], document)
        self.assertNotIn(bridge.ID_KEY, self.image)
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'separate image copies'):
            bridge.export_textures(self.root/'bad.gltf', [self.material, other], self.bpy)
        self.image[bridge.ID_KEY] = second
        with self.assertRaisesRegex(bridge.StadiumBlenderError, 'different Stadium texture IDs'):
            bridge.export_textures(self.root/'bad.gltf', [self.material], self.bpy)
        self.assertFalse((self.root/'bad.gltf').exists())

    def test_private_cli_publishes_only_after_successful_compile(self):
        from tools import nfl_stadium_texture_bundle as cli
        path = self.root/'textures.gltf'
        bridge.export_textures(path, [self.material], self.bpy)
        destination = self.root/'compiled'
        with patch.object(cli, 'build_unified_stadium_texture_imports', side_effect=ValueError('fit failed')):
            with self.assertRaisesRegex(ValueError, 'fit failed'):
                cli.compile_bundle(path, self.root/'0', self.root/'inventory.json', destination)
        self.assertFalse(destination.exists())
        result = [(b'synthetic SCNE', [('preview.png', b'preview')], {'input_pngs': []}, ID, {})]
        with patch.object(cli, 'build_unified_stadium_texture_imports', return_value=result):
            self.assertEqual(cli.compile_bundle(path, self.root/'0', self.root/'inventory.json', destination), destination)
        self.assertEqual((destination/'scene.scne').read_bytes(), b'synthetic SCNE')
        self.assertTrue(json.loads((destination/'receipt.json').read_text())['private_output_contains_retail_bytes'])


if __name__ == '__main__':
    unittest.main()
