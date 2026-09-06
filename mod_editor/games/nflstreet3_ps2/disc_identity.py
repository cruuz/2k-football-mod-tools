"""Which NFL Street 3 (PlayStation 2) disc image this is.

One image is known: the USA retail release, ``SLUS-21482``.  There is no community
rebuild of this disc in this project's reach, so the identifier names one
boot-ELF digest and says ``unknown edition`` about anything else rather than
refusing it -- the digest is the honest key, because a serial says which game
and not which build.

The shared :class:`mod_editor.games._formats.ps2_disc.Ps2DiscIdentifier` gets the
ISO9660 volume, ``SYSTEM.CNF`` and the boot ELF digest; this file adds the
edition.

Read-only: the image is opened for reading and never written.

**Evidence tags.**  **[M]** measured on the disc this box holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mod_editor.games._formats.ps2_disc import ACCEPTED_SUFFIXES, Ps2DiscIdentifier
from mod_editor.games.contract import GameIdentity, Refusal, SourceIdentity

from . import containers

#: The one image this module knows, by boot-ELF digest [M].
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


class NflStreet3DiscIdentifier:
    """Say whether this is the NFL Street 3 (PlayStation 2) disc."""

    accepted_suffixes = tuple(ACCEPTED_SUFFIXES)

    def __init__(self, identity: GameIdentity) -> None:
        self.identity = identity
        self._base = Ps2DiscIdentifier(identity)

    def identify(self, path: Path) -> SourceIdentity:
        base = self._base.identify(Path(path))
        if not base.serial_matches:
            expected = ", ".join(self.identity.serials) or "no serial"
            found = base.serial or "no SYSTEM.CNF boot serial"
            raise Refusal(
                f"{Path(path).name} boots {found}, not {expected}; this studio reads "
                f"the NFL Street 3 (PlayStation 2) disc, so choose that image."
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


def edition_of(identity: SourceIdentity) -> Optional[str]:
    """``"retail"`` or ``None`` for an image the one digest does not name."""

    found: Any = EDITIONS.get(identity.executable_sha256 or "")
    return None if found is None else str(found["edition"])


__all__ = ["EDITIONS", "UNKNOWN_EDITION", "NflStreet3DiscIdentifier", "edition_of"]
