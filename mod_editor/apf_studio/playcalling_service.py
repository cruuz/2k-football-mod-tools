"""Authored play-calling recipes, using the beta-67 core contract.

No selector or writer is emulated here. Core imports are lazy so the other
Studio workspaces remain usable while the independently developed P3 lands.
Recipes contain choices and receipts, never decoded game resources.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
import hashlib
import importlib
import json
from pathlib import Path
import struct

from mod_editor.core.errors import ValidationError
from .models import Modification

PROVIDER_KIND = "apf_playcalling"
SCHEMA = "apf_playcalling/v1"
SELECTOR = "apf:playbooks:cpu-playcalling"
# P3's pinned aligned-word scan found exactly two direct callsites of the lineup
# resolver, both inside a routine that supplies both team managers, and no direct
# caller of that routine: "This cannot support a human-only classification or a CPU
# exclusion claim. Keep the 66.1 refusal." See docs/research/apf_b67_static_audit.json.
# Change this only on new caller evidence, never as a user-facing toggle.
LINEUP_CALLERS = "unclassified"
# P3's corrected semantics, from docs/mod_editor/apf_b67_play_calling.md.
RATING_EXPLANATION = (
    "The raw formation numbers are not a conventional higher is better scale: a lower "
    "number makes the game weigh this formation more. The three fields are the short, "
    "medium and long yardage settings, and the situation interpolates between them."
)
RATING_MAPPING = (
    "For equal ratings the game weighs 0/0/0 as category 3 and formation 0.5; 1/1/1 as 2 "
    "and 2; 2/2/2 as 1 and 1; 3/3/3 as 0.5 and 0.5; and 4/4/4 through 7/7/7 as 0.1 and "
    "0.1, before distance and cubing. Urgency changes that calculation. A zero rating "
    "does not disable a formation; remove it to exclude it from this book. A category "
    "averages its formations' weights before the category lottery, so edit every record "
    "of that personnel when changing its category weight."
)
# Authored experiment values, not a native witness. P3's core accepts exactly five
# offensive weights and three defensive ones, starting at one and never increasing.
# Retail is (1, 1, 0.85, 0.5, 0.05) on offense and (1, 0.01, 0) on defense, so each
# preset weighs personnel farther from the request less than the game does.
CURVE_PRESETS = {
    "offense": (1.0, 0.35, 0.10, 0.02, 0.0),
    "defense": (1.0, 0.002, 0.0),
}
RETAIL_CURVES = {"offense": (1.0, 1.0, 0.85, 0.5, 0.05), "defense": (1.0, 0.01, 0.0)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def assignment_row(assignment):
    return {key: getattr(assignment, key) for key in
            ("team_index", "team_name", "label_id", "donor_name", "clone_name")}


def validate_metadata(asset_id, value):
    if asset_id != SELECTOR or value != {"schema": SCHEMA}:
        raise ValidationError("CPU Play Calling identity or metadata changed")
    return value


def validate_payload(data, asset_id, metadata):
    validate_metadata(asset_id, metadata)
    if len(data) > 2 * 1024 * 1024:
        raise ValidationError("CPU Play Calling recipe is too large")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate recipe field")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
        if set(value) != {"schema", "events"} or value["schema"] != SCHEMA:
            raise ValueError("Unknown recipe schema")
        if not isinstance(value["events"], list) or not 1 <= len(value["events"]) <= 4096:
            raise ValueError("Choose one to 4096 edits")
        for event in value["events"]:
            if set(event) != {"request", "before", "after", "coverage", "retired", "warning"}:
                raise ValueError("Unknown edit receipt fields")
            validate_request(event["request"])
        json_bytes(value)  # Reject NaN/Infinity, including in receipt fields.
        return value["events"]
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ValidationError(f"Invalid CPU Play Calling recipe: {exc}") from exc


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"Choose a whole number from {low} to {high}")


def validate_request(request):
    if not isinstance(request, dict):
        raise ValidationError("Choose a CPU Play Calling edit")
    fields = {
        "ratings": {"book", "formation", "ratings"},
        "play_rating": {"book", "formation", "play", "value"},
        "categories": {"book", "formation", "primary", "secondary"},
        "remove": {"book", "formation"}, "retire": {"book", "category"},
        "tendency": {"team", "value"}, "master_row": {"category", "row"},
        "master_roles": {"category", "roles"}, "audibles": {"book"},
        "clones": {"side", "assignments"},
    }
    kind = request.get("kind")
    if kind not in fields or set(request) != fields[kind] | {"kind"}:
        raise ValidationError("Unknown CPU Play Calling control or fields")
    if "book" in request and (not isinstance(request["book"], str) or not 1 <= len(request["book"]) <= 27):
        raise ValidationError("Choose a named book")
    # "row" stops at 27 because apf2k8_master_writer.set_category_row refuses more.
    for key, high in (("formation", 255), ("play", 1022), ("category", 27), ("primary", 27), ("team", 39), ("row", 27)):
        if key in request:
            _integer(request[key], 0, high)
    if kind in {"ratings", "master_roles", "categories"}:
        key, maximum, count = {"ratings": ("ratings", 7, 3), "master_roles": ("roles", 31, 11),
                               "categories": ("secondary", 27, None)}[kind]
        values = request[key]
        if not isinstance(values, (list, tuple)) or (count is not None and len(values) != count) or len(values) > 28:
            raise ValidationError(f"Choose all {key} values")
        for value in values:
            _integer(value, 0, maximum)
    if kind in {"play_rating", "tendency"}:
        _integer(request["value"], 0, 7 if kind == "play_rating" else 100)
    if kind == "clones":
        if request["side"] not in {"offense", "defense"}:
            raise ValidationError("Choose offense or defense")
        rows = request["assignments"]
        if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 24:
            raise ValidationError("Choose one to 24 teams")
        for row in rows:
            if set(row) != {"team_index", "team_name", "label_id", "donor_name", "clone_name"}:
                raise ValidationError("Own-book plan fields changed")
            _integer(row["team_index"], 0, 39)
            _integer(row["label_id"], 0, 68)
            for key in ("team_name", "donor_name", "clone_name"):
                if not isinstance(row[key], str) or not 1 <= len(row[key]) <= 100:
                    raise ValidationError("Own-book plan names changed")
        if len({r["team_index"] for r in rows}) != len(rows) or len({r["clone_name"] for r in rows}) != len(rows):
            raise ValidationError("Own-book plan repeats a team or clone")
    return request


def read_profile(modification):
    payload = modification.replacement_path.read_bytes()
    if digest(payload) != modification.replacement_sha256:
        raise ValidationError("CPU Play Calling recipe changed after staging")
    return validate_payload(payload, modification.asset_id, dict(modification.metadata))


@dataclass
class State:
    books: dict
    master: bytes
    rost: bytes
    teams: tuple
    sides: dict
    inventory: dict

    def copy(self):
        return replace(self, books=dict(self.books), sides=dict(self.sides))


class Backend:
    """The facade's injection seam; production always uses the real core modules."""
    def __init__(self):
        for attr, suffix in (("model", "playcall_model"), ("splb", "splb_writer"),
                             ("master", "master_writer"), ("tendency", "team_tendency"),
                             ("clone", "book_clone"), ("audibles", "audibles")):
            setattr(self, attr, importlib.import_module("mod_editor.core.apf2k8_" + suffix))
        self.lineup_callers = LINEUP_CALLERS

    @property
    def curves(self):
        return importlib.import_module("mod_editor.core.apf2k8_playcall_curves_patch")

    def load(self, session):
        from .book_content import book_catalog, master_inventory
        from mod_editor.core import apf2k8_book_identity as identity
        index = session.source.index_0a
        books = book_catalog(index)
        inventory, master = master_inventory(index)
        rost = identity.read_disc_roster(index)
        parsed = identity.parse_roster_identity(rost)
        labels = {r.index: r for r in parsed.labels}
        teams = tuple({"team_index": t.index, "team_name": t.name,
                       "offense": labels[t.offense].kind, "defense": labels[t.defense].kind}
                      for t in parsed.teams[:24])
        bodies = {}
        changes = session.staged_splb_changes()
        for outer, book in books.items():
            selected = tuple(c for c in changes if c.outer_index == outer)
            bodies[book.name] = self.splb.compile_book(book, selected).replacement if selected else book.body
        from . import scheme_service
        for modification in session.modifications:
            if modification.kind == scheme_service.PROVIDER_KIND:
                from mod_editor.core import apf2k8_scheme_presets as presets
                for recipe in scheme_service.read_profile(modification):
                    name = recipe["book_type"]
                    bodies[name] = presets.apply_preset(self.splb.parse_book(bodies[name], 0), recipe, inventory)[0]
        sides = dict(self.splb.BOOK_SIDES)
        sides.update({label.kind: label.side for label in parsed.labels})
        return State(bodies, master, rost, teams, sides, inventory)


