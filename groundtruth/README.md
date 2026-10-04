# Ground truth (never visible to agents)

The bug catalog used for demos and evals. **Nothing in this directory may be mounted into an agent
sandbox, copied into a target repo, or referenced by target-repo commits.** Agents see only what a
real on-call engineer would: the target repos' history, telemetry, reports and issues.

- `bugs/BUG-xxx.yaml` — scenario definition: injection, trigger, ground-truth location/facts, expected outcome
- `patches/BUG-xxx/*.patch` — regression commits (`git format-patch`, fictional authors), applied with `git am`
- `fixes/BUG-xxx.patch` — the reference fix (diff on top of the regression)
- `hidden_tests/BUG-xxx/*` — tests that fail on the regression and pass with a correct fix

Backgrounding in scenarios is emulated through the Page Visibility API (as a WebView/PWA host
would deliver it) so browser timer throttling does not mask client-side hot loops.
