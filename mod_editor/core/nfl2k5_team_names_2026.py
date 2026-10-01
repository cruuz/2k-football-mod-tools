"""2026 team identity text on every screen. EXPERIMENTAL / UNWITNESSED.

Every team name the game draws comes from the main ROST (the XBE holds no team names; the STRG banks resolve
ROST names). This option writes the 2026 values into the ROST so every screen shows them, full length:
Los Angeles Rams (LAR), Los Angeles Chargers (LAC), Las Vegas Raiders (LV), Arizona Cardinals (ARI) and the
Washington Commanders. The playbook list shows Commanders too.

Room. The ROST string region is packed and its zero tail is not free (the 2026 season template and the runtime
use it), so nothing grows. Each changed team's five identity strings are one contiguous retail run; the run is
rewritten as one piece and the pointers into it move. Where the full names need more room, the identity
abbreviation and the city abbreviation (always the same 2026 code) share one allocation, and Washington's label
nickname points at the identity nickname; its old 18-byte label allocation is cleared. Every reference into a
run is checked before and after (only the team's own pointer fields may point into it).

Engine keys. Two strings stay retail: the asset code (+0x10C, every team file name and the menu colour table)
and the label abbreviation ([+0x110]+4, the playbook file name "%s-pb.iff"). The identity abbreviation (+0x108)
and the identity nickname (+0x104) are renamed; the places the game used them as keys are patched in place in
default.xbe (xbe_sites; PROVED OFFLINE on the retail XBE, the game's own code under Unicorn in the tests):

* the franchise and season schedule generator (0x2BEA40; four retail callers and the preseason option's code)
  and the Thanksgiving hosts lookup (0x2BEA70; its two callers pass the table's DAL and DET entries) find each
  team of the code table (0xE9A45C) by the asset code instead of the abbreviation, so the table holds asset codes;
* loading a saved custom playbook (the loop at 0xE9AC0) finds the team whose label abbreviation matches (the key
  the save was written with) instead of the identity abbreviation;
* the ESPN 25th Anniversary lookup (0x20C4E0) compares each team nickname through an alias helper written over
  the dead find-team-by-abbreviation routine 0xC03F0 (no caller, no pointer, no relative branch in retail), so
  the moment selector "redskins" finds the Commanders as well as the Redskins;
* the label relink in the team copy (0xBFBD0) is left alone: its three callers copy only created and historic
  teams (0x16D254 and 0x16E8E1 import a created team; 0x2D1891 is the Crib's historic load).

Dallas road uniforms. The game swaps the uniform sides (the visitor in its home, dark set) when Dallas is at home,
and when Dallas visits the teams that wear white at home against it: WAS and TEN in 2004 (match setup 0x6160F,
Team Select preview 0x31F830, both comparing identity abbreviations with literals). The 2026 rule (the 2026
uniform schedule, found by job d5): Dallas wears navy only at HOU, IND and LAR, and white everywhere else on the
road, Washington included. Both blocks are rewritten in place to compare asset codes (stable across every roster).

Menu colours. The menus colour each team from an XBE .rdata table (0x4E7FE0, 80 rows of 28 bytes keyed by the asset
code; the menu background, primary, secondary, accent and translucent background). The 32 teams and the NFL, AFC and
NFC rows take their 2026 colours from the sourced palette (data/nfl2k5_team_colours_2026.json); the key pointer stays.

Old saves keep working (their rosters carry the 2004 strings, which every patched key path still accepts) and keep
the names they were made with. Off keeps retail. Historic ROSTs, STRG, audio, art codes and saves are not written.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Callable

from . import nfl2k5_roster_records as rr

MANIFEST = Path(__file__).resolve().parents[2] / "data/nfl2k5_team_names_2026.json"
COLOURS = Path(__file__).resolve().parents[2] / "data/nfl2k5_team_colours_2026.json"
COLOURS_SHA256 = "82e5b884299527322069d402175f9a967f60877635c47d364893b6456682321a"
COLOUR_TABLE, COLOUR_STRIDE, COLOUR_ROWS = 0x4E7FE0, 0x1C, 80
MANIFEST_SHA256 = "ff48f623aba3ed7a3cd8b192ad874b8c82deec0cc21f5dddc2b5ce28bfd27049"
SCHEMA = "nfl2k5_team_names_2026/v3"
OWNER = "nfl2k5_team_names_2026"
ROST_OUTER_INDEX = 5
TEAM_CITY_ABBREVIATION = 0x13C
TEAM_FIELDS = {"nickname": 0x104, "abbreviation": 0x108, "asset_code": 0x10C, "city": 0x138, "city_abbreviation": 0x13C}
LABEL_FIELDS = {"nickname": 0, "abbreviation": 4}
# (domain, field) pairs the engine uses as file names or table keys: never renamed.
ENGINE_KEY_FIELDS = frozenset({("team", "asset_code"), ("team_label", "abbreviation")})
# (domain, field) pairs the engine used as lookup keys: renamed, with the XBE key paths below.
KEYED_FIELDS = frozenset({("team", "abbreviation"), ("team", "nickname")})

WCSCMP_I = 0x30B90         # case-insensitive wide compare, 0 = equal (ecx, edx)
WCS_EQUAL = 0x30C40        # wide equality, nonzero = equal (ecx, edx)
PLAYBOOK_SLOT = 0xE2F10    # playbook slot i -> 0xB75A40 + i * 0x13390
ROSTER_ROOT = 0xB72918
SCHEDULE_KEY_LOAD = 0x2BEA4A       # 0x2BEA40: code table entry -> team index
THANKSGIVING_KEY_LOAD = 0x2BEA7D   # 0x2BEA70: code table entry -> team (its only callers: DAL and DET hosts)
CODE_TABLE = 0xE9A45C      # 32 inline 8-byte wide codes, pointed at by 0xACF038 and 0xACEE38
CODE_TABLE_ORDER = ("STL", "SF", "SEA", "ARZ", "CHI", "GB", "MIN", "DET", "TB", "NO", "ATL", "CAR", "PHI", "WAS",
                    "NYG", "DAL", "OAK", "DEN", "KC", "SD", "PIT", "BAL", "CLE", "CIN", "TEN", "IND", "JAX", "HOU",
                    "NE", "MIA", "NYJ", "BUF")
PLAYBOOK_LOOP, PLAYBOOK_LOOP_END = 0xE9AC0, 0xE9B07
ESPN25_COMPARE = 0x20C588
ALIAS_HELPER, ALIAS_HELPER_END = 0xC03F0, 0xC044D
DALLAS = "DAL"
DALLAS_ROAD_DARK_AT = ("HOU", "IND", "LAR")   # 2026 (d5, the 2026 uniform schedule); retail: WAS, TEN
MATCH_RULE, MATCH_RULE_END = 0x6160F, 0x61670          # game setup: esi = swap the uniform sides
PREVIEW_RULE, PREVIEW_RULE_END = 0x31F830, 0x31F891    # Team Select preview: edi/esi = side letters
AWAY_ASSET, HOME_ASSET = 0xB30B64, 0xB30970            # the match's away and home asset code pointers
PREVIEW_JOIN, PREVIEW_SIDES, PREVIEW_DONE = 0x31F8A5, 0xEA2CDC, 0x31F8AA
RETAIL_MATCH_RULE = bytes.fromhex(
    "8b15600bb300b94810e60033f6e81ff6fcff85c074328b156c09b300b95010e600e80bf6fcff85c07405be010000008b156c09b300"
    "b95810e600e8f2f5fcff85c07405be010000008b156c09b300b94810e600e8d9f5fcff85c07405be01000000")
RETAIL_PREVIEW_RULE = bytes.fromhex(
    "8b9108010000b9e42cea00e80014d1ff85c074328b9508010000b9ec2cea00e8ec13d1ff85c075148b9508010000b9f42cea00e8d8"
    "13d1ff85c0740abfdc2cea00bee02cea008b9508010000b9e42cea00e8ba13d1ff85c07420bfdc2cea00eb14")
RETAIL_PLAYBOOK_LOOP = bytes.fromhex(
    "83fbff741785db7c133bd87d0f8b411c8bf369f6f401000003f0eb0233f68bcfe82b94ffff8b40308b8e080100008bd0e84b71f4ff"
    "85c08b0d1829b70075088b4118433bd87cb9")
RETAIL_ALIAS_HELPER = bytes.fromhex(
    "538bd98b0d1829b7008b4118565733ff85c07e3d83ffff743085ff7c2c3bf87d288b511c8bf769f6f401000003f285f674178b8e08"
    "0100008bd3e86107f7ff85c074148b0d1829b7008b4118473bf87cc35f5e33c05bc35f8bc65e5bc3")


class TeamNamesError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamNamesError(message)


def _call(at: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (at + 5))


def _wide(text: str) -> bytes:
    return (text + "\0").encode("utf-16le")


def check_engine_keys(data: dict[str, Any]) -> None:
    """Refuse a manifest that renames a string the engine uses as a file name or table key."""
    listed = {tuple(pair) for pair in data["engine_keys"]["kept_retail"]}
    _require(listed == ENGINE_KEY_FIELDS, "2026 team-name manifest lists a different set of engine keys")
    for team in data["teams"]:
        for field in ("asset_code", "label_abbreviation"):
            _require(team["written"][field] == team["retail"][field],
                     f"team {team['index']} {field} is an engine key and must stay {team['retail'][field]!r}")
    for block in data["blocks"]:
        for item in block["written"]:
            for field in item["fields"]:
                domain, index, name = field.split(".")
                _require((domain, name) not in ENGINE_KEY_FIELDS or block["id"] == f"team.{index}",
                         f"{field} is an engine key and must stay in its own team's run")
                if (domain, name) in ENGINE_KEY_FIELDS:
                    team = data["teams"][int(index)]
                    _require(item["text"] == team["retail"][name], f"{field} is an engine key and must keep its text")


def manifest() -> dict[str, Any]:
    raw = MANIFEST.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256,
             "2026 team-name manifest differs from its verified allocation map")
    data = json.loads(raw)
    _require(data.get("schema") == SCHEMA, "unsupported 2026 team-name manifest")
    check_engine_keys(data)
    return data


def colours() -> dict[str, Any]:
    raw = COLOURS.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == COLOURS_SHA256, "2026 team colour table differs from its verified rows")
    data = json.loads(raw)
    _require(data.get("schema") == "nfl2k5_team_colours_2026/v1", "unsupported 2026 team colour table")
    return data


_colour_data = colours   # the verified rows, for callers whose ``colours`` is a switch


def _colour_row(values: dict[str, Any]) -> bytes:
    """The 24 bytes after the key pointer: scale, primary, secondary, two flags, accent, background."""
    return struct.pack("<fIIHHII", values["scale"], int(values["primary"], 16), int(values["secondary"], 16),
                       values["flag10"], values["flag12"], int(values["accent"], 16), int(values["background"], 16))


def cells(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Per changed team and field: retail and written text (the Team Identity view)."""
    data = data or manifest()
    out = []
    for team in data["teams"]:
        if team["retail"] == team["written"]:
            continue
        for field in TEAM_FIELDS:
            out.append({"team_index": team["index"], "domain": "team", "field": field,
                        "retail": team["retail"][field], "desired": team["written"][field],
                        "written": team["written"][field]})
        for field in LABEL_FIELDS:
            out.append({"team_index": team["index"], "domain": "team_label", "field": field,
                        "retail": team["retail"][f"label_{field}"], "desired": team["written"][f"label_{field}"],
                        "written": team["written"][f"label_{field}"]})
    return out


