"""PROVED OFFLINE mechanism: isolated retail franchise books for historical sides.

The default-book decision runs separately for each match team. Mode 8 or category
4 bypasses saved/custom selections. Anniversary sides from 2005 onward use their
franchise's current book; older or unavailable seasons use the preserved bank.
A bounded, exact franchise lookup copies a
NUL-terminated alias into the existing 32-wide-character buffer. No team pointer,
shared label or cached game state is modified. DESIGN: rendered-game acceptance.

b77-a4 (second generation of the body): the same 1,536 byte allocation also carries the era's shotgun weights for the
Anniversary moments (``nfl2k5_moment_gun_weight``: a 34 byte stub and 51 floats), because the books alone cannot make a
modern team call shotgun (retail rule 0x207EF0). To make room the 32 aliases are no longer stored as 40 byte rows: a row is
the 8 byte franchise key and the resolver builds ``E2R-<key>-pb.iff`` from a shared prefix and suffix, which produces the
same wide string, byte for byte, as the earlier bodies copied. The earlier bodies are still recognised and completed
in place (``needs_fix``).

b77-a4pd (third generation): the franchise part of the shotgun weight is a 32 x 7 table (one weight per down and distance bin,
uint16 multiples of 0.05) instead of 32 floats. The stub grows from 127 to 245 bytes (it reads the down and the yards to go), so it
now has 256 bytes, the moment table moves up with it and the bin table (448 bytes) takes the old franchise table's place and the
free tail; the 1,536 byte allocation, its owner and the two edited sites do not change. The a4 body (one weight per franchise) is
recognised as a previous generation and completed in place, like the v0.5 body.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_moment_gun_weight as gun
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
LEGACY_TABLE = 256                    # earlier bodies: code, then 32 rows of key (8 bytes) + alias (32 bytes)
LEGACY_STRIDE = 40
TABLE = 320                           # current body: code (at most 320 bytes), then 32 rows of the 8 byte key
STRIDE = 8
PREFIX_OFFSET = TABLE + 32 * STRIDE   # L"E2R-"
SUFFIX_OFFSET = PREFIX_OFFSET + 8     # L"-pb.iff\0"
STUB_OFFSET = 608                     # the shotgun weight stub (padded to 256 bytes; 128 in the a4 body)
WEIGHT_OFFSET = STUB_OFFSET + gun.STUB_SPACE        # 51 float32 moment weights (204 bytes)
BIN_TABLE_OFFSET = WEIGHT_OFFSET + 208              # 32 x 7 uint16 franchise bin weights (units of 0.05), in the order of the key rows (448 bytes)
assert SUFFIX_OFFSET + 16 <= STUB_OFFSET and WEIGHT_OFFSET + gun.TABLE_SIZE <= BIN_TABLE_OFFSET
assert BIN_TABLE_OFFSET + gun.BIN_TABLE_SIZE <= CODE_SIZE
# the a4 body (generation 2): 128 byte stub, 51 moment floats, 32 franchise floats
SINGLE_WEIGHT_OFFSET = STUB_OFFSET + gun.STUB_SPACE_SINGLE
SINGLE_TEAM_OFFSET = SINGLE_WEIGHT_OFFSET + 208
assert SINGLE_TEAM_OFFSET + gun.TEAM_TABLE_SIZE <= CODE_SIZE
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


def code_for(va, *, modern_moments=True, moment_limit=MOMENT_COUNT, legacy=False, single_weight=False,
             legacy_team_pointer=False, weights=None, team_weights=None):
    """The 1,536 owned bytes at ``va``. ``legacy`` is the body of v0.5 and earlier (40 byte alias rows, no shotgun weights);
    ``single_weight`` is the a4 body (one franchise float per franchise, ``team_weights`` = 32 floats); the default is the current
    body, whose weights are ``weights`` (51 moment floats) and ``team_weights`` (32 rows of 7 bin weights in key-row order) or the
    era data file's."""
    require(type(moment_limit) is int and moment_limit in (50, MOMENT_COUNT), "unsupported Anniversary moment limit")
    table, stride = (LEGACY_TABLE, LEGACY_STRIDE) if legacy else (TABLE, STRIDE)
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
    a.b("b9" + struct.pack("<I", va + table).hex())
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
    a.b("83c1" + bytes([stride]).hex() + "81f9" + struct.pack("<I", va + table + 32 * stride).hex())
    a.j32("0f82", "scan")
    a.label("retail")
    a.b("85ff")
    a.j32("0f84", "default")
    a.jmp_abs(SITE + len(RETAIL))
    a.label("default")
    a.jmp_abs(0x62A1B)
    a.label("found")
    if legacy:
        a.b("56578bfe8d7108b910000000fcf366a55f5e")  # copy exactly 32 bytes including NUL
    else:
        # ECX = the matching 8 byte key row. Build L"E2R-" + key + L"-pb.iff" + NUL into the 16 word buffer (zeroed first, so the
        # 32 bytes are exactly what the earlier bodies copied); ESI/EDI are restored, EAX/ECX/EDX are free here.
        a.b("5657")                     # push esi / push edi
        a.b("8bd1")                     # mov edx, ecx  (key row)
        a.b("8bfe33c0b910000000fcf366ab")   # mov edi,esi / xor eax,eax / mov ecx,16 / cld / rep stosw
        a.b("8bfe")                     # mov edi, esi
        a.b("be" + struct.pack("<I", va + PREFIX_OFFSET).hex() + "b904000000f366a5")   # mov esi,prefix / mov ecx,4 / rep movsw
        a.label("key_char")
        a.b("668b026685c0")             # mov ax,[edx] / test ax,ax
        a.j8("74", "key_done")
        a.b("66ab83c202")               # stosw / add edx,2
        a.j8("eb", "key_char")
        a.label("key_done")
        a.b("be" + struct.pack("<I", va + SUFFIX_OFFSET).hex() + "b908000000f366a5")   # mov esi,suffix / mov ecx,8 / rep movsw
        a.b("5f5e")                     # pop edi / pop esi
    a.jmp_abs(0x62A37)                  # original epilogue
    out = bytearray(a.assemble())
    require(len(out) <= table, "stock resolver exceeded its code budget")
    out.extend(b"\xcc" * (table - len(out)))
    for row in aliases():
        key = row["source"].removesuffix("-pb.iff")
        require(2 <= len(key) <= 3 and key.isascii(), "invalid franchise key")
        name = (row["alias"] + "\0").encode("utf-16le")
        require(len(name) <= 32, "stock alias exceeds bounded copy")
        if legacy:
            out.extend((key + "\0").encode("utf-16le").ljust(8, b"\0") + name.ljust(32, b"\0"))
        else:
            require(row["alias"] == "E2R-" + key + "-pb.iff", "stock alias is not E2R-<key>-pb.iff")
            out.extend((key + "\0").encode("utf-16le").ljust(8, b"\0"))
    if legacy:
        return bytes(out).ljust(CODE_SIZE, b"\xcc")
    out.extend("E2R-".encode("utf-16le") + "-pb.iff\0".encode("utf-16le"))
    out.extend(b"\xcc" * (STUB_OFFSET - len(out)))
    moment_values = gun.weights() if weights is None else list(weights)
    if single_weight:
        require(team_weights is not None, "the a4 body needs its 32 franchise floats")
        out.extend(gun.stub_bytes_single(va + STUB_OFFSET, va + SINGLE_WEIGHT_OFFSET, va + TABLE, va + SINGLE_TEAM_OFFSET))
        out.extend(gun.table_bytes(moment_values))
        out.extend(b"\xcc" * (SINGLE_TEAM_OFFSET - len(out)))
        out.extend(gun.team_table_bytes(list(team_weights)))
    else:
        out.extend(gun.stub_bytes(va + STUB_OFFSET, va + WEIGHT_OFFSET, va + TABLE, va + BIN_TABLE_OFFSET,
                                  legacy_team_pointer=legacy_team_pointer))
        out.extend(gun.table_bytes(moment_values))
        out.extend(b"\xcc" * (BIN_TABLE_OFFSET - len(out)))
        out.extend(gun.bin_table_bytes(gun.team_bin_weights(keys=key_order()) if team_weights is None else [list(r) for r in team_weights]))
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def key_order():
    """The franchise keys of the 32 key rows, in row order."""
    return [row["source"].removesuffix("-pb.iff") for row in aliases()]


