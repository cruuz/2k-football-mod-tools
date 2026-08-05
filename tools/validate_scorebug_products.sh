#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

# One registered command owns both scorebug capabilities.  The NFL validator
# checks the typed three-target project contract and delegates the single
# retail-sized copied-XISO build to the presentation validator.  Keeping that
# composition here lets the aggregate deduplicate the two registry rows without
# retaining or trusting a cross-process 6.3 GB cache.
bash tools/validate_nfl2k5_scorebug_mod_project.sh

echo 'SCOREBUG_PRODUCTS_VALIDATION_PASS capabilities=apf-inventory,nfl-textures retail_xiso_builds=1 retained_xiso=false'
