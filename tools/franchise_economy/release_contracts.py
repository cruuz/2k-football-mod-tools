"""b81 #48 (coordinator 11/27): re-fit every club player's contract in a release roster-edits document from a current
nflverse historical_contracts snapshot (OverTheCap), mapped by gsis id.

DESIGN: the import's own rules (import_contracts.contract_fit: an observed 2026-on cap schedule is fitted as it is, an
absent one keeps OTC's term at the deal's APY, a 2026 draftee takes the draft-slot schedule, no current term takes the
one-year minimum), with the 2026 charge never under the one-year minimum (OTC prorates an in-season signing or trade;
the game charges a whole season). Identity is the roster refresh's own gsis id for each record (roster_refresh.players).
The document changes only through mechanisms it already uses for contracts:
  * a player the refresh initializes (a record without a contract) keeps his initializer row, with the fitted fields;
  * any other player on a club list of the refresh plan gets a contract correction (the five fields before and after,
    its rule and its source), the mechanism the refresh already uses for Quenton Nelson;
  * a player the plan lists as injured (status RES, who rejoins his club on IR in the writer and is outside the plan's
    lists) gets a contract-only entry appended to the document's edits, as the fc import layered its contracts.
Players with an existing correction (a reviewed in-season trade charge), players with no active OTC contract today, and
schedules the import leaves to review keep their contract and are listed in the report. Fifth-year options are what
OTC's season history holds (an exercised option is a cap year; an unexercised one is not), as the import reads them.

  python3 tools/franchise_economy/release_contracts.py --doc DOC.json --edition 128|64
      --contracts historical_contracts_active.json --out NEW.json --report REPORT.json
The contracts JSON is the active rows of the release parquet with a meta block (url, asset_updated_at, parquet_sha256,
rows); a parquet beside it must match parquet_sha256. The written rosters come from the retail disc (NFL2K5_RETAIL_XISO)
the way a build writes them on a user's dump (tests/mod_editor/test_b780_m64b_console_memory.users_dump_base).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402
from tools.franchise_economy.contracts import FIELDS  # noqa: E402
from tools.franchise_economy.import_contracts import contract_fit, identifier, term_end  # noqa: E402

RULE = ("b81 #48: the player's current OverTheCap contract by gsis id, fitted by "
        "tools/franchise_economy/import_contracts.contract_fit (2026 cap schedule; without one, OTC's term at APY; "
        "2026 charge at least the one-year minimum)")
FALLBACK_SOURCE = "https://github.com/nflverse/nflverse-data/releases/tag/contracts"
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))


def load_contracts(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(Path(path).read_text())
    meta = data["meta"]
    for key in ("url", "asset_updated_at", "parquet_sha256", "rows"):
        if not meta.get(key):
            raise ValueError(f"contract snapshot meta lacks {key}")
    if meta["rows"] != len(data["rows"]):
        raise ValueError("contract snapshot row count differs from its meta")
    parquet = Path(path).with_name("historical_contracts.parquet")
    if parquet.exists() and hashlib.sha256(parquet.read_bytes()).hexdigest() != meta["parquet_sha256"]:
        raise ValueError("the parquet beside the snapshot is not the one it was converted from")
    return meta, data["rows"]


def users_dump_base(source: dict) -> bytes:
    """The main roster a build makes from a retail dump before the dated refresh (the roster edits pass with the
    refresh deferred, then the 2026 team names); the same steps as test_b780_m64b_console_memory.users_dump_base."""
    from mod_editor.core import nfl2k5_free_agents, nfl2k5_team_names_2026 as names
    retail = rr.load_image(RETAIL).to_body()
    edits = {k: v for k, v in source.items() if k not in ("roster_refresh", "created_history")}
    if nfl2k5_free_agents.is_pack_input(edits):
        edits = dict(edits, modern_free_agents="2026-10-05")
    if edits.get("modern_free_agents"):
        edits = dict(edits, restore_historic_spare_capacity=True)
    body, _receipt = rr.apply_body(retail, edits, scheme="one_pool", refresh_follows=True)
    with rr._outer_image()(RETAIL) as archive:
        entry = rr._entry(archive)
        header = archive.read(entry.virtual_offset, 32)
    payload, _ = names.apply(header + body)
    return payload[32:]


def written_body(doc: dict, edition: int) -> bytes:
    """The club rosters a build writes from this document: the 128 MB capacity growth and the dated refresh, or the
    64 MB retail fit's writers, on the user's-dump base."""
    base = users_dump_base(doc)
    if edition == 64:
        from tools import nfl2k5_roster_retail_fit as fit
        body, *_ = fit._writers(base, doc["roster_refresh"], doc.get("created_history"))
        return body
    from mod_editor.core import nfl2k5_college_check as cc
    from mod_editor.core import nfl2k5_roster_arena as arena
    grown, _ = arena.migrate(base, reserves_16=False, capacity_records=doc["free_agent_capacity"]["records"])
    out, _ = refresh.apply_body(grown, doc["roster_refresh"])
    out, _ = cc.heal_null_references(out, source="capacity roster")
    return out


def club_players(body: bytes) -> dict[int, tuple[int, object]]:
    view = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
    out = {}
    for team in view.teams[:32]:
        for p in view.team_players(team.index) + view.reserve_players(team.index):
            if p.pool == "primary":
                out[p.index] = (team.index, p)
    return out


def fields_of(player) -> dict[str, int]:
    return {k: player.record.get(k) for k in sorted(FIELDS)}


def model_end(fields: dict[str, int]) -> int:
    return 2026 + fields["contract_remaining"] - 1 if fields["contract_remaining"] else 2025


def choose(candidates: list[dict], review: dict | None) -> tuple[dict | None, str | None]:
    if not candidates:
        return None, None
    if len(candidates) > 1 and review and "active_value_millions" in review:
        picked = [r for r in candidates if r["value"] == review["active_value_millions"]]
        if len(picked) == 1:
            return picked[0], "identity review"
    if len(candidates) > 1:
        best = sorted(candidates, key=lambda r: (int(r.get("year_signed") or 0), float(r.get("value") or 0)))[-1]
        return best, f"{len(candidates)} active rows: latest signed"
    return candidates[0], None


def refit(doc: dict, body: bytes, rows: list[dict], data: dict, *, as_of: str,
          force_correction: frozenset = frozenset()) -> tuple[dict, dict]:
    plan = doc["roster_refresh"]
    owned = {i for t in plan["teams"] for i in t["active"] + t["reserves"]}
    plan_rows = {r["index"]: r for r in plan["players"]}
    inits = {r["index"]: r for r in plan.get("contract_initializations", [])}
    kept = {c["index"] for c in plan.get("contract_corrections", [])}
    reviews = {identifier(r.get("gsis_id")): r for r in
               json.loads((ROOT / "fc/data/identity_review.json").read_text())["entries"] if r.get("gsis_id")}
    by_gsis = defaultdict(list)
    for r in rows:
        if r.get("is_active") in (True, 1, "TRUE", "true") and int(r.get("year_signed") or 9999) <= 2026:
            by_gsis[identifier(r.get("gsis_id"))].append(r)
    report = Counter()
    changes, untouched = [], defaultdict(list)
    new_doc = copy.deepcopy(doc)
    new_plan = new_doc["roster_refresh"]
    new_inits = {r["index"]: r for r in new_plan.get("contract_initializations", [])}
    corrections = new_plan.setdefault("contract_corrections", [])
    layer = []
    for index, (team, p) in sorted(club_players(body).items()):
        report["club players"] += 1
        row_plan = plan_rows.get(index, {})
        gsis = identifier(row_plan.get("gsis_id"))
        label = {"index": index, "name": p.display, "team": team, "gsis_id": gsis, "status": row_plan.get("status")}
        injured = index not in owned and row_plan.get("status") in refresh.INJURED_STATUSES
        if index not in owned and not injured:
            untouched["on a club but outside the refresh plan"].append(label)
            continue
        if index in kept:
            untouched["existing reviewed contract correction kept"].append(label)
            continue
        row, how = choose(by_gsis.get(gsis, []), reviews.get(gsis))
        if row is None:
            untouched["no active OTC contract today: kept"].append(label)
            continue
        if how:
            report[f"choice: {how}"] += 1
        try:
            fit, modeled, _ = contract_fit(p, row, data, floor_opening=True)
        except ValueError as exc:
            untouched[f"left to review: {exc}"].append(label)
            continue
        now, new = fields_of(p), {k: fit["fields"][k] for k in sorted(FIELDS)}
        report["matched"] += 1
        if now == new:
            report["unchanged"] += 1
            continue
        kind = (modeled or {}).get("rule", "observed 2026 cap schedule")
        if modeled and "opening_floor_dollars" in modeled:
            kind += " (2026 raised to the minimum)"
        change = {**label, "was": now, "fields": new, "kind": kind, "model_end_was": model_end(now),
                  "model_end": model_end(new), "real_end": term_end(row), "source": row.get("player_page"),
                  "otc_team": row.get("team"), "apy_millions": row.get("apy"),
                  "source_cap_dollars": fit["source_cap_dollars"],
                  "represented_cap_dollars": fit["represented_cap_dollars"], "mechanism": None}
        source = row.get("player_page") or FALLBACK_SOURCE
        if injured:
            layer.append({"fields": new, "first": p.first, "index": index, "last": p.last, "pool": "primary"})
            change["mechanism"] = "edits layer (injured, rejoins on IR)"
        elif (index in new_inits and index not in force_correction
              and now == {k: inits[index]["fields"][k] for k in sorted(FIELDS)}):
            new_inits[index].update(fields=new, fit=fit, rule=RULE + f" [{kind}]", source=source, as_of=as_of)
            change["mechanism"] = "initializer"
        else:
            corrections.append({"index": index, "first": p.first, "last": p.last, "was": now, "fields": new,
                                "source": source, "rule": RULE + f" [{kind}]", "as_of": as_of})
            change["mechanism"] = "correction"
        changes.append(change)
    if layer:
        new_doc["edits"] = list(new_doc["edits"]) + layer
    summary = dict(report)
    summary["changed"] = len(changes)
    summary["term_changed"] = sum(c["model_end"] != c["model_end_was"] for c in changes)
    summary["value_only_changed"] = sum(c["model_end"] == c["model_end_was"] for c in changes)
    summary["by_kind"] = dict(Counter(c["kind"] for c in changes))
    summary["by_mechanism"] = dict(Counter(c["mechanism"] for c in changes))
    summary["untouched"] = {k: len(v) for k, v in untouched.items()}
    return new_doc, {"summary": summary, "changes": changes, "untouched": untouched}


def verify(body_new: bytes, changes: list[dict]) -> list[dict]:
    players = club_players(body_new)
    return [c for c in changes if c["index"] not in players or fields_of(players[c["index"]][1]) != c["fields"]]


def run(doc: dict, edition: int, rows: list[dict], data: dict, as_of: str):
    body = written_body(doc, edition)
    force = frozenset()
    for _ in range(3):
        new_doc, result = refit(doc, body, rows, data, as_of=as_of, force_correction=force)
        body_new = written_body(new_doc, edition)
        missed = verify(body_new, result["changes"])
        retry = {c["index"] for c in missed if c["mechanism"] == "initializer"}
        if not missed or not retry - force:
            break
        force = force | retry   # the record already held a contract, so the initializer does not run: correct it
    if missed:
        raise SystemExit(f"{len(missed)} contracts did not land: {[c['name'] for c in missed[:10]]}")
    result["summary"]["initializer_retried_as_correction"] = sorted(force)
    return new_doc, result, body, body_new


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", type=Path, required=True)
    ap.add_argument("--edition", type=int, choices=(128, 64), required=True)
    ap.add_argument("--contracts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    meta, rows = load_contracts(args.contracts)
    doc = json.loads(args.doc.read_text(encoding="utf-8"))
    data = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
    new_doc, result, body, body_new = run(doc, args.edition, rows, data, meta["asset_updated_at"][:10])
    new_doc["b81_contract_refresh"] = {
        "job": "b81-contracts (#48)", "rule": RULE, "source": meta["url"], "asset_updated_at": meta["asset_updated_at"],
        "parquet_sha256": meta["parquet_sha256"], "changed": result["summary"]["changed"],
        "term_changed": result["summary"]["term_changed"], "value_only_changed": result["summary"]["value_only_changed"],
        "by_mechanism": result["summary"]["by_mechanism"], "kept": result["summary"]["untouched"]}
    text = json.dumps(new_doc, indent=1) + "\n"   # the release documents' own form (indent 1, ASCII escapes)
    args.out.write_text(text, encoding="utf-8")
    result["summary"].update(doc_sha256=hashlib.sha256(args.doc.read_bytes()).hexdigest(),
                             out_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                             body_sha256=hashlib.sha256(body).hexdigest(),
                             body_new_sha256=hashlib.sha256(body_new).hexdigest(), snapshot=meta)
    args.report.write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps(result["summary"], indent=1, default=str))


if __name__ == "__main__":
    main()
