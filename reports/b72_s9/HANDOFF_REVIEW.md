# Handoff fact-check dispositions

The installed factcheck.py recipe checked the exact 20-line ASTRA_LAST_MESSAGE.md against the four job reports. All 20 claims are covered; five were flagged for manual reading. Raw requests/answers and handoff_factcheck.md retain the result. No in-game witness was inferred from a model score.

| Flagged claim | Direct check and disposition |
|---|---|
| Supplied before witnesses name Noah | NAMES_PERSON is expected: the user explicitly supplied Noah's captures and attribution. They are labelled disc q before views, never proposed-build captures. |
| 72 state sheets plus four detail sheets | Directory count is exactly 76 PNGs: 72 without `_detail_` and four with it. Filenames enumerate two matchups, 18 states and two aspects, plus two live reference matchups at both aspects. Claim retained. |
| All 104 team/aspect label checks pass | readability.json contains 104 rows, all predicted_pass=true, each core_luma>=200 and contrast>=4.5. This is the specifically stated offline luminance/contrast check. The 40 detailed residual failures concern strict visual matching, including the intentional cap-size difference; they do not contradict this narrower readability result. Claim retained. |
| Jev activity and cost names a person | Jev is the requested typed-decision model. Forty-one logged batches, 966 batch states and one initial status ping total $0.05185558, below $3. This is not a human attribution. |
| Noah approves release | NAMES_PERSON is required task attribution. No release or new game witness is claimed, and no release action was performed. |

All five flags were reviewed against receipts or the user's explicit instructions. The fact-check remains recorded as flagged-with-dispositions rather than relabelled clean. The final source implementation is unchanged after its gate; subsequent commits contain only reports and evidence.
