"""NFL-shaped player development for franchise: aging-table data plus an in-place NFL career layer (b778 pg1).

How retail NFL 2K5 develops a player (all found in ``default.xbe``; nothing here is random once a player
exists):

* Every offseason the Postseason step ``FUN_00247b40`` adds one to each active player's **years pro**
  (player+0x24 bits 8-12) and the Preseason step (``FUN_002480b0`` stage 7) runs the aging routine
  ``FUN_000e63f0(player, old_years, new_years)`` on every player.  For each of the 29 rating bytes it
  looks up the player's hidden **development archetype** (player+0x24 bit 7 = profile, bits 4-6 =
  sub-type, drawn once at generation) in the 162-row table at 0x4F27B0 (position, profile, sub ->
  ten curve indices) and applies ``rating += curve[new_years] - curve[old_years]`` (``FUN_000e5890``),
  clamped 0..100.  A curve is 21 signed bytes (years pro 0..20).  The ten curve tables sit at
  0x4F31D0..0x4F4CB0 (.rdata), one per rating family: speed/agility; strength/jumping/arm/kick power;
  stamina/durability; a hidden byte; consistency; read coverage + aggression; leadership/composure;
  pass accuracy/catch/kick accuracy; secure ball/break tackle/blocking/tackle; routes/pass rush/coverage.
* Rookies are rolled uniformly between a low and a high template per position (68 templates in the
  roster pack, ``FUN_000e6780``), then ``curve[0]`` is applied.  The archetype is drawn with the
  per-position weights at 0x521680 (162 rows of ``{position, profile, sub, weight}``; ``FUN_002be5b0``).

So the game already makes busts and gems: the same draft-day rating leads to different careers only
through the hidden archetype.  Retail curves are flat, though (about +2..+3 from rookie year to the
prime, then a slow slide), so nobody really develops and the draft-day rating is the career.

This patch keeps the mechanism and re-shapes the data:

* **growth**: every curve gains a ramp over years 1..5 (per family: physical +1..+3, technique and
  mental +5..+6), so a prime-age player sits well above his rookie self;
* **decline**: after a per-family age (years 9..12) each extra year subtracts more (speed fastest);
* **spread**: per position the archetypes with the most and the least growth get more weight and the
  middle ones less (``SPREAD`` = 35 %), so more prospects turn into stars or busts.  Per-position weight
  totals are preserved exactly (the draw is ``rand % total``).

Year 0 is never changed: draft-day ratings, the draft and the scouting screens are identical.
Everything is pattern-checked against the retail tables; the section digests are recomputed.

b778 pg1 adds the native career layer described above ``PERF_VA`` below (position aging, quarterback form,
retirement ages); a beta-77 executable with only the data tables reads ``legacy`` and is upgraded in place.
"""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
CURVES_VA = 0x004F31D0
CURVES_SIZE = 0x004F4CB0 - CURVES_VA        # 6880
WEIGHTS_VA = 0x00521680
WEIGHT_ROWS = 162
WEIGHTS_SIZE = WEIGHT_ROWS * 8               # 1296
PROFILES_VA = 0x004F27B0                     # 162 rows x 16: position, profile, sub, 10 curve indices (read only)
CURVE_LEN = 21                               # years pro 0..20
YEARS_CAP = 20

# (family, table VA, curve count) -- the tables abut with a little padding each; the aging routine
# indexes them with row.byte[6 + family]*21.  The families below name the ratings each table drives.
TABLES = (
    ("speed_agility", 0x004F31D0, 42),
    ("strength_jumping_arm_kickpower", 0x004F3548, 41),
    ("stamina_durability", 0x004F38A8, 20),
    ("hidden_4f", 0x004F3A50, 14),
    ("consistency", 0x004F3B78, 16),
    ("read_coverage_aggression", 0x004F3CC8, 39),
    ("leadership_composure", 0x004F4000, 35),
    ("pass_accuracy_catch_kick_accuracy", 0x004F42E0, 42),
    ("secure_breaktackle_blocking_tackle", 0x004F4658, 42),
    ("routes_passrush_coverage", 0x004F49D0, 35),
)
# family -> (growth by year 5, extra decline per year after DECLINE_AFTER, decline starts after this year)
SHAPE = {
    "speed_agility": (1.0, 2.0, 9),
    "strength_jumping_arm_kickpower": (3.0, 1.0, 10),
    "stamina_durability": (1.0, 1.5, 9),
    "hidden_4f": (0.0, 0.0, 20),
    "consistency": (6.0, 0.5, 12),
    "read_coverage_aggression": (6.0, 0.5, 12),
    "leadership_composure": (5.0, 0.0, 20),
    "pass_accuracy_catch_kick_accuracy": (6.0, 0.5, 11),
    "secure_breaktackle_blocking_tackle": (5.0, 1.0, 10),
    "routes_passrush_coverage": (6.0, 1.0, 10),
}
GROWTH_YEARS = 5
SPREAD = 0.35
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")

