#!/usr/bin/env python3
"""Share NFL 2K5 disc edits without sharing the disc: ``.2k5patch`` files.

    export   diff a patched copy against the base it was built from and write a
             patch file (byte runs + the creator's source assets + a recipe)
    inspect  show what a patch file contains without touching any disc
    check    dry run: does this disc image carry the expected bytes?
    apply    copy your own disc image and apply the patch to the copy
             (or --in-place to patch an existing copy)
    extract  write the bundled assets, recipe and manifest to a folder

Every run is verified against the SHA-256 of the bytes it replaces before
anything is written; a wrong base is refused, not patched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import modpack  # noqa: E402


def _progress(enabled: bool):
    last = {"stage": None, "tick": -1}

    def report(stage: str, done: int, total: int) -> None:
        if not enabled:
            return
        if total:
            tick = done * 40 // total
            if stage == last["stage"] and tick == last["tick"]:
                return
            last["stage"], last["tick"] = stage, tick
            bar = "#" * tick + "." * (40 - tick)
            sys.stderr.write(f"\r{stage:<28} [{bar}] {done / total * 100:5.1f}%")
            if done >= total:
                sys.stderr.write("\n")
        elif stage != last["stage"]:
            last["stage"], last["tick"] = stage, -1
            sys.stderr.write(f"{stage}...\n")
        sys.stderr.flush()

    return report


def _human(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{count} B"
        value /= 1024
    return f"{count} B"


def _print_inspect(info: dict) -> None:
    base = info["base"]
    print(f"{info['name']}  v{info['version'] or '-'}  by {info['author'] or 'unknown'}")
    if info["description"]:
        print(f"  {info['description']}")
    print(f"  created {info['created'] or '?'}  tool {info['tool'].get('name')} {info['tool'].get('version')}")
    print(f"  base: {base['label']}  size {base['size']}  sha256 {base['sha256'] or 'unknown'}"
          + ("  [retail]" if base["is_retail"] else "  [NOT the retail image: the author built on a modified copy]"))
    print(f"  runs: {info['runs']}  changed bytes: {_human(info['bytes'])}  pack file: {_human(info['pack_bytes'])}")
    for region in info["regions"]:
        print(f"    {region['name']}: {region['runs']} run(s), {_human(region['bytes'])}")
    if info["recipe_lines"]:
        print("  recipe:")
        for line in info["recipe_lines"]:
            print(f"    - {line}")
    if info["assets"]:
        print(f"  assets ({len(info['assets'])}, {_human(info['assets_bytes'])}):")
        for asset in info["assets"]:
            role = f"  [{asset['role']}]" if asset.get("role") else ""
            print(f"    {asset['path']}  {_human(asset['size'])}{role}")


def cmd_export(args: argparse.Namespace) -> int:
    operations = []
    if args.recipe:
        document = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
        operations = document.get("operations", document) if isinstance(document, dict) else document
    receipt = modpack.export(
        args.base, args.patched, args.out,
        {"name": args.name, "author": args.author or "", "version": args.version or "",
         "description": args.description or "", "base_label": args.base_label or "",
         "assets": [Path(item) for item in args.asset], "operations": operations, "project": args.project},
        overwrite=args.overwrite, recipe=not args.no_recipe, progress=_progress(not args.json),
    )
    if args.json:
        print(json.dumps(receipt, indent=1))
    else:
        print(f"Wrote {receipt['pack']} ({_human(receipt['pack_bytes'])}): {receipt['runs']} run(s), "
              f"{_human(receipt['bytes'])} changed, {len(receipt['assets'])} asset(s), in {receipt['elapsed_seconds']} s")
        base = receipt["base"]
        print("  base: " + ("retail disc image" if base["is_retail"] else f"custom base ({base['label']})"))
        for line in receipt["recipe_lines"]:
            print(f"  - {line}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    info = modpack.inspect(args.pack)
    if args.json:
        print(json.dumps(info, indent=1))
    else:
        _print_inspect(info)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    report = modpack.check(args.pack, args.image, hash_image=args.hash, progress=_progress(not args.json))
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        counts = report["counts"]
        print(f"{report['state'].upper()}: {report['explanation']}")
        print(f"  match {counts['match']}  applied {counts['applied']}  mismatch {counts['mismatch']}  out of range {counts['out_of_range']}")
        if report["image_sha256"]:
            print(f"  image sha256 {report['image_sha256']}"
                  + ("  [retail]" if report["image_is_retail"] else "")
                  + ("  [same base as the author]" if report["image_matches_base_sha256"] else ""))
        for run in report["runs"]:
            if run["state"] != "match":
                print(f"    run {run['index']} @0x{run['file_offset']:x} ({run['length']} B, {run['region'] or 'no file'}): {run['state']}")
    return 0 if report["state"] == "ready" else 1


def cmd_apply(args: argparse.Namespace) -> int:
    if args.in_place:
        receipt = modpack.apply_in_place(args.pack, args.in_place, progress=_progress(not args.json))
    else:
        if not args.source or not args.out:
            print("apply needs --source and --out (or --in-place IMAGE)", file=sys.stderr)
            return 2
        receipt = modpack.apply(args.pack, args.source, args.out, overwrite=args.overwrite,
                                hash_streams=not args.no_hash, progress=_progress(not args.json))
    if args.json:
        print(json.dumps(receipt, indent=1))
    else:
        target = receipt["target"]
        print(f"Applied '{receipt['name']}': {receipt['runs']} run(s), {_human(receipt['bytes'])} written to {target['path']} "
              f"in {receipt['elapsed_seconds']} s")
        if receipt["mode"] == "copy":
            source = receipt["source"]
            if source["sha256"]:
                print("  your source image: " + ("the retail disc image" if source["is_retail"] else "not the retail disc image")
                      + ("; the same base the author used" if source["matches_base_sha256"] else
                         "; a different base from the author's" if source["matches_base_sha256"] is False else ""))
            if target["matches_author_result"] is not None:
                print("  result: " + ("byte-identical to the author's patched image" if target["matches_author_result"]
                                      else "every run verified, but the whole file differs from the author's image outside the patch "
                                           "(your base is not the author's base)"))
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    receipt = modpack.extract_assets(args.pack, args.out, overwrite=args.overwrite)
    if args.json:
        print(json.dumps(receipt, indent=1))
    else:
        print(f"Extracted {receipt['assets']} asset(s) plus recipe.json and manifest.json to {receipt['directory']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="write a .2k5patch from base + patched images")
    export.add_argument("--base", required=True, help="the disc image the patched copy was built from")
    export.add_argument("--patched", required=True, help="the patched copy")
    export.add_argument("--out", required=True, help="output .2k5patch")
    export.add_argument("--name", required=True)
    export.add_argument("--author")
    export.add_argument("--version")
    export.add_argument("--description")
    export.add_argument("--base-label", help="how to describe the base when it is not the retail image")
    export.add_argument("--asset", action="append", default=[], metavar="FILE",
                        help="bundle a source file (PNG, WAV, JSON...) under assets/; repeatable")
    export.add_argument("--recipe", metavar="JSON", help="a JSON list of recipe operations ({'op': ..., parameters}) to record")
    export.add_argument("--project", metavar="PROJECT.2k5mod", help="embed a studio project archive as the pack's sources")
    export.add_argument("--no-recipe", action="store_true", help="skip recognising studio edits")
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--json", action="store_true")
    export.set_defaults(run=cmd_export)

    inspect = sub.add_parser("inspect", help="describe a .2k5patch")
    inspect.add_argument("pack")
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(run=cmd_inspect)

    check = sub.add_parser("check", help="dry run against a disc image")
    check.add_argument("pack")
    check.add_argument("--image", required=True)
    check.add_argument("--hash", action="store_true", help="also hash the whole image (slow) to say whether it is retail")
    check.add_argument("--json", action="store_true")
    check.set_defaults(run=cmd_check)

    apply = sub.add_parser("apply", help="apply a .2k5patch to a copy of your own disc image")
    apply.add_argument("pack")
    apply.add_argument("--source", help="your own disc image (never modified)")
    apply.add_argument("--out", help="the patched copy to create")
    apply.add_argument("--in-place", metavar="IMAGE", help="patch this existing copy in place instead")
    apply.add_argument("--overwrite", action="store_true")
    apply.add_argument("--no-hash", action="store_true", help="skip the whole-file digests (faster; runs are still verified)")
    apply.add_argument("--json", action="store_true")
    apply.set_defaults(run=cmd_apply)

    extract = sub.add_parser("extract", help="write the bundled assets, recipe and manifest to a folder")
    extract.add_argument("pack")
    extract.add_argument("--out", required=True)
    extract.add_argument("--overwrite", action="store_true")
    extract.add_argument("--json", action="store_true")
    extract.set_defaults(run=cmd_extract)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except modpack.ModpackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
