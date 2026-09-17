"""Authored play-calling recipes, using the beta-67 core contract.

No selector or writer is emulated here. Core imports are lazy so the other
Studio workspaces remain usable while the independently developed P3 lands.
Recipes contain choices and receipts, never decoded game resources.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, replace, field
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
    "Lower raw ratings generally favor the personnel category. The later formation draw "
    "has an exception: equal ratings of 0 weigh less than 1. The three fields are short, "
    "medium and long yardage settings; the situation interpolates between them. Preview "
    "the resulting calls instead of treating the sliders as guaranteed frequencies."
)
RATING_MAPPING = (
    "For equal ratings the game weighs 0/0/0 as category 3 and formation 0.5; 1/1/1 as 2 "
    "and 2; 2/2/2 as 1 and 1; 3/3/3 as 0.5 and 0.5; and 4/4/4 through 7/7/7 as 0.1 and "
    "0.1, before distance and cubing. Urgency changes that calculation. A zero rating "
    "does not disable a formation; remove it to exclude it from this book. A category "
    "averages its formations' weights before the category lottery, so edit every record "
    "of that personnel when changing its category weight."
)
BOOK_CAPACITY_EXPLANATION = (
    "Give every team its own book covers the 24 disc teams: 24 offense and 24 defense "
    "copies, 48 independent books across both sides. This is the action's scope, not "
    "an archive limit. The retail pool has 36 offensive and 33 defensive labels; "
    "labels initially share content. Manual book allocation opens all 40 roster slots "
    "and unused labels after you build your project. "
    "The 16 saved-team slots keep their shared USER-o / USER-d assignments; edit saved "
    "assignments through Save Assignments. This disc-team scope has not changed in this "
    "release."
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
        "situation_mask": {"book", "key", "formation", "exclude"},
        "situation_masks_enabled": {"enabled"},
        "ratings": {"book", "formation", "ratings"},
        "play_rating": {"book", "formation", "play", "value"},
        "categories": {"book", "formation", "primary", "secondary"},
        "remove": {"book", "formation"}, "retire": {"book", "category"},
        "tendency": {"team", "value"}, "master_row": {"category", "row"},
        "master_roles": {"category", "roles"}, "audibles": {"book"},
        "clones": {"side", "assignments"},
        "scheme": {"team", "book", "scheme", "assignments"},
        "never_call": {"book", "formation", "never", "restore_masks"},
        "add": {"book", "donor", "formation"},
    }
    kind = request.get("kind")
    if kind not in fields or set(request) != fields[kind] | {"kind"}:
        raise ValidationError("Unknown CPU Play Calling control or fields")
    if "book" in request and (not isinstance(request["book"], str) or not 1 <= len(request["book"]) <= 27):
        raise ValidationError("Choose a named book")
    if kind == "situation_masks_enabled" and type(request["enabled"]) is not bool:
        raise ValidationError("Choose whether situation exclusions are enabled")
    if kind == "situation_mask":
        _integer(request["key"], 0, 11)
        _integer(request["formation"], 0, 150)
        if type(request["exclude"]) is not bool:
            raise ValidationError("Choose whether to exclude this formation here")
    if kind == "add" and (not isinstance(request["donor"], str) or not 1 <= len(request["donor"]) <= 27):
        raise ValidationError("Choose a named donor book")
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
    if kind == "never_call":
        if type(request["never"]) is not bool or not isinstance(request["restore_masks"], list) or not 1 <= len(request["restore_masks"]) <= 176:
            raise ValidationError("Review this formation's original memberships before changing Never call")
        for mask in request["restore_masks"]:
            _integer(mask, 1, (1 << 28)-1)
    if kind == "scheme":
        _integer(request["team"], 0, 23)
        from mod_editor.core.apf2k8_offensive_schemes import get_scheme
        get_scheme(request["scheme"])
        rows = request["assignments"]
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValidationError("A scheme applies to one team's offensive book")
        if rows:
            validate_request({"kind": "clones", "side": "offense", "assignments": rows})
            if rows[0]["team_index"] != request["team"] or rows[0]["donor_name"] != request["book"]:
                raise ValidationError("The scheme's own-book plan belongs to another team or book")
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
    situation_masks: dict = field(default_factory=dict)
    situation_masks_enabled: bool = False

    def copy(self):
        return replace(self, books=dict(self.books), sides=dict(self.sides),
                       situation_masks={name: [list(row) for row in rows] for name, rows in self.situation_masks.items()})


class Backend:
    """The facade's injection seam; production always uses the real core modules."""
    def __init__(self):
        from .book_content import BookSourceCache
        self.source_cache = BookSourceCache()
        for attr, suffix in (("model", "playcall_model"), ("splb", "splb_writer"),
                             ("master", "master_writer"), ("tendency", "team_tendency"),
                             ("clone", "book_clone"), ("audibles", "audibles")):
            setattr(self, attr, importlib.import_module("mod_editor.core.apf2k8_" + suffix))
        self.lineup_callers = LINEUP_CALLERS
        self._compiled = OrderedDict()

    def cache_token(self, session):
        return self.source_cache.token(session.source.index_0a)

    @property
    def curves(self):
        return importlib.import_module("mod_editor.core.apf2k8_playcall_curves_patch")

    def load(self, session):
        from .book_content import book_catalog, master_inventory
        from mod_editor.core import apf2k8_book_identity as identity
        index = session.source.index_0a
        books = book_catalog(index, cache=self.source_cache)
        inventory, master = master_inventory(index, cache=self.source_cache)
        rost = self.source_cache.roster(index)
        parsed = identity.parse_roster_identity(rost)
        labels = {r.index: r for r in parsed.labels}
        teams = tuple({"team_index": t.index, "team_name": t.name,
                       "offense": labels[t.offense].kind, "defense": labels[t.defense].kind}
                      for t in parsed.teams[:24])
        bodies = {}
        changes = session.staged_splb_changes()
        for outer, book in books.items():
            selected = tuple(c for c in changes if c.outer_index == outer)
            key = (book.name, digest(book.body), selected)
            if selected and key not in self._compiled:
                PlayCallingService._remember(self._compiled, key, self.splb.compile_book(book, selected).replacement)
            bodies[book.name] = self._compiled[key] if selected else book.body
        from . import scheme_service
        source_books = {book.name: book for book in books.values()}
        for modification in session.modifications:
            if modification.kind == scheme_service.PROVIDER_KIND:
                from mod_editor.core import apf2k8_scheme_presets as presets
                for recipe in scheme_service.read_profile(modification):
                    name = recipe["book_type"]
                    if recipe.get("schema") == scheme_service.REPLACEMENT_SCHEMA:
                        donor_name = scheme_service.SCHEME_CONTENT[recipe["scheme_id"]][0]
                        # Every replacement reads its donor from the source,
                        # matching build compilation even when that donor is
                        # also a target elsewhere in this staged profile.
                        bodies[name] = scheme_service.replace_starting_content(
                            source_books[name], source_books[donor_name], master, recipe)[0]
                    else:
                        bodies[name] = presets.apply_preset(self.splb.parse_book(bodies[name], 0), recipe, inventory)[0]
        sides = dict(self.splb.BOOK_SIDES)
        sides.update({label.kind: label.side for label in parsed.labels})
        return State(bodies, master, rost, teams, sides, inventory)


