#!/usr/bin/env python3
"""fs1: plan which real face scan every moment and classic player gets (offline; reads two discs, writes data).

Noah, 2026-10-18: "Eli Manning MVP. We should use Eli's actual face scan if we still have it, for any player that
actually has their face scan in the game." This tool decides, for every player of the 35 retail-moment rosters, the 50
added-moment team-seasons and the 24 classic teams:

  own-2026   a current main-roster record of the same person (the existing rule; also found by last name + birth date
             or first name + birth date when the spelling differs: Greg / Gregory, Joey Porter Jr.)
  own-retail the person's retail 2004 record (or a retail historic team's record) that has a live face, when no current
             record uses that id
  relocate   the same, but the 2026 league reused the retail id: the scan is copied into a free id
             (data/nfl2k5_moment_scans.json, applied by nfl2k5_moment_scans)
  generic    no scan exists: the generic head by skin

Matching (all tiers keep the retail record's own photo id, skin, face and dreads):
  name+year        first + last name and birth year (as the roster stores it)
  last+birthdate   last name, birth year, month and day, first names one the prefix of the other (Mike / Michael)
  first+birthdate  first name, birth date, last names one the prefix of the other ("Porter" / "Porter Jr.")
  fuzzy(dy=n)      identical name, birth year within three, same broad position group (the retail rookie class carries
                   birth years two off: Eli Manning is 1979-12-27 there, 1981-01-03 in life)

  python3 tools/b77/fs1_scans_plan.py --retail RETAIL.iso --base SOFTDRINK.iso --out OUTDIR [--write]

--base is any disc whose main roster and faces are the league the data is planned for (the canonical SOFTDRINK build).
Nothing is written to a disc. --write copies the generated data into data/ (the three appearance files and the scans
table); without it everything lands in OUTDIR for review.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_classic_teams as ct  # noqa: E402
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_espn25_rosters as er  # noqa: E402
from mod_editor.core import nfl2k5_historic_styles as hs  # noqa: E402
from mod_editor.core import nfl2k5_moment_scans as ms  # noqa: E402
from mod_editor.core import nfl2k5_roster_appearance_transfer as at  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

GROUP = {"QB": "QB", "HB": "SK", "FB": "SK", "WR": "SK", "TE": "SK", "C": "OL", "G": "OL", "T": "OL", "DE": "F7",
         "DT": "F7", "ILB": "F7", "OLB": "F7", "CB": "DB", "FS": "DB", "SS": "DB", "K": "K", "P": "P"}
RETAIL_APPEARANCE_JSON = ROOT / "data/nfl2k5_espn25_moment_rosters/appearance.json"
MORE_APPEARANCE_JSON = mm.APPEARANCE_JSON
CLASSIC_APPEARANCE_JSON = ct.DATA_DIR / "appearance.json"


def _clean(text):
    return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", text.casefold()))


def _related(a, b):
    a, b = _clean(a), _clean(b)
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def person(p):
    v = p.record.values
    return dict(first=p.first, last=p.last, group=p.group, photo=v["photo_id"], by=v["birth_year_low"] | (v["birth_year_high"] << 3),
                bm=v["birth_month"], bd=v["birth_day"], face=v["face"], skin=p.record.skin, dreads=v["dreads"],
                pos=p.record.position_name)


class Index:
    def __init__(self, people):
        self.people = people
        self.k1, self.k2, self.k3 = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
        self.names = collections.defaultdict(list)
        for x in people:
            f, l = x["first"].casefold(), x["last"].casefold()
            self.k1[(f, l, x["by"])].append(x)
            self.k2[(l, x["by"], x["bm"], x["bd"])].append(x)
            self.k3[(f, x["by"], x["bm"], x["bd"])].append(x)
            self.names[(f, l)].append(x)

    def strict(self, first, last, born):
        by = born.year % 100
        hit = self.k1.get((first.casefold(), last.casefold(), by))
        if hit:
            return "name+year", hit
        hit = [h for h in self.k2.get((last.casefold(), by, born.month, born.day), []) if _related(h["first"], first)]
        if hit:
            return "last+birthdate", hit
        hit = [h for h in self.k3.get((first.casefold(), by, born.month, born.day), []) if _related(h["last"], last)]
        if hit:
            return "first+birthdate", hit
        return None, []

    def fuzzy(self, first, last, born, pos):
        out = []
        for x in self.names.get((first.casefold(), last.casefold()), []):
            d = abs((x["by"] - born.year % 100 + 50) % 100 - 50)
            if d <= 3 and GROUP.get(x["pos"], x["pos"]) == GROUP.get(pos, pos):
                out.append((d, x))
        return out


class Planner:
    def __init__(self, retail, base):
        self.retail_path, self.base_path = Path(retail), Path(base)
        self.catalog = at._catalog()
        self.face_ids = {int(r["face_id"]) for r in self.catalog_resources()}
        self.generic = set(range(9001, 9508))
        self.custom = {f for f in self.face_ids if f not in self.generic}
        self.retail_doc = rr.load_image(self.retail_path)
        self.base_doc = rr.load_image(self.base_path)
        self.retail_people = [person(p) for p in self.retail_doc.players]
        self.base_people = [person(p) for p in self.base_doc.players]
        self.base_photos = {x["photo"] for x in self.base_people}
        self.named_base = {x["photo"] for x in self.base_people if (x["first"] + x["last"]).strip()}
        self.read_discs()

    def catalog_resources(self):
        return [r for k, r in self.catalog.items() if k.endswith(":f") and not k.startswith("portrait:")]

    def read_discs(self):
        with rr._outer_image()(self.retail_path) as a:
            main = a.read(a.entries[5].virtual_offset, a.entries[5].size)
            self.descriptors = mm._retail_descriptors(main)
            by_id = {e.name_id: e for e in a.entries}
            self.retail_files = {}
            for d in self.descriptors:
                e = by_id.get(hs.name_id(d["filename"]))
                self.retail_files[d["filename"]] = a.read(e.virtual_offset, e.size)
            shapes = at._shape_offsets(a)
            self.retail_f = {}
            for face in self.custom:
                row = self.catalog[f"{face:04d}:f"]
                self.retail_f[face] = a.read(at._entry_for(a, row, shapes), row["span_size"])
        with rr._outer_image()(self.base_path) as b:
            shapes = at._shape_offsets(b)
            self.changed = set()
            for face in self.custom:
                row = self.catalog[f"{face:04d}:f"]
                if b.read(at._entry_for(b, row, shapes), row["span_size"]) != self.retail_f[face]:
                    self.changed.add(face)
        self.base_photo = {}
        with rr._outer_image()(self.base_path) as b:
            by_id = {e.name_id: e for e in b.entries}
            names = [f for f in self.retail_files] + [f for _k, f, *_ in mm.table_entries(mm.Data.load())]
            cd = ct.Data.load()
            names += [cd.filename(k, "HTS-") for k in cd.order()]
            for fn in names:
                e = by_id.get(hs.name_id(fn))
                if e is not None:
                    doc = rr.RosterDocument(b.read(e.virtual_offset, e.size)[32:])
                    self.base_photo[fn] = {p.index: p.record.values["photo_id"] for p in doc.players}
        self.hist = []
        for fn, raw in self.retail_files.items():
            for p in rr.RosterDocument(raw[32:]).players:
                x = person(p)
                if x["photo"] in self.custom:
                    self.hist.append(dict(x, group="hist:" + fn))
        self.idx_retail = Index(self.retail_people)
        self.idx_hist = Index(self.hist)
        self.idx_base = Index(self.base_people)
        self.retail_names = collections.defaultdict(list)
        for x in self.retail_people + self.hist:
            self.retail_names[(x["first"].casefold(), x["last"].casefold())].append(x)

    def current(self, r):
        fn = r["file"]
        photos = self.base_photo.get(fn) or self.base_photo.get(next((k for k in self.base_photo if k.endswith(fn)), ""), {})
        return photos.get(r["slot"])

    def has_portrait(self, ph):
        return f"portrait:{ph:04d}" in self.catalog

    # ------------------------------------------------------------------------------------------- one person
    def resolve(self, first, last, born, pos):
        out = dict(b26=[], retail=[])
        kind, hit = self.idx_base.strict(first, last, born)
        out["b26"] = [(kind, h) for h in hit if h["photo"] in self.custom]
        for src, idx in (("main", self.idx_retail), ("hist", self.idx_hist)):
            kind, hit = idx.strict(first, last, born)
            out["retail"] += [(kind, src, h) for h in hit if h["photo"] in self.custom]
        if not out["retail"]:
            for d, x in sum((i.fuzzy(first, last, born, pos) for i in (self.idx_retail, self.idx_hist)), []):
                if x["photo"] in self.custom:
                    out["retail"].append((f"fuzzy(dy={d})", "hist" if x["group"].startswith("hist:") else "main", x))
        out["retail"].sort(key=lambda c: (c[1] != "main", c[2]["photo"] in self.changed))
        return out

    def decide(self, first, last, born, pos):
        res = self.resolve(first, last, born, pos)
        if res["b26"]:
            tier, rec = res["b26"][0]
            return dict(want="own-2026", photo=rec["photo"], tier=tier, record=f"{rec['first']} {rec['last']}",
                        retail=dict(photo=rec["photo"], skin=rec["skin"], face=rec["face"], dreads=rec["dreads"]))
        if res["retail"]:
            tier, src, rec = res["retail"][0]
            retail = dict(photo=rec["photo"], skin=rec["skin"], face=rec["face"], dreads=rec["dreads"])
            want = "relocate" if rec["photo"] in self.changed else "own-retail"
            return dict(want=want, photo=rec["photo"], tier=tier, retail=retail, record=f"{rec['first']} {rec['last']}")
        return dict(want="generic", photo=None, tier=None, retail=None, record=None)

    # ------------------------------------------------------------------------------------------ all the teams
    def teams(self):
        """[(file, kind, key, [rows])]; a row: slot, first, last, pos, born, current disc photo from `current`."""
        out = []
        manifest = json.loads((er.DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
        for res in manifest["resources"]:
            rows = []
            raw = self.retail_files[res["filename"]]
            retail_names = {p.index: (p.first, p.last) for p in rr.RosterDocument(raw[32:]).players}
            for p in res["players"]:
                digits = p["source_identity"].split("|")[-1]
                born = datetime.date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
                rows.append(dict(slot=p["slot"], first=p["first"], last=p["last"], pos=None, born=born,
                                 retained=retail_names[p["slot"]] and tuple(s.casefold() for s in retail_names[p["slot"]])
                                 == (p["first"].casefold(), p["last"].casefold())))
            sheet = list(csv.DictReader(io.StringIO((er.DATA_DIR / res["csv"]).read_text(encoding="utf-8"))))
            for r, s in zip(rows, sheet):
                r["pos"] = s["position"]
            out.append((res["filename"], "retail-moment", res["filename"], rows))
        md = mm.Data.load()
        for key, fn, _e, _sel, _ident in mm.table_entries(md):
            rows = [dict(slot=i, first=r["first"], last=r["last"], pos=r["position"], born=datetime.date.fromisoformat(r["birth_date"]),
                         retained=False) for i, r in enumerate(md.rosters[key])]
            out.append((fn, "new-moment", key, rows))
        cd = ct.Data.load()
        for key in cd.order():
            rows = [dict(slot=i, first=r["first"], last=r["last"], pos=r["position"], born=datetime.date.fromisoformat(r["birth_date"]),
                         retained=False) for i, r in enumerate(cd.rosters[key])]
            out.append((cd.filename(key), "classic", key, rows))
        return out

    def plan(self):
        rows = []
        for fn, kind, key, players in self.teams():
            for r in players:
                d = self.decide(r["first"], r["last"], r["born"], r["pos"])
                rows.append(dict(file=fn, kind=kind, key=key, slot=r["slot"], name=f"{r['first']} {r['last']}", pos=r["pos"],
                                 born=str(r["born"]), retained=r["retained"], **d))
        return rows

    # -------------------------------------------------------------------------------------------- relocation
    def relocation(self, rows, other_files):
        """Choose a free id for every retail scan that the 2026 league reused. Exact head shape preferred."""
        info = collections.defaultdict(dict)
        for r in self.catalog_resources():
            info[int(r["face_id"])]["f"] = r
        for k, r in self.catalog.items():
            if k.endswith(":h") or k.endswith(":n"):
                info[int(r["face_id"])][k[-1]] = r
            elif k.endswith(":s"):
                info[int(r["face_id"])]["s"] = r
        demand = {}
        for r in rows:
            if r["want"] == "relocate":
                demand.setdefault(r["photo"], r["record"])
        kept = {r["photo"] for r in rows if r["want"] in ("own-2026", "own-retail")}
        # a retained retail-moment head stays: its retail id stays referenced
        kept |= {self.current(r) for r in rows if r["retained"]}
        other = {p.record.values["photo_id"] for fn, raw in self.retail_files.items() if fn not in other_files
                 for p in rr.RosterDocument(raw[32:]).players}
        supply = [f for f in sorted(self.custom) if f not in self.base_photos and f not in kept and f not in other
                  and f not in demand and self.has_portrait(f) and self.has_portrait_of(f)]
        need = {d: info[d] for d in demand}

        def fits(d, s):
            return (info[s]["h"]["stored_size"] >= need[d]["h"]["lz"]["consumed_bytes"]
                    and info[s]["n"]["stored_size"] >= need[d]["n"]["lz"]["consumed_bytes"] and self.has_portrait(d))

        # A slot's retail owner is lost to the game; prefer slots of the lowest-rated players (never a star).
        from mod_editor.core import nfl2k5_my_career_prospects as prospects
        owner_overall = collections.defaultdict(int)
        for p in self.retail_doc.players:
            ph = p.record.values["photo_id"]
            owner_overall[ph] = max(owner_overall[ph], prospects.native_overall(p.record))
        order = sorted(demand)
        cost = {}
        for d in order:
            for s in supply:
                if fits(d, s):
                    waste = (info[s]["h"]["stored_size"] - need[d]["h"]["lz"]["consumed_bytes"]
                             + info[s]["n"]["stored_size"] - need[d]["n"]["lz"]["consumed_bytes"])
                    same = info[s]["s"]["span_size"] == need[d]["s"]["span_size"]
                    cost[(d, s)] = (0 if same else 1000000) + 1000 * owner_overall[s] + waste
        assign = self.assign(order, supply, cost)
        scans = []
        for d in order:
            s = assign[d]
            same = info[s]["s"]["span_size"] == need[d]["s"]["span_size"]
            scans.append(dict(name=demand[d], retail=d, slot=s, shape="copied" if same else "kept"))
        return scans, dict(demand=len(demand), supply=len(supply))

    def has_portrait_of(self, f):
        return f"portrait:{f:04d}" in self.catalog

    @staticmethod
    def assign(order, supply, cost):
        try:
            import numpy as np
            from scipy.optimize import linear_sum_assignment
            big = 10 ** 9
            m = np.full((len(order), len(supply)), big, dtype=np.int64)
            for i, d in enumerate(order):
                for j, s in enumerate(supply):
                    if (d, s) in cost:
                        m[i, j] = cost[(d, s)]
            rr_, cc = linear_sum_assignment(m)
            out = {}
            for i, j in zip(rr_, cc):
                if m[i, j] >= big:
                    raise SystemExit(f"no free head id fits {order[i]}")
                out[order[i]] = supply[j]
            return out
        except ImportError:
            match = {}

            def go(d, seen):
                for s in sorted((s for (dd, s) in cost if dd == d), key=lambda s: cost[(d, s)]):
                    if s in seen:
                        continue
                    seen.add(s)
                    if s not in match or go(match[s], seen):
                        match[s] = d
                        return True
                return False
            for d in order:
                if not go(d, set()):
                    raise SystemExit(f"no free head id fits {d}")
            return {d: s for s, d in match.items()}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(path, doc):
    Path(path).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def appearance_updates(planner, rows):
    """Refresh the `retail` block of the added-moment and classic appearance files from the new matches."""
    changes = collections.Counter()
    out = {}
    for path, kind in ((MORE_APPEARANCE_JSON, "new-moment"), (CLASSIC_APPEARANCE_JSON, "classic")):
        doc = load_json(path)
        by = collections.defaultdict(dict)
        for r in rows:
            if r["kind"] == kind:
                by[r["key"]][r["slot"]] = r
        for key, looks in doc["teams"].items():
            for i, look in enumerate(looks):
                r = by[key][i]
                assert look["name"] == r["name"], (key, i)
                if r["retail"] is None or r["want"] == "own-2026":
                    continue
                if look.get("retail") is None:
                    look["retail"] = dict(r["retail"])
                    if r["tier"] != "name+year":
                        look["match"] = r["tier"]
                    changes[(kind, "new retail block")] += 1
                elif look["retail"]["photo"] != r["retail"]["photo"]:
                    changes[(kind, "DIFFERENT retail photo kept")] += 1
        out[path] = doc
    return out, changes


def retail_moment_doc(planner, rows):
    """appearance.json for the 35 retail-moment rosters: keep / retail / relocate / generic per slot."""
    files = collections.defaultdict(list)
    for r in rows:
        if r["kind"] != "retail-moment":
            continue
        cur = planner.current(r)
        look = dict(name=r["name"], mode="keep")
        if r["retained"] and cur not in planner.changed:
            pass            # the slot already holds this very person (the retail slot's name is his)
        elif r["want"] in ("own-retail", "own-2026"):
            if cur != r["photo"]:
                look = dict(name=r["name"], mode="retail", retail=r["retail"])
        elif r["want"] == "relocate":
            look = dict(name=r["name"], mode="relocate", retail=r["retail"])
        elif r["want"] == "generic" and cur in planner.custom:
            look = dict(name=r["name"], mode="generic")
        if r.get("tier") and look["mode"] != "keep" and r["tier"] != "name+year":
            look["match"] = r["tier"]
        files[r["file"]].append((r["slot"], look))
    return {"schema": 1,
            "about": "Per-slot head decisions for the 35 retail-moment rosters (tools/b77/fs1_scans_plan.py). keep = the "
                     "retail record is untouched; retail = the person's own retail record (photo id, whole skin value, "
                     "face, dreads); relocate = the same, the head id being the unused one of nfl2k5_moment_scans; "
                     "generic = no scan exists and the slot held another person's head, so it takes the no-photo id "
                     "(7100 + slot).",
            "files": {fn: [look for _s, look in sorted(v, key=lambda t: t[0])] for fn, v in sorted(files.items())}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retail", type=Path, required=True)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--write", action="store_true", help="copy the generated data into data/")
    a = ap.parse_args(argv)
    planner = Planner(a.retail, a.base)
    a.out.mkdir(parents=True, exist_ok=True)
    rows = planner.plan()
    print(collections.Counter((r["kind"], r["want"]) for r in rows))
    moment_files = {r["file"] for r in rows if r["kind"] == "retail-moment"}
    scans, stats = planner.relocation(rows, moment_files)
    print("relocation", stats, collections.Counter(s["shape"] for s in scans))
    dump_json(a.out / "plan_rows.json", rows)
    dump_json(a.out / "nfl2k5_moment_scans.json",
              {"schema": ms.SCHEMA,
               "about": "retail id -> unused id that holds a copy of the retail scan (retail head f/h/n, portrait, and the "
                        "head shape when the spans are the same size). Generated by tools/b77/fs1_scans_plan.py; applied by "
                        "mod_editor/core/nfl2k5_moment_scans.py.",
               "scans": scans})
    updates, changes = appearance_updates(planner, rows)
    print("appearance changes", dict(changes))
    docs = {MORE_APPEARANCE_JSON: updates[MORE_APPEARANCE_JSON], CLASSIC_APPEARANCE_JSON: updates[CLASSIC_APPEARANCE_JSON],
            RETAIL_APPEARANCE_JSON: retail_moment_doc(planner, rows), ms.DATA: json.loads((a.out / "nfl2k5_moment_scans.json").read_text())}
    for path, doc in docs.items():
        dump_json(a.out / (path.parent.name + "__" + path.name), doc)
        if a.write:
            dump_json(path, doc)
    print("done", len(rows), "written to data/" if a.write else "(review only)")


if __name__ == "__main__":
    main()
