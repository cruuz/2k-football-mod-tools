#!/usr/bin/env python3
"""Check, export and retarget community playbook packs (``.2k5book``).

A ``.2k5book`` is a **recipe**, not a book: the studio's own formation/play/link
rows written out as JSON.  It carries no retail bytes, so the first six checks
run with **no game data at all** -- a contributor, a reviewer or a GitHub Action
needs only this file and the pack.

Usage::

    nfl2k5_playbook_pack.py check    PACK.2k5book
    nfl2k5_playbook_pack.py check    PACK.2k5book --book ATL-pb.PLAY
    nfl2k5_playbook_pack.py check    PACK.2k5book --image IMAGE_OR_PACK_DIR [--team GB]
    nfl2k5_playbook_pack.py check    PACK.2k5book --image IMAGE_OR_PACK_DIR --all-teams
    nfl2k5_playbook_pack.py retarget PACK.2k5book --team GB --image IMAGE_OR_PACK_DIR -o GB.2k5book
    nfl2k5_playbook_pack.py export   PROJECT.2k5mod -o PACK.2k5book --image IMAGE_OR_PACK_DIR [--team ATL]

``--image`` accepts a disc image **or** a folder of extracted ``vc_53450030``
packs, and is only ever read.  ``check`` exits 0 when every stage is green.

The checks, in order: schema/types, budget (50 formations / 270 plays / 3,500
nodes / 36 links per formation / 15-node chains), the ported retail play
validator on every play, class-flag sanity, formation legality, the
donor-header rule, and -- when a book is supplied -- a dry compile through the
real writer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _entry in (_ROOT, _HERE):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from mod_editor.core import nfl2k5_playbook_pack as pack_mod  # noqa: E402
from mod_editor.core.nfl2k5_playbook_inspector import (  # noqa: E402
    BODY_SIZE,
    RESOURCE_HEADER_SIZE,
    parse_playbook_resource,
)

RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE


class PackToolError(SystemExit):
    def __init__(self, message: str) -> None:
        super().__init__(f"error: {message}")


def _recode_module():
    import importlib

    return importlib.import_module("nfl2k5_playbook_position_recode")


def _resource_from_file(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) == RESOURCE_SIZE:
        return raw
    if len(raw) == BODY_SIZE:
        # A bare body: rebuild the retail wrapper so the writer sees a real resource.
        import struct

        header = struct.pack("<4s7I", b"PLAY", BODY_SIZE, BODY_SIZE, 0, 0, 0, 0, 0)
        return header + raw
    raise PackToolError(
        f"{path.name} is {len(raw):,} bytes; a PLAY book is {RESOURCE_SIZE:,} "
        f"(wrapper + body) or {BODY_SIZE:,} (body only)."
    )


def _resource_from_image(image: Path, team: str) -> bytes:
    recode = _recode_module()
    index = recode.BOOK_ENTRIES.get(team)
    if index is None:
        raise PackToolError(f"“{team}” is not one of the 37 books ({', '.join(recode.BOOK_NAMES)}).")
    with recode.OuterImage(image) as archive:
        if index >= len(archive.entries):
            raise PackToolError(f"that image has no outer entry {index} for “{team}”.")
        raw = archive.read_entry(index)
    if len(raw) != RESOURCE_SIZE:
        raise PackToolError(f"{team}: outer entry {index} is not a playbook resource.")
    return raw


def _resolve_book(args: argparse.Namespace, team: str) -> bytes | None:
    if getattr(args, "book", None):
        return _resource_from_file(Path(args.book))
    if getattr(args, "image", None):
        return _resource_from_image(Path(args.image), team)
    return None


def _print_check(team: str, report: pack_mod.PackCheck, *, header: bool = True) -> None:
    if header:
        print(f"=== {team} ===")
    print(report.text())


def cmd_check(args: argparse.Namespace) -> int:
    pack = pack_mod.load_pack(Path(args.pack))
    teams = [args.team or pack.book.team]
    if args.all_teams:
        if not args.image:
            raise PackToolError("--all-teams reads every team's own book: pass --image.")
        teams = list(pack_mod.TEAM_BOOKS)
    if not args.image and not args.book:
        # no game data at all: rules 1-6 on the pack as authored
        teams = [pack.book.team]
    results: list[dict[str, Any]] = []
    failed = 0
    for team in teams:
        resource = _resolve_book(args, team)
        use = pack
        resolutions: tuple[pack_mod.Resolution, ...] = ()
        if resource is not None and (team != pack.book.team or args.retarget):
            book = parse_playbook_resource(resource, asset_id=f"book:{team}")
            use, resolutions = pack_mod.retarget_pack(pack, team, book, resource[RESOURCE_HEADER_SIZE:])
        report = pack_mod.check_pack(use, resource=resource, asset_id=f"book:{team}")
        _print_check(team, report, header=len(teams) > 1)
        for res in resolutions:
            if res.how in ("ranked", "unresolved"):
                print(f"    ~ {res.kind} “{res.entry_id}” {res.field}: {res.detail}")
        results.append({"team": team, **report.to_json(),
                        "resolutions": [r.__dict__ for r in resolutions]})
        if not report.ok:
            failed += 1
    if args.json:
        Path(args.json).write_text(
            json.dumps({"pack": Path(args.pack).name, "results": results}, indent=1),
            encoding="utf-8", newline="\n",
        )
    if len(teams) > 1:
        print(f"\n{len(teams) - failed} of {len(teams)} book(s) green.")
    return 1 if failed else 0


def cmd_retarget(args: argparse.Namespace) -> int:
    pack = pack_mod.load_pack(Path(args.pack))
    team = args.team
    resource = _resolve_book(args, team)
    if resource is None:
        raise PackToolError("retargeting needs the target team's book: pass --image or --book.")
    book = parse_playbook_resource(resource, asset_id=f"book:{team}")
    retargeted, resolutions = pack_mod.retarget_pack(
        pack, team, book, resource[RESOURCE_HEADER_SIZE:]
    )
    for res in resolutions:
        print(f"{res.kind:9s} {res.entry_id:32s} {res.field:8s} -> "
              f"{res.index if res.index is not None else '(new)'} “{res.name}” [{res.how}] {res.detail}")
    report = pack_mod.check_pack(retargeted, resource=resource, asset_id=f"book:{team}")
    print()
    print(report.text())
    if not report.ok:
        return 1
    out = Path(args.output) if args.output else Path(args.pack).with_name(
        f"{Path(args.pack).stem}-{team}{pack_mod.PACK_EXTENSION}"
    )
    pack_mod.save_pack(retargeted, out)
    print(f"\nwrote {out}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    import zipfile

    project = Path(args.project)
    if project.suffix.casefold() != ".2k5mod":
        raise PackToolError("export reads a .2k5mod Mod Studio project.")
    try:
        with zipfile.ZipFile(project) as archive:
            document = json.loads(archive.read("project.json").decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise PackToolError(f"could not read {project.name}: {exc}") from exc
    creates = document.get("playbook_creates", [])
    links = document.get("playbook_links", [])
    if not creates:
        raise PackToolError("that project stages no formations or plays to export.")
    asset_ids = {str(row.get("asset_id")) for row in creates}
    if len(asset_ids) != 1:
        raise PackToolError(
            "that project edits more than one playbook; a pack describes one book. "
            f"Books staged: {', '.join(sorted(asset_ids))}"
        )
    team = args.team
    resource = _resolve_book(args, team or "ATL")
    if resource is None:
        raise PackToolError("export needs the book the project was authored against: pass --image or --book.")
    book = parse_playbook_resource(resource, asset_id=f"book:{team or book_team(resource)}")
    body = resource[RESOURCE_HEADER_SIZE:]
    pack = pack_mod.pack_from_staged_rows(
        team=team or book.book_name,
        book=book,
        body=body,
        formation_rows=[r for r in creates if r.get("kind") == "play_formation_create"],
        play_rows=[r for r in creates if r.get("kind") == "play_create"],
        link_rows=links,
        name=args.name or f"{team or book.book_name} playbook pack",
        author=args.author or "unknown",
        version=args.pack_version,
        license=args.license,
    )
    report = pack_mod.check_pack(pack, resource=resource, asset_id="book:export")
    print(report.text())
    out = Path(args.output) if args.output else project.with_suffix(pack_mod.PACK_EXTENSION)
    pack_mod.save_pack(pack, out)
    print(f"\nwrote {out}")
    return 0 if report.ok else 1


def book_team(resource: bytes) -> str:
    return parse_playbook_resource(resource, asset_id="book:probe").book_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfl2k5_playbook_pack.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="run the offline check pipeline on a pack")
    check.add_argument("pack")
    check.add_argument("--book", help="a retail PLAY resource or body to compile against")
    check.add_argument("--image", help="a disc image or extracted vc_53450030 folder (read-only)")
    check.add_argument("--team", help="which book in --image to use (default: the pack's own team)")
    check.add_argument("--all-teams", action="store_true",
                       help="retarget and check against all 32 team books in --image")
    check.add_argument("--retarget", action="store_true",
                       help="retarget even when the team matches (re-resolves every index by name)")
    check.add_argument("--json", help="write the machine-readable report here")
    check.set_defaults(func=cmd_check)

    retarget = sub.add_parser("retarget", help="point a pack at another team's book, by name")
    retarget.add_argument("pack")
    retarget.add_argument("--team", required=True)
    retarget.add_argument("--book")
    retarget.add_argument("--image")
    retarget.add_argument("-o", "--output")
    retarget.set_defaults(func=cmd_retarget)

    export = sub.add_parser("export", help="export a pack from a .2k5mod project's staged rows")
    export.add_argument("project")
    export.add_argument("-o", "--output")
    export.add_argument("--book")
    export.add_argument("--image")
    export.add_argument("--team")
    export.add_argument("--name", default="")
    export.add_argument("--author", default="")
    export.add_argument("--pack-version", default="1.0.0")
    export.add_argument("--license", default="CC0-1.0")
    export.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except pack_mod.PlaybookPackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