_RETAIL_CURVES_Z = (
    "eNptWdlyGzkSRDf6IJukSMmSPZ6N0Itf5sUv+//fsBF7zXjs0X1RvMlu9sU+NrOApjQTC9syBQGoQlVWVhVU1XXTtE1T11V1OBRp"
    "sl283Ddt2yqlHNU2dXXIkt1m9nRrphzHdR1HqbZtDlm8wEzrKrd1tWqqbntV4TAceOCH0k56nu8Hge9p7FdtVeacljlMetpx2rrY"
    "x2tKbzpRSvSSA1SjsOBQQ6NDkWdJulnNnz0Z2jWKQn6yw0pHY1DFhtKTDY68Mme2ZlmZG0GKl3GV4mRZ4JrLl4drF3NaU1uei0tx"
    "MWQfKqcuK3UoyiKP1/Pnuz9gH1ET574JErUpCdcvik6QkUS12qYqcfd49YLPyvVciCghPt7HiwesdM2NcPOKq15fnm5/YLvsdqkG"
    "xKcUhTneU+5elelmPn24/l2JRlwKQTBdnm1mtzVdLObA7rIoshj+UPyuaqDj4VAV2028mj/RcbXYiFL28Xa9fH26NT6n7iLqUGbx"
    "eiZaN1CnyPLdarl5fZndfOe9+afF0bh7lqVpvrMKUXmaqUx2q9lTp6ZjF0P69FnEmNu31us0HS8P0Cg6PlnPprC8Q5WwlAuhbLcS"
    "i7gQRx7g491y9vJkDUJRxGe2nU+fHqB8xatnaV5iYbyRSQ7CeFeUqwUOvDX2dAhxY3brDvEl8UoowaBpvN3MGlqtafKmEjPn6X63"
    "nleAHeDoe8ZyRZ5sV69KWVFiFG47MEZ2m9XC+s41VoEHNsYCnQVxXYAnz+IlbuRoz9GYcuuqYThtF1pwSws6xthAys7cnjihywl+"
    "rCTKZE6m6CxMtg1hKtsd0QtxstMOghsRhRjnFasiL7cL/JwuYCzSAqVst+wgnm54KUAt1ox5iW+JMojaxyu387MN0ny7fH1uW0s6"
    "EMhzD9yu5GbZPgPM9llaEJOvFhG0qfgUMbacKgEEw6vYgwU2q+nz052iNxCxOCTfp0m8XE8XjyJcHz3IC+QiqKxAL4KdIsdIE3AO"
    "4qguD3A9YmGFf/NXBpP5V5Fx8gznxhZjSiKHGm2X82eDPYcMQ7Wsno2ACbYtir14fTZ9UIZKzIXKbqUy8UQoUKMUrGMCR+KG5iS5"
    "bl+uHGXvZGkn3+93m7cQowneVJI5y1my/RaYCYIw8EFIMAfontJdy4LwnMkBR+UrCX2qBP5HNNIYHDUBl6fpfr9dx6KQzyPrtzON"
    "dNdpDoRckWXJ6vmms5KWtTBTtl3NlGs8H++SNM/2COXF9Om4TjGAwSTrl4fbd9sNvQO0SWd4bY+R4AJz0HTwOzGyXc6mL8+P97c3"
    "wtYSvrASjAQuuPmhdOu7raNLt3YOdV7sUm63dP/nMy1dZsKXczAEtzfkgGyfxFi15Nw9JpWJdoOZzXz2OiVBiWS7djmTlRI/JJzt"
    "Zr2Y2+24S1shBWZFki42s+NK4AXHQfZi9vp0f3d79cN4Do6D3berJbV8vGtdOC3JY2+7WSzA9XfXf3A7ow4sdUjeBJHVwV9QB2dC"
    "R8xdcyXLBDDcu5VgN4s8yMIPRJTJSG/6vz6au6s0AWPBQbz8CmcYcqbxK9oP6WK/T2CF7UbZHMTBNMLprdKem/OGdzfXf3z/9tuv"
    "//3Pv/+lojasvKIpE2cbr7fLzRpetcfKzQwyMVRTlmmKVLGZPdze3tzcXF9dXaEQqYjafLcDXT8+PDzc36MscIWTC6EBKpbtZur7"
    "yv+teNwc7hb1dv79+2+/f/v2TQQZGeD75ZM58/9Kp0/8sB8NMQYYURT1lRu4qqjbA1b6WNmalUrVbYUTAu6u6gMnZRwOoNkXiLj6"
    "JgOi/Oj8/PxzN/D5fIyFvm+TjDqkC66/V4fxl19++fr173Z8xfgFu8fYfHn5xY7Ly8vPKjr/fIm1x8F5nDh+t86u9LFbTrWDi5U5"
    "8stfto85dXkeUaH7b//gkEmceUm9xxF1ThfYbuT8afv5ZXT5y/nnr5/xw7HaqnO1fcEtzy+/fPmLnoc0xfyXtwNkUu7+969Wga3U"
    "adrvRRyDd8PRYX84Go0xTo9DuX5veDI5+3D+bjiB7vX9/mDY86OgF/o9T1ubS3XwNnTVuB7oNexhhGEYyECZF2Izjp1MxicyRphE"
    "KPWiwckpRZ3JOFWeG/hBqHEI6mzPd1qEgbBQV427prL0lGFsM3w7GKFeGI3e3ef0VHc/D7oBxYB65IGwdzRI1O/3UO42OlCN44Fh"
    "fb+WXY6pPK0wmUIp5uo36d10A+A6Xls2yDgBmBQk7XkEuokNU1WR+LZVw8vBSP1+P+oGVYJDhjTPuBvMf3K8UduMKmgYXm6jG90b"
    "wrEBtksXwi9V1X2sKxbYcEYnoi8Dk0FvMP5wcfHxbUB66PXD4ej0pD/qj8YDke7CRG8aGktBedGU3w+7wSMxMRyN3w1lbNwNI71V"
    "UFoHEZwcDqPRMALesNLtvPRmUEARhw7HpxefPn3q9ERtD9wOBqPR6MQOWqkDiBmCktpUo38xHfMzSxm2azLwvZJSTKoPVdNB3nq1"
    "POLbO/ZykgqTHa5qL4P/A89MVhBHTIk06fJ0U6qqycoCbUads3jOU2fHsteoygpCMg8zKzajePQ7PEkJ61ibyLecYS+pqlqKP853"
    "s8xHsCoc6OpQas1Gtr/ZwrRpUo/oTkXfdF4HtBNH5a0CrN9QD7rh4GQ0DAfjyXAQ9QDpPMUWn3YM9NHYiplaOcEgxA+l0NW6Qdlh"
    "kwKx3zLns4YQRETgAQn3ycmw5zWZAhAmZx9//unj2WQ0iEIfghJiTJgkpAmgaJXv5soL+sOTs4uffv75b58/XVycn51EgEkQDbV/"
    "Dio5OwsnJ70TnmlykpI22CTYIkV09k5Ozz99/tvPnz+ef5ic9HWbKoTQ5Gx0Ohif/XQ66Yf+mNItmJT8wRWpUtMC5UJqnVP4NuCR"
    "bj5gnIFrxgHoqioR3jTzn43cqA4472AjJ2ISbImS1LS4iHi/bTwwke+imfJqLRQIpwc9iTk4IwwpqABXSXNBMEj/nscAmKFGU/QL"
    "8RTZztOeJSx+gBy20SgyesI3J3DFkC5G3ZBKgDGScZ8TuEjL5P9N6drxcRh0bQne2pGVUhDYJw2pdtDB12S8gFRCJvClFTpwKuyP"
    "Tsn8p5OTqN9j70hwA3PnFx8vLj58mEQwjMtWnY19a/4jpJoDSTo0eQZbA11TEIveLoJggJb9+1xKZr8P5ODED6e4Uotuqy6z1SKe"
    "oQR+vL+7ubr68fu3f8t7j2vjRprKLFnbBwnddZGwZ7zWnk1zPUGEZ0wHx9U6gqMguqrzMk53K6uP17XAJTtjpe1rTttKV5asX9HB"
    "afItAIIjubxKPXQHwtcRU1RP2hbk9KXpjDwalFfXTpUlr0CphlX7jhcFMENbpei3JA6EBw1oW3QDa7ESY0vLm0KVbucvDx3jMd7Q"
    "B6JfmT7e2tbCWBP+ZM+Zv6dbfqgy9LQqBCNPJqenJwASzZEbd0ie6wGv0kvku9VMsBAE9Kwnbx1VnmyE7AG74aDPqOH+RPgiBGYA"
    "AUFVkaxmz/ZBQd7SsLLJN7PnewUxnttWLrCo3crJ081ienxKMsrXaHmSdd3UTRgAxYEOg9Gg56mYoHVMoPOxLt2vXtEt3eJMsMOg"
    "3+trN2CDoeRMY3p2+W0lbdt6XtWorwZMSUh7kwmyWqjllr2hncQYRsEw6lKVeRPQ5n0QoAFO3/O96ffrItG6o2XzEFkX8eKFzyCO"
    "3+pAK1RITemU+91KyNY8ZEpDhs5j/SJRG0g+gnGEg9crEmtA1HouyWG/Q48z5TIDUejUyjPoeuXoAJHd62m/dVWdH2TSGlSMejzT"
    "0V3i0ibd1GW88kzixcFInm1VpLvF7NHpKje5ZV3ymWhmIu6Y1tibJ2vUTy4A77C19hQohGciOl37JuWSleM1OkGvK3H6IWDPl9XX"
    "6aOxs1yfkkp2pjfKsrrjyntrkaJDujeIEttDdJkuZ48PV85RJ4lT0kG2aitYO0Q0AX9eBFSWUOn4diEJhylHFYnwmNQBTl0SI9P7"
    "ux/W+XQK8JQvX59vb35XrfZdELqDMK0xu5s/PV5Dc98Yz+ejRrlfL9E+B5FGTeHw2dKp8irbTf/4p+ocLE9RdbabPzzcsHYKEFAg"
    "B4nFhtzoSuFHAo8kRF1ivXsytMhzxcjKRLb5C7/Fq9nj9fGp2LPcypV1VbQ+n+ccF3Vzje1tsoLj/N6o15cqr66cNF48P6ruzQv2"
    "QRO/W8k1fZMRhdiYqPgKqyVRIskFTJT6nZ7aFB+0abF6vvq1QiEc9ljggmF8orncbxlcnUmoJLSf3nctor1Z14vzHcfO/3lS28pR"
    "rKLsrwy6hkdyAC71dHf1/T+WIe3Tn6vMylZZKLQ2Bcbr5ZHzXVOa8cJ7I9wEOUqH3eL1+fGOBGNLDc9SpLEAAW2dzSkwJGquPuIr"
    "gMMZfHyzyrBqt13u0XDEzXbFBHd3/SvPNIDyjtLlTNczMJNfDvBFCV1Yi1IpcD2naeBW1XhlJuxogkcppzOXCS8Oz+Q20KGml441"
    "TWe6VippDDKbvJbv9x0gGbeBL298Vam6/O1AGQTy48P97bWiPSTXEihFLgdYgB7TEL9Wqitz5NXQrjT517Ocy+S23yyt5WW0cvF4"
    "OZNf5VTyFeSAienT/V2DpnI4Ao2jPO2Hnr2RiQel+I7H34dM765+sDpHnQPk9oFsIPKQ7zdSy9JOsGt9SDZz4ObONUxrG1owPVLo"
    "VDe+03Mr5Q9C14fxD+wcWE16vDxkv9lT+kJjdb6JpQkfZv8HZW5NwA=="
)
_RETAIL_WEIGHTS_Z = (
    "eNpNk0ly5DAMBAkukkhxG8f8/62mUHlwH5yhVkYZLKJD+D7J/wZrYuQ5wbzEovcWLtGmGE3Et/wjlhn0poon3xmjmHjOXSx3iO6/"
    "onXx+JF5IvNEfP3HJloVj5/wnfm/iG+hi7ZEfMO3rDw7fvb8RzQTTz/OVMUzj7O8TgtTNH1v+F++E99KCoXzFhUpRr5PXTx+Yf4L"
    "/6Kfi/NenPfCv/Bv7vcm/yb/pn9n/ieW5fxO6bQhnvt1Jpi3ePzH82/ReD7zPMzjzFMsP07Dt7MPD/0/9OM8+/DQfyW/cr+V+Sv5"
    "lfutnLd6/hINnvkr+ZX7reQ3+mz008hv9N/os5HfPF++md5/8zfyG/fbyH/Zn5f5ndHEFMVzXmcpzm9/XuZ/2R9nyuL5fTlLPZus"
    "+Tv70Om/009n/s78A3/gD/yBP/AH/sSf+BN/4k/8ib/xN31u+tz0ufH3H9/wvz43fW763PS56XORv5hnMc9inkX+Yp8X+Yv8Rf4i"
    "f5G/2OdfahkMSg=="
)


