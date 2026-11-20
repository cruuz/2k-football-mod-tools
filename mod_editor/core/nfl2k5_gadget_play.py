"""The SPECIAL GAD row on gadget plays (beta 81, Q62 "rule 3" redo). EXPERIMENTAL.

Noah (11/03): "sometimes gadget player should be in the halfback position ... just make sure that every movement in the
special part of the depth chart does something accurately, and it doesn't permanently make someone in a special
position a starter somewhere else." The approved default (11/03, "Rest looks good"): the gadget player is only in
for gadget plays; starters keep priority everywhere else.

What it does. When the offense snaps a gadget play (the quarterback hands off, opcode 0x13, to a wide receiver whose own
script takes the ball, opcode 0x16: end around, reverse, WB sweep), the club's SPECIAL GAD player (WR ordinal 7, the
receiver side order's fourth man) is offered to that receiver's lineup slot for that snap only. He plays there if he is
healthy, passes the picker's own availability gate, is not already on the field, and his Speed (player byte 0x36,
unsigned) is at least the normal pick's. Every other play, and every other slot, keeps the game's own lineup.

Why the beta-80 rule froze (FC1 0x151CCB1, FC2 0x151CCCA). It read the lineup builder's second stack argument as the
called play. At the builder call 0x18A641 the first two stack arguments are the personnel category and the formation
record. On the type-12 set-up path (return 0x18B189) a punt formation's word there is zero; on the snap path a Gun
Empty formation's lateral alignment of -302 cm (low 16 bits 0xFED2) was taken for a pointer.

How this one decides (Codex's private Q62 candidate, job/b81-gadget-proof f9df9acc5; its classifier unchanged; sources in
tools/gadget_play/). A build-time table lists every (book, formation, play) link of the disc's 37 play books whose play
hands one wide receiver slot the ball, with the play's whole script as the game relocates it. At run time it acts only
on the snap path (0x18A5D0 returning to 0x18AD4B, called from 0x89624), only for the team that has the ball, only with
that side's own book, and only when the builder's category and formation are the play the game published. It finds
the book by its name, bounds-checks every pointer against that book before reading it, and byte-compares the
published play's script with the table's copy. Anything else returns the game's own lineup. Inside the builder, the
ordinal helper's call for the matched slot (0xE8AFC, the only call that runs when the user made no explicit
substitution) also reads the GAD row; after the builder returns, a GAD player who is not on the field and is at least
as fast replaces the slot's pick.

One snap only (beta 81 review F1). The rule changes one build's output; the game rebuilds a lineup only on the
play-call path. The no-huddle, audible and CPU re-pick handlers store the next play with 0x9F990 and keep the eleven
on the field, so the emulator showed the GAD staying for a no-huddle snap. 0x9F990's call to 0xB8790 (right after the
store) now runs through a small restore. A substitution marks the offense side; the side's next store, or its next
play-call offense build, spends the mark. When that store is for the offense and is not the huddle play call
(0x2074BC, always followed by the play-call build), the offense lineup is rebuilt exactly as 0x89590 builds it: the
game's own eleven for the stored play (so after a gadget play a no-huddle or audible snap lines up the normal players
for the new play, as a huddle call of it would, rather than the same eleven; retail no-huddle keeps the eleven).
The marker is a word in the owner's code allocation, which lies in the writable scale-out pool section (as the QB
bank's state does).

Placement. The code and table use the fixed gadget slots (nfl2k5_xbe_space.GADGET_REQUESTS: code 0x151F680, 2,048
bytes; table 0x151FE80, 12,800 bytes, right below the Backfield cards at 0x1523080), which every beta-81 standard
build reserves, so installing, rebuilding or removing it never moves another owner. Three sites: the builder call
0x18A641 (5 bytes), the ordinal helper entry 0xE7760 (6 bytes) and the play store's call 0x9F9CB (5 bytes).
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any, Mapping

from . import nfl2k5_gadget_play_code as template
from . import nfl2k5_lineup_roles as lineup
from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from . import nfl2k5_playbook_inspector as ip
from . import nfl2k5_playbook_pair as pair
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.GADGET_OWNER
REQUESTS = space.GADGET_REQUESTS
CODE_SIZE = REQUESTS[0][2]
TABLE_SIZE = REQUESTS[1][2]
CODE_VA = space.GADGET_CODE_VA
TABLE_VA = CODE_VA + CODE_SIZE
BUILD_CAPTION = "Gadget player on gadget plays (experimental)"
HELP_TEXT = ("EXPERIMENTAL. On an end around, reverse or WB sweep that hands a wide receiver the ball, your SPECIAL GAD "
             "player takes that receiver's spot for that snap, if he is healthy, not already on the field and at least "
             "as fast. Every other play keeps your normal receivers. A disc that already has it keeps it when you build "
             "on it again with this box unticked; to take it out, build again from your retail disc or run "
             "tools/nfl2k5_modpack.py edit-gadget-play --mode off on a copy.")
BOOK_ASSETS = tuple(str(asset) for asset in range(307, 344))   # 32 club books, Editor, GEN, PRACTICE, reference, WCO
WR_CODE = 9

BUILDER_SITE, BUILDER = 0x0018A641, 0x000E89F0
ORDINAL_SITE = 0x000E7760
BUILDER_RETAIL = b"\xe8" + struct.pack("<i", BUILDER - BUILDER_SITE - 5)
ORDINAL_RETAIL = bytes.fromhex("53558b6c2410")   # push ebx; push ebp; mov ebp,[esp+0x10] (continues at 0xE7766)
# Review F1: 0x9F990 (store the next play: play call, no-huddle, audible, CPU re-pick) calls 0xB8790 right after the
# store; that call goes through the restore, which rebuilds the offense lineup when its last build had a substitution.
STORE_SITE, FORMATION_SYNC = 0x0009F9CB, 0x000B8790
STORE_RETAIL = b"\xe8" + struct.pack("<i", FORMATION_SYNC - STORE_SITE - 5)

BOOK_RECORD = struct.Struct("<12sHH")
LINK = struct.Struct("<HHBBBBII")

# Native code the runtime's stack offsets and calls rely on (sha256 of the retail bytes; masked spans belong to other
# owners). The lineup builder, picker and list helpers are pinned by nfl2k5_lineup_roles, which this owner requires.
GUARDS = (
    (0x0018A5D0, 0x71, (), "e248d59a53380f86c5d1f80a39aeee5da2dd2e4365141d7d28a8127149950518", "lineup set-up frame"),
    (0x0018AD10, 0x3B, (), "d4421a4e274aa2d5474666237ab035ff05010d63fb46552830f5fd2cd5ca05f1", "snap-path caller"),
    (0x0008960E, 0x16, (), "9fd1f95955dee5afc61fde9ec4f69459196a6969825fa881e2dc72d4fd9d1341", "snap-path parent"),
    (0x000E7766, 0x2A, (), "ac2e67b18b974c67fd4c0b95466809f3484c3f8a0e99479fb0a09eda1e7babfa", "ordinal helper body"),
    (0x000E8AF0, 0x11, (), "08b44aba82c6e70edad55ad647dacc4cdd4bd618fed93df0ab87a93e01881601", "builder's ordinal helper call"),
    (0x000E89F0, 0x150, ((0x000E8B21, 4),), "82c6b3a4e62b22508d0492801a68e5634270563bb368d6fea4efa2d0eda52334", "lineup builder"),
    (0x0009F990, 0x3B, (), "99150b8c6d835d4a46916383f88eddfd66f58a587e7ea0fdc7d19b19bdce5c33", "play store, before the restore site"),
    (0x0009F9D0, 0xA8, (), "9c0c03d32d2954adf2e938a39bda7e8b69d7f4a2088c9f7ce1b34f139e6755c4", "play store, after the restore site"),
    (0x000895E4, 0x40, (), "52d3d3f18eda6f9d2e54973aecc3e230ae77c3c90aac6568b0267cac90736b0f", "play-call offense build the restore repeats"),
    (0x002074AD, 0x1B, (), "4b2164592b7b5f25f4c1bcefb1bf188dde46c072edb123a72632f09c25b723d3", "huddle play-call store the restore leaves alone"),
)


class GadgetPlayError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise GadgetPlayError(message)


def _span(image: XbeImage, va: int, size: int, masks) -> bytes:
    raw = bytearray(image.read(va, size))
    for at, length in masks:
        raw[at - va:at - va + length] = bytes(length)
    return bytes(raw)


def _guards_ok(image: XbeImage) -> bool:
    return all(hashlib.sha256(_span(image, va, size, masks)).hexdigest() == pin
               for va, size, masks, pin, _name in GUARDS)


# ---------------------------------------------------------------------------------------------------------------------
# The gadget table (Codex's candidate.choose/table_for, unchanged in output).

def _choose(body: bytes, play: int) -> tuple[int, set[int], bytes]:
    flags, chains = lib.play_chains(body, play)
    recipients = {int(codec.Node.from_bytes(node).operands[0]) for _desc, nodes in chains for node in nodes
                  if node[0] == 0x13}
    carriers = {slot for slot in recipients if 0 <= slot < 11 and any(n[0] == 0x16 for n in chains[slot][1])}
    program = bytearray(struct.pack("<I", flags & 0x7FFFFFFF))
    for descriptor, nodes in chains:
        program.extend(struct.pack("<I", descriptor))
        program.extend(b"".join(nodes))
    return flags, carriers, bytes(program)


def compile_table(resources: Mapping[str, bytes], pair_address: int, *,
                  left_out: tuple[str, ...] = ()) -> tuple[bytes, dict[str, int], list[dict]]:
    """The read-only table for the 37 play books of a disc: (bytes padded to 16, offsets, per-book rows).

    Book rows (name, first link, link count) in asset order; then the links (play, paired play, formation, paired
    formation, slot, 0, script offset, category codes offset); then the de-duplicated scripts and category codes;
    then the playbook pair contract address. A play with two receiver carriers is left out (the runtime keeps the
    game's lineup for it). Books named in ``left_out`` keep their row with no links (their plays keep the game's
    lineup)."""
    books, links, blobs = bytearray(), bytearray(), bytearray()
    by_content: dict[bytes, int] = {}
    rows: list[dict] = []

    def intern(data: bytes) -> int:
        if data not in by_content:
            by_content[data] = len(blobs)
            blobs.extend(data)
        return by_content[data]

    seen = set()
    for asset in BOOK_ASSETS:
        _require(asset in resources, f"play book {asset} is missing")
        raw = resources[asset]
        book = ip.parse_playbook_resource(raw, asset_id=asset)
        name = book.book_name.encode("ascii")
        _require(0 < len(name) < 12 and name not in seen, "missing or ambiguous native book identity")
        seen.add(name)
        body = raw[32:]
        plays = [_choose(body, play.index) for play in book.plays]
        pair_plays = [i for i, (flags, _, _) in enumerate(plays) if (flags >> 6) & 7 != 1]
        pair_forms = [f.index for f in book.formations if not 4 <= lib.formation_record(body, f.index).type_code <= 7]
        first = len(links) // LINK.size
        used, evidence, ambiguous = set(), [], []
        for form in book.formations:
            category = lib.formation_category(body, form.index)
            if category >= len(book.categories):
                continue
            codes = lib.category_positions(body, category)
            if not lib.is_offense_category(codes):
                continue
            for p in sorted({link.play_index for link in form.play_links}):
                if book.book_name in left_out:
                    break
                _, carried, exact_program = plays[p]
                receivers = sorted(s for s in carried if (codes[s] & 31) == WR_CODE)
                if not receivers:
                    continue
                if len(receivers) != 1:
                    ambiguous.append([form.index, p, receivers])
                    continue
                slot = receivers[0]
                p2 = pair_plays.index(p) if p in pair_plays else 0xFFFF
                f2 = pair_forms.index(form.index) if form.index in pair_forms else 0xFF
                off = ip.CATEGORY_BASE + category * ip.CATEGORY_SIZE
                links.extend(LINK.pack(p, p2, form.index, f2, slot, 0, intern(exact_program),
                                       intern(body[off + 4:off + 16])))
                used.add(p)
                evidence.append([form.index, p, slot])
        books.extend(BOOK_RECORD.pack(name, first, len(links) // LINK.size - first))
        rows.append(dict(asset=int(asset), name=book.book_name, plays=len(plays), compiled_plays=len(used),
                         eligible_links=evidence, ambiguous=ambiguous,
                         source_sha256=hashlib.sha256(raw).hexdigest()))
    ro = bytes(books + links + blobs + struct.pack("<I", pair_address))
    offsets = dict(book_rows=0, links=len(books), blobs=len(books) + len(links), pair_info=len(ro) - 4)
    if offsets["pair_info"] % 4:
        pad = b"\0" * (-offsets["pair_info"] % 4)
        ro = ro[:-4] + pad + ro[-4:]
        offsets["pair_info"] += len(pad)
    ro += bytes(-len(ro) % 16)
    return ro, offsets, rows


# When a disc's books hold more gadget links than the reserved table holds, whole books are left out in this order
# (their gadget plays keep the game's own receivers): the shared books no club plays by default first, then the
# clubs from the last book. The released books fill the 12,800 bytes exactly.
LEAVE_OUT_ORDER = ("reference", "Editor", "PRACTICE", "WCO", "GEN")


def fit_table(resources: Mapping[str, bytes], pair_address: int) -> tuple[bytes, dict[str, int], list[dict], list[str]]:
    """``compile_table`` within the reserved 12,800 bytes, leaving out whole books (``LEAVE_OUT_ORDER``, then clubs
    from the last) until it fits. Returns (table, offsets, rows, left-out book names)."""
    left: list[str] = []
    table, offsets, rows = compile_table(resources, pair_address)
    order = list(LEAVE_OUT_ORDER) + [r["name"] for r in reversed(rows) if r["name"] not in LEAVE_OUT_ORDER]
    while len(table) > TABLE_SIZE:
        _require(order, "the gadget table cannot fit its reserved bytes")
        name = order.pop(0)
        if not any(r["name"] == name and r["eligible_links"] for r in rows):
            continue
        left.append(name)
        table, offsets, _ = compile_table(resources, pair_address, left_out=tuple(left))
    return table, offsets, rows, left


def code_for(offsets: Mapping[str, int], native_gate: int) -> bytes:
    """The 2,048-byte code allocation for a table layout and gate (the template with its five fields moved)."""
    values = {"native_gate": native_gate, **{k: TABLE_VA + v for k, v in offsets.items()}}
    _require(set(values) == set(template.TEMPLATE_VALUES), "unexpected gadget runtime symbols")
    _require(template.CODE_VA == CODE_VA, "the gadget runtime template is linked for another address")
    code = bytearray(template.TEMPLATE)
    for name, value in values.items():
        delta = value - template.TEMPLATE_VALUES[name]
        for at in template.SITES[name]:
            field = int.from_bytes(code[at:at + 4], "little")
            code[at:at + 4] = ((field + delta) & 0xFFFFFFFF).to_bytes(4, "little")
    _require(len(code) <= CODE_SIZE, "the gadget runtime exceeds its allocation")
    # Zero padding after the runtime, as in the qualified candidate (XBE 7963a1db); nothing jumps there.
    return bytes(code).ljust(CODE_SIZE, b"\0")


def _hooks() -> tuple[tuple[str, int, bytes, bytes], ...]:
    entry = CODE_VA + template.LABELS["scoped_builder"]
    ordinal = CODE_VA + template.LABELS["tapped_ordinal"]
    restore = CODE_VA + template.LABELS["restore_after_store"]
    return (("gadget_builder", BUILDER_SITE, BUILDER_RETAIL, b"\xe8" + struct.pack("<i", entry - BUILDER_SITE - 5)),
            ("gadget_ordinal", ORDINAL_SITE, ORDINAL_RETAIL,
             b"\xe9" + struct.pack("<i", ordinal - ORDINAL_SITE - 5) + b"\x90"),
            ("gadget_restore", STORE_SITE, STORE_RETAIL, b"\xe8" + struct.pack("<i", restore - STORE_SITE - 5)))


def _allocations(payload: bytes) -> dict[str, dict] | None:
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    by_kind = {r["kind"]: r for r in rows}
    _require(len(rows) == 2 and set(by_kind) == {"code", "read_only"}, "incomplete or foreign gadget allocation")
    _require((by_kind["code"]["va"], by_kind["code"]["size"]) == (CODE_VA, CODE_SIZE)
             and (by_kind["read_only"]["va"], by_kind["read_only"]["size"]) == (TABLE_VA, TABLE_SIZE),
             "the gadget allocation is not at its fixed release slot")
    return by_kind


def _installed(payload: bytes) -> dict[str, Any]:
    """What the image holds: hook states, the code and table bytes and the values the code was linked with."""
    image = XbeImage(payload)
    hooks = {}
    for label, va, retail, patched in _hooks():
        got = image.read(va, len(retail))
        hooks[label] = "retail" if got == retail else "applied" if got == patched else "foreign"
    allocation = _allocations(payload)
    code = image.read(CODE_VA, CODE_SIZE) if allocation else None
    table = image.read(TABLE_VA, TABLE_SIZE) if allocation else None
    values = None
    if code is not None and code[:len(template.TEMPLATE)] != b"\xcc" * len(template.TEMPLATE):
        values = {}
        for name, sites in template.SITES.items():
            moves = {(int.from_bytes(code[at:at + 4], "little") - int.from_bytes(template.TEMPLATE[at:at + 4], "little"))
                     & 0xFFFFFFFF for at in sites}
            values[name] = (template.TEMPLATE_VALUES[name] + moves.pop()) & 0xFFFFFFFF if len(moves) == 1 else None
    return dict(image=image, hooks=hooks, allocation=allocation, code=code, table=table, values=values)


def read_settings(payload: bytes, resources: Mapping[str, bytes] | None = None) -> dict[str, Any]:
    """``status``: retail (nothing installed, slots empty or absent), applied (hooks, code and table agree with this
    executable's gate and pair contract, and with ``resources`` when given), stale (installed, but the gate, the pair
    contract or the books changed since; apply refreshes it in place), or foreign."""
    try:
        state = _installed(payload)
        image, hooks, code, table, values = (state[k] for k in ("image", "hooks", "code", "table", "values"))
        if set(hooks.values()) == {"retail"}:
            # Nothing installed: the empty reserved slots (or none). Other owners' code is theirs to check.
            empty = code is None or (code == b"\xcc" * CODE_SIZE and table == bytes(TABLE_SIZE))
            return {"status": "retail" if empty else "foreign", **({} if empty else {"reason": "unhooked gadget code"})}
        if not _guards_ok(image):
            return {"status": "foreign", "reason": "native lineup code differs"}
        if set(hooks.values()) != {"applied"} or code is None or values is None or None in values.values():
            return {"status": "foreign", "reason": "partial or foreign gadget hooks"}
        offsets = {k: values[k] - TABLE_VA for k in ("book_rows", "links", "blobs", "pair_info")}
        if not (offsets["book_rows"] == 0 < offsets["links"] <= offsets["blobs"] <= offsets["pair_info"] < TABLE_SIZE):
            return {"status": "foreign", "reason": "gadget table layout"}
        if code != code_for(offsets, values["native_gate"]):
            return {"status": "foreign", "reason": "gadget code differs"}
        stale = []
        if values["native_gate"] != lineup._gate_target(payload):
            stale.append("gate")
        if struct.unpack_from("<I", table, offsets["pair_info"])[0] != pair.contract_va(payload):
            stale.append("pair")
        settings = {"status": "applied", "native_gate": hex(values["native_gate"]), "offsets": offsets,
                    "table_sha256": hashlib.sha256(table).hexdigest()}
        if resources is not None:
            expected, expected_offsets, _rows, _left = fit_table(resources, pair.contract_va(payload))
            if table != expected.ljust(TABLE_SIZE, b"\0") or expected_offsets != offsets:
                stale.append("books")
        if stale:
            settings.update(status="stale", stale=stale)
        return settings
    except (KeyError, ValueError, IndexError, struct.error) as exc:
        return {"status": "foreign", "reason": str(exc)}


def status(payload: bytes, resources: Mapping[str, bytes] | None = None) -> str:
    return read_settings(payload, resources)["status"]


def preflight(payload: bytes) -> None:
    """Refuse, before a build writes anything, a source this owner could not install on or refresh: foreign gadget
    sites, native lineup code that differs, or (when the gadget slots are not reserved yet) an earlier build whose
    allocations the fixed slots would move."""
    state = read_settings(payload)
    _require(state["status"] in ("retail", "applied", "stale"),
             f"the gadget-play sites on this disc hold unrecognized bytes ({state.get('reason', state['status'])})")
    _require(_guards_ok(XbeImage(payload)), "this executable's native lineup code differs from the game's")
    if not space.is_scaleout(payload) or _allocations(payload) is not None:
        return
    _grown, _special, current = space._validate(payload)
    taken = {(owner, kind) for owner, kind, _size, _align in current}
    missing = [r for r in REQUESTS if (r[0], r[1]) not in taken]
    before = space._scale_allocations(current)
    after = space._scale_allocations(space._requests(list(current) + missing))
    moved = sorted({row["owner"] for row in before if row not in after and row["owner"] != space.DIRECTORY_OWNER})
    _require(not moved, "this disc was built earlier without the gadget slots; adding them now would move code an "
                        f"earlier build placed ({', '.join(moved)}). Rebuild from your original game disc.")


def _write_sites(payload: bytes, sites) -> bytes:
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    image = XbeImage(payload)
    for _label, va, data in sites:
        off = image.offset(va, len(data))
        buf[off:off + len(data)] = data
        touched.add(_section_for_offset(sections, off).index)
    for section in sections:
        if section.index in touched:
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
    return bytes(buf)


def _reserve(payload: bytes) -> bytes:
    _require(space.is_scaleout(payload), "the gadget rule needs the 128 MB standard edition's scale-out executable")
    if _allocations(payload) is None:
        payload, _ = space.extend_scaleout(payload, REQUESTS)
        _allocations(payload)  # refuses unless it landed in the fixed slot
    return payload


def apply(payload: bytes, resources: Mapping[str, bytes]) -> tuple[bytes, dict[str, Any]]:
    """Install (or refresh in place) the gadget rule for the disc's books. Needs the situational lineup owner."""
    before = payload
    current = read_settings(payload, resources)
    _require(current["status"] in ("retail", "stale", "applied"),
             f"the gadget-play sites hold unrecognized bytes ({current.get('reason', current['status'])})")
    table, offsets, rows, left = fit_table(resources, pair.contract_va(payload))
    receipt = {"owner": OWNER, "code_va": hex(CODE_VA), "table_va": hex(TABLE_VA), "table_bytes": len(table),
               "eligible_links": sum(len(r["eligible_links"]) for r in rows if r["name"] not in left),
               "left_out_books": left,
               **({"user_notes": ["Gadget player on gadget plays: the gadget plays of these play books keep their "
                                  "normal receivers (the table is full): " + ", ".join(left) + "."]} if left else {}),
               "books": [{k: r[k] for k in ("asset", "name", "compiled_plays", "eligible_links", "ambiguous")}
                         for r in rows]}
    if current["status"] == "applied":
        return payload, {**receipt, "already_applied": True, "changed_bytes": 0}
    _require(lineup.status(payload) == "applied",
             "the gadget rule needs the SPECIAL situational lineup roles (nfl2k5_lineup_roles) applied first")
    _require(_guards_ok(XbeImage(payload)), "this executable's native lineup code differs from the game's")
    gate = lineup._gate_target(payload)
    payload = _reserve(payload)
    code = code_for(offsets, gate)
    installed = _installed(payload)
    old_code, old_table = installed["code"], installed["table"]
    if old_table != bytes(TABLE_SIZE) and old_table != table.ljust(TABLE_SIZE, b"\0"):
        payload, _ = space.uninstall_read_only(payload, OWNER)
    payload, _ = space.install_code(payload, OWNER, code,
                                    previous=None if old_code in (b"\xcc" * CODE_SIZE, code) else old_code)
    payload, _ = space.install_read_only(payload, OWNER, table.ljust(TABLE_SIZE, b"\0"))
    payload = _write_sites(payload, [(label, va, patched) for label, va, _retail, patched in _hooks()])
    final = read_settings(payload, resources)
    _require(final["status"] == "applied", f"the gadget rule did not verify ({final})")
    _require(lineup.status(payload) == "applied", "the situational lineup owner did not survive the gadget install")
    return payload, {**receipt, "already_applied": False, "refreshed": current["status"] == "stale",
                     "native_gate": hex(gate), "changed_bytes": space.count_differing_bytes(before, payload)}


def remove(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Back to the reserved, empty slots and the retail sites (the allocation stays; nothing moves)."""
    current = read_settings(payload)
    if current["status"] == "retail":
        return payload, {"owner": OWNER, "already_retail": True, "changed_bytes": 0}
    _require(current["status"] in ("applied", "stale"), "the gadget-play sites hold unrecognized bytes")
    before = payload
    payload = _write_sites(payload, [(label, va, retail) for label, va, retail, _patched in _hooks()])
    installed = _installed(payload)
    payload, _ = space.uninstall_read_only(payload, OWNER)
    payload, _ = space.install_code(payload, OWNER, b"\xcc" * CODE_SIZE, previous=installed["code"])
    _require(status(payload) == "retail", "the gadget rule did not come off cleanly")
    return payload, {"owner": OWNER, "already_retail": False, "changed_bytes": space.count_differing_bytes(before, payload)}


__all__ = ["BOOK_ASSETS", "BUILD_CAPTION", "GadgetPlayError", "HELP_TEXT", "OWNER", "REQUESTS", "apply", "code_for",
           "compile_table", "preflight", "read_settings", "remove", "status"]