# ------------------------------------------------------------------------------------------------ ROST
def _relative(body: bytes, field: int) -> int | None:
    _require(0 <= field <= len(body) - 4, "team-name pointer field outside ROST")
    value = struct.unpack_from("<i", body, field)[0]
    target = field + value - 1 if value else None
    _require(target is None or 0 <= target < len(body), "team-name pointer outside ROST")
    return target


def _text_references(body: bytes) -> list[tuple[int, int]]:
    # The proved UTF-16 pointer domains (roster_text_reference_counts): every known reader, interior aliases too.
    domains = ((0x00, 0x54, (0x10, 0x14)), (0x08, 0x54, (0x10, 0x14)),
               (0x10, 0x80, (0, 8, 12, 16, 20)),
               (0x18, 0x1F4, (0x104, 0x108, 0x10C, 0x138, 0x13C)),
               (0x20, 8, (0,)), (0x30, 0xA8, (0, 4, 8, 12, 16)),
               (0x48, 8, (0, 4)), (0x50, 8, (0, 4)), (0x58, 16, (12,)))
    refs = []
    for offset, stride, fields in domains:
        count = struct.unpack_from("<I", body, 0x40 + offset)[0]
        table = _relative(body, 0x44 + offset)
        _require(count <= 100000 and (not count or table is not None and
                 table + count * stride <= len(body)), "ROST text table outside its fixed body")
        for index in range(count):
            for relative in fields:
                field = table + index * stride + relative
                target = _relative(body, field)
                if target is not None:
                    refs.append((field, target))
    return refs