class ProgressionError(ValueError):
    """The progression patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProgressionError(message)


def retail_curves() -> bytes:
    data = zlib.decompress(base64.b64decode(_RETAIL_CURVES_Z))
    _require(len(data) == CURVES_SIZE, "embedded retail curve tables have the wrong size")
    return data


def retail_weights() -> bytes:
    data = zlib.decompress(base64.b64decode(_RETAIL_WEIGHTS_Z))
    _require(len(data) == WEIGHTS_SIZE, "embedded retail weight table has the wrong size")
    return data


# ---------------------------------------------------------------- decoding
def decode_curves(blob: bytes) -> dict[str, list[list[int]]]:
    """family -> list of 21-entry signed curves."""

    out: dict[str, list[list[int]]] = {}
    for family, va, count in TABLES:
        base = va - CURVES_VA
        out[family] = [list(struct.unpack("<21b", blob[base + i * CURVE_LEN: base + (i + 1) * CURVE_LEN]))
                       for i in range(count)]
    return out


def decode_weights(blob: bytes) -> list[dict[str, int]]:
    rows = []
    for i in range(WEIGHT_ROWS):
        pos, profile, sub, weight, pad = struct.unpack_from("<IBBBB", blob, i * 8)
        rows.append({"position": pos, "profile": profile, "sub": sub, "weight": weight})
    return rows


def _encode_curves(tables: Mapping[str, list[list[int]]], retail: bytes) -> bytes:
    buf = bytearray(retail)                  # keeps the padding bytes between tables
    for family, va, count in TABLES:
        base = va - CURVES_VA
        for i, curve in enumerate(tables[family]):
            _require(len(curve) == CURVE_LEN, "curve length")
            buf[base + i * CURVE_LEN: base + (i + 1) * CURVE_LEN] = struct.pack("<21b", *curve)
    return bytes(buf)


def _encode_weights(rows: list[dict[str, int]], retail: bytes) -> bytes:
    buf = bytearray(retail)
    for i, row in enumerate(rows):
        buf[i * 8 + 6] = row["weight"]
    return bytes(buf)


# ---------------------------------------------------------------- the transform
def _clamp8(value: float) -> int:
    return max(-127, min(127, int(round(value))))


def reshape_curve(curve: list[int], family: str, growth_scale: float = 1.0, decline_scale: float = 1.0) -> list[int]:
    """Year 0 untouched; a growth ramp over years 1..GROWTH_YEARS; steeper decline after the family's age."""

    growth, decline, after = SHAPE[family]
    out = []
    for year, value in enumerate(curve):
        ramp = growth * growth_scale * min(year, GROWTH_YEARS) / GROWTH_YEARS
        slide = decline * decline_scale * max(0, year - after)
        out.append(_clamp8(value + ramp - slide) if year else value)
    return out


def reshape_curves(tables: Mapping[str, list[list[int]]], growth_scale: float = 1.0,
                   decline_scale: float = 1.0) -> dict[str, list[list[int]]]:
    return {family: [reshape_curve(c, family, growth_scale, decline_scale) for c in curves]
            for family, curves in tables.items()}


def _row_growth(profile_row: bytes, tables: Mapping[str, list[list[int]]]) -> float:
    """How much this archetype gains from rookie year to year 6, summed over the ten families."""

    total = 0.0
    for family_index, (family, _va, count) in enumerate(TABLES):
        idx = profile_row[6 + family_index]
        if idx < count:
            curve = tables[family][idx]
            total += curve[6] - curve[0]
    return total


def spread_weights(rows: list[dict[str, int]], profiles: bytes, tables: Mapping[str, list[list[int]]],
                   spread: float = SPREAD) -> list[dict[str, int]]:
    """Move weight from the middle archetypes to the two best- and two worst-developing ones per
    position, keeping every position's total exactly (the game draws ``rand % total``)."""

    out = [dict(r) for r in rows]
    by_pos: dict[int, list[int]] = {}
    for i, row in enumerate(out):
        by_pos.setdefault(row["position"], []).append(i)
    profile_rows = {(struct.unpack_from("<I", profiles, k * 16)[0], profiles[k * 16 + 4], profiles[k * 16 + 5]):
                    profiles[k * 16: k * 16 + 16] for k in range(WEIGHT_ROWS)}
    for pos, idxs in by_pos.items():
        total = sum(out[i]["weight"] for i in idxs)
        growth = {}
        for i in idxs:
            key = (pos, out[i]["profile"], out[i]["sub"])
            growth[i] = _row_growth(profile_rows[key], tables) if key in profile_rows else 0.0
        order = sorted(idxs, key=lambda i: growth[i])
        n = len(order)
        extremes = set(order[:2]) | set(order[-2:]) if n >= 6 else set(order[:1]) | set(order[-1:])
        scaled = {}
        for i in idxs:
            factor = (1.0 + spread) if i in extremes else (1.0 - spread * len(extremes) / max(1, n - len(extremes)))
            scaled[i] = max(1.0, out[i]["weight"] * factor)
        weights = {i: max(1, int(round(scaled[i]))) for i in idxs}
        diff = total - sum(weights.values())
        biggest = max(idxs, key=lambda i: weights[i])
        weights[biggest] = max(1, weights[biggest] + diff)
        _require(sum(weights.values()) == total, "weight total drifted")
        for i in idxs:
            out[i]["weight"] = weights[i]
    return out


