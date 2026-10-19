"""MyCareer Career Home (job ui1, Noah 2026-10-17). EXPERIMENTAL / UNWITNESSED.

Noah: "make a test MyCareer new menu system/screen to push the limits of what we can get working in game."

What it is
----------
* The MyCareer Apartment's descriptor becomes **Career Home**: six section rows (Play next game, Schedule, Practice,
  MyPlayer, Upgrades, Settings + Save) plus Quit to Menu, all inside the native seven-row window, and a live panel
  on the right drawn after the native list: MyPlayer's name, position and club; three chips (overall from the
  game's own unboosted overall, XP, depth chart spot with starter/backup); the next game and its date; this
  season's stat line (the Player Card's season bank).
* Club colours: the header card is a gradient from the club's primary to its secondary colour and every card has
  an accent bar, from the retail colour accessors (0x68D70 / 0x68DC0).
* Full-colour art: the MyPlayer position photo (FRONTEND ``position_photos_*``) and the helmet silhouette
  (FRONTEND_SYNC ``ghostlogo_h``), textures the front end already holds, found by name each frame and drawn as
  textured quads. Nothing is loaded or allocated; if a texture or the font is absent that piece is skipped.
* Panels and art use the retail immediate path the text itself uses (2D2A0 begin, 2CBE0 colour, 2CB90 UV,
  2CA70 vertex, 2CA00 end) with an aligned stack copy of a loaded font's material, like the player star.
* **Schedule** (job mcs, Noah 2026-10-18: "it would be nice if we had a schedule we could look at") opens a native
  list of the season's weeks (Week 1 .. the image's last regular week, then Wild Card, Divisional, Conference and
  Super Bowl). The cursor starts on this week and the native list scrolls; beside each visible week a card shows the
  club's game from the league grid MyCareer plays from: "vs"/"@" opponent, date and kickoff, and for a played game
  the result and score (W 27-20) from the game's own cell scores; bye weeks and unset playoff rounds say so. This
  week's card takes the club gradient, a scroll bar shows the position, the footer gives the club's regular-season
  record. A does nothing, B goes back. Everything is read only; nothing is stored.
* **Settings + Save** opens a native sub-list: Settings, Save, Sim to next appearance, Start MyPlayer,
  **Classic Apartment** (the old nine-row Apartment, unchanged, with its two info lines) and Back.
* Every row except the two screen openers is an existing MyCareer row action. B on Career Home is MyCareer's own
  quit question (the descriptor is still the Apartment); B on the sub-list, the Classic Apartment and (with Career
  Home) Upgrades goes back. The controller port rule is MyCareer's (the pad that pressed A owns MyPlayer).
* Native rows draw the first word heavy and the rest light with no space (retail ESPN style, PLAY|NEXTGAME), so
  the new labels are chosen to read that way.

Where it lives
--------------
The complete allocator union has no free code or writable bytes (job ui1 ledger, 10/17). Career Home is one
preloaded writable+executable section (flags 0x07, like retail ``.data``) in the scale-out image's single
optional extra section slot: the music section's descriptor slot, name and already-zero file gap
(``VA 0x14BC000``, raw ``nfl2k5_xbe_space.FILE_SIZE``). The jukebox music library uses the same slot, so the two
are mutually exclusive. An image without Career Home keeps exactly its bytes and 28 sections. The MyCareer code
is not changed; only its Apartment descriptor (template data) names this owner's title, rows and handler.

Section block: 128-byte header (magic, content length, content SHA-256, zeros), then the content (the title and
the Career Home row table at fixed offsets, machine code, UTF-16 strings, three descriptors and two more row tables,
the schedule's rows and week labels last), then zero padding to ``SIZE``. Resident cost: ``SIZE`` bytes
of preloaded executable memory; no disc resource, no heap allocation.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_my_career as legacy
from . import nfl2k5_my_career_home_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_my_career_home"
EVIDENCE = "EXPERIMENTAL"
VA = space.DATA_VA + space.PAGE          # the music section's address (an unmapped hole in every scale-out image)
RAW = space.FILE_SIZE                    # its zero file gap
# 0x3000 since job mcs (the Schedule screen; ui1 used 0x2000). The music slot's file gap and VA hole hold 0x10000.
SIZE = 0x3000
FLAGS = 0x07                             # writable | preload | executable (retail .data uses the same flags)
HEADER = 128
MAGIC = space.HOME_SECTION_MAGIC
CONTENT_VA = VA + HEADER

UI_LABEL = "MyCareer Career Home (test)"
BUILD_CAPTION = UI_LABEL
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. MyCareer's Apartment becomes Career Home: Play next game, Schedule, Practice, "
    "MyPlayer, Upgrades, Settings and save, and Quit, with no scrolling, and a live panel with MyPlayer's club, "
    "overall, XP, depth chart spot, next game and this season's stats. Schedule lists the club's season week by week "
    "with opponents, dates and results. Settings and save holds Settings, Save, Sim to next "
    "appearance, Start MyPlayer and the Classic Apartment (the old screen, unchanged). Uses the optional extra "
    "executable section, so it cannot be combined with a jukebox music library.")

# Native list descriptor fields shared with every MyCareer screen: the retail 'navigation' layout name, its
# standard binding table, the standard content rectangle, and flags 0x13 (0x10 lets B reach the handler).
LAYOUT, BINDINGS, FRAME = 0xE7F928, 0xAA281C, (0x02400044, 0x018D0052)
PRACTICE_LABEL = 0xE9C3BC  # the retail "Practice" literal MyCareer's Apartment already uses

HOME_TITLE = "Career Home"
STRINGS = (
    # Native rows draw the first word heavy and the rest light, with no space
    # (retail ESPN style: PLAY|NEXTGAME), so labels are chosen to read that way.
    ("home_text_more", "Settings + Save"),
    ("home_text_quit", "Quit to Menu"),
    ("home_text_classic", "Classic Apartment"),
    ("home_text_next", "NEXT GAME"),
    ("home_text_season", "THIS SEASON"),
    ("home_text_overall", "OVERALL"),
    ("home_text_xp", "XP"),
    ("home_text_starter", "STARTER"),
    ("home_text_backup", "BACKUP"),
    ("home_text_none", "No game scheduled"),
    ("home_text_options_note", "B: back to Career Home"),
    ("home_fmt_matchup", "%s at %s"),
    # Full-colour art already resident in the front end (no load): the FRONTEND
    # position photos (outer 9) and the FRONTEND_SYNC helmet silhouette (outer 8).
    ("home_tex_ghost", "ghostlogo_h"),
    ("home_tex_qb", "position_photos_qb"), ("home_tex_k", "position_photos_k"),
    ("home_tex_wr", "position_photos_wr"), ("home_tex_rb", "position_photos_rb"),
    ("home_tex_te", "position_photos_te"), ("home_tex_def", "position_photos_def"),
    # Schedule (job mcs). Row labels follow the native heavy/light style (WEEK|1, WILD|CARD).
    ("home_text_schedule", "Schedule"),
    ("home_title_schedule", "Season Schedule"),
    ("home_text_bye", "BYE WEEK"),
    ("home_text_tbd", "TBD"),
    ("home_text_nogame", "NO GAME"),
    ("home_text_now", "THIS WEEK"),
    ("home_text_pre", "PRESEASON"),
    ("home_fmt_home", "vs %s"),
    ("home_fmt_away", "@ %s"),
    ("home_fmt_date", "%u/%u/%u at %u:%02u"),
)
# Retail position codes 0..16: QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE. Linemen have no photo.
PHOTOS = ("qb", "k", "k", "wr", "def", "def", "def", "rb", "rb", "te", "def", "def", None, None, None, "def", "def")
# (label, MyCareer or own action). Six sections and Quit: the native window shows seven rows.
HOME_ROWS = (("play_text", "mode_play_row"), ("home_text_schedule", "home_schedule_open"),
             (PRACTICE_LABEL, "mode_practice"), ("card_text", "mode_card"),
             ("m3_upgrade_text", "m3_upgrade_open"), ("home_text_more", "home_options_open"),
             ("home_text_quit", "mode_quit"))
OPTION_ROWS = (("m3_settings_text", "mode_settings_open"), ("save_text", "mode_save_menu"),
               ("sim_appearance_text", "mode_sim_appearance"), ("start_text", "mode_start"),
               ("home_text_classic", "home_classic_open"), ("m3_back_text", "m3_back"))
DESCRIPTORS = (("home_classic", "apartment_text", "hub_rows"), ("home_options", "home_text_more", "home_options_rows"),
               ("home_schedule", "home_title_schedule", "home_schedule_rows"))
MAX_VISIBLE_ROWS = 7
# Schedule rows: the image's regular weeks (the stage table's Season row byte +4, which the 18-week season owner
# raises from 17), then the four postseason rounds, in grid-row order. The runtime reads the same byte.
SEASON_WEEKS_VA = 0x005151C4
PLAYOFF_ROUNDS = ("Wild Card", "Divisional", "Conference", "Super Bowl")
GRID_ROWS = 22
# Front block (job mcs). MyCareer's LZ-compressed RW template stores three of this section's addresses: the
# Apartment's title, its row table and its handler. They sit at fixed offsets ahead of the code (the title in
# TITLE_ROOM bytes, then the Career Home row table with room for the native window's seven rows and the end marker,
# then the code, whose first byte is the handler), so no change to this section's code or tables moves them and
# MyCareer's code block keeps its size (11 spare bytes at the b775 VAs, 7 on the retail test image, as with ui1).
TITLE_ROOM = 32
FRONT = TITLE_ROOM + 52 * (MAX_VISIBLE_ROWS + 1)
CODE_VA = CONTENT_VA + FRONT


def season_weeks(payload):
    weeks = XbeImage(payload).read(SEASON_WEEKS_VA, 1)[0]
    _require(weeks in (17, 18), f"Career Home schedule: unexpected regular season length {weeks}")
    return weeks


def schedule_labels(weeks):
    _require(weeks in (17, 18), f"Career Home schedule: unexpected regular season length {weeks}")
    return tuple(f"Week {i}" for i in range(1, weeks + 1)) + PLAYOFF_ROUNDS


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def career_labels(payload):
    """MyCareer's label addresses for this image (independent of the Career Home variant), plus the image's regular
    season length for the schedule rows (``season_weeks``; not an address)."""
    from . import nfl2k5_my_career_mode as mode
    code, data = legacy.allocations(payload)
    return {**mode.code_for(code["va"], data["va"])[1], "state": data["va"], "m3": mode.EXTRA_VA,
            "season_weeks": season_weeks(payload)}


def code_for(career):
    """Section content and labels. ``career`` is MyCareer's label map for the same image.

    Only the schedule's row table contents and week labels depend on ``career["season_weeks"]`` (default 18); they
    are the last bytes of the content, so every label address (the Apartment fields MyCareer's template names
    included) is the same for either season length."""
    weeks = career.get("season_weeks", 18)
    out = bytearray(FRONT) + assembly.CODE
    labels = {name: CODE_VA + offset for name, offset in assembly.LABELS.items()}
    title = (HOME_TITLE + "\0").encode("utf-16le")
    _require(len(title) <= TITLE_ROOM, "Career Home title does not fit its fixed room")
    out[:len(title)] = title
    labels["home_title"], labels["home_rows"] = CONTENT_VA, CONTENT_VA + TITLE_ROOM

    def reserve(name, size):
        out.extend(bytes((-len(out)) % 4))
        labels[name] = CONTENT_VA + len(out)
        out.extend(bytes(size))
        return labels[name] - CONTENT_VA

    for name, value in STRINGS:
        content = (value + "\0").encode("utf-16le")
        at = reserve(name, len(content))
        out[at:at + len(content)] = content
    at = reserve("home_photo_names", 4 * len(PHOTOS))
    struct.pack_into("<17I", out, at, *(labels["home_tex_" + key] if key else 0 for key in PHOTOS))
    names = {**career, **labels}

    def rows(name, content, limit=MAX_VISIBLE_ROWS):
        _require(len(content) <= limit, f"{name}: more rows than the native window shows")
        at = labels[name] - CONTENT_VA if name == "home_rows" else reserve(name, 52 * (len(content) + 1))
        for i, (label, action) in enumerate(content):
            struct.pack_into("<13I", out, at + 52 * i, 9, names[label] if isinstance(label, str) else label,
                             *([0] * 8), names[action], 0, 0)
        struct.pack_into("<I", out, at + 52 * len(content), 3)

    rows("home_rows", HOME_ROWS)
    rows("home_options_rows", OPTION_ROWS)
    # The schedule table goes last (its length and labels depend on the season length): reserve its address now,
    # after the descriptors, so nothing before it moves.
    for name, title, table in DESCRIPTORS:
        reserve(name, 44)
    weekly = schedule_labels(weeks)
    labels["home_schedule_rows"] = CONTENT_VA + len(out)
    week_names = []
    out.extend(bytes(52 * (GRID_ROWS + 1)))  # room for the longest season; the unused tail stays zero
    for i, text in enumerate(weekly):
        week_names.append("home_week_%d" % i)
        content = (text + "\0").encode("utf-16le")
        at = reserve(week_names[-1], len(content))
        out[at:at + len(content)] = content
    names = {**career, **labels}
    at = labels["home_schedule_rows"] - CONTENT_VA
    for i, name in enumerate(week_names):
        struct.pack_into("<13I", out, at + 52 * i, 9, names[name], *([0] * 8), names["home_schedule_row"], 0, 0)
    struct.pack_into("<I", out, at + 52 * len(week_names), 3)
    for name, title, table in DESCRIPTORS:
        struct.pack_into("<11I", out, labels[name] - CONTENT_VA, names[title], 0, labels["home_handler"], 0,
                         names[table], 0, LAYOUT, BINDINGS, *FRAME, 0x13)
    symbols = {"code": CODE_VA, "": 0, **career, **labels}
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, FRONT + off)[0]
        if kind == 2:
            target -= CODE_VA + off
        struct.pack_into("<I", out, FRONT + off, target & 0xFFFFFFFF)
    _require(HEADER + len(out) <= SIZE, f"Career Home needs {HEADER + len(out)} bytes; its section has {SIZE}")
    labels["content_end"] = CONTENT_VA + len(out)
    return bytes(out), labels


def apartment_fields(labels):
    """The three Apartment descriptor words MyCareer's template takes from this owner."""
    return {"title": labels["home_title"], "handler": labels["home_handler"], "rows": labels["home_rows"]}


