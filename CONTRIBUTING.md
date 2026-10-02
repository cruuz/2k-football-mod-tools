# Contributing

Contributions are welcome — PS2 support arrived this way. Before you write code,
please read the one section that makes this project different from most:

---

## The rule that matters most: never claim more than you can prove

This tool is pointed at irreplaceable files people care about. Its entire value
is that it **does not overstate what it can do**. A missing feature is a
disappointment; a feature that claims to work and quietly corrupts a save is a
betrayal. So:

**Every capability is filed on a ladder, and it may only sit on the rung it has
earned:**

| Rung | Means |
| --- | --- |
| `unknown` | Not investigated. |
| `read-only-mapped` | The container is parsed. The *meaning* of the bytes may still be opaque. |
| `extract-only` | Data can be pulled out, not written back. |
| `offline-writer-proved` | A writer exists and an **independent verifier** confirms byte-for-byte that only the declared ranges changed. In-game behaviour is **not** claimed. |
| `runtime-proved` | The change was observed working in an emulator or on hardware, with evidence recorded. |

Two things follow that reviewers will check every time:

1. **Do not file a capability one rung above its evidence.** If you have not
   watched it work in-game, it is `offline-writer-proved`, and `runtime.status`
   says so plainly. Writing "not tested" is not a weakness in a PR — it is the
   thing being asked for.
2. **A writer ships with an independent verifier.** "Independent" means it
   re-derives the container itself rather than importing the writer's parser. A
   verifier that shares the writer's code agrees with the writer's bugs.

Other hard rules:

- **Never write to the user's original.** Read the source, write a copy. Always.
- **Fail closed.** If a check cannot be performed on some platform, refuse, or
  degrade to the strongest thing you *can* enforce and report that honestly —
  never a field that claims more than the platform delivers.
- **No game data, ever.** No ISO, extracted file, texture, decoded pixel, audio
  sample or rollback byte enters this repository or a release archive. Hashes and
  offsets are fine; payloads are not. An automated retail-free gate enforces
  this and will fail your build.

---

## Getting set up

```bash
git clone https://github.com/cruuz/2k-football-mod-tools
cd 2k-football-mod-tools
python3 -m pip install PyQt5 Pillow      # Python 3.11+
```

Run the suite the way CI does — each file as a script, with the repo root on
`PYTHONPATH`:

```bash
export QT_QPA_PLATFORM=offscreen
for f in tests/mod_editor/test_*.py; do PYTHONPATH="$PWD" python3 "$f" || echo "FAIL $f"; done
```

**A clean checkout lacks developer evidence.** CI names and skips 12 test files
that need large, unshipped inventories or models. Use the current runner in
`.github/workflows/ci.yml` for the skip list and per-file timeouts. Running the
simple loop above does not apply those skips. Product test failures still need
investigation.

---

## Things that will surprise you

- **Open your PR against `cruuz/2k-football-mod-tools`, not against your own
  fork.** A PR whose base is your fork's `main` only merges into your copy and
  never reaches this repository. GitHub offers the right base in a banner on
  your branch page.
- **CI runs on pushes to `main` and on pull requests.** A push to a feature
  branch with no open PR silently runs nothing.
- **SHA-256 self-integrity pins.** Several modules hash their own bytes and their
  declared import closure. Editing a pinned module — or anything it imports —
  makes `test_providers`, `test_provider_integrity` or `test_apf_digital_font`
  fail with `hash changed`. That is not a bug and the fix is never to loosen the
  test:
  ```bash
  python3 packaging/repin.py            # show what would change
  python3 packaging/repin.py --apply    # rewrite the pins
  ```
- **Some files in `tools/vendor/` and `reports/` are gitignored build inputs.**
  Restore the allowlisted files with `packaging/hydrate_release_inputs.py`, as
  described below. Large developer evidence stays unshipped; tests that require
  it must name the omission and its reason.
- **Registry evidence paths** under `docs/research/` and `reports/` are absent
  from a clean clone by design, so registry loads in tests and at runtime use
  `check_files=False`.

---

## Submitting

1. Keep the change focused, and keep Linux green.
2. Run the suite. If your change touches packaging, run the release gates too:
   ```bash
   python3 packaging/stage_release.py packaging/release-allowlist.txt /tmp/stage-2k5
   python3 packaging/check_2k5_mod_studio_release.py /tmp/stage-2k5
   ```
3. Re-sync pins if you touched a pinned module.
4. In the PR, say **what you proved and how**, and what you did *not* prove. That
   sentence is the most useful part of the description.

Commit messages here are prose: what changed, and why it was wrong before.

---

## Making your own fork