def gun_sites(va):
    return gun.sites(va + STUB_OFFSET)


def allocation(payload):
    found = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not found:
        return None
    require(len(found) == 1 and found[0]["kind"] == "code" and found[0]["size"] == CODE_SIZE,
            "reserve stock books in the complete owner union")
    return found[0]


def hook(va):
    return b"\xe9" + struct.pack("<i", va - SITE - 5) + b"\x90" * (len(RETAIL) - 5)


def _previous_bodies(va):
    """Every earlier body of this allocation (v0.5 and before), which apply() completes in place."""
    return (code_for(va, modern_moments=False, legacy=True), code_for(va, moment_limit=50, legacy=True), code_for(va, legacy=True))


def _installed_kind(image, va):
    """(kind, (moment weights, franchise weights) or None) for the 1,536 bytes at ``va``; anything else raises. Kinds: "empty";
    "previous" (the v0.5 and earlier bodies); "single" (the a4 body, one float per franchise; the weights are its own, 32 floats);
    "unfixed_bins" (shipped a4pd, missing the live-to-roster dereference);
    "current" (fixed per-bin body; the weights are its own, 32 rows of 7)."""
    installed = image.read(va, CODE_SIZE)
    if installed == b"\xcc" * CODE_SIZE:
        return "empty", None
    if installed in _previous_bodies(va):
        return "previous", None
    try:
        weights = gun.decode_table(installed[WEIGHT_OFFSET:WEIGHT_OFFSET + gun.TABLE_SIZE])
        bins = gun.decode_bin_table(installed[BIN_TABLE_OFFSET:BIN_TABLE_OFFSET + gun.BIN_TABLE_SIZE])
        if installed == code_for(va, weights=weights, team_weights=bins):
            return "current", (weights, bins)
        if installed == code_for(va, weights=weights, team_weights=bins, legacy_team_pointer=True):
            return "unfixed_bins", (weights, bins)
    except ValueError:
        pass
    weights = gun.decode_table(installed[SINGLE_WEIGHT_OFFSET:SINGLE_WEIGHT_OFFSET + gun.TABLE_SIZE])
    team = gun.decode_team_table(installed[SINGLE_TEAM_OFFSET:SINGLE_TEAM_OFFSET + gun.TEAM_TABLE_SIZE])
    require(installed == code_for(va, single_weight=True, weights=weights, team_weights=team), "foreign stock resolver body")
    return "single", (weights, team)


