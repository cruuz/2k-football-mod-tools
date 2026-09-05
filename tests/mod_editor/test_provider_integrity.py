"""Adversarial integrity gates for the provider execution boundary."""

from __future__ import annotations

import ast
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.providers import (
    Apf2k8HelmetColorProvider,
    Apf2k8JerseyColorProvider,
    Apf2k8PantsColorProvider,
    Apf2k8ShoulderColorProvider,
    Nfl2k5ScorebugProvider,
    Nfl2k5UnifiedVisualProvider,
    ProviderError,
    _pinned_execution_bundle,
)
from tests.mod_editor.test_providers import (
    PINNED_SOURCE_SHA,
    apf_request,
    request,
    scorebug_request,
)


WORKSPACE = Path(__file__).resolve().parents[2]


_DEFERRED_BACKEND_IMPORT_SITES = frozenset({
    (
        "mod_editor/core/nfl2k5_audio_catalog.py",
        "replacement_provider",
        "mod_editor.core.nfl_audio_provider",
    ),
})


def _local_module_path(name: str) -> str | None:
    """Resolve a product-package or legacy bare-tools module without init files."""

    product = WORKSPACE.joinpath(*name.split(".")).with_suffix(".py")
    if product.is_file():
        return product.relative_to(WORKSPACE).as_posix()
    if "." not in name:
        tool = WORKSPACE / "tools" / f"{name}.py"
        if tool.is_file():
            return tool.relative_to(WORKSPACE).as_posix()
    return None


def _is_type_checking(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
    ) or (
        isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
        and test.attr == "TYPE_CHECKING"
    )


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[str] = []
        self.rows: list[tuple[ast.Import | ast.ImportFrom, str | None]] = []

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        if _is_type_checking(node.test):
            for item in node.orelse:
                self.visit(item)
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        self.rows.append((node, self.functions[-1] if self.functions else None))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        self.rows.append((node, self.functions[-1] if self.functions else None))


def _module_name(relative: str) -> str:
    path = Path(relative)
    if path.parts[0] == "mod_editor":
        return ".".join(path.with_suffix("").parts)
    return path.stem


def _absolute_import_names(
    relative: str,
    node: ast.Import | ast.ImportFrom,
) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if node.level == 0:
        if node.module is None:
            return ()
        return (node.module,) + tuple(
            f"{node.module}.{alias.name}"
            for alias in node.names
            if alias.name != "*"
        )

    package = _module_name(relative).rpartition(".")[0]
    parts = package.split(".") if package else []
    keep = len(parts) - (node.level - 1)
    if keep < 0:
        return ()
    base = ".".join(parts[:keep])
    if node.module is not None:
        return ((f"{base}.{node.module}").strip("."),)
    return tuple(
        (f"{base}.{alias.name}").strip(".")
        for alias in node.names
        if alias.name != "*"
    )


