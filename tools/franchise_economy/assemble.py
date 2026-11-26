"""DESIGN: reproduce the bounded economy replacements with GNU i386 tools.

PROVED OFFLINE: rejects oversized sections and unresolved symbols. No retail
code is emitted by this generator; the owner contains only input hashes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.franchise_economy.contracts import fit_schedule

TARGET = ROOT / "mod_editor/core/nfl2k5_franchise_economy_code.py"
# b81 revision 10: unreferenced retail functions (tools/franchise_economy/dead_code.py WINDOWS) for the revision's code
# and tables, and the input sections each one takes.
R10_WINDOWS = {"r10_5de10": (0x5de10, 84),
               "r10_87dc0": (0x87dc0, 88),
               "r10_8e150": (0x8e150, 83),
               "r10_975a0": (0x975a0, 123),
               "r10_c4930": (0xc4930, 83),
               "r10_f3300": (0xf3300, 85),
               "r10_10d210": (0x10d210, 82),
               "r10_118a40": (0x118a40, 100),
               "r10_12e110": (0x12e110, 82),
               "r10_1b6cb0": (0x1b6cb0, 93),
               "r10_224420": (0x224420, 104),
               "r10_25dee0": (0x25dee0, 87),
               "r10_2b3f40": (0x2b3f40, 214),
               "r10_31efa0": (0x31efa0, 103),
               "r10_328ce0": (0x328ce0, 89),
               "r10_332940": (0x332940, 82),
               "r10_347f40": (0x347f40, 82),
               "r10_351d60": (0x351d60, 82),
               "r10_39c3f0": (0x39c3f0, 81),
               "r10_3c8e00": (0x3c8e00, 107),
               "r10_3c98c0": (0x3c98c0, 108),
               "r10_3d3390": (0x3d3390, 81),
               "r10_121900": (0x121900, 84),
               "r10_17a480": (0x17a480, 84),
               "r10_256230": (0x256230, 109),
               "r10_26cb60": (0x26cb60, 84),
               "r10_2ec530": (0x2ec530, 84),
               "r10_2ee400": (0x2ee400, 85),
               "r10_3d62d0": (0x3d62d0, 83),
               "r10_3e1030": (0x3e1030, 104),
               "r10_ecce0": (0xecce0, 91),
               "r10_9ab90": (0x9ab90, 84),
               "r10_35b2f0": (0x35b2f0, 84),
               "r10_65380": (0x65380, 86),
               "r10_65940": (0x65940, 86),
               "r10_6f420": (0x6f420, 95),
               "r10_15e9d0": (0x15e9d0, 91),
               "r10_faa20": (0xfaa20, 94),
               "r10_25cc20": (0x25cc20, 94),
               "r10_28d4a0": (0x28d4a0, 94),
               "r10_329c50": (0x329c50, 94),
               "r10_31b000": (0x31b000, 93),
               "r10_36f380": (0x36f380, 93),
               "r10_250b70": (0x250b70, 92),
               "r10_1646e0": (0x1646e0, 88),
               "r10_1d12c0": (0x1d12c0, 88)}
# the input sections each window takes (value: economy_value's own bytes, placed before economy_floor's pin below)
R10_SECTIONS = {'r10_5de10': ['r10_casualty'],
                'r10_87dc0': ['r10_rank'],
                'r10_8e150': ['r10_tab_a'],
                'r10_975a0': ['r10_cuttable'],
                'r10_c4930': ['r10_usable'],
                'r10_f3300': ['r10_rscan'],
                'r10_10d210': ['r10_tab_e'],
                'r10_118a40': ['r10_reserve'],
                'r10_12e110': ['r10_tab_d'],
                'r10_1b6cb0': ['r10_age'],
                'r10_224420': ['r10_tab_c'],
                'r10_25dee0': ['r10_tier'],
                'r10_2b3f40': ['r10_camp', 'r10_overpay', 'r10_budget'],
                'r10_31efa0': ['r10_clear'],
                'r10_328ce0': ['r10_best'],
                'r10_332940': ['r10_tab_b'],
                'r10_347f40': ['r10_resign'],
                'r10_351d60': ['r10_most'],
                'r10_39c3f0': ['r10_ask'],
                'r10_3c8e00': ['r10_camp_pick'],
                'r10_3c98c0': ['r10_rank_club'],
                'r10_3d3390': ['r10_cell'],
                'years': ['r10_years'],
                'roster_b': ['r10_clamp'],
                'roster_d': ['r10_rollover'],
                'r10_121900': ['r10_bench'],
                'r10_17a480': ['r10_hole'],
                'r10_256230': ['r10_league'],
                'r10_26cb60': ['r10_each'],
                'r10_2ec530': ['r10_weakest'],
                'r10_2ee400': ['r10_could'],
                'r10_3d62d0': ['r10_seat_in'],
                'r10_3e1030': ['r10_pts'],
                'r10_ecce0': ['r10_count'],
                'r10_9ab90': ['r10_level'],
                'r10_35b2f0': ['r10_pool_man', 'r10_seat_pts'],
                'r10_65380': ['r10_low', 'r10_club_seats'],
                'r10_65940': ['r10_prove'],
                'r10_6f420': ['r10_rbest', 'r10_release'],
                'r10_15e9d0': ['r10_rcount'],
                'r10_faa20': ['r10_camp_ahead'],
                'r10_25cc20': ['r10_camp_keep'],
                'r10_28d4a0': ['r10_camp_one'],
                'r10_329c50': ['r10_hash'],
                'r10_31b000': ['r10_hole_room'],
                'r10_36f380': ['r10_camp_cut'],
                'r10_250b70': ['r10_camp_ok', 'r10_camp_fits'],
                'r10_1646e0': ['r10_camp_cover'],
                'r10_1d12c0': ['r10_camp_pos'],
                'roster_v': ['r10_holefirst']}
WINDOWS = {"value": (0x2BD440, 1082), "contracts": (0x3228A0, 215),
           "rookie": (0x322980, 280), "picks": (0x2BAB20, 403),
           "money": (0x31E580, 198), "reconcile": (0x2BFBE0, 370),
           # b778 fa2: the retail weekly CPU signing pass 0x323870..0x323A5F (one caller, 0x248010),
           # rebuilt in "week", and five unreferenced retail library functions (no encoding of any
           # address inside them anywhere in the image; tools/franchise_economy/dead_code.py).
           "week": (0x323870, 496), "roster_a": (0x396F50, 448), "roster_b": (0x3B9F60, 400),
           "roster_c": (0x3D2890, 352), "roster_d": (0x3BA4B0, 352), "roster_e": (0x3975F0, 224),
           # b779 rc1 (revision 4): one more unreferenced retail library function for the draft-class
           # record supply and position mix (dead_code.py WINDOWS).
           "roster_f": (0x382200, 192), "roster_g": (0x41E2A0, 192), "roster_h": (0x3A5F20, 192), "roster_i": (0x3BAB20, 192), "roster_j": (0x3E2310, 176), "roster_k": (0x3E9740, 160), "roster_l": (0x3E21D0, 160), "roster_m": (0x3DBC10, 160),
           # b780 econ3 (revision 7): one more unreferenced retail library function (dead_code.py WINDOWS).
           "roster_n": (0x3C0920, 537), "roster_o": (0x264AC0, 295),
           # b81 practice squads (revision 8): six more unreferenced retail functions (dead_code.py WINDOWS).
           "roster_p": (0x38D3E0, 143), "roster_q": (0x1C62E0, 156), "roster_r": (0x343040, 159),
           "roster_s": (0x3E9A90, 142), "roster_t": (0x3E9CD0, 134),
           "roster_u": (0x3220B0, 131),
           # b81 team building (revision 9): economy_room_for_signing, one routine every CPU free-agent signing's
           # affordability reads (the team-building wishes; the economy lane's revision 10 changes only its body).
           "roster_v": (0x2D82F0, 110),
           # b81 revision 10: the retail "years wanted" routine 0x322690 (its four callers keep calling its entry, which
           # now answers from economy_years) and the revision's code and tables in unreferenced retail functions
           # (tools/franchise_economy/dead_code.py WINDOWS; R10_WINDOWS below names them).
           "years": (0x322690, 133), **{name: window for name, window in R10_WINDOWS.items()}}
# b778 fa2: retail routines the C code calls directly (rel32 instead of mov/call reg).
NATIVE = {"n_rating": 0x246D80, "n_recount": 0xC3F00, "n_human": 0x13EC30, "n_team": 0xC4C50,
          "n_teams": 0xC4BE0, "n_roster_limit": 0x247AF0, "n_salary": 0xE6380, "n_base": 0xE6040,
          "n_prorated": 0xE6020, "n_frand": 0x48B90, "n_rand": 0x48B50, "n_trunc": 0x322260,
          "n_release": 0x2BD900, "n_cpu_sign": 0x322BB0, "n_cut_to": 0x2BF9A0, "n_need_low": 0x2BD880, "n_prune": 0x2BB9A0,
          "n_need_want": 0x2BD8C0, "n_at_position": 0xC3CB0, "n_minimum_at": 0x2BD410,
          "n_wanted_at": 0x2BD400,
          # b81 practice squads (revision 8): the free-agent list's remove-by-value and append, the active list's
          # append (the squad's ps_append when the practice squad is installed) and remove-by-value.
          "n_fa_remove": 0x2425C0, "n_fa_add": 0x242560, "n_append": 0xC3EE0, "n_remove": 0xC3EB0,
          "n_ir_return": 0x246F90, "n_next_class": 0x2BF8B0}
# b81 (revision 8): the practice squad's fixed ABI entries (its pinned caves; the roster arena bridges them).
from mod_editor.core.nfl2k5_practice_squad_runtime import SYMBOLS as _SQUAD  # noqa: E402
NATIVE.update({"ps_append": _SQUAD["ps_append"], "ps_demote": _SQUAD["ps_demote"],
               "retail_fa_add": _SQUAD["retail_fa_add"]})   # re-check R1: the put-back with no ownership test
# b81 revision 10: symbols other owners or the native code reach at fixed addresses inside a window (not its first
# byte): they must not move (the team-building owner calls economy_cap; the practice-squad composition chains to
# economy_fill_gate).
STABLE = {"economy_floor": 0x2BD65C, "economy_penalty": 0x2BD68F, "economy_cap": 0x2BD6D7, "economy_fill_gate": 0x31E605,
          # b81 r10: the stage stubs keep their revision 3-9 addresses (the hook sites 0x248628 and 0x24809C keep their bytes)
          "economy_after": 0x323A1F, "economy_stage6": 0x323A2F}
# Entry points that must sit at their window's first byte.
ENTRIES = {"economy_value": 0x2BD440, "economy_contract": 0x3228A0, "economy_rookie": 0x322980,
           "economy_pick": 0x2BAB20, "economy_money": 0x31E580, "economy_week": 0x323870,
           "economy_reconcile": 0x2BFBE0, "economy_room_for_signing": 0x2D82F0, "economy_years_entry": 0x322690}
# PROVED OFFLINE: the first seven words at the retail pick-index base also
# belong to Player Contracts' last action row. Only retire the values after it.
ROOKIE_TABLE_VA = 0x521598
ROOKIE_TABLE_SIZE = 224
POSITION_MARKET = ("quarterback", "kicker", "punter", "wide-receiver", "cornerback", "safety", "safety",
                   "running-back", "fullback", "tight-end", "linebacker", "linebacker", "center", "guard",
                   "left-tackle", "interior-defensive-line", "edge-rusher")


def inputs():
    data = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
    market = {r["url"].rsplit("/", 1)[1]: sum(v["apy"] for v in r["rows"]) / len(r["rows"])
              for r in data["market"]}
    top = [round(market[p] / 4000) for p in POSITION_MARKET]
    floor = [v // 1000 for v in data["minimums"]["dollars"]]
    chart = data["draft_chart"]["values"]
    deltas = [a - b for a, b in zip(chart[1:], chart[2:])]
    assert len(deltas) == 222 and all(0 <= d <= 255 for d in deltas)
    fits = []
    for row in data["rookie_anchors"]["rows"]:
        if len(row.get("cap_hits", [])) != 4:
            continue
        fit = fit_schedule([r["cap_number"] for r in row["cap_hits"]])
        f = fit["fields"]
        fits.append({"pick": row["pick"], "value": f["contract_value"],
                     "curve": f["contract_type"] | f["contract_bonus"] << 4,
                     "errors_dollars": fit["errors_dollars"]})
    if not fits or fits[0]["pick"] != 1 or fits[-1]["pick"] < 224:
        raise ValueError("rookie knots must cover the entire native draft")
    table = b"".join(bytes((r["pick"], r["curve"])) + r["value"].to_bytes(2, "little") for r in fits)
    if len(table) > ROOKIE_TABLE_SIZE:
        raise ValueError("rookie knots exceed the retired pick table")
    return data, top, floor, deltas, fits, table.ljust(ROOKIE_TABLE_SIZE, b"\0")


def r10_tables(data):
    """b81 revision 10: the price curve, aging, ask, length and reserve tables from data/nfl2k5_franchise_economy.json."""
    r = data["revision_10"]
    price = r["price"]
    scale, ranks, groups = price["price_scale"], price["ranks"], price["groups"]
    # 0.1% of the cap at scale 1.0 (a byte holds the top QB's 24.5%); price_of applies the scale (11/25: 1.05 > 1.0)
    curve = [[round(1000 * v) for v in price["market_curve_capshare"][g]] for g in groups]
    assert all(0 < v <= 255 for row in curve for v in row) and all(a >= b for row in curve for a, b in zip(row, row[1:]))
    scale_pct = round(100 * scale)
    assert abs(scale_pct - 100 * scale) < 1e-9 and 50 <= scale_pct <= 200
    years = []
    for band in r["lengths"]["bands"]:
        for tier in r["lengths"]["tiers"]:
            mix = {int(k): v for k, v in r["lengths"]["by_age_and_price"][band][tier]["length_pct"].items()}
            total, run, cum = sum(mix.values()), 0.0, []
            for length in range(1, 6):
                run += mix.get(length, 0.0)
                cum.append(min(256, round(256 * run / total)))
            years.append(cum)
    tables = [("u8", "price_group", price["position_group"], "r10_tab_a"),
              ("u8", "price_ranks", ranks, "r10_tab_a"),
              ("u8", "decline_age", r["aging"]["decline_age"], "r10_tab_a"),
              ("u8", "reserve_pm", r["reserve"]["permille"], "r10_tab_a"),
              ("u8", "ask_decay", r["asks"]["decay_256_by_unsigned_weeks"][1:], "r10_tab_a"),   # weeks 1..7 (week 0: 256)
              ("u8", "price_curve_a", [v for row in curve[:5] for v in row], "r10_tab_b"),
              ("u8", "price_curve_b", [v for row in curve[5:10] for v in row], "r10_tab_d"),
              ("u8", "price_curve_c", [v for row in curve[10:] for v in row], "r10_tab_e"),
              ("u8", "years_cum", [min(v, 255) for row in years for v in row[:4]], "r10_tab_c")]
    header = "\n".join(f'const {typ} {name}[] SECTION(".{sec}") __attribute__((aligned(1))) = '
                       + "{" + ",".join(map(str, values)) + "};" for typ, name, values, sec in tables)
    header += f"\n#define PRICE_KNOTS {len(ranks)}\n#define PRICE_SCALE_PCT {scale_pct}u\n"
    return header


def generate():
    data, top, floor, deltas, fits, table = inputs()
    arrays = [("u16", "market", top, "rookie"), ("u16", "minimums", floor, "value"),
              ("u8", "decline_after", data["model"]["decline_after_years_pro"], "value"),
              ("u8", "pick_deltas", deltas, "picks")]
    header = "\n".join(f'const {typ} {name}[] SECTION(".{sec}_rodata") __attribute__((aligned(1))) = '
                       + "{" + ",".join(map(str, values)) + "};" for typ, name, values, sec in arrays)
    header += f"\n#define ROOKIE_COUNT {len(fits)}\nstruct rookie_row {{ u8 pick, curve; u16 value; }};\n"
    header += f"#define ROOKIE_TABLE_VA {ROOKIE_TABLE_VA:#x}\n"
    header += r10_tables(data) + "\n"
    with tempfile.TemporaryDirectory(prefix="fc-assemble-") as tmp:
        d = Path(tmp)
        (d / "generated_tables.h").write_text(header)
        obj, elf = d / "runtime.o", d / "runtime.elf"
        subprocess.run(["gcc", "-m32", "-Os", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie",
                        "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
                        "-fno-jump-tables", "-mpreferred-stack-boundary=2", "-mno-sse", "-mno-mmx",
                        "-Wall", "-Wextra", "-Werror", "-I", str(d), "-I", str(ROOT / "tools/common"), "-c",
                        str(ROOT / "tools/franchise_economy/runtime.c"), "-o", str(obj)], check=True)
        script = "SECTIONS {\n" + "\n".join(
            f".{name} {address:#x} : {{ *(.{name}) *(.{name}_rodata) }}"
            for name, (address, _) in WINDOWS.items())
        # Compiler-generated float constants are read-only and belong to value.
        script = script.replace("*(.value_rodata)", "*(.penalty) *(.cap) *(.offer_room) *(.renew_room) *(.value_rodata) *(.rodata*)")
        # b81 revision 10: the new price's helpers follow economy_value inside its old 540 bytes; economy_floor (the
        # first .penalty routine) stays at its address (ld refuses a location counter that would move backwards).
        script = script.replace("*(.value) *(.penalty)", "*(.value) *(.r10_value) . = 0x21C; *(.penalty)")
        for name, sections in R10_SECTIONS.items():
            script = script.replace(f"*(.{name}_rodata)", f"*(.{name}_rodata) " + " ".join(f"*(.{x})" for x in sections))
        script = script.replace("*(.reconcile_rodata)", "*(.fill_room)")
        script = script.replace("*(.contracts_rodata)", "*(.offer_gate) *(.renew_gate)")
        script = script.replace("*(.money_rodata)", "*(.fill_gate)")
        # b779 vs1: the transaction-years display stub shares the picks window's spare bytes.
        script = script.replace("*(.picks_rodata)", "*(.txn_years) *(.picks_rodata)")
        # b780 b4-economy: the two stage stubs follow economy_week (which must start the window) in their own
        # input section, so gcc's function order inside .week cannot move them in front of it.
        script = script.replace("*(.week_rodata)", "*(.week_rodata) . = 0x1AF; *(.week_tail)")   # b81 r10: the stubs keep their addresses
        # b780 hunt1: economy_cover follows roster_h's read-only byte (economy_floor_protected stays at its address).
        script = script.replace("*(.roster_h_rodata)", "*(.roster_h_rodata) *(.roster_h_tail)")
        # b780 econ3 (revision 7): economy_need follows economy_best_room, which keeps its address.
        script = script.replace("*(.roster_c_rodata)", "*(.roster_c_rodata) *(.roster_c_tail)")
        script += "\n/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n"
        # fastcall/stdcall decorations: @name@N / _name@N / plain cdecl names.
        script += "".join(f"{name} = {address:#x};\n" for name, address in NATIVE.items())
        (d / "link.ld").write_text(script)
        subprocess.run(["ld", "-m", "elf_i386", "-T", str(d / "link.ld"), "-o", str(elf), str(obj)], check=True)
        symbol_text = subprocess.check_output(["nm", "-n", str(elf)], text=True)
        symbols = {line.split()[2]: int(line.split()[0], 16) for line in symbol_text.splitlines()
                   if len(line.split()) == 3}
        for name, address in ENTRIES.items():
            if symbols.get(name) != address:
                raise ValueError(f"{name} must start its window at {address:#x}")
        for name, address in STABLE.items():
            if symbols.get(name) != address:
                raise ValueError(f"{name} moved to {symbols.get(name, 0):#x}; it must stay at {address:#x}")
        blobs = {}
        for name, (_address, limit) in WINDOWS.items():
            path = d / (name + ".bin")
            subprocess.run(["objcopy", "-O", "binary", "--only-section=." + name, str(elf), str(path)], check=True)
            code = path.read_bytes()
            if not code or len(code) > limit:
                raise ValueError(f"{name}: {len(code)} bytes, capacity {limit}")
            blobs[name] = code
    lines = ['"""DESIGN: generated original code; reproduce with tools/franchise_economy/assemble.py."""',
             "", "WINDOWS = {"]
    for name, code in blobs.items():
        address, limit = WINDOWS[name]
        lines += [f"    {address:#x}: (  # {name}: {len(code)}/{limit} bytes", "        bytes.fromhex("]
        lines += ['            "' + code[i:i + 40].hex() + '"' for i in range(0, len(code), 40)]
        lines += [f'        ).ljust({limit}, b"\\xcc")', "    ),"]
    lines += ["}", f"ROOKIE_TABLE_VA = {ROOKIE_TABLE_VA:#x}", "ROOKIE_TABLE = bytes.fromhex("]
    lines += ['    "' + table[i:i + 40].hex() + '"' for i in range(0, len(table), 40)]
    lines += [")", "SYMBOLS = " + repr({k: v for k, v in symbols.items() if k.startswith("economy_")}), ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    result = generate()
    if args.check:
        if TARGET.read_text() != result:
            raise SystemExit("economy code template is stale")
    else:
        TARGET.write_text(result)
    print("PROVED OFFLINE: economy template reproduced")


if __name__ == "__main__":
    main()