def patched_tables(payload_profiles: bytes | None = None, growth_scale: float = 1.0, decline_scale: float = 1.0,
                   spread: float = SPREAD) -> tuple[bytes, bytes]:
    """The two replacement blobs (curves, weights) derived from the embedded retail tables."""

    retail_c = retail_curves()
    retail_w = retail_weights()
    tables = reshape_curves(decode_curves(retail_c), growth_scale, decline_scale)
    curves = _encode_curves(tables, retail_c)
    if payload_profiles is None:
        weights = retail_w
    else:
        weights = _encode_weights(spread_weights(decode_weights(retail_w), payload_profiles, tables, spread), retail_w)
    return curves, weights


# ---------------------------------------------------------------- b778 pg1: NFL career arcs (native layer)
# Noah 10/22: "running backs regress faster unless they're generational ... quarterbacks, not so much ... young
# quarterbacks should be more volatile ... other positions should be based on how they work in the NFL".
#
# Retail facts this layer builds on (static disassembly of the USA executable, b778 pg1):
# * Aging 0xE63F0 (Preseason, every allocated player, 0x2485C7) adds curve[new] - curve[old] per rating through
#   0xE5890; the curves are shared by every position (the profile table only picks which curve), so a position's
#   aging cannot be set by the curve data alone without changing draft-day ratings (curve[0]).
# * Right after the aging loop the Preseason calls 0x2BE0F0 (0x2485D6, ecx = 1 = last season). It rates every
#   team roster player's last season from one or two stat totals (0x14EF20) into a FORM level 0..3 (young players,
#   years pro < 3: 1..3; veterans 0..2, a level of 2+ never falls below the old one) and moves the ratings by
#   mini-curve[new] - mini-curve[old] through 0xE63B0 (0x4F27A4: mental -1/0/0/+1, skill -2/0/+1/+2, physical
#   -3/0/+1/+3). So retail already punishes a veteran quarterback's down year (< 1,000 yards: level 0, -2 on
#   every skill) and a rookie quarterback's level cannot drop.
# * Retirement 0x2BCF90: delta = years pro - base[position] (0xACEDE0) adjusted by overall, rand < P[delta] x Y.
#
# What this layer changes (everything in place; no allocator bytes):
# * base[position] for retirement: NFL career lengths (nflverse draft_picks 1994-2013, see b778_pg1 report).
# * 0x2BE0F0 is rewritten table-driven in its own 1,216 bytes. Every position except QB keeps the retail rule
#   exactly (same stat fields and thresholds, PERF_RULES). Quarterbacks are rated by adjusted yards per attempt
#   ((yards + 20 TD - 45 INT) / attempts, 150+ attempts) against the league's qualifying quarterbacks: young
#   quarterbacks (years pro <= 4) move freely 0..3, a veteran's level never drops (no regression after a down
#   year), and a quarterback's form moves his skills more (QB_MINI) but not his speed.
# * The aging call 0xE5890 inside 0xE63F0 (0xE6488) goes through AGING_EXT: after the curve it adds the position
#   class's yearly change dd[class][group][years pro] (D_TARGET minus the mean of the installed curves, so each
#   position's MEAN follows the NFL-shaped target while every archetype keeps its own deviation). A running back
#   who produced 1,200+ (1,600+) scrimmage yards last season ages on the curve of a back one (two) years
#   younger. The same routine runs for the Player Progress screen's "Previously" (0x365B94 un-ages with
#   (y, y-1)), and the adjustment is symmetric in old/new, so that screen stays exact.
# Weekly preparation boosts are per game (0x2AC4E0/0x2AB840) and gone by the Preseason, so nothing here captures
# them. Deterministic: no random numbers are drawn.

PERF_VA = 0x002BE0F0
PERF_SIZE = 0x4C0                 # the retail routine, its two jump tables and the 4 padding bytes up to 0x2BE5B0
RETAIL_PERF_SHA256 = "eecc32ae4cd9ec1f82a34f2d1e9e673c222f69fab4454680c0b3f8346727492b"
AGING_CALL_VA = 0x000E6488        # call 0xE5890 inside the aging routine 0xE63F0
RETAIL_AGING_CALL = bytes.fromhex("e803f4ffff")
MINI_LOAD_VA = 0x000E63C8         # mov ecx, [esi+4]; mov dl, al inside the form routine 0xE63B0
RETAIL_MINI_LOAD = bytes.fromhex("8b4e048ad0")
RETIRE_BASE_VA = 0x00ACEDE0       # .data: u32 per position, retirement base years
RETAIL_RETIRE_BASE = (13, 12, 10, 9, 8, 8, 8, 8, 8, 8, 8, 8, 11, 10, 10, 10, 10)
# QB K P WR CB FS SS RB FB TE OLB ILB C G T DT DE.  NFL: a typical starter (overall .7-.8, -2) retires around
# base + 2 years pro (rookie = 1), a star (.9+, -5) around base + 5; see the report for the nflverse numbers.
NFL_RETIRE_BASE = (14, 14, 14, 8, 7, 8, 8, 6, 7, 9, 8, 8, 11, 10, 10, 9, 9)
FN_AGING_CURVE, FN_FORM, FN_STAT_AGO = 0x000E5890, 0x000E63B0, 0x0014EF20
FN_TEAM_COUNT, FN_TEAM = 0x000C4BE0, 0x000C4C50
GUARDS = (  # retail code this layer calls or hooks; own edits are masked back to retail before hashing
    (0x000E63F0, 0xD5, "1639496f8a03fed199f0f1498d1612ed2a14abdb4b3c1f26d33aa8d8835c0614"),   # aging
    (0x000E63B0, 0x3E, "e76263138ee17d2c920dc253548e39362febdeb003522d9326299be57b6570c3"),   # form
    (0x000E5890, 0x3F, "1e8df0bc09d2af3916e37414d97a1d6a01450665f935280143ec70cc4e05d1ef"),   # curve step
    (0x0014EF20, 0x2A, "53e747dc5d477f71877fd3aadb5ab58627b629c061d4c54696d6c2d3ec4b22d3"),   # stat, seasons ago
    (0x000C4BE0, 0x1C, "2ab6d0df54e0fe9f355845269a30ce1774673fec28ee026ab01af7c486deab2d"),   # team count
    (0x000C4C50, 0x40, "806522d001c6ac072bbb5a6f9ff61bd8e12f55eef0e4d213f5c31ed37c4f2360"),   # team pointer
    (0x002485B6, 0x2A, "5c9e84140c1ac6e4bea4c6d493c6ed9d5f846f117316bf36df927fd94bca0631"),   # Preseason calls
)
POS = {name: i for i, name in enumerate(POSITIONS)}
# Retail form rule per position: (stat field, second field or None, young (high, low), veteran (high, low)).
# young: level = 1 + [v > high] + [v > low];  veteran: level = 1 + [v > high] - [v < low], and a level of 2 or 3
# keeps a higher old level.  Read from the jump tables 0x2BE524 (years pro < 3) and 0x2BE568.
PERF_RULES = {
    "QB": (8, None, (2500, 2000), (2500, 1000)), "K": (0x43, 0x41, (10, 7), (7, 3)), "P": (0x22, None, (25, 20), (21, 10)),
    "WR": (13, None, (800, 500), (600, 200)), "CB": (10, None, (3, 2), (2, 1)), "FS": (0x12, None, (78, 49), (69, 30)),
    "SS": (0x12, None, (78, 49), (69, 30)), "RB": (2, None, (800, 500), (700, 200)), "FB": (13, None, (99, 49), (79, 20)),
    "TE": (13, None, (450, 200), (300, 75)), "OLB": (0x12, None, (89, 49), (69, 30)), "ILB": (0x12, None, (89, 49), (69, 30)),
    "C": (0, None, (15, 11), (13, 6)), "G": (0, None, (15, 11), (13, 6)), "T": (0, None, (15, 11), (13, 6)),
    "DT": (0x13, None, (9, 5), (7, 2)), "DE": (0, None, (14, 7), (9, 3)),
}
QB_MIN_ATTEMPTS = 150
CLUB_TEAMS = 32                   # the league average counts the 32 clubs (not the classic, Pro Bowl or NFL lists)
QB_YOUNG_MAX_YEARS = 4            # years pro after the rollover: seasons 1..3 just completed
QB_LEVEL_EDGES = (-8, 3, 12)      # adjusted yards per attempt x10 above the league: level 0 below -0.8, 3 from +1.2
# QB form mini-curves, laid out like the retail ones at 0x4F27A4 (mental-ish, skill, physical) for levels 0..3
QB_MINI = ((-3, 0, 1, 3), (-5, 0, 2, 5), (0, 0, 0, 0))
RB_PRODUCTION_SHIFT = (1200, 1600)
# Quarterbacks' non-physical ratings (accuracy, reads, arm, consistency, composure...): the yearly change is at least
# -1 until years pro 16 (age about 36), -2 at 17 and -3 from 18 (NFL QB efficiency: about -0.2 ANY/A a year to 35 against
# a 1.2 year-to-year spread, a cliff from 37). Physical ratings age by the table.
QB_CAP_STEP_YEARS = (17, 18)  # scrimmage yards last season -> ages like a back 1 / 2 years younger

