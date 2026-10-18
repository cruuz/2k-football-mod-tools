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
  rules), with identity numbers 226.. (moments use 176..225, the extra created teams 250/251), its home venue row
  (the stadium record's id byte, which the importer maps to the main roster's row) and its kit (team +0x192 with a
  non-zero year pair at +0x15A, the same rule the Anniversary kits use);
- installs a small late allocator owner (read-only, executable page) holding four helpers and a 4-byte row per new
  team ({u16 season, u8 file digit, u8 retail entry whose franchise text and asset code it borrows});
- switches the Quick Game code to its classic variant: the list length becomes 75 + M + N (M = the moment
  team-seasons of nfl2k5_espn25_more_moments, read from its own table, N = the new teams), entry k < 75 is the roster's
  own entry, then the moment table, then the new rows; a moment entry loads its plain "h-" file even when the season
  route (HTS- files) is on.
Create a Team's own "Load Historic Team" list stays the retail 75. Franchise and season modes are unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/nfl2k5_classic_teams"
OWNER = "nfl2k5_classic_teams"
RO_SIZE = 240
REQUESTS = ((OWNER, "read_only", RO_SIZE, 16),)
ROWS_OFFSET = 0x88
MAX_ROWS = (RO_SIZE - ROWS_OFFSET) // 4            # 26 rows of list space
FIRST_ID, LAST_ID = 226, 249                       # free team identities: the ceiling for new files (24)
FILE_NUMBER = 8                                    # the file-name digit (moments use 9)
FILLER = "ct1_classic_teams_end.bin"
UI_LABEL = "Classic teams in Quick Game"
BUILD_CAPTION = "Anniversary and classic team-seasons in Quick Game Team Select"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. With historic teams in Quick Game on, the list runs on past the 75 retail "
             "historic teams into every 25th Anniversary team-season and 24 classic teams of 2005-2025 (season "
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
        require(0 < len(keys) <= min(MAX_ROWS, LAST_ID - FIRST_ID + 1), "classic team count outside the capacity")
        require(set(keys) == set(self.presentation) == set(self.appearance), "teams, classic.json and appearance differ")
        for key in keys:
            t, rows = self.teams[key], self.rosters[key]
            require(key == f"{t['selector']}_{t['season']}", f"{key}: key")
            require(len(rows) == 53, f"{key}: 53 players")
            require(len({int(r["jersey"]) for r in rows}) == 53, f"{key}: jersey numbers must be unique")
            looks = self.appearance[key]
            require(len(looks) == 53 and all(l["name"] == f"{r['first']} {r['last']}" for l, r in zip(looks, rows)),
                    f"{key}: appearance rows")
            kit = self.presentation[key]["kit"]
            require(kit in ("modern", "retail") or (type(kit) is int and 0 <= kit <= 14)
                    or (isinstance(kit, dict) and set(kit) == {"prefer", "fallback"}), f"{key}: kit")
            require(self.presentation[key]["stadium"] == "franchise", f"{key}: stadium")

    def filename(self, key, prefix=""):
        t = self.teams[key]
        return f"{prefix}h-{t['asset_code']}-{t['season']}-{t['selector']}-{FILE_NUMBER}.iff"


# ------------------------------------------------------------------------------------------------- the executable

