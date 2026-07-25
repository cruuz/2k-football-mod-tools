"""Private, manifest-backed NFL 2K5 Team Kit authoring bundles.

This product adapter generalizes the proved Giants hand-off workflow to any
uniform set exposed by :mod:`mod_editor.core.nfl2k5_uniform_catalog`. It does
not decode or write game formats itself: exports come from the active
``StudioSession`` visual provider route, and imports finish through the
session's validate-all ``replace_batch`` transaction.

Bundle PNGs can reproduce source artwork, so a Team Kit bundle is explicitly a
private working export, not a shareable mod. The existing ``.2k5mod`` project
path remains the distribution format and includes only pixel-changed,
user-authored replacements.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Callable, Iterable, Iterator, Sequence
from uuid import uuid4
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_uniform_catalog import (
    ASSETS_PER_SET,
    Nfl2k5UniformCatalog,
    UniformAsset,
    UniformSet,
)
from mod_editor.core.platform_compat import fsync_path

from .session import BatchReplaceResult, StudioSession


TEAM_KIT_BUNDLE_SCHEMA = "2k5_mod_studio_team_kit_bundle/v1"
TEAM_KIT_MANIFEST = "team-kit-manifest.json"
TEAM_KIT_GUIDE = "EDITING-GUIDE.md"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
_SHA256_HEX = frozenset("0123456789abcdef")
BundleProgress = Callable[[str, int, int], None]


def _quiet_progress(_stage: str, _completed: int, _total: int) -> None:
    pass


class TeamKitBundleError(ValidationError):
    """A Team Kit selection, working export, or edited import is invalid."""


@dataclass(frozen=True, slots=True)
class TeamKitBundleExportResult:
    path: Path
    container: str
    set_selectors: tuple[str, ...]
    asset_count: int
    manifest_sha256: str
    private_source_derived: bool = True

    @property
    def message(self) -> str:
        return (
            f"Exported {self.asset_count} Team Kit components from "
            f"{len(self.set_selectors)} physical set"
            f"{'s' if len(self.set_selectors) != 1 else ''} to {self.path.name}. "
            "This private working export may contain retail artwork; share the "
            ".2k5mod project, not this bundle."
        )


@dataclass(frozen=True, slots=True)
class TeamKitBundleImportResult:
    path: Path
    set_selectors: tuple[str, ...]
    asset_count: int
    changed_count: int
    unchanged_count: int
    batch: BatchReplaceResult | None
    message: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamKitBundleError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256_HEX for character in value)
    )


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _safe_relative(value: object, *, suffix: str | None = None) -> str:
    _require(isinstance(value, str) and bool(value), "Bundle path must be text")
    pure = PurePosixPath(value)
    _require(
        not pure.is_absolute()
        and value == pure.as_posix()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        f"Unsafe Team Kit bundle path: {value!r}",
    )
    if suffix is not None:
        _require(pure.suffix.casefold() == suffix, f"Bundle file must end in {suffix}")
    return value


def _regular_file(path: Path, label: str, *, maximum: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise TeamKitBundleError(f"{label} is missing: {path}") from exc
    _require(
        stat.S_ISREG(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_nlink == 1,
        f"{label} must be a regular file, not a folder or link: {path}",
    )
    if maximum is not None:
        _require(0 < info.st_size <= maximum, f"{label} exceeds its safe size limit")
    return info


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _source_sha256(session: StudioSession) -> str:
    value = getattr(getattr(session, "cache", None), "source", None)
    digest = getattr(value, "sha256", None)
    _require(_is_sha256(digest), "The loaded NFL 2K5 source has no valid identity")
    return str(digest)


def _normalize_sides(sides: str | Iterable[str]) -> tuple[str, ...]:
    values = (sides,) if isinstance(sides, str) else tuple(sides)
    normalized: list[str] = []
    for raw in values:
        _require(isinstance(raw, str), "Uniform side must be HOME, AWAY, or BOTH")
        value = raw.strip().upper()
        if value == "BOTH":
            for side in ("H", "A"):
                if side not in normalized:
                    normalized.append(side)
            continue
        value = {"HOME": "H", "AWAY": "A"}.get(value, value)
        _require(value in {"H", "A"}, "Uniform side must be HOME, AWAY, or BOTH")
        if value not in normalized:
            normalized.append(value)
    _require(bool(normalized), "Choose HOME, AWAY, or BOTH uniform sides")
    return tuple(normalized)


def select_team_uniform_sets(
    catalog: Nfl2k5UniformCatalog,
    *,
    asset_code: str,
    variant: int,
    sides: str | Iterable[str] = "BOTH",
) -> tuple[UniformSet, ...]:
    """Resolve one team's exact HOME/AWAY physical sets from catalog evidence."""

    return tuple(
        catalog.uniform_set_for(asset_code, side, variant)
        for side in _normalize_sides(sides)
    )