def _layout_bytes(items: list[dict[str, Any]], size: int) -> bytes:
    out = bytearray(size)
    for item in items:
        raw = _wide(item["text"])
        _require(item["offset"] % 2 == 0 and item["offset"] + len(raw) <= size, "team-name layout outside its run")
        out[item["offset"]:item["offset"] + len(raw)] = raw
    return bytes(out)


def _targets(block: dict[str, Any], state: str) -> dict[str, int]:
    return {field: block["start"] + item["offset"] for item in block[state] for field in item["fields"]}


def _plan(data: dict[str, Any]) -> tuple[dict[str, int], dict[str, int], list[tuple[int, int, bytes, bytes]]]:
    retail_targets, written_targets, runs = {}, {}, []
    for block in data["blocks"]:
        retail_targets.update(_targets(block, "retail"))
        written_targets.update(_targets(block, "written"))
        runs.append((block["start"], block["size"], _layout_bytes(block["retail"], block["size"]),
                     _layout_bytes(block["written"], block["size"])))
    _require(set(retail_targets) == set(data["pointers"]) == set(written_targets),
             "2026 team-name manifest pointer sets differ")
    ends = sorted((start, start + size) for start, size, _r, _w in runs)
    _require(all(a[1] <= b[0] for a, b in zip(ends, ends[1:])), "2026 team-name runs overlap")
    return retail_targets, written_targets, runs