The code is MIT licensed. Keep [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md)
with your copies; NOTICE lists the third-party components and data licences.
Game data never belongs in this repository or the editor release files.
League, ESPN and sponsor logos stay outside this repository too. Those travel
only in the [SOFTDRINK 2K28 pack](https://github.com/cruuz/softdrink-2k28).

Before shipping your fork, change all four repository references in
`mod_editor/core/update_check.py`: `RELEASES_API`, `RELEASES_PAGE`, the
`html_url` prefix check inside `check()`, and `_ASSET_HOST`. Replace
`cruuz/2k-football-mod-tools` with your `OWNER/REPOSITORY` in each. This makes
your builds offer your releases. Update the corresponding updater tests.

Set the product versions in `mod_editor/__init__.py` and
`mod_editor/apf_studio/__init__.py`, and set `BUILD_RELEASE_TAG` in
`mod_editor/core/update_check.py`. Use tags `beta-N` or `beta-N.M`, increasing
the numbers for each release. Search before changing versions:

```bash
git grep -n -e '1.0.0rc107' -e 'RC107' -e '0.1.0-alpha.103' -e 'beta-76.2'
```

Use your checkout's current strings and update every hit in docs, packaging
checks and tests. Re-run `packaging/repin.py` if a changed module is pinned.

Build from the checkout root on Linux with Python 3.11+, pip, curl and NSIS
(`makensis`) installed. Install the Studio dependencies from
`packaging/requirements-studio.txt` into your Python environment. Start by
restoring the missing build inputs:

```bash
python3 packaging/hydrate_release_inputs.py
```

This recipe was verified on a clean clone of public beta-76.1. Without
`--tag`, the script uses the checkout's `BUILD_RELEASE_TAG`, which must already
be published; pass `--tag` to take the inputs from another release. The default source is `cruuz/2k-football-mod-tools`; use
`--repo OWNER/REPOSITORY` once your fork publishes its own portable archives.
For offline use, pass `--archive PATH` twice, once per product, with each
archive's `.sha256` beside it. Both paths verify checksums and restore only
missing files from the two allowlists. Existing files are preserved. A refusal
means the inputs are incomplete or unsafe; do not bypass the release gates.

Use a fresh output directory for each build. These commands read the versions
from the checkout and use its commit time for the archive date and epoch:

```bash
OUT=$(mktemp -d)
V2K5=$(awk -F '"' '/^__version__ = / {print $2}' mod_editor/__init__.py)
VAPF=$(awk -F '"' '/^__version__ = / {print $2}' mod_editor/apf_studio/__init__.py)
EPOCH=$(git show -s --format=%ct HEAD)
STAMP=$(date -u -d "@$EPOCH" +%Y%m%d)
T2K5="2K5-Mod-Studio-v1.0-RC${V2K5##*rc}-$STAMP"
TAPF="apf2k8-mod-studio-$VAPF-$STAMP"

python3 packaging/stage_release.py packaging/release-allowlist.txt "$OUT/2k5"
python3 packaging/check_2k5_mod_studio_release.py "$OUT/2k5"
python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt "$OUT/apf"
python3 packaging/check_apf2k8_mod_studio_release.py "$OUT/apf"
python3 packaging/build_archive.py "$OUT/2k5" "$T2K5" "$OUT/$T2K5.tar.gz" "$EPOCH"
python3 packaging/build_archive.py "$OUT/apf" "$TAPF" "$OUT/$TAPF.tar.gz" "$EPOCH"

python3 packaging/windows/build_windows_installer.py --stage "$OUT/2k5" --product 2k5 --version "$V2K5" --out "$OUT" --work "$OUT/windows-2k5"
makensis "$OUT/windows-2k5/installer.nsi"
python3 packaging/windows/build_windows_installer.py --stage "$OUT/apf" --product apf --version "$VAPF" --out "$OUT" --work "$OUT/windows-apf"
makensis "$OUT/windows-apf/installer.nsi"
(cd "$OUT" && sha256sum *-Setup.exe > installers.sha256)
while read -r hash name; do printf '%s  %s\n' "$hash" "$name" > "$OUT/$name.sha256"; done < "$OUT/installers.sha256"
```

Each product needs its own `--work` directory. The builder downloads and
verifies pinned Windows Python and wheels before generating the NSIS script.
Compiling on Linux proves packaging; test the installers on Windows before
publishing. `build_archive.py` writes the portable sidecars. Each sidecar must
be named `<asset>.sha256` and contain `<hash>  <name>` with two spaces and the
asset's basename.

Attach both portables, both installers and their four sidecars to your tagged
GitHub release. The updater in `mod_editor/core/self_update.py` looks for these
case-sensitive names:

| Product | Portable archive | Windows installer |
| --- | --- | --- |
| 2K5 | `2K5-Mod-Studio-v*.tar.gz` | `2K5-Mod-Studio-*-Setup.exe` |
| APF | `apf2k8-mod-studio-*.tar.gz` | `APF-2K8-Mod-Studio-*-Setup.exe` |

Enable Actions in your fork. CI runs on pushes to `main`, pull requests and
manual dispatch. In `.github/workflows/ci.yml`, the step **Hydrate exact
retail-free beta inputs** downloads two hash-pinned beta-50 test fixtures from
`cruuz/2k-football-mod-tools`, so it works in a fork without changes. If that
repository ever goes away, mirror those two assets under a beta-50 release in
your fork, point `--repo` at it and keep the pins. These older fixtures serve
tests; the release build recipe above uses the current release. Keep the 12 named developer-evidence skips for lean
checkouts. They are not permission to ignore new product failures. The workflow
runs tests and gates; it does not publish release files.

To author a SOFTDRINK pack from your own clean and finished images, use:

```bash
python3 tools/nfl2k5_modpack.py export-files --base RETAIL.xiso.iso --patched FINISHED.xiso.iso --out SOFTDRINK-2K28.2k5patch --recipe FROZEN_RECIPE.json --json
```

This exports a finished-disc pack without rebuilding a disc. Keep images,
patches, artwork and optional `--sources-out` bundles outside Git. See
[the pack format](docs/MODPACK_FORMAT.md) for source bundles and `--marks-pack`.

---

## Reporting instead of coding

A precise bug report is worth a great deal — the more specific the better. If you
can name the exact playbook, formation, down and distance, or the exact file and
byte offset, say so. A case that reproduces on demand is worth more than a broad
description, because it gives the work something to be right or wrong about.

Security issues: see [SECURITY.md](SECURITY.md) — please do not open a public
issue for those.
