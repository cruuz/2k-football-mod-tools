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
WINDOWS = {"value": (0x2BD440, 1082), "contracts": (0x3228A0, 215),
           "rookie": (0x322980, 280), "picks": (0x2BAB20, 403),
           "money": (0x31E580, 198), "reconcile": (0x2BFBE0, 370)}
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


def generate():
    data, top, floor, deltas, fits, table = inputs()
    arrays = [("u16", "market", top, "rookie"), ("u16", "minimums", floor, "value"),
              ("u8", "decline_after", data["model"]["decline_after_years_pro"], "value"),
              ("u8", "pick_deltas", deltas, "picks")]
    header = "\n".join(f'const {typ} {name}[] SECTION(".{sec}_rodata") __attribute__((aligned(1))) = '
                       + "{" + ",".join(map(str, values)) + "};" for typ, name, values, sec in arrays)
    header += f"\n#define ROOKIE_COUNT {len(fits)}\nstruct rookie_row {{ u8 pick, curve; u16 value; }};\n"
    header += f"#define ROOKIE_TABLE_VA {ROOKIE_TABLE_VA:#x}\n"
    with tempfile.TemporaryDirectory(prefix="fc-assemble-") as tmp:
        d = Path(tmp)
        (d / "generated_tables.h").write_text(header)
        obj, elf = d / "runtime.o", d / "runtime.elf"
        subprocess.run(["gcc", "-m32", "-Os", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie",
                        "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-fno-unwind-tables",
                        "-fno-jump-tables", "-mpreferred-stack-boundary=2", "-mno-sse", "-mno-mmx",
                        "-Wall", "-Wextra", "-Werror", "-I", str(d), "-c",
                        str(ROOT / "tools/franchise_economy/runtime.c"), "-o", str(obj)], check=True)
        script = "SECTIONS {\n" + "\n".join(
            f".{name} {address:#x} : {{ *(.{name}) *(.{name}_rodata) }}"
            for name, (address, _) in WINDOWS.items())
        # Compiler-generated float constants are read-only and belong to value.
        script = script.replace("*(.value_rodata)", "*(.penalty) *(.cap) *(.offer_room) *(.renew_room) *(.value_rodata) *(.rodata*)")
        script = script.replace("*(.reconcile_rodata)", "*(.fill_room)")
        script = script.replace("*(.contracts_rodata)", "*(.offer_gate) *(.renew_gate)")
        script = script.replace("*(.money_rodata)", "*(.fill_gate)")
        script += "\n/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n"
        (d / "link.ld").write_text(script)
        subprocess.run(["ld", "-m", "elf_i386", "-T", str(d / "link.ld"), "-o", str(elf), str(obj)], check=True)
        symbol_text = subprocess.check_output(["nm", "-n", str(elf)], text=True)
        symbols = {line.split()[2]: int(line.split()[0], 16) for line in symbol_text.splitlines()
                   if len(line.split()) == 3}
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
