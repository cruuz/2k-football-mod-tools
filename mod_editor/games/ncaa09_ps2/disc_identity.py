"""Which NCAA Football 09 (PlayStation 2) disc image this is.

One image is known: the USA retail release, ``SLUS-21752``.  Unlike Madden 09
there is no community rebuild of this disc in this project's reach, so the
identifier names one boot-ELF digest and says ``unknown edition`` about anything
else rather than refusing it -- every lane in this module is read-only, so
nothing is risked by listing a re-cut, and nothing is claimed about it either.

The shared :class:`mod_editor.games._formats.ps2_disc.Ps2DiscIdentifier` gets the
ISO9660 volume, ``SYSTEM.CNF`` and the boot ELF digest; this file adds the
edition.

**This studio reads two kinds of source, not one.**  Every lane but one works
off the disc; the Saves page works off the memory-card draft class NCAA
Football writes for Madden, which is not a disc image and never was.  So the
identifier recognises that file too -- by its exact length and its four-byte
header -- and says which of the two it was handed, rather than refusing a real
NCAA Football 09 artefact because it is not an ISO.

Read-only: the image is opened for reading and never written.

**Evidence tags.**  **[M]** measured on the disc this box holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mod_editor.games._formats.ps2_disc import ACCEPTED_SUFFIXES, Ps2DiscIdentifier
from mod_editor.games.contract import GameIdentity, Refusal, SourceIdentity

from . import containers
from .saves_lane import FILE_BYTES as CLASS_BYTES, MAGIC as CLASS_MAGIC, SAVE_DIRECTORY

#: The one image this module knows, by boot-ELF digest [M].  A digest is the
#: honest key: a serial says which game, not which build.
EDITIONS: Dict[str, Dict[str, str]] = {
    containers.RETAIL_BOOT_ELF_SHA256: {
        "edition": containers.RETAIL_EDITION,
        "name": "retail",
        "elf_crc": containers.RETAIL_ELF_CRC,
        "image_sha256": containers.RETAIL_IMAGE_SHA256,
    },
}

#: What a headline says about a disc whose boot ELF is not the one above.  It is
#: a statement, not a failure.
UNKNOWN_EDITION = "unknown edition"

#: What :meth:`Ncaa09DiscIdentifier.identify` calls a draft-class save.
DRAFT_CLASS_KIND = "ncaa-draft-class"

#: The suffixes a chooser offers.  The disc's, plus the two a class save is
#: usually saved under once a container tool has unpacked it.
CLASS_SUFFIXES = (".bin", ".dat")


class Ncaa09DiscIdentifier:
    """Say whether this is the NCAA Football 09 PlayStation 2 disc."""

    accepted_suffixes = tuple(ACCEPTED_SUFFIXES) + tuple(
        suffix for suffix in CLASS_SUFFIXES if suffix not in ACCEPTED_SUFFIXES)

    def __init__(self, identity: GameIdentity) -> None:
        self.identity = identity
        self._base = Ps2DiscIdentifier(identity)

    @staticmethod
    def _identify_draft_class(path: Path) -> Optional[SourceIdentity]:
        """The Saves page's source, recognised, or ``None`` for everything else.

        A draft class is not a disc and has no serial or boot ELF, so
        ``serial_matches`` is True on the strength of what it *is* -- an NCAA
        Football artefact this studio reads -- and ``retail_executable`` is
        False, because there is no executable in it to be retail.
        """

        if not _is_draft_class_file(path):
            return None
        return SourceIdentity(
            kind=DRAFT_CLASS_KIND,
            path=str(path),
            size_bytes=CLASS_BYTES,
            serial=None,
            executable_sha256=None,
            serial_matches=True,
            retail_executable=False,
            headline=f"{path.name} — NCAA Football send-to-Madden draft class · "
                     f"{CLASS_BYTES:,} bytes · 1,600 records",
            details={"edition": "draft-class save",
                     "save_directory": SAVE_DIRECTORY,
                     "note": "The Saves page reads this; every other page reads the disc."},
        )

    def identify(self, path: Path) -> SourceIdentity:
        class_identity = self._identify_draft_class(Path(path))
        if class_identity is not None:
            return class_identity
        base = self._base.identify(Path(path))
        if not base.serial_matches:
            expected = ", ".join(self.identity.serials) or "no serial"
            found = base.serial or "no SYSTEM.CNF boot serial"
            raise Refusal(
                f"{Path(path).name} boots {found}, not {expected}; this studio reads "
                f"the NCAA Football 09 PlayStation 2 disc, so choose that image."
            )
        edition = EDITIONS.get(base.executable_sha256 or "")
        details = dict(base.details)
        details["edition"] = edition["edition"] if edition else "unknown"
        details["expected_editions"] = [value["name"] for value in EDITIONS.values()]
        if edition is not None:
            details["elf_crc"] = edition["elf_crc"]
            details["expected_image_sha256"] = edition["image_sha256"]
            label = f"{edition['name']} disc"
        else:
            label = (
                f"{UNKNOWN_EDITION}: the boot ELF does not match the retail digest, "
                f"so every lane here reads it and none claims it"
            )
        size = base.size_bytes
        return SourceIdentity(
            kind=base.kind,
            path=base.path,
            size_bytes=size,
            serial=base.serial,
            executable_sha256=base.executable_sha256,
            serial_matches=base.serial_matches,
            retail_executable=base.executable_sha256 == containers.RETAIL_BOOT_ELF_SHA256,
            headline=f"{Path(path).name} — {base.serial} · {label} · {size:,} bytes",
            details=details,
        )


def _is_draft_class_file(path: Path) -> bool:
    """Whether this file is the 138,240-byte class, by length and header only.

    Length first: it is one ``stat`` and it rejects every disc image on the
    planet before a byte is read.
    """

    try:
        if path.stat().st_size != CLASS_BYTES:
            return False
        with open(path, "rb") as handle:
            return handle.read(len(CLASS_MAGIC)) == CLASS_MAGIC
    except OSError:
        return False


def edition_of(identity: SourceIdentity) -> Optional[str]:
    """``"retail"`` or ``None`` for an image the one digest does not name."""

    found: Any = EDITIONS.get(identity.executable_sha256 or "")
    return None if found is None else str(found["edition"])


__all__ = ["CLASS_SUFFIXES", "DRAFT_CLASS_KIND", "EDITIONS", "Ncaa09DiscIdentifier",
           "UNKNOWN_EDITION", "edition_of"]
