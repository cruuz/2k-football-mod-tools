"""ESPN 2026 wipes and boards, experimental: the replay transition, two wipes and the presentation boards.

Fourteen textures inside six presentation scene resources are repainted to the 2026 ESPN Monday Night Football
package as the 2026 broadcast frames show it (the stills and the numbers measured from them are listed in
``docs/espn_wipes_boards/README.md``; the art comes from ``reports/b76_p2/author_wipes_boards.py``):

- ``replay_wipe`` (wipe.cdf slot 1, raw MRKS): the replay transition. pattern_flash, the streaks, the
  ESPN logo glow and the rays and crescents become the 2026 stinger: the silver of the MNF band it flies
  through, glossy red rim lines, the red 2026 wordmark, red rims with their echo ridges.
- ``fullscreen_WipeRedFlashy`` (slot 4, raw MRKS): logo1, the red 2026 wordmark in its two-row wrap.
- ``fullscreen_WipeElectricity`` (slot 3, raw MRKS): the back plate and the bolts in the 2026 MNF
  bumper's red and white-hot outline.
- ``scoreboard`` (outer 347 chunk 5, VC-LZ): the pause-menu scoreboard backdrop: the marquee, the signs,
  the LED labels, the screen and the backboard in the 2026 board look.
- ``helmetbumper`` (outer 18 chunk 11, VC-LZ): the set monitor and its scrolling colours.
- ``playercard`` (outer 3 chunk 57, VC-LZ): the league shield on the player card.

Geometry, material colours and dynamic text are untouched. Raw MRKS resources go through the transport
adapter (new pixel and palette bytes at the same allocation, nothing else); VC-LZ scenes are refit to the
retail consumed length with the wrapper, scratch word and opaque tail kept (``nfl2k5_presentation_scenes``).
Every resource is compiled at build time from the copy's own retail span and the shipped PNGs, checked
against its applied pin and read back; nothing grows. ``revert_image`` restores the retail spans exactly
from a retail source (the repository holds only their SHA-256 pins). EXPERIMENTAL and UNWITNESSED in game;
the pause board's relation to the pause score and clock strip is unwitnessed too.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

OWNER = "nfl2k5_espn_wipes_boards"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "espn_wipes_boards_2026"
BUILD_CAPTION = "ESPN 2026 wipes and boards"
HELP_TEXT = (
    "Requires a separate official marks pack (NFL2K5_MARKS_PACK). Without it, leave this off to keep retail art. "
    "Repaints the instant replay transition and the pause scoreboard to the 2026 Monday Night Football look: "
    "the replay wipe's flash, streaks, logo glow and rims become the red and silver of the 2026 MNF shield "
    "transition, two more wipes get the red 2026 wordmark and bumper colours, the pause backdrop becomes a "
    "2026 ESPN MNF board, the set monitor behind the helmet bumper turns MNF red and the player card gets the "
    "current NFL shield. Textures only, each rebuilt inside its own retail space; nothing else changes. Off "
    "in every preset; needs a disc image. Appearance in game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
ART_DIR = ROOT / "data" / "nfl2k5_espn_wipes_boards"
PINS_PATH = ROOT / "data" / "nfl2k5_espn_wipes_boards_pins.json"
PINS_SCHEMA = "nfl2k5_espn_wipes_boards_pins/v1"
WIPE_SLOT = 124_160          # wipe.cdf (outer 3114) is six raw MRKS slots of this size
# (resource, outer, chunk, ((texture index, PNG), ...)) in the order they are written
RESOURCES = (
    ("replay_wipe", 3114, 1, ((0, "replay_wipe_pattern_flash.png"), (1, "replay_wipe_streaks.png"),
                              (2, "replay_wipe_logo_glow.png"), (3, "replay_wipe_rays.png"))),
    ("fullscreen_WipeElectricity", 3114, 3, ((0, "electricity_background1.png"), (1, "electricity_lightning.png"))),
    ("fullscreen_WipeRedFlashy", 3114, 4, ((0, "redflashy_logo1.png"),)),
    ("scoreboard", 347, 5, ((0, "scoreboard_sign02.png"), (1, "scoreboard_dot.png"), (2, "scoreboard_sign01.png"),
                            (3, "scoreboard_backboard01.png"))),
    ("helmetbumper", 18, 11, ((0, "helmetbumper_monitor.png"), (1, "helmetbumper_monitorcolors.png"))),
    ("playercard", 3, 57, ((1, "playercard_znfl_shield.png"),)),
)
# The presentation research's targets this option does not paint, with the reason each receipt carries.
REFUSED = {
    "logo_coin_wipe": "no embedded texture: a 598-vertex logo mesh and a glow mesh (geometry, out of scope)",
    "fullscreen_PlayerOfTheGame_transition": "its only descriptor (16x16) is unbound: no visible bitmap to paint",
    "fullscreen_WipeRedName": "a complete restyle (text, rings, a 1,012-vertex logo coin and team colours set at "
                              "runtime), not a texture repaint",
    "enf_logo_wipe": "no embedded texture: shapes and MRKS text (FOOTBALL / NFL / ESPN)",
    "snf_logo_wipe": "no embedded texture: shapes and MRKS text (FOOTBALL / NIGHT / SUNDAY)",
    "overlay_wipe": "no embedded texture: its materials have null texture pointers",
    "replay_wipe ESPN01/ESPN02 letters": "untextured geometry coloured by material +0x18 (orange front, gold "
                                         "sides); material colour is a separate lever, not a texture",
    "propsgamecoin": "no clean 2026 source: no coin toss in the 2026 frame sets (the eight unbound coin "
                     "descriptors also stay refused)",
    "sc_studio": "no clean 2026 source: no studio set in the 2026 frame sets",
    "coach_desk": "no clean 2026 source: no desk in the 2026 frame sets",
    "commish01": "no clean 2026 source (the commissioner model)",
    "bermanintro": "read-only in this wave (job z2 is investigating the pregame intro freeze)",
    "sc_intro": "no clean 2026 source (two of its descriptors are also refused by the allocation proof)",
    "playercard zframe_trim, zplayers_logo": "no clean 2026 source (the card trim and the Players Inc mark)",
    "menus (main_menu, Menubackground, team select, sega logo, sc_logo)": "menu art with no broadcast "
                                                                          "counterpart in the 2026 frames",
    "media1-3, ticker, glowball, orange_cursor, power_meter, player_photo_a, playerinfopanel, gamecast_2, "
    "playcallframe_coachpick, intro": "game UI with no broadcast counterpart in the 2026 frames",
}


class EspnWipesBoardsError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EspnWipesBoardsError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _scenes():
    from . import nfl2k5_presentation_scenes as scenes
    return scenes


def _outer_image():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl2k5_playbook_position_recode as recode  # noqa: E402
    return recode.OuterImage


def art_path(name: str, marks_pack=None) -> Path:
    from . import nfl2k5_official_marks as official
    return official.resolve_path(ART_DIR / name, marks_pack)


def art_pins(marks_pack=None) -> dict[str, str]:
    return {name: sha(art_path(name, marks_pack).read_bytes()) for name in [png for _n, _o, _c, edits in RESOURCES for _i, png in edits]}


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
    require(document.get("schema") == PINS_SCHEMA, "unsupported ESPN 2026 wipes and boards pins schema")
    resources = document.get("resources") or []
    named = [(r.get("name"), r.get("outer_index"), r.get("chunk_index"),
              [[t.get("texture_index"), t.get("png")] for t in r.get("textures") or []]) for r in resources]
    require(named == [(name, outer, chunk, [[index, png] for index, png in edits])
                      for name, outer, chunk, edits in RESOURCES],
            "the pins must name the six resources and their textures in build order")
    spans: dict[int, list[tuple[int, int]]] = {}
    for resource in resources:
        name = resource.get("name")
        require(all(type(resource.get(key)) is int and resource[key] >= 0 for key in
                    ("outer_index", "outer_name_id", "outer_size", "chunk_index", "chunk_offset", "span_size")),
                f"{name}: pin geometry is incomplete")
        require(resource["chunk_offset"] + resource["span_size"] <= resource["outer_size"], f"{name}: pin escapes the outer")
        require(all(isinstance(resource.get(key), str) and len(resource[key]) == 64
                    for key in ("retail_sha256", "applied_sha256"))
                and resource["retail_sha256"] != resource["applied_sha256"], f"{name}: span pins are incomplete")
        require(resource.get("kind") in ("MRKS", "SCNE") and isinstance(resource.get("raw"), bool),
                f"{name}: the pins must name the resource kind")
        spans.setdefault(resource["outer_index"], []).append((resource["chunk_offset"],
                                                              resource["chunk_offset"] + resource["span_size"]))
        for texture in resource["textures"]:
            require(isinstance(texture.get("png"), str) and texture["png"].endswith(".png")
                    and all(type(texture.get(key)) is int and texture[key] > 0 for key in ("width", "height", "mip_levels")),
                    f"{name}: texture pins are incomplete")
    for outer, ranges in spans.items():
        ranges.sort()
        require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), f"pinned spans overlap in outer {outer}")
    return document


def _pins() -> dict:
    """Public metadata pins; validate_art checks local and external art separately."""

    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "ESPN 2026 wipes and boards pins are missing from this build")
        document = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
        wanted = sorted(png for _n, _o, _c, edits in RESOURCES for _i, png in edits)
        require(sorted(document["art"]) == wanted, "the shipped art set is not the fourteen pinned textures")
        _PINS = document
    return _PINS


def available(marks_pack=None) -> bool:
    return not availability_reason(marks_pack)


def refused_targets() -> dict[str, str]:
    return dict(REFUSED)


# --- one resource ---------------------------------------------------------------------------------------

def _entry(archive, resource: dict):
    """The pinned outer when it still holds the pinned span's bytes range.

    Its size may differ from retail: a Build option may append chunks to an outer and leave every earlier chunk
    in place (the Guardian overlay appends its helmet texture to GLOBAL.IFF, outer 3, before this step runs).
    The span itself is always judged by its SHA-256 against the retail and applied pins, so a span that moved
    reads as foreign and nothing is written.
    """

    index = resource["outer_index"]
    if index >= len(archive.entries):
        return None
    entry = archive.entries[index]
    if entry.name_id != resource["outer_name_id"] or entry.size < resource["chunk_offset"] + resource["span_size"]:
        return None
    return entry


def open_span(span: bytes, resource: dict):
    """The parsed retail resource of one pin (fail-closed on anything but the pinned retail bytes)."""

    require(len(span) == resource["span_size"] and sha(span) == resource["retail_sha256"],
            f"{resource['name']}: the span is not the pinned retail resource")
    scenes = _scenes()
    try:
        parsed = scenes.open_resource(span, outer_index=resource["outer_index"],
                                      outer_id=f"0x{resource['outer_name_id']:08x}", outer_size=resource["outer_size"],
                                      chunk_index=resource["chunk_index"], chunk_offset=resource["chunk_offset"])
    except scenes.PresentationSceneError as exc:
        raise EspnWipesBoardsError(f"{resource['name']}: {exc}") from exc
    require(parsed.scene["name"] == resource["scene"] and parsed.raw is resource["raw"] and parsed.kind == resource["kind"],
            f"{resource['name']}: the retail resource is not the pinned scene")
    return parsed


def compile_span(span: bytes, resource: dict, *, marks_pack=None) -> tuple[bytes, dict[str, Any]]:
    """The 2026 replacement for one retail resource span (same size, wrapper and scratch word kept)."""

    scenes = _scenes()
    parsed = open_span(span, resource)
    edits = [(texture["texture_index"], art_path(texture["png"], marks_pack)) for texture in resource["textures"]]
    for _index, png in edits:
        require(png.is_file() and not png.is_symlink(), f"{png.name}: the shipped art must be a regular PNG")
    try:
        return scenes.compile_resource(parsed, edits, pack_name=resource.get("pack_name", ""),
                                       pack_offset=resource.get("pack_offset", 0))
    except scenes.PresentationSceneError as exc:
        raise EspnWipesBoardsError(f"{resource['name']}: {exc}") from exc


# --- images ---------------------------------------------------------------------------------------------

def _state(span: bytes, resource: dict) -> str:
    digest = sha(span)
    return "retail" if digest == resource["retail_sha256"] else "applied" if digest == resource["applied_sha256"] else "foreign"


def resource_states(source, *, pins: dict | None = None) -> dict[str, str]:
    """{resource: retail | applied | foreign} for the six pinned spans (foreign when its outer is not the pinned
    outer or no longer reaches the span)."""

    pins = _check_pins(pins) if pins is not None else _pins()
    states = {}
    with _outer_image()(source) as archive:
        for resource in pins["resources"]:
            entry = _entry(archive, resource)
            if entry is None:
                states[resource["name"]] = "foreign"
                continue
            span = archive.read(entry.virtual_offset + resource["chunk_offset"], resource["span_size"])
            states[resource["name"]] = _state(span, resource)
    return states


def image_status(source, *, pins: dict | None = None) -> str:
    """retail / applied / mixed / foreign across the six pinned resources."""

    states = resource_states(source, pins=pins)
    if "foreign" in states.values():
        return "foreign"
    values = set(states.values())
    return values.pop() if len(values) == 1 else "mixed"


status = image_status


def _write_all(archive, plan: list[tuple[int, bytes, bytes]]) -> None:
    written: list[tuple[int, bytes]] = []
    try:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "a resource span changed after preflight")
            require(archive.write(at, after) == len(after), "short ESPN wipes and boards write")
            written.append((at, before))
            require(archive.read(at, len(after)) == after, "ESPN wipes and boards read-back differs")
    except BaseException:
        for at, before in reversed(written):
            archive.write(at, before)
        raise


def apply_to_image(target, *, pins: dict | None = None, progress=None, marks_pack=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or applied resources only."""

    pins = _check_pins(pins) if pins is not None else _pins()
    validate_art(marks_pack, pins=pins)
    say = progress or (lambda message, done, total: None)
    rows: list[dict[str, Any]] = []
    plan: list[tuple[int, bytes, bytes]] = []
    total = len(pins["resources"])
    with _outer_image()(target, writable=True) as archive:
        for index, resource in enumerate(pins["resources"]):
            entry = _entry(archive, resource)
            require(entry is not None, f"{resource['name']}: outer {resource['outer_index']} is not the pinned USA "
                                       "resource; rebuild from a supported source")
            at = entry.virtual_offset + resource["chunk_offset"]
            before = archive.read(at, resource["span_size"])
            state = _state(before, resource)
            require(state != "foreign", f"{resource['name']}: the span is neither retail nor this option's 2026 "
                                        "repaint; rebuild from a supported USA source")
            row = dict(resource=resource["name"], scene=resource["scene"], outer_index=resource["outer_index"],
                       outer_size=entry.size, outer_size_retail=resource["outer_size"],
                       chunk_index=resource["chunk_index"], chunk_offset=resource["chunk_offset"],
                       span_size=resource["span_size"], kind=resource["kind"], raw=resource["raw"],
                       retail_sha256=resource["retail_sha256"], applied_sha256=resource["applied_sha256"],
                       state_before=state, image_offset=archive.image_offset(at) if hasattr(archive, "image_offset") else None)
            if state == "retail":
                say(f"ESPN 2026 wipes and boards: {resource['name']} ({index + 1} of {total})", index, total)
                after, detail = compile_span(before, resource, marks_pack=marks_pack)
                require(sha(after) == resource["applied_sha256"],
                        f"{resource['name']}: the compiled resource differs from its applied pin")
                plan.append((at, before, after))
                row.update(written=True, changed_bytes=sum(a != b for a, b in zip(before, after)),
                           system_bytes=detail["system_bytes"], video_bytes=detail["video_bytes"],
                           scratch_before=detail["scratch_before"], scratch_after=detail["scratch_after"],
                           wrapper_identical=True, textures=[
                               {key: texture[key] for key in ("texture_index", "materials", "width", "height",
                                                              "mip_levels", "decoded_pixel_offset",
                                                              "decoded_palette_offset", "allocation_bytes",
                                                              "retail_allocation_sha256", "applied_allocation_sha256",
                                                              "png_sha256", "palette_entries", "base_rgba_exact",
                                                              "changed_bytes")}
                               for texture in detail["textures"]])
                if not detail["raw"]:
                    row.update({key: detail[key] for key in ("retail_consumed", "encoded_bytes", "zero_gap_bytes",
                                                             "minimum_scratch", "opaque_tail_size", "encoder")})
            else:
                row.update(written=False, changed_bytes=0)
            rows.append(row)
        _write_all(archive, plan)
        say("ESPN 2026 wipes and boards: done", total, total)
    state = image_status(target, pins=pins)
    require(state == "applied", "the ESPN 2026 wipes and boards failed their read-back on the copy")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False, resources=rows,
                written=len(plan), already_applied=len(rows) - len(plan),
                changed_bytes=sum(row["changed_bytes"] for row in rows), refused=refused_targets(),
                pause_board_note="the relation between the pause scoreboard's signs and the pause score and clock "
                                 "strip is unwitnessed",
                archive_growth=0, rw_pool_growth=0, gamedata_growth=0)


