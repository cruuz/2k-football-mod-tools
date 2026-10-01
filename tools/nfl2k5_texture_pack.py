#!/usr/bin/env python3
"""Texture packs for the xemu 2K5 Edition: catalog a disc, name a dump, make a redraw workspace, build a pack.

  nfl2k5_texture_pack.py key --fmt 0b --size 256x256 LEVEL0.bin [PALETTE.bin]
  nfl2k5_texture_pack.py catalog DISC.iso OUT.tsv [--retail RETAIL.tsv] [--jobs 16]
  nfl2k5_texture_pack.py find CATALOG.tsv [--name TEXT] [--file 18H0.IFF] [--key KEY] [--outer N] [--changed]
  nfl2k5_texture_pack.py name-dump DUMP_DIR CATALOG.tsv [--out named.tsv]
  nfl2k5_texture_pack.py workspace CATALOG.tsv OUT_DIR (--keys K1,K2 | --name TEXT) [--disc DISC | --dump DUMP_DIR]
  nfl2k5_texture_pack.py build MANIFEST.json CATALOG.tsv OUT_PACK_DIR [--disc-label TEXT] [--overwrite]
  nfl2k5_texture_pack.py validate PACK_DIR [--catalog CATALOG.tsv]
  nfl2k5_texture_pack.py install PACK_DIR [--packs-root DIR] [--overwrite]

Every key is the Edition's x2 key (see mod_editor/core/nfl2k5_xemu_texture_packs.py). Catalog the disc that will be
played: a pack keyed from another build (or from retail) only matches the textures that build left unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_xemu_texture_packs as tp  # noqa: E402


def cmd_key(args: argparse.Namespace) -> int:
    width, height = (int(v) for v in args.size.lower().split("x"))
    level0 = Path(args.level0).read_bytes()
    palette = Path(args.palette).read_bytes() if args.palette else None
    print(tp.texture_key(int(args.fmt, 16), width, height, level0, palette))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    t = time.time()
    last = [0]

    def progress(done: int, total: int) -> None:
        if done - last[0] >= 500 or done == total:
            last[0] = done
            print(f"  {done}/{total} archive entries, {time.time() - t:.0f}s", file=sys.stderr)

    rows, errors = tp.catalog_disc(Path(args.disc), jobs=args.jobs, progress=progress)
    named = tp.name_from_ledgers(rows, ROOT)
    counts = {}
    if args.retail:
        counts = tp.compare_with_retail(rows, tp.read_catalog(Path(args.retail)))
    tp.write_catalog(rows, Path(args.out), source={
        "disc": str(Path(args.disc).resolve()), "disc_size": Path(args.disc).stat().st_size,
        "seconds": round(time.time() - t, 1), "vs_retail": counts})
    print(f"{len(rows)} texture descriptors, {len({r.key for r in rows})} unique keys, {named} named from the "
          f"ledgers, {len(errors)} unstructured entries skipped; vs retail {counts or '(not compared)'} -> {args.out}")
    return 0


def _select(rows, args):
    out = rows
    if args.name:
        needle = args.name.casefold()
        out = [r for r in out if needle in r.name.casefold()]
    if getattr(args, "file", None):
        wanted = args.file.casefold()
        out = [r for r in out if r.file.casefold() == wanted]
    if args.key:
        out = [r for r in out if r.key == args.key or r.wild == args.key]
    if args.outer is not None:
        out = [r for r in out if r.outer == args.outer]
    if args.chunk is not None:
        out = [r for r in out if r.chunk == args.chunk]
    if getattr(args, "changed", False):
        out = [r for r in out if r.changed == "changed"]
    return out


def cmd_find(args: argparse.Namespace) -> int:
    rows = _select(tp.read_catalog(Path(args.catalog)), args)
    for r in rows[: args.limit]:
        print(f"{r.key}\t{r.kind}\t{r.file or '-'}\t{r.outer}:{r.chunk}@{r.descriptor}\t{r.width}x{r.height}\t"
              f"{tp.format_name(r.fmt)}\t{r.changed or '-'}\t{r.name}")
    print(f"{len(rows)} rows", file=sys.stderr)
    return 0


def cmd_name_dump(args: argparse.Namespace) -> int:
    rows = tp.name_dump(Path(args.dump), tp.read_catalog(Path(args.catalog)))
    out = Path(args.out) if args.out else Path(args.dump) / "named.tsv"
    with out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["key", "size", "fmt", "source", "match", "dynamic", "names", "png"])
        for r in rows:
            writer.writerow([r.key, r.size, r.fmt, r.source, r.match, int(r.dynamic), r.names, r.png])
    summary = {}
    for r in rows:
        summary[r.match] = summary.get(r.match, 0) + 1
    print(f"{len(rows)} dumped textures: {summary}; dynamic {sum(r.dynamic for r in rows)} -> {out}")
    return 0


def cmd_workspace(args: argparse.Namespace) -> int:
    rows = tp.read_catalog(Path(args.catalog))
    if args.keys:
        wanted = [k.strip() for k in args.keys.split(",") if k.strip()]
        chosen = {k: next((r.name for r in rows if r.key == k), "") for k in wanted}
    else:
        args.key = args.outer = args.chunk = None
        chosen = {r.key: r.name for r in _select(rows, args)}
    dump = Path(args.dump) if args.dump else None
    targets = []
    staging = Path(args.out) / ".guest"
    by_key = {r.key: r for r in rows}
    archive = tp.DiscArchive(Path(args.disc)) if args.disc else None
    try:
        for key, label in sorted(chosen.items()):
            guest = dump / f"{key}.png" if dump and (dump / f"{key}.png").is_file() else None
            if guest is None and archive is not None and key in by_key:
                staging.mkdir(parents=True, exist_ok=True)
                try:
                    guest = staging / f"{key}.png"
                    tp.guest_image(Path(args.disc), by_key[key], archive).save(guest)
                except tp.TexturePackError as exc:
                    print(f"  {key}: no guest image ({exc})", file=sys.stderr)
                    guest = None
            targets.append((key, label or key, guest))
    finally:
        if archive is not None:
            archive.close()
    path = tp.make_workspace(targets, Path(args.out), scale=args.scale)
    print(f"{len(targets)} textures -> {path}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    pack = tp.build_pack(Path(args.manifest), tp.read_catalog(Path(args.catalog)), Path(args.out),
                         disc_label=args.disc_label, overwrite=args.overwrite)
    print(f"pack {pack['name']!r}: {len(pack['textures'])} images -> {args.out}")
    for key, entry in pack["textures"].items():
        notes = "; ".join(entry["notes"]) if entry["notes"] else "ok"
        print(f"  {key}  {entry['asset']}  guest {entry['guest']}  x{entry['scale']}  {notes}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    catalog = tp.read_catalog(Path(args.catalog)) if args.catalog else None
    report = tp.validate_pack(Path(args.pack), catalog)
    print(json.dumps(report, indent=2))
    return 1 if report["errors"] else 0


def cmd_install(args: argparse.Namespace) -> int:
    target = tp.install_pack(Path(args.pack), Path(args.packs_root), overwrite=args.overwrite)
    print(f"installed -> {target} (RELOAD touched: a running Edition re-reads its packs within a second)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("key", help="the x2 key of raw level-0 bytes (and palette)")
    p.add_argument("--fmt", required=True, help="NV2A colour format, hex (0b = P8, 0c = DXT1, 06 = A8R8G8B8)")
    p.add_argument("--size", required=True, help="WxH")
    p.add_argument("level0")
    p.add_argument("palette", nargs="?")
    p.set_defaults(func=cmd_key)

    p = sub.add_parser("catalog", help="every keyable texture on a disc")
    p.add_argument("disc")
    p.add_argument("out")
    p.add_argument("--retail", help="a catalog of the retail disc: marks textures the mod changed")
    p.add_argument("--jobs", type=int, default=8)
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("find", help="search a catalog")
    p.add_argument("catalog")
    p.add_argument("--name")
    p.add_argument("--file", help="archive file name, e.g. 18H0.IFF or s18dd.iff")
    p.add_argument("--key")
    p.add_argument("--outer", type=int)
    p.add_argument("--chunk", type=int)
    p.add_argument("--changed", action="store_true", help="only textures the mod changed")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("name-dump", help="name the textures an Edition dump recorded")
    p.add_argument("dump")
    p.add_argument("catalog")
    p.add_argument("--out")
    p.set_defaults(func=cmd_name_dump)

    p = sub.add_parser("workspace", help="guest images + templates to redraw")
    p.add_argument("catalog")
    p.add_argument("out")
    p.add_argument("--keys")
    p.add_argument("--name")
    p.add_argument("--changed", action="store_true")
    p.add_argument("--file", help="archive file name, e.g. 18H0.IFF")
    p.add_argument("--dump", help="an Edition dump folder holding the guest PNGs")
    p.add_argument("--disc", help="the disc the catalog was made from: decode guest images from it")
    p.add_argument("--scale", type=int, default=4)
    p.set_defaults(func=cmd_workspace)

    p = sub.add_parser("build", help="build a pack folder from a manifest")
    p.add_argument("manifest")
    p.add_argument("catalog")
    p.add_argument("out")
    p.add_argument("--disc-label", default="")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="check a pack folder")
    p.add_argument("pack")
    p.add_argument("--catalog")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("install", help="copy a pack into the Edition and reload")
    p.add_argument("pack")
    p.add_argument("--packs-root", default=str(tp.DEFAULT_PACKS_ROOT))
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_install)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except tp.TexturePackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
