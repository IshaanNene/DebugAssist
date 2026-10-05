# Contributing skills and domain extensions

DebugAssist's plan is fixed in code. What makes it good at *your* code is know-how written as markdown:
**skills** (in plugins) and **domain extensions**. Adding either needs no code and no redeploy — a PR to
`marketplace/`.

## Layout

```
marketplace/
  plugins/<plugin>/plugin.yaml                 name, version, description, owners, skills
  plugins/<plugin>/skills/<skill>/SKILL.md     frontmatter (name, description) + body
  domains/<domain>/domain.yaml                 name, description, owners, components, subagents
  domains/<domain>/kb/*.md                     knowledge-base docs (frontmatter: description)
```

There are exactly five plugins: `pr-authoring`, `test-planning`, `web-client-fixes`, `backend-fixes`,
`perf-and-battery`. Improve their skills, or add a skill to the plugin it belongs to.

## Writing a skill

```markdown
---
name: my-skill                # must equal the directory name
description: When to use it, in one sentence (≤ 300 chars) — this is all the agent sees up front.
---

# Title

Short, imperative rules the agent can act on. Prefer "do X because Y" over background reading.
```

- **Progressive disclosure:** a node's prompt lists only skill names and descriptions; the agent calls
  `load_skill(name)` to read the body. A good description is what gets a skill loaded.
- **Budget:** each agent type caps how many tokens of skills one node may load (`skill_token_budget` in
  `configs/agent_types/<type>.yaml`, ≈ characters / 4). Keep skills short.
- **Which nodes load it:** add the skill to an agent type's `skills: {node: [...]}` (nodes: `classify_rca`,
  `reproduce`, `fix`). The diff fixer uses the `fix` list.
- **No evaluation answers.** Skills are general know-how. Never describe a specific catalog bug, its fix
  or its tests; the lint rejects references to bug ids and ground truth, and evaluations should also run
  with skills off.

## Domain extensions

A domain owns components (`repo` + `path`). For issues in those components:

- its **subagents** (same format as `configs/subagents.yaml`) join the pool Clef's D7 picks from;
- its **knowledge-base docs** become loadable as `kb/<domain>/<doc>` next to the node's skills.

Keep knowledge-base docs factual (layout, contracts, runbooks) and check them against the code.

## Pinning

Agent types fetch the marketplace at `marketplace_ref` (`working` = this checkout; or a git ref).
`DA_MARKETPLACE_REF` overrides it for a run; PEX builds and runtime images record the commit they were
built from. `debugassist harness fetch <ref>` shows exactly what a ref contains.

## Checks

```bash
make lint-skills
```

It checks: exactly 5 plugins; every skill listed by its plugin and vice versa; frontmatter name and
description; each agent type's per-node token budget; and no evaluation answers. CI runs the same lint via
the test suite.

## Feedback loop

Review corrections classified by Clef (D18) as *fix approach* or *style* are proposed as one-line
additions under "Lessons from reviews" in the relevant skill, on a `debugassist/skill-…` branch. A human
reviews and merges them like any other skill change.