def _inspect(payload: bytes, data: dict[str, Any]) -> str:
    _require(len(payload) == data["resource_size"], "not the main disc ROST resource")
    _require(payload[:32].hex() == data["resource_header_hex"], "foreign ROST wrapper")
    body = payload[32:]
    _require(body[:64].hex() == data["body_prefix_hex"], "foreign ROST preamble")
    for pin in data["structure_pins"]:
        raw = bytes.fromhex(pin["hex"])
        _require(body[pin["offset"]:pin["offset"] + len(raw)] == raw, "foreign team or team-label table")
    retail_targets, written_targets, runs = _plan(data)
    pointers = data["pointers"]
    actual = {name: _relative(body, field) for name, field in pointers.items()}
    if actual == retail_targets:
        state = "retail"
    elif actual == written_targets:
        state = "applied"
    else:
        raise TeamNamesError("foreign or mixed team-name pointers")
    for start, size, retail_bytes, written_bytes in runs:
        _require(body[start:start + size] == (retail_bytes if state == "retail" else written_bytes),
                 "foreign team-name run")
    own = set(pointers.values())
    for field, target in _text_references(body):
        for start, size, _r, _w in runs:
            if start <= target < start + size:
                _require(field in own, "a team-name run has a foreign or interior reference")
    return state


