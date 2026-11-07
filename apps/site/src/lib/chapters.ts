// The site's pages after the home page, in reading order.

/** The site's chapters, in reading order: the nav, the home page's contents and every page's "next" link. */
export const CHAPTERS = [
  { href: "/system/", n: "01", title: "System", blurb: "Signals in, read-only evidence up, one write gate out — and the servers that hold the evidence." },
  { href: "/pipeline/", n: "02", title: "Pipeline", blurb: "Ten steps in a fixed order. Who acts at each, which decisions it takes, and how long each took in a real run." },
  { href: "/decisions/", n: "03", title: "Decisions", blurb: "Every judgement call as a calibrated probability: every Clef template, its thresholds and outcomes." },
  { href: "/run/", n: "04", title: "A real run", blurb: "One evaluated run on its true clock, each figure linked to the file, row and field it comes from." },
  { href: "/safety/", n: "05", title: "Safety", blurb: "The write policy as the agent runs under it, and the threat model: boundaries, controls and the tests that hold them." },
  { href: "/design/", n: "06", title: "Design records", blurb: "The architecture decisions behind all of it, with their context and consequences." },
  { href: "/results/", n: "07", title: "Lab notebook", blurb: "Every measurement with its report: the bug catalog, Clef against an LLM, real open-source bugs." },
] as const;