CLASSES = ("QB", "KP", "WR", "CB", "S", "RB", "FB", "TE", "LB", "OL", "DL")
CLASS_OF = {"QB": "QB", "K": "KP", "P": "KP", "WR": "WR", "CB": "CB", "FS": "S", "SS": "S", "RB": "RB", "FB": "FB",
            "TE": "TE", "OLB": "LB", "ILB": "LB", "C": "OL", "G": "OL", "T": "OL", "DT": "DL", "DE": "DL"}
GROUPS = ("physical", "skill")   # speed/agility/stamina/durability; strength/jump/arm/kick power and the skills
GROUP_OF_FAMILY = (0, 1, 0, 2, 2, 2, 2, 1, 1, 1)   # family byte 0..9 of a rating entry; 2 = untouched (mental)
DD_FIRST_YEAR = 4                 # dd is zero before years pro 4 (age 24) for every class; stored from here
DD_BYTES = (CURVE_LEN - DD_FIRST_YEAR + 1) // 2   # 17 nibbles per class/group curve
# The NFL-shaped MEAN change per year (rating points) by age a (the change from the season at age a to the next),
# per class and group; before the first age the installed curves alone decide (growth years).  Age of the season
# at years pro y is about 21 + y, so the change applied at the rollover to years pro y is the one at age 20 + y.
# Shapes from nflverse snap counts 2013-2025 and stats 2000-2025 (delta method; report b778_pg1).
D_TARGET = {
    "QB": ({27: -1, 30: -2}, {27: 0, 36: -1, 37: -2, 38: -3}),
    "KP": ({29: -1}, {27: 0, 35: -0.5, 37: -1.5}),
    "RB": ({24: -1, 26: -1.5, 27: -2, 28: -2.5, 29: -3, 31: -4}, {26: -0.5, 27: -1, 28: -1.5, 29: -2}),
    "FB": ({27: -1, 29: -2, 31: -3}, {29: -1}),
    "WR": ({26: -0.5, 27: -1.5, 29: -2, 31: -3}, {28: -0.5, 30: -1.5, 32: -2}),
    "CB": ({26: -1, 27: -1.5, 28: -2.5, 29: -3, 30: -4}, {28: -1, 30: -2}),
    "S": ({27: -1, 28: -1.5, 29: -2.5, 30: -3}, {29: -1, 31: -2}),
    "TE": ({27: -1, 29: -1.5, 31: -2.5}, {29: -0.5, 31: -1.5, 33: -2}),
    "LB": ({26: -1, 28: -2, 30: -3}, {28: -1, 30: -1.5, 31: -2}),
    "OL": ({28: -1, 31: -2}, {29: 0, 31: -1, 33: -2}),
    "DL": ({27: -1, 29: -1.5, 31: -2.5}, {29: -0.5, 31: -1.5, 33: -2}),
}
AGE_AT_YEAR = 20                  # the change applied at years pro y is the NFL change at age 20 + y
# Rating table 0x4F4CB4 (29 x 20 bytes): (rating byte, curve table VA or 0, family byte). Read only.
RATING_ENTRIES = (
    (0x36, 0x4F31D0, 0), (0x37, 0x4F31D0, 0), (0x3C, 0x4F3548, 1), (0x3D, 0x4F3548, 1), (0x39, 0x4F38A8, 2),
    (0x47, 0x4F4658, 8), (0x41, 0x4F4658, 8), (0x3B, 0x4F38A8, 2), (0x4C, 0x4F4000, 6), (0x42, 0x4F42E0, 7),
    (0x38, 0x4F3548, 1), (0x43, 0x4F3CC8, 3), (0x4D, 0, 5), (0x44, 0x4F42E0, 7), (0x3F, 0x4F49D0, 9),
    (0x45, 0x4F4658, 8), (0x46, 0x4F4658, 8), (0x40, 0x4F4658, 8), (0x48, 0x4F49D0, 9), (0x49, 0x4F49D0, 9),
    (0x3E, 0x4F49D0, 9), (0x3A, 0x4F3548, 1), (0x4A, 0x4F42E0, 7), (0x4B, 0, 0), (0x51, 0x4F3CC8, 5),
    (0x4F, 0x4F3A50, 3), (0x50, 0x4F3B78, 4), (0x51, 0x4F4000, 6), (0x4E, 0x4F4000, 6),
)


def _target(schedule: Mapping[int, float], age: int) -> float | None:
    value = None
    for start in sorted(schedule):
        if age >= start:
            value = schedule[start]
    return value


def _native_means(curves: bytes, weights: bytes, profiles: bytes) -> dict[tuple[int, int], list[float]]:
    """(class, group) -> mean yearly change of the installed curves at years pro 0..20, weighted by how often the
    game draws each archetype (the weight table) and counting every rating of the group."""

    weight = {(r["position"], r["profile"], r["sub"]): r["weight"] for r in decode_weights(weights)}
    sums: dict[tuple[int, int], list[float]] = {}
    totals: dict[tuple[int, int], float] = {}
    for k in range(WEIGHT_ROWS):
        pos, profile, sub = struct.unpack_from("<IBB", profiles, k * 16)
        if pos >= len(POSITIONS):
            continue
        cls = CLASSES.index(CLASS_OF[POSITIONS[pos]])
        w = weight.get((pos, profile, sub), 0)
        for _rating, table_va, family in RATING_ENTRIES:
            group = GROUP_OF_FAMILY[family]
            if not table_va or group >= len(GROUPS):
                continue
            base = table_va - CURVES_VA + profiles[k * 16 + 6 + family] * CURVE_LEN
            curve = struct.unpack("<21b", curves[base: base + CURVE_LEN])
            acc = sums.setdefault((cls, group), [0.0] * CURVE_LEN)
            for y in range(1, CURVE_LEN):
                acc[y] += w * (curve[y] - curve[y - 1])
            totals[(cls, group)] = totals.get((cls, group), 0.0) + w
    return {key: [v / totals[key] if totals[key] else 0.0 for v in acc] for key, acc in sums.items()}


