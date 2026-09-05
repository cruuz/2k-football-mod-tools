"""Qt-free export of edited Xbox uniform art as a PCSX2 replacement pack.

The PS2 lane never patches the user's ISO. It emits a folder of PNGs named by
GS texture/CLUT hash, which PenguinScreen2 loads at draw time. This module is
the whole writer: it plans an export from an open (or saved) Xbox project plus
the shipped ``nfl2k5-xbox-map.v1.json`` manifest, and then publishes the pack.

**The one hard rule: an unedited target is never written.** Emitting one would
be emitting retail pixels off the user's disc under a PCSX2 filename, which is
exactly what this product must not do. The rule is enforced structurally rather
than by a check that could be forgotten -- ``plan_export`` can only ever see
targets the project itself lists as edited, because that is the only thing an
``ExportProject`` carries. There is no code path from a catalog, a disc, or a
source cache into an output file.

That is stronger than it looks, because of where the edit list comes from. A
``.2k5mod`` archive refuses to record an edit whose decoded RGBA equals the
retail original (``project_archive.py``: "matches the retail original and was
excluded. Revert it first."), so every row in a saved project is *provably*
user-authored pixels. A live ``StudioSession`` is the same set before it is
written down.

Target identity
---------------

The studio names an edit by ``asset_id``, and the manifest names the Xbox side
of a row by ``xbox_asset_id``. For three of the studio's four namespaces those
are the *same string*, so the mapping is identity:

===============================================  =========================
studio ``asset_id``                              manifest ``xbox_asset_id``
===============================================  =========================
``p8:{outer}:{name}``                            identical
``tset:{outer}:{chunk}:{child}:{name}``          identical
``nfl2k5.crib.scene.c{chunk:04d}.t{idx:03d}``    identical
``nfl2k5.uniform.{selector}.{component}``        **not expressible**
===============================================  =========================

The fourth is the exception and it is reported, never guessed. A
``nfl2k5.uniform.*`` id is a *logical* provider target -- one of 39 components
of one of 634 uniform sets -- that a writer composes into physical TSET/P8
packages at build time. It does not name a texture on the disc, so it has no
GS hash and cannot be joined to a PCSX2 filename by this module. Such a target
is planned as ``unmapped`` with an explicit reason. If a later manifest build
resolves those logical ids to physical ones and ships them under the
``nfl2k5.`` namespace the audit tool already permits, they will map here with
no change to this file: lookup is always by exact string.

Geometry
--------

A PCSX2 replacement name ends in ``-%08x``, the packed texture-property word
``bits = PSM | TW << 6 | TH << 10 | TCC << 14``. ``TW``/``TH`` are log2 sizes,
so the PS2 native geometry is ``(2 ** TW, 2 ** TH)``. Where the user's PNG has
a different *aspect* from that, the art is resampled to the PS2 aspect and the
original size is recorded in the receipt as ``resampled_from``. PCSX2 scales
any replacement size, so only the aspect matters; 2,521 names differ in
geometry between the two platforms.

Pillow does the resample and is imported lazily, so this module stays
importable -- and every test that does not resample stays runnable -- on an
interpreter without it.

Publishing
----------

The pack is built in a temporary sibling of the destination and published with
``platform_compat.publish_no_replace``. Not ``mkdir`` + ``os.rename``: that
sequence is POSIX-only and failed on every Windows folder export until beta-11,
because Windows cannot rename a directory onto an existing one. An existing
destination is refused, never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from uuid import uuid4
import zipfile

from mod_editor.core import platform_compat
from mod_editor.core.errors import ValidationError


#: The receipt this module writes, and the file it writes it to.
RECEIPT_SCHEMA = "nfl2k5_ps2_export_receipt/v1"
RECEIPT_NAME = "nfl2k5-ps2-export-receipt.v1.json"

#: The shipped manifest this module consumes. Both names are also spelled out
#: in ``tools/nfl2k5_ps2_replacement_pack_audit.py``; they must agree, and the
#: tests assert that they do.
MAPPING_SCHEMA = "nfl2k5_ps2_to_xbox_texture_map/v1"
MAPPING_MANIFEST = "nfl2k5-xbox-map.v1.json"

SERIAL = "SLUS-20919"
#: Where PCSX2 looks, relative to the pack root the user drops in.
REPLACEMENTS_DIR = ("textures", SERIAL, "replacements")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = ROOT / "mod_editor" / "data" / MAPPING_MANIFEST

#: The provenance block copied verbatim from the manifest into the receipt, so
#: a pack can be traced to the disc, emulator build and method that produced
#: the hashes in its filenames. The verifier compares these key-for-key.
PROVENANCE_KEYS = ("disc", "emulator", "method", "generated", "counts")

#: Studio asset-id namespaces that ARE Xbox asset ids. See the module docstring.
PHYSICAL_NAMESPACES = ("p8:", "tset:", "nfl2k5.crib.scene.")
#: The logical uniform provider namespace, which is not one. Also see there.
LOGICAL_UNIFORM_NAMESPACE = "nfl2k5.uniform."

STATUS_MAPPED = "mapped"
STATUS_UNMAPPED = "unmapped"
STATUS_AMBIGUOUS = "ambiguous"

# The canonical PCSX2 replacement-name shape. Restated here rather than
# imported from the audit tool: this module is shipped product code and the
# audit tool is a dev-time script, and the two are tested against each other
# instead of sharing a definition. PCSX2's 64-bit fields print through %llx,
# which is NOT zero padded, so a hash whose top nibble is zero prints fewer
# than 16 digits -- demanding 16 throws away 10% of a real pack.
_HASH64 = r"[0-9a-f]{1,16}"
_PROPS32 = r"[0-9a-f]{8}"
_DECIMAL = r"[0-9]{1,5}"
PCSX2_HASH_NAME = re.compile(
    r"^" + _HASH64
    + r"(?:-" + _HASH64 + r")?"
    + r"(?:-r(?:" + _DECIMAL + r"x" + _DECIMAL + r"|" + _HASH64 + r"))?"
    + r"-" + _PROPS32
    + r"(?:-mip" + _DECIMAL + r")?"
    + r"\.(?i:png)$",
    re.ASCII,
)
#: The trailing property word, which carries the PS2 native geometry.
_PROPS_TAIL = re.compile(r"-(" + _PROPS32 + r")(?:-mip" + _DECIMAL + r")?\.png$",
                         re.ASCII | re.IGNORECASE)

MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_PROJECT_BYTES = 2 * 1024 * 1024 * 1024
MAX_EXPORT_FILES = 100_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Ps2ExportError(ValidationError):
    """A project, manifest, plan or destination is unfit for export."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Ps2ExportError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    """Bytes, not text: it sidesteps the platform newline question entirely."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    """Create ``path`` exclusively and durably, refusing a link or a clobber."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
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


