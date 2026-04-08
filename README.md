# PR Review Agent

## Introduction
Given a PR, this multi-agent pipeline gives you automated feedback on code quality,
security, test coverage, and documentation. Each agent works concurrently on a specific
area, and results are combined into an executive summary presented via a human-in-the-loop
approval gate before anything is posted to GitHub. Built with GPT-4o, OpenTelemetry for
observability, and designed to migrate cleanly to Microsoft Agent Framework.

## Architecture
```
GitHub PR
    │
    ▼
Orchestrator (ThreadPoolExecutor — all 4 agents run concurrently)
├── Code Quality Agent   AST checks + GPT-4o
├── Security Agent       Bandit + GPT-4o
├── Test Coverage Agent  GPT-4o
└── Docs Checker Agent   GPT-4o
    │
    ▼
Synthesis + HITL Gate  ← human reviews and approves here
    │
    ▼
GitHub Review Comments (inline, per finding)
```

## Benchmark Results

Evaluated against 15 merged PRs from `psf/requests` with existing human review comments.

|       Metric          | Result    |
|-----------------------|-----------|
| PRs evaluated         |   15      |
| Agent findings        |   61      |
| Human comments        |   57      |
| Overlapping           |   21      |
| Precision             |   34%     |
| Avg pipeline latency  |   ~5.5s   |

## Setup

```bash
git clone https://github.com/aksh3004/pr-review-agent
cd pr-review-agent
pip install -r requirements.txt
cp .env.example .env
# fill in OPENAI_API_KEY and GITHUB_TOKEN in .env
python main.py --repo psf/requests --pr 6710 --dry-run
```

## Running the Benchmark

```bash
python eval/benchmark.py
```

Results are saved to `results/benchmark_results.json`.

## Migration to Microsoft Agent Framework

The `ThreadPoolExecutor` fan-out in `orchestrator.py` maps directly to the Agent Framework Workflows.
The OpenTelemetry spans flow into Azure Monitor with no code changes.
Just swap `ConsoleSpanExporter` for the Azure Monitor exporter.
