#!/usr/bin/env python3
"""Lint NFL 2K5 playbooks for plays the game cannot execute the way they are drawn.

Works on any book, whoever authored it:
  --image DISC.iso        every PLAY entry of an XISO (read only; entries 307-343 and 4418-4449)
  --resource ENTRY.bin    extracted fixed-size PLAY resources
  --pack BOOK.2k5book     Studio packs (complete offense, defense, option, community packs)

Checks (see mod_editor/core/nfl2k5_playbook_lint.py for the measured retail envelopes):
  HANDOFF_FAR / PITCH_FAR      handoff or pitch target too far from the giver at the snap (P1)
  HANDOFF_PLAN_FAR             native exchange plan beyond retail travel (needs --xbe, Unicorn)
  CHECKDOWN_BACKWARD           a back's route finishes level with or behind the QB's release (P3)
  BACKWARD_TARGET              the same for wide receivers and tight ends
  BACK_PRIMARY_SHARE           book-level: a back is the first read on more pass links than retail (P3)
  SCREEN_DEPTH_MARGIN / SCREEN_SIDE_CROSS / SCREEN_NO_RELEASE   screen setup (P2)
  FORMATION_OVERLAP / FORMATION_ILLEGAL / DEF_STACK / DEF_MIDDLE_MUG          formations (P5)

--studio-rules lints packs as the Studio compiler writes them (deep-flat and p13 repair rules).
Exit status: 0 clean, 1 findings at or above --fail-on, 2 usage or read error. Never writes a game file.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from mod_editor.core import nfl2k5_playbook_inspector as inspector  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402

PLAY_ENTRIES = tuple(range(307, 344)) + tuple(range(4418, 4450))
RESOURCE_SIZE = inspector.RESOURCE_HEADER_SIZE + inspector.BODY_SIZE
RANK = {"none": 3, "error": 2, "warning": 1}


def _read_bounded(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path} is larger than a PLAY resource")
    return data


def image_resources(image: Path, entries=PLAY_ENTRIES):
    from mod_editor.core import nfl2k5_music_archive as archive
    with archive.Disc(image, descriptors=()) as disc:
        for index in entries:
            if index >= len(disc.archive_entries):
                continue
            entry = disc.archive_entries[index]
            if entry.size != RESOURCE_SIZE:
                continue
            raw = disc.read_entry_range(entry, 0, entry.size)
            if raw[:4] != b"PLAY":
                continue
            yield f"entry {index}", raw


def lint_everything(args) -> list[lint.LintReport]:
    native = None
    if args.xbe:
        from tools.b77.p13_handoff_probe import native_plan_callback
        native = native_plan_callback(_read_bounded(args.xbe, 16 * 1024 * 1024))
    reports = []
    if args.image:
        entries = tuple(args.entries) if args.entries else PLAY_ENTRIES
        for label, raw in image_resources(args.image, entries):
            book = inspector.parse_playbook_resource(raw)
            reports.append(lint.lint_resource(raw, f"{label} {book.book_name}", native))
    for path in args.resource or ():
        raw = _read_bounded(path, RESOURCE_SIZE)
        book = inspector.parse_playbook_resource(raw)
        reports.append(lint.lint_resource(raw, f"{path.name} {book.book_name}", native))
    if args.pack:
        from mod_editor.core import nfl2k5_playbook_pack as packs
        for path in args.pack:
            pack = packs.load_pack(path)
            label = f"{path.name} {pack.book.name}" + (" (as built)" if args.studio_rules else "")
            reports.append(lint.lint_pack(pack, label, studio_rules=args.studio_rules, native_plan=native))
    return reports


def markdown(reports: list[lint.LintReport], limit: int) -> str:
    codes = sorted({code for r in reports for code in r.counts()})
    lines = ["# Playbook lint", "", "| book | links | " + " | ".join(codes) + " |",
             "|---|---:|" + "---:|" * len(codes)]
    total = Counter()
    for r in reports:
        counts = r.counts()
        total.update(counts)
        lines.append(f"| {r.label} | {r.links_checked} | " + " | ".join(str(counts.get(c, 0)) for c in codes) + " |")
    lines.append("| **total** | " + str(sum(r.links_checked for r in reports)) + " | "
                 + " | ".join(f"**{total.get(c, 0)}**" for c in codes) + " |")
    lines += ["", "## Findings", ""]
    for r in reports:
        if not r.findings:
            continue
        lines.append(f"### {r.label}")
        for f in r.findings[:limit]:
            where = f"formation {f.formation} '{f.formation_name}'"
            if f.play is not None:
                where += f", play {f.play} '{f.play_name}'"
            if f.slot is not None:
                where += f", slot {f.slot}"
            lines.append(f"- **{f.code}** ({f.severity}, {lint.GOAL_IDS[f.code]}) {where}: {f.message}")
        if len(r.findings) > limit:
            lines.append(f"- ... {len(r.findings) - limit} more in the JSON receipt")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--entries", type=int, nargs="*")
    parser.add_argument("--resource", type=Path, nargs="*")
    parser.add_argument("--pack", type=Path, nargs="*")
    parser.add_argument("--studio-rules", action="store_true")
    parser.add_argument("--xbe", type=Path, help="default.xbe for native exchange plans (Unicorn)")
    parser.add_argument("--json", type=Path, help="new file for the full findings")
    parser.add_argument("--markdown", type=Path, help="new file for the per-book table")
    parser.add_argument("--limit", type=int, default=60, help="findings per book in the markdown")
    parser.add_argument("--fail-on", choices=("error", "warning", "none"), default="error")
    args = parser.parse_args(argv)
    if not (args.image or args.resource or args.pack):
        parser.error("Give --image, --resource or --pack")
    for out in (args.json, args.markdown):
        if out is not None and (out.exists() or out.is_symlink()):
            parser.error(f"{out} exists; choose a new output path")
    try:
        reports = lint_everything(args)
    except (OSError, ValueError) as exc:
        print(f"playbook lint: {exc}", file=sys.stderr)
        return 2
    total = Counter()
    for r in reports:
        total.update(r.counts())
        print(f"{r.label}: {r.links_checked} links, " + (", ".join(f"{k} {v}" for k, v in r.counts().items()) or "clean"))
    print("TOTAL " + (", ".join(f"{k} {v}" for k, v in sorted(total.items())) or "clean"))
    if args.json:
        with args.json.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(dict(schema=lint.SCHEMA, reports=[r.to_json() for r in reports]), stream, indent=1)
            stream.write("\n")
    if args.markdown:
        with args.markdown.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown(reports, args.limit))
    worst = max((RANK[f.severity] for r in reports for f in r.findings), default=0)
    return 1 if args.fail_on != "none" and worst >= RANK[args.fail_on] else 0


if __name__ == "__main__":
    raise SystemExit(main())
