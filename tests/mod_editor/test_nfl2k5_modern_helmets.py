"""Modern helmets and facemasks (beta 76 hm): layout, writer, the Revolution details, composition and the historic
classic set. The shipped mode is "revolution"; the research mode "speedflex" is checked when its data is present."""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import math
import os
import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mod_editor.core import nfl2k5_models as models  # noqa: E402
from mod_editor.core import nfl2k5_modern_helmets as mh  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", str(REPO / "extracted")))  # the hydrated link
PACK0 = EXTRACTION / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"
INVENTORY = REPO / "reports" / "assets" / "nfl2k5_resource_chunks_v2.json"
HAVE_DISC = PACK0.is_file() and INVENTORY.is_file()
SLOW = os.environ.get("NFL2K5_SLOW_TESTS", "1") != "0"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_SOURCE = None


def source():
    global _SOURCE
    if _SOURCE is None:
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACK0.parents[1])
        _SOURCE = models.ModelSource(PACK0, INVENTORY)
    return _SOURCE


def outer(index: int) -> bytes:
    src = source()
    entry = src.archive.entries[index]
    return src._outer.read_entry_range(src.archive, entry, 0, entry.size)


def modes():
    """The shipped mode, then every research mode whose data is in the tree (a release carries only the first)."""
    return [m for m in mh.MODES if m == "revolution" or all(p.is_file() for p in mh.mode_paths(m))]


def detail_block(document):
    """(records, local strip, retail strip) of the Revolution details, or None."""
    detail = document["resources"][mh.HI].get("shell_detail")
    if detail is None:
        return None
    unpack = lambda text: list(struct.unpack(f"<{len(base64.b64decode(text)) // 2}H", base64.b64decode(text)))  # noqa: E731
    return base64.b64decode(detail["records"]), unpack(detail["strip"]), unpack(detail["retail_strip"])


class PackerTests(unittest.TestCase):
    def test_strip_packing_round_trips_and_is_minimal(self):
        gltf = models._tools_module("nfl_scne_gltf")
        cases = [list(range(40)), [5, 5, 6, 7, 8, 9, 10, 2, 3, 3, 4, 20, 21, 22, 23, 24, 25, 26, 1],
                 [9, 1, 7, 3, 8, 2, 6], list(range(300, 900)) + [3, 3] + list(range(10, 20))]
        for indices in cases:
            words = mh.encode_strip(indices)
            back = gltf.decode_batches(struct.pack(f"<{len(words)}I", *words), 0, len(words))
            self.assertEqual([list(b[1]) for b in back], [indices])
            self.assertEqual(back[0][0], mh.TRIANGLE_STRIP)
        # a long ascending run costs one DRAW_ARRAYS word pair per 256 indices
        self.assertEqual(len(mh.encode_strip(list(range(512)))), 4 + 2 * 2)


