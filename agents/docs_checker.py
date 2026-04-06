import re
import json
import os
from openai import OpenAI
from models import AgentResult, Finding, PRContext, Severity
from telemetry import agent_span


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

SYSTEM_PROMPT = """You are a docs checker. Return ONLY a JSON array of findings, no other text.

Each finding must have: severity, file_path, line_number, title, body, suggestion.

Flag these:
- New public function with no docstring (MEDIUM)
- New class with no docstring (MEDIUM)
- Docstring present but missing Args/Returns sections (LOW)
- CHANGELOG not updated despite API changes (HIGH) - only flag if _has_api_changes is True and _changelog_updated is False.
- Inline TODO or FIXME in new code (LOW)"""


def _changelog_updated(diff: str) -> bool:
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            fileName = line[6:].lower()
            if any(
                kw in fileName for kw in ["changelog", "changes", "release", "history"]
            ):
                return True
    return False


def _has_api_changes(diff: str) -> bool:
    all_public = re.findall(
        r"^\+\s*def ([a-zA-Z][a-zA-Z0-9_]*)\(", diff, re.MULTILINE
    ) or re.findall(r"^-\s*def ([a-zA-Z][a-zA-Z0-9_]*)\(", diff, re.MULTILINE)
    return bool(all_public)


def run(pr: PRContext) -> AgentResult:
    api_changes = _has_api_changes(pr.pr_diff)
    changelog_updated = _changelog_updated(pr.pr_diff)

    hint = (
        f"API changes detected: {api_changes}. Changelog updated: {changelog_updated}."
    )

    user_msg = (
        f"PR: {pr.pr_title}\n\n" f"HINT:\n{hint}\n\n" f"DIFF:\n{pr.pr_diff[:14_000]}"
    )

    with agent_span("docs_checker", pr.pr_number) as span:
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
            agent_name="docs_checker",
            severity=Severity(item.get("severity", "low").lower()),
            file_path=item.get("file_path", "unknown"),
            line_number=item.get("line_number"),
            title=item.get("title", ""),
            body=item.get("body", ""),
            suggestion=item.get("suggestion"),
        )
        for item in items
    ]

    return AgentResult(
        agent_name="docs_checker",
        findings=findings,
        summary=f"{len(findings)} doc issue(s) found. API changes: {api_changes}. Changelog updated: {changelog_updated}.",
        prompt_tokens_used=usage.prompt_tokens,
        completion_tokens_used=usage.completion_tokens,
    )
