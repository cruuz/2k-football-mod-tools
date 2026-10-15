"""The modern game ball for modern play, the user's own retail ball for the older Anniversary moments (N15).

The ball is the scene "ball" in global.iff (outer 3), resident for the whole session: texture 0 (P8 256 x 256, six
mips) carries the design and texture 1 the normal map. The game finds the scene by name at every per-game init
(0x950B0) and binds texture 0 by descriptor pointer; its palette address (descriptor +8) is read live at draw.

Data: texture 0 gets one index image quantised jointly from the authored modern ball and the disc's own ball, so two
palettes describe the two designs: palette A (the modern ball) at texture 0's palette and palette B (the disc's ball)
in the last 1,344 bytes of texture 1's pixel chain, freed by giving the normal map three mips instead of six. The
scene keeps its size and wrapper and is refit into its existing compressed span; nothing else in outer 3 changes.
Texture 1's three-mip format word is the signature the runtime selector requires before it touches anything.

Runtime (installed inside the moment-venue owner, see nfl2k5_moment_venues): at 0x950CC, after the ball scene is
found, texture 0's palette pointer is set to palette B in Anniversary mode (mode 8) for a row whose season is before
MODERN_FROM_SEASON, and to palette A otherwise, so every game re-asserts the choice and normal games keep the
modern ball.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data/nfl2k5_era_ball"
CATALOG = ROOT / "data/nfl2k5_espn25_fields.json"
SCHEMA = "nfl2k5_era_ball/v1"
GLOBAL_ID = 0x8EE9EEED
SCENE = "ball"
SIZE, LEVELS = 256, 6
BALL_FORMAT = 0x08860B29
DUAL_FORMAT = 0x08830B29
TEX0 = dict(descriptor=448, pixel=0, palette=87360)
TEX1 = dict(descriptor=480, pixel=88448, palette=175808)
OLD_PALETTE = TEX1["pixel"] + 256 * 256 + 128 * 128 + 64 * 64
PALETTE_BYTES = 1024
HOOK = ("ball", 0x950CC, bytes.fromhex("687057e600"))
MODE, ORDINAL = 0xE5FF80, 0xBF1858
SELECTOR_SIZE = 88
PALETTE_CAPS = (256, 224, 192, 160, 128)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest():
    raw = (ART / "manifest.json").read_bytes()
    require(len(raw) < 64 * 1024, "era ball manifest is too large")
    doc = json.loads(raw)
    require(doc.get("schema") == SCHEMA and doc["texture"]["size"] == [SIZE, SIZE], "foreign era ball manifest")
    require(isinstance(doc.get("modern_from_season"), int), "era ball season boundary")
    return doc


def art():
    from PIL import Image
    import numpy as np
    texture = manifest()["texture"]
    path = (ART / texture["file"]).resolve()
    require(path.is_relative_to(ART.resolve()), "era ball art path escapes its folder")
    raw = path.read_bytes()
    require(len(raw) < 1024 * 1024 and sha(raw) == texture["sha256"], "era ball art hash differs")
    with Image.open(path) as im:
        rgba = np.asarray(im.convert("RGBA")).copy()
    require(rgba.shape == (SIZE, SIZE, 4) and set(np.unique(rgba[..., 3])) <= {0, 255},
            "era ball art must be 256 x 256 with a binary mark mask")
    return rgba


def old_ball_rows():
    """Anniversary rows (1-based) whose season predates the modern ball."""
    boundary = manifest()["modern_from_season"]
    moments = json.loads(CATALOG.read_text())["moments"]
    return sorted(m["row"] for m in moments if m["season"] < boundary)


def row_mask():
    rows = old_ball_rows()
    require(rows and all(1 <= r <= 51 for r in rows), "era ball rows")
    return sum(1 << (r - 1) for r in rows)


# --- the ball scene ------------------------------------------------------------------------------------------------

def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def ball_scene(outer):
    """(chunk, rec, decoded) of the single ball scene, after checking the retail texture layout exactly."""
    mm = _mm()
    tx = mm._tools()[0]
    found = []
    for chunk in tx.parse_chunks(outer, allow_trailing=True):
        if chunk.kind == "SCNE":
            rec, decoded = mm._scene(outer, chunk)
            if rec.get("name") == SCENE:
                found.append((chunk, rec, decoded))
    require(len(found) == 1, "global.iff lacks a single ball scene")
    chunk, rec, decoded = found[0]
    textures = rec["embedded_textures"]
    require(len(textures) == 2 and len(rec["materials"]) == 3, "the ball scene is not the retail two-texture layout")
    for t, want in zip(textures, (TEX0, TEX1)):
        require(t["format_name"] == "P8" and (t["width"], t["height"]) == (SIZE, SIZE)
                and all(int(t[k + "_offset"]) == v for k, v in want.items()), "the ball textures moved")
    require(int(textures[0]["mip_levels"]) == LEVELS, "the ball texture is not a six-mip chain")
    require(_format(decoded, TEX0) == BALL_FORMAT and _format(decoded, TEX1) in (BALL_FORMAT, DUAL_FORMAT),
            "the ball texture formats differ from retail")
    return chunk, rec, decoded


def _format(decoded, texture):
    return struct.unpack_from("<I", decoded, texture["descriptor"] + 12)[0]


def state(outer):
    """'retail' or 'applied' (texture 1 carries the three-mip signature)."""
    _, _, decoded = ball_scene(outer)
    return "applied" if _format(decoded, TEX1) == DUAL_FORMAT else "retail"


def _levels(decoded, system):
    """RGBA arrays of every mip of texture 0 as the disc stores it."""
    import numpy as np
    tx = _mm()._tools()[0]
    at = system + TEX0["pixel"]
    palette = np.frombuffer(bytes(decoded[system + TEX0["palette"]:system + TEX0["palette"] + PALETTE_BYTES]),
                            np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    out = []
    for level in range(LEVELS):
        n = SIZE >> level
        linear = np.frombuffer(tx.unswizzle_2d(bytes(decoded[at:at + n * n]), n, n, 1), np.uint8)
        out.append(palette[linear].reshape(n, n, 4))
        at += n * n
    return out


def joint_palettes(modern, old, cap=256):
    """(palette pairs (256, 6) uint8, [index array per level]) for two mip chains of the same size.

    Deterministic median cut over the (modern RGB, old RGB) pairs of every level, weighted by count, then three
    Lloyd passes; each pair takes its nearest entry."""
    import numpy as np
    pairs = np.concatenate([np.hstack([m.reshape(-1, 4)[:, :3], o.reshape(-1, 4)[:, :3]]) for m, o in zip(modern, old)])
    uniq, inverse, counts = np.unique(pairs, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    boxes = [np.arange(len(uniq))]
    while len(boxes) < cap:
        best, score = None, -1.0
        for i, box in enumerate(boxes):
            if len(box) < 2:
                continue
            spread = uniq[box].max(0).astype(int) - uniq[box].min(0)
            value = float(spread.max()) * float(np.sqrt(counts[box].sum()))
            if value > score:
                best, score = i, value
        if best is None:
            break
        box = boxes.pop(best)
        channel = int(np.argmax(uniq[box].max(0).astype(int) - uniq[box].min(0)))
        order = box[np.argsort(uniq[box, channel], kind="stable")]
        weight = np.cumsum(counts[order])
        cut = min(max(int(np.searchsorted(weight, weight[-1] / 2)) + 1, 1), len(order) - 1)
        boxes += [order[:cut], order[cut:]]
    palette = np.array([np.average(uniq[b].astype(float), axis=0, weights=counts[b]) for b in boxes])

    def nearest(pal):
        labels = np.empty(len(uniq), np.int64)
        p = pal.astype(np.int64)
        for start in range(0, len(uniq), 4096):
            block = uniq[start:start + 4096].astype(np.int64)
            labels[start:start + 4096] = ((block[:, None, :] - p[None]) ** 2).sum(2).argmin(1)
        return labels

    for _ in range(3):
        labels = nearest(palette)
        for k in range(len(palette)):
            members = labels == k
            if members.any():
                palette[k] = np.average(uniq[members].astype(float), axis=0, weights=counts[members])
    palette = np.clip(np.rint(palette), 0, 255).astype(np.uint8)
    labels = nearest(palette)
    index = labels[inverse].astype(np.uint8)
    out, at = [], 0
    for m in modern:
        n = m.shape[0] * m.shape[1]
        out.append(index[at:at + n].reshape(m.shape[:2]))
        at += n
    full = np.zeros((256, 6), np.uint8)
    full[:len(palette)] = palette
    return full, out


def _palette_bytes(rgb):
    import numpy as np
    out = np.zeros((256, 4), np.uint8)
    out[:, 0], out[:, 1], out[:, 2], out[:, 3] = rgb[:, 2], rgb[:, 1], rgb[:, 0], 255
    return out.tobytes()


def plain_leather(rgb):
    """Boolean mask of texels that read as plain brown leather (not lace white, gold or black ink)."""
    import numpy as np
    c = rgb.astype(int)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    lum = (299 * r + 587 * g + 114 * b) // 1000
    return (r - g > 28) & (g - b >= 4) & (lum >= 38) & (lum <= 140) & (g * 100 < r * 64)


def _blur(a, sigma):
    """Separable Gaussian blur of a 2-D or 3-D float array, wrapping across the ball's seams horizontally."""
    import numpy as np
    radius = int(sigma * 3)
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    out = a.astype(float)
    for axis, mode in ((1, "wrap"), (0, "edge")):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (radius, radius)
        p = np.pad(out, pad, mode=mode)
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            acc += w * np.take(p, np.arange(i, i + out.shape[axis]), axis=axis)
        out = acc
    return out


