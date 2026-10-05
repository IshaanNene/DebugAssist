// Shapes returned by packages/api (debugassist.api.data).
export type Json = Record<string, unknown>;

export interface RunSummary {
  run_id: string;
  issue_ref: string;
  issue_id: string;
  source: "vitals" | "bugdrop" | null;
  title: string | null;
  app: string | null;
  version: string | null;
  status: string;
  llm_mode: string;
  started_at: string | null;
  priority: string | null;
  severity: string | null;
  owner: string | null;
  oncall: string | null;
  customer_impacting: number | null;
  worth_agent_run: number | null;
  jira: string | null;
  category: string | null;
  location: string | null;
  validated: boolean;
  tier: string | null;
  outcome: string | null;
  pr: string | null;
  watch: string | null;
  cost_usd: number;
  seconds: number;
}

export interface Issue {
  source: "vitals" | "bugdrop";
  id: string;
  title: string;
  kind: string | null;
  app: string | null;
  version: string | null;
  status: string | null;
  opened_at: string | null;
  events: number | null;
  url: string;
  run: RunSummary | null;
}

export interface GraphNode {
  id: string;
  kind: string;
  status: "done" | "failed" | "running" | "pending" | "skipped";
  ms: number | null;
  runs: number;
}

export interface Claim {
  text: string;
  evidence_ids: string[];
}

export interface RunDetail {
  summary: RunSummary;
  state: RunState;
  graph: GraphNode[];
  phoenix_url: string;
}

export interface TestRun {
  label: string;
  command: string;
  exit_code: number;
  output_tail: string;
}

export interface RunState {
  run_id: string;
  status: string;
  issue: Json & { id: string; title: string; url: string; source: string };
  triage: (Json & { priority: string; severity: string; owner_team: string; oncall: string; jira_url?: string }) | null;
  evidence: { id: string; source: string; kind: string; summary: string }[];
  rca: {
    category_decision: Json;
    actionable: boolean;
    llm: Json;
    routing?: Json;
    subagents?: { id: string; status: string; turns?: number; cost_usd?: number; finding?: { summary: string; confidence: string } | null }[];
    grounding?: { claim: number; text: string; grounding: "supported" | "unverified" | "unsupported"; p: number | null }[];
    dropped_claims?: Claim[];
    output: {
      summary: string;
      category: string;
      root_cause: string;
      location: { repo: string; file: string; function: string; line: number | null };
      suspect_commit: string | null;
      implicated_flag: string | null;
      claims: Claim[];
      timeline: { when: string; event: string; evidence_ids: string[] }[];
      reproduction: string;
      fix_direction: string;
    } | null;
  } | null;
  mitigation: { flag: string | null; action: string; detail: string; correlation: Json } | null;
  fix_plan: { focus: string[]; strategy: Json; tier: Json; ladder: string[]; suspect_commits: { sha: string; subject: string }[]; skip: string | null } | null;
  fix_attempts: {
    n: number;
    tier: string | null;
    repro: { test_file: string; asserts: string } | null;
    repro_verified: boolean;
    output: { commit_title: string; summary: string; rationale: string; strategy: string; risk: string } | null;
    diff: string;
    files: string[];
    llm: Record<string, Json>;
  }[];
  validation: { passed: boolean; failing_before: TestRun | null; passing_after: TestRun | null; suite: TestRun | null; static: TestRun | null; attempts: Json[] } | null;
  ship: { outcome: string; risk: number | null } | null;
  pr: { url: string; number: number; branch: string; base: string; draft: boolean; mode: string } | null;
  watch: { status: string; reason: string | null; before: Json; after: Json; decision: Json; actions: string[] } | null;
  notifications: Json[];
  post_pr?: Json[];
  costs: Record<string, number>;
  timings_ms: Record<string, number>;
  errors: string[];
}

export interface Decision {
  id: string;
  created_at: string;
  decision_id: string;
  description?: string;
  backend: string;
  model: string;
  mode: string;
  questions: Record<string, { instructions?: string; type?: string }>;
  answers: Record<string, Json>;
  chosen: Json;
  confidence: number;
  band: string;
  action: string;
  latency_ms: number;
  cost_usd: number;
  fallback_reason: string | null;
  policy?: { question: string; tau_high: number; tau_low: number };
}

export interface Call {
  at: string;
  node: string;
  turn?: number;
  kind: string;
  tool?: string;
  args?: Json;
  ok?: boolean;
  ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  reason?: string;
}
