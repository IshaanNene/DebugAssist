## Bisect, replayed (`debugassist eval replay-bisect`)

Each earlier validated run's reproduction test, run back through history from the release (earlier release tags until it passes, then git bisect; a commit is bad only when the test fails with the release's exception), no model; set beside the commit the run's RCA named.

| case | tests | found | commits | agree_with_rca | rca_named_another | other |
|---|---|---|---|---|---|---|
| REAL-001 | 13 | 0 | — | 0 | 0 | no_good_release |
| REAL-002 | 6 | 0 | — | 0 | 0 | no_good_release |
| REAL-003 | 3 | 3 | d8813b67a2 | 0 | 3 | — |
| REAL-004 | 5 | 0 | — | 0 | 0 | no_good_release |
| REAL-005 | 6 | 0 | — | 0 | 0 | could not apply, no_good_release |


| case | arm | seed | result | good | first_bad | subject | steps | rca_suspect | agrees |
|---|---|---|---|---|---|---|---|---|---|
| REAL-001 | real-04ab2bf | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | real-04ab2bf | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | real-04ab2bf | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | fixwidth-7f15556 | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | fixwidth-7f15556 | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | fixwidth-7f15556 | 4 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | repro2-f277379 | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | repro2-f277379 | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | repro2-f277379 | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | callers-0ed427d | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | callers-0ed427d | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | callers-0ed427d | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-001 | variants-4b1325c | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 57d2e4813d98 | None |
| REAL-002 | real-16088da | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-002 | real-16088da | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-002 | real-16088da | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-002 | fixwidth-7f15556 | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-002 | fixwidth-7f15556 | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-002 | fixwidth-7f15556 | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-003 | real-16088da | 2 | found | 3.0.4 | d8813b67a2 | Fix #460 Improve bump_prerelease to alway get a newer version (#462) | 4 | fdec4ae1e5e2 | False |
| REAL-003 | real-16088da | 3 | found | 3.0.4 | d8813b67a2 | Fix #460 Improve bump_prerelease to alway get a newer version (#462) | 4 | fdec4ae1e5e2 | False |
| REAL-003 | fixwidth-7f15556 | 3 | found | 3.0.4 | d8813b67a2 | Fix #460 Improve bump_prerelease to alway get a newer version (#462) | 4 | fdec4ae1e5e2 | False |
| REAL-004 | real-16088da | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-004 | real-16088da | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-004 | real-16088da | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-004 | fixwidth-7f15556 | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-004 | fixwidth-7f15556 | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  |  | None |
| REAL-005 | real-16088da | None | could not apply |  |  |  |  |  | None |
| REAL-005 | real-16088da | 2 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 3f43b98e8704 | None |
| REAL-005 | real-16088da | 3 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 3f43b98e8704 | None |
| REAL-005 | fixwidth-7f15556 | 1 | no_good_release |  |  | the test fails on every earlier release tried in this history (a regression from |  | 3f43b98e8704 | None |
| REAL-005 | fixwidth-7f15556 | None | could not apply |  |  |  |  |  | None |
| REAL-005 | fixwidth-7f15556 | None | could not apply |  |  |  |  |  | None |
