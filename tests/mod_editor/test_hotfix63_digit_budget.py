"""beta-63.1 hotfix: a jersey-digit texture budget must never refuse the disc.

Coach Edwards (#2k5-bugs 2026-09-09 09:51 and 10:16, beta 63 on Windows)
exported a Team Kit, edited it, imported it back and Build refused the whole
disc with

    live_number_nameplate (asset_code=02, side=H, variant=0, family=arm):
    Digit artwork cannot fit its 896-byte texture slot without dropping below
    the 16-colour quality budget.

Two defects, both covered here:

1. **The kit round trip staged digit layers he did not really change.**  A
   colour-managed editor re-save leaves every pixel within a channel step or
   two of the export, which the exact-RGBA comparison called "edited".  The
   retail ``02H0`` digit 1 re-encodes into its own 896-byte slot with six
   bytes to spare, so that re-encode noise alone is what could not fit.
2. **A digit that cannot fit blocked the disc.**  The compile path now keeps
   the RETAIL digit for that one slot, records a ``kept_retail`` row that names
   the slot in the build receipt, and lets the build succeed.  A corrupt
   payload still fails closed.

The retail-backed cases need the private extracted pack 0 and the pinned
compatibility reports; they skip precisely when those are absent.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests/fixtures"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from PIL import Image, PngImagePlugin  # noqa: E402

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_uniform_catalog import (  # noqa: E402
    ASSETS_PER_SET,
    load_nfl2k5_uniform_catalog,
)
from mod_editor.studio.session import StudioSession  # noqa: E402
from mod_editor.studio.uniform_bundle import (  # noqa: E402
    TEAM_KIT_MANIFEST,
    TeamKitBundleService,
)
from number_sheet_quality_cases import digit_image  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402
from nfl_txtr import encode_rgba_png  # noqa: E402


REPORTED_SET = "02H0"
REPORTED_SLOT_BYTES = 896


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _retail_index() -> Path | None:
    candidates = [
        os.environ.get("NFL2K5_TEST_INDEX"),
        str(ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
        "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def _retail_inventory() -> Path | None:
    candidates = [
        os.environ.get("NFL2K5_TEST_INVENTORY"),
        str(ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


# ---------------------------------------------------------------------------
# Defect 1: the Team Kit round trip
# ---------------------------------------------------------------------------


class _GlyphAssetIO:
    """Private-source stand-in whose digit originals look like real digits.

    Flat colours would make every "near-identical" question trivial.  Digit
    originals are antialiased glyphs with transparent surroundings and hidden
    RGB under alpha 0, exactly what the retail decoder exports.
    """

    def __init__(self, cache: object) -> None:
        self.cache = cache
        self.originals = Path(getattr(cache, "root")) / "originals"
        self.originals.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def rgba_for(asset: object) -> bytes:
        width = int(getattr(asset, "width"))
        height = int(getattr(asset, "height"))
        digit = getattr(asset, "digit", None)
        if getattr(asset, "kind", "") == "live_number_nameplate" and digit is not None:
            image = digit_image(int(digit), soft=True, size=64)
            if (width, height) != (64, 64):
                image = image.resize((width, height), Image.Resampling.LANCZOS)
            data = bytearray(image.tobytes())
            for offset in range(0, len(data), 4):
                if data[offset + 3] == 0:
                    # Retail palettes carry colour under fully transparent
                    # texels; a decoder export reproduces it.
                    data[offset:offset + 3] = b"\x65\x52\x00"
            return bytes(data)
        seed = hashlib.sha256(str(getattr(asset, "asset_id")).encode()).digest()
        return bytes((seed[0], seed[1], seed[2], 255)) * (width * height)

    def ensure_original(self, asset: object) -> Path:
        name = hashlib.sha256(str(getattr(asset, "asset_id")).encode()).hexdigest()
        path = self.originals / f"{name}.png"
        if not path.exists():
            path.write_bytes(encode_rgba_png(
                int(getattr(asset, "width")), int(getattr(asset, "height")),
                self.rgba_for(asset),
            ))
        return path

    @staticmethod
    def validate_replacement(asset: object, path: Path) -> tuple[bytes, bytes]:
        supplied = path.resolve(strict=True)
        payload = supplied.read_bytes()
        try:
            width, height, rgba = decode_rgba_png(
                payload,
                (int(getattr(asset, "width")), int(getattr(asset, "height"))),
            )
        except ValueError as exc:
            raise ValidationError(f"bad synthetic Team Kit PNG: {exc}") from exc
        if (width, height) != (int(getattr(asset, "width")), int(getattr(asset, "height"))):
            raise ValidationError("bad synthetic Team Kit dimensions")
        return payload, rgba


def _resave_with_pillow(path: Path) -> None:
    """Different bytes, identical pixels: what a plain re-save does."""

    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        info = PngImagePlugin.PngInfo()
        info.add_text("Software", "a third-party editor")
        rgba.save(path, format="PNG", optimize=True, pnginfo=info)


def _colour_managed_resave(path: Path, seed: int) -> None:
    """Re-encode noise: every visible channel drifts by at most one step.

    A colour-managed export (ICC round trip, 16-bit intermediate, alpha
    dither) leaves the art visually identical while changing the exact RGBA
    of most pixels.  Hidden RGB under alpha 0 is flattened to white the way
    many editors do.
    """

    generator = random.Random(seed)
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        data = bytearray(rgba.tobytes())
    for offset in range(0, len(data), 4):
        if data[offset + 3] == 0:
            data[offset:offset + 3] = b"\xff\xff\xff"
            continue
        for channel in range(4):
            if channel == 3 and data[offset + 3] == 255:
                continue
            step = generator.choice((-1, 0, 1))
            data[offset + channel] = max(0, min(255, data[offset + channel] + step))
    Image.frombytes("RGBA", rgba.size, bytes(data)).save(path, format="PNG")


def _recolour(path: Path) -> None:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        data = bytearray(rgba.tobytes())
    for offset in range(0, len(data), 4):
        if data[offset + 3]:
            data[offset:offset + 3] = b"\x24\x12\x5a"
    Image.frombytes("RGBA", rgba.size, bytes(data)).save(path, format="PNG")


class KitRoundTripDigitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_uniform_catalog()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="hf63-digit-kit-")
        self.root = Path(self.temporary.name)
        source = SimpleNamespace(sha256="a" * 64)
        self.cache = SimpleNamespace(source=source, root=self.root / "private-cache")
        with mock.patch(
            "mod_editor.studio.session.Nfl2k5ProductVisualIO", _GlyphAssetIO
        ):
            self.session = StudioSession(
                self.cache, self.catalog, root=self.root / "sessions", session_id="active",
            )
        self.service = TeamKitBundleService(self.catalog, self.session)
        self.kit = self.root / "kit"
        self.service.export((REPORTED_SET,), self.kit)
        manifest = json.loads((self.kit / TEAM_KIT_MANIFEST).read_text(encoding="utf-8"))
        self.rows = {row["asset_id"]: row for row in manifest["assets"]}
        self.digit_ids = [
            asset.asset_id for asset in self.catalog.assets_for_set(REPORTED_SET)
            if asset.kind == "live_number_nameplate" and asset.digit is not None
        ]
        self.assertEqual(len(self.digit_ids), 30)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _path(self, asset_id: str) -> Path:
        return self.kit / self.rows[asset_id]["path"]

    def _decisions(self, result: object) -> dict[str, str]:
        return {row.asset_id: row.decision for row in getattr(result, "components")}

    def test_reencoded_but_pixel_equal_digits_stage_nothing(self) -> None:
        before = {asset_id: self._path(asset_id).read_bytes() for asset_id in self.digit_ids}
        for asset_id in self.digit_ids:
            _resave_with_pillow(self._path(asset_id))
        self.assertTrue(all(
            self._path(asset_id).read_bytes() != before[asset_id]
            for asset_id in self.digit_ids
        ), "the re-save must change bytes for the case to mean anything")

        result = self.service.import_edited(self.kit, expected_set_selectors=(REPORTED_SET,))

        self.assertEqual(result.changed_count, 0)
        self.assertEqual(result.imported_count, 0)
        self.assertEqual(result.skipped_unchanged_count, ASSETS_PER_SET)
        decisions = self._decisions(result)
        self.assertEqual({decisions[asset_id] for asset_id in self.digit_ids}, {"skipped_unchanged"})
        self.assertEqual(self.session.modified_count, 0)

    def test_colour_managed_resave_noise_is_not_an_edit_of_a_digit(self) -> None:
        """The reported case: every digit 'Modified' after an editor re-save."""

        for number, asset_id in enumerate(self.digit_ids):
            _colour_managed_resave(self._path(asset_id), seed=number)
        rgba_now = {
            asset_id: decode_rgba_png(
                self._path(asset_id).read_bytes(),
                (self.catalog.get_asset(asset_id).width, self.catalog.get_asset(asset_id).height),
            )[2]
            for asset_id in self.digit_ids
        }
        self.assertTrue(all(
            _sha(rgba_now[asset_id]) != self.rows[asset_id]["baseline_rgba_sha256"]
            for asset_id in self.digit_ids
        ), "the noise must change decoded pixels for the case to mean anything")

        result = self.service.import_edited(self.kit, expected_set_selectors=(REPORTED_SET,))

        self.assertEqual(result.changed_count, 0, result.details)
        self.assertEqual(result.imported_count, 0)
        decisions = self._decisions(result)
        self.assertEqual({decisions[asset_id] for asset_id in self.digit_ids}, {"skipped_reencoded"})
        self.assertIn("re-encoded", result.details)
        self.assertIn("Skipped unchanged: 39", result.message)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(sorted(self.session.modified_asset_ids), [])

    def test_a_real_digit_edit_and_noise_elsewhere_are_told_apart(self) -> None:
        edited = self.digit_ids[1]
        _recolour(self._path(edited))
        for number, asset_id in enumerate(self.digit_ids):
            if asset_id != edited:
                _colour_managed_resave(self._path(asset_id), seed=100 + number)

        result = self.service.import_edited(self.kit, expected_set_selectors=(REPORTED_SET,))

        decisions = self._decisions(result)
        self.assertEqual(decisions[edited], "imported")
        self.assertEqual(
            {decisions[asset_id] for asset_id in self.digit_ids if asset_id != edited},
            {"skipped_reencoded"},
        )
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(sorted(self.session.modified_asset_ids), [edited])

    def test_scope_is_digits_only_and_a_large_step_is_still_an_edit(self) -> None:
        """Torso and nameplate keep the exact-pixel rule; ±4 on a digit is an edit."""

        assets = {asset.asset_id: asset for asset in self.catalog.assets_for_set(REPORTED_SET)}
        torso = next(asset_id for asset_id, asset in assets.items() if asset.kind == "torso")
        _colour_managed_resave(self._path(torso), seed=7)
        stepped = self.digit_ids[0]
        path = self._path(stepped)
        with Image.open(path) as image:
            data = bytearray(image.convert("RGBA").tobytes())
        for offset in range(0, len(data), 4):
            if data[offset + 3] == 255:
                data[offset] = max(0, min(255, data[offset] + 4))
        Image.frombytes("RGBA", (assets[stepped].width, assets[stepped].height), bytes(data)).save(path)

        result = self.service.import_edited(self.kit, expected_set_selectors=(REPORTED_SET,))

        decisions = self._decisions(result)
        self.assertEqual(decisions[torso], "imported")
        self.assertEqual(decisions[stepped], "imported")
        self.assertEqual(result.changed_count, 2)


# ---------------------------------------------------------------------------
# Defect 2: the compile path keeps retail for one unfit slot
# ---------------------------------------------------------------------------


def _retail_digit_rgba(index: Path, family: str, digit: int) -> tuple[object, bytes]:
    import nfl_live_numbers_nameplate_png_import as writer
    import nfl_live_numbers_nameplate_targets as targets

    _, _, target = targets.select_target(family, "02", "H", 0, digit)
    archive = writer.parse_archive(index)
    span = writer.read_entry_range(
        archive, archive.entries[target.outer_index], target.chunk_offset, target.span_size
    )
    chunk, decoded, texture = writer.validate_template(span, target)
    return target, writer.decode_levels(decoded, chunk, texture)[0].rgba


def _reencode_noise(rgba: bytes, seed: int) -> bytes:
    """Coach Edwards' re-save, reduced to what matters: ±1 on visible RGBA."""

    generator = random.Random(seed)
    data = bytearray(rgba)
    for offset in range(0, len(data), 4):
        if data[offset + 3]:
            for channel in range(4):
                step = generator.choice((-1, 0, 1))
                data[offset + channel] = max(0, min(255, data[offset + channel] + step))
    return bytes(data)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


class BackendKeepsRetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nfl_live_numbers_nameplate_targets as targets

        cls.index = _retail_index()
        cls.inventory = _retail_inventory()
        missing = [
            str(path) for path in (cls.index, cls.inventory, targets.DEFAULT_REPORT)
            if path is None or not Path(path).is_file()
        ]
        if missing or cls.index is None or cls.inventory is None:
            raise unittest.SkipTest(
                "Private retail digit evidence absent: " + ", ".join(missing or ["index"])
            )
        cls.target, retail = _retail_digit_rgba(cls.index, "arm_digit", 1)
        cls.unfit_rgba = _reencode_noise(retail, seed=2)
        _, jersey_zero = _retail_digit_rgba(cls.index, "jersey_digit", 0)
        recoloured = bytearray(jersey_zero)
        for offset in range(0, len(recoloured), 4):
            if recoloured[offset + 3] == 255 and recoloured[offset:offset + 3] == b"\xff\xff\xff":
                recoloured[offset:offset + 3] = b"\x24\x12\x5a"
        cls.fits_rgba = bytes(recoloured)

    def _project(self, root: Path, edits: list[dict[str, object]]) -> Path:
        path = root / "project.json"
        path.write_bytes(_canonical({
            "schema": "nfl2k5_visual_mod_project/v1",
            "purpose": "beta-63.1 digit budget regression",
            "edits": edits,
        }))
        return path

    def _prepare(self, root: Path, edits: list[dict[str, object]]):
        import nfl2k5_visual_mod_project as backend

        project = backend.read_project(self._project(root, edits))
        reports = backend.pin_reports({"live_number_nameplate"})
        index_pin = backend.ownership.pin_large_file(
            self.index, "canonical extracted pack 0", backend.INDEX_SIZE, backend.INDEX_SHA256)
        inventory_pin = backend.ownership.pin_large_file(
            self.inventory, "canonical chunk inventory",
            backend.INVENTORY_SIZE, backend.INVENTORY_SHA256)
        placeholder = os.open(root / "not-a-source.bin", os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        prepared = None
        try:
            prepared = backend.prepare_project(
                project, index_pin, inventory_pin, reports, root, placeholder, {})
            return backend, prepared
        finally:
            os.close(placeholder)
            os.close(index_pin.descriptor)
            os.close(inventory_pin.descriptor)
            if prepared is not None:
                self.addCleanup(
                    backend.ownership.cleanup_owned, prepared.temp_files, [prepared.temp_root])

    def test_unfit_digit_keeps_retail_and_the_fitting_digit_still_compiles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hf63-backend-") as temporary:
            root = Path(temporary).resolve()
            (root / "arm1.png").write_bytes(encode_rgba_png(64, 64, self.unfit_rgba))
            (root / "jersey0.png").write_bytes(encode_rgba_png(64, 64, self.fits_rgba))
            backend, prepared = self._prepare(root, [
                {"kind": "live_number_nameplate", "asset_code": "02", "side": "H",
                 "variant": 0, "family": "arm", "digit": 1, "png": "arm1.png"},
                {"kind": "live_number_nameplate", "asset_code": "02", "side": "H",
                 "variant": 0, "family": "jersey", "digit": 0, "png": "jersey0.png"},
            ])
            self.assertEqual([edit.selector for edit in prepared.edits], ["02H0:jersey_digit:0"])
            self.assertEqual(len(prepared.kept_retail), 1)
            row = prepared.kept_retail[0]
            self.assertEqual(row["selector"], "02H0:arm_digit:1")
            self.assertEqual(row["outcome"], "kept_retail")
            self.assertEqual(row["stored_size"], REPORTED_SLOT_BYTES)
            self.assertEqual((row["asset_code"], row["side"], row["variant"], row["family"], row["digit"]),
                             ("02", "H", 0, "arm", 1))
            self.assertEqual(row["input_sha256"], _sha((root / "arm1.png").read_bytes()))
            self.assertIn("kept retail", row["message"])
            self.assertIn("896-byte", row["message"])
            self.assertIn("arm digit 1", row["message"])
            self.assertIn("02H0", row["message"])
            self.assertIn("16-colour", row["reason"])
            # The manifest and the independent verify reconstruct the same rows.
            self.assertEqual(json.loads(_canonical(prepared.kept_retail)), prepared.kept_retail)

    def test_a_corrupt_digit_payload_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hf63-backend-") as temporary:
            root = Path(temporary).resolve()
            (root / "arm1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"not a png body" * 8)
            import nfl2k5_visual_mod_project as backend

            with self.assertRaisesRegex(backend.ProjectError, "digit=1"):
                self._prepare(root, [
                    {"kind": "live_number_nameplate", "asset_code": "02", "side": "H",
                     "variant": 0, "family": "arm", "digit": 1, "png": "arm1.png"},
                ])

    def test_a_project_whose_only_edit_kept_retail_still_binds(self) -> None:
        import nfl2k5_visual_mod_project as backend

        with tempfile.TemporaryDirectory(prefix="hf63-backend-") as temporary:
            root = Path(temporary).resolve()
            (root / "arm1.png").write_bytes(encode_rgba_png(64, 64, self.unfit_rgba))
            backend, prepared = self._prepare(root, [
                {"kind": "live_number_nameplate", "asset_code": "02", "side": "H",
                 "variant": 0, "family": "arm", "digit": 1, "png": "arm1.png"},
            ])
            self.assertEqual(prepared.edits, [])
            self.assertEqual([row["selector"] for row in prepared.kept_retail], ["02H0:arm_digit:1"])
            placeholder = os.open(root / "source.bin", os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
            try:
                # No span binds, so no pack is read: an empty XDVDFS table is enough.
                backend.bind_prepared_to_source(prepared, placeholder, {})
            finally:
                os.close(placeholder)

    def test_describe_edit_names_the_digit(self) -> None:
        import nfl2k5_visual_mod_project as backend

        label = backend.describe_edit({
            "kind": "live_number_nameplate", "asset_code": "02", "side": "H",
            "variant": 0, "family": "arm", "digit": 1, "png": "x.png",
        })
        self.assertIn("digit=1", label)


class PreviewKeepsRetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nfl_live_numbers_nameplate_targets as targets

        cls.index = _retail_index()
        if cls.index is None or not Path(targets.DEFAULT_REPORT).is_file():
            raise unittest.SkipTest("Private retail digit evidence absent")
        cls.catalog = load_nfl2k5_uniform_catalog()

    def test_preview_shows_the_retail_digit_for_an_unfit_slot(self) -> None:
        from mod_editor.core.nfl2k5_digit_preview import (
            decode_digit_texture, preview_digit_sheet,
        )
        from mod_editor.core.nfl2k5_digit_sheet import DigitSheetPng
        import nfl_live_numbers_nameplate_png_import as writer

        selected = tuple(
            asset for asset in self.catalog.assets_for_set(REPORTED_SET)
            if asset.family == "arm" and asset.digit is not None
        )
        target, retail = _retail_digit_rgba(self.index, "arm_digit", 1)
        outputs = []
        for asset in selected:
            _, rgba = _retail_digit_rgba(self.index, "arm_digit", asset.digit)
            if asset.digit == 1:
                rgba = _reencode_noise(rgba, seed=2)
            else:
                data = bytearray(rgba)
                for offset in range(0, len(data), 4):
                    if data[offset + 3] == 255 and data[offset:offset + 3] == b"\xff\xff\xff":
                        data[offset:offset + 3] = b"\x24\x12\x5a"
                rgba = bytes(data)
            outputs.append(DigitSheetPng(
                asset.digit, asset.asset_id, asset.width, asset.height,
                encode_rgba_png(asset.width, asset.height, rgba), "horizontal", (64, 64),
            ))
        preview = preview_digit_sheet(self.index, selected, outputs)
        self.assertEqual(len(preview.receipts), 10)
        kept = preview.receipts[1]
        self.assertTrue(kept.get("kept_retail"))
        self.assertEqual(kept["target"]["selector"], "02H0:arm_digit:1")
        self.assertIn("Digit 1: kept retail", preview.details)
        self.assertIn("896-byte", preview.details)
        archive = writer.parse_archive(self.index)
        span = writer.read_entry_range(
            archive, archive.entries[target.outer_index], target.chunk_offset, target.span_size)
        self.assertEqual(kept["replacement"]["span_sha256"], _sha(span))
        self.assertEqual(decode_digit_texture(span).span_sha256, kept["replacement"]["span_sha256"])
        with Image.open(BytesIO(preview.png)) as image:
            self.assertEqual(image.size, (730, 850))
        self.assertFalse(any(r.get("kept_retail") for i, r in enumerate(preview.receipts) if i != 1))


# ---------------------------------------------------------------------------
# The build receipt the product shows
# ---------------------------------------------------------------------------


class BuildReceiptTests(unittest.TestCase):
    ROW = {
        "kind": "live_number_nameplate",
        "selector": "02H0:arm_digit:1",
        "asset_code": "02", "side": "H", "variant": 0, "family": "arm", "digit": 1,
        "stored_size": 896,
        "outcome": "kept_retail",
        "input_sha256": "b" * 64,
        "reason": "Digit artwork cannot fit its 896-byte texture slot without dropping below the 16-colour quality budget.",
        "message": (
            "arm digit 1 (02H0): kept retail: could not fit its 896-byte texture slot "
            "at the 16-colour quality budget; the retail digit was kept."
        ),
    }

    def _build(self, manifest_extra: dict[str, object]):
        from tests.mod_editor.test_nfl2k5_build_service import (
            FakeBackendRunner, SyntheticFixture,
        )
        from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildService

        class Runner(FakeBackendRunner):
            def run(self, argv, cwd):
                result = super().run(argv, cwd)
                if tuple(str(value) for value in argv)[2] == "build":
                    manifest = self._argument(tuple(str(value) for value in argv), "--manifest")
                    value = json.loads(manifest.read_text(encoding="utf-8"))
                    value.update(manifest_extra)
                    manifest.write_text(json.dumps(value), encoding="utf-8", newline="")
                return result

        with tempfile.TemporaryDirectory(prefix="hf63-receipt-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            service = Nfl2k5BuildService(runner=Runner())
            return service.build(fixture.cache, fixture.project, fixture.output)

    def test_kept_retail_rows_reach_the_result_and_its_message(self) -> None:
        result = self._build({"kept_retail": [self.ROW]})
        self.assertEqual(result.kept_retail, (self.ROW,))
        self.assertIn("Kept retail for 1 uniform slot", result.message)
        self.assertIn("02H0", result.message)
        self.assertIn("896-byte", result.message)
        self.assertIn(result.output_xiso.name, result.message)

    def test_no_rows_means_no_message_so_the_gui_fallback_stands(self) -> None:
        result = self._build({})
        self.assertEqual(result.kept_retail, ())
        self.assertEqual(result.message, "")

    def test_a_forged_row_shape_is_refused(self) -> None:
        from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildError

        with self.assertRaisesRegex(Nfl2k5BuildError, "receipt"):
            self._build({"kept_retail": [{"selector": 5}]})

    def test_build_and_share_completion_names_the_kept_slot(self) -> None:
        from mod_editor.core.build_feedback import completion
        from mod_editor.core.nfl2k5_build_service import BuildResult

        result = BuildResult(
            output_xiso=Path(tempfile.gettempdir()) / "x.iso", output_size=1, output_sha256="a" * 64,
            edit_count=2, changed_byte_count=12, kept_retail=(self.ROW,),
        )
        receipt = {
            "outcome": {"status": "changed", "message": "The output differs from the source."},
            "steps": [{"step": "shared_project", **asdict(result)}, {"step": "xbe"}],
        }
        title, message = completion(receipt)
        self.assertEqual(title, "Disc ready")
        self.assertIn("The output differs from the source.", message)
        self.assertIn("Kept retail for 1 uniform slot", message)
        self.assertIn("02H0", message)
        plain_title, plain_message = completion({
            "outcome": {"status": "changed", "message": "The output differs from the source."},
            "steps": [{"step": "xbe"}],
        })
        self.assertEqual((plain_title, plain_message), ("Disc ready", "The output differs from the source."))


class FacadeKeptRetailTests(unittest.TestCase):
    def test_last_build_kept_retail_maps_rows_to_catalog_asset_ids(self) -> None:
        from mod_editor.core.nfl2k5_build_service import BuildResult
        from mod_editor.studio.facade import Nfl2k5StudioFacade

        facade = Nfl2k5StudioFacade.__new__(Nfl2k5StudioFacade)
        import threading

        facade._lock = threading.RLock()
        facade._last_build = BuildResult(
            output_xiso=Path(tempfile.gettempdir()) / "x.iso", output_size=1, output_sha256="a" * 64,
            edit_count=1, changed_byte_count=0, kept_retail=(BuildReceiptTests.ROW,),
        )
        rows = facade.last_build_kept_retail
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset_id"], "nfl2k5.uniform.02h0.digit.arm.1")
        self.assertEqual(rows[0]["message"], BuildReceiptTests.ROW["message"])
        self.assertEqual(facade.kept_retail_asset_ids, frozenset({"nfl2k5.uniform.02h0.digit.arm.1"}))
        facade._last_build = None
        self.assertEqual(facade.last_build_kept_retail, ())
        self.assertEqual(facade.kept_retail_asset_ids, frozenset())


if __name__ == "__main__":
    unittest.main()
