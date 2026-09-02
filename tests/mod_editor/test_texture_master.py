"""High-resolution authoring stays separate from native game texture limits."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image

from mod_editor.core.errors import ValidationError
from mod_editor.core.image_fit import fit_image
from mod_editor.core.texture_master import (
    AuthoringTransform,
    RPCS3_TEXTURE_REPLACEMENT_EXPORT_SUPPORTED,
    TEXTURE_MASTER_SCHEMA,
    fit_transform,
    load_texture_master_bundle,
    render_master,
    require_rpcs3_texture_replacement_export,
    save_texture_master_bundle,
    snapshot_texture_master_source,
)


class TextureMasterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _detailed_source(self) -> tuple[Path, bytes]:
        image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        pixels = image.load()
        for y_value in range(16):
            for x_value in range(16):
                pixels[x_value, y_value] = (
                    255 if (x_value + y_value) % 2 else 0,
                    x_value * 17,
                    y_value * 17,
                    255,
                )
        path = self.root / "full-resolution-logo.png"
        image.save(path, compress_level=1)
        return path, path.read_bytes()

    def test_bundle_preserves_exact_master_and_compiles_native_size(self) -> None:
        source, source_bytes = self._detailed_source()
        output = save_texture_master_bundle(
            source_image=source,
            destination=self.root / "helmet.2ktexmaster",
            asset_id="apf.team_logo.crest_00",
            editor_target="apf2k8_xbox360",
            native_width=4,
            native_height=4,
        )
        loaded = load_texture_master_bundle(output)
        self.assertEqual(loaded.source_bytes, source_bytes)
        self.assertEqual(loaded.manifest["schema"], TEXTURE_MASTER_SCHEMA)
        self.assertEqual(
            loaded.manifest["editor_transform"]["operation"],
            "affine-master-placement",
        )
        self.assertEqual(
            loaded.manifest["native"]["generation"], "rendered-from-master"
        )
        with Image.open(io.BytesIO(loaded.native_png)) as native:
            self.assertEqual(native.size, (4, 4))
            self.assertEqual(native.mode, "RGBA")
        with Image.open(io.BytesIO(loaded.high_resolution_png)) as preview:
            self.assertEqual(preview.size, (16, 16))
            # The 4x output is sampled from the full-res master. At this exact
            # transform it retains the source pixels; it is not a 4x enlargement
            # of the already-downsampled 4x4 game PNG.
            self.assertEqual(preview.tobytes(), Image.open(source).tobytes())

    def test_game_specific_compiled_native_can_differ_from_painted_master(self) -> None:
        source, _payload = self._detailed_source()
        compiled = self.root / "semantic-region-mask.png"
        Image.new("RGBA", (4, 4), (255, 0, 0, 136)).save(compiled)
        output = save_texture_master_bundle(
            source_image=source,
            destination=self.root / "apf-mask.2ktexmaster",
            asset_id="apf.team_logo.crest_00",
            editor_target="apf2k8_xbox360-full-shell-region-mask",
            native_width=4,
            native_height=4,
            compiled_native_png=compiled,
        )
        loaded = load_texture_master_bundle(output)
        self.assertEqual(
            loaded.manifest["native"]["generation"], "supplied-game-compiled"
        )
        with Image.open(io.BytesIO(loaded.native_png)) as native:
            self.assertEqual(native.getpixel((0, 0)), (255, 0, 0, 136))
        self.assertFalse(
            loaded.manifest["capabilities"][
                "high_resolution_preview_is_game_replacement"
            ]
        )

    def test_manual_transform_round_trips(self) -> None:
        source, _payload = self._detailed_source()
        transform = AuthoringTransform(
            center_x=5.25,
            center_y=4.75,
            width=6.0,
            height=3.0,
            rotation_degrees=17.5,
            resample="bicubic",
        )
        output = save_texture_master_bundle(
            source_image=source,
            destination=self.root / "placed.2ktexmaster",
            asset_id="nfl2k5.uniform.helmet.logo",
            editor_target="nfl2k5_xbox",
            native_width=8,
            native_height=8,
            transform=transform,
            high_resolution_scale=2,
        )
        loaded = load_texture_master_bundle(output)
        self.assertEqual(loaded.manifest["transform"], transform.document())
        self.assertEqual(loaded.high_resolution_scale, 2)

    def test_contain_and_cover_transform_have_expected_geometry(self) -> None:
        contain = fit_transform(16, 8, 10, 10, mode="contain")
        cover = fit_transform(16, 8, 10, 10, mode="cover")
        self.assertEqual((contain.width, contain.height), (10.0, 5.0))
        self.assertEqual((cover.width, cover.height), (20.0, 10.0))

    def test_fit_transform_preserves_the_image_fitter_odd_pixel_alignment(self) -> None:
        contain = fit_transform(5, 3, 8, 8, mode="contain")
        self.assertEqual((contain.width, contain.height), (8.0, 5.0))
        self.assertEqual((contain.center_x, contain.center_y), (4.0, 3.5))
        cover = fit_transform(5, 3, 8, 8, mode="cover")
        self.assertEqual((cover.width, cover.height), (13.0, 8.0))
        self.assertEqual((cover.center_x, cover.center_y), (4.5, 4.0))

    def test_lanczos_transform_exactly_matches_native_fit_pixels(self) -> None:
        source = self.root / "odd-source.png"
        image = Image.new("RGBA", (5, 3), (0, 0, 0, 0))
        for y_value in range(3):
            for x_value in range(5):
                image.putpixel(
                    (x_value, y_value),
                    (x_value * 40, y_value * 70, 190, 80 + x_value * 20),
                )
        image.save(source)
        opened = Image.open(source).convert("RGBA")
        for mode in ("contain", "cover"):
            expected = fit_image(source, 8, 8, mode=mode)
            transform = fit_transform(
                5, 3, 8, 8, mode=mode, resample="lanczos"
            )
            rendered = render_master(opened, 8, 8, transform)
            self.assertEqual(rendered.tobytes(), expected.rgba)

    def test_native_canvas_edits_overlay_the_direct_master_preview(self) -> None:
        source = self.root / "large-source.png"
        image = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        image.putpixel((0, 0), (200, 100, 50, 255))
        image.save(source)
        baseline = self.root / "baseline.png"
        Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(baseline)
        final = self.root / "final.png"
        edited = Image.open(baseline).copy()
        edited.putpixel((2, 1), (255, 0, 180, 128))
        edited.save(final)

        output = save_texture_master_bundle(
            source_image=source,
            destination=self.root / "edited.2ktexmaster",
            asset_id="nfl2k5.portrait.0000",
            editor_target="nfl2k5_xbox",
            native_width=4,
            native_height=4,
            compiled_native_png=final,
            compiled_native_baseline_png=baseline,
            high_resolution_scale=4,
            editor_transform={
                "operation": "native-canvas-raster-edit-after-import"
            },
        )
        loaded = load_texture_master_bundle(output)
        self.assertEqual(loaded.native_baseline_png, baseline.read_bytes())
        self.assertEqual(
            loaded.manifest["native_raster_edit"]["changed_pixel_count"], 1
        )
        self.assertEqual(
            loaded.manifest["high_resolution_preview"]["composition"],
            "direct-master-plus-native-raster-edits",
        )
        with Image.open(io.BytesIO(loaded.high_resolution_png)) as preview:
            # Native pixel (2,1) occupies this exact 4x block; neighbouring
            # source detail remains the direct full-resolution render.
            self.assertEqual(preview.getpixel((8, 4)), (255, 0, 180, 128))
            self.assertEqual(preview.getpixel((11, 7)), (255, 0, 180, 128))

    def test_existing_bundle_is_never_overwritten(self) -> None:
        source, _payload = self._detailed_source()
        output = self.root / "existing.2ktexmaster"
        output.write_bytes(b"keep me")
        with self.assertRaisesRegex(ValidationError, "already exists"):
            save_texture_master_bundle(
                source_image=source,
                destination=output,
                asset_id="asset",
                editor_target="nfl2k5_xbox",
                native_width=4,
                native_height=4,
            )
        self.assertEqual(output.read_bytes(), b"keep me")

    def test_private_snapshot_preserves_import_bytes_and_hash(self) -> None:
        source, source_bytes = self._detailed_source()
        snapshot, digest = snapshot_texture_master_source(
            source, self.root / "private" / "logo.source"
        )
        self.assertEqual(snapshot.read_bytes(), source_bytes)
        self.assertEqual(len(digest), 64)
        source.write_bytes(b"changed after import")
        with self.assertRaisesRegex(ValidationError, "changed outside Mod Studio"):
            save_texture_master_bundle(
                source_image=snapshot,
                expected_source_sha256="0" * 64,
                destination=self.root / "changed.2ktexmaster",
                asset_id="asset",
                editor_target="nfl2k5_xbox",
                native_width=4,
                native_height=4,
            )

    def test_capability_claim_tampering_is_rejected(self) -> None:
        source, _payload = self._detailed_source()
        valid = save_texture_master_bundle(
            source_image=source,
            destination=self.root / "valid.2ktexmaster",
            asset_id="asset",
            editor_target="nfl2k5_xbox",
            native_width=4,
            native_height=4,
        )
        members: dict[str, bytes] = {}
        with zipfile.ZipFile(valid, "r") as archive:
            for name in archive.namelist():
                members[name] = archive.read(name)
        manifest = json.loads(members["manifest.json"])
        manifest["capabilities"]["rpcs3_texture_pack_export"] = True
        members["manifest.json"] = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        tampered = self.root / "tampered.2ktexmaster"
        with zipfile.ZipFile(tampered, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        with self.assertRaisesRegex(ValidationError, "capability truth"):
            load_texture_master_bundle(tampered)

    def test_rpcs3_pack_export_refuses_instead_of_inventing_mapping(self) -> None:
        self.assertFalse(RPCS3_TEXTURE_REPLACEMENT_EXPORT_SUPPORTED)
        with self.assertRaisesRegex(
            ValidationError, "no source-proved APF PS3 texture-ID/name mapping"
        ):
            require_rpcs3_texture_replacement_export()


if __name__ == "__main__":
    unittest.main()
