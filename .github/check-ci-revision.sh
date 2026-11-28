#!/usr/bin/env bash
# Keep testing the merge result when the base branch contributes file changes.
# With identical trees, use the proposed commit itself for release provenance.
set -euo pipefail

proposed_sha=${1:-}
if [[ -n "$proposed_sha" ]]; then
    merge_tree=$(git rev-parse 'HEAD^{tree}')
    proposed_tree=$(git rev-parse "$proposed_sha^{tree}")
    if [[ "$merge_tree" == "$proposed_tree" ]]; then
        git checkout --quiet --detach "$proposed_sha"
    fi
fi

printf 'CI_CHECKOUT_SHA=%s\n' "$(git rev-parse HEAD)"