def local_import_closure(
    *entries: str,
    exact_path_entries: frozenset[str] = frozenset(),
) -> set[str]:
    """Return the recursive executable local closure, intentionally init-free."""

    pending = [(relative, relative in exact_path_entries) for relative in entries]
    closure: set[str] = set()
    visited: set[tuple[str, bool]] = set()
    while pending:
        relative, exact_path_mode = pending.pop()
        if (relative, exact_path_mode) in visited:
            continue
        visited.add((relative, exact_path_mode))
        closure.add(relative)
        tree = ast.parse((WORKSPACE / relative).read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node, function in visitor.rows:
            if exact_path_mode and isinstance(node, ast.ImportFrom) and node.level:
                # These four adapters are loaded with a top-level synthetic
                # module name. Their guarded relative product imports cannot
                # resolve; each file's reviewed standalone fallback executes.
                continue
            for name in _absolute_import_names(relative, node):
                if (relative, function, name) in _DEFERRED_BACKEND_IMPORT_SITES:
                    continue
                parts = name.split(".")
                for count in range(len(parts), 0, -1):
                    candidate = _local_module_path(".".join(parts[:count]))
                    if candidate is not None:
                        if (candidate, False) not in visited:
                            pending.append((candidate, False))
                        break
    return closure


class ProviderIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = CapabilityRegistryLoader().load(
            allow_sample_fallback=False, check_files=False
        )

    def test_all_external_writer_and_verifier_import_closures_are_exactly_pinned(self) -> None:
        providers = (
            Nfl2k5UnifiedVisualProvider(),
            Nfl2k5ScorebugProvider(),
            Apf2k8JerseyColorProvider(),
            Apf2k8PantsColorProvider(),
            Apf2k8HelmetColorProvider(),
            Apf2k8ShoulderColorProvider(),
        )
        self.assertEqual(
            [len(provider.module_pins) for provider in providers],
            # The reviewed closure includes the original visual adapters and
            # the integrated music, scorebug, animation and gameplay compilers.
            # The unified visual provider includes standalone/SCNE Crib
            # textures, bounded Crib/Stadium geometry, stock PLAY route copy,
            # formation/play clone writer, fixed-slot audio, the fail-closed
            # AUDO family-label loader, package-local equipment, and every
            # local module in those exact import closures.
            [173, 9, 8, 9, 8, 9],
        )
        for provider in providers:
            entries = [provider.backend_module]
            verifier = getattr(provider, "verifier_module", None)
            if verifier:
                entries.append(verifier)
            expected_closure = local_import_closure(*entries)
            if isinstance(provider, Nfl2k5UnifiedVisualProvider):
                # The backend directly imports reviewed product audio modules
                # and dynamically loads these seven adapters by exact path.
                # Both package init files stay absent so their unrelated eager
                # GUI/provider imports cannot escape the finite pin closure.
                adapters = frozenset({
                    "mod_editor/core/nfl2k5_guardian_cap.py",
                    "mod_editor/core/nfl2k5_animation.py",
                    "mod_editor/core/nfl2k5_animation_math.py",
                    "mod_editor/core/nfl2k5_scorebug_runtime.py",
                    "mod_editor/core/nfl2k5_scorebug_resources.py",
                    "mod_editor/core/nfl2k5_scorebug_ingame.py",
                    "mod_editor/core/nfl2k5_music_policy.py",
                    "mod_editor/core/nfl2k5_music_catalog.py",
                    "mod_editor/core/nfl2k5_music_build.py",
                    "mod_editor/core/nfl2k5_music_banks.py",
                    "mod_editor/core/nfl2k5_music_metadata.py",
                    "mod_editor/core/nfl2k5_music_storage.py",
                    "mod_editor/core/nfl2k5_music_archive.py",
                    "mod_editor/core/nfl2k5_xbe_space.py",
                    "mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py",
                    "mod_editor/core/nfl2k5_season_cap.py",
                    "mod_editor/core/nfl2k5_screen_timing.py",

                    "mod_editor/core/nfl2k5_audo_fixed_slots.py",
                    "mod_editor/core/nfl2k5_safe_text_banks.py",
                    "mod_editor/core/nfl2k5_scorebug_unified_adapter.py",
                    "mod_editor/core/nfl2k5_stadium_texture_writer.py",
                    "mod_editor/core/nfl2k5_p8_texture_writer.py",
                    "mod_editor/core/nfl2k5_unif_color_writer.py",
                    "mod_editor/core/nfl2k5_uniform_equipment_writer.py",
                })
                expected_closure.update(local_import_closure(
                    *adapters, exact_path_entries=frozenset({
                        "mod_editor/core/nfl2k5_audo_fixed_slots.py",
                        "mod_editor/core/nfl2k5_safe_text_banks.py",
                        "mod_editor/core/nfl2k5_scorebug_unified_adapter.py",
                        "mod_editor/core/nfl2k5_stadium_texture_writer.py",
                        "mod_editor/core/nfl2k5_p8_texture_writer.py",
                        "mod_editor/core/nfl2k5_unif_color_writer.py",
                        "mod_editor/core/nfl2k5_uniform_equipment_writer.py",
                    })
                ))
                self.assertNotIn("mod_editor/__init__.py", expected_closure)
                self.assertNotIn("mod_editor/core/__init__.py", expected_closure)
                self.assertNotIn("mod_editor/core/providers.py", expected_closure)
                self.assertEqual(len(provider.module_pins), len(expected_closure))
            self.assertEqual(set(provider.module_pins), expected_closure)
            for relative, expected in provider.module_pins.items():
                path = WORKSPACE / relative
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_nlink, 1)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        unified = providers[0]
        self.assertEqual(
            unified.data_pins,
            {
                "mod_editor/data/nfl2k5_crib_catalog.v1.json":
                    "c78801144df2f070e003ba458c5affa15a52cc00221cc1a3d9983f1fbf172cd8",
                "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json":
                    "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173",
                "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json":
                    "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
                "reports/specs/nfl2k5_crib_static_position_targets.v1.json":
                    "90f955166c8582f7041bd0d936bacbef1f44b3869487f71535acec1caeb44b4f",
            },
        )
        for relative, expected in unified.data_pins.items():
            path = WORKSPACE / relative
            self.assertLess(path.stat().st_size, 8 * 1024 * 1024)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        for provider in providers[1:]:
            schema = WORKSPACE / provider.recipe_schema_file
            self.assertEqual(
                hashlib.sha256(schema.read_bytes()).hexdigest(),
                provider.recipe_schema_file_sha256,
            )

    def test_unified_bundle_is_init_free_and_executes_help_and_visual_validate(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider()
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            with _pinned_execution_bundle(
                WORKSPACE,
                {**provider.module_pins, **provider.data_pins},
                provider.backend_module,
                "NFL unified visual backend",
            ) as entry:
                bundle_root = entry.parents[1]
                self.assertFalse((bundle_root / "mod_editor/__init__.py").exists())
                self.assertFalse((bundle_root / "mod_editor/core/__init__.py").exists())
                help_result = subprocess.run(
                    (sys.executable, "-B", os.fspath(entry), "--help"),
                    cwd=Path("/"),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn("{validate,build,verify}", help_result.stdout)

                validate_result = subprocess.run(
                    (
                        sys.executable,
                        "-B",
                        os.fspath(entry),
                        "validate",
                        "--project",
                        os.fspath(job.backend_project),
                    ),
                    cwd=Path("/"),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
                self.assertEqual(
                    validate_result.returncode, 0, validate_result.stderr
                )
                report = json.loads(validate_result.stdout)
                self.assertEqual(report["kind_counts"], {"team_identity": 1})
                self.assertTrue(report["schema_and_png_pins_valid"])

    def test_unified_registry_authorization_is_an_exact_contract(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider()
        capability = self.registry.get("nfl2k5.uniforms.all_visual")
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            provider._validate_capability(job, capability)
            provider._validate_capability(
                replace(job, capability_id="nfl2k5.crib.assets"),
                self.registry.get("nfl2k5.crib.assets"),
            )
            provider._validate_capability(
                replace(job, capability_id="nfl2k5.audio.fixed_audo_wav"),
                self.registry.get("nfl2k5.audio.fixed_audo_wav"),
            )
            provider._validate_capability(
                replace(
                    job, capability_id="nfl2k5.audio.ausb_fixed_range_wav"
                ),
                self.registry.get("nfl2k5.audio.ausb_fixed_range_wav"),
            )

            mutations = []
            raw = copy.deepcopy(capability.raw)
            raw["backend"]["command"] += " --unreviewed"
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["backend"]["extra"] = True
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["source_container"]["hash_pins"].append("0" * 64)
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["selectors"]["fields"].append(
                {"allowed": "anything", "name": "raw_offset", "required": False}
            )
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["classification"] = Classification.RUNTIME_PROVED.value
            mutations.append(replace(capability, raw=raw))
            mutations.append(
                replace(capability, classification=Classification.RUNTIME_PROVED)
            )

            for altered in mutations:
                with self.subTest(altered=altered):
                    with self.assertRaisesRegex(ProviderError, "does not authorize"):
                        provider._validate_capability(job, altered)

    def test_unified_source_record_identity_is_exact(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider(
            source_hasher=lambda path, progress: (PINNED_SOURCE_SHA, path.stat().st_size)
        )
        capability = self.registry.get("nfl2k5.uniforms.all_visual")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = request(root)
            forged = (
                replace(job.source, fingerprint_id="another-retail-disc"),
                replace(job.source, kind="directory"),
                replace(job.source, inspected_path=str(root / "missing.iso")),
            )
            for source in forged:
                with self.subTest(source=source):
                    with self.assertRaises(ProviderError):
                        provider.preflight(
                            replace(job, source=source), capability, lambda event: None
                        )

    def test_provider_owned_inputs_reject_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            unified = request(root)
            os.link(unified.backend_project, root / "project-alias.json")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                Nfl2k5UnifiedVisualProvider()._read_project_header(
                    unified.backend_project
                )

            scorebug = scorebug_request(root)
            scorebug_provider = Nfl2k5ScorebugProvider()
            project = scorebug_provider._read_project(scorebug.backend_project)
            scorebug_png = root / "score_buga.png"
            os.link(scorebug_png, root / "scorebug-alias.png")
            with self.assertRaises(ProviderError):
                scorebug_provider._pin_project_pngs(project)

            apf_root = root / "apf"
            apf_root.mkdir()
            apf = apf_request(apf_root)
            os.link(apf.backend_project, apf_root / "recipe-alias.json")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                Apf2k8JerseyColorProvider()._read_recipe(apf.backend_project)

            source = root / "source.bin"
            source.write_bytes(b"source")
            os.link(source, root / "source-alias.bin")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                Nfl2k5UnifiedVisualProvider._regular_non_symlink(source, "source")

    def test_private_bundle_executes_hashed_bytes_after_workspace_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            main = tools / "main.py"
            dependency = tools / "dependency.py"
            main.write_text("import dependency\nprint(dependency.VALUE)\n", encoding="utf-8")
            dependency.write_text("VALUE = 'PINNED'\n", encoding="utf-8")
            pins = {
                "tools/main.py": hashlib.sha256(main.read_bytes()).hexdigest(),
                "tools/dependency.py": hashlib.sha256(dependency.read_bytes()).hexdigest(),
            }

            with _pinned_execution_bundle(
                workspace, pins, "tools/main.py", "test backend"
            ) as staged:
                main.write_text("print('FORGED MAIN')\n", encoding="utf-8")
                dependency.write_text("VALUE = 'FORGED DEPENDENCY'\n", encoding="utf-8")
                result = subprocess.run(
                    (sys.executable, os.fspath(staged)),
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "PINNED\n")

    def test_private_bundle_rejects_hardlinked_modules_and_post_stage_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            module = tools / "main.py"
            module.write_text("print('safe')\n", encoding="utf-8")
            digest = hashlib.sha256(module.read_bytes()).hexdigest()
            os.link(module, tools / "alias.py")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                with _pinned_execution_bundle(
                    workspace, {"tools/main.py": digest}, "tools/main.py", "test backend"
                ):
                    pass

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            module = tools / "main.py"
            module.write_text("print('safe')\n", encoding="utf-8")
            digest = hashlib.sha256(module.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ProviderError, "bundle changed"):
                with _pinned_execution_bundle(
                    workspace, {"tools/main.py": digest}, "tools/main.py", "test backend"
                ) as staged:
                    staged.chmod(0o600)
                    staged.write_text("print('forged')\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
