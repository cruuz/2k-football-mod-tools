"""One lane step in a child process: ``python -m mod_editor.games lane …``.

    lane <game> <lane> catalogue --source SRC --out catalogue.json
    lane <game> <lane> plan      --source SRC --recipe R.json --catalogue C.json --out plan.json
    lane <game> <lane> build     --source SRC --destination NEW --recipe R.json \\
                                 --catalogue C.json [--work-dir DIR] --receipt receipt.json
    lane <game> <lane> verify    --source SRC --destination NEW --receipt receipt.json --out verdict.json

Two things need this.  The studio runs a long catalogue and every build
through it, so a lane that crashes takes a child process down and not the
window; and a writer is usable from a terminal before any window exists,
which is what "the CLI is the product's floor" has meant since RC80.

Every step prints progress lines while it works and exactly one verdict line
at the end, exits 0 or 1, and turns every failure into the lane's own
:class:`~mod_editor.games.contract.Refusal` sentence -- never a traceback.

The JSON files are the contract's own values, written whole: a catalogue
carries the lane tool's own ``document`` verbatim plus the targets the shell
draws, a receipt carries the tool's own receipt plus the declared ranges and
artifacts the harness checks.  They round-trip, so ``plan`` and ``build``
consume exactly what ``catalogue`` wrote and ``verify`` exactly what ``build``
wrote.

Standard library only; importable without Qt.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Optional, Sequence

from . import discover
from .contract import (
    Artifact,
    Catalogue,
    ContractError,
    DeclaredRange,
    Field,
    Lane,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    lane_page,
)

CATALOGUE_SCHEMA = "vc_game_lane_catalogue/v1"
PLAN_SCHEMA = "vc_game_lane_plan/v1"
RECEIPT_SCHEMA = "vc_game_lane_receipt/v1"
VERDICT_SCHEMA = "vc_game_lane_verdict/v1"

STEPS = ("catalogue", "plan", "build", "verify")


# --------------------------------------------------------------------------
# The contract's values as JSON, both ways.
# --------------------------------------------------------------------------

def field_json(item: Field) -> dict[str, Any]:
    return {
        "key": item.key,
        "kind": item.kind,
        "label": item.label,
        "help": item.help,
        "choices": list(item.choices),
        "minimum": item.minimum,
        "maximum": item.maximum,
        "read_only": item.read_only,
    }


def field_from_json(document: Mapping[str, Any]) -> Field:
    return Field(
        key=str(document["key"]),
        kind=str(document["kind"]),
        label=str(document["label"]),
        help=str(document.get("help", "")),
        choices=tuple(document.get("choices", ()) or ()),
        minimum=document.get("minimum"),
        maximum=document.get("maximum"),
        read_only=bool(document.get("read_only", False)),
    )


def target_json(target: Target) -> dict[str, Any]:
    return {
        "key": target.key,
        "label": target.label,
        "detail": target.detail,
        "budget": target.budget,
        "searchable": target.searchable,
        "raw": dict(target.raw),
        "fields": [field_json(item) for item in target.fields],
    }


def target_from_json(document: Mapping[str, Any]) -> Target:
    return Target(
        key=str(document["key"]),
        label=str(document["label"]),
        detail=str(document.get("detail", "")),
        budget=str(document.get("budget", "")),
        searchable=str(document.get("searchable", "")),
        raw=dict(document.get("raw", {}) or {}),
        fields=tuple(field_from_json(item) for item in document.get("fields", ()) or ()),
    )


def catalogue_json(catalogue: Catalogue, *, game_id: str = "", page: str = "") -> dict[str, Any]:
    return {
        "schema": CATALOGUE_SCHEMA,
        "game": game_id,
        "lane_id": catalogue.lane_id,
        "page": page,
        "source": catalogue.source,
        "catalogue_schema": catalogue.schema,
        "targets": [target_json(target) for target in catalogue.targets],
        "document": dict(catalogue.document),
    }


def catalogue_from_json(document: Mapping[str, Any]) -> Catalogue:
    if document.get("schema") != CATALOGUE_SCHEMA:
        raise Refusal(
            f"that catalogue file says schema {document.get('schema')!r}; this command reads "
            f"{CATALOGUE_SCHEMA}. Rebuild it with 'lane <game> <lane> catalogue'."
        )
    return Catalogue(
        schema=str(document["catalogue_schema"]),
        lane_id=str(document["lane_id"]),
        source=str(document["source"]),
        targets=tuple(target_from_json(item) for item in document.get("targets", ()) or ()),
        document=dict(document.get("document", {}) or {}),
    )


def _ranges_json(ranges: Sequence[DeclaredRange]) -> list[dict[str, Any]]:
    return [{"start": item.start, "length": item.length, "reason": item.reason} for item in ranges]


def _ranges_from_json(rows: Sequence[Mapping[str, Any]]) -> tuple[DeclaredRange, ...]:
    return tuple(
        DeclaredRange(int(row["start"]), int(row["length"]), str(row.get("reason", "")))
        for row in rows or ()
    )


def plan_json(plan: Plan) -> dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "lane_id": plan.lane_id,
        "target_keys": list(plan.target_keys),
        "declared_ranges": _ranges_json(plan.declared_ranges),
        "declared_bytes": plan.declared_bytes,
        "document": dict(plan.document),
    }


def receipt_json(receipt: Receipt) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "lane_id": receipt.lane_id,
        "receipt_schema": receipt.schema,
        "source": receipt.source,
        "destination": receipt.destination,
        "declared_ranges": _ranges_json(receipt.declared_ranges),
        "artifacts": [
            {"path": item.path, "sha256": item.sha256, "kind": item.kind}
            for item in receipt.artifacts
        ],
        "document": dict(receipt.document),
    }


def receipt_from_json(document: Mapping[str, Any]) -> Receipt:
    if document.get("schema") != RECEIPT_SCHEMA:
        raise Refusal(
            f"that receipt file says schema {document.get('schema')!r}; this command reads "
            f"{RECEIPT_SCHEMA}. Use the receipt 'lane <game> <lane> build' wrote."
        )
    return Receipt(
        schema=str(document["receipt_schema"]),
        lane_id=str(document["lane_id"]),
        source=str(document["source"]),
        destination=str(document["destination"]),
        declared_ranges=_ranges_from_json(document.get("declared_ranges", ())),
        document=dict(document.get("document", {}) or {}),
        artifacts=tuple(
            Artifact(str(item["path"]), str(item["sha256"]), str(item.get("kind", "")))
            for item in document.get("artifacts", ()) or ()
        ),
    )


def verdict_json(verdict: Verdict, *, lane_id: str = "") -> dict[str, Any]:
    return {
        "schema": VERDICT_SCHEMA,
        "lane_id": lane_id,
        "passed": verdict.passed,
        "summary": verdict.summary,
        "document": dict(verdict.document),
    }


# --------------------------------------------------------------------------
# Running one step
# --------------------------------------------------------------------------

def _read_json(path: Path, what: str) -> dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refusal(f"{path} cannot be read as the {what}: {exc}.") from exc
    except ValueError as exc:
        raise Refusal(f"{path} is not valid JSON, so it cannot be the {what}: {exc}.") from exc
    if not isinstance(document, dict):
        raise Refusal(f"{path} must hold a JSON object to be the {what}.")
    return document


def _write_json(path: Optional[Path], document: Mapping[str, Any]) -> None:
    if path is None:
        return
    target = Path(path)
    if target.parent and not target.parent.exists():
        raise Refusal(f"{target.parent} does not exist; make it before writing {target.name}.")
    try:
        target.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise Refusal(f"{target} could not be written: {exc}.") from exc


def _lane(game_id: str, lane_id: str, games_root: Optional[Path]) -> tuple[Any, Lane]:
    report = discover(games_root)
    for refused in report.refused:
        if refused.directory == game_id:
            raise Refusal(f"Game {game_id!r} could not be hosted: {refused.reason}")
    game = report.game(game_id)  # raises a Refusal naming the hosted games
    return game, game.lane(lane_id)  # raises a Refusal naming the lanes


def run(
    game_id: str,
    lane_id: str,
    step: str,
    *,
    source: Optional[Path] = None,
    destination: Optional[Path] = None,
    recipe: Optional[Path] = None,
    catalogue: Optional[Path] = None,
    receipt: Optional[Path] = None,
    out: Optional[Path] = None,
    work_dir: Optional[Path] = None,
    games_root: Optional[Path] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> tuple[int, str]:
    """Run one lane step; return ``(exit code, the one verdict line)``.

    Raises :class:`Refusal` (never anything else) when a step cannot run.
    """

    say = progress or (lambda line: None)
    game, lane = _lane(game_id, lane_id, games_root)
    say(f"{game.game_id} · {lane.lane_id} · {step} · {lane.classification}")

    if step == "catalogue":
        built = lane.build_catalogue(Path(source), progress=say)
        _write_json(out, catalogue_json(built, game_id=game.game_id, page=lane_page(lane)))
        return 0, (
            f"LANE_CATALOGUE ok game={game.game_id} lane={lane.lane_id} "
            f"targets={len(built.targets)} page={lane_page(lane)}"
        )

    if step == "plan":
        pinned = catalogue_from_json(_read_json(Path(catalogue), "catalogue"))
        say(f"{len(pinned.targets)} catalogued targets pinned")
        planned = lane.plan(Path(source), _read_json(Path(recipe), "recipe"), pinned)
        _write_json(out, plan_json(planned))
        return 0, (
            f"LANE_PLAN ok game={game.game_id} lane={lane.lane_id} "
            f"targets={len(planned.target_keys)} declared_bytes={planned.declared_bytes}"
        )

    if step == "build":
        pinned = catalogue_from_json(_read_json(Path(catalogue), "catalogue"))
        say(f"{len(pinned.targets)} catalogued targets pinned")
        written = lane.build(
            Path(source), Path(destination), _read_json(Path(recipe), "recipe"), pinned,
            work_dir=Path(work_dir) if work_dir else None,
        )
        say(f"wrote {destination}")
        _write_json(receipt, receipt_json(written))
        return 0, (
            f"LANE_BUILD ok game={game.game_id} lane={lane.lane_id} "
            f"ranges={len(written.declared_ranges)} artifacts={len(written.artifacts)} "
            f"destination={written.destination}"
        )

    if step == "verify":
        recorded = receipt_from_json(_read_json(Path(receipt), "receipt"))
        verdict = lane.verify(Path(source), Path(destination), recorded)
        _write_json(out, verdict_json(verdict, lane_id=lane.lane_id))
        state = "pass" if verdict.passed else "FAIL"
        return (0 if verdict.passed else 1), (
            f"LANE_VERIFY {state} game={game.game_id} lane={lane.lane_id} — {verdict.summary}"
        )

    raise Refusal(f"{step!r} is not a lane step; choose " + ", ".join(STEPS) + ".")


def main(argv: Optional[Sequence[str]] = None, *, games_root: Optional[Path] = None) -> int:
    """The ``lane`` verb, wired by ``mod_editor.games.__main__``."""

    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m mod_editor.games lane", description=__doc__.splitlines()[0]
    )
    parser.add_argument("game")
    parser.add_argument("lane")
    steps = parser.add_subparsers(dest="step", required=True)

    catalogue = steps.add_parser("catalogue", help="build the lane's catalogue from a source")
    catalogue.add_argument("--source", type=Path, required=True)
    catalogue.add_argument("--out", type=Path, required=True)

    plan = steps.add_parser("plan", help="dry run: what a build would change")
    plan.add_argument("--source", type=Path, required=True)
    plan.add_argument("--recipe", type=Path, required=True)
    plan.add_argument("--catalogue", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)

    build = steps.add_parser("build", help="write a NEW destination and its receipt")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--destination", type=Path, required=True)
    build.add_argument("--recipe", type=Path, required=True)
    build.add_argument("--catalogue", type=Path, required=True)
    build.add_argument("--work-dir", type=Path)
    build.add_argument("--receipt", type=Path, required=True)

    verify = steps.add_parser("verify", help="the lane's independent verifier over a build")
    verify.add_argument("--source", type=Path, required=True)
    verify.add_argument("--destination", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        code, verdict = run(
            args.game, args.lane, args.step,
            source=getattr(args, "source", None),
            destination=getattr(args, "destination", None),
            recipe=getattr(args, "recipe", None),
            catalogue=getattr(args, "catalogue", None),
            receipt=getattr(args, "receipt", None),
            out=getattr(args, "out", None),
            work_dir=getattr(args, "work_dir", None),
            games_root=games_root,
            progress=lambda line: print(line, flush=True),
        )
    except ContractError as exc:  # Refusal is one; both are one sentence
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:  # a lane that raised past its own refusals
        print(f"error: {args.lane} could not {args.step}: {exc}", file=sys.stderr)
        return 1
    print(verdict, flush=True)
    return code


__all__ = [
    "CATALOGUE_SCHEMA",
    "PLAN_SCHEMA",
    "RECEIPT_SCHEMA",
    "STEPS",
    "VERDICT_SCHEMA",
    "catalogue_from_json",
    "catalogue_json",
    "field_from_json",
    "field_json",
    "main",
    "plan_json",
    "receipt_from_json",
    "receipt_json",
    "run",
    "target_from_json",
    "target_json",
    "verdict_json",
]
