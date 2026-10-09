#!/usr/bin/env python3
"""Re-seat the SOFTDRINK team defense packs on the books this Studio's complete-offense compile makes.

A custom defense pack records the SHA-256 of the book it was authored on: that team's retail book with the
team's complete offense already compiled. Beta 76.5's deep-back flat repair (job d2b, ``forward_back_flats`` in
``compile_offense``) changed the compiled offense, so every ``data/playbooks/softdrink_<team>_defense.2k5book``
stopped matching its book and a Studio build with the modern books and their defenses was refused ("Custom
defense source changed"), minutes into the preflight or after the project build.

This tool compiles each team's complete offense onto the retail book exactly as a build does, then for every
defense pack that no longer matches:

* refuses unless every record the pack depends on is still where it was: same team, same formation and play
  counts, the formations and plays it replaces still carry the names it recorded, and every defense play still
  passes ``validate_defense_pack_play`` (donor shape signature, donor header, formation, personnel, front);
* re-stamps ONLY ``base.book_fingerprint`` and ``base.donor_node_count`` (the plays and formations are the
  pack's own authored data and are never touched);
* proves the result by compiling it on the composed book with the full offline check, and by comparing the
  formation and play indices it replaces with the recorded ``pb/defense_manifest.json`` compile.

``--check`` (default) writes nothing and exits 1 when any pack is stale or refused: run it as a release gate
after the LAST change to any complete-offense pack, ``compile_offense`` or ``nfl2k5_play_library``. ``--apply``
writes the re-stamped packs; running it again changes nothing.

Reads the retail disc only. The input is never copied and no disc is written.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_scoring as scoring  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402

PLAYBOOKS = ROOT / "data" / "playbooks"
MANIFEST = ROOT / "pb" / "defense_manifest.json"


def _packs(pattern: str, schema: str) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(PLAYBOOKS.glob(pattern)):
        pack = pk.load_pack(path)
        if pack.schema == schema and not any(p.preset_recipe for p in pack.plays):
            found[pack.book.team] = path
    return found


def offense_packs() -> dict[str, Path]:
    """team -> complete offense pack (the books every defense pack is authored on)."""
    return _packs("softdrink_*_modern.2k5book", pk.OFFENSE_SCHEMA)


def defense_packs() -> dict[str, Path]:
    """team -> custom team defense pack (the preset-recipe softdrink_modern_defense pack is not one)."""
    return _packs("softdrink_*_defense.2k5book", pk.DEFENSE_SCHEMA)


def rebase(pack: pk.PlaybookPack, book, body: bytes) -> pk.PlaybookPack:
    """The same pack with its base re-stamped for ``book``, or ValueError naming what no longer holds."""
    base = pack.base
    if base.donor_formation_count != len(book.formations) or base.donor_play_count != len(book.plays):
        raise ValueError(
            f"the book has {len(book.formations)} formations and {len(book.plays)} plays; the pack was authored on "
            f"{base.donor_formation_count} and {base.donor_play_count}")
    for formation in pack.formations:
        if (formation.replace_index is None or not formation.replace_name
                or not 0 <= formation.replace_index < len(book.formations)
                or book.formations[formation.replace_index].name != formation.replace_name):
            raise ValueError(f"formation {formation.id} no longer replaces a formation named {formation.replace_name!r}")
        if not 0 <= formation.donor.index < len(book.formations) \
                or book.formations[formation.donor.index].name != formation.donor.name:
            raise ValueError(f"formation {formation.id} donor {formation.donor.name!r} moved")
    for play in pack.plays:
        if (play.play_type != "defense" or play.replace_index is None or not play.replace_name
                or not 0 <= play.replace_index < len(book.plays)
                or book.plays[play.replace_index].name != play.replace_name):
            raise ValueError(f"play {play.id} no longer replaces a defense play named {play.replace_name!r}")
        try:
            pk.validate_defense_pack_play(play, book, body)
        except pk.PlaybookPackError as exc:
            raise ValueError(f"play {play.id}: {exc}") from exc
    return replace(pack, base=replace(base, book_fingerprint=pk.book_fingerprint(body),
                                      donor_node_count=book.node_count))


def check_team(job: tuple[str, str, str, str, bool]) -> dict:
    disc, team, offense_path, defense_path, apply = job
    recode = pk._outer_image()
    xbe = scoring.executable_bytes(Path(disc))
    with recode.OuterImage(Path(disc)) as image:
        retail = image.read_entry(recode.BOOK_ENTRIES[team])
    composed = pk.apply_pack_to_resource(retail, pk.load_pack(offense_path), asset_id=f"book:{team}", xbe=xbe).replacement
    book, body = insp.parse_playbook_resource(composed, asset_id=f"book:{team}"), composed[pk.RESOURCE_HEADER_SIZE:]
    pack = pk.load_pack(defense_path)
    row = {"team": team, "pack": str(Path(defense_path).relative_to(ROOT)),
           "recorded_fingerprint": pack.base.book_fingerprint, "composed_fingerprint": pk.book_fingerprint(body),
           "recorded_node_count": pack.base.donor_node_count, "composed_node_count": book.node_count}
    if pk.book_fingerprint(body) == pack.base.book_fingerprint:
        return {**row, "status": "current"}
    try:
        rebased = rebase(pack, book, body)
        check = pk.check_pack(rebased, book=book, body=body, xbe=xbe)
        if not check.ok:
            raise ValueError("the offline pack check fails: " + check.text())
        compiled = pk.apply_pack_to_resource(composed, rebased, asset_id=f"book:{team}", xbe=xbe)
    except (ValueError, pk.PlaybookPackError) as exc:
        return {**row, "status": "refused", "reason": str(exc)}
    row["replaced_formation_indices"] = list(compiled.report["replaced_formation_indices"])
    row["replaced_play_indices"] = list(compiled.report["replaced_play_indices"])
    if apply:
        pk.save_pack(rebased, defense_path)
    return {**row, "status": "rebased" if apply else "stale"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--disc", required=True, type=Path, help="the retail USA NFL 2K5 XISO (read only)")
    parser.add_argument("--teams", nargs="*", default=[], help="limit to these team codes")
    parser.add_argument("--apply", action="store_true", help="write the re-stamped packs (default: check only)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--receipt", type=Path, help="write the JSON receipt here (new file)")
    args = parser.parse_args(argv)
    offense, defense = offense_packs(), defense_packs()
    missing = sorted(set(defense) - set(offense))
    if missing:
        print("defense packs without a complete offense pack:", ", ".join(missing), file=sys.stderr)
        return 2
    teams = [t for t in sorted(defense) if not args.teams or t in args.teams]
    jobs = [(str(args.disc), t, str(offense[t]), str(defense[t]), args.apply) for t in teams]
    if args.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(check_team, jobs))
    else:
        rows = [check_team(job) for job in jobs]
    recorded = {}
    if MANIFEST.is_file():
        recorded = {r["team"]: r["compile"] for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["teams"]}
    for row in rows:
        old = recorded.get(row["team"])
        if old is not None and "replaced_play_indices" in row:
            row["same_replaced_indices_as_pb_manifest"] = (
                old.get("replaced_formation_indices") == row["replaced_formation_indices"]
                and old.get("replaced_play_indices") == row["replaced_play_indices"])
        print(f"{row['team']:4} {row['status']:8} {row.get('reason', '')}", flush=True)
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("current", "stale", "rebased", "refused")}
    print(json.dumps(counts), flush=True)
    if args.receipt:
        with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({"schema": "b77_e3_defense_pack_rebase/v1", "counts": counts, "teams": rows}, stream, indent=2)
            stream.write("\n")
    return 0 if counts["stale"] == counts["refused"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