def _ordered_sets(
    catalog: Nfl2k5UniformCatalog, selectors: Sequence[str]
) -> tuple[UniformSet, ...]:
    _require(
        not isinstance(selectors, (str, bytes)) and bool(selectors),
        "Choose at least one uniform set for the Team Kit bundle",
    )
    selected: dict[str, UniformSet] = {}
    for selector in selectors:
        _require(isinstance(selector, str), "Uniform set selectors must be text")
        uniform_set = catalog.get_uniform_set(selector)
        _require(
            uniform_set.selector not in selected,
            f"Uniform set {uniform_set.selector} was selected more than once",
        )
        selected[uniform_set.selector] = uniform_set
    # Catalog order is the stable product order and is independent of GUI click
    # order, making equivalent exports byte-for-byte deterministic.
    return tuple(
        uniform_set for uniform_set in catalog.uniform_sets
        if uniform_set.selector in selected
    )


def _component_relative(asset: UniformAsset) -> str:
    root = f"SETS/{asset.set_selector}_{asset.side_name}"
    if asset.kind in {"torso", "sleeve", "pants"}:
        name = "torso_jersey" if asset.kind == "torso" else asset.kind
        return f"{root}/01_LIVE_UNIFORM/{name}.png"
    if asset.kind == "live_helmet":
        _require(asset.family in {"helmet00", "helmet02"}, "Unknown helmet family")
        return f"{root}/02_LIVE_HELMETS/{asset.family}.png"
    if asset.kind == "live_number_nameplate":
        if asset.family == "nameplate":
            return f"{root}/04_NAMEPLATE/nameplate_atlas.png"
        _require(
            asset.family in {"jersey", "helmet", "arm"}
            and type(asset.digit) is int
            and 0 <= asset.digit <= 9,
            "Unknown live digit target",
        )
        return f"{root}/03_LIVE_DIGITS/{asset.family}/digit_{asset.digit}.png"
    _require(asset.kind == "team_select", "Unknown Team Kit component kind")
    names = {
        ("unif", 256): "uniform_card_256.png",
        ("helm", 256): "helmet_card_256.png",
        ("helm", 128): "helmet_card_128.png",
    }
    try:
        name = names[(str(asset.family), int(asset.resolution or 0))]
    except KeyError as exc:
        raise TeamKitBundleError("Unknown Team Select card target") from exc
    return f"{root}/05_TEAM_SELECT/{name}"


def _authoring_note(asset: UniformAsset) -> str:
    if asset.kind in {"torso", "sleeve", "pants"}:
        return (
            "UV atlas: paint over the exported islands; preserve seams, blank margins, "
            "orientation, dimensions, and RGBA channels. Exact front/back/left/right "
            "pixel regions are not decoded. The builder derives mud palettes from the "
            "edited clean art."
        )
    if asset.kind == "live_helmet":
        return (
            f"Distinct {asset.family} player-model UV atlas. Preserve transparent "
            "margins and registration; edit both helmet00 and helmet02 for complete "
            "player-model coverage."
        )
    if asset.kind == "live_number_nameplate" and asset.family == "nameplate":
        return (
            "32×1024 vertical alphabet/nameplate atlas. Glyph metrics remain read-only; "
            "keep each glyph in its existing registered slot and preserve alpha."
        )
    if asset.kind == "live_number_nameplate":
        return (
            f"Transparent {asset.family} digit glyph. Keep the glyph registered inside "
            "the existing canvas and preserve antialiased alpha."
        )
    if asset.family == "unif":
        return (
            "Baked Team Select uniform picture. It includes its own helmet/lower art "
            "and never regenerates from live uniform textures."
        )
    return (
        "Standalone Team Select helmet picture; it never regenerates from the live "
        "helmet textures. Preserve canvas size and transparency."
    )


