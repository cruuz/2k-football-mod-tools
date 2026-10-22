"""One ordered compile for every writer that edits MASTER or a CPU playbook.

Design Play/Formation, Assignment Routes, Who lines up and Fine-tune Plays each
used to compile straight from the retail MASTER and retail CPU books, so staging
two of them together would have made the later one silently discard the earlier
one.  The studio therefore refused the combination.

Every one of those writers already works on any body of the right shape, so they
can be chained instead:

    retail MASTER --design--> designed MASTER --who-lines-up + routes--> final MASTER
    retail CPU book --design CPU calls--> designed book --Fine-tune--> final book

Nothing here writes game files.  Each step keeps its own verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from . import apf2k8_play_codec as c
from . import apf2k8_splb_writer as splb
from .apf2k8_package_map_writer import compile_master_play_edits
from .apf2k8_play_design_build import compile_cpu_calls, pack_resource, read_resource, CPU_PINS
from .apf2k8_play_designer import compile_design, normalize_plan, sha
from .errors import ValidationError


@dataclass(frozen=True)
class DesignState:
    """What Design alone does to MASTER and to the CPU books it names."""

    master: bytes
    books: Mapping[int, bytes]
    report: dict
    plan: dict


def design_state(master_retail: bytes, retail_book_body: Callable[[int], bytes], plan: Mapping) -> DesignState:
    """Apply a design plan to the retail MASTER and to the CPU books it calls into."""

    plan = normalize_plan(plan)
    compiled = compile_design(master_retail, plan)
    books: dict[int, bytes] = {}
    for outer in sorted({row["outer"] for row in plan["cpu_calls"]}):
        calls = [row for row in plan["cpu_calls"] if row["outer"] == outer]
        replacement, _receipt = compile_cpu_calls(
            retail_book_body(outer), outer, master_retail, compiled.replacement, calls)
        books[outer] = replacement
    return DesignState(compiled.replacement, books, compiled.report, plan)


def compose_master(base: bytes, package_maps: Iterable = (), routes: Iterable = ()) -> bytes:
    """Who-lines-up maps, then route clones, on top of a (possibly designed) MASTER."""

    maps, route_requests = tuple(package_maps), tuple(routes)
    if not maps and not route_requests:
        return base
    return compile_master_play_edits(base, package_maps=maps, routes=route_requests)


def play_count(master: bytes) -> int:
    return len(c.Book.from_bytes(master).plays)


def group_by_outer(changes: Iterable) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for change in changes:
        grouped.setdefault(change.outer_index, []).append(change)
    return grouped


def check_fine_tune(base_books: Mapping[int, bytes], retail_book_body: Callable[[int], bytes],
                    changes: Iterable, master_plays: int) -> None:
    """Compile (in memory) every Fine-tune book on top of its designed base."""

    for outer, group in sorted(group_by_outer(changes).items()):
        body = base_books.get(outer)
        if body is None:
            body = retail_book_body(outer)
        splb.compile_book(splb.parse_book(body, outer), group, master_play_count=master_plays)


@dataclass(frozen=True)
class Combined:
    entries: dict[int, bytes]
    reports: dict[int, dict]
    master: bytes
    books: dict[int, bytes]
    design_report: dict


def build_combined(index: Path, plan: Mapping, *, package_maps: Iterable = (), routes: Iterable = (),
                   splb_changes: Iterable = ()) -> Combined:
    """Compile Design plus Who-lines-up, Assignment Routes and Fine-tune Plays into outer entries.

    The result keeps one entry per touched outer: MASTER (180) and each CPU book.
    """

    plan = normalize_plan(plan)
    maps, route_requests, changes = tuple(package_maps), tuple(routes), tuple(splb_changes)
    master_resource = read_resource(index, 180)
    cache: dict[int, object] = {}

    def retail_resource(outer: int):
        if outer not in cache:
            cache[outer] = read_resource(index, outer)
        return cache[outer]

    state = design_state(master_resource.body, lambda outer: retail_resource(outer).body, plan)
    master_final = compose_master(state.master, maps, route_requests)
    plays = play_count(master_final)
    entries: dict[int, bytes] = {}
    reports: dict[int, dict] = {}
    if master_final != master_resource.body:
        entry, receipt = pack_resource(master_resource, master_final)
        entries[180] = entry
        reports[180] = {**receipt, "kind": "master", "plays_after": plays}

    grouped = group_by_outer(changes)
    for outer in sorted(set(state.books) | set(grouped)):
        base = state.books.get(outer)
        if outer in grouped:
            # Fine-tune rewrites the entry prefixes of the records it names, on top of the designed book.
            built = splb.build_book_patch(index, grouped[outer], base_body=base, master_play_count=plays)
            entries[outer] = built.entry_bytes
            reports[outer] = {**dict(built.report), "kind": "cpu_book", "design_calls": base is not None}
        else:
            resource = retail_resource(outer)
            entry, receipt = pack_resource(resource, base)
            entries[outer] = entry
            reports[outer] = {**receipt, "kind": "cpu_book", "design_calls": True}
    return Combined(entries, reports, master_final, {**dict(state.books)}, state.report)


def uses_design(modifications: Iterable) -> bool:
    from .apf2k8_play_designer import PROVIDER_KIND
    return any(m.kind == PROVIDER_KIND for m in modifications)


__all__ = ["Combined", "DesignState", "build_combined", "check_fine_tune", "compose_master", "design_state",
           "group_by_outer", "play_count", "uses_design", "CPU_PINS", "sha"]