def decline_tables(curves: bytes, weights: bytes, profiles: bytes) -> dict[tuple[str, str], tuple[int, ...]]:
    """(class, group) -> dd[0..20]: the integer change added at the rollover to years pro y, so that the class's
    mean change follows D_TARGET; error diffusion keeps the running total within half a point of the target."""

    native = _native_means(curves, weights, profiles)
    out = {}
    for ci, cls in enumerate(CLASSES):
        for gi, group in enumerate(GROUPS):
            mean = native.get((ci, gi), [0.0] * CURVE_LEN)
            dd, carry = [0] * CURVE_LEN, 0.0
            for y in range(1, CURVE_LEN):
                target = _target(D_TARGET[cls][gi], AGE_AT_YEAR + y)
                carry += 0.0 if target is None else target - mean[y]
                dd[y] = int(round(carry))
                carry -= dd[y]
            _require(all(-8 <= v <= 7 for v in dd), f"{cls} {group} decline step does not fit a nibble")
            _require(not any(dd[:DD_FIRST_YEAR]), f"{cls} {group} changes before years pro {DD_FIRST_YEAR}")
            out[(cls, group)] = tuple(dd)
    return out


class _Asm:
    """Two-pass assembler for hand-encoded x86: bytes, labels, rel8 jumps, rel32 calls, absolute label words."""

    def __init__(self, base: int) -> None:
        self.base, self.items, self.labels = base, [], {}

    def __call__(self, hexs: str) -> None:
        self.items.append(bytes.fromhex(hexs))

    def raw(self, data: bytes) -> None:
        self.items.append(bytes(data))

    def label(self, name: str) -> None:
        self.items.append(("label", name))

    def j8(self, opcode: str, label: str) -> None:
        self.items.append(("j8", bytes.fromhex(opcode), label))

    def j32(self, opcode: str, label: str) -> None:
        self.items.append(("j32", bytes.fromhex(opcode), label))

    def call(self, target) -> None:
        self.items.append(("call", target))

    def abs32(self, label: str, addend: int = 0) -> None:
        self.items.append(("abs", label, addend))

    @staticmethod
    def _size(item) -> int:
        if isinstance(item, bytes):
            return len(item)
        if item[0] == "j32":
            return len(item[1]) + 4
        return {"label": 0, "j8": 2, "call": 5, "abs": 4}[item[0]]

    def assemble(self) -> bytes:
        pos = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "label":
                _require(item[1] not in self.labels, f"duplicate label {item[1]}")
                self.labels[item[1]] = self.base + pos
            pos += self._size(item)
        out = bytearray()
        for item in self.items:
            here = self.base + len(out)
            if isinstance(item, bytes):
                out += item
            elif item[0] == "j8":
                rel = self.labels[item[2]] - (here + 2)
                _require(-128 <= rel <= 127, f"rel8 out of range to {item[2]}")
                out += item[1] + struct.pack("<b", rel)
            elif item[0] == "j32":
                out += item[1] + struct.pack("<i", self.labels[item[2]] - (here + len(item[1]) + 4))
            elif item[0] == "call":
                target = self.labels[item[1]] if isinstance(item[1], str) else item[1]
                out += b"\xe8" + struct.pack("<i", target - (here + 5))
            elif item[0] == "abs":
                out += struct.pack("<I", (self.labels[item[1]] + item[2]) & 0xFFFFFFFF)
        return bytes(out)


def _nibbles(values: tuple[int, ...]) -> bytes:
    padded = list(values) + [0] * (len(values) % 2)
    return bytes(((padded[i] & 15) | ((padded[i + 1] & 15) << 4)) for i in range(0, len(padded), 2))


