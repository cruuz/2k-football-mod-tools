"""PlayStation 2 disc identity, shared by every PS2 game module.

Wraps the shipped ISO9660 reader (``tools/ps2_iso9660.py``) unchanged.  The
identifier is *parameterised by the game's identity* rather than pinned to a
serial: ESPN NFL 2K5 instantiates it with ``SLUS-20919`` and its two retail
digests, and an ESPN NBA 2K5 module would instantiate it with that disc's
serial and digests, with no code in common but this file.  It reads the volume
descriptor, ``/SYSTEM.CNF`` and the boot ELF and never writes.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from pathlib import Path
import stat
import sys
from typing import Any, Optional

from mod_editor.games.contract import GameIdentity, Refusal, SourceIdentity

_ROOT = Path(__file__).resolve().parents[4]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

SOURCE_KIND = "ps2-iso"
ACCEPTED_SUFFIXES = (".iso", ".bin", ".img")


class Ps2DiscIdentifier:
    """Say which PS2 disc image this is, against one game's retail identity."""

    accepted_suffixes = ACCEPTED_SUFFIXES

    def __init__(self, identity: GameIdentity) -> None:
        self.identity = identity

    def identify(self, path: Path) -> SourceIdentity:
        path = Path(path)
        try:
            info = path.lstat()
        except OSError as exc:
            raise Refusal(f"{path} cannot be opened: {exc}. Choose a disc image file.") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise Refusal(f"{path} is not a regular file; a disc image must be one.")
        try:
            image = iso_lib.open_image(str(path))
            boot = iso_lib.boot_identity(image)
        except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise Refusal(str(exc).strip() or exc.__class__.__name__) from exc
        serial: Optional[str] = boot.get("serial")
        boot_sha256: Optional[str] = boot.get("boot_sha256")
        serial_matches = serial is not None and serial in self.identity.serials
        retail_executable = (
            boot_sha256 is not None and boot_sha256 in self.identity.executable_sha256
        )
        expected = ", ".join(self.identity.serials) or "no serial"
        if serial is None:
            serial_text = "no SYSTEM.CNF boot serial"
        elif serial_matches:
            serial_text = serial
        else:
            serial_text = f"{serial} (expected {expected})"
        boot_text = "retail boot ELF" if retail_executable else "boot ELF differs from retail"
        details: dict[str, Any] = {
            "boot_file": boot.get("boot_file"),
            "boot_size": boot.get("boot_size"),
            "volume_id": image.volume_id,
            "volume_blocks": image.volume_blocks,
            "sector_size": image.sector_size,
            "expected_serials": list(self.identity.serials),
        }
        return SourceIdentity(
            kind=SOURCE_KIND,
            path=str(path),
            size_bytes=int(info.st_size),
            serial=serial,
            executable_sha256=boot_sha256,
            serial_matches=serial_matches,
            retail_executable=retail_executable,
            headline=f"{path.name} — {serial_text} · {boot_text} · {info.st_size:,} bytes",
            details=details,
        )


__all__ = ["ACCEPTED_SUFFIXES", "Ps2DiscIdentifier", "SOURCE_KIND"]
