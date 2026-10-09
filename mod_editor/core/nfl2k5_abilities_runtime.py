"""Abilities rules v2. EXPERIMENTAL / UNWITNESSED, every preset off.

Use the shipped seven roster bits. Movement Speed is extended after BOTH
native clamps; base move commands and the native charge meter remain available
to every player by default. Explicit move locks can require stored permissions
and confine the meter to live ball carriers, including CPU carriers. No new
timer, mutable allocation, roster save migration, simulated-game effect, or
extra week is supplied. The editor
authors tiers separately. Five existing move flags gain capped live attribute
bonuses for tiered players. Move locks are opt-in; Speedster permission remains
required by default.

g2 (beta 77): star-only moves. The roster star tag (record word bit 0x0100, the star under a player) plus the
ability tier (Unranked, Star, Superstar, X-Factor) select one of eight access levels from a four-entry table in the
owner (``tier_grants``). The flag reader adds that level's grant bits (0x01..0x10) to the permissions it returns;
they are never stored in a roster (all sixteen bits at record +0x52 are assigned) and never counted against a tier's
flag capacity. Three optional rules put grant bits into the required mask of a command class, so only players whose
level holds them can use it: ``right_stick_stars_only`` (the right stick: lateral flicks, stutter-step and stop-short
flicks, the click hurdle), ``charge_stars_only`` (the charge-up meter of live ball carriers) and
``button_moves_stars_only`` (every other mapped ball-carrier command). All default off; with all off the owner
behaves as in beta 76.5. CPU carriers follow the same rules as human ones. Speedster and the tier bonuses are
unchanged.

Reserve REQUESTS together with every other owner before installing any owner.
The optional off-week is a ZERO-BASED regular-season row (0..17); None means
no off-week. Rebuild from a supported base to change installed configuration.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_abilities_runtime_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_abilities_runtime"
MODEL_VERSION = 2
CODE_SIZE = (len(assembly.CODE) + 15) & -16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUDGET = 1536
assert CODE_SIZE <= BUDGET
_UNSET = object()
SPEEDSTER, RIGHT_STICK, JUKE = 0x20, 0x40, 0x80
SPIN, TRUCK, HURDLE, STIFF_ARM = 0x200, 0x400, 0x800, 0x1000
ABILITY_MASK = 0x1EE0
DEFAULT_LOCKS = {"lock_right_stick": False, "lock_special_moves": False,
                 "lock_speedster": True}
LOCK_MASKS = {"lock_right_stick": RIGHT_STICK,
              "lock_special_moves": JUKE | SPIN | TRUCK | HURDLE | STIFF_ARM,
              "lock_speedster": SPEEDSTER}
# Star access. Grant bits live in the low byte of the permission word the flag reader returns (the record's own
# 0x1F depth-lock bits are masked out there, so these positions are free in the returned word).
GRANT_STICK, GRANT_STOP, GRANT_HURDLE, GRANT_CHARGE, GRANT_BUTTON = 0x01, 0x02, 0x04, 0x08, 0x10
GRANT_MASK = 0x1F
# Access level name -> grant bits. Every starred record also holds GRANT_BUTTON (used only by the optional
# button-moves rule); a level only chooses which right-stick and charge-up powers the star has.
ACCESS_LEVELS = {
    "none": 0,
    "charge": GRANT_CHARGE,
    "flicks": GRANT_STICK,
    "flicks_charge": GRANT_STICK | GRANT_CHARGE,
    "stick": GRANT_STICK | GRANT_STOP,
    "stick_charge": GRANT_STICK | GRANT_STOP | GRANT_CHARGE,
    "stick_hurdle": GRANT_STICK | GRANT_STOP | GRANT_HURDLE,
    "full": GRANT_STICK | GRANT_STOP | GRANT_HURDLE | GRANT_CHARGE,
}
ACCESS_LABELS = {
    "none": "No right-stick moves or charge-ups",
    "charge": "Charge-ups only",
    "flicks": "Stick juke flicks only",
    "flicks_charge": "Stick juke flicks and charge-ups",
    "stick": "Stick flicks, stutter-step and stop short",
    "stick_charge": "Stick flicks, stutter-step, stop short and charge-ups",
    "stick_hurdle": "All stick moves including the hurdle",
    "full": "Everything: all stick moves, hurdle and charge-ups",
}
# One level per class of starred player, indexed by ability tier: 0 Unranked (star tag only), 1 Star, 2 Superstar, 3 X-Factor.
STAR_CLASSES = ("Starred, no ability tier", "Star tier", "Superstar tier", "X-Factor tier")
DEFAULT_STAR_ACCESS = ("flicks_charge", "stick_charge", "full", "full")
DEFAULT_STARS = {"right_stick_stars_only": False, "charge_stars_only": False, "button_moves_stars_only": False,
                 "star_access": DEFAULT_STAR_ACCESS}
# Grant bits each right-stick command needs when the rule is on. The stick-flick numbers come from the game's own
# decoder: 0x24/0x28 up (stutter-step), 0x25/0x29 left and 0x27/0x2B right (jukes), 0x26/0x2A down (stop short);
# 0x1A is the click of the right stick (hurdle).
STICK_GRANTS = {0x1A: GRANT_STICK | GRANT_HURDLE,
                **{c: GRANT_STICK | GRANT_STOP for c in (0x24, 0x26, 0x28, 0x2A)},
                **{c: GRANT_STICK for c in (0x25, 0x27, 0x29, 0x2B)}}
TABLE_FIRST_COMMAND, TABLE_ENTRIES = 0x18, 20     # move_masks holds one word per command 0x18..0x2B
# Effective-attribute table indices differ from on-disc byte order.
EFFECTS = {
    "juke": (1, JUKE, "Agility"),
    "stiff_arm": (2, STIFF_ARM, "Strength"),
    "hurdle": (3, HURDLE, "Jumping"),
    "truck": (12, TRUCK, "Break Tackle"),
    "spin": (18, SPIN, "Pass Rush"),
}
EFFECT_STEP = .02
MOVE_MASKS = {
    0x18: STIFF_ARM, 0x19: STIFF_ARM, 0x1A: HURDLE | RIGHT_STICK,
    0x1B: SPIN, 0x1C: SPIN, 0x1D: JUKE, 0x1E: JUKE, 0x20: JUKE,
    0x21: JUKE, 0x22: JUKE, 0x23: TRUCK,
    **{command: JUKE | RIGHT_STICK for command in range(0x24, 0x2C)},
    0x5C: JUKE, 0x5D: JUKE,
}
# The two "stars only" classes. A command is a right-stick move when its mask holds RIGHT_STICK (the hurdle is the
# right-stick CLICK); the other twelve mapped commands are button moves (face buttons, triggers, bumpers, and the
# CPU/derived juke, spin and stiff-arm commands that never come from the stick).
STICK_COMMANDS = tuple(sorted(c for c, m in MOVE_MASKS.items() if m & RIGHT_STICK))
BUTTON_COMMANDS = tuple(sorted(c for c, m in MOVE_MASKS.items() if not m & RIGHT_STICK))
assert len(STICK_COMMANDS) == 9 and len(BUTTON_COMMANDS) == 12
# Direct call PCs from a byte-granular E8/E9 scan of retail .text. Zero means
# outside the researched five-move contract, so never authorize consumption.
CONSUMERS = {
    0x18D2C6: 0, 0x18DF7C: 0, 0x1E773E: 0, 0x1E7BA2: 0, 0x2319CB: 0,
    0x29089B: 0x290880, 0x291D60: 0, 0x2DBBCC: 0x2DBBC0,
    0x2DC803: 0x2DC7F0, 0x2DCF93: 0x2DCF70, 0x306DF7: 0x306DE0,
    0x308512: 0, 0x30D2C2: 0x30D2A0, 0x30EDA7: 0, 0x31793D: 0,
}
HOOKS = {
    "attribute": (0x17B010, bytes.fromhex("83ec088b4130")),
    "speed": (0x75CC8, bytes.fromhex("e843531000")),
    "decode": (0x15647D, bytes.fromhex("e85eadfcff")),
    "dispatch": (0x18EC6D, bytes.fromhex("e8ce460200")),
    "initialize": (0x1CD550, bytes.fromhex("5356578bf9")),
    "generate": (0x2D43F0, bytes.fromhex("a180ffe500")),
    "ai_ready": (0x2D46D0, bytes.fromhex("8b41108b8890000000")),
    "consume": (0x2D4740, bytes.fromhex("568b7110d94644")),
}
SYMBOLS = {
    "retail_attribute_tail": 0x17B016,
    "retail_attribute": 0x17B010, "retail_decode": 0x1211E0,
    "retail_account": 0x1B3340, "retail_initialize_tail": 0x1CD555,
    "retail_generate_tail": 0x2D43F5, "retail_ai_tail": 0x2D46D9,
    "retail_consume_tail": 0x2D4747,
}
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail ignores stored ability flags. Patch: "
    "base moves and charge work for every player by default. Optional locks "
    "require Speedster for speed above 99, each special move's "
    "ability, and Right-Stick Moves for stick moves. Tiered Juke, Stiff-Arm, "
    "Hurdle, Truck and Spin add 2/4/6 effective points to Agility, Strength, "
    "Jumping, Break Tackle and Pass Rush during live play, capped at 100. "
    "When either move lock is on, the charge meter is limited to live ball "
    "carriers and known move consumers. Turn both move locks off for retail "
    "charge behavior. An optional existing franchise week turns stored "
    "abilities off. Author tiers and abilities on the Rosters Abilities page. "
    "Tiered players with excess stored abilities receive no stored permissions "
    "or bonuses until corrected. Unranked legacy flags retain v1 permissions. "
    "Optional star rules use the roster star tag and the ability tier: "
    "right-stick moves (stick flicks, stutter-step, stop short, the stick-click "
    "hurdle), charge-ups and button moves (spin, truck, stiff-arm, button jukes) "
    "can each be limited to starred players, and each class of star (no tier, "
    "Star, Superstar, X-Factor) chooses which of those powers it has. CPU players "
    "follow the same rules. Speedster and the tier bonuses are unchanged. "
    "No simulated-game effects or guaranteed outcomes."
)


class AbilitiesError(ValueError):
    """Unsupported, mixed, foreign, or differently configured executable."""


def _require(condition, message):
    if not condition:
        raise AbilitiesError(message)


def _week(value):
    _require(value is None or (type(value) is int and 0 <= value <= 17),
             "abilities_off_week must be None or a zero-based regular-season row 0..17")
    return value


def _locks(**values):
    for key, value in values.items():
        _require(key in LOCK_MASKS and type(value) is bool, f"{key} must be Boolean")
    return {key: values.get(key, DEFAULT_LOCKS[key]) for key in LOCK_MASKS}


def _stars(**values):
    for key, value in values.items():
        _require(key in DEFAULT_STARS, f"unknown star rule {key}")
        if key == "star_access":
            _require(isinstance(value, (tuple, list)) and len(value) == 4 and all(v in ACCESS_LEVELS for v in value),
                     "star_access must name one access level for each of the four star classes")
        else:
            _require(type(value) is bool, f"{key} must be Boolean")
    out = {key: values.get(key, DEFAULT_STARS[key]) for key in DEFAULT_STARS}
    out["star_access"] = tuple(out["star_access"])
    return out


def _relocate(blob, code_va, relocations=None):
    symbols = {"code": code_va, **SYMBOLS}
    for offset, kind, symbol, value in (assembly.RELOCATIONS if relocations is None else relocations):
        target = symbols[symbol] + value + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)


def _star_classes(blob, stars):
    """Install the star rules into a relocated template: the 20 command words, the seven descriptor-family masks
    the initializer falls back to, the 0x5C/0x5D juke immediate, the tier grant table and (charge rule) the charge
    gate."""
    labels = assembly.LABELS
    stick, button = stars["right_stick_stars_only"], stars["button_moves_stars_only"]
    table = labels["move_masks"]
    for command, base in MOVE_MASKS.items():
        if TABLE_FIRST_COMMAND <= command < TABLE_FIRST_COMMAND + TABLE_ENTRIES:
            at = table + 2 * (command - TABLE_FIRST_COMMAND)
            word = struct.unpack_from("<H", blob, at)[0]
            _require(word == base, "abilities move table differs from the declared command masks")
            extra = (STICK_GRANTS[command] if stick else 0) if base & RIGHT_STICK else (GRANT_BUTTON if button else 0)
            struct.pack_into("<H", blob, at, word | extra)
    families = labels["families"]
    for index in range(7):
        at = families + 8 * index + 4
        mask = struct.unpack_from("<I", blob, at)[0]
        _require(mask and not mask & GRANT_MASK, "abilities descriptor-family table differs from the template")
        if mask & RIGHT_STICK:
            extra = (GRANT_STICK | (GRANT_HURDLE if mask & HURDLE else 0)) if stick else 0
        else:
            extra = GRANT_BUTTON if button else 0
        struct.pack_into("<I", blob, at, mask | extra)
    at = labels["mask_juke"]
    _require(blob[at] == 0xBF and struct.unpack_from("<I", blob, at + 1)[0] == JUKE,
             "abilities juke mask immediate differs from the template")
    struct.pack_into("<I", blob, at + 1, JUKE | (GRANT_BUTTON if button else 0))
    at = labels["tier_grants"]
    _require(bytes(blob[at:at + 4]) == bytes(4), "abilities tier grant table differs from the template")
    blob[at:at + 4] = bytes(ACCESS_LEVELS[name] | GRANT_BUTTON for name in stars["star_access"])
    if stars["charge_stars_only"]:
        # The retail charge policy is replaced, for live ball carriers only, by "the carrier's access level holds
        # the charge-up grant". Four one-byte/one-immediate edits in maintain(); consume() keeps retail behaviour.
        head = labels["maintain_head"] + 5            # je maintain_yes after unlocked_moves
        _require(blob[head] == 0x74, "abilities maintain head differs from the template")
        blob[head:head + 2] = b"\x90\x90"
        at = labels["maintain_carrier"] + 5           # jnc maintain_clear after carrier: non-carriers keep retail charge
        _require(blob[at] == 0x73, "abilities maintain carrier branch differs from the template")
        displacement = labels["maintain_yes"] - (at + 2)
        _require(0 <= displacement < 128, "abilities maintain layout differs from the template")
        blob[at + 1] = displacement
        at = labels["maintain_test"]                  # test eax, 0x1e80 (any move permission) -> the charge grant
        _require(blob[at] == 0xA9 and struct.unpack_from("<I", blob, at + 1)[0] == 0x1E80,
                 "abilities maintain permission test differs from the template")
        struct.pack_into("<I", blob, at + 1, GRANT_CHARGE)
        at = labels["maintain_state"]                 # jne maintain_yes after the state test: skip the per-move check
        _require(blob[at] == 0x75, "abilities maintain state branch differs from the template")
        blob[at] = 0xEB


def _read_stars(content):
    """The star rules a template-shaped owner carries, or None when its bytes are not this template's."""
    labels = assembly.LABELS
    try:
        words = struct.unpack_from("<%dH" % TABLE_ENTRIES, content, labels["move_masks"])
        grants = content[labels["tier_grants"]:labels["tier_grants"] + 4]
        by_value = {v: k for k, v in ACCESS_LEVELS.items()}
        names = tuple(by_value[g & ~GRANT_BUTTON] for g in grants)
    except (KeyError, struct.error):
        return None
    return {"right_stick_stars_only": bool(words[0x1A - TABLE_FIRST_COMMAND] & GRANT_STICK),
            "charge_stars_only": content[labels["maintain_head"] + 5] == 0x90,
            "button_moves_stars_only": bool(words[0x1B - TABLE_FIRST_COMMAND] & GRANT_BUTTON),
            "star_access": names}


