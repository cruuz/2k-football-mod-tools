#!/usr/bin/env python3
"""SOFTDRINK offense v2 (beta 77, job p48o): shared core + team packages -> complete offenses.

DESIGN built on PROVED OFFLINE grammar.  Every play comes from
``mod_editor.core.nfl2k5_offense_concepts`` (the engine the Studio's Create a Play
wizard also offers); every formation is one of its ``FORMATIONS``.  Headers are the
team book's own retail words for the play's kind (quick game, dropback, play action,
screen, each run kind, trick) with the preference bits set per play.  Each formation
record is cloned from the team book's retail formation of the same personnel group,
backfield type and QB alignment whose retail situation ratings (short / medium / long)
are closest to the set's target, so the CPU selector sees retail-like situation tags.
Menus hold 8-12 plays; the pack replaces exactly the book's ordinary offense.
Never writes a disc.  Gameplay is unwitnessed.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core.nfl2k5_complete_offense import ordinary_indices  # noqa: E402
from pb.v2 import targeting  # noqa: E402

V2 = ROOT / "pb" / "v2"
CORE = V2 / "core.json"
TEAMS_DIR = V2 / "teams"
ALIASES = {"ARZ": "ARI", "STL": "LA", "SD": "LAC", "OAK": "LV"}
PREF_SHIFT = 9
PREF_MASK = 7 << PREF_SHIFT
VERSION = "2.0.0"


def pack_path(team: str) -> Path:
    name = "softdrink_giants_modern.2k5book" if team == "NYG" else f"softdrink_{team.lower()}_modern.2k5book"
    return ROOT / "data" / "playbooks" / name


# ---------------------------------------------------------------------------
# Retail book analysis
# ---------------------------------------------------------------------------

def header_kind(name: str, flags: int, sig: str) -> str | None:
    """Classify a retail ordinary offensive play into the engine's header kinds."""
    n = name.upper()
    cls = flags & 0xF000
    if sig == "flea":
        return "flea"
    if sig == "pass":
        if "SCREEN" in n:
            return "quick_screen" if cls == 0x2000 else "screen"
        if cls == 0x2000:
            return "quick"
        if n.startswith("RO"):
            return "rollout"
        return "dropback" if cls == 0x6000 else None
    if sig == "pa_pass":
        return "pa_rollout" if n.startswith("PA-RO") else "pa"
    if sig == "draw":
        return "draw" if cls == 0x8000 else None
    if sig == "qb_run":
        if "SNEAK" in n:
            return "qb_sneak"
        if "DRAW" in n:
            return "qb_draw"
        return None
    if sig == "run":
        if flags & 0x1000:
            return "reverse" if "REVERSE" in n else None
        if cls != 0x8000:
            return None
        return "run_toss" if flags & 0x02000000 else "run"
    return None


HEADER_FALLBACK = {"quick_screen": "quick", "screen": "dropback", "rollout": "dropback", "pa_rollout": "pa",
                   "run_toss": "run", "draw": "run", "qb_sneak": "qb_draw", "qb_draw": "draw",
                   "reverse": "run", "flea": "pa"}


