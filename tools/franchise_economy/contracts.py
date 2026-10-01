"""DESIGN: fit cited annual cap schedules to the native five-field contract.

This is a cap-accounting approximation. Guarantees are never treated as a
signing bonus. Exact cap hits, cash, void years and guarantees remain in the
source ledger; the game cannot represent them all independently.
"""
from __future__ import annotations

import math

from mod_editor.core.nfl2k5_practice_squad import contract_base_salary, contract_bonus_salary

FIELDS = frozenset(("contract_value", "contract_length", "contract_remaining",
                    "contract_type", "contract_bonus"))
SCALE = 4


def charges(fields: dict[str, int]) -> list[int]:
    """PROVED OFFLINE: host port of E6040 + E6020, amounts in game $1000."""
    value, kind, bonus, length, remaining = (fields[k] for k in
        ("contract_value", "contract_type", "contract_bonus", "contract_length", "contract_remaining"))
    return [contract_base_salary(value, kind, bonus, year, length)
            + contract_bonus_salary(value, bonus, length)
            for year in range(length - remaining, length)]


def fit_schedule(cap_dollars: list[int], *, scale: int = SCALE, opening_priority: bool = False) -> dict:
    """DESIGN: fit remaining cap hits, emphasizing the opening-year charge.

    The encoded total is remaining cap liability, not the original deal's
    headline value. Retain that distinction in every import receipt.
    """
    if not cap_dollars or len(cap_dollars) > 15:
        raise ValueError("one to fifteen consecutive cap years are required")
    if type(scale) is not int or scale < 1:
        raise ValueError("scale must be a positive integer")
    if any(type(v) is not int or v <= 0 for v in cap_dollars):
        raise ValueError("cap hits must be positive integer dollars, without missing years")
    target = [v / (1000 * scale) for v in cap_dollars]
    n = len(target)
    best = None
    weights = [16] + [1] * (n - 1)
    for kind in range(8):
        for bonus in range(8):
            base = dict(contract_value=10000, contract_type=kind, contract_bonus=bonus,
                        contract_length=n, contract_remaining=n)
            factors = [v / 10000 for v in charges(base)]
            value = (target[0] / factors[0] if opening_priority else
                     sum(w * f * t for w, f, t in zip(weights, factors, target)) / sum(
                         w * f * f for w, f in zip(weights, factors)))
            if value > 65535.5:
                continue
            for units in range(max(1, math.floor(value) - 3), min(65535, math.ceil(value) + 3) + 1):
                fields = {**base, "contract_value": units}
                actual = charges(fields)
                loss = sum(w * (a - t) ** 2 for w, a, t in zip(weights, actual, target))
                # A balanced deal with no synthetic bonus wins identical fits.
                key = ((max(0, abs(actual[0] - target[0]) - 5), loss, bonus, kind != 2, kind, units)
                       if opening_priority else (loss, bonus, kind != 2, kind, units))
                if best is None or key < best[0]:
                    best = (key, fields, actual)
    if best is None:
        raise ValueError("contract exceeds the native 16-bit total-value field")
    _, fields, actual = best
    real = [v * 1000 * scale for v in actual]
    return {"evidence": "DESIGN", "fields": fields, "source_cap_dollars": cap_dollars,
            "represented_cap_dollars": real, "errors_dollars": [a - b for a, b in zip(real, cap_dollars)],
            "meaning": "remaining cap liability fitted to native curves; not cash or guaranteed money"}


def fit_minimum(minimum_dollars: int, *, scale: int = SCALE) -> dict:
    """Smallest legal one-year charge, never nearest-fit below the floor.

    With length=remaining=1 every supported curve has its midpoint at year
    zero. Base plus annual bonus therefore equals value*10 game thousands.
    A one-year contract's charge lattice is $10,000*scale, not the formatter's
    $1,000*scale lattice. Balanced/no bonus expresses that floor directly.
    """
    if type(minimum_dollars) is not int or minimum_dollars <= 0 or type(scale) is not int or scale < 1:
        raise ValueError("minimum and scale must be positive integers")
    quantum = 10000 * scale
    units = (minimum_dollars + quantum - 1) // quantum
    if units > 65535:
        raise ValueError("minimum exceeds the native 16-bit total-value field")
    fields = dict(contract_value=units,contract_length=1,contract_remaining=1,contract_type=2,contract_bonus=0)
    actual = charges(fields)[0] * 1000 * scale
    assert actual >= minimum_dollars and actual - quantum < minimum_dollars
    return dict(evidence="DESIGN",fields=fields,source_cap_dollars=[minimum_dollars],
                represented_cap_dollars=[actual],errors_dollars=[actual-minimum_dollars],
                minimum_floor_dollars=minimum_dollars,charge_quantum_dollars=quantum,
                meaning="smallest representable one-year charge at or above minimum; years pro proxies credited seasons")
