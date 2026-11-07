// The site's pages after the home page, in reading order. `nav` marks the ones in the header bar; every page is in
// the header's index, the footer and the home page's contents.

/** The site's chapters, in reading order: the nav, the home page's contents and every page's "next" link. */
export const CHAPTERS = [
  { href: "/system/", n: "01", nav: true, title: "System", blurb: "Signals in, read-only evidence up, one write gate out — and the servers that hold the evidence." },
  { href: "/discovery/", n: "02", nav: true, title: "Discovery", blurb: "How a bug reaches it: crash groups, rider reports, labeled issues and red checks — deduplicated and triaged before any agent runs." },
  { href: "/pipeline/", n: "03", nav: true, title: "Pipeline", blurb: "Ten steps in a fixed order. Who acts at each, which decisions it takes, and how long each took in a real run." },
  { href: "/decisions/", n: "04", nav: false, title: "Decisions", blurb: "Every judgement call as a calibrated probability: every Clef template, its thresholds and outcomes." },
  { href: "/clef/", n: "05", nav: true, title: "Why Clef", blurb: "The case for a decision model over an LLM's own confidence, how it works inside, and where the bet stands — losses included." },
  { href: "/run/", n: "06", nav: false, title: "A real run", blurb: "One evaluated run on its true clock, each figure linked to the file, row and field it comes from." },
  { href: "/safety/", n: "07", nav: false, title: "Safety", blurb: "The write policy as the agent runs under it, and the threat model: boundaries, controls and the tests that hold them." },
  { href: "/testbed/", n: "08", nav: false, title: "Test bed", blurb: "MiniRide, a four-service app with real telemetry, and how each catalog bug is shipped into it, triggered and verified." },
  { href: "/repo/", n: "09", nav: false, title: "On your repository", blurb: "The GitHub App: label an issue, get the root cause on it and a draft pull request when the fix validates." },
  { href: "/design/", n: "10", nav: false, title: "Design records", blurb: "The architecture decisions behind all of it, with their context and consequences." },
  { href: "/stories/", n: "11", nav: true, title: "Field notes", blurb: "The problems that cost real time, as case files: the numbers that lied, the harness bugs, the checks no model could do." },
  { href: "/lessons/", n: "12", nav: false, title: "Lessons learned", blurb: "Every problem that cost real time: what we saw, why, what fixed it, and the guard that stops it coming back." },
  { href: "/results/", n: "13", nav: true, title: "Lab notebook", blurb: "Every measurement with its report: the bug catalog, Clef against an LLM, real open-source bugs." },
  { href: "/costs/", n: "14", nav: false, title: "Cost and latency", blurb: "What a run costs and how long it takes: per-run cost, time to a root cause, Clef latency and the caps that bound a run." },
  { href: "/limits/", n: "15", nav: false, title: "Limitations", blurb: "What it cannot do yet: each weakness with the evidence from the reports and what would change it." },
] as const;
