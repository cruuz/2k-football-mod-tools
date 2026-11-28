"""PS2 roster saves on the Rosters page (b81 wave 3 item 2): the same pages and guards as an Xbox save.

A PS2 save (``BASLUS-20919<name>``) is a memory-card directory: the payload, ``icon.sys``, ``TYPE`` and ``EXTRA``, the
CRC-32 of the payload. A roster save's payload is a ROST resource laid out like the Xbox ``SAVEGAME.DAT`` of a roster
save (0x20-byte wrapper, version-0 arena, root at 0x40), so the Rosters document, its writers and its checks read it
unchanged. What differs is the container, which this module supplies in ``SaveContainer``'s shape:

* reading: ``.psu`` (EMS / SharkPort), an extracted save folder, or one save on a ``.ps2`` memory-card image, through
  ``tools/nfl2k5_ps2_save.py``; the stored CRC must match the payload;
* writing: the payload is replaced (never resized), ``EXTRA`` is resealed, the copy is staged on the target's volume,
  written by the existing ``.psu`` writer or into a copy of the source card (page ECC included), and then checked by
  the independent verifier ``tools/nfl2k5_ps2_save_verify.py`` (file set and sidecars unchanged, CRC, every ROST table's
  count and offset unchanged; for a card also every page's ECC and every other save untouched). Only a verified copy is
  published, never over an existing file or the source.

Scope: roster saves (``TYPE`` ROS). A PS2 franchise save is refused here: none has been checked yet. Nothing in this
module says how the PS2 game reads an edit; that needs a PCSX2 load witness (see ``PCSX2_WITNESS``).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from . import nfl2k5_roster_records as rr

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_save as save_lib  # noqa: E402
import nfl2k5_ps2_save_verify as verify_lib  # noqa: E402

SUFFIXES = (".psu", ".ps2")
PCSX2_WITNESS = (
    "Import the written .psu into a PCSX2 memory card (or boot the written .ps2 card) with ESPN NFL 2K5 (SLUS-20919): "
    "the game lists the save with no corrupt-data message and loads it as a roster; each edited player shows the new "
    "name, number, position and ratings on the roster and player card screens; a moved depth row and a chosen returner "
    "show on the depth chart; a reserve move, a team paste, team settings, a coach edit and a career stats clear show "
    "where the game shows them; an exhibition game plays through with the edited clubs.")


class Ps2SaveError(rr.RosterRecordError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Ps2SaveError(message)


def is_ps2_path(path: Path | str) -> bool:
    source = Path(path)
    if source.suffix.lower() in SUFFIXES:
        return True
    return source.is_dir() and source.name.startswith(save_lib.SAVE_PREFIX) and (source / source.name).is_file()


def card_saves(path: Path | str) -> list[str]:
    """The 2K5 roster saves on a memory-card image, by directory name."""

    return [save.directory for save in save_lib.read_memcard(Path(path)) if save.type_code == "ROS"]


class Ps2SaveContainer:
    """One PS2 roster save in ``rr.SaveContainer``'s shape: ``savegame``, ``path``, ``verified``, ``document()``,
    ``write()``. ``kind`` is ``psu``, ``card`` or ``directory``."""

    platform = "ps2"

    def __init__(self, path: Path, save: Any, kind: str) -> None:
        self.path = path
        self.save = save
        self.kind = kind
        self.directory = save.directory
        self.savegame = bytes(save.payload)
        self.verified = bool(save.crc_is_valid())
        self.savegame_name = save.payload_name
        self.extra_name = "EXTRA"

    @classmethod
    def load(cls, path: Path | str, *, directory: str | None = None,
             require_checksum: bool = True) -> "Ps2SaveContainer":
        source = Path(path).expanduser()
        _require(source.exists(), f"{source} does not exist")
        kind = "card" if source.suffix.lower() == ".ps2" else ("directory" if source.is_dir() else "psu")
        try:
            if kind == "card" and directory is None:
                rosters = card_saves(source)
                _require(bool(rosters), f"{source.name} holds no ESPN NFL 2K5 roster save")
                _require(len(rosters) == 1, f"{source.name} holds {len(rosters)} 2K5 roster saves "
                                            f"({', '.join(rosters)}); choose one")
                directory = rosters[0]
            save = save_lib.load_save(source, directory)
        except save_lib.SaveError as exc:
            raise Ps2SaveError(str(exc)) from exc
        _require(save.directory.startswith(save_lib.SAVE_PREFIX),
                 f"{save.directory} is not an ESPN NFL 2K5 (SLUS-20919) save")
        kind_code = save.type_code
        if kind_code == "FXG":
            raise Ps2SaveError("this is a PS2 franchise save. The Rosters page opens PS2 roster saves; no PS2 "
                               "franchise save has been checked yet, so franchise saves are not edited here")
        _require(kind_code == "ROS", f"this PS2 save is a {save_lib.TYPE_CODES.get(kind_code or '', kind_code)} "
                                     "save, not a roster save")
        _require(not require_checksum or save.crc_is_valid(),
                 "the save's EXTRA checksum does not match its data; the game would call it corrupt, so it is not "
                 "opened")
        try:
            offset, length = save_lib.roster_region(save)
        except save_lib.SaveError as exc:
            raise Ps2SaveError(str(exc)) from exc
        _require(offset == 0, "the roster is not at the start of this save")
        return cls(source, save, kind)

    def document(self, *, scheme: str = "retail", base_year: int = 2004,
                 reference_year: int | None = None) -> rr.RosterDocument:
        payload = self.savegame
        base = rr.find_block_base(payload)
        return rr.RosterDocument(payload, base=base, source=str(self.path), container=self, scheme=scheme,
                                 base_year=base_year, reference_year=reference_year)

    def staged_save(self, payload: bytes):
        """A copy of the save with ``payload`` and a resealed EXTRA (the source save object is left alone)."""

        _require(len(payload) == len(self.savegame), "the roster changed size; a PS2 save is rewritten in place only")
        copy = save_lib.Ps2Save(directory=self.directory, files=dict(self.save.files),
                                _entries=dict(self.save._entries), _dir_entry=self.save._dir_entry)
        copy.files[copy.payload_name] = bytes(payload)
        copy.reseal()
        return copy

    def write(self, target: Path | str, payload: bytes, *, overwrite: bool = False) -> dict[str, Any]:
        """Stage, write, verify independently, then publish. ``.psu`` always; ``.ps2`` only for a save opened from a
        card (the copy of that card, the other saves byte for byte). Never over the source; never over an existing file
        unless ``overwrite``."""

        from .image_use import studio_staging
        from .platform_compat import publish_no_replace
        destination = Path(target).expanduser()
        to_card = destination.suffix.lower() == ".ps2"
        _require(destination.suffix.lower() in SUFFIXES, "a PS2 copy is a .psu save file or a .ps2 memory card")
        _require(not to_card or self.kind == "card",
                 "a memory-card copy needs a save opened from a card; write a .psu instead")
        _require(not destination.exists() or overwrite, f"{destination} exists")
        _require(not destination.exists() or destination.resolve() != self.path.resolve(),
                 "the target must not be the source save")
        save = self.staged_save(payload)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with studio_staging(destination.parent, ".studio-ps2-") as stage:
            staged = stage.path / destination.name
            try:
                if to_card:
                    save_lib.write_into_memcard(self.path, save, staged, save.directory)
                    report = verify_lib.verify_memcard_write(self.path, staged, save.directory,
                                                             expected_payload=payload)
                    checked = report["save"]
                    extra = {"ecc_pages": report["ecc"]["pages_checked"],
                             "other_saves_untouched": report["other_saves_untouched"]}
                else:
                    save_lib.write_psu(save, staged)
                    checked = verify_lib.verify(verify_lib.decode_save(self.path, self.directory),
                                                verify_lib.decode_psu(staged), expected_payload=payload)
                    extra = {}
            except (save_lib.SaveError, verify_lib.VerifyError, OSError) as exc:
                raise Ps2SaveError(f"the PS2 copy did not verify, nothing was written: {exc}") from exc
            _require(checked.get("result") == "PASS", "the PS2 copy did not verify; nothing was written")
            if overwrite and destination.exists():
                os.replace(staged, destination)
            else:
                publish_no_replace(staged, destination)
        return {"target": str(destination), "kind": "card" if to_card else "psu", "platform": "ps2",
                "directory": self.directory, "crc32": checked["crc32"], "changed_bytes": checked["changed_bytes"],
                "tables_checked": checked["tables_checked"], "verified": True, "signed": False, "sealed": True,
                **extra}


__all__ = ["SUFFIXES", "PCSX2_WITNESS", "Ps2SaveError", "Ps2SaveContainer", "is_ps2_path", "card_saves"]