def _block(content):
    block = bytearray(SIZE)
    block[:8] = MAGIC
    struct.pack_into("<I", block, 8, len(content))
    block[12:44] = hashlib.sha256(content).digest()
    block[HEADER:HEADER + len(content)] = content
    return bytes(block)


def _block_content(block):
    _require(len(block) >= SIZE and block[:8] == MAGIC, "foreign Career Home section magic")
    size = struct.unpack_from("<I", block, 8)[0]
    _require(0 < size <= SIZE - HEADER, "foreign Career Home section size")
    content = block[HEADER:HEADER + size]
    _require(block[12:44] == hashlib.sha256(content).digest() and not any(block[44:HEADER])
             and not any(block[HEADER + size:]), "foreign Career Home section seal/padding")
    return content


def _descriptor(block):
    _header, name, refs = space.scale_music_slots()
    return struct.pack("<9I20s", FLAGS, VA, SIZE, RAW, SIZE, 0x10000 + name, 0, 0x10000 + refs,
                       0x10000 + refs + 2, space._digest(bytes(block[:SIZE])))


def _career_state(payload):
    """(graded, home) of the installed MyCareer blob, or raise."""
    from . import nfl2k5_my_career_mode as mode
    from . import nfl2k5_letter_grades as grades
    code, data = legacy.allocations(payload)
    blob = XbeImage(payload).read(code["va"], legacy.CODE_SIZE)
    bands = None
    try:
        bands = grades._owned_state(payload)[2]
    except (ValueError, KeyError, IndexError, TypeError, struct.error):
        bands = None
    for graded in (False, True):
        if graded and bands is None:
            continue
        for home in (None, "installed"):
            fields = None
            if home:
                fields = apartment_fields(code_for(career_labels(payload))[1])
            expected = mode.code_for(code["va"], data["va"], letter_grades=graded, grade_bands=bands,
                                     home=fields)[0]
            if blob == expected:
                return graded, bands, home is not None
    raise ValueError("foreign MyCareer code for Career Home")


