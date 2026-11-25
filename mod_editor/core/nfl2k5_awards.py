"""Season award vote, a 24-man All-Pro team and defensive credit in simulated games (job b81-awards). EXPERIMENTAL.

Owner, 2026-11-25 (simmed franchise, 2029): "award logic needs work. in 2029 in my sim, arvell reese wins mvp with an
insane 4.5 sack, 104 tackle, 15 int, 2ff, 2 td season. but thats DPOY numbers... jayden daniels should be mvp, qb, plus
40td passing, PLUS 1000 yards rushing... plus team success, easy pick. non qbs can win mvp, but not when a qb plays like
that... reese would need more sacks probably, but 15 int is insane... perhaps too insane?" Earlier (2026-10-28): "always
leave exceptions where if someone puts up insane stats at literally any position ... that player could win MVP".

Why it happened (lane DESIGN.txt, measured on the 40-season combined panel 68001-68004)
--------------------------------------------------------------------------------------
* The champions owner's vote (``champions_modern_awards``, beta 79) names any man with 15 interceptions (or 30 sacks, 300
  tackles, ...) MVP before any score is compared ("otherworldly"); a 15-INT linebacker or corner beats a 40-TD quarterback.
* The simulator credits defenders by three retail lotteries that favour linebackers: coverage 0x1035E0 (4 of 10 candidates
  are linebackers, the targeted receiver is not read, the club's best coverage man takes a further 0.2 of every draw), pass
  rush 0x103760 (4 linebacker slots of 14, rated 40% on Tackle and Strength; its DE/DT bonus compares the table index with
  the slot number at 0x10379B and never fires) and tackler 0x1036A0 (its running total passes 1 after about ten men, so the
  list order decides). Linebackers took 23-42% of interceptions (real off-ball LBs 15-16%), 40-44% of sacks (real 15-21%),
  36% of tackles (real 27%) and 32 of 40 DPOYs; the season interception leader averaged 10.9 (real 8.0), with 1.6 men a
  season at 10+ (real 0.18).

What this owner does (one fixed page, ``nfl2k5_xbe_space.AWARDS_VA``, code only)
-------------------------------------------------------------------------------
* The vote, at 0x116E5A (``pop esi; pop ebp; add esp,0x1c`` of FUN_00116920's last-week award block: after the retail
  pass and the champions owner's vote at 0x116E55, before the honors owner's tail at 0x116E5F records the slots). It
  writes the five player awards and the best-at-position slots again (rule: ``choose_awards`` and ``all_pro`` below, the
  plain-data twin of ``tools/nfl2k5_awards/runtime.c``):
    MVP: a quarterback's offence points x team factor (40% at .500 or worse to 100% at .750, +10 for one of the league's
    two best records) x fatigue (-15% for last season's MVP, -8% for each other MVP in the four seasons before, cap -30%;
    from the man's own MVP honors, history field 96). Backs, receivers and tight ends only with a historic season (2,000
    rushing yards, 2,400 scrimmage yards, 26 touchdowns or 1,950 receiving yards); defenders only past a record (24 sacks
    or 14 interceptions), worth 280 offence points x the larger fraction of the record.
    OPOY / OROY: offence points against each position's award season, x 80-100% for the club's record.
    DPOY / DROY: 10 a sack, 2 a QB hit (field 107), 20 an interception, 6 a forced fumble, 0.3 a tackle, x a position weight.
    All-Pro: QB, HB, FB, three WR, TE, two T, two G, C, two DE, two DT, two LB, two CB, two S, K, P (24). The first of each
    retail category takes its best-at-position slot (the honors owner records those); the other fifteen get history field 104
    here (Franchise only, regular class). The return-man slot is cleared.
* The credit, at 0x134DF1 (``mov ebx,eax; mov al,[edi+0x11c]`` of FUN_00134DD0, before one club's players are merged into
  their careers): in a simulated Franchise game (league mode 2, game mode 4, regular season or playoffs) the club's credited
  interceptions, sacks and tackles are drawn again among its defenders who played, one at a time (whole sacks to one man),
  by the real position shares (``CREDIT_SHARES``, nflverse 2021-2025) and within a position by the game's own derived
  ratings (0x246A80 categories 9 / 4 / 11, squared, squared and to the fifth power); 10% of the interceptions go to the
  club's best coverage back. The club's totals, the plays and the score are unchanged; the draw uses its own xorshift
  generator seeded from the game (never the game's 0x48B90 stream), so a simulated season plays out byte for byte as
  before. When the cornerback tackle owner (``nfl2k5_sim_cb_tackles``) is installed its per-game corner bonus is part of the
  corners' share, so the tackle table changes with it (``CREDIT_SHARES['tackles_with_cb']``).

Installed with the honors owner (one toggle; ``nfl2k5_honors.apply``). Not witnessed in game; the rule is proven on the
stored seasons and the credit on a paired season panel (lane REVIEW_ME.txt).
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_awards_code as runtime
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.AWARDS_OWNER
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = space.AWARDS_SIZE
CODE_VA = space.AWARDS_VA
REQUESTS = (space.AWARDS_REQUEST,)
HELP_TEXT = (
    "Season awards are voted the way they have gone in the modern NFL: the MVP is a quarterback on a winning club unless "
    "a back or receiver has a historic season (2,000 rushing yards, 26 touchdowns...) or a defender breaks a record (24 "
    "sacks or 14 interceptions) in a year without a standout quarterback; repeat winners face some voter fatigue. Pass "
    "rushers and cover men win Defensive Player of the Year, and the All-Pro team has 24 men in the AP shape. In "
    "simulated franchise games interceptions, sacks and tackles are credited by the real position shares, so linebackers "
    "no longer collect corners' interceptions and edge rushers' sacks; scores and plays are unchanged.")

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
P = {name: i for i, name in enumerate(POSITIONS)}

# (label, VA, retail bytes, entry label, opcode, length): each site becomes a jmp rel32 to the entry, NOP-padded.
SITE_TABLE = (
    ("vote", 0x00116E5A, bytes.fromhex("5e5d83c41c"), "awards_vote_entry", 0xE9, 5),
    ("credit", 0x00134DF1, bytes.fromhex("8bd88a871c010000"), "awards_credit_entry", 0xE9, 8),
)
AWARD_CALL, AWARD_TAIL = 0x00116E55, 0x00116E5F     # the champions owner's call site and the honors owner's tail
CB_SITE = 0x001334C3                                 # read at run time: retail 0x8B unless the cornerback owner hooks it

# Retail routines the runtime calls or reads, pinned by SHA-256 of their retail bytes (own sites masked; the two
# neighbouring award sites are masked to retail whatever another owner put there, and checked by opcode instead).
GUARDS = (
    ("history get", 0x0014EE40, 0x1F, "fc126037b6c785bd0575f57a96d322c442e7e6786cab43d75368c4d3a4a4ccd3"),
    ("history ago", 0x0014EF20, 0x2A, "53e747dc5d477f71877fd3aadb5ab58627b629c061d4c54696d6c2d3ec4b22d3"),
    ("history set", 0x0014F430, 0x17, "c50c4461b01c36f097954be45394d9aaec9804b89a26d32584689153ecd02151"),
    ("class set", 0x0014EDB0, 0x07, "d865ebcc76568491ae0bd0c5d7759826052fed67e74abe915e831d299326bef6"),
    ("team first", 0x000C3E70, 0x10, "d2dca284a4b79a29764b40ba0a6b4917a7f7efa2a22033e1cc8f89bcc193143b"),
    ("team next", 0x000C3E80, 0x10, "5215f6bb8c45e4866d42661900f17be8b21674bcb0b5ca1c940816a6fab10319"),
    ("team count", 0x000C6430, 0x1D, "580846043b88c68576012ac8f9e52c3814120dbe5a03ab5888b16ee66f7c396f"),
    ("team by index", 0x000C4C50, 0x35, "0a2bf8745446926481a11c536ad91ebc1b719721dd961762064905f0d6901a26"),
    ("club index", 0x000C4CA0, 0x0E, "9f3b8071de1f12c085a482262b097225705a9d4b28c67c7a20a412d66c5b9ac5"),
    ("team wins", 0x000C7720, 0x30, "83c4b626588be7c7e5da821f5c997519a879a1363edf84c23e2859e5c17a3d90"),
    ("team losses", 0x000C7750, 0x30, "405d309f1add61c7e134c95d1ec455b83848e24c1c882cdb42bfacf43cffc714"),
    ("team ties", 0x000C7780, 0x30, "2481cd7485cb21874604d2e063c8f2897c951ae7efa349ec2cd4dcf181494dab"),
    ("derived attribute", 0x00246A80, 0x14, "fceb09aae6f34368c6afd32d5dd43384a032ac0acad3eebe64d907cc6b58bb1e"),
    ("overall", 0x00246D80, 0x0B, "b1d398b4daafb19cfa40d3752616c907d3a2b5210446b6fa137e8d034bcbeee9"),
    ("live next", 0x00061B90, 0x18, "2293018ff01ac08f455d72b1a63bf840f3a702034ad353487e7ed425067b96a6"),
    ("award block", 0x00116E55, 0x0F, "80b8b0b7def41097d6b4d39eb6cde77b31dec53990a3b5be583a1ada1dd559e0"),
    ("club merge head", 0x00134DD0, 0x35, "d76cb3b9b599b7053c7f1d26471790dbf282a752ea81e8f9140d3cce8013c900"),
)
ALWAYS_RETAIL = ((AWARD_CALL, bytes.fromhex("e856f1ffff")), (AWARD_TAIL, bytes.fromhex("e95cf2ffff")))


class AwardsError(ValueError):
    """Unsupported executable, foreign or mixed installation."""


def _require(condition, message):
    if not condition:
        raise AwardsError(message)


def code_for(code_va: int = CODE_VA) -> bytes:
    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        _require(symbol == "code", "unexpected awards relocation")
        target = code_va + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "the awards runtime exceeds its page")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def labels(code_va: int = CODE_VA) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def sites(code_va: int = CODE_VA) -> list[tuple[str, int, bytes, bytes]]:
    at = labels(code_va)
    return [(label, va, before, bytes([opcode]) + struct.pack("<i", at[entry] - (va + 5)) + b"\x90" * (length - 5))
            for label, va, before, entry, opcode, length in SITE_TABLE]


def _masked(image: XbeImage, va: int, size: int) -> bytes:
    content = bytearray(image.read(va, size))
    for _label, address, before, _after in sites():
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    for address, before in ALWAYS_RETAIL:
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    return bytes(content)


def guard_digests(payload: bytes) -> dict[str, str]:
    image = XbeImage(payload)
    return {name: hashlib.sha256(_masked(image, va, size)).hexdigest() for name, va, size, _d in GUARDS}


def _check_guards(image: XbeImage) -> None:
    for name, va, size, digest in GUARDS:
        _require(hashlib.sha256(_masked(image, va, size)).hexdigest() == digest,
                 f"foreign awards dependency: {name} ({va:#x})")
    _require(image.read(AWARD_CALL, 1)[0] == 0xE8 and image.read(AWARD_TAIL, 1)[0] == 0xE9,
             "foreign award block call or tail")


def allocations(payload: bytes) -> dict[str, dict]:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and (rows[0]["va"], rows[0]["size"]) == (CODE_VA, CODE_SIZE),
             "foreign awards allocation")
    return {"code": rows[0]}


def owned_state(payload: bytes):
    """-> ("retail" | "applied", allocations | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    _check_guards(image)
    found = allocations(payload)
    edits = sites()
    if not found or image.read(CODE_VA, CODE_SIZE) == b"\xcc" * CODE_SIZE:
        _require(rdata.status(payload, edits) == "retail", "awards sites changed without the owner's code")
        return "retail", (found or None)
    _require(image.read(CODE_VA, CODE_SIZE) == code_for(), "foreign awards code")
    _require(rdata.status(payload, edits) == "applied", "mixed awards sites")
    return "applied", found


def status(payload: bytes) -> str:
    try:
        return owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def applied_sites(image) -> list[tuple[str, int, bytes, bytes]]:
    """This owner's site edits while it reads exactly applied, else []: the honors owner (its 'season awards' guard spans
    0x116E5A) and the weekly progression owner (its merge-loop guard spans 0x134DF1) mask them back to retail."""

    data = image.data if isinstance(image, XbeImage) else image
    try:
        return sites() if status(data) == "applied" else []
    except Exception:  # noqa: BLE001 - a foreign image simply has no awards edits to mask
        return []


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "awards_vote": state == "applied", "all_pro_size": ALL_PRO_SIZE if state == "applied" else None}


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in sites()]


