#!/usr/bin/env python3
"""b81-uniforms: boot a disc, Play Now with the default matchup (Browns at Ravens), CPU v CPU, and take a still every
few seconds from the Coach Matchup screen through the pregame scenes and the first plays (16:9 frame of the private
display). Optional guest RAM pokes before the game loads (bump strength floats).
Usage: game_route.py TAG SECONDS [--poke VA=HEX ...] [--every S]"""
import sys, json, time
sys.path.insert(0, "/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/emu")
import route
tag = sys.argv[1]; secs = float(sys.argv[2]); pokes = []; every = 2.0; teams = None; expect = None
args = sys.argv[3:]
while args:
    a = args.pop(0)
    if a == "--poke": pokes.append(args.pop(0))
    elif a == "--every": every = float(args.pop(0))
    elif a == "--expect": expect = args.pop(0).upper()
    elif a == "--teams": teams = [args.pop(0).upper(), args.pop(0).upper()]
log = {"tag": tag, "frames": []}
assert route.boot(), "main menu not reached"
f = route.drv({"op": "tap", "k": "A", "wait": 4, "note": "playnow"})["frame"]
t = route.ocr(f)
if "TEAM" not in t:
    f = route.drv({"op": "wait", "s": 3, "note": "playnow2"})["frame"]; t = route.ocr(f)
log["team_select"] = f; log["team_select_text"] = t[:200]
print("team select", f, t[:120], flush=True)
if expect and expect not in t.replace(" ", ""):
    print("ABORT: default matchup is not", expect, flush=True); sys.exit(3)
for p in pokes:                                   # before the game loads its materials
    va, hx = p.split("=")
    before = route.drv({"op": "read", "va": va, "n": len(hx) // 2})
    r = route.drv({"op": "write", "va": va, "hex": hx})
    after = route.drv({"op": "read", "va": va, "n": len(hx) // 2})
    log.setdefault("pokes", []).append({"va": va, "before": before.get("hex"), "after": after.get("hex")})
    print("poke", va, before.get("hex"), "->", after.get("hex"), flush=True)
import subprocess
def read_side(f, side):
    """The club index the name strip of one side shows (None when unreadable). At render scale 2 the strip sits a few
    pixels lower than at scale 1, so several crops are tried and the first that names a listed club wins."""
    x = 300 if side == 0 else 690
    for y, h in ((152, 30), (160, 30), (149, 26), (146, 40), (156, 34)):
        t = subprocess.run(f"convert '{f}' -crop 250x{h}+{x}+{y} +repage -resize 300% -colorspace gray png:- | tesseract stdin stdout --psm 7 2>/dev/null",
                           shell=True, capture_output=True, text=True).stdout.upper().replace("|", "")
        k = route.idx(t)
        if k is not None and not route.offlist(t):
            return k
        if len("".join(c for c in t if c.isalpha())) >= 4:
            seen_text = True
    return -1 if "seen_text" in dir() else None      # -1: a readable strip that is not a listed 2026 club (alumni, classic)
def seek(side, team, limit=140):
    f = route.drv({"op": "shot", "note": "seek"})["frame"]
    want = route.MODERN.index(team); miss = 0
    for _ in range(limit):
        k = read_side(f, side)
        if k == want:
            return True, f
        miss = miss + 1 if k is None else 0
        if miss >= 8:                       # the strip cannot be read: stop pressing rather than wander off
            return False, f
        f = route.drv({"op": "tap", "k": "RT", "n": 1, "hold": 0.15, "gap": 0.45, "wait": 0.9, "note": "seek"})["frame"]
    return False, f
def seek_old(side, team, limit=70):
    """One RT press per look until the name strip of this side reads the club (b81-art's method)."""
    f = route.drv({"op": "shot", "note": "seek"})["frame"]
    want = route.MODERN.index(team)
    for _ in range(limit):
        t = route.name_side(f, side)
        if route.idx(t) == want and not route.offlist(t):
            return True, f
        f = route.drv({"op": "tap", "k": "RT", "n": 1, "hold": 0.15, "gap": 0.45, "wait": 0.9, "note": "seek"})["frame"]
    return False, f
if teams:
    ok_h, f = seek(1, teams[1])
    f = route.to_away()
    ok_a, f = seek(0, teams[0])
    log["teams"] = dict(away=teams[0], home=teams[1], ok=bool(ok_h and ok_a)); print("teams", log["teams"], flush=True)
    if not (ok_h and ok_a):
        print("ABORT: clubs not reached", flush=True); sys.exit(4)
    f = route.to_center()
else:
    # controller icon: home -> centre (two yellow arrows) = CPU v CPU
    for _ in range(4):
        if route.arrows_state(f): break
        f = route.drv({"op": "tap", "k": "LEFT", "hold": 0.2, "wait": 2.0, "note": "center"})["frame"]
log["cpu_v_cpu"] = bool(route.arrows_state(f)); print("cpu v cpu", log["cpu_v_cpu"], f, flush=True)
f = route.drv({"op": "tap", "k": "START", "hold": 0.4, "wait": 4, "note": "coach_matchup"})["frame"]
print("matchup", f, route.ocr(f)[:100], flush=True)
f = route.drv({"op": "tap", "k": "START", "hold": 0.4, "wait": 2, "note": "go"})["frame"]
t0 = time.time(); i = 0
while time.time() - t0 < secs:
    try:
        f = route.drv({"op": "wait", "s": every, "note": f"{tag}_g{i:03d}"})["frame"]
    except Exception as exc:                 # a slow screenshot must not lose the run's record
        print("shot failed", repr(exc)[:160], flush=True); log["stopped"] = repr(exc)[:200]; break
    log["frames"].append(f); i += 1
    if i % 20 == 0: print("frame", i, f, flush=True)
json.dump(log, open(f"/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/emu/evidence/{tag}-game.json", "w"), indent=1)
print("done", i, flush=True)
