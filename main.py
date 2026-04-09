from dotenv import load_dotenv

load_dotenv()

from telemetry import init_telemetry
from tools.github_client import get_pr_context
from orchestrator import run as orchestrator_run
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=str, required=True)
    parser.add_argument("--pr", type=int, required=True)
    # optional argument dry-run lets you see full pipeline results without posting to GitHub (for testing)
    parser.add_argument("--dry-run", action="store_true", required=False)
    args = parser.parse_args()

    pr = get_pr_context(args.repo, args.pr)
    result = orchestrator_run(pr)

    if result.approved and not args.dry_run:
        print("Would post to GitHub here")
    elif result.approved and args.dry_run:
        print("[dry-run] Approved but not posting to GitHub")

    print(f"\nTotal latency: {result.latency}ms")


if __name__ == "__main__":
    init_telemetry()
    main()