def _read_regular_bytes(path: Path, label: str, maximum: int) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise Ps2ExportError(f"{label} cannot be read: {path}") from exc
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             f"{label} must be a regular file, not a folder or link: {path}")
    _require(info.st_size <= maximum, f"{label} is larger than its safe bound: {path}")
    return path.read_bytes()


# --------------------------------------------------------------------------
# PNG geometry, read from the IHDR alone.
#
# Reading 33 bytes is enough to learn a PNG's size, so planning never needs
# Pillow and never decodes a pixel. Only an actual resample does.
# --------------------------------------------------------------------------

def png_dimensions(payload: bytes, label: str = "replacement PNG") -> Tuple[int, int]:
    """``(width, height)`` from a PNG's IHDR, without decoding pixels."""

    _require(
        len(payload) >= 33
        and payload[:8] == PNG_SIGNATURE
        and payload[12:16] == b"IHDR",
        f"{label} is not a PNG with a valid IHDR",
    )
    width, height = struct.unpack_from(">II", payload, 16)
    _require(0 < width <= 16_384 and 0 < height <= 16_384,
             f"{label} dimensions are outside the safe bound")
    return int(width), int(height)


def native_size_from_name(pcsx2_png: str) -> Optional[Tuple[int, int]]:
    """The PS2 native ``(width, height)`` a replacement filename implies.

    The trailing ``%08x`` is ``PSM | TW << 6 | TH << 10 | TCC << 14``, and
    ``TW``/``TH`` are log2 sizes. Returns ``None`` when the name carries no
    readable property word, which the caller treats as "cannot check the
    aspect" rather than as a failure.
    """

    match = _PROPS_TAIL.search(pcsx2_png)
    if match is None:
        return None
    bits = int(match.group(1), 16)
    width_log2 = (bits >> 6) & 0xF
    height_log2 = (bits >> 10) & 0xF
    return (1 << width_log2), (1 << height_log2)