def code_for(code_va, abilities_off_week=None, *, lock_right_stick=False,
             lock_special_moves=False, lock_speedster=True, right_stick_stars_only=False,
             charge_stars_only=False, button_moves_stars_only=False, star_access=DEFAULT_STAR_ACCESS):
    _week(abilities_off_week)
    locks = _locks(lock_right_stick=lock_right_stick,
                   lock_special_moves=lock_special_moves, lock_speedster=lock_speedster)
    stars = _stars(right_stick_stars_only=right_stick_stars_only, charge_stars_only=charge_stars_only,
                   button_moves_stars_only=button_moves_stars_only, star_access=star_access)
    _require(not (stars["charge_stars_only"] and (locks["lock_right_stick"] or locks["lock_special_moves"])),
             "charge_stars_only replaces the charge policy of the two move locks: turn both locks off")
    blob = bytearray(assembly.CODE)
    _relocate(blob, code_va)
    struct.pack_into("<i", blob, assembly.LABELS["config"],
                     -1 if abilities_off_week is None else abilities_off_week)
    struct.pack_into("<I", blob, assembly.LABELS["unlocked_mask"],
                     sum(LOCK_MASKS[key] for key, locked in locks.items() if not locked))
    _star_classes(blob, stars)
    blob.extend(b"\xcc" * (CODE_SIZE - len(blob)))
    return bytes(blob), {name: code_va + offset for name, offset in assembly.LABELS.items()}