def helper_code(va, *, moment_table, moment_count, rows, default_fmt):
    """The owned bytes: total (0x00), cmp_total (0x10), entry (0x28), fmt (0x68), then one 4-byte row per new team (0x88).
    rows: [(season, digit, retail entry index)]."""
    require(len(rows) <= MAX_ROWS, "too many classic rows")
    total = 75 + moment_count + len(rows)
    root = struct.pack("<I", ROOT_PTR)
    p32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)  # noqa: E731
    out = bytearray(b"\xcc" * ROWS_OFFSET)

    def put(offset, code):
        require(len(code) <= {0x00: 0x10, 0x10: 0x18, 0x28: 0x40, 0x68: 0x20}[offset], "helper overflow")
        out[offset:offset + len(code)] = code
    # total: EAX = the list length (the roster's count + moments + classic rows)
    put(0x00, b"\xa1" + root + bytes.fromhex("8b4058") + b"\x05" + p32(moment_count + len(rows)) + b"\xc3")
    # cmp_total: ECX = root, flags = cmp EAX, length
    put(0x10, b"\x8b\x0d" + root + bytes.fromhex("528b5158") + b"\x81\xc2" + p32(moment_count + len(rows))
        + bytes.fromhex("3bc25ac3"))
    # entry: EAX = k -> EAX = the entry (asset code at +4, franchise text at +12), EDI = season (+0) and digit (+2)
    entry = bytearray(b"\x8b\x0d" + root + bytes.fromhex("3b4158"))      # mov ecx,[root]; cmp eax,[ecx+58h]
    retail = bytes.fromhex("c1e004" "03415c" "8bf8" "c3")                 # shl eax,4; add eax,[ecx+5Ch]; mov edi,eax
    moment = bytes.fromhex("2b4158") + b"\x3d" + p32(moment_count)      # sub eax,[ecx+58h]; cmp eax,M
    moment_hit = bytes.fromhex("c1e004") + b"\x05" + p32(moment_table) + bytes.fromhex("8bf8c3")
    classic = (b"\x2d" + p32(moment_count) + b"\x8d\x3c\x85" + p32(va + ROWS_OFFSET)
               + bytes.fromhex("0fb64703" "c1e004" "03415c" "c3"))
    entry += b"\x73" + bytes([len(retail)]) + retail
    entry += moment + b"\x73" + bytes([len(moment_hit)]) + moment_hit + classic
    put(0x28, bytes(entry))
    # fmt: EDX = the file-name format; a moment entry (EDI inside the moment table) keeps the plain "h-" file
    end = moment_table + 16 * moment_count
    fmt = (b"\xba" + p32(default_fmt) + b"\x81\xff" + p32(moment_table) + b"\x72\x0d"
           + b"\x81\xff" + p32(end) + b"\x73\x05" + b"\xba" + p32(FMT_FILE) + b"\xc3")
    put(0x68, fmt)
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
        default = struct.unpack_from("<I", body, 0x69)[0]
        expected = helper_code(a["va"], moment_table=table, moment_count=count, default_fmt=default,
                               rows=[struct.unpack_from("<HBB", body, ROWS_OFFSET + 4 * i) for i in range(rows)])
        return "applied" if body == expected and h1.classic_status(payload) == "applied" else "foreign"
    except (ValueError, KeyError, IndexError, struct.error):
        return "foreign"


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


def compile_files(main, templates, data, *, spares, has_kit, prefix="", one_pool=False):
    """[(file name, bytes)] in list order, plus per-team receipts."""
    from . import nfl2k5_espn25_more_moments as more
    from . import nfl2k5_roster_records as rr
    main_doc = rr.RosterDocument(main[32:])
    colleges = main_doc.colleges
    main_photos = frozenset(p.record.values["photo_id"] for p in main_doc.players)
    people = more.main_people(main)
    homes = franchise_stadium_ids(main)
    files, receipts = [], {}
    for n, key in enumerate(data.order()):
        team = dict(data.teams[key], team_key=key)
        identity = FIRST_ID + n
        raw = more.compile_team(templates[key], team, data.rosters[key], colleges, identity, people,
                                appearance=data.appearance[key], main_photos=main_photos)
        if one_pool:
            raw = more._one_pool(raw)
        code = team["asset_code"]
        style, how = resolve_kit(data.presentation[key]["kit"], code, spares, has_kit)
        raw = finish_file(raw, team, identity=identity, stadium_id=homes[code], style=style)
        files.append((data.filename(key, prefix), raw))
        receipts[key] = dict(file=data.filename(key, prefix), identity=identity, style=style, kit=how,
                             stadium_id=homes[code], template=team["template"], sha256=sha(raw))
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
    data = Data.load() if data is None else data
    try:
        payload = e.read_xbe(path)
        state = xbe_status(payload)
        main, templates, spares, has_kit, present = _inputs(path, source, data)
        if not present and state == "retail":
            return "retail"
        prefix = "HTS-" if h1.season_routing_status(payload) else ""
        files, _ = compile_files(main, templates, data, spares=spares, has_kit=has_kit, prefix=prefix,
                                 one_pool=pools.status(payload) == "applied")
        with archive.Disc(Path(path), descriptors=()) as disc:
            target = hs.Target(disc)
            same = all(target.has(name) and target.get(name) == raw for name, raw in files)
        rows_ok = state == "applied" and XbeImage(payload).read(allocation(payload)["va"] + ROWS_OFFSET,
                                                                4 * len(files)) == b"".join(
            struct.pack("<HBB", *r) for r in rows_for(main, data))
        return "applied" if same and rows_ok and present == {n for n, _ in files} else "foreign"
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
    prefix = "HTS-" if h1.season_routing_status(payload) else ""
    main, templates, spares, has_kit, _present = _inputs(path, source, data)
    files, receipts = compile_files(main, templates, data, spares=spares, has_kit=has_kit, prefix=prefix,
                                    one_pool=pools.status(payload) == "applied")
    rows = rows_for(main, data)
    patched, xbe_receipt = apply_xbe(payload, rows)      # computed before any disc write
    receipt = hs.rewrite_archive(path, {}, files + [(FILLER, bytes(2048))])
    seasons_bank.write_xbe(path, patched)
    require(image_status(path, source, data) == "applied", "classic teams read-back failed")
    return dict(status="applied", experimental=True, runtime_witnessed=False, teams=receipts, xbe=xbe_receipt,
                file_prefix=prefix, **receipt)
