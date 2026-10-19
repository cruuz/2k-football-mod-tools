"""Formation play-menu pages that repeat a play (b776, job pb2).

The play-call screen shows a formation's plays three at a time. The first page is the formation's three featured links
(selection groups 0, 1 and 2); every later page lists the next three links in order. A formation whose link count is
not a multiple of three leaves its last page short, and the screen fills the empty buttons by repeating the last play:
Noah's 10/18 video shows the Bears' Singleback Bunch (10 links) ending on a page of Bubble Screen, Bubble Screen,
Bubble Screen, and another page of PA Dagger three times. The formation has no duplicate link (a duplicated link makes
the menu walk endless, see test_nfl2k5_play_menu_walk); the repeat is only the padding of a short page.

Retail keeps 95% of its offensive formations at a multiple of three links (879 of 927 in the 34 team and generic books);
the b775 team books kept only 46% (424 of 927 were short), which is why their menus looked repetitive.

``padding_report`` lists every short formation of a PLAY resource and what it would take to fix it, and
``summary`` totals a set of books. Fixing a book means giving each short formation distinct extra plays (never a
duplicate link) or dropping its surplus, which is a playbook-authoring decision: this module only measures.
"""
from __future__ import annotations

import struct
from typing import Iterable, Mapping

from . import nfl2k5_playbook_inspector as ip

PAGE = 3
SCHEMA = "nfl2k5_formation_menu_pages/v1"


def formation_type(body: bytes, index: int) -> int:
    flags = struct.unpack_from("<I", body, ip.FORMATION_BASE + index * ip.FORMATION_SIZE + 4)[0]
    return (flags >> 8) & 63


def padding_report(resource: bytes, *, offense_only: bool = True) -> list[dict]:
    """One row per formation whose last menu page is short: ``links``, ``pad`` (buttons that repeat the last
    play), ``adds`` (distinct plays to add for full pages), ``trim`` (links to drop instead) and ``repeated_play``."""
    book = ip.parse_playbook_resource(resource)
    body = resource[ip.RESOURCE_HEADER_SIZE:]
    rows = []
    for formation in book.formations:
        kind = formation_type(body, formation.index)
        if offense_only and kind >= 4:
            continue
        links = len(formation.play_links)
        if not links or links % PAGE == 0:
            continue
        last = book.plays[formation.play_links[-1].play_index]
        rows.append(dict(formation=formation.index, name=formation.name.strip(), type=kind, links=links,
                         pad=-links % PAGE, adds=-links % PAGE, trim=links % PAGE,
                         repeated_play=last.name.strip()))
    return rows


def summary(books: Mapping[str, bytes] | Iterable[tuple[str, bytes]], *, offense_only: bool = True) -> dict:
    """Totals over named books: formations, short formations, buttons that repeat a play, and the per-book rows."""
    items = books.items() if isinstance(books, Mapping) else books
    per_book, formations = {}, 0
    for name, resource in items:
        book = ip.parse_playbook_resource(resource)
        body = resource[ip.RESOURCE_HEADER_SIZE:]
        count = sum(1 for f in book.formations if not offense_only or formation_type(body, f.index) < 4)
        short = padding_report(resource, offense_only=offense_only)
        formations += count
        per_book[name] = dict(formations=count, short=len(short), repeated_buttons=sum(r["pad"] for r in short))
    short_total = sum(v["short"] for v in per_book.values())
    return dict(schema=SCHEMA, formations=formations, short_formations=short_total,
                repeated_buttons=sum(v["repeated_buttons"] for v in per_book.values()),
                full_page_share=round(1 - short_total / formations, 4) if formations else None,
                books=per_book)
