"""Keep the XBE boot logo decodable while caves live in its bitmap.

Several executable patches (catch slider, acceleration ramp, draft AI, EDGE legend, scorebug floats)
store code and constants in the XBE header's boot-logo bitmap (VA 0x10A10..0x10CC2, 690 bytes, the
"Microsoft" logo the kernel draws during the boot animation). The game never reads that bitmap, but the
kernel does when it shows the boot animation, and a bitmap full of x86 code decodes to nonsense run
lengths (26,665 "pixels" for a 100 x 17 image). xemu with the Complex BIOS shrugs; a kernel that draws
the logo may not. A user report on 2026-09-03 flagged exactly this.

So whenever the bitmap region is no longer retail, the retail bitmap is copied into the zero padding
that follows the header (0x10CD0..0x10F82, inside the header page, 830 zero bytes in retail) and the
header's LogoBitmapAddr / LogoBitmapSize point at the copy; SizeOfHeaders grows to cover it. The caves
keep their bytes, the kernel decodes the genuine 100 x 17 logo, and nothing in the game changes.

The optional r61 grown-section allocator transfers this bitmap into its named
read-only page allocation before taking the header padding. Recognition here
delegates to that allocator. Loader availability of that new bitmap location
is EXPERIMENTAL/UNWITNESSED; see ASTRA_XBE_SPACE_REPORT.md.
"""

from __future__ import annotations

import struct
from typing import Mapping

BASE = 0x10000
LOGO_ADDR_FIELD = 0x170
LOGO_SIZE_FIELD = 0x174
SIZE_OF_HEADERS_FIELD = 0x108
RETAIL_LOGO_VA = 0x00010A10
LOGO_SIZE = 690
RETAIL_SIZE_OF_HEADERS = 0xCC4
NEW_LOGO_VA = 0x00010CD0
NEW_SIZE_OF_HEADERS = NEW_LOGO_VA - BASE + LOGO_SIZE      # 0xF82, still inside the header page
LOGO_WIDTH, LOGO_HEIGHT = 100, 17

RETAIL_LOGO = bytes.fromhex(
    "0733ad030753ad03a903ea000373a7033200b3fd030503fdd343f9ea0003e3f93347332200ff030573fd7373a773ea0073f7"
    "d373e3f7430f03ff0305ff332e00037a00035200f93303f9030f33ff030343ff13f913050393a3f7730773a7632353a30513"
    "a3d3f77303071373e3f7e3a3130903a3f7e39313054353f95373f9b333032363030593ff4303e3ff33f9030343e3fdb305f9"
    "d3f5d303a3ffe303037326f0130523e3ff630336f0132333c36305d3ff45ffa393f7e3036326f04303ff73d3f9b3f97313f9"
    "5313e3f7930323f9e3d3f9d336f00323638363030322f043e3ff43d3f79323f9a30323f7b33332f0130353f7e343f7e305a3"
    "f7a303e3f7d305d3f7c303d3f75303f913071333030313f9d3f7a3f7d3f913f943d3f9030303f993f9e32323f9730503f963"
    "f9d34313030773f92305a3f903f92303f9030f53f973fde3b3f913f923f9730fd3f7e3030393f9030533f913e3ffd30303e3"
    "f7d307a3f913f90343f7d32200a3f923fd43e3f7d343f943f9030d03f95305f9e30743f90303b3ffe303f9a307d3f953f7e3"
    "0393f7932200fb03fbe303f973a3f7d343f90305030723f90305f9a307d3f39323090333d3fb23f9430513f973b3f79303e3"
    "f7330f03f9d303fb4323f933e3f79343f90513f963f907f9b3054322f0430573f923f97305a3f913f94303f9030f33f97303"
    "f9e30353f913f94313f97343e3f773b3f7b30793f96323e3f7d3f9a30303a3f903d3f7e32373f96303f90313f9b3a30d73f9"
    "2303f94303b3f923f90303d322f0b303f973071326f0e303d32af073032326f0a30343f90343fb930dd3f90303f7e305f9a3"
    "53f90503e3fdb30303f9330923ff73030303e322f0630763fde34305a3f7b305d3f9330d4b0547130303491373a793070343"
    "a3c3a37313051349030b0353d3f3e3731309034373a3d3f3e373130b03235347030749130749030d"
)
assert len(RETAIL_LOGO) == LOGO_SIZE