# The beta 76.5 / SOFTDRINK v0.5 owner template (what tools/b77/g2_repair.py upgrades). Hooks, tables and every
# function from `carrier` on are byte-identical to the current template (same labels); only the flag reader, the
# 1-byte `permissions`/`unlocked_moves` shift and the new grant table differ, so the repair rewrites just the
# owner's own allocation. LEGACY_V05_SHA256 pins the whole 1344-byte owner of the shipped v0.5 disc.
LEGACY_V05_CODE = bytes.fromhex(
    "31c085c9746183f9ff745c833d00000000ff741f833da076e500027516833da476e50008750da1000000003b05b476e5"
    "0074320fb7415225e01e00005352510fb65153c1ea0674198a923605000089c385db740dfeca78078d4bff21cbebf131"
    "c0595a5bc331c0c3e893ffffff0b0508050000c3a10805000025c01e00003dc01e0000c331f631d28d430183f801763b"
    "8b73108d460183f801762c8b530c8d420183f8017623833db802e6000e751ca100fce5004083f8017611483918750c83"
    "7b1c017506f9c331f631d2f8c38b0283f8ff741a83f80377136bc02c8b8060b9a90083f808740783f80a7402f8c3f9c3"
    "31ff83f95c741683f95d741183e91883f91377080fb73c4d00000000c3bf80000000c385f6741583a690000000fcc746"
    "4400000000c74648000080bf85d27404836218fbc3e83affffff7443e843ffffff733e8b4b3ce81dffffff89c5a94000"
    "0000750525fff7ffffa9801e000074218b869000000083e00383f80175118b0ee87bffffff85ff740821fd39fd7502f9"
    "c3e88dfffffff8c3e8a8ffffffe8f2feffff732de834ffffff73268b4a1ce84dffffff85ff741a8b4b3ce8b9feffff21"
    "f839f8740cc7421c00000000e852ffffffc351ff742408e8fcffffff599c6083ec0cd91c24c7442404a4707d3fe886fe"
    "ffffa92000000074270fb6413683e86483f81b771b83c06489442408db442408d80d04000000d9542404d80c24d91c24"
    "8b042485c078133d0000807f730c3b442404760b8b442404eb0231c0890424d9042483c40c619dc20400e8fcffffff9c"
    "60e842ffffff619dc39c6089cbe836ffffff619d8b410c8b781c89fae9fcffffff9c6089cbe81afeffff7377e85cfeff"
    "ff73708b6c24148b0e83f95d77093b2c8df067ad00742b8b4a1c83f95d77093b2c8df067ad00741abfd0040000b90700"
    "00003b2f740783c708e2f7eb368b7f04eb05e839feffff85ff74288b4b3ce8a5fdffff21f839f8741ac7442414ecf450"
    "00c70600000000c7421c00000000e830feffff619d53565789cfe9fcffffff9c6089cbe83dfeffff730c619da180ffe5"
    "00e9fcffffff619dc39c6089cbe823feffff73f2619d8b41108b8890000000e9fcffffff9c6089cbe847fdffff7451e8"
    "50fdffff73588b442424bf00000000b90f0000003b07740783c708e2f7eb3f8b6f0485ed74388b0e83f95d77318b048d"
    "f067ad003968047525e882fdffff85ff741c8b4b3ce8eefcffff21f839f8750e619d568b7110d94644e9fcffffffe880"
    "fdffff619dc35251ff74240ce8790000009c608b4c24248b542428833db802e6000e755d83fa12775889d6e840fcffff"
    "668504751005000074470fb64153c1e806743e83ec0889442404d91c248b042485c07e273d0000803f7320db442404d8"
    "0d0c050000d80424d91c24813c240000803f7607c704240000803fd9042483c408619d8d642408c2040083ec088b4130"
    "e9fcffffffccccccffffffff0ad7233c001000104008000200028000800000008000800080000004c000c000c000c000"
    "c000c000c000c000cbd218000000000081df18000000000043771e0000000000a77b1e0000000000d019230000000000"
    "a008290080082900651d290000000000d1bb2d00c0bb2d0008c82d00f0c72d0098cf2d0070cf2d00fc6d3000e06d3000"
    "1785300000000000c7d23000a0d23000aced3000000000004279310000000000480153000010000008cb510040080000"
    "f80053008002000064105300000400005c0f5300c000000034015300800000002001530080020000000000000ad7a33c"
    "000080000010000800000000000000000000000000000000000400000000000000000000000207020407"
)
LEGACY_V05_RELOCATIONS = ((13, 1, 'code', 1064), (39, 1, 'code', 1064), (74, 1, 'code', 0), (111, 1, 'code', 0), (117, 1, 'code', 0), (264, 1, 'code', 1072), (456, 2, 'retail_attribute', 0), (514, 1, 'code', 1064), (571, 2, 'retail_decode', 0), (665, 1, 'code', 0), (827, 1, 'code', 1112), (964, 1, 'code', 0), (1009, 1, 'code', 0), (605, 2, 'retail_account', 0), (747, 2, 'retail_initialize_tail', 0), (770, 2, 'retail_generate_tail', 0), (800, 2, 'retail_ai_tail', 0), (906, 2, 'retail_consume_tail', 0), (1057, 2, 'retail_attribute_tail', 0))
LEGACY_V05_LABELS = {'ai_ready': 777, 'attribute': 918, 'attribute_body': 1050, 'attribute_done': 1041, 'attribute_load': 1035, 'carrier': 132, 'carrier_bad_state': 199, 'carrier_bad_steer': 201, 'carrier_no': 203, 'clear_charge': 275, 'clear_done': 308, 'clear_request': 300, 'code_end': 1338, 'config': 1064, 'consume': 804, 'consume_allowed': 896, 'consume_denied': 910, 'consume_find': 836, 'consume_found': 847, 'consumers': 1112, 'decode': 570, 'dispatch': 585, 'effect_masks': 1296, 'effect_step': 1292, 'effective': 0, 'effective_done': 103, 'effective_read': 51, 'effective_zero': 101, 'families': 1232, 'filter': 392, 'filter_done': 449, 'generate': 751, 'generate_denied': 774, 'initialize': 609, 'initialize_check': 695, 'initialize_done': 739, 'initialize_family': 664, 'initialize_family_found': 685, 'initialize_find': 674, 'initialize_mask': 690, 'initialize_steer': 647, 'instructions_end': 1061, 'maintain': 309, 'maintain_any': 345, 'maintain_clear': 385, 'maintain_yes': 383, 'mask_done': 268, 'mask_juke': 269, 'move_mask': 240, 'move_masks': 1072, 'permissions': 104, 'running': 205, 'running_no': 236, 'running_yes': 238, 'speed': 450, 'speed_bound': 528, 'speed_load': 559, 'speed_store': 556, 'speed_zero': 554, 'tier_count': 80, 'tier_done': 97, 'tier_limits': 1334, 'tier_overfull': 95, 'unlocked_mask': 1288, 'unlocked_moves': 116}
LEGACY_V05_SHA256 = "2caea89c9171fcd0490791bd37b4e3a3d57418c3dbd48a879d287e0857371e13"
LEGACY_V05_VA = 0x14DA000


