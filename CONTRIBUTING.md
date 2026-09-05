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

**Some failures are expected on a clean checkout.** Around 19 test files need
retail game data, which this repository deliberately does not ship. They fail
identically on every OS, which is why CI's headline number is 107/126 rather
than 126/126. If your change makes that number *move*, that is the signal.

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
- **`tools/vendor/` and `reports/` are gitignored release-build inputs.** They
  exist only on a full build host. Anything that requires them must skip loudly
  with a reason on a clean checkout, the way the release-gate CI job already
  does — never a silent pass.
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

## Reporting instead of coding

A precise bug report is worth a great deal — the more specific the better. If you
can name the exact playbook, formation, down and distance, or the exact file and
byte offset, say so. A case that reproduces on demand is worth more than a broad
description, because it gives the work something to be right or wrong about.

Security issues: see [SECURITY.md](SECURITY.md) — please do not open a public
issue for those.

---

## Game modules

Support for another game lives under `mod_editor/games/<game>/` behind a versioned contract
(`mod_editor/games/contract.py`, spec in `docs/product/GAME_MODULE_CONTRACT.md`). The core
discovers a module and lists it under **File ▸ Select other games…**; it never imports one by
name. To start one: `python -m mod_editor.games new <game_id> --title "…" --platform "…"` and
follow `docs/product/ADDING_A_GAME_MODULE.md`. The contract's files are pinned
(`mod_editor/games/CONTRACT_PINS.json`); changing them is a versioned event with its own
procedure, described in `CLAUDE.md` / `AGENTS.md` at the repository root and in the spec.
