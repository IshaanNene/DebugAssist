---
name: perf-and-battery
description: Diagnose and fix CPU, battery and jank problems in the web client — background work, timers, render loops. Use for performance or battery reports.
---

# CPU, battery and responsiveness

- **Measure before and after.** Use the session's perf samples (wakeups, busy fraction, long tasks) to say
  what was busy and when — visible or hidden. A fix must change the number, not just the code.
- **Background work must be justified.** While the page is hidden, timers and polling should stop, slow
  down sharply, or be replaced by a single catch-up on return. Check `document.visibilityState` handling
  on both transitions.
- **Every rescheduling loop needs a floor.** Code that computes the next delay should clamp it to a sane
  minimum so a bad input cannot turn it into a busy loop.
- **Avoid render storms:** stable dependencies in effects, no state updates in render, batch updates that
  arrive together.
- **Tests:** drive timers with fake time and count callbacks or wakeups over a fixed interval, visible and
  hidden; for real-browser behaviour use the E2E helpers (`throttleCpu`, `setHidden`, `scriptSeconds`).
