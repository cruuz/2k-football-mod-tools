#!/usr/bin/env python3
"""Uniform art off an ESPN NFL 2K5 (SLUS-20919) PlayStation 2 disc.

A command line over ``mod_editor/games/nfl2k5_ps2/uniform_art.py``: the same
lane the studio's Uniforms page drives, usable before any window exists and in
CI, where it proves the whole route on a synthetic image with no disc at all.

    nfl2k5_ps2_uniform_art.py catalogue --iso DISC.iso --out catalogue.json
    nfl2k5_ps2_uniform_art.py export --iso DISC.iso --team ARZ --out-dir art/
    nfl2k5_ps2_uniform_art.py pack --iso DISC.iso --edits edits.json \\
        --destination mypack
    nfl2k5_ps2_uniform_art.py --selftest

What each verb does
-------------------

``catalogue`` walks the disc's 634 uniform packages read-only and writes a
retail-free JSON: names, sizes, pixel formats, mip counts, the PCSX2
replacement filename of every texture whose identity the shipped map proves,
and a summary that counts what could not be joined instead of guessing at it.

``export`` decodes textures to PNG files. It is the *extract* half of an
``extract-only`` row: the pixels are the user's own disc's, written to their
own folder, and nothing leaves the machine.

``pack`` writes a PCSX2 replacement pack from an edits document -- one row per
texture, each naming a PNG the user authored -- and then verifies it with the
independent verifier, which is not this program.

The disc is opened read-only and is never written.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _path in (str(_ROOT), str(_HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.nfl2k5_ps2 import uniform_art as lane_module  # noqa: E402

SELFTEST_BANNER = "NFL2K5_PS2_UNIFORM_ART_SELFTEST_PASS"


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def _lane(args: argparse.Namespace) -> lane_module.UniformArtLane:
    return lane_module.UniformArtLane(map_path=getattr(args, "map", None))


def _scope(lane: lane_module.UniformArtLane, args: argparse.Namespace):
    """Which uniform packages the walk has to read, given --team / --selector.

    Reading 634 packages to show one team's kit costs a minute; reading that
    team's costs a second. The filters still run over the result, so a scope
    that is too wide is only slow, never wrong.
    """

    selector = (getattr(args, "selector", "") or "").strip()
    if selector:
        return (selector.upper(),)
    team = (getattr(args, "team", "") or "").strip()
    if team:
        found = lane.selectors_for_team(team)
        if not found:
            raise Refusal(
                f"{team!r} is not a team the shipped kit table names; run "
                f"`catalogue` without --team to see what this disc carries."
            )
        return found
    return ()


def _progress(message: str) -> None:
    sys.stderr.write("\r  " + message.ljust(72))
    sys.stderr.flush()


def _selected(catalogue, args: argparse.Namespace) -> List[Any]:
    """The targets one invocation names, by key, team, selector or part."""

    wanted_keys = set(getattr(args, "target", None) or ())
    team = (getattr(args, "team", "") or "").strip().upper()
    selector = (getattr(args, "selector", "") or "").strip().upper()
    part = (getattr(args, "part", "") or "").strip().lower()
    out = []
    for target in catalogue.targets:
        row = dict(target.raw)
        if wanted_keys and target.key not in wanted_keys:
            continue
        if team and team not in (str(row["team_abbreviation"]).upper(),
                                 str(row["team"]).upper()):
            continue
        if selector and str(row["selector"]).upper() != selector:
            continue
        if part and str(row["part"]).lower() != part:
            continue
        if getattr(args, "packable_only", False) and not row["identity_confirmed"]:
            continue
        out.append(target)
    if wanted_keys:
        missing = sorted(wanted_keys - {target.key for target in out})
        if missing:
            raise Refusal(
                f"{', '.join(missing)} is not a target this catalogue names; run "
                f"`catalogue` and choose a key it lists."
            )
    return out


# --------------------------------------------------------------------------
# Verbs
# --------------------------------------------------------------------------

def do_catalogue(args: argparse.Namespace) -> int:
    lane = _lane(args)
    catalogue = lane.build_catalogue(Path(args.iso), progress=_progress, jobs=args.jobs,
                                     selectors=_scope(lane, args))
    sys.stderr.write("\n")
    document = dict(catalogue.document)
    if args.team or args.selector or args.part or args.packable_only:
        keys = {target.key for target in _selected(catalogue, args)}
        document = dict(document)
        document["targets"] = [row for row in document["targets"] if row["key"] in keys]
        document["filtered"] = {"team": args.team or "", "selector": args.selector or "",
                                "part": args.part or "",
                                "packable_only": bool(args.packable_only),
                                "targets": len(document["targets"])}
    _write_json(Path(args.out), document)
    summary = document["summary"]
    print(f"{summary['textures']} uniform textures across "
          f"{summary['uniform_packages']} packages and {summary['teams']} named "
          f"teams; {summary['packable_textures']} carry an identity the shipped "
          f"map proves; {summary['textures_without_a_team_name']} belong to a "
          f"package the kit table does not name; "
          f"{summary['textures_without_an_identity']} have no computable "
          f"identity at all. -> {args.out}")
    return 0


def do_export(args: argparse.Namespace) -> int:
    lane = _lane(args)
    catalogue = lane.build_catalogue(Path(args.iso), progress=_progress, jobs=args.jobs,
                                     selectors=_scope(lane, args))
    sys.stderr.write("\n")
    targets = _selected(catalogue, args)
    if not targets:
        raise Refusal("no texture matched; widen --team / --selector / --part, or "
                      "run `catalogue` to see what this disc carries.")
    if args.limit:
        targets = targets[: args.limit]
    out_dir = Path(args.out_dir)
    if os.path.lexists(out_dir) and not out_dir.is_dir():
        raise Refusal(f"{out_dir} exists and is not a folder; choose another --out-dir.")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for target in targets:
        row = dict(target.raw)
        png = lane.decode_png(Path(args.iso), target)
        name = "{selector}-{chunk}-{child}-{texture}.png".format(
            selector=row["selector"] or "unknown", chunk=row["chunk"],
            child=row["child"], texture=row["name"] or "unnamed")
        path = out_dir / name
        path.write_bytes(png)
        written.append({"target": target.key, "file": path.as_posix(),
                        "size": [row["width"], row["height"]],
                        "pcsx2_png": row["pcsx2_png"],
                        "identity": row["identity_source"]})
        print(f"{path}  {row['width']}x{row['height']}  {row['part_description']}")
    _write_json(out_dir / "exported.json",
                {"schema": "nfl2k5_ps2_uniform_art_export/v1",
                 "source": str(args.iso), "files": written})
    print(f"{len(written)} PNG(s) -> {out_dir}")
    return 0


def _recipe_from_edits(document: Any, path: Path) -> Dict[str, Any]:
    if isinstance(document, list):
        rows, emulator = document, None
    elif isinstance(document, dict):
        rows = document.get("edits")
        emulator = document.get("emulator_target")
    else:
        raise Refusal(f"{path} is neither a list of edits nor an object carrying one.")
    if not isinstance(rows, list) or not rows:
        raise Refusal(f"{path} lists no edits; give one row per texture, each with "
                      f"a target and a png_path.")
    edits = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get("target"), str):
            raise Refusal(f"{path}: edit {number} names no target.")
        values: Dict[str, Any] = {}
        for key in ("png_path", "png_base64", "png"):
            if isinstance(row.get(key), str):
                values["png_path" if key == "png" else key] = row[key]
                break
        if not values:
            raise Refusal(f"{path}: edit {number} gives no PNG; add png_path.")
        if "png_path" in values and not Path(values["png_path"]).is_absolute():
            values["png_path"] = str((path.parent / values["png_path"]).resolve())
        edits.append(Edit(row["target"], values, note=str(row.get("note", ""))))
    recipe = dict(lane_module.UniformArtLane().compose_recipe(edits))
    if emulator:
        recipe["emulator_target"] = str(emulator)
    return recipe


def do_pack(args: argparse.Namespace) -> int:
    lane = _lane(args)
    edits_path = Path(args.edits)
    try:
        document = json.loads(edits_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise Refusal(f"{edits_path} cannot be read as JSON: {exc}") from exc
    recipe = _recipe_from_edits(document, edits_path)
    if args.emulator_target:
        recipe["emulator_target"] = args.emulator_target
    # A pack's own target keys say which uniform packages have to be read, so
    # a one-team pack costs a second rather than the whole disc's minute.
    scope = sorted({str(row["target"]).split(":", 1)[0].upper()
                    for row in recipe["edits"]})
    catalogue = lane.build_catalogue(Path(args.iso), progress=_progress,
                                     jobs=args.jobs, selectors=scope)
    sys.stderr.write("\n")
    plan = lane.plan(Path(args.iso), recipe, catalogue)
    print(f"plan: {len(plan.target_keys)} texture(s) -> "
          f"{plan.document['file_count']} replacement file(s)")
    destination = Path(args.destination)
    receipt = lane.build(Path(args.iso), destination, recipe, catalogue)
    verdict = lane.verify(Path(args.iso), destination, receipt)
    print(f"pack:   {receipt.document['pack']}")
    print(f"edits:  {destination}")
    print(f"verify: {'PASS' if verdict.passed else 'FAIL'} — {verdict.summary}")
    return 0 if verdict.passed else 1


# --------------------------------------------------------------------------
# Self-test: the whole route on a synthetic image, no disc, no retail bytes.
# --------------------------------------------------------------------------

def selftest(tmp: Optional[str] = None) -> int:
    import shutil

    room = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="ps2-uniform-art-"))
    room = room.resolve()
    try:
        lane = lane_module.UniformArtLane()
        source = lane.synthetic_source(room)
        assert source.is_file(), source
        before = source.read_bytes()

        catalogue = lane.build_catalogue(source)
        assert catalogue.schema == lane_module.CATALOGUE_SCHEMA, catalogue.schema
        assert len(catalogue.targets) == 2, len(catalogue.targets)
        formats = sorted(dict(t.raw)["pixel_format"] for t in catalogue.targets)
        assert formats == ["PSMT4", "PSMT8"], formats
        assert catalogue.document["summary"]["packable_textures"] == 2

        for target in catalogue.targets:
            row = dict(target.raw)
            assert [field.kind for field in target.fields] == ["png"], target.fields
            assert lane.replacement_identity(target) == row["pcsx2_png"]
            png = lane.decode_png(source, target)
            header = lane_module.png_header(png)
            assert header == (row["width"], row["height"], 8, 6, 0), header

        target = catalogue.targets[0]
        row = dict(target.raw)
        native = lane_module.write_rgba_png(
            bytes([1, 2, 3, 255]) * (row["width"] * row["height"]),
            row["width"], row["height"])
        accepted = lane.encode(source, target, native)
        assert isinstance(accepted, lane_module.EncodedArt), accepted
        doubled = lane_module.write_rgba_png(
            bytes([4, 5, 6, 255]) * (row["width"] * 2 * row["height"] * 2),
            row["width"] * 2, row["height"] * 2)
        assert isinstance(lane.encode(source, target, doubled), lane_module.EncodedArt)
        for bad, why in (
            (lane_module.write_rgba_png(
                bytes([7, 8, 9, 255]) * (row["width"] * 3 * row["height"] * 2),
                row["width"] * 3, row["height"] * 2), "a 3:2 stretch"),
            (b"this is not a png", "bytes that are not a PNG"),
        ):
            refusal = lane.encode(source, target, bad)
            assert isinstance(refusal, Refusal), why
            assert f"{row['width']}x{row['height']}" in str(refusal), str(refusal)

        edits = lane.conformance_edits(catalogue)
        recipe = lane.compose_recipe(edits)
        plan = lane.plan(source, recipe, catalogue)
        assert plan.target_keys == (edits[0].target_key,), plan.target_keys

        destination = room / "pack-receipt.json"
        receipt = lane.build(source, destination, recipe, catalogue)
        pack_root = lane.pack_root_for(destination)
        assert pack_root.is_dir(), pack_root
        verdict = lane.verify(source, destination, receipt)
        assert verdict.passed, verdict.summary
        assert source.read_bytes() == before, "the source image was written to"

        pngs = sorted(pack_root.rglob("*.png"))
        assert pngs, "the pack wrote no replacement"
        original = pngs[0].read_bytes()
        blob = bytearray(original)
        blob[-9] ^= 0xFF
        pngs[0].write_bytes(bytes(blob))
        assert not lane.verify(source, destination, receipt).passed, \
            "a flipped byte in the pack must fail verification"
        pngs[0].write_bytes(original)
        assert lane.verify(source, destination, receipt).passed, \
            "putting the byte back must verify again"

        # A tampered edits document is caught too: it is the pack's own record
        # of which textures the user replaced, so a pack cannot outlive it.
        tampered = room / "tampered-receipt.json"
        shutil.copyfile(destination, tampered)
        with open(tampered, "ab") as handle:
            handle.write(b" ")
        assert not lane.verify(source, tampered, receipt).passed, \
            "an edits document that is not the receipted one must fail"

        refused = 0
        for again in (destination, source):
            try:
                lane.build(source, again, recipe, catalogue)
            except Refusal:
                refused += 1
        assert refused == 2, "a build must refuse an existing destination and the source"
    finally:
        if not tmp:
            shutil.rmtree(room, ignore_errors=True)
    print(f"{SELFTEST_BANNER} textures=2 formats=PSMT8,PSMT4 "
          "decode=rgba-png encode=same-size,2x refuses=3:2,not-a-png "
          "pack=written verify=pass tamper=fails destination=refused")
    return 0


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true",
                        help="prove the whole route on a synthetic image; no disc needed")
    sub = parser.add_subparsers(dest="verb")

    def common(target: argparse.ArgumentParser, *, needs_iso: bool = True) -> None:
        if needs_iso:
            target.add_argument("--iso", required=True, type=Path,
                                help="the operator's own SLUS-20919 disc image, read-only")
        target.add_argument("--map", type=Path, default=None,
                            help="an identity map other than the shipped one")
        target.add_argument("--jobs", type=int, default=0,
                            help="worker processes for the disc walk (default: up to 8)")

    catalogue = sub.add_parser("catalogue", help="walk the disc's uniform packages")
    common(catalogue)
    catalogue.add_argument("--out", required=True, type=Path, help="where the JSON goes")
    catalogue.add_argument("--team", default="", help="one team abbreviation or name")
    catalogue.add_argument("--selector", default="", help="one uniform package, e.g. 00H0")
    catalogue.add_argument("--part", default="",
                           help="torso, pants, sleeve, helmet, numbers, logo, equipment…")
    catalogue.add_argument("--packable-only", action="store_true",
                           help="only textures whose identity the shipped map proves")
    catalogue.set_defaults(handler=do_catalogue, target=())

    export = sub.add_parser("export", help="decode textures to PNG files")
    common(export)
    export.add_argument("--out-dir", required=True, type=Path, help="where the PNGs go")
    export.add_argument("--target", action="append", default=[],
                        help="one catalogue key; repeatable")
    export.add_argument("--team", default="", help="one team abbreviation or name")
    export.add_argument("--selector", default="", help="one uniform package, e.g. 00H0")
    export.add_argument("--part", default="", help="torso, pants, sleeve, helmet…")
    export.add_argument("--packable-only", action="store_true",
                        help="only textures whose identity the shipped map proves")
    export.add_argument("--limit", type=int, default=0, help="stop after this many")
    export.set_defaults(handler=do_export)

    pack = sub.add_parser("pack", help="write and verify a PCSX2 replacement pack")
    common(pack)
    pack.add_argument("--edits", required=True, type=Path,
                      help="a JSON list of {target, png_path} rows")
    pack.add_argument("--destination", required=True, type=Path,
                      help="a new file; the pack folder is written beside it")
    pack.add_argument("--emulator-target", default="",
                      help="penguinscreen2_classic | pcsx2_modern | pcsx2_legacy")
    pack.set_defaults(handler=do_pack, target=())
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "handler", None):
        parser.print_help()
        return 2
    try:
        return args.handler(args)
    except Refusal as exc:
        print(f"nfl2k5_ps2_uniform_art: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
