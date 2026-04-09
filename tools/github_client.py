import os
import urllib.request
from github import Github
from models import PRContext


# takes repo name and the PR number and returns a PRContext object.
# we fetch the diff via the diff_url to get the full diff since the GitHub API truncates it.
def get_pr_context(repo_full_name: str, pr_number: int) -> PRContext:
    g = Github(os.environ["GITHUB_TOKEN"])
    repo = g.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)

    req = urllib.request.Request(
        pr.diff_url,
        headers={
            "Authorization": f"token {os.environ['GITHUB_TOKEN']}"
        },  # get the diff directly from diff_url to avoid truncation
    )

    with urllib.request.urlopen(req) as resp:
        diff = resp.read().decode(
            "utf-8", errors="replace"
        )  # decode with replacement to avoid issues with non-utf-8 characters in diffs

    changed_files = [f.filename for f in pr.get_files()]

    return PRContext(
        repo_name=repo_full_name,
        pr_number=pr_number,
        pr_title=pr.title,
        pr_body=pr.body,
        pr_diff=diff,
        base_branch=pr.base.ref,
        head_branch=pr.head.ref,
        addition_count=pr.additions,
        deletion_count=pr.deletions,
        changed_files=changed_files,
    )
