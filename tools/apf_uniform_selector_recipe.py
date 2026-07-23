#!/usr/bin/env python3
"""Emit the one admitted APF 2K8 deterministic built-in all-family recipe."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import apf_uniform_selector_patch as writer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path, help="new recipe path")
    args = parser.parse_args(argv)
    try:
        allocation, _raw, _capacity, _capacity_raw = writer.load_authorities()
        payload = writer.transport.canonical_json_bytes(writer.expected_recipe(allocation))
        with args.json.open("xb") as descriptor:
            descriptor.write(payload)
        print(payload.decode("utf-8"), end="")
        return 0
    except (writer.PatchError, writer.transport.PatchError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
