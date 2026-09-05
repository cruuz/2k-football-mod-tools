"""PS2 boot-ELF identity and pnach delivery, shared by every PS2 game module.

A PS2 executable patch is a set of 32-bit words at EE virtual addresses.  It
ships **emulator-side first**, as a PCSX2 / PenguinScreen2 ``.pnach`` file,
exactly as textures ship as a replacement pack; writing the words into the ELF
on a copy of the disc through the fixed-allocation ISO9660 writer is the
optional second delivery.  This package holds the format knowledge both need
and nothing game-specific:

* :func:`parse_program_headers` -- the ELF32 little-endian MIPS program
  headers, and :func:`file_offset`, the only honest way to turn an EE address
  into a file position (``p_offset + (vaddr - p_vaddr)`` inside a file-backed
  segment; a ``.bss`` address has no file position and is refused);
* :func:`pcsx2_crc` -- the CRC PCSX2 keys per-game patch files by: the XOR of
  every 32-bit little-endian word of the ELF (``pcsx2/Elfheader.cpp``,
  ``ElfObject::GetCRC``); the owner's ``whichbin.py`` computes the same value
  and names it ``pcsx2_crc`` to keep it apart from zlib's CRC-32;
* :func:`emit_pnach` / :func:`parse_pnach` -- the grammar PCSX2 reads and the
  owner's ``bake_pnach.py`` accepts: ``patch=1,EE,<addr>,word,<value>`` lines
  under ``gametitle=`` / ``comment=`` metadata, ``[Section]`` headers and
  comments skipped, any other ``key=`` refused (a dropped line would be an
  unshipped patch).  ``word`` is emitted rather than ``extended``: a plain
  32-bit write is what both readers accept without an address-nibble encoding;
* :func:`read_boot_elf` -- the boot ELF out of the user's own ISO through the
  shipped ISO9660 reader, read-only;
* :func:`build_synthetic_elf` -- a minimal valid ELF for tests and the
  conformance harness, so nothing here ever needs a retail executable.

No retail address or byte appears in this file.  Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct
import sys
from typing import Iterable, Mapping, Optional, Sequence

from mod_editor.games.contract import Refusal

_ROOT = Path(__file__).resolve().parents[4]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

ELF_MAGIC = b"\x7fELF"
ELFCLASS32 = 1
ELFDATA2LSB = 1
EM_MIPS = 8
PT_LOAD = 1
PF_X, PF_W, PF_R = 1, 2, 4
_EHDR = struct.Struct("<16sHHIIIIIHHHHHH")   # e_ident .. e_shstrndx
_PHDR = struct.Struct("<IIIIIIII")           # p_type p_offset p_vaddr p_paddr p_filesz p_memsz p_flags p_align
MAX_PROGRAM_HEADERS = 64

METADATA_KEYS = frozenset({
    "gametitle", "comment", "author", "description", "credits", "date", "version", "cheat", "name",
})
_PATCH_LINE = re.compile(
    r"^patch=(?P<place>[0-3]),(?P<cpu>[A-Za-z]+),(?P<addr>[0-9A-Fa-f]{1,8}),(?P<width>[a-z]+),(?P<value>[0-9A-Fa-f]{1,8})\s*$"
)


class PnachError(Refusal):
    """A pnach or an ELF is not what it claims; the sentence says what."""


@dataclass(frozen=True)
class Segment:
    index: int
    offset: int
    vaddr: int
    filesz: int
    memsz: int
    flags: int

    @property
    def executable(self) -> bool:
        return bool(self.flags & PF_X)

    def contains_in_file(self, vaddr: int, size: int = 4) -> bool:
        return self.vaddr <= vaddr and vaddr + size <= self.vaddr + self.filesz

    def contains_in_memory(self, vaddr: int, size: int = 4) -> bool:
        return self.vaddr <= vaddr and vaddr + size <= self.vaddr + self.memsz


def parse_program_headers(elf: bytes, label: str = "the ELF") -> tuple[Segment, ...]:
    """The PT_LOAD segments of an ELF32 little-endian MIPS executable."""

    if len(elf) < _EHDR.size or elf[:4] != ELF_MAGIC:
        raise PnachError(f"{label} is not an ELF file.")
    ident = elf[:16]
    if ident[4] != ELFCLASS32 or ident[5] != ELFDATA2LSB:
        raise PnachError(f"{label} is not a 32-bit little-endian ELF; a PS2 boot ELF is.")
    (_ident, _type, machine, _version, _entry, phoff, _shoff, _flags, _ehsize,
     phentsize, phnum, _shentsize, _shnum, _shstrndx) = _EHDR.unpack_from(elf, 0)
    if machine != EM_MIPS:
        raise PnachError(f"{label} is not a MIPS executable (e_machine {machine}); a PS2 boot ELF is.")
    if phentsize != _PHDR.size or phnum == 0 or phnum > MAX_PROGRAM_HEADERS:
        raise PnachError(f"{label} has an unreadable program-header table ({phnum} entries of {phentsize} bytes).")
    if phoff + phnum * phentsize > len(elf):
        raise PnachError(f"{label} program headers run past the end of the file.")
    segments = []
    for index in range(phnum):
        p_type, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, p_flags, _p_align = _PHDR.unpack_from(elf, phoff + index * phentsize)
        if p_type != PT_LOAD:
            continue
        if p_offset + p_filesz > len(elf):
            raise PnachError(f"{label}: segment {index} claims more file bytes than exist.")
        segments.append(Segment(index, p_offset, p_vaddr, p_filesz, p_memsz, p_flags))
    if not segments:
        raise PnachError(f"{label} has no loadable segment.")
    return tuple(segments)


def file_offset(segments: Sequence[Segment], vaddr: int, size: int = 4) -> int:
    """The file position of ``size`` bytes at ``vaddr``; refuses .bss and outside."""

    for segment in segments:
        if segment.contains_in_file(vaddr, size):
            return segment.offset + (vaddr - segment.vaddr)
    for segment in segments:
        if segment.contains_in_memory(vaddr, size):
            raise PnachError(
                f"0x{vaddr:08X} lies in segment {segment.index}'s zero-filled tail (.bss): it exists in "
                "memory but has no bytes in the file, so it can be patched at run time (pnach) but never on disc."
            )
    raise PnachError(f"0x{vaddr:08X} lies outside every loadable segment of the ELF.")


def read_word(elf: bytes, segments: Sequence[Segment], vaddr: int) -> int:
    position = file_offset(segments, vaddr)
    return struct.unpack_from("<I", elf, position)[0]


def pcsx2_crc(elf: bytes) -> str:
    """PCSX2's game CRC: XOR of every 32-bit little-endian word (tail bytes ignored)."""

    crc = 0
    for (word,) in struct.iter_unpack("<I", elf[: len(elf) - len(elf) % 4]):
        crc ^= word
    return f"{crc:08X}"


