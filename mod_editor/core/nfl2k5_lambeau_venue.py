"""Lambeau Field venue record (experimental): the Packers' stadium row (s10) in the main ROST.

Job st2 (2026-09-28). The retail row names Lambeau Field, Green Bay, WI (capacity 72,515); the 2026 venue names (job
u4) leave it (same building, same name). With the Lambeau Field model on, the row keeps its strings and takes the
stadium's capacity since the 2013 south end zone expansion:

* the name, display name and location stay as retail (no string is repacked);
* +0x04, the capacity: 81,441 seats (Wikipedia; 80,750 when the south end zone expansion opened in 2013);
* +0x18, the indoor word, stays 0 (open air);
* +0x1C, the surface word, stays 1 (natural grass: SIS Grass, a hybrid grass since 2018);
* the climate floats are untouched.

EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import struct

LABEL = "EXPERIMENTAL / UNWITNESSED"
ROST_OUTER_INDEX = 5
VENUE = "s10"
NAME = "Lambeau Field"
LOCATION = "Green Bay, WI"
CAPACITY = 81441
RETAIL_STRINGS = {"name": "Lambeau Field", "location": "Green Bay, WI", "asset_code": "s10",
                  "display_name": "Lambeau Field", "secondary_label": ""}
#: retail words (+0x04 capacity, +0x18 indoor, +0x1C natural grass)
RETAIL_WORDS = (72515, 0, 1)
LAMBEAU_WORDS = (CAPACITY, 0, 1)
WORD_FIELDS = (0x04, 0x18, 0x1C)


class LambeauVenueError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise LambeauVenueError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def lambeau_strings():
    return dict(RETAIL_STRINGS)


def _words(body, offset):
    return tuple(struct.unpack_from("<I", body, offset + f)[0] for f in WORD_FIELDS)


def _record(body):
    mm = _mm()
    for offset, fields in mm._stadium_records(bytes(body)):
        if fields["asset_code"][1] == VENUE:
            return offset, fields
    return None


def row_state(body):
    """retail / applied / foreign for the s10 row of a ROST body."""
    found = _record(body)
    if found is None:
        return "foreign"
    offset, fields = found
    texts = {name: text for name, (_t, text) in fields.items()}
    words = _words(body, offset)
    if texts != RETAIL_STRINGS:
        return "foreign"
    if words == RETAIL_WORDS:
        return "retail"
    if words == LAMBEAU_WORDS:
        return "applied"
    return "foreign"


def rost_state(resource):
    try:
        from . import nfl2k5_roster_records as rr
        return row_state(resource[rr.RESOURCE_HEADER_SIZE:])
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"


def rost_lambeau(resource):
    """(ROST resource, receipt): the s10 row takes today's capacity (its strings stay as retail); nothing else in the ROST
    changes and a second pass is a no-op."""
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    state = row_state(body)
    if state == "applied":
        return bytes(resource), dict(label=LABEL, records=[dict(venue=VENUE, state="already_applied")])
    require(state == "retail", "the s10 stadium row is neither retail nor Lambeau Field's")
    offset, _fields = _record(body)
    before = _words(body, offset)
    for field, value in zip(WORD_FIELDS, LAMBEAU_WORDS):
        struct.pack_into("<I", body, offset + field, value)
    require(row_state(body) == "applied", "s10: the Lambeau Field row read-back differs")
    receipt = dict(label=LABEL, records=[dict(venue=VENUE, state="applied", record_offset=offset, block=None,
                                              bytes_used=0, words_before=list(before),
                                              words_after=list(LAMBEAU_WORDS))])
    return bytes(resource[:header]) + bytes(body), receipt


def apply_rost(archive):
    """Write the s10 row into the image's main ROST (same size, in place); returns the receipt."""
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the Packers stadium row is {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_lambeau(data)
    require(len(after) == len(data), "the Lambeau Field row changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the Lambeau Field row read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))