def modern_chain(art_rgba, old):
    """The modern ball's mip chain on the disc's leather: authored texels for the laces, the marks and wherever the
    disc's ball is not plain leather; the disc's own texels where both are plain leather. Each mip keeps the disc's
    texel wherever its 2 x 2 footprint is unchanged, so the two designs share one leather at every level."""
    import numpy as np
    stw = _mm()._tools()[4]
    ink = ~plain_leather(old[0][..., :3])
    for _ in range(2):  # the anti-aliased rims of the disc's lettering read as leather; take them with the ink
        grown = ink.copy()
        grown[1:] |= ink[:-1]
        grown[:-1] |= ink[1:]
        grown[:, 1:] |= ink[:, :-1]
        grown[:, :-1] |= ink[:, 1:]
        ink = grown
    leather = ~ink
    marks = art_rgba[..., 3] == 255
    authored = marks | ~leather
    # Where the disc's ball has ink but the modern ball has plain leather, the leather is the disc leather's local
    # mean (a normalised blur over its plain-leather texels) plus the authored leather's fine grain.
    known = leather.astype(float)
    local = _blur(old[0][..., :3].astype(float) * known[..., None], 6.0) / np.maximum(_blur(known, 6.0), 1e-6)[..., None]
    wide = _blur(old[0][..., :3].astype(float) * known[..., None], 18.0) / np.maximum(_blur(known, 18.0), 1e-6)[..., None]
    local = np.where((_blur(known, 6.0) > 0.05)[..., None], local, wide)
    plain = (~marks).astype(float)
    art_mean = (_blur(art_rgba[..., :3].astype(float) * plain[..., None], 6.0)
                / np.maximum(_blur(plain, 6.0), 1e-6)[..., None])
    grain = (art_rgba[..., :3].astype(float) - art_mean) * plain[..., None]
    filled = np.clip(np.rint(local + grain), 0, 255).astype(np.uint8)
    base = old[0].copy()
    gap = authored & ~marks
    base[gap, :3] = filled[gap]
    base[marks, :3] = art_rgba[marks, :3]
    base[..., 3] = 255
    dims = stw._mip_dimensions(SIZE, SIZE, LEVELS)
    made = [np.frombuffer(m.rgba, np.uint8).reshape(m.height, m.width, 4)
            for m in stw._generate_dynamic_mips(np.ascontiguousarray(base).tobytes(), dims)]
    changed = np.any(base != old[0], axis=2)
    out = [base]
    for level in range(1, LEVELS):
        n = SIZE >> level
        changed = changed.reshape(n, 2, n, 2).any(axis=(1, 3))
        out.append(np.where(changed[..., None], made[level], old[level]).astype(np.uint8))
    return out, int(authored.sum())


