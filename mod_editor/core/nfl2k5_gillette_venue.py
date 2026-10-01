"""Gillette Stadium venue record (experimental): the Patriots' stadium row (s16) in the main ROST.

Job st2 (2026-09-28). The retail row names Gillette Stadium, Foxboro, MA (capacity 68,000); the 2026 venue names (job u4)
leave it. With the Gillette Stadium model on, the row takes the town's own spelling and the current capacity:

* the name and display name "Gillette Stadium" with the location "Foxborough, MA" (the stadium's address), through the
  same in-place string-block repack the other rows use; the asset code stays;
* +0x04, the capacity: 64,628 seats (Wikipedia);
* +0x18, the indoor word, stays 0 (open air);
* +0x1C, the surface word, stays 1 (retail's grass word: the grass word is Noah's call and stays retail; Modern playing
  surfaces draws the 2026 turf);
* the climate floats are untouched.

EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import struct

LABEL = "EXPERIMENTAL / UNWITNESSED"
ROST_OUTER_INDEX = 5
VENUE = "s16"
NAME = "Gillette Stadium"
LOCATION = "Foxborough, MA"
CAPACITY = 64628
RETAIL_STRINGS = {"name": "Gillette Stadium", "location": "Foxboro, MA", "asset_code": "s16",
                  "display_name": "Gillette Stadium", "secondary_label": ""}
#: retail words (+0x04 capacity, +0x18 indoor, +0x1C natural grass)
RETAIL_WORDS = (68000, 0, 1)
GILLETTE_WORDS = (CAPACITY, 0, 1)
WORD_FIELDS = (0x04, 0x18, 0x1C)


class GilletteVenueError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise GilletteVenueError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def gillette_strings():
    return dict(RETAIL_STRINGS, name=NAME, display_name=NAME, location=LOCATION)


def _words(body, offset):
    return tuple(struct.unpack_from("<I", body, offset + f)[0] for f in WORD_FIELDS)


def _record(body):
    mm = _mm()
    for offset, fields in mm._stadium_records(bytes(body)):
        if fields["asset_code"][1] == VENUE:
            return offset, fields
    return None


def row_state(body):
    """retail / applied / foreign for the s16 row of a ROST body."""
    found = _record(body)
    if found is None:
        return "foreign"
    offset, fields = found
    texts = {name: text for name, (_t, text) in fields.items()}
    words = _words(body, offset)
    if texts == RETAIL_STRINGS and words == RETAIL_WORDS:
        return "retail"
    if texts == gillette_strings() and words == GILLETTE_WORDS:
        return "applied"
    return "foreign"


def rost_state(resource):
    try:
        from . import nfl2k5_roster_records as rr
        return row_state(resource[rr.RESOURCE_HEADER_SIZE:])
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"


def rost_gillette(resource):
    """(ROST resource, receipt): the s16 row names Gillette Stadium (u4's strings) with the modernized capacity; nothing
    else in the ROST changes and a second pass is a no-op."""
    mm = _mm()
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    state = row_state(body)
    if state == "applied":
        return bytes(resource), dict(label=LABEL, records=[dict(venue=VENUE, state="already_applied")])
    require(state == "retail", "the s16 stadium row is neither retail nor Gillette Stadium")
    records = mm._stadium_records(bytes(body))
    text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
    offset, fields = _record(body)
    block = mm._string_block(fields)
    require(block is not None, "s16: stadium strings are not one contiguous block")
    start, end = block
    pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
    stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
    require(not stray, f"s16: other pointers reach the stadium strings at {stray[:4]}")
    wanted = gillette_strings()
    layout = [("name", NAME), ("location", LOCATION), ("asset_code", wanted["asset_code"]),
              ("secondary_label", wanted["secondary_label"])]
    payload, at = bytearray(), {}
    for key, text in layout:
        at[key] = start + len(payload)
        payload += text.encode("utf-16le") + b"\0\0"
    used = len(payload)
    require(used <= end - start, "s16: the Gillette Stadium strings do not fit the retail block")
    body[start:end] = bytes(payload) + bytes(end - start - used)
    at["display_name"] = at["name"]
    for field, name in mm.ROST_STRING_FIELDS:
        struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
    before = _words(body, offset)
    for field, value in zip(WORD_FIELDS, GILLETTE_WORDS):
        struct.pack_into("<I", body, offset + field, value)
    require(row_state(body) == "applied", "s16: the Gillette Stadium row read-back differs")
    receipt = dict(label=LABEL, records=[dict(venue=VENUE, state="applied", record_offset=offset, block=[start, end],
                                              bytes_used=used, words_before=list(before),
                                              words_after=list(GILLETTE_WORDS))])
    return bytes(resource[:header]) + bytes(body), receipt


def apply_rost(archive):
    """Write the s16 row into the image's main ROST (same size, in place); returns the receipt."""
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the Patriots stadium row is {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_gillette(data)
    require(len(after) == len(data), "the Gillette Stadium row changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the Gillette Stadium row read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))
