<!--
Check the base branch: it should be cruuz/2k-football-mod-tools : main.
A PR based on your own fork's main only merges into your copy.
-->

## What this changes

<!-- One or two sentences. What was wrong or missing before? -->

## What I proved, and how

<!--
The most important part of this description. For anything that writes bytes:
what did you verify, and with what? Byte-diff against a known-good output,
an independent verifier, a test with a fixture?
-->

## What I did NOT prove

<!--
Equally important, and not a weakness. Did you watch it work in-game, or only
offline? Which platforms did you actually run on? Saying "not tested on macOS"
or "no runtime witness yet" is the expected answer, not a problem.
-->

## Checklist

- [ ] Base branch is `cruuz/2k-football-mod-tools : main`, not my own fork
- [ ] The suite runs; the pass count did not drop
      (~19 files fail on any clean checkout — they need retail game data)
- [ ] No game data: no ISO, extracted file, texture, decoded pixel, audio sample
      or rollback byte is added to the repo or to a release archive
- [ ] Nothing writes to the user's original disc image or save — copies only
- [ ] If this adds or changes a capability: it is filed on the rung its evidence
      earns, and `runtime.status` honestly reflects whether it was seen working
      in-game
- [ ] If this adds a writer: it ships with a verifier that re-derives the
      container independently, rather than importing the writer's own parser
- [ ] If I touched a pinned module or anything it imports, I ran
      `python3 packaging/repin.py --apply`
- [ ] If I touched packaging or an allowlist, both release gates still pass

## Anything you want a second opinion on

<!-- Places you were unsure. Genuinely useful to flag; it directs the review. -->