def status(payload: bytes) -> str:
    """retail / applied / foreign for a complete main ROST resource."""
    try:
        return _inspect(payload, manifest())
    except (ValueError, OSError, KeyError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Validate every owned run and pointer before returning a modified private byte copy."""
    data = manifest()
    state = _inspect(payload, data)
    retail_targets, written_targets, runs = _plan(data)
    out = bytearray(payload)
    for start, size, _retail_bytes, written_bytes in runs:
        out[32 + start:32 + start + size] = written_bytes
    for name, field in data["pointers"].items():
        struct.pack_into("<i", out, 32 + field, written_targets[name] - field + 1)
    result = bytes(out)
    _require(_inspect(result, data) == "applied", "2026 team-name readback failed")
    changed = [dict(team=t["index"], full_name=t["full_name"],
                    **{k: v for k, v in t["written"].items() if v != t["retail"][k]})
               for t in data["teams"] if t["written"] != t["retail"]]
    moved = sum(1 for n in data["pointers"] if written_targets[n] != retail_targets[n])
    return result, {"schema": data["schema"], "status": "applied", "already_applied": state == "applied",
                    "experimental": True, "witnessed": False, "outer_index": ROST_OUTER_INDEX,
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "teams": changed, "runs": [dict(body_offset=s, size=n) for s, n, _a, _b in runs],
                    "changed_runs": 0 if state == "applied" else len(runs),
                    "pointers_moved": 0 if state == "applied" else moved,
                    "growth_bytes": 0, "strg_writes": 0,
                    "engine_keys_retail": [f"{d}.{f}" for d, f in sorted(ENGINE_KEY_FIELDS)],
                    "note": "Full 2026 names in the existing runs; the asset code and the label abbreviation stay "
                            "retail; new disc rosters only, existing saves keep their names."}


def read_team_identities(payload: bytes, *, enabled: bool = False) -> list[dict[str, Any]]:
    """Team Identity reads actual source or planned strings, never display-only aliases."""
    if enabled:
        payload, _receipt = apply(payload)
    _require(len(payload) == rr.RESOURCE_SIZE and payload[:4] == b"ROST", "not a disc ROST")
    doc = rr.RosterDocument(payload[32:])
    return [{"index": team.index, "city": team.city, "nickname": team.nickname,
             "abbreviation": team.abbreviation,
             "city_abbreviation": doc._string_at(team.offset + TEAM_CITY_ABBREVIATION),
             "display": f"{team.city} {team.nickname}"}
            for team in doc.teams[:32]]


def catalog_overrides(catalog, *, enabled: bool = False,
                      value_lookup: Callable[[Any], str] | None = None) -> dict[str, str]:
    """Values for the protected Studio facade's text_value() when the option is on.

    The catalog maps Team Identity to the same ROST cells. Conflicting manual edits refuse explicitly.
    Historic resources never receive aliases. This is a preview; the Build pass writes the runs.
    """
    if not enabled:
        return {}
    assets = {asset.asset_id: asset for asset in catalog.assets}
    values, states = {}, set()
    for cell in cells():
        key = f"nfl2k5.text.rost.5.{cell['domain']}.{cell['team_index']}.{cell['field']}"
        asset = assets.get(key)
        _require(asset is not None, f"Team Identity lacks {key}")
        current = value_lookup(asset) if value_lookup else asset.value
        _require(current in (cell["retail"], cell["written"]), f"2026 names conflict with a manual edit to {asset.label}")
        if cell["retail"] != cell["written"]:
            states.add("retail" if current == cell["retail"] else "applied")
        values[key] = cell["written"]
    _require(len(states) == 1, "mixed retail and 2026 catalog names")
    return values


def image_status(path: Path | str) -> str:
    from . import nfl2k5_roster_arena as arena
    with rr._outer_image()(path) as archive:
        if arena.grown_outer(archive, ROST_OUTER_INDEX):
            try:
                return status(arena.inspection_resource(archive, ROST_OUTER_INDEX))
            except ValueError:
                return "foreign"
        entry = archive.entries[ROST_OUTER_INDEX]
        if entry.size != rr.RESOURCE_SIZE:
            return "foreign"
        return status(archive.read(entry.virtual_offset, entry.size))


def apply_to_image(path: Path | str, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Build adapter, ROST half: write only the caller's disposable image copy, never a save."""
    with rr._outer_image()(path, writable=True) as archive:
        entry = archive.entries[ROST_OUTER_INDEX]
        _require(entry.size == rr.RESOURCE_SIZE, "not the main roster allocation")
        before = archive.read(entry.virtual_offset, entry.size)
        after, receipt = apply(before)
        if after != before:
            if progress:
                progress("Writing the 2026 team names")
            _require(archive.read(entry.virtual_offset, entry.size) == before,
                     "roster changed after team-name preview")
            _require(archive.write(entry.virtual_offset, after) == len(after), "short team-name write")
            _require(archive.read(entry.virtual_offset, entry.size) == after, "team-name image readback differs")
    return {**receipt, "virtual_offset": entry.virtual_offset}


# ------------------------------------------------------------------------------------------------ XBE keys
def _code_table(data: dict[str, Any]) -> tuple[bytes, bytes]:
    by_code = {t["retail"]["abbreviation"]: t["retail"]["asset_code"] for t in data["teams"]}
    _require(sorted(by_code) == sorted(CODE_TABLE_ORDER), "schedule code table and manifest teams differ")
    retail = b"".join(_wide(code).ljust(8, b"\0") for code in CODE_TABLE_ORDER)
    keyed = b"".join(_wide(by_code[code]).ljust(8, b"\0") for code in CODE_TABLE_ORDER)
    return retail, keyed


def _playbook_loop() -> bytes:
    at = PLAYBOOK_LOOP
    code = bytearray()
    code += bytes.fromhex("8b411c")                 # mov eax,[ecx+0x1c]      team table
    code += bytes.fromhex("8bf3")                   # mov esi,ebx
    code += bytes.fromhex("69f6f4010000")           # imul esi,esi,0x1f4
    code += bytes.fromhex("03f0")                   # add esi,eax              team
    code += bytes.fromhex("8bcf")                   # mov ecx,edi
    code += _call(at + len(code), PLAYBOOK_SLOT)    # call 0xe2f10             slot
    code += bytes.fromhex("8b5030")                 # mov edx,[eax+0x30]       the saved abbreviation
    code += bytes.fromhex("8b8e10010000")           # mov ecx,[esi+0x110]      label
    code += bytes.fromhex("33c0")                   # xor eax,eax
    code += bytes.fromhex("85c9")                   # test ecx,ecx
    code += bytes.fromhex("7408")                   # je +8 (no label: not this team)
    code += bytes.fromhex("8b4904")                 # mov ecx,[ecx+4]          label abbreviation (the save key)
    code += _call(at + len(code), WCS_EQUAL)        # call 0x30c40
    code += bytes.fromhex("85c0")                   # test eax,eax
    code += bytes.fromhex("8b0d") + struct.pack("<I", ROSTER_ROOT)   # mov ecx,[0xb72918]
    code += bytes([0x75, PLAYBOOK_LOOP_END - (at + len(code) + 2)])  # jne 0xe9b07 (found)
    code += bytes.fromhex("8b4118")                 # mov eax,[ecx+0x18]
    code += bytes.fromhex("43")                     # inc ebx
    code += bytes.fromhex("3bd8")                   # cmp ebx,eax
    code += bytes([0x7C, (PLAYBOOK_LOOP - (at + len(code) + 2)) & 0xFF])   # jl loop
    _require(len(code) <= PLAYBOOK_LOOP_END - PLAYBOOK_LOOP, "playbook loop exceeds its retail bytes")
    return bytes(code).ljust(PLAYBOOK_LOOP_END - PLAYBOOK_LOOP, b"\x90")


def _alias_helper(data: dict[str, Any]) -> bytes:
    pairs = [(t["written"]["nickname"], t["retail"]["nickname"]) for t in data["teams"]
             if t["written"]["nickname"] != t["retail"]["nickname"]]
    _require(len(pairs) == 1, "the in-place ESPN25 alias holds exactly one renamed nickname")
    new, old = pairs[0]
    at, strings = ALIAS_HELPER, ALIAS_HELPER + 0x28
    code = bytearray()
    code += bytes.fromhex("5152")                   # push ecx; push edx       (team nickname, selector)
    code += _call(at + len(code), WCSCMP_I)         # the retail compare first
    code += bytes.fromhex("5a59")                   # pop edx; pop ecx
    code += bytes.fromhex("85c0741a")               # test eax,eax; je ret     equal
    code += bytes.fromhex("52")                     # push edx
    code += b"\xba" + struct.pack("<I", strings)    # mov edx,<2026 nickname>
    code += _call(at + len(code), WCSCMP_I)         # is this team the renamed one?
    code += bytes.fromhex("59")                     # pop ecx                  selector
    code += bytes.fromhex("85c0750a")               # test eax,eax; jne ret    not equal
    code += b"\xba" + struct.pack("<I", strings + len(_wide(new)))   # mov edx,<2004 nickname>
    code += _call(at + len(code), WCSCMP_I)         # does the selector name its 2004 nickname?
    code += b"\xc3"
    _require(len(code) == 0x28, "alias helper encoding drifted")
    body = bytes(code) + _wide(new) + _wide(old)
    _require(len(body) <= ALIAS_HELPER_END - ALIAS_HELPER, "alias helper exceeds the dead routine")
    return body.ljust(ALIAS_HELPER_END - ALIAS_HELPER, b"\xcc")


def _code_dword(code: str) -> bytes:
    _require(len(code) == 2, "asset codes are two characters")
    return code.encode("utf-16le")


def _dallas_codes(data: dict[str, Any]) -> tuple[bytes, list[bytes]]:
    by_abbr = {t["written"]["abbreviation"]: t["retail"]["asset_code"] for t in data["teams"]}
    return _code_dword(by_abbr[DALLAS]), [_code_dword(by_abbr[a]) for a in DALLAS_ROAD_DARK_AT]


class _Asm:
    """Tiny forward-label assembler for short jumps (rel8) inside one in-place block."""

    def __init__(self, va: int):
        self.va, self.code, self.fix, self.labels = va, bytearray(), [], {}

    def raw(self, data: bytes) -> None:
        self.code += data

    def jcc(self, opcode: int, label: str) -> None:
        self.code += bytes([opcode, 0])
        self.fix.append((len(self.code) - 1, label))

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def done(self, size: int, message: str) -> bytes:
        for at, name in self.fix:
            target = self.labels[name] if isinstance(name, str) else name - self.va
            rel = target - (at + 1)
            _require(-128 <= rel <= 127, "short jump out of range")
            self.code[at] = rel & 0xFF
        _require(len(self.code) <= size, message)
        return bytes(self.code).ljust(size, b"\x90")


def _match_rule(data: dict[str, Any]) -> bytes:
    dal, dark = _dallas_codes(data)
    a = _Asm(MATCH_RULE)
    a.raw(bytes.fromhex("33f6"))                                    # xor esi,esi          (no swap)
    a.raw(b"\xa1" + struct.pack("<I", AWAY_ASSET))                  # mov eax,[away asset code]
    a.raw(b"\x8b\x15" + struct.pack("<I", HOME_ASSET))             # mov edx,[home asset code]
    a.raw(b"\x81\x38" + dal)                                       # cmp dword [eax],"07"  (Dallas visiting?)
    a.jcc(0x75, "home")
    a.raw(bytes.fromhex("8b02"))                                    # mov eax,[edx]
    for code in dark:
        a.raw(b"\x3d" + code)                                       # cmp eax,<home that wears white vs Dallas>
        a.jcc(0x74, "swap")
    a.label("home")
    a.raw(b"\x81\x3a" + dal)                                       # cmp dword [edx],"07"  (Dallas at home?)
    a.jcc(0x75, "end")
    a.label("swap")
    a.raw(b"\x46")                                                  # inc esi              (swap the sides)
    a.label("end")
    return a.done(MATCH_RULE_END - MATCH_RULE, "match uniform rule exceeds its retail bytes")


def _preview_rule(data: dict[str, Any]) -> bytes:
    dal, dark = _dallas_codes(data)
    a = _Asm(PREVIEW_RULE)
    a.raw(bytes.fromhex("8b910c010000"))                            # mov edx,[ecx+0x10c]  right (visiting) team
    a.raw(b"\x81\x3a" + dal)                                       # cmp dword [edx],"07"
    a.raw(bytes.fromhex("8b950c010000"))                            # mov edx,[ebp+0x10c]  left (home) team
    a.jcc(0x75, "home")
    a.raw(bytes.fromhex("8b02"))                                    # mov eax,[edx]
    for code in dark:
        a.raw(b"\x3d" + code)
        a.jcc(0x74, "swap")
    a.label("home")
    a.raw(b"\x81\x3a" + dal)                                       # cmp dword [edx],"07"
    a.jcc(0x75, PREVIEW_DONE)                                       # no swap: continue at 0x31f8aa
    a.label("swap")
    a.raw(b"\xbf" + struct.pack("<I", PREVIEW_SIDES))               # mov edi,"h"
    a.jcc(0xEB, PREVIEW_JOIN)                                       # jmp 0x31f8a5 (esi = "a")
    return a.done(PREVIEW_RULE_END - PREVIEW_RULE, "preview uniform rule exceeds its retail bytes")


def xbe_sites(data: dict[str, Any] | None = None, *, colours: bool = True) -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, retail bytes, applied bytes) of every in-place XBE edit; ``colours=False`` leaves out the 35
    menu colour rows (the key paths and the Dallas rule only)."""
    data = data or manifest()
    retail_table, keyed_table = _code_table(data)
    table = _colour_data()
    rows = [(f"menu_colours.{row['code']}", COLOUR_TABLE + row["entry"] * COLOUR_STRIDE + 4,
             _colour_row(row["retail"]), _colour_row(row["written"])) for row in table["rows"]]
    _require(all(0 <= row["entry"] < COLOUR_ROWS for row in table["rows"]), "colour row outside the table")
    return [
        ("schedule_key", SCHEDULE_KEY_LOAD, bytes.fromhex("8b9008010000"), bytes.fromhex("8b900c010000")),
        ("thanksgiving_key", THANKSGIVING_KEY_LOAD, bytes.fromhex("8b9708010000"), bytes.fromhex("8b970c010000")),
        ("schedule_codes", CODE_TABLE, retail_table, keyed_table),
        ("user_playbook_team", PLAYBOOK_LOOP, RETAIL_PLAYBOOK_LOOP, _playbook_loop()),
        ("espn25_nickname_compare", ESPN25_COMPARE, _call(ESPN25_COMPARE, WCSCMP_I),
         _call(ESPN25_COMPARE, ALIAS_HELPER)),
        ("espn25_alias_helper", ALIAS_HELPER, RETAIL_ALIAS_HELPER, _alias_helper(data)),
        ("dallas_road_uniform_match", MATCH_RULE, RETAIL_MATCH_RULE, _match_rule(data)),
        ("dallas_road_uniform_preview", PREVIEW_RULE, RETAIL_PREVIEW_RULE, _preview_rule(data)),
    ] + (rows if colours else [])


def _xbe_image(payload: bytes):
    from .nfl2k5_cave_oracle import XbeImage
    return XbeImage(payload)


def _site_states(payload: bytes) -> tuple[set[str], set[str]]:
    """(states of the key-path and Dallas sites, states of the menu colour rows)."""
    image = _xbe_image(payload)
    keys, rows = set(), set()
    for label, va, before, after in xbe_sites():
        raw = image.read(va, len(before))
        state = "retail" if raw == before else "applied" if raw == after else "foreign"
        (rows if label.startswith("menu_colours.") else keys).add(state)
    return keys, rows


def xbe_colours_written(payload: bytes) -> bool:
    """Whether the 35 menu colour rows hold their 2026 values (the key paths may be installed without them)."""
    try:
        return _site_states(payload)[1] == {"applied"}
    except (ValueError, KeyError, struct.error):
        return False


def xbe_status(payload: bytes, *, colours: bool | None = None) -> str:
    """retail / applied / foreign for default.xbe (retail or any composed build: only these bytes are read).

    ``colours=True`` asks for the key paths with the menu colour rows, ``False`` for the key paths with the rows
    still retail, and ``None`` accepts either complete form. Anything partial is foreign."""
    try:
        keys, rows = _site_states(payload)
    except (ValueError, KeyError, struct.error):
        return "foreign"
    if len(keys) != 1 or len(rows) != 1 or "foreign" in keys | rows:
        return "foreign"
    key, row = keys.pop(), rows.pop()
    if key == "retail":
        return "retail" if row == "retail" else "foreign"
    wanted = {True: {"applied"}, False: {"retail"}, None: {"applied", "retail"}}[colours]
    return "applied" if row in wanted else "foreign"


def apply_xbe(payload: bytes, *, colours: bool = True) -> tuple[bytes, dict[str, Any]]:
    """Install the key paths (and, with ``colours``, the 35 menu colour rows) on a retail-state copy, or replay an
    applied copy of the same form unchanged."""
    from .nfl2k5_bump_strength import _sections, section_digest
    state = xbe_status(payload, colours=colours)
    _require(state in ("retail", "applied"), "default.xbe has foreign or mixed 2026 team-name key paths")
    sites = xbe_sites(colours=colours)
    common = dict(experimental=True, witnessed=False, menu_colours=colours,
                  sites=[dict(label=label, va=hex(va), size=len(before)) for label, va, before, _after in sites])
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0)
    image = _xbe_image(payload)
    buffer = bytearray(payload)
    for _label, va, before, after in sites:
        at = image.offset(va, len(before))
        buffer[at:at + len(before)] = after
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    _require(xbe_status(result, colours=colours) == "applied", "2026 team-name key paths readback failed")
    return result, dict(common, status="applied", changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


def xbe_reservations(payload: bytes) -> list[dict[str, Any]]:
    """The cave manifest's ownership rows: every in-place byte this option writes in default.xbe."""
    _require(xbe_status(payload) == "applied", "2026 team-name key paths are not installed")
    return [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                 basis=f"in-place {label} (no runtime space)")
            for label, va, before, _after in xbe_sites(colours=xbe_colours_written(payload))]


class XbePatch:
    """Adapter for the shared executable gates and the cave manifest's ownership recorder."""
    OWNER = OWNER
    REQUESTS = ()
    apply = staticmethod(apply_xbe)
    status = staticmethod(xbe_status)
    reservations = staticmethod(xbe_reservations)