class PlayCallingService:
    def __init__(self, backend=None):
        self._backend = backend
        self.cache = OrderedDict()

    @property
    def backend(self):
        if self._backend is None:
            try:
                self._backend = Backend()
            except ImportError as exc:
                raise ValidationError("CPU Play Calling needs the beta-67 model and writers; integrate job P3 first.") from exc
        return self._backend

    @staticmethod
    def snapshot(session):
        return tuple((m.asset_id, m.replacement_sha256) for m in session.modifications)

    def events(self, session):
        return next((read_profile(m) for m in session.modifications if m.kind == PROVIDER_KIND), [])

    def state(self, session):
        state = self.backend.load(session)
        for event in self.events(session):
            state, fresh = self.apply(state, event["request"], session.source.index_0a)
            if fresh != event:
                raise ValidationError("An earlier book edit changed; undo or revert CPU Play Calling and review again")
        return state

    def plan(self, session, side, team=None, donor=None):
        state = self.state(session)
        rows = [assignment_row(r) for r in self.backend.clone.own_book_plan(session.source.index_0a, state.rost, side)]
        if team is not None:
            rows = [r for r in rows if r["team_index"] == team]
        if donor is not None:
            if state.sides.get(donor) != side or donor not in state.books:
                raise ValidationError("Choose a donor on the team's selected side")
            rows = [dict(r, donor_name=donor) for r in rows]
        if not rows:
            raise ValidationError("These teams already own their books, or no free label is available")
        return {"kind": "clones", "side": side, "assignments": rows}

    def _record(self, book, formation):
        return next((r for r in self.backend.splb.parse_book(book, 0).records
                     if r.populated and r.formation_index == formation), None)

    def facts(self, state, request):
        b = self.backend
        kind = request["kind"]
        if kind == "clones":
            return [{"team_index": r["team_index"], "book": next(t[request["side"]] for t in state.teams
                     if t["team_index"] == r["team_index"])} for r in request["assignments"]]
        if kind == "tendency":
            return b.tendency.team_tendency(state.rost, request["team"])
        if kind.startswith("master_"):
            row = next(r for r in b.model.category_table(state.master) if r.id == request["category"])
            return row.row if kind == "master_row" else list(state.master[0x49 + row.id * 16:0x54 + row.id * 16][i] & 31 for i in range(11))
        if request["book"] not in state.books:
            raise ValidationError("This named book is missing; select a team and review its book again")
        book = state.books[request["book"]]
        if kind == "ratings":
            return list(b.splb.formation_ratings(book, request["formation"]))
        if kind == "play_rating":
            return b.splb.play_rating(book, request["formation"], request["play"])
        if kind == "categories":
            record = self._record(book, request["formation"])
            if record is None:
                raise ValidationError("This formation has been removed")
            mask = struct.unpack_from(">I", record.trailer, 4)[0]
            return {"primary": record.category_index, "secondary": [i for i in range(28) if mask & (1 << i)]}
        # Removal, retirement and audible balancing own whole record membership.
        return digest(book)

    def apply(self, state, request, index):
        validate_request(request)
        state = state.copy()
        b, kind = self.backend, request["kind"]
        before = self.facts(state, request)
        coverage, retired, warning = {}, [], ""
        if kind == "clones":
            side = request["side"]
            available = {r.team_index: assignment_row(r) for r in b.clone.own_book_plan(index, state.rost, side)}
            for row in request["assignments"]:
                expected = available.get(row["team_index"])
                if expected is None or any(row[k] != expected[k] for k in ("team_index", "team_name", "label_id", "clone_name")):
                    raise ValidationError("The own-book plan changed; review the new table")
                if state.sides.get(row["donor_name"]) != side:
                    raise ValidationError("Choose a donor on the same side")
                if row["clone_name"] in state.books:
                    raise ValidationError("This clone name already exists")
                state.books[row["clone_name"]] = b.clone.clone_body(state.books[row["donor_name"]], row["clone_name"])
                state.sides[row["clone_name"]] = side
            # The fourth field is P3's clone name; without it the writer falls back to
            # the label's own name and the reviewed table stops matching the archive.
            requests = tuple(b.clone.CloneRequest(r["label_id"], r["team_index"], r["donor_name"], r["clone_name"])
                             for r in request["assignments"])
            state.rost = b.clone.bind_roster(state.rost, requests)[0]
            assignments = {r["team_index"]: r["clone_name"] for r in request["assignments"]}
            state.teams = tuple(dict(t, **{side: assignments.get(t["team_index"], t[side])}) for t in state.teams)
        elif kind == "tendency":
            state.rost = b.tendency.set_team_tendency(state.rost, request["team"], request["value"])
        elif kind.startswith("master_"):
            if kind == "master_row":
                state.master = b.master.set_category_row(state.master, request["category"], request["row"])
            else:
                state.master = b.master.set_category_roles(state.master, request["category"], tuple(request["roles"]))
            b.master.verify_master(state.master)
        else:
            name = request["book"]
            book = state.books[name]
            if kind == "ratings":
                book = b.splb.set_formation_ratings(book, request["formation"], tuple(request["ratings"]))
            elif kind == "play_rating":
                book = b.splb.set_play_rating(book, request["formation"], request["play"], request["value"])
            elif kind == "categories":
                book = b.splb.set_formation_categories(book, request["formation"], request["primary"], tuple(request["secondary"]))
            elif kind == "remove":
                result = b.splb.remove_formation(book, request["formation"])
                book, retired = result.book, list(result.retired_categories)
            elif kind == "retire":
                book = b.splb.retire_category(book, request["category"])
                retired = [request["category"]]
            elif kind == "audibles":
                if state.sides[name] != "offense":
                    raise ValidationError("Automatic run/pass audibles need an offensive book")
                parsed = replace(b.splb.parse_book(book, 0), name="USER-o")
                book = b.audibles.plan_audibles(parsed, b.audibles.play_catalog(state.master)).replacement
            state.books[name] = book
            if kind in {"remove", "retire", "categories"}:
                coverage = {str(k): list(v) for k, v in b.splb.row_coverage(book, state.master).items()}
                holes = [k for k, v in coverage.items() if not v]
                if holes:
                    warning = "The lineup resolver has no formation for rows " + ", ".join(holes) + ". "
                    warning += ("P3 classifies its callers as non-CPU; review the lineup risk before staging."
                                if b.lineup_callers == "non_cpu" else
                                "Cannot safely retire: CPU reachability is present or still unclassified; keep a nearby personnel category.")
        return state, {"request": json.loads(json_bytes(request)), "before": before,
                       "after": self.facts(state, request), "coverage": coverage,
                       "retired": retired, "warning": warning}

    def review(self, session, request):
        state = self.state(session)
        try:
            after, event = self.apply(state, request, session.source.index_0a)
        except (ValidationError, ValueError) as exc:
            if request.get("kind") not in {"remove", "retire", "categories"} or request.get("book") not in state.books:
                raise
            # A writer can refuse before returning replacement bytes. The current
            # coverage remains useful, but must never be labeled post-edit supply.
            coverage = self.backend.splb.row_coverage(state.books[request["book"]], state.master)
            names = {r.id: r.name for r in self.backend.model.category_table(state.master)}
            return {"event": {"request": request, "before": self.facts(state, request), "after": None,
                              "coverage": {str(k): list(v) for k, v in coverage.items()}, "retired": [],
                              "warning": str(exc) + " Coverage below is the current book, before the refused edit."},
                    "snapshot": self.snapshot(session), "refused": True, "session_id": session.session_id,
                    "retired_names": [], "category_names": names}
        refused = bool(event["warning"] and self.backend.lineup_callers != "non_cpu")
        names = {r.id: r.name for r in self.backend.model.category_table(after.master)}
        return {"event": event, "snapshot": self.snapshot(session), "refused": refused,
                "session_id": session.session_id,
                "retired_names": [names[i] for i in event["retired"]], "category_names": names}

    def stage(self, session, review):
        if review["session_id"] != session.session_id or review["snapshot"] != self.snapshot(session):
            raise ValidationError("Project changed; review this edit again")
        fresh = self.review(session, review["event"]["request"])
        if fresh != review:
            raise ValidationError("Book or plan changed; review this edit again")
        if fresh["refused"]:
            raise ValidationError(fresh["event"]["warning"])
        events = self.events(session) + [fresh["event"]]
        payload = json_bytes({"schema": SCHEMA, "events": events})
        validate_payload(payload, SELECTOR, {"schema": SCHEMA})
        sha = digest(payload)
        path = session._store_payload(sha, payload, ".json")
        modification = Modification(SELECTOR, PROVIDER_KIND, path, sha, {"schema": SCHEMA})
        session._record_undo()
        session._modifications = {**session._modifications, SELECTOR: modification}
        return fresh["event"]

    def context(self, session, team, side):
        state = self.state(session)
        selected = next((t for t in state.teams if t["team_index"] == team), state.teams[0])
        name = selected[side]
        book = state.books[name]
        parsed = self.backend.splb.parse_book(book, 0)
        categories = self.backend.model.category_table(state.master)
        formations = []
        form_names = {int(r["index"]): r["name"] for r in state.inventory.get("formations", ())}
        play_names = {int(r["index"]): r["name"] for r in state.inventory.get("plays", ())}
        for r in parsed.records:
            if not r.populated or any(f["id"] == r.formation_index for f in formations):
                continue
            formations.append({"id": r.formation_index, "name": form_names.get(r.formation_index, f"Formation {r.formation_index}"),
                               "ratings": self.backend.splb.formation_ratings(book, r.formation_index),
                               **self.facts(state, {"kind": "categories", "book": name, "formation": r.formation_index}),
                               "plays": [(e.play_index, play_names.get(e.play_index, f"Play {e.play_index}"),
                                          self.backend.splb.play_rating(book, r.formation_index, e.play_index)) for e in r.entries]})
        return {"state": state, "snapshot": self.snapshot(session), "team": selected, "book": name,
                "sharing": [t["team_name"] for t in state.teams if t["team_index"] != selected["team_index"] and t[side] == name],
                "donors": sorted(n for n in state.books if state.sides.get(n) == side), "formations": formations,
                "categories": categories, "tendency": self.backend.tendency.team_tendency(state.rost, selected["team_index"]),
                "events": self.events(session)}

    def predict(self, context, side, rows):
        state, model = context["state"], self.backend.model
        book = state.books[context["book"]]
        key = (digest(book), digest(state.master), context["tendency"], side, json_bytes(rows))
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        distributions = []
        for label, values in rows:
            if side == "offense":
                call = model.predict_offense(book, state.master, context["tendency"] / 100,
                                             model.Situation(**values), seeds=256)
            else:
                call = model.predict_defense(book, state.master, values["offense_category_row"], values["yards_to_goal"], seeds=256)
            distributions.append((label, call))
        self.cache[key] = distributions
        while len(self.cache) > 32:
            self.cache.popitem(last=False)
        return distributions


def main(argv=None):
    """Build a saved authored project through the same facade used by the tab."""
    import argparse
    from .facade import ApfStudioFacade
    parser = argparse.ArgumentParser(description="Build authored CPU Play Calling; gameplay UNWITNESSED")
    parser.add_argument("--game-folder", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    facade = ApfStudioFacade()
    try:
        facade.load_source(args.game_folder)
        facade.load_project(args.project)
        receipt = facade.build(args.output)
        print("Built", receipt.output_game)
        if receipt.teams_now_own_books:
            print("Teams now owning a book:", ", ".join(receipt.teams_now_own_books))
        return 0
    finally:
        facade.close()


if __name__ == "__main__":
    raise SystemExit(main())
