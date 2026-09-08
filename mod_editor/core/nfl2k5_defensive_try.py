"""Default-off EXPERIMENTAL / UNWITNESSED defensive try rules, USA Xbox.

Allocate the union of selected owners before applying this or relocated kickoff.
Only named grown RX/RW/RO storage is used. See
ASTRA_DEFENSIVE_TRY_BOXSCORE_REPORT.md for the native proofs and save boundaries.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_draft_ai import _Asm
from .nfl2k5_team_column import COLUMN_LISTS, DESCRIPTOR_VA as TEAM_COLUMN_VA
from .nfl2k5_team_column import status as team_column_status

OWNER = "nfl2k5_defensive_try"
STATS_OWNER = "nfl2k5_defensive_try_stats"
DEFAULT_ENABLED = False
UI_TEXT = (
    "Retail: Defensive possession ends a try. Patch: Allows defensive returns, "
    "two points for a return score and one point for a try safety. "
    "Adds defensive conversion totals to the box score and player season stats. "
    "EXPERIMENTAL / UNWITNESSED. Suspended saves do not retain these game counts."
)
LIMITATIONS = (
    "Owned current-game counters are not serialized by suspended-game saves",
    "Historical team totals follow roster membership; archived per-game franchise box scores are not extended",
    "Offensive-line Player Cards retain their retail absence of a stats sheet",
    "Actual console loading, rendering, CPU running and commentary are unwitnessed",
    "Try penalties, retries, multiple possession changes and period/OT endings need gameplay witnesses",
)
CODE_SIZE = 1440
DATA_SIZE = 1040
STATS_CODE_SIZE, STATS_RO_SIZE = 2048, 4096
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (STATS_OWNER, "code", STATS_CODE_SIZE, 16),
            (STATS_OWNER, "read_only", STATS_RO_SIZE, 16))
STAT_ID, HISTORY_FIELD = 0x4000, 59
LIVE_ROSTERS = (0xB30C4C, 0xB321A0)
LIVE_TEAMS = (0xB30864, 0xB30A58)
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
    "player_stat": (0xCB240, "538bd985db8bc2", "jump"),
    "team_stat": (0xCB2D0, "568bf185f68bc2", "jump"),
    "stats_reset": (0x1ECAF0, "5733c0b942000000", "jump"),
    "season_merge": (0x1336B2, "33c9e8f7b60100", "jump"),
    "card_prepare": (0x320B90, "a14802c900", "jump"),
    "box_count": (0x363690, "b826000000", "jump"),
    "box_label": (0x3636A3, "8b048570d6ae00", "jump"),
    "box_id": (0x3636BA, "8b9668d6ae00", "jump"),
    "box_format": (0x3636CB, "8bb66cd6ae00", "jump"),
    "attempt_commit_a": (0x1EEA1E, "e89dd4ecff", "call"),
    "attempt_commit_b": (0x1EEA2A, "e891d4ecff", "call"),
    "attempt_reader_a": (0x250D2F, "e88cb1e6ff", "call"),
    "attempt_reader_b": (0x250D3B, "e880b1e6ff", "call"),
    "attempt_reader_c": (0x250D51, "e86ab1e6ff", "call"),
    "attempt_reader_d": (0x250D5D, "e85eb1e6ff", "call"),
    "player_points": (0x24FFCB, "8d04475f5e", "jump"),
    "summary_event": (0xEC471, "e8aaf2ffff", "call"),
    "summary_label": (0xEBD35, "8b1485cc05a900", "jump"),
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
    (0xCB240, 23, "a1fd6bbd6e6ca9683c7e1c988206f701187a4c8be9c1e64ad8b561f302bbffad"),
    (0xCB2D0, 23, "f2604b5845f2425741225140bd3617decd811566b204abea9aaad1660b9dc470"),
    (0x1ECAF0, 24, "042acb9eb6f5a1507f53bb270945921fec14264ef392c882c684c30323fbdf2f"),
    (0x1336B2, 23, "e844581d34b4de63adfdaba10904f71d37a29274062361a851a117954ea1f0eb"),
    (0x320B90, 21, "a20b3cb3dd15729e5e878307a71652424bffae7d6f96f39cc765c6ca781eb31e"),
    (0x363690, 21, "3ea096f5959d579267e7e99fae434c888eb17576e1684c9b9bdfd81500485914"),
    (0x3636A3, 23, "cedde0e4733478a2e1e05a482bcb6612edba3e483d445604622cd5311cc41078"),
    (0x3636BA, 22, "957b367b1d74603e5b645576cc702602a5e1025f2ee63f61c54624b67f30df92"),
    (0x3636CB, 22, "27016d3a394d55f833a5658683dc56eaf0b0d0bace54911aa4d97ab38ca80ced"),
    (0x14E7E0, 3216, "c7020202dfbce2c004a16190ced287ea822452a41931bd7d55f5a964dc5e8b00"),
    (0xBBA60, 152, "e7f1a716e1450c8698e7c735724dce87c532f60dd97f865dbb34e3e0882eb8e2"),
    (0xCA810, 94, "ad20d98bfaa4ba2e38fa5dc50f923699110bfea6d7b452049272f46d1118fdc6"),
    (0xA8A510, 5124, "a85fdcb83fc27ac63ad3ede82f9e4d6c0f92162239e00b3cea8f79c144de0c8e"),
    (0x4FC528, 716, "cb7e73a38ccadd8ad6805a8009e65b4427be9e0a308f728714c5d8537e6d682d"),
    (0xAA26C0, 348, "d922f19c1920a5b4af3f226a1c0eaab5474cd31c86266639079d0e55944dbff4"),
    (0xAED668, 456, "88919c3285eb4b61c1d67fd7d0dc290bd8e4e604b395478eb3c174c874a09c42"),
    (0x5350D0, 176, "c033d898079b064813d4506be329612800743fc76b739894f3eed41a3eca6a8a"),
    (0x535180, 156, "60051b408e81e07b097fe82fe1592f20b1a81f2d673b4cf9e671392fc8375f16"),
    (0x535258, 156, "60051b408e81e07b097fe82fe1592f20b1a81f2d673b4cf9e671392fc8375f16"),
    (0x535320, 156, "60051b408e81e07b097fe82fe1592f20b1a81f2d673b4cf9e671392fc8375f16"),
    (0x5353E8, 156, "60051b408e81e07b097fe82fe1592f20b1a81f2d673b4cf9e671392fc8375f16"),
    (0x5354A8, 156, "60051b408e81e07b097fe82fe1592f20b1a81f2d673b4cf9e671392fc8375f16"),
    (0x535580, 156, "60051b408e81e07b097fe82fe1592f20b1a81f2d673b4cf9e671392fc8375f16"),
    (0x1EEA16, 70, "0f1431e5a1616e8a2ee4ce029f0965ecb6096a4149eee211953cfb28a31ee4f5"),
    (0x250D10, 116, "450ec1f32c9502db741d5aa1cfefbae6dd44667039f7db5a04d6d1bdbeb5f7ed"),
    (0x24FFCB, 16, "c03d984e043028a27d8e67dd29c8f38a17e6c2aa072fd197cf6666a8c025a208"),
    (0xEC465, 41, "2809d60ee52aeef7acd4cb610e470d2190102070d732ec1918d21eae1a60bd9a"),
    (0xEBD30, 24, "2925117976a80ffade9f60a853296bab0af3af672a88de90cf309b84625bde38"),
    (0xEB720, 303, "fcd8200eeb76182cf6abdf8c342271e31b3c6dba719316d2384e6f43290f60da"),
    (0xA905CC, 60, "c6496f9db34bcd6c34c44793b650d48efed2d1d87f35e5854398c8875e6d6ed8"),
    (0x53572C, 4, "a8699fdcbd3c12df436e42d19a30b5a715e9be4ec81954c3bd5f40262b37e86e"),
    (0x53582C, 4, "179ed24bf64321305e652a764500e7c0a916830061649b7f456fe4b3e91ac183"),
    (0x53592C, 4, "8bff954f57fbc772ca0e5289e2c7b3154fafc0117cf70af08c1590b380263523"),
    (0x535A2C, 4, "62674a813042a090f1d8a22ded89340fe28029194dfcca52f8dd231b1a2cafd6"),
    (0x535B2C, 4, "809c68f161b1a25d719ed32de8440a6afcbba4775a6fd0190f0f7fbe76a7613c"),
    (0x535C2C, 4, "e3258d72080e18e670b9b0a604befad4654838bc61d00a1a1895403f5382b348"),
)


def _u(value):
    return struct.pack("<I", value).hex()


def stat_tables(payload, ro_va):
    """Clone native definitions into immutable owned storage, including terminators.

    Both card variants are installed. The entry hook selects the variant from
    the actual TEAM-column hook at runtime, so either installation order works.
    No pointer list is appended over the next retail structure.
    """
    out = bytearray(_read(payload, 0xAED668, 38 * 12))
    out.extend(struct.pack("<3I", STAT_ID, 0, ro_va + 480))
    out.extend(bytes(480 - len(out)))
    out.extend("Defensive 2pt Conversions\0".encode("utf-16-le"))
    short = ro_va + len(out)
    out.extend("D2PT\0".encode("utf-16-le"))
    out.extend(bytes((-len(out)) % 16))
    descriptor = ro_va + len(out)
    column = bytearray(_read(payload, 0x5350D0, 0xB0))
    struct.pack_into("<I", column, 0x70, short)
    struct.pack_into("<I", column, 0x88, ro_va + 480)
    # Both native card callbacks subtract EA for ids greater than E9.
    struct.pack_into("<I", column, 0xA0, STAT_ID + 0xEA)
    out.extend(column)
    lists = []
    for with_team in (False, True):
        variant = []
        for _, va, pointers in COLUMN_LISTS:
            out.extend(bytes((-len(out)) % 4))
            variant.append(ro_va + len(out))
            out.extend(_read(payload, va, 0x9C))
            columns = pointers[:1] + ((TEAM_COLUMN_VA,) if with_team else ()) + pointers[1:] + (descriptor, 0)
            out.extend(struct.pack("<" + "I" * len(columns), *columns))
        lists.append(variant)
    space._require(len(out) <= 3800, "defensive card table capacity exceeded")
    out.extend(bytes(3800 - len(out)))
    out.extend("DEFENSIVE 2PT RETURN\0".encode("utf-16-le"))
    out.extend(bytes(3864 - len(out)))
    out.extend("SAFETY ON TRY (+1)\0".encode("utf-16-le"))
    space._require(len(out) <= STATS_RO_SIZE, "defensive stat table capacity exceeded")
    return bytes(out).ljust(STATS_RO_SIZE, b"\0"), lists


def stats_code_for(code_va, data_va, ro_va, lists):
    """Native integer readers and commit hooks; x87 is used only for float ABI.

    256 u16 counters use native BBAA0 player ids. The high bit marks a successful
    season merge. 128 u32 replacement records carry absolute drive identity and
    actor id; ring reuse retains earlier counts, while replay replaces a try.
    """
    a = _Asm(code_va)
    a.label("history_clear")
    a.b("60 a10038e500 8bd0 c1e008 25ffffff7f 83e27f 8b0c95" + _u(data_va + 512))
    a.b("8bd9 81e300ffff7f 3bd8")
    a.j8("75", "clear_store")
    a.b("0fb6c9 83f902")
    a.j8("72", "clear_store")
    a.b("6681244d" + _u(data_va) + "ff7f")
    a.b("66833c4d" + _u(data_va) + "00")
    a.j8("74", "clear_store")
    a.b("66ff0c4d" + _u(data_va))
    a.label("clear_store")
    a.b("837e4003")
    a.j8("74", "clear_kick")
    a.b("0d00000080")  # original play was a two-point attempt, even if it failed
    a.label("clear_kick")
    a.b("890495" + _u(data_va + 512) + "61 c3")

    a.label("history_credit")
    a.b("60 8b8e5c030000 85c9")
    a.j8("74", "credit_done")
    a.b("8b493c")
    a.j32("e8", "player_id")
    a.b("85c0")
    a.j8("74", "credit_done")
    a.b("8b150038e500 83e27f 090495" + _u(data_va + 512))
    a.b("66812445" + _u(data_va) + "ff7f 66813c45" + _u(data_va) + "ff7f")
    a.j8("74", "credit_done")
    a.b("66ff0445" + _u(data_va))
    a.label("credit_done")
    a.b("61 c3")

    # Validate the full pointer, not only BBAA0's truncating byte return.
    a.label("player_id")
    a.b("56 8bf1 8d86" + _u((-LIVE_ROSTERS[0]) & 0xFFFFFFFF) + "3da82a0000")
    a.j8("73", "id_zero")
    a.call(0xBBAA0)
    a.b("0fb6c0 83f802")
    a.j8("72", "id_zero")
    a.b("50 8bc8")
    a.call(0xBBA60)
    a.b("59 3bc6")
    a.j8("75", "id_zero")
    a.b("8bc1 5e c3")
    a.label("id_zero")
    a.b("33c0 5e c3")
    a.label("live_count")
    a.j32("e8", "player_id")
    a.b("85c0")
    a.j8("74", "live_done")
    a.b("0fb70445" + _u(data_va))
    a.label("live_done")
    a.b("c3")

    # Shared integer player value. Callee-saved registers survive every native
    # lookup. Native CA810 resolves a live roster copy to its franchise record.
    a.label("player_value")
    a.b("53 55 56 57 8bd8 8bf1 33ed 85f6")
    a.j32("0f84", "value_zero")
    a.b("83fb07")
    a.j8("77", "value_history")
    a.j32("e8", "live_count")
    a.b("25ff7f0000")
    a.j32("e9", "value_done")
    a.label("value_history")
    a.b("83fb1a")
    a.j32("0f87", "value_zero")
    a.j32("e8", "player_id")
    a.b("8bfe 85c0")
    a.j8("74", "value_bank")
    a.b("8bce")
    a.j32("e8", "live_count")
    a.b("a900800000")
    a.j8("75", "value_mapped")
    a.b("8be8")
    a.label("value_mapped")
    a.b("8bce")
    a.call(0xCA810)
    a.b("8bf8 85ff")
    a.j8("74", "value_no_history")
    a.label("value_bank")
    a.b("8bcf ba3b000000 83fb0c")
    a.j8("72", "value_current")
    a.b("83eb0b 53")
    a.call(0x14EF20)
    a.j8("eb", "value_done")
    a.label("value_current")
    a.b("83fb0a")
    a.j8("72", "value_total")
    a.call(0x14EF00)
    a.j8("eb", "value_add")
    a.label("value_total")
    a.call(0x14EE60)
    a.label("value_add")
    a.b("f6c301")
    a.j8("74", "value_done")
    a.b("03c5")
    a.j8("eb", "value_done")
    a.label("value_no_history")
    a.b("33c0 83fb0b")
    a.j8("76", "value_add")
    a.label("value_zero")
    a.b("33c0")
    a.label("value_done")
    a.b("5f 5e 5d 5b c3")

    for name in ("player_stat", "team_stat"):
        a.label(name)
        a.b("9c 81fa" + _u(STAT_ID))
        a.j32("0f85", name + "_retail")
        a.b("60 8b442428")
        if name == "player_stat":
            a.j32("e8", "player_value")
        else:
            # Native team roster has an inline player pointer list. Reusing
            # the player reader keeps current/season/career/class semantics.
            a.b("8bf9 8be8 33db 33f6 85ff")
            a.j8("74", "team_done")
            a.label("team_loop")
            a.b("0fb6871c010000 3bf0")
            a.j8("73", "team_done")
            a.b("8b0cb7 8bc5")
            a.j32("e8", "player_value")
            a.b("03d8 46")
            a.j8("eb", "team_loop")
            a.label("team_done")
            a.b("8bc3")
        a.b("8944241c 61 9d 50 db0424 58 c20400")
        a.label(name + "_retail")
        a.b("9d " + HOOKS[name][1])
        a.jmp_abs(HOOKS[name][0] + len(bytes.fromhex(HOOKS[name][1])))

    a.label("stats_reset")
    a.b("9c 60 fc 33c0 bf" + _u(data_va) + " b904010000 f3ab 61 9d")
    a.b(HOOKS["stats_reset"][1])
    a.jmp_abs(0x1ECAF8)

    # Runs inside the existing per-player postgame merge, before class reset.
    # FX state is saved because pool exhaustion may call the progress UI.
    a.label("season_merge")
    a.b("9c 60 81ec10020000 8d44240f 83e0f0 8984240c020000 0fae00 8bcd")
    a.j32("e8", "player_id")
    a.b("8bd8 85db")
    a.j8("74", "merge_done")
    a.b("0fb7345d" + _u(data_va) + "85f6")
    a.j8("74", "merge_done")
    a.b("f7c600800000")
    a.j8("75", "merge_done")
    a.b("8bcf ba3b000000")
    a.call(0x14EF00)
    a.b("03c6 3dff7f0000")
    a.j8("7e", "merge_write")
    a.b("b8ff7f0000")
    a.label("merge_write")
    a.b("50 8bcf ba3b000000")
    a.call(0x14F430)
    a.b("85c0")
    a.j8("74", "merge_done")
    a.b("66810c5d" + _u(data_va) + "0080")
    a.label("merge_done")
    a.b("8b84240c020000 0fae08 81c410020000 61 9d 33c9")
    a.call(0x14EDB0)
    a.jmp_abs(0x1336B9)

    a.label("card_prepare")
    a.b("9c 60 803d1b7c2400e8")
    a.j8("74", "card_with_team")
    for i, va in enumerate(lists[0]):
        a.b("c705" + _u(0x53572C + i * 0x100) + _u(va))
    a.j8("eb", "card_ready")
    a.label("card_with_team")
    for i, va in enumerate(lists[1]):
        a.b("c705" + _u(0x53572C + i * 0x100) + _u(va))
    a.label("card_ready")
    a.b("61 9d " + HOOKS["card_prepare"][1])
    a.jmp_abs(0x320B95)
    a.label("box_count")
    a.b("b827000000 c3")
    for name, op, offset in (("box_label", "8b0485", 8), ("box_id", "8b96", 0), ("box_format", "8bb6", 4)):
        a.label(name)
        a.b(op + _u(ro_va + offset))
        a.jmp_abs(HOOKS[name][0] + len(bytes.fromhex(HOOKS[name][1])))

    for name in ("attempt_commit_a", "attempt_commit_b", "attempt_reader_a", "attempt_reader_b",
                 "attempt_reader_c", "attempt_reader_d"):
        a.label(name)
    a.b("51")
    a.call(0xBBEC0)
    a.b("59 9c 83f805")
    a.j8("72", "attempt_done")
    a.b("50 8bc1 83e07f f70485" + _u(data_va + 512) + "00000080 58")
    a.b("b803000000")
    a.j8("74", "attempt_done")
    a.b("40")
    a.label("attempt_done")
    a.b("9d c3")

    a.label("player_points")
    a.b("8d0447 9c 60 8bce 8bc3")
    a.j32("e8", "player_value")
    a.b("8b54241c 8d0442 8944241c 61 9d 5f 5e")
    a.jmp_abs(0x24FFD0)

    # The native event banner has a separate classifier and label consumer.
    # Extend it with ids 15/16 only on a scored try, retaining all fifteen
    # ordinary labels and the existing period/game-over override at EC4A5.
    a.label("summary_event")
    a.call(0xEB720)
    a.b("9c 60 85db")
    a.j8("78", "event_done")
    a.b("8bcb")
    a.call(0xCCF80)
    a.b("8b08 f7c100000010")
    a.j8("74", "event_done")
    a.b("f6c170")
    a.j8("75", "event_done")
    a.b("c1e907 83e17f 8b0c8d" + _u(DRIVE_RING) + "8bd1 c1ea1d 83fa05")
    a.j8("72", "event_done")
    a.b("8bc1 c1e81a 83e007 83f801")
    a.j8("74", "event_td")
    a.b("83f806")
    a.j8("75", "event_done")
    a.b("81f100002000")
    a.label("event_td")
    a.b("83fa06")
    a.j8("74", "event_beneficiary")
    a.b("81f100002000")
    a.label("event_beneficiary")
    a.b("c1e915 83e101 69c9f4010000 81c1" + _u(LIVE_TEAMS[0]))
    a.b("890d64c2b900 b80f000000 83fa05")
    a.j8("74", "event_result")
    a.b("40")
    a.label("event_result")
    a.b("8944241c")
    a.label("event_done")
    a.b("61 9d c3")
    a.label("summary_label")
    a.b("9c 83f80f")
    a.j8("72", "summary_label_retail")
    a.b("ba" + _u(ro_va + 3800))
    a.j8("74", "summary_label_ready")
    a.b("ba" + _u(ro_va + 3864))
    a.label("summary_label_ready")
    a.b("9d")
    a.jmp_abs(0xEBD3C)
    a.label("summary_label_retail")
    a.b("9d " + HOOKS["summary_label"][1])
    a.jmp_abs(0xEBD3C)
    content = a.assemble()
    space._require(len(content) <= STATS_CODE_SIZE, "defensive stats code capacity exceeded")
    return content.ljust(STATS_CODE_SIZE, b"\xcc"), {k: code_va + v for k, v in a.labels.items()}


def code_for(code_va: int, data_va: int, stat_labels):
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
    a.call(stat_labels["history_clear"])
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
    a.b("8b08 c1e91d 83f905")
    a.j8("75", "history_credited")
    a.call(stat_labels["history_credit"])
    a.label("history_credited")
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

    # The team projection includes every committed try, even after ring wrap.
    # Reading does not increment; history replacement owns the per-player count.
    a.label("stat_commit")
    a.b("9c 60 33db 33ed b9fe000000")
    a.label("stat_loop")
    a.b("0fb7044d" + _u(data_va) + " 25ff7f0000 03d8")
    a.b("0fb7044d" + _u(data_va + 2) + " 25ff7f0000 03e8 83e902")
    a.j8("73", "stat_loop")
    a.b("891d" + _u(data_va + 1024) + " 892d" + _u(data_va + 1028))
    a.b("c705" + _u(data_va + 1032) + "02000000 61 9d 5f5e5d83c428")
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
    return content.ljust(CODE_SIZE, b"\xcc"), {**stat_labels, **{k: code_va + v for k, v in a.labels.items()}}


def _sites(payload):
    owned = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    space._require(set(owned) == {"code", "data"}, "defensive try allocation missing; rebuild with complete owner union")
    for kind, size in (("code", CODE_SIZE), ("data", DATA_SIZE)):
        space._require((owned[kind]["size"], owned[kind]["align"]) == (size, 16), "foreign defensive try allocation")
    return owned["code"], owned["data"]


def _stats_sites(payload):
    owned = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == STATS_OWNER}
    space._require(set(owned) == {"code", "read_only"}, "defensive stats allocation missing; rebuild with complete owner union")
    for kind, size in (("code", STATS_CODE_SIZE), ("read_only", STATS_RO_SIZE)):
        space._require((owned[kind]["size"], owned[kind]["align"]) == (size, 16), "foreign defensive stats allocation")
    return owned["code"], owned["read_only"]


def assembled(payload):
    code, data = _sites(payload)
    stats, ro = _stats_sites(payload)
    tables, lists = stat_tables(payload, ro["va"])
    stats_code, stat_labels = stats_code_for(stats["va"], data["va"], ro["va"], lists)
    main_code, labels = code_for(code["va"], data["va"], stat_labels)
    return main_code, stats_code, tables, labels


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
    space._require(team_column_status(payload) in ("retail", "applied"),
                   "foreign TEAM-column hook; cannot select native card layout")
    labels = None
    code_state = "retail"
    if state == "applied":
        owners = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
        if owners:
            code, data = _sites(payload)
            expected, stats_code, tables, labels = assembled(payload)
            actual = payload[code["raw"]:code["raw"] + code["size"]]
            space._require(actual in (b"\xcc" * CODE_SIZE, expected), "foreign defensive try code")
            code_state = "applied" if actual == expected else "retail"
            stats, ro = _stats_sites(payload)
            for site, expected, empty in ((stats, stats_code, b"\xcc" * STATS_CODE_SIZE),
                                          (ro, tables, bytes(STATS_RO_SIZE))):
                actual = payload[site["raw"]:site["raw"] + site["size"]]
                space._require(actual == (expected if code_state == "applied" else empty),
                               "mixed or foreign defensive stats code/table")
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

    The native box score uses the same player counters. The postgame merge
    stores field 59 in each credited player's normal season stream.
    """
    space._require(status(payload) == "applied", "runtime stats require this exact installed patch")
    _, data = _sites(payload)
    raw = read_memory(data["va"] + 1024, 12)
    space._require(len(raw) == 12, "short defensive conversion tally")
    home, away, version = struct.unpack("<3I", raw)
    space._require(version in (0, 2) and home + away <= 256 * 32767, "foreign defensive conversion tally")
    return {"label": "Defensive two-point conversions", "teams": [home, away],
            "points": [2 * home, 2 * away], "committed": version == 2,
            "scope": "current game", "persistent": True, "history_field": HISTORY_FIELD}


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = _validate(payload)  # all pins and sections before any mutation
    if state == "applied":
        return payload, {"status": "already_applied", "changed_bytes": 0,
                         "experimental": True, "runtime_witnessed": False,
                         "limitations": list(LIMITATIONS)}
    allocated, allocation = space.apply(payload, REQUESTS, scaleout=True) if space.status(payload) == "retail" else (payload, {})
    code, data = _sites(allocated)
    content, stats_code, tables, labels = assembled(allocated)
    installed, code_receipt = space.install_code(allocated, OWNER, content)
    installed, stats_receipt = space.install_code(installed, STATS_OWNER, stats_code)
    installed, table_receipt = space.install_read_only(installed, STATS_OWNER, tables)
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
                        stats_install=stats_receipt, table_install=table_receipt,
                        edits=edits, reservations=space.reservations(result),
                        code_va=hex(code["va"]), data_va=hex(data["va"]))


def main(argv=None):
    """Bounded standalone capability entry point; output creation is exclusive."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("status", "apply"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args(argv)
    if (args.operation == "apply") != (args.output is not None):
        parser.error("apply requires a new output path; status accepts only a source")
    with args.source.open("rb") as stream:
        payload = stream.read(space.SCALE_FILE_SIZE + 1)
    space._require(len(payload) <= space.SCALE_FILE_SIZE, "input exceeds supported XBE size")
    if args.operation == "status":
        result = {"status": status(payload), "experimental": True, "runtime_witnessed": False}
    else:
        payload, result = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