def compile_scene(decoded, rec, modern_rgba=None, cap=256):
    """(edited decoded scene, receipt): the jointly quantised index image, palettes A and B and the signature."""
    import numpy as np
    mm = _mm()
    tx = mm._tools()[0]
    system = int(rec["system_bytes"])
    old = _levels(decoded, system)
    require(all((level[..., 3] == 255).all() for level in old), "the disc's ball is not opaque")
    modern, authored = modern_chain(art() if modern_rgba is None else modern_rgba, old)
    palette, indices = joint_palettes(modern, old, cap)
    edited = bytearray(decoded)
    at = system + TEX0["pixel"]
    for level in indices:
        n = level.shape[0]
        edited[at:at + n * n] = tx.swizzle_2d(level.tobytes(), n, n, 1)
        at += n * n
    require(at == system + TEX0["palette"], "ball pixel chain length")
    edited[system + TEX0["palette"]:system + TEX0["palette"] + PALETTE_BYTES] = _palette_bytes(palette[:, :3])
    edited[system + OLD_PALETTE:system + OLD_PALETTE + PALETTE_BYTES] = _palette_bytes(palette[:, 3:])
    struct.pack_into("<I", edited, TEX1["descriptor"] + 12, DUAL_FORMAT)
    error = []
    for chain, side in ((modern, slice(0, 3)), (old, slice(3, 6))):
        want = chain[0][..., :3].astype(int)
        error.append(round(float(np.abs(palette[indices[0]][..., side].astype(int) - want).mean()), 3))
    return edited, dict(modern_mean_abs_error=error[0], disc_ball_mean_abs_error=error[1], authored_texels=authored, palette_entries=cap)


