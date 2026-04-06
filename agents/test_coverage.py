import json
import os
import re
from openai import OpenAI
from models import AgentResult, Finding, PRContext, Severity
from telemetry import agent_span

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

SYSTEM_PROMPT = """You are a test coverage reviewer. Return ONLY a JSON array of findings, no other text.

Each finding must have: severity, file_path, line_number, title, body, suggestion.

Flag these:
- New public function with no corresponding test added (HIGH)
- New class with no test (HIGH)
- Test missing edge cases like None, empty input, boundary values (MEDIUM)
- Test function with no assertion (CRITICAL)"""


def _count_new_test_functions(diff: str) -> int:
    return len(re.findall(r"^\+\s*def test_", diff, re.MULTILINE))


def _count_new_public_functions(diff: str) -> int:
    all_new = re.findall(r"^\+\s*def ([a-zA-Z][a-zA-Z0-9_]*)\(", diff, re.MULTILINE)
    return sum(
        1
        for name in all_new
        if not name.startswith("test_") and not name.startswith("_")
    )


def run(pr: PRContext) -> AgentResult:
    test_functions = _count_new_test_functions(pr.pr_diff)
    public_functions = _count_new_public_functions(pr.pr_diff)

    hint = f"{test_functions} new test(s) for {public_functions} new public function(s)"

    user_msg = (
        f"PR: {pr.pr_title}\n\n" f"HINT:\n{hint}\n\n" f"DIFF:\n{pr.pr_diff[:14_000]}"
    )

    with agent_span("test_coverage", pr.pr_number) as span:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        usage = response.usage
        span.set_attribute("prompt_tokens", usage.prompt_tokens)
        span.set_attribute("completion_tokens", usage.completion_tokens)

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("findings", [])
    except Exception:
        items = []

    findings = [
        Finding(
            agent_name="test_coverage",
            severity=Severity(item.get("severity", "low")),
            file_path=item.get("file_path", "unknown"),
            line_number=item.get("line_number"),
            title=item.get("title", ""),
            body=item.get("body", ""),
            suggestion=item.get("suggestion"),
        )
        for item in items
    ]

    return AgentResult(
        agent_name="test_coverage",
        findings=findings,
        summary=f"{len(findings)} gap(s) found. {test_functions} new test(s) for {public_functions} new public function(s).",
        prompt_tokens_used=usage.prompt_tokens,
        completion_tokens_used=usage.completion_tokens,
    )
