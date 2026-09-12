## Beta 66.1 H3b: game-folder pass-fetch export (supersedes the flat-input handoff)

The panel already renders in `gui.py` on the H3 base (88a3b353). **No gui.py
edit is needed.** The owned panel reads `facade.launcher.settings` and
`facade.last_build.output_game` directly. Its two background operations first
derive/check the image, then publish the authored patch after the save dialog.
The default input is Choose game folder; Choose flat image is an expert option.

The earlier paragraph saying no LZX/decryption belongs in the product is
superseded: `mod_editor/core/xex_codec.py` and `mod_editor/core/apf2k8_xex.py`
are standard-library Python product modules. They use no Java, subprocess,
ctypes, native codec, cryptography package or research harness. The existing
shipped `tools/apf_stfs_roster_extract.py` supplies the STFS verifier. The
retail LIVE parent-status exception is confined to the pinned TU package.
The APF release allowlist has been updated with both new modules. The combined
2K5 release allowlist does not ship this APF panel and needs no addition.

### Protected runtime gate: complete additions

In `packaging/check_apf2k8_mod_studio_runtime.py::PRODUCT_MODULES`, immediately
after `'mod_editor.core.apf2k8_playcall_patch'`, insert:

```python
    'mod_editor.core.apf2k8_xex',
    'mod_editor.core.xex_codec',
```

Add this complete function immediately before `_check_apf_wave_contract`:

```python
def _check_xex_image_contract(modules: dict[str, object]) -> None:
    import hashlib
    import struct
    from mod_editor.core.errors import ValidationError

    codec = modules["mod_editor.core.xex_codec"]
    xex = modules["mod_editor.core.apf2k8_xex"]
    patch = modules["mod_editor.core.apf2k8_playcall_patch"]
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    ciphertext = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    if codec.aes_cbc_decrypt(key, ciphertext) != bytes.fromhex("00112233445566778899aabbccddeeff"):
        raise RuntimeError("Python XEX AES decoder failed its standard vector")
    # Entirely synthetic uncompressed XEX, never game bytes.
    header = bytearray(0x400)
    struct.pack_into(">6I", header, 0, 0x58455832, 1, len(header), 0, 0x80, 1)
    struct.pack_into(">II", header, 24, 0x3FF, 0x300)
    struct.pack_into(">I", header, 0x84, 2)
    struct.pack_into(">IHH", header, 0x300, 8, 0, 0)
    image, receipt = xex.decode_xex(bytes(header) + b"MZ")
    if image != b"MZ" or receipt["image_sha256"] != hashlib.sha256(image).hexdigest():
        raise RuntimeError("Python XEX image derivation failed")
    try:
        patch.check_image(image)
    except ValidationError as exc:
        if not all(value in str(exc) for value in (
            hashlib.sha256(image).hexdigest(), *(p.sha256 for p in patch.PROFILES)
        )):
            raise RuntimeError("Pass-fetch refusal omits an image hash") from exc
    else:
        raise RuntimeError("Pass-fetch export accepted an unpinned image")
```

In `main`, immediately after its existing `_check_apf_wave_contract(modules)`
call, insert this complete block:

```python
        _check_xex_image_contract(modules)
```

Retain every existing release/runtime gate. No dependency wheel changes are
needed. Existing Capstone 5.0.7 is still required for the authored patch
instruction verifier, independently of the new Python image decoder.

### Protected registry: complete replacement object

Replace only the object with id `apf2k8.playbooks.pass_fetch_te_bias` in
`mod_editor/capabilities/registry.v1.json` with the following object (also
available in `docs/mod_editor/apf_playcall_capabilities.json`). This keeps the
existing registered capability and status while correcting its input contract.

```json
{
  "backend": {
    "command": "python3 -m mod_editor.core.apf2k8_playcall_patch --game-folder <game-folder> --output <new.patch.toml> [--title-update <installed-content>]",
    "module": "mod_editor/core/apf2k8_playcall_patch.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": [
    "ASTRA_REPORT.md",
    "docs/research/apf_playcall_receipt.json",
    "tests/mod_editor/test_apf_playcall_patch.py",
    "tools/apf_playcall_audit.py",
    "tests/mod_editor/test_apf_xex_image.py",
    "tests/mod_editor/test_apf_xex_image_retail.py",
    "tests/mod_editor/test_apf_pass_fetch_export_qt.py"
  ],
  "game": "apf2k8_xbox360",
  "gui": {
    "default_enabled": true,
    "expose": true,
    "mode": "edit",
    "reason": "CPU Audibles & Personnel workspace: Export TE bias for pass fetches. The export is a verified one-shot authored TOML file; removing or disabling that file reverses deployment."
  },
  "id": "apf2k8.playbooks.pass_fetch_te_bias",
  "input_constraints": [
    "Choose the Xbox 360 game folder with default.xex and optional installed Title Update 1.1; expert flat images are also accepted. Python derives the image in memory. Full SHA, fetch hash, original hook and entire zero cave reservation are checked.",
    "Pass subtypes 2/3/4 on any down, including user calls. Main CPU weighted picker and untyped emergency fetch use different paths.",
    "Reserve 0x84D0E000..0x84D0EFFF exclusively; Capstone is required. Shared plays, later formation resolution and Subs can still produce a lineup without a TE."
  ],
  "portme": [
    "Obtain an in-game witness before changing the unwitnessed runtime status."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Ship authored code and logical selectors only. Retail books, executable images and reconstructed title updates remain private.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": [],
    "scope": "Unwitnessed. Capstone redecodes all 179 cave instructions and checks all 34 branches; synthetic execution and BASE/TU image identities pass. Live down/distance is not proved, so this is unconditional for offensive pass fetches, not a third-and-long or forced-lineup claim.",
    "status": "not-tested"
  },
  "selectors": {
    "fields": [
      {
        "allowed": "Xbox 360 game folder / default.xex, or expert pinned BASE or TU 1.1 flat image",
        "name": "image",
        "required": true
      },
      {
        "allowed": "Separate authored .patch.toml file",
        "name": "output",
        "required": true
      }
    ],
    "notes": "Optional --title-update selects installed TU 1.1 content. Nearby Xenia content is detected. Module hash selects the Xenia image; no game or executable is modified by export."
  },
  "source_container": {
    "format": "Xbox 360 XEX2 plus optional LIVE STFS Title Update / XEXP delta, or expert flat PE; authored Xenia patch TOML output",
    "hash_pins": [
      "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf",
      "65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457"
    ],
    "resource": "BASE fetch 0x84869B20 or TU fetch 0x8486A820 and cave 0x84D0E000",
    "retail_file": "User-owned Xbox 360 game folder / default.xex and optional installed Title Update 1.1 content"
  },
  "summary": "Export an assembled, SHA-pinned BASE or TU 1.1 Xenia patch that prefers TE-compatible records for offensive pass fetches at every down, with zero-match fallback.",
  "surface": "scripts_config",
  "title": "TE bias for pass fetches (unwitnessed)",
  "validation_command": "python3 -m tests.mod_editor.test_apf_playcall_patch"
}
```

### Integration acceptance

The owned panel, actual retail decoder/TU reconstruction, authored patch
reparse, and synthetic refusal tests pass independently. After the protected
runtime/registry changes, run the unchanged staged APF release and runtime
gates and the offscreen export suite. No full packaged Windows or game witness
is claimed here. See `ASTRA_REPORT.md` for exact commands and Urianus's steps.
