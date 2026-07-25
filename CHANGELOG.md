# Changelog

Release-level history. Per-product detail lives in
[`STATUS.md`](STATUS.md) (2K5, plus the published-asset receipts) and
[`docs/mod_editor/apf2k8_mod_studio_changelog.md`](docs/mod_editor/apf2k8_mod_studio_changelog.md)
(APF).

Product versions and release tags are deliberately separate. A tag like
`beta-3` names a *published set of archives*; the editors inside carry their own
versions (`v1.0-RC29`, `0.1.0-alpha.34`) and only change when their code does.

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
