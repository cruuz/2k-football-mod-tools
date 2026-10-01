"""SoFi Stadium venue records (experimental): the Rams (s23), Chargers (s24) and first Super Bowl (s40) stadium rows in
the main ROST.

The Super Bowl row (main's option 1, 2026-09-24): in the season phase 9, week 20, the executable picks the venue by
the season index from six asset codes, s40 first (PROVED OFFLINE, deliverable section 10), so a franchise's first
Super Bowl is played in row s40, retail "Super Bowl 2005" in Jacksonville. Super Bowl LXI is at SoFi Stadium on
2027-02-14: the row keeps the event as its name ("Super Bowl LXI") with "SoFi Stadium" as its display name, takes
SoFi's location, capacity, roof, turf and climate, and the XBE's codes stay as they are.

Job u6 (2026-09-24). The retail game has one stadium row per home team (82 rows, 0x80 bytes each, main ROST outer 5).
SoFi Stadium is one building shared by two venue records, as Giants Stadium is in retail (s18, s19). This module
writes what the two rows say about the building:

* the name and display name "SoFi Stadium" and the location "Inglewood, CA", through the same in-place string-block
  repack Modern MetLife and the 2026 venue names use (the asset code, the engine's file-name key, stays);
* +0x04, the capacity (retail Edward Jones Dome 66,000, QUALCOMM Stadium 71,500): 70,240 (SoFi Stadium's standard
  capacity);
* the climate (+0x28 to +0x7B: seven temperatures, seven precipitation thresholds, seven winds): the Rams row takes
  the Chargers row's floats, so the one building rolls one weather (main, 2026-09-24). Retail s23 holds 70 F and 0%
  in every month; s24 (San Diego) never gets below the 35 F snow split, so neither row rolls snow, and a rain roll
  loads the rain bundle while the indoor reset keeps the bowl dry. The copy runs on every apply, after any climate
  edits, so a build always ends with the two rows alike;
* +0x18, the indoor word, and +0x1C, the surface (1 on the natural grass rows, 0 on the turf rows): SoFi is roofed
  and plays on artificial turf, so s24 takes s23's values (indoor 1, turf 0). s23 already has them.

What the indoor word does (read from the executable, PROVED OFFLINE by a native run of the retail routines on these
rows, job u6): 0x62BE0 names the stadium bundle from the generated weather first, then 0x62CC5 resets wind,
precipitation and haze to zero and the temperature to 70 F; the team packages named after the reset take their dry
variants; 0x641C0 selects the night/indoor light rig; the haze reader, the player-shadow setup (shadow mode 2 from the
flare markers) and the weather classifiers at 0xA8EC14 treat the venue as indoors. The surface word selects the
player-shadow scene (``shadow_100`` on turf, ``shadow_low`` on grass at night or indoors) and the grass-only effect
and physics paths. EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import struct

LABEL = "EXPERIMENTAL / UNWITNESSED"
ROST_OUTER_INDEX = 5
VENUES = ("s23", "s24")
#: the Super Bowl venue of a franchise's first season (the XBE's season index 0; main's option 1): Super Bowl LXI is
#: played at SoFi Stadium on 2027-02-14, so its row becomes SoFi with the event's name
SUPER_BOWL = "s40"
ROWS = VENUES + (SUPER_BOWL,)
NAME = "SoFi Stadium"
SUPER_BOWL_NAME = "Super Bowl LXI"
LOCATION = "Inglewood, CA"
CAPACITY = 70240
#: retail strings of the two rows (job u4's names table records the same)
RETAIL_STRINGS = {
    "s23": {"name": "Edward Jones Dome ", "location": "St. Louis, MO", "asset_code": "s23",
            "display_name": "Edward Jones Dome ", "secondary_label": ""},
    "s24": {"name": "QUALCOMM Stadium", "location": "San Diego, CA", "asset_code": "s24",
            "display_name": "QUALCOMM Stadium", "secondary_label": ""},
    "s40": {"name": "Super Bowl 2005", "location": "Jacksonville, FL", "asset_code": "s40",
            "display_name": "Super Bowl 2005 Stadium", "secondary_label": ""},
}
#: retail words (+0x04 capacity, +0x18 indoor, +0x1C natural grass)
RETAIL_WORDS = {"s23": (66000, 1, 0), "s24": (71500, 0, 1), "s40": (73000, 0, 1)}
SOFI_WORDS = (CAPACITY, 1, 0)
WORD_FIELDS = (0x04, 0x18, 0x1C)
CLIMATE = (0x28, 0x7C)          # [start, end) of the climate floats in a row


class SofiVenueError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise SofiVenueError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def sofi_strings(code):
    """The row's SoFi strings: the team rows name the stadium; the Super Bowl row keeps the event as its name (the
    retail row reads "Super Bowl 2005" and "Super Bowl 2005 Stadium") and shows SoFi Stadium as its display name."""
    name = SUPER_BOWL_NAME if code == SUPER_BOWL else NAME
    return dict(RETAIL_STRINGS[code], name=name, display_name=NAME, location=LOCATION)


def _words(body, offset):
    return tuple(struct.unpack_from("<I", body, offset + f)[0] for f in WORD_FIELDS)


def _records(body):
    mm = _mm()
    return {fields["asset_code"][1]: (offset, fields) for offset, fields in mm._stadium_records(bytes(body))}


def row_state(body, code):
    """retail / applied / foreign for one of the two rows of a ROST body."""
    records = _records(body)
    if code not in records:
        return "foreign"
    offset, fields = records[code]
    texts = {name: text for name, (_t, text) in fields.items()}
    words = _words(body, offset)
    if texts == RETAIL_STRINGS[code] and words == RETAIL_WORDS[code]:
        return "retail"
    if texts == sofi_strings(code) and words == SOFI_WORDS:
        return "applied"
    return "foreign"


def rost_state(resource):
    """retail / applied / mixed / foreign for the SoFi rows (the two teams' and the Super Bowl's) of one ROST."""
    try:
        from . import nfl2k5_roster_records as rr
        body = resource[rr.RESOURCE_HEADER_SIZE:]
        states = {row_state(body, code) for code in ROWS}
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"
    if "foreign" in states:
        return "foreign"
    return states.pop() if len(states) == 1 else "mixed"


def rost_sofi(resource):
    """(ROST resource, receipt): both rows name SoFi Stadium, Inglewood, CA, with SoFi's capacity, roof and turf.

    Strings: Modern MetLife's in-place repack of each row's contiguous string block (one shared "SoFi Stadium" for
    the name and display name, then the location, the asset code and the secondary label), zero-filled to the retail
    block end, with the five relative pointers rewritten; any other pointer into a block refuses. Words: +0x04,
    +0x18 and +0x1C set in place. Nothing else in the ROST changes, and a second pass is a no-op.
    """
    mm = _mm()
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    receipt = dict(label=LABEL, records=[])
    records = mm._stadium_records(bytes(body))
    text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
    for code in ROWS:
        state = row_state(body, code)
        if state == "applied":
            receipt["records"].append(dict(venue=code, state="already_applied"))
            continue
        require(state == "retail", f"{code}: the stadium row is neither retail nor SoFi")
        offset, fields = _records(body)[code]
        block = mm._string_block(fields)
        require(block is not None, f"{code}: stadium strings are not one contiguous block")
        start, end = block
        pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
        stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
        require(not stray, f"{code}: other pointers reach the stadium strings at {stray[:4]}")
        wanted = sofi_strings(code)
        layout = [("name", wanted["name"])]
        if wanted["display_name"] != wanted["name"]:
            layout.append(("display_name", wanted["display_name"]))
        layout += [("location", LOCATION), ("asset_code", wanted["asset_code"]),
                   ("secondary_label", wanted["secondary_label"])]
        payload, at = bytearray(), {}
        for key, text in layout:
            at[key] = start + len(payload)
            payload += text.encode("utf-16le") + b"\0\0"
        used = len(payload)
        require(used <= end - start, f"{code}: the SoFi strings do not fit the retail block")
        body[start:end] = bytes(payload) + bytes(end - start - used)
        at.setdefault("display_name", at["name"])
        for field, name in mm.ROST_STRING_FIELDS:
            struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
        before = _words(body, offset)
        for field, value in zip(WORD_FIELDS, SOFI_WORDS):
            struct.pack_into("<I", body, offset + field, value)
        require(row_state(body, code) == "applied", f"{code}: the SoFi row read-back differs")
        receipt["records"].append(dict(venue=code, state="applied", record_offset=offset, block=[start, end],
                                       bytes_used=used, words_before=list(before), words_after=list(SOFI_WORDS)))
    receipt["climate"] = sync_climate(body)
    return bytes(resource[:header]) + bytes(body), receipt


def sync_climate(body):
    """Copy the Chargers row's climate floats into the Rams row and the Super Bowl row (in place); returns what
    changed (the first entry is the Rams row, as before)."""
    records = _records(body)
    a, b = CLIMATE
    src = records["s24"][0]
    out = []
    for target in ("s23", SUPER_BOWL):
        dst = records[target][0]
        before = bytes(body[dst + a:dst + b])
        body[dst + a:dst + b] = body[src + a:src + b]
        out.append(dict(source="s24", target=target, changed=before != bytes(body[dst + a:dst + b]),
                        before_sha256=sha(before), after_sha256=sha(body[dst + a:dst + b])))
    return dict(out[0], also=out[1:])


def climate_synced(resource):
    from . import nfl2k5_roster_records as rr
    body = resource[rr.RESOURCE_HEADER_SIZE:]
    records = _records(body)
    a, b = CLIMATE
    src = body[records["s24"][0] + a:records["s24"][0] + b]
    return all(body[records[t][0] + a:records[t][0] + b] == src for t in ("s23", SUPER_BOWL))


def apply_rost(archive):
    """Write the two SoFi rows into the image's main ROST (same size, in place); returns the receipt."""
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the Rams, Chargers and Super Bowl stadium rows are {state}; rebuild from a "
            "supported base")
    if state == "applied" and climate_synced(data):
        return dict(state="already_applied")
    after, receipt = rost_sofi(data)
    require(len(after) == len(data), "the SoFi rows changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the SoFi rows read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))