def legacy_code_for(code_va, abilities_off_week=None, *, lock_right_stick=False,
                    lock_special_moves=False, lock_speedster=True):
    """The v0.5 owner bytes for the same settings (no star rules existed)."""
    _week(abilities_off_week)
    locks = _locks(lock_right_stick=lock_right_stick,
                   lock_special_moves=lock_special_moves, lock_speedster=lock_speedster)
    blob = bytearray(LEGACY_V05_CODE)
    _relocate(blob, code_va, LEGACY_V05_RELOCATIONS)
    struct.pack_into("<i", blob, LEGACY_V05_LABELS["config"], -1 if abilities_off_week is None else abilities_off_week)
    struct.pack_into("<I", blob, LEGACY_V05_LABELS["unlocked_mask"],
                     sum(LOCK_MASKS[key] for key, locked in locks.items() if not locked))
    blob.extend(b"\xcc" * (CODE_SIZE - len(blob)))
    return bytes(blob), {name: code_va + offset for name, offset in LEGACY_V05_LABELS.items()}


def sites(labels):
    result = []
    for name, (va, before) in HOOKS.items():
        opcode = b"\xe8" if name in ("speed", "decode", "dispatch") else b"\xe9"
        after = opcode + struct.pack("<i", labels[name] - va - 5) + b"\x90" * (len(before) - 5)
        result.append((name, va, before, after))
    return result


