"""U.S. Bank Stadium venue record (experimental): the Vikings' stadium row (s15) in the main ROST.

Job st3 (2026-09-27). The retail row names the H. H. H. Metrodome, Minneapolis, MN; the 2026 venue names (job u4) keep it,
because the 2004 building is the one the game draws. With the U.S. Bank Stadium model on, the row names the new building:

* the name and display name "U.S. Bank Stadium" (Wikipedia "U.S. Bank Stadium"; the stadium's own fact guide), through
  the same in-place string-block repack Modern MetLife, SoFi, Highmark, AT&T, Levi's and the 2026 venue names use; the
  location stays "Minneapolis, MN" and the asset code (the engine's file-name key) stays;
* +0x04, the capacity: 66,202 seats (the 2022 Vikings media guide via Wikipedia; expandable to 73,000; retail 64,121);
* +0x18, the indoor word, stays 1: the roof is fixed (the retail Metrodome row is indoor already);
* +0x1C, the surface word, stays 0 (synthetic: Act Global Xtreme Turf DX, ESPN 2023-12-21);
* the climate floats are untouched (flat 70 F, no precipitation: main, 2026-09-27).

EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import struct

LABEL = "EXPERIMENTAL / UNWITNESSED"
ROST_OUTER_INDEX = 5
VENUE = "s15"
NAME = "U.S. Bank Stadium"
LOCATION = "Minneapolis, MN"
CAPACITY = 66202
RETAIL_STRINGS = {"name": "H. H. H. Metrodome", "location": "Minneapolis, MN", "asset_code": "s15",
                  "display_name": "H. H. H. Metrodome", "secondary_label": ""}
#: retail words (+0x04 capacity, +0x18 indoor, +0x1C natural grass)
RETAIL_WORDS = (64121, 1, 0)
USBANK_WORDS = (CAPACITY, 1, 0)
WORD_FIELDS = (0x04, 0x18, 0x1C)


class USBankVenueError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise USBankVenueError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def usbank_strings():
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
    """retail / applied / foreign for the s15 row of a ROST body."""
    found = _record(body)
    if found is None:
        return "foreign"
    offset, fields = found
    texts = {name: text for name, (_t, text) in fields.items()}
    words = _words(body, offset)
    if texts == RETAIL_STRINGS and words == RETAIL_WORDS:
        return "retail"
    if texts == usbank_strings() and words == USBANK_WORDS:
        return "applied"
    return "foreign"


def rost_state(resource):
    try:
        from . import nfl2k5_roster_records as rr
        return row_state(resource[rr.RESOURCE_HEADER_SIZE:])
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"


def rost_usbank(resource):
    """(ROST resource, receipt): the s15 row names U.S. Bank Stadium with its capacity; nothing else in the ROST changes
    and a second pass is a no-op."""
    mm = _mm()
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    state = row_state(body)
    if state == "applied":
        return bytes(resource), dict(label=LABEL, records=[dict(venue=VENUE, state="already_applied")])
    require(state == "retail", "the s15 stadium row is neither retail nor U.S. Bank Stadium")
    records = mm._stadium_records(bytes(body))
    text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
    offset, fields = _record(body)
    block = mm._string_block(fields)
    require(block is not None, "s15: stadium strings are not one contiguous block")
    start, end = block
    pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
    stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
    require(not stray, f"s15: other pointers reach the stadium strings at {stray[:4]}")
    wanted = usbank_strings()
    layout = [("name", NAME), ("location", LOCATION), ("asset_code", wanted["asset_code"]),
              ("secondary_label", wanted["secondary_label"])]
    payload, at = bytearray(), {}
    for key, text in layout:
        at[key] = start + len(payload)
        payload += text.encode("utf-16le") + b"\0\0"
    used = len(payload)
    require(used <= end - start, "s15: the U.S. Bank Stadium strings do not fit the retail block")
    body[start:end] = bytes(payload) + bytes(end - start - used)
    at["display_name"] = at["name"]
    for field, name in mm.ROST_STRING_FIELDS:
        struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
    before = _words(body, offset)
    for field, value in zip(WORD_FIELDS, USBANK_WORDS):
        struct.pack_into("<I", body, offset + field, value)
    require(row_state(body) == "applied", "s15: the U.S. Bank Stadium row read-back differs")
    receipt = dict(label=LABEL, records=[dict(venue=VENUE, state="applied", record_offset=offset, block=[start, end],
                                              bytes_used=used, words_before=list(before),
                                              words_after=list(USBANK_WORDS))])
    return bytes(resource[:header]) + bytes(body), receipt


def apply_rost(archive):
    """Write the s15 row into the image's main ROST (same size, in place); returns the receipt."""
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the Vikings stadium row is {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_usbank(data)
    require(len(after) == len(data), "the U.S. Bank Stadium row changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the U.S. Bank Stadium row read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))
