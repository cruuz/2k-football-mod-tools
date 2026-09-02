"""A stale cached original is not a tampered one.

Reported symptom: exporting team kits died with "A private original-backup file
changed outside Mod Studio. Remove the source cache and load the XISO again."
Nothing had been edited behind the app's back.

The check folded two unrelated situations into one message. It required the
cached PNG's recorded hashes to match its bytes *and* the record to name the
currently loaded source. Load a different XISO and the second half fails on
every cached original, so a perfectly intact cache reported itself as
tampered-with and the only advice on offer was to delete it.

Those cases now separate. Bytes that disagree with their own recorded hashes are
still refused loudly. An intact legacy entry is re-decoded once and rebound to
the canonical extracted-content cache; canonical entries are shared by every
recognized layout of that same disc.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

for _extra in (_REPO_ROOT / "tools",):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_asset_io as uniform_io  # noqa: E402
from mod_editor.core import nfl2k5_extended_visual_io as vio  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_source_cache import SOURCE_SHA256  # noqa: E402
import nfl_tset_png_import as png_codec  # noqa: E402

_encode = png_codec.encode_rgba_png


class _Asset:
    asset_id = "visual.demo.0001"
    label = "Demo asset"
    width = 4
    height = 4

    @property
    def dimensions(self) -> tuple[int, int]:
        return (self.width, self.height)


class _Source:
    def __init__(self, sha: str) -> None:
        self.sha256 = sha


class _Cache:
    def __init__(self, root: Path, sha: str) -> None:
        self.originals = root
        root.mkdir(parents=True, exist_ok=True)
        self.source = _Source(sha)


def _write_cached_original(root: Path, asset: _Asset, source_sha: str,
                           *, corrupt: bool = False,
                           dimensions: tuple[int, int] | None = None,
                           extended: bool = True) -> tuple[Path, bytes]:
    """Lay down a cached original and its record the way the app would."""
    width, height = dimensions or (asset.width, asset.height)
    rgba = bytes([10, 20, 30, 255]) * (width * height)
    png = _encode(width, height, rgba)
    key = (
        vio._asset_key(asset.asset_id)
        if extended else uniform_io._safe_key(asset.asset_id)
    )
    path = root / f"{key}.png"
    path.write_bytes(png)
    record = {
        "asset_id": asset.asset_id,
        "dimensions": [width, height],
        "png_sha256": uniform_io.sha256_bytes(
            png if not corrupt else b"not the png"
        ),
        "rgba_sha256": uniform_io.sha256_bytes(rgba),
        "schema": (
            vio.ORIGINAL_SCHEMA if extended else uniform_io.ORIGINAL_SCHEMA
        ),
        "source_sha256": source_sha,
    }
    path.with_suffix(".json").write_text(json.dumps(record), encoding="utf-8")
    return path, png


class StaleOriginalTests(unittest.TestCase):
    def test_an_intact_legacy_binding_is_refreshed_not_refused(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cached_original(root, asset, "c" * 64)
            # A pre-fix sidecar named one particular container. That mismatch is
            # stale metadata, not evidence that its verified PNG was altered.
            decoded: list[str] = []

            def decoder(_asset):
                decoded.append("called")
                rgba = bytes([1, 2, 3, 255]) * (asset.width * asset.height)
                return _encode(asset.width, asset.height, rgba), rgba

            io = vio.Nfl2k5ExtendedVisualIO(
                _Cache(root, "a" * 64),
                original_decoder=decoder,
            )
            path = io.ensure_original(asset)
            self.assertEqual(decoded, ["called"],
                             "a stale entry should be re-decoded, not refused")
            record = json.loads(path.with_suffix(".json").read_text())
            self.assertEqual(record["source_sha256"], SOURCE_SHA256)

    def test_canonical_entry_is_reused_across_legal_container_hashes(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, png = _write_cached_original(root, asset, SOURCE_SHA256)

            def decoder(_asset):  # pragma: no cover - must not run
                raise AssertionError("a valid cached original was re-decoded")

            repack = vio.Nfl2k5ExtendedVisualIO(
                _Cache(root, "a" * 64), original_decoder=decoder
            )
            raw_read = vio.Nfl2k5ExtendedVisualIO(
                _Cache(root, "b" * 64), original_decoder=decoder
            )
            self.assertEqual(repack.ensure_original(asset), path)
            self.assertEqual(raw_read.ensure_original(asset), path)
            self.assertEqual(path.read_bytes(), png)

    def test_bytes_that_disagree_with_their_own_record_are_still_refused(self) -> None:
        """The real tampering case must keep its loud failure."""
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cached_original(root, asset, SOURCE_SHA256, corrupt=True)
            io = vio.Nfl2k5ExtendedVisualIO(_Cache(root, "a" * 64))
            with self.assertRaises(ValidationError) as caught:
                io.ensure_original(asset)
            self.assertIn("changed outside Mod Studio", str(caught.exception))

    def test_an_old_dimension_is_redecoded_instead_of_called_tampering(self) -> None:
        """The Titans fix changes 64x64 cache records to their real 32x32."""

        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cached_original(
                root, asset, SOURCE_SHA256, dimensions=(8, 8)
            )
            rgba = bytes([1, 2, 3, 255]) * (asset.width * asset.height)
            io = vio.Nfl2k5ExtendedVisualIO(
                _Cache(root, "a" * 64),
                original_decoder=lambda _asset: (
                    _encode(asset.width, asset.height, rgba), rgba
                ),
            )
            path = io.ensure_original(asset)
            self.assertEqual(
                png_codec.decode_rgba_png(path.read_bytes(), asset.dimensions)[:2],
                asset.dimensions,
            )
            self.assertEqual(
                json.loads(path.with_suffix(".json").read_text())["dimensions"],
                [asset.width, asset.height],
            )

    def test_a_failed_refresh_preserves_the_intact_stale_pair(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, old_png = _write_cached_original(root, asset, "c" * 64)
            metadata = path.with_suffix(".json")
            old_metadata = metadata.read_bytes()

            def failed(_asset):
                raise ValidationError("fresh decode failed")

            io = vio.Nfl2k5ExtendedVisualIO(
                _Cache(root, "a" * 64), original_decoder=failed
            )
            with self.assertRaisesRegex(ValidationError, "fresh decode failed"):
                io.ensure_original(asset)
            self.assertEqual(path.read_bytes(), old_png)
            self.assertEqual(metadata.read_bytes(), old_metadata)


def _uniform_io(root: Path, source_sha: str, decoder) -> uniform_io.Nfl2k5AssetIO:
    """Build the uniform cache lane without requiring a retail archive fixture."""

    result = uniform_io.Nfl2k5AssetIO.__new__(uniform_io.Nfl2k5AssetIO)
    result.cache = _Cache(root, source_sha)
    result._decode_original = decoder
    return result


class TeamKitUniformCacheTests(unittest.TestCase):
    """Team Kit export calls Nfl2k5AssetIO through session.current_path."""

    def test_team_kit_lane_refreshes_an_intact_old_dimension(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cached_original(
                root, asset, SOURCE_SHA256, dimensions=(8, 8), extended=False
            )
            decoded: list[str] = []
            rgba = bytes([5, 6, 7, 255]) * (asset.width * asset.height)

            def decoder(_asset):
                decoded.append("called")
                return _encode(asset.width, asset.height, rgba), rgba

            io = _uniform_io(root, "a" * 64, decoder)
            path = io.ensure_original(asset)
            self.assertEqual(decoded, ["called"])
            self.assertEqual(
                png_codec.decode_rgba_png(path.read_bytes(), asset.dimensions)[2],
                rgba,
            )

    def test_team_kit_lane_refreshes_an_intact_other_source(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cached_original(
                root, asset, "c" * 64, extended=False
            )
            rgba = bytes([5, 6, 7, 255]) * (asset.width * asset.height)
            io = _uniform_io(
                root,
                "a" * 64,
                lambda _asset: (_encode(asset.width, asset.height, rgba), rgba),
            )
            path = io.ensure_original(asset)
            record = json.loads(path.with_suffix(".json").read_text())
            self.assertEqual(record["source_sha256"], SOURCE_SHA256)

    def test_team_kit_lane_reuses_canonical_entry_across_layouts(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, png = _write_cached_original(
                root, asset, SOURCE_SHA256, extended=False
            )

            def decoder(_asset):  # pragma: no cover - must not run
                raise AssertionError("a canonical cached original was re-decoded")

            self.assertEqual(
                _uniform_io(root, "a" * 64, decoder).ensure_original(asset), path
            )
            self.assertEqual(
                _uniform_io(root, "b" * 64, decoder).ensure_original(asset), path
            )
            self.assertEqual(path.read_bytes(), png)

    def test_team_kit_lane_still_refuses_changed_bytes(self) -> None:
        asset = _Asset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_cached_original(
                root, asset, SOURCE_SHA256, corrupt=True, extended=False
            )
            io = _uniform_io(
                root,
                "a" * 64,
                lambda _asset: (_ for _ in ()).throw(
                    AssertionError("tampered bytes must not be silently refreshed")
                ),
            )
            with self.assertRaisesRegex(ValidationError, "changed outside Mod Studio"):
                io.ensure_original(asset)


if __name__ == "__main__":
    unittest.main()
