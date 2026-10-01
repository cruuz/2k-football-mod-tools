"""EverBank Stadium venue record (experimental): the Jaguars' stadium row (s12) in the main ROST.

Job st2 (2026-09-28). The retail row names ALLTEL Stadium, Jacksonville, FL (capacity 73,000); the 2026 venue names (job
u4) rename it EverBank Stadium and keep its location. With the EverBank Stadium model on, the row takes exactly u4's
strings (so the two compose in either order: the same bytes whichever runs first) and the season's capacity:

* the name and display name "EverBank Stadium" with the location "Jacksonville, FL" (u4's), through the same in-place
  string-block repack Modern MetLife, SoFi, Highmark, AT&T, Levi's, Allegiant and the 2026 venue names use; the asset code
  stays;
* +0x04, the capacity: 42,507 with the 2026 construction (SOURCED: jaguars.com 2026-02-25, standing room included;
  Wikipedia), 67,814 without it (the 2025 stadium, the Jaguars' 2018 media guide via Wikipedia);
* +0x18, the indoor word, stays 0 (open air);
* +0x1C, the surface word, stays 1 (natural grass: Tifway 419 Bermuda, Wikipedia);
* the climate floats are untouched.

EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import struct

LABEL = "EXPERIMENTAL / UNWITNESSED"
ROST_OUTER_INDEX = 5
VENUE = "s12"
NAME = "EverBank Stadium"
LOCATION = "Jacksonville, FL"
CAPACITY = 42507
CLASSIC_CAPACITY = 67814
RETAIL_STRINGS = {"name": "ALLTEL Stadium", "location": "Jacksonville, FL", "asset_code": "s12",
                  "display_name": "ALLTEL Stadium", "secondary_label": ""}
#: retail words (+0x04 capacity, +0x18 indoor, +0x1C natural grass)
RETAIL_WORDS = (73000, 0, 1)
EVERBANK_WORDS = (CAPACITY, 0, 1)
CLASSIC_WORDS = (CLASSIC_CAPACITY, 0, 1)
WORD_FIELDS = (0x04, 0x18, 0x1C)


class EverBankVenueError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise EverBankVenueError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def everbank_strings():
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
    """retail / applied / foreign for the s12 row of a ROST body."""
    found = _record(body)
    if found is None:
        return "foreign"
    offset, fields = found
    texts = {name: text for name, (_t, text) in fields.items()}
    words = _words(body, offset)
    if texts in (RETAIL_STRINGS, everbank_strings()) and words == RETAIL_WORDS:
        return "retail"           # retail, or u4's 2026 name on the retail words: this module's input either way
    if texts == everbank_strings() and words in (EVERBANK_WORDS, CLASSIC_WORDS):
        return "applied"
    return "foreign"


def rost_state(resource):
    try:
        from . import nfl2k5_roster_records as rr
        return row_state(resource[rr.RESOURCE_HEADER_SIZE:])
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"


def rost_everbank(resource, construction=True):
    """(ROST resource, receipt): the s12 row names EverBank Stadium (u4's strings) with the season's capacity (42,507 with
    the 2026 construction, 67,814 without); nothing else in the ROST changes and a second pass is a no-op."""
    words_after = EVERBANK_WORDS if construction else CLASSIC_WORDS
    mm = _mm()
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    state = row_state(body)
    if state == "applied":
        return bytes(resource), dict(label=LABEL, records=[dict(venue=VENUE, state="already_applied")])
    require(state == "retail", "the s12 stadium row is neither retail nor EverBank Stadium")
    records = mm._stadium_records(bytes(body))
    text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
    offset, fields = _record(body)
    if {name: text for name, (_t, text) in fields.items()} == everbank_strings():
        # u4's 2026 names ran first: the strings are already this row's, only the words change
        before = _words(body, offset)
        for field, value in zip(WORD_FIELDS, words_after):
            struct.pack_into("<I", body, offset + field, value)
        require(row_state(body) == "applied", "s12: the EverBank Stadium row read-back differs")
        receipt = dict(label=LABEL, records=[dict(venue=VENUE, state="applied", record_offset=offset, block=None,
                                                  bytes_used=0, words_before=list(before),
                                                  words_after=list(words_after))])
        return bytes(resource[:header]) + bytes(body), receipt
    block = mm._string_block(fields)
    require(block is not None, "s12: stadium strings are not one contiguous block")
    start, end = block
    pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
    stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
    require(not stray, f"s12: other pointers reach the stadium strings at {stray[:4]}")
    wanted = everbank_strings()
    layout = [("name", NAME), ("location", LOCATION), ("asset_code", wanted["asset_code"]),
              ("secondary_label", wanted["secondary_label"])]
    payload, at = bytearray(), {}
    for key, text in layout:
        at[key] = start + len(payload)
        payload += text.encode("utf-16le") + b"\0\0"
    used = len(payload)
    require(used <= end - start, "s12: the EverBank Stadium strings do not fit the retail block")
    body[start:end] = bytes(payload) + bytes(end - start - used)
    at["display_name"] = at["name"]
    for field, name in mm.ROST_STRING_FIELDS:
        struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
    before = _words(body, offset)
    for field, value in zip(WORD_FIELDS, words_after):
        struct.pack_into("<I", body, offset + field, value)
    require(row_state(body) == "applied", "s12: the EverBank Stadium row read-back differs")
    receipt = dict(label=LABEL, records=[dict(venue=VENUE, state="applied", record_offset=offset, block=[start, end],
                                              bytes_used=used, words_before=list(before),
                                              words_after=list(words_after))])
    return bytes(resource[:header]) + bytes(body), receipt


def apply_rost(archive, construction=True):
    """Write the s12 row into the image's main ROST (same size, in place); returns the receipt."""
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the Jaguars stadium row is {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_everbank(data, construction=construction)
    require(len(after) == len(data), "the EverBank Stadium row changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the EverBank Stadium row read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))
