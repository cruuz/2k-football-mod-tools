"""PROVED OFFLINE mechanism: isolated retail franchise books for historical sides.

The default-book decision runs separately for each match team. Mode 8 or category
4 bypasses saved/custom selections. Anniversary sides from 2005 onward use their
franchise's current book; older or unavailable seasons use the preserved bank.
A bounded, exact franchise lookup copies a
NUL-terminated alias into the existing 32-wide-character buffer. No team pointer,
shared label or cached game state is modified. DESIGN: rendered-game acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_stock_books"
UI_LABEL = "Stock playbooks for historic teams"
BUILD_CAPTION = UI_LABEL
CODE_SIZE = 1536
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
SITE = 0x62902
RETAIL = bytes.fromhex("85ff8bd80f840f010000")
TABLE = 256
STRIDE = 40
MANIFEST = Path(__file__).resolve().parents[2] / "data/nfl2k5_stock_books.json"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def aliases():
    rows = json.loads(MANIFEST.read_text())["aliases"]
    require(len(rows) == 32 and len({r["alias_name_id"] for r in rows}) == 32, "stock bank manifest")
    return rows


MODERN_FIRST_SEASON, MODERN_LAST_SEASON = 2005, 2030
MOMENT_COUNT = 51


def code_for(va, *, modern_moments=True, moment_limit=MOMENT_COUNT):
    require(type(moment_limit) is int and moment_limit in (50, MOMENT_COUNT), "unsupported Anniversary moment limit")
    a = _Asm(va)
    a.b("8bd8")                         # EBX = match team (displaced)
    if modern_moments:
        a.b("85db")
        a.j32("0f84", "retail")
    a.b("833d80ffe50008")               # mode == Anniversary
    a.j32("0f84", "moment" if modern_moments else "stock")
    if not modern_moments:
        a.b("85db")
        a.j32("0f84", "retail")
    a.b("83bb2801000004")               # this side's category, never the opponent's
    a.j32("0f85", "retail")
    if modern_moments:
        a.j32("e9", "stock")
        a.label("moment")
        # 2CFD00 binds the live SITU rows/count. 20CB30 stores the selected
        # ordinal and reads home +20 / away +1c. The formatter's own argument
        # [EBP+8] is 1 for home, 0 for away. Do not infer an era from a title,
        # roster pointer or the other side. Invalid/unloaded tables stay stock.
        a.b("833dd4f0c80000")
        a.j8("74", "stock")
        a.b("833dd8f0c800" + bytes([moment_limit]).hex())
        a.j8("77", "stock")
        a.b("8b0d5818bf003b0dd8f0c800")
        a.j8("73", "stock")
        a.call(0x2CFD40)
        a.b("85c0")
        a.j8("74", "stock")
        a.b("8b4d0885c90f95c10fb6c98b44881c")
        a.b("2d" + struct.pack("<I", MODERN_FIRST_SEASON).hex())
        a.b("83f8" + bytes([MODERN_LAST_SEASON - MODERN_FIRST_SEASON]).hex())
        a.j8("77", "stock")
        a.j32("e9", "default")
    a.label("stock")
    a.b("85db")
    a.j32("0f84", "retail")
    a.b("8b931001000085d2")
    a.j32("0f84", "retail")
    a.b("8b520485d2")
    a.j32("0f84", "retail")
    a.b("b9" + struct.pack("<I", va + TABLE).hex())
    a.label("scan")
    a.b("8b023b01")                    # first two UTF-16 letters
    a.j32("0f85", "next")
    a.b("668b4204663b4104")             # third letter or NUL
    a.j32("0f85", "next")
    a.b("6685c0")
    a.j32("0f84", "found")
    a.b("66837a0600")                  # a three-letter key must terminate
    a.j32("0f84", "found")
    a.label("next")
    a.b("83c12881f9" + struct.pack("<I", va + TABLE + 32 * STRIDE).hex())
    a.j32("0f82", "scan")
    a.label("retail")
    a.b("85ff")
    a.j32("0f84", "default")
    a.jmp_abs(SITE + len(RETAIL))
    a.label("default")
    a.jmp_abs(0x62A1B)
    a.label("found")
    a.b("56578bfe8d7108b910000000fcf366a55f5e")  # copy exactly 32 bytes including NUL
    a.jmp_abs(0x62A37)                  # original epilogue
    out = bytearray(a.assemble())
    require(len(out) <= TABLE, "stock resolver exceeded its code budget")
    out.extend(b"\xcc" * (TABLE - len(out)))
    for row in aliases():
        key = row["source"].removesuffix("-pb.iff")
        require(2 <= len(key) <= 3 and key.isascii(), "invalid franchise key")
        name = (row["alias"] + "\0").encode("utf-16le")
        require(len(name) <= 32, "stock alias exceeds bounded copy")
        out.extend((key + "\0").encode("utf-16le").ljust(8, b"\0") + name.ljust(32, b"\0"))
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def allocation(payload):
    found = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not found:
        return None
    require(len(found) == 1 and found[0]["kind"] == "code" and found[0]["size"] == CODE_SIZE,
            "reserve stock books in the complete owner union")
    return found[0]


def hook(va):
    return b"\xe9" + struct.pack("<i", va - SITE - 5) + b"\x90" * (len(RETAIL) - 5)


def _recognize(payload):
    image, owned = XbeImage(payload), allocation(payload)
    actual = image.read(SITE, len(RETAIL))
    state = "retail" if actual == RETAIL else "applied" if owned and actual == hook(owned["va"]) else "foreign"
    if owned:
        current = code_for(owned["va"])
        previous = (code_for(owned["va"], modern_moments=False),
                    code_for(owned["va"], moment_limit=50))
        expected = (b"\xcc" * CODE_SIZE, current, *previous) if state == "retail" else (current, *previous)
        installed = image.read(owned["va"], CODE_SIZE)
        require(installed in expected, "foreign stock resolver body")
        if state == "applied" and installed in previous:
            state = "needs_fix"
    # Pin the complete formatter, normalizing only the owned decision.
    body = bytearray(image.read(0x628D0, 0x170))
    body[SITE - 0x628D0:SITE - 0x628D0 + len(RETAIL)] = RETAIL
    require(hashlib.sha256(body).hexdigest() == FORMATTER_SHA256, "foreign default book formatter")
    for va, size, digest in MOMENT_GUARDS:
        actual_digest = hashlib.sha256(image.read(va, size)).hexdigest()
        if actual_digest != digest and va == 0x20CB43:
            # Chronological Anniversary selection owns a call inside this
            # reader window. Normalize it only after its complete hooks and
            # generated body have passed that owner's exact recognizer.
            from . import nfl2k5_espn25_more_moments as moments
            require(moments.status(payload) == "applied", "foreign Anniversary display reader")
            code, data = moments.allocations(payload)
            edits = moments.sites(code["va"], data["va"], MOMENT_COUNT)
            actual_digest = moments._guard_digest(image, va, size, edits)
        require(actual_digest == digest,
                "foreign native moment table reader")
    require(state != "foreign", "foreign stock resolver hook")
    return state


FORMATTER_SHA256 = "b1c5fcbd35e743d9d172d5fd8072ed2bafde6548a22da99b8a7474743deb33d5"
MOMENT_GUARDS = (
    (0x2CFD00, 0x20, "c913e67e94778fd703278c689761a0987c36b3cb00eecf97a94f23a8b82f0c0c"),
    (0x2CFD40, 0x15, "7f3be8f6f9f97aaacbe7155caaca6bfcbda8b967352a84d7e12e2d61ca746b80"),
    (0x20CB43, 0x20, "318a575180b1048b70d1b5f36dc58128c2269c131dc5d63c5ed7be53c786b5cb"),
)


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, KeyError, IndexError, TypeError, struct.error):
        return "foreign"


def apply(payload, *, enabled=True):
    before = _recognize(payload)
    desired = "applied" if enabled else "retail"
    if before == desired:
        return payload, dict(status="already_" + desired, owner=OWNER, changed_bytes=0)
    original = payload
    if allocation(payload) is None:
        require(space.status(payload) == "retail", "stock books missing from complete owner union")
        payload, _ = space.apply(payload, REQUESTS)
    owned = allocation(payload)
    if enabled:
        image = XbeImage(payload)
        if image.read(owned["va"], CODE_SIZE) in (code_for(owned["va"], modern_moments=False),
                                                code_for(owned["va"], moment_limit=50)):
            # Only this owner admits this exact checked version transition.
            # The generic allocator still refuses arbitrary filled-code edits.
            buffer = bytearray(payload)
            buffer[owned["raw"]:owned["raw"] + CODE_SIZE] = code_for(owned["va"])
            _, _, requests = space._validate(payload)
            if space.is_scaleout(payload):
                space._seal_scaleout(buffer, requests)
            else:
                buffer[space.DIRECTORY:space._directory_end(requests)] = space._directory(
                    requests, space._code_bytes(buffer, requests))
                for section in _sections(buffer):
                    buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
            payload = bytes(buffer)
        else:
            payload, _ = space.install_code(payload, OWNER, code_for(owned["va"]))
    image = XbeImage(payload)
    out = bytearray(payload)
    at = image.offset(SITE, len(RETAIL))
    out[at:at + len(RETAIL)] = hook(owned["va"]) if enabled else RETAIL
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    result = bytes(out)
    require(status(result) == desired, "stock book resolver read-back failed")
    return result, dict(status=desired, owner=OWNER, classification="PROVED OFFLINE", runtime_witnessed=False,
                        upgraded_moment_routing=before == "needs_fix" and enabled,
                        changed_bytes=sum(a != b for a, b in zip(original, result)) + len(result) - len(original))


def preserve(source, *, one_pool=False):
    """Read and pin ALL retail bytes before any gameplay writer. Recode personnel only."""
    from . import nfl2k5_historic_styles as hs
    from tools import nfl2k5_playbook_position_recode as rc
    bank, receipt = {}, []
    with hs.Source(source) as src:
        for row in aliases():
            raw = src.get(row["source"])
            require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["source_sha256"],
                    f"{row['source']}: not the verified retail PLAY resource")
            out = bytearray(raw)
            changed = []
            if one_pool:
                entry = rc.OuterEntry(row["source_outer"], 0, 0, len(raw))
                book = rc.parse_book(row["source"], entry, raw)
                for cat in book.categories:
                    # Historic ROST always uses reclassify's 4-3 mapping, even for
                    # an odd-front book. Keep DE/DT pools and merge only OLB.
                    codes = list(cat.codes)
                    used = {c >> 5 for c in codes if c & 31 == rc.KIND_ILB}
                    for i in sorted((i for i, c in enumerate(cat.codes) if c & 31 == rc.KIND_OLB),
                                    key=lambda i: (cat.codes[i] >> 5, i)):
                        variant = (cat.codes[i] >> 5) + 1
                        while variant in used:
                            variant += 1
                        used.add(variant)
                        codes[i] = rc.make_code(rc.KIND_ILB, variant)
                    at = 32 + rc.CATEGORY_BASE + cat.index * rc.CATEGORY_SIZE + 5
                    out[at:at + 11] = bytes(codes)
                    changed.extend(at + i for i, (a, b) in enumerate(zip(cat.codes, codes)) if a != b)
            require([i for i, (a, b) in enumerate(zip(raw, out)) if a != b] == sorted(changed),
                    "stock book changed outside personnel codes")
            bank[row["alias"]] = bytes(out)
            receipt.append(dict(file=row["alias"], source_sha256=row["source_sha256"],
                                sha256=hashlib.sha256(out).hexdigest(), personnel_bytes=len(changed)))
    return bank, dict(classification="PROVED OFFLINE", source=str(source), one_pool=one_pool, books=receipt)


def image_status(path, bank=None):
    from . import nfl2k5_historic_styles as hs
    with hs.Source(path) as src:
        rows = aliases()
        present = [src.has(row["alias"]) for row in rows]
        if not any(present):
            return "retail"
        if not all(present):
            return "foreign"
        if bank is not None:
            return "applied" if all(src.get(n) == raw for n, raw in bank.items()) else "foreign"
        hashes = [hashlib.sha256(src.get(row["alias"])).hexdigest() for row in rows]
        return "applied" if any(all(actual == row[key] for actual, row in zip(hashes, rows))
                                for key in ("source_sha256", "one_pool_sha256")) else "foreign"


def apply_to_image(path, bank):
    from . import nfl2k5_historic_styles as hs
    state = image_status(path, bank)
    if state == "applied":
        return dict(status="already_applied")
    require(state == "retail", "stock bank is mixed or foreign")
    # PLAY's internal length stays exact. A separate filler finishes pack F on a sector.
    appended = list(bank.items()) + [("e2-stock-bank-pad.bin", bytes(2048))]
    receipt = hs.rewrite_archive(path, {}, appended, verify=lambda p: image_status(p, bank) == "applied")
    return dict(status="applied", books=len(bank), **receipt)
