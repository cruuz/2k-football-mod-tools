"""Pipeline receipt regression: venue art -> model fans -> boards -> surfaces.

Small byte archives isolate ownership from the expensive geometry/texture
compilers. The archive writes, receipt persistence and state readers are real.
vr/reproduce.py also exercises the compilers against the retail archive.
"""
from contextlib import ExitStack
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_model_fan_art as fans
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_modern_surfaces as surfaces
from mod_editor.core import nfl2k5_board_kit as boards
from mod_editor.core import nfl2k5_modern_metlife as ml


class Archive:
    def __init__(self, names):
        self.entries = [SimpleNamespace(index=i, name_id=mv.name_id(n), size=64, virtual_offset=i * 64)
                        for i, n in enumerate(names)]
        self.data = bytearray(b"R" * (64 * len(names)))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, at, size):
        return bytes(self.data[at:at + size])

    def write(self, at, data):
        self.data[at:at + len(data)] = data
        return len(data)


MODELS = ("sofi", "highmark", "att", "levis", "allegiant", "mercedes_benz", "usbank", "lucas_oil",
          "state_farm", "hard_rock", "lambeau", "everbank")


class ModelDelegation(unittest.TestCase):
    def test_every_venue_helper_checks_the_recorded_model_parent_and_exact_span(self):
        for name in MODELS:
            module = importlib.import_module(f"mod_editor.core.nfl2k5_{name}_model")
            prefix = sorted(getattr(mv, name.upper() + "_VENUES"))[0]
            filename = prefix + "dd.iff"
            archive = Archive([filename])
            archive.write(16, b"F" * 32)
            pin = dict(name=filename, size=64, outer=0, name_id=mv.name_id(filename),
                       sites=[dict(kind="stadium", offset=16, size=32, retail=mv.sha(b"R" * 32))])
            model = dict(pin, offset=16, length=32, model_sha256=mv.sha(b"M" * 32),
                         model_portrait_sha256="portrait", classic_sha256="classic", retail_sha256=mv.sha(b"R" * 32))
            fan = dict(schema="nfl2k5_model_fan_art/v1", offset=16, length=32,
                       before_sha256=model["model_sha256"], after_sha256=mv.sha(b"F" * 32))
            with self.subTest(model=name), patch.object(module, "_pin", return_value=model), \
                    patch.object(module, "_venue_pins", return_value={filename: pin}), \
                    patch.object(module, "_entry", return_value=archive.entries[0]):
                self.assertEqual(mv.bundle_state(archive, pin, None, None), "foreign")
                receipt = dict(model_fan_art={filename: fan})
                self.assertEqual(mv.bundle_state(archive, pin, receipt, None), name)
                for key, value in (("schema", "unknown"), ("before_sha256", "unknown"),
                                   ("offset", 17), ("length", 31), ("after_sha256", "unknown")):
                    bad = dict(model_fan_art={filename: dict(fan, **{key: value})})
                    self.assertEqual(mv.bundle_state(archive, pin, bad, None), "foreign", key)
                archive.write(16, b"?")
                self.assertEqual(mv.bundle_state(archive, pin, receipt, None), "foreign")


