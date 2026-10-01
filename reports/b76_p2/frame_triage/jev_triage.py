#!/home/noah/ai-stack/jev/.venv/bin/python
"""p2 Jev triage: route every 2026 frame (764 MNF highlight stills + 3,129 OBS stills) to an r2 presentation target.

Code measures (features.jsonl, stinger_color.json, band.json); Jev judges the text state; the routed frames are then
read by eye on contact sheets. Journal: jev_journal.jsonl (one line per frame: state, answers)."""
import json, sys
sys.path.insert(0, "/home/noah/ai-stack/jev/recipes")
import jevlib as J
rows = [json.loads(l) for l in open("features.jsonl")]
sc = json.load(open("stinger_color.json")); bd = json.load(open("band.json"))
def bucket(v, cuts, names):
    for c, n in zip(cuts, names):
        if v is not None and v < c:
            return n
    return names[-1]
def share(v):
    return bucket(v, (0.02, 0.1, 0.3), ("none", "a little", "some", "much"))
states = []
for r in rows:
    k = r["key"]
    st = {
        "frame": k,
        "source": "highlights video" if r["src"] == "mnf" else "off-air recording",
        "scorebug_bar": "visible" if (r["bar_ncc"] or 0) >= 0.35 else "not visible",
        "espn_mnf_corner_watermark": "visible" if r["watermark_ncc"] >= 0.6 else "not visible",
        "red_shield_emblem_match": bucket(sc[k]["stinger_color"], (0.4, 0.5), ("no", "weak", "strong")),
        "white_letter_band_match": bucket(bd[k]["band"], (0.6, 0.7), ("no", "weak", "strong")),
        "grass_green_share": share(r["green"]), "saturated_red_share": share(r["red"]),
        "navy_share": share(r["navy"]), "near_black_share": share(r["black"]), "near_white_share": share(r["white"]),
        "flat_graphic_share": bucket(r["flat"], (0.15, 0.4, 0.7), ("low", "medium", "high", "very high")),
        "brightness": bucket(r["luma"], (50, 110, 170), ("dark", "medium", "bright", "very bright")),
        "ocr_words": " ".join(r["ocr"] or [])[:600] if r.get("ocr") else "",
    }
    states.append(st)
Q = {
    "target": J.choice(
        "The state describes one still from a 2026 ESPN Monday Night Football broadcast using measured facts only "
        "(no pixels). Which kind of broadcast moment does it most likely show?",
        {"replay_transition_emblem": "the red ESPN MNF shield emblem that flies in before an instant replay "
                                     "(strong red shield emblem match)",
         "live_play_or_replay_footage": "game action or its replay on the field (much grass green)",
         "sideline_or_crowd": "players, coaches, officials or fans off the play, with or without the scorebug bar",
         "score_board_or_card": "a graphic that shows the score: an end of quarter, halftime or final card, a corner "
                                "score box, or a postgame board (score and quarter words in the text)",
         "bumper_or_break": "a show bumper or a going to or coming back from break graphic or beauty shot "
                            "(MONDAY NIGHT FOOTBALL, sponsor, COMING UP, network words)",
         "stat_or_lower_third": "a player, team or stat graphic, a lower third or a name strip",
         "coin_toss": "the coin toss at midfield or a coin toss graphic",
         "studio_or_desk": "a studio set or an announcers desk",
         "commercial_or_app_screen": "an advertisement, or the streaming app's own screen or pause overlay",
         "other": "anything else, or the facts are not enough"}),
    "graphic": J.noul("Does a broadcast graphic, emblem, board or studio set (not only live action) fill a clear part of this frame?"),
}
out = J.batch(states, Q, tool="b76_p2_frame_triage")
from collections import Counter
cnt = Counter()
with open("jev_journal.jsonl", "w") as f:
    for st, ans in zip(states, out):
        t, c = J.pick(ans, "target")
        cnt[t] += 1
        f.write(json.dumps(dict(state=st, answers=ans, target=t, confidence=round(c, 3),
                                graphic=round(J.p(ans, "graphic"), 3))) + "\n")
print("frames", len(states), dict(cnt))
