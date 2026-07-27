"""Read-only source inspection and exact-hash recognition."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sys
from typing import Callable, Iterable

from .errors import ValidationError
from .model import GameId, SourceRecord


def _xdvdfs_module():
    """The XDVDFS reader, imported the way the rest of core imports tools/."""
    tools = str(Path(__file__).resolve().parents[2] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import nfl_uniform_color_xiso_direct_patch as module
    except ImportError:  # pragma: no cover - lean checkouts without tools/
        return None
    return module


HashProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class KnownFingerprint:
    fingerprint_id: str
    game: GameId
    kind: str
    sha256: str
    note: str


KNOWN_FINGERPRINTS: tuple[KnownFingerprint, ...] = (
    KnownFingerprint(
        "nfl2k5-usa-retail-xiso",
        GameId.NFL2K5,
        "xiso",
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
        "Known project research copy of the USA retail XISO.",
    ),
    KnownFingerprint(
        "nfl2k5-usa-default-xbe",
        GameId.NFL2K5,
        "xbe",
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        "Known extracted USA retail default.xbe.",
    ),
    KnownFingerprint(
        "nfl2k5-usa-retail-ps2-iso",
        GameId.NFL2K5_PS2,
        "ps2-iso",
        "f1300699ab445ad04b1e27f6e2df87f7a4d1d080d06c7d73499e1be9618a4ebe",
        "Known USA retail PS2 ISO (SLUS-20919, NTSC-U v1.01, redump-verified).",
    ),
    KnownFingerprint(
        "nfl2k5-usa-ps2-boot-elf",
        GameId.NFL2K5_PS2,
        "ps2-elf",
        "e8c3ba9a3224d567e3abb50c91e9d6fdd9820138226c05e525f9dbf34a47d8aa",
        "Known extracted USA retail PS2 boot ELF SLUS_209.19.",
    ),
    KnownFingerprint(
        "apf2k8-usa-default-xex",
        GameId.APF2K8,
        "xex2",
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        "Known extracted USA retail default.xex.",
    ),
    KnownFingerprint(
        "apf2k8-usa-volume-0a",
        GameId.APF2K8,
        "apf-volume-0a",
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
        "Known APF 2K8 archive volume 0A used by the proved texture writer.",
    ),
)


@dataclass(frozen=True)
class ContainedFingerprint:
    """Identify a disc image by a file INSIDE it rather than by the container.

    A dump of an Xbox disc is not one canonical file. Where the game partition
    starts, whether trailing padding is kept, and how the ripper closed the
    image all change the whole-file SHA-256 without changing one byte of the
    game. Pinning the container therefore rejected other people's perfectly
    legal dumps -- the defect this exists to fix.

    What does not vary is the executable. ``default.xbe`` is the game, and its
    hash answers "is this the USA retail revision?" far better than the size of
    the file someone wrapped it in. Nothing here is weaker: the writers still
    verify the exact extents they touch, and the source cache still refuses
    unless the extracted archive packs hash to their pinned values.
    """

    fingerprint_id: str
    game: GameId
    kind: str
    contained_path: str
    sha256: str
    size: int
    note: str


CONTAINED_FINGERPRINTS: tuple[ContainedFingerprint, ...] = (
    ContainedFingerprint(
        "nfl2k5-usa-retail-xiso",
        GameId.NFL2K5,
        "xiso",
        "default.xbe",
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        11_948_032,
        "USA retail NFL 2K5 identified by its default.xbe, not by the container.",
    ),
)


def contained_identity(path: Path) -> ContainedFingerprint | None:
    """Recognize a disc image by hashing the executable inside it.

    Returns None for anything that is not an Xbox disc image or whose
    executable is not one we have pinned; callers treat that as unrecognized
    exactly as before.
    """
    xiso = _xdvdfs_module()
    if xiso is None:
        return None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
    except OSError:
        return None
    try:
        size = os.fstat(descriptor).st_size
        try:
            base = xiso.locate_xdvdfs_base(descriptor, size)
            entries, _ = xiso.parse_xdvdfs(descriptor, size, base)
        except Exception:  # noqa: BLE001 - simply not a disc image we can read
            return None
        for row in CONTAINED_FINGERPRINTS:
            entry = entries.get(row.contained_path.casefold())
            if entry is None or entry.size != row.size:
                continue
            digest = hashlib.sha256()
            remaining = entry.size
            offset = entry.byte_offset
            while remaining:
                chunk = xiso.read_exact(descriptor, offset, min(4 << 20, remaining))
                if not chunk:
                    return None
                digest.update(chunk)
                offset += len(chunk)
                remaining -= len(chunk)
            if digest.hexdigest() == row.sha256:
                return row
        return None
    finally:
        os.close(descriptor)


def sha256_file(path: Path, progress: HashProgress | None = None) -> tuple[str, int]:
    """Hash a regular file through a read-only handle."""

    if not path.is_file():
        raise ValidationError(f"Source is not a regular file: {path}")
    size = path.stat().st_size
    digest = hashlib.sha256()
    completed = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            completed += len(chunk)
            if progress:
                progress(completed, size)
    return digest.hexdigest(), size


class SourceInspector:
    def __init__(self, fingerprints: Iterable[KnownFingerprint] = KNOWN_FINGERPRINTS):
        self._fingerprints = tuple(fingerprints)

    def inspect(
        self,
        selected_path: Path,
        expected_game: GameId | None = None,
        progress: HashProgress | None = None,
    ) -> SourceRecord:
        selected = selected_path.expanduser().resolve(strict=True)
        inspected = self._select_inspection_file(selected, expected_game)
        digest, size = sha256_file(inspected, progress)
        match = next((row for row in self._fingerprints if row.sha256 == digest), None)
        if match:
            note = match.note
            if expected_game is not None and match.game != expected_game:
                note = f"GAME MISMATCH: expected {expected_game.value}; {note}"
            return SourceRecord(
                selected_path=str(selected),
                inspected_path=str(inspected),
                kind=match.kind,
                sha256=digest,
                size=size,
                recognized=True,
                fingerprint_id=match.fingerprint_id,
                detected_game=match.game.value,
                note=note,
            )
        # The container hash missed. Before refusing, ask the only question that
        # actually matters: is the RIGHT GAME inside this file? Dumps of one disc
        # legitimately differ in where the game partition starts and how much
        # padding is kept, so a container miss is not evidence of a wrong game.
        contained = contained_identity(inspected)
        if contained is not None:
            note = contained.note
            if expected_game is not None and contained.game != expected_game:
                note = f"GAME MISMATCH: expected {expected_game.value}; {note}"
            return SourceRecord(
                selected_path=str(selected),
                inspected_path=str(inspected),
                kind=contained.kind,
                sha256=digest,
                size=size,
                recognized=True,
                fingerprint_id=contained.fingerprint_id,
                detected_game=contained.game.value,
                note=note,
            )
        return SourceRecord(
            selected_path=str(selected),
            inspected_path=str(inspected),
            kind=self._guess_kind(inspected),
            sha256=digest,
            size=size,
            recognized=False,
            note=(
                "Hash is not in the reviewed fingerprint list. The editor will not call a "
                "binary writer for this source until a capability-specific verifier accepts it."
            ),
        )

    @staticmethod
    def _select_inspection_file(selected: Path, expected_game: GameId | None) -> Path:
        if selected.is_file():
            return selected
        if not selected.is_dir():
            raise ValidationError(f"Source path must be a file or directory: {selected}")
        preferred = "default.xbe" if expected_game == GameId.NFL2K5 else "default.xex"
        entries = {entry.name.lower(): entry for entry in selected.iterdir() if entry.is_file()}
        if preferred in entries:
            return entries[preferred]
        for name in ("default.xex", "default.xbe", "0a"):
            if name in entries:
                return entries[name]
        raise ValidationError(
            "Selected directory has no root-level default.xex, default.xbe, or APF volume 0A"
        )

    @staticmethod
    def _guess_kind(path: Path) -> str:
        name = path.name.lower()
        if name.endswith(".xbe"):
            return "xbe"
        if name.endswith(".xex"):
            return "xex2"
        if name.endswith(".iso") or ".xiso" in name:
            return "disc-image"
        if name == "0a":
            return "apf-volume-0a"
        return "unknown-file"