class PipelineOrder(unittest.TestCase):
    def setUp(self):
        self.settings = colour.normalize_settings({})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.target = Path(self.stack.enter_context(tempfile.TemporaryDirectory())) / "archive"
        self.names = ("s02dd.iff", "s13dd.iff", "s01dd.iff", "s40dd.iff")
        self.archive = Archive(self.names)
        self.pins = {}
        for i, name in enumerate(self.names):
            self.pins[name] = dict(name=name, size=64, outer=i, name_id=mv.name_id(name),
                                   retail_sha256=mv.sha(b"R" * 64),
                                   sites=[dict(kind=k, offset=o, size=s, retail=mv.sha(b"R" * s))
                                          for k, o, s in (("field", 0, 16), ("stadium", 16, 32))])
        self.table = {n[:3]: dict(team=n[:3], bundles=[self.pins[n]]) for n in self.names[:-1]}
        for module in (mv, colour, surfaces, ml):
            self.mock(module, "_outer_image", return_value=lambda *a, **kw: self.archive)
        self.mock(mv, "venues", return_value=self.table)
        self.mock(mv, "_read_rost", return_value=(None, b"names"))
        self.mock(mv, "rost_state", return_value="applied")
        self.mock(colour, "_pins", return_value=dict(bundles=list(self.pins.values())))
        self.model_pins = {}
        self.models = {}
        for name, model_name in (("s01dd.iff", "mercedes_benz"), ("s40dd.iff", "sofi")):
            mod = importlib.import_module(f"mod_editor.core.nfl2k5_{model_name}_model")
            pin = dict(self.pins[name], offset=16, length=32, model_sha256=mv.sha(b"M" * 32),
                       model_portrait_sha256="portrait", retail_sha256=mv.sha(b"R" * 32))
            self.model_pins[name] = pin
            self.models[name] = mod
            self.mock(mod, "_pin", return_value=pin)
            self.mock(mod, "_venue_pins", return_value={name: self.pins[name]})
            self.mock(mod, "_entry", return_value=self.archive.entries[self.pins[name]["outer"]])
        self.mock(boards, "pinned_venues", return_value=("s02", "s13"))
        self.mock(boards, "variants", side_effect=lambda p: (p + "dd.iff",))
        self.mock(boards, "_venue_pins", side_effect=lambda p: {p + "dd.iff": self.pins[p + "dd.iff"]})
        self.mock(boards, "_pin", side_effect=lambda n: dict(self.pins[n], offset=16, length=32,
                  retail_sha256=mv.sha(b"R" * 32), model_sha256=mv.sha(b"B" * 32)))
        self.mock(boards, "_renovated", side_effect=lambda b, n: b[16:48] == b"B" * 32)
        self.mock(boards, "model_bundle", side_effect=lambda b, n: (b[:16] + b"B" * 32 + b[48:],
                                                                  dict(system=32, video=0)))
        self.mock(surfaces, "HOME_BUNDLES", self.names[:-1])
        self.mock(surfaces, "home_entries", side_effect=lambda a: {n: a.entries[self.pins[n]["outer"]]
                                                                  for n in self.names[:-1]})
        self.mock(surfaces, "indoor_flags", return_value={n[:3]: False for n in self.names})
        self.mock(surfaces, "_normal_state", return_value=("other", None, None))
        self.mock(surfaces, "_job", side_effect=self.surface_job)

    def mock(self, module, attr, *args, **kw):
        return self.stack.enter_context(patch.object(module, attr, *args, **kw))

    def blob(self, name):
        return self.archive.read(self.pins[name]["outer"] * 64, 64)

    def refresh_colour(self):
        for name in self.names:
            surfaces._update_colour_receipt(self.cr, name, self.blob(name))
        colour._save_image_receipt(self.target, self.cr)

    @staticmethod
    def surface_job(job):
        name, before, *_ = job
        after = b"S" * 16 + before[16:]
        edit = dict(kind="field", offset=0, size=16, before=mv.sha(before[:16]), after=mv.sha(after[:16]))
        return name, after, dict(look="grass", light="day", rig="day", normal="full", field={}, edits=[edit])

    def prepare_through_models(self):
        # Colour, then venue art. F owns Kansas City through venue art (Arrowhead option off).
        settings = self.settings
        self.cr = dict(schema=colour.RECEIPT_SCHEMA, settings=settings, settings_sha256=colour.settings_id(settings),
                       state="applied", bundle_pins={n: dict(p) for n, p in self.pins.items()})
        for n in self.names:
            self.archive.write(self.pins[n]["outer"] * 64, b"C" * 16)
        for n in self.names[:2]:
            self.archive.write(self.pins[n]["outer"] * 64 + 16, b"V" * 32)
        mv._save_receipt(self.target, dict(schema=mv.RECEIPT_SCHEMA,
                         bundles={n: dict(applied_sha256=mv.sha(self.blob(n))) for n in self.names[:2]}))
        self.refresh_colour()
        self.assertEqual(mv.image_status(self.target), "applied")
        # Models, then the same fan receipt producer and sidecar hand-off used by all writers.
        results = []
        for n in self.names[2:]:
            self.archive.write(self.pins[n]["outer"] * 64 + 16, b"M" * 32)
            results.append((n, self.blob(n), {}))
        plan = dict(items=[dict(scene="stadium", key="banner_home_player")], base={}, manifest="m", digest="d")
        with patch.object(mv, "load_art", return_value=dict(venues={"s01": plan})), \
                patch.object(mv, "plan_venue", return_value=plan), patch.object(fans, "neutral_plan", return_value=plan), \
                patch.object(fans, "paint_bundle", side_effect=lambda b, n, p: (b[:16] + b"F" * 32 + b[48:], {})):
            painted = fans.paint_results(results, {}, "art", dict(bundles=list(self.model_pins.values())))
        for n, blob, info in painted:
            self.archive.write(self.pins[n]["outer"] * 64, blob)
            fans.preserve_receipts(self.target, dict(bundles={n: dict(fan_art=info["fan_art"])}))
        self.refresh_colour()
        self.fan_rows = mv.read_receipt(self.target)["model_fan_art"]
        for n, mod in self.models.items():
            self.assertEqual(mod.bundle_state(self.archive, n, fan_receipt=self.fan_rows[n]), "applied")

    def test_f_receipts_survive_boards_then_surfaces_including_neutral_s40(self):
        self.prepare_through_models()
        boards.apply_to_image(self.target, workers=1)
        self.assertEqual(boards.image_status(self.target), "applied")
        surfaces.apply_to_image(self.target, workers=1)  # 918b4a47 fails its venue read-back here.
        self.assertEqual(mv.image_status(self.target), "applied")
        self.assertEqual(colour.image_status(self.target), "applied")
        self.assertEqual(surfaces.image_status(self.target), "applied")
        self.assertEqual(boards.image_status(self.target), "applied")
        self.assertEqual(mv.read_receipt(self.target)["model_fan_art"], self.fan_rows)
        for n, mod in self.models.items():
            self.assertEqual(mod.bundle_state(self.archive, n, fan_receipt=self.fan_rows[n]), "applied")
        # Unknown bytes still fail even with an otherwise valid fan receipt.
        self.archive.write(self.pins["s01dd.iff"]["outer"] * 64 + 20, b"?")
        self.assertEqual(mv.image_status(self.target), "foreign")

    def test_arrowhead_combined_receipt_still_requires_its_recorded_bytes(self):
        from mod_editor.core import nfl2k5_modern_arrowhead as arrowhead
        n = "s13dd.iff"
        pin = self.pins[n]
        self.archive.write(pin["outer"] * 64 + 16, b"A" * 32)
        cr = dict(modern_arrowhead=dict(bundles={n: dict(applied_sha256=mv.sha(self.blob(n)))}))
        with patch.object(arrowhead, "_pins", return_value=dict(bundles=[pin])):
            self.assertEqual(mv.bundle_state(self.archive, pin, None, cr), "arrowhead")
            self.archive.write(pin["outer"] * 64 + 20, b"?")
            self.assertEqual(mv.bundle_state(self.archive, pin, None, cr), "foreign")

    def test_report_names_each_bad_bundle_and_the_rost_state(self):
        self.prepare_through_models()
        for n in ("s02dd.iff", "s01dd.iff"):
            self.archive.write(self.pins[n]["outer"] * 64 + 20, b"?")
        report = mv.image_report(self.target)
        self.assertEqual(report["state"], "foreign")
        self.assertEqual(report["venues"]["s13"]["bundles"], {"s13dd.iff": "venues"})
        details = mv.readback_details(report)
        for text in ("s02 (s02): s02dd.iff=foreign", "s01 (s01): s01dd.iff=foreign", "ROST venue names=applied"):
            self.assertIn(text, details)
        with self.assertRaisesRegex(mv.ModernVenuesError, "s01dd.iff=foreign"):
            mv.verify(self.target)
        with patch.object(mv, "rost_state", return_value="foreign"):
            self.assertIn("ROST venue names=foreign", mv.readback_details(mv.image_report(self.target)))

    def test_surfaces_failure_names_the_foreign_model_bundle(self):
        self.prepare_through_models()
        boards.apply_to_image(self.target, workers=1)
        receipt = mv.read_receipt(self.target)
        receipt["model_fan_art"]["s01dd.iff"]["before_sha256"] = "unknown"
        mv._save_receipt(self.target, receipt)
        with self.assertRaisesRegex(surfaces.ModernSurfacesError,
                                    r"2026 venue read-back failed after Modern surfaces.*s01dd\.iff=foreign"):
            surfaces.apply_to_image(self.target, workers=1)


