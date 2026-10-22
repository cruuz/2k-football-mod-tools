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

# b778 fa1 (revision 2). PROVED OFFLINE: the retail stage-6 veteran cap cut 0x2BFAF0, called for
# every club from the offseason advance at 0x247FF5 (years pro >= 10, 210%), releases a veteran while
# payroll + 6000 >= cap when his base salary exceeds 2.1 x 0x2BD440(surplus, aging, remaining) and
# his dead money is below salary x remaining. The economy's 0x2BD440 answers surplus=1 with trade
# surplus, value + (value - salary) x min(remaining, 4) x 0.5, which clamps an overpaid player to
# one unit, so real contracts (Mahomes 48.53M vs 18.01M, Kittle 16.80M vs 1.84M, Stanley 16.45M vs
# 5.33M in 2027) were cut after free agency and the draft, when no club had room to sign them.
# Pass surplus=0 at this one call: the rule then compares salary with 2.1 x the player's modelled
# market value (Mahomes 38.35M, Kittle 12.09M, Stanley 9.04M), as retail compared it with its own
# bounded value. The cut still gives over-cap clubs relief from genuinely overpaid veterans; trades
# and every other 0x2BD440 caller are unchanged. A revision-1 image reads "legacy" and upgrades.
VETERAN_CUT_SURPLUS = 0x2BFB61              # push 1 (surplus) -> push 0, inside retail 0x2BFAF0
VETERAN_CUT_PATCHED = bytes.fromhex("6a00")
PINS[VETERAN_CUT_SURPLUS] = "5bbc5bfabfc3553dfedc9330b8318b2f152eb1da00cb08f894cc88b395a0b178"
# b778 fa1 (revision 2). PROVED OFFLINE: the rollover (0x247B40) lowers every rostered contract's years left
# with ((v - 1) ^ v) & 15 ^ v, so a player still on a club with 0 years left wraps to 15. Under the economy
# the renew gate refuses a renewal the club cannot afford and leaves him on the roster at 0 (Noah's MyNFL3,
# 2027: Humphrey, Chase Brown, Brisker, Togiai; native 2028 rollover: Chase Brown 15 of 1). Lower only a
# nonzero count; a player at 0 reaches the next re-signing stage as an expiring contract again.
ROLLOVER_DECREMENT = 0x247BA8
ROLLOVER_DECREMENT_PATCHED = bytes.fromhex("f642240f7403fe4a24") + b"\x90" * 7   # test; jz; dec byte [edx+0x24]
PINS[ROLLOVER_DECREMENT] = "4fbd4ad51bfce990b29a4f408fab5b2aad2c9f030cafebeb45c552d0c6a15cd8"
REVISION_2_SITES = frozenset({VETERAN_CUT_SURPLUS, ROLLOVER_DECREMENT})
REVISION = 2


class EconomyError(ValueError):
    """PROVED OFFLINE: mismatched or mixed economy bytes are refused atomically."""


@dataclass(frozen=True)
class Site:
    va: int
    patched: bytes
    digest: str


def sites(revision: int = REVISION) -> tuple[Site, ...]:
    if revision not in (1, 2):
        raise EconomyError("unknown economy revision")
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
    if revision >= 2:
        replacements[VETERAN_CUT_SURPLUS] = VETERAN_CUT_PATCHED
        replacements[ROLLOVER_DECREMENT] = ROLLOVER_DECREMENT_PATCHED
    return tuple(Site(a, b, PINS[a]) for a, b in sorted(replacements.items()))


def _site_state(image: XbeImage, site: Site) -> str:
    current = image.read(site.va, len(site.patched))
    return ("applied" if current == site.patched else
            "retail" if hashlib.sha256(current).hexdigest() == site.digest else "foreign")


def _standalone_status(payload: bytes) -> str:
    """retail | applied | legacy (revision 1: every site but the two revision-2 sites) | foreign."""
    try:
        image = XbeImage(payload)
        states = {site.va: _site_state(image, site) for site in sites()}
        core = {state for va, state in states.items() if va not in REVISION_2_SITES}
        if core == {"applied"} and {states[va] for va in REVISION_2_SITES} == {"retail"}:
            return "legacy"
        unique = set(states.values())
        return next(iter(unique)) if len(unique) == 1 else "foreign"
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
    if state not in ("retail", "legacy"):
        raise EconomyError(f"economy sites are {state}; refusing to patch")
    from . import nfl2k5_roster_fill_composition as composition
    # A legacy (revision-1) image already carries every other site and the shared chain.
    shared = composition.installation_edits(payload, "economy") if state == "retail" else []
    todo = sites() if state == "retail" else tuple(s for s in sites() if s.va in REVISION_2_SITES)
    image, out = XbeImage(payload), bytearray(payload)
    sections, touched, edits = _sections(payload), set(), []
    for site in todo:
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
                    "revision": REVISION, **({"upgraded_from": "legacy"} if state == "legacy" else {}),
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
