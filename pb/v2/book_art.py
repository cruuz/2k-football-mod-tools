#!/usr/bin/env python3
"""Play-art sheets of a composed team book (b776 job pb1): what the book itself holds, drawn from its bytes.

Every ordinary offensive play is drawn once, in the first formation whose menu lists it (formation geometry and
personnel from that formation record, chains decoded from the play), with the codec's play-art geometry
(``nfl2k5_play_codec.play_art``): routes as arrows, blocks as bars, carrier paths, QB drops, read order in red.
Panels are grouped by formation and labelled "formation / play (menu count)".

    python3 pb/v2/book_art.py BOOK.play --out sheet.png [--title "KC"] [--cols 10]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402

YD = codec.YD_CM
COLORS = {lib.WR: "#1f6feb", lib.TE: "#8957e5", lib.HB: "#d1242f", lib.FB: "#bf8700", lib.QB: "#1a7f37"}


def draw_view(ax, v: lint.PlayView, title: str) -> None:
    pos, kinds = v.positions, v.kinds
    ax.axhline(0, color="#999999", lw=0.8, zorder=0)
    for y in (5, 10, 15, 20):
        ax.axhline(y, color="#e6e6e6", lw=0.5, zorder=0)
    q = lint.qb_slot(v)
    reads = []
    if q is not None:
        node = next((n for n in v.chains[q] if n.op == 0x06), None)
        if node is not None:
            reads = [int(node.operands[i]) + 5 for i in range(1, 5) if 1 <= int(node.operands[i]) <= 5]
    rank = {s: i + 1 for i, s in enumerate(reads)}
    for s in range(11):
        x0, z0 = pos[s]
        kind = kinds[s]
        color = COLORS.get(kind, "#57606a")
        px, pz = x0 / YD, z0 / YD
        art = []
        for n in v.chains[s]:
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
            elif n.op == 0x02 and int(n.operands[0]) != q:
                t = int(n.operands[0])
                ax.plot([px, pos[t][0] / YD], [pz, pos[t][1] / YD], color="#cf222e", lw=0.8, ls=":")
            else:
                art.append(n)
        for seg in codec.play_art(art, (x0, z0), 1 if x0 >= 0 else -1):
            xs = [p[0] / YD for p in seg.points]
            zs = [p[1] / YD for p in seg.points]
            if seg.style == "block":
                ax.plot(xs, zs, color="#57606a", lw=1.0)
                continue
            ax.plot(xs, zs, color=color, lw=1.3, ls="--" if seg.style == "dashed" else "-")
            if seg.end_marker == "arrow" and len(xs) == 2 and (xs[0] != xs[1] or zs[0] != zs[1]):
                ax.annotate("", xy=(xs[1], zs[1]), xytext=(xs[0], zs[0]),
                            arrowprops=dict(arrowstyle="->", color=color, lw=1.1))
            elif seg.end_marker == "block" and len(xs) == 2:
                dx, dz = xs[1] - xs[0], zs[1] - zs[0]
                n = math.hypot(dx, dz) or 1
                ox, oz = -dz / n * 0.6, dx / n * 0.6
                ax.plot([xs[1] - ox, xs[1] + ox], [zs[1] - oz, zs[1] + oz], color="#57606a", lw=1.1)
        marker = "s" if kind in lib.OL_KINDS else "o"
        ax.scatter([x0 / YD], [z0 / YD], s=18, marker=marker, color=color if kind not in lib.OL_KINDS else "#57606a",
                   zorder=3)
        if s in rank:
            ax.text(x0 / YD + 0.8, z0 / YD - 1.8, str(rank[s]), fontsize=6, color="#cf222e", weight="bold")
    ax.set_xlim(-27, 27)
    ax.set_ylim(-10, 26)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=6)


def book_panels(raw: bytes):
    book = insp.parse_playbook_resource(raw)
    links = {}
    first = {}
    for v in lint.resource_views(raw):
        if v.play_flags & lib.PLAY_FLAG_SPECIAL:
            continue
        links[v.play] = links.get(v.play, 0) + 1
        first.setdefault(v.play, v)
    order = sorted(first.values(), key=lambda v: (v.formation, v.play))
    return [(v, f"{v.formation_name}\n{v.play_name} ({links[v.play]})") for v in order]


def render(raw: bytes, out: Path, title: str, cols: int = 10) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = book_panels(raw)
    rows = math.ceil(len(panels) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.3, rows * 1.85))
    for ax in axes.flat:
        ax.axis("off")
    for ax, (v, label) in zip(axes.flat, panels):
        ax.axis("on")
        draw_view(ax, v, label)
    fig.suptitle(f"{title}: every offensive play once, drawn from the composed book's bytes "
                 "(red numbers = read order; (n) = menus listing it)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return len(panels)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--cols", type=int, default=10)
    args = ap.parse_args(argv)
    n = render(args.book.read_bytes(), args.out, args.title or args.book.stem, args.cols)
    print(args.out, n, "plays")


if __name__ == "__main__":
    main()
