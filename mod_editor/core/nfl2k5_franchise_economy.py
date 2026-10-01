"""DESIGN: opt-in 2026 franchise economy, with four real dollars per game dollar.

PROVED OFFLINE: byte guards and bounded native probes are in the economy tests.
The replacement code stays inside existing retail routines. No allocated
cave, persistent extension or new save field is required. Annual cap schedules
are approximations; contract cash and guarantees cannot be represented exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_franchise_economy_code import WINDOWS, ROOKIE_TABLE, ROOKIE_TABLE_VA, SYMBOLS

BUILD_CAPTION = "2026 franchise economy (experimental, real-dollar display)"
REAL_CAP_DOLLARS = 301_200_000
DOLLAR_SCALE = 4
GAME_CAP = REAL_CAP_DOLLARS // (1000 * DOLLAR_SCALE)
# DESIGN: repeat the observed change as a scenario, not an official forecast.
CAP_GROWTH = 301_200_000 / 279_200_000
SOURCE = "https://www.nfl.com/news/2026-nfl-free-agency-questions-answers"
PINS = {
    0x322eb0: "d73c5eb6d2ca06e132366d3b28297358d7d92b19330a75660c6a45b84379515d",
    0x322bb0: "2332cdddbc192c0bf4bdcee6d70815fda185dd02d17ce7c687f6677ee2eef572",
    0x323bb3: "18e4b926cc26c8485636850589cb49c6c4449300486ca07026052e0e8a97a56b",
    0x31e580: "2b3646f49553fc5f3a4a81ea5ac1385ab8bf3236f9437dd847a58b6ffd102af4",
    0x2bfbe0: "99c9612d45dda760560c05fd3567d3cae27bcc54c05b07677386c512dcd557f8",
    0x247bc6: "269a8b2e1242b18e7b98c7ea2251fe5c98cf7230b7fc87c7cc5f85b112f373d3",

    0x2BD440: "04c68607c55cfd54db5a8a94f522bc2f61b6914914dba84b05c511d8d8a4d39c",
    0x3228A0: "200a8f3dbfb2e8c8672e19c5c9b5c7a39d2f8cad55dcc32309d3c6467eec841e",
    0x322980: "0184657837ab7ad64c3f3a1cbb4397282f918899a8eacca2e82c8401d99152bf",
    0x2BAB20: "b710ddd55cffbc45a72d4b151e9fb9f753ac747eadd587eb26526c4b7990e790",
    ROOKIE_TABLE_VA: "fd43c8802c4fc4187dbd800c57dddb086f817e5a2b4bab00d98fbd5d14a26113",
    0x13EF17: "59d21dbfe2723882ccf08136295a2b573519daec780b40ccdda59bfa4ad17043",
    0x4FE7A0: "81e41c20b2c34089266941f30c4e125b0c964a92be301e966a3959a3b15cc792",
    0x2BACCA: "91046df2aa008410555df240b14243aa348b37cd16582c9d8a80ca305afccab2",
    0x13ED30: "a2cfdb5ce563576292af1eadeb02a14083ae709a037f6afb659e5a219d3d8796",
    0x13ECA0: "b38f0a0efc9ddd6e2a56e58581da229723090d2de23f9ee4d051a2e5f0a143ce",
}


class EconomyError(ValueError):
    """PROVED OFFLINE: mismatched or mixed economy bytes are refused atomically."""


@dataclass(frozen=True)
class Site:
    va: int
    patched: bytes
    digest: str


def sites() -> tuple[Site, ...]:
    replacements = {**WINDOWS, ROOKIE_TABLE_VA: ROOKIE_TABLE,
                    0x13EF17: bytes.fromhex("c70578c2e300") + struct.pack("<I", GAME_CAP),
                    0x4FE7A0: struct.pack("<f", CAP_GROWTH),
                    # Apply surplus to both sides of a trade, keeping legality checks.
                    0x2BACCA: bytes.fromhex("6a01")}
    replacements[0x247BC6] = b"\xe8" + struct.pack("<i", SYMBOLS["economy_reconcile"] - 0x247BC6 - 5)
    for address, symbol in ((0x322BB0, "economy_fill_gate"), (0x323BB3, "economy_offer_gate")):
        replacements[address] = b"\xe9" + struct.pack("<i", SYMBOLS[symbol] - address - 5) + b"\x90"
    replacements[0x322EB0] = b"\xe9" + struct.pack("<i", SYMBOLS["economy_renew_gate"] - 0x322EB0 - 5) + b"\x90\x90"
    for address, symbol in ((0x13ED30, "economy_penalty"), (0x13ECA0, "economy_cap")):
        replacements[address] = b"\xe9" + struct.pack("<i", SYMBOLS[symbol] - address - 5)
    return tuple(Site(a, b, PINS[a]) for a, b in sorted(replacements.items()))


def _standalone_status(payload: bytes) -> str:
    try:
        image = XbeImage(payload)
        states = set()
        for site in sites():
            current = image.read(site.va, len(site.patched))
            states.add("applied" if current == site.patched else
                       "retail" if hashlib.sha256(current).hexdigest() == site.digest else "foreign")
        return next(iter(states)) if len(states) == 1 else "foreign"
    except (ValueError, struct.error, IndexError):
        return "foreign"


def status(payload: bytes) -> str:
    from . import nfl2k5_roster_fill_composition as composition
    try:
        return _standalone_status(composition.project(payload, "economy"))
    except (ValueError, KeyError, TypeError, struct.error, IndexError, StopIteration):
        return "foreign"


def revert(payload: bytes, retail: bytes) -> tuple[bytes, dict]:
    from . import nfl2k5_roster_fill_composition as composition
    return composition.revert(payload, retail, "economy")


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "changed_bytes": 0}
    if state != "retail":
        raise EconomyError(f"economy sites are {state}; refusing to patch")
    from . import nfl2k5_roster_fill_composition as composition
    shared = composition.installation_edits(payload, "economy")
    image, out = XbeImage(payload), bytearray(payload)
    sections, touched, edits = _sections(payload), set(), []
    for site in sites():
        offset = image.offset(site.va, len(site.patched))
        out[offset:offset + len(site.patched)] = site.patched
        touched.add(_section_for_offset(sections, offset).index)
        edits.append({"va": hex(site.va), "bytes": len(site.patched), "retail_sha256": site.digest})
    for address, code in shared:
        offset = image.offset(address, len(code))
        out[offset:offset + len(code)] = code
        touched.add(_section_for_offset(sections, offset).index)
        edits.append({"va": hex(address), "bytes": len(code), "composition": "squad_then_economy"})
    for section in sections:
        if section.index in touched:
            offset = section.header_offset + 36
            out[offset:offset + 20] = section_digest(bytes(out), section)
    result = bytes(out)
    if status(result) != "applied":
        raise EconomyError("economy post-apply verification failed")
    return result, {"evidence": "PROVED OFFLINE", "changed_bytes": sum(a != b for a, b in zip(payload, result)),
                    "edits": edits, "sections_repinned": sorted(touched), "game_cap_thousands": GAME_CAP,
                    "real_dollars_per_game_dollar": DOLLAR_SCALE, "source": SOURCE,
                    "limitations": "DESIGN: fitted cap curves, experience-based aging, estimated rookie pool; no exact cash/guarantee accounting"}


def main(argv=None):
    """DESIGN: guarded copy-only CLI; the source executable is never changed."""
    import argparse
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    args = ap.parse_args(argv)
    if args.source.resolve() == args.target.resolve() or args.target.exists():
        ap.error("choose a new output path")
    if args.source.stat().st_size > 16 * 1024 * 1024:
        ap.error("expected a bounded USA XBE")
    result, receipt = apply(args.source.read_bytes())
    with args.target.open("xb") as stream:
        stream.write(result)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
