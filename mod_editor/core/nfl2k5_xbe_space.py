"""EXPERIMENTAL/UNWITNESSED, bounded grown XBE allocator (USA beta 61).

Two owned 4 KiB pages, with separate RX/preload and RW/preload sections. The
22 existing section descriptors stay at their addresses. Their shared counters
and names move, byte for byte, from 0x840..904 to proven header padding. This
frees exactly two contiguous descriptors without moving any retail section.
See ASTRA_XBE_SPACE_REPORT.md for evidence and the loader witness boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct

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
METADATA_SHA256 = "155d094c9592c93f1fd7ce1eb635667d8b88e92cfd46d6e77659e7ae7dd4a252"
GEOMETRY_SHA256 = "904d5748e0650b7627e1d9d77d926088f4cd43749b481455b1803fdc53acd243"
LOGO_REQUEST = ("nfl2k5_boot_logo", "code", logo.LOGO_SIZE, 16)


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _requests(requests):
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


def _allocations(requests):
    cursors = {"code": 0, "data": 0}
    out = []
    for owner, kind, size, align in _requests(requests):
        offset = (cursors[kind] + align - 1) & -align
        _require(offset + size <= PAGE, f"{kind} page capacity exceeded; no unreserved page may be used")
        va, raw = (CODE_VA, CODE_RAW) if kind == "code" else (DATA_VA, DATA_RAW)
        out.append(dict(owner=owner, kind=kind, size=size, align=align, va=va + offset, raw=raw + offset))
        cursors[kind] = offset + size
    return out


def _directory(requests, code):
    document = {"requests": _requests(requests), "code_sha256": _sha(code)}
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
    result = MAGIC + struct.pack("<I", len(raw)) + raw
    _require(len(result) <= PAGE - DIRECTORY, "allocation directory capacity exceeded")
    return result.ljust(PAGE - DIRECTORY, b"\0")


def _read_directory(payload):
    _require(payload[DIRECTORY:DIRECTORY + 8] == MAGIC, "missing allocation directory")
    size = struct.unpack_from("<I", payload, DIRECTORY + 8)[0]
    _require(0 < size <= PAGE - DIRECTORY - 12, "invalid allocation directory size")
    doc = json.loads(payload[DIRECTORY + 12:DIRECTORY + 12 + size])
    requests = _requests(doc["requests"])
    _require(payload[DIRECTORY:PAGE] == _directory(requests, payload[CODE_RAW:CODE_RAW + PAGE]),
             "foreign allocation directory or code bytes")
    _allocations(requests)
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
    _require(payload[:4] == b"XBEH", "missing XBE header")
    base, headers, image_size = struct.unpack_from("<3I", payload, 0x104)
    count, table = struct.unpack_from("<II", payload, 0x11C)
    grown = count == COUNT + 2
    _require(base == 0x10000 and table == base + TABLE and count in (COUNT, COUNT + 2), "foreign XBE section table")
    _require(headers == PAGE if grown else headers in (META_COPY, logo.NEW_SIZE_OF_HEADERS), "foreign header size")
    _geometry(payload, grown)
    state = _special_state(payload, grown)
    expected_size = FILE_SIZE if grown else special.FILE_SIZE if state == "applied" else special.RETAIL_FILE_SIZE
    expected_image = IMAGE_SIZE if grown else special.TABLE_VA + special.TABLE_SIZE - base if state == "applied" else special.RETAIL_IMAGE_SIZE
    _require(len(payload) == expected_size and image_size == expected_image, "foreign grown XBE extent")
    if grown:
        _require(_sha(payload[META_COPY:NAMES]) == METADATA_SHA256, "foreign relocated names/counters")
        _require(payload[NAMES:REFS] == b".ASTRAc\0.ASTRAd\0" and not any(payload[REFS:DIRECTORY]), "foreign new names/counters")
        # The unoverwritten suffix of the original metadata remains pinned too.
        _require(payload[META_START + 112:META_END] == payload[META_COPY + 112:NAMES], "foreign retired header metadata")
        requests = _read_directory(payload)
        allocations = _allocations(requests)
        logo_site = next(a for a in allocations if a["owner"] == LOGO_REQUEST[0])
        _require(struct.unpack_from("<II", payload, 0x170) == (logo_site["va"], logo.LOGO_SIZE), "foreign grown logo pointer")
        _require(payload[logo_site["raw"]:logo_site["raw"] + logo.LOGO_SIZE] == logo.RETAIL_LOGO, "foreign grown logo bitmap")
        code = payload[CODE_RAW:DATA_RAW]
        mask = bytearray(PAGE)
        for a in allocations:
            if a["kind"] == "code":
                start = a["raw"] - CODE_RAW
                mask[start:start + a["size"]] = b"\1" * a["size"]
        _require(all(owned or value == 0xCC for owned, value in zip(mask, code)), "foreign unallocated code padding")
        _require(not any(payload[DATA_RAW:]), "data page must be zero initialised")
        for i, kind in enumerate(("code", "data")):
            raw = CODE_RAW + i * PAGE
            h = META_START + i * 56
            _require(payload[h:h + 56] == _descriptor(kind, _digest(payload[raw:raw + PAGE])), "foreign grown section header/digest")
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
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError):
        return "foreign"


def special_state(payload: bytes) -> str:
    """Validated projection used by SPECIAL, without recursion through its state()."""
    return _validate(payload)[1]


def layout(payload: bytes) -> dict:
    grown, special_status, requests = _validate(payload)
    return {"status": "applied" if grown else "retail", "special": special_status,
            "file_size": FILE_SIZE, "image_size": IMAGE_SIZE, "headers_size": PAGE,
            "regions": [{"kind": k, "va": va, "raw": raw, "size": PAGE, "flags": flags}
                        for k, va, raw, flags in (("code", CODE_VA, CODE_RAW, 0x36), ("data", DATA_VA, DATA_RAW, 3))],
            "allocations": _allocations(requests) if grown else []}


def reservations(payload: bytes | None = None) -> list[dict]:
    """Owned parent pages and named children; parent overlap is intentional."""
    result = [dict(start=hex(va), end=hex(va + PAGE), size=PAGE, owner=OWNER,
                   basis="owned grown " + kind + " page; all unused bytes reserved")
              for va, kind in ((CODE_VA, "code"), (DATA_VA, "data"))]
    if payload is not None:
        for a in layout(payload)["allocations"]:
            result.append(dict(start=hex(a["va"]), end=hex(a["va"] + a["size"]), size=a["size"],
                               owner=a["owner"], basis="named " + a["kind"] + " sub-allocation", parent_owner=OWNER))
    return result


def apply(payload: bytes, requests=()) -> tuple[bytes, dict]:
    grown, _, previous = _validate(payload)
    wanted = _requests(requests)
    _allocations(wanted)
    if grown:
        _require(wanted == previous or wanted == [LOGO_REQUEST], "allocation requests differ; rebuild from base")
        return payload, {"status": "already_applied", "changed_bytes": 0, "allocations": _allocations(previous)}
    code = bytearray(b"\xcc" * PAGE)
    logo_site = next(a for a in _allocations(wanted) if a["owner"] == LOGO_REQUEST[0])
    logo_offset = logo_site["raw"] - CODE_RAW
    code[logo_offset:logo_offset + logo.LOGO_SIZE] = logo.RETAIL_LOGO
    directory = _directory(wanted, code)
    buf = bytearray(payload)
    buf.extend(bytes(FILE_SIZE - len(buf)))
    buf[META_COPY:NAMES] = payload[META_START:META_END]
    for i in range(COUNT):
        for field in (20, 28, 32):
            off = TABLE + i * 56 + field
            struct.pack_into("<I", buf, off, struct.unpack_from("<I", buf, off)[0] + META_DELTA)
    buf[NAMES:REFS] = b".ASTRAc\0.ASTRAd\0"
    buf[REFS:DIRECTORY] = bytes(DIRECTORY - REFS)
    buf[DIRECTORY:PAGE] = directory
    buf[CODE_RAW:DATA_RAW] = code
    for i, kind in enumerate(("code", "data")):
        raw = CODE_RAW + i * PAGE
        buf[META_START + i * 56:META_START + (i + 1) * 56] = _descriptor(kind, _digest(buf[raw:raw + PAGE]))
    struct.pack_into("<II", buf, 0x108, PAGE, IMAGE_SIZE)
    struct.pack_into("<I", buf, 0x11C, COUNT + 2)
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
    buf[DIRECTORY:PAGE] = _directory(requests, buf[CODE_RAW:DATA_RAW])
    # Reuse the production section digest helper for executable writes.
    from .nfl2k5_bump_strength import _sections, section_digest
    s = next(s for s in _sections(buf) if s.virtual_address == CODE_VA)
    buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    result = bytes(buf)
    _require(status(result) == "applied", "code install postcondition failed")
    return result, {"status": "applied", "edits": [{"label": owner, "va": hex(a["va"]), "size": a["size"]}]}


def allocation_evidence(retail: bytes, manifest, *, allocated: bytes | None = None) -> dict:
    """Byte-granular absolute and relative encoding proof, including rel8/rel16.

    This proves encoded references, not register-synthesised addresses, kernel
    acceptance or gameplay. The pinned USA hash and manifest bind the evidence.
    """
    from .nfl2k5_cave_oracle import RETAIL_SHA256
    image = XbeImage(retail)
    _require(image.sha256 == RETAIL_SHA256 == manifest.document.get("retail_sha256"), "allocation proof needs pinned retail and matching manifest")
    _validate(retail)
    _require(image.base + image.image_size <= CODE_VA and all(s.end <= CODE_VA for s in image.sections), "new pages overlap retail")
    _require(special.TABLE_VA + special.TABLE_SIZE <= CODE_VA, "new pages overlap SPECIAL")
    from . import nfl2k5_dynamic_kickoff_relocated as relocated
    children = layout(allocated)["allocations"] if allocated is not None else _allocations(relocated.REQUESTS)
    for r in reservations():
        overlaps = manifest.overlaps(int(r["start"], 0), int(r["end"], 0), exclude_owner=OWNER)
        for overlap in overlaps:
            start, end = overlap.start, overlap.end
            _require(any(a["owner"] == overlap.detail.split(":", 1)[0] and a["va"] <= start < end <= a["va"] + a["size"]
                         for a in children), "new pages overlap another manifest owner")
    hits = []
    spans = [(image.base, retail[:image.headers_size], False)]
    spans += [(s.start, retail[s.raw:s.raw + s.raw_size], s.executable) for s in image.sections]
    for base, data, executable in spans:
        for off in range(len(data)):
            if off + 4 <= len(data) and CODE_VA <= struct.unpack_from("<I", data, off)[0] < DATA_VA + PAGE:
                hits.append((base + off, "absolute"))
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
                if CODE_VA <= target < DATA_VA + PAGE:
                    hits.append((base + off, "relative"))
            # Operand-size-overridden near transfers truncate EIP to 16 bits;
            # they cannot encode either page above 16 MiB.
    _require(not hits, f"retail reference encodings into new pages: {hits[:8]}")
    return {"allocation": "new_preloaded_sections", "start": hex(CODE_VA), "end": hex(DATA_VA + PAGE),
            "encoded_references": [], "manifest_overlaps": [], "retail_sha256": image.sha256,
            "cave_verdict": "unmapped; owned loader allocation, not a free retail cave",
            "proof_boundary": "encoded references and structural mapping; runtime loader/gameplay unwitnessed"}
