"""Transactional multi-edit APF game-directory builder."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Callable, Iterable, Mapping

from mod_editor.core import platform_compat
from mod_editor.core.platform_compat import try_reflink

from .backend import ensure_tools_importable
from .models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    DRAFT_LOGO_EDIT_ID,
    DRAFT_LOGO_INNER_INDEX,
    DRAFT_LOGO_OUTER_INDEX,
    ApfSource,
    BuildReceipt,
    Modification,
)
from .source import EXPECTED_0A_SHA256, sha256_file


ensure_tools_importable()
import apf_audo_exact_slot  # type: ignore  # noqa: E402
import apf_ausb_exact_slot  # type: ignore  # noqa: E402
import apf_digital_font_transport  # type: ignore  # noqa: E402
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_player_rating_patch  # type: ignore  # noqa: E402
import apf_player_position_patch  # type: ignore  # noqa: E402
import apf_roster_composite_patch  # type: ignore  # noqa: E402
import apf_texture_patch  # type: ignore  # noqa: E402
import apf_txt_loc_patch  # type: ignore  # noqa: E402
import apf_roster_identity_patch  # type: ignore  # noqa: E402

from .project import ProjectError, decode_text_payload
from .uniform_targets import compile_uniform_patch


Progress = Callable[[str, int, int], None]
BUILD_SCHEMA = "apf2k8_mod_studio_build/v1"
BUILD_SPACE_MARGIN = 512 * 1024 * 1024
EXPECTED_TREE: dict[str, tuple[int, str]] = {
    "0A": (
        1_140_850_688,
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    ),
    "0B": (
        1_073_838_080,
        "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
    ),
    "1A": (
        1_140_850_688,
        "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
    ),
    "1B": (
        517_971_968,
        "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
    ),
    "default.xex": (
        38_408_192,
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    ),
    "$SystemUpdate/su20076000_00000000": (
        7_299_072,
        "39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8",
    ),
}
COMPILED_SPAN_PACKS = frozenset({"0A", "0B", "1A", "1B"})


class BuildError(ValueError):
    """A build failure that never publishes a partial output directory."""


@dataclass(frozen=True)
class _CompiledBuildSpan:
    """One typed, verified pack write in a composed APF build.

    Whole-entry writers and exact-slot audio writers meet at this internal
    boundary.  There is deliberately no public generic raw-write API: only a
    reviewed ``Modification`` compiler may create one of these spans.
    """

    pack_name: str
    offset: int
    data: bytes
    outer_index: int
    asset_ids: tuple[str, ...]
    kind: str
    writer_schema: str
    reparse_owner: bool
    source_span_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.pack_name, str)
            or self.pack_name not in COMPILED_SPAN_PACKS
        ):
            raise BuildError("Compiled APF span has an invalid pack name")
        if type(self.offset) is not int or self.offset < 0:
            raise BuildError("Compiled APF span has an invalid pack offset")
        if not isinstance(self.data, bytes) or not self.data:
            raise BuildError("Compiled APF span must contain nonempty bytes")
        if type(self.outer_index) is not int or self.outer_index < 0:
            raise BuildError("Compiled APF span has an invalid outer owner")
        if (
            not self.asset_ids
            or len(set(self.asset_ids)) != len(self.asset_ids)
            or any(not isinstance(value, str) or not value for value in self.asset_ids)
        ):
            raise BuildError("Compiled APF span has an invalid asset identity")
        if not isinstance(self.kind, str) or not self.kind:
            raise BuildError("Compiled APF span has an invalid writer kind")
        if not isinstance(self.writer_schema, str) or not self.writer_schema:
            raise BuildError("Compiled APF span has an invalid writer schema")
        if type(self.reparse_owner) is not bool:
            raise BuildError("Compiled APF span has an invalid reparse policy")
        if self.source_span_sha256 is not None and (
            not isinstance(self.source_span_sha256, str)
            or len(self.source_span_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.source_span_sha256
            )
        ):
            raise BuildError("Compiled APF span has an invalid source guard")
        if self.kind == AUDO_EXACT_SLOT_KIND and (
            self.writer_schema != AUDO_EXACT_SLOT_WRITER_SCHEMA
            or self.source_span_sha256 is None
        ):
            raise BuildError("Compiled exact-slot audio span lost its source guard")
        if self.kind == AUSB_EXACT_SLOT_KIND and (
            self.writer_schema != AUSB_EXACT_SLOT_WRITER_SCHEMA
            or self.source_span_sha256 is None
            or self.reparse_owner
        ):
            raise BuildError("Compiled AUSB exact-slot span lost its safety contract")

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def label(self) -> str:
        return ", ".join(self.asset_ids)


def _noop(_stage: str, _completed: int, _total: int) -> None:
    return None


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_build_space(parent: Path) -> None:
    """Refuse before staging when a complete APF game folder cannot fit."""

    required = sum(size for size, _digest in EXPECTED_TREE.values())
    required += BUILD_SPACE_MARGIN
    try:
        free = shutil.disk_usage(parent).free
    except OSError as exc:
        raise BuildError(
            "APF Mod Studio could not check free space in the selected output "
            f"folder. Choose another local folder and try again ({exc})."
        ) from exc
    if free >= required:
        return
    shortfall = required - free
    if shortfall >= 1024**3:
        unit = 1024**3
        suffix = "GiB"
    elif shortfall >= 1024**2:
        unit = 1024**2
        suffix = "MiB"
    elif shortfall >= 1024:
        unit = 1024
        suffix = "KiB"
    else:
        shortfall_text = f"{shortfall} byte{'s' if shortfall != 1 else ''}"
        unit = 0
        suffix = ""
    if unit:
        # This is an instruction, so round upward: freeing the displayed amount
        # must be sufficient even when the exact shortage is between hundredths.
        hundredths = (shortfall * 100 + unit - 1) // unit
        shortfall_text = f"{hundredths / 100:.2f} {suffix}"
    raise BuildError(
        "The selected drive does not have enough free space for a safe APF "
        f"build. It has {free / 1024**3:.2f} GiB free; this build needs at "
        f"least {required / 1024**3:.2f} GiB. Free another {shortfall_text} "
        "or choose a different drive. No "
        "output was created."
    )


def _copy_regular(
    source: Path,
    destination: Path,
    progress: Progress,
    completed_before: int,
    total: int,
) -> int:
    supplied = source.lstat()
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise BuildError(f"Source game file is not a regular file: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        destination_fd = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            stat.S_IMODE(supplied.st_mode),
        )
    except BaseException:
        os.close(source_fd)
        raise
    copied = 0
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            supplied.st_dev,
            supplied.st_ino,
            supplied.st_size,
        ):
            raise BuildError(f"Source identity changed while opening {source.name}")
        cloned = try_reflink(destination_fd, source_fd)
        if cloned:
            copied = opened.st_size
            progress("Copying a safe, separate game folder", completed_before + copied, total)
        if not cloned:
            os.ftruncate(destination_fd, 0)
            os.lseek(source_fd, 0, os.SEEK_SET)
            os.lseek(destination_fd, 0, os.SEEK_SET)
            while copied < opened.st_size:
                count = min(16 * 1024 * 1024, opened.st_size - copied)
                try:
                    written = platform_compat.copy_file_range(
                        source_fd, destination_fd, count
                    )
                except OSError as exc:
                    if exc.errno not in {errno.EXDEV, errno.EINVAL, errno.ENOSYS}:
                        raise
                    data = os.read(source_fd, count)
                    if not data:
                        break
                    view = memoryview(data)
                    written = 0
                    while view:
                        amount = os.write(destination_fd, view)
                        if amount <= 0:
                            raise BuildError("Short write while copying game data")
                        view = view[amount:]
                        written += amount
                if written <= 0:
                    raise BuildError(f"Short copy while publishing {source.name}")
                copied += written
                progress(
                    "Copying a safe, separate game folder",
                    completed_before + copied,
                    total,
                )
        platform_compat.fchmod(destination_fd, stat.S_IMODE(supplied.st_mode), path=destination)
        os.fsync(destination_fd)
        after_source = os.fstat(source_fd)
        after_destination = os.fstat(destination_fd)
        if (after_source.st_dev, after_source.st_ino, after_source.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise BuildError(f"Source changed while copying {source.name}")
        if after_destination.st_size != opened.st_size:
            raise BuildError(f"Copied {source.name} has the wrong size")
        if (after_destination.st_dev, after_destination.st_ino) == (
            after_source.st_dev,
            after_source.st_ino,
        ):
            raise BuildError("Output unexpectedly aliases the source inode")
    finally:
        os.close(destination_fd)
        os.close(source_fd)
    return copied


def _publish_directory_noreplace(staging: Path, destination: Path) -> None:
    """Publish the staged build folder to its final name, never overwriting one.

    This is the path-based (``AT_FDCWD``) folder publisher.  The OS-primitive
    layer lives in :mod:`platform_compat`: Linux keeps
    ``renameat2(RENAME_NOREPLACE)`` byte-for-byte; macOS uses
    ``renameatx_np(RENAME_EXCL)``, its atomic exclusive directory rename; a POSIX
    kernel or volume with neither reserves the destination with ``os.mkdir``
    (atomic; refuses an existing name) and ``os.rename``\\ s the staged folder
    onto that placeholder; Windows uses its own ``os.rename``, which natively
    refuses to overwrite an existing destination.  A destination that already
    exists raises :class:`FileExistsError`, exactly as before.

    Only the ``os.mkdir``-reserve fallback is not a single atomic no-clobber
    step, and it is the one mechanism this function refuses to accept: a build
    output must never be able to land on top of a directory another process
    created, so a publish reporting ``atomic_no_clobber=False`` raises
    :class:`BuildError` instead of returning, and no receipt is produced.
    """

    try:
        published = platform_compat.publish_no_replace(
            staging, destination, dir_fd=None, is_directory=True
        )
    except FileExistsError as exc:
        raise FileExistsError(destination) from exc
    except platform_compat.NoReplacePublishUnavailable as exc:
        raise BuildError(
            "This system does not provide atomic no-replace folder publishing"
        ) from exc
    if not published.atomic_no_clobber:
        # platform_compat had to fall back to reserve-then-rename, which is two
        # steps: a same-user racer that replaced the reserved placeholder between
        # them would have had its directory overwritten by the swap.  The staged
        # folder is at `destination` by the time we can see that -- there is no
        # mechanism here that could have asked first -- so the only fail-closed
        # move left is to refuse the build rather than hand back a receipt whose
        # "published_atomically" is not true.  It is deliberately NOT rolled
        # back: deleting or renaming `destination` now would act on a name whose
        # ownership is precisely what could not be established.
        raise BuildError(
            "This system published the build folder without an atomic "
            f"no-replace guarantee (mechanism {published.mechanism}): "
            f"{destination} now exists but Mod Studio cannot prove the publish "
            "did not replace a folder another process created at the same "
            "instant. That folder is not a completed build and its manifest's "
            "published_atomically flag was written before the publish, so do "
            "not trust it: inspect the folder and remove it, then build to a "
            "destination on a filesystem that supports atomic no-replace folder "
            "publishing."
        )


class ApfBuildService:
    def __init__(self, source: ApfSource):
        self.source = source
        self._audo_source_fingerprints: (
            apf_audo_exact_slot.SourceAudioFingerprints | None
        ) = None
        self._ausb_source_fingerprints: (
            apf_audo_exact_slot.SourceAudioFingerprints | None
        ) = None

    def _protected_audo_fingerprints(
        self,
    ) -> apf_audo_exact_slot.SourceAudioFingerprints:
        if self._audo_source_fingerprints is None:
            try:
                self._audo_source_fingerprints = (
                    apf_audo_exact_slot.original_audio_fingerprints(
                        self.source.index_0a
                    )
                )
            except apf_audo_exact_slot.ExactSlotImportError as exc:
                raise BuildError(
                    f"Could not protect source AUDO packets during build: {exc}"
                ) from exc
        return self._audo_source_fingerprints

    def _protected_ausb_fingerprints(
        self,
    ) -> apf_audo_exact_slot.SourceAudioFingerprints:
        if self._ausb_source_fingerprints is None:
            try:
                self._ausb_source_fingerprints = (
                    apf_ausb_exact_slot.original_audio_fingerprints(
                        self.source.index_0a
                    )
                )
            except apf_ausb_exact_slot.AusbExactSlotError as exc:
                raise BuildError(
                    f"Could not protect source AUSB packets during build: {exc}"
                ) from exc
        return self._ausb_source_fingerprints

    def _reject_any_source_audio_reuse(self, payload: bytes) -> None:
        """Fail closed if a build payload copies either source-audio family."""

        try:
            apf_audo_exact_slot.reject_source_audio_reuse(
                payload,
                self._protected_audo_fingerprints(),
            )
            apf_ausb_exact_slot.reject_source_audio_reuse(
                payload,
                self._protected_ausb_fingerprints(),
            )
        except (
            apf_audo_exact_slot.ExactSlotImportError,
            apf_ausb_exact_slot.AusbExactSlotError,
        ) as exc:
            raise BuildError(str(exc)) from exc

    def build(
        self,
        modifications: Iterable[Modification],
        output_game: Path,
        progress: Progress = _noop,
    ) -> BuildReceipt:
        output_game = output_game.expanduser().absolute().resolve(strict=False)
        source_root = self.source.game_root.resolve(strict=True)
        if output_game == source_root or output_game.is_relative_to(source_root):
            raise BuildError(
                "Choose an output folder outside the untouched source game folder"
            )
        if output_game.exists():
            raise FileExistsError(
                f"Choose a new output folder; this already exists: {output_game}"
            )
        output_game.parent.mkdir(parents=True, exist_ok=True)
        _require_build_space(output_game.parent)
        source_before = sha256_file(
            self.source.index_0a, progress, stage="Confirming untouched source"
        )
        if source_before != EXPECTED_0A_SHA256:
            raise BuildError("The source 0A changed after it was loaded")
        edits = tuple(sorted(modifications, key=lambda item: item.asset_id))
        if len({item.asset_id for item in edits}) != len(edits):
            raise BuildError("The same APF asset was selected more than once")
        progress("Compiling mod edits", 0, max(1, len(edits)))
        compiled: dict[int, tuple[bytes, dict[str, object]]] = {}
        raw_overlays: list[_CompiledBuildSpan] = []
        edit_rows: list[dict[str, object]] = []
        localization_groups: dict[int, list[Modification]] = {}
        roster_identity_group: list[Modification] = []
        player_rating_group: list[Modification] = []
        player_position_group: list[Modification] = []
        audo_overlay_group: list[Modification] = []
        ausb_overlay_group: list[Modification] = []
        replacement_hashes: dict[str, str] = {}
        for index, modification in enumerate(edits, start=1):
            try:
                replacement_before = sha256_file(
                    modification.replacement_path,
                    stage=f"Checking replacement {modification.asset_id}",
                )
            except (OSError, ValueError) as exc:
                raise BuildError(
                    f"Could not read replacement for {modification.asset_id}: {exc}"
                ) from exc
            if replacement_before != modification.replacement_sha256:
                raise BuildError(
                    f"Replacement changed after import: {modification.asset_id}"
                )
            replacement_hashes[modification.asset_id] = replacement_before
            if modification.kind == "localization_text":
                try:
                    outer_index, _inner_index, _pool_index = (
                        apf_txt_loc_patch.parse_asset_id(modification.asset_id)
                    )
                except apf_txt_loc_patch.TextPatchError as exc:
                    raise BuildError(str(exc)) from exc
                localization_groups.setdefault(outer_index, []).append(modification)
            elif modification.kind == "roster_identity_text":
                roster_identity_group.append(modification)
            elif modification.kind == "player_base_rating":
                player_rating_group.append(modification)
            elif modification.kind == "player_position":
                player_position_group.append(modification)
            elif modification.kind == AUDO_EXACT_SLOT_KIND:
                audo_overlay_group.append(modification)
            elif modification.kind == AUSB_EXACT_SLOT_KIND:
                ausb_overlay_group.append(modification)
            else:
                outer_index, entry_bytes, writer_schema = self._compile(modification)
                if outer_index in compiled:
                    raise BuildError(
                        f"Two edits resolve to the same APF outer entry {outer_index}"
                    )
                compiled[outer_index] = (
                    entry_bytes,
                    {
                        "asset_id": modification.asset_id,
                        "kind": modification.kind,
                        "outer_index": outer_index,
                        "replacement_png_sha256": modification.replacement_sha256,
                        "entry_size": len(entry_bytes),
                        "entry_sha256": _hash_bytes(entry_bytes),
                        "writer_schema": writer_schema,
                    },
                )
                edit_rows.append(compiled[outer_index][1])
            progress("Compiling mod edits", index, max(1, len(edits)))
        if audo_overlay_group:
            coordinates = tuple(
                self._audo_coordinates(modification)
                for modification in audo_overlay_group
            )
            try:
                resolved_targets = apf_audo_exact_slot.resolve_targets(
                    self.source.index_0a, coordinates
                )
            except apf_audo_exact_slot.ExactSlotImportError as exc:
                raise BuildError(
                    f"Could not resolve exact-slot audio targets: {exc}"
                ) from exc
            for modification, coordinates_key in zip(
                audo_overlay_group, coordinates
            ):
                resolved = resolved_targets.get(coordinates_key)
                if resolved is None:
                    raise BuildError(
                        "Exact-slot audio batch resolver omitted "
                        f"{modification.asset_id}"
                    )
                overlay, row = self._compile_audo_exact_slot_overlay(
                    modification, resolved
                )
                raw_overlays.append(overlay)
                edit_rows.append(row)
        if ausb_overlay_group:
            overlays, rows = self._compile_ausb_exact_slot_overlays(
                tuple(ausb_overlay_group)
            )
            raw_overlays.extend(overlays)
            edit_rows.extend(rows)
        for outer_index, group in sorted(localization_groups.items()):
            if outer_index in compiled:
                raise BuildError(
                    f"Text edits collide with another APF outer entry {outer_index} edit"
                )
            replacements: dict[int, str] = {}
            for modification in group:
                try:
                    parsed_outer, parsed_inner, pool_index = (
                        apf_txt_loc_patch.parse_asset_id(modification.asset_id)
                    )
                    text = decode_text_payload(
                        modification.replacement_path.read_bytes(),
                        modification.asset_id,
                    )
                except (OSError, ProjectError, apf_txt_loc_patch.TextPatchError) as exc:
                    raise BuildError(
                        f"Could not read text replacement {modification.asset_id}: {exc}"
                    ) from exc
                if pool_index in replacements:
                    raise BuildError(
                        f"Text pool allocation {pool_index} was edited twice"
                    )
                expected_name = apf_txt_loc_patch.TABLE_TARGETS.get(parsed_outer)
                metadata = modification.metadata
                if (
                    parsed_outer != outer_index
                    or expected_name is None
                    or parsed_inner != expected_name[0]
                    or metadata.get("outer_index") != parsed_outer
                    or metadata.get("inner_index") != parsed_inner
                    or metadata.get("pool_index") != pool_index
                    or metadata.get("table_name") != expected_name[1]
                ):
                    raise BuildError(
                        f"Text target metadata changed: {modification.asset_id}"
                    )
                replacements[pool_index] = text
            try:
                result = apf_txt_loc_patch.build_table_patch(
                    self.source.index_0a,
                    outer_index,
                    replacements,
                )
            except apf_txt_loc_patch.TextPatchError as exc:
                raise BuildError(f"Could not compile APF text edits: {exc}") from exc
            receipt_rows = {
                str(row["asset_id"]): row
                for row in result.manifest.get("edits", ())
                if isinstance(row, dict) and "asset_id" in row
            }
            for modification in group:
                receipt = receipt_rows.get(modification.asset_id)
                if receipt is None or any(
                    modification.metadata.get(key) != receipt.get(key)
                    for key in (
                        "pool_index",
                        "reference_count",
                        "maximum_utf16_units",
                    )
                ):
                    raise BuildError(
                        f"Text allocation changed: {modification.asset_id}"
                    )
            row = {
                "asset_ids": tuple(item.asset_id for item in group),
                "kind": "localization_text_batch",
                "outer_index": outer_index,
                "replacement_payload_sha256s": {
                    item.asset_id: item.replacement_sha256 for item in group
                },
                "entry_size": len(result.entry_bytes),
                "entry_sha256": _hash_bytes(result.entry_bytes),
                "writer_schema": str(result.manifest.get("schema")),
                "writer_mode": str(result.manifest.get("mode")),
            }
            compiled[outer_index] = (result.entry_bytes, row)
            edit_rows.append(row)
        roster_group_count = sum(
            bool(group)
            for group in (
                roster_identity_group,
                player_rating_group,
                player_position_group,
            )
        )
        if roster_group_count >= 2:
            result, row = self._compile_roster_composite_groups(
                tuple(roster_identity_group),
                tuple(player_rating_group),
                tuple(player_position_group),
            )
            outer_index = result.outer_index
            if outer_index in compiled:
                raise BuildError(
                    f"Combined ROST edits collide with another APF outer entry {outer_index} edit"
                )
            compiled[outer_index] = (result.entry_bytes, row)
            edit_rows.append(row)
        elif roster_identity_group:
            result, row = self._compile_roster_identity_group(
                tuple(roster_identity_group)
            )
            outer_index = result.outer_index
            if outer_index in compiled:
                raise BuildError(
                    f"Roster-name edits collide with another APF outer entry {outer_index} edit"
                )
            compiled[outer_index] = (result.entry_bytes, row)
            edit_rows.append(row)
        elif player_rating_group:
            result, row = self._compile_player_rating_group(
                tuple(player_rating_group)
            )
            outer_index = result.outer_index
            if outer_index in compiled:
                raise BuildError(
                    f"Player-rating edits collide with another APF outer entry {outer_index} edit"
                )
            compiled[outer_index] = (result.entry_bytes, row)
            edit_rows.append(row)
        elif player_position_group:
            result, row = self._compile_player_position_group(
                tuple(player_position_group)
            )
            outer_index = result.outer_index
            if outer_index in compiled:
                raise BuildError(
                    f"Player-position edits collide with another APF outer entry {outer_index} edit"
                )
            compiled[outer_index] = (result.entry_bytes, row)
            edit_rows.append(row)
        for modification in edits:
            try:
                replacement_after = sha256_file(
                    modification.replacement_path,
                    stage=f"Rechecking replacement {modification.asset_id}",
                )
            except (OSError, ValueError) as exc:
                raise BuildError(
                    f"Could not recheck replacement for {modification.asset_id}: {exc}"
                ) from exc
            if replacement_after != replacement_hashes[modification.asset_id]:
                raise BuildError(
                    f"Replacement changed while compiling: {modification.asset_id}"
                )
        if not edits:
            progress("Compiling mod edits", 1, 1)
        try:
            source_archive = apf_outer.parse_archive(self.source.index_0a)
        except apf_outer.FormatError as exc:
            raise BuildError(f"Could not map the APF source archive: {exc}") from exc
        spans: list[_CompiledBuildSpan] = list(raw_overlays)
        for outer_index, (entry_bytes, _row) in compiled.items():
            try:
                entry = source_archive.entries[outer_index]
            except IndexError as exc:
                raise BuildError(f"Compiled edit targets missing outer {outer_index}") from exc
            if (
                len(entry.segments) != 1
                or entry.segments[0].pack_name != "0A"
                or len(entry_bytes) != entry.size
            ):
                raise BuildError(
                    f"Outer {outer_index} is not one fixed-size 0A allocation"
                )
            row = compiled[outer_index][1]
            row_asset_ids = row.get("asset_ids")
            if isinstance(row_asset_ids, (tuple, list)):
                asset_ids = tuple(str(value) for value in row_asset_ids)
            else:
                row_asset_id = row.get("asset_id")
                if not isinstance(row_asset_id, str):
                    raise BuildError(
                        f"Compiled outer {outer_index} lost its asset identity"
                    )
                asset_ids = (row_asset_id,)
            spans.append(
                _CompiledBuildSpan(
                    pack_name="0A",
                    offset=entry.segments[0].pack_offset,
                    data=entry_bytes,
                    outer_index=outer_index,
                    asset_ids=asset_ids,
                    kind=str(row.get("kind", "whole_outer_entry")),
                    writer_schema=str(row.get("writer_schema", "unknown")),
                    reparse_owner=True,
                )
            )
        spans = self._normalize_compiled_spans(spans)
        changed_pack_names = tuple(sorted({span.pack_name for span in spans}))
        source_pack_hashes_before = {"0A": source_before}
        for pack_name in changed_pack_names:
            if pack_name == "0A":
                continue
            source_pack = self.source.game_root / pack_name
            source_pack_hash = sha256_file(
                source_pack,
                progress,
                stage=f"Confirming untouched source {pack_name}",
            )
            if source_pack_hash != EXPECTED_TREE[pack_name][1]:
                raise BuildError(
                    f"The source {pack_name} changed after it was loaded"
                )
            source_pack_hashes_before[pack_name] = source_pack_hash
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{output_game.name}.building-", dir=output_game.parent
            )
        )
        try:
            total = sum(size for size, _digest in EXPECTED_TREE.values())
            completed = 0
            for relative, (expected_size, expected_hash) in EXPECTED_TREE.items():
                source_path = self.source.game_root / relative
                if source_path.stat().st_size != expected_size:
                    raise BuildError(f"Source game file changed size: {relative}")
                copied = _copy_regular(
                    source_path,
                    staging / relative,
                    progress,
                    completed,
                    total,
                )
                if copied != expected_size:
                    raise BuildError(f"Did not copy all bytes of {relative}")
                completed += copied
            output_0a = staging / "0A"
            self._apply_compiled_spans(staging, spans, progress)
            output_sha = self._verify_composed(staging, spans, progress)
            source_after = sha256_file(
                self.source.index_0a,
                progress,
                stage="Confirming source remained untouched",
            )
            if source_after != source_before:
                raise BuildError("The source changed during the build")
            for pack_name, source_pack_hash_before in source_pack_hashes_before.items():
                if pack_name == "0A":
                    continue
                source_pack_hash_after = sha256_file(
                    self.source.game_root / pack_name,
                    progress,
                    stage=f"Confirming source {pack_name} remained untouched",
                )
                if source_pack_hash_after != source_pack_hash_before:
                    raise BuildError(
                        f"The source {pack_name} changed during the build"
                    )
            manifest_document = {
                "schema": BUILD_SCHEMA,
                "game": "apf2k8_xbox360",
                "mode": "modded" if edits else "clean_copy",
                "source": {
                    "0a_sha256_before": source_before,
                    "0a_sha256_after": source_after,
                    "opened_read_only": True,
                    "source_modified": False,
                },
                "output": {
                    "type": "complete_extracted_game_directory",
                    "launch_file": "default.xex",
                    "0a_size": output_0a.stat().st_size,
                    "0a_sha256": output_sha,
                    # Written into the staging folder before the publish, so it
                    # is a claim about something that has not happened yet.  It
                    # is true of every build this service completes, because
                    # _publish_directory_noreplace accepts only a single atomic
                    # no-clobber mechanism and raises BuildError on any other --
                    # so no BuildReceipt is ever returned for a folder published
                    # some weaker way.  The one case where this line can be read
                    # off a folder it is not true of is that BuildError itself:
                    # the fallback publish has already put the staged folder in
                    # place by the time its mechanism is visible, and it is not
                    # rolled back, so the error names that folder and says to
                    # remove it rather than trust the manifest inside it.
                    "published_atomically": True,
                },
                "edit_count": len(edits),
                "compiled_entry_count": len(compiled),
                "compiled_span_count": len(spans),
                "compiled_raw_overlay_count": len(raw_overlays),
                "compiled_span_packs": changed_pack_names,
                "edits": edit_rows,
                "verification": {
                    "all_bytes_outside_changed_outer_entries_identical": True,
                    "all_bytes_outside_compiled_spans_identical": True,
                    "all_changed_pack_bytes_outside_compiled_spans_identical": True,
                    "all_compiled_spans_match_exactly": True,
                    "all_changed_entries_reparsed": all(
                        span.reparse_owner for span in spans
                    ),
                    "all_applicable_changed_entries_reparsed": True,
                    "all_unchanged_packs_match_retail": True,
                    "all_unchanged_sibling_files_match_retail": True,
                    "source_and_output_are_distinct_inodes": True,
                },
                "distribution": {
                    "build_contains_user_owned_retail_data": True,
                    "build_must_not_be_redistributed": True,
                    "share_the_apf2k8mod_project_instead": True,
                },
            }
            manifest_stage = staging / ".apf2k8-mod-studio-build.json"
            with manifest_stage.open("xb") as stream:
                stream.write(
                    (json.dumps(manifest_document, indent=2, sort_keys=True) + "\n").encode(
                        "utf-8"
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            _publish_directory_noreplace(staging, output_game)
            final_manifest = output_game / manifest_stage.name
            return BuildReceipt(
                output_game=output_game,
                output_0a=output_game / "0A",
                manifest=final_manifest,
                modified_assets=tuple(item.asset_id for item in edits),
                changed_outer_entries=tuple(
                    sorted(
                        {
                            item.outer_index
                            for item in spans
                            if item.reparse_owner
                        }
                    )
                ),
                output_0a_sha256=output_sha,
                source_unchanged=True,
            )
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _normalize_compiled_spans(
        spans: Iterable[_CompiledBuildSpan],
    ) -> list[_CompiledBuildSpan]:
        """Sort typed spans and reject collisions within each physical pack."""

        ordered = sorted(
            spans,
            key=lambda item: (
                item.pack_name,
                item.offset,
                item.end,
                item.label,
            ),
        )
        previous_by_pack: dict[str, _CompiledBuildSpan] = {}
        for current in ordered:
            previous = previous_by_pack.get(current.pack_name)
            if previous is not None and previous.end > current.offset:
                raise BuildError(
                    "Compiled APF edit spans overlap in "
                    f"{current.pack_name}: {previous.label} and {current.label}"
                )
            previous_by_pack[current.pack_name] = current
        return ordered

    @staticmethod
    def _apply_compiled_spans(
        output_root: Path,
        spans: Iterable[_CompiledBuildSpan],
        progress: Progress = _noop,
    ) -> None:
        """Apply already-normalized spans to their staged physical packs."""

        ordered = ApfBuildService._normalize_compiled_spans(spans)
        spans_by_pack: dict[str, list[_CompiledBuildSpan]] = {}
        for span in ordered:
            spans_by_pack.setdefault(span.pack_name, []).append(span)
        completed = 0
        for pack_name, pack_spans in sorted(spans_by_pack.items()):
            output_pack = output_root / pack_name
            descriptor = os.open(
                output_pack,
                os.O_RDWR
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            )
            try:
                pack_size = os.fstat(descriptor).st_size
                for span in pack_spans:
                    if span.end > pack_size:
                        raise BuildError(
                            f"Compiled {pack_name} span exceeds its pack: "
                            f"{span.label}"
                        )
                for span in pack_spans:
                    progress("Applying compiled APF edits", completed, len(ordered))
                    cursor = 0
                    while cursor < span.size:
                        written = platform_compat.pwrite(
                            descriptor,
                            span.data[cursor:],
                            span.offset + cursor,
                        )
                        if written <= 0:
                            raise BuildError(f"Short write for {span.label}")
                        cursor += written
                    completed += 1
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _compile_audo_exact_slot_overlay(
        self,
        modification: Modification,
        resolved: apf_audo_exact_slot.ResolvedExactSlot,
    ) -> tuple[_CompiledBuildSpan, dict[str, object]]:
        """Resolve and compile one source-bound standalone AUDO packet slot.

        The project payload is not a generic binary patch.  Its logical
        outer/inner identity is resolved again against the untouched source;
        the owning SRAM block must be physically uncompressed in 0A; source
        shape metadata must match the project target; and the stored packets
        pass the dedicated XMA1 validator before this method returns a span.
        """

        if modification.kind != AUDO_EXACT_SLOT_KIND:
            raise BuildError(
                f"Unsupported raw overlay kind: {modification.kind}"
            )
        outer_index, inner_index = self._audo_coordinates(modification)
        metadata = modification.metadata
        if (
            metadata.get("outer_table_index") != outer_index
            or metadata.get("inner_file_index") != inner_index
            or metadata.get("writer_schema") != AUDO_EXACT_SLOT_WRITER_SCHEMA
        ):
            raise BuildError(
                f"Exact-slot audio target metadata changed: {modification.asset_id}"
            )
        if (
            resolved.asset_id != modification.asset_id
            or resolved.outer_index != outer_index
            or resolved.inner_index != inner_index
            or resolved.pack_name != "0A"
            or resolved.pack_offset < 0
            or resolved.encoded_size != resolved.target.encoded_size
        ):
            raise BuildError(
                f"Exact-slot audio source identity changed: {modification.asset_id}"
            )
        expected_metadata = {
            "encoded_size": resolved.target.encoded_size,
            "sample_rate": resolved.target.sample_rate,
            "channel_count": resolved.target.channels,
            "declared_sample_count": resolved.target.declared_sample_count,
            "packet_count": resolved.target.encoded_size // 0x800,
        }
        if any(
            type(value) is not int
            or modification.metadata.get(key) != value
            for key, value in expected_metadata.items()
        ):
            raise BuildError(
                f"Exact-slot audio source shape changed: {modification.asset_id}"
            )
        try:
            replacement_data = modification.replacement_path.read_bytes()
            replacement_payload = apf_audo_exact_slot.validate_stored_payload(
                replacement_data, resolved.target
            )
        except (OSError, apf_audo_exact_slot.ExactSlotImportError) as exc:
            raise BuildError(
                f"Could not compile exact-slot audio replacement "
                f"{modification.asset_id}: {exc}"
            ) from exc
        self._reject_any_source_audio_reuse(replacement_payload)
        if (
            len(replacement_payload) != resolved.encoded_size
            or _hash_bytes(replacement_payload)
            != modification.replacement_sha256
        ):
            raise BuildError(
                f"Exact-slot audio replacement changed: {modification.asset_id}"
            )
        overlay = _CompiledBuildSpan(
            pack_name=resolved.pack_name,
            offset=resolved.pack_offset,
            data=replacement_payload,
            outer_index=outer_index,
            asset_ids=(modification.asset_id,),
            kind=AUDO_EXACT_SLOT_KIND,
            writer_schema=AUDO_EXACT_SLOT_WRITER_SCHEMA,
            source_span_sha256=resolved.source_payload_sha256,
            reparse_owner=True,
        )
        row: dict[str, object] = {
            "asset_id": modification.asset_id,
            "kind": AUDO_EXACT_SLOT_KIND,
            "outer_index": outer_index,
            "inner_index": inner_index,
            "pack_name": resolved.pack_name,
            "pack_offset": resolved.pack_offset,
            "span_size": overlay.size,
            "source_span_sha256": resolved.source_payload_sha256,
            "replacement_payload_sha256": modification.replacement_sha256,
            "writer_schema": AUDO_EXACT_SLOT_WRITER_SCHEMA,
            "writer_mode": "source_bound_exact_slot_raw_overlay",
            "target": expected_metadata,
            "retail_bytes_embedded_in_receipt": False,
        }
        return overlay, row

    def _compile_ausb_exact_slot_overlays(
        self,
        modifications: tuple[Modification, ...],
    ) -> tuple[list[_CompiledBuildSpan], list[dict[str, object]]]:
        """Compile one semantic AUSB batch into deduplicated physical writes.

        AUSB descriptor rows can alias one canonical external-bank range and a
        single range can cross a pack boundary.  Resolve the complete semantic
        batch against the untouched source, validate every project target,
        compile with the dedicated writer, then merge only byte-identical
        aliases.  Physical coordinates and source hashes remain private build
        state and are never copied into a semantic manifest edit row.
        """

        coordinates = tuple(
            self._ausb_coordinates(modification)
            for modification in modifications
        )
        try:
            resolved_targets = apf_ausb_exact_slot.resolve_targets(
                self.source.index_0a, coordinates
            )
            source_payload_hashes = (
                self._protected_ausb_fingerprints().payload_sha256s
            )
        except apf_ausb_exact_slot.AusbExactSlotError as exc:
            raise BuildError(
                f"Could not resolve source-bound AUSB audio targets: {exc}"
            ) from exc

        write_groups: list[tuple[apf_ausb_exact_slot.CompiledAusbWrite, ...]] = []
        rows: list[dict[str, object]] = []
        contributors: dict[
            tuple[str, int, int, str, int], list[str]
        ] = {}
        source_guards: dict[
            tuple[str, int, int, str, int], str
        ] = {}
        external_owners: dict[
            tuple[str, int, int, str, int], int
        ] = {}
        canonical_guards: dict[
            str,
            tuple[
                tuple[tuple[str, int, int, int], ...],
                str,
                dict[tuple[str, int, int, int], str],
            ],
        ] = {}

        for modification, coordinate in zip(modifications, coordinates):
            resolved = resolved_targets.get(coordinate)
            if resolved is None:
                raise BuildError(
                    "AUSB exact-slot batch resolver omitted "
                    f"{modification.asset_id}"
                )
            owner_asset_ids, owner_fingerprint, target_row = (
                self._validate_ausb_exact_slot_target(
                    modification, coordinate, resolved
                )
            )
            physical_signature = tuple(
                (
                    span.pack_name,
                    span.pack_offset,
                    span.length,
                    span.payload_offset,
                )
                for span in resolved.physical_spans
            )
            cached = canonical_guards.get(resolved.canonical_physical_id)
            if cached is None:
                guards = self._source_ausb_span_guards(resolved)
                canonical_guards[resolved.canonical_physical_id] = (
                    physical_signature,
                    resolved.source_payload_sha256,
                    guards,
                )
            else:
                cached_signature, cached_source_hash, guards = cached
                if (
                    cached_signature != physical_signature
                    or cached_source_hash != resolved.source_payload_sha256
                ):
                    raise BuildError(
                        "AUSB alias source identity changed: "
                        f"{modification.asset_id}"
                    )

            try:
                replacement_data = modification.replacement_path.read_bytes()
                self._reject_any_source_audio_reuse(replacement_data)
                writes = apf_ausb_exact_slot.compile_physical_writes(
                    replacement_data,
                    resolved,
                    source_payload_hashes,
                )
            except (OSError, apf_ausb_exact_slot.AusbExactSlotError) as exc:
                raise BuildError(
                    "Could not compile AUSB exact-slot replacement "
                    f"{modification.asset_id}: {exc}"
                ) from exc
            if _hash_bytes(replacement_data) != modification.replacement_sha256:
                raise BuildError(
                    f"AUSB exact-slot replacement changed: {modification.asset_id}"
                )
            if len(writes) != len(resolved.physical_spans):
                raise BuildError(
                    f"AUSB exact-slot compiler changed its span plan: "
                    f"{modification.asset_id}"
                )

            for write, physical_span in zip(writes, resolved.physical_spans):
                if (
                    not isinstance(write, apf_ausb_exact_slot.CompiledAusbWrite)
                    or write.pack_name != physical_span.pack_name
                    or write.pack_offset != physical_span.pack_offset
                    or write.length != physical_span.length
                    or write.side_payload_offset != physical_span.payload_offset
                    or write.canonical_physical_id
                    != resolved.canonical_physical_id
                    or write.payload
                    != replacement_data[
                        physical_span.payload_offset :
                        physical_span.payload_offset + physical_span.length
                    ]
                ):
                    raise BuildError(
                        f"AUSB exact-slot compiler changed a physical span: "
                        f"{modification.asset_id}"
                    )
                identity = (
                    write.pack_name,
                    write.pack_offset,
                    write.length,
                    write.canonical_physical_id,
                    write.side_payload_offset,
                )
                guard_identity = (
                    physical_span.pack_name,
                    physical_span.pack_offset,
                    physical_span.length,
                    physical_span.payload_offset,
                )
                source_guard = guards.get(guard_identity)
                if source_guard is None:
                    raise BuildError(
                        f"AUSB exact-slot span lost its source guard: "
                        f"{modification.asset_id}"
                    )
                prior_guard = source_guards.setdefault(identity, source_guard)
                prior_owner = external_owners.setdefault(
                    identity, resolved.external_outer_index
                )
                if (
                    prior_guard != source_guard
                    or prior_owner != resolved.external_outer_index
                ):
                    raise BuildError(
                        f"AUSB alias source identity changed: "
                        f"{modification.asset_id}"
                    )
                contributors.setdefault(identity, []).append(
                    modification.asset_id
                )
            write_groups.append(writes)
            rows.append(
                {
                    "asset_id": modification.asset_id,
                    "kind": AUSB_EXACT_SLOT_KIND,
                    "replacement_payload_sha256": modification.replacement_sha256,
                    "writer_schema": AUSB_EXACT_SLOT_WRITER_SCHEMA,
                    "writer_mode": "source_bound_external_ausb_exact_slot_overlays",
                    "target": target_row,
                    "shared_effect": len(owner_asset_ids) > 1,
                    "shared_owner_asset_ids": owner_asset_ids,
                    "owner_fingerprint": owner_fingerprint,
                    "changed_pack_names": sorted(
                        {span.pack_name for span in resolved.physical_spans}
                    ),
                    "retail_bytes_embedded_in_receipt": False,
                    "physical_source_coordinates_embedded_in_receipt": False,
                }
            )

        try:
            merged_writes = apf_ausb_exact_slot.merge_compiled_writes(
                write_groups
            )
        except apf_ausb_exact_slot.AusbExactSlotError as exc:
            raise BuildError(f"Could not merge AUSB exact-slot edits: {exc}") from exc

        overlays: list[_CompiledBuildSpan] = []
        for write in merged_writes:
            identity = (
                write.pack_name,
                write.pack_offset,
                write.length,
                write.canonical_physical_id,
                write.side_payload_offset,
            )
            asset_ids = tuple(sorted(set(contributors.get(identity, ()))))
            source_guard = source_guards.get(identity)
            outer_index = external_owners.get(identity)
            if not asset_ids or source_guard is None or outer_index is None:
                raise BuildError("Merged AUSB exact-slot write lost its semantic owner")
            overlays.append(
                _CompiledBuildSpan(
                    pack_name=write.pack_name,
                    offset=write.pack_offset,
                    data=write.payload,
                    outer_index=outer_index,
                    asset_ids=asset_ids,
                    kind=AUSB_EXACT_SLOT_KIND,
                    writer_schema=AUSB_EXACT_SLOT_WRITER_SCHEMA,
                    source_span_sha256=source_guard,
                    reparse_owner=False,
                )
            )
        return overlays, rows

    @staticmethod
    def _validate_ausb_exact_slot_target(
        modification: Modification,
        coordinate: tuple[int, int, int],
        resolved: apf_ausb_exact_slot.ResolvedExactSlot,
    ) -> tuple[tuple[str, ...], str, dict[str, int]]:
        """Fail closed if project semantics no longer match the source target."""

        allowed_metadata = {
            "outer_table_index",
            "inner_file_index",
            "substream_index",
            "encoded_size",
            "sample_rate",
            "channel_count",
            "declared_sample_count",
            "packet_count",
            "shared_owner_asset_ids",
            "owner_fingerprint",
            "writer_schema",
        }
        if (
            modification.kind != AUSB_EXACT_SLOT_KIND
            or not isinstance(resolved, apf_ausb_exact_slot.ResolvedExactSlot)
            or set(modification.metadata) != allowed_metadata
        ):
            raise BuildError(
                f"AUSB exact-slot target metadata changed: {modification.asset_id}"
            )
        outer_index, inner_index, substream_index = coordinate
        requested = resolved.requested_owner
        owner_asset_ids = tuple(owner.asset_id for owner in resolved.owners)
        owner_fingerprint = hashlib.sha256(
            "\n".join(owner_asset_ids).encode("ascii")
        ).hexdigest()
        metadata = modification.metadata
        target = resolved.target
        target_row = {
            "encoded_size": target.encoded_size,
            "sample_rate": target.sample_rate,
            "channel_count": target.channels,
            "declared_sample_count": target.declared_sample_count,
            "packet_count": target.encoded_size // 0x800,
            "physical_span_count": len(resolved.physical_spans),
        }
        semantic_metadata = {
            "outer_table_index": outer_index,
            "inner_file_index": inner_index,
            "substream_index": substream_index,
            "encoded_size": target.encoded_size,
            "sample_rate": target.sample_rate,
            "channel_count": target.channels,
            "declared_sample_count": target.declared_sample_count,
            "packet_count": target.encoded_size // 0x800,
            "shared_owner_asset_ids": list(owner_asset_ids),
            "owner_fingerprint": owner_fingerprint,
            "writer_schema": AUSB_EXACT_SLOT_WRITER_SCHEMA,
        }
        if (
            resolved.asset_id != modification.asset_id
            or requested.asset_id != modification.asset_id
            or requested.coordinates != coordinate
            or not owner_asset_ids
            or len(set(owner_asset_ids)) != len(owner_asset_ids)
            or modification.asset_id not in owner_asset_ids
            or any(metadata.get(key) != value for key, value in semantic_metadata.items())
            or any(
                type(metadata.get(key)) is not int
                for key in (
                    "outer_table_index",
                    "inner_file_index",
                    "substream_index",
                    "encoded_size",
                    "sample_rate",
                    "channel_count",
                    "declared_sample_count",
                    "packet_count",
                )
            )
        ):
            raise BuildError(
                f"AUSB exact-slot target metadata changed: {modification.asset_id}"
            )
        if (
            not isinstance(resolved.canonical_physical_id, str)
            or not resolved.canonical_physical_id.startswith(
                "apf:audio:ausb:physical:"
            )
            or type(resolved.external_outer_index) is not int
            or resolved.external_outer_index < 0
            or type(resolved.external_range_offset) is not int
            or resolved.external_range_offset < 0
            or type(target.channels) is not int
            or target.channels not in (1, 2)
            or type(target.sample_rate) is not int
            or not 8_000 <= target.sample_rate <= 192_000
            or type(target.encoded_size) is not int
            or target.encoded_size <= 0
            or target.encoded_size % 0x800
            or type(target.declared_sample_count) is not int
            or target.declared_sample_count <= 0
            or requested.channels != target.channels
            or requested.sample_rate != target.sample_rate
            or requested.declared_sample_count != target.declared_sample_count
            or not isinstance(resolved.source_payload_sha256, str)
            or len(resolved.source_payload_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in resolved.source_payload_sha256
            )
        ):
            raise BuildError(
                f"AUSB exact-slot source identity changed: {modification.asset_id}"
            )
        payload_cursor = 0
        for span in resolved.physical_spans:
            if (
                not isinstance(span, apf_ausb_exact_slot.PhysicalSpan)
                or span.pack_name not in COMPILED_SPAN_PACKS
                or type(span.pack_offset) is not int
                or span.pack_offset < 0
                or type(span.length) is not int
                or span.length <= 0
                or type(span.payload_offset) is not int
                or span.payload_offset != payload_cursor
                or span.pack_offset + span.length
                > EXPECTED_TREE[span.pack_name][0]
            ):
                raise BuildError(
                    f"AUSB exact-slot physical layout changed: "
                    f"{modification.asset_id}"
                )
            payload_cursor += span.length
        if payload_cursor != target.encoded_size:
            raise BuildError(
                f"AUSB exact-slot physical layout changed: {modification.asset_id}"
            )
        return owner_asset_ids, owner_fingerprint, target_row

    def _source_ausb_span_guards(
        self,
        resolved: apf_ausb_exact_slot.ResolvedExactSlot,
    ) -> dict[tuple[str, int, int, int], str]:
        """Hash every source pack slice and the canonical payload in order."""

        whole_digest = hashlib.sha256()
        guards: dict[tuple[str, int, int, int], str] = {}
        for span in resolved.physical_spans:
            source_pack = self.source.game_root / span.pack_name
            try:
                descriptor = os.open(
                    source_pack,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
                )
            except OSError as exc:
                raise BuildError(
                    f"Could not open source AUSB pack {span.pack_name}: {exc}"
                ) from exc
            span_digest = hashlib.sha256()
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or span.pack_offset + span.length > opened.st_size
                ):
                    raise BuildError(
                        f"AUSB source span leaves pack {span.pack_name}"
                    )
                cursor = 0
                while cursor < span.length:
                    count = min(8 * 1024 * 1024, span.length - cursor)
                    data = platform_compat.pread(
                        descriptor,
                        count,
                        span.pack_offset + cursor,
                    )
                    if not data:
                        raise BuildError(
                            f"Could not read source AUSB span in {span.pack_name}"
                        )
                    span_digest.update(data)
                    whole_digest.update(data)
                    cursor += len(data)
            finally:
                os.close(descriptor)
            identity = (
                span.pack_name,
                span.pack_offset,
                span.length,
                span.payload_offset,
            )
            if identity in guards:
                raise BuildError("AUSB source target repeats a physical span")
            guards[identity] = span_digest.hexdigest()
        if whole_digest.hexdigest() != resolved.source_payload_sha256:
            raise BuildError(
                f"AUSB source payload changed for {resolved.asset_id}"
            )
        return guards

    @staticmethod
    def _audo_coordinates(modification: Modification) -> tuple[int, int]:
        fields = modification.asset_id.split(":")
        try:
            outer_index = int(fields[3])
            inner_index = int(fields[4])
        except (IndexError, ValueError) as exc:
            raise BuildError(
                f"Invalid exact-slot audio target: {modification.asset_id}"
            ) from exc
        if (
            len(fields) != 5
            or fields[:3] != ["apf", "audio", "audo"]
            or outer_index < 0
            or inner_index < 0
        ):
            raise BuildError(
                f"Invalid exact-slot audio target: {modification.asset_id}"
            )
        return outer_index, inner_index

    @staticmethod
    def _ausb_coordinates(modification: Modification) -> tuple[int, int, int]:
        fields = modification.asset_id.split(":")
        try:
            outer_index = int(fields[3])
            inner_index = int(fields[4])
            substream_index = int(fields[5])
        except (IndexError, ValueError) as exc:
            raise BuildError(
                f"Invalid AUSB exact-slot target: {modification.asset_id}"
            ) from exc
        if (
            len(fields) != 6
            or fields[:3] != ["apf", "audio", "ausb"]
            or outer_index < 0
            or inner_index < 0
            or substream_index < 0
        ):
            raise BuildError(
                f"Invalid AUSB exact-slot target: {modification.asset_id}"
            )
        return outer_index, inner_index, substream_index

    def _compile(self, modification: Modification) -> tuple[int, bytes, str]:
        if modification.kind == "uniform":
            family = modification.metadata.get("family")
            asset_index = modification.metadata.get("asset_index")
            if not isinstance(asset_index, int) or not 0 <= asset_index <= 23:
                raise BuildError(f"Invalid uniform asset index: {modification.asset_id}")
            if str(family) not in {"jersey", "pants", "helmet", "shoulder"}:
                raise BuildError(f"Unsupported APF uniform family: {family}")
            expected_asset_id = f"apf:uniform:{family}:{asset_index:02d}"
            if modification.asset_id != expected_asset_id:
                raise BuildError(
                    f"Uniform edit identity does not match its target: {modification.asset_id}"
                )
            result = compile_uniform_patch(
                self.source.index_0a,
                modification.replacement_path,
                str(family),
                asset_index,
            )
            target = result.manifest.get("family_target", {})
            outer_index = target.get("outer_table_index")
            if (
                not isinstance(outer_index, int)
                or outer_index != modification.metadata.get("outer_index")
                or target.get("asset_index") != asset_index
            ):
                raise BuildError(f"Writer target changed: {modification.asset_id}")
            return outer_index, result.entry_bytes, str(result.manifest.get("schema"))
        if (
            modification.kind == "digital_font"
            and modification.asset_id == "apf:presentation:digital_font"
        ):
            result = apf_digital_font_transport.build_patch(
                self.source.index_0a, modification.replacement_path
            )
            source = result.manifest.get("source", {})
            if source.get("outer_entry_index") != 1310:
                raise BuildError("digital_font writer target changed")
            return 1310, result.entry_bytes, str(result.manifest.get("schema"))
        if (
            modification.kind == "draft_logo"
            and modification.asset_id == DRAFT_LOGO_EDIT_ID
        ):
            fixed_metadata = {
                "width": 128,
                "height": 128,
                "outer_index": DRAFT_LOGO_OUTER_INDEX,
                "inner_index": DRAFT_LOGO_INNER_INDEX,
                "format": "BC3",
                "mip_levels": 1,
            }
            if any(
                modification.metadata.get(key) != value
                for key, value in fixed_metadata.items()
            ):
                raise BuildError("draft_logo edit target metadata changed")
            result = apf_texture_patch.build_patch(
                self.source.index_0a,
                modification.replacement_path,
                DRAFT_LOGO_OUTER_INDEX,
                DRAFT_LOGO_INNER_INDEX,
            )
            source = result.manifest.get("source", {})
            target = result.manifest.get("target", {})
            if (
                source.get("outer_entry_index") != DRAFT_LOGO_OUTER_INDEX
                or source.get("inner_file_index") != DRAFT_LOGO_INNER_INDEX
                or target.get("name") != "draft_logo"
                or target.get("type") != "TXTR"
            ):
                raise BuildError("draft_logo writer target changed")
            return (
                DRAFT_LOGO_OUTER_INDEX,
                result.entry_bytes,
                str(result.manifest.get("schema")),
            )
        raise BuildError(f"No APF build writer owns {modification.asset_id}")

    def _compile_roster_identity_group(
        self, modifications: tuple[Modification, ...]
    ) -> tuple[
        apf_roster_identity_patch.RosterIdentityPatchResult,
        dict[str, object],
    ]:
        if not modifications:
            raise BuildError("Select at least one roster-name edit")
        try:
            inventory = {
                item.asset_id: item
                for item in apf_roster_identity_patch.inventory(
                    self.source.index_0a
                )
            }
        except apf_roster_identity_patch.RosterIdentityError as exc:
            raise BuildError(f"Could not map APF roster-name edits: {exc}") from exc
        replacements: dict[int, str] = {}
        for modification in modifications:
            allocation = inventory.get(modification.asset_id)
            if allocation is None:
                raise BuildError(
                    f"Unknown APF roster-name edit: {modification.asset_id}"
                )
            try:
                pool_index = apf_roster_identity_patch.parse_asset_id(
                    modification.asset_id
                )
                value = decode_text_payload(
                    modification.replacement_path.read_bytes(),
                    modification.asset_id,
                )
                apf_roster_identity_patch.validate_replacement(allocation, value)
            except (
                OSError,
                ProjectError,
                apf_roster_identity_patch.RosterIdentityError,
            ) as exc:
                raise BuildError(
                    f"Could not read roster-name replacement "
                    f"{modification.asset_id}: {exc}"
                ) from exc
            if pool_index in replacements:
                raise BuildError(
                    f"Roster-name allocation {pool_index} was edited twice"
                )
            if modification.metadata != (
                apf_roster_identity_patch.allocation_metadata(allocation)
            ):
                raise BuildError(
                    f"Roster-name target metadata changed: {modification.asset_id}"
                )
            replacements[pool_index] = value
        try:
            result = apf_roster_identity_patch.build_patch(
                self.source.index_0a, replacements
            )
        except apf_roster_identity_patch.RosterIdentityError as exc:
            raise BuildError(f"Could not compile APF roster-name edits: {exc}") from exc
        receipt_rows = {
            str(item["asset_id"]): item
            for item in result.manifest.get("edits", ())
            if isinstance(item, dict) and "asset_id" in item
        }
        for modification in modifications:
            receipt = receipt_rows.get(modification.asset_id)
            if receipt is None or any(
                modification.metadata.get(key) != receipt.get(key)
                for key in (
                    "pool_index",
                    "maximum_utf16_units",
                    "known_owner_count",
                    "owner_fingerprint",
                )
            ):
                raise BuildError(
                    f"Roster-name allocation changed: {modification.asset_id}"
                )
        row: dict[str, object] = {
            "asset_ids": tuple(item.asset_id for item in modifications),
            "kind": "roster_identity_text_batch",
            "outer_index": result.outer_index,
            "replacement_payload_sha256s": {
                item.asset_id: item.replacement_sha256 for item in modifications
            },
            "entry_size": len(result.entry_bytes),
            "entry_sha256": _hash_bytes(result.entry_bytes),
            "writer_schema": str(result.manifest.get("schema")),
            "writer_mode": str(result.manifest.get("mode")),
        }
        return result, row

    def _compile_player_rating_group(
        self, modifications: tuple[Modification, ...]
    ) -> tuple[
        apf_player_rating_patch.PlayerRatingPatchResult,
        dict[str, object],
    ]:
        """Compile strict public 0..99 ratings through the proved ROST writer."""

        if not modifications:
            raise BuildError("Select at least one APF player rating to edit")
        replacements: dict[int, dict[str, int]] = {}
        for modification in modifications:
            try:
                target = apf_player_rating_patch.parse_asset_id(
                    modification.asset_id
                )
                value = apf_player_rating_patch.decode_replacement_payload(
                    modification.replacement_path.read_bytes(),
                    modification.asset_id,
                )
            except (OSError, apf_player_rating_patch.PlayerRatingPatchError) as exc:
                raise BuildError(
                    f"Could not read player-rating replacement "
                    f"{modification.asset_id}: {exc}"
                ) from exc
            if modification.metadata != apf_player_rating_patch.target_metadata(
                target
            ):
                raise BuildError(
                    f"Player-rating target metadata changed: {modification.asset_id}"
                )
            player = replacements.setdefault(target.player_index, {})
            if target.field_id in player:
                raise BuildError(
                    f"Player rating was edited twice: {modification.asset_id}"
                )
            player[target.field_id] = value
        try:
            result = apf_player_rating_patch.build_patch(
                self.source.index_0a, replacements
            )
        except apf_player_rating_patch.PlayerRatingPatchError as exc:
            raise BuildError(f"Could not compile APF player ratings: {exc}") from exc
        receipt_rows = {
            str(item["asset_id"]): item
            for item in result.manifest.get("edits", ())
            if isinstance(item, dict) and "asset_id" in item
        }
        for modification in modifications:
            receipt = receipt_rows.get(modification.asset_id)
            if receipt is None or any(
                modification.metadata.get(key) != receipt.get(key)
                for key in (
                    "player_index",
                    "field_id",
                    "record_relative_offset",
                    "public_minimum",
                    "public_maximum",
                )
            ):
                raise BuildError(
                    f"Player-rating target changed: {modification.asset_id}"
                )
            if receipt.get("replacement_value_sha256") != (
                modification.replacement_sha256
            ):
                raise BuildError(
                    f"Player-rating replacement receipt changed: {modification.asset_id}"
                )
        row: dict[str, object] = {
            "asset_ids": tuple(item.asset_id for item in modifications),
            "kind": "player_base_rating_batch",
            "outer_index": result.outer_index,
            "replacement_payload_sha256s": {
                item.asset_id: item.replacement_sha256 for item in modifications
            },
            "entry_size": len(result.entry_bytes),
            "entry_sha256": _hash_bytes(result.entry_bytes),
            "writer_schema": str(result.manifest.get("schema")),
            "writer_mode": str(result.manifest.get("mode")),
            "runtime_status": "runtime_proved_xenia_player_card",
        }
        return result, row

    def _compile_player_position_group(
        self, modifications: tuple[Modification, ...]
    ) -> tuple[
        apf_player_position_patch.PlayerPositionPatchResult,
        dict[str, object],
    ]:
        """Compile exact paired +0x34/+0x35 player-position replacements."""

        if not modifications:
            raise BuildError("Select at least one APF player position to edit")
        replacements: dict[int, int] = {}
        for modification in modifications:
            try:
                target = apf_player_position_patch.parse_asset_id(
                    modification.asset_id
                )
                value = apf_player_position_patch.decode_replacement_payload(
                    modification.replacement_path.read_bytes(),
                    modification.asset_id,
                )
            except (
                OSError,
                apf_player_position_patch.PlayerPositionPatchError,
            ) as exc:
                raise BuildError(
                    f"Could not read player-position replacement "
                    f"{modification.asset_id}: {exc}"
                ) from exc
            if modification.metadata != apf_player_position_patch.target_metadata(
                target
            ):
                raise BuildError(
                    f"Player-position target metadata changed: {modification.asset_id}"
                )
            if target.player_index in replacements:
                raise BuildError(
                    f"Player position was edited twice: {modification.asset_id}"
                )
            replacements[target.player_index] = value
        try:
            result = apf_player_position_patch.build_patch(
                self.source.index_0a, replacements
            )
        except apf_player_position_patch.PlayerPositionPatchError as exc:
            raise BuildError(f"Could not compile APF player positions: {exc}") from exc
        receipt_rows = {
            str(item["asset_id"]): item
            for item in result.manifest.get("edits", ())
            if isinstance(item, dict) and "asset_id" in item
        }
        for modification in modifications:
            receipt = receipt_rows.get(modification.asset_id)
            if receipt is None or any(
                modification.metadata.get(key) != receipt.get(key)
                for key in (
                    "player_index",
                    "semantic_relative_offset",
                    "mirror_relative_offset",
                    "minimum_code",
                    "maximum_code",
                    "source_mirror_required",
                )
            ):
                raise BuildError(
                    f"Player-position target changed: {modification.asset_id}"
                )
            if receipt.get("replacement_value_sha256") != (
                modification.replacement_sha256
            ):
                raise BuildError(
                    f"Player-position replacement receipt changed: {modification.asset_id}"
                )
        row: dict[str, object] = {
            "asset_ids": tuple(item.asset_id for item in modifications),
            "kind": "player_position_batch",
            "outer_index": result.outer_index,
            "replacement_payload_sha256s": {
                item.asset_id: item.replacement_sha256 for item in modifications
            },
            "entry_size": len(result.entry_bytes),
            "entry_sha256": _hash_bytes(result.entry_bytes),
            "writer_schema": str(result.manifest.get("schema")),
            "writer_mode": str(result.manifest.get("mode")),
            "runtime_status": "offline_proved_runtime_spot_check_pending",
        }
        return result, row

    def _compile_roster_composite_groups(
        self,
        identity_modifications: tuple[Modification, ...] = (),
        rating_modifications: tuple[Modification, ...] = (),
        position_modifications: tuple[Modification, ...] = (),
    ) -> tuple[
        apf_roster_composite_patch.RosterCompositePatchResult,
        dict[str, object],
    ]:
        """Compile any two or three ROST edit classes into one safe span."""

        if sum(
            bool(group)
            for group in (
                identity_modifications,
                rating_modifications,
                position_modifications,
            )
        ) < 2:
            raise BuildError(
                "Combined ROST composition needs at least two edit classes"
            )
        identity_result = identity_row = None
        rating_result = rating_row = None
        position_result = position_row = None
        if identity_modifications:
            identity_result, identity_row = self._compile_roster_identity_group(
                identity_modifications
            )
        if rating_modifications:
            rating_result, rating_row = self._compile_player_rating_group(
                rating_modifications
            )
        if position_modifications:
            position_result, position_row = self._compile_player_position_group(
                position_modifications
            )
        try:
            result = apf_roster_composite_patch.compose_components(
                self.source.index_0a,
                identity=identity_result,
                ratings=rating_result,
                positions=position_result,
            )
        except apf_roster_composite_patch.RosterCompositeError as exc:
            raise BuildError(
                f"Could not compose APF roster edits: {exc}"
            ) from exc
        component_rows = tuple(
            row
            for row in (identity_row, rating_row, position_row)
            if row is not None
        )
        replacement_hashes: dict[str, object] = {}
        for component_row in component_rows:
            hashes = component_row.get("replacement_payload_sha256s")
            if not isinstance(hashes, dict):
                raise BuildError("A ROST component replacement receipt changed")
            duplicate_hashes = set(replacement_hashes).intersection(hashes)
            if duplicate_hashes:
                raise BuildError("The same ROST target was selected twice")
            replacement_hashes.update(hashes)
        asset_ids = tuple(
            item.asset_id
            for item in (
                *identity_modifications,
                *rating_modifications,
                *position_modifications,
            )
        )
        if len(set(asset_ids)) != len(asset_ids):
            raise BuildError("The same ROST target was selected twice")
        if identity_modifications and rating_modifications and not position_modifications:
            receipt_kind = "roster_identity_and_player_rating_batch"
        else:
            receipt_kind = "roster_composite_batch"
        row: dict[str, object] = {
            "asset_ids": asset_ids,
            "kind": receipt_kind,
            "outer_index": result.outer_index,
            "replacement_payload_sha256s": replacement_hashes,
            "entry_size": len(result.entry_bytes),
            "entry_sha256": _hash_bytes(result.entry_bytes),
            "writer_schema": str(result.manifest.get("schema")),
            "writer_mode": str(result.manifest.get("mode")),
            "component_writer_schemas": tuple(
                result.manifest.get("component_schemas", ())
            ),
            "runtime_status": (
                "offline_proved_position_runtime_spot_check_pending"
                if position_modifications
                else "runtime_proved_token_preserving_roster_consumers"
            ),
        }
        return result, row

    def build_private_player_rating_candidate(
        self,
        replacements: Mapping[int, Mapping[str, int]],
        output_game: Path,
        progress: Progress = _noop,
    ) -> BuildReceipt:
        """Build an atomic private game copy for a bounded runtime experiment.

        This helper intentionally bypasses projects, sessions, the facade, and
        the GUI.  Its temporary files contain only caller-supplied integers;
        the resulting complete game directory remains private user-owned game
        data and carries the standard non-redistribution build manifest.
        """

        normalized = apf_player_rating_patch.normalize_replacements(replacements)
        with tempfile.TemporaryDirectory(
            prefix="apf2k8-private-player-ratings-"
        ) as directory:
            root = Path(directory)
            modifications: list[Modification] = []
            for ordinal, (target, value) in enumerate(normalized):
                payload = apf_player_rating_patch.encode_replacement_payload(value)
                path = root / f"rating-{ordinal:04d}.json"
                descriptor = os.open(
                    path,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                try:
                    view = memoryview(payload)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise BuildError(
                                "Short write while preparing a private rating candidate"
                            )
                        view = view[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                modifications.append(
                    Modification(
                        asset_id=target.asset_id,
                        kind="player_base_rating",
                        replacement_path=path,
                        replacement_sha256=_hash_bytes(payload),
                        metadata=apf_player_rating_patch.target_metadata(target),
                    )
                )
            return self.build(tuple(modifications), output_game, progress)

    def _verify_composed(
        self,
        output_root: Path,
        spans: list[_CompiledBuildSpan],
        progress: Progress,
    ) -> str:
        ordered = self._normalize_compiled_spans(spans)
        spans_by_pack: dict[str, list[_CompiledBuildSpan]] = {}
        for span in ordered:
            spans_by_pack.setdefault(span.pack_name, []).append(span)

        # The receipt's historic output_0a_sha256 field remains exactly that:
        # the complete staged 0A digest, even when only another pack changed.
        output_0a_sha256 = self._verify_changed_pack(
            output_root,
            "0A",
            spans_by_pack.get("0A", ()),
            progress,
        )
        for pack_name, pack_spans in sorted(spans_by_pack.items()):
            if pack_name == "0A":
                continue
            self._verify_changed_pack(
                output_root,
                pack_name,
                pack_spans,
                progress,
            )

        # Every physical pack not targeted by a compiled span, plus the
        # executable and update sibling, is hash-checked once after the copy.
        changed_packs = set(spans_by_pack)
        for relative, (_size, expected) in EXPECTED_TREE.items():
            if relative == "0A" or relative in changed_packs:
                continue
            actual = sha256_file(
                output_root / relative,
                stage=f"Verifying copied {relative}",
            )
            if actual != expected:
                raise BuildError(f"Copied game file failed verification: {relative}")

        source_0a = self.source.index_0a
        output_0a = output_root / "0A"
        output_archive = apf_outer.parse_archive(output_0a)
        source_archive = apf_outer.parse_archive(source_0a)
        if (
            output_archive.alignment != source_archive.alignment
            or len(output_archive.entries) != len(source_archive.entries)
            or [
                (item.table_index, item.name_id, item.offset_blocks, item.size_blocks)
                for item in output_archive.entries
            ]
            != [
                (item.table_index, item.name_id, item.offset_blocks, item.size_blocks)
                for item in source_archive.entries
            ]
        ):
            raise BuildError("Composed APF archive directory changed")

        reparsed_outer_indices = sorted(
            {span.outer_index for span in ordered if span.reparse_owner}
        )
        if reparsed_outer_indices:
            with apf_inner.ArchiveReader(output_archive) as reader:
                for outer_index in reparsed_outer_indices:
                    try:
                        entry = output_archive.entries[outer_index]
                    except IndexError as exc:
                        raise BuildError(
                            f"Compiled edit targets missing outer {outer_index}"
                        ) from exc
                    record = apf_inner.parse_iff(reader, entry)
                    if record.warnings:
                        raise BuildError(
                            f"Rebuilt outer {outer_index} has IFF warnings"
                        )
        return output_0a_sha256

    def _verify_changed_pack(
        self,
        output_root: Path,
        pack_name: str,
        spans: Iterable[_CompiledBuildSpan],
        progress: Progress,
    ) -> str:
        """Verify one pack's exact spans and every byte outside them."""

        if pack_name not in COMPILED_SPAN_PACKS:
            raise BuildError(f"Unsupported compiled APF pack: {pack_name}")
        ordered = self._normalize_compiled_spans(spans)
        if any(span.pack_name != pack_name for span in ordered):
            raise BuildError(f"Compiled APF pack group changed: {pack_name}")
        source_pack = (
            self.source.index_0a
            if pack_name == "0A"
            else self.source.game_root / pack_name
        )
        output_pack = output_root / pack_name
        source_fd = os.open(
            source_pack,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            output_fd = os.open(
                output_pack,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            )
        except BaseException:
            os.close(source_fd)
            raise
        output_digest = hashlib.sha256()
        try:
            source_size = os.fstat(source_fd).st_size
            output_size = os.fstat(output_fd).st_size
            expected_size = EXPECTED_TREE[pack_name][0]
            if source_size != expected_size or output_size != source_size:
                raise BuildError(f"Composed {pack_name} size changed")
            cursor = 0
            for span in ordered:
                if span.offset < cursor or span.end > source_size:
                    raise BuildError(
                        f"Compiled {pack_name} span exceeds its pack: {span.label}"
                    )
                self._compare_range(
                    source_fd,
                    output_fd,
                    cursor,
                    span.offset - cursor,
                    output_digest,
                    progress,
                    source_size,
                    pack_name,
                )
                source_data = platform_compat.pread(source_fd, span.size, span.offset)
                if len(source_data) != span.size:
                    raise BuildError(
                        f"Could not re-read source span for {span.label}"
                    )
                if (
                    span.source_span_sha256 is not None
                    and _hash_bytes(source_data) != span.source_span_sha256
                ):
                    raise BuildError(f"Source span changed for {span.label}")
                actual = platform_compat.pread(output_fd, span.size, span.offset)
                if len(actual) != span.size or actual != span.data:
                    raise BuildError(
                        f"Output {span.label} differs from the compiled edit"
                    )
                output_digest.update(actual)
                cursor = span.end
            self._compare_range(
                source_fd,
                output_fd,
                cursor,
                source_size - cursor,
                output_digest,
                progress,
                source_size,
                pack_name,
            )
        finally:
            os.close(output_fd)
            os.close(source_fd)
        return output_digest.hexdigest()

    @staticmethod
    def _compare_range(
        source_fd: int,
        output_fd: int,
        offset: int,
        size: int,
        output_digest: "hashlib._Hash",
        progress: Progress,
        total: int,
        pack_name: str,
    ) -> None:
        cursor = 0
        while cursor < size:
            count = min(8 * 1024 * 1024, size - cursor)
            before = platform_compat.pread(source_fd, count, offset + cursor)
            after = platform_compat.pread(output_fd, count, offset + cursor)
            if len(before) != count or before != after:
                raise BuildError(
                    f"Output {pack_name} changed outside the compiled APF edit spans"
                )
            output_digest.update(after)
            cursor += count
            progress("Verifying the complete APF build", offset + cursor, total)