def allowed_ranges(system):
    return [(system + TEX0["pixel"], system + TEX0["palette"] + PALETTE_BYTES),
            (system + OLD_PALETTE, system + OLD_PALETTE + PALETTE_BYTES),
            (TEX1["descriptor"] + 12, TEX1["descriptor"] + 16)]


def apply_global(outer, modern_rgba=None):
    """(outer, receipt): global.iff with the era ball data; an applied outer returns unchanged."""
    mm = _mm()
    tx = mm._tools()[0]
    chunk, rec, decoded = ball_scene(outer)
    span = mm.scene_span(outer, chunk)
    if _format(decoded, TEX1) == DUAL_FORMAT:
        return outer, dict(already_applied=True, written=False, ball_offset=chunk.offset, ball_size=len(span))
    modern_rgba = art() if modern_rgba is None else modern_rgba
    attempts = []
    for cap in PALETTE_CAPS:
        edited, quality = compile_scene(decoded, rec, modern_rgba, cap)
        protected = bytearray(edited)
        for start, end in allowed_ranges(int(rec["system_bytes"])):
            protected[start:end] = decoded[start:end]
        require(bytes(protected) == decoded, "the era ball changed bytes outside texture 0 and palette B")
        try:
            rebuilt, info = mm.fit_span(span, bytes(edited))
            break
        except (tx.TxtrError, mm.ModernMetLifeError) as exc:
            attempts.append(f"{cap}: {exc}")
    else:
        raise ValueError("the era ball does not fit the ball span: " + " | ".join(attempts))
    back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(back == bytes(edited) and len(rebuilt) == len(span), "the era ball refit read-back differs")
    result = outer[:chunk.offset] + rebuilt + outer[chunk.offset + len(span):]
    return result, dict(already_applied=False, written=True, ball_offset=chunk.offset, ball_size=len(span),
                        ball_before=sha(span), ball_after=sha(rebuilt), decoded_before=sha(decoded),
                        decoded_after=sha(bytes(edited)), old_ball_rows=old_ball_rows(), fit=info, fit_attempts=attempts,
                        **quality)