class GeometryDataTests(unittest.TestCase):
    def test_geometry_and_pins_agree(self):
        masks = {f"FACEMASK{slot:02d}" for slot in mh.MODERN_MASKS}
        expect = {"speedflex": {k: set(mh.OWNED[k]) for k in mh.KEYS}, "revolution": {mh.HI: masks, mh.LO: set()}}
        self.assertEqual(mh.mode_paths("revolution"), (mh.GEOMETRY_PATH, mh.PINS_PATH))
        for mode in modes():
            geometry, _pins_path = mh.mode_paths(mode)
            document, pins = mh.load_geometry(mode=mode), mh.load_pins(mode=mode)
            self.assertEqual(pins["geometry_sha256"], sha(geometry.read_bytes()), mode)
            self.assertEqual(pins["mode"], mode)
            self.assertEqual(set(document["resources"]), set(mh.KEYS))
            for key in mh.KEYS:
                self.assertEqual(set(document["resources"][key]["parts"]), expect[mode][key], f"{mode} {key}")
            self.assertEqual(sorted(int(k) for k in document["mask_alpha"]), list(mh.MODERN_MASKS))
            edits = mh.historic_edits(document)
            self.assertEqual(sum(1 for rows in edits.values() for r in rows if r[1] == "helmet"), 34)
            self.assertEqual(sum(1 for rows in edits.values() for r in rows if r[1] == "face_mask"), 26)
            self.assertTrue(all(r[3] in mh.CLASSIC_MASKS for rows in edits.values() for r in rows if r[1] == "face_mask"))
        detail = mh.load_geometry()["resources"][mh.HI]["shell_detail"]
        self.assertEqual((detail["host"], detail["submesh"]), ("FACEMASK12", mh.DETAIL_SUBMESH[mh.HI]))

    def test_every_part_winds_with_its_normals_and_the_shells_face_out(self):
        """Retail parts wind every triangle with its stored normal (PROVED OFFLINE: 0.93-1.00 of the triangles of each
        retail helmet, mask, visor and decal part) and the game may cull the other side. The new parts do the same,
        and the shells, visors and decals face away from the head."""
        for mode, key in ((m, k) for m in modes() for k in mh.KEYS):
            document = mh.load_geometry(mode=mode)
            shape = document["resources"][key]["shape"]
            stride = 16 if key == mh.HI else 24
            centre = (0.0, 42.0, 9.0) if key == mh.HI else (0.0, 42.0 + 33.89, 9.0 - 4.581)
            parts = {name: (base64.b64decode(part["records"]), base64.b64decode(part["strip"]))
                     for name, part in document["resources"][key]["parts"].items()}
            block = detail_block(document) if key == mh.HI else None
            if block is not None:                  # the Revolution details: dark parts facing out like a decal
                parts["shell_detail"] = (block[0], struct.pack(f"<{len(block[1])}H", *block[1]))
            for name, (records, raw) in parts.items():
                strip = struct.unpack(f"<{len(raw) // 2}H", raw)
                pos, nrm = [], []
                for k in range(len(records) // stride):
                    q = struct.unpack_from("<3hI", records, k * stride)
                    pos.append([models.normshort(q[a]) * shape["scale"] + shape["offset"][a] for a in range(3)])
                    nrm.append(models.decode_normpacked3(q[3]))
                agree = facing = total = 0
                for i in range(len(strip) - 2):
                    a, b, c = strip[i:i + 3]
                    if len({a, b, c}) < 3:
                        continue
                    if i % 2:
                        a, b = b, a
                    e1 = [pos[b][j] - pos[a][j] for j in range(3)]
                    e2 = [pos[c][j] - pos[a][j] for j in range(3)]
                    n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                    if sum(x * x for x in n) < 1e-8:      # zero area (the shell's collapsed rear corner) draws nothing
                        continue
                    total += 1
                    agree += sum(n[j] * (nrm[a][j] + nrm[b][j] + nrm[c][j]) for j in range(3)) > 0
                    facing += sum(n[j] * (pos[a][j] - centre[j]) for j in range(3)) > 0
                self.assertGreater(total, 0, f"{mode} {key} {name}")
                self.assertGreaterEqual(agree / total, 0.97, f"{mode} {key} {name}: winding against the normals")
                if not name.startswith("FACEMASK"):
                    self.assertGreaterEqual(facing / total, 0.97, f"{mode} {key} {name}: faces into the head")

    def test_modern_masks_name_the_catalogue(self):
        parts = mh.load_geometry()["resources"][mh.HI]["parts"]
        styles = [parts[f"FACEMASK{slot:02d}"]["style"] for slot in mh.MODERN_MASKS]
        self.assertEqual(len(set(styles)), 15)
        self.assertTrue(all(s.startswith(("SF-", "AXIOM W-")) for s in styles))


@unittest.skipUnless(HAVE_DISC, "needs the private retail extraction")
class RetailSceneTests(unittest.TestCase):
    def test_pinned_runs_are_the_retail_layout(self):
        for key in mh.KEYS:
            _r, decoded, _s = source().parse(key)
            strict = mh.parse_layout(key, decoded, strict=True)
            found = tuple((r.first_vertex, r.vertex_count, r.command, r.words, tuple(s.name for s in r.submeshes))
                          for r in strict.runs)
            self.assertEqual(found, mh.RUNS[key])
            acc = strict.by_name()["HELMET_C_accessories"]
            self.assertEqual((acc.vertices[0], acc.vertices[1] - acc.vertices[0] + 1), mh.ACCESSORIES[key])

    def test_author_changes_only_owned_bytes_and_keeps_the_classic_set(self):
        for mode, key in ((m, k) for m in modes() for k in mh.KEYS):
            document = mh.load_geometry(mode=mode)
            _r, decoded, _s = source().parse(key)
            authored, receipt = mh.author(key, decoded, document)
            self.assertEqual(len(authored), len(decoded))
            mask = mh.owned_mask(key, decoded)
            self.assertFalse([k for k in range(len(decoded)) if decoded[k] != authored[k] and not mask[k]])
            layout = mh.parse_layout(key, decoded)
            for sub in layout.submeshes:          # the Standard shell, masks 0-11 and shared parts stay retail
                if sub.name not in mh.OWNED[key]:
                    for s in sorted(layout.streams):
                        base, stride = layout.streams[s]
                        lo, hi = base + sub.vertices[0] * stride, base + (sub.vertices[1] + 1) * stride
                        if sub.name == "HELMET_C_accessories":      # only the position lanes may move (pulled in)
                            self.assertFalse([k for k in range(lo, hi) if authored[k] != decoded[k] and not mask[k]])
                            continue
                        self.assertEqual(authored[lo:hi], decoded[lo:hi], f"{key} {sub.name}")
                    self.assertEqual(authored[sub.command:sub.command + 4 * sub.words],
                                     decoded[sub.command:sub.command + 4 * sub.words], f"{key} {sub.name}")
            for run in receipt["runs"]:
                self.assertLessEqual(run["vertices"], run["vertex_budget"])
                self.assertLessEqual(run["words"], run["word_budget"])
            if mode == "revolution":
                # only the mask run and the decal submesh's command pointer are written: the retail shell C, its
                # visor, decals and accessories keep every vertex, and lo_body stays retail
                changed = {k for k in range(len(decoded)) if authored[k] != decoded[k]}
                allowed = set()
                if key == mh.HI:
                    run = next(r for r in layout.runs if r.submeshes[0].name == "FACEMASK12")
                    for s_ in sorted(layout.streams):
                        base, stride = layout.streams[s_]
                        allowed |= set(range(base + run.first_vertex * stride,
                                             base + (run.first_vertex + run.vertex_count) * stride))
                    allowed |= set(range(run.command, run.command + 4 * run.words))
                    for sub in run.submeshes + [layout.by_name()[mh.DETAIL_SUBMESH[key]]]:
                        allowed |= set(range(sub.record + 0x78, sub.record + 0x80))
                self.assertFalse(changed - allowed, f"{mode} {key}")

    def test_collection_compile_matches_pins_with_zero_memory_delta(self):
        for mode in modes():
            self._compile_matches(mode)

    def _compile_matches(self, mode):
        document, pins = mh.load_geometry(mode=mode), mh.load_pins(mode=mode)
        retail = outer(mh.OUTER)
        self.assertEqual(mh.collection_status(retail, pins), "retail")
        applied, receipt = mh.compile_collection(retail, document, pins)
        self.assertEqual(len(applied), len(retail))
        self.assertEqual(mh.collection_status(applied, pins), "applied")
        again, _ = mh.compile_collection(applied, document, pins)
        self.assertEqual(again, applied)
        chunks = mh._chunks(retail)
        for key in mh.KEYS:
            _o, index = models.parse_model_key(key)
            before, after = mh._chunk_span(retail, chunks[index]), mh._chunk_span(applied, chunks[index])
            self.assertEqual(after[:32], before[:32])            # wrapper: system/video/scratch words unchanged
            self.assertEqual(sha(after), pins["scenes"][key]["span_applied"])
        self.assertEqual(sorted(receipt["masks"]), list(mh.MODERN_MASKS))
        for slot in mh.CLASSIC_MASKS:
            span = mh._chunk_span(retail, chunks[mh.MASK_CHUNKS[slot]])
            self.assertEqual(mh._chunk_span(applied, chunks[mh.MASK_CHUNKS[slot]]), span)

    def test_the_shells_and_details_stay_under_the_guardian_cap(self):
        """Where the Guardian overlay's cap covers the head (its covering vertices; the open rim excluded), the helmet
        C shell and the Revolution details never reach past it, close up or at distance."""
        gen = importlib.import_module("nfl2k5_modern_helmets_generate")
        gen.PACK0, gen.INVENTORY = PACK0, INVENTORY
        for mode, key in ((m, k) for m in modes() for k in mh.KEYS):
            document = mh.load_geometry(mode=mode)
            centre = gen.C if key == mh.HI else gen.add(gen.C, gen.LO_OFFSET)
            _r, decoded, _s = source().parse(key)
            authored, _receipt = mh.author(key, decoded, document)
            span = source().span(source().resource(key))
            new = gen.Scene(key, span=mh.refit(span, authored))
            shell = [tuple(tuple(new.pos[v]) for v in t) for t in new.by_material("HI_HELMET_C")[0]["tris"]]
            if key == mh.HI and mode == "revolution":
                shell += [tuple(tuple(new.pos[v]) for v in t)
                          for t in new.by_material(mh.DETAIL_SUBMESH[key])[0]["tris"]]
            capped = mh.guardian_lanes(key, decoded)
            cap_pos = mh._positions(mh.parse_layout(key, capped), capped)
            retail = gen.Scene(key)
            cap = gen.cap_interior_triangles([tuple(tuple(cap_pos[v]) for v in t)
                                              for t in retail.by_material("HI_HELMET_B")[0]["tris"]])
            covering = sorted({q for t in cap for q in t})
            self.assertGreater(len(covering), 50, f"{mode} {key}")
            beyond = []
            for q in covering:
                d = gen.norm(gen.sub(q, centre))
                hit = gen.ray_hit(d, shell, origin=centre)
                if hit is not None and hit > math.dist(q, centre) + 0.02:
                    beyond.append((round(hit - math.dist(q, centre), 2), q))
            self.assertEqual(beyond, [], f"{mode} {key}")

    def test_revolution_details_ride_on_the_retail_shell(self):
        """The shipped mode: the retail shell C keeps its triangles; the decal submesh draws its own retail triangles
        and then the details, whose vertices all sample the dark texel and sit just above the retail shell."""
        gen = importlib.import_module("nfl2k5_modern_helmets_generate")
        gen.PACK0, gen.INVENTORY = PACK0, INVENTORY
        document = mh.load_geometry()
        records, local, retail_strip = detail_block(document)
        _r, decoded, _s = source().parse(mh.HI)
        authored, receipt = mh.author(mh.HI, decoded, document)
        self.assertEqual(receipt["shell_detail"]["submesh"], mh.DETAIL_SUBMESH[mh.HI])
        span = source().span(source().resource(mh.HI))
        new, old = gen.Scene(mh.HI, span=mh.refit(span, authored)), gen.Scene(mh.HI)
        for name in ("HI_HELMET_C", "HI_faceshield_C", "HELMET_C_accessories"):
            self.assertEqual(new.by_material(name)[0]["tris"], old.by_material(name)[0]["tris"], name)
        decal_old = old.by_material(mh.DETAIL_SUBMESH[mh.HI])[0]
        decal_new = new.by_material(mh.DETAIL_SUBMESH[mh.HI])[0]
        self.assertEqual(decal_old["batches"], [(mh.TRIANGLE_STRIP, retail_strip)])
        self.assertEqual(decal_new["tris"][:len(decal_old["tris"])], decal_old["tris"])
        first = min(i for t in decal_new["tris"][len(decal_old["tris"]):] for i in t)
        count = len(records) // 16
        self.assertEqual(sorted({i for t in decal_new["tris"][len(decal_old["tris"]):] for i in t}),
                         list(range(first, first + count)))
        self.assertTrue(all(abs(new.uv[v][0] - gen.DARK_UV[0]) < 2e-3 and abs(new.uv[v][1] - gen.DARK_UV[1]) < 2e-3
                            for v in range(first, first + count)))
        shell = gen.RetailShell(old)           # the outermost retail surface along each ray from the centre
        heights = []
        for v in range(first, first + count):
            d = gen.sub(new.pos[v], gen.REV_CENTRE)
            az, el = math.degrees(math.atan2(d[0], d[2])), math.degrees(math.atan2(d[1], math.hypot(d[0], d[2])))
            surface = shell.cast(az, el)[0]
            heights.append(math.dist(new.pos[v], gen.REV_CENTRE) - math.dist(surface, gen.REV_CENTRE))
        self.assertGreater(min(heights), 0.02)
        self.assertLess(max(heights), 0.4)

    def test_revolution_masks_have_their_photos_proportions_and_sit_outside_the_shell(self):
        """Pass 5 (Noah 9/25: the pass-4 masks were "too tall and skinny"): every modern mask is as wide as the
        helmet at the top and shorter than it is wide, like its product photo (width over height 1.25-1.45 on the
        riddell.com photos), its top bar's middle sits under the front bumper, and no vertex is inside the shell or the
        face."""
        gen = importlib.import_module("nfl2k5_modern_helmets_generate")
        gen.PACK0, gen.INVENTORY = PACK0, INVENTORY
        document = mh.load_geometry()
        shape = document["resources"][mh.HI]["shape"]
        shell, face = gen.mask_surfaces(gen.Scene(mh.HI))
        for slot in mh.MODERN_MASKS:
            part = document["resources"][mh.HI]["parts"][f"FACEMASK{slot:02d}"]
            records = base64.b64decode(part["records"])
            pos = []
            for k in range(len(records) // 16):
                q = struct.unpack_from("<3h", records, k * 16)
                pos.append([models.normshort(q[a]) * shape["scale"] + shape["offset"][a] for a in range(3)])
            xs, ys = [p[0] for p in pos], [p[1] for p in pos]
            width, height = max(xs) - min(xs), max(ys) - min(ys)
            self.assertTrue(1.2 <= width / height <= 1.55, f"mask {slot}: {width:.1f} x {height:.1f} cm")
            self.assertGreater(width, 20.5, f"mask {slot}")
            top = max(p_[1] for p_ in pos if abs(p_[0]) < 2.0)          # the top bar's middle, under the bumper
            self.assertTrue(44.6 <= top <= 45.3, f"mask {slot}: top at {top:.2f}")
            for p_ in pos:
                for surf in (shell, face):
                    z = surf.front_z(p_[0], p_[1])
                    self.assertTrue(z is None or p_[2] >= z - 0.05, f"mask {slot}: vertex {p_} inside at z {z}")

    def test_mask_textures_carry_the_drawn_alpha(self):
        tx = models._tools_module("nfl_txtr")
        document = mh.load_geometry()
        retail = outer(mh.OUTER)
        chunks = mh._chunks(retail)
        for slot in (12, 21, 26):
            span = mh._chunk_span(retail, chunks[mh.MASK_CHUNKS[slot]])
            new = mh.compile_mask_texture(mh.mask_alpha(document, slot), span)
            chunk = tx.parse_chunks(new, allow_trailing=True)[0]
            decoded, _ = tx.decode_chunk(new, chunk)
            texture = tx.parse_texture(decoded, chunk)
            rgba = tx.texture_to_rgba(decoded, chunk, texture)
            self.assertEqual(bytes(rgba[3::4]), mh.mask_alpha(document, slot))


@unittest.skipUnless(HAVE_DISC and SLOW, "needs the private retail extraction (slow)")
class CompositionTests(unittest.TestCase):
    def test_guardian_overlay_either_order(self):
        from mod_editor.core import nfl2k5_guardian_resources as guardian
        retail = outer(mh.OUTER)
        donor = outer(4002)[0x661B0:0x661B0 + 36704]
        g, _ = guardian.compile_collection(retail, donor)
        for mode in modes():
            document, pins = mh.load_geometry(mode=mode), mh.load_pins(mode=mode)
            gh, _ = mh.compile_collection(g, document, pins)
            h, _ = mh.compile_collection(retail, document, pins)
            self.assertEqual(guardian.collection_status(h), "retail", mode)
            hg, _ = guardian.compile_collection(h, donor)
            self.assertEqual(gh, hg, mode)
            self.assertEqual(guardian.collection_status(gh), "applied", mode)
            self.assertEqual(mh.collection_status(gh, pins), "applied", mode)

    def test_historic_rosters_either_order_and_every_classic_record_is_retail_equipment(self):
        from mod_editor.core import nfl2k5_espn25_rosters as espn25
        from mod_editor.core import nfl2k5_roster_records as rr
        edits = mh.historic_edits()
        manifest, _sheets = espn25.dataset()
        resources = {t["outer"]: outer(t["outer"]) for t in manifest["resources"]}
        first, _ = espn25._compile_resources(resources)
        a = {o: (mh.compile_historic(first[o], o, edits) if o in edits else first[o]) for o in first}
        helmets_first = {o: (mh.compile_historic(resources[o], o, edits) if o in edits else resources[o]) for o in resources}
        self.assertEqual(espn25.status(helmets_first), "retail")
        b, _ = espn25._compile_resources(helmets_first)
        self.assertEqual(a, b)
        self.assertEqual(espn25.status(b), "applied")
        for o in mh.HISTORIC_OUTERS:
            payload = mh.compile_historic(outer(o), o, edits) if o in edits else outer(o)
            for p in rr.RosterDocument(payload[32:]).players:
                self.assertEqual(p.record.values["helmet"], 0)
                self.assertIn(p.record.values["face_mask"], mh.CLASSIC_MASKS)


class BuildPlanTests(unittest.TestCase):
    def test_presets_off_and_guardian_cap_refused(self):
        from mod_editor.core import mod_build
        for preset in mod_build.PRESETS.values():
            self.assertIs(preset["modern_helmets"], False)
        self.assertIn("modern_helmets", mod_build.availability())

    def test_modes(self):
        self.assertEqual(mh.MODES, ("revolution", "speedflex"))
        self.assertEqual([value for _label, value in mh.MODE_LABELS], list(mh.MODES))
        self.assertEqual(mh.mode_paths()[0].name, "geometry.json")
        with self.assertRaises(mh.ModernHelmetsError):
            mh.mode_paths("f7")


if __name__ == "__main__":
    unittest.main()