class ConstructionStatus(unittest.TestCase):
    def test_fan_art_preserves_on_and_off_and_rejects_an_unknown_parent(self):
        from mod_editor.core import nfl2k5_everbank_model as model
        from mod_editor.core import nfl2k5_everbank_venue as venue
        name = "s12dd.iff"
        archive = Archive([name])
        pin = dict(name=name, size=64, offset=16, length=32, model_sha256=mv.sha(b"M" * 32),
                   classic_sha256=mv.sha(b"C" * 32), retail_sha256=mv.sha(b"R" * 32))
        archive.write(16, b"F" * 32)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            target = Path(tmp) / "archive"
            stack.enter_context(patch.object(model, "VARIANTS", (name,)))
            stack.enter_context(patch.object(model, "_pin", return_value=pin))
            stack.enter_context(patch.object(model, "_venue_pins", return_value={name: pin}))
            stack.enter_context(patch.object(model, "_entry", return_value=archive.entries[0]))
            stack.enter_context(patch.object(model.sm._ml(), "_outer_image", return_value=lambda *a, **kw: archive))
            stack.enter_context(patch.object(venue, "ROST_OUTER_INDEX", 0))
            stack.enter_context(patch.object(venue, "rost_state", return_value="applied"))
            for parent, expected in ((pin["model_sha256"], "on"), (pin["classic_sha256"], "off"), ("unknown", "foreign")):
                fan = dict(schema="nfl2k5_model_fan_art/v1", offset=16, length=32,
                           before_sha256=parent, after_sha256=mv.sha(b"F" * 32))
                mv._save_receipt(target, dict(schema=mv.RECEIPT_SCHEMA, model_fan_art={name: fan}))
                with self.subTest(parent=parent):
                    self.assertEqual(model.construction_status(target), expected)


if __name__ == "__main__":
    unittest.main()
