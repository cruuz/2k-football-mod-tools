"""Synthetic art and real StudioSession imports; no game files required."""
from test_nfl2k5_equipment_texture_chain import *
from test_nfl2k5_equipment_import import EquipmentSessionTests
from mod_editor.core.nfl2k5_equipment_import import stage_equipment_import
from mod_editor.core import nfl2k5_equipment_lz as lz
import time
from test_b69_j1_fit import tight_fixture

class SizedFixture(Fixture):
    def __init__(self, root, *, width=256, family=4, margin=1000, names=None):
        self.width, self.height, self.count = width, width, 3
        if names is not None and len(names) != self.count:
            raise ValueError("synthetic equipment fixture names must match its three references")
        self.levels = 3
        system = 512
        chains = []
        for level in range(self.levels):
            w, h = self.width >> level, self.height >> level
            linear = bytes((x + y + level) % 8 for y in range(h) for x in range(w))
            chains.append(swizzle_2d(linear, w, h, 1))
        shared = b"".join(chains)
        self.chain_size = len(shared)
        video = bytearray(shared)
        palette_offsets = []
        for reference in range(self.count):
            if reference:
                video.extend(bytes((-len(video)) % 128))
            palette_offsets.append(len(video))
            video.extend(b"".join(bytes((i // 2, (i + reference * 30) % 256, i, 255))
                                  for i in range(256)))
        video.extend(b"Z" * ((-len(video)) % 128))  # preserve an opaque unused tail
        decoded = bytearray(system) + video
        struct.pack_into("<II", decoded, 0, 13, self.count)
        rows = []
        for reference, palette_offset in enumerate(palette_offsets):
            name = ("glove" if family == 6 else "shoes") + f"{reference + 1:02d}"
            if names is not None:
                name = names[reference]
            base = 0x18 + reference * 0x24
            name_at, descriptor = 128 + reference * 32, 256 + reference * 32
            decoded[base:base + 4] = b"TXTR"
            for field, target in ((base + 4, name_at), (base + 8, descriptor)):
                struct.pack_into("<i", decoded, field, target - field + 1)
            encoded_name = (name + "\0").encode("utf-16le")
            decoded[name_at:name_at + len(encoded_name)] = encoded_name
            packed = 0xB29 | self.levels << 16 | (width.bit_length() - 1) << 20 | (width.bit_length() - 1) << 24
            struct.pack_into("<6I", decoded, descriptor, 0, 0, palette_offset, packed, 0, 0x80000000)
            rows.append(writer.EquipmentTarget(
                0, "SYNTHETIC", family, reference, name, self.width, self.height,
                0, palette_offset, packed, 0, 0x80000000, digest(chains[0]),
                digest(video[palette_offset:palette_offset + 1024]),
            ))
        self.rows = tuple(rows)
        self.decoded = bytes(decoded)
        encoded, _ = compress_vc_lz(self.decoded, stream_tag=1, offset_bits=12)
        stored = (len(encoded) + margin + 15) & ~15
        self.span = HEADER.pack(b"TSET", stored, system, len(video), 0xFEEDBEEF,
                                stored, 0, 0) + encoded + bytes(stored - len(encoded))
        self.chunk = replace(parse_chunks(self.span)[0], index=family)
        self.root = root
        self.pack = root / "synthetic-pack"
        self.pack.write_bytes(self.span)


CASES = (
    ("sock256_stripes", 256, 4, 1000, "stripes"),
    ("shoe64_stripes", 64, 8, 128, "stripes"),
    ("shoe64_diagonal", 64, 8, 2048, "diagonal"),
    ("shoe32_tight", 32, 8, 0, "diagonal"),
    ("shoe32_noise_refused", 32, 8, -1, "noise"),
    ("shoe32_noise_half", 32, 8, -1, "noise_half"),
    ("shoe32_noise_quarter", 32, 8, -1, "noise_quarter"),
)

def stage_case(case, *, profile=None, repeat=False):
    name, width, family, margin, design = case
    harness = EquipmentSessionTests()
    factory = lambda root: tight_fixture(root)[0] if margin == -1 else SizedFixture(root, width=width, family=family, margin=margin,
        names=("socks00", "socks00_mud", "untouched") if family == 4 else None)
    with patch("test_nfl2k5_equipment_import.Fixture", factory):
        harness.setUp()
    try:
        f = harness.f
        rgba = (b"".join(bytes((20, 60, 140, 255) if (y // 7) % 3 == 0 else
                             (240, 245, 250, 255) if (y // 7) % 3 == 1 else (170, 35, 55, 255))
                          for y in range(width) for x in range(width))
                if design == "stripes" else artwork(width, width))
        if design.startswith("noise"):
            rng = random.Random(69)
            rgba = b"".join(bytes((rng.randrange(256), rng.randrange(256), rng.randrange(256), 255)) for _ in range(width*width))
        scale = 2 if design == "noise_half" else 4 if design == "noise_quarter" else 1
        asset, path = f.png(rgba=rgba)
        with f.context(), patch.object(lz, "_optimal_helper", return_value=None):
            start = time.perf_counter()
            if profile: profile.enable()
            try:
                result = stage_equipment_import(harness.a, harness.asset, path, independent=True, scale=scale)
                receipt = result.receipt
                if receipt['schema'] == 'nfl2k5_equipment_staging/v1':
                    # Atomic staging now returns measured rows for every group.
                    # Read this fixture's physical span from the same checked
                    # cache, so historical byte assertions still test the bytes
                    # that were actually staged without another fit search.
                    _, _, receipt, _, _ = writer.build_unified_uniform_equipment_imports(
                        harness.cache.pack0,
                        [(edit.asset_id, edit.replacement_path) for edit in harness.a.iter_edits()],
                        compile_cache=writer.staged_equipment_cache())
                answer = dict(outcome="fit", span_sha256=receipt["replacement"]["span_sha256"],
                    decoded_sha256=receipt["replacement"]["decoded_sha256"],
                    attempts=receipt["bounded_palette_fit"]["attempts"],
                    encoded_dimensions=receipt["edits"][0]["encoded_dimensions"])
            except writer.EquipmentFitError as error:
                answer = dict(outcome="refused", budget=error.budget, required=error.required,
                              suggestion=error.suggestion)
            finally:
                if profile: profile.disable()
            answer["seconds"] = time.perf_counter() - start
            if repeat and answer["outcome"] == "fit":
                start = time.perf_counter()
                stage_equipment_import(harness.a, harness.asset, path, independent=True, scale=scale)
                answer["repeat_seconds"] = time.perf_counter() - start
        return answer
    finally:
        harness.doCleanups()