def allocation(payload):
    found = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    _require(len(found) == 1 and (found[0]["kind"], found[0]["size"], found[0]["align"])
             == ("code", CODE_SIZE, 16), "reserve abilities with the complete owner union on a clean base")
    return found[0]


def _inspect_revision(payload):
    """(state, settings, revision). revision is "retail", "star-gate" (this template) or "beta-76.5" (the v0.5 reader)."""
    _require(isinstance(payload, (bytes, bytearray)) and len(payload) >= 4096, "truncated abilities XBE")
    layout = space.layout(payload)  # checks every section digest and allocation seal
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for hook, before in HOOKS.values():
            if va <= hook and hook + len(before) <= va + size:
                blob[hook - va:hook - va + len(before)] = before
        _require(hashlib.sha256(blob).hexdigest() == digest,
                 f"foreign abilities dependency at {va:#x}")
    present = any(a["owner"] == OWNER for a in layout["allocations"])
    state = "retail"
    revision = "retail"
    settings = {"abilities_off_week": None, **_locks(), **_stars()}
    labels = {name: 0 for name in HOOKS}
    if present:
        a = allocation(payload)
        content = image.read(a["va"], a["size"])
        if content != b"\xcc" * a["size"]:
            value = struct.unpack_from("<i", content, assembly.LABELS["config"])[0]
            settings["abilities_off_week"] = _week(None if value == -1 else value)
            mask = struct.unpack_from("<I", content, assembly.LABELS["unlocked_mask"])[0]
            settings.update({key: not bool(mask & bits) for key, bits in LOCK_MASKS.items()})
            stars = _read_stars(content)
            expected = None
            if stars is not None:
                try:
                    expected, labels = code_for(a["va"], **{**settings, **stars})
                except AbilitiesError:
                    expected = None
            if expected is not None and content == expected:
                settings.update(stars)
                revision = "star-gate"
            else:
                # The beta 76.5 template has no star rules (it behaves like this one with all of them off).
                legacy, labels = legacy_code_for(a["va"], **{k: v for k, v in settings.items() if k not in DEFAULT_STARS})
                _require(content == legacy, "foreign abilities code/table/configuration")
                revision = "beta-76.5"
            state = "applied"
    for name, va, before, after in sites(labels):
        _require(image.read(va, len(before)) == (after if state == "applied" else before),
                 f"mixed/foreign abilities hook: {name}")
    return state, settings, revision


