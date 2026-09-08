"""Observe the complete pure-XBE gate stack without allocating a disc copy.

NFL2K5_GUARDIAN_MANIFEST_OUTPUT optionally retains this private proof manifest.
It expressly describes XBE execution only, with no resource/disc build claim.
The protected release manifest still requires the normal integration rebuild.
"""
from __future__ import annotations

import ast
from contextlib import ExitStack
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_cave_manifest as cm
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_guardian_overlay as g
from mod_editor.core.nfl2k5_cave_oracle import MANIFEST_SCHEMA, RETAIL_SHA256, XbeImage, ReservationManifest
from tests.mod_editor import test_xbe_patch_memory_writes as gate


@unittest.skipUnless(gate.XBE.is_file() and importlib.util.find_spec("capstone"),"retail USA XBE and Capstone required for full gate/manifest proof")
class ManifestTests(unittest.TestCase):
    def test_observed_complete_owner_union_and_private_manifest(self):
        # Import actual gate dependencies before observing their unmodified
        # public byte writers. No byte writer is replaced by a fake output.
        for file in (ROOT/"tests/mod_editor/test_xbe_patch_memory_writes.py",ROOT/"tests/nfl2k5_allocator_stack.py"):
            for node in ast.walk(ast.parse(file.read_text())):
                if isinstance(node,ast.ImportFrom) and node.module=="mod_editor.core":
                    for alias in node.names:importlib.import_module(node.module+"."+alias.name)
        retail=gate.XBE.read_bytes();recorder=cm.Recorder(retail)
        # Generic engines receive an owner as an argument. Observe their
        # public owning modules, as the production recorder does, rather than
        # falsely reserving the same edit for the generic engine's filename.
        engines={"mod_editor.core.nfl2k5_gameplay_lever", "mod_editor.core.nfl2k5_rdata_sites"}
        modules=[m for name,m in tuple(sys.modules.items()) if name.startswith("mod_editor.core.nfl2k5_")
                 and name not in engines and hasattr(m,"__file__")]
        fingerprints=cm.source_fingerprints()
        with ExitStack() as stack:
            for module in modules:
                for name in ("apply","apply_xbe","xbe_apply","plan_patch","apply_arc_table","patch_xbe","apply_chop_block"):
                    function=getattr(module,name,None)
                    if inspect.isfunction(function) and function.__module__==module.__name__:
                        stack.enter_context(patch.object(module,name,recorder.wrapper(module,name)))
            # The anniversary adapter captured apply_xbe at module import, before
            # observation. Route its alias through the same real writer wrapper;
            # otherwise its C2319 edit is absent from the observed manifest.
            from mod_editor.core import nfl2k5_espn25_rosters as espn25
            stack.enter_context(patch.object(espn25.XbePatch, "apply", staticmethod(espn25.apply_xbe)))
            gate.PatchWriteTests.setUpClass()
            final=gate.PatchWriteTests.patched
        spans=recorder.finish(final)  # rejects every unattributed changed byte
        self.assertEqual(fingerprints,cm.source_fingerprints())
        self.assertEqual(g.status(final),"applied")
        doc=dict(schema=MANIFEST_SCHEMA,retail_sha256=RETAIL_SHA256,complete=True,
                 model="Observed pure XBE safety-gate composition with all allocator owners; no disc or resource build",
                 stack_image_size=XbeImage(final).image_size,stack_xbe_sha256=hashlib.sha256(final).hexdigest(),
                 section_digests_verified=True,source_sha256=fingerprints,spans=spans,steps=recorder.steps,
                 allocator_layout=g.space.layout(final),image_steps=[],runtime_witnessed=False)
        manifest=ReservationManifest(doc,XbeImage(retail),source_root=ROOT)
        for va,before in g.HOOKS.values():
            rows=manifest.overlaps(va,va+len(before))
            self.assertTrue(rows)
            self.assertTrue(all(row.detail.startswith(g.OWNER+":") for row in rows))
        self.assertEqual(g.space.allocation_evidence(retail,manifest,allocated=final)["retail_mapping_overlaps"],[])
        output=os.environ.get("NFL2K5_GUARDIAN_MANIFEST_OUTPUT")
        if output:
            path=Path(output).resolve()
            self.assertNotEqual(path,(ROOT/"data/nfl2k5_cave_reservations.json").resolve())
            path.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":unittest.main()