def _recognize(payload):
    image, owned = XbeImage(payload), allocation(payload)
    actual = image.read(SITE, len(RETAIL))
    state = "retail" if actual == RETAIL else "applied" if owned and actual == hook(owned["va"]) else "foreign"
    if owned:
        kind, _weights = _installed_kind(image, owned["va"])
        gun_state = gun.site_state(image, owned["va"] + STUB_OFFSET if kind in ("single", "unfixed_bins", "current") else None)
        if state == "retail":
            require(gun_state == "retail", "shotgun weight site installed without the stock book resolver")
        else:
            require(kind != "empty", "foreign stock resolver body")
            if kind == "previous":
                require(gun_state == "retail", "shotgun weight site installed on an earlier resolver body")
                state = "needs_fix"
            elif kind in ("single", "unfixed_bins"):
                require(gun_state == "applied", "shotgun weight site missing on the earlier a4 resolver body")
                state = "needs_fix"
            elif gun_state == "retail":
                state = "needs_fix"
            gun.check_rule(image)
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


def _write_body(payload, owned, body):
    """``payload`` with the owner's 1,536 bytes replaced by ``body`` and the allocator seals and section digests recomputed."""
    buffer = bytearray(payload)
    buffer[owned["raw"]:owned["raw"] + CODE_SIZE] = body
    _, _, requests = space._validate(payload)
    if space.is_scaleout(payload):
        space._seal_scaleout(buffer, requests)
    else:
        buffer[space.DIRECTORY:space._directory_end(requests)] = space._directory(
            requests, space._code_bytes(buffer, requests))
        for section in _sections(buffer):
            buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    return bytes(buffer)


def apply(payload, *, enabled=True, weights=None, team_weights=None):
    """Install (or, ``enabled=False``, switch off) the resolver and the shotgun weight site. ``weights`` are the 51 per-moment
    shotgun weights (default: ``data/nfl2k5_moment_playbook_eras.json``) and ``team_weights`` the 32 x 7 franchise bin weights
    (key-row order, ``gun.BIN_NAMES`` order); other weights over an installed body replace it in place."""
    before = _recognize(payload)
    desired = "applied" if enabled else "retail"
    values = gun.weights() if weights is None else list(weights)
    team_values = gun.team_bin_weights(keys=key_order()) if team_weights is None else [list(r) for r in team_weights]
    if before == desired:
        found = allocation(payload)
        if not (enabled and found and XbeImage(payload).read(found["va"], CODE_SIZE) != code_for(found["va"], weights=values, team_weights=team_values)):
            return payload, dict(status="already_" + desired, owner=OWNER, changed_bytes=0)
    original = payload
    if allocation(payload) is None:
        require(space.status(payload) == "retail", "stock books missing from complete owner union")
        payload, _ = space.apply(payload, REQUESTS)
    owned = allocation(payload)
    if enabled:
        image = XbeImage(payload)
        gun.check_rule(image)                     # the shotgun rule must be the retail bytes this owner replaces the constant of
        kind, installed_weights = _installed_kind(image, owned["va"])
        wanted = code_for(owned["va"], weights=values, team_weights=team_values)
        if kind in ("previous", "single", "unfixed_bins") or (kind == "current" and image.read(owned["va"], CODE_SIZE) != wanted):
            # Only this owner admits these exact checked version transitions (an earlier body, or other weights).
            # The generic allocator still refuses arbitrary filled-code edits.
            payload = _write_body(payload, owned, wanted)
        elif kind == "empty":
            payload, _ = space.install_code(payload, OWNER, wanted)
    image = XbeImage(payload)
    out = bytearray(payload)
    at = image.offset(SITE, len(RETAIL))
    out[at:at + len(RETAIL)] = hook(owned["va"]) if enabled else RETAIL
    for _label, va, retail, patched in gun_sites(owned["va"]):
        at = image.offset(va, len(retail))
        out[at:at + len(retail)] = patched if enabled else retail
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    result = bytes(out)
    require(status(result) == desired, "stock book resolver read-back failed")
    return result, dict(status=desired, owner=OWNER, classification="PROVED OFFLINE", runtime_witnessed=False,
                        upgraded_moment_routing=before == "needs_fix" and enabled,
                        moment_gun_weights=[round(v, 4) for v in values] if enabled else None,
                        team_gun_weights={key: dict(zip(gun.BIN_NAMES, row)) for key, row in zip(key_order(), team_values)} if enabled else None,
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
