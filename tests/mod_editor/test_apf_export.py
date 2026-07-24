"""Focused mocked tests for the editor's read-only APF export surface."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from mod_editor.__main__ import main as editor_main
from mod_editor.core.apf_export import (
    ApfJerseyExportResult,
    export_apf_jersey,
)
from mod_editor.core.errors import OutputRefusedError, ValidationError


class ApfEditorExportTests(unittest.TestCase):
    def test_adapter_passes_only_source_asset_and_absent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "0A"
            source.write_bytes(b"mocked; the backend owns the retail hash gate")
            output = root / "asset-06-export"
            backend_result = SimpleNamespace(
                output_dir=output,
                provenance=output / "provenance.json",
                asset_index=6,
                file_count=11,
            )
            with mock.patch(
                "mod_editor.core.apf_export._backend_export",
                return_value=backend_result,
            ) as backend:
                result = export_apf_jersey(source, 6, output)

            self.assertEqual(
                result,
                ApfJerseyExportResult(
                    output, output / "provenance.json", 6, 11
                ),
            )
            # _new_output_directory canonicalises the destination (resolve),
            # so the backend receives output.resolve(): equal to output on Linux
            # but /private/var-expanded on macOS and long-name-expanded on
            # Windows. Assert the resolved form so the call contract holds on
            # every OS while still pinning source, index and the exact directory.
            backend.assert_called_once_with(source, 6, output.resolve())
            self.assertFalse(output.exists())

            existing = root / "existing"
            existing.mkdir()
            with mock.patch("mod_editor.core.apf_export._backend_export") as backend:
                with self.assertRaises(OutputRefusedError):
                    export_apf_jersey(source, 6, existing)
                backend.assert_not_called()
            for invalid in (-1, 24, True):
                with self.subTest(asset_index=invalid), mock.patch(
                    "mod_editor.core.apf_export._backend_export"
                ) as backend:
                    with self.assertRaises(ValidationError):
                        export_apf_jersey(source, invalid, root / f"invalid-{invalid}")
                    backend.assert_not_called()

    def test_headless_cli_uses_fixed_contract_and_rejects_raw_or_invalid_selector(self) -> None:
        result = ApfJerseyExportResult(
            Path("/new/export"), Path("/new/export/provenance.json"), 6, 11
        )
        stdout = io.StringIO()
        with mock.patch(
            "mod_editor.__main__.export_apf_jersey", return_value=result
        ) as export, contextlib.redirect_stdout(stdout):
            self.assertEqual(
                editor_main(
                    [
                        "--export-apf-jersey",
                        "/new/export",
                        "--source-0a",
                        "/owned/0A",
                        "--asset-index",
                        "6",
                    ]
                ),
                0,
            )
        export.assert_called_once_with(
            source_0a=Path("/owned/0A"),
            asset_index=6,
            output_dir=Path("/new/export"),
        )
        report = stdout.getvalue()
        self.assertIn("MOD_EDITOR_APF_JERSEY_EXPORT_CREATED", report)
        self.assertIn("archive_written=false", report)
        self.assertIn("bank_labels=0,1", report)
        self.assertIn("provenance=/new/export/provenance.json", report)

        for extra in (("--entry", "875"), ("--offset", "1234")):
            with self.subTest(raw_argument=extra[0]), mock.patch(
                "mod_editor.__main__.export_apf_jersey"
            ) as export, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    editor_main(
                        [
                            "--export-apf-jersey",
                            "/new/export",
                            "--source-0a",
                            "/owned/0A",
                            "--asset-index",
                            "6",
                            *extra,
                        ]
                    )
                export.assert_not_called()
        with mock.patch(
            "mod_editor.__main__.export_apf_jersey"
        ) as export, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                editor_main(
                    [
                        "--export-apf-jersey",
                        "/new/export",
                        "--source-0a",
                        "/owned/0A",
                        "--asset-index",
                        "24",
                    ]
                )
            export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
