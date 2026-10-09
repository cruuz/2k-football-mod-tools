"""Beta 77 u3b read-back (the build session's paths: worktree and scratch are hard-coded below).
Independent read-back of the repaired packs for the u3b alternates.
Args: PACKS OUT XBE KEY... (KEY = TEAM:style, e.g. CLE:3)
For every kit of every key: decode the kit package from the repaired packs (u1_audit.export_package); each texture
that the build authored (art PNG exists and differs from the v0.5 export) must decode within a quantisation tolerance
of the authored PNG, and each texture the build did not author must be identical to the v0.5 export. Then the Team
Select cards, the year pairs in the repaired roster, and the game's own Team Select code on the repaired record."""
import json, sys, hashlib
from pathlib import Path
wt = Path("/home/noah/2k-worktrees/b77-u3b"); sys.path[:0] = [str(wt), str(wt / "tools"), str(wt / "tools/b765"), str(wt / "tools/b77")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from mod_editor.core import nfl2k5_historic_styles as hs
from mod_editor.core import nfl2k5_uniform_slots as us
import u1_audit, u3s_slots, u3s_alternates as ua
from nfl_txtr import decode_chunk, parse_texture, texture_to_rgba
from PIL import Image
import numpy as np
S = Path("/home/noah/2k-worktrees/.b77-scratch/u3b")
packs, out, xbe = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
keys = [k.split(":") for k in sys.argv[4:]]
recipes = json.loads((wt / "data/nfl2k5_uniform_alternates_2026_u3b.json").read_text())["alternates"]
CODE = {r["team"]: r["code"] for r in recipes.values()}
folder = {"CLE": "cle", "DAL": "dal", "DEN": "den", "DET": "det", "GB": "gb", "HOU": "hou", "IND": "ind"}
out.mkdir(parents=True, exist_ok=True)
res = {"kits": {}, "cards": {}, "pairs": {}, "cycle": {}}
records = {}
def rgba(path):
    return np.asarray(Image.open(path).convert("RGBA")).astype(int)
with bump._Image.open(packs, writable=False) as image:
    index = bump._parsed_index(image)
    by_id = {e.name_id: e for e in index.entries}
    def outer(e):
        return b"".join(image.read_pack(o, off, n) for o, off, n in index.sub_extents(e, 0, e.size))
    for team, style in keys:
        code = CODE[team]
        art_root = S / f"{team.lower()}{style}" / "art"
        exp_root = S / f"export_{team}" / "uniforms"
        for side in "HA":
            sel = f"{code}{side}{style}"
            data = outer(by_id[ua.name_id(sel + ".IFF")])
            row = u1_audit.export_package(data, {"selector": sel}, out)
            got = out / "uniforms" / sel
            checked = {"authored_ok": 0, "authored_bad": [], "untouched_ok": 0, "untouched_bad": [], "max_authored_mad": 0.0}
            for png in sorted(got.glob("*.png")):
                name = png.name
                if name.startswith("bump_"):
                    continue
                art = art_root / sel / name
                orig = exp_root / sel / name
                new = rgba(png)
                if art.exists() and orig.exists() and not np.array_equal(rgba(art), rgba(orig)):
                    a = rgba(art)
                    if a.shape != new.shape:
                        checked["authored_bad"].append((name, "shape")); continue
                    # compare where the authored texel is opaque: mean absolute difference of RGB
                    m = a[..., 3] > 127
                    mad = float(np.abs(a[..., :3] - new[..., :3])[m].mean()) if m.any() else 0.0
                    checked["max_authored_mad"] = max(checked["max_authored_mad"], mad)
                    if mad < 14: checked["authored_ok"] += 1
                    else: checked["authored_bad"].append((name, round(mad, 1)))
                elif orig.exists():
                    if np.array_equal(new, rgba(orig)): checked["untouched_ok"] += 1
                    else: checked["untouched_bad"].append(name)
            res["kits"][sel] = {"sha256": hashlib.sha256(data).hexdigest(), "assets": len(row["assets"]),
                                "unif": ua.unif_words(data), **checked}
    wanted = {f"{f}_{s}{CODE[t]}_{st}" for t, st in keys for f in ("unif", "helm") for s in "ha"}
    for i in (3102, 3105):
        data = outer(index.entries[i])
        for ch in ua._walk_chunks(data):
            if ch.kind != "TXTR": continue
            dec, _ = decode_chunk(data, ch)
            try: t = parse_texture(dec, ch)
            except Exception: continue
            if t.name in wanted:
                Image.frombytes("RGBA", (t.width, t.height), texture_to_rgba(dec, ch, t)).save(out / f"{t.name}_{t.width}.png")
                res["cards"][f"{t.name}_{t.width}"] = hashlib.sha256(data[ch.offset:ch.end_offset]).hexdigest()
    roster = outer(by_id[0x4A37581D])
    body = roster[32:]
    codes = {CODE[t] for t, _ in keys}
    for at, c in hs.team_records(roster)[:32]:
        if c in codes:
            res["pairs"][c] = [list(p) for p in us.team_pairs(body, at)]
            records[c] = body[at:at + us.TEAM_SIZE]
m = u3s_slots.Machine(xbe.read_bytes())
for c, rec in records.items():
    res["cycle"][c] = m.cycle(rec)
(out / "readback.json").write_text(json.dumps(res, indent=1))
for c in res["cycle"]:
    print(c, [x[1] for x in res["cycle"][c]["order"]])
for k, v in res["kits"].items():
    print(k, "authored ok", v["authored_ok"], "bad", v["authored_bad"], "untouched ok", v["untouched_ok"], "bad", v["untouched_bad"], "max mad", round(v["max_authored_mad"], 1), v["unif"])
print("cards", len(res["cards"]))
