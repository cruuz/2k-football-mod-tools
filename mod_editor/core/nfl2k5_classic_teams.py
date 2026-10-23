"""Classic teams in Quick Game: the Anniversary team-seasons and new classic team-seasons (USA Xbox). EXPERIMENTAL /
UNWITNESSED.

Job ct1 (Noah, 2026-10-17): "add a few more classic teams for some of the better teams over the last decade that
aren't in 25th anniversary mode, with their proper stadium, uniforms, rosters, depth charts", then: every 25th
Anniversary team must be a selectable classic team too, and existing stadiums and kits are reused wherever the real
ones exist in the game.

How classic teams work (PROVED OFFLINE, see the h1 and ht reports): a classic team is a one-team ROST file in pack F
("h-<code>-<season>-<name>-<n>.iff"). Quick Game Team Select (option nfl2k5_historic_teams_quick_game) steps past
the last resident team into the roster's historic list (75 entries of 16 bytes, root +0x58/+0x5C) and imports the
picked file into the side's spare slot (USER1 home, USER2 away) with the game's own loader and importer (C1030).
Nothing is resident: the teams cost no main-roster players and no name bytes; two classic sides need the same 106
import vacancies an Anniversary moment needs (nfl2k5_spare_capacity.restore_import_floor keeps them).

This option:
- writes one new file per classic team-season (data/nfl2k5_classic_teams: 53 players, depth chart, ratings and
  appearance; the m1 team compiler, so names, own faces or none, star tags and special teams follow the Anniversary
  rules), with identity numbers 226..249 and 252 (moments use 176..225; the extra created teams 250/251 are skipped), its home venue row
  (the stadium record's id byte, which the importer maps to the main roster's row) and its kit (team +0x192 with a
  non-zero year pair at +0x15A, the same rule the Anniversary kits use);
- installs a small late allocator owner (read-only, executable page) holding four helpers and a 4-byte row per new
  team ({u16 season, u8 file digit, u8 retail entry whose franchise text and asset code it borrows});
- switches the Quick Game code to its classic variant: the list length becomes 75 + M + N (M = the moment
  team-seasons of nfl2k5_espn25_more_moments, read from its own table, N = the new teams), entry k < 75 is the roster's
  own entry, then the moment table, then the new rows; a moment entry loads its plain "h-" file even when the season
  route (HTS- files) is on.
Create a Team's own "Load Historic Team" list stays the retail 75. Franchise and season modes are unchanged.

Job sm1 (Noah, 2026-10-18, after the b775 video: "they should all be organized by date properly"): Team Select used to
step through the list in storage order (the retail 75 in franchise order, then the moments, then the classic rows). The
list is now one chronological run. The Quick Game code still steps a list POSITION k; the entry helper (ENTRY_SORTED)
turns k into the STORAGE index j whose rank is k, then falls into the unchanged entry body, so the stepping, the
remembered position, the loader and the label lookup keep working on storage indexes. Rank = position in the sort by
(season, franchise asset code, storage index): the season is the word at +0 of an entry, the asset code the two UTF-16
digits at +4 and +6 of the retail entry the team borrows, and the storage index (retail, moments, classic) breaks exact
ties, so a retail season and the moment of the same team-season sit side by side. The helper finds j by counting, for each
candidate, the entries that sort before it (149 entries: about 20 thousand key reads per button press). It needs no
table, which the all-owner allocator union has no room for (its read-only pages are full: this block may not grow past
288 bytes), and it needs no build-time year lookup, so a moment table or a classic row is ordered by what the executable
itself holds. Registers: it keeps EBX and clobbers the rest; the only call site (the loader's entry lookup) has no other
live register.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import struct

from . import nfl2k5_front_schemes as front
from . import nfl2k5_classic_face as classic_face
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/nfl2k5_classic_teams"
OWNER = "nfl2k5_classic_teams"
RETAIL_ENTRIES = 75                                # the roster's own historic list
# sm1: the helper block, repacked (offsets into the owned read-only block). total, cmp_total and fmt keep their bytes
# and move; ENTRY_KEY and ENTRY_SORTED are the chronological entry helper; ENTRY_BODY is the unchanged entry body.
OFF_TOTAL, OFF_CMP_TOTAL, OFF_FMT, OFF_KEY, OFF_SORTED, OFF_BODY = 0x00, 0x06, 0x0C, 0x27, 0x3E, 0x74
ROWS_OFFSET = 0xB4                                 # 25 four-byte rows follow the helpers
# b778-ss1: identities 250/251 belong to the two extra created teams. The classic list takes 226..249 and 252
# (the next byte-wide identity), so 25 rows need 280 of the 288 bytes and the created teams keep their numbers.
IDENTITIES = tuple([*range(226, 250), 252])
MAX_ROWS = len(IDENTITIES)                         # 25
RO_SIZE = 288                                      # the all-owner union holds 304 here and keeps 16 for a synthetic constant
REQUESTS = ((OWNER, "read_only", RO_SIZE, 16),)
FIRST_ID, LAST_ID = IDENTITIES[0], IDENTITIES[-1]  # free team identities: the ceiling for new files
FILE_NUMBER = 8                                    # the file-name digit (moments use 9)
FILLER = "ct1_classic_teams_end.bin"
UI_LABEL = "Classic teams in Quick Game"
BUILD_CAPTION = "Anniversary and classic team-seasons in Quick Game Team Select"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. With historic teams in Quick Game on, the list runs on past the 75 retail "
             "historic teams into every 25th Anniversary team-season and 25 classic teams of 2005-2025 plus the 2006 Seamen (season "
             "rosters, depth charts, their kit and home stadium). Needs the historic teams in Quick Game option.")
ROOT_PTR = 0xB72918
FMT_FILE = 0xE9F984


class ClassicTeamsError(ValueError):
    """Foreign prerequisites, invalid data or a failed read-back."""


def require(ok, message):
    if not ok:
        raise ClassicTeamsError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------------------------ data

class Data:
    def __init__(self, teams, rosters, appearance, presentation):
        self.teams, self.rosters, self.appearance, self.presentation = teams, rosters, appearance, presentation

    @classmethod
    def load(cls, folder=DATA_DIR):
        folder = Path(folder)
        teams = json.loads((folder / "teams.json").read_text(encoding="utf-8"))["teams"]
        presentation = json.loads((folder / "classic.json").read_text(encoding="utf-8"))["teams"]
        appearance = json.loads((folder / "appearance.json").read_text(encoding="utf-8"))["teams"]
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["teams"]
        rosters = {}
        for key in teams:
            raw = (folder / f"{key}.csv").read_bytes()
            require(sha(raw) == manifest[key]["csv_sha256"], f"{key}.csv differs from its generated manifest")
            rosters[key] = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        data = cls(teams, rosters, appearance, presentation)
        data.validate()
        return data

    def order(self):
        """Team-seasons in list order: by season, then key (the identity numbers follow it)."""
        return sorted(self.teams, key=lambda k: (self.teams[k]["season"], k))

    def validate(self):
        keys = self.order()
        require(0 < len(keys) <= MAX_ROWS, "classic team count outside the capacity")
        require(set(keys) == set(self.presentation) == set(self.appearance), "teams, classic.json and appearance differ")
        for key in keys:
            t, rows = self.teams[key], self.rosters[key]
            require(key == f"{t['selector']}_{t['season']}" or t.get("key") == key, f"{key}: key")
            require(len(rows) == 53, f"{key}: 53 players")
            require(len({int(r["jersey"]) for r in rows}) == 53, f"{key}: jersey numbers must be unique")
            looks = self.appearance[key]
            require(len(looks) == 53 and all(l["name"] == f"{r['first']} {r['last']}" for l, r in zip(looks, rows)),
                    f"{key}: appearance rows")
            kit = self.presentation[key]["kit"]
            require(kit in ("modern", "retail") or (type(kit) is int and 0 <= kit <= 14)
                    or (isinstance(kit, dict) and set(kit) == {"prefer", "fallback"}), f"{key}: kit")
            require(self.presentation[key]["stadium"] == "franchise", f"{key}: stadium")
            if "stadium_id" in self.presentation[key]:
                require(type(self.presentation[key]["stadium_id"]) is int
                        and 0 <= self.presentation[key]["stadium_id"] <= 255, f"{key}: stadium_id")
            if "stadium_info" in self.presentation[key]:
                require(isinstance(self.presentation[key]["stadium_info"], dict), f"{key}: stadium_info")

    def filename(self, key, prefix=""):
        t = self.teams[key]
        return f"{prefix}h-{t['asset_code']}-{t['season']}-{t['selector']}-{FILE_NUMBER}.iff"



def label_holder(main):
    """The main roster with the two empty created-team rows made into the Seamen's label holder. Quick Game's
    historic import copies the label of the resident team with the entry's asset code; both user rows take code 14,
    their own name as the label pair (nickname/abbreviation), so the last matching row names the imported team SEAMEN
    (Sarasota's abbreviation is SEA, whose playbook exists) without renaming any real team. The rows stay category 2
    with no players, so they remain hidden; only the label lookup sees them."""
    from . import nfl2k5_roster_records as rr
    body = bytearray(main[32:])
    doc = rr.RosterDocument(bytes(body))
    require(len(doc.teams) >= 34, "the main roster has no two created-team rows")
    for index in (32, 33):
        t = doc.teams[index].offset
        for field, text, capacity in ((0x104, "SEAMEN", 34), (0x108, "SEA", 12), (0x10C, "14", 6)):
            at = t + field + struct.unpack_from("<i", body, t + field)[0] - 1
            require(0 < at < len(body) - capacity, f"created-team row {index}: text outside the roster")
            raw = text.encode("utf-16le") + b"\0\0"
            require(len(raw) <= capacity, "created-team label text does not fit")
            body[at:at + capacity] = raw + bytes(capacity - len(raw))
        struct.pack_into("<i", body, t + 0x110, -11)   # label pair = this row's nickname and abbreviation
    result = main[:32] + bytes(body)
    check = rr.RosterDocument(result[32:])
    for index in (32, 33):
        t = check.teams[index].offset
        require(struct.unpack_from("<i", result, 32 + t + 0x110)[0] == -11, "label holder read-back")
        for field, text in ((0x104, "SEAMEN"), (0x108, "SEA"), (0x10C, "14")):
            at = 32 + t + field + struct.unpack_from("<i", result, 32 + t + field)[0] - 1
            require(result[at:at + 2 * len(text)] == text.encode("utf-16le"), "label holder text read-back")
    return result


# ------------------------------------------------------------------------------------------------- the executable

# The chronological entry helper: the key function and the ranking loop (77 bytes, OFF_KEY..OFF_BODY), assembled with GNU as
# (intel syntax) at its final offsets; its one variable is the list length, the imm8 marked below (the length is at most
# 151, and the loop counter is compared in DL). Source:
#   key:    call body; movzx ecx,word [edi]; shl ecx,8; mov cl,[eax+4]; shl ecx,8; mov cl,[eax+6]; mov eax,ecx; ret
#           (EAX = key of list entry EAX = season<<16 | the two asset code characters; the body returns EAX/EDI = the entry)
#   sorted: push ebx; mov ebp,eax; xor esi,esi
#     Lj:   mov eax,esi; call key; push eax; xor ebx,ebx; xor edx,edx
#     Li:   mov eax,edx; call key; cmp eax,[esp]; jb Lcount; ja Lnext; cmp edx,esi; jae Lnext
#     Lcount: inc ebx
#     Lnext:  inc edx; cmp dl,TOTAL; jb Li
#           pop eax; cmp ebx,ebp; je Ldone; inc esi; jmp Lj
#     Ldone: mov eax,esi; pop ebx; nop       ; falls into the entry body with EAX = the storage index
_SORT_TOTAL_MARK = bytes.fromhex("80fa7f")
_SORT_CODE = bytes.fromhex(
    "e8480000000fb70fc1e1088a4804c1e1088a480689c8c3"
    "5389c531f689f0e8ddffffff5031db31d289d0e8d1ffffff3b04247206770539f27301434280fa7f72e75839eb740346ebd389f05b90")


def helper_code(va, *, moment_table, moment_count, rows, default_fmt):
    """The owned bytes: total, cmp_total, fmt, the chronological entry helper (key, sorted) and the entry body, then one
    4-byte row per new team. rows: [(season, digit, retail entry index)]. The list length is a constant (the build checks
    the roster's own count is 75)."""
    require(len(rows) <= MAX_ROWS and 0 <= moment_count <= 50, "too many classic rows or moment team-seasons")
    root = struct.pack("<I", ROOT_PTR)
    p32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)  # noqa: E731
    total = RETAIL_ENTRIES + moment_count + len(rows)
    require(total <= 151, "the list length exceeds the ranking loop's byte counter")
    out = bytearray(b"\xcc" * ROWS_OFFSET)

    def put(offset, code, size):
        require(len(code) == size, "helper size drift")
        out[offset:offset + len(code)] = code
    # total: EAX = the list length (the roster's 75 + moments + classic rows); only EAX changes
    put(OFF_TOTAL, b"\xb8" + p32(total) + b"\xc3", OFF_CMP_TOTAL - OFF_TOTAL)
    # cmp_total: flags = cmp EAX, the list length (ECX is no longer loaded: no caller reads it)
    put(OFF_CMP_TOTAL, b"\x3d" + p32(total) + b"\xc3", OFF_FMT - OFF_CMP_TOTAL)
    # fmt: EDX = the file-name format; a moment entry (EDI inside the moment table) keeps the plain "h-" file
    end = moment_table + 16 * moment_count
    put(OFF_FMT, b"\xba" + p32(default_fmt) + b"\x81\xff" + p32(moment_table) + b"\x72\x0d"
        + b"\x81\xff" + p32(end) + b"\x73\x05" + b"\xba" + p32(FMT_FILE) + b"\xc3", OFF_KEY - OFF_FMT)
    # chronological entry helper (key + sorted): EAX = list position k -> storage index, then the entry body
    require(_SORT_CODE.count(_SORT_TOTAL_MARK) == 1, "sorted entry marker")
    put(OFF_KEY, _SORT_CODE.replace(_SORT_TOTAL_MARK, b"\x80\xfa" + bytes([total])), OFF_BODY - OFF_KEY)
    # entry body: EAX = a STORAGE index -> EAX = the entry (asset code at +4, franchise text at +12), EDI = season (+0) and digit (+2)
    entry = bytearray(b"\x8b\x0d" + root + bytes.fromhex("3b4158"))      # mov ecx,[root]; cmp eax,[ecx+58h]
    retail = bytes.fromhex("c1e004" "03415c" "8bf8" "c3")                 # shl eax,4; add eax,[ecx+5Ch]; mov edi,eax
    moment = bytes.fromhex("2b4158") + b"\x3d" + p32(moment_count)      # sub eax,[ecx+58h]; cmp eax,M
    moment_hit = bytes.fromhex("c1e004") + b"\x05" + p32(moment_table) + bytes.fromhex("8bf8c3")
    classic = (b"\x2d" + p32(moment_count) + b"\x8d\x3c\x85" + p32(va + ROWS_OFFSET)
               + bytes.fromhex("0fb64703" "c1e004" "03415c" "c3"))
    entry += b"\x73" + bytes([len(retail)]) + retail
    entry += moment + b"\x73" + bytes([len(moment_hit)]) + moment_hit + classic
    put(OFF_BODY, bytes(entry), ROWS_OFFSET - OFF_BODY)
    for season, digit, index in rows:
        require(0 <= index < 75 and 0 <= digit <= 9 and 1900 < season < 2100, "classic row")
        out.extend(struct.pack("<HBB", season, digit, index))
    return bytes(out).ljust(RO_SIZE, b"\0")


def allocation(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    require(len(rows) == 1 and rows[0]["kind"] == "read_only" and rows[0]["size"] == RO_SIZE,
            "the classic teams' owner is not allocated")
    return rows[0]


def reserved(payload):
    try:
        allocation(payload)
        return True
    except (ValueError, KeyError):
        return False


def reserve(payload):
    """A late owner: the build's own request set does not carry it, so it is appended to the sealed scale-out image
    (space.extend_scaleout proves no existing allocation moves). A union that already carries it is kept."""
    if reserved(payload):
        return payload, dict(status="already_reserved")
    return space.extend_scaleout(payload, REQUESTS)


def executable(payload, va):
    from .nfl2k5_bump_strength import _sections
    hit = [s for s in _sections(payload) if s.virtual_address <= va < s.virtual_address + s.raw_size]
    if len(hit) != 1:
        return False
    flags = struct.unpack_from("<I", payload, hit[0].header_offset)[0]
    return bool(flags & 0x4)                         # XBE section flag: executable


def moment_table(payload):
    """(table VA, team-season count) of the installed Anniversary moments, else (0, 0)."""
    from . import nfl2k5_espn25_more_moments as more
    try:
        if more.status(payload) != "applied":
            return 0, 0
        code, _data = more.allocations(payload)
    except (ValueError, KeyError, IndexError, struct.error):
        return 0, 0
    image = XbeImage(payload)
    va = code["va"] + more.TABLE_OFFSET
    count = 0
    while count < more.MAX_TEAMS and image.read(va + 16 * count, 2) != b"\0\0":
        count += 1
    return va, count


def xbe_status(payload):
    """'retail' (the owner reserved and empty), 'applied' (helpers installed and the Quick Game classic variant on),
    else 'foreign'."""
    from . import nfl2k5_historic_teams_quick_game as h1
    try:
        if not reserved(payload):
            return "retail" if h1.classic_status(payload) != "applied" else "foreign"
        a = allocation(payload)
        body = XbeImage(payload).read(a["va"], RO_SIZE)
        if body == bytes(RO_SIZE):
            return "retail" if h1.classic_status(payload) != "applied" else "foreign"
        rows = (len(body.rstrip(b"\0")) - ROWS_OFFSET + 3) // 4
        table, count = moment_table(payload)
        default = struct.unpack_from("<I", body, OFF_FMT + 1)[0]
        expected = helper_code(a["va"], moment_table=table, moment_count=count, default_fmt=default,
                               rows=[struct.unpack_from("<HBB", body, ROWS_OFFSET + 4 * i) for i in range(rows)])
        return "applied" if body == expected and h1.classic_status(payload) == "applied" else "foreign"
    except (ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def authored_kits():
    """The classic teams' authored kit document (data/nfl2k5_classic_teams/kits.json), validated in the shared
    moment-kit shape. It is kept out of the Anniversary data so the moment stage never expects these packages."""
    from . import nfl2k5_moment_kits as kits
    return kits.validate_document(json.loads((DATA_DIR / "kits.json").read_text(encoding="utf-8")))


def authored_kits_status(path):
    """'applied' when the classic teams' authored kit packages and cards are installed, 'retail' when none is,
    'foreign' otherwise."""
    from . import nfl2k5_moment_kits as kits
    try:
        doc = authored_kits()
        if not doc["kits"]:
            return "not_applicable"
        return kits.image_status(path, doc)
    except (ValueError, KeyError, IndexError, struct.error, OSError):
        return "foreign"


def install_authored_kits(path):
    """Install the classic teams' authored kit packages and aggregate cards before the classic files are compiled.
    Replay is a no-op; a partly installed or foreign kit refuses."""
    from . import nfl2k5_moment_kits as kits
    doc = authored_kits()
    if not doc["kits"]:
        return dict(status="none")
    state = kits.image_status(path, doc)
    if state == "applied":
        return dict(status="already_applied")
    require(state == "retail", f"classic teams: the authored kit is {state}")
    return dict(kits.apply_to_image(path, doc), status="applied")


def apply_xbe(payload, rows):
    """Install the helpers for these rows and switch Quick Game to the classic variant (after the season route)."""
    from . import nfl2k5_historic_teams_quick_game as h1
    state = xbe_status(payload)
    require(state in ("retail", "applied"), f"classic teams: the executable is {state}")
    require(h1.status(payload) == "applied", "classic teams need historic teams in Quick Game")
    original = payload
    payload, reservation = reserve(payload)
    a = allocation(payload)
    require(executable(payload, a["va"]), "the classic helper page is not executable")
    table, count = moment_table(payload)
    code, _data = h1.allocations(payload)
    seasons = h1.season_routing_status(payload)
    default = (code["va"] + len(h1.assembly.CODE)) if seasons else FMT_FILE
    content = helper_code(a["va"], moment_table=table, moment_count=count, rows=rows, default_fmt=default)
    if state == "applied":
        require(XbeImage(payload).read(a["va"], RO_SIZE) == content, "classic teams: installed with other rows")
        return payload, dict(status="already_applied", changed_bytes=0)
    result, _ = space.install_read_only(payload, OWNER, content)
    result = h1.enable_classic(result, a["va"])
    require(xbe_status(result) == "applied", "classic teams executable read-back")
    return result, dict(status="applied", owner_va=hex(a["va"]), moment_table=hex(table), moment_teams=count,
                        classic_rows=len(rows), list_length=75 + count + len(rows), season_route=seasons,
                        reservation={k: v for k, v in reservation.items() if k != "allocations"},
                        changed_bytes=sum(x != y for x, y in zip(original, result)) + abs(len(result) - len(original)))


# ------------------------------------------------------------------------------------------------------ the files

def _descriptors(main):
    from . import nfl2k5_espn25_more_moments as more
    return more._retail_descriptors(main)


def _team_offset(raw):
    from . import nfl2k5_roster_records as rr
    doc = rr.RosterDocument(raw[32:])
    require(len(doc.teams) == 1, "one-team file")
    return 32 + doc.teams[0].offset


def _stadium_offset(raw):
    """File offset of the file's single stadium record (root +0x10 count, +0x14 relative pointer)."""
    body = 32
    count, relative = struct.unpack_from("<Ii", raw, body + 0x40 + 0x10)
    require(count == 1 and relative, "a one-team file carries one stadium record")
    return body + 0x40 + 0x14 + relative - 1


def franchise_stadium_ids(main):
    """{asset code: stadium id (+0x7C)} of each NFL team's home row in the main roster."""
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_roster_storage as storage
    body = main[32:]
    stadiums = storage.read_stadiums(body, root=0x40, end=len(body))
    out = {}
    for at, code in hs.team_records(main)[:32]:
        s = storage.team_stadium(body, at, stadiums)
        require(s is not None, f"franchise {code} has no home row")
        out[code] = body[s.offset + 0x7C]
    return out


def resolve_kit(choice, code, spares, has_kit):
    """(style index, how) for a kit choice; has_kit(code, style) says whether both kit files exist on the disc."""
    if isinstance(choice, dict):
        if has_kit(code, choice["prefer"]):
            return choice["prefer"], "preferred"
        return resolve_kit(choice["fallback"], code, spares, has_kit)[0], "fallback"
    if choice == "modern":
        return 0, "modern"
    if choice == "retail":
        if code in spares:
            return spares[code], "retail spare"
        return 0, "modern (no spare)"
    require(has_kit(code, choice), f"kit {code} style {choice} is not on the disc")
    return choice, "existing"


def finish_file(raw, team, *, identity, stadium_id, style):
    """Identity, home row id and kit on a compiled team file."""
    out = bytearray(raw)
    t = _team_offset(out)
    struct.pack_into("<H", out, t + 0x118, identity)
    out[_stadium_offset(out) + 0x7C] = stadium_id
    out[t + 0x192] = style
    if style:
        season = team["season"]
        struct.pack_into("<HH", out, t + 0x15A + 4 * (style - 1), season, season)
    return bytes(out)



def finish_stadium(raw, info):
    """The one-team file's stadium record with the named venue's asset code and text. The importer resolves the
    venue through this record, so both the id byte and the asset string must name the chosen venue."""
    if not info:
        return raw
    require(set(info) <= {"asset", "name", "location", "display", "secondary"}, "stadium_info fields")
    body = bytearray(raw[32:])
    off = _stadium_offset(raw) - 32
    fields = ((0x00, info.get("name", "")), (0x08, info.get("location", "")),
              (0x0C, info.get("asset", "")), (0x10, info.get("display", info.get("name", ""))),
              (0x14, info.get("secondary", "")))
    for field, text in fields:
        if not text:
            continue
        require(isinstance(text, str) and text.isascii() and "\0" not in text, "stadium text")
        at = len(body)
        body.extend(text.encode("utf-16le") + b"\0\0")
        struct.pack_into("<i", body, off + field, at - (off + field) + 1)
    body.extend(bytes(-len(body) % 16))
    out = bytearray(raw[:32])
    struct.pack_into("<II", out, 4, len(body), len(body))
    out.extend(body)
    return bytes(out)

def compile_files(main, templates, data, *, spares, has_kit, prefix="", one_pool=False):
    """[(file name, bytes)] in list order, plus per-team receipts."""
    from . import nfl2k5_espn25_more_moments as more
    from . import nfl2k5_roster_records as rr
    main_doc = rr.RosterDocument(main[32:])
    colleges = main_doc.colleges
    main_photos = more.named_photos(main_doc)
    people = more.main_people(main)
    homes = franchise_stadium_ids(main)
    files, receipts = [], {}
    for n, key in enumerate(data.order()):
        team = dict(data.teams[key], team_key=key)
        identity = IDENTITIES[n]
        missing = []
        raw = more.compile_team(templates[key], team, data.rosters[key], colleges, identity, people,
                                appearance=data.appearance[key], main_photos=main_photos, missing_colleges=missing)
        if one_pool:
            raw = more._one_pool(raw, front.mapping_scheme("classic", key, team["abbreviation"], team["season"]))
        code = team["asset_code"]
        style, how = resolve_kit(data.presentation[key]["kit"], code, spares, has_kit)
        stadium_id = data.presentation[key].get("stadium_id", homes[code])
        raw = finish_file(raw, team, identity=identity, stadium_id=stadium_id, style=style)
        raw = finish_stadium(raw, data.presentation[key].get("stadium_info"))
        files.append((data.filename(key, prefix), raw))
        receipts[key] = dict(file=data.filename(key, prefix), identity=identity, style=style, kit=how,
                             stadium_id=stadium_id, template=team["template"], sha256=sha(raw),
                             template_colleges=missing)
    return files, receipts


def rows_for(main, data):
    by_name = {}
    for d in _descriptors(main):
        by_name.setdefault((d["selector"], d["code"]), d["index"])
    rows = []
    for key in data.order():
        t = data.teams[key]
        index = by_name.get((t["selector"], t["asset_code"]))
        if index is None:   # franchise text under another nickname (Oilers files carry the Titans' code)
            index = next(d["index"] for d in _descriptors(main) if d["code"] == t["asset_code"])
        rows.append((t["season"], FILE_NUMBER, index))
    return rows


# ------------------------------------------------------------------------------------------------------ the image

def _inputs(path, source, data):
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    with archive.Disc(Path(path), descriptors=()) as disc, hs.Source(source) as src:
        target = hs.Target(disc)
        main = target.get(identity=hs.ROSTER_OUTER_ID)
        templates = {k: target.get(data.teams[k]["template"]) for k in data.order()}
        try:
            plan = hs.plan_spares(target, src)
            spares = dict(plan["spares"])
        except (ValueError, KeyError):
            spares = {}
        kits = {name for name in (f"{c}{s}{i}.iff" for c in {data.teams[k]["asset_code"] for k in data.teams}
                                  for s in "ha" for i in range(15)) if target.has(name)}
        present = {name for name in (data.filename(k, p) for k in data.order() for p in ("", "HTS-"))
                   if target.has(name)}
    has_kit = lambda code, style: f"{code}h{style}.iff" in kits and f"{code}a{style}.iff" in kits  # noqa: E731
    # A spare counts only once its kit files are installed on this copy (historic styles ran).
    spares = {c: s for c, s in spares.items() if has_kit(c, s)}
    return main, templates, spares, has_kit, present


def image_status(path, source, data=None):
    """'retail' (no classic file, executable retail), 'applied' (files equal a fresh compile, executable applied),
    else 'foreign'."""
    from . import nfl2k5_espn25_rosters as e
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_historic_teams_quick_game as h1
    from . import nfl2k5_music_archive as archive
    from . import nfl2k5_position_pools as pools
    from . import nfl2k5_classic_field as field
    data = Data.load() if data is None else data
    try:
        payload = e.read_xbe(path)
        state = xbe_status(payload)
        authored = authored_kits_status(path)
        if authored == "foreign":
            return "foreign"
        field_state = field.status(path, source)
        if field_state == "foreign":
            return "foreign"
        main, templates, spares, has_kit, present = _inputs(path, source, data)
        if not present and state == "retail":
            return "retail" if field_state == "retail" and authored in ("retail", "not_applicable") else "foreign"
        holder = label_holder(main)
        prefix = "HTS-" if h1.season_routing_status(payload) else ""
        files, _ = compile_files(holder, templates, data, spares=spares, has_kit=has_kit, prefix=prefix,
                                 one_pool=pools.status(payload) == "applied")
        with archive.Disc(Path(path), descriptors=()) as disc:
            target = hs.Target(disc)
            same = all(target.has(name) and target.get(name) == raw for name, raw in files)
            same = same and target.get(identity=hs.ROSTER_OUTER_ID) == holder
        rows_ok = state == "applied" and XbeImage(payload).read(allocation(payload)["va"] + ROWS_OFFSET,
                                                                4 * len(files)) == b"".join(
            struct.pack("<HBB", *r) for r in rows_for(main, data))
        return "applied" if (same and rows_ok and present == {n for n, _ in files}
                              and authored == "applied" and field_state == "applied") else "foreign"
    except (ValueError, OSError, KeyError, IndexError, struct.error):
        return "foreign"


def apply_to_image(path, source, data=None):
    """Append the classic files to pack F, then install the helpers and the Quick Game variant. Run it after every
    other roster, style and season-route pass (it reads their results)."""
    from . import nfl2k5_espn25_rosters as e
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_historic_teams_quick_game as h1
    from . import nfl2k5_position_pools as pools
    from . import nfl2k5_historic_rosters as seasons_bank
    data = Data.load() if data is None else data
    state = image_status(path, source, data)
    if state == "applied":
        return dict(status="already_applied", teams=len(data.teams))
    require(state == "retail", f"classic teams: the disc is {state}")
    payload = e.read_xbe(path)
    require(h1.status(payload) == "applied", "classic teams need historic teams in Quick Game")
    require(xbe_status(payload) == "retail", "classic teams: the executable is not clean")
    authored_receipt = install_authored_kits(path)
    from . import nfl2k5_classic_field as field
    field_edits, field_receipts = field.edits(path, source)
    prefix = "HTS-" if h1.season_routing_status(payload) else ""
    main, templates, spares, has_kit, _present = _inputs(path, source, data)
    holder = label_holder(main)
    files, receipts = compile_files(holder, templates, data, spares=spares, has_kit=has_kit, prefix=prefix,
                                    one_pool=pools.status(payload) == "applied")
    rows = rows_for(main, data)
    patched, xbe_receipt = apply_xbe(payload, rows)      # computed before any disc write
    edits = {hs.ROSTER_OUTER_ID: holder, **field_edits}
    receipt = hs.rewrite_archive(path, edits, files + [(FILLER, bytes(2048))])
    seasons_bank.write_xbe(path, patched)
    try:
        face_receipt = dict(classic_face.patch_image(path), status="applied")
    except (ValueError, OSError) as exc:
        # The authored spans target the retail pack layout. A build whose face/portrait packs were rebuilt by the
        # face pipeline cannot take the raw spans; the PNGs and the fragment are delivered for that pipeline.
        face_receipt = dict(status="not_applied", reason=str(exc))
    require(image_status(path, source, data) == "applied", "classic teams read-back failed")
    return dict(status="applied", experimental=True, runtime_witnessed=False, teams=receipts, xbe=xbe_receipt,
                authored_kits=authored_receipt, field=field_receipts, face=face_receipt, file_prefix=prefix, **receipt)