def _inspect(payload):
    state, settings, _revision = _inspect_revision(payload)
    return state, settings


def revision(payload):
    """retail | star-gate | beta-76.5 | foreign."""
    try:
        return _inspect_revision(payload)[2]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload):
    try:
        state, settings, rev = _inspect_revision(payload)
        return {"status": state, **settings, "model_version": MODEL_VERSION, "revision": rev,
                "experimental": True, "runtime_witnessed": False}
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return {"status": "foreign", "experimental": True, "runtime_witnessed": False}


def reservations(payload):
    _require(status(payload) == "applied", "abilities reservations require complete installation")
    out = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    for name, (va, before) in HOOKS.items():
        out.append(dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + name + "; not a cave"))
    return out


def apply(payload, *, abilities_off_week=_UNSET, lock_right_stick=_UNSET,
          lock_special_moves=_UNSET, lock_speedster=_UNSET, right_stick_stars_only=_UNSET,
          charge_stars_only=_UNSET, button_moves_stars_only=_UNSET, star_access=_UNSET):
    """Install both phases; omitted replay option retains the installed week.

    An explicit None removes the week only on a clean base. Configuration
    changes on an installed image refuse before any byte is changed.
    """
    state, previous = _inspect(payload)
    wanted = dict(previous)
    if abilities_off_week is not _UNSET:
        wanted["abilities_off_week"] = _week(abilities_off_week)
    for key, value in dict(lock_right_stick=lock_right_stick,
                           lock_special_moves=lock_special_moves, lock_speedster=lock_speedster).items():
        if value is not _UNSET:
            wanted[key] = _locks(**{key: value})[key]
    for key, value in dict(right_stick_stars_only=right_stick_stars_only, charge_stars_only=charge_stars_only,
                           button_moves_stars_only=button_moves_stars_only, star_access=star_access).items():
        if value is not _UNSET:
            wanted[key] = _stars(**{key: value})[key]
    receipt = dict(owner=OWNER, **wanted, model_version=MODEL_VERSION,
                   experimental=True, runtime_witnessed=False, changed_bytes=0, edits=[])
    if state == "applied":
        _require(wanted == previous, "different abilities settings; rebuild from supported base")
        return payload, {**receipt, "status": "already_applied"}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                     if space.status(payload) == "retail" else (payload, {}))
    a = allocation(allocated)
    content, labels = code_for(a["va"], **wanted)
    installed, install_receipt = space.install_code(allocated, OWNER, content)
    image = XbeImage(installed)
    buf = bytearray(installed)
    edits = []
    for name, va, before, after in sites(labels):
        off = image.offset(va, len(before))
        buf[off:off + len(after)] = after
        edits.append(dict(label=name, va=hex(va), file_offset=hex(off), size=len(after),
                          before=before.hex(), after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied", "abilities installation postcondition failed")
    return result, {**receipt, "status": "applied", "edits": edits,
                    "allocation": allocation_receipt, "code_install": install_receipt,
                    "code_va": hex(a["va"]), "code_bytes": CODE_SIZE, "data_bytes": 0,
                    "reservations": reservations(result),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "result_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": sum(x != y for x, y in zip(payload, result)) + len(result) - len(payload)}


# SHA-256 pins of complete dependency spans, normalizing only HOOKS above.
GUARDS = (
    # Native getter bodies and dispatch entries prove the five effect names.
    (0x1798b0, 112, "86d4bdc2207c23e0eae80be17922e692470bacdee6d88570032f71e0016010e4"),
    (0xaa4048, 4, "b1e397fd0eb3030455b5290c0b529630d08cf09eb0c4808bcf52341c6bab51e2"),
    (0x179a00, 112, "e103922e87b4456e7f59a1e66315ed0879fe3183a722667211b300352986310b"),
    (0xaa4068, 4, "9e448c1acc101889ddc719e94011779581f93d44928a5c3a540a4a725db09be2"),
    (0x179920, 112, "fefd39d7f0ec7e2fc098641e74cdf22b8cda5c557c95996026c97994c2da560f"),
    (0xaa4088, 4, "d63d4e083057487f9fa94809da7d42cfc84f078941cf0317e2f05c59e541f71e"),
    (0x179d80, 112, "dcf24c85f96b343ee09a96efe06f6ce74486ffaee6ad5f84348e6dba899114c8"),
    (0xaa41a8, 4, "42055bc458ad159d5c3a3312ee567c9cf1a6f5d17d815e97087c814ac8e21426"),
    (0x17a020, 112, "a0b04288f9e9eb25acd08a2f31b084fe10477c5355e7f1e8b138fe81ab5278c9"),
    (0xaa4268, 4, "e0a30ebc76e3f3442a705fe2ac19f2d4b4cb072c1616db3423263925bc28cb34"),
    (0x75CC2, 19, "1647b13869fd1e514019903ddc78f26105f625281f8e14c58a3d34cddce6e93a"),
    (0x179840, 109, "1545508121481397d24e2d8713d08d4403521b8923b3bd1e846a196ea7b39f28"),
    (0x17B010, 407, "ba9015aa5f6b34151c14cd6ab0090d8f20d906c47c3be360cdf2da59b178acd2"),
    (0x156470, 26, "9e99f7c7010375034ad7b21a4c59ebe6aa556ea14863ea075219e9dbcba6e525"),
    (0x18EC40, 95, "a6391fed20582d34d21034343c1ee11712a0fceb6f3eac7a3d8fd6ae28087da1"),
    (0x1CD550, 59, "fa171719f06965537ecd42af3764d5a6c174115c2f4ae100e646c77d23307997"),
    (0x2D43F0, 985, "6be1c1e49b2752a9bbd105612bb9920d96b7cfa5cb17f82517f5022a58cf45d1"),
    (0xAD67F0, 376, "6c9cd06066d299e3edfa474fc59316fd1373ccc94ad89e6b64c48925669a00ef"),
    (0xAABF58, 80, "9ee3bf9a98114f9dd486b926fba466eeca83973d45cbf1b233e7c1a1e737e990"),
    (0x50A38C, 24, "84f31d7edb057b23dfd6a994e439d3908dcac40d0bf62369e26fd666bca35b0c"),
    (0x120A20, 1983, "258ebc6f41a343243bea41d17fa042b8b3f73449c6371b83372b2562045d6234"),
    (0xA9A220, 108, "8554ad5808a1f0bf1e7fbb79d3723faaa62f67f59814dc48212dc70c70d0d277"),
    (0xA9A2F8, 108, "ba33700c6b378357a60d1e1a7ce609fea19b0b87991cab88b17fc5c38f03665e"),
    (0xA9AAFC, 108, "8554ad5808a1f0bf1e7fbb79d3723faaa62f67f59814dc48212dc70c70d0d277"),
    (0xA9ABD4, 108, "191a644ef47c4430dd1d095441d5986d2e62ebd43adde396306250bdc2d9a2d3"),
    (0xA9B3D8, 108, "7cf5d92da644b3d7a71e9f7a32aea5b7d4a9c70e7d3663d527e562ac2e0921f6"),
    (0xA9B4B0, 108, "688da526368a7181635c7fb0b4f97119514675040bd84ee63df9849a1e9c9ce0"),
    (0x530148, 20, "7186376e5efd45bec4fd29472e1461259b97cde7a84ec1ff2f6afab80f35f118"),
    (0x51CB08, 20, "863c64d5511a3f3f4e6a7f519f937320ee56856a1e794a3bc9093077d54a87b1"),
    (0x5300F8, 20, "46ee1b7dd5f0b8e17bd66ec10d1dcacead8b8e40991a7a61dadc53b7eab608f8"),
    (0x531064, 20, "29a9d871be57136c2740da26eb4ed21471516a98eefed89b4b867c192bad1155"),
    (0x530F5C, 20, "c091f32f8708700c7be75e547a1d9abc3864d44b2c1b885bd93a2e11292ef8ef"),
    (0x530134, 20, "c9ce35a55b2a923d649f050244e6e4966a36f24470eb7eb003b88a0990379d19"),
    (0x530120, 20, "03c31ac36faee4f7e0e438cb73223296855d37e7e08a68a77a82e51b426c2156"),
    (0x18D2BE, 18, "18e23a525b489a41f24c5d7d41191c4c7d9734aff653ccd1f5618b6ca8281b58"),
    (0x18DF74, 18, "b5dd15d982e8e8fa33cdb89096f99fdeb42f5be736b74cea97cbde4dff626159"),
    (0x1E7736, 18, "3f8358ee9b86848c91d87cfc1a4695d350fc53b4883dfd0363c8bf3dbabc1a72"),
    (0x1E7B9A, 18, "b73689c3cffee75ffb5624d4d10fbc475afbfb739b67658ff842522fe00607c3"),
    (0x2319C3, 18, "fb12385b4198cf388e83fed7f24e5af1f74179e209775ce87c7cd97be4b75780"),
    (0x290893, 18, "4a186be1cef5829d3df31a249b47c03cd5fc3f08d98e04173e2dc912c298d78b"),
    (0x291D58, 18, "4323b27155db8e6e5f3d23ab641baa2700c61cb74402c1cf8e1877e23e22928f"),
    (0x2DBBC4, 18, "1a4b9b0565b7a360e8d94991ad1b4155010e01ab23e9981aeabbfb687c06db42"),
    (0x2DC7FB, 18, "c0d689996e1f512eff4db2b8e29575e18114685357a512b2f4e644409b177641"),
    (0x2DCF8B, 18, "3c7fa6b80464b2a76019e8379b41731d388f49f1c4eeb0901ed3e4b3617c358d"),
    (0x306DEF, 18, "38904e0ac49d389f6c1d89c3bc275038c6b7e99fde200f3efca6c30b547200f1"),
    (0x30850A, 18, "c4357450d021df9b9f800993dbeb0c18f6fe83483f3be5cc9d51406604e3e761"),
    (0x30D2BA, 18, "c41c4d43a45af1d0a613777e40dee46ecbdb6e208a09a6d471c403b8133b8229"),
    (0x30ED9F, 18, "0fd124664ca80eb8d095eb63b5060f1f49f0487ca43c7839d04d3cbf04fd44d6"),
    (0x317935, 18, "9a47fd8256bee3de7c5c06cdd4fa1b9f86e272177511773aecbd1c4b3f401c1f"),
)


def main():
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="new XBE copy; omit to inspect")
    parser.add_argument("--off-week", type=int, default=None, help="zero-based regular-season row 0..17")
    for name in LOCK_MASKS:
        parser.add_argument("--" + name.replace("_", "-"),
                            action=argparse.BooleanOptionalAction,
                            default=DEFAULT_LOCKS[name])
    for name in ("right_stick_stars_only", "charge_stars_only", "button_moves_stars_only"):
        parser.add_argument("--" + name.replace("_", "-"), action=argparse.BooleanOptionalAction,
                            default=DEFAULT_STARS[name])
    parser.add_argument("--star-access", default=",".join(DEFAULT_STAR_ACCESS),
                        help="four access levels (starred no tier, Star, Superstar, X-Factor): " + ", ".join(ACCESS_LEVELS))
    args = parser.parse_args()
    _require(args.source.stat().st_size <= 16 * 1024**2, "expected a bounded XBE, not a disc or pack")
    with args.source.open("rb") as source:
        payload = source.read(16 * 1024**2 + 1)
    if args.output is None:
        print(json.dumps(read_settings(payload), indent=2))
        return
    locks = {name: getattr(args, name) for name in (*LOCK_MASKS, "right_stick_stars_only", "charge_stars_only",
                                                    "button_moves_stars_only")}
    locks["star_access"] = tuple(args.star_access.split(","))
    result, receipt = apply(payload, abilities_off_week=args.off_week, **locks)
    with args.output.resolve().open("xb") as output:
        output.write(result)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
