"""Pipeline nodes N0–N9 (minimal-but-real versions for the walking skeleton).

Deterministic nodes call backends directly (the same functions the MCP servers expose, so evidence
ids match what agents see); LLM nodes go through the LLMRunner seam; decisions go through Clef;
every write goes through the policy gate.

One module per node (ROADMAP-100 031); shared helpers in `common` and `testing`. Every name the old
single module had is still importable from here, the old private ones as aliases."""

from __future__ import annotations

import httpx  # tests patch `nodes.httpx`

from debugassist.core.policy import ROOT
from debugassist.pipeline import skills  # tests patch `nodes.skills`
from debugassist.pipeline.nodes import (
    checks,
    classify,
    common,
    context,
    fixing,
    intake,
    mitigation,
    pr,
    ship,
    testing,
    triage,
    validation,
)
from debugassist.pipeline.nodes.checks import (
    call_variants_check,
    check_prompt,
    prove_culprit,
    python_for,
    second_reproduction,
)
from debugassist.pipeline.nodes.classify import classify_rca, rca_prompt
from debugassist.pipeline.nodes.common import (
    ASSERTION_FAILED,
    NON_ACTIONABLE,
    PRIORITIES,
    PROMPTS,
    TIMEOUT_MARKERS,
    bot_branch,
    code_repos_env,
    component_cfg,
    error_pattern,
    error_signature,
    error_type,
    evidence_bundle,
    llm_summary,
    load_prompt,
    pipeline_yaml,
    repro_problem,
    run_on_release,
    run_values,
    sandbox_for,
    source_label,
    static_problem,
    stop_if_out_of_quota,
    top_in_app,
    wrong_value_report,
)
from debugassist.pipeline.nodes.context import context_collector
from debugassist.pipeline.nodes.fixing import fix
from debugassist.pipeline.nodes.intake import ingest, with_agent_type
from debugassist.pipeline.nodes.mitigation import flag_names, known_flag, mitigate
from debugassist.pipeline.nodes.pr import (
    app_comment,
    comment_app_issue,
    link_source,
    post_merge_watch,
    pr_and_notify,
)
from debugassist.pipeline.nodes.ship import (
    SCOPE_SLACK,
    commit_trailer,
    outside_plan,
    ready_pr_allowed,
    ship_gate,
)
from debugassist.pipeline.nodes.testing import (
    apply_diff,
    e2e_tool,
    file_at_release,
    fix_contract_problem,
    new_test_files,
    repro_cmd,
    reset_to,
    revert_non_tests,
    run_test,
    test_cmd,
    tier_problem,
    worktree_status,
)
from debugassist.pipeline.nodes.triage import auto_triage, jira_label, oncall_for, repo_owner
from debugassist.pipeline.nodes.validation import decide_retry, validate
from debugassist.pipeline.notify import notify

MODULES = (
    common,
    testing,
    intake,
    triage,
    context,
    classify,
    mitigation,
    fixing,
    checks,
    validation,
    ship,
    pr,
)

# the old module's private names

_apply_diff = apply_diff

_at = file_at_release

_bot_branch = bot_branch

_bundle = evidence_bundle

_code_repos_env = code_repos_env

_comment_app_issue = comment_app_issue

_commit_trailer = commit_trailer

_component_cfg = component_cfg

_e2e_tool = e2e_tool

_error_signature = error_signature

_error_type = error_type

_flag_names = flag_names

_jira_label = jira_label

_link_source = link_source

_llm_summary = llm_summary

_new_test_files = new_test_files

_notify = notify

_oncall = oncall_for

_outside_plan = outside_plan

_pipeline_yaml = pipeline_yaml

_prompt = load_prompt

_python = python_for

_ready_pr_allowed = ready_pr_allowed

_repo_owner = repo_owner

_repro_cmd = repro_cmd

_repro_problem = repro_problem

_reset_to = reset_to

_revert_non_tests = revert_non_tests

_run_on_release = run_on_release

_run_test = run_test

_sandbox = sandbox_for

_source_label = source_label

_static_problem = static_problem

_status = worktree_status

_stop_if_out_of_quota = stop_if_out_of_quota

_test_cmd = test_cmd

_tier_problem = tier_problem

_top_in_app = top_in_app

_with_agent_type = with_agent_type

_wrong_value_report = wrong_value_report


__all__ = [
    "ASSERTION_FAILED",
    "MODULES",
    "NON_ACTIONABLE",
    "PRIORITIES",
    "PROMPTS",
    "ROOT",
    "SCOPE_SLACK",
    "TIMEOUT_MARKERS",
    "_apply_diff",
    "_at",
    "_bot_branch",
    "_bundle",
    "_code_repos_env",
    "_comment_app_issue",
    "_commit_trailer",
    "_component_cfg",
    "_e2e_tool",
    "_error_signature",
    "_error_type",
    "_flag_names",
    "_jira_label",
    "_link_source",
    "_llm_summary",
    "_new_test_files",
    "_notify",
    "_oncall",
    "_outside_plan",
    "_pipeline_yaml",
    "_prompt",
    "_python",
    "_ready_pr_allowed",
    "_repo_owner",
    "_repro_cmd",
    "_repro_problem",
    "_reset_to",
    "_revert_non_tests",
    "_run_on_release",
    "_run_test",
    "_sandbox",
    "_source_label",
    "_static_problem",
    "_status",
    "_stop_if_out_of_quota",
    "_test_cmd",
    "_tier_problem",
    "_top_in_app",
    "_with_agent_type",
    "_wrong_value_report",
    "app_comment",
    "apply_diff",
    "auto_triage",
    "bot_branch",
    "call_variants_check",
    "check_prompt",
    "checks",
    "classify",
    "classify_rca",
    "code_repos_env",
    "comment_app_issue",
    "commit_trailer",
    "common",
    "component_cfg",
    "context",
    "context_collector",
    "decide_retry",
    "e2e_tool",
    "error_pattern",
    "error_signature",
    "error_type",
    "evidence_bundle",
    "file_at_release",
    "fix",
    "fix_contract_problem",
    "fixing",
    "flag_names",
    "httpx",
    "ingest",
    "intake",
    "jira_label",
    "known_flag",
    "link_source",
    "llm_summary",
    "load_prompt",
    "mitigate",
    "mitigation",
    "new_test_files",
    "notify",
    "oncall_for",
    "outside_plan",
    "pipeline_yaml",
    "post_merge_watch",
    "pr",
    "pr_and_notify",
    "prove_culprit",
    "python_for",
    "rca_prompt",
    "ready_pr_allowed",
    "repo_owner",
    "repro_cmd",
    "repro_problem",
    "reset_to",
    "revert_non_tests",
    "run_on_release",
    "run_test",
    "run_values",
    "sandbox_for",
    "second_reproduction",
    "ship",
    "ship_gate",
    "skills",
    "source_label",
    "static_problem",
    "stop_if_out_of_quota",
    "test_cmd",
    "testing",
    "tier_problem",
    "top_in_app",
    "triage",
    "validate",
    "validation",
    "with_agent_type",
    "worktree_status",
    "wrong_value_report",
]
