#!/usr/bin/env python3
"""Exercise the clean APF product closure, optionally against a private game source."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import zipfile


# Do not dirty an already-audited release stage merely by importing it.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
EXPECTED_PRODUCT_VERSION = "0.1.0-alpha.73"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

EXTRACTOR = ROOT / "tools/vendor/extract-xiso/build/extract-xiso"
EXTRACTOR_LICENSE = ROOT / "tools/vendor/extract-xiso/LICENSE.TXT"
EXTRACTOR_SIZE = 51_336
EXTRACTOR_SHA256 = "222e7763df8f16d9b252c625fac5ef551cd25cdf031a785b3ec73c6e53c5d7f2"
# The Windows extractor, built from the same vendored extract-xiso 2.7.1 source
# so a Windows user can hand the app a .iso directly.  Pinned exactly like the
# ELF above: a bundled binary nobody can rebuild from this tree at review time
# is only trustworthy if its bytes are fixed here.
EXTRACTOR_WINDOWS = ROOT / "tools/vendor/extract-xiso/build/extract-xiso.exe"
EXTRACTOR_WINDOWS_SIZE = 293_273
EXTRACTOR_WINDOWS_SHA256 = (
    "e9567fe31b168b226531ed532714b3e1cc9070cdfac0c102fb881e2825aee68d"
)
EXTRACTOR_LICENSE_SIZE = 3_115
EXTRACTOR_LICENSE_SHA256 = "719d9e9a12c470a20d9f1988a03108fd99bb0b07a5340c6bbf3caf524b7adf01"
H7A_ENCODER = ROOT / "tools/apf_h7a_optimal"
H7A_ENCODER_SIZE = 14_472
H7A_ENCODER_SHA256 = (
    "9061866e31f1a2930eceaa4fb8652ef1b7aa9b04cbce0174cc0eae125f8e49ab"
)
INSTALLER = ROOT / "packaging/apf2k8_mod_studio_installer.py"
STADIUM_MATERIAL_FINDINGS_SIZE = 2_341
STADIUM_MATERIAL_FINDINGS_SHA256 = (
    "cefcf72b94df7e5af69fb67f2f306168f4bdd9716464b15767038f598fa4a99d"
)

EXPECTED_RETAIL_HASHES = frozenset(
    {
        "c45aab61de93773dfe25adbae5749ad5adb3f3369a6c0106b2159ad603b6fe53",
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
        "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
        "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
        "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        "39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8",
    }
)

PRODUCT_MODULES = (
    "mod_editor.apf_studio",
    "mod_editor.apf_studio.__main__",
    "mod_editor.apf_studio.asset_io",
    "mod_editor.apf_studio.audio_annotations",
    "mod_editor.apf_studio.audio_batch_export",
    "mod_editor.apf_studio.audio_encoding",
    "mod_editor.apf_studio.audio_replacement_pack",
    "mod_editor.apf_studio.backend",
    "mod_editor.apf_studio.build",
    "mod_editor.apf_studio.catalog",
    "mod_editor.apf_studio.custom_team_appearance_qt",
    "mod_editor.apf_studio.facade",
    "mod_editor.apf_studio.field_art",
    "mod_editor.apf_studio.gui",
    "mod_editor.apf_studio.helmet_crest_design",
    "mod_editor.apf_studio.helmet_logo_placement",
    "mod_editor.apf_studio.helmet_logo_placement_qt",
    "mod_editor.apf_studio.helmet_logo_regions",
    "mod_editor.apf_studio.helmet_logo_regions_qt",
    "mod_editor.apf_studio.inspectors",
    "mod_editor.apf_studio.launcher",
    "mod_editor.apf_studio.model_export",
    "mod_editor.apf_studio.model_export_qt",
    "mod_editor.apf_studio.model_import",
    "mod_editor.apf_studio.models",
    "mod_editor.apf_studio.player_ratings",
    "mod_editor.apf_studio.player_positions",
    "mod_editor.apf_studio.player_rating_sheet",
    "mod_editor.apf_studio.product_findings",
    "mod_editor.apf_studio.project",
    "mod_editor.apf_studio.roster_workspace",
    "mod_editor.apf_studio.roster_workspace_qt",
    "mod_editor.apf_studio.save_appearance",
    "mod_editor.apf_studio.save_playbooks",
    "mod_editor.apf_studio.save_playbooks_qt",
    "mod_editor.apf_studio.session",
    "mod_editor.apf_studio.source",
    "mod_editor.apf_studio.stadium",
    "mod_editor.apf_studio.stadium_model_import",
    "mod_editor.apf_studio.stadium_material_findings",
    "mod_editor.apf_studio.text_sheet",
    "mod_editor.apf_studio.textlogo_authoring",
    "mod_editor.apf_studio.uniform_targets",
    "mod_editor.apf_studio.uniform_equipment_colors_qt",
    "mod_editor.apf_studio.uniform_independence",
    "mod_editor.apf_studio.uniform_independence_panel",
    "mod_editor.core.capabilities",
    "mod_editor.core.errors",
    "mod_editor.core.json_stream",
    "mod_editor.core.model",
    "mod_editor.core.texture_master",
    "mod_editor.gui.apf_audio_waveform_qt",
    "mod_editor.gui.stadium_viewer",
)

# Import the complete writer/export dependency closure.  Importing performs no
# game reads and no GUI work; a missing product dependency fails here rather
# than on a modder's first build.
TOOL_MODULES = (
    "apf_audio",
    "apf_audo_exact_slot",
    "apf_ausb_audio",
    "apf_ausb_exact_slot",
    "apf_custom_team_appearance_patch",
    "apf_digital_font_layout",
    "apf_digital_font_transport",
    "apf_helmet_color_transport",
    "apf_helmet_crest_mask_fit",
    "apf_helmet_crest_wrap_patch",
    "apf_helmet_crest_wrap_verify",
    "apf_inner",
    "apf_jersey_selector_patch",
    "apf_outer",
    "apf_pants_color_transport",
    "apf_player_rating_patch",
    "apf_player_position_patch",
    "apf_roster",
    "apf_roster_composite_patch",
    "apf_roster_identity_patch",
    "apf_save_custom_team_appearance",
    "apf_stfs_roster_extract",
    "apf_scene",
    "apf_stadium_catalog_position_patch",
    "apf_stadium_catalog_position_verify",
    "apf_stadium_static_position_patch",
    "apf_stadium_static_position_verify",
    "apf_shoulder_color_transport",
    "apf_textlogo_patch",
    "apf_textlogo_verify",
    "apf_texture_patch",
    "apf_uniform_equipment_color_patch",
    "apf_txt_loc",
    "apf_txt_loc_patch",
    "apf_uniform_inventory",
    "apf_uniform_selector_patch",
    "apf_uniform_mip_patch",
    "apf_xenos_bc1_mip_layout",
    "apf_xenos_dxn_mip_layout",
    "apf_xenos_dxt5a",
    "apf_xenos_mip_layout",
    "director_inventory",
    "nfl_dxt1",
    "nfl_outer",
    "nfl_scene_probe",
    "nfl_txtr",
    "playbook_inventory",
    "string_table_inventory",
    "validate_apf_custom_team_appearance",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _require_regular(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} is missing: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a regular non-symlink file")
    return info


def _check_clean_stage() -> None:
    for name in (
        ".cache",
        ".codex-tmp",
        "assets",
        "cache",
        "captures",
        "derived",
        "evidence",
        "exports",
        "extracted",
        "originals",
        "reports",
        "runtime",
        "screenshots",
    ):
        require(not os.path.lexists(ROOT / name),
                f"private or retail-derived root is present: {name}")
    for path in ROOT.rglob("__pycache__"):
        raise RuntimeError(f"bytecode cache was staged: {path.relative_to(ROOT)}")
    for path in ROOT.rglob("*.pyc"):
        raise RuntimeError(f"compiled Python file was staged: {path.relative_to(ROOT)}")


def _check_extractor() -> None:
    windows_binary = _require_regular(
        EXTRACTOR_WINDOWS, "reviewed extract-xiso Windows binary"
    )
    require(
        windows_binary.st_size == EXTRACTOR_WINDOWS_SIZE
        and _sha256(EXTRACTOR_WINDOWS) == EXTRACTOR_WINDOWS_SHA256,
        "the reviewed extract-xiso Windows binary is not the pinned build",
    )
    binary = _require_regular(EXTRACTOR, "reviewed extract-xiso binary")
    license_info = _require_regular(EXTRACTOR_LICENSE, "extract-xiso license")
    require(binary.st_size == EXTRACTOR_SIZE and _sha256(EXTRACTOR) == EXTRACTOR_SHA256,
            "reviewed extract-xiso size/hash changed")
    require(binary.st_mode & stat.S_IXUSR, "reviewed extract-xiso is not executable")
    require(
        license_info.st_size == EXTRACTOR_LICENSE_SIZE
        and _sha256(EXTRACTOR_LICENSE) == EXTRACTOR_LICENSE_SHA256,
        "reviewed extract-xiso license size/hash changed",
    )


def _check_h7a_encoder() -> None:
    binary = _require_regular(H7A_ENCODER, "reviewed H7A encoder")
    require(
        binary.st_size == H7A_ENCODER_SIZE
        and _sha256(H7A_ENCODER) == H7A_ENCODER_SHA256,
        "reviewed H7A encoder size/hash changed",
    )
    require(
        binary.st_mode & stat.S_IXUSR and not binary.st_mode & 0o022,
        "reviewed H7A encoder mode changed",
    )


def _check_desktop_contract() -> None:
    desktop = ROOT / "packaging/apf2k8-mod-studio.desktop"
    _require_regular(desktop, "APF desktop entry")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read(desktop, encoding="utf-8")
    require(parser.sections() == ["Desktop Entry"], "desktop entry has unexpected sections")
    row = parser["Desktop Entry"]
    expected = {
        "Type": "Application",
        "Name": "APF 2K8 Mod Studio",
        "Exec": "apf2k8-mod-studio",
        "TryExec": "apf2k8-mod-studio",
        "Icon": "apf2k8-mod-studio",
        "Terminal": "false",
    }
    for key, value in expected.items():
        require(row.get(key) == value, f"desktop entry {key} changed")

    launcher = ROOT / "tools/launch_apf2k8_mod_studio.sh"
    launcher_info = _require_regular(launcher, "no-terminal APF launcher")
    require(launcher_info.st_mode & stat.S_IXUSR,
            "no-terminal APF launcher is not executable")
    script = launcher.read_text(encoding="utf-8")
    for marker in (
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONNOUSERSITE=1",
        "python3 -m mod_editor.apf_studio",
        "zenity --error",
        "kdialog",
        "XDG_STATE_HOME",
        "mktemp -d",
        "python3-pyqt5",
        "python3-pil",
        "last-launch.log",
    ):
        require(marker in script, f"no-terminal launcher omitted {marker!r}")
    require(":0" not in script and "xdotool" not in script,
            "launcher contains active-desktop automation")
    syntax = subprocess.run(
        ["bash", "-n", str(launcher)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    require(syntax.returncode == 0,
            f"no-terminal launcher has invalid shell syntax: {syntax.stderr.strip()}")

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPATH"] = str(ROOT)
    version = subprocess.run(
        [sys.executable, "-m", "mod_editor.apf_studio", "--version"],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        check=False,
    )
    require(
        version.returncode == 0
        and "APF 2K8 Mod Studio alpha" in version.stdout
        and f"({EXPECTED_PRODUCT_VERSION})" in version.stdout
        and "QApplication" not in version.stderr,
        f"headless APF GUI entry point failed: {version.stderr.strip()}",
    )


def _load_installer_module() -> object:
    _require_regular(INSTALLER, "per-user APF installer")
    spec = importlib.util.spec_from_file_location("_apf2k8_release_installer", INSTALLER)
    require(spec is not None and spec.loader is not None,
            "per-user APF installer could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _check_install_contract() -> None:
    scripts = (
        ROOT / "install.sh",
        ROOT / "uninstall.sh",
        ROOT / "APF-2K8-Mod-Studio.sh",
        ROOT / "tools/launch_apf2k8_mod_studio.sh",
    )
    for script in scripts:
        info = _require_regular(script, "install/launch script")
        require(info.st_mode & stat.S_IXUSR, f"install/launch script is not executable: {script.name}")
        text = script.read_text(encoding="utf-8")
        require(
            all(token not in text for token in ("rm -rf", "rm -fr", "DISPLAY=:0", "xdotool")),
            f"install/launch script acquired a destructive or active-desktop token: {script.name}",
        )
        if script.name in {"install.sh", "uninstall.sh"}:
            require(
                "PYTHONDONTWRITEBYTECODE=1" in text,
                f"installer bootstrap can contaminate its audited source: {script.name}",
            )
        syntax = subprocess.run(
            ["bash", "-n", str(script)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        require(syntax.returncode == 0,
                f"install/launch script has invalid shell syntax: {script.name}: {syntax.stderr.strip()}")
    _require_regular(ROOT / "APF2K8-README.md", "top-level install guide")

    installer = _load_installer_module()
    with tempfile.TemporaryDirectory(prefix="apf-runtime-install-") as temporary_name:
        temporary = Path(temporary_name)
        home = temporary / "home"
        home.mkdir()
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        environment["XDG_DATA_HOME"] = str(home / "xdg-data")
        environment["XDG_STATE_HOME"] = str(home / "xdg-state")
        environment.pop("DISPLAY", None)
        environment.pop("WAYLAND_DISPLAY", None)

        first = installer.install(ROOT, environment=environment)
        paths = first.paths
        resolved_home = home.resolve(strict=True)
        require(first.action == "installed", "first per-user install was not classified as installed")
        require(paths.app_dir == resolved_home / "xdg-data/apf2k8-mod-studio/app",
                "per-user application path changed")
        require(paths.wrapper == resolved_home / ".local/bin/apf2k8-mod-studio",
                "per-user command path changed")
        for path in (paths.app_dir, paths.wrapper, paths.desktop, paths.icon, paths.record):
            require(os.path.lexists(path), f"per-user install omitted {path}")

        installed_desktop = configparser.ConfigParser(interpolation=None, strict=True)
        installed_desktop.optionxform = str
        installed_desktop.read(paths.desktop, encoding="utf-8")
        desktop_row = installed_desktop["Desktop Entry"]
        require(desktop_row["Exec"] == f'"{paths.wrapper}"',
                "installed desktop entry does not use the absolute per-user wrapper")
        require(desktop_row["TryExec"] == str(paths.wrapper),
                "installed desktop TryExec does not use the absolute per-user wrapper")
        require(desktop_row["X-APF2K8-Mod-Studio-Managed"] == "true",
                "installed desktop entry has no ownership marker")

        version = subprocess.run(
            [str(paths.wrapper), "--version"],
            env=environment,
            cwd=home,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        require(
            version.returncode == 0
            and "APF 2K8 Mod Studio alpha" in version.stdout
            and f"({EXPECTED_PRODUCT_VERSION})" in version.stdout
            and "QApplication" not in version.stderr,
            f"installed absolute wrapper failed headlessly: {version.stderr.strip()}",
        )

        second = installer.install(ROOT, environment=environment)
        require(second.action == "updated", "second per-user install did not use the update path")

        preserved = (
            home / ".cache/apf2k8-mod-studio/preserve-me",
            home / ".config/apf2k8-mod-studio/preserve-me",
            home / "xdg-state/apf2k8-mod-studio/preserve-me",
            home / "projects/preserve-me.apf2k8mod",
        )
        for sentinel in preserved:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("user data, not installer-owned\n", encoding="utf-8", newline="\n")
        removed = installer.uninstall(environment=environment)
        require(removed.action == "uninstalled", "per-user uninstall result changed")
        require(all(path.exists() for path in preserved),
                "uninstall removed cache, settings, state, or a user project")
        require(
            not any(os.path.lexists(path) for path in (
                paths.app_dir, paths.record, paths.wrapper, paths.desktop, paths.icon
            )),
            "uninstall left an unchanged installer-owned program path behind",
        )


def _check_namespace_isolation() -> None:
    """Prove APF does not pull the legacy mixed-game package initializers."""

    require(not (ROOT / "mod_editor/__init__.py").exists(),
            "legacy mod_editor/__init__.py was staged into the APF product")
    require(not (ROOT / "mod_editor/core/__init__.py").exists(),
            "legacy mod_editor/core/__init__.py was staged into the APF product")
    top = sys.modules.get("mod_editor")
    core = sys.modules.get("mod_editor.core")
    require(top is not None and getattr(top, "__file__", None) is None,
            "mod_editor is not the tested APF namespace package")
    require(core is not None and getattr(core, "__file__", None) is None,
            "mod_editor.core is not the tested APF namespace package")


def _check_audo_authoring_doc() -> None:
    guide = ROOT / "docs/product/APF_AUDO_EXACT_SLOT_XMA1_EDITOR.md"
    info = _require_regular(guide, "standalone AUDO exact-slot authoring guide")
    require(info.st_size < 256 * 1024,
            "standalone AUDO exact-slot authoring guide is unexpectedly large")
    text = guide.read_text(encoding="utf-8")
    for marker in (
        "2,261 standalone `AUDO` resources",
        "pre-encoded",
        "Xenia boot-compatible",
        "cue consumption inconclusive",
        "The shareable `.apf2k8mod` archive stores only",
        "AUSB commentary, soundtrack, and music replacement",
        "canonical raw packets from",
        "the user's supplied replacement",
    ):
        require(marker in text,
                f"standalone AUDO authoring guide omitted {marker!r}")


def _check_ausb_feasibility_doc() -> None:
    guide = ROOT / "docs/product/APF_AUSB_EXACT_SLOT_FEASIBILITY.md"
    info = _require_regular(guide, "external AUSB exact-slot feasibility guide")
    require(info.st_size < 256 * 1024,
            "external AUSB exact-slot feasibility guide is unexpectedly large")
    text = guide.read_text(encoding="utf-8")
    for marker in (
        "45,514 semantic substream rows",
        "45,513 canonical physical ranges",
        "40,316 unique whole-payload hashes",
        "crosses the end",
        "of `0A` and start of `0B`",
        "completed objective capture experiment was negative/inconclusive",
        "mutated candidate nor stock Track 12",
        "neither authored-audio consumption nor stock fallback",
        "No encoder ships with Mod Studio",
        "user-configured external",
    ):
        require(marker in text,
                f"external AUSB feasibility guide omitted {marker!r}")


def _check_external_xma1_bridge_doc() -> None:
    guide = ROOT / "docs/mod_editor/apf2k8_external_xma1_encoder.md"
    info = _require_regular(guide, "external XMA1 encoder authoring guide")
    require(info.st_size < 128 * 1024,
            "external XMA1 encoder authoring guide is unexpectedly large")
    text = guide.read_text(encoding="utf-8")
    for marker in (
        "does not ship an XMA1 encoder",
        "There are two PCM routes",
        "selected-sound workflow",
        "Batch PCM16 folder or ZIP workflow",
        "apf2k8_mod_studio_audio_replacement_pack/v2",
        "256 supplied WAVs",
        "one argument per line",
        "`{encoded_size}`",
        "final XMA1 output",
        "do not claim that fake output",
        "cannot determine the copyright or license",
    ):
        require(marker in text,
                f"external encoder authoring guide omitted {marker!r}")


def _exercise_external_xma1_bridge(modules: dict[str, object]) -> None:
    """Prove only the retail-free PCM/process plumbing, never an encoder."""

    audio_encoding = modules["mod_editor.apf_studio.audio_encoding"]
    session = modules["mod_editor.apf_studio.session"]
    facade = modules["mod_editor.apf_studio.facade"]
    audo_exact_slot = importlib.import_module("apf_audo_exact_slot")
    target = audio_encoding.Pcm16Target(1, 22_050, 16, 0x800)
    with tempfile.TemporaryDirectory(prefix="apf-runtime-pcm-bridge-") as temporary_name:
        temporary = Path(temporary_name)
        template = temporary / "authoring.wav"
        receipt = audio_encoding.export_pcm16_template(template, target)
        payload = template.read_bytes()
        require(
            receipt.schema == "apf2k8_audio_pcm16_template/v1"
            and receipt.byte_size == 76
            and receipt.encoded_size == 0x800
            and receipt.contains_retail_audio is False
            and len(payload) == 76
            and payload[:4] == b"RIFF"
            and payload[8:12] == b"WAVE"
            and payload[-32:] == bytes(32),
            "retail-free exact PCM16 silence-template contract changed",
        )
        encoder = audio_encoding.ExternalXma1Encoder(
            Path(sys.executable).resolve(strict=True),
            arguments=(
                "-c",
                "import shutil,sys;shutil.copyfile(sys.argv[1],sys.argv[2])",
                "{input}",
                "{output}",
            ),
        )
        encoded = encoder.encode(template, target)
        encoded_receipt = encoded.receipt
        require(
            encoded.xma1_riff == payload
            and encoded_receipt.get("status")
            == "encoded_pending_exact_slot_validation"
            and encoded_receipt.get("no_shell") is True
            and encoded_receipt.get("encoder_binary_bundled") is False
            and encoded_receipt.get("contains_encoder_binary") is False
            and encoded_receipt.get("bridge_reads_loaded_game") is False
            and encoded_receipt.get("bridge_passes_loaded_game_path") is False
            and encoded_receipt.get("encoder_input_is_user_selected_pcm") is True
            and str(sys.executable) not in json.dumps(encoded_receipt, sort_keys=True),
            "external-XMA1 process adapter or retail-free receipt changed",
        )
        try:
            audo_exact_slot.parse_xma1_riff(encoded.xma1_riff)
        except audo_exact_slot.ExactSlotImportError:
            pass
        else:
            raise RuntimeError(
                "synthetic PCM copy was mistaken for encoder-compatible XMA1"
            )
    for owner in (session.ApfSession, facade.ApfStudioFacade):
        for method in (
            "audio_pcm_target",
            "export_audio_pcm_template",
            "replace_audio_from_pcm",
        ):
            require(
                callable(getattr(owner, method, None)),
                f"external-XMA1 bridge omitted {owner.__name__}.{method}",
            )


def _exercise_retail_free_project(modules: dict[str, object]) -> None:
    from PIL import Image

    models = modules["mod_editor.apf_studio.models"]
    project = modules["mod_editor.apf_studio.project"]
    session = modules["mod_editor.apf_studio.session"]
    source_module = modules["mod_editor.apf_studio.source"]
    with tempfile.TemporaryDirectory(prefix="apf-runtime-project-") as temporary_name:
        temporary = Path(temporary_name)
        png = temporary / "replacement.png"
        Image.new("RGBA", (4, 4), (20, 40, 60, 255)).save(png, format="PNG")
        data, digest = session.ApfSession._validated_png(
            png, width=4, height=4, contract="pants"
        )
        require(hashlib.sha256(data).hexdigest() == digest,
                "strict PNG validation hash changed")
        modification = models.Modification(
            asset_id="apf:uniform:pants:00",
            kind="uniform",
            replacement_path=png,
            replacement_sha256=digest,
            metadata={"family": "pants", "asset_index": 0},
        )
        archive = temporary / "fixture.apf2k8mod"
        project.save_project(
            archive,
            source_sha256=source_module.EXPECTED_0A_SHA256,
            modifications=(modification,),
            title="Retail-free runtime fixture",
        )
        with zipfile.ZipFile(archive) as reader:
            names = {item.filename for item in reader.infolist()}
            manifest = json.loads(reader.read("project.json"))
        require(
            names == {
                "project.json",
                f"replacements/{hashlib.sha256(modification.asset_id.encode('utf-8')).hexdigest()}.png",
            },
            "project archive acquired undeclared members",
        )
        distribution = manifest.get("distribution", {})
        require(
            distribution.get("contains_original_game_bytes") is False
            and distribution.get("contains_original_preimages") is False,
            "project retail-free declaration changed",
        )
        imported = temporary / "imported"
        _manifest, replacements, _annotations = project.load_project(
            archive,
            expected_source_sha256=source_module.EXPECTED_0A_SHA256,
            destination_dir=imported,
        )
        require(len(replacements) == 1 and replacements[0].replacement_sha256 == digest,
                "project replacement did not round-trip")


def _exercise_texture_master(modules: dict[str, object]) -> None:
    """Round-trip a user-authored APF master plus one native mask edit."""

    from PIL import Image

    texture_master = modules["mod_editor.core.texture_master"]
    with tempfile.TemporaryDirectory(prefix="apf-runtime-master-") as name:
        root = Path(name)
        source = root / "user-logo.png"
        Image.new("RGBA", (32, 12), (240, 240, 240, 255)).save(source)
        baseline = root / "semantic-before-edit.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 136)).save(baseline)
        final = root / "semantic-final.png"
        edited = Image.open(baseline).copy()
        edited.putpixel((5, 3), (0, 255, 0, 136))
        edited.save(final)
        archive = texture_master.save_texture_master_bundle(
            source_image=source,
            destination=root / "fixture.2ktexmaster",
            asset_id="apf.runtime.user.crest",
            editor_target="apf2k8_xbox360-helmet-crest",
            native_width=8,
            native_height=8,
            compiled_native_png=final,
            compiled_native_baseline_png=baseline,
            high_resolution_scale=2,
            editor_transform={"operation": "runtime-semantic-mask-edit"},
        )
        loaded = texture_master.load_texture_master_bundle(archive)
        require(
            loaded.manifest["native_raster_edit"]["changed_pixel_count"] == 1
            and loaded.native_png == final.read_bytes()
            and loaded.native_baseline_png == baseline.read_bytes(),
            "APF high-resolution texture-master runtime contract changed",
        )


def _exercise_retail_free_audio_project(modules: dict[str, object]) -> None:
    """Prove the public project carries only synthetic replacement packets.

    This deliberately exercises the cheap project-boundary packet validator,
    not the FFmpeg import gate.  A release check must never require a retail
    game source or ship an audio sample merely to prove its project format.
    """

    models = modules["mod_editor.apf_studio.models"]
    project = modules["mod_editor.apf_studio.project"]
    source_module = modules["mod_editor.apf_studio.source"]
    with tempfile.TemporaryDirectory(prefix="apf-runtime-audio-project-") as temporary_name:
        temporary = Path(temporary_name)
        # 0x08000000 means sequence 0, metadata 2, first-frame offset 0,
        # packet skip 0.  The remaining synthetic bytes are zero.
        payload = b"\x08\x00\x00\x00" + bytes(0x800 - 4)
        digest = hashlib.sha256(payload).hexdigest()
        replacement = temporary / "user-authored.xma1-packets"
        replacement.write_bytes(payload)
        asset_id = "apf:audio:audo:988:19"
        modification = models.Modification(
            asset_id=asset_id,
            kind=models.AUDO_EXACT_SLOT_KIND,
            replacement_path=replacement,
            replacement_sha256=digest,
            metadata={
                "outer_table_index": 988,
                "inner_file_index": 19,
                "encoded_size": len(payload),
                "sample_rate": 22_050,
                "channel_count": 1,
                "declared_sample_count": 4_096,
                "packet_count": 1,
                "writer_schema": models.AUDO_EXACT_SLOT_WRITER_SCHEMA,
            },
        )
        archive = temporary / "audio.apf2k8mod"
        project.save_project(
            archive,
            source_sha256=source_module.EXPECTED_0A_SHA256,
            modifications=(modification,),
            title="Retail-free exact-slot audio fixture",
        )
        member = (
            "replacements/"
            f"{hashlib.sha256(asset_id.encode('utf-8')).hexdigest()}"
            ".xma1-packets"
        )
        with zipfile.ZipFile(archive) as reader:
            names = {item.filename for item in reader.infolist()}
            manifest = json.loads(reader.read("project.json"))
            stored_payload = reader.read(member)
        require(
            names == {"project.json", member}
            and stored_payload == payload
            and not stored_payload.startswith(b"RIFF"),
            "exact-slot audio project acquired a wrapper, preimage, or undeclared member",
        )
        distribution = manifest.get("distribution", {})
        require(
            distribution.get("contains_original_game_bytes") is False
            and distribution.get("contains_original_preimages") is False
            and manifest.get("replacement_count") == 1,
            "exact-slot audio project retail-free declaration changed",
        )
        imported = temporary / "imported"
        _manifest, replacements, _annotations = project.load_project(
            archive,
            expected_source_sha256=source_module.EXPECTED_0A_SHA256,
            destination_dir=imported,
        )
        require(
            len(replacements) == 1
            and replacements[0].kind == models.AUDO_EXACT_SLOT_KIND
            and replacements[0].replacement_sha256 == digest
            and replacements[0].replacement_path.read_bytes() == payload,
            "exact-slot audio project replacement did not round-trip",
        )
        refused = temporary / "protected-source-audio.apf2k8mod"
        try:
            project.save_project(
                refused,
                source_sha256=source_module.EXPECTED_0A_SHA256,
                modifications=(modification,),
                protected_replacement_hashes=(digest,),
            )
        except project.ProjectError as exc:
            require(
                "protected source game data" in str(exc),
                "source-audio hash refusal returned an unexpected error",
            )
        else:
            raise RuntimeError("project accepted a protected source-audio payload hash")
        require(not os.path.lexists(refused),
                "failed protected-audio save left a project behind")


def _check_audio_packet_reuse_release_boundary(
    modules: dict[str, object],
) -> None:
    """Behaviorally prove same- and cross-domain source-packet refusal.

    The fixtures are synthetic.  Each candidate has a new whole-payload hash
    but deliberately contains one exact 0x800-byte packet from a protected
    source domain.  Going through both ``ApfSession`` and ``ApfBuildService``
    proves the public edit and build boundaries combine AUDO and AUSB packet
    protection instead of merely checking target-bank whole-payload hashes.
    """

    session_module = modules["mod_editor.apf_studio.session"]
    build_module = modules["mod_editor.apf_studio.build"]
    models = modules["mod_editor.apf_studio.models"]
    catalog_module = modules["mod_editor.apf_studio.catalog"]
    inspectors = modules["mod_editor.apf_studio.inspectors"]
    audo = importlib.import_module("apf_audo_exact_slot")
    ausb = importlib.import_module("apf_ausb_exact_slot")
    packet_size = 0x800
    refusal_marker = "reuses a complete 0x800-byte audio packet"

    require(
        audo.SOURCE_PACKET_SIZE == packet_size
        and ausb.XMA_PACKET_SIZE == packet_size,
        "AUDO/AUSB source-packet sizes changed",
    )

    def packet(fill: int, discriminator: int) -> bytes:
        value = bytearray([fill] * packet_size)
        value[:4] = (0x08000000).to_bytes(4, "big")
        value[4:8] = discriminator.to_bytes(4, "big")
        return bytes(value)

    audo_source_payload = packet(0x21, 1) + packet(0x22, 2)
    ausb_source_payload = packet(0x31, 3) + packet(0x32, 4)
    user_packet = packet(0x71, 5)
    candidates = {
        "AUDO same-domain source packet": user_packet
        + audo_source_payload[packet_size:],
        "AUDO cross-domain AUSB source packet": user_packet
        + ausb_source_payload[packet_size:],
        "AUSB same-domain source packet": user_packet
        + ausb_source_payload[packet_size:],
        "AUSB cross-domain AUDO source packet": user_packet
        + audo_source_payload[packet_size:],
    }
    candidate_hashes = {
        hashlib.sha256(payload).hexdigest() for payload in candidates.values()
    }
    audo_source_hash = hashlib.sha256(audo_source_payload).hexdigest()
    ausb_source_hash = hashlib.sha256(ausb_source_payload).hexdigest()

    excluded_filler_hashes = candidate_hashes | {
        audo_source_hash,
        ausb_source_hash,
    }
    ausb_filler_hashes: list[str] = []
    filler_value = 0
    while len(ausb_filler_hashes) < (
        ausb.EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT - 1
    ):
        candidate = f"{filler_value:064x}"
        filler_value += 1
        if candidate not in excluded_filler_hashes:
            ausb_filler_hashes.append(candidate)
    ausb_payload_hashes = frozenset((*ausb_filler_hashes, ausb_source_hash))
    require(
        len(ausb_payload_hashes)
        == ausb.EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT,
        "synthetic AUSB source fingerprint inventory is incomplete",
    )

    def packet_hashes(payload: bytes) -> frozenset[bytes]:
        return frozenset(
            hashlib.sha256(payload[offset : offset + packet_size]).digest()
            for offset in range(0, len(payload), packet_size)
        )

    audo_source_fingerprints = audo.SourceAudioFingerprints(
        domain=audo.SOURCE_AUDIO_DOMAIN,
        payload_sha256s=frozenset({audo_source_hash}),
        packet_sha256s=packet_hashes(audo_source_payload),
        payload_occurrence_count=audo.EXPECTED_STANDALONE_AUDO_COUNT,
        packet_occurrence_count=2,
    )
    ausb_source_fingerprints = audo.SourceAudioFingerprints(
        domain=ausb.SOURCE_AUDIO_DOMAIN,
        payload_sha256s=ausb_payload_hashes,
        packet_sha256s=packet_hashes(ausb_source_payload),
        payload_occurrence_count=ausb.EXPECTED_CANONICAL_RANGE_COUNT,
        packet_occurrence_count=2,
    )
    require(
        candidate_hashes.isdisjoint(
            audo_source_fingerprints.payload_sha256s
            | ausb_source_fingerprints.payload_sha256s
        ),
        "synthetic packet-reuse probe accidentally matched a whole source payload",
    )

    encoded_size = packet_size * 2
    audo_target = audo.ExactSlotTarget(
        channels=2,
        sample_rate=48_000,
        encoded_size=encoded_size,
        declared_sample_count=4_096,
        loop_start_bit=0,
        loop_end_bit=encoded_size * 8,
        loop_subframe=0,
    )
    audo_resolved = audo.ResolvedExactSlot(
        asset_id="apf:audio:audo:0:0",
        name="synthetic-audo",
        outer_index=0,
        inner_index=0,
        target=audo_target,
        pack_name="0A",
        pack_offset=0,
        encoded_size=encoded_size,
        source_payload_sha256=audo_source_hash,
    )
    ausb_owner = ausb.AusbOwner(
        descriptor_outer_index=1,
        descriptor_inner_index=2,
        substream_index=3,
        bank_name="synthetic-ausb",
        external_filename="synthetic-ausb-bank",
        channels=2,
        sample_rate=48_000,
        duration_value_bits=0,
        duration_seconds=1.0,
        declared_sample_count=4_096,
    )
    ausb_target = ausb.ResolvedExactSlot(
        asset_id=ausb_owner.asset_id,
        requested_owner=ausb_owner,
        owners=(ausb_owner,),
        canonical_physical_id="apf:audio:ausb:physical:1:0:4096",
        external_outer_index=1,
        external_range_offset=0,
        target=ausb.ExactSlotTarget(
            channels=2,
            sample_rate=48_000,
            encoded_size=encoded_size,
            declared_sample_count=4_096,
        ),
        physical_spans=(ausb.PhysicalSpan("0A", 0, encoded_size, 0),),
        source_payload_sha256=ausb_source_hash,
    )

    def accepted_audo(
        data: bytes,
        _target: object,
        fingerprints: object,
        **_keywords: object,
    ) -> object:
        audo.reject_source_audio_reuse(data, fingerprints)
        return audo.ExactSlotImportResult(
            payload=data,
            receipt={
                "replacement": {"payload_sha256": hashlib.sha256(data).hexdigest()}
            },
        )

    def accepted_ausb(
        data: bytes,
        _target: object,
        fingerprints: object,
        **_keywords: object,
    ) -> object:
        ausb.reject_source_audio_reuse(data, fingerprints)
        return ausb.ExactSlotImportResult(
            payload=data,
            receipt={
                "replacement": {"payload_sha256": hashlib.sha256(data).hexdigest()}
            },
        )

    original_audo_scan = audo.original_audio_fingerprints
    original_ausb_scan = ausb.original_audio_fingerprints
    original_audo_validator = audo.validate_exact_slot_import
    original_ausb_validator = ausb.validate_exact_slot_import
    audo.original_audio_fingerprints = lambda _source: audo_source_fingerprints
    ausb.original_audio_fingerprints = lambda _source: ausb_source_fingerprints
    audo.validate_exact_slot_import = accepted_audo
    ausb.validate_exact_slot_import = accepted_ausb
    try:
        with tempfile.TemporaryDirectory(
            prefix="apf-audio-packet-release-gate-"
        ) as temporary_name:
            temporary = Path(temporary_name)
            game_root = temporary / "game"
            game_root.mkdir()
            index_0a = game_root / "0A"
            index_0a.write_bytes(b"synthetic packet-fingerprint source")
            source = models.ApfSource(
                selected_path=game_root,
                game_root=game_root,
                index_0a=index_0a,
                source_sha256="1" * 64,
                source_size=index_0a.stat().st_size,
                xex_sha256="2" * 64,
                display_name="Synthetic APF packet gate",
            )
            catalog = catalog_module.ApfCatalog(
                source_sha256=source.source_sha256,
                outer_count=0,
                iff_count=0,
                non_iff_count=0,
                inner_count=0,
                assets=(),
                uniform_assets=(),
                capabilities=(),
                audio_selection_manifest=temporary / "selection.json",
            )
            for probe_index, (label, payload) in enumerate(candidates.items()):
                active = session_module.ApfSession(
                    source,
                    catalog,
                    cache_root=temporary / f"cache-{probe_index}",
                )
                supplied = temporary / f"probe-{probe_index}.xma"
                supplied.write_bytes(payload)
                try:
                    if label.startswith("AUDO "):
                        active._resolve_audo_identity = lambda _identity: audo_resolved
                        identity = inspectors.ExportIdentity(
                            "audo", 0, 0, None, "synthetic-audo"
                        )
                        active.replace_audo_exact_slot(identity, supplied)
                    else:
                        active._resolve_ausb_identity = lambda _identity: ausb_target
                        identity = inspectors.ExportIdentity(
                            "ausb_substream", 1, 2, 3, "synthetic-ausb"
                        )
                        active.replace_ausb_exact_slot(identity, supplied)
                except session_module.SessionError as exc:
                    require(
                        refusal_marker in str(exc),
                        f"{label} was refused for the wrong reason: {exc}",
                    )
                else:
                    raise RuntimeError(
                        f"public product boundary accepted an exact {label.lower()}"
                    )
                finally:
                    active.close()

            build_service = build_module.ApfBuildService.__new__(
                build_module.ApfBuildService
            )
            build_service._audo_source_fingerprints = audo_source_fingerprints
            build_service._ausb_source_fingerprints = ausb_source_fingerprints
            for label, payload in candidates.items():
                try:
                    build_service._reject_any_source_audio_reuse(payload)
                except build_module.BuildError as exc:
                    require(
                        refusal_marker in str(exc),
                        f"build {label} was refused for the wrong reason: {exc}",
                    )
                else:
                    raise RuntimeError(
                        f"public build boundary accepted an exact {label.lower()}"
                    )
    finally:
        audo.original_audio_fingerprints = original_audo_scan
        ausb.original_audio_fingerprints = original_ausb_scan
        audo.validate_exact_slot_import = original_audo_validator
        ausb.validate_exact_slot_import = original_ausb_validator


def _check_static_product_contract(modules: dict[str, object]) -> int:
    package = modules["mod_editor.apf_studio"]
    source = modules["mod_editor.apf_studio.source"]
    build = modules["mod_editor.apf_studio.build"]
    project = modules["mod_editor.apf_studio.project"]
    session = modules["mod_editor.apf_studio.session"]
    catalog = modules["mod_editor.apf_studio.catalog"]
    facade = modules["mod_editor.apf_studio.facade"]
    models = modules["mod_editor.apf_studio.models"]
    targets = modules["mod_editor.apf_studio.uniform_targets"]
    gui = modules["mod_editor.apf_studio.gui"]
    entry = modules["mod_editor.apf_studio.__main__"]
    inspectors = modules["mod_editor.apf_studio.inspectors"]
    asset_io = modules["mod_editor.apf_studio.asset_io"]
    findings = modules["mod_editor.apf_studio.product_findings"]
    player_ratings = modules["mod_editor.apf_studio.player_ratings"]
    player_positions = modules["mod_editor.apf_studio.player_positions"]
    player_rating_sheet = modules["mod_editor.apf_studio.player_rating_sheet"]
    roster_workspace = modules["mod_editor.apf_studio.roster_workspace"]
    roster_workspace_qt = modules["mod_editor.apf_studio.roster_workspace_qt"]
    save_appearance = modules["mod_editor.apf_studio.save_appearance"]
    model_export = modules["mod_editor.apf_studio.model_export"]
    model_export_qt = modules["mod_editor.apf_studio.model_export_qt"]
    model_import = modules["mod_editor.apf_studio.model_import"]
    stadium_model_import = modules["mod_editor.apf_studio.stadium_model_import"]
    audio_batch_export = modules["mod_editor.apf_studio.audio_batch_export"]
    audio_replacement_pack = modules[
        "mod_editor.apf_studio.audio_replacement_pack"
    ]
    stadium = modules["mod_editor.apf_studio.stadium"]
    stadium_material_findings = modules[
        "mod_editor.apf_studio.stadium_material_findings"
    ]
    textlogo_authoring = modules["mod_editor.apf_studio.textlogo_authoring"]
    stadium_viewer = modules["mod_editor.gui.stadium_viewer"]
    capability_core = modules["mod_editor.core.capabilities"]
    core_model = modules["mod_editor.core.model"]

    require(
        package.__version__ == EXPECTED_PRODUCT_VERSION,
        "APF source/UI version is not the Alpha34 candidate",
    )

    source_hashes = set(source.EXPECTED_GAME_HASHES.values()) | {source.EXPECTED_ISO_SHA256}
    require(source_hashes == EXPECTED_RETAIL_HASHES,
            "the complete seven-file APF recognition ledger changed")
    require(set(project.RETAIL_HASHES) == EXPECTED_RETAIL_HASHES,
            "project retail-hash refusal set is incomplete")
    require(
        project.MAX_PROJECT_FILES == 131_072
        and project.MAX_PROJECT_MANIFEST_BYTES == 128 * 1024 * 1024
        and project.MAX_REPLACEMENT_BYTES == 24 * 1024 * 1024
        and project.MAX_PROJECT_ARCHIVE_BYTES == 2 * 1024 * 1024 * 1024
        and project.MAX_PROJECT_EXPANDED_BYTES == 2 * 1024 * 1024 * 1024
        and project.MAX_PROJECT_BYTES == project.MAX_PROJECT_ARCHIVE_BYTES
        and project.MAX_PROJECT_FILES > 63_112 + 45_514 + 1,
        "retail-free project bounds no longer fit all ratings plus AUSB-scale edits",
    )
    require(
        set(digest for _size, digest in build.EXPECTED_TREE.values())
        == set(source.EXPECTED_GAME_HASHES.values()),
        "transactional build source ledger is incomplete",
    )
    registry = capability_core.CapabilityRegistryLoader().load(
        allow_sample_fallback=False,
        check_files=False,
    )
    require(
        len(registry.capabilities) == 70
        and len(registry.for_game(core_model.GameId.APF2K8)) == 37,
        "shared/APF capability registry counts changed",
    )
    cards = catalog.build_capability_cards()
    require(len(cards) == 37 and len({item.capability_id for item in cards}) == 37,
            "APF capability surface is not exactly 37 unique rows")
    require(len(models.APF_CATEGORY_ORDER) == 14,
            "APF complete sidebar category count changed")
    editable = {item.capability_id for item in cards if item.status is models.ApfStatus.EDITABLE}
    expected_editable = {
        "apf2k8.audio.ausb_xma_export",
        "apf2k8.audio.xma_export",
        "apf2k8.colors.uniform_selector_appearance_custom_team",
        "apf2k8.field_art.base_texture",
        "apf2k8.logos_cards.draft_logo",
        "apf2k8.logos_cards.team_logo",
        "apf2k8.logos_cards.team_logo_cache",
        "apf2k8.logos_cards.textlogo_wordmarks",
        "apf2k8.menus.layouts",
        "apf2k8.models.scne_gltf",
        "apf2k8.models.scne_same_count_position",
        "apf2k8.players.roster",
        "apf2k8.scorebug_presentation.digital_font",
        "apf2k8.scripts.director_playbook",
        "apf2k8.stadiums.textures",
        "apf2k8.uniforms.helmet_color_00_23",
        "apf2k8.uniforms.jersey_00_23",
        "apf2k8.uniforms.pants_color_00_23",
        "apf2k8.uniforms.shoulder_color_00_23",
    }
    require(
        editable == expected_editable
        and all(
            models.CAPABILITY_ACTION_BINDINGS[capability_id].has_complete_editor
            or models.CAPABILITY_ACTION_BINDINGS[
                capability_id
            ].has_verified_one_shot_writer
            for capability_id in editable
        ),
        "public editable capability/action boundary changed",
    )
    textlogo_patch = importlib.import_module("apf_textlogo_patch")
    textlogo_verify = importlib.import_module("apf_textlogo_verify")
    textlogo_targets = textlogo_patch.load_targets()
    require(
        textlogo_authoring.WORDMARK_WIDTH == 512
        and textlogo_authoring.WORDMARK_HEIGHT == 128
        and textlogo_authoring.WORDMARK_FIT_MODES == ("contain", "cover", "stretch")
        and len(textlogo_targets) == 206
        and textlogo_targets[0]["asset_index"] == 0
        and textlogo_targets[-1]["asset_index"] == 205
        and textlogo_patch.SELECTOR_SLOT == 6
        and textlogo_patch.INNER_NAME == "textlogo_color"
        and textlogo_patch.CATALOG_SHA256
        == "39a1e0c944a846e24d7a11c52d6a0fbba4091959f01856d3a087efde01ba490c"
        and callable(textlogo_patch.build_patch)
        and callable(textlogo_verify.verify_copied_volume)
        and models.CAPABILITY_ACTION_BINDINGS[
            "apf2k8.logos_cards.textlogo_wordmarks"
        ].has_complete_editor
        and hasattr(gui, "ApfTextLogoPanel"),
        "complete 206-slot APF wordmark editor contract changed",
    )
    model_binding = models.CAPABILITY_ACTION_BINDINGS[
        "apf2k8.models.scne_gltf"
    ]
    model_panel_source = inspect.getsource(
        model_export_qt.PlayerEquipmentModelExportPanel
    )
    require(
        [(item.key, item.outer_index, item.inner_index, item.expected_mesh_count)
         for item in model_export.TARGETS]
        == [("helmet", 1310, 128, 33), ("player", 1310, 273, 1)]
        and model_import.EXPORT_SCHEMA
        == "apf2k8_private_static_model_export/v2"
        and model_import.IMPORT_SCHEMA
        == "apf2k8_same_topology_model_import/v1"
        and "POSITION-only" in model_import.MODEL_IMPORT_BOUNDARY
        and model_binding.handler_id == "uniforms.model_position_roundtrip"
        and model_binding.actions
        == frozenset(
            {
                models.ApfProductAction.PREVIEW,
                models.ApfProductAction.EXPORT,
                models.ApfProductAction.BUILD_COPY,
            }
        )
        and model_binding.one_shot_target
        == "mod_editor.apf_studio.model_import:import_model"
        and model_binding.output_kind == "verified copied 0A"
        and model_binding.has_verified_one_shot_writer
        and "Import edited glTF" in model_panel_source
        and "import_model(" in model_panel_source,
        "APF helmet/player model POSITION round-trip closure changed",
    )
    stadium_model_binding = models.CAPABILITY_ACTION_BINDINGS[
        "apf2k8.models.scne_same_count_position"
    ]
    require(
        stadium_model_binding.handler_id
        == "stadium.selected_mesh_position_roundtrip"
        and stadium_model_binding.one_shot_target
        == "mod_editor.apf_studio.stadium_model_import:import_edited_mesh"
        and stadium_model_binding.output_kind == "verified copied 1A"
        and stadium_model_binding.has_verified_one_shot_writer
        and callable(stadium_model_import.import_edited_mesh),
        "APF stadium selected-mesh POSITION round-trip closure changed",
    )
    audio_card = next(
        item for item in cards if item.capability_id == "apf2k8.audio.xma_export"
    )
    audio_binding = models.CAPABILITY_ACTION_BINDINGS["apf2k8.audio.xma_export"]
    audo_exact_slot = importlib.import_module("apf_audo_exact_slot")
    ausb_exact_slot = importlib.import_module("apf_ausb_exact_slot")
    audio_tool = importlib.import_module("apf_audio")
    ausb_audio_tool = importlib.import_module("apf_ausb_audio")
    audio_browser_source = inspect.getsource(gui.InspectorBrowser)
    main_window_source = inspect.getsource(gui.ApfStudioMainWindow)
    require(
        all(
            marker in audio_browser_source
            for marker in (
                "_applied_audio_query_token",
                "_audio_query_controls_match_applied",
                "_cleared_audio_shortlist",
                "tuple(self._audio_shortlist.items())",
                "_audio_preview_request_is_current",
                "_audio_preview_job",
                "_complete_audio_preview",
                "Cancel preview",
                "Cancel waveform",
                "cancel_requested=cancel_event.is_set",
                "cancel_requested=lambda: request.cancelled",
                "Updating audio results…",
                "shortlist_matching_button",
                "_matching_audio_cache_key",
                "_matching_audio_shortlist_additions",
                "_add_matching_audio_to_shortlist",
            )
        )
        and callable(
            getattr(gui.InspectorBrowser, "cancel_pending_audio_reads", None)
        )
        and all(
            marker in main_window_source
            for marker in (
                "_cancel_transient_audio_reads",
                "_defer_source_load_until_idle",
                "_resume_pending_source_load",
                "_close_when_workers_finish",
                "self.facade.close()",
            )
        ),
        "APF Audio query, shortlist recovery, or preview ownership contract changed",
    )
    cancellable_apis = (
        asset_io.ApfAssetIO.export_audio_identity,
        asset_io.ApfAssetIO.prepare_audio_preview,
        session.ApfSession.prepare_audio_preview,
        facade.ApfStudioFacade.prepare_audio_preview,
        audio_tool.export_selected,
        ausb_audio_tool.export_substream,
        audo_exact_slot.decode_stored_payload_to_wav,
        ausb_exact_slot.decode_stored_payload_to_wav,
    )
    decoder_source = inspect.getsource(audio_tool)
    task_source = inspect.getsource(gui.ApfStudioMainWindow._run_task)
    require(
        issubclass(audio_tool.AudioCancelled, audio_tool.AudioError)
        and issubclass(asset_io.AudioPreviewCancelled, asset_io.AssetIoError)
        and all(
            "cancel_requested" in inspect.signature(function).parameters
            for function in cancellable_apis
        )
        and all(
            marker in decoder_source
            for marker in (
                "start_new_session=True",
                "os.killpg",
                "signal.SIGTERM",
                "signal.SIGKILL",
                "run_cancellable_subprocess",
                "_publish_complete_file",
            )
        )
        and "return False" in task_source
        and "return True" in task_source,
        "APF Audio preview process cancellation or task-admission contract changed",
    )
    require(
        audio_card.status is models.ApfStatus.EDITABLE
        and audio_binding.actions
        == frozenset(
            {
                models.ApfProductAction.PREVIEW,
                models.ApfProductAction.EXPORT,
                models.ApfProductAction.REPLACE,
                models.ApfProductAction.REVERT,
            }
        )
        and audio_binding.has_complete_editor
        and audio_binding.handler_id
        == "audio.standalone_audo_exact_slot_editor"
        and audio_binding.bound_replace_methods == ("replace_audo_exact_slot",)
        and callable(getattr(facade.ApfStudioFacade, "replace_audo_exact_slot", None))
        and callable(getattr(gui.InspectorBrowser, "_replace_audio", None))
        and callable(getattr(gui.InspectorBrowser, "_revert_audio", None))
        and models.AUDO_EXACT_SLOT_KIND == "audo_exact_slot_xma1"
        and models.AUDO_EXACT_SLOT_WRITER_SCHEMA
        == "apf2k8_audo_exact_slot_xma1/v1"
        and audo_exact_slot.SCHEMA == "apf2k8_audo_exact_slot_import/v1"
        and audo_exact_slot.MODIFICATION_KIND == models.AUDO_EXACT_SLOT_KIND
        and audo_exact_slot.EXPECTED_STANDALONE_AUDO_COUNT == 2_261
        and "XMA1 encoder" in audio_binding.product_note
        and "AUSB soundtrack/commentary bank replacement remain Coming Soon"
        not in audio_binding.product_note
        and all(
            callable(getattr(audo_exact_slot, name, None))
            for name in (
                "resolve_target",
                "resolve_targets",
                "original_audio_fingerprints",
                "original_payload_hashes",
                "reject_source_audio_reuse",
                "validate_exact_slot_import",
                "validate_stored_payload",
                "validate_stored_payload_complete",
                "decode_stored_payload_to_wav",
            )
        )
        and callable(getattr(project, "validate_xma1_packet_payload", None))
        and callable(
            getattr(build.ApfBuildService, "_compile_audo_exact_slot_overlay", None)
        )
        and any("2,261" in finding for finding in audio_card.findings)
        and any("pre-encoded" in finding for finding in audio_card.findings),
        "standalone AUDO exact-slot XMA1 editor is not fully packaged and bound",
    )
    ausb_card = next(
        item for item in cards if item.capability_id == "apf2k8.audio.ausb_xma_export"
    )
    ausb_binding = models.CAPABILITY_ACTION_BINDINGS[
        "apf2k8.audio.ausb_xma_export"
    ]
    ausb_exact_slot = importlib.import_module("apf_ausb_exact_slot")
    require(
        ausb_card.status is models.ApfStatus.EDITABLE
        and ausb_binding.actions
        == frozenset(
            {
                models.ApfProductAction.PREVIEW,
                models.ApfProductAction.EXPORT,
                models.ApfProductAction.REPLACE,
                models.ApfProductAction.REVERT,
            }
        )
        and ausb_binding.has_complete_editor
        and ausb_binding.handler_id == "audio.ausb_exact_slot_editor"
        and ausb_binding.bound_replace_methods == ("replace_ausb_exact_slot",)
        and callable(getattr(facade.ApfStudioFacade, "replace_ausb_exact_slot", None))
        and callable(getattr(session.ApfSession, "replace_ausb_exact_slot", None))
        and callable(getattr(gui.InspectorBrowser, "_replace_audio", None))
        and callable(getattr(gui.InspectorBrowser, "_revert_audio", None))
        and models.AUSB_EXACT_SLOT_KIND == "ausb_exact_slot_xma1"
        and models.AUSB_EXACT_SLOT_WRITER_SCHEMA
        == "apf2k8_ausb_exact_slot_xma1/v1"
        and ausb_exact_slot.SCHEMA == "apf2k8_ausb_exact_slot_import/v1"
        and ausb_exact_slot.MODIFICATION_KIND == models.AUSB_EXACT_SLOT_KIND
        and ausb_exact_slot.ASSET_ID_PREFIX == "apf:audio:ausb"
        and ausb_exact_slot.EXPECTED_DESCRIPTOR_COUNT == 20
        and ausb_exact_slot.EXPECTED_OWNER_ROW_COUNT == 45_514
        and ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT == 45_513
        and ausb_exact_slot.EXPECTED_EXTERNAL_BANK_COUNT == 19
        and ausb_exact_slot.EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT == 40_316
        and ausb_exact_slot.XMA_PACKET_SIZE == 0x800
        and ausb_exact_slot.asset_id(1, 2, 3) == "apf:audio:ausb:1:2:3"
        and all(
            callable(getattr(ausb_exact_slot, name, None))
            for name in (
                "resolve_target",
                "resolve_targets",
                "resolve_jukebox_pair",
                "original_audio_fingerprints",
                "original_payload_hashes",
                "reject_source_audio_reuse",
                "validate_exact_slot_import",
                "validate_stored_payload",
                "validate_stored_payload_complete",
                "decode_stored_payload_to_wav",
                "compile_physical_writes",
                "merge_compiled_writes",
                "validate_paired_soundtrack_import",
            )
        )
        and callable(
            getattr(build.ApfBuildService, "_compile_ausb_exact_slot_overlays", None)
        )
        and any("45,514" in finding for finding in ausb_card.findings)
        and any("pre-encoded" in finding for finding in ausb_card.findings),
        "AUSB exact-slot XMA1 editor is not fully packaged and bound",
    )
    _check_audio_packet_reuse_release_boundary(modules)
    roster_card = next(
        item for item in cards if item.capability_id == "apf2k8.players.roster"
    )
    roster_binding = models.CAPABILITY_ACTION_BINDINGS["apf2k8.players.roster"]
    require(
        roster_card.status is models.ApfStatus.EDITABLE
        and roster_binding.actions
        == frozenset(
            {
                models.ApfProductAction.PREVIEW,
                models.ApfProductAction.EXPORT,
                models.ApfProductAction.REPLACE,
                models.ApfProductAction.REVERT,
            }
        )
        and roster_binding.has_complete_editor
        and roster_binding.handler_id
        == "roster.player_team_name_and_base_rating_editor"
        and roster_binding.bound_replace_methods
        == (
            "replace_roster_identity_text",
            "replace_player_base_rating",
            "replace_player_position",
        )
        and all(
            callable(getattr(facade.ApfStudioFacade, method, None))
            for method in (
                "roster_identity_value",
                "roster_identity_edit_scope",
                "roster_identity_is_product_editable",
                "replace_roster_identity_text",
                "player_base_rating_value",
                "replace_player_base_rating",
                "player_position_value",
                "replace_player_position",
                "revert",
            )
        )
        and "token-preserving ROST"
        in facade.TEAM_DISPLAY_NAME_EDIT_SCOPE_MESSAGE,
        "bounded roster name/base-rating/player-position editor is not fully bound",
    )
    empty_reserve_plan = roster_workspace.ReserveRosterPlan.empty()
    reserve_payload = roster_workspace.encode_reserve_plan(empty_reserve_plan)
    reserve_document = json.loads(reserve_payload)
    require(
        roster_workspace.SCHEMA == "apf2k8_roster_reserve_plan/v1"
        and roster_workspace.FILE_EXTENSION == ".apf2k8roster"
        and roster_workspace.TEAM_COUNT == 32
        and roster_workspace.STOCK_ACTIVE_SLOTS == 42
        and roster_workspace.PROJECT_RESERVE_SLOTS == 11
        and roster_workspace.MASTER_ROSTER_SLOTS == 53
        and roster_workspace.PLAYER_COUNT == 2_254
        and roster_workspace.MAX_PLAN_BYTES == 256 * 1024
        and empty_reserve_plan.assigned_count == 0
        and roster_workspace.decode_reserve_plan(reserve_payload)
        == empty_reserve_plan
        and reserve_document["distribution"]
        == {
            "contains_executable_patch": False,
            "contains_retail_bytes": False,
            "contains_source_active_memberships": False,
            "payload": "user-authored reserve player indices only",
        }
        and b"active_player_indices" not in reserve_payload
        and b"source_memberships" not in reserve_payload
        and all(
            callable(getattr(facade.ApfStudioFacade, name, None))
            for name in (
                "roster_workspace",
                "assign_roster_reserve",
                "open_roster_reserve_plan",
                "save_roster_reserve_plan",
            )
        )
        and roster_workspace_qt.RosterReservePlanner.__name__
        == "RosterReservePlanner",
        "retail-free 32-team 53-player planning closure is incomplete",
    )
    roster_boundary_note = roster_workspace_qt.RUNTIME_BOUNDARY_NOTE
    require(
        all(
            marker in roster_boundary_note
            for marker in (
                "Build Modded Game does not apply",
                "+0x120..+0x126",
                "safe extension storage remains unresolved",
                "one exact consumer",
            )
        )
        and "runtime_boundary_note"
        in roster_workspace_qt.RosterReservePlanner.__dict__["__init__"].__code__.co_names,
        "roster planner does not disclose the proved slot-43 runtime boundary",
    )
    lock_message = facade.ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE.casefold()
    require(
        all(
            marker in lock_message
            for marker in (
                "player first/last names",
                "separate save players",
                "raw-save jersey",
                "depth",
                "membership",
                "team abbreviations",
                "runtime-locked",
            )
        )
        and not any(
            hasattr(facade.ApfStudioFacade, method)
            for method in (
                "replace_player_name",
                "replace_team_abbreviation",
                "replace_player_jersey_number",
                "replace_player_membership",
                "import_player_rating_sheet",
            )
        ),
        "locked APF roster fields were widened beyond the proved product scope",
    )

    class _LockedRosterSession:
        @staticmethod
        def roster_identity_edit_scope(_asset_id: str) -> None:
            return None

        @staticmethod
        def roster_identity_is_product_editable(_asset_id: str) -> bool:
            return False

    locked_facade = facade.ApfStudioFacade()
    locked_facade.session = _LockedRosterSession()
    try:
        locked_facade.replace_roster_identity_text(
            "apf:roster-name:synthetic-player", "USER TEXT"
        )
    except facade.FacadeError as exc:
        require(
            str(exc) == facade.ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE,
            "locked roster identity field returned an unexpected public error",
        )
    else:
        raise RuntimeError("public facade accepted a locked roster identity field")

    rating_schema = player_ratings.load_player_rating_schema()
    position_schema = player_positions.load_player_position_schema()
    rating_patch = importlib.import_module("apf_player_rating_patch")
    position_patch = importlib.import_module("apf_player_position_patch")
    appearance_patch = importlib.import_module(
        "apf_custom_team_appearance_patch"
    )
    save_appearance_patch = importlib.import_module(
        "apf_save_custom_team_appearance"
    )
    stfs_roster_extract = importlib.import_module("apf_stfs_roster_extract")
    roster_composite = importlib.import_module("apf_roster_composite_patch")
    unknown_rating = next(
        field
        for field in rating_schema.fields
        if field.field_id == "unknown_rating_d4"
    )
    synthetic_record = bytearray(rating_schema.record_stride)
    synthetic_record[rating_schema.fields[0].relative_offset] = 99
    synthetic_record[unknown_rating.relative_offset] = 100
    synthetic_values = rating_schema.decode_record(synthetic_record)
    require(
        len(rating_schema.fields) == 31
        and sum(field.named for field in rating_schema.fields) == 27
        and (rating_schema.native_minimum, rating_schema.native_maximum) == (0, 100)
        and (
            rating_schema.stock_observed_minimum,
            rating_schema.stock_observed_maximum,
        )
        == (0, 99)
        and unknown_rating.relative_offset == 0xD4
        and unknown_rating.label == "Unknown Rating (0xD4)"
        # 0xBD, 0xC5 and 0xD2 became named editable fields; height is the one
        # remaining excluded neighbour.
        and [
            item.relative_offset
            for item in rating_schema.excluded_neighbor_bytes
        ]
        == [0xD9]
        and sorted(field.relative_offset for field in rating_schema.fields)
        == list(range(0xBA, 0xD9))
        and rating_schema.runtime_status == "token_preserving_runtime_loaded"
        and synthetic_values["speed"] == 99
        and synthetic_values["unknown_rating_d4"] == 100,
        "retail-free APF native base-rating dictionary changed",
    )
    rating_targets = tuple(
        rating_patch.target_for(0, field.field_id)
        for field in rating_schema.fields
    )
    require(
        rating_patch.EXPECTED_PLAYER_COUNT == 2_254
        and (rating_patch.PUBLIC_MINIMUM, rating_patch.PUBLIC_MAXIMUM) == (0, 99)
        and len(rating_targets) == 31
        and tuple(target.field_id for target in rating_targets)
        == tuple(field.field_id for field in rating_schema.fields)
        and tuple(target.record_relative_offset for target in rating_targets)
        == tuple(field.relative_offset for field in rating_schema.fields)
        and rating_patch.target_for(2_253, "speed").asset_id
        == "apf:player-rating:2253:speed"
        and rating_patch.decode_replacement_payload(
            rating_patch.encode_replacement_payload(99),
            "synthetic-rating",
        )
        == 99
        and callable(getattr(rating_patch, "build_patch", None))
        and callable(getattr(rating_patch, "write_private_outer_entry", None))
        and roster_composite.SCHEMA == "apf2k8_roster_composite_patch/v1"
        and callable(getattr(roster_composite, "compose_results", None))
        and callable(getattr(roster_composite, "compose_components", None))
        and callable(
            getattr(build.ApfBuildService, "_compile_roster_composite_groups", None)
        ),
        "strict 31-field APF player-rating writer contract changed",
    )
    synthetic_position_record = bytearray(position_schema.record_stride)
    synthetic_position_record[0x34] = synthetic_position_record[0x35] = 16
    position_target = position_patch.target_for(2_253)
    require(
        len(position_schema.positions) == 17
        and position_schema.player_count == 2_254
        and position_schema.record_stride == 0x14C
        and position_schema.semantic_relative_offset == 0x34
        and position_schema.mirror_relative_offset == 0x35
        and position_schema.positions[7].abbreviation == "HB"
        and position_schema.decode_record(synthetic_position_record).code == 16
        and position_schema.runtime_status
        == "offline_writer_proved_runtime_spot_check_pending"
        and position_patch.EXPECTED_PLAYER_COUNT == 2_254
        and (position_patch.MINIMUM_CODE, position_patch.MAXIMUM_CODE) == (0, 16)
        and position_target.asset_id == "apf:player-position:2253"
        and position_target.semantic_relative_offset == 0x34
        and position_target.mirror_relative_offset == 0x35
        and position_patch.decode_replacement_payload(
            position_patch.encode_replacement_payload(16),
            "synthetic-position",
        )
        == 16
        and callable(getattr(position_patch, "build_patch", None)),
        "strict paired APF player-position writer contract changed",
    )
    for refused_value in (-1, 17, True, 3.0, "3"):
        try:
            position_patch.validate_code(refused_value)
        except position_patch.PlayerPositionPatchError:
            continue
        raise RuntimeError(
            "APF player-position writer accepted a non-0..16 code: "
            f"{refused_value!r}"
        )
    synthetic_bank = appearance_patch.AppearanceBank(
        tuple(0xFF000000 + index for index in range(10)),
        bytes.fromhex("0703020009000000"),
        bytes.fromhex("5000000302010000"),
    )
    synthetic_appearance = appearance_patch.CustomTeamAppearance(
        32, synthetic_bank, synthetic_bank
    )
    eagles_appearance = appearance_patch.eagles_2017_preset(
        synthetic_appearance
    )
    require(
        appearance_patch.SCHEMA
        == "apf2k8_custom_team_appearance_patch/v1"
        and appearance_patch.USER_SLOTS == tuple(range(32, 40))
        and len(eagles_appearance.home.palette) == 10
        and eagles_appearance.home.palette[8] == 0xFF004C54
        and eagles_appearance.home.helmet_selector
        == bytes.fromhex("0708020009000000")
        and eagles_appearance.home.logo_selector
        == bytes.fromhex("1E00010009000000")
        and appearance_patch.decode_replacement_payload(
            appearance_patch.encode_replacement_payload(eagles_appearance),
            "synthetic-appearance",
        )
        == eagles_appearance
        and callable(getattr(appearance_patch, "build_patch", None))
        and callable(
            getattr(appearance_patch, "patch_private_staged_volume", None)
        )
        and callable(
            getattr(appearance_patch, "verify_output_appearances", None)
        )
        and callable(
            getattr(build.ApfBuildService, "_compile_custom_team_appearance_group", None)
        )
        and callable(
            getattr(facade.ApfStudioFacade, "replace_custom_team_appearance", None)
        ),
        "bounded APF custom-team appearance writer/editor contract changed",
    )
    require(
        save_appearance_patch.SCHEMA
        == "apf2k8_save_custom_team_appearance/v1"
        and save_appearance_patch.MANIFEST_SCHEMA
        == "apf2k8_save_custom_team_appearance_patch/v1"
        and save_appearance_patch.STFS_EXTRACT_SCHEMA
        == "apf2k8_stfs_roster_extract/v1"
        and save_appearance_patch.STFS_HANDOFF_SCHEMA
        == "apf2k8_stfs_roster_appearance_handoff/v1"
        and save_appearance_patch.STFS_MAGICS
        == (b"CON ", b"LIVE", b"PIRS")
        and stfs_roster_extract.STFS_MAGICS == (b"CON ", b"LIVE", b"PIRS")
        and save_appearance_patch.ROOT_OFFSET == 4
        and save_appearance_patch.USER_CATEGORY == 2
        and callable(getattr(save_appearance_patch, "parse_save", None))
        and callable(getattr(save_appearance_patch, "make_patch", None))
        and callable(getattr(save_appearance_patch, "verify_patch", None))
        and callable(getattr(save_appearance_patch, "make_stfs_extract", None))
        and callable(getattr(save_appearance_patch, "verify_stfs_extract", None))
        and callable(getattr(save_appearance_patch, "make_stfs_handoff", None))
        and callable(getattr(save_appearance_patch, "verify_stfs_handoff", None))
        and callable(getattr(save_appearance_patch, "write_stfs_extract", None))
        and callable(getattr(save_appearance_patch, "write_patch", None))
        and callable(getattr(stfs_roster_extract, "extract_roster_payload", None))
        and "24–31" in save_appearance.RAW_SAVE_BOUNDARY
        and "32–39" in save_appearance.RAW_SAVE_BOUNDARY
        and "STFS" in save_appearance.SIGNED_SAVE_BOUNDARY
        and "does not write the signed container"
        in save_appearance.SIGNED_SAVE_BOUNDARY
        and "unavailable private keys" in save_appearance.SIGNED_SAVE_BOUNDARY
        and callable(getattr(save_appearance, "inspect_save", None))
        and callable(getattr(save_appearance, "extract_raw_save", None))
        and callable(getattr(save_appearance, "write_new_save", None))
        and save_appearance.SaveAppearanceWriteReceipt.__dataclass_fields__[
            "runtime_in_game_proved"
        ].default
        is False,
        "raw/STFS custom-team appearance safety/runtime boundary changed",
    )
    for refused_slot in (31, 40, True):
        try:
            appearance_patch.asset_id(refused_slot)
        except appearance_patch.CustomTeamAppearanceError:
            continue
        raise RuntimeError(
            "APF custom-team appearance writer accepted unsafe slot "
            f"{refused_slot!r}"
        )
    for refused_value in (-1, 100, True, 99.0, "99"):
        try:
            rating_patch.validate_value(refused_value)
        except rating_patch.PlayerRatingPatchError:
            continue
        raise RuntimeError(
            f"APF player-rating writer accepted a non-0..99 value: {refused_value!r}"
        )
    require(
        callable(getattr(inspectors, "export_player_rating_sheet", None))
        and callable(
            getattr(facade.ApfStudioFacade, "export_player_rating_sheet", None)
        )
        and callable(
            getattr(facade.ApfStudioFacade, "preview_player_rating_sheet", None)
        )
        and callable(
            getattr(facade.ApfStudioFacade, "apply_player_rating_sheet", None)
        )
        and player_rating_sheet.PLAYER_RATING_SHEET_SCHEMA
        == "apf2k8_private_player_rating_sheet/v2"
        and len(player_rating_sheet.RATING_COLUMNS) == 31
        and callable(getattr(player_rating_sheet, "preview_player_rating_sheet", None))
        and callable(getattr(player_rating_sheet, "apply_player_rating_sheet", None))
        and "save players"
        in gui.CATEGORY_BLURBS[models.ApfCategory.ROSTERS].casefold()
        and "149 exact packed fields"
        in gui.CATEGORY_BLURBS[models.ApfCategory.ROSTERS],
        "complete private APF player-rating sheet import/export route is missing",
    )
    require(
        audio_batch_export.MANIFEST_SCHEMA
        == "apf2k8_mod_studio_audio_batch_export/v2"
        and audio_batch_export.MAX_BATCH_ROWS == 47_814
        and {
            "payload_bytes",
            "catalog_record_count",
            "playlist_record_count",
        }.issubset(audio_batch_export.AudioBatchReceipt.__dataclass_fields__)
        and callable(
            getattr(audio_batch_export.ApfAudioBatchExporter, "export_all", None)
        )
        and audio_batch_export.EXTERNAL_BANK_MANIFEST_SCHEMA
        == "apf2k8_mod_studio_external_audio_bank_bundle/v1"
        and audio_batch_export.MAX_EXTERNAL_AUDIO_BANKS == 19
        and callable(
            getattr(
                audio_batch_export.ApfExternalAudioBankBundleExporter,
                "export_all",
                None,
            )
        )
        and callable(
            getattr(
                facade.ApfStudioFacade,
                "export_external_audio_bank_bundle",
                None,
            )
        )
        and callable(
            getattr(
                facade.ApfStudioFacade,
                "export_all_external_audio_banks",
                None,
            )
        )
        and callable(
            getattr(gui.InspectorBrowser, "_export_all_original_audio_banks", None)
        )
        and callable(
            getattr(gui.InspectorBrowser, "_cancel_running_audio_export", None)
        ),
        "self-describing APF cue catalog or original-bank bundle route is missing",
    )
    pack_facade_signature = inspect.signature(
        facade.ApfStudioFacade.import_audio_replacement_pack
    ).parameters
    pack_preview_facade_signature = inspect.signature(
        facade.ApfStudioFacade.preview_audio_replacement_pack
    ).parameters
    pack_template_signature = inspect.signature(
        audio_replacement_pack.create_audio_replacement_template
    ).parameters
    pack_session_signature = inspect.signature(
        session.ApfSession.apply_audio_replacement_pack
    ).parameters
    pack_preview_session_signature = inspect.signature(
        session.ApfSession.preview_audio_replacement_pack
    ).parameters
    pack_session_source = inspect.getsource(session.ApfSession)
    pack_preview_gui_source = inspect.getsource(
        gui.InspectorBrowser._audio_replacement_pack_previewed
    )
    pack_worker_gui_source = inspect.getsource(
        gui.InspectorBrowser._run_cancellable_audio_import
    )
    pack_category_gui_source = inspect.getsource(gui.InspectorCategoryPage.__init__)
    pack_main_pages_source = inspect.getsource(gui.ApfStudioMainWindow._build_pages)
    pack_idle_gui_source = inspect.getsource(gui.ApfStudioMainWindow._run_when_idle)
    direct_drop_gui_source = inspect.getsource(gui.AudioReplacementDropZone)
    direct_mutation_gui_source = inspect.getsource(
        gui.InspectorBrowser._run_direct_audio_mutation
    )
    direct_idle_gui_source = inspect.getsource(
        gui.InspectorBrowser._direct_audio_replacement_worker_finished
    )
    pack_preview_fields = (
        audio_replacement_pack.AudioReplacementPreviewReceipt.__dataclass_fields__
    )
    require(
        audio_replacement_pack.MANIFEST_SCHEMA
        == "apf2k8_mod_studio_audio_replacement_pack/v1"
        and audio_replacement_pack.PCM_MANIFEST_SCHEMA
        == "apf2k8_mod_studio_audio_replacement_pack/v2"
        and audio_replacement_pack.BASELINE_SCHEMA
        == "apf2k8_mod_studio_audio_target_baseline/v1"
        and audio_replacement_pack.MAX_PACK_ENTRIES == 47_775
        and audio_replacement_pack.MAX_PCM_PACK_SUPPLIED == 256
        and audio_replacement_pack.PCM_PAYLOAD_DIRECTORY == "pcm16"
        and audio_replacement_pack.TEMPLATE_PAYLOADS_INCLUDED is False
        and dict(audio_replacement_pack.INPUT_CONTRACT)
        == {
            "container": "RIFF",
            "codec": "XMA1",
            "stream_count": 1,
            "filename_extension": ".xma",
            "wav_flac_input_supported": False,
        }
        and dict(audio_replacement_pack.PCM_INPUT_CONTRACT)
        == {
            "container": "RIFF",
            "codec": "PCM",
            "bits_per_sample": 16,
            "byte_order": "little_endian",
            "stream_count": 1,
            "filename_extension": ".wav",
            "shape": "exact_target",
            "encoder": "user_configured_external_xma1",
        }
        and {"validated_count", "was_cancelled", "input_kind"}.issubset(
            audio_replacement_pack.AudioReplacementApplyReceipt.__dataclass_fields__
        )
        and set(pack_preview_fields)
        == {
            "root",
            "template_entry_count",
            "supplied_count",
            "would_change_count",
            "already_current_count",
            "missing_count",
            "current_modified_audio_count",
            "resulting_modified_audio_count",
            "validated_count",
            "confirmation_token",
            "was_cancelled",
            "input_kind",
        }
        and pack_preview_fields["confirmation_token"].repr is False
        and {"stage", "completed", "total", "asset_id"}.issubset(
            audio_replacement_pack.AudioReplacementApplyProgress.__dataclass_fields__
        )
        and {"baseline_sha256", "input_kind"}.issubset(
            audio_replacement_pack.AudioReplacementPackPlan.__dataclass_fields__
        )
        and "baseline"
        in audio_replacement_pack.AudioReplacementEntry.__dataclass_fields__
        and {"root_identity", "payload_directory_identity"}.issubset(
            audio_replacement_pack.AudioReplacementPackPlan.__dataclass_fields__
        )
        and "file_identity"
        in audio_replacement_pack.SuppliedAudioReplacement.__dataclass_fields__
        and {"device", "inode", "modified_ns", "changed_ns", "link_count"}
        .issubset(
            audio_replacement_pack.AudioReplacementDirectoryIdentity.__dataclass_fields__
        )
        and {
            "device",
            "inode",
            "size",
            "modified_ns",
            "changed_ns",
            "content_sha256",
        }.issubset(
            audio_replacement_pack.AudioReplacementFileIdentity.__dataclass_fields__
        )
        and callable(
            getattr(
                audio_replacement_pack,
                "create_audio_replacement_template",
                None,
            )
        )
        and callable(
            getattr(audio_replacement_pack, "load_audio_replacement_pack", None)
        )
        and callable(
            getattr(audio_replacement_pack, "read_audio_replacement_payload", None)
        )
        and callable(
            getattr(
                audio_replacement_pack,
                "materialize_audio_replacement_pcm",
                None,
            )
        )
        and callable(
            getattr(
                audio_replacement_pack,
                "current_audio_target_baseline",
                None,
            )
        )
        and callable(
            getattr(facade.ApfStudioFacade, "export_audio_replacement_template", None)
        )
        and callable(
            getattr(facade.ApfStudioFacade, "import_audio_replacement_pack", None)
        )
        and callable(
            getattr(facade.ApfStudioFacade, "preview_audio_replacement_pack", None)
        )
        and callable(
            getattr(session.ApfSession, "apply_audio_replacement_pack", None)
        )
        and callable(
            getattr(session.ApfSession, "preview_audio_replacement_pack", None)
        )
        and {"progress", "cancel_requested", "encoder", "confirmation_token"}.issubset(
            pack_facade_signature
        )
        and {"progress", "cancel_requested", "encoder"}.issubset(
            pack_preview_facade_signature
        )
        and {"active_modifications", "input_kind"}.issubset(
            pack_template_signature
        )
        and {"progress", "cancel_requested", "encoder", "confirmation_token"}.issubset(
            pack_session_signature
        )
        and {"progress", "cancel_requested", "encoder"}.issubset(
            pack_preview_session_signature
        )
        and gui.AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT
        == "fully_validated_read_only_preview_then_explicit_apply"
        and gui.AUDIO_DIRECT_DROP_CONTRACT
        == "selected_exact_slot_xma1_or_conformed_audio"
        and all(
            marker in pack_session_source
            for marker in (
                "_audio_replacement_confirmation_token",
                "member_sha256",
                "validated_result_sha256",
                "project_audio_revision",
                "hmac.compare_digest",
                "would_change_count=0",
                "if not batch.changed_ids",
                "_discard_failed_audio_pack_payloads(batch.prepared)",
            )
        )
        and all(
            marker in pack_preview_gui_source
            for marker in (
                "Would change",
                "Already current",
                "Modified audio after Apply",
                "QMessageBox.Apply | QMessageBox.Cancel",
                "QMessageBox.Cancel",
                "if would_change == 0",
                "answer != QMessageBox.Apply",
                "confirmation_token=confirmation_token",
            )
        )
        and "self._run_when_idle" in pack_worker_gui_source
        and "run_when_idle=run_when_idle" in pack_category_gui_source
        and "run_when_idle=self._run_when_idle" in pack_main_pages_source
        and "self._idle_callbacks.append(callback)" in pack_idle_gui_source
        and "if self._workers" in pack_idle_gui_source
        and all(
            marker in direct_drop_gui_source
            for marker in (
                "len(urls) != 1",
                "bool(urls[0].host())",
                "path.is_file() and not path.is_symlink()",
                # The admission list widened from {".xma", ".wav"} to ".xma"
                # plus everything the converter can read. Both halves are
                # pinned, so the lossless passthrough route and the conform
                # route each stay gated on suffix rather than the drop target
                # quietly admitting any file at all.
                'path.suffix.casefold() == ".xma"',
                "audio_conform.is_supported_suffix(path)",
            )
        )
        and all(
            marker in direct_mutation_gui_source
            for marker in (
                "self._direct_audio_replacement_running = True",
                "self.directAudioReplacementWorkerFinished.emit()",
                "if admitted is False",
                "Nothing was staged",
            )
        )
        and "self._run_when_idle(self._direct_audio_replacement_idle)"
        in direct_idle_gui_source
        and callable(
            getattr(gui.InspectorBrowser, "_cancel_running_audio_import", None)
        ),
        "metadata-only APF audio replacement-pack product contract changed",
    )
    target_families = targets.load_targets()
    require(
        tuple(target_families) == targets.FAMILIES
        and sum(len(rows) for rows in target_families.values()) == 96,
        "retail-free APF uniform target catalog is incomplete",
    )
    require(gui.QApplication.instance() is None,
            "importing the APF GUI unexpectedly created an application")
    gameplay = findings.gameplay_snapshot()
    presentation = findings.presentation_snapshot()
    require(
        dict(gameplay.summary)
        == {"sliders": 21, "draft_lineage_weights": 17, "editable_controls": 0}
        and len(gameplay.model.rows) == 38,
        "sanitized APF gameplay findings changed",
    )
    require(
        dict(presentation.summary)
        == {"scorebug_scene_components": 7, "bounded_texture_writers": 1,
            "semantic_rows": 8}
        and len(presentation.model.rows) == 8,
        "sanitized APF presentation findings changed",
    )
    require(callable(entry.main) and entry.build_parser().prog == "apf2k8-mod-studio",
            "APF GUI entry point contract changed")
    require(
        callable(stadium.stadium_scenes)
        and callable(stadium.ApfStadiumService.prepare)
        and callable(stadium_viewer.GltfWireframeModel.load)
        and stadium_viewer.StadiumViewport.__name__ == "StadiumViewport",
        "APF Stadium Studio runtime closure is incomplete",
    )
    material_findings_path = stadium_material_findings.STADIUM_MATERIAL_FINDINGS
    material_findings_info = _require_regular(
        material_findings_path,
        "retail-free APF stadium material findings",
    )
    require(
        material_findings_path.resolve(strict=True).is_relative_to(ROOT),
        "APF stadium material findings escaped the packaged runtime",
    )
    require(
        material_findings_info.st_size == STADIUM_MATERIAL_FINDINGS_SIZE
        and _sha256(material_findings_path) == STADIUM_MATERIAL_FINDINGS_SHA256,
        "reviewed retail-free APF stadium material findings size/hash changed",
    )
    material_findings = stadium_material_findings.load_stadium_material_findings()
    require(
        material_findings.outcome == "embedded_texture_ownership_proved"
        and material_findings.experiment["scene_surface_nodes"] == 89
        and material_findings.experiment["serialized_material_records"] == 84
        and material_findings.experiment["shader_family_records"] == 20
        and material_findings.experiment["embedded_texture_descriptors"] == 78
        and material_findings.experiment["editable_texture_descriptors"] == 78
        and material_findings.experiment["orphaned_embedded_textures"] == 0
        and material_findings.proof["material_slot_to_embedded_texture"] is True
        and material_findings.proof["texture_writer_safe_to_expose"] is True
        and material_findings.proof["runtime_visibility_proved"] is False
        and material_findings.runtime_capture["outcome"] == "offline_writer_proved"
        and material_findings.runtime_capture["emulator_used"] is False
        and material_findings.runtime_capture["source_opened_read_only"] is True
        and material_findings.runtime_capture["copied_output_reopened"] is True
        and "Replace, Revert" in material_findings.author_summary
        and "Xbox 360 hardware" in material_findings.best_next_experiment,
        "APF stadium material findings runtime boundary changed",
    )
    scene_tool = importlib.import_module("apf_scene")
    require(
        callable(scene_tool.parse_scene_system_part)
        and callable(scene_tool.write_gltf_collection),
        "APF stadium scene decoder/exporter is absent from the runtime closure",
    )
    audo = inspectors.ExportIdentity(
        kind="audo",
        outer_table_index=12,
        inner_file_index=3,
        substream_index=None,
        suggested_basename="synthetic-audo",
    )
    ausb = inspectors.ExportIdentity(
        kind="ausb_substream",
        outer_table_index=44,
        inner_file_index=5,
        substream_index=6,
        suggested_basename="synthetic-ausb",
    )
    require(
        audo.exporter == "apf_audio.export_selected"
        and audo.coordinates == (12, 3, None)
        and ausb.exporter == "apf_ausb_audio.export_substream"
        and ausb.coordinates == (44, 5, 6),
        "AUDO/AUSB ExportIdentity routing changed",
    )
    ausb_module = importlib.import_module("apf_ausb_audio")
    require(callable(ausb_module.export_substream),
            "AUSB substream exporter is absent from the runtime closure")
    unbound_io = object.__new__(asset_io.ApfAssetIO)
    try:
        unbound_io.export_audio_identity(ausb, Path("synthetic.invalid"))
    except asset_io.AssetIoError as exc:
        require("ending in .xma or .wav" in str(exc),
                "AUSB modder-facing extension error changed")
    else:
        raise RuntimeError("AUSB export accepted an unsupported extension")
    _exercise_retail_free_project(modules)
    _exercise_texture_master(modules)
    _exercise_retail_free_audio_project(modules)
    _exercise_external_xma1_bridge(modules)
    return len(cards)


def _check_private_source(
    supplied: Path,
    modules: dict[str, object],
) -> tuple[int, int, int, int]:
    supplied = supplied.expanduser().resolve(strict=True)
    require(not supplied.is_relative_to(ROOT),
            "--source must point outside the staged public release")
    source_module = modules["mod_editor.apf_studio.source"]
    catalog_module = modules["mod_editor.apf_studio.catalog"]
    models = modules["mod_editor.apf_studio.models"]
    with tempfile.TemporaryDirectory(prefix="apf-runtime-private-") as temporary_name:
        cache = Path(temporary_name) / "cache"
        manager = source_module.SourceManager(cache_root=cache, extract_xiso=EXTRACTOR)
        resolved = manager.resolve(supplied)
        product_catalog = catalog_module.CatalogBuilder(cache_root=cache).build(
            resolved, force=True
        )
        universal_count = len(product_catalog.assets)
        uniform_count = len(product_catalog.uniform_assets)
        uniform_inventory = product_catalog.browse(
            category=models.ApfCategory.UNIFORMS,
            limit=universal_count + 1,
        )
        uniform_inventory_count = len(uniform_inventory)
        capability_count = len(product_catalog.capabilities)
        require(
            (product_catalog.outer_count, product_catalog.iff_count,
             product_catalog.non_iff_count, product_catalog.inner_count)
            == (1_543, 1_473, 70, 10_394),
            "private APF outer/inner coverage changed",
        )
        require(universal_count == 10_464,
                f"expected 10,464 universal assets, found {universal_count}")
        require(uniform_count == 302,
                f"expected 302 editable uniform/wordmark assets, found {uniform_count}")
        require(uniform_inventory_count == 408,
                f"expected 408 uniform inventory records, found {uniform_inventory_count}")
        require(capability_count == 37,
                f"expected 37 capabilities, found {capability_count}")
        require(
            len({item.asset_id for item in product_catalog.assets}) == universal_count
            and len({item.asset_id for item in product_catalog.uniform_assets}) == uniform_count,
            "private APF catalog contains duplicate asset IDs",
        )
        by_family: dict[str, int] = {}
        for item in product_catalog.uniform_assets:
            by_family[item.family] = by_family.get(item.family, 0) + 1
        require(
            by_family
            == {
                "helmet": 24,
                "jersey": 24,
                "pants": 24,
                "shoulder": 24,
                "textlogo": 206,
            },
                f"uniform family coverage changed: {by_family}")
        inventory_by_type: dict[str, int] = {}
        inventory_by_coordinate: dict[tuple[int, int], object] = {}
        for item in uniform_inventory:
            require(item.inner_index is not None,
                    f"uniform inventory unexpectedly contains outer-only record {item.asset_id}")
            inventory_by_type[item.type_name] = inventory_by_type.get(item.type_name, 0) + 1
            coordinate = (item.outer_index, item.inner_index)
            require(coordinate not in inventory_by_coordinate,
                    f"uniform inventory repeats archive coordinate {coordinate}")
            inventory_by_coordinate[coordinate] = item
        require(
            inventory_by_type
            == {"NameFont": 11, "NumberFont": 24, "SCNE": 2, "TXTR": 371},
            f"uniform inventory type coverage changed: {inventory_by_type}",
        )
        editable_coordinates = {
            (item.outer_index, item.inner_index): item
            for item in product_catalog.uniform_assets
        }
        require(len(editable_coordinates) == 302,
                "editable uniform targets repeat an archive coordinate")
        require(set(editable_coordinates).issubset(inventory_by_coordinate),
                "editable uniform targets are missing from the 408-record inventory")
        expected_inner_names = {
            "jersey": "jersey_color",
            "pants": "pants_color",
            "helmet": "helmet_color",
            "shoulder": "shoulder_color",
            "textlogo": "textlogo_color",
        }
        require(
            all(
                inventory_by_coordinate[coordinate].name
                == expected_inner_names[item.family]
                and inventory_by_coordinate[coordinate].type_name == "TXTR"
                for coordinate, item in editable_coordinates.items()
            ),
            "editable uniform targets no longer map to their named TXTR records",
        )
        additional_inventory = tuple(
            item
            for coordinate, item in inventory_by_coordinate.items()
            if coordinate not in editable_coordinates
        )
        additional_by_type: dict[str, int] = {}
        for item in additional_inventory:
            additional_by_type[item.type_name] = additional_by_type.get(item.type_name, 0) + 1
        require(
            len(additional_inventory) == 106
            and additional_by_type
            == {"NameFont": 11, "NumberFont": 24, "SCNE": 2, "TXTR": 69},
            f"additional uniform inventory coverage changed: count={len(additional_inventory)} types={additional_by_type}",
        )
        external_audio_banks = tuple(
            item
            for item in product_catalog.assets
            if item.type_name == "XMA1_BANK"
        )
        require(
            len(external_audio_banks) == 19
            and len({item.outer_index for item in external_audio_banks}) == 19
            and all(
                item.inner_index is None
                and item.category is models.ApfCategory.AUDIO
                and item.status is models.ApfStatus.EXPORT_ONLY
                and item.name.casefold().endswith(".bin")
                and item.decoded_size == item.outer_size > 0
                and item.metadata.get("external_filename") == item.name
                for item in external_audio_banks
            ),
            "physical APF external audio-bank catalog coverage changed",
        )
        require(
            sum(
                int(item.metadata.get("descriptor_owner_count", 0))
                for item in external_audio_banks
            )
            == 20,
            "20 AUSB descriptors no longer own the 19 external audio banks",
        )
        require(product_catalog.audio_selection_manifest.is_relative_to(cache),
                "private selection manifest escaped the private cache")
        roster_identity = importlib.import_module("apf_roster_identity_patch")
        roster_names = roster_identity.inventory(resolved.index_0a)
        team_display_names = tuple(
            item
            for item in roster_names
            if item.editable
            and item.known_owners
            and all(
                owner.entity_kind == "team" and owner.field == "display_name"
                for owner in item.known_owners
            )
        )
        mapped_player_names = tuple(
            item
            for item in roster_names
            if any(
                owner.entity_kind == "player"
                and owner.field in roster_identity.PLAYER_IDENTITY_FIELDS
                for owner in item.known_owners
            )
        )
        product_player_names = tuple(
            item
            for item in mapped_player_names
            if item.editable
            and bool(item.text)
            and item.known_owners
            and all(
                owner.entity_kind == "player"
                and owner.field in roster_identity.PLAYER_IDENTITY_FIELDS
                for owner in item.known_owners
            )
        )
        mapped_team_abbreviations = tuple(
            item
            for item in roster_names
            if any(
                owner.entity_kind == "team"
                and owner.field in {"abbreviation", "secondary_abbreviation"}
                for owner in item.known_owners
            )
        )
        require(
            len(roster_names) == 3_273
            and sum(item.editable for item in roster_names) == 3_272
            and sum(item.known_owner_count for item in roster_names) == 4_628
            and len(team_display_names) == 40
            and len(mapped_player_names) == 3_192
            and len(product_player_names) == 3_191
            and sum(item.known_owner_count for item in product_player_names)
            == 4_482
            and sum(item.known_owner_count > 1 for item in product_player_names)
            == 429
            and max(item.known_owner_count for item in product_player_names) == 23
            and len(mapped_team_abbreviations) == 41
            and roster_identity.JERSEY_NUMBER_FINDING.get("status")
            == "read_only_unmapped",
            "bounded APF roster editable/locked field boundary changed",
        )
        require(_sha256(resolved.index_0a) == source_module.EXPECTED_0A_SHA256,
                "private source changed during the runtime check")
    return capability_count, universal_count, uniform_count, uniform_inventory_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        help=(
            "optional private APF USA ISO, extracted game folder, or 0A; "
            "never required for the default public-release closure check"
        ),
    )
    args = parser.parse_args(argv)
    try:
        _check_clean_stage()
        _check_extractor()
        _check_h7a_encoder()
        _check_desktop_contract()
        _check_install_contract()
        modules = {name: importlib.import_module(name) for name in PRODUCT_MODULES}
        for name in TOOL_MODULES:
            importlib.import_module(name)
        _check_namespace_isolation()
        _check_audo_authoring_doc()
        _check_ausb_feasibility_doc()
        _check_external_xma1_bridge_doc()
        capabilities = _check_static_product_contract(modules)
        if args.source is None:
            print(
                "APF2K8_MOD_STUDIO_RUNTIME_PASS "
                f"modules={len(PRODUCT_MODULES) + len(TOOL_MODULES)} "
                f"capabilities={capabilities} universal=private_source_not_provided "
                "uniforms=private_source_not_provided "
                "uniform_inventory=private_source_not_provided "
                "audio_query_lifecycle=applied_token_debounce_guarded "
                "audio_shortlist_clear=one_level_ordered_restore "
                "audio_preview_lifecycle=request_owned_success_failure "
                "audio_preview_cancellation=request_owned_process_group_cancel "
                "audio_waveform_cancellation=request_owned_process_group_cancel "
                "audio_add_all_matching=applied_query_atomic_256 "
                "audio_session_teardown=cancel_drain_before_close_source "
                "audio_replacement_confirmation=fully_validated_read_only_preview_then_explicit_apply "
                "audio_replacement_token=exact_member_result_source_session_project_revision "
                "audio_replacement_noop=cancel_unchanged "
                "audio_replacement_lifecycle=worker_drained_before_confirmation "
                "audio_direct_drop=selected_exact_slot_xma1_or_conformed_audio "
                "audio_mutation_lifecycle=submission_to_worker_idle "
                "retail_source_required=false"
            )
        else:
            capabilities, universal, uniforms, uniform_inventory = _check_private_source(
                args.source, modules
            )
            print(
                "APF2K8_MOD_STUDIO_RUNTIME_PASS "
                f"modules={len(PRODUCT_MODULES) + len(TOOL_MODULES)} "
                f"capabilities={capabilities} universal={universal} uniforms={uniforms} "
                f"uniform_inventory={uniform_inventory} "
                "audio_query_lifecycle=applied_token_debounce_guarded "
                "audio_shortlist_clear=one_level_ordered_restore "
                "audio_preview_lifecycle=request_owned_success_failure "
                "audio_preview_cancellation=request_owned_process_group_cancel "
                "audio_waveform_cancellation=request_owned_process_group_cancel "
                "audio_add_all_matching=applied_query_atomic_256 "
                "audio_session_teardown=cancel_drain_before_close_source "
                "audio_replacement_confirmation=fully_validated_read_only_preview_then_explicit_apply "
                "audio_replacement_token=exact_member_result_source_session_project_revision "
                "audio_replacement_noop=cancel_unchanged "
                "audio_replacement_lifecycle=worker_drained_before_confirmation "
                "audio_direct_drop=selected_exact_slot_xma1_or_conformed_audio "
                "audio_mutation_lifecycle=submission_to_worker_idle "
                "private_source_verified=true"
            )
    except (ImportError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"APF2K8_MOD_STUDIO_RUNTIME_REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
