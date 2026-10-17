# Pre-registered arms

An arm states what would count as success **before** it runs (ROADMAP-100 083). Add `evals/arms/<name>.yaml`, commit
it, then run the arm; `debugassist eval report` checks it in the section "Pre-registered checks":

```yaml
arm: variants            # matches result rows whose `arm` starts with this
registered: 2026-10-20T09:00:00Z
hypothesis: the call-variations check stops narrow fixes without refusing good ones
checks:
  - metric: hidden_tests_pass   # rca_exact | rca_exact_or_directional | category_ok | validated | hidden_tests_pass
    at_least: 0.5
  - metric: validated
    at_least: 0.6
```

A check is **met** when the pooled rate reaches `at_least`; the report shows its 95% Wilson interval beside it, so a
rate that only just reaches the threshold on a handful of runs reads as what it is. An arm whose first run is
older than its `registered` time is reported as **not pre-registered** — its checks are still computed, but they were
chosen with the results in view.
