#!/usr/bin/env python3
"""Execute real native VIP replay and ordinary selection with declared fixtures.

No VIP selector, RNG, accessor, or compatibility function is mocked. This is
an offline component experiment, not full-game acceptance. The existing World
supplies roster/player/kicker environmental inputs. The retail comparison uses
the real retail coach record, native statistics initializer and game-plan code.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_scoring as s, nfl2k5_playbook_inspector as ip, nfl2k5_vip as vip
from mod_editor.core.mod_build import _xbe_bytes
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
from pb.scoring_selectors import World


def settings(index):
    if index == 18:
        return dict(down=1, distance=10, yard=1, margin=0, quarter=2, seconds=300)
    if index == 19:
        return dict(down=1, distance=3, yard=97, margin=0, quarter=2, seconds=300)
    group, score = divmod(index, 3)
    distance, urgent = divmod(group, 2)
    down, yards = ((1, 10), (3, 1), (3, 10))[distance]
    return dict(down=down, distance=yards, yard=50, margin=(7, -7, 0)[score],
                quarter=4 if score == 0 else 2, seconds=60 if urgent else 300)


def seed(world, value):
    rng = random.Random(value)
    world.put(0xE5FCA0, 54)
    world.put(0xE5FCA4, 23)
    for i in range(110):
        world.put(0xE5FCA8 + i * 4, rng.getrandbits(32))
    return rng


def classify(world, formation, play):
    fi, frem = divmod(formation - s.BOOK - ip.FORMATION_BASE, ip.FORMATION_SIZE)
    pi, prem = divmod(play - s.BOOK - ip.PLAY_BASE, ip.PLAY_SIZE)
    if frem or prem or not 0 <= fi < len(world.book.formations) or not 0 <= pi < len(world.book.plays):
        raise ValueError(f"Out-of-book choice {formation:#x}/{play:#x}")
    flags = world.book.plays[pi].flags_or_id
    run, passed = bool(flags & 0x8000), bool(flags & 0x2000)
    if world.book.plays[pi].family_id != 0 or run == passed:
        return "special", fi, pi
    gun = world.get(formation + 4) & 0xC0000 == 0x80000
    return ("pass" if passed else "run") + ("_gun" if gun else "_under"), fi, pi


def bind(world, payload, book_index):
    world.m.mem_write(0xBDFCF0, payload[:vip.PRIMARY_SIZE])
    world.m.mem_write(0xBC6E40, payload[vip.PRIMARY_SIZE:])
    context = world.call(0x142370, ecx=0)
    root = s.SOURCE + 0x1F000
    labels = root + 0x400
    world.put(0xB72918, root)
    world.put(root + 0x48, 36)
    world.put(root + 0x4C, labels)
    world.put(0xBA04B4, context)
    world.put(0xE5FF80, 4)
    world.put(s.TEAM + 0x30, 0)
    world.call(0xF6E60, eax=s.TEAM, args=(1, labels + book_index * 8, 1))
    assert world.get(context + 0x38) == 2 and world.get(context + 0x10) == 1
    world.call(0xF7A90, edi=s.TEAM, ecx=s.TEAM)
    assert world.get(s.META + 0x100) == context + 0x20B8
    return context


def native_vip(xbe, book, payload, receipt, samples, *, automatic=None):
    if automatic is None:
        w = World(xbe)
        w.load(book)
        context = bind(w, payload, receipt["book_index"])
    else:
        w, context = automatic(xbe, book, receipt)
    checked = set()
    for row in receipt["pools"]:
        for c in row["choices"]:
            pair = c["formation"], c["play"]
            if pair not in checked:
                fv = s.BOOK + ip.FORMATION_BASE + pair[0] * ip.FORMATION_SIZE
                pv = s.BOOK + ip.PLAY_BASE + pair[1] * ip.PLAY_SIZE
                if not w.call(0xE1440, ecx=s.BOOK, edx=pv, args=(fv,)):
                    raise ValueError(f"Native compatibility rejected {pair}")
                checked.add(pair)
    rows = []
    for index, source in enumerate(receipt["pools"]):
        counts = Counter()
        fallbacks = 0
        feature_totals = [0.0] * (2 * len(vip.FEATURE_KEYS))
        choices = {(c["formation"], c["play"], bool(c["flipped"])): vip.Choice(**c) for c in source["choices"]}
        rng = seed(w, 20261012 + index)
        # The previous call is carried between draws, exercising exclusion.
        w.put(s.META + 0x118, 0)
        w.put(s.META + 0x11C, 0)
        for sample in range(samples):
            w.configure(**settings(index), direction=1 if sample % 2 else -1)
            w.fput(0xBF1484, rng.random())
            w.call(0x1B2D40, ecx=s.TEAM)
            out = s.SOURCE + 0x19100
            w.m.mem_write(out, bytes(20))
            w.call(0x17F1D0, ecx=out, edx=out + 4, args=(out + 8, out + 12, out + 16))
            fv, pv = struct.unpack("<II", w.m.mem_read(out, 8))
            category, fi, pi = classify(w, fv, pv)
            counts[category] += 1
            flipped = bool(w.get(out + 12))
            choice = choices[fi, pi, flipped]
            terms = vip._feature_terms(choice)
            feature_totals = [a + b for a, b in zip(feature_totals, terms)]
            # Independently verify the native run-lane classifier in both
            # orientations; this is not inferred from the display name.
            if sample < 64 and choice.run_lane is not None:
                lane = w.call(0x281300, ecx=pv, edx=2 if flipped else 0)
                if vip.RUN_LANES[lane] != choice.run_lane:
                    raise ValueError(f"Native lane mismatch {fi}/{pi}/{flipped}: {lane} vs {choice.run_lane}")
            record = w.get(context + 0xDE8)
            pool = context + vip.OFFENSE + index * vip.POOL_SIZE
            if not pool + 2 <= record < pool + vip.POOL_SIZE:
                fallbacks += 1
            w.put(s.META + 0x118, fv)
            w.put(s.META + 0x11C, pv)
        observed_pass = sum(n for k, n in counts.items() if k.startswith("pass")) / samples
        observed_gun = sum(n for k, n in counts.items() if k.endswith("_gun")) / samples
        target = source["target"]["joint"]
        target_pass = target["pass_under"] + target["pass_gun"]
        target_gun = target["pass_gun"] + target["run_gun"]
        checks = dict(no_fallback=fallbacks == 0,
                      pass_quantized=abs(observed_pass - source["quantized_pass"]) <= .07,
                      gun_quantized=abs(observed_gun - source["quantized_shotgun"]) <= .07,
                      pass_target=abs(observed_pass - target_pass) <= .19,
                      gun_target=abs(observed_gun - target_gun) <= .19)
        width = len(vip.FEATURE_KEYS)
        features = [dict(feature=k, part=sub, numerator=feature_totals[i], denominator=feature_totals[i + width],
                         observed=feature_totals[i] / feature_totals[i + width] if feature_totals[i + width] else None)
                    for i, (k, sub) in enumerate(vip.FEATURE_KEYS)]
        rows.append(dict(index=index, settings=settings(index), samples=samples, counts=dict(counts), features=features,
                         fallback_calls=fallbacks, observed_pass=observed_pass, observed_shotgun=observed_gun,
                         target_pass=target_pass, target_shotgun=target_gun,
                         quantized_pass=source["quantized_pass"], quantized_shotgun=source["quantized_shotgun"],
                         raw_observations=source["target"]["observations"], sparse_fallback=source["target"]["fallback"],
                         checks=checks, passed=all(checks.values())))
    aggregate = []
    total = sum(row["target"].get("observations", {}).get("calls", 0) for row in receipt["pools"])
    for i, (key, sub) in enumerate(vip.FEATURE_KEYS):
        num = den = 0.0
        for row, source in zip(rows, receipt["pools"]):
            weight = source["target"].get("observations", {}).get("calls", 0) / total if total else 0
            num += weight * row["features"][i]["numerator"] / samples
            den += weight * row["features"][i]["denominator"] / samples
        fit = receipt["secondary_fit"]["features"][i]
        observed = num / den if den else None
        aggregate.append(dict(feature=key, part=sub, observed=observed, target=fit["target"], modeled=fit["modeled"],
                              quantized_match=observed is None or abs(observed - fit["modeled"]) <= .07,
                              target_proxy_match=observed is not None and fit["target"] is not None and
                              abs(observed - fit["target"]) <= .15))
    return dict(compatible_pairs=len(checked), rows=rows, secondary_weighted=aggregate,
                passed=all(r["passed"] for r in rows) and all(f["quantized_match"] for f in aggregate))


def retail_control(xbe, book, coach, samples, *, world_factory=World):
    w = world_factory(xbe)
    w.load(book)
    fallback_visits = []
    w.m.hook_add(w.ucmod.UC_HOOK_CODE, lambda *_: fallback_visits.append(1),
                 begin=0x20B7B1, end=0x20B7B1)
    address = s.SOURCE + 0x1D000
    w.m.mem_write(address, coach)
    w.call(0x2818D0, ecx=s.META + 0x800, edx=address)
    rows = []
    for index in range(20):
        rng = seed(w, 20261012 + index)
        counts = Counter()
        nullable = []
        fallback_start = len(fallback_visits)
        for sample in range(samples):
            w.configure(**settings(index))
            w.fput(0xBF1484, rng.random())
            w.call(0x281D90)
            w.m.mem_write(0xBF16F8, bytes(w.m.mem_read(0xC5D4B0, 4)))
            out = s.SOURCE + 0x19100
            w.m.mem_write(out, bytes(16))
            before_fallback = len(fallback_visits)
            w.call(0x20B670, ecx=s.TEAM, edx=out)
            _, fv, pv, _ = struct.unpack("<4I", w.m.mem_read(out, 16))
            if not fv:
                # Native 20B670 may exhaust four formation searches, then
                # choose a fallback play at 20B7B1 without a formation.
                # Keep that observed control outcome; never invent a form
                # or silently discard the draw from rate denominators.
                pi, remainder = divmod(pv - s.BOOK - ip.PLAY_BASE, ip.PLAY_SIZE)
                if len(fallback_visits) == before_fallback or remainder or not 0 <= pi < len(w.book.plays):
                    raise ValueError(f"Invalid native control fallback {fv:#x}/{pv:#x}")
                counts["no_formation"] += 1
                nullable.append(dict(sample=sample, play=pi, native_fallback=True))
                continue
            category, _, _ = classify(w, fv, pv)
            counts[category] += 1
        rows.append(dict(index=index, samples=samples, counts=dict(counts),
                         native_fallback_calls=len(fallback_visits) - fallback_start,
                         no_formation_draws=nullable,
                         rate_denominator="all draws, including explicitly counted no-formation fallback outcomes",
                         pass_rate=sum(n for k, n in counts.items() if k.startswith("pass")) / samples,
                         shotgun_rate=sum(n for k, n in counts.items() if k.endswith("_gun")) / samples))
    return rows


def native_defense(xbe, book, payload, receipt, samples, *, automatic=None):
    if automatic is None:
        w = World(xbe)
        w.load(book)
        context = bind(w, payload, receipt["book_index"])
    else:
        w, context = automatic(xbe, book, receipt)
    w.call(0xF7A90, ecx=w.defense, edi=w.defense)
    categories = {}
    for form in w.book.formations:
        fv = s.BOOK + ip.FORMATION_BASE + form.index * ip.FORMATION_SIZE
        if (w.get(fv + 4) >> 8) & 63 < 4:
            cv = w.call(0xE1A80, ecx=s.BOOK, edx=fv)
            categories.setdefault(w.get(cv + 4) & 63, cv)
    rows = []
    # These are opponent personnel groups, not one mandatory category per
    # book. Some current books lack category 0 or 3 while retaining another
    # legal category in the same native group. Preserve the original fixture
    # preference when present and choose an available peer otherwise.
    group_categories = [next((k for k in group if k in categories), None)
                        for group in ((0, 1, 2), (3, 4), (6, 5, 7), (9, 8, 10))]
    if any(k is None for k in group_categories):
        raise ValueError(f"Book cannot supply all opponent category fixtures: {sorted(categories)}")
    for index, source in enumerate(receipt["defense_pools"]):
        distance_bin, known = divmod(index, 5)
        state = dict(down=1, distance=(1, 10, 20)[distance_bin], yard=50, margin=0, quarter=2, seconds=300)
        counts = Counter()
        selected = {(c["formation"], c["front"], c["coverage"]): c for c in source["choices"]}
        rng = seed(w, 779000 + index)
        w.put(s.META + 0x318, 0)
        w.put(s.META + 0x320, 0)
        for draw in range(samples):
            w.configure(**state)
            w.put(s.META + 0x124, 8 if known else 0)
            if known:
                w.put(s.META + 0x104, categories[group_categories[known - 1]])
            pool = w.call(0xF7450, ecx=0)
            if pool != context + 0xA3C + index * 62:
                raise ValueError(f"Wrong native defensive pool {index}: {pool:#x}")
            w.fput(0xBF1484, rng.random())
            out = s.SOURCE + 0x19100
            w.m.mem_write(out, bytes(28))
            w.call(0x17DFC0, ecx=out, edx=out + 4, args=tuple(out + n for n in (8, 12, 16, 20, 24)))
            fv, front, cover = struct.unpack("<3I", w.m.mem_read(out, 12))
            fi = (fv - s.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE
            pi = (front - s.BOOK - ip.PLAY_BASE) // ip.PLAY_SIZE
            ci = (cover - s.BOOK - ip.PLAY_BASE) // ip.PLAY_SIZE
            choice = selected[fi, pi, ci]
            record = w.get(context + 0xDEC)
            counts["fallback"] += not pool + 2 <= record < pool + 62
            counts["man"] += choice["man"]
            counts["rush_five_plus"] += choice["rushers"] >= 5
            w.put(s.META + 0x318, fv)
            w.put(s.META + 0x320, cover)
        features = {}
        for key in ("man", "rush_five_plus"):
            target = source["targets"][key]["rate"] if source["targets"].get(key) else None
            observed = counts[key] / samples
            features[key] = dict(observed=observed, target=target, quantized=source["quantized"][key],
                                 quantized_match=abs(observed - source["quantized"][key]) <= .08,
                                 target_match=target is None or abs(observed - target) <= .20)
        rows.append(dict(index=index, settings=state, opponent_known_group=known, samples=samples,
                         opponent_category=group_categories[known - 1] if known else None,
                         counts=dict(counts), features=features,
                         passed=counts["fallback"] == 0 and all(f["quantized_match"] and f["target_match"] for f in features.values())))
    return dict(rows=rows, passed=all(r["passed"] for r in rows))


def native_decisions(xbe, book, payload, receipt, samples, tempo_samples, *, automatic=None):
    if automatic is None:
        w = World(xbe)
        w.load(book)
        context = bind(w, payload, receipt["book_index"])
    else:
        w, context = automatic(xbe, book, receipt)
    rows = {}
    states = {"fourth_down": dict(down=4, distance=1, yard=25, margin=0, quarter=2, seconds=300),
              "two_point": dict(down=1, distance=2, yard=98, margin=0, quarter=2, seconds=300, phase=3)}
    for key, state in states.items():
        spec = receipt["decisions"][key]
        if not spec["written"]:
            rows[key] = dict(passed=False, reason="No derived decision counter")
            continue
        counts = Counter()
        rng = seed(w, 123456)
        for draw in range(samples):
            w.configure(**state)
            w.fput(0xBF1484, rng.random())
            w.call(0x1B2D40, ecx=s.TEAM)
            out = s.SOURCE + 0x19100
            w.m.mem_write(out, bytes(20))
            w.call(0x17F1D0, ecx=out, edx=out + 4, args=(out + 8, out + 12, out + 16))
            fv, pv = struct.unpack("<II", w.m.mem_read(out, 8))
            category, _, _ = classify(w, fv, pv)
            counts["special" if category == "special" else "go"] += 1
            counts["vip"] += bool(w.get(context + 0xDE8))
        observed = counts["go"] / samples
        rows[key] = dict(settings=state, samples=samples, counts=dict(counts), observed=observed,
                         target=spec["observations"]["rate"], native_roll=spec["native_roll"],
                         passed=abs(observed - spec["observations"]["rate"]) <= .05)
    spec = receipt["decisions"]["no_huddle"]
    w.configure(down=1, distance=10, yard=50, margin=0, quarter=1, seconds=300)
    category = s.SOURCE + 0x1D400
    w.put(category + 4, 3)
    w.put(s.META + 0x104, category)
    w.fput(s.STATE + 0x510, 300)
    w.put(0xC5D50C, 0)
    w.put(0xC5D510, 0)
    seed(w, 5551212)
    if spec["written"]:
        observed = sum(bool(w.call(0x281800, ecx=s.TEAM)) for _ in range(tempo_samples)) / tempo_samples
        rows["no_huddle"] = dict(samples=tempo_samples, observed=observed, target=spec["observations"]["rate"],
                                  modeled_continuous_eligible_rate=spec["continuous_eligible_rate"],
                                  passed=abs(observed - spec["observations"]["rate"]) <= .015,
                                  scope="Continuous eligible first-half stream; native burst state persists")
    else:
        rows["no_huddle"] = dict(passed=False, reason="No derived tempo counter")
    return dict(rows=rows, passed=all(r["passed"] for r in rows.values()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exports", type=Path)
    ap.add_argument("--automatic", action="store_true", help="prove native automatic game setup without a selected user VIP")
    ap.add_argument("--profiles", type=Path, help="prepared automatic PLAY resources and compiler receipts")
    ap.add_argument("--baseline-xbe", type=Path, help="same mod executable without automatic coach AI")
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--xbe", type=Path, help="exact candidate executable, including the VIP-aware policy")
    ap.add_argument("--retail-image", type=Path, required=True)
    ap.add_argument("--retail-xbe", type=Path, required=True)
    ap.add_argument("--samples", type=int, default=1000)
    ap.add_argument("--control-samples", type=int, default=100)
    ap.add_argument("--same-book-control-samples", type=int, default=100)
    ap.add_argument("--defense-samples", type=int, default=1000)
    ap.add_argument("--decision-samples", type=int, default=1000)
    ap.add_argument("--tempo-samples", type=int, default=10000)
    ap.add_argument("--team", action="append")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists() or min(args.samples, args.control_samples, args.same_book_control_samples,
                               args.defense_samples, args.decision_samples, args.tempo_samples) < 1:
        ap.error("Output must be new; sample counts must be positive")
    if args.automatic:
        if args.profiles is None or args.baseline_xbe is None:
            ap.error("--automatic requires --profiles and --baseline-xbe")
        from tools.b77.vp2_native import run
        return run(args)
    if args.exports is None:
        ap.error("manual VIP verification requires --exports")
    xbe, retail_xbe = _xbe_bytes(args.xbe or args.image), args.retail_xbe.read_bytes()
    specs = json.loads((ROOT / "data/vip/coach_sources_2026.json").read_text())
    result = dict(schema="nfl2k5_vip_native_replay/v2", status="RUNNING", xbe_sha256=hashlib.sha256(xbe).hexdigest(),
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  retail_xbe_sha256=hashlib.sha256(retail_xbe).hexdigest(), samples=args.samples,
                  tolerance=dict(offense_target=.19, offense_quantized=.07, secondary_proxy_target=.15,
                                 defense_target=.20, defense_quantized=.08, optional_decision=.05, continuous_tempo=.015),
                  scope="20 offense pools, 15 defense pools, optional fourth/2pt and eligible tempo; synthetic clock/player state",
                  retail_control="Native retail selector, original book and coach, 2818D0 statistics and 281D90 game plan; all 20 offense situations",
                  same_book_control="Exact candidate executable/book, no active VIP, original coach statistics; identical synthetic situations",
                  runtime_witness=False, teams={})
    start = time.monotonic()
    with OuterImage(args.image) as arc, OuterImage(args.retail_image) as stock:
        roster = rr.RosterDocument(stock.read_entry(5)[32:])
        for spec in specs:
            team = spec["team"]
            if args.team and team not in args.team:
                continue
            receipt = json.loads((args.exports / (team + ".json")).read_text())
            payload = vip.load_signed(args.exports / team, xbe).payload
            book = arc.read_entry(BOOK_ENTRIES[spec["archive_book"]])
            assert hashlib.sha256(book).hexdigest() == receipt["book_sha256"]
            assert hashlib.sha256(payload).hexdigest() == receipt["save_sha256"]
            assert receipt.get("executable", {}).get("xbe_sha256", result["xbe_sha256"]) == result["xbe_sha256"]
            try:
                print(team, "offense", flush=True)
                entry = native_vip(xbe, book, payload, receipt, args.samples)
                print(team, "defense", flush=True)
                entry["defense"] = native_defense(xbe, book, payload, receipt, args.defense_samples)
                print(team, "decisions", flush=True)
                entry["decisions"] = native_decisions(xbe, book, payload, receipt, args.decision_samples, args.tempo_samples)
                coach_offset = roster.teams[spec["native_book_index"]].coach_offset
                coach = bytes(roster.body[coach_offset:coach_offset + 0xA8])
                print(team, "retail comparison", flush=True)
                entry["retail_control"] = retail_control(retail_xbe, stock.read_entry(BOOK_ENTRIES[spec["archive_book"]]), coach, args.control_samples)
                print(team, "same-book comparison", flush=True)
                entry["same_book_control"] = retail_control(xbe, book, coach, args.same_book_control_samples)
                entry["passed"] &= entry["defense"]["passed"] and entry["decisions"]["passed"]
                entry["candidate"] = dict(save_sha256=receipt["save_sha256"], book_sha256=receipt["book_sha256"],
                                           receipt_sha256=hashlib.sha256((args.exports / (team + ".json")).read_bytes()).hexdigest())
            except Exception as exc:
                entry = dict(passed=False, error=f"{type(exc).__name__}: {exc}")
            result["teams"][team] = entry
            print(team, "PASS" if entry["passed"] else "FAIL", entry.get("error", ""), flush=True)
            result["elapsed_seconds"] = time.monotonic() - start
            args.out.write_text(json.dumps(result, indent=1) + "\n")
    result["status"] = "PASS" if result["teams"] and all(e["passed"] for e in result["teams"].values()) else "FAIL"
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
