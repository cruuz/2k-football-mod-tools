"""ku1 (b776): the 2026 Chiefs menu art (Team Select uniform and helmet cards, schedule miniatures) in the 2026 red.

The eight Chiefs menu slots (``unif_h13_0``/``unif_a13_0`` and ``helm_h13_0``/``helm_a13_0`` at 256, the helmets at
128, ``mini_h13_0``/``mini_a13_0``) were rendered from the old kit red #E31837, whose blue sits well above its green:
the cards read raspberry next to the 2026 kits (``data/nfl2k5_kit_fixes_2026_ku1.json``). This pass pulls every red
palette entry of those slots toward the club's red: an entry whose red leads green by more than 40 and blue by more
than 20, and whose blue is above its green, moves ``pull`` of the blue-over-green gap from blue to green (exact
integers), so the shading, highlights and indices stay as they are. Only the palette bytes change.

Each slot is pinned before and after; retail, older or user art is left alone.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import nfl2k5_historic_styles as hs

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_menu_chiefs_2026.json"
SCHEMA = "nfl2k5_menu_chiefs_2026/v1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec(path=None) -> dict:
    doc = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    hs.require(doc.get("schema") == SCHEMA, "unexpected Chiefs menu data schema")
    return doc


def pull_palette(palette: np.ndarray, rule: dict) -> tuple[np.ndarray, np.ndarray]:
    """(256, 4) RGBA int64 -> pulled palette and the moved entries."""
    out = palette.copy()
    r, g, b, a = (palette[:, i] for i in range(4))
    hit = (r > g + int(rule["red_over_green"])) & (r > b + int(rule["red_over_blue"])) & (b > g) & (a > 0)
    num, den = (int(v) for v in rule["pull"])
    hs.require(0 < num < den, "the pull must be a fraction")
    k = ((b - g) * num) // den
    out[hit, 1] = g[hit] + k[hit]
    out[hit, 2] = b[hit] - k[hit]
    return out, hit & (k > 0)


def _palette_at(span: bytes) -> tuple[int, object, object]:
    from tools import nfl_txtr as tx
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    hs.require(chunk.kind == "TXTR" and not chunk.compressed, "expected a raw menu TXTR slot")
    decoded, _ = tx.decode_chunk(span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    hs.require(texture.format_name == "P8", "expected a P8 menu slot")
    at = 32 + chunk.system_bytes + texture.palette_offset
    inner = chunk.system_bytes + texture.palette_offset
    hs.require(span[at:at + 1024] == decoded[inner:inner + 1024], "menu slot palette not where expected")
    return at, chunk, texture


def paint(span: bytes, rule: dict) -> tuple[bytes, dict]:
    at, _, _ = _palette_at(span)
    palette = np.frombuffer(span[at:at + 1024], np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]].astype(np.int64)
    new, moved = pull_palette(palette, rule)
    hs.require(moved.any(), "no red palette entry to move")
    out = bytearray(span)
    out[at:at + 1024] = np.ascontiguousarray(new[:, [2, 1, 0, 3]], np.uint8).tobytes()
    return bytes(out), dict(palette_entries_moved=int(moved.sum()))


def plan_archive(archive, doc=None):
    from . import nfl2k5_menu_helmet_w2026 as menu
    doc = doc or spec()
    plan, rows = [], []
    for target in doc["targets"]:
        try:
            at, before = menu.locate(archive, target["aggregate"], target["member"])
        except (ValueError, KeyError, hs.HistoricStylesError):
            rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="not_applicable"))
            continue
        digest = sha(before)
        if digest == target["after_sha256"]:
            rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="applied", written=0))
            continue
        if digest != target["before_sha256"]:
            rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="not_applicable",
                             target_sha256=digest))
            continue
        after, receipt = paint(before, doc["rule"])
        hs.require(sha(after) == target["after_sha256"], f"{target['member']} differs from its pin")
        plan.append((at, before, after))
        rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="applied", written=1,
                         virtual_offset=at, size=len(before), before_sha256=digest, after_sha256=sha(after),
                         changed_bytes=sum(x != y for x, y in zip(before, after)), **receipt))
    states = {r["state"] for r in rows}
    state = "applied" if states == {"applied"} else ("not_applicable" if "applied" not in states else "partial")
    return plan, dict(state=state, written=len(plan), slots=rows)


def apply_to_image(image, *, strict=False) -> dict:
    from tools.nfl2k5_playbook_position_recode import OuterImage
    try:
        archive_cm = OuterImage(Path(image), writable=True)
        archive = archive_cm.__enter__()
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written=0)
    try:
        plan, receipt = plan_archive(archive)
        hs.require(not strict or receipt["state"] == "applied", "the Chiefs menu art is not the known art")
        attempted = []
        try:
            for at, before, after in plan:
                hs.require(archive.read(at, len(before)) == before, "Chiefs menu slot changed after preflight")
                attempted.append((at, before))
                hs.require(archive.write(at, after) == len(after), "short Chiefs menu slot write")
                hs.require(archive.read(at, len(after)) == after, "Chiefs menu slot read-back differs")
            replay, _ = plan_archive(archive)
            hs.require(not replay, "Chiefs menu correction did not survive read-back")
        except BaseException:
            for at, before in reversed(attempted):
                archive.write(at, before)
            raise
    finally:
        archive_cm.__exit__(None, None, None)
    return receipt
