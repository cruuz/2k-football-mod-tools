# APF-1 integration wiring

No protected file in this worktree was edited. Apply the following changes before packaging. The gates were run on a temporary stage with these exact changes.

## Registry counts

Added capability rows: **0**. Extend `apf2k8.playbooks.scheme_presets`; its existing Book Identity route remains the integration point. Shared registry count stays **172**, APF count stays **72**. Both 2K5 count assertions, `test_phase1_packaging.py`, APF runtime counts/cards and `test_apf_studio_installer.py` stay unchanged.

Replace the existing registry row with:

```json
{
  "backend": {
    "command": "python3 tools/apf_book_unlock.py preset --source <0A> --preset <wide-zone|spread-to-run|pro-power> --output <new-game>",
    "module": "tools/apf_book_unlock.py",
    "operation": "write"
  },
  "classification": "offline-writer-proved",
  "evidence": [
    "docs/mod_editor/apf_wave_2026_09_09.md",
    "docs/mod_editor/apf_b661_cpu_book_control.md",
    "docs/mod_editor/apf2k8_book_identity_walkthrough.md"
  ],
  "game": "apf2k8_xbox360",
  "gui": {
    "default_enabled": true,
    "expose": true,
    "mode": "edit",
    "reason": "Book Identity links the walkthrough and exposes replacement unchecked by default, per book. Offline writer/reparse proved; gameplay UNWITNESSED."
  },
  "id": "apf2k8.playbooks.scheme_presets",
  "input_constraints": [
    "Use a separate new destination; source game files remain read-only.",
    "Reject malformed ownership, hash collisions, shared clone labels, occupied directory slack, IFF overflow, and H7A length greater than distance.",
    "Only existing plays/formations are used; no CPU situational frequency, WR depth flip, true RPO, or TU compatibility is established.",
    "Stock replacement must fit the existing allocation, cover ordinary personnel rows and have no conflicting Fine-tune selectors. All users of the shared target receive the change."
  ],
  "portme": [
    "Witness base-XEX loading and per-team cloned-book consumption; reconstruct TU resolver before claiming TU compatibility."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "rule": "Distribute JSON selectors and tooling; each user builds from their own game. Never bundle copied game outputs.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": [],
    "scope": "Gameplay UNWITNESSED. BASE bounded personnel picker/record lookup is proved for the documented Queens retirement; expanded archive loading and TU compatibility remain unproved.",
    "status": "not-tested"
  },
  "selectors": {
    "fields": [
      {
        "allowed": "wide-zone, spread-to-run, pro-power",
        "name": "preset",
        "required": true
      }
    ],
    "notes": "Existing copy recipes retain their CLI. Book Identity also calls scheme_service.stage_replacement with a stock book name and one of eight beta-69 scheme IDs; it replaces the entire donor content and retains donor special-call tails. Existing target membership is not merged."
  },
  "source_container": {
    "format": "APF AA00B3BF four-volume archive, IFF/H7A, SPLB and ROST",
    "hash_pins": [
      "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
    ],
    "resource": "filename-addressed book resources and root[11] labels; root[4] team pointers",
    "retail_file": "user-owned extracted APF Xbox 360 game folder"
  },
  "summary": "Book Identity offers three copy recipes and opt-in replacement of any of eight stock offensive books with beta-69 scheme starting content. Whole-content reparse and fixed-allocation refusal precede staging; gameplay UNWITNESSED.",
  "surface": "scripts_config",
  "title": "Starting recipes and stock book replacement",
  "validation_command": "python3 packaging/check_apf2k8_mod_studio_runtime.py"
}
```

## APF allowlist

Append these four exact paths to `packaging/apf2k8-release-allowlist.txt`:

```text
docs/mod_editor/apf2k8_book_identity_walkthrough.md
docs/mod_editor/apf2k8_book_identity/book-identity.png
docs/mod_editor/apf2k8_book_identity/stock-replacement.png
docs/mod_editor/apf2k8_book_identity/walkthrough.png
```

## Release gate

In `packaging/check_apf2k8_mod_studio_release.py`, insert this dictionary immediately before `REVIEWED_PATHS`; add `*REVIEWED_EDITOR_IMAGES,` to that set. These three images are offscreen editor UI only, visually inspected; the local source path is replaced by a generic label. No game pixels are included. Other PNG paths remain forbidden.

```python
REVIEWED_EDITOR_IMAGES = {'docs/mod_editor/apf2k8_book_identity/book-identity.png': (171333, '49031072810725b3835b2bdf76ae9380add77917f733fc5f5341acb9c3cf31b8'), 'docs/mod_editor/apf2k8_book_identity/stock-replacement.png': (211991, 'df3ba6f510754917d0aa376596daaca5f29888960eb25054ec2a32085f462b98'), 'docs/mod_editor/apf2k8_book_identity/walkthrough.png': (113176, '9062606c54d9198c9bc77dc4e7730a1fb0f66952a9d918fc38e3eef3c3e2a3d5')}
```

Insert this function immediately before `audit_release`:

```python
def _validate_editor_image(path, info, relative):
    expected_size, expected_sha = REVIEWED_EDITOR_IMAGES[relative]
    if info.st_size != expected_size:
        raise ReleaseCheckError(f"reviewed editor image size changed: {relative}")
    digest, payload = _hash_regular(path, info.st_size, expected_size)
    if digest != expected_sha or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ReleaseCheckError(f"reviewed editor image bytes changed: {relative}")
    return digest


```

In `audit_release`, immediately before the `elif relative == REVIEWED_ICON:` arm, insert:

```python
        elif relative in REVIEWED_EDITOR_IMAGES:
            digest = _validate_editor_image(path, info, relative)
```

## Runtime gate

In `packaging/check_apf2k8_mod_studio_runtime.py`, insert the same `REVIEWED_EDITOR_IMAGES` dictionary and the following function immediately before `_check_book_unlock_contract`. Call `_check_book_identity_guide(modules)` immediately after `_check_book_unlock_contract(modules)` in `main`.

```python
def _check_book_identity_guide(modules):
    guide = ROOT / "docs/mod_editor/apf2k8_book_identity_walkthrough.md"
    require(guide.is_file(), "Book Identity walkthrough is absent")
    for relative, (size, digest) in REVIEWED_EDITOR_IMAGES.items():
        path = ROOT / relative
        info = _require_regular(path, "reviewed editor image")
        require(info.st_size == size and _sha256(path) == digest,
                f"reviewed Book Identity image changed: {relative}")
    service = modules["mod_editor.apf_studio.scheme_service"]
    require(len(service.STOCK_TARGETS) == 8 and len(service.SCHEME_CONTENT) == 8,
            "stock replacement book/scheme choices changed")
    require(service.replacement_recipe("USER-o", "wide_zone") == {
        "schema": service.REPLACEMENT_SCHEMA, "book_type": "USER-o", "scheme_id": "wide_zone"},
        "stock replacement authoring contract changed")


```

The native helper has not changed: size 18,568 bytes, mode 0755, SHA-256 `d081d19c0078f768d2cb935732c910945c55d372dd9e1cc2b3e16ef9cfcf86a0`. No helper pin updates. No new runtime modules, installer dependencies or per-platform binary changes.