def _ownership_note(asset: UniformAsset) -> str:
    if asset.kind == "live_helmet":
        material = "A" if asset.family == "helmet00" else "C"
        return (
            f"This target owns one independently writable player-model material family "
            f"({material}). Matching pixels in other sets/families are content aliases, "
            "not shared writable storage."
        )
    if asset.kind == "live_number_nameplate" and asset.family in {"jersey", "arm"}:
        return (
            "Jersey and arm digits can look identical but occupy independent targets; "
            "changing this file does not update the other digit family or uniform side."
        )
    if asset.kind == "team_select":
        consumer = (
            "The 128×128 helmet card's exact visible timing remains unresolved; it is "
            "included because its storage and bounded writer are proved."
            if asset.resolution == 128 else
            "The 256×256 Team Select class has menu ownership evidence."
        )
        return (
            "Menu-only storage is independent from live gameplay art and from the other "
            f"card sizes. {consumer}"
        )
    return (
        "One independently writable target in this physical set. Matching retail pixels "
        "elsewhere are content aliases; this write changes only the selected target."
    )


def _set_document(uniform_set: UniformSet) -> dict[str, object]:
    return {
        "asset_code": uniform_set.asset_code,
        "historic_abbreviations": list(uniform_set.historic_abbreviations),
        "label": uniform_set.label,
        "package": uniform_set.uniform_package,
        "selector": uniform_set.selector,
        "side": uniform_set.side_name,
        "style": uniform_set.style_label,
        "team_abbreviations": list(uniform_set.team_abbreviations),
        "team_names": list(uniform_set.team_names),
        "variant": uniform_set.variant,
    }


def _asset_document(
    asset: UniformAsset,
    *,
    baseline_png_sha256: str,
    baseline_rgba_sha256: str,
    content_origin: str,
) -> dict[str, object]:
    return {
        "asset_id": asset.asset_id,
        "authoring_note": _authoring_note(asset),
        "baseline_png_sha256": baseline_png_sha256,
        "baseline_rgba_sha256": baseline_rgba_sha256,
        "content_origin": content_origin,
        "dimensions": {"height": asset.height, "width": asset.width},
        "family": asset.family,
        "group": asset.group,
        "kind": asset.kind,
        "label": asset.label,
        "ownership_note": _ownership_note(asset),
        "path": _component_relative(asset),
        "set_selector": asset.set_selector,
        "target_selector": asset.target_selector,
    }


def _guide(sets: Sequence[UniformSet]) -> bytes:
    rows = "\n".join(
        f"- `{item.selector}` — {item.label} ({item.uniform_package})"
        for item in sets
    )
    text = f"""# Team Kit Editing Guide

This is a **private working export** from your own NFL 2K5 copy. Its PNGs may
reproduce retail artwork, so do not upload or distribute this folder/ZIP. Share
the resulting `.2k5mod` project instead; projects contain only your authored,
pixel-changed replacements and logical metadata.

## Included physical sets

{rows}

Each set contains all {ASSETS_PER_SET} supported parts: torso/jersey, sleeve,
pants, both live helmet UV families, jersey/helmet/arm digits 0–9, the vertical
nameplate atlas, and three independent Team Select cards.

## Safe editing contract

1. Edit PNGs under `SETS/`; leave `{TEAM_KIT_MANIFEST}` unchanged.
2. Keep every image at its exact dimensions as an 8-bit RGBA PNG with
   interlacing off. Do not crop, rotate, rename, or flatten transparency.
3. Paint over existing UV islands and preserve seams, registration, blank
   margins, and orientation. Exact body-region UV coordinates are not decoded.
4. Edit both `helmet00` and `helmet02` for full player-model coverage. Team
   Select cards are baked menu art and do not update from live textures.
5. Returning an unchanged or merely re-encoded PNG is safe: import compares
   decoded RGBA pixels and stages only truly changed files.
6. Import validates every manifest row and PNG before staging anything. The
   entire changed kit lands as one Undo action.
"""
    return text.encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.flag_bits = 0x800  # UTF-8 names
    return info


