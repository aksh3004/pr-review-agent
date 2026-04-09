# These are the data classes that flow through the entire pipeline.
# Every agent reads PRContext as input and writes AgentResult as output.

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# str mixin means Severity.HIGH serializes to "high" automatically,
# which matters when we write results to JSON in the benchmark and eval code.
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# One issue from one agent, body is posted verbatim to GitHub,
# so agents should write it accordingly.
# suggestion is optional and is a code fix if the agent can offer one
@dataclass
class Finding:
    agent_name: str
    severity: Severity
    file_path: str
    title: str
    body: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


# Everything the orchestrator passes to each agent.
# Built once from GitHub API and passed unchanged, so agents should not mutate it.
@dataclass
class PRContext:
    repo_name: str
    pr_number: int
    pr_title: str
    pr_body: str
    pr_diff: str
    base_branch: str
    head_branch: str
    addition_count: int
    deletion_count: int
    changed_files: list[str] = field(default_factory=list)


# What each agent returns after analyzing the PR.
# findings is empty list, so the orchestrator can always iterate it safely even if the agent errored.
@dataclass
class AgentResult:
    agent_name: str
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    latency: float = 0.0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    error: Optional[str] = None


# The final result of the entire PR review process, after all agents finish.
# approved defaults as false, and only set to true if the human explicitly approves in the HITL step.
@dataclass
class SynthesisResult:
    pr_number: int
    repo_name: str
    agent_results: list[AgentResult]
    all_findings: list[Finding]
    summary: str
    latency: float = 0.0
    approved: bool = False
    human_edit_count: int = 0