def career_code(dd: Mapping[tuple[str, str], tuple[int, ...]]) -> tuple[bytes, dict[str, int]]:
    """The PERF_SIZE bytes placed over 0x2BE0F0 (form routine, two hook bodies and their tables) and the labels."""

    a = _Asm(PERF_VA)
    # ---- form routine (entry 0x2BE0F0, ecx = seasons ago; the one caller passes 1). Preserves ebx ebp esi edi.
    a.label("perf")
    a("53555657")                          # push ebx; push ebp; push esi; push edi
    a("33db33ff")                          # xor ebx, ebx; xor edi, edi  (league: N sum, attempts sum)
    a("ba"); a.abs32("h_league")           # mov edx, h_league
    a.call("iter")
    a("b800000080")                        # mov eax, 0x80000000 (no qualifying quarterback)
    a("85ff"); a.j8("74", "noq")           # test edi, edi; jz
    a("8bc36bc00a99f7ff")                  # mov eax, ebx; imul eax, eax, 10; cdq; idiv edi
    a.label("noq")
    a("8bf8")                              # mov edi, eax  (league x10, kept for h_main)
    a("ba"); a.abs32("h_main")             # mov edx, h_main
    a.call("iter")
    a("5f5e5d5b")                          # pop edi; pop esi; pop ebp; pop ebx
    a("c3")
    # ---- iter: edx = handler; calls it with esi = each team roster player (retail's team/roster walk)
    a.label("iter")
    a("558bea6a00")                        # push ebp; mov ebp, edx; push 0  ([esp] = team)
    a.label("team")
    a.call(FN_TEAM_COUNT)
    a("390424"); a.j8("7d", "done")        # cmp [esp], eax; jge done
    a("8b0c24")                            # mov ecx, [esp]
    a.call(FN_TEAM)
    a("506a00")                            # push eax (team); push 0 ([esp] = roster slot)
    a.label("player")
    a("8b442404")                          # mov eax, [esp+4]
    a("85c0"); a.j8("74", "next")          # test eax, eax; jz next
    a("0fb6881c010000")                    # movzx ecx, byte [eax+0x11C]  (roster count)
    a("390c24"); a.j8("7d", "next")        # cmp [esp], ecx; jge next
    a("8b0c24" "8b3488")                   # mov ecx, [esp]; mov esi, [eax+ecx*4]
    a("ffd5")                              # call ebp
    a("ff0424"); a.j8("eb", "player")      # inc dword [esp]; jmp player
    a.label("next")
    a("83c408" "ff0424"); a.j8("eb", "team")   # add esp, 8; inc dword [esp]; jmp team
    a.label("done")
    a("585dc3")                            # pop eax; pop ebp; ret
    # ---- stat: edx = field -> eax = last season's value for esi
    a.label("stat")
    a("8bce6a01"); a.call(FN_STAT_AGO); a("c3")
    # ---- qbn: esi -> eax = yards + 20 TD - 45 INT, edx = attempts (last season)
    a.label("qbn")
    a("53" "6a085a"); a.call("stat")
    a("8bd8" "6a095a"); a.call("stat")
    a("6bc014" "03d8" "6a0a5a"); a.call("stat")
    a("6bc02d" "2bd8" "6a065a"); a.call("stat")
    a("8bd0" "8bc3" "5b" "c3")
    # ---- h_league: qualifying quarterbacks add to ebx (N) and edi (attempts)
    a.label("h_league")
    a("837c240c%02x" % CLUB_TEAMS); a.j8("73", "hl_r")   # club teams only ([esp+0xC] = iter's team index)
    a("807e3500"); a.j8("75", "hl_r")      # cmp byte [esi+0x35], 0 (QB); jne
    a.call("qbn")
    a("81fa" + struct.pack("<I", QB_MIN_ATTEMPTS).hex()); a.j8("7c", "hl_r")
    a("03d8" "03fa")                       # add ebx, eax; add edi, edx
    a.label("hl_r")
    a("c3")
    # ---- h_main: one roster player (esi); edi = league x10 or 0x80000000
    a.label("h_main")
    a("53" "57")                           # push ebx; push edi
    a("8b5e1c" "c1eb1e")                   # ebx = old level ([esi+0x1C] >> 30)
    a("0fb64635" "83f810"); a.j32("0f87", "out")   # eax = position; > 16: leave the player alone
    a("8b4e24" "c1e908" "83e11f")          # ecx = years pro
    a("85c0"); a.j32("0f84", "qb")
    a("83f903" "1bc9" "f7d9" "51")         # ecx = young (years pro < 3); push
    a("0fb680"); a.abs32("rule_tab")       # movzx eax, byte [eax + rule_tab]
    a("8d0441" "8d3c80")                   # edi = 5 * (2 * rule + young)
    a("81c7"); a.abs32("perf_tab")         # rows {field, high, low}
    a("0fb617"); a.call("stat"); a("50")   # v = stat(field); push
    a("807e35%02x" % POS["K"]); a.j8("75", "one")
    a("6a%02x5a" % PERF_RULES["K"][1]); a.call("stat"); a("010424")   # kickers: v += the second field
    a.label("one")
    a("58" "59" "6a015a")                  # pop eax (v); pop ecx (young); edx = 1
    a("663b4701"); a.j8("7e", "nh"); a("42")    # v > high: +1
    a.label("nh")
    a("663b4703"); a.j8("e3", "vet")       # cmp ax, low; jecxz vet
    a.j8("7e", "store"); a("42"); a.j8("eb", "store")   # young: v > low: +1
    a.label("vet")
    a.j8("7d", "max"); a("4a")             # veteran: v < low: -1
    a.label("max")
    a("83fa01"); a.j8("7e", "store")
    a("3bda"); a.j8("7e", "store"); a.j8("eb", "keep")   # level 2+ keeps a higher old level
    a.label("keep")
    a("8bd3")
    a.label("store")                       # edx = new level, ebx = old level (retail tail from here)
    a("52" "52" "8bd3" "8bce"); a.call(FN_FORM); a("5a")
    a("8b461c" "8b4e18" "8bf8" "d1ef" "33f9" "81e700000060" "33cf" "25ffffff3f" "c1e21e" "0bc2" "894e18" "89461c")
    a.label("out")
    a("5f" "5b" "c3")
    a.label("qb")
    a("51"); a.call("qbn"); a("59")        # eax = N, edx = attempts
    a("81fa" + struct.pack("<I", QB_MIN_ATTEMPTS).hex()); a.j8("7c", "keep")
    a("81ff00000080"); a.j8("74", "keep")
    a("51" "8bca" "6bc00a" "99" "f7f9" "59" "2bc7")   # eax = 10 N / attempts - league
    a("33d2")
    for edge in QB_LEVEL_EDGES:
        a("83f8" + struct.pack("<b", edge).hex()); a.j8("7c", "qv"); a("42")
    a.label("qv")
    a("83f9" + struct.pack("<b", QB_YOUNG_MAX_YEARS + 1).hex()); a.j8("72", "store")   # young: as rated
    a("3bd3"); a.j8("7d", "store")         # veteran: never below the old level
    a.j8("eb", "keep")
    # ---- aging_ext: replaces call 0xE5890 at 0xE6488 (al = new years, bl = old, dl = value, ecx = curve;
    #      ebp = player, esi = rating entry). Returns al = value, as 0xE5890 does.
    a.label("aging_ext")
    a("52" "50"); a.call(FN_AGING_CURVE); a("59" "5a")   # cl = new years, dl = the rating before the curve step
    a("80fbff"); a.j8("74", "a_ret0")      # generation (old = 0xFF): untouched
    a("3acb"); a.j8("75", "a_go")          # same year (both clamped at 20): untouched
    a.label("a_ret0")
    a("c3")
    a.label("a_go")
    a("57" "56" "52" "51" "50")            # [esp] = value, [esp+4] = new, [esp+8] = value before, [esp+0xC] = entry
    a("8b560c" "83fa09"); a.j32("0f87", "a_done")
    a("0fb692"); a.abs32("group_tab")      # movzx edx, byte [edx + group_tab]
    a("83fa%02x" % len(GROUPS)); a.j32("0f83", "a_qb")    # mental ratings: no table step (QB cap below)
    a("0fb67d35" "83ff10"); a.j32("0f87", "a_done")
    a("0fb6bf"); a.abs32("class_tab")      # movzx edi, byte [edi + class_tab]
    a("8d3c7a")                            # edi = 2 * class + group
    a("0fb6bf"); a.abs32("cid_tab")        # movzx edi, byte [edi + cid_tab]
    a("6bff%02x81c7" % DD_BYTES); a.abs32("dd_tab")   # edi = dd_tab + DD_BYTES * id
    a("33f6" "807d35" + "%02x" % POS["RB"]); a.j8("75", "ns")
    a("6a025a" "8bcd" "6a01"); a.call(FN_STAT_AGO); a("50")
    a("6a0d5a" "8bcd" "6a01"); a.call(FN_STAT_AGO); a("5a" "03c2")
    for yards in RB_PRODUCTION_SHIFT:
        a("3d" + struct.pack("<I", yards).hex()); a.j8("7c", "ns"); a("46")
    a.label("ns")
    a("0fb6442404" "0fb6cb" "3bc1"); a.j8("73", "m"); a("8bc1")   # eax = max(new, old)
    a.label("m")
    a("2bc6" "83e8%02x" % DD_FIRST_YEAR); a.j32("0f88", "a_qb")     # minus the shift; nothing before year 4
    a("8bc8" "d1e8" "0fbe1407" "f6c101"); a.j8("74", "lo")
    a("c1fa04"); a.j8("eb", "sx")
    a.label("lo")
    a("c1e21c" "c1fa1c")
    a.label("sx")
    a("0fb6442404" "3ac3"); a.j8("77", "add"); a("f7da")         # backwards (un-aging): subtract
    a.label("add")
    a("0fbe0424" "03c2" "83f880"); a.j8("7d", "c1"); a("b080")
    a.label("c1")
    a("83f87f"); a.j8("7e", "c2"); a("b07f")
    a.label("c2")
    a("880424")
    # quarterbacks: a non-physical rating moves at most QB_CAP per year (curve + table together), symmetric so the
    # Player Progress un-aging restores it exactly
    a.label("a_qb")
    a("807d3500"); a.j8("75", "a_done")
    a("8b44240c" "8b400c" "83f809"); a.j8("77", "a_done")
    a("80b8"); a.abs32("group_tab"); a("00"); a.j8("74", "a_done")    # physical: declines as the table says
    a("0fb6542404" "0fb6cb" "3bd1"); a.j8("73", "q1"); a("8bd1")      # edx = max(new, old)
    a.label("q1")
    a("33c941")                            # cap 1
    for year in QB_CAP_STEP_YEARS:
        a("83fa%02x" % year); a.j8("72", "q2"); a("41")
    a.label("q2")
    a("0fbe0424" "0fbe542408" "2bc2")      # eax = this year's change
    a("8a542404" "3ad3"); a.j8("77", "qf")
    a("3bc1"); a.j8("7e", "a_done"); a("8bc1"); a.j8("eb", "qs")       # un-aging: at most +cap
    a.label("qf")
    a("f7d9" "3bc1"); a.j8("7d", "a_done"); a("8bc1")                 # aging: at least -cap
    a.label("qs")
    a("02442408" "880424")
    a.label("a_done")
    a("58" "59" "59" "5e" "5f" "c3")
    # ---- qb_mini: replaces mov ecx, [esi+4]; mov dl, al at 0xE63C8 (edi = player)
    a.label("qb_mini")
    a("8ad0" "8b4e04" "807f3500"); a.j8("75", "qm_r")
    a("81c1"); a.abs32("qb_mini_tab", -0x004F27A4)
    a.label("qm_r")
    a("c3")
    # ---- tables
    rules = []                                        # unique (field, young, veteran) rules
    for name in POSITIONS:
        rule = (PERF_RULES[name][0],) + PERF_RULES[name][2:]
        if rule not in rules:
            rules.append(rule)
    a.label("perf_tab")
    for field, young, veteran in rules:
        for high, low in (veteran, young):            # row 2 * rule + young
            a.raw(struct.pack("<Bhh", field, high, low))
    a.label("rule_tab")
    a.raw(bytes(rules.index((PERF_RULES[name][0],) + PERF_RULES[name][2:]) for name in POSITIONS))
    a.label("class_tab")
    a.raw(bytes(CLASSES.index(CLASS_OF[name]) for name in POSITIONS))
    a.label("group_tab")
    a.raw(bytes(GROUP_OF_FAMILY))
    curves = sorted(set(dd.values()))
    a.label("cid_tab")
    a.raw(bytes(curves.index(dd[(cls, group)]) for cls in CLASSES for group in GROUPS))
    a.label("qb_mini_tab")
    a.raw(b"".join(struct.pack("<4b", *row) for row in QB_MINI))
    a.label("dd_tab")
    for curve in curves:
        a.raw(_nibbles(curve[DD_FIRST_YEAR:]))
    body = a.assemble()
    _require(len(body) <= PERF_SIZE, f"career code is {len(body)} bytes, the routine has {PERF_SIZE}")
    labels = {k: v for k, v in a.labels.items() if k in ("perf", "aging_ext", "qb_mini", "perf_tab", "dd_tab")}
    labels["used"] = len(body)
    return body.ljust(PERF_SIZE, b"\xcc"), labels


