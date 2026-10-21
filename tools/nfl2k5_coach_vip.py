#!/usr/bin/env python3
"""Derive observed coach tendencies and export experimental coach USRs.

Outputs must be new paths. Nothing is installed into an HDD or published.
See docs/mod_editor/nfl2k5_coach_vip.md for scope and manual game selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_coach_tendencies as tendencies
from mod_editor.core import nfl2k5_vip as vip
from mod_editor.core.mod_build import _xbe_bytes
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES


def dump(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=1, allow_nan=False)
        handle.write("\n")


def package_exports(source: Path, xbe: bytes, output: Path, teams=None):
    """Copy verified staging saves into correctly named Xbox containers."""
    vip.require(not output.exists(), "Package destination must be new")
    folders = sorted(p for p in source.iterdir() if p.is_dir() and re.fullmatch(r"[A-Z]{2,3}", p.name))
    if teams:
        folders = [p for p in folders if p.name in teams]
        vip.require({p.name for p in folders} == set(teams), "Requested team export is absent")
    vip.require(folders, "No coach export folders")
    built = []
    for folder in folders:
        save = vip.load_signed(folder, xbe)
        receipt_path = source / (folder.name + ".json")
        receipt = json.loads(receipt_path.read_text())
        digest = hashlib.sha256(save.payload).hexdigest()
        vip.require(receipt["save_sha256"] == digest and receipt["name"] == save.name,
                    f"Export receipt does not match {folder.name}")
        expected_meta = b"\xff\xfe" + ("Name=" + save.name + "\r\n").encode("utf-16le")
        vip.require((folder / "SaveMeta.xbx").read_bytes() == expected_meta,
                    f"SaveMeta name does not match {folder.name}")
        container = vip.save_container_id(save.name)
        row = dict(team=folder.name, name=save.name, container_id=container,
                   path=f"UDATA/53450030/{container}", save_sha256=digest,
                   receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
        built.append((save, row))
    vip.require(len({r["container_id"] for _, r in built}) == len(built), "Save-name container collision")
    title = output / "UDATA" / "53450030"
    title.mkdir(parents=True)
    for save, row in built:
        vip.write_signed(title / row["container_id"], save, xbe)
    result = dict(schema="nfl2k5_vip_transfer/v1", title_id="53450030", profiles=[r for _, r in built],
                  scope="Copy the 12-hex containers into the existing title directory; retain its metadata/icons. No HDD was edited.")
    dump(output / "manifest.json", result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    derive = commands.add_parser("derive")
    derive.add_argument("--source", type=Path, action="append", required=True)
    derive.add_argument("--charting", type=Path, action="append", default=[], help="optional FTN charting parquet/CSV")
    derive.add_argument("--participation", type=Path, action="append", default=[], help="optional nflverse coverage participation parquet/CSV")
    derive.add_argument("--coaches", type=Path, default=ROOT / "data/vip/coach_sources_2026.json")
    derive.add_argument("--out", type=Path, required=True)
    compact = commands.add_parser("compact", help="retain build inputs and provenance; omit full situation grids")
    compact.add_argument("--source", type=Path, required=True)
    compact.add_argument("--out", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("--tendencies", type=Path, required=True)
    export.add_argument("--image", type=Path, required=True, help="exact compiled game disc; read only")
    export.add_argument("--xbe", type=Path, help="optional executable; otherwise extracted read-only from image")
    export.add_argument("--template", type=Path, required=True, help="USR folder with SAVEGAME.DAT, TYPE and EXTRA")
    export.add_argument("--team", action="append")
    export.add_argument("--out", type=Path, required=True)
    policy = commands.add_parser("upgrade-executable", help="upgrade a verified installed CPU policy in a new XBE copy")
    policy.add_argument("--xbe", type=Path, required=True)
    policy.add_argument("--out", type=Path, required=True)
    package = commands.add_parser("package", help="copy exports into name-matched Xbox UDATA containers")
    package.add_argument("--exports", type=Path, required=True)
    package.add_argument("--xbe", type=Path, required=True, help="local executable for save-signature verification")
    package.add_argument("--team", action="append")
    package.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("--out must be a new path")
    if args.command == "compact":
        from mod_editor.core.nfl2k5_coach_ai import compact_tendency
        rows = []
        prepared = []
        for path in sorted(args.source.glob("*.json")):
            before = path.read_bytes()
            value = compact_tendency(json.loads(before))
            # Keep compact JSON auditable by the release text gate: bounded
            # whitespace-free tokens, without reintroducing full pretty grids.
            after = (json.dumps(value, separators=(", ", ":"), allow_nan=False) + "\n").encode()
            prepared.append((path.name, after))
            rows.append(dict(team=value["team"], before_bytes=len(before), after_bytes=len(after),
                             before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(after).hexdigest()))
        vip.require(prepared, "No tendency inputs to compact")
        args.out.mkdir(parents=True)
        for name, content in prepared:
            (args.out / name).write_bytes(content)
        print(json.dumps(dict(schema="nfl2k5_coach_compaction/v1", profiles=rows,
                              before_bytes=sum(r["before_bytes"] for r in rows),
                              after_bytes=sum(r["after_bytes"] for r in rows)), indent=2))
        return
    if args.command == "upgrade-executable":
        from mod_editor.core import nfl2k5_cpu_money_downs as money
        result, receipt = money.upgrade_to_modern2(_xbe_bytes(args.xbe))
        with args.out.open("xb") as handle:
            handle.write(result)
        print(json.dumps(receipt, indent=2))
        return
    if args.command == "package":
        print(json.dumps(package_exports(args.exports, _xbe_bytes(args.xbe), args.out, args.team), indent=2))
        return
    if args.command == "derive":
        specs = json.loads(args.coaches.read_text())
        values = tendencies.build(args.source, specs, args.charting, args.participation)
        args.out.mkdir(parents=True)
        for value in values:
            dump(args.out / (value["team"] + ".json"), value)
            print(value["team"], value["coach"], "calls", value["overall"]["calls"],
                  "pass", value["overall"]["pass_rate"]["rate"], flush=True)
        return
    paths = sorted(args.tendencies.glob("*.json"))
    values = [json.loads(path.read_text()) for path in paths]
    if args.team:
        values = [value for value in values if value["team"] in args.team]
        if {value["team"] for value in values} != set(args.team):
            ap.error("Requested team is absent from tendency data")
    if not values:
        ap.error("No coach tendency files")
    if any(not isinstance(v.get("team"), str) or not re.fullmatch(r"[A-Z]{2,3}", v["team"]) for v in values):
        ap.error("Team identifiers must be two or three uppercase ASCII letters")
    if len({v["team"] for v in values}) != len(values):
        ap.error("Duplicate team tendency files")
    xbe = _xbe_bytes(args.xbe or args.image)
    compatibility = vip.executable_compatibility(xbe)
    template = vip.load_signed(args.template, xbe)
    # Validate/build everything in memory before creating any output directory.
    built = []
    with OuterImage(args.image) as archive:
        for value in values:
            spec = value["provenance"]
            book = archive.read_entry(BOOK_ENTRIES[spec["archive_book"]])
            result, receipt = vip.build_coach(template, book, value, spec["profile_name"], spec["native_book_index"])
            receipt["executable"] = compatibility
            built.append((value["team"], result, receipt))
    if len({save.payload[:4] for _, save, _ in built}) != len(built):
        ap.error("Generated profile identity collision; choose distinct names")
    args.out.mkdir(parents=True)
    for team, result, receipt in built:
        vip.write_signed(args.out / team, result, xbe)
        dump(args.out / (team + ".json"), receipt)
        print(team, receipt["changed_bytes"], "changed bytes; signed; native replay pending", flush=True)


if __name__ == "__main__":
    main()