def _same_aspect(source: Tuple[int, int], native: Tuple[int, int]) -> bool:
    """Aspect equality by cross-multiplication, so no float ever decides this."""

    return source[0] * native[1] == native[0] * source[1]


def _resample(payload: bytes, native: Tuple[int, int]) -> bytes:
    """Resample ``payload`` to ``native``. Pillow is imported only here.

    Keeping the import inside the call is what lets this module be imported --
    and most of its tests run -- on an interpreter without Pillow. The GUI
    already depends on it, so a real export in the studio always has it.
    """

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - exercised by the skip path
        raise Ps2ExportError(
            "Pillow is required to resample a replacement to the PS2 aspect. "
            "Install Pillow, or supply art already at the PS2 aspect."
        ) from exc
    import io

    with Image.open(io.BytesIO(payload)) as image:
        converted = image.convert("RGBA")
        resized = converted.resize(native, Image.LANCZOS)
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")
    return buffer.getvalue()


def pillow_available() -> bool:
    """Whether a resample can run here, asked without importing Pillow twice."""

    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------
# The project side: only edited targets, and nothing else, ever enter here.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ExportTarget:
    """One edited target and the user's replacement PNG bytes for it.

    ``target_id`` is the studio's own name for the target; ``xbox_asset_id`` is
    what the manifest is keyed by. They are equal for every physical namespace
    and differ only for the logical uniform provider ids -- see the module
    docstring's table.
    """

    target_id: str
    payload: bytes
    label: str = ""

    @property
    def xbox_asset_id(self) -> str:
        return self.target_id

    @property
    def is_physical_asset_id(self) -> bool:
        return self.target_id.startswith(PHYSICAL_NAMESPACES)

    @property
    def is_logical_uniform_id(self) -> bool:
        return self.target_id.startswith(LOGICAL_UNIFORM_NAMESPACE)


@dataclass(frozen=True)
class ExportProject:
    """The edited targets of one Xbox project. Unedited targets are absent.

    This type is the enforcement point for the hard rule. It carries no
    catalog, no disc handle and no source cache, so there is nothing for an
    export to read an unedited texture *from*.
    """

    targets: Tuple[ExportTarget, ...]
    source: str = ""

    @property
    def edited_target_ids(self) -> frozenset:
        return frozenset(item.target_id for item in self.targets)


def project_from_targets(
    targets: Iterable[Any], source: str = ""
) -> ExportProject:
    """Build a project from ``(target_id, png_bytes)`` pairs or ``ExportTarget``."""

    rows: List[ExportTarget] = []
    seen = set()
    for entry in targets:
        if isinstance(entry, ExportTarget):
            target = entry
        else:
            target_id, payload = entry[0], entry[1]
            label = entry[2] if len(entry) > 2 else ""
            target = ExportTarget(str(target_id), bytes(payload), str(label))
        _require(bool(target.target_id), "An edited target must have an id")
        _require(target.target_id not in seen,
                 f"Duplicate edited target: {target.target_id}")
        seen.add(target.target_id)
        png_dimensions(target.payload, f"replacement for {target.target_id}")
        rows.append(target)
    return ExportProject(tuple(sorted(rows, key=lambda row: row.target_id)), source)