# --------------------------------------------------------------------------
# pnach
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PnachPatch:
    address: int
    value: int
    enabled: bool = True

    def line(self) -> str:
        return f"patch={1 if self.enabled else 0},EE,{self.address:08X},word,{self.value:08X}"


@dataclass(frozen=True)
class PnachDocument:
    gametitle: Optional[str]
    comments: tuple[str, ...]
    patches: tuple[PnachPatch, ...]

    @property
    def crc(self) -> Optional[str]:
        """The CRC named in ``gametitle=... (CRC XXXXXXXX)`` or ``[XXXXXXXX]``, if any."""

        if not self.gametitle:
            return None
        match = re.search(r"(?:CRC\s+|\[)([0-9A-Fa-f]{8})\]?", self.gametitle)
        return match.group(1).upper() if match else None


def emit_pnach(title: str, crc: str, patches: Iterable[PnachPatch], comments: Iterable[str] = ()) -> str:
    """The text of a PCSX2 patch file for ``crc``; one word write per line."""

    if re.fullmatch(r"[0-9A-Fa-f]{8}", crc) is None:
        raise PnachError(f"{crc!r} is not an eight-digit hexadecimal PCSX2 CRC.")
    lines = [f"gametitle={title} (CRC {crc.upper()})"]
    for comment in comments:
        cleaned = " ".join(str(comment).split())
        if cleaned:
            lines.append(f"comment={cleaned}")
    rows = list(patches)
    if not rows:
        raise PnachError("A pnach must carry at least one patch line.")
    seen: set[int] = set()
    for patch in rows:
        if not 0 <= patch.address <= 0xFFFFFFFF or patch.address % 4:
            raise PnachError(f"0x{patch.address:08X} is not a word-aligned 32-bit address.")
        if not 0 <= patch.value <= 0xFFFFFFFF:
            raise PnachError(f"value {patch.value!r} does not fit a 32-bit word.")
        if patch.address in seen:
            raise PnachError(f"0x{patch.address:08X} is patched twice in one file.")
        seen.add(patch.address)
        lines.append(patch.line())
    return "\n".join(lines) + "\n"


