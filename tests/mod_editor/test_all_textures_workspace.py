"""All Textures must be a workspace, and its edits must reach the disc.

The capability shipped registered and marked Editable with **no page behind
it** -- a sidebar entry that did nothing. Fixing that is two separate things,
and only one of them is visible:

1. A browser to pick a texture in. That is the obvious half.
2. A route into ``Build Modded XISO``. That is the half that matters. A
   browser whose edits are silently dropped at build time would be worse than
   the bare card it replaced, because the user would believe the edit landed.

So these assertions are about the second half. The composed build has to know
the ``p8_texture`` kind, validate it, refuse duplicates, and dispatch it to the
adapter; the catalog has to publish assets the browser can list; and the
category has to mount the real visual page rather than the capability-card
fallback.

Everything here is metadata and source structure. The end-to-end proof -- two
texture edits composed into a real modded XISO, 31,652 bytes changed -- is a
retail-data run recorded in the release notes, not something CI can perform.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core.capabilities import CapabilityRegistryLoader  # noqa: E402
from mod_editor.core.nfl2k5_extended_visual_catalog import (  # noqa: E402
    PRODUCTION_EXPECTATIONS, load_nfl2k5_extended_visual_catalog,
)
from mod_editor.core.nfl2k5_p8_texture_writer import (  # noqa: E402
    EXPECTED_TARGETS, load_inventory,
)
from mod_editor.core.product_catalog import (  # noqa: E402
    ProductCategory, build_nfl2k5_product_catalog,
)

_PROJECT = _REPO_ROOT / "tools" / "nfl2k5_visual_mod_project.py"
_STUDIO = _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"


class InventoryTests(unittest.TestCase):
    def test_every_target_loads(self) -> None:
        targets = load_inventory()
        self.assertEqual(len(targets), EXPECTED_TARGETS)

    def test_targets_carry_the_identity_the_build_binds_against(self) -> None:
        target = load_inventory()["p8:3136:pad_north"]
        self.assertEqual(target.pack_path, "vc_53450030/8")
        self.assertTrue(target.pack_sha256)
        self.assertGreater(target.span_size, 0)
        self.assertEqual((target.width, target.height), (128, 128))

    def test_the_four_families_are_all_present(self) -> None:
        groups = {target.group for target in load_inventory().values()}
        self.assertEqual(
            groups, {"End Zone", "Goalpost Pads", "Field Surface", "Equipment"}
        )


class CatalogTests(unittest.TestCase):
    def test_the_browser_has_assets_to_list(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        assets = catalog.assets_for_kind("p8_texture")
        self.assertEqual(len(assets), PRODUCTION_EXPECTATIONS.p8_texture_count)
        self.assertEqual(len(assets), EXPECTED_TARGETS)

    def test_an_asset_produces_the_edit_the_build_accepts(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        asset = catalog.assets_for_kind("p8_texture")[0]
        edit = asset.provider_edit("/tmp/example.png")
        self.assertEqual(set(edit), {"kind", "asset_id", "png"})
        self.assertEqual(edit["kind"], "p8_texture")
        self.assertTrue(str(edit["asset_id"]).startswith("p8:"))

    def test_every_asset_declares_the_capability_it_belongs_to(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        owners = {
            asset.capability_id for asset in catalog.assets_for_kind("p8_texture")
        }
        self.assertEqual(owners, {"nfl2k5.textures.all_p8"})


class ComposedBuildTests(unittest.TestCase):
    """The half that matters: the edit must survive Build Modded XISO."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _PROJECT.read_text(encoding="utf-8")

    def test_the_build_declares_the_kind(self) -> None:
        self.assertIn('P8_TEXTURE_KIND = "p8_texture"', self.source)
        self.assertIn(
            'P8_TEXTURE_FIELDS = {"kind", "asset_id", "png"}', self.source
        )

    def test_the_build_validates_the_edit_shape(self) -> None:
        self.assertIn("elif kind == P8_TEXTURE_KIND:", self.source)
        self.assertIn("has invalid p8_texture fields/types", self.source)

    def test_the_build_refuses_a_repeated_target(self) -> None:
        self.assertIn('"project repeats one p8_texture target"', self.source)

    def test_the_build_dispatches_to_the_adapter(self) -> None:
        self.assertIn("build_unified_p8_texture_import", self.source)
        self.assertIn("p8_texture_adapter", self.source)

    def test_the_adapter_is_registered_before_execution(self) -> None:
        """@dataclass resolves through sys.modules; an unregistered module
        raises AttributeError on import."""
        loader = self.source[self.source.index("def _load_p8_texture_adapter"):]
        loader = loader[:loader.index("def _load_stadium_texture_adapter")]
        self.assertLess(
            loader.index("sys.modules[spec.name] = module"),
            loader.index("spec.loader.exec_module(module)"),
        )


class WorkspaceMountTests(unittest.TestCase):
    def test_the_category_mounts_the_real_browser(self) -> None:
        source = _STUDIO.read_text(encoding="utf-8")
        self.assertIn("ProductCategory.TEXTURES: frozenset({", source)
        self.assertIn('"p8_texture",', source)
        mount = source.index("elif category == ProductCategory.TEXTURES:")
        window = source[mount:mount + 700]
        self.assertIn("_build_visual_page(section, visual_kinds)", window)

    def test_the_capability_is_exposed_and_enabled(self) -> None:
        catalog = build_nfl2k5_product_catalog(CapabilityRegistryLoader().load())
        binding = catalog.binding("nfl2k5.textures.all_p8")
        gui = binding.capability.raw["gui"]
        self.assertTrue(gui["expose"])
        self.assertTrue(gui["default_enabled"])

    def test_the_category_holds_the_capability(self) -> None:
        catalog = build_nfl2k5_product_catalog(CapabilityRegistryLoader().load())
        section = catalog.section(ProductCategory.TEXTURES)
        self.assertIn(
            "nfl2k5.textures.all_p8",
            {binding.capability_id for binding in section.capabilities},
        )


if __name__ == "__main__":
    unittest.main()
