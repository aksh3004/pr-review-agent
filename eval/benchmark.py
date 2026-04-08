import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()
from github import Github, Auth
from tools.github_client import get_pr_context
import json, os, re, time
import orchestrator


def _fetch_benchmark_prs(repo_full_name: str, count: int) -> list[int]:
    g = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    repo = g.get_repo(repo_full_name)
    total_prs = repo.get_pulls(state="closed", sort="updated", direction="desc")
    pr_numbers = []
    for pr in total_prs:
        if len(pr_numbers) >= count:
            break
        if pr.merged and len(list(pr.get_review_comments())) >= 2:
            pr_numbers.append(pr.number)
    return pr_numbers


def _finding_overlaps_comment(
    finding, comment_body, comment_file, comment_line
) -> bool:
    if finding.file_path and comment_file:
        if not (
            finding.file_path.endswith(comment_file)
            or comment_file.endswith(finding.file_path)
        ):
            return False

    if finding.line_number and comment_line:
        if abs(finding.line_number - comment_line) <= 5:
            return True

    stop_words = {"the", "a", "an", "is", "in", "it", "of", "to", "and", "or", "not"}

    def tokenize(text):
        words = re.findall(r"[a-z][a-z0-9]{2,}", text.lower())
        return {w for w in words if w not in stop_words}

    finding_tokens = tokenize(f"{finding.title} {finding.body}")
    comment_tokens = tokenize(comment_body)
    return len(finding_tokens & comment_tokens) >= 2


def run_benchmark(repo_full_name, pr_numbers) -> dict:
    g = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    repo = g.get_repo(repo_full_name)

    results = {}
    total_overlap = 0
    total_agent_findings = 0
    total_human_comments = 0

    for pr_number in pr_numbers:
        try:
            print(f" Running PR #{pr_number}...")
            pr = get_pr_context(repo_full_name, pr_number)
            orchestrator_result = orchestrator.run(pr, skip_hitl=True)
            human_comments = repo.get_pull(pr_number).get_review_comments()

            total_agent_findings += len(orchestrator_result.all_findings)
            total_human_comments += len(list(human_comments))

            for finding in orchestrator_result.all_findings:
                for comment in human_comments:
                    if _finding_overlaps_comment(
                        finding, comment.body, comment.path, comment.position
                    ):
                        total_overlap += 1
                        break

            precision = (
                total_overlap / total_agent_findings if total_agent_findings else 0
            )
        except Exception as e:
            print(f"Skipping PR # {pr_number}: {e}")
            continue
        time.sleep(3)

    results = {
        "repo": repo_full_name,
        "total_prs": len(pr_numbers),
        "total_agent_findings": total_agent_findings,
        "total_human_comments": total_human_comments,
        "total_overlap": total_overlap,
        "precision": round(precision, 3),
    }

    return results


def main():
    repo_full_name = "psf/requests"
    count = 15
    print(f"Fetching {count} benchmark merged PRs from {repo_full_name}...")
    pr_numbers = _fetch_benchmark_prs(repo_full_name, count)
    print(f"Found PRs: {len(pr_numbers)} PRs: Running benchmark...")
    results = run_benchmark(repo_full_name, pr_numbers)
    print("\n--- Benchmark Results ---")
    print(f"PRs evaluated:       {results['total_prs']}")
    print(f"Agent findings:      {results['total_agent_findings']}")
    print(f"Human comments:      {results['total_human_comments']}")
    print(f"Overlapping:         {results['total_overlap']}")
    print(f"Precision:           {results['precision']}")
    out_path = Path("results/benchmark_results.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
