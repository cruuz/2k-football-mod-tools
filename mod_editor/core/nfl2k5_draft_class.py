"""Draft classes with a real position mix, on every build with the franchise draft fixes (b780 b1-draft).

Row B1 of the b780 bug list. SharkMagick 11/01, original 2004 rosters: "kickers getting drafted in R3 again",
"6 by my count", "even punters are getting drafted in r3", "only one qb". SWeaR 10/27: after the first draft
"I only have 4 QBs to draft from".

PROVED OFFLINE (Unicorn, the game's own class generator and CPU draft, b779 rc1 and this job): the retail class
generator (0x2BE940 -> loop 0x2BE900) takes the first free player records (allocator 0x2BD390: bit 2 clear, from
record 0 on) and hands each new prospect the reused record's OLD position (0x2BE91D movzx edx, [eax+0x35]). So a
class is shaped by whoever left the league: undrafted kickers and punters retire as free agents and come back as
kicker and punter records, while the quarterbacks the CPU drafts stay on rosters. The disc's own first class
already has 19 K and 23 P in 380. Measured on the original rosters with the Basic preset (b780 b1-draft, three
native drafts): class 2 had 15 QB, 16 K, 15 P, 47 CB, 38 OLB, 9 C and 14 of its 15 quarterbacks were drafted;
class 3 had 22 K, 24 P, 5 FS, 10 C and left no TE or T undrafted. The allocator also counts Create Player
vacancies (flags & 5 == 1) as free and spends them: the original rosters' 155 were all gone by the third draft.

b779 rc1 fixed this inside franchise economy revision 4, which is off in every preset. This owner installs that
class half on its own:
- the allocator (0x2BD3C0) and the retirement pass's free count (0x2BDCAE) skip create vacancies, so Create
  Player, MyCareer and moment/historic imports keep their records and the top-up frees enough other records;
- prospect k of a class takes slot (k - 1) x 151 mod 450 of a fixed position mix (0x2BE91D): QB 21, K 9, P 9,
  WR 37, CB 44, FS 18, SS 14, HB 25, FB 9, TE 25, OLB 18, ILB 18, C 30, G 28, T 44, DT 49, DE 52 per 450, with
  OLB slots as LB when no rostered player carries OLB (the one-pool scheme). A 380-player class (the retail size,
  every class without the economy) visits slots 0..379 of that walk: QB 21, K 9, P 9, WR 37, CB 31, FS 12, SS 10,
  HB 25, FB 9, TE 25, OLB 18, ILB 12, C 20, G 20, T 44, DT 43, DE 35 (the 70 unvisited slots fall in three bands).

The code is the economy's own window "roster_f" (0x382200..0x3822BF, an unreferenced retail library function,
tools/franchise_economy/dead_code.py) and the three call sites, byte for byte. With the economy on, the economy
owns the same bytes (nfl2k5_franchise_economy.CLASS_SITES); the class size, the age-based record supply and the
rest of the economy stay behind the economy option. No allocator bytes, no save change.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_cave_oracle import XbeImage
from . import nfl2k5_franchise_economy as economy

BUILD_CAPTION = "draft class position mix"
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
MIX_OFFSET = 0xAC          # class_counts[17] inside window roster_f (runtime.c, .roster_f_rodata)
CLASS_SIZE = 450


class DraftClassError(ValueError):
    """The draft class sites are not in a state this owner can install over."""


def sites() -> tuple[economy.Site, ...]:
    """The four revision-4 economy sites that make up the class fix, with the economy's own bytes and pins."""
    return tuple(s for s in economy.sites() if s.va in economy.CLASS_SITES)


def mix() -> dict[str, int]:
    """The position mix per CLASS_SIZE prospects, as the installed window carries it."""
    window = next(s.patched for s in sites() if s.va == economy.CLASS_WINDOW)
    counts = window[MIX_OFFSET:MIX_OFFSET + len(POSITIONS)]
    if sum(counts) != CLASS_SIZE:
        raise DraftClassError("the class window's position mix does not add up to a full class")
    return dict(zip(POSITIONS, counts))


def _state(image: XbeImage, site: economy.Site) -> str:
    current = image.read(site.va, len(site.patched))
    return ("applied" if current == site.patched else
            "retail" if hashlib.sha256(current).hexdigest() == site.digest else "foreign")


def status(payload: bytes) -> str:
    """retail | applied | foreign. No other owner shares these sites (the economy writes the same bytes)."""
    try:
        image = XbeImage(payload)
        states = {_state(image, site) for site in sites()}
    except (ValueError, struct.error, IndexError, StopIteration):
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "changed_bytes": 0}
    if state != "retail":
        raise DraftClassError(f"draft class sites are {state}; refusing to patch")
    image, out = XbeImage(payload), bytearray(payload)
    sections, touched, edits = _sections(payload), set(), []
    for site in sites():
        offset = image.offset(site.va, len(site.patched))
        out[offset:offset + len(site.patched)] = site.patched
        touched.add(_section_for_offset(sections, offset).index)
        edits.append({"va": hex(site.va), "bytes": len(site.patched), "retail_sha256": site.digest})
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            out[at:at + 20] = section_digest(bytes(out), section)
    result = bytes(out)
    if status(result) != "applied" or economy.status(result) != economy.status(payload):
        raise DraftClassError("draft class post-apply verification failed")
    return result, {"evidence": "PROVED OFFLINE", "changed_bytes": sum(a != b for a, b in zip(payload, result)),
                    "edits": edits, "sections_repinned": sorted(touched), "mix_per_450": mix(),
                    "keeps_create_vacancies": True}


__all__ = ["BUILD_CAPTION", "DraftClassError", "apply", "mix", "sites", "status"]
