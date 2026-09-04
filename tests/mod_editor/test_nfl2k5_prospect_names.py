"""Modern draft-prospect names: CSV rules, the pool layout and rewrite, the executable cave, both halves.

Offline tests rebuild the retail name pool from the module's embedded lists (which reproduces the pinned
retail digest byte for byte) and use a synthetic ROST resource in the XDVDFS fixture.  Tests on the retail
roster need the private extraction (loose packs); the executable tests need the retail default.xbe; the
cave run needs unicorn.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_prospect_names as pn  # noqa: E402
from mod_editor.core import nfl2k5_team_history as th  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

RETAIL_EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"
RETAIL_XBE = RETAIL_EXTRACTION / "default.xbe"
HAVE_RETAIL = (RETAIL_EXTRACTION / "vc_53450030" / "0").is_file()
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
BASE = 0x10000


# --------------------------------------------------------------------------------------------- synthetic roster
def retail_rows() -> list[pn.NameRow]:
    return [pn.NameRow(index=i, first=pn.RETAIL_FIRSTS[i], last=pn.RETAIL_LASTS[i]) for i in range(pn.POOL_COUNT)]


def synthetic_body() -> bytes:
    """A ROST body carrying only the retail name pool, laid out exactly as the retail resource (interleaved
    first0, last0, first1, ... from 0x8B7D0): its pool digest is the pinned retail digest."""

    body = bytearray(pn.BODY_SIZE)
    body[0x0C:0x10] = b"ROST"
    struct.pack_into("<I", body, 0x10, 17)
    struct.pack_into("<I", body, pn.HEADER_COUNT_OFF, pn.POOL_COUNT)
    struct.pack_into("<i", body, pn.HEADER_ARRAY_OFF, pn.ARRAY_OFF - pn.HEADER_ARRAY_OFF + 1)
    cursor = pn.STRINGS_START
    for i in range(pn.POOL_COUNT):
        field = pn.ARRAY_OFF + i * 8
        for k, text in enumerate((pn.RETAIL_FIRSTS[i], pn.RETAIL_LASTS[i])):
            encoded = text.encode("utf-16-le") + b"\0\0"
            body[cursor: cursor + len(encoded)] = encoded
            struct.pack_into("<i", body, field + k * 4, cursor - (field + k * 4) + 1)
            cursor += len(encoded)
    assert cursor == pn.STRINGS_END
    return bytes(body)


def synthetic_resource(body: bytes) -> bytes:
    header = b"ROST" + struct.pack("<II", pn.BODY_SIZE, pn.BODY_SIZE) + bytes(pn.RESOURCE_HEADER_SIZE - 12)
    return header + body


def csv_text(rows, *, index: bool = True, header: str | None = None) -> str:
    lines = [header or ("index,first,last" if index else "first,last")]
    for r in rows:
        lines.append(f"{r.index},{r.first},{r.last}" if index else f"{r.first},{r.last}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------- csv + layout
class CsvTests(unittest.TestCase):
    def test_shipped_csv_is_pinned_attributed_and_lays_out_within_budget(self) -> None:
        self.assertTrue(pn.SHIPPED_CSV.is_file())
        data = pn.SHIPPED_CSV.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), pn.SHIPPED_CSV_SHA256)
        text = data.decode("utf-8")
        self.assertIn("nflverse", text.splitlines()[1])
        self.assertIn("CC-BY-4.0", text)
        rows, provenance = pn.load_rows("modern")
        self.assertEqual(provenance["source"], "modern")
        self.assertEqual(len(rows), pn.POOL_COUNT)
        layout = pn.plan_layout(rows)
        self.assertEqual((len(layout.retained), len(layout.replaced)), (433, 52))
        self.assertLessEqual(layout.bytes_used, pn.BUDGET)
        self.assertEqual(layout.boundary, pn.SHIPPED_BOUNDARY)
        self.assertEqual(pn.SHIPPED_BOUNDARY, pn.STRINGS_START + sum(pn.encoded_size(pn.RETAIL_LASTS[i]) for i in layout.retained))
        for r in rows:
            for name in (r.first, r.last):
                self.assertTrue(name and name.isascii() and len(name) <= pn.MAX_NAME_CHARS, name)
        self.assertEqual(len({r.first for r in rows}), pn.POOL_COUNT, "first names are unique")
        self.assertEqual(len({r.last for r in rows}), pn.POOL_COUNT, "surnames are unique")
        # the audio column says what the layout says
        audio = [line.split(",")[3] for line in text.splitlines() if line and not line.startswith("#")][1:]
        self.assertEqual(audio, ["retail" if r.retained else "number" for r in rows])
        # the study's flagged surnames are the replaced ones; the modern replacements are unknown to the bank
        self.assertTrue(all(pn.RETAIL_LASTS[i] in ("Garcia", "Martinez", "Rodriguez", "Lopez", "Horsley", "Hamre", "Zdyrko") or i in layout.replaced
                            for i in (17, 18, 21, 30, 171, 257, 483)))
        self.assertTrue(all(rows[i].last not in pn.RETAIL_LASTS for i in layout.replaced))
        self.assertIn("Christopher", {r.first for r in rows})
        self.assertIn("prospect_names", mod_build.availability())

    def test_index_is_optional_and_headers_are_case_insensitive(self) -> None:
        rows = retail_rows()
        self.assertEqual(pn.read_csv(csv_text(rows, index=False)), rows)
        self.assertEqual(pn.read_csv(csv_text(rows, header="Index,First,Last")), rows)
        shuffled = list(reversed(rows))
        self.assertEqual(pn.read_csv("# a comment\n\n" + csv_text(shuffled)), rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mine.csv"
            path.write_bytes(b"\xef\xbb\xbf" + csv_text(rows).encode("utf-8"))
            loaded, provenance = pn.load_rows(path)
            self.assertEqual((loaded, provenance["source"]), (rows, "custom"))
            with self.assertRaises(pn.ProspectNamesError):
                pn.load_rows(Path(tmp) / "missing.csv")

    def test_csv_validation_edge_cases(self) -> None:
        rows = retail_rows()

        def bad(text: str, message: str) -> None:
            with self.assertRaises(pn.ProspectNamesError, msg=message) as ctx:
                pn.read_csv(text)
            self.assertIn(message, str(ctx.exception))

        bad("", "no rows")
        bad("first,surname\nA,B\n", "lacks the columns")
        bad(csv_text(rows[:-1]), "484 rows")
        bad(csv_text(rows + [pn.NameRow(485, "Extra", "Row")]), "outside 0..484")
        bad(csv_text(rows[:-1] + [pn.NameRow(0, "Dup", "Index")]), "appears twice")
        bad(csv_text(rows[:-1] + [pn.NameRow(0, "Dup", "Index")], index=False)[:-1].replace("\n", "\n", 1) + "\nMore,Rows\n", "486 rows")
        bad(csv_text(rows).replace("0,James,Smith", "x,James,Smith"), "bad index")
        bad(csv_text(rows).replace("0,James,Smith", "0,,Smith"), "empty name")
        bad(csv_text(rows).replace("0,James,Smith", "0,José,Smith"), "not ASCII")
        bad(csv_text(rows).replace("0,James,Smith", "0,Bartholomewson,Smith"), "longer than 12")
        bad(csv_text(rows).replace("0,James,Smith", "0,James,Sm1th"), "may only use letters")
        bad(csv_text(rows).replace("0,James,Smith", "0,James,'Neal"), "must start with a letter")
        ok = pn.read_csv(csv_text(rows).replace("0,James,Smith", "0,T.J.,O'Brien-Lee"))
        self.assertEqual((ok[0].first, ok[0].last), ("T.J.", "O'Brien-Lee"))
        self.assertEqual(pn.validate_name("  Jalen ", "x"), "Jalen")

    def test_layout_rules_boundary_budget_and_log(self) -> None:
        retail = pn.plan_layout(retail_rows())
        self.assertEqual((len(retail.retained), len(retail.replaced)), (pn.POOL_COUNT, 0))
        self.assertEqual(retail.boundary, pn.STRINGS_START + sum(pn.encoded_size(n) for n in pn.RETAIL_LASTS))
        self.assertEqual(retail.bytes_used, pn.BUDGET)
        self.assertTrue(all("kept" in line for line in retail.log))
        replaced_all = pn.plan_layout([pn.NameRow(i, "Al", pn.RETAIL_LASTS[i] + "x") for i in range(pn.POOL_COUNT)])
        self.assertEqual((replaced_all.boundary, len(replaced_all.retained), len(replaced_all.replaced)), (pn.STRINGS_START, 0, pn.POOL_COUNT))
        self.assertTrue(all("announced by number" in line or "first" in line for line in replaced_all.log))
        # retained surnames go first whatever their index; replacements after the boundary; every first name after that
        rows = retail_rows()
        rows[0] = pn.NameRow(0, "Jalen", "Diggs")
        mixed = pn.plan_layout(rows)
        first0, last0 = struct.unpack_from("<ii", mixed.array, 0)
        self.assertGreaterEqual(pn.ARRAY_OFF + 4 + last0 - 1, mixed.boundary)
        self.assertEqual(pn.ARRAY_OFF + 4 + last0 - 1, mixed.boundary, "the first replacement sits exactly at the boundary")
        self.assertGreater(pn.ARRAY_OFF + first0 - 1, mixed.boundary)
        _first1, last1 = struct.unpack_from("<ii", mixed.array, 8)
        self.assertEqual(pn.ARRAY_OFF + 8 + 4 + last1 - 1, pn.STRINGS_START, "the first retained surname opens the span")
        self.assertIn("  0: last 'Smith' -> 'Diggs' (announced by number)", mixed.log)
        self.assertIn("  0: first 'James' -> 'Jalen'", mixed.log)
        with self.assertRaises(pn.ProspectNamesError) as ctx:
            pn.plan_layout([pn.NameRow(i, "Bartholomews", "Bartholomews") for i in range(pn.POOL_COUNT)])
        self.assertIn("more than the pool's", str(ctx.exception))
        with self.assertRaises(pn.ProspectNamesError):
            pn.plan_layout(rows[:-1])


# --------------------------------------------------------------------------------------------- the pool
class SyntheticPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = synthetic_body()
        cls.rows, _prov = pn.load_rows("modern")
        cls.patched, cls.receipt = pn.apply_body(cls.body, cls.rows)

    def test_retail_pin_is_reproducible_from_the_embedded_lists(self) -> None:
        self.assertEqual(pn.pool_digest(self.body), pn.RETAIL_POOL_SHA256)
        self.assertEqual(pn.body_status(self.body), "retail")
        pool = pn.parse_pool(self.body)
        self.assertEqual((pool.firsts, pool.lasts), (pn.RETAIL_FIRSTS, pn.RETAIL_LASTS))
        self.assertEqual(pool.entries[0], (0x8B7D0, 0x8B7DC))
        self.assertEqual(self.body[pn.ARRAY_OFF: pn.ARRAY_OFF + 8], bytes.fromhex("1d88010025880100"))
        self.assertEqual(pn.boundary_range(self.body), (pn.STRINGS_END, pn.STRINGS_END))

    def test_rewrite_keeps_every_retained_surname_at_its_index_and_touches_nothing_else(self) -> None:
        self.assertEqual(pn.body_status(self.patched), "applied")
        self.assertEqual(pn.pool_digest(self.patched), pn.SHIPPED_POOL_SHA256)
        self.assertEqual(self.receipt["boundary"], pn.SHIPPED_BOUNDARY)
        self.assertEqual((self.receipt["retained"], self.receipt["replaced"]), (433, 52))
        self.assertEqual((self.receipt["bytes_before"], self.receipt["budget"]), (pn.BUDGET, pn.BUDGET))
        self.assertLessEqual(self.receipt["bytes_used"], pn.BUDGET)
        pool = pn.parse_pool(self.patched)
        layout = pn.plan_layout(self.rows)
        for i in layout.retained:
            self.assertEqual(pool.lasts[i], pn.RETAIL_LASTS[i], i)
            self.assertLess(pool.entries[i][1], layout.boundary)
        for i in layout.replaced:
            self.assertNotEqual(pool.lasts[i], pn.RETAIL_LASTS[i], i)
            self.assertGreaterEqual(pool.entries[i][1], layout.boundary)
        self.assertTrue(all(pool.entries[i][0] >= layout.boundary for i in range(pn.POOL_COUNT)), "first names sit after the boundary")
        self.assertEqual(pn.boundary_range(self.patched), (layout.boundary, layout.boundary))
        self.assertEqual(self.patched[pn.HEADER_COUNT_OFF: pn.HEADER_ARRAY_OFF + 4], self.body[pn.HEADER_COUNT_OFF: pn.HEADER_ARRAY_OFF + 4])
        changed = {i for i, (a, b) in enumerate(zip(self.body, self.patched)) if a != b}
        allowed = set(range(pn.ARRAY_OFF, pn.ARRAY_OFF + pn.ARRAY_SIZE)) | set(range(pn.STRINGS_START, pn.STRINGS_END))
        self.assertTrue(changed <= allowed)
        self.assertTrue(all(pool.firsts) and all(pool.lasts))
        self.assertEqual(self.patched[pn.STRINGS_START + self.receipt["bytes_used"]: pn.STRINGS_END], bytes(pn.BUDGET - self.receipt["bytes_used"]))
        # the canonical roster parser (what Text & Rosters reads) still walks the pool by the header pair
        import nfl_roster

        tables = nfl_roster.parse_tables(self.patched, pn.OBJ_OFF, pn.ROST_OUTER_INDEX)
        self.assertEqual((tables["generated_names"]["count"], tables["generated_names"]["offset"]), (pn.POOL_COUNT, pn.ARRAY_OFF))
        for i in range(pn.POOL_COUNT):
            _p, first = nfl_roster.string_pointer(self.patched, pn.ARRAY_OFF + i * 8, "first")
            _p, last = nfl_roster.string_pointer(self.patched, pn.ARRAY_OFF + i * 8 + 4, "last")
            self.assertEqual((first, last), (self.rows[i].first, self.rows[i].last), i)
        self.assertEqual(len(self.receipt["log"]), 485 + sum(1 for r in self.rows if r.first != pn.RETAIL_FIRSTS[r.index]))

    def test_custom_rewrites_and_foreign_pools(self) -> None:
        rows = retail_rows()
        rows[10] = pn.NameRow(10, "Jalen", "Diggs")
        custom, receipt = pn.apply_body(self.body, rows)
        self.assertEqual(pn.body_status(custom), "custom")
        self.assertEqual((receipt["retained"], receipt["replaced"]), (484, 1))
        self.assertEqual(pn.boundary_range(custom), (receipt["boundary"], receipt["boundary"]))
        again, _r = pn.apply_body(self.body, self.rows)
        self.assertEqual(again, self.patched, "the rewrite is deterministic")
        tampered = bytearray(self.patched)
        struct.pack_into("<I", tampered, pn.HEADER_COUNT_OFF, pn.POOL_COUNT + 1)
        self.assertEqual(pn.body_status(bytes(tampered)), "foreign")
        with self.assertRaises(pn.ProspectNamesError):
            pn.apply_body(bytes(tampered), self.rows)
        tampered = bytearray(self.patched)
        struct.pack_into("<i", tampered, pn.ARRAY_OFF, 0x7FFF)                      # a pointer past the span
        self.assertEqual(pn.body_status(bytes(tampered)), "foreign")
        tampered = bytearray(self.patched)
        tampered[pn.STRINGS_START: pn.STRINGS_START + 2] = b"\0\0"                  # an empty string
        self.assertEqual(pn.body_status(bytes(tampered)), "foreign")
        self.assertEqual(pn.body_status(b"\0" * 64), "foreign")
        self.assertEqual(pn.resource_status(b"ROST" + bytes(60)), "foreign")
        self.assertEqual(pn.resource_status(synthetic_resource(self.patched)), "applied")

    def test_apply_through_the_image_writer(self) -> None:
        from nfl2k5_xiso_fixture import SyntheticXiso

        resource = synthetic_resource(self.body)
        with tempfile.TemporaryDirectory() as tmp:
            dummies = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(5)]
            fixture = SyntheticXiso(Path(tmp), dummies + [(5, resource), (200, b"TAIL" + bytes(0x100))], pack_sizes=(0xA0000,), pack_sectors=(64,))
            self.assertEqual(pn.status(fixture.path), "retail")
            receipt = pn.apply(fixture.path, "modern")
            self.assertEqual((receipt["status"], receipt["boundary"], receipt["source"]), ("applied", pn.SHIPPED_BOUNDARY, "modern"))
            self.assertEqual((receipt["retained"], receipt["replaced"]), (433, 52))
            self.assertEqual(pn.status(fixture.path), "applied")
            with pn._rost._outer_image()(fixture.path) as archive:
                entry = pn._rost._entry(archive)
                written = archive.read(entry.virtual_offset, entry.size)
            self.assertEqual(written, resource[:pn.RESOURCE_HEADER_SIZE] + self.patched)
            again = pn.apply(fixture.path, "modern")
            self.assertTrue(again.get("already_applied"))
            self.assertEqual(again["boundary"], pn.SHIPPED_BOUNDARY)
            # other names on an already rewritten pool: refused
            other = Path(tmp) / "other.csv"
            other.write_text(csv_text(retail_rows()), encoding="utf-8")
            with self.assertRaises(pn.ProspectNamesError):
                pn.apply(fixture.path, other)
            # the fixture's 16-byte default.xbe stub is no executable: the image as a whole is not "applied"
            self.assertIn(pn.image_status(fixture.path), ("foreign", "partial"))
            # a foreign pool (count word changed) is refused
            with pn._rost._outer_image()(fixture.path, writable=True) as archive:
                entry = pn._rost._entry(archive)
                archive.write(entry.virtual_offset + pn.RESOURCE_HEADER_SIZE + pn.HEADER_COUNT_OFF, struct.pack("<I", 486))
            self.assertEqual(pn.status(fixture.path), "foreign")
            with self.assertRaises(pn.ProspectNamesError):
                pn.apply(fixture.path, "modern")

    def test_combined_status_needs_both_halves(self) -> None:
        b = pn.SHIPPED_BOUNDARY
        self.assertEqual(pn.combined_status("retail", "retail", None, None), "retail")
        self.assertEqual(pn.combined_status("applied", "applied", b, (b, b)), "applied")
        self.assertEqual(pn.combined_status("custom", "applied", 0x8C000, (0x8BF00, 0x8C100)), "applied-custom")
        self.assertEqual(pn.combined_status("applied", "applied", b + 2, (b, b)), "foreign")        # baked boundary disagrees
        self.assertEqual(pn.combined_status("custom", "applied", 0x8C200, (0x8BF00, 0x8C100)), "foreign")
        self.assertEqual(pn.combined_status("applied", "applied", None, (b, b)), "foreign")
        for pool_state, xbe_state in (("applied", "retail"), ("custom", "retail"), ("retail", "applied")):
            self.assertEqual(pn.combined_status(pool_state, xbe_state, b, (b, b)), "partial", (pool_state, xbe_state))
        self.assertEqual(pn.combined_status("foreign", "applied", b, (b, b)), "foreign")
        self.assertEqual(pn.combined_status("applied", "foreign", b, (b, b)), "foreign")
        self.assertEqual(pn.combined_status("retail", "foreign", None, None), "foreign")


# --------------------------------------------------------------------------------------------- the cave (offline)
class CaveShapeTests(unittest.TestCase):
    def test_cave_bytes_hook_and_boundary_round_trip(self) -> None:
        cave = pn.cave_bytes(pn.SHIPPED_BOUNDARY)
        self.assertEqual(len(cave), pn.HOST_SIZE)
        self.assertEqual(pn.HOST_SIZE, 27)
        self.assertEqual(len(pn.RETAIL_HOST), 27)
        self.assertEqual(pn.PATCHED_HOOK, b"\xe8" + struct.pack("<i", pn.HOST_VA - (pn.HOOK_VA + 5)) + b"\x90")
        self.assertEqual(len(pn.PATCHED_HOOK), pn.HOOK_SIZE)
        self.assertEqual(pn._cave_boundary(cave), pn.SHIPPED_BOUNDARY)
        self.assertEqual(struct.unpack_from("<I", cave, pn.BOUNDARY_IMM_OFFSET)[0], pn.SHIPPED_BOUNDARY - pn.OBJ_OFF)
        self.assertIn(pn.RETAIL_HOOK, cave)                                       # the retail add edx,0x2454 survives inside
        self.assertEqual(cave[-6:], b"\xba" + struct.pack("<I", pn.NUMBER_AUDIO_ID) + b"\xc3")
        self.assertEqual(pn.NUMBER_AUDIO_ID, 9100)
        self.assertEqual(pn.RETAIL_AUDIO_BASE, 9300)
        for boundary in (pn.STRINGS_START, pn.STRINGS_END, pn.SHIPPED_BOUNDARY):
            self.assertEqual(pn._cave_boundary(pn.cave_bytes(boundary)), boundary)
        for bad in (pn.STRINGS_START - 2, pn.STRINGS_END + 2, 0):
            with self.assertRaises(pn.ProspectNamesError):
                pn.cave_bytes(bad)
        self.assertIsNone(pn._cave_boundary(pn.RETAIL_HOST))
        self.assertIsNone(pn._cave_boundary(cave[:-1] + b"\x90"))
        self.assertEqual(pn.HOST_VA, 0xB4A70)
        self.assertEqual(pn.HOST_VA + pn.HOST_SIZE, 0xB4A8B)                      # up to the routine's `ret 8`
        from mod_editor.core import nfl2k5_penalties as pen
        self.assertEqual(pen.HOST_VA + pen.HOST_SIZE, pn.HOST_VA, "the two stubs share the dead routine without overlapping")

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_cave_disassembles_as_designed_and_writes_no_memory(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_MEM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        insns = list(md.disasm(pn.cave_bytes(pn.SHIPPED_BOUNDARY), pn.HOST_VA))
        text = [f"{i.mnemonic} {i.op_str}".strip() for i in insns]
        self.assertEqual(text, [f"mov eax, dword ptr [0x{pn.ROSTER_GLOBAL:x}]", f"add eax, 0x{pn.SHIPPED_BOUNDARY - pn.OBJ_OFF:x}",
                                "cmp ecx, eax", f"jae 0x{pn.HOST_VA + 21:x}", "add edx, 0x2454", "ret",
                                f"mov edx, 0x{pn.NUMBER_AUDIO_ID:x}", "ret"])
        self.assertEqual(sum(len(i.bytes) for i in insns), pn.HOST_SIZE)
        writes = [f"{i.mnemonic} {i.op_str}" for i in insns if i.operands and i.operands[0].type == X86_OP_MEM]
        self.assertEqual(writes, [])
        hook = [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(pn.PATCHED_HOOK, pn.HOOK_VA)]
        self.assertEqual(hook, [f"call 0x{pn.HOST_VA:x}", "nop"])

    def test_junk_payloads_are_foreign(self) -> None:
        self.assertEqual(pn.xbe_status(b"XBEH" + b"\0" * 0x200), "foreign")
        self.assertIsNone(pn.xbe_boundary(b"XBEH" + b"\0" * 0x200))
        with self.assertRaises(pn.ProspectNamesError):
            pn.xbe_apply(b"XBEH" + b"\0" * 0x200, pn.SHIPPED_BOUNDARY)


# --------------------------------------------------------------------------------------------- wiring (offline)
class WiringTests(unittest.TestCase):
    def test_build_plan_presets_availability_and_refusals(self) -> None:
        self.assertEqual(mod_build.PRESETS["softdrink_basic"]["prospect_names"], "")
        self.assertEqual(mod_build.PRESETS["softdrink_advanced"]["prospect_names"], "modern")
        self.assertEqual(mod_build.PRESETS["softdrink_experimental"]["prospect_names"], "modern")
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertEqual(plan.prospect_names, "modern")
        self.assertIn("prospect_names", plan.to_recipe())
        self.assertTrue(mod_build.BuildPlan(source="s", target="t", prospect_names="modern").wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").wants_xbe_patch())
        self.assertTrue(mod_build.availability()["prospect_names"])
        from mod_editor.core import modpack

        self.assertIn("nflverse", modpack.describe_operation({"op": "prospect_names", "source": "modern"}))
        self.assertIn("custom", modpack.describe_operation({"op": "prospect_names", "source": "custom"}))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "default.xbe"
            src.write_bytes(b"XBEH" + bytes(64))
            with self.assertRaises(ValueError):
                mod_build.build(mod_build.BuildPlan(source=str(src), target=str(Path(tmp) / "out.xbe"), prospect_names="modern"))
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "default.xbe"
            src.write_bytes(_build_synthetic_xbe())
            state = mod_build.inspect(src)
            self.assertEqual(state["prospect_names"], "foreign", "the throw fixture models no generator: foreign, never applied")
            report = tt.read_any(src)
            self.assertEqual(report["prospect_names"], "foreign")
        adapter = tt._prospect_names_adapter("")
        self.assertEqual(adapter.boundary(), pn.SHIPPED_BOUNDARY)
        self.assertEqual(tt._prospect_names_adapter("modern").boundary(), pn.SHIPPED_BOUNDARY)
        with self.assertRaises(tt.ThrowTuningError):
            tt._apply_all(b"XBEH" + bytes(0x200), None, catch_slider=False, prospect_names="modern")

    def test_panels_carry_the_toggle_and_the_csv_field(self) -> None:
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import NEEDS_IMAGE, PATCHES, STRING_TOGGLES, GameplayPatchesPanel

        app = QApplication.instance() or QApplication([])   # noqa: F841
        keys = [k for k, _l, _e in PATCHES]
        self.assertGreater(keys.index("prospect_names"), keys.index("penalties"))   # after penalties (jerseys/laces merged in between)
        self.assertEqual(STRING_TOGGLES["prospect_names"], "modern")
        self.assertIn("prospect_names", NEEDS_IMAGE)
        panel = BuildPanel()
        try:
            panel.apply_state({"path": "x.iso", "container": "xiso", "prospect_names": "retail", "throw": None})
            self.assertTrue(panel.prospect_names_check.isEnabled())
            panel.apply_state({"path": "default.xbe", "container": "xbe", "prospect_names": "retail", "throw": None})
            self.assertFalse(panel.prospect_names_check.isEnabled())
            panel.apply_state({"path": "x.iso", "container": "xiso", "prospect_names": "partial", "throw": None})
            self.assertFalse(panel.prospect_names_check.isEnabled())
            panel.apply_state({"path": "x.iso", "container": "xiso", "prospect_names": "retail", "throw": None})
            self.assertEqual(panel.plan().prospect_names, "")
            panel.prospect_names_check.setChecked(True)
            self.assertEqual(panel.plan().prospect_names, "modern")
            panel.prospect_names_field.setText("/tmp/my_names.csv")
            self.assertEqual(panel.plan().prospect_names, "/tmp/my_names.csv")
            self.assertTrue(panel.has_work())
            self.assertIn("prospect_names", panel.apply_preset("softdrink_advanced")["applied"])
        finally:
            panel.deleteLater()
        gameplay = GameplayPatchesPanel()
        try:
            gameplay.apply_state({"path": "default.xbe", "container": "xbe", "prospect_names": "retail"})
            self.assertFalse(gameplay.checks["prospect_names"].isEnabled())
            self.assertEqual(gameplay.checks["prospect_names"].toolTip(), "Needs a disc image.")
            gameplay.apply_state({"path": "x.iso", "container": "xiso", "prospect_names": "retail"})
            self.assertTrue(gameplay.checks["prospect_names"].isEnabled())
            gameplay.checks["prospect_names"].setChecked(True)
            self.assertEqual(gameplay.plan().prospect_names, "modern")
            gameplay.apply_state({"path": "x.iso", "container": "xiso", "prospect_names": "partial"})
            self.assertFalse(gameplay.checks["prospect_names"].isEnabled())
            self.assertIn("one half", gameplay.checks["prospect_names"].toolTip())
        finally:
            gameplay.deleteLater()
        app.processEvents()


# --------------------------------------------------------------------------------------------- the retail roster
@unittest.skipUnless(HAVE_RETAIL, "private retail extraction not present")
class RetailPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with pn._rost._outer_image()(RETAIL_EXTRACTION) as archive:
            entry = pn._rost._entry(archive)
            cls.resource = archive.read(entry.virtual_offset, entry.size)
        cls.body = cls.resource[pn.RESOURCE_HEADER_SIZE:]
        cls.rows, _prov = pn.load_rows("modern")
        cls.patched, cls.receipt = pn.apply_body(cls.body, cls.rows)

    def test_retail_pool_facts_and_round_trip(self) -> None:
        self.assertEqual(pn.body_status(self.body), "retail")
        self.assertEqual(pn.status(RETAIL_EXTRACTION), "retail")
        self.assertEqual(self.body[pn.ARRAY_OFF: pn.ARRAY_OFF + 8], bytes.fromhex("1d88010025880100"))
        self.assertEqual(self.body[pn.STRINGS_START - 0x110: pn.STRINGS_START], bytes(0x110), "the 68 spare records' empty names")
        self.assertEqual(self.body[pn.STRINGS_END: pn.STRINGS_END + 12], "49ers\0".encode("utf-16-le"), "the team nicknames follow the pool")
        self.assertEqual(self.body[pn.ARRAY_OFF: pn.STRINGS_END] [:0] , b"")
        pool = pn.parse_pool(self.body)
        self.assertEqual((pool.firsts, pool.lasts), (pn.RETAIL_FIRSTS, pn.RETAIL_LASTS))
        self.assertEqual(self.body[pn.STRINGS_START - 0x110: pn.STRINGS_END], synthetic_body()[pn.STRINGS_START - 0x110: pn.STRINGS_END])
        self.assertEqual(pn.body_status(self.patched), "applied")
        self.assertEqual(self.receipt["boundary"], pn.SHIPPED_BOUNDARY)
        after = pn.parse_pool(self.patched)
        for i in range(pn.POOL_COUNT):
            self.assertEqual((after.firsts[i], after.lasts[i]), (self.rows[i].first, self.rows[i].last), i)
            if self.rows[i].retained:
                self.assertEqual(after.lasts[i], pn.RETAIL_LASTS[i])
        changed = {i for i, (a, b) in enumerate(zip(self.body, self.patched)) if a != b}
        self.assertTrue(changed <= set(range(pn.ARRAY_OFF, pn.ARRAY_OFF + pn.ARRAY_SIZE)) | set(range(pn.STRINGS_START, pn.STRINGS_END)))
        # nothing else in the roster references the string span: the 970 array pointers are the only ones (the
        # scan skips UTF-16 text inside the span and the non-pointer fields of the player records, whose packed
        # audio-id/face word at +0x04 can look like a relative pointer; +0x10/+0x14 ARE their name pointers)
        roster = th.parse_body(self.body)
        players_lo, players_hi = roster.players_off, roster.players_off + roster.player_count * th.PLAYER_SIZE
        refs = []
        for off in range(0, len(self.body) - 4, 4):
            value = struct.unpack_from("<i", self.body, off)[0]
            target = off + value - 1
            if not value or not (pn.STRINGS_START <= target < pn.STRINGS_END) or target & 1:
                continue
            if pn.ARRAY_OFF <= off < pn.ARRAY_OFF + pn.ARRAY_SIZE or pn.STRINGS_START <= off < pn.STRINGS_END:
                continue
            if players_lo <= off < players_hi and (off - players_lo) % th.PLAYER_SIZE not in (0x10, 0x14):
                continue
            refs.append((hex(off), hex(target)))
        self.assertEqual(refs, [])
        # the Text & Rosters parser reads the rewritten pool
        import nfl_roster

        tables = nfl_roster.parse_tables(self.patched, pn.OBJ_OFF, pn.ROST_OUTER_INDEX)
        self.assertEqual(tables["generated_names"]["count"], pn.POOL_COUNT)
        self.assertEqual(tables["primary_players"]["count"], 2479)
        self.assertEqual(nfl_roster.string_pointer(self.patched, pn.ARRAY_OFF + 4, "last")[1], "Smith")

    def test_digest_gate_order_with_the_other_roster_passes(self) -> None:
        import dataclasses

        import nfl2k5_franchise_schedule as fs
        import nfl2k5_roster_reclassify as rr

        # reclassify: hashes the header and the player records; the name pool is outside both, so the two
        # passes commute (its edits leave our digest alone, ours leaves its digest alone)
        self.assertEqual(rr.status(RETAIL_EXTRACTION)["status"], "retail")
        with pn._rost._outer_image()(RETAIL_EXTRACTION) as archive:
            main = rr.load_resources(archive, historic=False)[0]
        if dataclasses.is_dataclass(main):
            self.assertEqual(rr.record_digest([dataclasses.replace(main, body=self.patched)]), rr.record_digest([main]))
        roster = th.parse_body(self.body)
        moved = bytearray(self.body)
        for p in roster.players[:50]:
            moved[p.offset + rr.PLAYER_POSITION] ^= 0x01
            struct.pack_into("<H", moved, p.offset + rr.PLAYER_ORDER_WORD, 0x155)
        self.assertEqual(pn.body_status(bytes(moved)), "retail")
        out, _r = pn.apply_body(bytes(moved), self.rows)
        self.assertEqual(pn.body_status(out), "applied")
        # team history: the history pool and the +0x2C words; ours keeps its status and it keeps ours
        history_rows, _p = th.load_rows("retail")
        with_history, _r = th.apply_body(self.body, history_rows)
        self.assertEqual(th.body_status(with_history), "applied")
        self.assertEqual(pn.body_status(with_history), "retail")
        both, _r = pn.apply_body(with_history, self.rows)
        self.assertEqual((th.body_status(both), pn.body_status(both)), ("applied", "applied"))
        self.assertEqual(th.body_status(self.patched), "retail")
        reverse, _r = th.apply_body(self.patched, history_rows)
        self.assertEqual(reverse, both, "the two passes commute byte for byte")
        # schedule: the tail and the header pair at ROST+0x60
        fake = bytearray(fs.PACK_ROST_OFFSET) + self.resource
        self.assertEqual(fs.pack_status(bytes(fake))["state"], "retail")
        fake_after_ours = bytearray(fs.PACK_ROST_OFFSET) + self.resource[:pn.RESOURCE_HEADER_SIZE] + self.patched
        self.assertEqual(fs.pack_status(bytes(fake_after_ours))["state"], "retail")
        doc = __import__("json").loads((ROOT / "data" / "nfl_2026_schedule.json").read_text(encoding="utf-8"))
        template, _info = fs.encode_schedule(doc)
        preseason, _pinfo = fs.encode_preseason(doc) if hasattr(fs, "encode_preseason") else (b"", {})
        scheduled, _rec = fs.apply_pack(bytes(fake), template, preseason=preseason)
        self.assertEqual(fs.pack_status(scheduled)["state"], "applied")
        body_after_schedule = scheduled[fs.PACK_ROST_OFFSET + pn.RESOURCE_HEADER_SIZE: fs.PACK_ROST_OFFSET + pn._rost.RESOURCE_SIZE]
        self.assertEqual(pn.body_status(body_after_schedule), "retail")
        ours, _r = pn.apply_body(body_after_schedule, self.rows)
        both = scheduled[: fs.PACK_ROST_OFFSET + pn.RESOURCE_HEADER_SIZE] + ours + scheduled[fs.PACK_ROST_OFFSET + pn._rost.RESOURCE_SIZE:]
        self.assertEqual(fs.pack_status(both)["state"], "applied")
        self.assertEqual(pn.body_status(ours), "applied")


# --------------------------------------------------------------------------------------------- the retail executable
@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not present")
class RetailXbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()
        cls.patched, cls.receipt = pn.xbe_apply(cls.retail, pn.SHIPPED_BOUNDARY)

    def _off(self, va: int) -> int:
        return pn._offset(self.retail, va)

    def test_status_apply_idempotent_boundary_and_foreign(self) -> None:
        self.assertEqual(pn.xbe_status(self.retail), "retail")
        self.assertIsNone(pn.xbe_boundary(self.retail))
        self.assertEqual(pn.xbe_status(self.patched), "applied")
        self.assertEqual(pn.xbe_boundary(self.patched), pn.SHIPPED_BOUNDARY)
        self.assertEqual(self.receipt["boundary"], pn.SHIPPED_BOUNDARY)
        self.assertEqual(self.receipt["sections_repinned"], [0])
        self.assertEqual(self.receipt["changed_bytes"], sum(1 for a, b in zip(self.retail, self.patched) if a != b))
        hook, host = self._off(pn.HOOK_VA), self._off(pn.HOST_VA)
        self.assertEqual(self.retail[hook: hook + pn.HOOK_SIZE], pn.RETAIL_HOOK)
        self.assertEqual(self.retail[host: host + pn.HOST_SIZE], pn.RETAIL_HOST)
        self.assertEqual(self.retail[host + pn.HOST_SIZE: host + pn.HOST_SIZE + 5], pn.RETAIL_HOST_AFTER)
        self.assertEqual(self.patched[hook: hook + pn.HOOK_SIZE], pn.PATCHED_HOOK)
        self.assertEqual(self.patched[host: host + pn.HOST_SIZE], pn.cave_bytes(pn.SHIPPED_BOUNDARY))
        self.assertEqual(self.patched[host + pn.HOST_SIZE: host + pn.HOST_SIZE + 5], pn.RETAIL_HOST_AFTER)
        # every changed byte is the hook, the cave or the .text digest
        sites = {(hook, hook + pn.HOOK_SIZE), (host, host + pn.HOST_SIZE)}
        digests = {(s.header_offset + 36, s.header_offset + 56) for s in _sections(self.retail)}
        for i, (a, b) in enumerate(zip(self.retail, self.patched)):
            if a != b:
                self.assertTrue(any(lo <= i < hi for lo, hi in sites | digests), hex(i))
        for section in _sections(self.patched):
            d = section.header_offset + 36
            self.assertEqual(self.patched[d: d + 20], section_digest(self.patched, section), section.index)
        again, receipt2 = pn.xbe_apply(self.patched, pn.SHIPPED_BOUNDARY)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt2.get("already_applied"))
        with self.assertRaises(pn.ProspectNamesError):
            pn.xbe_apply(self.patched, pn.SHIPPED_BOUNDARY + 2)                 # another layout's boundary
        other, _r = pn.xbe_apply(self.retail, pn.STRINGS_START)
        self.assertEqual((pn.xbe_status(other), pn.xbe_boundary(other)), ("applied", pn.STRINGS_START))
        for va in (pn.HOOK_VA + 1, pn.HOST_VA + 1, pn.HOST_VA + pn.HOST_SIZE - 1, pn.HOOK_BEFORE_VA, pn.HOOK_AFTER_VA + 3, pn.HOST_AFTER_VA + 1):
            for base in (self.retail, self.patched):
                tampered = bytearray(base)
                tampered[self._off(va)] ^= 0x01
                self.assertEqual(pn.xbe_status(bytes(tampered)), "foreign", hex(va))
        with self.assertRaises(pn.ProspectNamesError):
            pn.xbe_apply(bytes(tampered), pn.SHIPPED_BOUNDARY)
        adapter = tt._prospect_names_adapter("modern")
        self.assertEqual(adapter.status(self.patched), "applied")
        self.assertEqual(adapter.status(other), "foreign", "the cave with another boundary is not this layout's")

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_penalties as pen
        from mod_editor.core import nfl2k5_position_row as row
        from mod_editor.core import nfl2k5_probowl_order as pb
        from mod_editor.core import nfl2k5_returner_fix as returner
        from mod_editor.core import nfl2k5_team_column as team_column

        a, receipt = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, team_column=True,
                                   position_row=True, probowl_order=True, penalties="nfl", prospect_names="modern")
        self.assertEqual(receipt["prospect_names_patch"]["boundary"], pn.SHIPPED_BOUNDARY)
        b, _ = pn.xbe_apply(self.retail, pn.SHIPPED_BOUNDARY)
        b, _ = pen.apply(b)
        b, _ = pb.apply(b)
        b, _ = team_column.apply(b)
        b, _ = row.apply(b)
        b, _ = returner.apply(b)
        self.assertEqual(a, b)
        self.assertEqual((pn.xbe_status(a), pen.status(a)), ("applied", "applied"))
        again, receipt2 = tt._apply_all(a, None, catch_slider=False, returner_fix=True, team_column=True,
                                        position_row=True, probowl_order=True, penalties="nfl", prospect_names="modern")
        self.assertEqual(again, a)
        self.assertTrue(receipt2["prospect_names_patch"].get("already_applied"))
        off, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, penalties="nfl")
        self.assertEqual(pn.xbe_status(off), "retail")
        # the shared dead routine: the penalties stub, then our cave, then the retail `ret 8` + padding
        host = self._off(pen.HOST_VA)
        self.assertEqual(a[host: host + pen.HOST_SIZE], pen.PATCHED_HOST)
        self.assertEqual(a[host + pen.HOST_SIZE: host + pen.HOST_SIZE + pn.HOST_SIZE], pn.cave_bytes(pn.SHIPPED_BOUNDARY))
        self.assertEqual(a[host + 0x2B: host + 0x30], pn.RETAIL_HOST_AFTER)

    def _text(self) -> tuple[int, int]:
        text = next(s for s in _sections(self.retail) if s.index == 0)
        return text.virtual_address, text.virtual_address + text.raw_size

    def test_the_host_is_unreferenced_in_the_retail_image(self) -> None:
        """The cave-reference scan on the host span plus the routine's padding (0xB4A70..0xB4A90): no rel32
        call/jump target, no push/mov immediate and no aligned .rdata/.data pointer lands on any byte."""

        lo, hi = pn.HOST_VA, 0x000B4A90
        data = self.retail
        text_lo, text_hi = self._text()
        hits = []
        for off in range(text_lo - BASE, text_hi - BASE - 5):
            op = data[off]
            if op in (0xE8, 0xE9):
                tgt = (BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                tgt = (BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]) & 0xFFFFFFFF
            else:
                continue
            if lo <= tgt < hi:
                hits.append(("rel", hex(BASE + off), hex(tgt)))
        for section in _sections(data):
            if section.index not in (0, 12, 13):
                continue
            step = 1 if section.index == 0 else 4
            raw, size = section.raw_offset, section.raw_size
            for off in range(raw, raw + size - 4, step):
                v = struct.unpack_from("<I", data, off)[0]
                if not (lo <= v < hi):
                    continue
                if section.index == 0:
                    prev = data[off - 1]
                    if not (prev == 0x68 or 0xB8 <= prev <= 0xBF or (data[off - 2] == 0xC7 and prev == 0x05)
                            or (data[off - 6] == 0xC7 and data[off - 5] == 0x05)):
                        continue
                hits.append(("ptr", section.index, hex(off), hex(v)))
        self.assertEqual(hits, [])
        # the hook itself is live code, reached by the generator's fall-through only (no jump lands inside the 6 bytes)
        inside = []
        for off in range(text_lo - BASE, text_hi - BASE - 5):
            op = data[off]
            if op in (0xE8, 0xE9):
                tgt = (BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                tgt = (BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]) & 0xFFFFFFFF
            else:
                continue
            if pn.HOOK_VA < tgt < pn.HOOK_VA + pn.HOOK_SIZE:
                inside.append(hex(BASE + off))
        self.assertEqual(inside, [])

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_no_neighbouring_instruction_jumps_into_the_host(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_IMM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        lo, hi = pn.HOST_VA, pn.HOST_VA + pn.HOST_SIZE
        # the live routine before the dead one (0xB4A30..0xB4A60) and the one after it (0xB4A90..0xB4AD0)
        for start, end in ((0xB4A30, 0xB4A60), (0xB4A90, 0xB4AD0)):
            for insn in md.disasm(self.retail[self._off(start): self._off(end)], start):
                for op in insn.operands:
                    if op.type == X86_OP_IMM and insn.group(1):      # CS_GRP_JUMP
                        self.assertFalse(lo <= op.imm < hi, f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")
        # the generator around the hook decodes as the study says: ecx from [eax+4], then the hook, then the store
        text = [f"{i.address:#x} {i.mnemonic} {i.op_str}" for i in md.disasm(self.retail[self._off(0x2BE7B5): self._off(0x2BE7D3)], 0x2BE7B5)]
        self.assertEqual(text[:3], ["0x2be7b5 mov ecx, dword ptr [eax + 4]", "0x2be7b8 add edx, 0x2454", "0x2be7be mov word ptr [esi + 4], dx"])
        self.assertEqual(text[-1], "0x2be7ce call 0xe6780")
        patched = [f"{i.address:#x} {i.mnemonic} {i.op_str}".strip() for i in md.disasm(self.patched[self._off(0x2BE7B5): self._off(0x2BE7C2)], 0x2BE7B5)]
        self.assertEqual(patched, ["0x2be7b5 mov ecx, dword ptr [eax + 4]", f"0x2be7b8 call 0x{pn.HOST_VA:x}", "0x2be7bd nop",
                                   "0x2be7be mov word ptr [esi + 4], dx"])

    # -- unicorn ------------------------------------------------------------------------------------
    STACK, SENTINEL, SCRATCH = 0x7FF00000, 0x0BADF000, 0x0BADE000

    def _run_hook(self, payload: bytes, surname_offset: int, index: int) -> int:
        """Run the generator from the hook through `mov [esi+4],dx` with ecx = the surname pointer of a roster
        whose body sits at SCRATCH and edx = the pool index; return the stored audio id."""
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(BASE, 0xEC0000 - BASE)
        uc.mem_write(BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for s in _sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        uc.mem_map(self.SCRATCH, 0x2000)
        uc.mem_write(pn.ROSTER_GLOBAL, struct.pack("<I", self.SCRATCH + pn.OBJ_OFF))    # the roster object = body + 0x40
        player = self.SCRATCH + 0x1000
        uc.reg_write(UC_X86_REG_ESI, player)
        uc.reg_write(UC_X86_REG_ECX, self.SCRATCH + surname_offset)
        uc.reg_write(UC_X86_REG_EDX, index)
        uc.reg_write(UC_X86_REG_EAX, 0xDEADBEEF)
        uc.reg_write(UC_X86_REG_ESP, self.STACK - 0x1000)
        stop = pn.HOOK_VA + pn.HOOK_SIZE + 4                                              # after `mov [esi+4],dx`
        uc.emu_start(pn.HOOK_VA, stop, count=100)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), stop)
        return struct.unpack("<H", bytes(uc.mem_read(player + 4, 2)))[0]

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_hook_keeps_audio_for_retained_surnames_and_numbers_the_rest(self) -> None:
        layout = pn.plan_layout(pn.load_rows("modern")[0])
        body, _r = pn.apply_body(synthetic_body(), layout.rows)
        pool = pn.parse_pool(body)
        retained, replaced = layout.retained[0], layout.replaced[0]
        self.assertEqual((retained, pn.RETAIL_LASTS[retained], replaced), (0, "Smith", 17))
        last_retained, first_replaced = layout.retained[-1], layout.replaced[-1]
        # patched: below the boundary keeps 9300 + index, at or above it stores 9100
        self.assertEqual(self._run_hook(self.patched, pool.entries[retained][1], retained), 9300 + retained)
        self.assertEqual(self._run_hook(self.patched, pool.entries[last_retained][1], last_retained), 9300 + last_retained)
        self.assertEqual(self._run_hook(self.patched, pool.entries[replaced][1], replaced), pn.NUMBER_AUDIO_ID)
        self.assertEqual(self._run_hook(self.patched, pool.entries[first_replaced][1], first_replaced), pn.NUMBER_AUDIO_ID)
        self.assertEqual(self._run_hook(self.patched, layout.boundary - 2, 400), 9300 + 400)
        self.assertEqual(self._run_hook(self.patched, layout.boundary, 400), pn.NUMBER_AUDIO_ID)
        # retail: 9300 + index whatever the pointer
        self.assertEqual(self._run_hook(self.retail, pool.entries[retained][1], retained), 9300 + retained)
        self.assertEqual(self._run_hook(self.retail, pool.entries[replaced][1], replaced), 9300 + replaced)
        # a cave whose boundary is the retail pool's own (every interleaved surname below the end of the span)
        # keeps every retail surname's audio; the shipped boundary on the retail pool would number the high
        # indices (what an old save's roster copy would get on the patched executable)
        retail_pool = pn.parse_pool(synthetic_body())
        self.assertEqual(pn.boundary_range(synthetic_body()), (pn.STRINGS_END, pn.STRINGS_END))
        kept, _r = pn.xbe_apply(self.retail, pn.STRINGS_END)
        self.assertEqual(self._run_hook(kept, retail_pool.entries[484][1], 484), 9300 + 484)
        self.assertEqual(self._run_hook(kept, retail_pool.entries[0][1], 0), 9300)
        self.assertEqual(self._run_hook(self.patched, retail_pool.entries[484][1], 484), pn.NUMBER_AUDIO_ID)
        self.assertEqual(self._run_hook(self.patched, retail_pool.entries[0][1], 0), 9300)


if __name__ == "__main__":
    unittest.main()
