"""Levi's Stadium venue record (experimental): the 49ers' stadium row (s25) in the main ROST.

Job st2 (2026-09-25). The retail row names San Francisco Park, San Francisco, CA; the 2026 venue names (job u4) keep it,
because the 2004 building is the one the game draws. With the Levi's Stadium model on, the row names the new building:

* the name and display name "Levi's Stadium" and the location "Santa Clara, CA" (Wikipedia "Levi's Stadium"), through the
  same in-place string-block repack Modern MetLife, SoFi, Highmark Stadium, AT&T Stadium and the 2026 venue names use;
  the asset code (the engine's file-name key) stays;
* +0x04, the capacity: 68,500 seats (Wikipedia; expandable to about 75,000; retail 70,270);
* +0x18, the indoor word, stays 0: the stadium is open (rain and snow fall on the field in those bundles);
* +0x1C, the surface word, stays 1 (natural grass: Bermuda and rye, Wikipedia);
* the climate floats are untouched.

EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import struct

LABEL = "EXPERIMENTAL / UNWITNESSED"
ROST_OUTER_INDEX = 5
VENUE = "s25"
NAME = "Levi's Stadium"
LOCATION = "Santa Clara, CA"
CAPACITY = 68500
RETAIL_STRINGS = {"name": "San Francisco Park", "location": "San Francisco, CA", "asset_code": "s25",
                  "display_name": "San Francisco Park", "secondary_label": ""}
#: retail words (+0x04 capacity, +0x18 indoor, +0x1C natural grass)
RETAIL_WORDS = (70270, 0, 1)
LEVIS_WORDS = (CAPACITY, 0, 1)
WORD_FIELDS = (0x04, 0x18, 0x1C)


class LevisVenueError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise LevisVenueError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def levis_strings():
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
    """retail / applied / foreign for the s25 row of a ROST body."""
    found = _record(body)
    if found is None:
        return "foreign"
    offset, fields = found
    texts = {name: text for name, (_t, text) in fields.items()}
    words = _words(body, offset)
    if texts == RETAIL_STRINGS and words == RETAIL_WORDS:
        return "retail"
    if texts == levis_strings() and words == LEVIS_WORDS:
        return "applied"
    return "foreign"


def rost_state(resource):
    try:
        from . import nfl2k5_roster_records as rr
        return row_state(resource[rr.RESOURCE_HEADER_SIZE:])
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"


def rost_levis(resource):
    """(ROST resource, receipt): the s25 row names Levi's Stadium with its location and capacity; nothing else in the
    ROST changes and a second pass is a no-op."""
    mm = _mm()
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    state = row_state(body)
    if state == "applied":
        return bytes(resource), dict(label=LABEL, records=[dict(venue=VENUE, state="already_applied")])
    require(state == "retail", "the s25 stadium row is neither retail nor Levi's Stadium")
    records = mm._stadium_records(bytes(body))
    text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
    offset, fields = _record(body)
    block = mm._string_block(fields)
    require(block is not None, "s25: stadium strings are not one contiguous block")
    start, end = block
    pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
    stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
    require(not stray, f"s25: other pointers reach the stadium strings at {stray[:4]}")
    wanted = levis_strings()
    layout = [("name", NAME), ("location", LOCATION), ("asset_code", wanted["asset_code"]),
              ("secondary_label", wanted["secondary_label"])]
    payload, at = bytearray(), {}
    for key, text in layout:
        at[key] = start + len(payload)
        payload += text.encode("utf-16le") + b"\0\0"
    used = len(payload)
    require(used <= end - start, "s25: the Levi's Stadium strings do not fit the retail block")
    body[start:end] = bytes(payload) + bytes(end - start - used)
    at["display_name"] = at["name"]
    for field, name in mm.ROST_STRING_FIELDS:
        struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
    before = _words(body, offset)
    for field, value in zip(WORD_FIELDS, LEVIS_WORDS):
        struct.pack_into("<I", body, offset + field, value)
    require(row_state(body) == "applied", "s25: the Levi's Stadium row read-back differs")
    receipt = dict(label=LABEL, records=[dict(venue=VENUE, state="applied", record_offset=offset, block=[start, end],
                                              bytes_used=used, words_before=list(before),
                                              words_after=list(LEVIS_WORDS))])
    return bytes(resource[:header]) + bytes(body), receipt


def apply_rost(archive):
    """Write the s25 row into the image's main ROST (same size, in place); returns the receipt."""
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the 49ers stadium row is {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_levis(data)
    require(len(after) == len(data), "the Levi's Stadium row changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the Levi's Stadium row read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))
