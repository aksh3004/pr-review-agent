import ast, json, os
from openai import OpenAI
from models import AgentResult, Finding, PRContext, Severity
from telemetry import agent_span


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

# temperature = 0 keeps the findings deterministic and avoid the model having hallucinations on repeated runs of the same PR.
SYSTEM_PROMPT = """You are a code quality reviewer. Return only JSON array of findings, no other text.

Each finding must have severity, file_path, line_number, title, body, suggestion.
Focus on functions over 40 lines, complexity, bare excepts, magic numbers, missing type hints on public functions.
Do not flag style preferences like quote style or indentation."""


# pull out only modified Python files from the diff and ignore the deleted files since there is nothing to review.
def _extract_python_files(diff: str) -> dict[str, str]:
    files = {}
    current_file = None

    for line in diff.splitlines():
        if line.startswith("+++ b/") and line.endswith(".py"):
            current_file = line[6:]
            files[current_file] = []
        elif current_file and line.startswith("+") and not line.startswith("+++"):
            files[current_file].append(line[1:])

    return {path: "\n".join(lines) for path, lines in files.items() if lines}


# runs local AST checks to catch obvious issues before calling the API.
# Helps to give the model precise line numbers to work with.
def _run_ast_checks(source: str, file_path: str) -> list[str]:
    notes = []
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.end_lineno - node.lineno > 40:
                    notes.append(
                        f"{file_path}:{node.lineno} function `{node.name}` is too long"
                    )
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                notes.append(f"{file_path}:{node.lineno} bare except clause")
    except SyntaxError:
        # if diff contains errors, then skip instead of crashing the agent
        return [f"{file_path}: could not parse"]
    return notes


def run(pr: PRContext) -> AgentResult:
    py_files = _extract_python_files(pr.pr_diff)
    ast_notes = []
    for path, source in py_files.items():
        ast_notes.extend(_run_ast_checks(source, path))

    ast_context = "\n".join(ast_notes) if ast_notes else "No issues pre-detected."

    # trim the diff by providing a limit of 12k characters, so that we stay within limits for large PRs.
    diff_snippet = pr.pr_diff[:12_000]
    user_msg = (
        f"PR: {pr.pr_title}\n\nAST NOTES:\n{ast_context}\n\nDIFF:\n{diff_snippet}"
    )

    with agent_span("code_quality", pr.pr_number) as span:
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
            agent_name="code_quality",
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
        agent_name="code_quality",
        findings=findings,
        summary=f"{len(findings)} issue(s) found across {len(py_files)} Python file(s).",
        prompt_tokens_used=usage.prompt_tokens,
        completion_tokens_used=usage.completion_tokens,
    )