class BootLogoError(ValueError):
    """The boot logo cannot be relocated in this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BootLogoError(message)


def decode_pixels(bitmap: bytes) -> tuple[int, int]:
    """(pixels described, bytes with neither run flag) for the XBE run-length logo format."""

    i = pixels = bad = 0
    while i < len(bitmap):
        b = bitmap[i]
        if b & 1:
            pixels += (b >> 1) & 7
            i += 1
        elif b & 2:
            word = b | (bitmap[i + 1] << 8 if i + 1 < len(bitmap) else 0)
            pixels += (word >> 2) & 0x3FF
            i += 2
        else:
            bad += 1
            i += 1
    return pixels, bad


def _fields(payload: bytes) -> tuple[int, int, int]:
    addr = struct.unpack_from("<I", payload, LOGO_ADDR_FIELD)[0]
    size = struct.unpack_from("<I", payload, LOGO_SIZE_FIELD)[0]
    headers = struct.unpack_from("<I", payload, SIZE_OF_HEADERS_FIELD)[0]
    return addr, size, headers


def bitmap_is_retail(payload: bytes) -> bool:
    return payload[RETAIL_LOGO_VA - BASE: RETAIL_LOGO_VA - BASE + LOGO_SIZE] == RETAIL_LOGO


def status(payload: bytes) -> str:
    """retail | applied | foreign: where the header says the logo is, and whether that decodes."""

    if len(payload) < 0x1000 or payload[:4] != b"XBEH":
        return "foreign"
    addr, size, headers = _fields(payload)
    if headers == 0x1000 and payload[0xDA0:0xDA8] in (b"XSPACE1\0", b"XSPACE2\0"):
        from . import nfl2k5_xbe_space as space
        if space.status(payload) == "applied":
            return "applied"
        return "foreign"
    copy = payload[NEW_LOGO_VA - BASE: NEW_LOGO_VA - BASE + LOGO_SIZE]
    if addr == RETAIL_LOGO_VA and size == LOGO_SIZE and headers == RETAIL_SIZE_OF_HEADERS and not any(copy):
        return "retail"
    if addr == NEW_LOGO_VA and size == LOGO_SIZE and headers == NEW_SIZE_OF_HEADERS and copy == RETAIL_LOGO:
        return "applied"
    return "foreign"


def needed(payload: bytes) -> bool:
    """True when caves have taken the bitmap and the header still points at it."""

    return status(payload) == "retail" and not bitmap_is_retail(payload)


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Point the header at a pristine copy of the logo in the header padding (idempotent)."""

    state = status(payload)
    if state == "applied":
        return payload, {"status": "applied", "already_applied": True, "logo_va": f"0x{_fields(payload)[0]:x}"}
    _require(state == "retail", f"boot-logo header fields are {state}; refusing")
    padding = payload[NEW_LOGO_VA - BASE: NEW_LOGO_VA - BASE + LOGO_SIZE]
    _require(not any(padding), "the header padding after the logo is not free")
    out = bytearray(payload)
    out[NEW_LOGO_VA - BASE: NEW_LOGO_VA - BASE + LOGO_SIZE] = RETAIL_LOGO
    struct.pack_into("<I", out, LOGO_ADDR_FIELD, NEW_LOGO_VA)
    struct.pack_into("<I", out, LOGO_SIZE_FIELD, LOGO_SIZE)
    struct.pack_into("<I", out, SIZE_OF_HEADERS_FIELD, NEW_SIZE_OF_HEADERS)
    result = bytes(out)
    pixels, bad = decode_pixels(result[NEW_LOGO_VA - BASE: NEW_LOGO_VA - BASE + LOGO_SIZE])
    _require((pixels, bad) == (LOGO_WIDTH * LOGO_HEIGHT, 0), "the relocated logo does not decode as 100 x 17")
    return result, {"status": "applied", "logo_va": f"0x{NEW_LOGO_VA:x}", "size_of_headers": f"0x{NEW_SIZE_OF_HEADERS:x}",
                    "changed_byte_count": sum(1 for a, b in zip(payload, result) if a != b)}


__all__ = ["BootLogoError", "LOGO_SIZE", "NEW_LOGO_VA", "RETAIL_LOGO", "RETAIL_LOGO_VA", "apply", "bitmap_is_retail",
           "decode_pixels", "needed", "status"]
