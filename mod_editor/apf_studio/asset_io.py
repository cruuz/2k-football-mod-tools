"""Preview and export adapters for the live APF asset catalog."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable, Iterable
import zipfile

from PIL import Image

from mod_editor.core import platform_compat

from .backend import ensure_tools_importable
from .catalog import ApfCatalog
from .inspectors import ExportIdentity, InspectorRow
from . import scene_textures
from .models import (
    ApfAsset,
    ApfCategory,
    ApfSource,
    ExternalAudioBankIdentity,
    UniformAsset,
)
from .stadium import (
    ApfStadiumPreview,
    ApfStadiumScene,
    ApfStadiumService,
)


ensure_tools_importable()
import apf_audio  # type: ignore  # noqa: E402
import apf_ausb_audio  # type: ignore  # noqa: E402
import apf_digital_font_layout  # type: ignore  # noqa: E402
import apf_helmet_color_transport  # type: ignore  # noqa: E402
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_xenos_dxn_mip_layout  # type: ignore  # noqa: E402
import apf_xenos_dxt5a  # type: ignore  # noqa: E402


class AssetIoError(ValueError):
    """Human-readable export/preview failure."""


class AudioPreviewCancelled(AssetIoError):
    """A private audio preview was cancelled before it could be published."""


def _require_audio_preview_not_cancelled(
    cancel_requested: Callable[[], bool] | None,
) -> None:
    if cancel_requested is None:
        return
    try:
        cancelled = cancel_requested()
    except Exception as exc:
        raise AssetIoError(
            f"Could not check whether audio preview was cancelled: {exc}"
        ) from exc
    if cancelled:
        raise AudioPreviewCancelled("Audio preview cancelled")


def _exclusive_copy(
    source: Path,
    destination: Path,
    *,
    cancel_requested: Callable[[], bool] | None = None,
) -> Path:
    _require_audio_preview_not_cancelled(cancel_requested)
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".exporting", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                _require_audio_preview_not_cancelled(cancel_requested)
                view = memoryview(block)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
        platform_compat.fchmod(descriptor, 0o644, path=temporary)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _require_audio_preview_not_cancelled(cancel_requested)
        # Publish through the platform layer: Windows/exFAT may not support
        # hard links even when a same-directory rename is atomic.
        platform_compat.publish_no_replace(temporary, destination)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _playlist_label(value: object, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = "".join(
        character if ord(character) >= 32 and ord(character) != 127 else " "
        for character in value
    ).strip()
    return cleaned or fallback


def _playlist_duration(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-1"
    duration = float(value)
    if not math.isfinite(duration) or duration < 0:
        return "-1"
    return f"{duration:.3f}".rstrip("0").rstrip(".")


def _write_audio_playlist(
    destination: Path,
    collection_name: str,
    records: Iterable[dict[str, object]],
) -> int:
    """Write an ordered UTF-8 playlist for one private XMA/WAV export."""

    selected = tuple(records)
    lines = [
        "#EXTM3U",
        f"#PLAYLIST:{_playlist_label(collection_name, fallback='APF audio collection')}",
    ]
    for index, row in enumerate(selected, 1):
        title = _playlist_label(row.get("title"), fallback=f"Sound {index:03d}")
        lines.append(
            f"#EXTINF:{_playlist_duration(row.get('duration_seconds'))},{title}"
        )
        lines.append(str(row["path"]))
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(selected)


class ApfAssetIO:
    PREVIEW_CACHE_VERSION = "v2"

    def __init__(
        self,
        source: ApfSource,
        catalog: ApfCatalog,
        cache_root: Path | None = None,
    ):
        self.source = source
        self.catalog = catalog
        self.cache_root = cache_root or Path.home() / ".cache" / "apf2k8-mod-studio"
        self._audio_preview_receipts: dict[Path, str] = {}
        # Set by every preview decode: a plain note when the decoded alpha was
        # uniformly zero and the preview was forced opaque for display, else
        # None. Panels append it to their status text so the user is not
        # misled about what they are editing; raw exports and encoders retain
        # the source alpha.
        self.display_alpha_note: str | None = None
        self.stadium = ApfStadiumService(source, catalog, self.cache_root)

    def _force_opaque_for_display(self, rgba: bytes) -> bytes:
        rgba, applied = apf_inner.force_opaque_alpha_for_display(rgba)
        self.display_alpha_note = (
            "This texture's alpha channel is unused storage (all zero); "
            "the preview is shown opaque so the real mask data is visible."
            if applied
            else None
        )
        return rgba

    def _set_display_alpha_note_from_rgba(self, rgba: bytes) -> None:
        _rgba, applied = apf_inner.force_opaque_alpha_for_display(rgba)
        self.display_alpha_note = (
            "This texture's alpha channel is unused storage (all zero); "
            "the preview is shown opaque so the real mask data is visible."
            if applied
            else None
        )

    @property
    def originals_root(self) -> Path:
        return self.cache_root / "originals" / self.source.source_sha256

    def preview_uniform(self, asset: UniformAsset | str) -> Path:
        item = self.catalog.uniform(asset) if isinstance(asset, str) else asset
        destination = (
            self.originals_root
            / self.PREVIEW_CACHE_VERSION
            / "uniforms"
            / f"{item.family}-{item.asset_index:02d}.png"
        )
        if destination.is_file():
            self._validate_uniform_png(destination, item)
            with Image.open(destination) as image:
                image.load()
                self._set_display_alpha_note_from_rgba(image.tobytes())
            return destination
        rgba = self._decode_uniform_rgba(item)
        rgba = self._force_opaque_for_display(rgba)
        self._write_png_cache(destination, item.width, item.height, rgba)
        self._validate_uniform_png(destination, item)
        return destination

    def export_uniform(self, asset: UniformAsset | str, destination: Path) -> Path:
        item = self.catalog.uniform(asset) if isinstance(asset, str) else asset
        with tempfile.TemporaryDirectory(prefix="apf-uniform-export-") as temporary:
            source = Path(temporary) / f"{item.family}-{item.asset_index:02d}.png"
            rgba = self._decode_uniform_rgba(item)
            self._write_png_cache(source, item.width, item.height, rgba)
            return _exclusive_copy(source, destination)

    def preview_digital_font(self) -> Path:
        self.display_alpha_note = None
        destination = self.originals_root / "presentation" / "digital_font.png"
        if destination.is_file():
            with Image.open(destination) as image:
                image.load()
                if image.size != (128, 128) or image.mode != "RGBA":
                    raise AssetIoError("The private digital_font preview cache is invalid")
            return destination
        document = apf_digital_font_layout.audit(self.source.index_0a)
        # ``audit`` verifies the exact owner and transport; read the same target
        # once more so no retail pixels are ever embedded in the application.
        archive = apf_outer.parse_archive(self.source.index_0a)
        entry = archive.entries[1310]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            target = record.files[246]
            block = apf_inner.decode_block(
                reader, record, target.parts[1].block_index, 1 << 30
            )
            part = target.parts[1]
            tiled = block[part.offset : part.offset + part.length]
        linear = apf_xenos_dxt5a.extract_linear(tiled)
        alpha = apf_xenos_dxt5a.decode_linear_alpha(linear)
        rgba = apf_xenos_dxt5a.alpha_to_rgba(alpha)
        if document.get("target", {}).get("decoded_alpha_sha256") not in {
            None,
            hashlib.sha256(alpha).hexdigest(),
        }:
            raise AssetIoError("digital_font preview did not match its pinned layout audit")
        self._write_png_cache(destination, 128, 128, rgba)
        return destination

    def export_digital_font(self, destination: Path) -> Path:
        return _exclusive_copy(self.preview_digital_font(), destination)

    def scene_textures(
        self, assets: Iterable[ApfAsset]
    ) -> tuple[scene_textures.SceneTexture, ...]:
        """Embedded TXTR descriptors declared by the given SCNE rows.

        These have no inner-file index, so they are not catalog assets and
        never gain an editable status; the caller lists them as read-only
        artwork.
        """

        return scene_textures.read_scene_textures(self.source, tuple(assets))

    def preview_scene_texture(self, texture: scene_textures.SceneTexture) -> Path:
        destination = (
            self.originals_root
            / self.PREVIEW_CACHE_VERSION
            / "scene-textures"
            / f"outer-{texture.outer_index:04d}-inner-{texture.inner_index:04d}"
            f"-tex-{texture.index:03d}.png"
        )
        if destination.is_file() and not destination.is_symlink():
            try:
                with Image.open(destination) as image:
                    image.load()
                    if image.format == "PNG" and image.mode == "RGBA":
                        self._set_display_alpha_note_from_rgba(image.tobytes())
                        return destination
            except (OSError, ValueError):
                pass
            # A private derived cache, so a truncated file is rebuilt rather
            # than handed to the user as their exported image.
            destination.unlink(missing_ok=True)
        payload = scene_textures.read_texture_payload(self.source, texture)
        try:
            width, height, rgba = scene_textures.decode_texture_rgba(
                texture, payload, for_display=True
            )
        except (scene_textures.SceneTextureError, apf_inner.FormatError, ValueError) as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise AssetIoError(
                f"{texture.title}: PNG preview failed ({detail}). "
                "Export the raw descriptor and payload instead."
            ) from exc
        rgba = self._force_opaque_for_display(rgba)
        self._write_png_cache(destination, width, height, rgba)
        return destination

    def export_scene_texture(
        self, texture: scene_textures.SceneTexture, destination: Path
    ) -> Path:
        suffix = destination.suffix.casefold()
        if suffix == ".png":
            with tempfile.TemporaryDirectory(prefix="apf-scene-texture-export-") as name:
                source = Path(name) / "scene-texture.png"
                payload = scene_textures.read_texture_payload(self.source, texture)
                width, height, rgba = scene_textures.decode_texture_rgba(texture, payload)
                self._write_png_cache(source, width, height, rgba)
                return _exclusive_copy(source, destination)
        if suffix != ".zip":
            raise AssetIoError(
                "An embedded scene texture exports as .png (decoded) or .zip "
                "(raw descriptor and payload)."
            )
        return self._export_scene_texture_bundle(texture, destination)

    def _export_scene_texture_bundle(
        self, texture: scene_textures.SceneTexture, destination: Path
    ) -> Path:
        payload = scene_textures.read_texture_payload(self.source, texture)
        with tempfile.TemporaryDirectory(prefix="apf-scene-texture-export-") as name:
            temporary = Path(name) / "scene-texture.zip"
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("payload.bin", payload)
                archive.writestr(
                    "metadata.json",
                    json.dumps(
                        {
                            "schema": "apf2k8_mod_studio_scene_texture_export/v1",
                            "outer_index": texture.outer_index,
                            "inner_index": texture.inner_index,
                            "scene_name": texture.scene_name,
                            "embedded_index": texture.index,
                            "texture_id": f"0x{texture.texture_id:08x}",
                            "width": texture.width,
                            "height": texture.height,
                            "format_name": texture.format_name,
                            "video_offset": texture.video_offset,
                            "payload_length": len(payload),
                            "payload_sha256": hashlib.sha256(payload).hexdigest(),
                            "writer_available": False,
                            "note": (
                                "Local export from the user's own game; do not "
                                "redistribute retail payloads. No writer is "
                                "proved for textures embedded in a SCNE part."
                            ),
                        },
                        indent=2,
                    )
                    + "\n",
                )
            return _exclusive_copy(temporary, destination)

    def preview_texture(self, asset: ApfAsset | str) -> Path:
        item = self.catalog.get(asset) if isinstance(asset, str) else asset
        if item.type_name != "TXTR" or item.inner_index is None:
            raise AssetIoError("Only TXTR assets have PNG previews")
        destination = (
            self.originals_root
            / self.PREVIEW_CACHE_VERSION
            / "textures"
            / f"outer-{item.outer_index:04d}-inner-{item.inner_index:04d}.png"
        )
        if destination.is_file():
            try:
                with Image.open(destination) as image:
                    image.load()
                    if image.format != "PNG" or image.mode != "RGBA":
                        raise AssetIoError("cached texture preview is not an RGBA PNG")
                    self._set_display_alpha_note_from_rgba(image.tobytes())
                return destination
            except (OSError, ValueError, AssetIoError):
                # This directory is a private, derived cache.  A truncated cache
                # must never become the user's exported image; rebuild it from
                # the validated source instead.
                destination.unlink(missing_ok=True)
        try:
            width, height, rgba = self._decode_texture_rgba(item)
        except (apf_inner.FormatError, ValueError) as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise AssetIoError(
                f"{item.name}: PNG preview failed ({detail}). "
                "Export the exact raw TXTR parts instead, or pick a format "
                "already supported for PNG (8, 1_5_5_5, 5_6_5, 8_8_8_8, 8_8, "
                "4_4_4_4, DXT1/2_3/4_5, DXN helmet+namefont base-only, "
                "format-32 cubemap face-0, linear untiled uncompressed + DXT). "
                "If this stays on “Preparing preview…”, re-select the row or "
                "search by asset name — a PORTME format will show this error "
                "instead of hanging blank."
            ) from exc
        rgba = self._force_opaque_for_display(rgba)
        self._write_png_cache(destination, width, height, rgba)
        return destination

    def export_asset(self, asset: ApfAsset | str, destination: Path) -> Path:
        item = self.catalog.get(asset) if isinstance(asset, str) else asset
        suffix = destination.suffix.casefold()
        if item.type_name == "TXTR" and suffix == ".png":
            with tempfile.TemporaryDirectory(prefix="apf-texture-export-") as temporary:
                source = Path(temporary) / f"outer-{item.outer_index:04d}-inner-{item.inner_index:04d}.png"
                width, height, rgba = self._decode_texture_rgba(item)
                self._write_png_cache(source, width, height, rgba)
                return _exclusive_copy(source, destination)
        if item.type_name == "AUDO" and suffix in {".xma", ".wav"}:
            return self._export_audo(item, destination)
        if item.inner_index is None and suffix != ".zip":
            return self._export_outer_raw(item, destination)
        return self._export_inner_bundle(item, destination)

    def stadium_scenes(self, search: str = "") -> tuple[ApfStadiumScene, ...]:
        return self.stadium.scenes(search)

    def stadium_package_assets(
        self, scene: ApfStadiumScene | str
    ) -> tuple[ApfAsset, ...]:
        return self.stadium.package_assets(scene)

    def prepare_stadium_scene(
        self,
        scene: ApfStadiumScene | str,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> ApfStadiumPreview:
        return self.stadium.prepare(scene, progress)

    def export_stadium_scene_bundle(
        self,
        scene: ApfStadiumScene | str,
        destination: Path,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> Path:
        """Export one private glTF/bin/manifest triplet as a local ZIP."""

        destination = destination.expanduser()
        if destination.suffix.casefold() != ".zip":
            raise AssetIoError("A stadium 3D scene exports as a .zip archive")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        preview = self.prepare_stadium_scene(scene, progress)
        with tempfile.TemporaryDirectory(
            prefix="apf-stadium-gltf-export-"
        ) as temporary_name:
            archive_path = Path(temporary_name) / "stadium-scene.zip"
            with zipfile.ZipFile(
                archive_path, "x", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.write(preview.gltf_path, "scene.gltf")
                archive.write(preview.bin_path, "scene.bin")
                archive.write(preview.manifest_path, "manifest.json")
            return _exclusive_copy(archive_path, destination)

    def export_audio_identity(
        self,
        identity: ExportIdentity,
        destination: Path,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        """Export one inspector-selected AUDO or AUSB substream as XMA/WAV."""

        _require_audio_preview_not_cancelled(cancel_requested)
        suffix = destination.suffix.casefold()
        supported = tuple(
            value for value in identity.supported_extensions if value in {".xma", ".wav"}
        )
        if suffix not in supported:
            expected = " or ".join(supported or (".xma", ".wav"))
            raise AssetIoError(f"Choose an audio filename ending in {expected}")
        if destination.exists():
            raise FileExistsError(destination)
        if identity.kind not in {"audo", "ausb_substream"}:
            raise AssetIoError(f"No audio exporter owns {identity.kind!r}")
        if identity.kind == "audo" and identity.substream_index is not None:
            raise AssetIoError("AUDO export coordinates unexpectedly include a substream")
        if identity.kind == "ausb_substream" and identity.substream_index is None:
            raise AssetIoError("AUSB export coordinates are missing the substream index")

        with tempfile.TemporaryDirectory(prefix="apf-audio-export-") as temporary_name:
            temporary = Path(temporary_name)
            xma = temporary / "selected.xma"
            wav = temporary / "selected.wav" if suffix == ".wav" else None
            try:
                if identity.kind == "audo":
                    arguments = (
                        self.source.index_0a,
                        identity.outer_table_index,
                        identity.inner_file_index,
                        xma,
                        wav,
                        512 * 1024 * 1024,
                    )
                    result = (
                        apf_audio.export_selected(*arguments)
                        if cancel_requested is None
                        else apf_audio.export_selected(
                            *arguments,
                            cancel_requested=cancel_requested,
                        )
                    )
                else:
                    assert identity.substream_index is not None
                    arguments = (
                        self.source.index_0a,
                        identity.outer_table_index,
                        identity.inner_file_index,
                        identity.substream_index,
                        xma,
                        wav,
                        512 * 1024 * 1024,
                    )
                    result = (
                        apf_ausb_audio.export_substream(*arguments)
                        if cancel_requested is None
                        else apf_ausb_audio.export_substream(
                            *arguments,
                            cancel_requested=cancel_requested,
                        )
                    )
            except apf_audio.AudioCancelled as exc:
                raise AudioPreviewCancelled("Audio preview cancelled") from exc
            except (apf_audio.AudioError, OSError, ValueError) as exc:
                raise AssetIoError(f"Could not export this APF sound: {exc}") from exc

            _require_audio_preview_not_cancelled(cancel_requested)
            if wav is not None:
                wav_report = result.get("wav")
                if (
                    not isinstance(wav_report, dict)
                    or not str(wav_report.get("status", "")).startswith("decoder_verified")
                    or not wav.is_file()
                ):
                    raise AssetIoError(
                        "This XMA1 sound did not decode cleanly to WAV. "
                        "Export it as .xma instead."
                    )
                generated = wav
            else:
                if not xma.is_file():
                    raise AssetIoError("The APF audio exporter produced no XMA file")
                generated = xma
            return _exclusive_copy(
                generated,
                destination,
                cancel_requested=cancel_requested,
            )

    def export_external_audio_bank(
        self,
        identity: ExternalAudioBankIdentity,
        destination: Path,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Export one proved physical XMA1 bank without treating it as a cue."""

        destination = destination.expanduser()
        if destination.suffix.casefold() != ".bin":
            raise AssetIoError("Original APF external audio banks export as .bin files")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        if (
            not identity.owners
            or Path(identity.external_filename).name != identity.external_filename
            or not identity.external_filename.casefold().endswith(".bin")
            or identity.encoded_size <= 0
        ):
            raise AssetIoError("The external audio-bank identity is incomplete")
        try:
            asset = self.catalog.get(identity.raw_asset_id)
        except (KeyError, ValueError) as exc:
            raise AssetIoError(
                f"The loaded catalog no longer owns {identity.external_filename}"
            ) from exc
        if (
            asset.inner_index is not None
            or asset.type_name != "XMA1_BANK"
            or asset.category is not ApfCategory.AUDIO
            or asset.name != identity.external_filename
            or asset.outer_index != identity.outer_table_index
            or asset.decoded_size != identity.encoded_size
            or str(asset.metadata.get("name_id", "")).casefold()
            != f"0x{identity.name_id:08x}"
        ):
            raise AssetIoError(
                f"The loaded catalog no longer matches {identity.external_filename}"
            )

        archive = apf_outer.parse_archive(self.source.index_0a)
        entries = {
            int(entry.table_index): entry for entry in archive.entries
        }
        entry = entries.get(identity.outer_table_index)
        if (
            entry is None
            or entry.head_hex == f"{apf_inner.IFF_MAGIC:08x}"
            or int(entry.name_id) != identity.name_id
            or int(entry.size) != identity.encoded_size
        ):
            raise AssetIoError(
                f"The source record for {identity.external_filename} changed ownership"
            )
        return self._export_outer_raw(asset, destination, progress=progress)

    def prepare_audio_preview(
        self,
        identity: ExportIdentity,
        preview_root: Path,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        """Create one session-private, decoder-verified WAV for Play/Stop.

        Preview WAVs never enter a project or release artifact. Existing files
        are accepted only when this live session created and receipted them;
        symlinks, replacements, and valid-looking tampered WAVs fail closed.
        """

        _require_audio_preview_not_cancelled(cancel_requested)
        preview_root = preview_root.expanduser()
        preview_root.mkdir(parents=True, exist_ok=True)
        root_stat = preview_root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
            raise AssetIoError("The private audio preview folder is not a safe directory")
        pieces = [
            identity.kind,
            f"o{identity.outer_table_index:04d}",
            f"i{identity.inner_file_index:04d}",
        ]
        if identity.substream_index is not None:
            pieces.append(f"s{identity.substream_index:05d}")
        destination = preview_root / ("-".join(pieces) + ".wav")
        expected_receipt = self._audio_preview_receipts.get(destination)
        if destination.exists() or destination.is_symlink():
            if expected_receipt is None:
                raise AssetIoError(
                    "An unreceipted file appeared in the private audio preview folder"
                )
            actual = self._validated_preview_wav(destination)
            _require_audio_preview_not_cancelled(cancel_requested)
            if actual != expected_receipt:
                raise AssetIoError(
                    "The private audio preview changed after it was decoded; reload the game"
                )
            return destination

        try:
            if cancel_requested is None:
                self.export_audio_identity(identity, destination)
            else:
                self.export_audio_identity(
                    identity,
                    destination,
                    cancel_requested=cancel_requested,
                )
            _require_audio_preview_not_cancelled(cancel_requested)
            receipt = self._validated_preview_wav(destination)
            _require_audio_preview_not_cancelled(cancel_requested)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        self._audio_preview_receipts[destination] = receipt
        return destination

    def export_audio_bank(
        self,
        identities: Iterable[ExportIdentity],
        destination: Path,
        *,
        bank_name: str,
        output_extension: str = ".xma",
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Transactionally export one complete, bounded AUSB bank as a ZIP."""

        selected = tuple(
            sorted(
                identities,
                key=lambda value: (
                    -1 if value.substream_index is None else value.substream_index
                ),
            )
        )
        if destination.suffix.casefold() != ".zip":
            raise AssetIoError("A complete APF audio bank exports as a .zip archive")
        if output_extension not in {".xma", ".wav"}:
            raise AssetIoError("Bank audio must export as original .xma or verified .wav")
        if not 1 <= len(selected) <= 256:
            raise AssetIoError(
                "One-click bank export is limited to complete banks of 1–256 sounds"
            )
        owner = {
            (identity.outer_table_index, identity.inner_file_index)
            for identity in selected
        }
        indices = [identity.substream_index for identity in selected]
        if (
            any(identity.kind != "ausb_substream" for identity in selected)
            or len(owner) != 1
            or any(index is None for index in indices)
            or indices != list(range(len(selected)))
        ):
            raise AssetIoError(
                "Bulk export requires every substream from one complete, bounded AUSB bank"
            )
        if destination.exists():
            raise FileExistsError(destination)
        safe_bank = "".join(
            character if character.isalnum() or character in "._-" else "-"
            for character in bank_name.strip()
        ).strip("-._")[:80] or "apf-audio-bank"
        report = progress or (lambda _completed, _total: None)
        with tempfile.TemporaryDirectory(prefix="apf-audio-bank-export-") as temporary_name:
            root = Path(temporary_name)
            payload_root = root / "audio"
            payload_root.mkdir()
            manifest_rows: list[dict[str, object]] = []
            report(0, len(selected))
            for completed, identity in enumerate(selected, 1):
                assert identity.substream_index is not None
                relative = Path("audio") / (
                    f"{identity.substream_index + 1:03d}-{safe_bank}"
                    f"{output_extension}"
                )
                self.export_audio_identity(identity, root / relative)
                manifest_rows.append(
                    {
                        "path": relative.as_posix(),
                        "title": f"{bank_name} Track {identity.substream_index + 1:03d}",
                        "duration_seconds": None,
                        "outer_table_index": identity.outer_table_index,
                        "inner_file_index": identity.inner_file_index,
                        "substream_index": identity.substream_index,
                    }
                )
                report(completed, len(selected))
            playlist_count = _write_audio_playlist(
                root / "playlist.m3u8", bank_name, manifest_rows
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "apf2k8_mod_studio_audio_bank_export/v1",
                        "bank_name": bank_name,
                        "substream_count": len(selected),
                        "format": output_extension.removeprefix("."),
                        "playlist": "playlist.m3u8",
                        "playlist_record_count": playlist_count,
                        "records": manifest_rows,
                        "note": (
                            "Local retail-derived audio from the user's own game; "
                            "do not redistribute copyrighted payloads."
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
    newline="\n",
)
            archive_path = root / "bank.zip"
            with zipfile.ZipFile(
                archive_path, "x", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.write(root / "manifest.json", "manifest.json")
                archive.write(root / "playlist.m3u8", "playlist.m3u8")
                for row in manifest_rows:
                    relative = Path(str(row["path"]))
                    archive.write(root / relative, relative.as_posix())
            return _exclusive_copy(archive_path, destination)

    def export_audio_bundle(
        self,
        rows: Iterable[InspectorRow],
        destination: Path,
        *,
        bundle_name: str,
        output_extension: str = ".xma",
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Transactionally export 1–256 currently filtered sounds as one ZIP.

        Unlike complete-bank export, a bundle may mix standalone AUDO sounds
        and AUSB substreams.  It is intentionally bounded so a broad 45,000-row
        filter cannot accidentally start an enormous decode; the GUI tells the
        user to narrow search/kind/role filters first.
        """

        selected = tuple(rows)
        if destination.suffix.casefold() != ".zip":
            raise AssetIoError("Matching APF sounds export as a .zip archive")
        if output_extension not in {".xma", ".wav"}:
            raise AssetIoError(
                "Matching audio must export as original .xma or verified .wav"
            )
        if not 1 <= len(selected) <= 256:
            raise AssetIoError(
                "Export matching sounds requires 1–256 playable rows; narrow the current filters"
            )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)

        identities: list[ExportIdentity] = []
        seen_rows: set[str] = set()
        seen_coordinates: set[tuple[int, int, int | None]] = set()
        for row in selected:
            identity = row.export_identity
            if identity is None or identity.kind not in {"audo", "ausb_substream"}:
                raise AssetIoError(
                    "Every matching-audio row must own an AUDO or AUSB sound export"
                )
            if row.row_id in seen_rows or identity.coordinates in seen_coordinates:
                raise AssetIoError("Matching-audio rows must be unique")
            seen_rows.add(row.row_id)
            seen_coordinates.add(identity.coordinates)
            identities.append(identity)

        safe_bundle = "".join(
            character if character.isalnum() or character in " ._-" else "-"
            for character in bundle_name.strip()
        ).strip(" ._-")[:120] or "APF filtered audio"
        report = progress or (lambda _completed, _total: None)
        with tempfile.TemporaryDirectory(
            prefix="apf-audio-bundle-export-"
        ) as temporary_name:
            root = Path(temporary_name)
            payload_root = root / "audio"
            payload_root.mkdir()
            manifest_rows: list[dict[str, object]] = []
            report(0, len(selected))
            for completed, (row, identity) in enumerate(
                zip(selected, identities, strict=True), 1
            ):
                safe_stem = "".join(
                    character if character.isalnum() or character in "._-" else "-"
                    for character in identity.suggested_basename.strip()
                ).strip("._-")[:96] or f"sound-{completed:03d}"
                relative = Path("audio") / (
                    f"{completed:03d}-{safe_stem}{output_extension}"
                )
                self.export_audio_identity(identity, root / relative)
                fields = row.fields
                duration = fields.get(
                    "duration_seconds", fields.get("duration_seconds_candidate")
                )
                manifest_rows.append(
                    {
                        "path": relative.as_posix(),
                        "row_id": row.row_id,
                        "kind": row.kind,
                        "title": row.title,
                        "game_catalog_title": fields.get(
                            "game_catalog_title", row.title
                        ),
                        "custom_title": fields.get("custom_title"),
                        "annotation_note": fields.get("annotation_note"),
                        "role_id": fields.get("role_id"),
                        "role_label": fields.get("role_label"),
                        "bank_name": fields.get("bank_name"),
                        "outer_table_index": identity.outer_table_index,
                        "inner_file_index": identity.inner_file_index,
                        "substream_index": identity.substream_index,
                        "sample_rate": fields.get("sample_rate"),
                        "channels": fields.get("derived_channel_count"),
                        "duration_seconds": duration,
                    }
                )
                report(completed, len(selected))
            playlist_count = _write_audio_playlist(
                root / "playlist.m3u8", safe_bundle, manifest_rows
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "apf2k8_mod_studio_audio_bundle_export/v1",
                        "bundle_name": safe_bundle,
                        "sound_count": len(selected),
                        "format": output_extension.removeprefix("."),
                        "playlist": "playlist.m3u8",
                        "playlist_record_count": playlist_count,
                        "records": manifest_rows,
                        "note": (
                            "Local retail-derived audio from the user's own game; "
                            "do not redistribute copyrighted payloads."
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
    newline="\n",
)
            archive_path = root / "matching-sounds.zip"
            with zipfile.ZipFile(
                archive_path, "x", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.write(root / "manifest.json", "manifest.json")
                archive.write(root / "playlist.m3u8", "playlist.m3u8")
                for row in manifest_rows:
                    relative = Path(str(row["path"]))
                    archive.write(root / relative, relative.as_posix())
            return _exclusive_copy(archive_path, destination)

    @staticmethod
    def _validated_preview_wav(path: Path) -> str:
        supplied = path.lstat()
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_size <= 44
            or supplied.st_size > 1024 * 1024 * 1024
        ):
            raise AssetIoError("The private audio preview is not a safe regular WAV")
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            digest = hashlib.sha256()
            while block := os.read(descriptor, 1024 * 1024):
                digest.update(block)
            after = os.fstat(descriptor)
            if (after.st_dev, after.st_ino, after.st_size) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ):
                raise AssetIoError("The private audio preview changed while being checked")
        finally:
            os.close(descriptor)
        try:
            layout = apf_audio.parse_pcm_wav(path)
        except (apf_audio.AudioError, OSError) as exc:
            raise AssetIoError(f"The private audio preview is not valid PCM WAV: {exc}") from exc
        final = path.lstat()
        if (
            stat.S_ISLNK(final.st_mode)
            or (final.st_dev, final.st_ino, final.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
        ):
            raise AssetIoError("The private audio preview changed during WAV validation")
        if layout["bits_per_sample"] != 16 or layout["channels"] not in {1, 2}:
            raise AssetIoError("The private audio preview has an unsupported PCM layout")
        return digest.hexdigest()

    def _decode_uniform_rgba(self, asset: UniformAsset) -> bytes:
        record, file, parts = self._read_inner_parts(asset.outer_index, asset.inner_index)
        del record, file
        if len(parts) < 2:
            raise AssetIoError(f"{asset.title} no longer has descriptor and texture parts")
        metadata = apf_inner.parse_txtr_metadata(parts[0])
        if asset.family == "helmet":
            apf_helmet_color_transport.strict_descriptor(metadata)
            locations = apf_xenos_dxn_mip_layout.derive_layout(metadata)
            linear = apf_xenos_dxn_mip_layout.extract_linear_dxn(parts[1], locations[0])
            rgba = apf_helmet_color_transport.decode_linear_dxn(linear, locations[0])
            if len(rgba) != asset.width * asset.height * 4:
                raise AssetIoError("Helmet preview dimensions changed")
            return rgba
        width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, parts[1])
        if (width, height) != (asset.width, asset.height):
            raise AssetIoError(
                f"{asset.title} decoded as {width}x{height}, expected {asset.width}x{asset.height}"
            )
        return rgba

    def _decode_texture_rgba(self, asset: ApfAsset) -> tuple[int, int, bytes]:
        assert asset.inner_index is not None
        _record, _file, parts = self._read_inner_parts(asset.outer_index, asset.inner_index)
        if not parts:
            raise AssetIoError("Texture has no stored parts")
        metadata = apf_inner.parse_txtr_metadata(parts[0])
        if int(metadata.get("format", -1)) == 49:
            locations = apf_xenos_dxn_mip_layout.derive_layout(metadata)
            linear = apf_xenos_dxn_mip_layout.extract_linear_dxn(parts[-1], locations[0])
            rgba = apf_helmet_color_transport.decode_linear_dxn(linear, locations[0])
            return (
                locations[0].width,
                locations[0].height,
                rgba,
            )
        if int(metadata.get("format", -1)) == 59:
            # General DXT5A (not only digital_font 128×128 fixed allocation).
            width = int(metadata["width"])
            height = int(metadata["height"])
            pitch = int(metadata.get("pitch_pixels", width))
            endian = int(metadata.get("endianness", 1))
            if not metadata.get("tiled", True):
                raise AssetIoError(
                    "PORTME: linear DXT5A base-level routing is unverified"
                )
            linear = apf_xenos_dxt5a.extract_linear_general(
                parts[-1], width, height, pitch, endian_mode=endian
            )
            alpha = apf_xenos_dxt5a.decode_linear_alpha_general(
                linear, width, height
            )
            rgba = apf_xenos_dxt5a.alpha_to_rgba_general(alpha, width, height)
            return width, height, rgba
        width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, parts[-1])
        return width, height, rgba

    def _read_inner_parts(
        self, outer_index: int, inner_index: int
    ) -> tuple[object, object, list[bytes]]:
        archive = apf_outer.parse_archive(self.source.index_0a)
        try:
            entry = archive.entries[outer_index]
        except IndexError as exc:
            raise AssetIoError(f"No APF outer entry {outer_index}") from exc
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            try:
                item = record.files[inner_index]
            except IndexError as exc:
                raise AssetIoError(
                    f"Outer {outer_index} has no inner asset {inner_index}"
                ) from exc
            cache: dict[int, bytes] = {}
            payloads: list[bytes] = []
            for part in item.parts:
                if part.block_index not in cache:
                    cache[part.block_index] = apf_inner.decode_block(
                        reader, record, part.block_index, 512 * 1024 * 1024
                    )
                block = cache[part.block_index]
                payloads.append(block[part.offset : part.offset + part.length])
        return record, item, payloads

    def _export_audo(self, asset: ApfAsset, destination: Path) -> Path:
        assert asset.inner_index is not None
        return self.export_audio_identity(
            ExportIdentity(
                kind="audo",
                outer_table_index=asset.outer_index,
                inner_file_index=asset.inner_index,
                substream_index=None,
                suggested_basename=asset.name,
            ),
            destination,
        )

    def _export_outer_raw(
        self,
        asset: ApfAsset,
        destination: Path,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        archive = apf_outer.parse_archive(self.source.index_0a)
        entry = archive.entries[asset.outer_index]
        report = progress or (lambda _completed, _total: None)
        destination = destination.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".exporting",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                with apf_inner.ArchiveReader(archive) as reader:
                    offset = 0
                    report(0, entry.size)
                    while offset < entry.size:
                        count = min(8 * 1024 * 1024, entry.size - offset)
                        block = reader.read(entry, offset, count)
                        if len(block) != count:
                            raise AssetIoError(
                                f"Outer {asset.outer_index} ended during export"
                            )
                        stream.write(block)
                        offset += count
                        report(offset, entry.size)
                stream.flush()
                platform_compat.fchmod(stream.fileno(), 0o644, path=temporary)
                os.fsync(stream.fileno())
            platform_compat.publish_no_replace(temporary, destination)
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def _export_inner_bundle(self, asset: ApfAsset, destination: Path) -> Path:
        if asset.inner_index is None:
            raise AssetIoError("Choose a .bin destination to export this outer record")
        if destination.suffix.casefold() != ".zip":
            raise AssetIoError(
                "Raw multi-part assets export as .zip bundles. Choose a filename ending in .zip."
            )
        _record, item, parts = self._read_inner_parts(asset.outer_index, asset.inner_index)
        with tempfile.TemporaryDirectory(prefix="apf-asset-export-") as temporary_name:
            temporary = Path(temporary_name) / "asset.zip"
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                part_rows = []
                for index, data in enumerate(parts):
                    name = f"part-{index:02d}.bin"
                    archive.writestr(name, data)
                    part_rows.append(
                        {
                            "path": name,
                            "length": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
                archive.writestr(
                    "metadata.json",
                    json.dumps(
                        {
                            "schema": "apf2k8_mod_studio_asset_export/v1",
                            "outer_index": asset.outer_index,
                            "inner_index": asset.inner_index,
                            "name": item.name,
                            "type_name": item.type_name,
                            "parts": part_rows,
                            "note": "Local export from the user's own game; do not redistribute retail payloads.",
                        },
                        indent=2,
                    )
                    + "\n",
                )
            # Publish exclusively only after the complete archive has closed.
            # This preserves a file created concurrently at the chosen path.
            return _exclusive_copy(temporary, destination)

    @staticmethod
    def _write_png_cache(path: Path, width: int, height: int, rgba: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            Image.frombytes("RGBA", (width, height), rgba).save(
                temporary, format="PNG"
            )
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _validate_uniform_png(path: Path, asset: UniformAsset) -> None:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG" or image.mode != "RGBA" or image.size != (
                asset.width,
                asset.height,
            ):
                raise AssetIoError(
                    f"The private {asset.title} preview cache is invalid; remove {path} and retry."
                )
