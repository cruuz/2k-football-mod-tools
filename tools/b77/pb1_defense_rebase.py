#!/usr/bin/env python3
"""Re-seat the SOFTDRINK team defense packs on the b776 (pb1) offense books without touching defensive content.

The b776 offense packs append formations and plays into each book's free records, so the composed book a defense
pack is applied to has more records than the one it was authored on and job e3's rebase (same counts only) refuses.
This tool keeps every defense play and formation exactly as authored (assignments, flags, names, positions, donors)
and re-stamps only ``base`` (book fingerprint, donor formation / play / node counts) after proving, per team:

* every record the pack replaces is still the record it recorded (same index, same name) and every defense play
  still passes ``validate_defense_pack_play`` on the new book;
* the pack's appended records still fit (50 formations, 270 plays);
* the re-stamped pack passes the offline pack check (native scoring included) and compiles on the composed book.

``--check`` (default) writes nothing; ``--apply`` writes the re-stamped packs.  Reads the retail disc only.
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


def content(pack: pk.PlaybookPack) -> tuple:
    """Defensive content: everything but the personnel-group index (a pointer the offense compile may renumber)."""
    def form(f):
        row = f.to_json()
        row.pop("category_index", None)
        return repr(row)
    return (tuple(form(f) for f in pack.formations), tuple(p.to_json().__repr__() for p in pack.plays))


NAMES = ROOT / "pb" / "defense" / "category_names_v2.json"


def remap_categories(pack: pk.PlaybookPack, team: str, book) -> tuple[pk.PlaybookPack, dict]:
    """Point each defense formation at the same personnel-group record (by name) in ``book``.

    The b776 offense compile keeps a different set of offensive groups than the beta 77 compile the packs were
    authored on, so the records after them are numbered differently; the defense groups themselves are untouched.
    ``pb/defense/category_names_v2.json`` holds the name behind each recorded index on the authored-on book."""
    names = json.loads(NAMES.read_text(encoding="utf-8"))["teams"][team]
    moved, forms = {}, []
    for f in pack.formations:
        ci = f.category_index
        if ci is not None:
            name = names[str(ci)]
            hits = [c.index for c in book.categories if c.name == name]
            if len(hits) != 1:
                raise ValueError(f"formation {f.id}: personnel group {name!r} is not one record of the new book")
            if hits[0] != ci:
                moved[ci] = hits[0]
                f = replace(f, category_index=hits[0])
        forms.append(f)
    return replace(pack, formations=tuple(forms)), moved


def rebase(pack: pk.PlaybookPack, book, body: bytes) -> pk.PlaybookPack:
    for f in pack.formations:
        if f.replace_index is not None and (not 0 <= f.replace_index < len(book.formations)
                                            or book.formations[f.replace_index].name != f.replace_name):
            raise ValueError(f"formation {f.id} no longer replaces a formation named {f.replace_name!r}")
        if not 0 <= f.donor.index < len(book.formations) or book.formations[f.donor.index].name != f.donor.name:
            raise ValueError(f"formation {f.id} donor {f.donor.name!r} moved")
    for p in pack.plays:
        if p.replace_index is not None and (not 0 <= p.replace_index < len(book.plays)
                                            or book.plays[p.replace_index].name != p.replace_name):
            raise ValueError(f"play {p.id} no longer replaces a play named {p.replace_name!r}")
        try:
            pk.validate_defense_pack_play(p, book, body)
        except pk.PlaybookPackError as exc:
            raise ValueError(f"play {p.id}: {exc}") from exc
    add_f = sum(1 for f in pack.formations if f.replace_index is None)
    add_p = sum(1 for p in pack.plays if p.replace_index is None)
    if len(book.formations) + add_f > insp.FORMATION_CAPACITY or len(book.plays) + add_p > insp.PLAY_CAPACITY:
        raise ValueError("the defense pack's appended records no longer fit the book")
    return replace(pack, base=replace(pack.base, book_fingerprint=pk.book_fingerprint(body),
                                      donor_formation_count=len(book.formations), donor_play_count=len(book.plays),
                                      donor_node_count=book.node_count))


def check_team(job) -> dict:
    disc, team, offense_path, defense_path, apply = job
    recode = pk._outer_image()
    xbe = scoring.executable_bytes(Path(disc))
    with recode.OuterImage(Path(disc)) as image:
        retail = image.read_entry(recode.BOOK_ENTRIES[team])
    composed = pk.apply_pack_to_resource(retail, pk.load_pack(offense_path), asset_id=f"book:{team}", xbe=xbe).replacement
    book, body = insp.parse_playbook_resource(composed, asset_id=f"book:{team}"), composed[pk.RESOURCE_HEADER_SIZE:]
    pack = pk.load_pack(defense_path)
    original_pack = pack
    pack, moved = remap_categories(pack, team, book)
    row = dict(team=team, category_index_moves=moved, pack=str(Path(defense_path).relative_to(ROOT)), composed_fingerprint=pk.book_fingerprint(body),
               composed_formations=len(book.formations), composed_plays=len(book.plays), composed_nodes=book.node_count)
    if pk.book_fingerprint(body) == pack.base.book_fingerprint:
        return {**row, "status": "current"}
    try:
        rebased = rebase(pack, book, body)
        if content(rebased) != content(original_pack):
            raise ValueError("defensive content would change")
        check = pk.check_pack(rebased, book=book, body=body, xbe=xbe)
        if not check.ok:
            raise ValueError("the offline pack check fails: " + check.text()[-600:])
        compiled = pk.apply_pack_to_resource(composed, rebased, asset_id=f"book:{team}", xbe=xbe)
    except (ValueError, pk.PlaybookPackError) as exc:
        return {**row, "status": "refused", "reason": str(exc)}
    row.update(after_defense_formations=compiled.report["new_formation_count"],
               after_defense_plays=compiled.report["new_play_count"], after_defense_nodes=compiled.report["new_node_count"])
    if apply:
        pk.save_pack(rebased, defense_path)
    return {**row, "status": "rebased" if apply else "stale"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--disc", required=True, type=Path, help="the retail USA NFL 2K5 XISO (read only)")
    ap.add_argument("--teams", nargs="*", default=[])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args(argv)
    jobs = []
    for team in pk.TEAM_BOOKS:
        if args.teams and team not in args.teams:
            continue
        off = PLAYBOOKS / ("softdrink_giants_modern.2k5book" if team == "NYG" else f"softdrink_{team.lower()}_modern.2k5book")
        jobs.append((str(args.disc), team, str(off), str(PLAYBOOKS / f"softdrink_{team.lower()}_defense.2k5book"), args.apply))
    if args.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(check_team, jobs))
    else:
        rows = [check_team(j) for j in jobs]
    for r in rows:
        print(f"{r['team']:4} {r['status']:8} {r.get('reason', '')[:300]} nodes={r.get('after_defense_nodes')}", flush=True)
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("current", "stale", "rebased", "refused")}
    print(json.dumps(counts))
    if args.receipt:
        args.receipt.write_text(json.dumps(dict(schema="b776_pb1_defense_rebase/v1", counts=counts, teams=rows), indent=1)
                                + "\n", encoding="utf-8", newline="\n")
    return 0 if counts["refused"] == 0 and (args.apply or counts["stale"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
