#!/usr/bin/env python3
"""Adversarial unit tests for the APF instruction-budget postprocessor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/apf_instrument_guest_instruction_budget.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("apf_budget_tool", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source(body: str) -> str:
    return (
        '#include "ppc_recomp_shared.h"\n\n'
        '__attribute__((alias("__imp__sub_84630000"))) '
        'PPC_WEAK_FUNC(sub_84630000);\n'
        'PPC_FUNC_IMPL(__imp__sub_84630000) {\n'
        '\tPPC_FUNC_PROLOGUE();\n' + body + '}\n'
    )


def expect_rejected(module, path: Path, mappings: dict[str, int]) -> None:
    try:
        module.parse_source(path, mappings)
    except module.InstrumentationError:
        return
    raise AssertionError(f"adversarial source was accepted: {path}")


def main() -> int:
    module = load_tool()
    mappings = {"sub_84630000": 0x84630000}
    with tempfile.TemporaryDirectory(prefix="apf-budget-parser-") as raw:
        directory = Path(raw)
        good = directory / "good.cpp"
        output = directory / "good.instrumented.cpp"
        good.write_text(source(
            '\tuint32_t ea{};\n'
            '\t// li r3,1\n'
            '\tctx.r3.s64 = 1;\n'
            'loc_84630004:\n'
            '\t// blr \n'
            '\treturn;\n'), encoding="utf-8")
        parsed = module.parse_source(good, mappings)
        assert len(parsed.function_symbols) == 1
        assert [item.address for item in parsed.markers] == [
            0x84630000, 0x84630004]
        hooks, _ = module.instrument_source(good, output, parsed, mappings)
        audited, _ = module.audit_instrumented(good, output, parsed.markers)
        assert hooks == audited == 2
        lines = output.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.startswith("\t// "):
                assert lines[index + 1].startswith(
                    "\tVC_APF_GUEST_INSTRUCTION_STEP(")

        missing = directory / "missing.cpp"
        missing.write_text(source("\treturn;\n"), encoding="utf-8")
        expect_rejected(module, missing, mappings)

        late_prologue = directory / "late-prologue.cpp"
        late_prologue.write_text(source(
            '\t// li r3,1\n'
            '\tctx.r3.s64 = 1;\n'
            '\tPPC_FUNC_PROLOGUE();\n'), encoding="utf-8")
        expect_rejected(module, late_prologue, mappings)

        pre_effect = directory / "pre-effect.cpp"
        pre_effect.write_text(source(
            '\tctx.r3.s64 = 7;\n'
            '\t// blr \n'
            '\treturn;\n'), encoding="utf-8")
        expect_rejected(module, pre_effect, mappings)

        bad_label = directory / "bad-label.cpp"
        bad_label.write_text(source(
            'loc_84630004:\n'
            '\t// blr \n'
            '\treturn;\n'), encoding="utf-8")
        expect_rejected(module, bad_label, mappings)

        preinstrumented = directory / "preinstrumented.cpp"
        preinstrumented.write_text(source(
            '\t// blr \n'
            '\tVC_APF_GUEST_INSTRUCTION_STEP(0x84630000u);\n'
            '\treturn;\n'), encoding="utf-8")
        expect_rejected(module, preinstrumented, mappings)

        error_annotation = directory / "error-annotation.cpp"
        error_annotation.write_text(source(
            '\t// b 0x84630008\n'
            '\t// ERROR 84630008\n'
            '\treturn;\n'), encoding="utf-8")
        parsed_error = module.parse_source(error_annotation, mappings)
        assert len(parsed_error.markers) == 1

        portme_annotation = directory / "portme-annotation.cpp"
        portme_annotation.write_text(source(
            '\t// frsqrte f0,f1\n'
            '\t// PORTME(0x84630000): bounded semantic caveat.\n'
            '\tctx.f0.u64 = ctx.f1.u64;\n'), encoding="utf-8")
        parsed_portme = module.parse_source(portme_annotation, mappings)
        assert len(parsed_portme.markers) == 1

        corrupted = directory / "corrupted.cpp"
        corrupted.write_text(output.read_text(encoding="utf-8").replace(
            "0x84630004u", "0x84630008u", 1), encoding="utf-8")
        try:
            module.audit_instrumented(good, corrupted, parsed.markers)
        except module.InstrumentationError:
            pass
        else:
            raise AssertionError("corrupted hook address was accepted")

    print(
        "APF_INSTRUCTION_BUDGET_INSTRUMENTER_TEST_PASS "
        "positive=1 immediate=2 rejected=5 annotations=2 "
        "corruption_rejected=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
