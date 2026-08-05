#!/usr/bin/env python3
"""Extract every shader constant interface from a user's own APF 2K8 executable.

APF's player surfaces are drawn by ``ps_3_0`` shaders whose constant interfaces
answer questions no asset inspection can. Two examples this tool was built to
settle:

* The crest UV transform is **not** in any asset. Three shader variants declare
  ``ReverseLogoScaleAndOffset`` as a single ``float4`` at register **c29**, with
  a compiled default of ``(1, 1, 0, 0)``. Changing how a crest maps onto a helmet
  therefore needs that register changed, not a different texture.
* The uniform region-colour scheme is declared outright: one shader binds
  ``RegionMap`` alongside ``Region0Weight``..``Region5Weight`` and
  ``Palette[6]``. The R/G/B channels of a crest layer are region masks the game
  fills from a six-entry palette, which had previously only been established by
  painting test patterns and looking at the result in game.

Each compiled shader carries a Direct3D 9 constant table (``D3DXSHADER_CONSTANTTABLE``)
holding, per constant, its name, register set, register index, register count and
compiled default. On the Xbox 360 those structures are big-endian. This walks the
decrypted executable image for well-formed tables and reports them.

The executable is the user's own game data, so nothing here is distributable:
this prints an interface report -- names, register numbers, counts and defaults --
and never writes shader bytecode, texture bytes or any other payload.

Getting the decrypted image
---------------------------
``default.xex`` is compressed and encrypted on disc. ``tools/xex_extract_pe.cpp``
produces the loaded memory image::

    clang++ -std=c++20 -O2 tools/xex_extract_pe.cpp \\
        -Itools/vendor/XenonRecomp/XenonUtils \\
        -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \\
        -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \\
        tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \\
        -o /tmp/xex_extract_pe
    /tmp/xex_extract_pe "<your extracted disc>/default.xex" /tmp/apf.pe

Then::

    python3 tools/apf_xex_shader_interfaces.py /tmp/apf.pe
    python3 tools/apf_xex_shader_interfaces.py /tmp/apf.pe --constant ReverseLogoScaleAndOffset
    python3 tools/apf_xex_shader_interfaces.py /tmp/apf.pe --json interfaces.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import struct
import sys


#: Loaded image base of the retail executable, from its PE optional header.
DEFAULT_IMAGE_BASE = 0x82000000

#: ``D3DXSHADER_CONSTANTTABLE.Size``.  A table always opens with this value, which
#: is what makes a linear scan viable.
CTAB_HEADER_SIZE = 0x1C

#: ``D3DXSHADER_CONSTANTINFO`` is name/set/index/count/reserved/typeinfo/default.
CONSTANT_INFO_SIZE = 20

#: Register sets, from ``D3DXREGISTER_SET``.
REGISTER_SETS = {0: "bool", 1: "int4", 2: "float4", 3: "sampler"}

#: A table's string and data offsets are relative to the table itself and stay
#: small; anything larger is a false positive rather than a huge shader.
MAX_RELATIVE_OFFSET = 0x40000

#: No real shader declares more than this many constants.
MAX_CONSTANTS = 300

MAX_NAME_BYTES = 96


class ShaderInterfaceError(RuntimeError):
    """The supplied file is not a decrypted APF executable image."""


@dataclass(frozen=True)
class ShaderConstant:
    name: str
    register_set: str
    register_index: int
    register_count: int
    #: The compiled default, when the table carries one.  Read as four floats for
    #: ``float4`` constants because that is the only width APF's shaders use for
    #: the values this tool exists to report.
    default: tuple[float, ...] | None

    @property
    def register(self) -> str:
        prefix = "s" if self.register_set == "sampler" else "c"
        if self.register_count > 1:
            last = self.register_index + self.register_count - 1
            return f"{prefix}{self.register_index}..{prefix}{last}"
        return f"{prefix}{self.register_index}"


@dataclass(frozen=True)
class ShaderInterface:
    address: int
    target: str
    creator: str
    constants: tuple[ShaderConstant, ...] = field(default=())

    def constant(self, name: str) -> ShaderConstant | None:
        return next((item for item in self.constants if item.name == name), None)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(item.name for item in self.constants)


def _text(data: bytes, offset: int, limit: int = MAX_NAME_BYTES) -> str | None:
    """A NUL-terminated ASCII string, or ``None`` if this is not one."""

    end = data.find(b"\0", offset, offset + limit)
    if end < 0:
        return None
    raw = data[offset:end]
    if not raw:
        return None
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    return value if all(0x20 <= ord(char) < 0x7F for char in value) else None


def _read_table(data: bytes, offset: int, image_base: int) -> ShaderInterface | None:
    """Parse one candidate constant table, or reject it."""

    if offset + CTAB_HEADER_SIZE > len(data):
        return None
    (size, creator_offset, _version, count,
     info_offset, _flags, target_offset) = struct.unpack_from(">7I", data, offset)
    if size != CTAB_HEADER_SIZE or not 1 <= count <= MAX_CONSTANTS:
        return None
    if max(creator_offset, info_offset, target_offset) > MAX_RELATIVE_OFFSET:
        return None

    # The target string is the strongest cheap discriminator: a real table names
    # a shader model, and random data almost never spells one.
    target = _text(data, offset + target_offset, 12)
    if target is None or not (target.startswith("vs_") or target.startswith("ps_")):
        return None
    creator = _text(data, offset + creator_offset) or ""

    constants: list[ShaderConstant] = []
    for index in range(count):
        entry = offset + info_offset + index * CONSTANT_INFO_SIZE
        if entry + CONSTANT_INFO_SIZE > len(data):
            return None
        (name_offset, register_set, register_index, register_count,
         _reserved, _type_info, default_offset) = struct.unpack_from(
            ">IHHHHII", data, entry)
        name = _text(data, offset + name_offset)
        if name is None or register_set not in REGISTER_SETS:
            return None
        default: tuple[float, ...] | None = None
        if default_offset and REGISTER_SETS[register_set] == "float4":
            # Read every register the constant declares, not just the first.
            # ``Palette`` is ``float4 Palette[6]`` at c12..c17, and reading a
            # fixed four floats reported only its first entry while looking like
            # a complete answer -- the worst shape for a wrong value.
            values_at = offset + default_offset
            span = 16 * max(1, register_count)
            if values_at + span <= len(data):
                default = struct.unpack_from(
                    f">{4 * max(1, register_count)}f", data, values_at)
        constants.append(
            ShaderConstant(name, REGISTER_SETS[register_set],
                           register_index, register_count, default)
        )
    if not constants:
        return None
    return ShaderInterface(image_base + offset, target, creator, tuple(constants))


def extract_interfaces(image: bytes,
                       image_base: int = DEFAULT_IMAGE_BASE) -> tuple[ShaderInterface, ...]:
    """Every well-formed shader constant table in a decrypted image."""

    if len(image) < 0x1000 or image[:2] != b"MZ":
        raise ShaderInterfaceError(
            "This does not look like a decrypted executable image. Run "
            "tools/xex_extract_pe.cpp on your own default.xex first."
        )
    header = struct.unpack_from(">I", CTAB_HEADER_SIZE.to_bytes(4, "big"), 0)[0]
    needle = header.to_bytes(4, "big")
    found: list[ShaderInterface] = []
    at = image.find(needle)
    while at != -1:
        if at % 4 == 0:
            table = _read_table(image, at, image_base)
            if table is not None:
                found.append(table)
        at = image.find(needle, at + 4)
    return tuple(found)


def _report(interfaces: tuple[ShaderInterface, ...], wanted: str | None) -> None:
    if wanted:
        matches = [item for item in interfaces if item.constant(wanted)]
        print(f"{len(matches)} of {len(interfaces)} shaders declare {wanted!r}\n")
        for item in matches:
            constant = item.constant(wanted)
            assert constant is not None
            default = ("(" + ", ".join(f"{v:g}" for v in constant.default) + ")"
                       if constant.default else "no compiled default")
            print(f"  {item.address:08X}  {item.target:<8} "
                  f"{constant.register:<12} {default}")
        return

    print(f"{len(interfaces)} shader constant interfaces\n")
    for item in interfaces:
        print(f"--- {item.address:08X}  {item.target}  "
              f"({len(item.constants)} constants, compiler {item.creator}) ---")
        for constant in item.constants:
            default = ("  = (" + ", ".join(f"{v:g}" for v in constant.default) + ")"
                       if constant.default else "")
            print(f"    {constant.register:<12} {constant.name}{default}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("image", type=Path,
                        help="decrypted executable image from xex_extract_pe")
    parser.add_argument("--constant",
                        help="report only the shaders declaring this constant")
    parser.add_argument("--json", type=Path,
                        help="also write the full report as JSON")
    parser.add_argument("--image-base", type=lambda v: int(v, 0),
                        default=DEFAULT_IMAGE_BASE)
    args = parser.parse_args(argv)

    try:
        image = args.image.expanduser().read_bytes()
    except OSError as exc:
        print(f"could not read {args.image}: {exc}", file=sys.stderr)
        return 2
    try:
        interfaces = extract_interfaces(image, args.image_base)
    except ShaderInterfaceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not interfaces:
        print("no shader constant tables found", file=sys.stderr)
        return 1

    _report(interfaces, args.constant)
    if args.json:
        args.json.write_text(json.dumps([
            {
                "address": f"{item.address:08X}",
                "target": item.target,
                "creator": item.creator,
                "constants": [
                    {
                        "name": constant.name,
                        "register_set": constant.register_set,
                        "register_index": constant.register_index,
                        "register_count": constant.register_count,
                        "register": constant.register,
                        "default": list(constant.default) if constant.default else None,
                    }
                    for constant in item.constants
                ],
            }
            for item in interfaces
        ], indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
