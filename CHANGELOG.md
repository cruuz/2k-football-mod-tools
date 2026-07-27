# Changelog

Release-level history. Per-product detail lives in
[`STATUS.md`](STATUS.md) (2K5, plus the published-asset receipts) and
[`docs/mod_editor/apf2k8_mod_studio_changelog.md`](docs/mod_editor/apf2k8_mod_studio_changelog.md)
(APF).

Product versions and release tags are deliberately separate. A tag like
`beta-3` names a *published set of archives*; the editors inside carry their own
versions (`v1.0-RC30`, `0.1.0-alpha.35`) and only change when their code does.

---

## beta-5 — 2026-07-27

**Windows bug fix.** Editor code changed, so both products move: `v1.0-RC30` and
`0.1.0-alpha.35`. If you are on Windows and beta-4 could not export a texture,
this is the release that fixes it.

### Fixed
- **Every APF texture writer now runs on Windows.** Field art / endzones, team
  logos, the logo cache, the generic texture writer and uniform mips all failed
  immediately with `AttributeError: module 'os' has no attribute 'O_CLOEXEC'`.
  That flag does not exist in CPython on Windows, and four writers passed it to
  `os.open` as a bare attribute rather than `getattr(os, "O_CLOEXEC", 0)` — the
  form 284 other sites in the tree already used. A user reported it against the
  ordinary "export and replace field endzone" flow; thank you.
- **The 2K5 direct uniform-colour writer falls back correctly off Linux.**
  `copy_fd_exact` called `os.copy_file_range` inside `except OSError`, but on
  Windows and macOS the syscall's absence raises `AttributeError`, so the
  documented fallback never ran. The syscall is resolved before the loop now.

### Unchanged on purpose
- **No capability was added, removed or re-graded.** Both registries and every
  ladder position are exactly what beta-4 shipped, and no guarantee is weaker:
  PEP 446 makes every descriptor CPython creates non-inheritable on all
  platforms, so close-on-exec never depended on the flag that was missing.
- Nothing was at risk on the affected machines. The failure landed in the output
  reservation — after the read-only preflight, before any output existed — so no
  file was written at all.

### Added
- `tests/mod_editor/test_shipped_tools_posix_only.py`, a guard that needs **no
  retail data**. Every test over these writers is gated on extracted retail data
  no CI runner has, which is how six green-parity CI jobs never executed one
  `os.open` inside a writer. The new file scans both release allowlists for bare
  POSIX-only `os.open` flags, and deletes those names from `os` to drive every
  shipped writer's real reservation path. Targets come from the allowlists, so a
  writer added later is covered without editing the test.

## beta-4 — 2026-07-25

**Windows installers.** No editor code changed, so both products still identify
as `v1.0-RC29` and `0.1.0-alpha.34`, and the tarballs are byte-identical to
beta 3. This release adds a way to install without a command prompt.

### Added
- **`2K5-Mod-Studio-…-Setup.exe` and `APF-2K8-Mod-Studio-…-Setup.exe`** — wizard
  installers that need nothing preinstalled. No Python, no pip, no 7-Zip, no
  PATH changes, no command prompt. They install per-user under `%LOCALAPPDATA%`,
  so they never ask for administrator rights or touch Program Files, and they
  add Start Menu and desktop shortcuts plus a normal entry in Apps & features.
- **A warning page as the second step of the wizard**, before anything is
  written to disk, with Next disabled until it is acknowledged. It explains the
  SmartScreen prompt an unsigned program triggers, that the visible button is the
  wrong one, that the path is *More info → Run anyway*, and how to verify the
  download by SHA-256 rather than trusting the project. Someone who meets that
  prompt with no warning reasonably concludes the download is malware.
- `packaging/windows/build_windows_installer.py` builds them, and
  `packaging/windows/UNSIGNED-NOTICE.txt` is the text shown in that page.

### How they are built, and why not PyInstaller
The application verifies its own integrity at runtime: `_read_pinned_payload`
reads each pinned module from `workspace/<path>` and hashes the bytes, and the
workspace comes from `Path(__file__).resolve().parents[2]`. A frozen build has
neither real `.py` files nor a meaningful `__file__`, so freezing would silently
delete the guarantee that makes the tool safe to point at a game.

Instead each installer carries a **private CPython** (python.org's embeddable
build) beside the application, with `..\app` on `sys.path` via its `._pth`. The
application ships byte-identical to the tarball — same files, same pins — and
runs with no `PYTHONPATH` and no dependence on the working directory.

### Reproducible, and fail-closed about it
Every byte entering the installer from outside this repository is pinned to an
exact SHA-256 and verified before use: the interpreter and all four wheels
(PyQt5, PyQt5-Qt5, PyQt5-sip, Pillow). A hash mismatch, an unpinned wheel the
resolver pulled in, or a pinned wheel that fails to appear all stop the build
rather than shipping. Version pins alone would not be enough — a version can be
re-uploaded and a resolver can choose a transitive dependency nobody reviewed.

Both installers rebuild **byte-identical**, verified by building each twice and
comparing, so the published SHA-256 means something.

