#!/usr/bin/env python3
"""Render concept diagrams from the engine's own chains (beta 77, job p48o).

Each panel draws one concept in one formation with the codec's play-art geometry
(``nfl2k5_play_codec.play_art``, a port of the retail draw handlers): routes as arrows,
blocks as short bars, the read order numbered.  Rendered from data, not drawn by hand.
DESIGN diagrams; gameplay unwitnessed.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402

YD = codec.YD_CM
COLORS = {lib.WR: "#1f6feb", lib.TE: "#8957e5", lib.HB: "#d1242f", lib.FB: "#bf8700", lib.QB: "#1a7f37"}
DEFAULT_FORMATION = {
    "quick": "Gun Trey", "dropback": "Gun Doubles", "pa": "Singleback Ace", "shot": "Singleback Doubles",
    "screen": "Gun Doubles", "run": "I-Form Pro", "trick": "I-Form Pro",
}
PREFERRED = {"Mesh": "Gun Bunch", "Snag": "Gun Bunch", "Stick": "Gun Trey", "Flood": "Gun Trips", "Levels": "Gun Trips",
             "Y Cross": "Singleback Y Trips", "Texas": "Gun Split Backs", "Bubble Screen": "Gun Trips",
             "WR Slip Screen": "Gun Spread", "TE Screen": "Singleback Doubles", "End Around": "Singleback Doubles",
             "Reverse": "Singleback Doubles", "QB Sneak": "Goal Line", "Iso": "I-Form Pro", "QB Draw": "Gun Empty",
             "PA Boot Leak": "Ace Wing", "Yankee": "I-Form Pro", "Spacing": "Gun Empty", "Hank": "Gun Trips Open",
             "Four Verticals": "Gun Spread", "Mills": "Gun Spread", "Fade Out": "Goal Line"}


def formation_for(concept: str) -> str:
    return PREFERRED.get(concept) or DEFAULT_FORMATION[oc.CONCEPTS[concept].family]


def draw(ax, spec: oc.FormationSpec, d: oc.PlayDesign, title: str) -> None:
    ctx = spec.context()
    pos = spec.positions_cm()
    ax.axhline(0, color="#999999", lw=0.8, zorder=0)
    for y in (5, 10, 15, 20):
        ax.axhline(y, color="#e6e6e6", lw=0.5, zorder=0)
    read_rank = {s: i + 1 for i, s in enumerate(d.reads)}
    for s in range(11):
        nodes = codec.encode_chain(d.chains[s])
        x0, z0 = pos[s]
        kind = ctx.player(s).kind
        color = COLORS.get(kind, "#57606a")
        # ball-carrier actions: take point (handoff hole), run path (mode 0 absolute, 1 relative,
        # 2 follow), QB drop / boot and handoffs, drawn over the codec's route and block art
        px, pz = x0 / YD, z0 / YD
        art_nodes = []
        for n in nodes:
            if n.op in (0x16, 0x17):
                hx = codec.HANDOFF_HOLE_CM[int(n.operands[2])] / YD
                ax.plot([px, hx], [pz, -1.0], color=color, lw=1.0, ls=":" if n.op == 0x17 else "--")
                px, pz = hx, -1.0
            elif n.op == 0x15:
                mode, dx, dy = int(n.operands[0]), n.operands[1] / YD, n.operands[2] / YD
                tx, tz = (dx, dy) if mode == 0 else (px + dx, pz + dy + (3.0 if mode == 2 else 0.0))
                ax.annotate("", xy=(tx, tz), xytext=(px, pz), arrowprops=dict(arrowstyle="->", color=color, lw=1.4))
                px, pz = tx, tz
            elif n.op == 0x04 and kind == lib.QB:
                tx = n.operands[1] / YD if int(n.operands[0]) == 1 else px
                tz = min(pz, n.operands[2] / YD)
                ax.plot([px, tx], [pz, tz], color=color, lw=1.0, ls=":")
                px, pz = tx, tz
            elif n.op == 0x13:
                t = int(n.operands[0])
                ax.plot([px, pos[t][0] / YD], [pz, pos[t][1] / YD], color="#57606a", lw=0.6, ls=":")
            else:
                art_nodes.append(n)
        nodes = art_nodes
        for seg in codec.play_art(nodes, (x0, z0), 1):
            xs = [p[0] / YD for p in seg.points]
            zs = [p[1] / YD for p in seg.points]
            if seg.style == "block":
                ax.plot(xs, zs, color="#57606a", lw=1.0)
                continue
            ax.plot(xs, zs, color=color, lw=1.4, ls="--" if seg.style == "dashed" else "-")
            if seg.end_marker == "arrow" and len(xs) == 2 and (xs[0] != xs[1] or zs[0] != zs[1]):
                ax.annotate("", xy=(xs[1], zs[1]), xytext=(xs[0], zs[0]),
                            arrowprops=dict(arrowstyle="->", color=color, lw=1.2))
            elif seg.end_marker == "block" and len(xs) == 2:
                dx, dz = xs[1] - xs[0], zs[1] - zs[0]
                n = math.hypot(dx, dz) or 1
                px, pz = -dz / n * 0.6, dx / n * 0.6
                ax.plot([xs[1] - px, xs[1] + px], [zs[1] - pz, zs[1] + pz], color="#57606a", lw=1.2)
        marker = "s" if kind in lib.OL_KINDS else "o"
        ax.scatter([x0 / YD], [z0 / YD], s=22, marker=marker, color=color if kind not in lib.OL_KINDS else "#57606a",
                   zorder=3)
        if s in read_rank:
            ax.text(x0 / YD + 0.8, z0 / YD - 1.6, str(read_rank[s]), fontsize=6, color="#cf222e", weight="bold")
    ax.set_xlim(-27, 27)
    ax.set_ylim(-10, 26)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=7)


def render(out: Path, concepts: list[str]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = 6
    rows = math.ceil(len(concepts) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.6, rows * 2.0))
    for ax in axes.flat:
        ax.axis("off")
    for ax, name in zip(axes.flat, concepts):
        ax.axis("on")
        fname = formation_for(name)
        spec = oc.FORMATIONS[fname]
        try:
            d = oc.design(name, spec.context())
        except oc.ConceptUnavailable:
            continue
        draw(ax, spec, d, f"{name}\n{fname}")
    fig.suptitle("SOFTDRINK 2K28 v0.6 offense concepts (rendered from the engine's chains; red numbers = read order)",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--family", action="append")
    args = ap.parse_args(argv)
    names = [n for n, c in oc.CONCEPTS.items() if not args.family or c.family in args.family]
    render(args.out, names)
    print(args.out, len(names))


if __name__ == "__main__":
    main()
