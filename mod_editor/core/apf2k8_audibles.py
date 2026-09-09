"""Balance the three proved CPU audible tags using only same-record plays.

No name heuristics: MASTER play +4 >> 28 is the play family (0 = offense,
not 'run'); +8 bit 1 marks passes and bit 3 marks runs. The retail classifiers
at 0x84865180..19C and 0x84865078..88 consume those flags. Y=3 is preserved
unless it is the only donor of the missing kind. The runtime loop skips tags
already present (0x84864BF4..BFC); the result remains unwitnessed in game.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import apf2k8_splb_writer as splb
from .apf2k8_playbook_route_writer import read_master_play_body
from .errors import ValidationError


CPU_OFFENSE_BOOKS = (130, 259, 369, 767, 891, 943, 1411)
AUDIBLE_TAGS = frozenset((0, 1, 2))
SCHEMA = "apf2k8_cpu_audibles/v1"


@dataclass(frozen=True)
class PlayMetadata:
    index: int
    name: str
    family: int
    flags: int

    @property
    def kind(self) -> str:
        if self.family != 0:
            return "special_or_defense"
        bits = self.flags & 0xA
        return {2: "pass", 8: "run"}.get(bits, "unknown")


def play_catalog(master_body: bytes) -> tuple[PlayMetadata, ...]:
    try:
        inventory = splb.playbook_inventory.parse_apf_body(master_body, 180, 0)
    except (ValueError, IndexError) as exc:
        raise ValidationError(f"Could not validate MASTER play metadata: {exc}") from exc
    return tuple(PlayMetadata(int(p["index"]), str(p["name"]),
                              int(p["flags_or_id_04"], 16) >> 28,
                              int(p["unknown_word_08"], 16))
                 for p in inventory["plays"])


def audible_census(book: splb.SplbBook, catalog: Iterable[PlayMetadata]) -> list[dict]:
    metadata = {p.index: p for p in catalog}
    rows = []
    for record in book.records:
        if not record.populated:
            continue
        if len({e.play_index for e in record.entries}) != len(record.entries):
            raise ValidationError(f"Record {record.record_index} repeats a play id; audible moves are ambiguous")
        if not splb.retail_tag_shape(record.entries):
            raise ValidationError(f"Record {record.record_index} does not have the retail audible tag set")
        if any(e.play_index not in metadata for e in record.entries):
            raise ValidationError(f"Record {record.record_index} references a play outside this MASTER catalog")
        slots = [{"tag": e.y, "play_index": e.play_index,
                  "kind": metadata[e.play_index].kind}
                 for e in record.entries if e.y in AUDIBLE_TAGS]
        slots.sort(key=lambda x: x["tag"])
        available = {kind: sum(metadata[e.play_index].kind == kind for e in record.entries)
                     for kind in ("run", "pass", "unknown", "special_or_defense")}
        counts = {kind: sum(s["kind"] == kind for s in slots) for kind in available}
        possible = available["run"] > 0 and available["pass"] > 0
        balanced = counts["run"] > 0 and counts["pass"] > 0
        rows.append({
            "record_index": record.record_index, "formation_index": record.formation_index,
            "category_index": record.category_index, "entry_count": len(record.entries),
            "slots": slots, "counts": counts, "available": available,
            "balanced": balanced, "possible": possible,
            "all_three_tags_present": {s["tag"] for s in slots} == AUDIBLE_TAGS,
            "reason": ("balanced" if balanced else "needs tag moves" if possible else
                       "no run play in this record" if not available["run"] else
                       "no pass play in this record"),
        })
    return rows


@dataclass(frozen=True)
class AudiblePlan:
    changes: tuple[splb.TagMove, ...]
    replacement: bytes
    report: dict


def plan_audibles(book: splb.SplbBook, catalog: Iterable[PlayMetadata]) -> AudiblePlan:
    """Minimal deterministic tag swaps; impossible formations get a receipt.

    Re-planning the output produces no moves. Never add a play to manufacture a
    guarantee: a pass-only Hail Mary record cannot acquire a run from itself.
    """
    if book.outer_index not in CPU_OFFENSE_BOOKS:
        raise ValidationError("CPU audible balancing applies to the seven offensive CPU books")
    catalog = tuple(catalog)
    metadata = {p.index: p for p in catalog}
    before = audible_census(book, catalog)
    changes: list[splb.TagMove] = []
    for row in before:
        if row["balanced"] or not row["possible"]:
            continue
        record = book.records[row["record_index"]]
        entries = record.entries
        for missing in ("run", "pass"):
            audible = [e for e in entries if e.y in AUDIBLE_TAGS]
            if any(metadata[e.play_index].kind == missing for e in audible):
                continue
            # Prefer an ordinary donor, then tag 3; never displace the only
            # audible of the other required kind.
            target = min((e for e in entries if metadata[e.play_index].kind == missing),
                         key=lambda e: (e.y != splb.UNTAGGED_Y, e.play_index))
            kinds = [metadata[e.play_index].kind for e in audible]
            choices = [e for e in audible if metadata[e.play_index].kind not in ("run", "pass")
                       or kinds.count(metadata[e.play_index].kind) > 1]
            if not choices:
                raise ValidationError(f"Record {record.record_index}: no safe audible slot to exchange")
            donor = min(choices, key=lambda e: (e.y, e.play_index))
            move = splb.TagMove(book.outer_index, record.record_index, donor.play_index, target.play_index)
            changes.append(move)
            entries = tuple(splb.SplbEntry(e.x, target.y if e.play_index == donor.play_index else
                                          donor.y if e.play_index == target.play_index else e.y,
                                          e.play_index) for e in entries)
    replacement = splb.compile_book(book, changes).replacement if changes else book.body
    after = audible_census(splb.parse_book(replacement, book.outer_index), catalog)
    if any(row["possible"] and not row["balanced"] for row in after):
        raise ValidationError("Audible reparse did not produce a run and pass in every eligible record")
    verification = (dict(splb.verify_book(book.body, replacement, changes)) if changes else
                    {"independent_reparse": True, "changed_byte_count": 0})
    report = {
        "schema": SCHEMA, "outer_index": book.outer_index, "book_name": book.name,
        "status": "unwitnessed", "offline_status": "tag writer and reparse verified",
        "before": before, "after": after, "tag_moves": len(changes),
        "balanced_before": sum(row["balanced"] for row in before),
        "balanced_after": sum(row["balanced"] for row in after),
        "impossible_records": [row["record_index"] for row in after if not row["possible"]],
        "verification": verification,
        "runtime_boundary": "Same-record authored tags only; the traced initializer fills missing tags, while actual CPU choices remain unwitnessed.",
    }
    return AudiblePlan(tuple(changes), replacement, report)


def build_audible_fix(index_path: Path, outer_index: int) -> tuple[AudiblePlan, splb.CompiledBook | None]:
    """Compile through the existing H7A/allocation/reparse gate; no file writes."""
    plan = plan_audibles(splb.read_book(index_path, outer_index),
                         play_catalog(read_master_play_body(index_path)))
    compiled = splb.build_book_patch(index_path, plan.changes) if plan.changes else None
    if compiled is not None and compiled.replacement != plan.replacement:
        raise ValidationError("Audible transport disagrees with the verified plan")
    return plan, compiled


def status() -> str:
    return "unwitnessed — same-record run/pass audible tags verified offline; records lacking either kind are reported"


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Compile and verify CPU audible tag recipes; print derived JSON only")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--outer", type=int, choices=CPU_OFFENSE_BOOKS, required=True)
    args = parser.parse_args()
    plan, compiled = build_audible_fix(args.index, args.outer)
    print(json.dumps({"changes": [splb.change_metadata(c) for c in plan.changes],
                      "audibles": plan.report,
                      "transport": dict(compiled.report) if compiled else None}, indent=2))
