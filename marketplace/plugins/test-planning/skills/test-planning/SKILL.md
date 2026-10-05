---
name: test-planning
description: Plan the reproduction test — pick the cheapest tier that shows the bug, assert the correct behaviour, keep it deterministic. Use before writing a reproduction or E2E test.
---

# Planning a reproduction test

1. **State the failure in one sentence** from the user's point of view ("a second ride is created",
   "the app throws on launch"), then the condition that triggers it.
2. **Pick the cheapest tier that can show it.** A pure function or one module → unit test. Several
   modules or a component rendering → integration/component test with only the network mocked. Timing,
   network conditions, real browser behaviour or several services → E2E with the user's environment.
3. **Assert the correct behaviour**, never the current one. The test fails on the buggy release for the
   reason in the root cause, and passes once the fix is right — not merely when the symptom is hidden.
4. **Make it deterministic.** Fake timers advanced explicitly; seeded data; no real sleeps; no reliance
   on test order. A test that only times out proves nothing.
5. **Reuse the repository's helpers** (factories, mocks, fixtures) and put the test where similar tests
   live, named after the behaviour it protects.
6. **Check it fails for the right reason**: read the failure message; an import error or a typo is not a
   reproduction.
