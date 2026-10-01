"""ESPN presentation marks (2026), experimental: four standalone GAMEDATA marks redrawn from 2026 stills.

Four TXTR chunks of ``gamedata.iff`` (outer 346, pack 0) carry the 2004 ESPN and NFL marks that the
presentation scenes draw by name:

- ``nfl_chiclet`` (chunk 24): the league chip. 2026 art: the flat NFL shield of the MNF replay stinger
  (five registered stills, median) on a navy plate. Grade A.
- ``shield_espn`` (chunk 26): the ESPN logo that the retail scorebug, the replay overlay and the
  voice-of and weather overlays all reassemble from a two-row wrap with the same two slanted triangles.
  2026 art: the red ESPN wordmark of the replay stinger, laid into that wrap so every consumer shows it
  whole (a picture painted straight across the texture tears). Grade A.
- ``espnLogo1`` (chunk 33): the white ESPN wordmark wrapped across two rows, from the 1,523-frame
  median of the 2026 scorebug wordmark (beta 72 art; the 2026 Week 3 wordmark matches it). Grade A.
- ``z_ESPN_bug`` (chunk 57): the same wordmark split across two rows (beta 72 art). Grade B: its
  consumer is untraced and the split is inferred from the retail art.

Each mark is compiled at build time from the user's own retail span and the shipped PNG through
``nfl2k5_presentation_standalone`` (the All Textures lane's quantiser, then the fixed-span fill that
keeps the 32-byte wrapper and scratch word byte-identical), checked against the applied pin and read
back. Nothing grows: every span keeps its size, the outer allocation and every other chunk are
untouched. ``revert_image`` restores the four retail spans exactly from a retail source (the repository
holds only their SHA-256 pins). EXPERIMENTAL and UNWITNESSED in game.

Composes with the sprite scorebug (b76 c1), in either order: the sprite appends its resources to the end of
``gamedata.iff`` and leaves the four spans where they are, and it accepts each span at its retail or applied pin
(``nfl2k5_scorebug_sprite.hud_espn_marks``). Here a grown ``gamedata.iff`` is accepted only when the sprite
recognizes the whole outer as its own install (``nfl2k5_scorebug_sprite.gamedata_status``); any other growth
still reads as foreign. The Hi-res pack's scorebug family stays refused at the build: it re-lays the outer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

OWNER = "nfl2k5_espn_marks"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "espn_marks_2026"
BUILD_CAPTION = "ESPN presentation marks (2026)"
HELP_TEXT = (
    "Requires a separate official marks pack (NFL2K5_MARKS_PACK). Without it, leave this off to keep retail art. "
    "Redraws four ESPN presentation marks from the 2026 Monday Night Football broadcast: the ESPN logo "
    "on the replay overlay and the voice-of and weather graphics (the red wordmark of the 2026 replay "
    "transition), the NFL league chip (the current shield), and the two white ESPN wordmark textures. "
    "Each is refit inside its own retail space; nothing else changes. Works with the sprite scorebug. Off in "
    "every preset; needs a disc image. Appearance in game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
ART_DIR = ROOT / "data" / "nfl2k5_espn_marks"  # legacy location, never loaded
PINS_PATH = ROOT / "data" / "nfl2k5_espn_marks_pins.json"
PINS_SCHEMA = "nfl2k5_espn_marks_pins/v1"
MARKS = ("nfl_chiclet", "shield_espn", "espnLogo1", "z_ESPN_bug")   # chunk order 24, 26, 33, 57
# The retail geometry the shield_espn art is laid out for: the score_bug scene's zz_ESPN_bug white
# layer (vertices 268..273), screen units and UVs in -1..1. The replay overlay (chunks 64 and 65) and
# the voice_of and weather_3row overlays draw the same two UV triangles at other scales.
SHIELD_ESPN_WRAP = (
    dict(pos=((-70.419, 7.371), (-70.419, 44.921), (-137.554, 44.921)),
         uv=((0.9585, 0.9677), (0.9585, -0.998), (-0.998, -0.998))),
    dict(pos=((-3.116, 19.858), (-70.419, 57.512), (-70.419, 19.858)),
         uv=((0.998, 0.998), (-0.9636, -0.9728), (-0.9636, 0.998))),
)


class EspnMarksError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EspnMarksError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _presentation():
    from . import nfl2k5_presentation_standalone as presentation
    return presentation


def _outer_image():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl2k5_playbook_position_recode as recode  # noqa: E402
    return recode.OuterImage


def art_path(name: str, marks_pack=None) -> Path:
    from . import nfl2k5_official_marks as official
    return official.asset_path(name, marks_pack)


def art_pins(marks_pack=None) -> dict[str, str]:
    return {name: sha(art_path(name, marks_pack).read_bytes()) for name in [f"{name}.png" for name in MARKS]}


def validate_art(marks_pack=None, *, pins=None) -> None:
    document = _pins() if pins is None else pins
    require(document.get("art") == art_pins(marks_pack), "presentation art differs from the pinned art")


def availability_reason(marks_pack=None) -> str:
    try:
        validate_art(marks_pack)
    except (OSError, ValueError) as exc:
        return str(exc)
    return ""


# --- pins ---------------------------------------------------------------------------------------------

_PINS: dict | None = None


def _check_pins(document: dict) -> dict:
    require(document.get("schema") == PINS_SCHEMA, "unsupported ESPN presentation marks pins schema")
    marks = document.get("marks") or []
    require([m.get("texture") for m in marks] == list(MARKS), "the pins must name the four marks in chunk order")
    outer = document.get("outer") or {}
    require(all(type(outer.get(key)) is int for key in ("index", "name_id", "size")), "the pins lack the outer identity")
    for mark in marks:
        require(all(type(mark.get(key)) is int and mark[key] >= 0 for key in
                    ("chunk_index", "chunk_offset", "span_size", "pack_offset", "width", "height", "mip_levels")),
                f"{mark.get('texture')}: pin geometry is incomplete")
        require(mark["chunk_offset"] + mark["span_size"] <= outer["size"], f"{mark['texture']}: pin escapes the outer")
        require(all(isinstance(mark.get(key), str) and len(mark[key]) == 64 for key in ("retail_sha256", "applied_sha256"))
                and mark["retail_sha256"] != mark["applied_sha256"], f"{mark['texture']}: span pins are incomplete")
        require(mark.get("png") == f"{mark['texture']}.png" and mark.get("grade") in ("A", "B"),
                f"{mark['texture']}: the pins must name its own PNG and an offered grade")
    spans = sorted((m["chunk_offset"], m["chunk_offset"] + m["span_size"]) for m in marks)
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "pinned mark spans overlap")
    return document


def _pins() -> dict:
    """Public metadata pins, cross-checked against the GAMEDATA inventory; art is validated separately."""

    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "ESPN presentation marks pins are missing from this build")
        document = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
        presentation = _presentation()
        rows = presentation.rows_by_texture()
        require(document["outer"] == dict(index=presentation.OUTER_INDEX, name_id=presentation.OUTER_NAME_ID,
                                          size=rows["shield_espn"]["outer_size"]), "the pins name another outer")
        for mark in document["marks"]:
            row = presentation.require_offered(mark["texture"])
            require((mark["chunk_index"], mark["chunk_offset"], mark["span_size"], mark["pack_offset"],
                     mark["retail_sha256"], mark["grade"])
                    == (row["chunk_index"], row["chunk_offset"], row["span_size"], row["pack_offset"],
                        row["span_sha256"], row["authored_grade"]),
                    f"{mark['texture']}: the pins disagree with the pinned GAMEDATA inventory")
        _PINS = document
    return _PINS


def available(marks_pack=None) -> bool:
    return not availability_reason(marks_pack)


def _row(mark: dict) -> dict:
    """A pin row in the inventory-row shape the presentation compiler takes."""

    return dict(texture=mark["texture"], outer_index=mark.get("outer_index", 346), chunk_index=mark["chunk_index"],
                chunk_offset=mark["chunk_offset"], span_size=mark["span_size"], span_sha256=mark["retail_sha256"],
                pack_name=mark.get("pack_name", "0"), pack_offset=mark["pack_offset"], width=mark["width"],
                height=mark["height"], mip_levels=mark["mip_levels"], authored_grade=mark["grade"])


def compile_mark_span(span: bytes, mark: dict, *, marks_pack=None) -> tuple[bytes, dict[str, Any]]:
    """The 2026 replacement for one retail span (complete resource, wrapper and scratch word kept)."""

    presentation = _presentation()
    row = _row(mark)
    try:
        target = presentation.resolve_span(span, row)
        return presentation.compile_mark(target, art_path(mark["png"], marks_pack), row)
    except presentation.PresentationMarkError as exc:
        raise EspnMarksError(str(exc)) from exc


# --- images ---------------------------------------------------------------------------------------------

def _sprite():
    from . import nfl2k5_scorebug_sprite as sprite
    return sprite


def _entry(archive, pins: dict, *, sprite_folder=None, retail_size: bool = False):
    """gamedata.iff's outer entry, or None when it is not the pinned resource.

    The pinned outer at its retail size, or (b76 c1, unless ``retail_size``) that outer grown by exactly the sprite
    scorebug's appended resources: the sprite checks the whole outer (its retail HUD with these four spans at their
    retail or applied pins, and its own appendix for ``sprite_folder``, default the shipped layout)."""

    outer = pins["outer"]
    if outer["index"] >= len(archive.entries):
        return None
    entry = archive.entries[outer["index"]]
    if entry.name_id != outer["name_id"]:
        return None
    if entry.size == outer["size"]:
        return entry
    if retail_size or entry.size < outer["size"]:
        return None
    state = _sprite().gamedata_status(lambda count, at: archive.read(entry.virtual_offset + at, count),
                                      entry.size, sprite_folder)
    return entry if state == "applied" else None


def _appended(entry, pins: dict) -> str:
    """What follows the pinned bytes of an accepted gamedata.iff, for receipts."""

    return "sprite scorebug" if entry.size != pins["outer"]["size"] else "none"


def mark_states(source, *, pins: dict | None = None, sprite_folder=None) -> dict[str, str] | None:
    """{texture: retail | applied | foreign} for the four spans, or None when gamedata.iff is foreign."""

    pins = _check_pins(pins) if pins is not None else _pins()
    with _outer_image()(source) as archive:
        entry = _entry(archive, pins, sprite_folder=sprite_folder)
        if entry is None:
            return None
        states = {}
        for mark in pins["marks"]:
            have = sha(archive.read(entry.virtual_offset + mark["chunk_offset"], mark["span_size"]))
            states[mark["texture"]] = ("retail" if have == mark["retail_sha256"] else
                                       "applied" if have == mark["applied_sha256"] else "foreign")
        return states


def image_status(source, *, pins: dict | None = None, sprite_folder=None) -> str:
    """retail / applied / mixed / foreign across the four pinned GAMEDATA marks (a sprite scorebug disc too)."""

    states = mark_states(source, pins=pins, sprite_folder=sprite_folder)
    if states is None or "foreign" in states.values():
        return "foreign"
    values = set(states.values())
    return values.pop() if len(values) == 1 else "mixed"


status = image_status


def refused_targets() -> dict[str, str]:
    """The six C targets with the reasons the receipt carries."""

    return dict(_presentation().REFUSED)


def _write_all(archive, plan: list[tuple[int, bytes, bytes]]) -> None:
    written: list[tuple[int, bytes]] = []
    try:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "a mark span changed after preflight")
            require(archive.write(at, after) == len(after), "short ESPN mark write")
            written.append((at, before))
            require(archive.read(at, len(after)) == after, "ESPN mark read-back differs")
    except BaseException:
        for at, before in reversed(written):
            archive.write(at, before)
        raise


def apply_to_image(target, *, pins: dict | None = None, progress=None, sprite_folder=None, marks_pack=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or applied marks only.

    ``sprite_folder`` names the sprite scorebug layout the same build installed (None: the shipped layout); it is
    read only to recognize that scorebug's appended resources in gamedata.iff."""

    pins = _check_pins(pins) if pins is not None else _pins()
    validate_art(marks_pack, pins=pins)
    say = progress or (lambda message, done, total: None)
    marks: list[dict[str, Any]] = []
    plan: list[tuple[int, bytes, bytes]] = []
    with _outer_image()(target, writable=True) as archive:
        entry = _entry(archive, pins, sprite_folder=sprite_folder)
        require(entry is not None, "gamedata.iff is not the pinned USA resource (retail, or grown only by the sprite "
                                   "scorebug); rebuild from a supported source")
        appended = _appended(entry, pins)
        total = len(pins["marks"])
        for index, mark in enumerate(pins["marks"]):
            at = entry.virtual_offset + mark["chunk_offset"]
            before = archive.read(at, mark["span_size"])
            state = ("retail" if sha(before) == mark["retail_sha256"] else
                     "applied" if sha(before) == mark["applied_sha256"] else "foreign")
            require(state != "foreign", f"{mark['texture']}: the span is neither retail nor this option's 2026 mark; "
                                        "rebuild from a supported USA source")
            row = dict(texture=mark["texture"], grade=mark["grade"], chunk_index=mark["chunk_index"],
                       chunk_offset=mark["chunk_offset"], pack_offset=mark["pack_offset"],
                       span_size=mark["span_size"], retail_sha256=mark["retail_sha256"],
                       applied_sha256=mark["applied_sha256"], state_before=state,
                       image_offset=archive.image_offset(at) if hasattr(archive, "image_offset") else None)
            if state == "retail":
                say(f"ESPN presentation marks: {mark['texture']} ({index + 1} of {total})", index, total)
                after, detail = compile_mark_span(before, mark, marks_pack=marks_pack)
                require(sha(after) == mark["applied_sha256"],
                        f"{mark['texture']}: the compiled mark differs from its applied pin")
                plan.append((at, before, after))
                fill = detail["fill"]
                row.update(written=True, changed_bytes=sum(a != b for a, b in zip(before, after)),
                           palette_entries=detail["palette_entries"], rgba_sha256=detail["rgba_sha256"],
                           compressed_bytes=fill["compressed_bytes"], filled_bytes=fill["filled_bytes"],
                           padding_bytes=fill["padding_bytes"], stored_size=fill["stored_size"],
                           scratch_bytes=fill["scratch_bytes"], exact_minimum_scratch=fill["exact_minimum_scratch"],
                           wrapper_identical=True)
            else:
                row.update(written=False, changed_bytes=0)
            marks.append(row)
        _write_all(archive, plan)
        say("ESPN presentation marks: done", total, total)
    # The read-back resolves gamedata.iff again; on a sprite scorebug disc that re-checks the sprite's whole outer
    # (its HUD outside these spans and its appended resources) after the writes.
    state = image_status(target, pins=pins, sprite_folder=sprite_folder)
    require(state == "applied", "the ESPN presentation marks failed their read-back on the copy")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False,
                outer=dict(pins["outer"]), marks=marks, written=len(plan), already_applied=len(marks) - len(plan),
                changed_bytes=sum(row["changed_bytes"] for row in marks), refused=refused_targets(),
                gamedata_appended=appended, archive_growth=0, gamedata_growth=0, rw_pool_growth=0)