class BookInfo:
    """Everything the generator needs from one retail team book (read only)."""

    def __init__(self, resource: bytes, team: str):
        self.resource = resource
        self.team = team
        self.book = insp.parse_playbook_resource(resource)
        self.body = resource[insp.RESOURCE_HEADER_SIZE:]
        fs, ps = ordinary_indices(self.book, self.body)
        self.forms = sorted(fs)
        self.plays = sorted(ps)
        self.cat_code = {}
        for ci in self.book.categories:
            off = insp.CATEGORY_BASE + ci.index * insp.CATEGORY_SIZE
            self.cat_code[ci.index] = self.body[off + 4] & 0x3F
        self.groups: dict[str, tuple[int, tuple[int, ...], tuple[int, ...]]] = {}
        for pers, canon in oc.PERSONNEL_CODES.items():
            full = oc.LINE_CODES + canon
            for ci in self.book.categories:
                codes = tuple(lib.category_positions(self.body, ci.index))
                if codes[:6] == full[:6] and sorted(codes) == sorted(full):
                    self.groups[pers] = (ci.index, codes, tuple(full.index(c) for c in codes))
                    break
        self.cat_names = {ci.index: ci.name.strip() for ci in self.book.categories}
        self.twins: dict[int, dict] = {}
        self.formation_donors = []
        for fi in self.forms:
            rec = lib.formation_record(self.body, fi)
            fl = rec.flags
            cat = lib.formation_category(self.body, fi)
            self.formation_donors.append(dict(
                index=fi, name=self.book.formations[fi].name.strip(), category=cat,
                code=self.cat_code.get(cat), type=rec.type_code, gun=rec.qb_alignment == 2,
                triple=((fl >> 21) & 7, (fl >> 24) & 7, (fl >> 27) & 7)))
        self.header_donors = self._header_donors(ps)
        self.retained_chains: set[bytes] = set()
        for p in self.book.plays:
            if p.index in ps:
                continue
            for _desc, nodes in lib.play_chains(self.body, p.index)[1]:
                self.retained_chains.add(b"".join(nodes))
        self.retained_nodes = sum(len(c) // 8 for c in self.retained_chains)

    def _header_donors(self, ps) -> dict[str, tuple[int, str, int, str]]:
        groups: dict[str, list[tuple[int, int, str, str]]] = {}
        for p in self.book.plays:
            if p.index not in ps:
                continue
            flags, chains = lib.play_chains(self.body, p.index)
            sig = lib.qb_signature(chains[0][1])
            kind = header_kind(p.name.strip(), flags, sig)
            if kind is not None:
                groups.setdefault(kind, []).append((p.index, flags, sig, p.name.strip()))
        out = {}
        for kind, rows in groups.items():
            pool = [r for r in rows if r[1] & 0x3F == 0x0E] or rows
            word = Counter(r[1] for r in pool).most_common(1)[0][0]
            index, flags, sig, name = next(r for r in pool if r[1] == word)
            out[kind] = (index, name, flags, sig)
        return out

    def category(self, name: str) -> int:
        hits = [ci for ci, t in self.twins.items() if t.get("name") == name] or \
               [ci for ci, n in self.cat_names.items() if n == name]
        if len(hits) != 1:
            raise ValueError(f"{self.team}: personnel group {name!r} is not one record of this book")
        return hits[0]

    def apply_personnel_groups(self, pkg: dict, core: dict | None = None) -> None:
        """b77 p6s: ``personnel_groups`` turns spare stock groups into twins of another personnel
        (same eleven players, its own CPU lottery code and label), e.g. an 11-personnel group at the
        passing-down code 9 so third and long keeps 11 personnel (the native category target
        0x209FE0 puts third and 8+ at 9-10, where the stock Flush group fields 10 personnel)."""
        groups = pkg.get("personnel_groups")
        if groups is None:
            # b77 p6s (GOAL P4): the core default turns the first spare record of each listed candidate into the
            # twin (e.g. Flush, else Queens -> "Kings Long", 11 personnel at the passing-down code 9)
            groups = {}
            for spec in (core or {}).get("personnel_groups_default", []):
                for name in spec["records"]:
                    if any(n == name for n in self.cat_names.values()):
                        groups[name] = {k: v for k, v in spec.items() if k != "records"}
                        break
        for name, spec in groups.items():
            ci = self.category(name)
            twin_of = spec["twin_of"]
            src_ci, codes, order = self.groups[twin_of]
            code = int(spec.get("code", self.cat_code[ci]))
            if not 0 <= code <= 10:
                raise ValueError(f"{self.team}: personnel group {name} code {code} outside 0..10")
            self.twins[ci] = dict(positions=codes, code=code, name=spec.get("name"), personnel=twin_of, order=order)
        if self.twins:
            for pers in list(self.groups):
                if self.groups[pers][0] in self.twins:
                    del self.groups[pers]

    def header_donor(self, kind: str) -> tuple[int, str, int, str]:
        seen = []
        while kind not in self.header_donors:
            seen.append(kind)
            kind = HEADER_FALLBACK.get(kind)
            if kind is None or kind in seen:
                raise ValueError(f"{self.team}: no retail donor for header kind {seen[0]}")
        return self.header_donors[kind]

    def formation_donor(self, spec: oc.FormationSpec, used: Counter) -> dict:
        code = oc.PERSONNEL_CATEGORY_ID[spec.personnel]
        gun = spec.align in ("gun", "pistol")

        def cost(d):
            return ((d["code"] != code) * 100 + (d["type"] != spec.backs) * 20 + (d["gun"] != gun) * 6
                    + sum(abs(a - b) for a, b in zip(d["triple"], spec.situation)) + used[d["index"]] * 0.75,
                    d["index"])
        return min(self.formation_donors, key=cost)


# ---------------------------------------------------------------------------
# Team packages
# ---------------------------------------------------------------------------

def load_core() -> dict:
    return json.loads(CORE.read_text(encoding="utf-8"))


def load_package(team: str) -> dict:
    path = TEAMS_DIR / f"{team}.json"
    if not path.exists():
        return {"team": team}
    return json.loads(path.read_text(encoding="utf-8"))


def tendency_features(pkg: dict) -> dict[str, float]:
    t = pkg.get("tendencies", {})
    pers = t.get("personnel", {})
    total = sum(pers.values()) or 1
    share = lambda k: 100.0 * pers.get(k, 0) / total  # noqa: E731
    gun = t.get("shotgun_pct", 65.0)
    return {"pistol": min(3.0, t.get("pistol_pct", 3.0) / 6.0), "p11": share("11") / 20.0,
            "p12": share("12") / 12.0, "p13": share("13") / 4.0, "p21": share("21") / 6.0,
            "p22": share("22") / 3.0, "p01": share("01") * 2.0, "gun": gun / 30.0, "uc": (100 - gun) / 30.0}


def choose_formations(info: BookInfo, core: dict, pkg: dict) -> list[str]:
    n = len(info.forms)
    exact = pkg.get("formations", {}).get("exact")
    if exact:
        # b77 p6s: a team package may name its whole formation list (book order, one per ordinary slot)
        bad = [f for f in exact if f not in oc.FORMATIONS or oc.FORMATIONS[f].personnel not in info.groups]
        if bad or len(exact) != n or len(set(exact)) != n:
            raise ValueError(f"{info.team}: formations.exact needs {n} distinct formations the book can field ({bad})")
        return list(exact)
    avoid = set(pkg.get("formations", {}).get("avoid", []))
    prefer = [f for f in pkg.get("formations", {}).get("prefer", []) if f in oc.FORMATIONS]

    def ok(name):
        return oc.FORMATIONS[name].personnel in info.groups and name not in avoid

    feats = tendency_features(pkg)
    optional = []
    for name, weights in core["optional_formations"].items():
        if not ok(name) or name in core["core_formations"]:
            continue
        score = sum(w * feats.get(k, 0.0) for k, w in weights.items()) + (100 if name in prefer else 0)
        optional.append((-score, name))
    optional.sort()
    chosen = [f for f in core["core_formations"] if ok(f)]
    preferred_optional = [name for _, name in optional if name in prefer]
    keep_core = n - len(preferred_optional)
    if len(chosen) > keep_core:
        chosen = chosen[:max(keep_core, 0)]
    chosen += preferred_optional
    # b77 p48o: the native 0x207EF0 rule scores a shotgun/pistol formation 0.05 outside the 10 and
    # 0x208120 averages every member of a personnel group, so each extra gun set in a group lowers
    # how often the CPU picks that personnel on early downs; tendency-filled extras stop at the cap.
    caps = core.get("max_gun_sets", {})

    def over_cap(name):
        spec = oc.FORMATIONS[name]
        cap = caps.get(spec.personnel)
        if cap is None or spec.align not in ("gun", "pistol"):
            return False
        have = sum(1 for f in chosen if oc.FORMATIONS[f].personnel == spec.personnel
                   and oc.FORMATIONS[f].align in ("gun", "pistol"))
        return have >= cap

    for _, name in optional:
        if len(chosen) >= n:
            break
        if name not in chosen and not over_cap(name):
            chosen.append(name)
    for _, name in optional:
        if len(chosen) >= n:
            break
        if name not in chosen:
            chosen.append(name)
    if len(chosen) < n:
        raise ValueError(f"{info.team}: only {len(chosen)} formations available for {n} ordinary slots")
    return chosen[:n]


def menu_candidates(fname: str, core: dict, pkg: dict) -> list[dict]:
    """Priority-ordered candidate entries {concept, overrides} for one formation."""
    keep = set(pkg.get("keep_in_menu", core.get("keep_in_menu", {})).get(fname, []))
    # b77 p48o: core gadgets (Flea Flicker, End Around, Reverse) never leave their menu, like signatures
    team_menu = pkg.get("menus", {}).get(fname)
    if team_menu is not None:
        # b77 p6s: a team package may author a formation's whole menu (priority order). Entries are concept
        # names or {"concept", "name", "overrides"}; named entries are team plays and never leave the menu.
        base = []
        for e in team_menu:
            if isinstance(e, str):
                base.append({"concept": e, "overrides": {}, **({"signature": True} if e in keep else {})})
            else:
                ov = dict(e.get("overrides", {}))
                if e.get("name"):
                    ov["name"] = e["name"]
                base.append({"concept": e["concept"], "overrides": ov,
                             **({"signature": True} if e.get("name") or e["concept"] in keep else {})})
    else:
        base = [{"concept": c, "overrides": {}, **({"signature": True} if c in keep else {})} for c in core["menus"][fname]]
    avoid = set(pkg.get("avoid_concepts", []))      # b77 p6s: e.g. node-tight books skip some core concepts
    base = [e for e in base if e["concept"] not in avoid or e.get("signature")]
    boost = pkg.get("boost", {})
    scored = []
    for rank, entry in enumerate(base):
        scored.append((rank - 2.0 * boost.get(entry["concept"], 0), rank, entry))
    # the formation's first entry (its base call) stays first
    first = scored[0]
    rest = sorted(scored[1:], key=lambda t: (t[0], t[1]))
    ordered = [first[2]] + [t[2] for t in rest]
    extras = []
    for sig in pkg.get("signature", []):
        if sig.get("formation") == fname:
            extras.append({"concept": sig["concept"], "overrides": dict(sig.get("overrides", {}), name=sig["name"]),
                           "signature": True})
    for name in pkg.get("menu_adds", {}).get(fname, []):
        extras.append({"concept": name, "overrides": {}})
    out = ordered[:2] + extras + ordered[2:]
    step = pkg.get("depth_step", 0)
    if step:
        for e in out:
            e["overrides"] = dict(e["overrides"])
            e["overrides"].setdefault("depth_step", step)
    return out


# ---------------------------------------------------------------------------
# Designs, dedupe and menu fitting
# ---------------------------------------------------------------------------

def chain_key(chains) -> tuple:
    return tuple(b"".join(n.to_bytes() for n in codec.encode_chain(ch)) for ch in chains)


def build_designs(formations: list[str], core: dict, pkg: dict):
    cands = OrderedDict()
    for fname in formations:
        spec = oc.FORMATIONS[fname]
        ctx = spec.context()
        rows, seen = [], set()
        for entry in menu_candidates(fname, core, pkg):
            try:
                d = targeting.apply(oc.design(entry["concept"], ctx, entry["overrides"]), spec, pkg["team"])
            except oc.ConceptUnavailable:
                continue
            key = (spec.personnel, d.header, chain_key(d.chains))
            # Retargeting can make a named signature share the core's chain.
            # Keep its name as a separate record without restoring old reads.
            # Identical assignments still share nodes in the compiled pool.
            if entry["overrides"].get("name"):
                key += (d.name,)
            if key in seen:
                continue
            seen.add(key)
            rows.append((key, d, bool(entry.get("signature"))))
        cands[fname] = rows
    return cands


def variant_candidates(fname: str, cands_row_keys: set, pkg: dict):
    """Extra unique plays for books with spare play slots: deeper stems and weak-side runs."""
    spec = oc.FORMATIONS[fname]
    ctx = spec.context()
    out = []
    base_step = pkg.get("depth_step", 0)
    heavy = spec.tag in ("goal", "short")
    # b77 p6s: goal-line and short-yardage sets take weak-side runs and play action first and never a deeper
    # dropback copy (a "Mesh Deep" from the goal line was filling spare play slots)
    order = sorted(oc.CONCEPTS, key=lambda n: (oc.CONCEPTS[n].family != "run") if heavy else 0)
    for name in order:
        cd = oc.CONCEPTS[name]
        families = ("pa", "shot") if heavy else ("dropback", "pa", "shot")
        for ov in ({"depth_step": base_step + 2} if cd.family in families else None,
                   {"direction": "weak"} if cd.family == "run" else None):
            if ov is None:
                continue
            try:
                d = oc.design(name, ctx, ov)
                d = targeting.apply(d, spec, pkg["team"])
            except oc.ConceptUnavailable:
                continue
            key = (spec.personnel, d.header, chain_key(d.chains))
            if key in cands_row_keys:
                continue
            if ov.get("direction") == "weak" and not d.name.endswith("Weak"):
                d.name = (d.name + " Weak")[:40]
            elif ov.get("depth_step"):
                d.name = (d.name + " Deep")[:40]
            out.append((key, d, False))
            cands_row_keys.add(key)
    return out


def fit_menus(cands, n_plays: int, core: dict, pkg: dict):
    """Pick 8-12 plays per formation so the book holds exactly ``n_plays`` distinct plays.

    1. every formation takes its first ``menu_min`` candidates (its OC priority order);
    2. if that is more distinct plays than the book holds, unique-only links leave the
       largest menus first (signature plays never leave);
    3. free links: a menu adds later candidates that some other menu already holds
       (more plays per menu at no play-slot cost);
    4. remaining play slots go to the smallest menus, a new distinct play each, then
       deeper or weak-side variants if a formation runs out of concepts;
    5. free links again up to ``menu_max``.
    """
    lo, hi = core["menu_min"], core["menu_max"]
    named = {s["name"] for s in pkg.get("signature", [])}
    named.update(e["name"] for menu in pkg.get("menus", {}).values()
                 for e in menu if isinstance(e, dict) and e.get("name"))
    designs = {}
    for rows in cands.values():
        for k, d, _ in rows:
            # A normalized read chain may be shared across formations.
            # A later core alias must not erase an existing team play's name.
            if k not in designs or designs[k].name not in named or d.name in named:
                designs[k] = d
    signature = {k for rows in cands.values() for k, _, s in rows if s}
    menus = {f: [] for f in cands}
    pointer = {f: 0 for f in cands}
    for f, rows in cands.items():
        for k, _, s in rows:
            if len(menus[f]) >= lo and not s:
                continue
            if k not in menus[f]:
                menus[f].append(k)
    def uses():
        u = Counter()
        for keys in menus.values():
            u.update(keys)
        return u
    u = uses()
    for floor in (lo, 6, 4, 3):
        while len(u) > n_plays:
            best = None
            for f, keys in menus.items():
                if len(keys) <= floor:
                    continue
                for pos in range(len(keys) - 1, 2, -1):
                    k = keys[pos]
                    if u[k] == 1 and k not in signature:
                        cand = (-len(keys), pos, list(menus).index(f))
                        if best is None or cand < best[0]:
                            best = (cand, f, pos)
                        break
            if best is None:
                break
            _, f, pos = best
            k = menus[f].pop(pos)
            u[k] -= 1
            if not u[k]:
                del u[k]
        if len(u) <= n_plays:
            break
    if len(u) > n_plays:
        raise ValueError(f"cannot fit {len(u)} distinct plays into {n_plays}")

    def free_links(limit):
        added = True
        while added:
            added = False
            for f, rows in cands.items():
                if len(menus[f]) >= limit:
                    continue
                for k, _, _ in rows:
                    if k in u and k not in menus[f]:
                        menus[f].append(k)
                        u[k] += 1
                        added = True
                        break

    free_links(hi - 2)
    extra = {f: None for f in cands}
    while len(u) < n_plays:
        progress = False
        for f in sorted(menus, key=lambda f: (len(menus[f]), list(menus).index(f))):
            if len(u) >= n_plays:
                break
            if len(menus[f]) >= hi:
                continue
            pick = next((k for k, _, _ in cands[f] if k not in u), None)
            if pick is None:
                if extra[f] is None:
                    extra[f] = variant_candidates(f, set(designs), pkg)
                    for k, d, _ in extra[f]:
                        designs[k] = d
                pick = next((k for k, _, _ in extra[f] if k not in u), None)
            if pick is None:
                continue
            menus[f].append(pick)
            u[pick] = 1
            progress = True
        if not progress:
            raise ValueError(f"cannot reach {n_plays} distinct plays (have {len(u)})")
    free_links(hi)
    # rebalance: a menu below ``menu_min`` takes a distinct play slot from the fullest menu
    for _ in range(400):
        small = [f for f in menus if len(menus[f]) < lo]
        if not small:
            break
        f = min(small, key=lambda f: (len(menus[f]), list(menus).index(f)))
        pick = next((k for k, _, _ in cands[f] if k not in u), None)
        if pick is None:
            if extra[f] is None:
                extra[f] = variant_candidates(f, set(designs), pkg)
                for k, d, _ in extra[f]:
                    designs[k] = d
            pick = next((k for k, _, _ in extra[f] if k not in u), None)
        donor = None
        for g in sorted(menus, key=lambda g: -len(menus[g])):
            if len(menus[g]) <= lo:
                break
            pos = next((i for i in range(len(menus[g]) - 1, 2, -1)
                        if u[menus[g][i]] == 1 and menus[g][i] not in signature), None)
            if pos is not None:
                donor = (g, pos)
                break
        if pick is None or donor is None:
            break
        g, pos = donor
        gone = menus[g].pop(pos)
        del u[gone]
        menus[f].append(pick)
        u[pick] = 1
        free_links(hi)
    return menus, designs


def book_chain_bytes(design, info: "BookInfo", personnel: str) -> list[bytes]:
    order = info.groups[personnel][2]
    return [b"".join(n.to_bytes() for n in codec.encode_chain(ch)) for ch in to_book_order(design.chains, order)]


def budget_repair(menus, designs, cands, info, cap: int, pkg: dict, core: dict | None = None) -> dict:
    """Keep the compiled total (retained retail chains + this offense) at or under ``cap`` nodes.

    The defense pack is compiled after the offense and appends its chains, so the offense
    leaves ``3500 - cap`` nodes for it.  Over the cap, the one-off play whose private chains
    cost the most nodes is swapped for the formation's cheapest unused candidate."""
    cache: dict = {}

    def chains_of(k):
        if k not in cache:
            cache[k] = book_chain_bytes(designs[k], info, k[0])
        return cache[k]

    def total_and_owner():
        owner: dict[bytes, set] = {}
        for keys in menus.values():
            for k in keys:
                for c in chains_of(k):
                    owner.setdefault(c, set()).add(k)
        own = {c: o for c, o in owner.items() if c not in info.retained_chains}
        return info.retained_nodes + sum(len(c) // 8 for c in own), own

    total, own = total_and_owner()
    start = total
    swaps = []
    extra_pool: dict = {}
    signature = {k for rows in cands.values() for k, _, s in rows if s}
    # Core gadgets a tight book may give up, in this order, once no other swap fits the cap
    # (the Flea Flicker is never on the list; team signatures, renamed, are never released).
    release = list((core or {}).get("keep_release_order", []))
    released = []
    for _ in range(300):
        if total <= cap:
            break
        uses = Counter(k for keys in menus.values() for k in keys)
        private = Counter()
        for c, o in own.items():
            if len(o) == 1:
                private[next(iter(o))] += len(c) // 8
        victims = sorted((k for k in private if uses[k] == 1 and k not in signature), key=lambda k: -private[k])
        done = False
        lo = (core or {}).get("menu_min", 8)
        hi = (core or {}).get("menu_max", 12)
        present = set(own) | info.retained_chains
        for victim in victims:
            f = next(f for f, keys in menus.items() if victim in keys)
            options = []
            for g in menus:
                if g != f and (len(menus[g]) >= hi or len(menus[f]) <= lo):
                    continue
                if g not in extra_pool:
                    extra_pool[g] = variant_candidates(g, set(designs), pkg)
                for k, d, _ in list(cands[g]) + extra_pool[g]:
                    if k in uses:
                        continue
                    designs.setdefault(k, d)
                    cost = sum(len(c) // 8 for c in set(chains_of(k)) if c not in present)
                    options.append((cost, g != f, list(menus).index(g), k, g))
            if not options:
                continue
            cost, _moved, _rank, best, g = min(options, key=lambda t: t[:3])
            if cost >= private[victim]:
                continue
            if g == f:
                menus[f][menus[f].index(victim)] = best
            else:
                menus[f].remove(victim)
                menus[g].append(best)
            swaps.append(dict(formation=f, into=g, removed=designs[victim].name, added=designs[best].name,
                              saved=private[victim] - cost))
            total, own = total_and_owner()
            done = True
            break
        if not done:
            if not release:
                break
            concept = release.pop(0)
            freed = {k for k in signature if designs[k].name == concept and designs[k].concept == concept}
            signature -= freed
            if freed:
                released.append(concept)
    if total > cap:
        raise ValueError(f"{info.team}: offense needs {total} nodes, over the {cap} cap")
    return dict(cap=cap, before=start, after=total, retained=info.retained_nodes, swaps=swaps, released=released)


# ---------------------------------------------------------------------------
# Pack assembly
# ---------------------------------------------------------------------------

def to_book_order(chains, order):
    moved = [[(op, list(vals)) for op, vals, *_ in chain] for chain in packs.permute_assignments(chains, order)]
    inverse = {old: new for new, old in enumerate(order)}
    for chain in moved:
        for op, vals in chain:
            if op == 0x06:
                for n in range(1, 5):
                    ordinal = int(vals[n])
                    if 1 <= ordinal <= 5:
                        vals[n] = inverse[ordinal + 5] - 5
    return moved


def header_word(donor_flags: int, preference: int) -> int:
    return (donor_flags & ~PREF_MASK) | ((max(0, min(4, int(preference))) & 7) << PREF_SHIFT)


def build_team(resource: bytes, team: str, core: dict | None = None, pkg: dict | None = None):
    core = core or load_core()
    pkg = pkg or load_package(team)
    info = BookInfo(resource, team)
    info.apply_personnel_groups(pkg, core)
    formations = choose_formations(info, core, pkg)
    cands = build_designs(formations, core, pkg)
    menus, designs = fit_menus(cands, len(info.plays), core, pkg)
    cap = int(pkg.get("node_cap", core.get("offense_total_node_cap", 3500)))
    budget = budget_repair(menus, designs, cands, info, cap, pkg, core)
    order_keys = []
    for f in formations:
        for k in menus[f]:
            if k not in order_keys:
                order_keys.append(k)
    assert len(order_keys) == len(info.plays), (len(order_keys), len(info.plays))
    play_ids = {}
    plays_out, rows = [], []
    for k, pi in zip(order_keys, info.plays):
        d = designs[k]
        pers = k[0]
        ci, codes, order = info.groups[pers]
        donor_index, donor_name, donor_flags, donor_sig = info.header_donor(d.header)
        pref = d.preference + int(pkg.get("preference_shift", {}).get(d.concept, 0))
        flags = header_word(donor_flags, pref)
        chains = to_book_order(d.chains, order)
        pid = f"p{pi:03d}"
        play_ids[k] = pid
        plays_out.append(packs.PackPlay(
            pid, d.name[:40], d.play_type, tuple(tuple(ch) for ch in chains),
            packs.PackDonor(donor_index, donor_name, donor_flags, donor_sig), flags, pi,
            info.book.plays[pi].name.strip(), d.concept))
        rows.append(dict(status="DESIGN", team=team, play_index=pi, name=d.name, concept=d.concept,
                         family=oc.CONCEPTS[d.concept].family, header=d.header, play_type=d.play_type,
                         personnel=pers, preference=pref, flags=f"0x{flags:08x}",
                         primary_slot=order.index(d.primary) if d.primary is not None else None,
                         reads=[order.index(r) for r in d.reads], tags=list(d.tags),
                         formations=[f for f in formations if k in menus[f]]))
    used = Counter()
    ratings = dict(core.get("formation_ratings", {}))
    ratings.update(pkg.get("formation_ratings", {}))
    forms_out, menus_out, form_rows = [], [], []
    fgroups = pkg.get("formation_groups")
    if fgroups is None:
        fgroups = core.get("formation_groups_default", {}) if pkg.get("personnel_groups") is None else {}
    for f, fi in zip(formations, info.forms):
        spec = oc.FORMATIONS[f]
        ci, codes, order = info.groups[spec.personnel]
        mask = None
        grp = fgroups.get(f)
        explicit = pkg.get("formation_groups") is not None
        resolvable = grp and all(any(t.get("name") == n for t in info.twins.values()) or n in info.cat_names.values()
                                 for n in [grp["own"], *grp.get("mask", [])])
        if grp and (explicit or resolvable):     # core defaults skip books that lack a named group
            ci = info.category(grp["own"])
            owner = info.twins.get(ci, dict(personnel=spec.personnel if ci == info.groups[spec.personnel][0] else None))
            if owner["personnel"] != spec.personnel:
                raise ValueError(f"{team}: {f} ({spec.personnel}) cannot be owned by {grp['own']}")
            mask = tuple(sorted({info.category(n) for n in grp.get("mask", [grp["own"]])} | {ci}))
        twin = info.twins.get(ci)
        donor = info.formation_donor(spec, used)
        if mask is None and info.twins:
            # a twin keeps only the members that field its players: drop it from stock cross-personnel masks
            aux = insp.FORMATION_AUX_BASE + donor["index"] * insp.FORMATION_AUX_SIZE
            d_own, d_mask = struct.unpack_from("<II", info.body, aux + 0x48)
            stock = [c for c in range(insp.CATEGORY_CAPACITY if hasattr(insp, "CATEGORY_CAPACITY") else 26)
                     if d_mask >> c & 1] if (d_own & 0x3F) == ci else [ci]
            mask = tuple(sorted({c for c in stock if c not in info.twins or info.twins[c]["personnel"] == spec.personnel} | {ci}))
        used[donor["index"]] += 1
        canon = spec.positions_cm()
        positions = tuple(canon[s] for s in order)
        fid = f"f{fi:02d}"
        cpu = ratings.get(spec.name)
        forms_out.append(packs.PackFormation(fid, spec.name, positions, codes,
                                             packs.PackDonor(donor["index"], donor["name"]), fi,
                                             info.book.formations[fi].name.strip(), ci,
                                             category_positions=tuple(twin["positions"]) if twin else None,
                                             situation=tuple(cpu) if cpu else None,
                                             category_mask=mask,
                                             category_code=twin["code"] if twin else None,
                                             category_name=twin["name"] if twin else None))
        menus_out.append((fid, tuple(play_ids[k] for k in menus[f])))
        form_rows.append(dict(formation_index=fi, name=spec.name, personnel=spec.personnel, align=spec.align,
                              group=info.twins[ci]["name"] if ci in info.twins and info.twins[ci]["name"] else info.cat_names[ci],
                              group_code=info.twins[ci]["code"] if ci in info.twins else info.cat_code[ci],
                              group_mask=[(info.twins[c]["name"] if c in info.twins and info.twins[c]["name"] else info.cat_names[c])
                                          for c in mask] if mask else None,
                              tag=spec.tag, situation_target=list(spec.situation), donor=donor["name"],
                              donor_index=donor["index"], donor_situation=list(donor["triple"]),
                              cpu_situation=list(cpu) if cpu else list(donor["triple"]),
                              donor_type=donor["type"], menu=[designs[k].name for k in menus[f]]))
    notes = (f"DESIGN (beta 77 p48o v2): {pkg.get('identity', 'shared SOFTDRINK core')}. Shared core plus the "
             f"{team} package (pb/v2/teams/{team}.json); retail-grammar routes and headers; situation ratings from "
             "the book's own retail formations. Compatible direct reads use 2026 regular-season target shares "
             "(pb/research/targets_2026.json; nflverse, CC-BY-4.0), via pb/v2/targeting.py. "
             "No pre-snap motion, no RPO. All gameplay unwitnessed.")
    pack = packs.PlaybookPack(
        packs.PackBook(team, f"SOFTDRINK 2K28 {team} Offense", "SOFTDRINK / Claude (p48o)", VERSION, "CC0-1.0",
                       notes=notes[:2000]),
        packs.PackBase(packs.book_fingerprint(info.body), len(info.book.formations), len(info.book.plays),
                       info.book.node_count),
        tuple(forms_out), tuple(plays_out), packs.OFFENSE_SCHEMA, tuple(menus_out))
    catalog = dict(team=team, formations=form_rows, plays=rows,
                   menu_sizes=[len(m) for _, m in menus_out], node_budget=budget,
                   target_policy=dict(data="pb/research/targets_2026.json",
                       sha256=hashlib.sha256(targeting.DATA.read_bytes()).hexdigest(),
                       weeks=targeting.target_data()["coverage"]["weeks"],
                       rule="Direct reads descend by observed share within authored depth bands; ties, screens, gadgets, moving pockets and delayed releases retain authored order."))
    return pack, catalog


def semantic_digest(pack) -> str:
    by_play = {p.id: p for p in pack.plays}
    semantic = [(pack.formations_by_id[f].slot_positions, pack.formations_by_id[f].position_codes,
                 [(by_play[p].concept, by_play[p].play_flags, by_play[p].assignments) for p in menu])
                + ((pack.formations_by_id[f].situation,) if pack.formations_by_id[f].situation else ())
                for f, menu in pack.menus]
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, default=list).encode()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True, help="retail ISO (read only)")
    ap.add_argument("--team", action="append", help="limit to these teams")
    ap.add_argument("--write", action="store_true", help="write data/playbooks packs and pb/v2 catalogs")
    args = ap.parse_args(argv)
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    core = load_core()
    teams = args.team or list(packs.TEAM_BOOKS)
    manifest = []
    (V2 / "catalogs").mkdir(exist_ok=True)
    with OuterImage(args.image) as image:
        for team in teams:
            pack, catalog = build_team(image.read_entry(BOOK_ENTRIES[team]), team, core)
            check = packs.check_pack(pack)
            if not check.ok:
                raise SystemExit(f"{team}: {check.text()}")
            row = dict(team=team, pack=str(pack_path(team).relative_to(ROOT)), formations=len(pack.formations),
                       plays=len(pack.plays), links=sum(len(m) for _, m in pack.menus),
                       semantic_sha256=semantic_digest(pack))
            manifest.append(row)
            if args.write:
                packs.save_pack(pack, pack_path(team))
                (V2 / "catalogs" / f"{team}.json").write_text(json.dumps(catalog, indent=1) + "\n",
                                                              encoding="utf-8", newline="\n")
            print(team, row["formations"], row["plays"], row["links"], flush=True)
    if args.write and not args.team:
        (V2 / "manifest.json").write_text(json.dumps(dict(status="DESIGN on PROVED OFFLINE grammar",
                                                          runtime_witness=False, version=VERSION, teams=manifest),
                                                     indent=1) + "\n", encoding="utf-8", newline="\n")
        # pb/defense/build.py and pb/phase4.py read the offense pack paths from the league manifest
        rows = [dict(team=r["team"], pack=r["pack"], plays=r["plays"], formations=r["formations"],
                     semantic_sha256=r["semantic_sha256"]) for r in manifest]
        (ROOT / "pb" / "league_manifest.json").write_text(json.dumps(dict(
            status="PROVED OFFLINE", runtime_witness=False,
            generator="pb/v2/build.py (beta 77 p48o); pb/build_league.py is the v0.5 reference generator",
            teams=rows), indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