def verify(source, *, enabled: bool = True, pins: dict | None = None) -> dict[str, Any]:
    state = image_status(source, pins=pins)
    require(state == ("applied" if enabled else "retail"), "the ESPN 2026 wipes and boards do not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


def revert_image(target, retail_source, *, pins: dict | None = None, progress=None) -> dict[str, Any]:
    """Exact revert: write the six retail spans, read from a retail source and checked against their pins."""

    pins = _check_pins(pins) if pins is not None else _pins()
    say = progress or (lambda message, done, total: None)
    retail: dict[str, bytes] = {}
    with _outer_image()(retail_source) as source:
        for resource in pins["resources"]:
            entry = _entry(source, resource)
            require(entry is not None, f"{resource['name']}: the retail source's outer is not the pinned USA resource")
            span = source.read(entry.virtual_offset + resource["chunk_offset"], resource["span_size"])
            require(sha(span) == resource["retail_sha256"], f"{resource['name']}: the retail source is not retail")
            retail[resource["name"]] = span
    plan: list[tuple[int, bytes, bytes]] = []
    rows = []
    with _outer_image()(target, writable=True) as archive:
        for index, resource in enumerate(pins["resources"]):
            entry = _entry(archive, resource)
            require(entry is not None, f"{resource['name']}: outer {resource['outer_index']} is not the pinned USA resource")
            at = entry.virtual_offset + resource["chunk_offset"]
            before = archive.read(at, resource["span_size"])
            state = _state(before, resource)
            require(state != "foreign", f"{resource['name']}: the span is neither retail nor this option's repaint")
            if state == "applied":
                say(f"Restoring {resource['name']}", index, len(pins["resources"]))
                plan.append((at, before, retail[resource["name"]]))
            rows.append(dict(resource=resource["name"], state_before=state, restored=state == "applied"))
        _write_all(archive, plan)
    state = image_status(target, pins=pins)
    require(state == "retail", "the exact revert failed its read-back")
    return dict(label=LABEL, option=BUILD_KEY, state=state, resources=rows, restored=len(plan), runtime_witnessed=False)


def _locate(archive, outer: int, chunk: int) -> tuple[int, int]:
    """(chunk offset, span size) of one resource in a retail outer (author-time)."""

    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from nfl_txtr import parse_chunks  # noqa: E402
    entry = archive.entries[outer]
    body = archive.read(entry.virtual_offset, entry.size)
    if outer == 3114:
        offset = chunk * WIPE_SLOT
        found = parse_chunks(body[offset:offset + WIPE_SLOT], allow_trailing=True)[0]
        return offset, found.end_offset
    found = parse_chunks(body, allow_trailing=True)[chunk]
    return found.offset, found.end_offset - found.offset


def record_pins(source, out_path: Path | str | None = PINS_PATH, *, marks_pack=None) -> dict:
    """Author-time: retail and applied pins for the six resources from a retail source (image or loose packs)."""

    scenes = _scenes()
    resources = []
    with _outer_image()(source) as archive:
        for name, outer, chunk, edits in RESOURCES:
            entry = archive.entries[outer]
            offset, size = _locate(archive, outer, chunk)
            span = archive.read(entry.virtual_offset + offset, size)
            parsed = scenes.open_resource(span, outer_index=outer, outer_id=f"0x{entry.name_id:08x}",
                                          outer_size=entry.size, chunk_index=chunk, chunk_offset=offset)
            pack = next(p for p in archive.packs if p.virtual_start <= entry.virtual_offset + offset < p.virtual_start + p.size)
            textures = []
            for index, png in edits:
                row = parsed.textures[index]
                textures.append(dict(texture_index=index, png=png, materials=list(row["mapped_material_names"]),
                                     width=row["width"], height=row["height"], mip_levels=row["mip_levels"]))
            resource = dict(name=name, scene=parsed.scene["name"], kind=parsed.kind, raw=parsed.raw,
                            outer_index=outer, outer_name_id=entry.name_id, outer_size=entry.size, chunk_index=chunk,
                            chunk_offset=offset, span_size=size, pack_name=pack.name,
                            pack_offset=entry.virtual_offset + offset - pack.virtual_start,
                            system_bytes=parsed.system_bytes, video_bytes=parsed.video_bytes, scratch=parsed.scratch,
                            retail_sha256=sha(span), textures=textures)
            after, detail = scenes.compile_resource(parsed, [(index, art_path(png, marks_pack)) for index, png in edits],
                                                    pack_name=pack.name, pack_offset=resource["pack_offset"])
            resource["applied_sha256"] = sha(after)
            for texture, compiled in zip(resource["textures"], detail["textures"]):
                texture.update({key: compiled[key] for key in ("decoded_pixel_offset", "decoded_palette_offset",
                                                               "allocation_bytes", "retail_allocation_sha256",
                                                               "applied_allocation_sha256", "png_sha256",
                                                               "palette_entries", "base_rgba_exact")})
            if not detail["raw"]:
                resource["fill"] = {key: detail[key] for key in ("retail_consumed", "encoded_bytes", "zero_gap_bytes",
                                                                 "minimum_scratch", "opaque_tail_size", "encoder")}
            resources.append(resource)
    document = dict(schema=PINS_SCHEMA, art=art_pins(marks_pack), resources=resources, refused=sorted(REFUSED),
                    runtime_witnessed=False)
    from . import nfl2k5_official_marks as official
    document["official_marks_pack"] = dict(schema=official.SCHEMA,
                                            files=sorted(row["name"] for row in official.CATALOG.values()
                                                         if row["feature"] == "espn_wipes_boards_2026"))
    _check_pins(document)
    if out_path is not None:
        Path(out_path).write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    return document


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_espn_wipes_boards")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status", help="retail / applied / mixed / foreign for a disc image or loose packs")
    s.add_argument("source")
    r = sub.add_parser("record-pins", help="author-time: pin the six resources from a retail source")
    r.add_argument("source")
    r.add_argument("--out", default=str(PINS_PATH))
    v = sub.add_parser("revert", help="restore the six retail spans in an image from a retail source")
    v.add_argument("target")
    v.add_argument("--retail", required=True)
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(dict(status=image_status(args.source), resources=resource_states(args.source)), indent=1))
        return 0
    if args.command == "revert":
        print(json.dumps(revert_image(args.target, args.retail), indent=1))
        return 0
    document = record_pins(args.source, args.out)
    print(json.dumps({r["name"]: [r["span_size"], r.get("fill", {}).get("minimum_scratch"), r["scratch"]]
                      for r in document["resources"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