# ---------------------------------------------------------------- XBE plumbing
def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise ProgressionError(f"VA 0x{va:x} is in no section")


def _profiles(payload: bytes) -> bytes:
    off = _offset(payload, PROFILES_VA)
    return payload[off: off + WEIGHT_ROWS * 16]


def _data_sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    """The curve and weight tables (the beta-77 data patch, unchanged by b778)."""

    curves, weights = patched_tables(_profiles(payload))
    return [
        ("aging_curves", CURVES_VA, retail_curves(), curves),
        ("archetype_weights", WEIGHTS_VA, retail_weights(), weights),
    ]


def _call(at: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (at + 5))


def career_layout(payload: bytes) -> tuple[bytes, dict[str, int], dict[tuple[str, str], tuple[int, ...]]]:
    """The routine bytes, their labels and the decline tables, derived from the installed (patched) curves."""

    profiles = _profiles(payload)
    curves, weights = patched_tables(profiles)
    dd = decline_tables(curves, weights, profiles)
    code, labels = career_code(dd)
    return code, labels, dd


def _career_sites(payload: bytes) -> list[tuple[str, int, bytes | None, bytes]]:
    code, labels, _dd = career_layout(payload)
    return [
        ("retirement_base_years", RETIRE_BASE_VA, struct.pack("<17I", *RETAIL_RETIRE_BASE),
         struct.pack("<17I", *NFL_RETIRE_BASE)),
        ("form_routine_and_aging_tables", PERF_VA, None, code),       # retail checked by RETAIL_PERF_SHA256
        ("aging_curve_hook", AGING_CALL_VA, RETAIL_AGING_CALL, _call(AGING_CALL_VA, labels["aging_ext"])),
        ("form_mini_curve_hook", MINI_LOAD_VA, RETAIL_MINI_LOAD, _call(MINI_LOAD_VA, labels["qb_mini"])),
    ]


def _site_state(payload: bytes, va: int, before: bytes | None, after: bytes) -> str:
    off = _offset(payload, va)
    got = payload[off: off + len(after)]
    if got == after:
        return "applied"
    if before is None:
        return "retail" if hashlib.sha256(got).hexdigest() == RETAIL_PERF_SHA256 else "foreign"
    return "retail" if got == before else "foreign"


def _guards_hold(payload: bytes) -> bool:
    hooks = [(AGING_CALL_VA, RETAIL_AGING_CALL), (MINI_LOAD_VA, RETAIL_MINI_LOAD)]
    for va, size, digest in GUARDS:
        off = _offset(payload, va)
        content = bytearray(payload[off: off + size])
        for at, retail in hooks:
            if va <= at and at + len(retail) <= va + size:
                content[at - va: at - va + len(retail)] = retail
        if hashlib.sha256(content).hexdigest() != digest:
            return False
    return True


def status(payload: bytes) -> str:
    """retail | legacy (the beta-77 curves and weights only) | applied | foreign."""

    try:
        data = {_site_state(payload, va, before, after) for _l, va, before, after in _data_sites(payload)}
        career = {_site_state(payload, va, before, after) for _l, va, before, after in _career_sites(payload)}
        if not _guards_hold(payload):
            return "foreign"
    except (ProgressionError, ValueError, struct.error, IndexError, KeyError):
        return "foreign"
    if len(data) != 1 or len(career) != 1 or "foreign" in data | career:
        return "foreign"
    return {("retail", "retail"): "retail", ("applied", "retail"): "legacy",
            ("applied", "applied"): "applied"}.get((data.pop(), career.pop()), "foreign")


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    _require(state in ("retail", "legacy"), f"progression sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    sites = _career_sites(payload) + (_data_sites(payload) if state == "retail" else [])
    for label, va, before, after in sites:
        off = _offset(payload, va)
        old = bytes(buf[off: off + len(after)])
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after),
                      "changed": sum(1 for a, b in zip(old, after) if a != b)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    code, labels, dd = career_layout(patched)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "upgraded_from_legacy": state == "legacy",
                     "shape": {k: {"growth_by_year_5": v[0], "extra_decline_per_year": v[1], "decline_after_year": v[2]}
                               for k, v in SHAPE.items()},
                     "spread": SPREAD,
                     "retirement_base_years": dict(zip(POSITIONS, NFL_RETIRE_BASE)),
                     "form_code_bytes": labels["used"], "form_code_capacity": PERF_SIZE,
                     "decline_tables": {f"{c}/{g}": list(v[DD_FIRST_YEAR:]) for (c, g), v in sorted(dd.items())},
                     "qb_rule": {"min_attempts": QB_MIN_ATTEMPTS, "young_max_years_pro": QB_YOUNG_MAX_YEARS,
                                 "level_edges_x10": list(QB_LEVEL_EDGES), "mini": [list(r) for r in QB_MINI]},
                     "rb_production_shift_yards": list(RB_PRODUCTION_SHIFT)}


__all__ = ["ProgressionError", "CURVES_VA", "CURVES_SIZE", "WEIGHTS_VA", "WEIGHTS_SIZE", "PROFILES_VA", "TABLES",
           "SHAPE", "SPREAD", "PERF_VA", "PERF_SIZE", "AGING_CALL_VA", "MINI_LOAD_VA", "RETIRE_BASE_VA",
           "RETAIL_RETIRE_BASE", "NFL_RETIRE_BASE", "PERF_RULES", "D_TARGET", "CLASSES", "GROUPS", "QB_MINI",
           "apply", "career_code", "career_layout", "decline_tables", "decode_curves", "decode_weights",
           "patched_tables", "reshape_curve", "retail_curves", "retail_weights", "spread_weights", "status"]