def project_from_archive(path: Path) -> ExportProject:
    """Read the edited targets out of a saved ``.2k5mod`` project archive.

    The archive is the shareable, versioned form of exactly the thing this
    module needs: ``payload_policy: "user-replacements-only"``, one manifest row
    per edit naming its ``asset_id`` and the member holding the user's PNG. Its
    writer already refused any edit that matched the retail original, so every
    row here is user-authored pixels.

    Only the visual ``edits`` are read. Audio, text, colour and playbook edits
    in the same archive are not textures and are silently none of this module's
    business.
    """

    archive_path = Path(path)
    info = archive_path.lstat()
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             f"A project must be a regular file, not a folder or link: {archive_path}")
    _require(info.st_size <= MAX_PROJECT_BYTES,
             f"That project is larger than its safe bound: {archive_path}")
    targets: List[ExportTarget] = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            try:
                manifest_bytes = archive.read("manifest.json")
            except KeyError as exc:
                raise Ps2ExportError(
                    f"That project has no manifest: {archive_path}"
                ) from exc
            document = json.loads(manifest_bytes.decode("utf-8"))
            _require(isinstance(document, dict), "That project manifest is not an object")
            edits = document.get("edits")
            _require(isinstance(edits, list), "That project manifest has no edit list")
            for number, row in enumerate(edits, 1):
                _require(isinstance(row, dict), f"Project edit {number} is not an object")
                asset_id = row.get("asset_id")
                member = row.get("file")
                _require(isinstance(asset_id, str) and bool(asset_id),
                         f"Project edit {number} has no asset id")
                _require(isinstance(member, str) and bool(member),
                         f"Project edit {number} has no payload member")
                pure = PurePosixPath(member)
                _require(
                    not pure.is_absolute()
                    and member == pure.as_posix()
                    and all(part not in {"", ".", ".."} for part in pure.parts),
                    f"Project edit {number} names an unsafe member: {member}",
                )
                try:
                    entry = archive.getinfo(member)
                except KeyError as exc:
                    raise Ps2ExportError(
                        f"Project edit {number} names a missing member: {member}"
                    ) from exc
                _require(entry.file_size <= MAX_PNG_BYTES,
                         f"Project edit {number} payload is larger than its safe bound")
                payload = archive.read(member)
                recorded = row.get("png_sha256")
                if isinstance(recorded, str) and recorded:
                    _require(
                        _sha256_bytes(payload) == recorded,
                        f"Project edit {number} payload does not match its recorded "
                        f"digest: {asset_id}",
                    )
                targets.append(ExportTarget(asset_id, payload))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        if isinstance(exc, Ps2ExportError):
            raise
        raise Ps2ExportError(f"That project cannot be read: {archive_path}: {exc}") from exc
    return project_from_targets(targets, source=archive_path.name)