class PlayCallingService:
    def __init__(self, backend=None):
        self._backend = backend
        self.cache = OrderedDict()
        self._profiles = OrderedDict()
        self._states = OrderedDict()
        self._base_key = None
        self._base = None
        self._parsed = OrderedDict()
        self._transitions = OrderedDict()

    @staticmethod
    def _remember(cache, key, value, limit=64):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)
        return value

    @staticmethod
    def _file_key(path):
        from .book_content import BookSourceCache
        return BookSourceCache.stat_key(path)

    def _mod_key(self, modification):
        # The staged recipe is small, so key on its live digest as well as its stat: a tamper that keeps the size
        # and mtime is invisible to stat on Windows (ctime is the creation time there and the inode survives an
        # in-place write), and it must still miss the memo so read_profile can refuse it.
        try:
            live = digest(modification.replacement_path.read_bytes())
        except OSError:
            live = None
        return (modification.asset_id, modification.kind, modification.replacement_sha256, live,
                json_bytes(dict(modification.metadata)), self._file_key(modification.replacement_path))

    def _input_key(self, session):
        token = self.backend.cache_token(session) if hasattr(self.backend, 'cache_token') else None
        return (session.session_id, token, tuple(self._mod_key(m) for m in session.modifications
                                                if m.kind != PROVIDER_KIND))

    def _parse(self, body):
        key = digest(body)
        if key not in self._parsed:
            self._remember(self._parsed, key, self.backend.splb.parse_book(body, 0))
        return self._parsed[key]

    def _transition_key(self, state, request):
        """Only inputs consumed by this existing writer/coverage check.

        Ownership/scheme plans consult the archive too, so they always replay.
        Confirm still calls review and apply even when a replay result exists.
        """
        kind = request['kind']
        if kind in {'clones', 'scheme'}:
            return None
        inputs = []
        for field in ('book', 'donor'):
            if field in request:
                name = request[field]
                inputs.append((name, digest(state.books[name]), state.sides.get(name)))
        if kind in {'categories', 'remove', 'retire', 'audibles', 'master_row', 'master_roles'}:
            inputs.append(digest(state.master))
        if kind == 'tendency':
            inputs.append(digest(state.rost))
        if kind == 'situation_mask':
            inputs.append(state.situation_masks)
        if kind == 'situation_masks_enabled':
            inputs.append(state.situation_masks_enabled)
        return json_bytes([request, inputs, self.backend.lineup_callers])

    def _replay(self, state, request, index):
        key = self._transition_key(state, request)
        cached = self._transitions.get(key) if key is not None else None
        if cached is None:
            return self.apply(state, request, index)
        books, fields, event = cached
        result = state.copy()
        result.books.update(books)
        for field, value in fields.items():
            setattr(result, field, deepcopy(value))
        return result, deepcopy(event)

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
        modification = next((m for m in session.modifications if m.kind == PROVIDER_KIND), None)
        if modification is None:
            return []
        key = self._mod_key(modification)
        if key not in self._profiles:
            self._remember(self._profiles, key, read_profile(modification), 8)
        return deepcopy(self._profiles[key])

    @staticmethod
    def _event_key(events):
        return tuple(digest(json_bytes(e)) for e in events)

    def state(self, session):
        key = self._input_key(session)
        # Injected test backends can change their in-memory source without a
        # filesystem identity. Production watches only the source dependencies.
        if not hasattr(self.backend, 'cache_token'):
            base = self.backend.load(session)
            key = (*key, digest(json_bytes([sorted((n, digest(b)) for n, b in base.books.items()),
                                          digest(base.master), digest(base.rost), base.teams, base.sides])))
        else:
            base = None
        if self._base_key != key:
            self._base = base or self.backend.load(session)
            # The first load discovers which pack files contain the resources.
            self._base_key = self._input_key(session) if base is None else key
            self._states.clear()
            self._states[()] = self._base
        events = self.events(session)
        keys = self._event_key(events)
        count = len(keys)
        while count and keys[:count] not in self._states:
            count -= 1
        state = self._states.get(keys[:count], self._base)
        for position, event in enumerate(events[count:], count + 1):
            state, fresh = self._replay(state, event["request"], session.source.index_0a)
            if fresh != event:
                raise ValidationError("An earlier book edit changed; undo or revert CPU Play Calling and review again")
            self._remember(self._states, keys[:position], state)
        return state.copy()

    def rebase_membership(self, session, modifications):
        """Replay authored requests after an explicit Fine-tune transaction.

        First validate the old receipts against the old inputs. Recompute them
        only for the proposed membership changes, before the session mutates.
        A failed replay leaves both the book edits and CPU recipe untouched.
        """
        from types import SimpleNamespace
        events = self.events(session)
        if not events:
            return modifications
        self.state(session)
        proposed = SimpleNamespace(source=session.source, modifications=tuple(modifications.values()),
                                   staged_splb_changes=lambda: session._active_splb_changes(modifications))
        state = self.backend.load(proposed)
        refreshed = []
        for event in events:
            state, fresh = self._replay(state, event["request"], session.source.index_0a)
            if fresh["warning"] and self.backend.lineup_callers != "non_cpu":
                raise ValidationError(fresh["warning"])
            refreshed.append(fresh)
        payload = json_bytes({"schema": SCHEMA, "events": refreshed})
        validate_payload(payload, SELECTOR, {"schema": SCHEMA})
        sha = digest(payload)
        path = session._store_payload(sha, payload, ".json")
        return {**modifications, SELECTOR: Modification(SELECTOR, PROVIDER_KIND, path, sha, {"schema": SCHEMA})}

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
        return next((r for r in self._parse(book).records
                     if r.populated and r.formation_index == formation), None)

    def scheme_plan(self, session, team, scheme_id):
        context = self.context(session, team, "offense")
        assignments = (self.plan(session, "offense", team, context["book"])["assignments"]
                       if context["sharing"] else [])
        return validate_request({"kind": "scheme", "team": team, "book": context["book"],
                                 "scheme": scheme_id, "assignments": assignments})

    def scheme_csv(self, session, team, *, book=None, preview_tendency=None):
        from mod_editor.core.apf2k8_offensive_schemes import spreadsheet
        context = self.context(session, team, "offense", book=book, preview_tendency=preview_tendency)
        selected = next((e["request"]["scheme"] for e in reversed(context["events"])
                         if e["request"]["kind"] == "scheme" and e["request"]["team"] == team), None)
        state = context["state"]
        return spreadsheet(state.books[context["book"]], state.master, context["preview_tendency"],
                           team_name="Book preview, independent of team" if book is not None else context["team"]["team_name"],
                           scheme_id=selected if book is None or context["team"]["offense"] == book else None,
                           preview_only=book is not None)

    def facts(self, state, request):
        b = self.backend
        kind = request["kind"]
        if kind == "situation_masks_enabled":
            return state.situation_masks_enabled
        if kind == "situation_mask":
            return request["formation"] in state.situation_masks.get(request["book"], [[] for _ in range(12)])[request["key"]]
        if kind == "scheme":
            team = next(t for t in state.teams if t["team_index"] == request["team"])
            return {"book": team["offense"], "book_sha256": digest(state.books[team["offense"]]),
                    "rost_sha256": digest(state.rost)}
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
        if kind == "never_call":
            from mod_editor.core.apf2k8_formation_calling import membership_masks
            return list(membership_masks(book, request["formation"]))
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
        original = state
        state = state.copy()
        b, kind = self.backend, request["kind"]
        before = self.facts(state, request)
        coverage, retired, warning = {}, [], ""
        scheme_receipt = None
        if kind == "situation_masks_enabled":
            state.situation_masks_enabled = request["enabled"]
        elif kind == "situation_mask":
            from mod_editor.core.apf2k8_situation_mask import canonical_policies
            name = request["book"]
            if name not in state.books or state.sides.get(name) != "offense":
                raise ValidationError("Choose an offensive book for situation exclusions")
            if self._record(state.books[name], request["formation"]) is None:
                raise ValidationError("This formation is no longer in the book; refresh its candidates")
            rows = state.situation_masks.setdefault(name, [[] for _ in range(12)])
            values = set(rows[request["key"]])
            if request["exclude"]: values.add(request["formation"])
            else: values.discard(request["formation"])
            rows[request["key"]] = sorted(values)
            state.situation_masks = canonical_policies(state.situation_masks)
        elif kind == "scheme":
            from mod_editor.core.apf2k8_offensive_schemes import apply_scheme
            team = next(t for t in state.teams if t["team_index"] == request["team"])
            if team["offense"] != request["book"]:
                raise ValidationError("The team's book changed; review the scheme again")
            if request["assignments"]:
                state, _ = self.apply(state, {"kind": "clones", "side": "offense",
                                             "assignments": request["assignments"]}, index)
            team = next(t for t in state.teams if t["team_index"] == request["team"])
            name = team["offense"]
            if any(t["team_index"] != request["team"] and t["offense"] == name for t in state.teams):
                raise ValidationError("Give this team its own book before applying a scheme")
            state.books[name], state.rost, scheme_receipt = apply_scheme(
                state.books[name], state.master, state.rost, request["team"], request["scheme"])
        elif kind == "clones":
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
            elif kind == "never_call":
                from mod_editor.core.apf2k8_formation_calling import set_never_call
                book = set_never_call(book, request["formation"], request["never"], tuple(request["restore_masks"]))
            elif kind == "add":
                donor = request["donor"]
                if donor not in state.books or state.sides[donor] != state.sides[name]:
                    raise ValidationError("Choose a donor on the selected book's side")
                if request["formation"] >= 151:
                    raise ValidationError("Choose an ordinary formation; special calls use separate caches")
                if self._record(book, request["formation"]) is not None:
                    raise ValidationError("This formation is already in the book; edit it below")
                donor_record = self._record(state.books[donor], request["formation"])
                if donor_record is None:
                    raise ValidationError("The donor no longer contains this formation; select it again")
                parsed = b.splb.parse_book(book, 0)
                slot = next((r.record_index for r in parsed.records if not r.populated), None)
                if slot is None:
                    raise ValidationError("This book has no empty formation slot; remove an ordinary formation first")
                changes = [b.splb.MembershipChange(0, slot, e.play_index, True) for e in donor_record.entries]
                changes.append(b.splb.TrailerReplace(0, slot, request["formation"], donor_record.category_index))
                compiled = b.splb.compile_book(parsed, changes)
                b.splb.verify_book(book, compiled.replacement, changes)
                book = b.splb._compact_normalize(compiled.replacement)
            state.books[name] = book
            if kind in {"remove", "retire", "categories"}:
                coverage = {str(k): list(v) for k, v in b.splb.row_coverage(book, state.master).items()}
                holes = [k for k, v in coverage.items() if not v]
                if holes:
                    warning = "The lineup resolver has no formation for rows " + ", ".join(holes) + ". "
                    warning += ("P3 classifies its callers as non-CPU; review the lineup risk before staging."
                                if b.lineup_callers == "non_cpu" else
                                "Cannot safely retire: CPU reachability is present or still unclassified; keep a nearby personnel category.")
        after = self.facts(state, request)
        if scheme_receipt is not None:
            after["scheme_receipt"] = scheme_receipt
        event = {"request": json.loads(json_bytes(request)), "before": before,
                 "after": after, "coverage": coverage, "retired": retired, "warning": warning}
        key = self._transition_key(original, request)
        if key is not None:
            books = {name: body for name, body in state.books.items() if original.books.get(name) != body}
            fields = {name: deepcopy(getattr(state, name)) for name in
                      ('master', 'rost', 'teams', 'sides', 'situation_masks', 'situation_masks_enabled')
                      if getattr(original, name) != getattr(state, name)}
            self._remember(self._transitions, key, (books, fields, deepcopy(event)), 128)
        return state, event

    def review(self, session, request, *, state=None):
        state = self.state(session) if state is None else state
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
        self._review_state = after
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
        self._commit(session, events, self._review_state)
        return fresh["event"]

    def _commit(self, session, events, state):
        """One validated payload and one Undo entry; nothing mutates on refusal."""
        payload = json_bytes({"schema": SCHEMA, "events": events})
        validate_payload(payload, SELECTOR, {"schema": SCHEMA})
        sha = digest(payload)
        path = session._store_payload(sha, payload, ".json")
        modification = Modification(SELECTOR, PROVIDER_KIND, path, sha, {"schema": SCHEMA})
        session._record_undo()
        session._modifications = {**session._modifications, SELECTOR: modification}
        self._remember(self._states, self._event_key(events), state)

    @staticmethod
    def describe_request(request):
        where = request.get('book', f"Team {request['team']}" if 'team' in request else 'MASTER / every book')
        for key in ('formation', 'play', 'category', 'key'):
            if key in request:
                where += f", {key} {request[key]}"
        return request.get('kind', 'edit').replace('_', ' '), where

    def confirm(self, session, requests):
        """Review the queue against one evolving state, then commit its clean set.

        Each request goes through review(), with exactly its captured arguments.
        A refused book keeps all its pending changes so order cannot silently
        decide which half of an incompatible pair gets staged. Independent books
        and tendencies can still commit in one transaction. MASTER and ownership
        changes are global dependencies: a blocker keeps that entire batch.
        """
        requests = deepcopy(list(requests))
        if not requests:
            return {'staged': [], 'blockers': [], 'reviews': []}
        initial = self.state(session)
        snapshot = self.snapshot(session)
        source_key = self._input_key(session)
        events = self.events(session)
        blockers = {}
        reviews = {}

        def block(i, why):
            what, where = self.describe_request(requests[i])
            blockers.setdefault(i, {'index': i, 'what': what, 'where': where, 'why': why,
                                   'fix': 'Clear this row, adjust its controls, and add it again.'})

        # Explicit formation references conflict regardless of queue order.
        for i, request in enumerate(requests):
            if request.get('kind') != 'remove':
                continue
            for j, other in enumerate(requests):
                references_book = (other.get('book') == request.get('book') or
                                   other.get('kind') == 'add' and other.get('donor') == request.get('book'))
                if i != j and references_book and other.get('formation') == request.get('formation'):
                    why = f"Pending edit {i + 1} removes a formation referenced by pending edit {j + 1}. Keep the formation or clear its other edit."
                    block(i, why); block(j, why)

        # Review every row, including pre-identified conflicts, to expose all
        # writer/coverage failures in one pass. Failed rows never supply state.
        state = initial
        for i, request in enumerate(requests):
            try:
                review = self.review(session, request, state=state)
                reviews[i] = review
                if review['refused']:
                    block(i, review['event']['warning'])
                elif i not in blockers:
                    state = self._review_state
            except (ValidationError, ValueError, KeyError, StopIteration) as exc:
                block(i, str(exc) or 'The referenced book or personnel is no longer available.')

        # Later MASTER edits must not invalidate coverage checked by an earlier
        # membership edit. The same writer coverage check runs on final state.
        for i, request in enumerate(requests):
            if i in blockers or request.get('kind') not in {'remove', 'retire', 'categories'}:
                continue
            coverage = self.backend.splb.row_coverage(state.books[request['book']], state.master)
            holes = [str(k) for k, v in coverage.items() if not v]
            if holes and self.backend.lineup_callers != 'non_cpu':
                block(i, 'Combined edits leave no lineup candidate for requested rows ' + ', '.join(holes) +
                      '. Keep a nearby personnel category or restore the MASTER row.')

        global_kinds = {'master_row', 'master_roles', 'clones', 'scheme'}
        blocked_books = {requests[i].get('book') for i in blockers} - {None}
        global_dependency = any(r.get('kind') in global_kinds for r in requests)
        if blockers:
            # A pending addition consumes its donor too. Propagate blockers
            # through donor chains before publishing any independent edits.
            while True:
                dependent = {r['book'] for r in requests if r.get('kind') == 'add'
                             and r.get('donor') in blocked_books}
                if dependent <= blocked_books:
                    break
                blocked_books.update(dependent)
            retired_books = {r.get('book') for r in requests if r.get('kind') == 'retire'} & blocked_books
            for i, request in enumerate(requests):
                paired_tendency = request.get('kind') == 'tendency' and any(
                    t['team_index'] == request['team'] and t['offense'] in retired_books for t in initial.teams)
                # The editor also allows a USER/donor book independent of the
                # team picker. Retire submits its captured share as the next
                # request even when that team does not own the selected book.
                if request.get('kind') == 'tendency' and i and requests[i - 1].get('kind') == 'retire':
                    paired_tendency |= requests[i - 1].get('book') in retired_books
                if global_dependency or request.get('book') in blocked_books or paired_tendency:
                    block(i, 'Another pending edit affects the same book or shared MASTER/ownership data. Resolve its blockers together.')

        # Replay the accepted set through review once more only if exclusions
        # changed its inputs. This makes every stored receipt match build replay.
        accepted = [i for i in range(len(requests)) if i not in blockers]
        if blockers:
            state = initial
            for i in accepted:
                review = self.review(session, requests[i], state=state)
                if review['refused']:
                    raise ValidationError('Pending dependencies changed; refresh and confirm again')
                reviews[i] = review
                state = self._review_state
        if snapshot != self.snapshot(session) or source_key != self._input_key(session):
            raise ValidationError('The project or source changed during confirmation; refresh and confirm again')
        if accepted:
            self._commit(session, events + [reviews[i]['event'] for i in accepted], state)
        return {'staged': accepted, 'blockers': [blockers[i] for i in sorted(blockers)],
                'reviews': [dict(index=i, **reviews[i]) for i in sorted(reviews)]}

    @staticmethod
    def _restore_masks(events, book, formation):
        # A clone copies its donor's membership bytes at that event. Follow the
        # same ancestry backwards so later donor edits cannot change its saved
        # restore state. This also handles the clone inside a scheme event and
        # existing saved recipes without changing their receipt format.
        for event in reversed(events):
            request = event["request"]
            if (request["kind"] == "never_call" and request["book"] == book
                    and request["formation"] == formation):
                return request["restore_masks"] if request["never"] else None
            if request["kind"] in {"clones", "scheme"}:
                donor = next((row["donor_name"] for row in request["assignments"]
                              if row["clone_name"] == book), None)
                if donor is not None:
                    book = donor
        return None

    def context(self, session, team, side, *, book=None, preview_tendency=None):
        state = self.state(session)
        selected = next((t for t in state.teams if t["team_index"] == team), state.teams[0])
        name = selected[side] if book is None else book
        if name not in state.books or state.sides.get(name) != side:
            raise ValidationError("Choose a book on the selected side, then refresh the preview")
        tendency = self.backend.tendency.team_tendency(state.rost, selected["team_index"])
        if preview_tendency is None:
            preview_tendency = tendency
        _integer(preview_tendency, 0, 100)
        book = state.books[name]
        parsed = self._parse(book)
        categories = self.backend.model.category_table(state.master)
        formations = []
        form_names = {int(r["index"]): r["name"] for r in state.inventory.get("formations", ())}
        play_names = {int(r["index"]): r["name"] for r in state.inventory.get("plays", ())}
        events = self.events(session)
        for r in parsed.records:
            if not r.populated or any(f["id"] == r.formation_index for f in formations):
                continue
            formations.append({"id": r.formation_index, "name": form_names.get(r.formation_index, f"Formation {r.formation_index}"),
                               "ratings": tuple((int.from_bytes(r.trailer[:4], 'big') >> shift) & 7 for shift in (14, 11, 8)),
                               "primary": r.category_index,
                               "secondary": [i for i in range(28) if int.from_bytes(r.trailer[4:], 'big') & (1 << i)],
                               "plays": [(e.play_index, play_names.get(e.play_index, f"Play {e.play_index}"),
                                          e.x) for e in r.entries]})
            masks = [int.from_bytes(other.trailer[4:], 'big') for other in parsed.records
                     if other.populated and other.formation_index == r.formation_index]
            saved = self._restore_masks(events, name, r.formation_index)
            formations[-1].update(never_call=not any(masks), restore_masks=masks if all(masks) else saved)
        return {"state": state, "snapshot": self.snapshot(session), "team": selected, "book": name,
                "sharing": [t["team_name"] for t in state.teams if t["team_index"] != selected["team_index"] and t[side] == name],
                "donors": sorted(n for n in state.books if state.sides.get(n) == side), "formations": formations,
                "categories": categories, "tendency": tendency, "preview_tendency": preview_tendency,
                "users": [t["team_name"] for t in state.teams if t[side] == name],
                "events": events}

    def predict(self, context, side, rows):
        state, model = context["state"], self.backend.model
        book = state.books[context["book"]]
        tendency = context.get("preview_tendency", context["tendency"])
        masks = state.situation_masks.get(context["book"], [[] for _ in range(12)]) if state.situation_masks_enabled else [[] for _ in range(12)]
        key = (digest(book), digest(state.master), tendency, side, json_bytes(rows), json_bytes(masks))
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        distributions = []
        for label, values in rows:
            if side == "offense":
                from mod_editor.core.apf2k8_situation_mask import situation_key
                situation = model.Situation(**values)
                excluded = masks[situation_key(situation)]
                kwargs = {"exclusions": excluded} if excluded else {}
                call = model.predict_offense(book, state.master, tendency / 100, situation, seeds=256, **kwargs)
            else:
                call = model.predict_defense(book, state.master, values["offense_category_row"], values["yards_to_goal"], seeds=256)
            distributions.append((label, call))
        self.cache[key] = distributions
        while len(self.cache) > 32:
            self.cache.popitem(last=False)
        return distributions

    def situations(self, context, side):
        from mod_editor.core.apf2k8_offensive_schemes import BUCKETS
        model, state = self.backend.model, context["state"]
        book = state.books[context["book"]]
        if side == "offense":
            return [{"name": bucket.name, "note": bucket.note,
                     "row": model.requested_offense_row(bucket.situation()),
                     "candidates": model.situation_candidates(book, state.master, bucket.situation())}
                    for bucket in BUCKETS]
        return [{"name": f"Opposing personnel row {row}",
                 "note": "Defense responds to the opposing personnel; membership edits apply throughout this book.",
                 "row": model.requested_defense_row(row, 50),
                 "candidates": model.situation_candidates(book, state.master, model.Situation(1, 10, 50, 1, 900, 0, 3),
                                                           requested_row=model.requested_defense_row(row, 50))}
                for row in range(11)]

    def preview_ratings(self, session, context, side, formation, ratings, pending=()):
        """Preview a draft through the existing writers without storing a recipe.

        Ratings are three shared yardage anchors, not 23 independent numbers.
        Return every situation so that their shared effects are visible.
        """
        state = self.state(session)
        for request in pending:
            state, _ = self.apply(state, request, session.source.index_0a)
        before = self.situations({**context, "state": state}, side)
        request = {"kind": "ratings", "book": context["book"],
                   "formation": formation, "ratings": list(ratings)}
        state, _ = self.apply(state, request, session.source.index_0a)
        after = self.situations({**context, "state": state}, side)
        return {"before": before, "after": after}


def main(argv=None):
    """Build a saved authored project through the same facade used by the tab."""
    import argparse
    from .facade import ApfStudioFacade
    parser = argparse.ArgumentParser(description="Build authored CPU Play Calling; gameplay UNWITNESSED")
    parser.add_argument("--game-folder", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spreadsheet-team", type=int, choices=range(24), metavar="0..23",
                        help="Export this team's current staged calls as CSV instead of building a game copy")
    args = parser.parse_args(argv)
    facade = ApfStudioFacade()
    try:
        facade.load_source(args.game_folder)
        facade.load_project(args.project)
        if args.spreadsheet_team is not None:
            from .launcher import _atomic_bytes
            _atomic_bytes(args.output, facade.playcalling_scheme_csv(args.spreadsheet_team))
            print("Exported play call spreadsheet", args.output)
            return 0
        receipt = facade.build(args.output)
        print("Built", receipt.output_game)
        if receipt.teams_now_own_books:
            print("Teams now owning a book:", ", ".join(receipt.teams_now_own_books))
        return 0
    finally:
        facade.close()


if __name__ == "__main__":
    raise SystemExit(main())
