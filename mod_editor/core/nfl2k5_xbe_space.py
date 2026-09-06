"""EXPERIMENTAL/UNWITNESSED, bounded grown XBE allocator (USA beta 62).

Legacy one/two-page outputs remain byte compatible. Scale-out groups N pages
into three additional sections: 96 KiB RX, 80 KiB RW and 20 KiB RO (including
one directory page). Existing owner VAs and raw offsets stay fixed. Requests
are immutable and never grow an installed request set in place.
Loader and gameplay behavior remain experimental and unwitnessed.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib

from . import nfl2k5_depth_chart_storage as special
from . import nfl2k5_boot_logo as logo
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_xbe_space"
PAGE = 0x1000
CODE_VA, DATA_VA = 0x14BA000, 0x14BB000
CODE_RAW = special.FILE_SIZE
DATA_RAW = CODE_RAW + PAGE
FILE_SIZE = DATA_RAW + PAGE
IMAGE_SIZE = DATA_VA + PAGE - 0x10000
TABLE = 0x370
COUNT = 22
META_START, META_END, META_COPY = 0x840, 0x904, 0xCC4
META_DELTA = META_COPY - META_START
NAMES = META_COPY + META_END - META_START  # 0xd88
REFS = NAMES + 16  # four distinct 16-bit shared-page counters
DIRECTORY = REFS + 8
MAGIC = b"XSPACE1\0"
EXT_MAGIC = b"XSPACE2\0"
METADATA_SHA256 = "155d094c9592c93f1fd7ce1eb635667d8b88e92cfd46d6e77659e7ae7dd4a252"
GEOMETRY_SHA256 = "904d5748e0650b7627e1d9d77d926088f4cd43749b481455b1803fdc53acd243"
# Keep legacy extents and music VA/raw stable. The intervening music file range
# is zero and unmapped until its separate read-only owner installs it.
CODE2_VA = 0x14D9000  # first post-music page with no byte-granular retail reference encodings
CODE2_RAW = FILE_SIZE + 0x10000
EXT_FILE_SIZE = CODE2_RAW + PAGE
EXT_IMAGE_SIZE = CODE2_VA + PAGE - 0x10000
LIB_START, LIB_END, LIB_COPY = 0x904, 0x9A4, 0xF60
LIB_SHA256 = "2491e839d648e5fd86c2b1ac8332addeac0d3cd38632d82de61f142b3f470070"
LIB_POINTERS = ((0x164, 0x10904), (0x168, 0x10924), (0x16C, 0x10904))
CODE2_NAME, CODE2_REFS = 0x940, 0x948
MUSIC2_NAME, MUSIC2_REFS = 0x950, 0x958
LOGO_REQUEST = ("nfl2k5_boot_logo", "code", logo.LOGO_SIZE, 16)


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _legacy_requests(requests):
    out = []
    for request in requests:
        _require(isinstance(request, (tuple, list)) and len(request) == 4, "request must be (owner, kind, size, align)")
        owner, kind, size, align = request
        _require(isinstance(owner, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", owner), "invalid allocation owner")
        _require(kind in ("code", "data"), "kind must be code or data")
        _require(type(size) is int and 0 < size <= PAGE, "size must be 1..4096")
        _require(type(align) is int and 0 < align <= PAGE and align & (align - 1) == 0, "align must be a power of two <=4096")
        out.append((owner, kind, size, align))
    out.sort()
    _require(len({(o, k) for o, k, _, _ in out}) == len(out), "duplicate owner/kind allocation")
    declared_logo = [r for r in out if r[0] == LOGO_REQUEST[0]]
    _require(not declared_logo or declared_logo == [LOGO_REQUEST], "boot logo has a fixed immutable allocation")
    if not declared_logo:
        out.append(LOGO_REQUEST)
        out.sort()
    return out


# Owners first allocated in beta 62. The v3 scale-out places every non-legacy owner
# on the new page pools, so shipped beta-61 owners keep their addresses.
R62_OWNERS = frozenset({"nfl2k5_roster_storage", "nfl2k5_coverage_slider", "nfl2k5_scramble_tuning"})


def _legacy_allocations(requests):
    cursors = {"code": 0, "data": 0}
    out = []
    # Preserve the already-shipped logo/kickoff/runtime layout when adding the
    # three new owners. Directory order remains canonical and immutable.
    new_owners = {"nfl2k5_defensive_try", "nfl2k5_momentum", "nfl2k5_zone_drop"}
    ordered = sorted(_legacy_requests(requests), key=lambda r: (r[0] in new_owners, r))
    for owner, kind, size, align in ordered:
        offset = (cursors[kind] + align - 1) & -align
        if offset // PAGE != (offset + size - 1) // PAGE:
            offset = (offset + PAGE - 1) & -PAGE
        _require(offset + size <= PAGE * (2 if kind == "code" else 1),
                 f"{kind} page capacity exceeded; no unreserved page may be used")
        if kind == "data":
            va, raw = DATA_VA, DATA_RAW
        elif offset < PAGE:
            va, raw = CODE_VA, CODE_RAW
        else:
            va, raw = CODE2_VA - PAGE, CODE2_RAW - PAGE
        out.append(dict(owner=owner, kind=kind, size=size, align=align, va=va + offset, raw=raw + offset))
        cursors[kind] = offset + size
    return out


def _extended(requests):
    return any(a["va"] >= CODE2_VA for a in _allocations(requests))


def _regions(requests):
    result = [dict(kind=k, va=va, raw=raw, size=PAGE, flags=flags)
              for k, va, raw, flags in (("code", CODE_VA, CODE_RAW, 0x36), ("data", DATA_VA, DATA_RAW, 3))]
    if _extended(requests):
        result.append(dict(kind="code", va=CODE2_VA, raw=CODE2_RAW, size=PAGE, flags=0x36))
    return result


def _code_bytes(payload, requests):
    return b"".join(payload[r["raw"]:r["raw"] + PAGE] for r in _regions(requests) if r["kind"] == "code")


def has_music(payload):
    if is_scaleout(payload):
        return struct.unpack_from("<I", payload, 0x11C)[0] == SCALE_COUNT + 1
    count = struct.unpack_from("<I", payload, 0x11C)[0]
    return count in (COUNT + 3, COUNT + 4) and any(
        struct.unpack_from("<I", payload, TABLE + i * 56 + 4)[0] == DATA_VA + PAGE
        for i in range(COUNT + 2, count))


def _library(payload, extended):
    start = LIB_COPY if extended else LIB_START
    _require(_sha(payload[start:start + LIB_END - LIB_START]) == LIB_SHA256, "foreign library metadata")
    for off, va in LIB_POINTERS:
        _require(struct.unpack_from("<I", payload, off)[0] == va + (LIB_COPY - LIB_START if extended else 0),
                 "foreign library metadata pointer")


def _extra_header_tail():
    tail = bytearray(LIB_END - (META_START + 168))
    off = CODE2_NAME - (META_START + 168)
    tail[off:off + 8] = b".ASTRc2\0"
    return bytes(tail)


def _directory_end(requests):
    return LIB_COPY if _extended(requests) else PAGE


def _directory(requests, code):
    document = {"requests": _requests(requests), "code_sha256": _sha(code)}
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
    extended = _extended(requests)
    if extended:
        raw = zlib.compress(raw, level=9)
    result = (EXT_MAGIC if extended else MAGIC) + struct.pack("<I", len(raw)) + raw
    capacity = _directory_end(requests) - DIRECTORY
    _require(len(result) <= capacity, "allocation directory capacity exceeded")
    return result.ljust(capacity, b"\0")


def _read_directory(payload):
    extended = len(payload) == EXT_FILE_SIZE
    magic = EXT_MAGIC if extended else MAGIC
    end = LIB_COPY if extended else PAGE
    _require(payload[DIRECTORY:DIRECTORY + 8] == magic, "missing allocation directory")
    size = struct.unpack_from("<I", payload, DIRECTORY + 8)[0]
    _require(0 < size <= end - DIRECTORY - 12, "invalid allocation directory size")
    raw = payload[DIRECTORY + 12:DIRECTORY + 12 + size]
    if extended:
        decoder = zlib.decompressobj()
        try:
            raw = decoder.decompress(raw, 4096)
        except zlib.error as exc:
            raise ValueError("foreign compressed allocation directory") from exc
        _require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                 "foreign compressed allocation directory")
    doc = json.loads(raw)
    requests = _requests(doc["requests"])
    _require(payload[DIRECTORY:end] == _directory(requests, _code_bytes(payload, requests)),
             "foreign allocation directory or code bytes")
    return requests


def _geometry(payload, grown):
    chunks = []
    for i in range(COUNT):
        h = TABLE + i * 56
        chunk = bytearray(payload[h:h + 36])
        if grown:
            for field in (20, 28, 32):
                ptr = struct.unpack_from("<I", chunk, field)[0]
                _require(0x10000 + META_COPY <= ptr < 0x10000 + NAMES, "foreign relocated header pointer")
                struct.pack_into("<I", chunk, field, ptr - META_DELTA)
        if i == COUNT - 1:
            # SPECIAL owns just these three descriptor fields and its digest.
            for off, value in ((0, special.RETAIL_FLAGS), (8, special.RETAIL_SIZE), (16, special.RETAIL_SIZE)):
                struct.pack_into("<I", chunk, off, value)
        chunks.append(chunk)
    _require(_sha(b"".join(chunks)) == GEOMETRY_SHA256, "foreign retail section geometry")


def _special_state(payload, grown):
    h = TABLE + (COUNT - 1) * 56
    fields = struct.unpack_from("<5I", payload, h)
    retail = (special.RETAIL_FLAGS, special.SECTION_VA, special.RETAIL_SIZE, special.RETAIL_RAW, special.RETAIL_SIZE)
    applied = (special.FLAGS, special.SECTION_VA, special.SIZE, special.RETAIL_RAW, special.SIZE)
    _require(fields in (retail, applied), "foreign SPECIAL section")
    _require(_sha(payload[special.RETAIL_RAW:special.RETAIL_RAW + special.RETAIL_SIZE]) == special.RETAIL_CONTENT_SHA256,
             "foreign pinned .XTLID content")
    state = "retail" if fields == retail else "applied"
    table_end = special.TABLE_RAW + special.TABLE_SIZE
    if grown or state == "applied":
        _require(not any(payload[special.RETAIL_RAW + special.RETAIL_SIZE:special.TABLE_RAW]), "foreign SPECIAL gap")
        _require(not any(payload[table_end:CODE_RAW]), "foreign SPECIAL padding")
        if state == "retail":
            _require(not any(payload[special.TABLE_RAW:table_end]), "partial SPECIAL table")
    else:
        _require(not any(payload[special.RETAIL_RAW + special.RETAIL_SIZE:]), "foreign retail padding")
    return state


def _descriptor(kind, digest):
    if kind == "code2":
        return struct.pack("<9I20s", 0x36, CODE2_VA, PAGE, CODE2_RAW, PAGE,
                           0x10000 + CODE2_NAME, 0, 0x10000 + CODE2_REFS,
                           0x10000 + CODE2_REFS, digest)
    code = kind == "code"
    return struct.pack("<9I20s", 0x36 if code else 0x03,
                       CODE_VA if code else DATA_VA, PAGE,
                       CODE_RAW if code else DATA_RAW, PAGE,
                       0x10000 + NAMES + (0 if code else 8), 0,
                       0x10000 + REFS + (0 if code else 4),
                       0x10000 + REFS + (0 if code else 4), digest)


def _digest(data):
    # Same length-prefixed SHA1 scheme as nfl2k5_bump_strength.section_digest.
    return hashlib.sha1(struct.pack("<I", len(data)) + data).digest()  # nosec B324


def _validate(payload):
    if is_scaleout(payload):
        return _validate_scaleout(payload)
    _require(payload[:4] == b"XBEH", "missing XBE header")
    if has_music(payload):
        from . import nfl2k5_music_storage as music_storage
        original, _ = music_storage.unwrap(payload)
        return _validate(original)
    base, headers, image_size = struct.unpack_from("<3I", payload, 0x104)
    count, table = struct.unpack_from("<II", payload, 0x11C)
    grown = count in (COUNT + 2, COUNT + 3)
    extended = count == COUNT + 3
    _require(base == 0x10000 and table == base + TABLE and count in (COUNT, COUNT + 2, COUNT + 3), "foreign XBE section table")
    _require(headers == PAGE if grown else headers in (META_COPY, logo.NEW_SIZE_OF_HEADERS), "foreign header size")
    _geometry(payload, grown)
    if extended:
        _library(payload, True)
    state = _special_state(payload, grown)
    expected_size = EXT_FILE_SIZE if extended else FILE_SIZE if grown else special.FILE_SIZE if state == "applied" else special.RETAIL_FILE_SIZE
    expected_image = EXT_IMAGE_SIZE if extended else IMAGE_SIZE if grown else special.TABLE_VA + special.TABLE_SIZE - base if state == "applied" else special.RETAIL_IMAGE_SIZE
    _require(len(payload) == expected_size and image_size == expected_image, "foreign grown XBE extent")
    if grown:
        _require(_sha(payload[META_COPY:NAMES]) == METADATA_SHA256, "foreign relocated names/counters")
        _require(payload[NAMES:REFS] == b".ASTRAc\0.ASTRAd\0" and not any(payload[REFS:DIRECTORY]), "foreign new names/counters")
        # The unoverwritten suffix of the original metadata remains pinned too.
        if extended:
            _require(payload[META_START + 168:LIB_END] == _extra_header_tail(), "foreign extended header metadata")
            _require(not any(payload[FILE_SIZE:CODE2_RAW]), "foreign reserved music gap")
        else:
            _require(payload[META_START + 112:META_END] == payload[META_COPY + 112:NAMES], "foreign retired header metadata")
        requests = _read_directory(payload)
        _require(extended == _extended(requests), "foreign allocation page count")
        allocations = _allocations(requests)
        logo_site = next(a for a in allocations if a["owner"] == LOGO_REQUEST[0])
        _require(struct.unpack_from("<II", payload, 0x170) == (logo_site["va"], logo.LOGO_SIZE), "foreign grown logo pointer")
        _require(payload[logo_site["raw"]:logo_site["raw"] + logo.LOGO_SIZE] == logo.RETAIL_LOGO, "foreign grown logo bitmap")
        for i, region in enumerate(_regions(requests)):
            raw = region["raw"]
            content = payload[raw:raw + PAGE]
            if region["kind"] == "data":
                _require(not any(content), "data page must be zero initialised")
            else:
                mask = bytearray(PAGE)
                for a in allocations:
                    if a["kind"] == "code" and raw <= a["raw"] < raw + PAGE:
                        start = a["raw"] - raw
                        mask[start:start + a["size"]] = b"\1" * a["size"]
                _require(all(owned or value == 0xCC for owned, value in zip(mask, content)), "foreign unallocated code padding")
            kind = "code2" if i == 2 else region["kind"]
            h = META_START + i * 56
            _require(payload[h:h + 56] == _descriptor(kind, _digest(content)), "foreign grown section header/digest")
    else:
        _require(_sha(payload[META_START:META_END]) == METADATA_SHA256, "foreign header names/counters")
        _require(logo.status(payload) in ("retail", "applied"), "foreign existing boot logo")
        padding = bytearray(payload[META_COPY:PAGE])
        if logo.status(payload) == "applied":
            start = logo.NEW_LOGO_VA - 0x10000 - META_COPY
            padding[start:start + logo.LOGO_SIZE] = bytes(logo.LOGO_SIZE)
        _require(not any(padding), "foreign header slack")
        requests = []
    image = XbeImage(payload)
    # Verify every section digest, including pre-existing owners, before writing.
    for s in image.sections:
        _require(payload[s.header + 36:s.header + 56] == _digest(payload[s.raw:s.raw + s.raw_size]), "stale section digest")
    return grown, state, requests


def status(payload: bytes) -> str:
    try:
        return "applied" if _validate(payload)[0] else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, zlib.error):
        return "foreign"


def special_state(payload: bytes) -> str:
    """Validated projection used by SPECIAL, without recursion through its state()."""
    return _validate(payload)[1]


def layout(payload: bytes) -> dict:
    if is_scaleout(payload):
        return _scaleout_layout(payload)
    grown, special_status, requests = _validate(payload)
    result = {"status": "applied" if grown else "retail", "special": special_status,
            "file_size": EXT_FILE_SIZE if _extended(requests) else FILE_SIZE,
            "image_size": EXT_IMAGE_SIZE if _extended(requests) else IMAGE_SIZE, "headers_size": PAGE,
            "regions": _regions(requests),
            "allocations": _allocations(requests) if grown else []}
    if has_music(payload):
        from . import nfl2k5_music_storage as music_storage
        result['file_size'] = len(payload)
        result['image_size'] = max(result['image_size'], music_storage.VA + music_storage.CAPACITY - 0x10000)
        result['regions'].append(dict(kind='read_only', va=music_storage.VA, raw=music_storage.RAW,
                                      size=music_storage.CAPACITY, flags=0x3A, music=True))
        result['allocations'].append(dict(owner=music_storage.OWNER, kind='read_only',
            va=music_storage.VA, raw=music_storage.RAW, size=music_storage.CAPACITY, align=PAGE))
    result["pages"] = _page_map(result["regions"], result["allocations"])
    result["capacity"] = _capacity(result["regions"], result["allocations"], scaleout=False)
    return result


def reservations(payload: bytes | None = None) -> list[dict]:
    """Owned parent pages and named children; parent overlap is intentional."""
    regions = layout(payload)["regions"] if payload is not None else _regions(())
    regions = [dict(r, va=r["va"] + offset, raw=r["raw"] + offset, size=min(PAGE, r["size"] - offset))
               for r in regions for offset in range(0, r["size"], PAGE)]
    result = [dict(start=hex(r["va"]), end=hex(r["va"] + r["size"]), size=r["size"], owner=OWNER,
                   basis="owned grown " + r["kind"] + " page; all unused bytes reserved")
              for r in regions if not r.get("music")]
    if payload is not None:
        for a in layout(payload)["allocations"]:
            result.append(dict(start=hex(a["va"]), end=hex(a["va"] + a["size"]), size=a["size"],
                               owner=a["owner"], basis="named " + a["kind"] + " allocation",
                               **({"parent_owner": OWNER} if a["owner"] != "nfl2k5_music_metadata" else {})))
    return result


def apply(payload: bytes, requests=(), *, scaleout=False) -> tuple[bytes, dict]:
    _require(type(scaleout) is bool, "scaleout must be a boolean")
    grown, _, previous = _validate(payload)
    wanted = _requests(requests)
    if is_scaleout(payload):
        _require(wanted == previous or wanted == [LOGO_REQUEST], "allocation requests differ; rebuild from base")
        return payload, {"status": "already_applied", "changed_bytes": 0, "allocations": _scale_allocations(previous)}
    if not grown and (scaleout or _needs_scaleout(wanted)):
        return _apply_scaleout(payload, wanted)
    _allocations(wanted)
    if grown:
        _require(not scaleout, "scale-out needs a rebuild from base")
        _require(wanted == previous or wanted == [LOGO_REQUEST], "allocation requests differ; rebuild from base")
        return payload, {"status": "already_applied", "changed_bytes": 0, "allocations": _allocations(previous)}
    extended = _extended(wanted)
    if extended:
        _library(payload, False)
    logo_site = next(a for a in _allocations(wanted) if a["owner"] == LOGO_REQUEST[0])
    buf = bytearray(payload)
    buf.extend(bytes((EXT_FILE_SIZE if extended else FILE_SIZE) - len(buf)))
    buf[META_COPY:NAMES] = payload[META_START:META_END]
    for i in range(COUNT):
        for field in (20, 28, 32):
            off = TABLE + i * 56 + field
            struct.pack_into("<I", buf, off, struct.unpack_from("<I", buf, off)[0] + META_DELTA)
    buf[NAMES:REFS] = b".ASTRAc\0.ASTRAd\0"
    buf[REFS:DIRECTORY] = bytes(DIRECTORY - REFS)
    buf[CODE_RAW:DATA_RAW] = b"\xcc" * PAGE
    if extended:
        buf[LIB_COPY:LIB_COPY + LIB_END - LIB_START] = payload[LIB_START:LIB_END]
        for off, va in LIB_POINTERS:
            struct.pack_into("<I", buf, off, va + LIB_COPY - LIB_START)
        buf[META_START + 168:LIB_END] = _extra_header_tail()
        buf[CODE2_RAW:CODE2_RAW + PAGE] = b"\xcc" * PAGE
    buf[logo_site["raw"]:logo_site["raw"] + logo.LOGO_SIZE] = logo.RETAIL_LOGO
    buf[DIRECTORY:_directory_end(wanted)] = _directory(wanted, _code_bytes(buf, wanted))
    for i, region in enumerate(_regions(wanted)):
        raw = region["raw"]
        kind = "code2" if i == 2 else region["kind"]
        buf[META_START + i * 56:META_START + (i + 1) * 56] = _descriptor(kind, _digest(buf[raw:raw + PAGE]))
    struct.pack_into("<II", buf, 0x108, PAGE, EXT_IMAGE_SIZE if extended else IMAGE_SIZE)
    struct.pack_into("<I", buf, 0x11C, COUNT + 3 if extended else COUNT + 2)
    struct.pack_into("<II", buf, 0x170, logo_site["va"], logo.LOGO_SIZE)
    result = bytes(buf)
    _require(status(result) == "applied", "grown XBE postcondition failed")
    return result, {"status": "applied", "experimental": True, "runtime_witnessed": False,
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                    "file_growth": len(result) - len(payload), "allocations": _allocations(wanted),
                    "reservations": reservations(result)}


def install_code(payload: bytes, owner: str, code: bytes) -> tuple[bytes, dict]:
    """Fill only an established code allocation, then seal its bytes and digest.

    A filled allocation can only be replayed with identical bytes. Reconfiguration
    requires a clean rebuild, so mixed owner payloads cannot be silently repaired.
    """
    if is_scaleout(payload):
        return _install_scaleout(payload, owner, code, "code")
    grown, _, requests = _validate(payload)
    _require(grown, "code requires an established allocation")
    matches = [a for a in _allocations(requests) if a["owner"] == owner and a["kind"] == "code"]
    _require(len(matches) == 1, "owner has no code allocation")
    a = matches[0]
    _require(len(code) == a["size"], "code must fill its exact named allocation")
    old = payload[a["raw"]:a["raw"] + a["size"]]
    _require(old in (b"\xcc" * a["size"], code), "foreign or differently configured owner code")
    buf = bytearray(payload)
    buf[a["raw"]:a["raw"] + a["size"]] = code
    buf[DIRECTORY:_directory_end(requests)] = _directory(requests, _code_bytes(buf, requests))
    # Reuse the production section digest helper for executable writes.
    from .nfl2k5_bump_strength import _sections, section_digest
    s = next(s for s in _sections(buf) if s.virtual_address <= a["va"] < s.virtual_address + s.raw_size)
    buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    result = bytes(buf)
    _require(status(result) == "applied", "code install postcondition failed")
    return result, {"status": "applied", "edits": [{"label": owner, "va": hex(a["va"]), "size": a["size"]}]}


def allocation_evidence(retail: bytes, manifest, *, allocated: bytes | None = None) -> dict:
    """Pinned mapping/ownership proof and byte-granular reference inventory.

    Legacy pages require zero encodings. Large v3 mappings use the same fresh
    section policy as music: all pointer-shaped candidates remain in the receipt,
    without treating them as rooted references or declaring a retail cave free.
    Register-synthesised addresses, kernel acceptance and gameplay are unproved.
    """
    from .nfl2k5_cave_oracle import RETAIL_SHA256
    image = XbeImage(retail)
    _require(image.sha256 == RETAIL_SHA256 == manifest.document.get("retail_sha256"), "allocation proof needs pinned retail and matching manifest")
    _validate(retail)
    _require(image.base + image.image_size <= CODE_VA and all(s.end <= CODE_VA for s in image.sections), "new pages overlap retail")
    _require(special.TABLE_VA + special.TABLE_SIZE <= CODE_VA, "new pages overlap SPECIAL")
    # Match the manifest builder's complete dormant-owner request set. This is
    # an ownership proof only; apply() still allocates exactly its caller's set.
    dormant = dormant_union()
    if allocated is not None:
        children = layout(allocated)["allocations"]
        proof_regions = [r for r in layout(allocated)["regions"] if not r.get("music")]
    elif _needs_scaleout(dormant):
        # Beta-62 owners put the dormant union on the v3 page pools.
        children = _scale_allocations(dormant)
        proof_regions = [r for r in _scale_regions() if r["kind"] != "read_only"]
    else:
        children = _allocations(dormant)
        proof_regions = _regions([(a["owner"], a["kind"], a["size"], a["align"]) for a in children if a["kind"] != "read_only"])
    for region in proof_regions:
        r = dict(start=hex(region["va"]), end=hex(region["va"] + region["size"]))
        overlaps = manifest.overlaps(int(r["start"], 0), int(r["end"], 0), exclude_owner=OWNER)
        for overlap in overlaps:
            start, end = overlap.start, overlap.end
            _require(any(a["owner"] == overlap.detail.split(":", 1)[0] and a["va"] <= start < end <= a["va"] + a["size"]
                         for a in children), "new pages overlap another manifest owner")
    page_numbers = {va // PAGE for r in proof_regions for va in range(r["va"], r["va"] + r["size"], PAGE)}
    def in_pages(va):
        return va // PAGE in page_numbers
    hits = []
    legacy_hits = []
    spans = [(image.base, retail[:image.headers_size], False)]
    spans += [(s.start, retail[s.raw:s.raw + s.raw_size], s.executable) for s in image.sections]
    for base, data, executable in spans:
        for off in range(len(data)):
            if off + 4 <= len(data) and in_pages(struct.unpack_from("<I", data, off)[0]):
                target = struct.unpack_from("<I", data, off)[0]
                hits.append((base + off, "absolute", target))
                if target < EXT_IMAGE_SIZE + image.base:
                    legacy_hits.append(hits[-1])
            if not executable:
                continue
            op, prefix, width = data[off], 0, 0
            if op in (0xE8, 0xE9):
                prefix, width = 1, 4
            elif op == 15 and off + 1 < len(data) and 0x80 <= data[off + 1] <= 0x8F:
                prefix, width = 2, 4
            elif op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3:
                prefix, width = 1, 1
            if width and off + prefix + width <= len(data):
                delta = int.from_bytes(data[off + prefix:off + prefix + width], "little", signed=True)
                target = (base + off + prefix + width + delta) & 0xFFFFFFFF
                if in_pages(target):
                    hits.append((base + off, "relative", target))
                    if target < EXT_IMAGE_SIZE + image.base:
                        legacy_hits.append(hits[-1])
            # Operand-size-overridden near transfers truncate EIP to 16 bits;
            # they cannot encode either page above 16 MiB.
    scaled = is_scaleout(allocated) if allocated is not None else _needs_scaleout(dormant)
    _require(not (legacy_hits if scaled else hits), f"retail reference encodings into legacy owned pages: {hits[:8]}")
    return {"allocation": "new_preloaded_sections", "start": hex(CODE_VA), "end": hex(max(r["va"] + r["size"] for r in proof_regions)),
            "regions": proof_regions,
            "encoded_references": hits, "legacy_encoded_references": legacy_hits,
            "pages": _page_map(proof_regions, children), "allocations": children,
            "retail_mapping_overlaps": [], "manifest_overlaps": [], "retail_sha256": image.sha256,
            "reference_policy": ("v3 adds loader mappings, never overwrites a retail cave; all raw encoding candidates retained; legacy pages retain zero-encoding gate"
                                 if scaled else "all allocated pages have zero byte-granular retail reference encodings"),
            "cave_verdict": "unmapped; owned loader allocation, not a free retail cave",
            "proof_boundary": "structural mapping and complete raw encoding inventory; candidates are not proved runtime references or freedom; loader/gameplay unwitnessed"}


# Scale-out v3 retains every existing owner VA and raw offset. Three larger
# sections provide page-granular RX, RW and general RO service. The fixed music
# slot remains independent. No descriptor touches the live header caves at A10.
LEGACY_OWNERS = frozenset((LOGO_REQUEST[0], "nfl2k5_dynamic_kickoff_relocated",
    "nfl2k5_scorebug_runtime", "nfl2k5_defensive_try", "nfl2k5_momentum", "nfl2k5_zone_drop"))
SCALE_RUNS = (
    ("code", 0x14DA000, 24),
    ("data", 0x14F2000, 20),
    ("read_only", 0x1506000, 5),
)
SCALE_COUNT = COUNT + 3 + len(SCALE_RUNS)
SCALE_HEADER_END = 0xA10
SCALE_NAMES = DIRECTORY + 64
SCALE_NAMES_END = SCALE_NAMES + (SCALE_COUNT + 1 - COUNT) * 12
SCALE_FILE_SIZE = EXT_FILE_SIZE + sum(n * PAGE for _, _, n in SCALE_RUNS)
SCALE_IMAGE_SIZE = max(va + n * PAGE for _, va, n in SCALE_RUNS) - 0x10000
SCALE_DIRECTORY = SCALE_FILE_SIZE - 5 * PAGE
SCALE_DIRECTORY_VA = SCALE_RUNS[-1][1]
DEBUG_START, DEBUG_END = LIB_END, 0xA10
DEBUG_COPY = SCALE_NAMES_END
DEBUG_SHA256 = 'f0b03ce7d5f3562f7d91f4de5f6a8a5fe1f8d6d13de53bd5d98a53de92e2f424'
DEBUG_POINTERS = ((332, 68040), (336, 68093), (340, 68004))
DIRECTORY_OWNER = "nfl2k5_xbe_space_directory"
MAX_REQUESTS = 96
MAX_REQUEST_BYTES = 96 * PAGE
# XSPACE2 is retained as the header envelope for the shipped boot-logo reader.
# SP03 and the sealed external directory distinguish the v3 interpretation.
SCALE_TAG = EXT_MAGIC + b"SP03"


def dormant_union():
    """Every allocator owner the manifest builder installs on its disposable disc (beta 61 + beta 62)."""
    from . import nfl2k5_dynamic_kickoff_relocated as relocated
    from . import nfl2k5_momentum as momentum, nfl2k5_defensive_try as defensive_try
    from . import nfl2k5_scorebug_runtime as runtime, nfl2k5_zone_drop as zone_drop
    from . import nfl2k5_roster_storage as roster_storage
    from . import nfl2k5_coverage_slider as coverage, nfl2k5_scramble_tuning as scramble
    from . import nfl2k5_music_playlist as playlist, nfl2k5_practice_squad_screen as practice_screen
    from . import nfl2k5_abilities_runtime as abilities, nfl2k5_qb_spy_runtime as qb_spy
    from . import nfl2k5_calendar_engine as calendar
    from . import nfl2k5_guardian_overlay as guardian
    from . import nfl2k5_read_option_runtime as read_option, nfl2k5_franchise_2026 as franchise_2026
    from . import nfl2k5_senior_bowl as senior_bowl, nfl2k5_roster_arena_growth as arena_growth
    from . import nfl2k5_animation_xbe as animation_xbe, nfl2k5_my_career as my_career
    from . import nfl2k5_screen_hooks as screen_hooks
    # keep this in step with tests/nfl2k5_allocator_stack.REQUESTS and the manifest builder's all_requests
    return (relocated.REQUESTS + momentum.REQUESTS + defensive_try.REQUESTS + runtime.REQUESTS + zone_drop.REQUESTS
            + roster_storage.REQUESTS + coverage.REQUESTS + scramble.REQUESTS + playlist.REQUESTS
            + practice_screen.REQUESTS + abilities.REQUESTS + qb_spy.REQUESTS + calendar.REQUESTS + guardian.REQUESTS
            + read_option.REQUESTS + franchise_2026.REQUESTS + senior_bowl.REQUESTS + animation_xbe.REQUESTS
            + my_career.REQUESTS + screen_hooks.REQUESTS + arena_growth.REQUESTS)


def is_scaleout(payload):
    return len(payload) >= DIRECTORY + 12 and payload[DIRECTORY:DIRECTORY + 12] == SCALE_TAG


def accepted_file_sizes():
    """Bounded pre-read policy; recognition still validates every byte/descriptor."""
    return (FILE_SIZE, FILE_SIZE + 0x10000, EXT_FILE_SIZE, SCALE_FILE_SIZE)


def _requests(requests):
    out = []
    for request in requests:
        _require(len(out) < MAX_REQUESTS, "allocation request count exceeds 96")
        _require(isinstance(request, (tuple, list)) and len(request) == 4,
                 "request must be (owner, kind, size, align)")
        owner, kind, size, align = request
        _require(isinstance(owner, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", owner), "invalid allocation owner")
        _require(owner not in (OWNER, DIRECTORY_OWNER, "nfl2k5_music_metadata"), "reserved allocation owner")
        _require(kind in ("code", "data", "read_only"), "kind must be code, data or read_only")
        _require(type(size) is int and 0 < size <= MAX_REQUEST_BYTES, "size exceeds allocation capacity")
        _require(type(align) is int and 0 < align <= PAGE and align & (align - 1) == 0,
                 "align must be a power of two <=4096")
        out.append((owner, kind, size, align))
    out.sort()
    _require(len({(o, k) for o, k, _, _ in out}) == len(out), "duplicate owner/kind allocation")
    declared = [r for r in out if r[0] == LOGO_REQUEST[0]]
    _require(not declared or declared == [LOGO_REQUEST], "boot logo has a fixed immutable allocation")
    if not declared:
        out.append(LOGO_REQUEST)
        out.sort()
    return out


def _needs_scaleout(requests):
    normalized = _requests(requests)
    # Unknown beta-62 owners never sort ahead of a shipped owner in its pages.
    if any(r[0] not in LEGACY_OWNERS for r in normalized) and any(
            r[0] in LEGACY_OWNERS - {LOGO_REQUEST[0]} for r in normalized):
        return True
    try:
        _legacy_allocations(normalized)
    except ValueError:
        return True
    return False


def _allocations(requests):
    # Legacy directories describe their original packing even when the same
    # request set would now select v3 on a fresh build. Decode by format.
    return _legacy_allocations(requests)


def _scale_regions():
    result = [dict(kind=k, va=va, raw=raw, size=PAGE, flags=flags)
              for k, va, raw, flags in (("code", CODE_VA, CODE_RAW, 0x36),
                  ("data", DATA_VA, DATA_RAW, 3), ("code", CODE2_VA, CODE2_RAW, 0x36))]
    raw = EXT_FILE_SIZE
    for kind, va, pages in SCALE_RUNS:
        result.append(dict(kind=kind, va=va, raw=raw, size=pages * PAGE,
                           flags={"code": 0x36, "data": 3, "read_only": 0x32}[kind]))
        raw += pages * PAGE
    return result


def _scale_allocations(requests):
    # This late arena owner must not displace shipped beta-62 allocations or
    # their protected manifest extents. Existing request sets pack identically.
    requests = sorted(_requests(requests), key=lambda r: (r[0] == 'nfl2k5_roster_arena_growth', r))
    out = _legacy_allocations([r for r in requests if r[0] in LEGACY_OWNERS])
    regions = _scale_regions()[3:]
    cursors = {r["va"]: PAGE if r["kind"] == "read_only" else 0 for r in regions}
    for owner, kind, size, align in requests:
        if owner in LEGACY_OWNERS:
            continue
        remaining, owner_offset = size, 0
        for r in regions:
            if r["kind"] != kind:
                continue
            at = (cursors[r["va"]] + align - 1) & -align
            if at >= r["size"]:
                continue
            take = min(remaining, r["size"] - at)
            out.append(dict(owner=owner, kind=kind, size=take, align=align,
                            va=r["va"] + at, raw=r["raw"] + at, owner_offset=owner_offset))
            cursors[r["va"]] = at + take
            remaining -= take
            owner_offset += take
            if not remaining:
                break
        _require(not remaining, f"{kind} page capacity exceeded for {owner}; no unreserved page may be used")
    out.append(dict(owner=DIRECTORY_OWNER, kind="read_only", size=PAGE, align=PAGE,
                    va=SCALE_DIRECTORY_VA, raw=SCALE_DIRECTORY))
    return out


def _scale_descriptor(index, region, digest):
    name = SCALE_NAMES + index * 12
    refs = name + 8
    return struct.pack("<9I20s", region["flags"], region["va"], region["size"], region["raw"], region["size"],
                       0x10000 + name, 0, 0x10000 + refs,
                       0x10000 + refs + (2 if region["size"] > PAGE else 0), digest)


def _scale_header_tail():
    return bytearray(SCALE_HEADER_END - META_START)


def _scale_names(*, music=False):
    names = bytearray()
    for index in range(SCALE_COUNT + 1 - COUNT):
        names.extend(f".AS{index:04d}\0".encode("ascii") + bytes(4))
    if music:
        names[-12:] = b".ASTRAr\0" + bytes(4)
    return bytes(names)


def _debug(payload, *, relocated):
    start = DEBUG_COPY if relocated else DEBUG_START
    _require(_sha(payload[start:start + DEBUG_END - DEBUG_START]) == DEBUG_SHA256, "foreign debug metadata")
    for at, va in DEBUG_POINTERS:
        _require(struct.unpack_from("<I", payload, at)[0] == va + (DEBUG_COPY - DEBUG_START if relocated else 0),
                 "foreign debug metadata pointer")


def _scale_header_directory(block, payload):
    header = SCALE_TAG + struct.pack("<II", SCALE_DIRECTORY_VA, SCALE_DIRECTORY) + hashlib.sha256(block).digest()
    result = bytearray(header.ljust(LIB_COPY - DIRECTORY, b"\0"))
    result[SCALE_NAMES - DIRECTORY:SCALE_NAMES_END - DIRECTORY] = _scale_names(music=has_music(payload))
    result[DEBUG_COPY - DIRECTORY:DEBUG_COPY - DIRECTORY + DEBUG_END - DEBUG_START] = payload[DEBUG_COPY:DEBUG_COPY + DEBUG_END - DEBUG_START]
    return result


def _scale_seals(payload):
    code = b"".join(payload[r["raw"]:r["raw"] + r["size"]] for r in _scale_regions() if r["kind"] == "code")
    ro = payload[SCALE_DIRECTORY + PAGE:SCALE_FILE_SIZE]
    return {"code_sha256": _sha(code), "read_only_sha256": _sha(ro)}


def _scale_directory(requests, seals):
    raw = json.dumps(dict(version=3, requests=_requests(requests)),
                     sort_keys=True, separators=(",", ":")).encode("ascii")
    _require(len(raw) <= 32768, "allocation directory document capacity exceeded")
    compressed = zlib.compress(raw, level=9)
    # Fixed-width content seals keep planner capacity independent of the
    # eventual machine-code hash's compressibility.
    block = (b"XSDIR3\0\0" + struct.pack("<I", len(compressed))
             + bytes.fromhex(seals["code_sha256"]) + bytes.fromhex(seals["read_only_sha256"]) + compressed)
    _require(len(block) <= PAGE, "allocation directory capacity exceeded")
    return block.ljust(PAGE, b"\0")


def _seal_scaleout(buf, requests):
    block = _scale_directory(requests, _scale_seals(buf))
    buf[SCALE_DIRECTORY:SCALE_DIRECTORY + PAGE] = block
    buf[DIRECTORY:LIB_COPY] = _scale_header_directory(block, buf)
    for index, region in enumerate(_scale_regions()):
        raw = region["raw"]
        at = META_START + index * 56
        buf[at:at + 56] = _scale_descriptor(index, region, _digest(buf[raw:raw + region["size"]]))


def _read_scale_directory(payload):
    block = payload[SCALE_DIRECTORY:SCALE_DIRECTORY + PAGE]
    _require(block[:8] == b"XSDIR3\0\0", "foreign scale-out allocation directory")
    size = struct.unpack_from("<I", block, 8)[0]
    _require(0 < size <= PAGE - 76, "foreign allocation directory size")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(block[76:76 + size], 32769)
    _require(len(raw) <= 32768 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
             "foreign compressed allocation directory")
    doc = json.loads(raw)
    _require(isinstance(doc, dict), "foreign allocation document")
    requests = _requests(doc["requests"])
    _require(block == _scale_directory(requests, _scale_seals(payload)), "foreign owner bytes/directory seal")
    _require(payload[DIRECTORY:LIB_COPY] == _scale_header_directory(block, payload), "foreign directory header seal/names/counters")
    return requests


def scale_music_slots():
    index = SCALE_COUNT - COUNT
    return META_START + index * 56, SCALE_NAMES + index * 12, SCALE_NAMES + index * 12 + 8


def validate_scale_structure(payload):
    _require(payload[:4] == b"XBEH" and len(payload) == SCALE_FILE_SIZE, "foreign scale-out XBE extent")
    _require(struct.unpack_from("<3I", payload, 0x104) == (0x10000, PAGE, SCALE_IMAGE_SIZE), "foreign scale-out image geometry")
    count, table = struct.unpack_from("<II", payload, 0x11C)
    _require(count in (SCALE_COUNT, SCALE_COUNT + 1) and table == 0x10000 + TABLE, "foreign scale-out section table")
    _geometry(payload, True)
    state = _special_state(payload, True)
    _library(payload, True)
    _debug(payload, relocated=True)
    _require(struct.unpack_from("<II", payload, 0x178) == (0x10000 + LIB_COPY + 0x90, 1), "foreign feature library pointer/count")
    _require(_sha(payload[META_COPY:NAMES]) == METADATA_SHA256, "foreign relocated names/counters")
    _require(payload[NAMES:DIRECTORY] == b".ASTRAc\0.ASTRAd\0" + bytes(8), "foreign retired allocator names/counters")
    _require(payload[SCALE_NAMES:SCALE_NAMES_END] == _scale_names(music=has_music(payload)), "foreign section names/counters")
    for index, region in enumerate(_scale_regions()):
        at = META_START + index * 56
        _require(payload[at:at + 56] == _scale_descriptor(index, region, payload[at + 36:at + 56]),
                 "foreign scale-out section geometry")
    return state


def _validate_scaleout(payload):
    state = validate_scale_structure(payload)
    count = struct.unpack_from("<I", payload, 0x11C)[0]
    requests = _read_scale_directory(payload)
    allocations = _scale_allocations(requests)
    expected = _scale_header_tail()
    for index, region in enumerate(_scale_regions()):
        raw, size = region["raw"], region["size"]
        content = payload[raw:raw + size]
        if region["kind"] == "data":
            _require(not any(content), "data pages must be zero initialised")
        else:
            mask = bytearray(size)
            for a in allocations:
                if raw <= a["raw"] < raw + size:
                    at = a["raw"] - raw
                    mask[at:at + a["size"]] = b"\1" * a["size"]
            pad = 0xCC if region["kind"] == "code" else 0
            _require(all(owned or value == pad for owned, value in zip(mask, content)), "foreign unallocated page padding")
        expected[index * 56:(index + 1) * 56] = _scale_descriptor(index, region, _digest(content))
    from . import nfl2k5_music_storage as music
    if count == SCALE_COUNT + 1:
        block = payload[music.RAW:music.RAW + music.CAPACITY]
        music._block_data(block)
        header, name, refs = scale_music_slots()
        expected[header - META_START:header - META_START + 56] = music._descriptor(block, scaleout=True)
    else:
        _require(not any(payload[FILE_SIZE:CODE2_RAW]), "foreign reserved music gap")
    _require(payload[META_START:SCALE_HEADER_END] == expected, "foreign scale-out descriptors/names/counters/padding")
    logo_site = next(a for a in allocations if a["owner"] == LOGO_REQUEST[0])
    _require(struct.unpack_from("<II", payload, 0x170) == (logo_site["va"], logo.LOGO_SIZE), "foreign grown logo pointer")
    _require(payload[logo_site["raw"]:logo_site["raw"] + logo.LOGO_SIZE] == logo.RETAIL_LOGO, "foreign grown logo bitmap")
    for section in XbeImage(payload).sections:
        _require(payload[section.header + 36:section.header + 56] == _digest(payload[section.raw:section.raw + section.raw_size]), "stale section digest")
    return True, state, requests


def _apply_scaleout(payload, requests):
    # Called only after complete retail/base validation and before any mutation.
    _library(payload, False)
    _debug(payload, relocated=False)
    _require(struct.unpack_from("<II", payload, 0x178) == (0x10994, 1), "foreign feature library pointer/count")
    allocations = _scale_allocations(requests)
    _scale_directory(requests, dict(code_sha256="0" * 64, read_only_sha256="0" * 64))
    _require(DEBUG_COPY + DEBUG_END - DEBUG_START <= LIB_COPY and TABLE + (SCALE_COUNT + 1) * 56 <= SCALE_HEADER_END, "section descriptor/name budget exceeded")
    buf = bytearray(payload)
    buf.extend(bytes(SCALE_FILE_SIZE - len(buf)))
    buf[META_COPY:NAMES] = payload[META_START:META_END]
    buf[META_START:SCALE_HEADER_END] = _scale_header_tail()
    for index in range(COUNT):
        for field in (20, 28, 32):
            at = TABLE + index * 56 + field
            struct.pack_into("<I", buf, at, struct.unpack_from("<I", payload, at)[0] + META_DELTA)
    buf[NAMES:DIRECTORY] = b".ASTRAc\0.ASTRAd\0" + bytes(8)
    buf[LIB_COPY:PAGE] = payload[LIB_START:LIB_END]
    struct.pack_into("<I", buf, 0x178, 0x10000 + LIB_COPY + 0x90)
    buf[DEBUG_COPY:DEBUG_COPY + DEBUG_END - DEBUG_START] = payload[DEBUG_START:DEBUG_END]
    for at, va in DEBUG_POINTERS:
        struct.pack_into("<I", buf, at, va + DEBUG_COPY - DEBUG_START)
    for at, va in LIB_POINTERS:
        struct.pack_into("<I", buf, at, va + LIB_COPY - LIB_START)
    for region in _scale_regions():
        if region["kind"] == "code":
            buf[region["raw"]:region["raw"] + region["size"]] = b"\xcc" * region["size"]
    logo_site = next(a for a in allocations if a["owner"] == LOGO_REQUEST[0])
    buf[logo_site["raw"]:logo_site["raw"] + logo.LOGO_SIZE] = logo.RETAIL_LOGO
    struct.pack_into("<3I", buf, 0x104, 0x10000, PAGE, SCALE_IMAGE_SIZE)
    struct.pack_into("<I", buf, 0x11C, SCALE_COUNT)
    struct.pack_into("<II", buf, 0x170, logo_site["va"], logo.LOGO_SIZE)
    _seal_scaleout(buf, requests)
    result = bytes(buf)
    _require(status(result) == "applied", "scale-out postcondition failed")
    return result, dict(status="applied", experimental=True, runtime_witnessed=False,
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
        file_growth=len(result) - len(payload), allocations=allocations, reservations=reservations(result))


def _install_scaleout(payload, owner, content, kind):
    _, _, requests = _validate(payload)
    allocations = [a for a in _scale_allocations(requests) if a["owner"] == owner and a["kind"] == kind]
    _require(allocations and owner not in (LOGO_REQUEST[0], DIRECTORY_OWNER), "owner has no installable allocation")
    _require(len(content) == sum(a["size"] for a in allocations), "content must fill its exact named allocation")
    old = b"".join(payload[a["raw"]:a["raw"] + a["size"]] for a in allocations)
    padding = b"\xcc" if kind == "code" else b"\0"
    _require(old in (padding * len(content), content), "foreign or differently configured owner content")
    buf, at, edits = bytearray(payload), 0, []
    for a in allocations:
        buf[a["raw"]:a["raw"] + a["size"]] = content[at:at + a["size"]]
        at += a["size"]
        edits.append(dict(label=owner, va=hex(a["va"]), size=a["size"]))
    _seal_scaleout(buf, requests)
    # The same production length-prefixed section digest scheme is used above.
    result = bytes(buf)
    _require(status(result) == "applied", "owner install postcondition failed")
    return result, dict(status="already_applied" if old == content else "applied", edits=edits)


def install_read_only(payload: bytes, owner: str, content: bytes) -> tuple[bytes, dict]:
    """Install an exact immutable general RO request, including all its spans."""
    _require(is_scaleout(payload), "read-only requests require scale-out")
    return _install_scaleout(payload, owner, content, "read_only")


def _capacity(regions, allocations, *, scaleout):
    result = {}
    for kind in ("code", "data", "read_only"):
        matching = [r for r in regions if r["kind"] == kind and not r.get("music")]
        capacity = sum(r["size"] for r in matching)
        used = sum(a["size"] for a in allocations if a["kind"] == kind and a["owner"] != "nfl2k5_music_metadata")
        free = capacity - used
        # Existing beta-61 tails remain owned, but are not offered to new owners.
        available = 0
        for r in matching:
            if scaleout and r["raw"] < EXT_FILE_SIZE:
                continue
            high = max([a["raw"] + a["size"] for a in allocations if r["raw"] <= a["raw"] < r["raw"] + r["size"]] or [r["raw"]])
            available += r["raw"] + r["size"] - high
        result[kind] = dict(pages=capacity // PAGE, capacity_bytes=capacity, requested_bytes=used,
                            free_bytes=free, available_bytes=available)
    return result


def _page_map(regions, allocations):
    pages = []
    indices = {"code": 0, "data": 0, "read_only": 0}
    for region in regions:
        for offset in range(0, region["size"], PAGE):
            va, raw = region["va"] + offset, region["raw"] + offset
            indices[region["kind"]] += 1
            children = [dict(owner=a["owner"], start=max(va, a["va"]),
                end=min(va + PAGE, a["va"] + a["size"])) for a in allocations
                if a["va"] < va + PAGE and va < a["va"] + a["size"]]
            used = sum(c["end"] - c["start"] for c in children)
            pages.append(dict(kind=region["kind"], page=indices[region["kind"]], va=va, raw=raw,
                              flags=region["flags"], size=PAGE, free_bytes=PAGE - used, children=children))
    return pages


def _scaleout_layout(payload):
    _, special_status, requests = _validate(payload)
    regions, allocations = _scale_regions(), _scale_allocations(requests)
    if has_music(payload):
        from . import nfl2k5_music_storage as music
        regions.append(dict(kind="read_only", va=music.VA, raw=music.RAW,
                            size=music.CAPACITY, flags=0x3A, music=True))
        allocations.append(dict(owner=music.OWNER, kind="read_only", va=music.VA, raw=music.RAW,
                                size=music.CAPACITY, align=PAGE))
    return dict(status="applied", version=3, special=special_status, file_size=len(payload),
                image_size=SCALE_IMAGE_SIZE, headers_size=PAGE, regions=regions, allocations=allocations,
                pages=_page_map(regions, allocations), capacity=_capacity(regions, allocations, scaleout=True))


def plan(requests=(), *, scaleout=True):
    """Pure capacity preflight. No input XBE, disc reads or writes are needed.

    The default exposes the beta-62 budget. Each allocation row is a contiguous
    span. Repeated owner/kind rows carry owner_offset into its logical content;
    callers MUST assemble for each VA instead of assuming adjacent virtual pages.
    Unused legacy tails and all alignment gaps remain reserved, never recycled.
    """
    normalized = _requests(requests)
    use_scaleout = scaleout or _needs_scaleout(normalized)
    allocations = _scale_allocations(normalized) if use_scaleout else _legacy_allocations(normalized)
    regions = _scale_regions() if use_scaleout else _regions(normalized)
    if use_scaleout:
        _scale_directory(normalized, dict(code_sha256="f" * 64, read_only_sha256="e" * 64))
    else:
        _directory(normalized, b"")
    return dict(version=3 if use_scaleout else 2 if _extended(normalized) else 1,
                requests=normalized, file_size=SCALE_FILE_SIZE if use_scaleout else EXT_FILE_SIZE if _extended(normalized) else FILE_SIZE,
                regions=regions, allocations=allocations, pages=_page_map(regions, allocations),
                capacity=_capacity(regions, allocations, scaleout=use_scaleout),
                experimental=True, runtime_witnessed=False)
