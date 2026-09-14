# J7 beta 69 integration wiring

J7 directly edits the GUI owners granted in the brief, public mod-editor docs and tests.
No core/tool writer, service, registry, model-project integration or equipment-fit wording
was changed. No writer repin or cave-manifest regeneration is needed for J7. **Zero new
capabilities.** Existing count pins do not change.

## Required package entries

Both release allowlists are protected. Add these exact lines, once each, beside their
existing GUI helper and guide entries. These are required because both shells and the
shared updater now import the plain-error/tooltip helpers.

`packaging/release-allowlist.txt`:

```text
mod_editor/gui/polish_qt.py
docs/mod_editor/2k5_mod_studio_faq.md
```

`packaging/apf2k8-release-allowlist.txt`:

```text
mod_editor/gui/ux_text.py
mod_editor/gui/polish_qt.py
docs/mod_editor/apf2k8_mod_studio_faq.md
```

Each guide links its own packaged FAQ. The APF FAQ's cross-product reference uses the
repository URL so it does not need to ship the 2K5 guide.

Do not ship audit inventories, tests, logs or the Git bundle as product assets.

## J1: preserve the actual failure before it reaches the GUI

`mod_editor/core/nfl2k5_build_service.py:_last_message`, currently lines 868–881, appends
stdout after stderr and chooses the last line. Consequently the final timing record can
replace the actual stderr failure. A GUI cannot recover a cause that this function discarded.
J7's formatter removes class prefixes and timing records as a final display guard. J1 owns
the source fix and richer edit identification. If J1 has not already replaced this function,
use this exact fallback implementation (or preserve its semantics in J1's richer result):

```python
def _last_message(result: CommandResult) -> str:
    import re
    for stream in (result.stderr, result.stdout):
        lines = [line.strip() for line in stream.splitlines()
                 if line.strip() and not line.strip().startswith("NFL2K5_BUILD_PHASE ")]
        if not lines:
            continue
        message = lines[-1]
        message = re.sub(r"^(?:[\w.]+(?:Error|Exception)|error):\s*", "", message,
                         flags=re.IGNORECASE)
        if message:
            return message
    return ("The build stopped without reporting its cause. Copy the Build summary "
            "and post it with the first error from the build log.")
```

At the failed-build raise in `Nfl2k5BuildService.build` (~1317), exact replacement:

```python
raise Nfl2k5BuildError("Could not make the disc copy. " + _last_message(built))
```

`tools/nfl2k5_visual_mod_project.py:_PhaseTimer` (~5246): keep its machine-readable timing
record in diagnostic output; it is not a user-facing replacement string. J1 should select
an actual error before composing the service message, as above. Do not relabel the protocol
or remove timing evidence. J1 retains all equipment fit/legacy-import refusals, including
byte shortfalls and the next usable import choice.

## Shared writer completion copy

`mod_editor/core/build_feedback.py:compare`: replace only the three user-facing messages;
keep outcome comparison and retained-art warnings unchanged.

Changed outcome, exact replacement:

```python
"The copy differs from your source. Review the Build summary for its selected contents and any edits kept original."
```

Unchanged outcome, exact replacement:

```python
"No changes were written. This is an unchanged copy of your source. The selected changes may already be installed; review the source and your selections before rebuilding."
```

`completion`, unknown-measurement body, exact replacement:

```python
"The copy was written, but this receipt does not say whether it differs from the source. Review the Build summary before using the copy."
```

The GUI now adds the build selection in words and a play/open next step. Its **Copy Build
summary** retains the original request and first failure. These wording changes must not
turn an unchanged or unmeasured receipt into a successful-change claim.

## Registry evidence wording, coordinate with J1/J3

No new rows and no broad upgrade to fully tested. The baseline registry still says the
inline MyCareer has no played result, while triage row 10 reports a positive witness for
the previous Supersim/PAT fixes and a separate new first-play failure. Keep prior offline
evidence and replace only the runtime scope/status for `nfl2k5.mode.my_career_inline` after
J3 merges. Exact additional scope sentence:

```text
andrethealchemist reported on 2026-09-12/13 that the previous Fast forward cancellation, possession, Apartment-setting and PAT fixes work in-game. He separately reported a preselected first play after returning to the field. These reports cover those sequences only; new beta 69 play-calling changes and other positions, saves and mode combinations remain UNWITNESSED.
```

Append that sentence to the existing `runtime.scope`; set `runtime.status` to `partial`.
Keep the original host/native proof description. J3 should supply the final scope for its
new writer, rather than declaring the whole mode witnessed.

For `nfl2k5.uniforms.all_visual` and `nfl2k5.textures.all_p8`, retain existing status values
and evidence. Append this exact sentence to `runtime.scope` and to the shoes09/shoes10
paragraph of `gui.reason` if that paragraph remains after J1:

```text
maumau78 reported Style 6/shoes10 visible in the Bears Edit Player preview but absent in-game on 2026-09-13. The earlier package-local colour proof is offline evidence and does not establish that played binding; preview visibility is not an in-game success.
```

APF `play_design.create_formation`, `play_design.create_play` and `playbooks.cpu_playcalling`
retain their not-tested/UNWITNESSED gameplay scope. J7 found no basis to upgrade them. The
new FAQ explicitly distinguishes Play Calling from designing a play and retains CPU-book,
off-by-default and BASE/TU 1.1 limits.

## Existing unrelated metadata gate

`tests/mod_editor/test_no_capability_is_invisible.py` validates every registry evidence
path before its GUI assertions. In this lean worktree it stops at
`docs/research/apf_audio.md`, which is absent. This is an existing untracked release-input
boundary, not a reason to weaken the gate. Restore the complete reviewed evidence metadata
in the integration tree and run the file standalone there. The current guide-title assertion
was preserved. J7's own page, public-string and local doc-link gates do not need that history.

## Git delivery under the read-only worktree metadata boundary

The shared worktree index is at an unwritable path under the main repository's `.git`.
All J7 commits therefore live in `/tmp/b69-j7-git`, on `astra/b69-j7-polish`, using this
worktree as their working directory. The root bundle `BETA69_J7.bundle` is the portable
commit delivery. No shared ref, index, other checkout or remote was changed. Fetch the
bundle and cherry-pick the listed commits in the integration tree. Preserve the untracked
handoff files already present at session start; they are not in these commits.
