"""Default-off EXPERIMENTAL / UNWITNESSED defensive try rules, USA Xbox.

Allocate the union of selected owners before applying this or relocated kickoff.
Only named grown RX/RW storage is used. See ASTRA_DEFENSIVE_TRY_REPORT.md for
the bounded proof and the gameplay/persistence boundary.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_defensive_try"
DEFAULT_ENABLED = False
UI_TEXT = (
    "Retail: Defensive possession ends a try. Patch: Allows defensive returns, "
    "two points for a return score and one point for a try safety. "
    "EXPERIMENTAL / UNWITNESSED. The separate conversion tally is temporary; "
    "a retail box-score row and saved player or season totals are not implemented."
)
LIMITATIONS = (
    "No retail defensive-conversion box-score row or persistent player/season category",
    "Temporary team tally covers only the 128 retained drive records",
    "Actual console loading, rendering, CPU running and commentary are unwitnessed",
    "Try penalties, retries, multiple possession changes and period/OT endings need gameplay witnesses",
)
CODE_SIZE = 1440
DATA_SIZE = 1040
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
PHASE = 0xE602B4
ORIGINAL_TEAM = 0xE60288
DRIVE_RING = 0xE57474
SUBTYPE_RETURN, SUBTYPE_SAFETY_TD, SUBTYPE_SAFETY_DEFENSE = 5, 6, 7

# Each complete instruction span has an independent pin. Small rule branches
# retain their comparisons, so the outgoing flags remain exactly retail's.
BRANCHES = {
    "interception_live": (0xB9BA4, "7527", "eb27"),
    "recovery_live": (0xB9E41, "751e", "eb1e"),
    "blocked_pat_live": (0xB7B51, "750a", "eb0a"),
    "safety_impetus": (0xB7693, "0f84b2000000", "909090909090"),
    "safety_own_end": (0xB76CC, "747d", "9090"),
    "safety_loose_out": (0xB7D86, "0f84b0010000", "909090909090"),
    "safety_possessed_out": (0xB7F06, "7434", "9090"),
}
HOOKS = {
    "descriptor": (0x22EC11, "e83af4ffff", "call"),
    "safety_score": (0x22E330, "8b4e7ce84838e7ff", "jump"),
    "history": (0xCD88A, "8b8e54030000", "jump"),
    "points": (0x250360, "5355568bf28bd9", "jump"),
    "summary_td": (0xD63A9, "e8125bfeff", "call"),
    "summary_def_td": (0xD63CB, "e8f05afeff", "call"),
    "try_text": (0xBD5BE, "83f802754a", "jump"),
    "stat_commit": (0x1EEA96, "5f5e5d83c428", "jump"),
    "cpu_return": (0x2E3786, "e805f3ffff", "call"),
    "blocked_loose_out": (0xB7C36, "0f8443010000", "jump"),
}

# Normalized instruction neighborhoods, hashed from the pinned USA retail XBE.
CONTEXT_PINS = (
    (0xB7687, 34, "0a17890dfe543363511f770c30648c5171a6e35d64e63ebf95c270f5320a3110"),
    (0xB76C0, 30, "73f3e1691df9d64360a7ce180a39f16bbabef2329236d42b494f24099b5f9cf4"),
    (0xB7B45, 30, "c9ddef50cc01a1f004ca8991cada1f29f72746853b3e05109777589d3aa371f4"),
    (0xB7C2A, 34, "187c185a8f553b292d9cf974712cb330865eb0544c8f10125c46c9264142ec66"),
    (0xB7D7A, 34, "351404244b0b1775236c84e1485e230d723791bdef2e7e4b531d97a2d2ef83d3"),
    (0xB7EFA, 30, "29346ccc893375d43651a97b2253b2409614ad559941bfca45f91e237af20a1d"),
    (0xB9B98, 30, "7bf3b5c883b6ef1a79494064ed8e7330d281f34af2bd170c1aacaf41b4938750"),
    (0xB9E35, 30, "86e27b6ae3ccc14061589e0d03a84d100814430c169715a29bcb7165893f0259"),
    (0xBD5B2, 33, "cdd1f91a6b018922a017ed9e2e51119024a05714b5f6e85d315b04cd3b35e527"),
    (0xCD87E, 34, "624f04cbae0181da2c354a72a1e5a687c8cefe0044bf6d1bb4ae3661782ba63e"),
    (0xD639D, 33, "f7e9c526478c302a82f5335d7b57f41c8cbfa92c662ae8682a97058530b25a76"),
    (0xD63BF, 33, "a4edc5b34f3c4880479caa3ae403f5dd1ca2fdc8904304b3a84ea54c38287997"),
    (0x1EEA8A, 34, "c040644b53a8a7b180622d4580b6dec1ceb181f40afe656eba0d365b353b7c99"),
    (0x22E324, 36, "034d2afc4744a08941f50496956247790341114c199a05f74206c0e4bbb09c23"),
    (0x22EC05, 33, "5cc7119f94b6811ee8dfbc404d0dde28a92877a26da15148dd7578f8bf71a37b"),
    (0x250354, 35, "257fb608b8c1645b099ca38be4c1e791fadabbdbf606c0909b7e41282f881eb4"),
    (0x2E377A, 33, "5d087f58620e8a17a19bbf66e8c33d5fb552781fce7be54ddbfb51574091189b"),
    (0x2EE110, 221, "19b82796deb364cf8d4494778f15e01e8f6dc3b2d43e1bd1dddf9a457a93c72b"),
    (0x2E2A90, 192, "f891568b0cb9ab3d657d0facdec3aa024bf85949035531a011ad509751141c21"),
    (0x22DFF0, 23, "f82fd87f73fdcc917872fb80449f00eb5a3aefa9b520f7aa044f7b9e56b066cf"),
    (0x22E030, 20, "533a9abb199d5edd8fd0c2f4f5e95323fbf30bb9d35ac0b9c7a211f3e4407ee9"),
)


def _u(value):
    return struct.pack("<I", value).hex()


def code_for(code_va: int, data_va: int):
    """Assemble position-dependent stubs; no runtime assembler dependency."""
    a = _Asm(code_va)
    # Original builder is balanced and does not change PHASE. Only the extra
    # failed-try builder needs a save: all GPRs, EFLAGS and the full x87 image.
    # Neither extra builder nor this wrapper uses SSE, and it aligns itself.
    a.label("descriptor")
    a.call(0x22E050)
    a.b("9c 60 833d" + _u(PHASE) + "03")
    a.j8("75", "descriptor_done")
    a.b("83ec6c dd3424 8bce")  # fnsave [esp]; ecx=record
    a.call(0x22E250)            # phase/team/spot only; retains score and actor
    a.b("dd2424 83c46c")       # frstor [esp]
    a.label("descriptor_done")
    a.b("61 9d c3")

    # Safety event 2 remains distinct from a made PAT. Its phase-3 dispatch
    # awards one and returns to the record applier, never the safety free kick.
    a.label("safety_score")
    a.b("9c 833d" + _u(PHASE) + "03")
    a.j8("75", "ordinary_safety")
    a.b("60 8b467c 8b4008 ff00 61 9d")
    a.jmp_abs(0xE9500)
    a.label("ordinary_safety")
    a.b("9d 8b4e7c")
    a.call(0xA1B80)
    a.jmp_abs(0x22E338)

    # Called only by the phase-3 arm of the committed snapshot writer.
    # EAX=packed drive pointer, ESI=snapshot, EBP=play number. Snapshot +358
    # is the scoring team and +35c the actor (the reverse of descriptor order).
    a.label("history")
    a.b("8b8e54030000 9c 60")
    a.b("8b18 c1eb1a 83e307 83fb01")
    a.j8("74", "history_td")
    a.b("83fb06")
    a.j32("0f85", "history_retail")
    a.label("history_td")
    a.b("8b18 c1eb15 83e301 8b9658030000 81fa20fce500 0f95c2 0fb6d2")
    # BL=drive team; DL=scoring team. Outcome 6 reverses touchdown beneficiary.
    a.b("8b38 c1ef1a 83e707 83ff06")
    a.j8("75", "history_beneficiary")
    a.b("83f301")
    a.label("history_beneficiary")
    a.b("83f905")
    a.j8("75", "history_safety")
    a.b("3bda")
    a.j32("0f84", "history_retail")
    a.b("b905000000")
    a.j8("eb", "history_store")
    a.label("history_safety")
    a.b("83f902")
    a.j32("0f85", "history_retail")
    a.b("b906000000 3bda")
    a.j8("74", "history_store")
    a.b("41")
    a.label("history_store")
    a.b("8b157476e500 894a1c 8b10 81e2ffffff1f c1e11d 0bd1 8910")
    # Sidecar is a per-drive replacement record, not an additive counter.
    # Replays overwrite; ring wrap replaces; pointers are current-game only.
    a.b("8b8e58030000 8b965c030000 2d" + _u(DRIVE_RING))
    a.b("898c00" + _u(data_va) + " 899400" + _u(data_va + 4))
    a.b("61 9d")
    a.jmp_abs(0xCD909)
    a.label("history_retail")
    a.b("61 9d")
    a.jmp_abs(0xCD890)

    # Custom subtypes on TD outcomes are split across the two beneficiaries.
    # The old reader still handles every retail subtype and non-TD outcome.
    a.label("points")
    a.b("9c 60 85d2")
    a.j8("78", "points_retail")
    a.b("83e27f 8b1495" + _u(DRIVE_RING) + " 8bfa c1ef1d 83ff05")
    a.j8("72", "points_retail")
    a.b("8bda c1eb1a 83e307 83fb01")
    a.j8("74", "points_td")
    a.b("83fb06")
    a.j8("75", "points_retail")
    a.label("points_td")
    a.b("c1ea15 83e201 83fb06")
    a.j8("75", "points_team")
    a.b("83f201")
    a.label("points_team")
    a.b("33c0 3bd1")
    a.j8("75", "points_other")
    a.b("b806000000 83ff06")
    a.j8("75", "points_done")
    a.b("40")
    a.j8("eb", "points_done")
    a.label("points_other")
    a.b("83ff06")
    a.j8("74", "points_done")
    a.b("40 83ff05")
    a.j8("75", "points_done")
    a.b("40")
    a.label("points_done")
    a.b("8944241c 61 9d c3")
    a.label("points_retail")
    a.b("61 9d 5355568bf28bd9")
    a.jmp_abs(0x250367)

    # D62E0 has another independent pair of score totals. Its ESI/EDI pointers
    # already account for requested team. The two entry points swap roles.
    for name, other in (("summary_td", "07"), ("summary_def_td", "06")):
        a.label(name)
        a.call(0xBBEC0)
        a.b("9c 83f805")
        a.j8("72", name + "_done")
        a.b("83f806")
        a.j8("74", name + "_one")
        a.b("ff" + other + " 83f805")
        a.j8("75", name + "_zero")
        a.b("ff" + other)
        a.label(name + "_zero")
        a.b("33c0")
        a.j8("eb", name + "_done")
        a.label(name + "_one")
        a.b("b801000000")
        a.label(name + "_done")
        a.b("9d c3")

    # Existing UTF-16 suffix appender, after the play event's scoring/try
    # guards. Strings are immutable in the code allocation, never written.
    a.label("try_text")
    a.b("9c 83f805")
    a.j8("72", "text_retail")
    a.b("ba" + _u(code_va + 1300) + " 83f805")
    a.j8("74", "text_append")
    a.b("ba" + _u(code_va + 1364))
    a.label("text_append")
    a.b("9d")
    a.jmp_abs(0xBD606)
    a.label("text_retail")
    a.b("9d 83f802")
    a.j32("0f85", "text_no_score")
    a.jmp_abs(0xBD5C3)
    a.label("text_no_score")
    a.jmp_abs(0xBD60D)

    # Rebuild a separate current-game defensive-conversion category at the
    # actual stat commit, never during descriptor previews. Count replacement
    # history records, so stat rebuild/retry cannot add the same conversion.
    a.label("stat_commit")
    a.b("9c 60 33db 33ed 8b0d0038e500 41 85c9")
    a.j8("7e", "stat_store")
    a.b("81f980000000")
    a.j8("76", "stat_loop")
    a.b("b980000000")
    a.label("stat_loop")
    a.b("8b148d" + _u(DRIVE_RING - 4) + " 8bc2 c1e81d 83f805")
    a.j8("75", "stat_next")
    a.b("8bc2 c1e81a 83e007 83f801")
    a.j8("74", "stat_td")
    a.b("83f806")
    a.j8("75", "stat_next")
    a.b("81f200002000")  # flip TD beneficiary for outcome 6
    a.label("stat_td")
    a.b("f7c200002000")
    a.j8("75", "stat_team_zero")
    a.b("45")           # drive TD team zero => defending team one
    a.j8("eb", "stat_next")
    a.label("stat_team_zero")
    a.b("43")
    a.label("stat_next")
    a.b("49")
    a.j8("75", "stat_loop")
    a.label("stat_store")
    a.b("891d" + _u(data_va + 1024) + " 892d" + _u(data_va + 1028))
    a.b("c705" + _u(data_va + 1032) + "01000000 61 9d 5f5e5d83c428")
    a.jmp_abs(0x1EEA9C)

    # The second carrier transition can choose the end-zone wait plan even
    # on a try (2E2A90). Bypass that choice only for a live CPU defender holder.
    # ESI is the player; zero selects the existing 2E2DA0 return controller,
    # whose heading follows the team's field-direction object.
    a.label("cpu_return")
    a.b("9c 51 833d" + _u(PHASE) + "03")
    a.j8("75", "cpu_retail")
    a.b("833db802e6000e")
    a.j8("75", "cpu_retail")
    a.b("8b4e38 3b0d" + _u(ORIGINAL_TEAM))
    a.j8("74", "cpu_retail")
    a.b("8b4e0c 8339ff")
    a.j8("75", "cpu_retail")
    a.b("8b0d00fce500 85c9")
    a.j8("74", "cpu_retail")
    a.b("3931")
    a.j8("75", "cpu_retail")
    a.b("59 b800000000 9d c3")
    a.label("cpu_retail")
    a.b("59 9d")
    a.jmp_abs(0x2E2A90)

    # A blocked PAT can roll out of the kicking team's own end zone before
    # anyone recovers. Retail's still-a-kick arm skips loose-ball safety.
    # Admit only a phase-3 placekick first touched by the other team; normal
    # missed PATs and all punt/kickoff handling retain the displaced branch.
    a.label("blocked_loose_out")
    a.j32("0f84", "blocked_out_loose")  # original TEST ctx.kick == 0
    a.b("9c 51 833d" + _u(PHASE) + "03")
    a.j8("75", "blocked_out_retail")
    a.b("83b8d001000000")
    a.j8("74", "blocked_out_retail")
    a.b("8b8894010000 85c9")
    a.j8("74", "blocked_out_retail")
    a.b("8b4938 3b0d" + _u(ORIGINAL_TEAM))
    a.j8("74", "blocked_out_retail")
    a.b("59 9d")
    a.label("blocked_out_loose")
    a.jmp_abs(0xB7D7F)
    a.label("blocked_out_retail")
    a.b("59 9d")
    a.jmp_abs(0xB7C3C)
    content = a.assemble()
    space._require(len(content) <= 1300, "defensive try code capacity exceeded")
    text_return = ". Defensive two-point return".encode("utf-16-le") + b"\0\0"
    text_safety = ". Safety on try (+1)".encode("utf-16-le") + b"\0\0"
    content = content.ljust(1300, b"\xcc") + text_return
    content = content.ljust(1364, b"\xcc") + text_safety
    return content.ljust(CODE_SIZE, b"\xcc"), {k: code_va + v for k, v in a.labels.items()}


def _sites(payload):
    owned = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    space._require(set(owned) == {"code", "data"}, "defensive try allocation missing; rebuild with complete owner union")
    for kind, size in (("code", CODE_SIZE), ("data", DATA_SIZE)):
        space._require((owned[kind]["size"], owned[kind]["align"]) == (size, 16), "foreign defensive try allocation")
    return owned["code"], owned["data"]


def _hook_bytes(name, labels):
    va, before, kind = HOOKS[name]
    opcode = b"\xe8" if kind == "call" else b"\xe9"
    return (opcode + struct.pack("<i", labels[name] - va - 5)).ljust(len(bytes.fromhex(before)), b"\x90")


def _read(payload, va, size):
    for s in _sections(payload):
        if s.virtual_address <= va and va + size <= s.virtual_address + s.raw_size:
            off = s.raw_offset + va - s.virtual_address
            return payload[off:off + size]
    raise ValueError("unmapped defensive try pin")


def _validate(payload):
    state = space.status(payload)
    space._require(state != "foreign", "foreign XBE geometry, allocation or section digest")
    labels = None
    code_state = "retail"
    if state == "applied":
        owners = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
        if owners:
            code, data = _sites(payload)
            expected, labels = code_for(code["va"], data["va"])
            actual = payload[code["raw"]:code["raw"] + code["size"]]
            space._require(actual in (b"\xcc" * CODE_SIZE, expected), "foreign defensive try code")
            code_state = "applied" if actual == expected else "retail"
    states = []
    for name, (va, before, after) in BRANCHES.items():
        before, after = bytes.fromhex(before), bytes.fromhex(after)
        actual = _read(payload, va, len(before))
        space._require(actual in (before, after), "foreign try branch: " + name)
        states.append("retail" if actual == before else "applied")
    for name, (va, before, _) in HOOKS.items():
        before = bytes.fromhex(before)
        actual = _read(payload, va, len(before))
        if actual == before:
            states.append("retail")
        else:
            space._require(labels is not None and actual == _hook_bytes(name, labels), "foreign try hook: " + name)
            states.append("applied")
    space._require(set(states) == {code_state}, "mixed defensive try hooks/code; rebuild from base")
    for start, size, digest in CONTEXT_PINS:
        context = bytearray(_read(payload, start, size))
        for va, before, _ in {**BRANCHES, **HOOKS}.values():
            original = bytes.fromhex(before)
            lo, hi = max(start, va), min(start + size, va + len(original))
            if lo < hi:
                context[lo-start:hi-start] = original[lo-va:hi-va]
        space._require(hashlib.sha256(context).hexdigest() == digest, "foreign try instruction context")
    return code_state


def status(payload: bytes) -> str:
    try:
        return _validate(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError):
        return "foreign"


def read_runtime_stats(payload: bytes, read_memory) -> dict:
    """Read the owned current-game tally from a supplied memory reader.

    Diagnostic/export contract only; this does not add a retail box-score row
    or a persistent season-stat column. On-disk data is intentionally zero.
    """
    space._require(status(payload) == "applied", "runtime stats require this exact installed patch")
    _, data = _sites(payload)
    raw = read_memory(data["va"] + 1024, 12)
    space._require(len(raw) == 12, "short defensive conversion tally")
    home, away, version = struct.unpack("<3I", raw)
    space._require(version in (0, 1) and home + away <= 128, "foreign defensive conversion tally")
    return {"label": "Defensive two-point conversions", "teams": [home, away],
            "points": [2 * home, 2 * away], "committed": version == 1,
            "scope": "current game, retained drive history", "persistent": False}


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = _validate(payload)  # all pins and sections before any mutation
    if state == "applied":
        return payload, {"status": "already_applied", "changed_bytes": 0,
                         "experimental": True, "runtime_witnessed": False,
                         "limitations": list(LIMITATIONS)}
    allocated, allocation = space.apply(payload, REQUESTS) if space.status(payload) == "retail" else (payload, {})
    code, data = _sites(allocated)
    content, labels = code_for(code["va"], data["va"])
    installed, code_receipt = space.install_code(allocated, OWNER, content)
    buf = bytearray(installed)
    edits = []
    for name, (va, before, after) in BRANCHES.items():
        after = bytes.fromhex(after)
        buf[va - 0x10000:va - 0x10000 + len(after)] = after
        edits.append(dict(label=name, va=hex(va), size=len(after), before=before, after=after.hex()))
    for name, (va, before, _) in HOOKS.items():
        after = _hook_bytes(name, labels)
        buf[va - 0x10000:va - 0x10000 + len(after)] = after
        edits.append(dict(label=name, va=hex(va), size=len(after), before=before, after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    space._require(status(result) == "applied", "defensive try postcondition failed")
    return result, dict(status="applied", experimental=True, runtime_witnessed=False,
                        limitations=list(LIMITATIONS),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        source_sha256=hashlib.sha256(payload).hexdigest(),
                        result_sha256=hashlib.sha256(result).hexdigest(),
                        allocation=allocation, code_install=code_receipt,
                        edits=edits, reservations=space.reservations(result),
                        code_va=hex(code["va"]), data_va=hex(data["va"]))