def project_from_session(session: Any) -> ExportProject:
    """Adapt a live ``StudioSession`` (or facade) without importing the studio.

    Deliberately duck-typed and read-only. The studio's edit map is private
    state that no exporter should reach into by name from outside, so this asks
    only for what the session already publishes: which ids are modified, and
    where the staged replacement for one lives. It never touches
    ``facade.py``, which another work package owns.
    """

    modified = getattr(session, "modified_asset_ids", None)
    _require(modified is not None,
             "That object does not look like a Mod Studio session")
    resolve = (
        getattr(session, "export_target_payload", None)
        or getattr(session, "replacement_payload", None)
    )
    edits = getattr(session, "visual_edits", None)
    targets: List[ExportTarget] = []
    for asset_id in sorted(str(value) for value in modified):
        payload = None
        if callable(resolve):
            payload = resolve(asset_id)
        elif isinstance(edits, Mapping) and asset_id in edits:
            staged = edits[asset_id]
            source = getattr(staged, "replacement_path", staged)
            payload = _read_regular_bytes(
                Path(source), f"replacement for {asset_id}", MAX_PNG_BYTES
            )
        if payload is None:
            # Text, audio and colour edits share ``modified_asset_ids`` with
            # the visual ones and have no PNG. They are not texture targets;
            # skipping them here is correct, not a loss.
            continue
        targets.append(ExportTarget(asset_id, bytes(payload)))
    return project_from_targets(targets, source=str(getattr(session, "session_id", "")))


def load_project(source: Any) -> ExportProject:
    """Coerce whatever the caller has into an :class:`ExportProject`."""

    if isinstance(source, ExportProject):
        return source
    if isinstance(source, (str, os.PathLike)):
        return project_from_archive(Path(source))
    return project_from_session(source)


# --------------------------------------------------------------------------
# The manifest side.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Manifest:
    """The shipped PCSX2-to-Xbox map, indexed for lookup."""

    by_asset: Mapping[str, Tuple[str, ...]]
    claimants: Mapping[str, Tuple[str, ...]]
    provenance: Mapping[str, Any]
    sha256: str
    document: Mapping[str, Any]
    #: The manifest's own bytes, so the copy dropped beside a pack is verbatim
    #: and hashes to ``sha256``. Re-serializing would produce a copy whose
    #: digest did not match the one the receipt records for the shipped file.
    raw: bytes = b""
    path: Optional[Path] = None

    @property
    def entry_count(self) -> int:
        return sum(len(names) for names in self.by_asset.values())


