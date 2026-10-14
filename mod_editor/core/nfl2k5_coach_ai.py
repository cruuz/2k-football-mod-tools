"""Automatic current-NFL coach playback and generated-coach portraits.

Profiles are authored targets compiled against exact PLAY bytes, never bundled
retail resources. The reserved tail stays inside the original resource span.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_vip as vip
from . import nfl2k5_playbook_inspector as ip

ROOT = Path(__file__).resolve().parents[2]
PROFILE_OFFSET, PROFILE_SIZE, HEADER_SIZE = 0x13000, 896, 128
BODY_SIZE, CONTEXT_SIZE = 0x13390, 0x21A0
MAGIC = b"COACHAI1"
VALID_MARKER = 0x314B4F43
OWNER = "nfl2k5_coach_ai"
CODE_SIZE, DATA_SIZE = 5120, 128
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
BUILD_CAPTION = "Automatic 2026 CPU coach profiles (experimental)"
HELP_TEXT = ("Retail: CPU teams use their native coach tendencies. Patch: use automatic 2026 coach "
             "profiles for current NFL CPU teams in Play Now, Season, Franchise and playoffs. "
             "Explicit Coach Matchup choices win. Rebuilds profiles for the final playbooks and "
             "includes VIP-aware Modern 2. Enabled in the SOFTDRINK experimental preset; "
             "turn this setting off to keep native coach tendencies.")


class CoachAIError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CoachAIError(message)


def compact_tendency(value):
    """Keep compiler inputs, observed counts and source audit; omit full grids."""
    require(value.get("schema") == "nfl2k5_coach_tendencies/v1", "Unknown coach tendency schema")
    keys = ("schema", "team", "coach", "provenance", "sources", "charting_sources", "participation_sources",
            "charting_join", "participation_join", "games", "season_calls", "overall", "native_statistics",
            "fourth_down", "two_point", "native_decision_projections", "defense", "native_offense_pools", "limitations")
    return {k: value[k] for k in keys if k in value}


def portrait_rows():
    return json.loads((ROOT / "data/vip/coach_portraits_2026.json").read_text(encoding="utf-8"))


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def tag_checksum(tag):
    copy = bytearray(tag)
    copy[0x14:0x18] = bytes(4)
    copy[0x1C:0x20] = bytes(4)
    return fnv(copy)


def _shape(resource):
    require(len(resource) == BODY_SIZE + 32, "Unsupported PLAY resource size")
    require(resource[32 + 12:32 + 16] == b"PLAY", "Expected native PLAY resource")
    used = struct.unpack_from("<I", resource, 32 + 0x1083C)[0]
    require(0x10840 + used * 2 <= PROFILE_OFFSET, "Declared PLAY strings overlap coach profile storage")


def inspect_profile(resource):
    _shape(resource)
    lo = 32 + PROFILE_OFFSET
    tag = resource[lo:lo + PROFILE_SIZE]
    require(tag[:8] == MAGIC, "Missing or foreign coach profile tag")
    version, book, asset, photo = struct.unpack_from("<4H", tag, 8)
    fingerprint, checksum, identity, marker = struct.unpack_from("<4I", tag, 16)
    require(version == 1 and book < 32 and marker == 0, "Unsupported or runtime-mutated coach profile header")
    require(checksum == tag_checksum(tag), "Corrupt coach profile checksum")
    original = resource[:lo] + bytes(PROFILE_SIZE) + resource[lo + PROFILE_SIZE:]
    digest = hashlib.sha256(original).digest()
    require(digest == tag[32:64], "Coach profile does not match the exact compiled book")
    require(fingerprint == fnv(resource[32 + 0x30:lo]), "Coach raw-book fingerprint mismatch")
    units = struct.unpack_from("<13H", tag, 64)
    require(0 in units, "Coach profile name is unterminated")
    name = tag[64:64 + units.index(0) * 2].decode("utf-16le")
    row = next((r for r in portrait_rows() if r["book_index"] == book), None)
    require(row and (asset, photo, identity, name) == (row["asset"], row["portrait"], row["identity"], row["name"]),
            "Coach profile identity does not match the current NFL directory")
    return dict(team=row["team"], book_index=book, asset=asset, portrait=photo, identity=identity,
                name=name, book_sha256=digest.hex(), raw_fingerprint=fingerprint,
                profile_sha256=hashlib.sha256(tag).hexdigest())


def strip_profile(resource):
    _shape(resource)
    lo = 32 + PROFILE_OFFSET
    tag = resource[lo:lo + PROFILE_SIZE]
    if tag != bytes(PROFILE_SIZE):
        inspect_profile(resource)  # Refuse stale/foreign data; never erase blindly.
    return resource[:lo] + bytes(PROFILE_SIZE) + resource[lo + PROFILE_SIZE:]


def expand_profile(resource):
    """Reference expansion for byte comparison with the actual native kernel.

    Unmapped statistics are zero here; runtime seeds them with native 2818D0.
    """
    info = inspect_profile(resource)
    p = resource[32 + PROFILE_OFFSET + HEADER_SIZE:32 + PROFILE_OFFSET + PROFILE_SIZE]
    out = bytearray(CONTEXT_SIZE)
    struct.pack_into("<i", out, 0x34, info["book_index"])
    at = 0
    for i in range(20):
        base = 0x3C + i * 128
        out[base] = 1
        for j in range(1, 9):
            flip, form, play = p[at:at + 3]
            out[base + 2 + j * 14] = flip
            out[base + 2 + j * 14 + 7:base + 2 + j * 14 + 9] = bytes((form, play))
            at += 3
    for i in range(15):
        base = 0xA3C + i * 62
        out[base] = 1
        for j in range(1, 5):
            out[base + 2 + j * 12 + 3:base + 2 + j * 12 + 6] = p[at:at + 3]
            at += 3
    struct.pack_into("<4H", out, 0xDF6, 1, 0, 1, 0)
    out[0xE90:0xE98] = p[660:668]
    out[0x20B8:0x2118] = p[668:764]
    out[0x2186:0x218A] = p[764:768]
    return bytes(out)


def build_profile(resource, tendency):
    original = strip_profile(resource)
    row = next((r for r in portrait_rows() if r["team"] == tendency["team"]), None)
    require(row is not None, "No current NFL coach identity for team")
    spec = tendency["provenance"]
    require((spec["native_book_index"], spec["profile_name"]) == (row["book_index"], row["name"]),
            "Coach tendency directory and portrait identity disagree")
    # A clean context, not a person's USR record or preferences.
    empty = bytearray(vip.SIZE)
    struct.pack_into("<I", empty, 0, 1)
    save, receipt = vip.build_coach(vip.VipSave.decode(bytes(empty)), original, tendency,
                                   row["name"], row["book_index"])
    ctx = bytearray(save.payload[vip.CONTEXT:vip.CONTEXT + CONTEXT_SIZE])
    passes, runs = struct.unpack_from("<HH", ctx, 0x20B8)
    # Native game-start 281A90 decays pass and run totals independently at
    # 254, unlike its paired denominator/numerator groups. Keep their ratio
    # below that boundary so a short-history coach is not biased toward the
    # category whose count happened to stay below it. Original counts remain
    # in the source audit; no observations are invented.
    scale = min(1, 253 / max(passes, runs)) if passes or runs else 1
    serialized = round(passes * scale), round(runs * scale)
    struct.pack_into("<HH", ctx, 0x20B8, *serialized)
    receipt["automatic_overall_counts"] = dict(source_passes=passes, source_runs=runs,
                                                serialized_passes=serialized[0], serialized_runs=serialized[1],
                                                reason="Preserve ratio across independent native game-start decay")
    packed = bytearray()
    for i in range(20):
        for j in range(1, 9):
            at = 0x3C + i * 128 + 2 + j * 14
            packed.extend((ctx[at], ctx[at + 7], ctx[at + 8]))
    for i in range(15):
        for j in range(1, 5):
            at = 0xA3C + i * 62 + 2 + j * 12
            packed.extend(ctx[at + 3:at + 6])
    packed += ctx[0xE90:0xE98] + ctx[0x20B8:0x2118] + ctx[0x2186:0x218A]
    require(len(packed) == 768, "Coach payload size changed")
    book = ip.parse_playbook_resource(original)
    require(all(c["formation"] < len(book.formations) and c["play"] < min(256, len(book.plays))
                for p in receipt["pools"] for c in p["choices"]), "Offensive recorded index out of bounds")
    require(all(c["formation"] < len(book.formations) and max(c["front"], c["coverage"]) < min(256, len(book.plays))
                for p in receipt["defense_pools"] for c in p["choices"]), "Defensive recorded index out of bounds")
    tag = bytearray(HEADER_SIZE) + packed
    tag[:8] = MAGIC
    struct.pack_into("<4H", tag, 8, 1, row["book_index"], row["asset"], row["portrait"])
    struct.pack_into("<4I", tag, 16, fnv(original[32 + 0x30:32 + PROFILE_OFFSET]), 0, row["identity"], 0)
    tag[32:64] = hashlib.sha256(original).digest()
    name = row["name"].encode("utf-16le")
    tag[64:64 + len(name)] = name
    tag[96:128] = hashlib.sha256(json.dumps(compact_tendency(tendency), sort_keys=True,
                                           separators=(",", ":"), allow_nan=False).encode()).digest()
    struct.pack_into("<I", tag, 20, tag_checksum(tag))
    lo = 32 + PROFILE_OFFSET
    result = original[:lo] + tag + original[lo + PROFILE_SIZE:]
    info = inspect_profile(result)
    receipt.update(automatic_profile=info, resource_sha256=hashlib.sha256(result).hexdigest(),
                   profile_offset=lo, profile_size=PROFILE_SIZE,
                   context_offense_hex=ctx[0x3C:0xA3C].hex(), context_defense_hex=ctx[0xA3C:0xDDE].hex(),
                   decision_counts_hex=ctx[0xE90:0xE98].hex(),
                   attachment="automatic current-NFL CPU only, native modes 4..7; explicit choice wins",
                   portrait=str(row["portrait"]))
    return bytes(result), receipt


# Pinned native instructions. No hook replaces an RNG, selector or accessor.
HOOKS = (
    ("source", 0x161E30, "5356578bfa8bf1", 0xE9),
    ("setup", 0xF6E9D, "8b4c241c8b048db004ba00", 0xE9),
    ("takeover", 0xF7BFC, "e8effeffff", 0xE8),
    ("cleanup", 0x6195A, "b92c16e600", 0xE9),
    ("matchup", 0x367BD0, "6bd2588b927824cc00", 0xE9),
    ("viewer", 0x350890, "833d0892cb00ff", 0xE9),
    ("resource", 0xE0D90, "5355568bf1", 0xE9),
    ("controller_commit", 0x1569CF, "e89cfeffff", 0xE8),
)
SYMBOLS = dict(source_continue=0x161E37, resource_continue=0xE0D95,
               setup_continue=0xF6EA8, takeover_native=0xF7AF0, controller_native=0x156870,
               cleanup_continue=0x6195F, matchup_continue=0x367BD9, matchup_finish=0x367C3D,
               viewer_continue=0x350897, viewer_finish=0x3508C0, setup_original=0xF6E60,
               stats_bind_native=0xF7A90, heap_native=0x38FB0, allocate_native=0x48700,
               free_native=0x48870, stats_native=0x2818D0, portrait_native=0xE71E0)


def allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 2 and {(r["kind"], r["size"], r["align"]) for r in rows} ==
            {(k, n, a) for _, k, n, a in REQUESTS}, "Missing or foreign coach AI allocation")
    return {r["kind"]: r for r in rows}


def career_state_va(payload):
    from . import nfl2k5_xbe_space as space
    return next((r["va"] for r in space.layout(payload)["allocations"]
                 if r["owner"] == "nfl2k5_my_career" and r["kind"] == "data"), 0)


def code_for(code_va, data_va, career_va=0):
    from . import nfl2k5_coach_ai_code as assembly
    symbols = dict(SYMBOLS, code=code_va, state=data_va, career_state=career_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, "Coach AI exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_coach_ai_code as assembly
    result = []
    for name, va, pin, op in HOOKS:
        before = bytes.fromhex(pin)
        after = bytes((op,)) + struct.pack("<i", code_va + assembly.LABELS[name] - va - 5)
        result.append((name, va, before, after.ljust(len(before), b"\x90")))
    return result


def _owned(payload):
    """Validate complete owned spans without recursively checking neighbors."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocations(payload) if present else None
    edits = sites(owned["code"]["va"] if owned else 0)
    states = set()
    for name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        c, d = owned["code"]["va"], owned["data"]["va"]
        require(image.read(d, DATA_SIZE) == bytes(DATA_SIZE), "Foreign initialized coach AI state")
        raw = image.read(c, CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else
                   "applied" if raw == code_for(c, d, career_state_va(payload)) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed coach AI hooks/code")
    return next(iter(states)), edits


def normalized_sites(payload):
    """Neighbor recognizers may normalize only the fully verified owner."""
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    if all(image.read(va, len(bytes.fromhex(pin))) == bytes.fromhex(pin) for _, va, pin, _ in HOOKS):
        return []
    state, edits = _owned(payload)
    require(state == "applied", "Foreign coach AI neighbor")
    return edits


def _recognize(payload):
    from . import nfl2k5_playbook_pair as pair
    from .nfl2k5_cave_oracle import XbeImage
    state, edits = _owned(payload)
    image = XbeImage(payload)
    neighbors = []
    for name, va, pin, _ in pair.HOOKS:
        if name not in ("cleanup", "vip"):
            continue
        before = bytes.fromhex(pin)
        if image.read(va, len(before)) != before:
            require(pair.status(payload) == "applied", "Foreign playbook-pair lifecycle neighbor")
            neighbors.append((name, va, before, None))
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits + neighbors:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign coach AI prerequisite at {va:#x}")
    return state


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    from . import nfl2k5_xbe_space as space, nfl2k5_cpu_money_downs as money
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = _recognize(payload)
    policy = money.read_settings(payload)
    require(policy and policy["level"] == "modern2" and policy["vip_policy"],
            "Coach AI requires VIP-aware Modern 2; install/upgrade it first")
    before = payload
    allocation_receipt = {}
    if state == "applied":
        return payload, dict(owner=OWNER, status="already_applied", changed_bytes=0)
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        require(space.is_scaleout(payload), "Coach AI requires the scale-out allocator")
        payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    owned = allocations(payload)
    c, d = owned["code"]["va"], owned["data"]["va"]
    result, _ = space.install_code(payload, OWNER, code_for(c, d, career_state_va(payload)))
    image = XbeImage(result)
    buf = bytearray(result)
    edits = sites(c)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(status(result) == "applied" and space.status(result) == "applied", "Coach AI postcondition failed")
    require(len(result) == len(before), "Coach AI installation must be fixed-span")
    return result, dict(owner=OWNER, status="applied", experimental=True, runtime_witnessed=False,
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=sum(a != b for a, b in zip(before, result)), allocation=allocation_receipt,
                        code_va=c, state_va=d, rx_bytes=CODE_SIZE, rw_bytes=DATA_SIZE,
                        maximum_context_heap_bytes=2 * CONTEXT_SIZE, user_slots_used=0, save_growth=0,
                        supported_modes=[4, 5, 6, 7],
                        edits=[dict(name=n, va=hex(v), size=len(o), before=o.hex(), after=a.hex())
                               for n, v, o, a in edits])


GUARDS = (
    (0xe0d90, 443, "94205d158baef4714e193ec2766d45a6ee7bb899c6b764966f1ebf9675b881a5"),
    (0x1665a0, 14, "51b06a9965cc2703be9b2bfb04f71587f78f65743d048629ec7bee538e23989f"),
    (0x1665f0, 25, "47beeb5ea7af7c4e2220dcc0ce44776f461396ba7b58894d5f065b57cd6c759c"),
    (0x27d050, 35, "e32f59f431754d717c0552ab6956f6bdb0b55080a94b492041f822ff1ef4af09"),
    (0xf7b30, 164, "5ed062a0aa7d1a1ff5a7a455847f4e386967b45fa1723add8a56983fb06a97c2"),
    (0x1b1ee0, 867, "7ea550783ad544a9609cefbcc7ab96f1d79ac7da7e93469c073ce1c4568c0fa8"),
    (0x281a90, 217, "da664a9f75586309e18506e72214e8a0f760c252fabf189a1f5fb632f0f241c8"),
    (0x2812b0, 37, "3200d06d83de028859077b61e1ec0af18f02c1d821b0ed9b26374ac86299809f"),
    (0x2812e0, 32, "186592f6d36cc0c49c1d382a64afb172c6adfa023586f23b40d27914e0fb1a78"),
    (0x161e30, 497, "775282ba400cb00b05892157089d8c02855ea49eaf7d764bc4fe3e7cd6abfa3f"),
    (0xf6e60, 424, "b5ff5abdc7060a2c7be8209ba21846fd3c8a1c16e2c573c9f019805f25c0901e"),
    (0xf7a90, 96, "bb9c6572069d2280f3e69431c63f9b0d7903d2f7b30b273a53680783ea4953e5"),
    (0xf7be0, 35, "c192858ca8b8d6c6bdfbd094bbddd1210150432ddb3190a28e62928f09b7743b"),
    (0x1569c0, 21, "0897f8631a01920c8c39c8c37e4cdd193e23c2bc408ebf5b495d918dd88a13ba"),
    (0x156877, 316, "4037b7405eb067341328ee33523156aef4ca2338dc2ffb0baeeb1bfca33b2f4e"),
    (0x771f0, 10, "e94fedfd4b5865214b4dba8cd6a7c2c893a66c4f4443c731313408e2834410fa"),
    (0x61950, 170, "d85a7efb8fb54926be24d716ef2bea7b50b5129525cef1c4300a5620544c8414"),
    (0xf71e0, 19, "5c08a7153ba0c9a94ddeb94b8a76215462a00393acb1b490c146c15397ef10d5"),
    (0x367bd0, 151, "6f3fcf016d199541c45aa8f12d6b8e44c9d5f706ae7156f5b31858ae806a067a"),
    (0x350890, 75, "2f3a923fd8c63268e7be238733d24248bc3dc712a649b672967c38433e71c8d8"),
    (0xe71e0, 93, "9577c623ec5493b2adb22dccd34c92ebc6882d35cf3ed9cb49169fa9446034bc"),
    (0x2818d0, 433, "66606192647bac6217d69df8ba42e74ee6f8ae442891713b9d6a2370c0d6876e"),
    (0x38fb0, 6, "cc3ad517ec546fdbfa574fe66093f15a5f30ce9dfa7457e426a684a84a063e98"),
    (0x48700, 39, "2afa1c64c28563d908a6f69d13fc1944f151aa7fc7c9baf50e4ded284cf88d01"),
    (0x48870, 185, "e010d1b355cbd4cf150dc9993b918c46f6805d4c410bc570207a695dc073fa3c"),
)


def plan_profiles(image, *, tendencies=None, progress=None):
    """Read-only preflight of all 32 exact books and the current coach roster.

    Returns complete before/after resources; callers publish only after every
    book has compiled. Unknown/stale existing tags are never silently removed.
    """
    from . import nfl2k5_playbook_pack as packs, nfl2k5_roster_records as rr
    archive_module = packs._outer_image()
    directory_path = Path(tendencies) if tendencies else ROOT / "data/vip/coaches"
    prepared = []
    with archive_module.OuterImage(image) as archive:
        roster = rr.RosterDocument(archive.read_entry(5)[32:])
        for row in portrait_rows():
            team = roster.teams[row["book_index"]]
            photo = struct.unpack_from("<H", roster.body, team.coach_offset + 0x40)[0] if team.coach_offset else None
            require((team.kind, team.asset_id) == (0, row["asset"])
                    and photo in (row["portrait"], row.get("alternate_portrait", row["portrait"])),
                    f"{row['team']}: automatic coach AI needs the matching 2026 NFL coach roster/portrait identity")
            value = json.loads((directory_path / (row["team"] + ".json")).read_text(encoding="utf-8"))
            names = rr._coach_tool()
            parts = []
            for field in (0, 4):
                at = names.relative_target(roster.body, team.coach_offset + field, "coach name")
                require(at is not None, f"{row['team']}: missing roster coach name")
                parts.append(names.utf16z(roster.body, at, "coach name"))
            require(" ".join(parts) == value["coach"],
                    f"{row['team']}: roster coach {' '.join(parts)!r} differs from profile coach {value['coach']!r}")
            index = archive_module.BOOK_ENTRIES[value["provenance"]["archive_book"]]
            original = archive.read_entry(index)
            result, receipt = build_profile(original, value)
            receipt["roster_portrait"] = photo
            prepared.append((index, original, result, receipt))
            if progress:
                progress(f"Compiled {row['team']} coach profile against its final playbook")
    return prepared


SKIP_MESSAGE = ("2026 CPU coach profiles skipped: this disc's rosters do not have the 2026 head coaches. "
                "Install the SOFTDRINK 2K28 pack to use them.")


def roster_readiness(image, *, roster_edits=None, tendencies=None):
    """Read-only, before a build writes anything: will the roster this build ends with carry the 32 2026 head coaches
    that ``plan_profiles`` requires (team identity, portrait and coach name for every profile)?

    The roster is the source image's main roster with the build's roster-edits ``coaches`` applied in memory by the
    same writer the build uses (``apply_coach_names``, the only build step that writes coach names; it never moves a
    coach record's portrait or team). Returns {"ready": bool, "checked": n, "mismatches": [plain lines]}; a roster that
    cannot be read is not ready (its reason is the first mismatch)."""
    from . import nfl2k5_playbook_pack as packs, nfl2k5_roster_records as rr
    directory_path = Path(tendencies) if tendencies else ROOT / "data/vip/coaches"
    mismatches, checked = [], 0
    try:
        with packs._outer_image().OuterImage(image) as archive:
            roster = rr.RosterDocument(archive.read_entry(5)[32:])
        body = bytearray(roster.body)
        if roster_edits:
            document = roster_edits if isinstance(roster_edits, dict) else rr.read_edits(Path(roster_edits))
            entries = document.get("coaches") or []
            if entries:
                rr.apply_coach_names(body, roster.teams, entries, [])
        names = rr._coach_tool()
        for row in portrait_rows():
            checked += 1
            team = roster.teams[row["book_index"]]
            if (team.kind, team.asset_id) != (0, row["asset"]) or not team.coach_offset:
                mismatches.append(f"{row['team']}: the roster's club {row['book_index']} is not the 2026 club")
                continue
            photo = struct.unpack_from("<H", body, team.coach_offset + 0x40)[0]
            if photo not in (row["portrait"], row.get("alternate_portrait", row["portrait"])):
                mismatches.append(f"{row['team']}: coach portrait {photo} is not the 2026 head coach's")
                continue
            parts = []
            for field in (0, 4):
                at = names.relative_target(bytes(body), team.coach_offset + field, "coach name")
                parts.append(names.utf16z(bytes(body), at, "coach name") if at is not None else "")
            want = json.loads((directory_path / (row["team"] + ".json")).read_text(encoding="utf-8"))["coach"]
            if " ".join(parts) != want:
                mismatches.append(f"{row['team']}: roster coach {' '.join(parts)!r} is not {want!r}")
    except (OSError, ValueError, IndexError, KeyError, struct.error) as exc:
        mismatches.insert(0, f"the roster could not be read: {exc}")
    return dict(ready=not mismatches, checked=checked, mismatches=mismatches)


def write_profiles(image, prepared):
    """Fixed-span writes/readback after a complete read-only preflight."""
    from . import nfl2k5_playbook_pack as packs
    archive_module = packs._outer_image()
    lo = 32 + PROFILE_OFFSET
    rows = []
    with archive_module.OuterImage(image, writable=True) as archive:
        # Check every input again before the first mutation.
        for index, before, after, receipt in prepared:
            require(archive.read_entry(index) == before, "PLAY changed after coach profile preflight")
            require(len(after) == len(before) and before[:lo] == after[:lo]
                    and before[lo + PROFILE_SIZE:] == after[lo + PROFILE_SIZE:], "Coach edit escaped fixed tail span")
            inspect_profile(after)
        for index, before, after, receipt in prepared:
            changed = sum(a != b for a, b in zip(before, after))
            offset = archive.entries[index].virtual_offset + lo
            if changed:
                archive.write(offset, after[lo:lo + PROFILE_SIZE])
            require(archive.read_entry(index) == after, "Coach PLAY readback mismatch")
            rows.append(dict(team=receipt["team"], entry=index, profile=receipt["automatic_profile"],
                             resource_before_sha256=hashlib.sha256(before).hexdigest(),
                             resource_after_sha256=hashlib.sha256(after).hexdigest(),
                             virtual_offset=offset, profile_size=PROFILE_SIZE, changed_bytes=changed,
                             readback_verified=True))
    return dict(schema="nfl2k5_automatic_coach_resources/v1", profiles=rows,
                changed_bytes=sum(r["changed_bytes"] for r in rows), resource_growth=0,
                all_preflighted=True, readback_verified=True)


def apply_profiles_to_image(image, *, tendencies=None, progress=None):
    return write_profiles(image, plan_profiles(image, tendencies=tendencies, progress=progress))


def main(argv=None):
    """Development XBE component CLI; Studio also builds the PLAY resources."""
    import argparse
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    parser.add_argument("operation", choices=("status", "apply"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args(argv)
    try:
        with args.source.open("rb") as stream:
            payload = stream.read(12_300_289)
        require(len(payload) <= 12_300_288, "Expected a bounded XBE, not a disc")
        if args.operation == "status":
            value = status(payload)
            print(json.dumps(dict(status=value)))
            return 2 if value == "foreign" else 0
        require(args.output is not None and args.output.resolve() != args.source.resolve(),
                "Apply requires a new output XBE; use Studio Build for disc resources")
        result, receipt = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(result)
        require(args.output.read_bytes() == result, "Executable readback failed")
        print(json.dumps(receipt, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Coach AI refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