def install(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Reserve the fixed page if needed, fill it and patch both sites. Idempotent."""

    state, found = owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE), "owner_bytes": CODE_SIZE}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if not found:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
    _require(bool(allocations(payload)), "reserve the awards page first")
    installed, code_receipt = space.install_code(payload, OWNER, code_for())
    result, site_receipt = rdata.apply(installed, sites(), OWNER)
    _require(status(result) == "applied", "awards postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(CODE_VA), "changed_bytes": sum(a != b for a, b in zip(before, result))
                    + abs(len(result) - len(before)),
                    "sites": [{"label": label, "va": hex(va), "size": len(b)} for label, va, b, _a in sites()],
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


apply = install


# ---- the rule on plain data (the native runtime's twin) -------------------------------------------------------------
OPOY_REF = {P["QB"]: 460, P["WR"]: 315, P["HB"]: 355, P["TE"]: 310}          # offence points of an award season
OROY_REF = {P["QB"]: 250, P["WR"]: 300, P["HB"]: 355, P["TE"]: 300}
ROLE_WEIGHT = {P["CB"]: 130, P["FS"]: 120, P["SS"]: 120, P["OLB"]: 80, P["ILB"]: 80, P["DT"]: 120, P["DE"]: 100}
OFFENSE = frozenset(P[n] for n in ("QB", "HB", "FB", "WR", "TE"))
DEFENSE = frozenset(ROLE_WEIGHT)
NOT_VOTED = frozenset(P[n] for n in ("K", "P", "C", "G", "T"))
HISTORIC = {"rush_yds": 2000, "scrimmage": 2400, "touchdowns": 26, "rec_yds": 1950}
RECORD = {"sacks2": 46, "def_int": 14}          # 23 sacks (2025), 14 interceptions (1952); the gate is 24 sacks / 14 INT
DEFENSIVE_MVP_POINTS = 28000                    # a record-level season counts as 280 offence points
FATIGUE = (15, 8, 30)                           # last season's MVP, each other MVP in the four before, cap (percent)
ALL_PRO = (("QB", 1), ("HB", 1), ("FB", 1), ("WR", 3), ("TE", 1), ("T", 2), ("G", 2), ("C", 1), ("DE", 2), ("DT", 2),
           ("LB", 2), ("CB", 2), ("S", 2), ("K", 1), ("P", 1))
ALL_PRO_SIZE = sum(n for _c, n in ALL_PRO)
AP_CATEGORY = {P["QB"]: "QB", P["K"]: "K", P["P"]: "P", P["WR"]: "WR", P["CB"]: "CB", P["FS"]: "S", P["SS"]: "S",
               P["HB"]: "HB", P["FB"]: "FB", P["TE"]: "TE", P["OLB"]: "LB", P["ILB"]: "LB", P["C"]: "C", P["G"]: "G",
               P["T"]: "T", P["DT"]: "DT", P["DE"]: "DE"}
RETAIL_SLOTS = ("QB", "HB", "WR", "TE", "T", "DE", "LB", "CB", "K")     # +0x5830 + 8 * i: QB RB/FB WR TE OL DL LB DB K
# nflverse 2021-2025 role shares (thousandths) the credit draws by: CB, S, LB, DE, DT
CREDIT_SHARES = {"interceptions": (410, 380, 155, 30, 25), "sacks": (35, 65, 220, 430, 250),
                 "tackles_with_cb": (120, 240, 300, 190, 150), "tackles": (220, 220, 270, 160, 130)}
CREDIT_POWER = {"interceptions": 2, "sacks": 2, "tackles": 5}
CREDIT_CATEGORY = {"interceptions": 9, "sacks": 4, "tackles": 11}
BEST_COVER_SHARE = 0.10


def _pos0(v):
    return v if v > 0 else 0


def offense_points(s) -> int:
    return _pos0(s["pass_yds"] * 4 + s["pass_td"] * 400 - s["pass_int"] * 200 + s["rush_yds"] * 10
                 + s["rush_td"] * 600 + s["rec_yds"] * 10 + s["rec"] * 50 + s["rec_td"] * 600)


def defense_points(s) -> int:
    return _pos0(s["sacks2"] * 50 + s.get("qbh", 0) * 20 + s["def_int"] * 200 + s["ff"] * 60 + s["tackles"] * 3)


def win_pct1000(rec) -> int:
    w, l, t = rec
    g = w + l + t
    return (2 * w + t) * 500 // g if g else 0


def mvp_base(s) -> int:
    pos = s["pos"]
    if pos == P["QB"]:
        return offense_points(s)
    if pos in OFFENSE:
        historic = (s["rush_yds"] >= HISTORIC["rush_yds"] or s["rush_yds"] + s["rec_yds"] >= HISTORIC["scrimmage"]
                    or s["rush_td"] + s["rec_td"] >= HISTORIC["touchdowns"] or s["rec_yds"] >= HISTORIC["rec_yds"])
        return offense_points(s) if historic else 0
    if s["sacks2"] < 48 and s["def_int"] < 14:
        return 0
    frac = max(_pos0(s["sacks2"]) * 1000 // RECORD["sacks2"], _pos0(s["def_int"]) * 1000 // RECORD["def_int"])
    return DEFENSIVE_MVP_POINTS * frac // 1000


def fatigue(mvp_ago) -> int:
    """mvp_ago: the man's MVP honor value 1, 2, 3, 4 and 5 seasons ago."""
    ago = list(mvp_ago or ()) + [0] * 5
    cut = (FATIGUE[0] if ago[0] > 0 else 0) + FATIGUE[1] * sum(1 for v in ago[1:5] if v > 0)
    return 100 - min(cut, FATIGUE[2])


def mvp_team_factor(pct, second) -> int:
    tf = 40 if pct <= 500 else 100 if pct >= 750 else 40 + (pct - 500) * 60 // 250
    return tf + (10 if pct >= second else 0)


def offense_award(s, ref, pct) -> int:
    if not ref:
        return 0
    tf = 100 if pct >= 750 else 80 if pct <= 500 else 80 + (pct - 500) * 20 // 250
    return offense_points(s) * 10 // ref * tf // 100


def all_pro_score(s, pct) -> int:
    pos, cat = s["pos"], AP_CATEGORY[s["pos"]]
    if cat == "QB":
        return offense_points(s)
    if cat in ("HB", "WR", "TE"):
        return offense_award(s, OPOY_REF.get(pos, 0), pct)
    if cat == "FB":
        return offense_points(s) + 1
    if cat in ("T", "G", "C"):
        if s.get("games", 0) < 12:
            return 0
        return _pos0(int(s.get("overall", 0.0) * 1000.0) - 10 * s.get("sacks_allowed", 0))
    if cat == "K":
        fga, fgm = s.get("fga", 0), s.get("fgm", 0)
        return _pos0(fgm) * 1000 // fga * fgm if fga >= 10 else 0
    if cat == "P":
        punts = s.get("punts", 0)
        return _pos0(s.get("punt_yds", 0)) * 100 // punts if punts >= 40 else 0
    return defense_points(s) * ROLE_WEIGHT[pos] // 100


def second_best(records) -> int:
    """records: the first 32 clubs' (w, l, t) in index order; the second-best win percentage (1 when it is 0)."""
    best = second = 0
    for rec in records:
        pct = win_pct1000(rec)
        if pct > best:
            second, best = best, pct
        elif pct > second:
            second = pct
    return second or 1


def choose_awards(players, record, clubs=None) -> dict:
    """The native vote on plain data. ``players``: the league in the game's iteration order (club by club, the active list
    then injured reserve), mappings with ``pos`` (code), ``team`` (club index), ``yrs``, the season stats (pass_yds, pass_td,
    pass_int, rush_yds, rush_td, rec, rec_yds, rec_td, tackles, sacks2, def_int, ff, qbh) and optionally ``mvp_ago``,
    ``games``, ``overall``, ``sacks_allowed``, ``fgm``, ``fga``, ``punts``, ``punt_yds``. ``record(team) -> (w, l, t)``;
    ``clubs``: club indices 0..31 present (default: those seen). Returns {award: player or None, "all_pro": {cat: [..]}}."""

    clubs = sorted(set(p["team"] for p in players)) if clubs is None else clubs
    second = second_best([record(c) for c in clubs if c < 32])

    def best(pairs):
        pick, top = None, 0
        for pl, sc in pairs:
            if sc > top:
                pick, top = pl, sc
        return pick

    rows = [p for p in players if p["pos"] <= 16]
    mvp = best((p, mvp_base(p) * mvp_team_factor(win_pct1000(record(p["team"])), second) * fatigue(p.get("mvp_ago"))
                // 10000) for p in rows if p["pos"] not in NOT_VOTED)
    opoy = best((p, offense_award(p, OPOY_REF.get(p["pos"], 0), win_pct1000(record(p["team"]))))
                for p in rows if p["pos"] in OFFENSE and p is not mvp)
    dpoy = best((p, defense_points(p) * ROLE_WEIGHT[p["pos"]] // 100) for p in rows if p["pos"] in DEFENSE and p is not mvp)
    rookies = [p for p in rows if p.get("yrs") == 1]
    oroy = best((p, offense_award(p, OROY_REF.get(p["pos"], 0), win_pct1000(record(p["team"]))))
                for p in rookies if p["pos"] in OFFENSE)
    droy = best((p, defense_points(p) * ROLE_WEIGHT[p["pos"]] // 100) for p in rookies if p["pos"] in DEFENSE)
    return {"mvp": mvp, "opoy": opoy, "dpoy": dpoy, "oroy": oroy, "droy": droy, "all_pro": all_pro(rows, record)}


def all_pro(players, record) -> dict:
    """{category: [players]} in the AP shape; the native keeps the first strictly higher score and never a man twice."""
    size = dict(ALL_PRO)
    table = {c: [] for c, _n in ALL_PRO}
    for p in players:
        if p["team"] >= 32:
            continue
        cat = AP_CATEGORY[p["pos"]]
        score = all_pro_score(p, win_pct1000(record(p["team"])))
        row = table[cat]
        if any(q is p for _s, q in row) or score <= 0:
            continue
        place = next((i for i, (s, _q) in enumerate(row) if score > s), len(row))
        if place < size[cat]:
            row.insert(place, (score, p))
            del row[size[cat]:]
    return {c: [q for _s, q in table[c]] for c, _n in ALL_PRO}


def credit_weights(defenders, stat, cb_bonus=True):
    """The credit's draw weights for one club-game: ``defenders`` = [(role, rating)] of the men who played (role in CB S LB
    DE DT, rating = the stat's derived attribute 0..1); returns the probability of each man per unit. Native floats are
    single precision with x87 intermediates, so the twin matches the native draw in distribution, not bit for bit."""

    key = "tackles_with_cb" if stat == "tackles" and cb_bonus else stat
    roles = ("CB", "S", "LB", "DE", "DT")
    share = dict(zip(roles, CREDIT_SHARES[key]))
    power = CREDIT_POWER[stat]
    v = [max(r, 0.05) ** power for _role, r in defenders]
    role_sum = {}
    for (role, _r), x in zip(defenders, v):
        role_sum[role] = role_sum.get(role, 0.0) + x
    present = sum(share[r] for r in role_sum)
    if not present:
        return [0.0] * len(defenders)
    w = [share[role] / present * x / role_sum[role] for (role, _r), x in zip(defenders, v)]
    if stat == "interceptions":
        backs = [i for i, (role, _r) in enumerate(defenders) if role in ("CB", "S")]
        if backs:
            top = backs[0]
            for i in backs:
                if v[i] > v[top]:
                    top = i
            w = [x * (1 - BEST_COVER_SHARE) for x in w]
            w[top] += BEST_COVER_SHARE
    total = sum(w)
    return [x / total for x in w]


__all__ = ["OWNER", "REQUESTS", "HELP_TEXT", "CODE_SIZE", "CODE_VA", "AwardsError", "code_for", "labels", "sites", "status",
           "owned_state", "applied_sites", "read_settings", "reservations", "install", "apply", "guard_digests",
           "choose_awards", "all_pro", "credit_weights", "offense_points", "defense_points", "CREDIT_SHARES"]