def load_manifest(source: Any = None) -> Manifest:
    """Load and validate the mapping manifest.

    Accepts the shipped path (the default), any other path, an already-parsed
    document, or a :class:`Manifest` to pass straight through.
    """

    if isinstance(source, Manifest):
        return source
    path: Optional[Path] = None
    if source is None:
        path = DEFAULT_MANIFEST_PATH
    elif isinstance(source, (str, os.PathLike)):
        path = Path(source)
    if path is not None:
        payload = _read_regular_bytes(path, "The mapping manifest", MAX_MANIFEST_BYTES)
        digest = _sha256_bytes(payload)
        try:
            # utf-8-sig, matching the audit tool: a manifest that has been
            # through a Windows pack manager can carry a BOM, which json
            # rejects as a stray character.
            document = json.loads(payload.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise Ps2ExportError(f"The mapping manifest is not valid JSON: {path}") from exc
    else:
        _require(isinstance(source, Mapping), "A mapping manifest must be a JSON object")
        document = dict(source)
        payload = _canonical_json(document)
        digest = _sha256_bytes(payload)

    _require(isinstance(document, dict), "A mapping manifest must be a JSON object")
    _require(document.get("schema") == MAPPING_SCHEMA,
             f"The mapping manifest schema must be {MAPPING_SCHEMA}")
    entries = document.get("entries")
    _require(isinstance(entries, list), "The mapping manifest has no entry list")

    by_asset: Dict[str, List[str]] = {}
    claimants: Dict[str, List[str]] = {}
    for number, row in enumerate(entries):
        _require(
            isinstance(row, dict)
            and set(row) == {"pcsx2_png", "xbox_asset_id"}
            and isinstance(row["pcsx2_png"], str)
            and isinstance(row["xbox_asset_id"], str)
            and bool(row["pcsx2_png"])
            and row["xbox_asset_id"].startswith(("p8:", "tset:", "nfl2k5.")),
            f"Mapping manifest entry {number} is invalid",
        )
        name = row["pcsx2_png"]
        asset_id = row["xbox_asset_id"]
        _require(PCSX2_HASH_NAME.fullmatch(name) is not None,
                 f"Mapping manifest entry {number} is not a canonical PCSX2 name: {name}")
        names = by_asset.setdefault(asset_id, [])
        if name not in names:
            names.append(name)
        owners = claimants.setdefault(name, [])
        if asset_id not in owners:
            owners.append(asset_id)
    provenance = {key: document[key] for key in PROVENANCE_KEYS if key in document}
    return Manifest(
        by_asset={key: tuple(value) for key, value in by_asset.items()},
        claimants={key: tuple(value) for key, value in claimants.items()},
        provenance=provenance,
        sha256=digest,
        document=document,
        raw=payload,
        path=path,
    )


# --------------------------------------------------------------------------
# Planning.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PlannedFile:
    """One PCSX2 file the export will write."""

    pcsx2_png: str
    xbox_asset_id: str
    source_target: str
    payload: bytes
    native_size: Optional[Tuple[int, int]]
    source_size: Tuple[int, int]

    @property
    def needs_resample(self) -> bool:
        return (
            self.native_size is not None
            and not _same_aspect(self.source_size, self.native_size)
        )

    @property
    def relative_path(self) -> str:
        return "/".join(REPLACEMENTS_DIR + (self.pcsx2_png,))


@dataclass(frozen=True)
class PlanEntry:
    """One edited target's fate: mapped to N names, or skipped with a reason."""

    target_id: str
    xbox_asset_id: str
    status: str
    pcsx2_pngs: Tuple[str, ...] = ()
    reason: str = ""

    @property
    def is_mapped(self) -> bool:
        return self.status == STATUS_MAPPED


@dataclass(frozen=True)
class ExportPlan:
    """What an export would write, and what it would skip and why."""

    entries: Tuple[PlanEntry, ...]
    files: Tuple[PlannedFile, ...]
    provenance: Mapping[str, Any]
    manifest_sha256: str
    manifest_document: Mapping[str, Any]
    #: The manifest's own bytes, copied into the pack verbatim.
    manifest_raw: bytes = b""
    project_source: str = ""

    @property
    def mapped(self) -> Tuple[PlanEntry, ...]:
        return tuple(row for row in self.entries if row.is_mapped)

    @property
    def skipped(self) -> Tuple[PlanEntry, ...]:
        return tuple(row for row in self.entries if not row.is_mapped)

    @property
    def file_count(self) -> int:
        return len(self.files)


def plan_export(project: Any, manifest: Any = None) -> ExportPlan:
    """Decide, without writing anything, what this project exports to PCSX2.

    Every planned file traces to a target the project lists as edited. A target
    the manifest cannot name is skipped with a reason, never guessed at.
    """

    resolved_project = load_project(project)
    resolved_manifest = load_manifest(manifest)

    entries: List[PlanEntry] = []
    files: List[PlannedFile] = []
    claimed: Dict[str, str] = {}

    for target in resolved_project.targets:
        asset_id = target.xbox_asset_id
        names = resolved_manifest.by_asset.get(asset_id, ())
        if not names:
            if target.is_logical_uniform_id:
                reason = (
                    "this is a logical uniform provider target, not a disc "
                    "texture; it has no GS hash until the manifest resolves it "
                    "to a physical p8:/tset: id"
                )
            elif not target.is_physical_asset_id:
                reason = (
                    "the target id is in no namespace the manifest can carry"
                )
            else:
                reason = "no manifest row maps this Xbox asset to a PCSX2 name"
            entries.append(PlanEntry(target.target_id, asset_id, STATUS_UNMAPPED,
                                     reason=reason))
            continue

        contested = [
            name for name in names
            if len(resolved_manifest.claimants.get(name, ())) > 1
        ]
        if contested:
            entries.append(PlanEntry(
                target.target_id, asset_id, STATUS_AMBIGUOUS, tuple(names),
                reason=(
                    "the manifest lets more than one Xbox asset claim "
                    + ", ".join(sorted(contested))
                    + "; the file it would write is not uniquely attributable"
                ),
            ))
            continue

        collision = [name for name in names if name in claimed]
        if collision:
            entries.append(PlanEntry(
                target.target_id, asset_id, STATUS_AMBIGUOUS, tuple(names),
                reason=(
                    "another edited target in this project already writes "
                    + ", ".join(sorted(collision))
                ),
            ))
            continue

        source_size = png_dimensions(
            target.payload, f"replacement for {target.target_id}"
        )
        for name in names:
            claimed[name] = target.target_id
            files.append(PlannedFile(
                pcsx2_png=name,
                xbox_asset_id=asset_id,
                source_target=target.target_id,
                payload=target.payload,
                native_size=native_size_from_name(name),
                source_size=source_size,
            ))
        entries.append(PlanEntry(target.target_id, asset_id, STATUS_MAPPED,
                                 tuple(names)))

    _require(len(files) <= MAX_EXPORT_FILES,
             "This export would write more files than the safe bound allows")
    return ExportPlan(
        entries=tuple(entries),
        files=tuple(files),
        provenance=dict(resolved_manifest.provenance),
        manifest_sha256=resolved_manifest.sha256,
        manifest_document=resolved_manifest.document,
        manifest_raw=resolved_manifest.raw,
        project_source=resolved_project.source,
    )


# --------------------------------------------------------------------------
# Writing.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ReceiptFile:
    path: str
    sha256: str
    xbox_asset_id: str
    pcsx2_png: str
    source_target: str
    resampled_from: Optional[List[int]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "pcsx2_png": self.pcsx2_png,
            "resampled_from": self.resampled_from,
            "sha256": self.sha256,
            "source_target": self.source_target,
            "xbox_asset_id": self.xbox_asset_id,
        }


@dataclass(frozen=True)
class ExportReceipt:
    path: Path
    files: Tuple[ReceiptFile, ...]
    skipped: Tuple[Dict[str, str], ...]
    provenance: Mapping[str, Any]
    document: Mapping[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def message(self) -> str:
        return (
            "Wrote {files} PCSX2 replacement file{plural} from {targets} edited "
            "target{tplural}; skipped {skipped}. Copy the textures/ folder into "
            "PenguinScreen2's texture directory and enable Load Textures.".format(
                files=len(self.files),
                plural="" if len(self.files) == 1 else "s",
                targets=len({row.source_target for row in self.files}),
                tplural="" if len({row.source_target for row in self.files}) == 1 else "s",
                skipped=len(self.skipped),
            )
        )


def _refuse_destination(out_dir: Path) -> Path:
    requested = Path(out_dir).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.abspath(os.fspath(requested)))
    # lexists, not exists: a dangling symlink at the destination still occupies
    # the name, and publishing "through" it is exactly what must not happen.
    _require(not os.path.lexists(requested),
             f"A file or folder already exists there: {requested}")
    parent = requested.parent
    _require(parent.is_dir() and not parent.is_symlink(),
             f"The destination's parent folder is missing or is a link: {parent}")
    return requested


def run_export(plan: ExportPlan, out_dir: Path) -> ExportReceipt:
    """Write ``plan``'s files to a new folder and return the receipt.

    The folder is built under a temporary sibling name and published with the
    platform layer's no-clobber primitive, so a destination that appears while
    the export runs is refused rather than overwritten.
    """

    _require(isinstance(plan, ExportPlan), "run_export needs a plan from plan_export")
    requested = _refuse_destination(out_dir)

    stage = Path(tempfile.mkdtemp(
        prefix=".{name}.ps2-export-{token}-".format(
            name=requested.name, token=uuid4().hex
        ),
        dir=str(requested.parent),
    ))
    published = False
    try:
        rows: List[ReceiptFile] = []
        for planned in plan.files:
            payload = planned.payload
            resampled_from: Optional[List[int]] = None
            if planned.needs_resample:
                payload = _resample(payload, planned.native_size)
                resampled_from = [planned.source_size[0], planned.source_size[1]]
            destination = stage.joinpath(*REPLACEMENTS_DIR, planned.pcsx2_png)
            _write_new(destination, payload)
            rows.append(ReceiptFile(
                path=planned.relative_path,
                sha256=_sha256_bytes(payload),
                xbox_asset_id=planned.xbox_asset_id,
                pcsx2_png=planned.pcsx2_png,
                source_target=planned.source_target,
                resampled_from=resampled_from,
            ))

        skipped = tuple(
            {"target": row.target_id, "status": row.status, "reason": row.reason}
            for row in plan.skipped
        )
        receipt_document: Dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "serial": SERIAL,
            "exported": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "replacements_directory": "/".join(REPLACEMENTS_DIR),
            "mapping_manifest": {
                "file": MAPPING_MANIFEST,
                "sha256": plan.manifest_sha256,
            },
            "counts": {
                "files": len(rows),
                "resampled": sum(1 for row in rows if row.resampled_from),
                "skipped": len(skipped),
                "targets": len({row.source_target for row in rows}),
            },
            "files": [row.as_dict() for row in rows],
            "skipped": list(skipped),
            # Verbatim, so a pack can be traced to the disc and emulator build
            # whose hash convention produced its filenames.
            "provenance": dict(plan.provenance),
        }
        _write_new(stage / RECEIPT_NAME, _canonical_json(receipt_document))
        # The audit tool reports ``xbox_mapping_ready`` only when the pack
        # carries the source-owned manifest beside it, so the pack ships one.
        # It is hashes and names, never pixels. The copy is byte-verbatim, so
        # it hashes to the digest the receipt records for the shipped file --
        # re-serializing would produce a copy whose digest did not match.
        _write_new(
            stage / MAPPING_MANIFEST,
            plan.manifest_raw or _canonical_json(plan.manifest_document),
        )

        try:
            # require_atomic=False keeps the two-step reserve available on the
            # exotic POSIX filesystems that offer neither renameat2 nor
            # RENAME_EXCL, exactly as the Team Kit folder export does.
            platform_compat.publish_no_replace(
                str(stage), str(requested), is_directory=True, require_atomic=False
            )
        except FileExistsError as exc:
            raise Ps2ExportError(
                f"A file or folder already exists there: {requested}"
            ) from exc
        published = True
    finally:
        if not published:
            shutil.rmtree(stage, ignore_errors=True)

    return ExportReceipt(
        path=requested,
        files=tuple(rows),
        skipped=skipped,
        provenance=dict(plan.provenance),
        document=receipt_document,
    )


def export_replacement_pack(
    project: Any, out_dir: Path, manifest: Any = None
) -> ExportReceipt:
    """Plan and write in one call, for a caller with nothing to preview."""

    return run_export(plan_export(project, manifest), out_dir)


__all__ = [
    "ExportPlan",
    "ExportProject",
    "ExportReceipt",
    "ExportTarget",
    "Manifest",
    "MAPPING_MANIFEST",
    "MAPPING_SCHEMA",
    "PlanEntry",
    "PlannedFile",
    "Ps2ExportError",
    "RECEIPT_NAME",
    "RECEIPT_SCHEMA",
    "REPLACEMENTS_DIR",
    "SERIAL",
    "STATUS_AMBIGUOUS",
    "STATUS_MAPPED",
    "STATUS_UNMAPPED",
    "export_replacement_pack",
    "load_manifest",
    "load_project",
    "native_size_from_name",
    "pillow_available",
    "plan_export",
    "png_dimensions",
    "project_from_archive",
    "project_from_session",
    "project_from_targets",
    "run_export",
]
