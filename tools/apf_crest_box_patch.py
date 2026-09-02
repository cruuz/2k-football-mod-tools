#!/usr/bin/env python3
"""Create the guarded Xenia patch that enlarges APF 2K8 helmet crests.

APF maps a team crest into a fixed helmet rectangle.  Making a 512x512 mask
larger cannot escape that rectangle: the transform is the pixel-shader
constant ``ReverseLogoScaleAndOffset`` (``c29``).  The retail USA executable
contains three crest-shader variants, each with one baked constant packet.

This module emits a Xenia Canary PatchDB file for those three packets.  It does
not patch ``default.xex`` or any game volume.  The addresses are keyed to the
three globally unique ``packet header + retail identity transform`` matches,
not to register 29: APF's cloth shaders reuse c29 for ``WeaveRepeat`` and a
register-only patch would corrupt them.

The optional decrypted-image check is the strongest preflight.  It requires
the user's own loaded executable image (from ``xex_extract_pe.cpp``) to contain
exactly the three reviewed packet addresses before a patch is written.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys


TITLE_NAME = "All Pro Football 2K8"
TITLE_ID = "54540807"
TITLE_HASH = "5447E5428AA2D52A"
# Xenia's upstream PatchDB contract is one discoverable file named from the
# title ID and title name.  The crest entry lives inside that canonical file so
# the editor never produces a plausible-looking patch that the emulator skips.
PATCH_BASENAME = f"{TITLE_ID} - {TITLE_NAME}.patch.toml"

DEFAULT_IMAGE_BASE = 0x82000000
PACKET_HEADER = bytes.fromhex("00 01 1D 01")
RETAIL_TRANSFORM = (1.0, 1.0, 0.0, 0.0)
RETAIL_PACKET_ADDRESSES = (0x84E82B20, 0x84E8B6B8, 0x84E98ED4)

MIN_COVERAGE = 1.01
MAX_COVERAGE = 2.0
EAGLES_COVERAGE = 1.40


class CrestBoxPatchError(ValueError):
    """The requested coverage or retail shader evidence is unsafe."""


def _f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _bits(value: float) -> int:
    return struct.unpack(">I", struct.pack(">f", value))[0]


def transform_for_coverage(coverage: float) -> tuple[float, float, float, float]:
    """Return a centred UV transform for a helmet-space coverage multiplier."""

    if isinstance(coverage, bool) or not isinstance(coverage, (int, float)):
        raise CrestBoxPatchError("crest coverage must be a number")
    coverage = float(coverage)
    if not MIN_COVERAGE <= coverage <= MAX_COVERAGE:
        raise CrestBoxPatchError(
            f"crest coverage must be between {MIN_COVERAGE:.2f}x and "
            f"{MAX_COVERAGE:.2f}x"
        )
    scale = _f32(1.0 / coverage)
    offset = _f32((1.0 - scale) / 2.0)
    return scale, scale, offset, offset


def _retail_packet() -> bytes:
    return PACKET_HEADER + struct.pack(">4f", *RETAIL_TRANSFORM)


def crest_packet_addresses(
    image: bytes, image_base: int = DEFAULT_IMAGE_BASE
) -> tuple[int, ...]:
    """Find guarded retail crest packets in a decrypted executable image."""

    if len(image) < 0x1000 or image[:2] != b"MZ":
        raise CrestBoxPatchError(
            "this is not a decrypted executable image; run xex_extract_pe.cpp "
            "on your own default.xex first"
        )
    needle = _retail_packet()
    addresses: list[int] = []
    at = image.find(needle)
    while at >= 0:
        if at % 4 == 0:
            # Xenia patches the transform, which starts after the packet header.
            addresses.append(image_base + at + len(PACKET_HEADER))
        at = image.find(needle, at + 4)
    return tuple(addresses)


def validate_retail_image(
    image: bytes, image_base: int = DEFAULT_IMAGE_BASE
) -> tuple[int, ...]:
    """Fail unless the exact three reviewed crest packets are present."""

    found = crest_packet_addresses(image, image_base)
    if found != RETAIL_PACKET_ADDRESSES:
        rendered = ", ".join(f"0x{address:08X}" for address in found) or "none"
        raise CrestBoxPatchError(
            "retail crest packet identity drift: expected "
            + ", ".join(f"0x{address:08X}" for address in RETAIL_PACKET_ADDRESSES)
            + f"; found {rendered}"
        )
    return found


def patch_document(coverage: float = EAGLES_COVERAGE) -> str:
    """Build one atomic Xenia patch containing all twelve guarded writes."""

    transform = transform_for_coverage(coverage)
    coverage = float(coverage)
    lines = [
        f'title_name = "{TITLE_NAME}"',
        f'title_id = "{TITLE_ID}"',
        f'hash = "{TITLE_HASH}"',
        "",
        "[[patch]]",
        f'    name = "Helmet crest coverage {coverage:.2f}x"',
        (
            '    desc = "Enlarge ReverseLogoScaleAndOffset for all three crest '
            f'shader variants; centred {coverage:.2f}x coverage. Xenia Canary only."'
        ),
        '    author = "2k-football-mod-tools"',
        "    is_enabled = true",
        "",
    ]
    for base in RETAIL_PACKET_ADDRESSES:
        for word, value in enumerate(transform):
            lines.extend(
                (
                    "    [[patch.be32]]",
                    f"        address = 0x{base + word * 4:08x}",
                    f"        value = 0x{_bits(value):08x}",
                    "",
                )
            )
    return "\n".join(lines)


def write_new_patch(
    destination: Path,
    coverage: float = EAGLES_COVERAGE,
    *,
    decrypted_image: bytes | None = None,
    image_base: int = DEFAULT_IMAGE_BASE,
) -> Path:
    """Write a new PatchDB file without following or overwriting anything."""

    destination = Path(destination).expanduser()
    if decrypted_image is not None:
        validate_retail_image(decrypted_image, image_base)
    document = patch_document(coverage).encode("utf-8")
    try:
        with destination.open("xb") as stream:
            stream.write(document)
    except FileExistsError as exc:
        raise CrestBoxPatchError(
            f"patch destination already exists: {destination}"
        ) from exc
    except OSError as exc:
        raise CrestBoxPatchError(f"could not write patch: {exc}") from exc
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coverage", type=float, default=EAGLES_COVERAGE)
    parser.add_argument(
        "--verify-image",
        type=Path,
        help="optional decrypted executable image to verify before writing",
    )
    parser.add_argument(
        "--image-base", type=lambda value: int(value, 0), default=DEFAULT_IMAGE_BASE
    )
    args = parser.parse_args(argv)
    try:
        image = args.verify_image.expanduser().read_bytes() if args.verify_image else None
        output = write_new_patch(
            args.output,
            args.coverage,
            decrypted_image=image,
            image_base=args.image_base,
        )
    except (OSError, CrestBoxPatchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        "APF_CREST_BOX_PATCH_PASS "
        f"coverage={args.coverage:.2f} writes=12 output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
