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

# b778 fa2 (revision 3). Noah 10/22: "allow contract restructures ... hold teams to a minimum of 50 players.
# They should never have less than 50 ... lower level players usually accept a veteran minimum ... take the
# best deal on the table after a week or two of no one signing them ... a one-year deal".
# DESIGN (code in tools/franchise_economy/runtime.c, PROVED OFFLINE by the fa2 tests and Unicorn seasons):
# - CPU clubs restructure (the money still owed is re-papered over the years left as the back-loaded curve 6
#   with a 20% prorated bonus) before any cap release and before the stage-6 veteran cut;
# - a 50-player floor for CPU clubs at every weekly advance and after every stage action, filled with
#   lower-level depth (0x322BB0 with a capped budget); at the re-signing stage a club at the floor
#   re-signs an expiring player it can afford instead of releasing him; unsigned free agents no longer all
#   retire at the new league year (the zero-value shortcut in 0x2BCF90), so the pool never empties; the reconcile no longer releases below 50 except a
#   player paid twice the minimum; the user club's preseason gate and in-season trade check move from 42 to
#   50 players (the roster screen's release warning and 42-healthy-players check, inside the Contracts
#   editor's guarded span, are unchanged);
# - every free agent counts his unsigned weeks (player +0x25 bits 5-7, the retail offer-days field, whose
#   seed into new offers is cleared); after two weeks a free agent rated over 70 asks no more than the best
#   room on the table and the CPU club with that room signs him to a one-year prove-it deal.
# Code space: the retail weekly CPU fill 0x323870 (rebuilt in C) and five unreferenced retail library
# functions (WINDOWS "roster_a".."roster_e"; tools/franchise_economy/dead_code.py proves no encoding of any
# address inside them exists anywhere in the retail image). No allocator bytes.
AFTER_STAGE = 0x248628              # call 0x247AA0 (stage getter), common tail of the stage advance 0x2480B0
STAGE6_CASE = 0x24809C              # weekly-advance jump table entry for stage 6 (retail 0x247FD7)
USER_FLOOR = 0x2BF992               # cmp byte [ecx+0x11C], 42: the user club's preseason roster gate
USER_FLOOR_TEXT = 0xE8922A          # "42" in "The %s %s must have at least 42 players."
OFFER_DAYS_SEED = 0x32327E          # new offers copied player +0x25 bits 5-7 into their day count
FA_RETIREMENT = 0x2BDB74           # call 0x2BCF90 for each free agent in the retirement pass 0x2BDB00
EXPIRING_RELEASE = 0x3237AC        # call 0x322B60: the re-signing stage releases an expiring contract
USER_TRADE_FLOOR = 0x2BB13C         # cmp ebp, 42: an in-season trade may not leave the user club below it
USER_TRADE_TEXT = 0xE99FA4          # "42" in "You must keep 42 players on your team or you will not be able to ..."
FLOOR_PLAYERS = 50
for _va, _digest in ((0x323870, "7ff0b7859e73de1e317c60d8c9d3f405f5e5519767a0e1923583a29dd07174ee"),
                     (0x396F50, "9ef09938fc4ad15399b0f2d82b8cb69e9fb9dbb3ddccff0ddef0d8c8b06c358b"),
                     (0x3B9F60, "e11762e6b811b005ce4599cf3e5ad83dc308d7c60c267f13522ec0276b220eb1"),
                     (0x3D2890, "144d399994dc288d29b729f8172ecba63d4ce22a1e66427b0f4e70426dc95565"),
                     (0x3BA4B0, "ac9713c06a3ec301ddf29ec79afdc40699b72730df3ed8e17303809076ef8f97"),
                     (0x3975F0, "3bfc5caea3ae7fb715b36e87d20e2e45d00d8da5d244823709af655fcdadbe9a"),
                     (AFTER_STAGE, "616fba6e927995227a28dfaa4392af04117e12fa040eef3097a1b3e7a10a8d2a"),
                     (STAGE6_CASE, "9efa9ffce65d9200a058489aa95613df2cfe39ed542ba6ffd5212bc4d48b41f4"),
                     (USER_FLOOR, "55d6f7b48ba7c82a511e35fc6bc68a1504cbca1f9cb3cda3e91ca7c06f010eb4"),
                     (USER_FLOOR_TEXT, "e24460917716856724254344202653c566f02f7c2074430cd4b9b6884b39c5cd"),
                     (OFFER_DAYS_SEED, "b4296d8e851226474af9a26c93be4874e70e454e69e0dc4c52bf790ac1a806b1"),
                     (USER_TRADE_FLOOR, "490566c6a8181843df6c7111073ac94bc538a1bce677071bb93660193154107a"),
                     (EXPIRING_RELEASE, "df8ba409850ca02e7cb8d6609900617acc3c9a69c2b5b9860f9a953650ffb4e8"),
                     (FA_RETIREMENT, "fe751a30c55501954375e0fd44439dc22498b7e447f069b7ad11817f220119d2"),
                     (USER_TRADE_TEXT, "e24460917716856724254344202653c566f02f7c2074430cd4b9b6884b39c5cd")):
    PINS[_va] = _digest