def palettes(outer):
    """(palette A RGBA (256, 4), palette B RGBA, index image level 0) of an applied outer, for previews and tests."""
    import numpy as np
    tx = _mm()._tools()[0]
    _, rec, decoded = ball_scene(outer)
    system = int(rec["system_bytes"])
    a = np.frombuffer(bytes(decoded[system + TEX0["palette"]:][:PALETTE_BYTES]), np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    b = np.frombuffer(bytes(decoded[system + OLD_PALETTE:][:PALETTE_BYTES]), np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    index = np.frombuffer(tx.unswizzle_2d(bytes(decoded[system:system + SIZE * SIZE]), SIZE, SIZE, 1),
                          np.uint8).reshape(SIZE, SIZE)
    return a, b, index


# --- the runtime selector --------------------------------------------------------------------------------------------

def selector(va):
    """(code, (site, retail bytes, hook bytes)) of the per-game palette choice at 0x950CC.

    edi is the ball scene descriptor (non-null). Unless the scene has two textures and texture 1 carries the
    three-mip signature, nothing is touched. Palette A = texture 1 Data - 0x440, palette B = texture 1 Data + 0x15000.
    """
    tex1 = TEX1["pixel"]
    to_a = (TEX0["palette"] - tex1) & 0xFFFFFFFF
    to_b = OLD_PALETTE - tex1
    mask_at = va + SELECTOR_SIZE - 8
    code = bytearray()
    fix = {}

    def emit(raw):
        code.extend(raw)

    def jcc(op, label):
        emit(bytes([op, 0]))
        fix[len(code) - 1] = label

    labels = {}
    emit(b"\x9c\x60")                                          # pushfd; pushad
    emit(b"\x83\x7f\x14\x02")                                  # cmp dword [edi+0x14], 2
    jcc(0x75, "done")
    emit(b"\x8b\x47\x18")                                      # mov eax, [edi+0x18]  (texture array)
    emit(b"\x81\x78\x2c" + struct.pack("<I", DUAL_FORMAT))     # cmp dword [eax+0x2c], DUAL_FORMAT
    jcc(0x75, "done")
    emit(b"\x8b\x50\x24")                                      # mov edx, [eax+0x24]  (texture 1 Data)
    emit(b"\x8d\x8a" + struct.pack("<I", to_a))                # lea ecx, [edx+A]
    emit(b"\x83\x3d" + struct.pack("<I", MODE) + b"\x08")      # cmp dword [MODE], 8
    jcc(0x75, "set")
    emit(b"\x8b\x1d" + struct.pack("<I", ORDINAL))             # mov ebx, [ORDINAL]
    emit(b"\x83\xfb\x33")                                      # cmp ebx, 51
    jcc(0x73, "set")
    emit(b"\x0f\xa3\x1d" + struct.pack("<I", mask_at))         # bt [mask], ebx
    jcc(0x73, "set")
    emit(b"\x8d\x8a" + struct.pack("<I", to_b))                # lea ecx, [edx+B]
    labels["set"] = len(code)
    emit(b"\x89\x48\x08")                                      # mov [eax+8], ecx  (texture 0 palette)
    labels["done"] = len(code)
    emit(b"\x61\x9d")                                          # popad; popfd
    emit(HOOK[2])                                              # the displaced push of L"fball0"
    emit(b"\xe9" + struct.pack("<i", (HOOK[1] + len(HOOK[2])) - (va + len(code) + 5)))
    for at, label in fix.items():
        rel = labels[label] - (at + 1)
        require(-128 <= rel <= 127, "selector branch range")
        code[at] = rel & 0xFF
    require(len(code) <= SELECTOR_SIZE - 8, "selector budget")
    code.extend(b"\xcc" * (SELECTOR_SIZE - 8 - len(code)))
    code.extend(struct.pack("<Q", row_mask()))
    hook = b"\xe9" + struct.pack("<i", va - HOOK[1] - 5)
    return bytes(code), (HOOK[1], HOOK[2], hook)


# --- image (build-only, on the caller's disposable copy) ------------------------------------------------------------

def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


def _global_entry(archive):
    entry = {e.name_id: e for e in archive.entries}.get(GLOBAL_ID)
    require(entry is not None, "global.iff is not on this disc")
    return entry


def plan_image(source, modern_rgba=None):
    """([(virtual offset, before, after)], receipt) for the ball span of global.iff (read only)."""
    mm = _mm()
    with _outer_image()(source) as archive:
        entry = _global_entry(archive)
        outer = archive.read(entry.virtual_offset, entry.size)
    result, receipt = apply_global(outer, modern_rgba)
    if not receipt["written"]:
        return [], receipt
    at, size = receipt["ball_offset"], receipt["ball_size"]
    require(result[:at] == outer[:at] and result[at + size:] == outer[at + size:], "era ball scope")
    del mm
    return [(entry.virtual_offset + at, outer[at:at + size], result[at:at + size])], receipt


def apply_to_image(target, modern_rgba=None):
    plan, receipt = plan_image(target, modern_rgba)
    with _outer_image()(target, writable=True) as archive:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "the ball span changed after preflight")
            require(archive.write(at, after) == len(after), "short era ball write")
            require(archive.read(at, len(after)) == after, "era ball read-back differs")
    require(image_status(target) == "applied", "the era ball failed its read-back on the copy")
    return dict(receipt, state="applied", runtime_witnessed=False, written_spans=len(plan))


def image_status(source):
    try:
        with _outer_image()(source) as archive:
            entry = _global_entry(archive)
            return state(archive.read(entry.virtual_offset, entry.size))
    except (ValueError, KeyError, IndexError, struct.error):
        return "foreign"
