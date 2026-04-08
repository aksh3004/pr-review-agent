import os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from models import PRContext, AgentResult, Finding, Severity, SynthesisResult
from telemetry import get_tracer
import agents.code_quality as code_quality
import agents.docs_checker as docs_checker
import agents.security as security
import agents.test_coverage as test_coverage
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel

console = Console()


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _run_agent_safely(agent_module, pr: PRContext) -> AgentResult:
    try:
        return agent_module.run(pr)
    except Exception as e:
        return AgentResult(
            agent_name=getattr(agent_module, "__name__", "unknown").split(".")[-1],
            error=str(e),
        )


def _synthesize_summary(pr: PRContext, results: list[AgentResult]) -> str:
    summaries = "\n".join(
        f"- {r.agent_name}: {r.summary or r.error or 'no output'}" for r in results
    )
    all_findings = "\n".join(
        f"[{f.severity}] {f.agent_name}: {f.title}" for r in results for f in r.findings
    )

    user_msg = f"PR: {pr.pr_title}\n\nAGENT SUMMARIES:\n{summaries}\n\nFINDINGS:\n{all_findings or 'None'}"
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "Write a 3-5 sentence executive summary of this PR review. State the overall risk level, the most important finding, and whether the PR is ready to merge. Be direct and concise.",
            },
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=300,
    )

    return response.choices[0].message.content.strip()


def _hitl_gate(synthesis: SynthesisResult) -> bool:
    table = Table(show_header=True, box=box.ROUNDED)
    table.add_column("Severity", width=10)
    table.add_column("Agent", width=14)
    table.add_column("Title", width=30)
    table.add_column("Line", width=6)
    table.add_column("File", width=40)
    sorted_findings = sorted(
        synthesis.all_findings, key=lambda f: SEVERITY_ORDER.get(f.severity.value, 9)
    )

    for f in sorted_findings:
        table.add_row(
            f.severity.value.upper(),
            f.agent_name,
            f.title[:40],
            str(f.line_number or "-"),
            f.file_path[-30:],
        )

    console.print(table)

    console.print(Panel(synthesis.summary, title="Executive Summary", box=box.ROUNDED))

    while True:
        user_choice = console.input("Approve and post to github [y/n] >>> ")
        if user_choice.lower() == "y":
            return True
        if user_choice.lower() == "n":
            return False
        console.print("[dim]Please enter y or n[/dim]")


def run(pr: PRContext, skip_hitl=False) -> SynthesisResult:
    agents = [
        (code_quality, "code_quality"),
        (security, "security"),
        (test_coverage, "test_coverage"),
        (docs_checker, "docs_checker"),
    ]

    results = []
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_run_agent_safely, mod, pr): name for mod, name in agents
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    all_findings = [f for r in results for f in r.findings]
    summary = _synthesize_summary(pr, results)
    total_ms = int((time.perf_counter() - t_start) * 1000)

    synthesis = SynthesisResult(
        pr_number=pr.pr_number,
        repo_name=pr.repo_name,
        agent_results=results,
        all_findings=all_findings,
        summary=summary,
        latency=total_ms,
    )

    if not skip_hitl:
        approved = _hitl_gate(synthesis)
        synthesis.approved = approved

    return synthesis