def parse_pnach(text: str, source: str = "<pnach>") -> PnachDocument:
    """Read a pnach strictly: every non-comment line is metadata or a word patch, or it refuses."""

    gametitle: Optional[str] = None
    comments: list[str] = []
    patches: list[PnachPatch] = []
    seen: set[int] = set()
    for number, raw in enumerate(text.lstrip("﻿").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("//", "#", ";")) or (line.startswith("[") and line.endswith("]")):
            continue
        where = f"{source}:{number}"
        if line.startswith("patch="):
            match = _PATCH_LINE.match(line)
            if match is None:
                raise PnachError(f"{where}: not a patch line this lane reads: {line!r}")
            if match.group("cpu").upper() != "EE":
                raise PnachError(f"{where}: only EE patches are handled; {match.group('cpu')} is refused.")
            width = match.group("width")
            if width != "word":
                raise PnachError(
                    f"{where}: width {width!r} is refused; this lane reads and writes 32-bit 'word' patches only "
                    "(the owner's ELF baker accepts the same, and 'extended' encodes its operation in the address)."
                )
            address = int(match.group("addr"), 16)
            if address % 4:
                raise PnachError(f"{where}: 0x{address:08X} is not word-aligned.")
            if address in seen:
                raise PnachError(f"{where}: 0x{address:08X} is patched twice.")
            seen.add(address)
            patches.append(PnachPatch(address, int(match.group("value"), 16), match.group("place") != "0"))
            continue
        key, separator, value = line.partition("=")
        if not separator or key.strip().lower() not in METADATA_KEYS:
            raise PnachError(f"{where}: unknown line {line!r}; a dropped line would be an unshipped patch.")
        key = key.strip().lower()
        if key == "gametitle":
            gametitle = value.strip()
        elif key == "comment":
            comments.append(value.strip())
    return PnachDocument(gametitle, tuple(comments), tuple(patches))


# --------------------------------------------------------------------------
# The user's disc, read-only
# --------------------------------------------------------------------------

def read_boot_elf(iso_path: Path) -> tuple[bytes, dict]:
    """``(elf bytes, boot identity)`` from the user's own image through the ISO9660 reader."""

    try:
        image = iso_lib.open_image(str(iso_path))
        identity = iso_lib.boot_identity(image)
        boot2 = identity.get("boot2")
        entry = iso_lib.find(image, boot2) if boot2 else None
        if entry is None or entry.is_dir:
            raise PnachError(f"{iso_path}: SYSTEM.CNF names no readable boot ELF.")
        payload = iso_lib.read_file(image, entry)
    except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
        raise PnachError(str(exc).strip() or exc.__class__.__name__) from exc
    return payload, identity


# --------------------------------------------------------------------------
# Synthetic executable for tests and the conformance harness
# --------------------------------------------------------------------------

def build_synthetic_elf(words: Sequence[int], *, base_vaddr: int = 0x00100000, bss_words: int = 4) -> bytes:
    """A minimal ELF32 LE MIPS executable: one code segment holding ``words``, plus a .bss tail."""

    code = b"".join(struct.pack("<I", word & 0xFFFFFFFF) for word in words)
    phoff = _EHDR.size
    data_offset = 0x100
    header = _EHDR.pack(
        ELF_MAGIC + bytes([ELFCLASS32, ELFDATA2LSB, 1, 0]) + bytes(8),
        2, EM_MIPS, 1, base_vaddr, phoff, 0, 0x20924001, _EHDR.size, _PHDR.size, 1, 0, 0, 0,
    )
    phdr = _PHDR.pack(PT_LOAD, data_offset, base_vaddr, base_vaddr, len(code), len(code) + 4 * bss_words, PF_R | PF_X, 0x1000)
    payload = bytearray(header + phdr)
    payload += bytes(data_offset - len(payload))
    payload += code
    return bytes(payload)


__all__ = [
    "METADATA_KEYS",
    "PnachDocument",
    "PnachError",
    "PnachPatch",
    "Segment",
    "build_synthetic_elf",
    "emit_pnach",
    "file_offset",
    "parse_pnach",
    "parse_program_headers",
    "pcsx2_crc",
    "read_boot_elf",
    "read_word",
]