def status(payload):
    try:
        if not space.is_scaleout(payload):
            return "retail" if not space.has_home_section(payload) else "foreign"
        if not space.has_home_section(payload):
            return "retail"
        from . import nfl2k5_my_career_mode as mode
        _require(mode.status(payload) == "applied", "Career Home needs the applied MyCareer owner")
        block = payload[RAW:RAW + SIZE]
        content = _block_content(block)
        _require(content == code_for(career_labels(payload))[0], "foreign Career Home content")
        _require(_career_state(payload)[2], "MyCareer Apartment does not name Career Home")
        return "applied"
    except (ValueError, KeyError, IndexError, TypeError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    """Install after MyCareer (and after letter grades, if used). Exact replay is a no-op."""
    from . import nfl2k5_my_career_mode as mode
    state = status(payload)
    _require(state != "foreign", "foreign/mixed Career Home; rebuild from the original")
    if state == "applied":
        return payload, {"owner": OWNER, "already_applied": True, "changed_bytes": 0}
    _require(space.is_scaleout(payload), "Career Home needs the scale-out allocator")
    _require(not space.has_music(payload), "Career Home and the jukebox music library share one section slot")
    _require(struct.unpack_from("<I", payload, 0x11C)[0] == space.SCALE_COUNT
             and not any(payload[RAW:RAW + SIZE]), "the extra section slot is not free")
    _require(mode.status(payload) == "applied", "install MyCareer before Career Home")
    graded, bands, home = _career_state(payload)
    _require(not home, "MyCareer already names Career Home without its section")
    career = career_labels(payload)
    content, labels = code_for(career)
    code, data = legacy.allocations(payload)
    blob = mode.code_for(code["va"], data["va"], letter_grades=graded, grade_bands=bands,
                         home=apartment_fields(labels))[0]
    requests = space._validate(payload)[2]
    buf = bytearray(payload)
    image = XbeImage(payload)
    at = image.offset(code["va"], legacy.CODE_SIZE)
    changed_career = sum(a != b for a, b in zip(buf[at:at + legacy.CODE_SIZE], blob))
    buf[at:at + legacy.CODE_SIZE] = blob
    block = _block(content)
    buf[RAW:RAW + SIZE] = block
    header, name, refs = space.scale_music_slots()
    buf[header:header + 56] = _descriptor(block)
    struct.pack_into("<I", buf, 0x11C, space.SCALE_COUNT + 1)
    space._seal_scaleout(buf, requests)
    result = bytes(buf)
    _require(space.status(result) == "applied", "Career Home section postcondition failed")
    _require(status(result) == "applied", "Career Home postcondition failed")
    return result, {"owner": OWNER, "already_applied": False, "experimental": True, "runtime_witnessed": False,
                    "section_va": hex(VA), "section_size": SIZE, "section_flags": FLAGS,
                    "content_bytes": len(content), "spare_bytes": SIZE - HEADER - len(content),
                    "mycareer_template_bytes_changed": changed_career,
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)),
                    "labels": {k: hex(v) for k, v in labels.items()},
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def reservations():
    return [dict(owner=OWNER, start=hex(VA), end=hex(VA + SIZE), size=SIZE,
                 basis="owned optional preloaded writable+executable section in the extra section slot; "
                       "Career Home code, tables and padding")]


