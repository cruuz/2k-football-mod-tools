"""Which Madden NFL 09 (PlayStation 2) disc image this is.

Two images are supported and they are not the same disc.  The **retail** USA
release and the community's **Deluxe** rebuild both boot ``SLUS-21770`` and
both carry the same ``/DATA`` container set, but Deluxe ships a patched
executable and thirteen rewritten containers, so telling them apart is not
cosmetic: a lane that reads ``UNIFORMS.DAT`` gets 725 members on one and a
different container on the other, and a code patch keyed to one executable's
CRC is wrong on the other.

The shared :class:`mod_editor.games._formats.ps2_disc.Ps2DiscIdentifier` gets
the ISO9660 volume, ``SYSTEM.CNF`` and the boot ELF digest; this file adds the
edition, because "a disc that boots SLUS-21770" is not specific enough to act
on.  Anything else is refused with one sentence naming what was expected.

Read-only: the image is opened for reading and never written.

**Evidence tags.**  **[M]** measured on a disc this box holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mod_editor.games._formats.ps2_disc import ACCEPTED_SUFFIXES, Ps2DiscIdentifier
from mod_editor.games.contract import GameIdentity, Refusal, SourceIdentity

from . import containers

#: The two images this module knows, by boot-ELF digest [M].  A digest is the
#: only honest key: both editions boot the same serial, and the Deluxe disc's
#: whole-image hash changes with every community re-cut while its executable
#: does not.
EDITIONS: Dict[str, Dict[str, str]] = {
    containers.RETAIL_BOOT_ELF_SHA256: {
        "edition": containers.RETAIL_EDITION,
        "name": "retail",
        "elf_crc": containers.RETAIL_ELF_CRC,
        "image_sha256": containers.RETAIL_IMAGE_SHA256,
    },
    containers.DELUXE_BOOT_ELF_SHA256: {
        "edition": containers.DELUXE_EDITION,
        "name": "Deluxe",
        "elf_crc": containers.DELUXE_ELF_CRC,
        "image_sha256": containers.DELUXE_IMAGE_SHA256,
    },
}

#: What a headline says about a disc whose boot ELF is neither.  It is a
#: statement, not a failure: an unknown Madden 09 re-cut still catalogues, and
#: every lane here is read-only, so nothing is risked by listing it.
UNKNOWN_EDITION = "unknown edition"


class Madden09DiscIdentifier:
    """Say which Madden NFL 09 PlayStation 2 image this is, retail or Deluxe."""

    accepted_suffixes = ACCEPTED_SUFFIXES

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
                f"the Madden NFL 09 PlayStation 2 disc, so choose that image."
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
                f"{UNKNOWN_EDITION}: the boot ELF matches neither the retail nor the "
                f"Deluxe digest, so every lane here reads it and none claims it"
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
    """``"retail"``, ``"deluxe"`` or ``None`` for an image neither digest names."""

    found: Any = EDITIONS.get(identity.executable_sha256 or "")
    return None if found is None else str(found["edition"])


__all__ = ["EDITIONS", "Madden09DiscIdentifier", "UNKNOWN_EDITION", "edition_of"]