@contextmanager
def _bundle_root(source: Path) -> Iterator[tuple[Path, Path]]:
    """Yield ``(materialized_root, reported_source)`` for a folder or ZIP."""

    requested = source.expanduser()
    try:
        info = requested.lstat()
    except FileNotFoundError as exc:
        raise TeamKitBundleError(f"Choose an existing Team Kit folder or ZIP: {source}") from exc
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        yield requested.resolve(strict=True), requested.resolve(strict=True)
        return
    _regular_file(requested, "Team Kit ZIP")
    _require(requested.suffix.casefold() == ".zip", "Team Kit archive must end in .zip")
    temporary = Path(tempfile.mkdtemp(prefix="2k5-team-kit-import-"))
    try:
        try:
            archive = zipfile.ZipFile(requested, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise TeamKitBundleError(f"Could not open Team Kit ZIP: {exc}") from exc
        with archive:
            infos = archive.infolist()
            names = [row.filename for row in infos]
            _require(len(names) == len(set(names)), "Team Kit ZIP contains duplicate paths")
            total = 0
            for row in infos:
                mode = row.external_attr >> 16
                if row.is_dir():
                    name = _safe_relative(row.filename.rstrip("/"))
                    _require(
                        row.file_size == 0
                        and not stat.S_ISLNK(mode)
                        and not (row.flag_bits & 0x1),
                        f"Team Kit ZIP directory is unsafe or encrypted: {name}",
                    )
                    continue
                name = _safe_relative(row.filename)
                _require(
                    not stat.S_ISLNK(mode)
                    and row.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    and not (row.flag_bits & 0x1),
                    f"Team Kit ZIP member is unsafe or encrypted: {name}",
                )
                limit = MAX_MANIFEST_BYTES if name in {TEAM_KIT_MANIFEST, TEAM_KIT_GUIDE} \
                    else MAX_PNG_BYTES
                _require(0 < row.file_size <= limit, f"Team Kit ZIP member is too large: {name}")
                total += row.file_size
                _require(total <= MAX_ZIP_TOTAL_BYTES, "Team Kit ZIP expands beyond 16 GiB")
                target = temporary.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(row, "r") as reader:
                    payload = reader.read(limit + 1)
                _require(len(payload) == row.file_size <= limit, f"ZIP member size changed: {name}")
                _write_new(target, payload)
        yield temporary, requested.resolve(strict=True)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _folder_files(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            path = current_path / directory
            info = path.lstat()
            _require(
                stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                f"Team Kit folder contains an unsafe directory link: {path}",
            )
        for name in files:
            path = current_path / name
            _regular_file(path, "Team Kit file")
            relative = path.relative_to(root).as_posix()
            _safe_relative(relative)
            _require(relative not in result, f"Duplicate Team Kit path: {relative}")
            result[relative] = path
    return result


class TeamKitBundleService:
    """Export and import complete physical uniform sets through one session."""

    def __init__(
        self, catalog: Nfl2k5UniformCatalog, session: StudioSession
    ) -> None:
        self.catalog = catalog
        self.session = session

    def export(
        self,
        selectors: Sequence[str],
        destination: Path,
        *,
        container: str | None = None,
        progress: BundleProgress = _quiet_progress,
    ) -> TeamKitBundleExportResult:
        """Export complete selected sets to a labeled folder or deterministic ZIP."""

        sets = _ordered_sets(self.catalog, selectors)
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        normalized = (
            container.strip().casefold() if isinstance(container, str)
            else ("zip" if requested.suffix.casefold() == ".zip" else "folder")
        )
        _require(normalized in {"folder", "zip"}, "Team Kit container must be folder or zip")
        if normalized == "zip":
            _require(requested.suffix.casefold() == ".zip", "ZIP destination must end in .zip")
        _require(not os.path.lexists(requested), f"A file or folder already exists there: {requested}")
        requested.parent.mkdir(parents=True, exist_ok=True)

        stage = Path(tempfile.mkdtemp(
            prefix=f".{requested.name}.team-kit-{uuid4().hex}-",
            dir=requested.parent,
        ))
        published = False
        try:
            assets: list[dict[str, object]] = []
            expected_count = len(sets) * ASSETS_PER_SET
            progress("Preparing complete Team Kit components", 0, expected_count + 1)
            for uniform_set in sets:
                rows = self.catalog.assets_for_set(uniform_set.selector)
                _require(
                    len(rows) == ASSETS_PER_SET,
                    f"Uniform set {uniform_set.selector} is incomplete",
                )
                for asset in rows:
                    current = self.session.current_path(asset)
                    payload, rgba = self.session.asset_io.validate_replacement(asset, current)
                    relative = _component_relative(asset)
                    _write_new(stage.joinpath(*PurePosixPath(relative).parts), payload)
                    assets.append(_asset_document(
                        asset,
                        baseline_png_sha256=_sha256(payload),
                        baseline_rgba_sha256=_sha256(rgba),
                        content_origin=(
                            "user_replacement"
                            if self.session.is_modified(asset) else "source_derived"
                        ),
                    ))
                    progress(
                        "Exporting complete Team Kit components",
                        len(assets),
                        expected_count + 1,
                    )
            _require(len(assets) == expected_count, "Team Kit export asset count changed")

            guide = _guide(sets)
            _write_new(stage / TEAM_KIT_GUIDE, guide)
            manifest = {
                "assets": assets,
                "counts": {
                    "assets": len(assets),
                    "sets": len(sets),
                },
                "guide": {
                    "path": TEAM_KIT_GUIDE,
                    "sha256": _sha256(guide),
                },
                "import_policy": (
                    "All rows and PNGs validate before any edit is staged; decoded pixel "
                    "changes apply as one undo action."
                ),
                "payload_policy": (
                    "private-source-derived-working-bundle; do-not-distribute; share a "
                    ".2k5mod project containing authored replacements instead"
                ),
                "schema": TEAM_KIT_BUNDLE_SCHEMA,
                "sets": [_set_document(item) for item in sets],
                "source": {"sha256": _source_sha256(self.session)},
            }
            manifest_payload = _canonical_json(manifest)
            _write_new(stage / TEAM_KIT_MANIFEST, manifest_payload)
            progress(
                "Publishing the private Team Kit bundle",
                expected_count,
                expected_count + 1,
            )

            if normalized == "folder":
                # Reserve the destination with mkdir(O_EXCL semantics), prove it
                # is still our empty directory, then atomically replace only that
                # reservation with the fully prepared tree.
                requested.mkdir(mode=0o700)
                reservation = requested.lstat()
                _require(stat.S_ISDIR(reservation.st_mode), "Could not reserve export folder")
                try:
                    _require(not any(requested.iterdir()), "Export folder reservation changed")
                    os.replace(stage, requested)
                except BaseException:
                    if requested.exists() and not any(requested.iterdir()):
                        requested.rmdir()
                    raise
                published = True
            else:
                archive_path = stage.with_suffix(".zip")
                try:
                    files = _folder_files(stage)
                    with zipfile.ZipFile(archive_path, "x") as archive:
                        for relative in sorted(files):
                            archive.writestr(
                                _zip_info(relative), files[relative].read_bytes()
                            )
                    os.chmod(archive_path, 0o600)
                    # The Team Kit ZIP is flushed before the hard link publishes
                    # it.  Windows cannot flush a read-only handle, so the helper
                    # opens read-write there and ``O_RDONLY`` everywhere else.
                    fsync_path(archive_path)
                    try:
                        os.link(archive_path, requested, follow_symlinks=False)
                    except FileExistsError as exc:
                        raise TeamKitBundleError(
                            f"A file already exists there: {requested}"
                        ) from exc
                    published = True
                finally:
                    archive_path.unlink(missing_ok=True)

            progress("Team Kit export complete", expected_count + 1, expected_count + 1)

            return TeamKitBundleExportResult(
                requested.resolve(strict=True),
                normalized,
                tuple(item.selector for item in sets),
                len(assets),
                _sha256(manifest_payload),
            )
        except FileExistsError as exc:
            raise TeamKitBundleError(f"A file or folder already exists there: {requested}") from exc
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            if not published and requested.exists() and requested.is_dir():
                try:
                    if not any(requested.iterdir()):
                        requested.rmdir()
                except OSError:
                    pass

    def export_team(
        self,
        *,
        asset_code: str,
        variant: int,
        destination: Path,
        sides: str | Iterable[str] = "BOTH",
        container: str | None = None,
        progress: BundleProgress = _quiet_progress,
    ) -> TeamKitBundleExportResult:
        """Convenience route for a team's HOME, AWAY, or paired kit export."""

        sets = select_team_uniform_sets(
            self.catalog,
            asset_code=asset_code,
            variant=variant,
            sides=sides,
        )
        return self.export(
            tuple(item.selector for item in sets),
            destination,
            container=container,
            progress=progress,
        )

    def import_edited(
        self,
        source: Path,
        *,
        progress: BundleProgress = _quiet_progress,
    ) -> TeamKitBundleImportResult:
        """Validate one complete edited bundle, then stage true changes once."""

        with _bundle_root(source) as (root, reported_source):
            files = _folder_files(root)
            manifest_path = files.get(TEAM_KIT_MANIFEST)
            _require(manifest_path is not None, f"{TEAM_KIT_MANIFEST} is missing")
            _regular_file(manifest_path, "Team Kit manifest", maximum=MAX_MANIFEST_BYTES)
            manifest_payload = manifest_path.read_bytes()
            try:
                document = json.loads(manifest_payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TeamKitBundleError(f"Team Kit manifest is not valid JSON: {exc}") from exc
            _require(
                isinstance(document, dict)
                and document.get("schema") == TEAM_KIT_BUNDLE_SCHEMA,
                "Team Kit manifest schema is unsupported",
            )
            _require(
                manifest_payload == _canonical_json(document),
                "Team Kit manifest changed; restore the original manifest and edit PNGs only",
            )
            _require(set(document) == {
                "assets", "counts", "guide", "import_policy", "payload_policy",
                "schema", "sets", "source",
            }, "Team Kit manifest fields changed")
            source_row = document.get("source")
            _require(
                isinstance(source_row, dict)
                and set(source_row) == {"sha256"}
                and _is_sha256(source_row.get("sha256")),
                "Team Kit source identity is invalid",
            )
            _require(
                source_row["sha256"] == _source_sha256(self.session),
                "This Team Kit bundle was exported from a different NFL 2K5 source",
            )

            set_rows = document.get("sets")
            _require(isinstance(set_rows, list) and bool(set_rows), "Team Kit has no sets")
            selectors: list[str] = []
            for number, row in enumerate(set_rows, 1):
                _require(isinstance(row, dict), f"Team Kit set {number} is invalid")
                selector = row.get("selector")
                _require(isinstance(selector, str), f"Team Kit set {number} has no selector")
                selected = self.catalog.get_uniform_set(selector)
                _require(row == _set_document(selected), f"Team Kit set metadata changed: {selector}")
                _require(selector not in selectors, f"Team Kit set is duplicated: {selector}")
                selectors.append(selector)
            ordered = _ordered_sets(self.catalog, selectors)
            _require(
                selectors == [item.selector for item in ordered],
                "Team Kit sets are not in deterministic catalog order",
            )

            guide_row = document.get("guide")
            _require(
                isinstance(guide_row, dict)
                and set(guide_row) == {"path", "sha256"}
                and guide_row.get("path") == TEAM_KIT_GUIDE
                and _is_sha256(guide_row.get("sha256")),
                "Team Kit guide record is invalid",
            )
            guide_path = files.get(TEAM_KIT_GUIDE)
            _require(guide_path is not None, f"{TEAM_KIT_GUIDE} is missing")
            guide = guide_path.read_bytes()
            _require(
                guide == _guide(ordered) and _sha256(guide) == guide_row["sha256"],
                "Team Kit editing guide changed",
            )

            asset_rows = document.get("assets")
            expected_count = len(ordered) * ASSETS_PER_SET
            counts = document.get("counts")
            _require(
                isinstance(asset_rows, list)
                and isinstance(counts, dict)
                and counts == {"assets": expected_count, "sets": len(ordered)}
                and len(asset_rows) == expected_count,
                "Team Kit manifest counts do not match its complete sets",
            )
            expected_assets = tuple(
                asset
                for uniform_set in ordered
                for asset in self.catalog.assets_for_set(uniform_set.selector)
            )
            _require(
                len({asset.asset_id for asset in expected_assets}) == expected_count,
                "Team Kit catalog targets overlap",
            )
            expected_paths = {TEAM_KIT_MANIFEST, TEAM_KIT_GUIDE}
            replacements: list[tuple[UniformAsset, Path]] = []
            seen_ids: set[str] = set()
            progress("Validating every Team Kit component", 0, expected_count + 1)
            for number, (row, asset) in enumerate(zip(asset_rows, expected_assets), 1):
                _require(isinstance(row, dict), f"Team Kit asset row {number} is invalid")
                _require(row.get("asset_id") == asset.asset_id, (
                    f"Team Kit asset order/identity changed at row {number}"
                ))
                _require(asset.asset_id not in seen_ids, f"Duplicate asset ID: {asset.asset_id}")
                seen_ids.add(asset.asset_id)
                baseline_png = row.get("baseline_png_sha256")
                baseline_rgba = row.get("baseline_rgba_sha256")
                origin = row.get("content_origin")
                _require(
                    _is_sha256(baseline_png)
                    and _is_sha256(baseline_rgba)
                    and origin in {"source_derived", "user_replacement"},
                    f"Team Kit baseline is invalid for {asset.asset_id}",
                )
                expected_static = _asset_document(
                    asset,
                    baseline_png_sha256=str(baseline_png),
                    baseline_rgba_sha256=str(baseline_rgba),
                    content_origin=str(origin),
                )
                _require(row == expected_static, f"Team Kit asset metadata changed: {asset.asset_id}")
                relative = _safe_relative(row["path"], suffix=".png")
                expected_paths.add(relative)
                supplied = files.get(relative)
                _require(supplied is not None, f"Team Kit PNG is missing: {relative}")
                _regular_file(supplied, f"Team Kit PNG {relative}", maximum=MAX_PNG_BYTES)

                current = self.session.current_path(asset)
                current_payload, current_rgba = self.session.asset_io.validate_replacement(
                    asset, current
                )
                current_origin = (
                    "user_replacement" if self.session.is_modified(asset)
                    else "source_derived"
                )
                _require(
                    _sha256(current_payload) == baseline_png
                    and _sha256(current_rgba) == baseline_rgba
                    and current_origin == origin,
                    f"The working pixels changed after export for {asset.label}; "
                    "export a fresh Team Kit bundle before importing",
                )
                _payload, supplied_rgba = self.session.asset_io.validate_replacement(
                    asset, supplied
                )
                if _sha256(supplied_rgba) != baseline_rgba:
                    replacements.append((asset, supplied))
                progress(
                    "Validating every Team Kit component",
                    number,
                    expected_count + 1,
                )

            _require(
                set(files) == expected_paths,
                "Team Kit folder/ZIP contains missing, renamed, or undeclared files",
            )
            if replacements:
                progress(
                    "Staging changed Team Kit components as one Undo action",
                    expected_count,
                    expected_count + 1,
                )
                batch = self.session.replace_batch(
                    replacements,
                    label=(
                        "Import Team Kit "
                        + ", ".join(item.selector for item in ordered)
                    ),
                )
                changed_count = len(batch.changed_asset_ids)
            else:
                batch = None
                changed_count = 0
            progress("Team Kit import complete", expected_count + 1, expected_count + 1)
            return TeamKitBundleImportResult(
                reported_source,
                tuple(item.selector for item in ordered),
                expected_count,
                changed_count,
                expected_count - changed_count,
                batch,
                (
                    f"Imported {changed_count} changed component"
                    f"{'s' if changed_count != 1 else ''} as one Undo action."
                    if changed_count else
                    "Every PNG has the same decoded pixels as the export; nothing was staged."
                ),
            )


__all__ = [
    "TEAM_KIT_BUNDLE_SCHEMA",
    "TEAM_KIT_GUIDE",
    "TEAM_KIT_MANIFEST",
    "TeamKitBundleError",
    "TeamKitBundleExportResult",
    "TeamKitBundleImportResult",
    "TeamKitBundleService",
    "select_team_uniform_sets",
]
