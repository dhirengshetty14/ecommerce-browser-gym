"""pass^k consistency evaluation — the τ-bench-inspired reliability metric.

WHY pass^k:
    pass@1 (single-run success) is the dominant metric in agent
    benchmarks, but it dramatically OVERSTATES production readiness.
    An agent that succeeds 50% of the time is unusable in real
    deployment — customers don't accept "maybe it'll work today."

    pass^k is the probability the SAME agent succeeds k times in a row
    on the SAME task across k independent seeds. Sierra showed in
    τ-bench that GPT-4 drops from ~50% pass@1 to ~6% pass^8 on retail
    tasks. That's the reality your gym should surface.

USAGE:
    # All 9 tasks, k=5 (Claude default)
    python -m eval.pass_k --tasks all --k 5

    # Just C-track checkout tasks with k=8
    python -m eval.pass_k --tasks C1/promo_partial,C2/split_shipping_gift,C3/subscription_loyalty --k 8

    # Specify model
    python -m eval.pass_k --model claude-sonnet-4-5 --k 5

OUTPUT:
    trajectories/pass_k/<task>__pass_k.json
        per-task: pass@1, pass^k, mean_score, consistency_rate
    trajectories/pass_k/_summary.json
        aggregate across all tasks
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from agents.oracle_agent import SOLVERS as ORACLE_SOLVERS
from harness.runner import (
    BrowserCtx, Trajectory, open_browser, reset_gym, save_trajectory,
)


ALL_TASKS = list(ORACLE_SOLVERS.keys())


# --------------------------------------------------------------------------- #
# One-episode runner — slim copy of eval/run.py's _run_one so we can
# iterate quickly without pulling its full CLI surface
# --------------------------------------------------------------------------- #

async def _run_one(*, agent_kind: str, task_id: str, seed: int,
                   server_url: str, headless: bool,
                   out_traj_dir: Path, out_screens_dir: Path,
                   llm_model: str | None) -> Trajectory:
    await reset_gym(server_url, task_id, seed)
    pw, browser, ctx_browser, page = await open_browser(
        server_url=server_url, headless=headless,
        record_video=False,
        videos_dir=Path("videos") / agent_kind,
    )
    episode_id = uuid.uuid4().hex[:8]
    shots_dir = out_screens_dir / f"{task_id.replace('/', '_')}__{seed}__{episode_id}"
    shots_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as c:
        r = (await c.get(f"{server_url}/_harness/snapshot")).json()
    traj = Trajectory(
        episode_id=episode_id, task_id=task_id, seed=seed,
        agent_name=f"oracle" if agent_kind == "oracle"
                   else f"llm[{llm_model or 'default'}]",
        started_at=time.time(),
        task_brief=r.get("task_brief", ""),
        task_difficulty=r.get("task_difficulty", ""),
        task_category=r.get("task_category", ""),
    )
    bctx = BrowserCtx(
        page=page, server_url=server_url, trajectory=traj,
        screenshot_dir=shots_dir,
    )
    traj.initial_url = page.url
    traj.initial_snapshot = r
    try:
        if agent_kind == "oracle":
            await ORACLE_SOLVERS[task_id](bctx)
        else:
            from agents.llm_agent import LLMBrowserAgent
            agent = LLMBrowserAgent(model=llm_model)
            await agent.run(bctx, task_brief=r.get("task_brief", ""))
    except Exception as e:
        traj.error = f"{type(e).__name__}: {e}"

    traj.final_url = page.url
    async with httpx.AsyncClient() as c:
        traj.final_snapshot = (await c.get(
            f"{server_url}/_harness/snapshot",
        )).json()
        traj.verifier_result = (await c.post(
            f"{server_url}/_harness/verify",
            json={"url": page.url, "step": len(traj.steps)},
        )).json()
    traj.finished_at = time.time()

    await ctx_browser.close()
    await browser.close()
    await pw.stop()
    save_trajectory(traj, out_traj_dir)
    return traj


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

def _per_task_summary(task_id: str, trajectories: list[Trajectory]) -> dict:
    n = len(trajectories)
    successes = [bool(t.verifier_result.get("success", False)) for t in trajectories]
    scores = [float(t.verifier_result.get("score", 0.0)) for t in trajectories]
    failures = [t.verifier_result.get("primary_failure_category")
                for t in trajectories
                if not t.verifier_result.get("success", False)]
    failure_counts = Counter(f for f in failures if f)

    return {
        "task_id": task_id,
        "n_runs": n,
        # The two τ-bench-style metrics:
        "pass_at_1": int(successes[0]) if successes else 0,
        "pass_k": 1 if all(successes) else 0,
        # Richer info:
        "consistency_rate": sum(successes) / n if n else 0.0,
        "mean_score":  round(statistics.mean(scores), 4) if scores else 0.0,
        "score_std":   round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
        "min_score":   round(min(scores), 4) if scores else 0.0,
        "max_score":   round(max(scores), 4) if scores else 0.0,
        "individual_scores":  [round(s, 4) for s in scores],
        "individual_success": successes,
        "failure_breakdown":  dict(failure_counts),
    }


def _print_scorecard(by_task: list[dict], k: int) -> None:
    print()
    print("=" * 110)
    print(f"{'task':<32} {'runs':>5} {'pass@1':>7} {f'pass^{k}':>8} "
          f"{'mean':>7} {'std':>7} {'min':>6} {'max':>6} {'consistency':>12}")
    print("-" * 110)
    for row in by_task:
        print(f"{row['task_id']:<32} {row['n_runs']:>5} "
              f"{row['pass_at_1']:>7} {row['pass_k']:>8} "
              f"{row['mean_score']:>7.2f} {row['score_std']:>7.2f} "
              f"{row['min_score']:>6.2f} {row['max_score']:>6.2f} "
              f"{row['consistency_rate']*100:>10.1f}%")
    print("-" * 110)
    overall_p1 = sum(r["pass_at_1"] for r in by_task) / max(len(by_task), 1)
    overall_pk = sum(r["pass_k"] for r in by_task) / max(len(by_task), 1)
    overall_mean = sum(r["mean_score"] for r in by_task) / max(len(by_task), 1)
    print(f"{'OVERALL':<32} {'':>5} {overall_p1*100:>6.1f}% {overall_pk*100:>7.1f}% "
          f"{overall_mean:>7.2f}")
    print("=" * 110)
    print()
    print("Interpretation:")
    print(f"  pass@1   = success on seed 0 alone (the headline benchmark)")
    print(f"  pass^{k}   = success on ALL {k} seeds (production-deployment metric)")
    print(f"  the gap between them = reliability tax")
    print()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", choices=["oracle", "llm"], default="llm")
    ap.add_argument("--tasks", default="all",
                    help="comma-separated task ids, or 'all'")
    ap.add_argument("--k", type=int, default=5,
                    help="number of runs per task (pass^k metric)")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--headless", action="store_true", default=True,
                    help="Run headless (default). Pass --no-headless to see browser.")
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--model", default=None,
                    help="LLM model id (Anthropic). Default: agent default.")
    ap.add_argument("--out-dir", default="trajectories/pass_k")
    args = ap.parse_args()

    tasks = ALL_TASKS if args.tasks == "all" else args.tasks.split(",")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    screens_dir = Path("screenshots/pass_k")
    screens_dir.mkdir(parents=True, exist_ok=True)

    # Reachability check
    try:
        httpx.get(f"{args.server}/_harness/tasks", timeout=3.0)
    except Exception as e:
        print(f"ERROR: cannot reach gym at {args.server}: {e}\n"
              "Start the server first: uvicorn server.main:app --reload",
              file=sys.stderr)
        sys.exit(2)

    by_task = []
    started = time.time()
    for task_id in tasks:
        print(f"\n>>> {args.agent} on {task_id}  (k={args.k})")
        trajs = []
        for seed in range(args.k):
            traj = asyncio.run(_run_one(
                agent_kind=args.agent, task_id=task_id, seed=seed,
                server_url=args.server,
                headless=args.headless,
                out_traj_dir=out_dir,
                out_screens_dir=screens_dir,
                llm_model=args.model,
            ))
            score = traj.verifier_result.get("score", 0.0)
            success = traj.verifier_result.get("success", False)
            fail = traj.verifier_result.get("primary_failure_category") or "-"
            print(f"    seed={seed}: score={score:.2f}  success={success}  failure={fail}")
            trajs.append(traj)

        row = _per_task_summary(task_id, trajs)
        by_task.append(row)
        (out_dir / f"{task_id.replace('/', '_')}__pass_k.json").write_text(
            json.dumps(row, indent=2), encoding="utf-8",
        )

    _print_scorecard(by_task, args.k)

    # Aggregate failure modes across all tasks
    global_failures: Counter = Counter()
    for row in by_task:
        global_failures.update(row["failure_breakdown"])

    summary = {
        "agent": args.agent, "model": args.model,
        "k": args.k,
        "tasks": [r["task_id"] for r in by_task],
        "by_task": by_task,
        "overall": {
            "pass_at_1_rate": sum(r["pass_at_1"] for r in by_task) / max(len(by_task), 1),
            "pass_k_rate":    sum(r["pass_k"]    for r in by_task) / max(len(by_task), 1),
            "mean_score":     sum(r["mean_score"] for r in by_task) / max(len(by_task), 1),
        },
        "failure_mode_taxonomy": dict(global_failures.most_common()),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (out_dir / "_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )

    print(f"Failure modes across {sum(global_failures.values())} failures:")
    for cat, n in global_failures.most_common():
        print(f"  {n:>3}× {cat}")
    print(f"\nSummary: {out_dir}/_summary.json")


if __name__ == "__main__":
    main()
