"""Abilities rules v2. EXPERIMENTAL / UNWITNESSED, every preset off.

Use the shipped seven roster bits. Movement Speed is extended after BOTH
native clamps; native move commands and charge consumption require their
specific permission. The native special-move meter is confined to live ball
carriers, including CPU carriers. No new timer, mutable allocation, roster
save migration, simulated-game effect, or extra week is supplied. The editor
authors tiers separately. Five existing move flags gain capped live attribute
bonuses for tiered players. Independent lock switches preserve v1 defaults.

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
LOCK_MASKS = {"lock_right_stick": RIGHT_STICK,
              "lock_special_moves": JUKE | SPIN | TRUCK | HURDLE | STIFF_ARM,
              "lock_speedster": SPEEDSTER}
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
    "optional locks require Speedster for speed above 99, each special move's "
    "ability, and Right-Stick Moves for stick moves. Tiered Juke, Stiff-Arm, "
    "Hurdle, Truck and Spin add 2/4/6 effective points to Agility, Strength, "
    "Jumping, Break Tackle and Pass Rush during live play, capped at 100. "
    "When either move lock is on, the charge meter is limited to live ball "
    "carriers and known move consumers. Turn both move locks off for retail "
    "charge behavior. An optional existing franchise week turns stored "
    "abilities off. Author tiers and abilities on the Rosters Abilities page. "
    "Tiered players with excess stored abilities receive no stored permissions "
    "or bonuses until corrected. Unranked legacy flags retain v1 permissions. "
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
    return {key: values.get(key, True) for key in LOCK_MASKS}


def code_for(code_va, abilities_off_week=None, *, lock_right_stick=True,
             lock_special_moves=True, lock_speedster=True):
    _week(abilities_off_week)
    locks = _locks(lock_right_stick=lock_right_stick,
                   lock_special_moves=lock_special_moves, lock_speedster=lock_speedster)
    blob = bytearray(assembly.CODE)
    symbols = {"code": code_va, **SYMBOLS}
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)
    struct.pack_into("<i", blob, assembly.LABELS["config"],
                     -1 if abilities_off_week is None else abilities_off_week)
    struct.pack_into("<I", blob, assembly.LABELS["unlocked_mask"],
                     sum(LOCK_MASKS[key] for key, locked in locks.items() if not locked))
    blob.extend(b"\xcc" * (CODE_SIZE - len(blob)))
    return bytes(blob), {name: code_va + offset for name, offset in assembly.LABELS.items()}


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


def _inspect(payload):
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
    settings = {"abilities_off_week": None, **_locks()}
    labels = {name: 0 for name in HOOKS}
    if present:
        a = allocation(payload)
        content = image.read(a["va"], a["size"])
        if content != b"\xcc" * a["size"]:
            value = struct.unpack_from("<i", content, assembly.LABELS["config"])[0]
            settings["abilities_off_week"] = _week(None if value == -1 else value)
            mask = struct.unpack_from("<I", content, assembly.LABELS["unlocked_mask"])[0]
            settings.update({key: not bool(mask & bits) for key, bits in LOCK_MASKS.items()})
            expected, labels = code_for(a["va"], **settings)
            _require(content == expected, "foreign abilities code/table/configuration")
            state = "applied"
    for name, va, before, after in sites(labels):
        _require(image.read(va, len(before)) == (after if state == "applied" else before),
                 f"mixed/foreign abilities hook: {name}")
    return state, settings


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload):
    try:
        state, settings = _inspect(payload)
        return {"status": state, **settings, "model_version": MODEL_VERSION,
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
          lock_special_moves=_UNSET, lock_speedster=_UNSET):
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
        parser.add_argument("--no-" + name.replace("_", "-"), action="store_true")
    args = parser.parse_args()
    _require(args.source.stat().st_size <= 16 * 1024**2, "expected a bounded XBE, not a disc or pack")
    with args.source.open("rb") as source:
        payload = source.read(16 * 1024**2 + 1)
    if args.output is None:
        print(json.dumps(read_settings(payload), indent=2))
        return
    locks = {name: not getattr(args, "no_" + name) for name in LOCK_MASKS}
    result, receipt = apply(payload, abilities_off_week=args.off_week, **locks)
    with args.output.resolve().open("xb") as output:
        output.write(result)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