### Verified
Built and exercised end to end under wine, not merely compiled: silent install
lands the expected tree, the private interpreter imports `mod_editor`, PyQt5 and
Pillow, `pythonw.exe` with the shortcut's exact arguments runs without exiting,
and the uninstaller removes everything it created. The warning page was captured
rendering with Next correctly disabled. The refusal path was tested by feeding
the build a wrong hash and confirming it stops.

### Known limit
The installers are **not code-signed**, so Windows shows a SmartScreen prompt the
first time. A certificate costs a few hundred dollars a year, which this project
does not have. The wizard, the release notes and the download instructions all
say so up front rather than letting it come as a surprise.

---

## beta-3 — 2026-07-25

**Documentation, licensing and packaging. No editor code changed**, so both
products still identify as `v1.0-RC29` and `0.1.0-alpha.34`.

Beta 2 shipped correct software with incorrect paperwork, and its APF asset was
replaced twice on release day. Beta 3 exists so there is one unambiguous set of
archives to point people at.

### Fixed
- **The shipped `APF2K8-README.md` contradicted the archive it shipped in.** It
  told Windows users the ISO path would not work and reported the test suite as
  not yet passing on Windows or macOS. Both had stopped being true: the bundled
  `extract-xiso.exe` was in the same tarball, and all six CI jobs had been
  reporting identical results. Corrected, and the title no longer says
  "for Linux" — one archive serves all three platforms.
- **`README.md`'s opening line** still described "two retail-free Linux mod
  editors" a few paragraphs above the section stating that all three platforms
  pass the same suite.
- **Neither archive contained a licence.** The MIT licence requires its own text
  to accompany every copy of the software, so the archives were out of
  compliance with their own licence. `LICENSE` and `NOTICE.md` now ship inside
  both.

### Added
- **`NOTICE.md`** — the game-IP scope (previously an appendix inside `LICENSE`),
  the retail-free statement, third-party attribution for the bundled extractor,
  and the trademark notice.
- **`tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md` now ships in
  the APF archive.** The release notes told users to read it; it was not in what
  they downloaded.
- **The release pipeline is in the repository**: `packaging/stage_release.py`,
  `packaging/build_archive.py` and `packaging/repin.py`. These had lived only in
  scratch directories and were reconstructed from transcripts three times, most
  recently after a power cut. Staging from an allowlist and rebuilding at epoch
  `2026-07-25T00:00:00Z` reproduces the published bytes exactly.
- **`STATUS.md` gained a "Published releases" section** recording the identity
  of every asset actually published, including superseded uploads, so an early
  download can be identified rather than left ambiguous.
- Contributor scaffolding: `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, issue forms and a pull-request template.

### Changed
- `LICENSE` now contains the MIT text and nothing else, so licence scanners
  identify the project as MIT. **No terms changed** — the game-IP paragraph moved
  verbatim into `NOTICE.md` and still applies.
- The APF asset is named `apf2k8-mod-studio-0.1.0-alpha.34-20260725.tar.gz`,
  matching the 2K5 convention of a dated asset name. Beta 2 reused one filename
  across three different sets of bytes; the date makes that impossible to repeat.

### Verified
All six CI jobs identical at **107/126 files, 1304 tests** (Windows, macOS and
Linux × Python 3.11 and 3.12); both retail-free release gates green. Local suite
on a host with retail data: **126/126 files, 1364 tests**. Both archives rebuild
byte-identically, pass their gates when run against the *extracted* archive, and
cold-start with no `PYTHONPATH`.

---

## beta-2 — 2026-07-25

**Superseded by beta 3** — its APF archive was replaced twice and its shipped
documentation was wrong. Kept for the record.

### Added
- **Windows and macOS support.** Every OS difference is concentrated in one shim
  (`mod_editor/core/platform_compat.py`). Real implementations rather than
  `if windows: skip` — positional I/O, directory transactions, atomic
  no-clobber publication, private-cache privacy, ownership and durable flushes
  each have genuine Windows and macOS paths, and where a platform cannot provide
  a guarantee the tools say so instead of pretending.
- **APF team logos** on helmets and the score bug, and **APF field art /
  endzones** — both proven bit-exact by an independent verifier, taking the
  capability registry to 65.
- CI matrix across Windows, macOS and Linux on Python 3.11 and 3.12, plus a
  capability-registry job and both retail-free release gates.
- `extract-xiso` bundled for Linux **and** Windows, each pinned by exact size and
  SHA-256, cross-compiled reproducibly from the same vendored 2.7.1 source.

### Fixed
- A `QScrollArea` regression that painted light grey over the dark theme on
  every APF page.
- Windows file locking, CRLF translation, binary-mode reads and 8.3 short names
  corrupting byte-exact artifacts.
- Twelve security weakenings in the Windows/macOS fallback branches, found by an
  independent audit and closed over ten remediation passes. The recurring fault
  was fallbacks *claiming* guarantees they did not enforce.

---

## beta-1 — 2026-07-22

First public beta of both editors. Linux-first. See
[`BETA_RELEASE_NOTES.md`](BETA_RELEASE_NOTES.md).