# ---------------------------------------------------------------------------------------------------- static checker
# The native menu engine does not validate descriptors (a bad pointer faults the game, ledger v1f), so every
# descriptor, row table, layout and pointer this owner creates or re-points is checked here on the final image.
DESCRIPTOR_FLAGS = 0x13
NAVIGATION = "navigation"


def _unpack_template(blob):
    """MyCareer's bounded LZ template (nfl2k5_my_career_mode._encode_menu) back to its RW bytes."""
    out, i = bytearray(), 0
    while True:
        n = blob[i]
        i += 1
        if not n:
            return bytes(out)
        if n & 128:
            count, distance = (n & 127) + 3, struct.unpack_from("<H", blob, i)[0]
            i += 2
            _require(0 < distance <= len(out), "template back-reference outside its output")
            for _ in range(count):
                out.append(out[-distance])
        else:
            out.extend(blob[i:i + n])
            i += n


def check_static(payload):
    """Validate every Career Home descriptor, row, string, handler and action pointer. Returns a receipt; raises."""
    from . import nfl2k5_my_career_mode as mode
    _require(status(payload) == "applied", "Career Home is not applied")
    image = XbeImage(payload)
    career = career_labels(payload)
    content, labels = code_for(career)
    code, data = legacy.allocations(payload)
    text_pool = {career[n] for n in career if n.endswith("_text")}

    def read(va, size):
        if VA <= va and va + size <= VA + SIZE:
            return payload[RAW + va - VA:RAW + va - VA + size]
        return image.read(va, size)

    # MyCareer's RW strings are expanded from ASCII templates by init_menus before any menu event; rebuild them.
    pool = {}
    blob = image.read(code["va"], legacy.CODE_SIZE)
    for name, base, template, count in (("text", data["va"] + 1408, "text_template", "text_bytes"),
                                        ("text2", mode.EXTRA_VA + 2160, "text2_template", "text2_bytes")):
        raw = blob[career[template] - code["va"]:career[template] - code["va"] + career[count]]
        for i, byte in enumerate(raw):
            pool[base + 2 * i] = byte

    def string(va, limit=64):
        if va in pool:
            out = []
            while pool.get(va, 0):
                out.append(chr(pool[va]))
                va += 2
                _require(len(out) <= limit, "unterminated MyCareer pool string")
            return "".join(out)
        raw = read(va, 2 * (limit + 1))
        end = next((i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), None)
        _require(end is not None and end > 0, f"no UTF-16 label at {va:#x}")
        text = raw[:end].decode("utf-16le")
        _require(all(0x20 <= ord(c) <= 0x7E for c in text), f"label at {va:#x} has glyphs the fonts lack")
        return text

    executable = [(s.start, s.start + s.raw_size) for s in image.sections if s.executable]

    def entry(va, name):
        _require(any(lo <= va < hi for lo, hi in executable), f"{name} {va:#x} is not in an executable section")
        known = {v for v in career.values()} | {v for v in labels.values()}
        _require(va in known, f"{name} {va:#x} is not a known function entry")

    # The Apartment descriptor in MyCareer's own RW template (state + 200).
    menu = _unpack_template(blob[career["menu_template"] - code["va"]:])
    at = career["apartment"] - data["va"] - 200
    descriptors = {"apartment": struct.unpack_from("<11I", menu, at)}
    for name in ("home_classic", "home_options", "home_schedule"):
        descriptors[name] = struct.unpack_from("<11I", read(labels[name], 44))
    receipt = {"descriptors": {}, "rows": {}}
    expected_rows = {"apartment": labels["home_rows"], "home_classic": career["hub_rows"],
                     "home_options": labels["home_options_rows"], "home_schedule": labels["home_schedule_rows"]}
    for name, fields in descriptors.items():
        title, events, handler, _c, rows, _14, layout, binding, frame0, frame1, flags = fields
        _require(events == 0 and _c == 0 and _14 == 0, f"{name}: unexpected event table or spare words")
        _require(handler == labels["home_handler"], f"{name}: handler is not Career Home's")
        _require(rows == expected_rows[name], f"{name}: foreign row table")
        _require(read(layout, 22) == (NAVIGATION + "\0").encode("utf-16le"), f"{name}: layout is not 'navigation'")
        _require((binding, frame0, frame1, flags) == (BINDINGS, *FRAME, DESCRIPTOR_FLAGS),
                 f"{name}: binding/frame/flags differ from every MyCareer list screen")
        receipt["descriptors"][name] = string(title)
        # Rows: kind 9 (call), a label, an executable action; kind 3 ends the table within the visible window.
        table = []
        if rows == career["hub_rows"]:
            raw = _unpack_template(blob[career["m3_menu_template"] - code["va"]:])
            source = lambda off, n: raw[rows - mode.EXTRA_VA - 256 + off:rows - mode.EXTRA_VA - 256 + off + n]
            limit = 10
        else:
            source = lambda off, n: read(rows + off, n)
            limit = GRID_ROWS if name == "home_schedule" else MAX_VISIBLE_ROWS
        for i in range(limit + 1):
            row = struct.unpack("<13I", source(52 * i, 52))
            if row[0] == 3:
                break
            _require(i < limit, f"{name}: no end marker within {limit} rows")
            _require(row[0] == 9 and not any(row[2:10]) and not any(row[11:]), f"{name} row {i}: not a call row")
            entry(row[10], f"{name} row {i} action")
            table.append(string(row[1]))
        receipt["rows"][name] = table
    _require(len(receipt["rows"]["apartment"]) == len(HOME_ROWS) <= MAX_VISIBLE_ROWS, "Career Home must show every row")
    weeks = career["season_weeks"]
    _require(tuple(receipt["rows"]["home_schedule"]) == schedule_labels(weeks)
             and weeks + len(PLAYOFF_ROUNDS) <= GRID_ROWS, "Career Home schedule rows differ from the season")
    entry(labels["home_handler"], "handler")
    entry(labels["home_draw"], "draw")
    entry(labels["home_schedule_open"], "schedule opener")
    for key in [k for k in labels if k.startswith("home_tex_")]:
        string(labels[key])
    receipt.update(section=hex(VA), size=SIZE, content_bytes=len(content), spare_bytes=SIZE - HEADER - len(content),
                   season_weeks=weeks,
                   mycareer_spare_bytes=mode.TAG_OFFSET - (mode.code_for(code["va"], data["va"], home=apartment_fields(labels))[1]["content_end"] - code["va"]))
    _require(receipt["mycareer_spare_bytes"] >= 0, "MyCareer code budget exceeded")
    return receipt