# Revision 1 and 2 bytes of every site whose revision-3 bytes differ (the windows and the jumps into code
# that moved), so an image built before revision 3 reads "legacy" and is upgraded in place.
PREVIOUS = {
    0x13ECA0: "4ffed08531493e9a5b249be6eb693b41a725dd59b730397ed269bd67cf1a5bef",
    0x13ED30: "e6db715c203a5ad265ccc283cd7b1c10d07d04f1a5e1c034ffef0245703f19e0",
    0x247BC6: "93bcf088d60a02096f8e9e588f0e0897189d4d145f3f47edcde91f78312acf5b",
    0x2BD440: "2098009afa479031474985580d1f68117db5ee9a30bf2c279103e660056624d6",
    0x2BFBE0: "368e9c6e5bef2a33c8d76f7fa2ab3bfe9e6f1c7c2b7040ebb8e171a411713ae7",
    0x31E580: "d26d9f9f8d2ab7144de95395d1c3116cefc1c06be3883994df9635c6c1900dc0",
    0x3228A0: "57c1299559f569bdd29b5d4236e088d39c422aadfeaef22388c47dd6c7f29833",
    0x322980: "379c73f85730ba9bad62e9f7627b5dd40a6212ebd9623c26883b6aa71c1db0c6",
    0x322EB0: "0ffa41ad20216692b7381d437159d0533eda6d0a495ec06bfd9d14f30a7c830f",
    0x323BB3: "b4b95b9f37daf14470599da75ef463b6aeea0e35a8c3ba6579830ccd8c3e20f3",
}
REVISION_3_SITES = frozenset({0x323870, 0x396F50, 0x3B9F60, 0x3D2890, 0x3BA4B0, 0x3975F0, AFTER_STAGE, STAGE6_CASE,
                              USER_FLOOR, USER_FLOOR_TEXT, OFFER_DAYS_SEED, USER_TRADE_FLOOR, USER_TRADE_TEXT,
                              EXPIRING_RELEASE, FA_RETIREMENT})
REVISION = 3


class EconomyError(ValueError):
    """PROVED OFFLINE: mismatched or mixed economy bytes are refused atomically."""


@dataclass(frozen=True)
class Site:
    va: int
    patched: bytes
    digest: str


def sites(revision: int = REVISION) -> tuple[Site, ...]:
    if revision not in (1, 2, 3):
        raise EconomyError("unknown economy revision")
    windows = {va: code for va, code in WINDOWS.items() if revision >= 3 or va not in REVISION_3_SITES}
    replacements = {**windows, ROOKIE_TABLE_VA: ROOKIE_TABLE,
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
    if revision >= 3:
        replacements[AFTER_STAGE] = b"\xe8" + struct.pack("<i", SYMBOLS["economy_after"] - AFTER_STAGE - 5)
        replacements[STAGE6_CASE] = struct.pack("<I", SYMBOLS["economy_stage6"])
        replacements[USER_FLOOR] = bytes.fromhex("80b91c010000") + bytes((FLOOR_PLAYERS,))
        replacements[USER_FLOOR_TEXT] = str(FLOOR_PLAYERS).encode("utf-16-le")
        replacements[OFFER_DAYS_SEED] = bytes.fromhex("5fc6460900") + b"\x90" * 8   # pop edi; mov byte [esi+9], 0
        replacements[USER_TRADE_FLOOR] = bytes.fromhex("83fd") + bytes((FLOOR_PLAYERS,))
        replacements[USER_TRADE_TEXT] = str(FLOOR_PLAYERS).encode("utf-16-le")
        replacements[EXPIRING_RELEASE] = b"\xe8" + struct.pack("<i", SYMBOLS["economy_expire"] - EXPIRING_RELEASE - 5)
        replacements[FA_RETIREMENT] = b"\xe8" + struct.pack("<i", SYMBOLS["economy_fa_retire"] - FA_RETIREMENT - 5)
    return tuple(Site(a, b, PINS[a]) for a, b in sorted(replacements.items()))


def _site_state(image: XbeImage, site: Site) -> str:
    current = image.read(site.va, len(site.patched))
    return ("applied" if current == site.patched else
            "retail" if hashlib.sha256(current).hexdigest() == site.digest else "foreign")


def _standalone_status(payload: bytes) -> str:
    """retail | applied | legacy (revision 1 or 2: the revision-1 sites with their revision-1/2 bytes, the
    revision-2 sites retail or applied, the revision-3 sites retail) | foreign."""
    try:
        image = XbeImage(payload)
        states = {}
        for site in sites():
            state = _site_state(image, site)
            if state == "foreign" and site.va in PREVIOUS and \
                    hashlib.sha256(image.read(site.va, len(site.patched))).hexdigest() == PREVIOUS[site.va]:
                state = "previous"
            states[site.va] = state
        unique = set(states.values())
        if len(unique) == 1 and unique <= {"applied", "retail"}:
            return next(iter(unique))
        core = {state for va, state in states.items() if va not in REVISION_2_SITES | REVISION_3_SITES}
        if core <= {"applied", "previous"} and "previous" in core and \
                {states[va] for va in REVISION_3_SITES} == {"retail"} and \
                len({states[va] for va in REVISION_2_SITES}) == 1 and states[VETERAN_CUT_SURPLUS] in ("retail", "applied"):
            return "legacy"
        return "foreign"
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
    todo = sites()
    if state == "legacy":
        # A revision-1/2 image: rewrite only the sites that differ in its owner view; the CPU fill entry
        # 0x322BB0 may belong to the shared practice-squad chain and is already correct.
        from . import nfl2k5_roster_fill_composition as composition
        view = XbeImage(composition.project(payload, "economy"))
        todo = tuple(s for s in todo if _site_state(view, s) != "applied")
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
