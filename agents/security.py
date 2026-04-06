import subprocess
import tempfile
import ast, json, os
from openai import OpenAI
from models import AgentResult, Finding, PRContext, Severity
from telemetry import agent_span


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

SYSTEM_PROMPT = """Return ONLY a JSON array where each item has: severity, file_path, line_number, title, body, suggestion. No other text, no markdown, just the JSON array."""


def _extract_all_files(diff: str) -> dict[str, str]:
    files = {}
    current_file = None

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            files[current_file] = []
        elif current_file and line.startswith("+") and not line.startswith("+++"):
            files[current_file].append(line[1:])

    return {path: "\n".join(lines) for path, lines in files.items() if lines}


def _run_bandit(py_files: dict[str, str]) -> str:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for path, source in py_files.items():
                safe_name = path.replace("/", "__").replace("\\", "__")
                full_path = os.path.join(tmp, safe_name)
                with open(full_path, "w", encoding="utf-8", errors="replace") as f:
                    f.write(source)

            result = subprocess.run(
                ["bandit", "-r", tmp, "-f", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            return result.stdout or "{}"

    except FileNotFoundError:
        return '{"error": "bandit not installed"}'
    except Exception as e:
        return f'{{"error": "{str(e)}"}}'


def run(pr: PRContext) -> AgentResult:
    all_files = _extract_all_files(pr.pr_diff)
    py_files = {k: v for k, v in all_files.items() if k.endswith(".py")}

    bandit_output = _run_bandit(py_files)

    user_msg = (
        f"PR: {pr.pr_title}\n\n"
        f"BANDIT OUTPUT:\n{bandit_output[:4000]}\n\n"
        f"DIFF:\n{pr.pr_diff[:14_000]}"
    )

    with agent_span("security", pr.pr_number) as span:
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
            agent_name="security",
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
        agent_name="security",
        findings=findings,
        summary=f"{len(findings)} issue(s) found across {len(py_files)} Python file(s).",
        prompt_tokens_used=usage.prompt_tokens,
        completion_tokens_used=usage.completion_tokens,
    )
