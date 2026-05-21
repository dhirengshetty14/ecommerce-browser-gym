"""Trajectory store query tool — the sellable "slice by failure mode" layer.

This is differentiator #1 made tangible. Every trajectory the gym
produces carries a universal `agent_failure_class` label (see
FAILURE_TAXONOMY.md). This tool turns a directory of trajectory JSONL
files into a queryable catalogue: a buyer (or a training pipeline) can
ask for exactly the slice they need.

USAGE
-----
    # Show the failure-mode distribution across a trajectory directory
    python -m scripts.query_trajectories --catalogue --dir trajectories

    # Slice: every trajectory where the agent picked a distractor product
    python -m scripts.query_trajectories --failure picked_distractor_product

    # Slice: failed C4 episodes only
    python -m scripts.query_trajectories --task C4/mega_checkout --failed

    # Slice: successful episodes scoring exactly 1.0, any task
    python -m scripts.query_trajectories --succeeded

    # Slice by agent + score band
    python -m scripts.query_trajectories --agent llm --min-score 0.4 --max-score 0.9

    # Emit matching file paths only (pipe into a packager / tar)
    python -m scripts.query_trajectories --failure budget_exceeded --paths-only

OUTPUT
------
By default prints a table of matches (task, agent, score, success,
failure_class, steps, path). With --catalogue, prints the failure-mode
histogram instead. With --paths-only, prints just the JSONL paths so the
result can be piped to a packaging step.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class TrajMeta:
    path: Path
    task_id: str
    agent_name: str
    score: float
    success: bool
    failure_class: Optional[str]
    n_steps: int
    seed: int


def _load_meta(path: Path) -> Optional[TrajMeta]:
    """Load just the metadata we filter on. Skips files that aren't
    trajectory JSONLs (e.g. _scorecard.json, _summary.json)."""
    if path.name.startswith("_"):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if "verifier_result" not in data or "task_id" not in data:
        return None
    v = data.get("verifier_result", {})
    return TrajMeta(
        path=path,
        task_id=data.get("task_id", "?"),
        agent_name=data.get("agent_name", "?"),
        score=float(v.get("score", 0.0)),
        success=bool(v.get("success", False)),
        failure_class=data.get("agent_failure_class"),
        n_steps=len(data.get("steps", [])),
        seed=int(data.get("seed", 0)),
    )


def _scan(root: Path) -> list[TrajMeta]:
    metas: list[TrajMeta] = []
    for p in root.rglob("*.jsonl"):
        m = _load_meta(p)
        if m is not None:
            metas.append(m)
    return metas


def _matches(m: TrajMeta, args) -> bool:
    if args.failure is not None and m.failure_class != args.failure:
        return False
    if args.task is not None and m.task_id != args.task:
        return False
    if args.agent is not None and args.agent not in m.agent_name:
        return False
    if args.failed and m.success:
        return False
    if args.succeeded and not m.success:
        return False
    if args.min_score is not None and m.score < args.min_score:
        return False
    if args.max_score is not None and m.score > args.max_score:
        return False
    return True


def _print_catalogue(metas: list[TrajMeta]) -> None:
    total = len(metas)
    succeeded = sum(1 for m in metas if m.success)
    failed = total - succeeded
    print(f"\nTrajectory store catalogue - {total} trajectories")
    print(f"  succeeded: {succeeded}    failed: {failed}\n")

    if failed:
        print("Failure-mode distribution (failed episodes):")
        fail_hist = Counter(m.failure_class or "(unlabeled)"
                            for m in metas if not m.success)
        width = max((len(k) for k in fail_hist), default=10)
        for label, n in fail_hist.most_common():
            bar = "#" * n
            print(f"  {label:<{width}}  {n:>3}  {bar}")
        print()

    print("By task:")
    task_hist = Counter(m.task_id for m in metas)
    for task, n in sorted(task_hist.items()):
        succ = sum(1 for m in metas if m.task_id == task and m.success)
        print(f"  {task:<32} {n:>3} traj  ({succ} success / {n - succ} fail)")
    print()

    print("By agent:")
    agent_hist = Counter(m.agent_name for m in metas)
    for agent, n in sorted(agent_hist.items()):
        print(f"  {agent:<40} {n:>3}")
    print()


def _print_matches(matches: list[TrajMeta], paths_only: bool) -> None:
    if paths_only:
        for m in matches:
            print(m.path)
        return
    if not matches:
        print("No trajectories matched the query.")
        return
    print(f"\n{len(matches)} matching trajectories:\n")
    print(f"{'task':<28} {'agent':<22} {'score':>6} {'ok':>4} "
          f"{'steps':>6}  {'failure_class':<28} path")
    print("-" * 130)
    for m in sorted(matches, key=lambda x: (x.task_id, -x.score)):
        print(f"{m.task_id:<28} {m.agent_name[:22]:<22} {m.score:>6.2f} "
              f"{('Y' if m.success else 'N'):>4} {m.n_steps:>6}  "
              f"{(m.failure_class or '-'):<28} {m.path}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="trajectories",
                    help="Root directory to scan (recursively) for *.jsonl")
    ap.add_argument("--catalogue", action="store_true",
                    help="Print the failure-mode + task + agent distribution.")
    ap.add_argument("--failure", default=None,
                    help="Filter to a specific agent_failure_class label.")
    ap.add_argument("--task", default=None,
                    help="Filter to a specific task_id (e.g. C4/mega_checkout).")
    ap.add_argument("--agent", default=None,
                    help="Substring filter on agent_name (e.g. 'llm', 'pixel').")
    ap.add_argument("--failed", action="store_true",
                    help="Only failed episodes.")
    ap.add_argument("--succeeded", action="store_true",
                    help="Only successful episodes.")
    ap.add_argument("--min-score", type=float, default=None)
    ap.add_argument("--max-score", type=float, default=None)
    ap.add_argument("--paths-only", action="store_true",
                    help="Print only the matching JSONL paths (for piping).")
    args = ap.parse_args()

    root = Path(args.dir)
    if not root.exists():
        print(f"ERROR: directory not found: {root}", file=sys.stderr)
        sys.exit(2)

    metas = _scan(root)
    if not metas:
        print(f"No trajectory JSONLs found under {root}")
        return

    if args.catalogue:
        _print_catalogue(metas)
        return

    matches = [m for m in metas if _matches(m, args)]
    _print_matches(matches, args.paths_only)


if __name__ == "__main__":
    main()
