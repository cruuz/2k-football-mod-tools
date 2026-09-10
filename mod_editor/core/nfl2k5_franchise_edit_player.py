"""EXPERIMENTAL / UNWITNESSED: Edit Player in Franchise Player Contracts.

The Contracts callback (2B83F0, context 2) filters ten 60-byte records into
eight-byte (UTF-16 label, action ID) pairs on its stack. Its existing context-5
arm at 2B8AB6 passes the selected live record to the same 346730 entry used by
Rosters. Append action 10 and point it at that arm. Keep all ten native rows.

Only instruction operands change. The expanded row and dispatch tables use
704 owned RO bytes; no new code, runtime flag, player copy, save field or heap
allocation is installed. The native stack frame and every epilogue grow by
eight bytes, including the selected-index argument offset and zero terminator.

346730 selects the retail real/created-face editor. Entry 346B90 records the
editor depth; Finish 346C50 pops through that depth and Back 346D90 pops one
page. Both restore the saved parent table state through F3430. Coach's Desk,
Front Office and Player Contracts stay beneath the editor. Position uses the
existing Position-row owner, with the native 0..16 cycle and edit-mode template
guard. Like Rosters, edits are immediate; Back is not an undo operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_position_row as position
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_franchise_edit_player"
RO_SIZE = 704
REQUESTS = ((OWNER, "read_only", RO_SIZE, 16),)
RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
MAX_XBE_BYTES = 16 * 1024 * 1024
CONTRACTS_VA = 0x540650
POPUP_VA = 0x2B83F0
ROWS_VA = 0x521340
ROW_SIZE = 0x3C
RETAIL_ROW_COUNT = 10
ROW_COUNT = 11
DISPATCH_OFFSET = ROW_COUNT * ROW_SIZE
EDIT_LABEL_VA = 0xE99098
EDIT_ACTION = 10
EDIT_ARM_VA = 0x2B8AB6
EDIT_ENTRY_VA = 0x346730
CREATED_EDITOR_VA = 0x56F6E0
REAL_EDITOR_VA = 0x56FD70
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail Player Contracts has no Edit Player action. "
    "Patch: adds Edit Player after Assign Jersey Number for the team you coach. "
    "Use the game's roster editor, including Position, appearance and ratings, "
    "then return to Player Contracts. Changes take effect immediately, including "
    "when you press Back. Review the depth chart after changing a position."
)

# label, action, current-team / other-team / free-agent eligibility, followed
# by the ten native phase/retirement predicates. The predicate code stays
# native. Append only; conditional actions and their relative order survive.
RETAIL_ROWS = (
    (0xE99088, 7, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    (0xE99150, 9, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    (0xE9916C, 3, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1),
    (0xE99198, 5, 0, 0, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1),
    (0xE99198, 6, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0),
    (0xE991C0, 4, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0),
    (0xE990B0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    (0xE991F0, 2, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0),
    (0xE99220, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 0, 0),
    (0xE99238, 8, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1),
)
EDIT_ROW = (EDIT_LABEL_VA, EDIT_ACTION, 1, 0, 0, *([1] * 10))
RETAIL_DISPATCH = (0x2B8605, 0x2B8700, 0x2B8778, 0x2B8810, 0x2B8863,
                   0x2B8891, 0x2B8891, 0x2B8ABF, 0x2B890B, 0x2B8754)
ROW_LOADS = (
    (0x2B849F, 8), (0x2B84A7, 12), (0x2B84B6, 16),
    (0x2B84E0, 24), (0x2B84E8, 20), (0x2B84F0, 28),
    (0x2B84F8, 32), (0x2B8500, 36), (0x2B852A, 40),
    (0x2B8536, 44), (0x2B8547, 48), (0x2B854F, 52), (0x2B8557, 56),
)
EPILOGUES = (0x2B869B, 0x2B86BF, 0x2B86F7, 0x2B874B, 0x2B876F,
             0x2B87C7, 0x2B8807, 0x2B885A, 0x2B887E, 0x2B8A41,
             0x2B8A5C, 0x2B8AC3, 0x2B8B5C, 0x2B8B8B, 0x2B8BF7,
             0x2B8C45, 0x2B8CBF)
GUARDS = (
    (0x562810, 0xb0, "3d2831b1e7c1704d12cd85c32973c31a3b56f8e26eba96de755b38918d8c8a5f"),
    (0xF3690, 0x10, "9cbe391adb02db634d91ef6a03a2b02d316d4304f08ac701ff913a7411afbc2a"),
    (0x2B83F0, 0x95C, "200d62a8ab6e5c91dd283bed3c60a8b524c9e0b3f72208f8b88a01e29124b5dc"),
    (0x521340, 0x258, "2cfa21d3a550da75c14e7e176740e0a80b89f39206855bc0f056a1af27ea1ecd"),
    (0x346730, 0x78, "06de1307d3681d254370b3ad6081191355db0000aa56d3e89eb1cfa77db1841c"),
    (0x35F6C0, 0x2D, "40a0b8ebcbc7cd4486646fc45cbe6fc81d4db2d814bc87631b57b668f37d981f"),
    (0x346B90, 0xB2, "a6c8edf94e0f230370aa21d5b2ba47a7ae9893bda499df05c025771acf268edc"),
    (0x346C50, 0x135, "95b8854916829321b25a322e302fca645954d5e8d3f6d7d2dfc27ad0ae6bd255"),
    (0x346D90, 0x57, "2264e84ad5affa97e87e8db02ef81762874a6546520f44d52d9289948a5708b4"),
    (0x346140, 0x14, "41199971811750fbaf766df4295184a6bd8a4b5588de226545b86eab1eec9619"),
    (0x345540, 0x72, "9cc0b189bf77fdffe83cb1c48958a4df76a33eb11857c41606386725e4872955"),
    (0x343460, 0x79A, "484d5eed9b63b4e6a74e9d002ec53c078af2294d902331c30e1322badf2ebad9"),
    (0x343C00, 0x43, "29d030d6a31bd9a0c0e90ed8fa0f7a797ae44015d9df8bb849f65179d469fe47"),
    (0x346840, 0x46, "01bfdb61f3776ac5366689bb4179bbd22acd6aef79b673c64798d8bca55fe252"),
    (0x6E390, 0x63, "a7d71ca2d920861e3d0eb3da9eb1f9ff8a78c25ca6251b250d987c96a257a3e5"),
    (0x6E400, 0x4E, "b1b06012384dd28e0503a365cccea84be942d28775c2ff6a41bc660ee4d85ee1"),
    (0x6E4E0, 0x14A, "99caf0191ed992d21b0f97a695a27cc63d1740ef4ec6483af48a10a211e9242d"),
    (0xF33C0, 0x70, "df1104bd5e2756b2efc16d2fd8d4d26e4f28136600b5d2a049776f61f87a8dc8"),
    (0xF3430, 0x8B, "99e90a25cc56834a51b2a96ad3b05d34d655d91cfee0b8f9cf5e89909a42feb4"),
    (0x540418, 0x264, "6da49f7074cd78739219f4105d30a4e0abf7fd550d56adba6092986be64ae267"),
    (0x56F3A8, 0x364, "d81dacbf154b272309ef646365a1615244d3566f5cfa90239bd3aa9589c0afc6"),
    (0x56FA38, 0x364, "f1a94821c6efc19b00e4845cc02a83f3519d247d05e36bfd7760f24515d5dcf3"),
)


class FranchiseEditPlayerError(ValueError):
    """Unsupported or partially installed Contracts editor patch."""


def require(condition, message):
    if not condition:
        raise FranchiseEditPlayerError(message)


def read_only_bytes():
    rows = b"".join(struct.pack("<15I", *row) for row in (*RETAIL_ROWS, EDIT_ROW))
    return rows + struct.pack("<11I", *RETAIL_DISPATCH, EDIT_ARM_VA)


def sites(ro_va=0):
    def u32(value):
        return struct.pack("<I", value)
    result = [("popup_stack", POPUP_VA, bytes.fromhex("81eca4000000"), bytes.fromhex("81ecac000000")),
              ("selected_index_argument", 0x2B8410, bytes.fromhex("8b8c24b0000000"), bytes.fromhex("8b8c24b8000000")),
              ("popup_clear_with_terminator", 0x2B8449, bytes.fromhex("b916000000"), bytes.fromhex("b918000000")),
              ("popup_row_count", 0x2B85AD, bytes.fromhex("81fd58020000"), bytes.fromhex("81fd94020000")),
              ("popup_action_limit", 0x2B85F5, bytes.fromhex("83f809"), bytes.fromhex("83f80a")),
              ("popup_pair_copy", 0x2B8584, b"\x8d\xb4\x28" + u32(ROWS_VA), b"\x8d\xb4\x28" + u32(ro_va)),
              ("popup_dispatch", 0x2B85FE, b"\xff\x24\x85" + u32(0x2B8D08),
               b"\xff\x24\x85" + u32(ro_va + DISPATCH_OFFSET))]
    result += [(f"popup_predicate_{offset}", va, b"\x8b\x85" + u32(ROWS_VA + offset),
                b"\x8b\x85" + u32(ro_va + offset)) for va, offset in ROW_LOADS]
    result += [(f"popup_stack_return_{i}", va, bytes.fromhex("81c4a4000000"),
                bytes.fromhex("81c4ac000000")) for i, va in enumerate(EPILOGUES)]
    return sorted(result, key=lambda row: row[1])


def allocation(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"])
            == ("read_only", RO_SIZE, 16), "reserve the complete Contracts editor owner union on a clean base")
    return rows[0]


def _recognize(payload):
    layout = space.layout(payload)  # verifies section digests, geometry and seals
    image = XbeImage(payload)
    owned = allocation(payload) if any(a["owner"] == OWNER for a in layout["allocations"]) else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for name, va, before, after in edits:
        got = image.read(va, len(before))
        states.add("retail" if got == before else "applied" if owned and got == after else "foreign")
    if owned:
        content = image.read(owned["va"], RO_SIZE)
        states.add("retail" if content == bytes(RO_SIZE) else
                   "applied" if content == read_only_bytes() else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign/mixed Contracts popup instructions or tables")
    state = next(iter(states))
    position_state = position.status(payload)
    require(position_state in ("retail", "applied"), "foreign Position row prerequisite")
    require(state != "applied" or position_state == "applied", "Contracts editor is missing its Position row")
    require(image.read(EDIT_LABEL_VA, 24) == "Edit Player\0".encode("utf-16le"), "foreign Edit Player label")

    # The existing MyCareer and playlist owners intercept shared native entry
    # points. Accept only their complete sealed installations, then normalize
    # those exact sites for the prerequisite hashes. Neither depends on us.
    companions = []
    career_sites = ((0x6E390, bytes.fromhex("568bf183be0001000020")),
                    (0x343460, bytes.fromhex("8b15148bcb00")),
                    (0x346D4F, bytes.fromhex("e9fc76d2ff")),
                    (0x346D80, bytes.fromhex("e9cb76d2ff")))
    if any(image.read(va, len(pin)) != pin for va, pin in career_sites):
        from . import nfl2k5_my_career_mode as career
        if career.status(payload) == "applied":
            code, data = career.legacy.allocations(payload)
            companions += career.sites(code["va"], data["va"])
        else:
            require(career.legacy.status(payload) == "applied", "foreign MyCareer editor/stack companion")
            code, data = career.legacy.allocations(payload)
            companions += career.legacy.sites(code["va"], data["va"])
    if image.read(0x6E4E0, 5) != bytes.fromhex("5155578bf9"):
        from . import nfl2k5_music_playlist as playlist
        require(playlist.status(payload) == "applied", "foreign playlist screen dispatcher")
        companions.append(("playlist_dispatch", 0x6E4E0, bytes.fromhex("5155578bf9"), image.read(0x6E4E0, 5)))
    # Pools owns both CAP cycles, also used by this editor's Position row.
    # Validate its complete installation before normalizing the overlapping
    # prerequisite hash (the old hash ends inside the previous callback).
    from . import nfl2k5_position_pools as pools
    cycles = pools.creation_sites()[:2]
    pooled_cycles = any(image.read(s.va, s.size) != s.befores[0] for s in cycles)
    if pooled_cycles:
        require(pools.status(payload) == "applied", "foreign position-pool editor companion")
        require(all(image.read(s.va, s.size) == s.after for s in cycles), "foreign position cycles")
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for _, at, before, after in [*edits, *companions]:
            if va <= at and at + len(before) <= va + size:
                require(bytes(blob[at-va:at-va+len(before)]) in (before, after), "foreign editor prerequisite site")
                blob[at-va:at-va+len(before)] = before
        if pooled_cycles:
            for site in cycles:
                lo, hi = max(va, site.va), min(va + size, site.va + site.size)
                if lo < hi:
                    blob[lo-va:hi-va] = site.befores[0][lo-site.va:hi-site.va]
        require(hashlib.sha256(blob).hexdigest() == digest, f"foreign Contracts editor prerequisite at {va:#x}")
    return state


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    state = _recognize(payload)  # all refusals precede mutation
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  code_bytes=0, rw_bytes=0, ro_bytes=RO_SIZE, stack_growth=8,
                  row_inserted_after="Assign Jersey Number", action_id=EDIT_ACTION,
                  native_editor=hex(EDIT_ENTRY_VA), position_row=True)
    if state == "applied":
        return payload, dict(common, already_applied=True, changed_bytes=0, edits=[])
    if space.status(payload) == "retail":
        result, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        allocation(payload)  # missing union reservation refuses before writes
        result, allocation_receipt = payload, {}
    result, dependency = position.apply(result)
    owned = allocation(result)
    result, _ = space.install_read_only(result, OWNER, read_only_bytes())
    result, patch = rdata.apply(result, sites(owned["va"]), OWNER)
    require(status(result) == "applied", "Contracts editor postcondition failed")
    return result, dict(common, already_applied=False, allocation=allocation_receipt,
        dependencies={"nfl2k5_position_row": dependency},
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
        file_growth=len(result)-len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
        after_sha256=hashlib.sha256(result).hexdigest(), sections_repinned=patch["sections_repinned"],
        edits=[dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
               for name, va, before, after in sites(owned["va"])] + [
            dict(label="owned_contracts_tables", va=hex(owned["va"]), size=RO_SIZE,
                 before=bytes(RO_SIZE).hex(), after=read_only_bytes().hex())],
        reservations=space.reservations(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    with args.source.open("rb") as stream:
        payload = stream.read(MAX_XBE_BYTES + 1)
    require(len(payload) <= MAX_XBE_BYTES, "choose default.xbe, at most 16 MiB")
    if args.command == "status":
        found = status(payload)
        print(json.dumps(dict(status=found, owner=OWNER, experimental=True, runtime_witnessed=False)))
        return int(found == "foreign")
    result, receipt = apply(payload)
    created = False
    try:
        with args.output.open("xb") as stream:
            created = True
            stream.write(result)
    except BaseException:
        if created:
            args.output.unlink(missing_ok=True)
        raise
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
