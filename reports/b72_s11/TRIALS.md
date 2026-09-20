# b72-s11 fit trials

`initial_unpinned_trial.log` is an exploratory render that started before the first fit-authoring process finished. It is excluded from every final measurement and must not be used as proof of a fixed candidate. `shift_measurements.log` records the rejected positive Texans offset, which worsened the reference residual.

`search_trials.json` and `search.log` retain all 80 safe candidates from the bounded native search, including smaller sizes and rejected shifts. The final author uses the selected per-team fits in `selected_fits.json`; every one must still pass complete source and filtered-ink containment.

`baseline_validation.log` and `final_validation.log`, together with their measurement JSON files, are the final same-state residual receipts. Fresh baseline rows equal s10 exactly. The original test expectation for the cropped Chiefs aspect failed once and is retained in `sprite_old_cropped_aspect.log`; the final complete-mark expectation retains the same tolerance.
