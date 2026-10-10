"""Emit docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json (the sourced data file for CPU decision level Modern 2).

Run: venv/bin/python -I build_sources_json.py <nfl4th_joined.parquet> <out.json>
Reproduces every table in the file from (a) the ESPN Analytics chart boundaries measured with digitize_espn4th.py,
(b) the nfl4th pre-computed decisions joined to nflverse play-by-play (load_nfl4th.py) and (c) the readings of the
ESPN two-point chart and overtime article recorded below. Deterministic: no random numbers.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_tables as bt  # noqa: E402

SOURCES = [
    dict(id="espn_cheat_sheet", title="NFL game management cheat sheet: Guide to fourth downs and 2-point conversions",
         authors=["Seth Walder (ESPN Analytics)"], publisher="ESPN", published="2022-01-15", updated="2023-01-14",
         url="https://www.espn.com/nfl/story/_/id/33059528",
         model="ESPN win probability model created by Brian Burke (score, time, distance, yard line, timeouts, pregame win probability, offense/defense strength)",
         images=["4th Down Recommendation, Typical situations (Source: ESPN Analytics): go / FG / punt regions by yards to end zone and yards to go 1..10",
                 "Breakeven Chances to Convert 2-Point Try (Source: ESPN Analytics): margin after the touchdown -15..+14 against minutes remaining; dashed line 48%"],
         used_for="base 4th-down go limits (typical situations) and the two-point thresholds by margin and clock"),
    dict(id="espn_ot_2025", title="New NFL overtime rules: Big questions on coin flip strategy", authors=["Ben Solak", "Seth Walder"],
         publisher="ESPN", published="2025-09-29", url="https://www.espn.com/nfl/story/_/id/46150828/nfl-new-regular-season-ot-rules-coin-toss-two-point-conversion",
         quotes=["If the first team scored a touchdown, the second team 'must go for any and all fourth downs.'",
                 "If the first team didn't score, the second team can kick a short field goal, even on fourth-and-1.",
                 "First team scores a touchdown: it should kick the PAT. Second team scores a touchdown: it should go for two."],
         used_for="overtime branch (second team facing a first-drive touchdown, two-point after the second team's touchdown, first team kicks the PAT)"),
    dict(id="nfl4th", title="nfl4th: Functions to Calculate Optimal Fourth Down Decisions in the National Football League (go-for-it, punt and field-goal models)",
         authors=["Ben Baldwin", "Sebastian Carl"], publisher="nflverse / CRAN", version="1.0.7 (2026-03-04) data release nfl4th_infrastructure",
         url="https://github.com/nflverse/nfl4th", data_url="https://github.com/nflverse/nfl4th/releases/download/nfl4th_infrastructure/pre_computed_go_boost.rds",
         explainer="https://www.nytimes.com/athletic/2144214/2020/10/28/nfl-fourth-down-decisions-the-math-behind-the-leagues-new-aggressiveness/",
         used_for="score and clock shifts of the go limit (model recommendation go_boost > 0 on 49,416 real fourth downs, 2014-2025), and the late-lead field goal rule"),
    dict(id="nflverse_pbp", title="nflverse play-by-play 2014-2025 (nflfastR)", publisher="nflverse", url="https://github.com/nflverse/nflverse-data/releases/tag/pbp",
         used_for="game state (yard line, distance, score, clock, win probability) joined to the nfl4th decisions"),
    dict(id="nyt_4th_bot", title="The New York Times 4th Down Bot (Brian Burke, Kevin Quealy, Josh Katz)", publisher="The New York Times", published="2013-12 / 2014-09 / 2015-10",
         url="https://www.niemanlab.org/2013/12/yes-the-vikings-should-have-gone-for-it-on-4th-down-and-a-new-york-times-robot-knows-why/",
         used_for="cross-check only: expected points through most of the game, win probability in the last ten minutes (the same split the shifts reproduce); no numbers taken"),
    dict(id="nfl_ngs", title="Next Gen Stats Decision Guide (NFL and AWS)", publisher="NFL.com", url="https://www.nfl.com/news/introducing-the-next-gen-stats-decision-guide-a-new-analytics-tool-for-fourth-do",
         used_for="cross-check only: win-probability criterion (a call is optimal when it adds win probability); no numbers taken"),
    dict(id="nfl_rule16", title="2026 NFL Rulebook, Rule 16 Overtime Procedures (as quoted in OVERTIME_2026-09-03.md)", publisher="NFL",
         url="https://static.www.nfl.com/image/upload/fl_attachment/league/tqivdkzt9mu6wdgsh1ku.pdf",
         used_for="the overtime rules the nfl2k5_overtime owner implements (both teams possess unless the kicking team scores a safety; then next score wins)"),
]

TWO_POINT = {  # margin after the touchdown (offense minus defense) -> (threshold seconds of game left, reading)
    -15: (1800, "ESPN text: go for two in the second half; chart: below the 48% line from about minute 28"),
    -14: (0, "chart: rises above the line late; kick"),
    -13: (0, "ESPN text: late can be advisable, chart noisy around the line; kick (not clear enough to ship)"),
    -12: (0, "ESPN text: consider very late, chart noisy; kick"),
    -11: (900, "ESPN text: go from about the start of the fourth quarter"),
    -10: (540, "ESPN text: go with roughly 8 to 9 minutes left; chart below the line from about minute 12"),
    -9: (0, "ESPN text: small advantage late and the model does not always agree; kick"),
    -8: (1350, "ESPN text: go from roughly midway through the third quarter; chart below the line from about minute 23"),
    -7: (0, "chart: at the line then rises to 95% late; kick"),
    -6: (0, "chart: at or above the line; kick"),
    -5: (1800, "ESPN text: either in the first half, go in the second half; chart below the line from about minute 29"),
    -4: (480, "ESPN text: go with 8 to 9 minutes or less in the fourth quarter (chart at the line until about minute 8)"),
    -3: (0, "chart: above the line from minute 25 on; kick"),
    -2: (-1, "ESPN text: either option, going for two should not be criticised (chart below the line in the second half); retail already goes at any time, kept"),
    -1: (20, "ESPN text: kick the PAT except in the final 15 to 20 seconds depending on timeouts"),
    0: (0, "chart: at the line then above; kick"),
    1: (1800, "ESPN text: in the second half go for two to be up a field goal; chart below the line from about minute 28"),
    2: (0, "chart: wanders around the line; kick"),
    3: (0, "chart: above the line late; kick"),
    4: (300, "ESPN text: in the final few minutes going for two is usually better; chart falls below the line in the last ten minutes"),
    5: (1800, "ESPN text: go for two in the second half to be up a touchdown; chart at or below the line from minute 17"),
    6: (0, "chart: above the line; kick"),
    7: (0, "ESPN text: kicking the PAT is logical; kick"),
    8: (0, "chart: above the line late; kick"),
    9: (0, "chart: above the line late; kick"),
    10: (0, "chart: spikes above the line at the end; kick"),
    11: (0, "chart: noisy around the line; kick"),
    12: (600, "ESPN text: try to go up two touchdowns later in the game; chart below the line from about minute 10"),
    13: (0, "chart: above the line; kick"),
    14: (0, "chart: at or above the line; kick"),
}

def main():
    src, out = sys.argv[1], Path(sys.argv[2])
    # reuse the table builder (fourth-down limits, shifts, diagnostics)
    tables_path = out.with_suffix(".tables_tmp.json")
    sys.argv = ["build_tables.py", src, str(tables_path)]
    bt.main()
    t = json.loads(tables_path.read_text()); tables_path.unlink()
    # sensitivity: the narrower win-probability window (close to the Next Gen Stats rule of counting spots with at least 10% win
    # probability) must give nearly the same shifts
    import os
    os.environ["WP_LO"], os.environ["WP_HI"] = "0.10", "0.90"
    sys.argv = ["build_tables.py", src, str(tables_path)]
    bt.main()
    narrow = json.loads(tables_path.read_text()); tables_path.unlink()
    os.environ.pop("WP_LO"); os.environ.pop("WP_HI")
    import numpy as np
    a, b = np.array(t["shift_final"]), np.array(narrow["shift_final"])
    mask = (a != 100) & (b != 100)
    diff = np.abs(a - b)[mask]
    sensitivity = dict(window="0.10 < win probability < 0.90", cells_compared=int(mask.sum()), identical=int((diff == 0).sum()),
                       within_one_yard=int((diff <= 1).sum()), max_difference=int(diff.max()), validation=narrow["diagnostics"])
    thr10 = []
    for m in range(-16, 17):
        s, _ = TWO_POINT.get(m, (0, "outside the chart: never"))
        thr10.append(255 if s < 0 else s // 10)
        assert s < 0 or s % 10 == 0
    shift_flat = [v for t_ in t["shift_final"] for m_ in t_ for v in m_]   # [t][m][r] row-major, r in P (own<40), M, F
    limit81 = t["limit_x_shipped"][:81]
    doc = dict(
        schema="softdrink_cpu_decisions_modern2/v1", level="modern2", accessed="2026-10-07", job="b77 p9 (sonnet-5.5)",
        generated_by="tools/b77/p9_research/build_sources_json.py (+ build_tables.py, digitize_espn4th.py, load_nfl4th.py)",
        honesty="Thresholds are digitized from published ESPN Analytics charts and derived from the published nfl4th model outputs; the "
                "conversion rates of this game's engine are unmeasured. Nothing here was witnessed in the game.",
        sources=SOURCES,
        fourth_down=dict(
            base="ESPN Analytics '4th Down Recommendation, Typical situations' chart (yards to go 1..10), digitized at the gridline of each distance",
            axis="x = yards to the opponent end zone (0 = goal line); the chart is a step chart whose boundaries sit on whole yards, so each is "
                 "ambiguous by one yard; the shipped windows exclude the boundary yard on both sides (conservative)",
            espn_runs_nominal={str(d): runs for d, runs in bt.ESPN.items()},
            go_windows_nominal=t["espn_windows_nominal"], go_windows_shipped=t["espn_windows_conservative"],
            limit_x_nominal=t["limit_x_nominal"][:101], limit_x_conservative=t["limit_x_conservative"][:101],
            limit_x_shipped_0_to_80=limit81,
            deliberate_deviations=[
                "Own goal line to own 20 (x above 80): the published chart says go on 4th-and-1 from about the own 8 and 4th-and-2 from about the own 11; "
                "the shipped table keeps retail there (as the v0.5 Modern table does) because a failed try deep in the CPU's own end is not "
                "covered by any measurement of this engine's conversion rate. Clock and score shifts still apply there.",
                "Every window edge is pulled in by one yard (chart resolution).",
                "Distances above 10 are outside the chart: only the clock/score shifts (nfl4th) can make the CPU go on 4th-and-11 or longer; capped at 25 yards."],
            typical_dstar_nfl4th=t["typical_dstar_nfl4th"],
            shift=dict(
                method="For every combination of game-clock class t (seconds of game left: >1800, 900-1800, 600-900, 300-600, 120-300, <=120), "
                       "margin class m (<=-9, -8..-4, -3..-1, 0, +1..+3, +4..+8, >=+9, offense minus defense) and field region r (own side of the 40: "
                       "yards to goal >60; middle 40..60; opponent 40 and in), a logistic fit of P(model says go) on yards to go gives the distance "
                       "where it crosses one half; the shift is that distance minus the same region's value in the first half with the score "
                       "within two scores (the regime ESPN calls typical). Cells are smoothed along the clock with weighted isotonic regression "
                       "(direction chosen from the rules: trailing teams need the ball more as time runs out, a team that a field goal ties or "
                       "leads prefers the kick near the goal), rounded to whole yards and limited to -4..+12. The first-half row is zero (typical). "
                       "Trailing by 4 or more with two minutes left: +100 (go on every fourth down).",
                filters="nfl4th decisions with 0.05 < win probability < 0.95 in periods 1-4 (overtime is not modelled by nfl4th); "
                        f"{t['diagnostics']['rows']} fourth downs",
                axes=["t: 0..5", "m: 0..6", "r: 0 own side, 1 middle, 2 opponent 40 and in"],
                raw=t["shift_raw"], n=t["shift_n"], smoothed=t["shift_smoothed"], final=t["shift_final"]),
            validation=t["diagnostics"], sensitivity=sensitivity),
        late_lead_field_goal=dict(
            rule="Fourth quarter, two minutes or less, leading by 1 to 3, 7 or more yards to go and inside the kicker's range minus 5 yards: kick the field goal. "
                 "Retail goes for it there when the FG test says it does not change the score class and the punt test says no.",
            evidence="nfl4th, same state, yards to goal <= 38: 4th-and-7 or more favours the kick in 87% of 23 states (mean go_boost -2.3 points); 4th-and-3 to 6 favours going (+1.3, +0.2)",
            source="nfl4th"),
        two_point=dict(
            margin="score margin after the touchdown, before the try (offense minus defense)", clock="seconds of game left (first half counts the second half)",
            threshold_seconds_by_margin={str(m): v[0] for m, v in TWO_POINT.items()}, readings={str(m): v[1] for m, v in TWO_POINT.items()},
            thr10=thr10, thr10_axis="margin -16..+16 in 10 s units; 0 never, 255 always",
            overtime=dict(
                rule="Overtime with possession tracking: go for two at -2 (retail) and at -1 when both teams have possessed (the second team's touchdown decides the game "
                     "with a try); never after the first team's touchdown (+6, kick the PAT); without possession tracking only -2 (retail).",
                source="espn_ot_2025")),
        overtime=dict(
            state="byte 0xE602A8 of the overtime owner: bit 0 home has possessed, bit 1 away has possessed; period 5 or later",
            rules=[
                "Neither bit set: tracking absent (retail sudden death or an era profile): retail.",
                "Only the team's own bit (the opponent has not possessed): first possession: the typical go table without clock or score terms; "
                "no field goal on downs 1 to 3 (a field goal there only hands the opponent a possession).",
                "Both bits and trailing by 4 or more: go on every fourth down, never punt or kick (a field goal leaves the team behind; the game ends when the possession ends).",
                "Both bits and trailing by 1 to 3: never punt; kick only when the native field goal test says so, otherwise go.",
                "Both bits and tied: sudden death, next score wins: retail."],
            source="espn_ot_2025, nfl_rule16"),
        design_choices_not_from_a_publication=[
            "Late-lead field goal: the 5 yard margin inside the kicker's range is a design value (u-ai's map), not a published number; it keeps the rule off the edge of the native range test. "
            "The 7 yard threshold, the lead of 1 to 3 and the two-minute window come from the nfl4th evidence above (23 states, a small sample).",
            "Overtime: no analytics source publishes a table for the new rules. ESPN only says the second team facing a first-drive touchdown must go for any and all fourth downs; "
            "the rows 'trailing by 4 or more: go every time' and 'no field goal on downs 1 to 3 of the first possession' are arithmetic on the rule text, not published decision tables.",
            "Overtime first possession uses the typical chart with no clock or score terms; u-ai's map suggested 'one band more aggressive', which no source sizes, so it was not adopted.",
            "Overtime trailing by 1 to 3: the native field goal test decides the kick (u-ai's map suggested the kicker's range minus 5 yards), so the guard and the game's own commit-time test always agree.",
            "The last two minutes of the second quarter stay retail (the retail window is kept); the Hail Mary test (0x206DD0) is the game's own and overrides a go decision; kneel never applies on fourth down.",
            "Thresholds are absolute game seconds, like every retail late-game test; a short quarter length is not scaled (not measured).",
            "Yards to go above 25, and own 20 and back in typical states, stay retail."],
        tables=dict(limit_x=limit81, shift=shift_flat, thr10=thr10, shift_axes="index = (t*7 + m)*3 + r"))
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", out, "limit_x", len(limit81), "shift", len(shift_flat), "thr10", len(thr10))

if __name__ == "__main__":
    main()
