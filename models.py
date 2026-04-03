from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class Finding:
    agent_name: str
    severity: Severity
    file_path: str
    title: str
    body: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None

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

@dataclass
class AgentResult:
    agent_name: str
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    latency: float = 0.0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    error: Optional[str] = None

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