def verify(source, *, enabled: bool = True, pins: dict | None = None, sprite_folder=None) -> dict[str, Any]:
    state = image_status(source, pins=pins, sprite_folder=sprite_folder)
    require(state == ("applied" if enabled else "retail"), "the ESPN presentation marks do not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


def revert_image(target, retail_source, *, pins: dict | None = None, progress=None, sprite_folder=None) -> dict[str, Any]:
    """Exact revert: write the four retail spans, read from a retail source and checked against their pins.

    The target may carry the sprite scorebug (its appended resources stay as they are); the retail source must be
    the pinned outer at its retail size."""

    pins = _check_pins(pins) if pins is not None else _pins()
    say = progress or (lambda message, done, total: None)
    retail: dict[str, bytes] = {}
    with _outer_image()(retail_source) as source:
        entry = _entry(source, pins, retail_size=True)
        require(entry is not None, "the retail source's gamedata.iff is not the pinned USA resource")
        for mark in pins["marks"]:
            span = source.read(entry.virtual_offset + mark["chunk_offset"], mark["span_size"])
            require(sha(span) == mark["retail_sha256"], f"{mark['texture']}: the retail source is not retail")
            retail[mark["texture"]] = span
    plan: list[tuple[int, bytes, bytes]] = []
    rows = []
    with _outer_image()(target, writable=True) as archive:
        entry = _entry(archive, pins, sprite_folder=sprite_folder)
        require(entry is not None, "gamedata.iff is not the pinned USA resource")
        appended = _appended(entry, pins)
        for index, mark in enumerate(pins["marks"]):
            at = entry.virtual_offset + mark["chunk_offset"]
            before = archive.read(at, mark["span_size"])
            state = ("retail" if sha(before) == mark["retail_sha256"] else
                     "applied" if sha(before) == mark["applied_sha256"] else "foreign")
            require(state != "foreign", f"{mark['texture']}: the span is neither retail nor this option's mark")
            if state == "applied":
                say(f"Restoring {mark['texture']}", index, len(pins["marks"]))
                plan.append((at, before, retail[mark["texture"]]))
            rows.append(dict(texture=mark["texture"], state_before=state, restored=state == "applied"))
        _write_all(archive, plan)
    state = image_status(target, pins=pins, sprite_folder=sprite_folder)
    require(state == "retail", "the exact revert failed its read-back")
    return dict(label=LABEL, option=BUILD_KEY, state=state, marks=rows, restored=len(plan),
                gamedata_appended=appended, runtime_witnessed=False)


def record_pins(source, out_path: Path | str | None = PINS_PATH, *, rows: dict[str, dict] | None = None, marks_pack=None) -> dict:
    """Author-time: retail and applied pins for the four marks from a retail source (image or loose packs).

    ``rows`` defaults to the pinned GAMEDATA inventory; a test passes the rows of its synthetic archive.
    """

    presentation = _presentation()
    if rows is None:
        rows = {texture: presentation.require_offered(texture) for texture in MARKS}
        outer = dict(index=presentation.OUTER_INDEX, name_id=presentation.OUTER_NAME_ID,
                     size=rows["shield_espn"]["outer_size"])
    else:
        first = rows[MARKS[0]]
        outer = dict(index=first["outer_index"], name_id=int(first["outer_id"], 16), size=first["outer_size"])
    marks = []
    with _outer_image()(source) as archive:
        entry = _entry(archive, dict(outer=outer), retail_size=True)
        require(entry is not None, "the source's gamedata.iff is not the expected resource")
        for texture in MARKS:
            row = rows[texture]
            span = archive.read(entry.virtual_offset + row["chunk_offset"], row["span_size"])
            require(sha(span) == row["span_sha256"], f"{texture}: the source span is not the pinned retail span")
            mark = dict(texture=texture, png=f"{texture}.png", grade=row["authored_grade"],
                        chunk_index=row["chunk_index"], chunk_offset=row["chunk_offset"], span_size=row["span_size"],
                        pack_name=row["pack_name"], pack_offset=row["pack_offset"], outer_index=row["outer_index"],
                        width=row["width"], height=row["height"], mip_levels=row["mip_levels"],
                        retail_sha256=row["span_sha256"])
            after, detail = presentation.compile_mark(presentation.resolve_span(span, row), art_path(mark["png"], marks_pack), row)
            mark.update(applied_sha256=sha(after), rgba_sha256=detail["rgba_sha256"],
                        palette_entries=detail["palette_entries"], fill=detail["fill"])
            marks.append(mark)
    document = dict(schema=PINS_SCHEMA, outer=outer, art=art_pins(marks_pack), marks=marks,
                    refused=sorted(presentation.REFUSED), runtime_witnessed=False)
    from . import nfl2k5_official_marks as official
    document["official_marks_pack"] = dict(schema=official.SCHEMA,
                                            files=sorted(set(document["art"]) & set(official.ASSETS)))
    _check_pins(document)
    if out_path is not None:
        Path(out_path).write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    return document


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_espn_marks")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status", help="retail / applied / mixed / foreign for a disc image or loose packs")
    s.add_argument("source")
    r = sub.add_parser("record-pins", help="author-time: pin the four marks from a retail source")
    r.add_argument("source")
    r.add_argument("--out", default=str(PINS_PATH))
    v = sub.add_parser("revert", help="restore the four retail spans in an image from a retail source")
    v.add_argument("target")
    v.add_argument("--retail", required=True)
    for command in (s, v):
        command.add_argument("--sprite-folder", default=None,
                             help="the sprite scorebug layout folder the disc was built with (default: the shipped one)")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source, sprite_folder=args.sprite_folder))
        return 0
    if args.command == "revert":
        print(json.dumps(revert_image(args.target, args.retail, sprite_folder=args.sprite_folder), indent=1))
        return 0
    document = record_pins(args.source, args.out)
    print(json.dumps({m["texture"]: [m["fill"]["compressed_bytes"], m["fill"]["filled_bytes"],
                                     m["fill"]["padding_bytes"], m["fill"]["scratch_bytes"],
                                     m["fill"]["exact_minimum_scratch"]] for m in document["marks"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
