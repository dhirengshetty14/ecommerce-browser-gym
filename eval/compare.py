"""Head-to-head comparison runner: DOM/JSON agent vs Pixel/SoM agent.

Runs the same matrix on both agent variants and emits a side-by-side
summary suitable for PIXEL_VS_JSON.md and any downstream analysis.

Default matrix: all 12 tasks × seeds {0,1,2} × 2 agents = 72 episodes
(plus oracle on the same matrix as a verifier sanity gate).

USAGE:
    # Full default matrix (takes ~2-4 hours, ~$30-50 in API)
    python -m eval.compare

    # Quick: 3 easy tasks, 1 seed
    python -m eval.compare --tasks A1/buy_wireless_mouse,B1/add_address,C1/promo_partial --seeds 0

    # Same model both ways (recommended for fair comparison)
    python -m eval.compare --model claude-sonnet-4-5-20250929

    # Skip oracle (faster — but you lose the verifier sanity check)
    python -m eval.compare --agents llm,pixel

    # Headed runs (you can watch the cursor)
    python -m eval.compare --no-headless

OUTPUT:
    trajectories/comparison/<agent>__<task>__<seed>__<id>.jsonl
    trajectories/comparison/_summary.json
        {
          "agents": [...],
          "tasks": [...],
          "seeds": [...],
          "per_task": {
            "<task_id>": {
              "<agent>": {"mean_score", "success_rate", "pass_k",
                          "mean_steps", "tokens_in_total",
                          "tokens_out_total", "cost_estimate_usd",
                          "primary_failure_categories": {...}}
            }
          },
          "overall": { ... },
          "head_to_head": {     # for the two non-oracle agents
            "<task_id>": {"dom_score", "pixel_score", "delta", "winner"}
          }
        }
    trajectories/comparison/_summary.md  (human-readable table)
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

# Approximate Anthropic Sonnet 4.5 pricing in USD per token. Used only
# for the cost_estimate_usd field — updated by hand as prices change.
_PRICE_IN_PER_TOK = 3.0 / 1_000_000     # $3 / 1M input tokens
_PRICE_OUT_PER_TOK = 15.0 / 1_000_000   # $15 / 1M output tokens


# --------------------------------------------------------------------------- #
# Episode runner — thin copy of eval/run._run_one for clarity
# --------------------------------------------------------------------------- #

async def _run_one(*, agent_kind: str, task_id: str, seed: int,
                   server_url: str, headless: bool,
                   out_traj_dir: Path, llm_model: str | None) -> Trajectory:
    await reset_gym(server_url, task_id, seed)

    pw, browser, ctx_browser, page = await open_browser(
        server_url=server_url, headless=headless,
        record_video=False,
        videos_dir=Path("videos") / "comparison",
    )
    episode_id = uuid.uuid4().hex[:8]
    shots_dir = Path("screenshots/comparison") / agent_kind / \
                f"{task_id.replace('/', '_')}__{seed}__{episode_id}"
    shots_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as c:
        initial = (await c.get(f"{server_url}/_harness/snapshot")).json()

    if agent_kind == "oracle":
        agent_name = "oracle"
    elif agent_kind == "pixel":
        agent_name = f"pixel[{llm_model or 'default'}]"
    else:
        agent_name = f"llm[{llm_model or 'default'}]"

    traj = Trajectory(
        episode_id=episode_id, task_id=task_id, seed=seed,
        agent_name=agent_name,
        started_at=time.time(),
        task_brief=initial.get("task_brief", ""),
        task_difficulty=initial.get("task_difficulty", ""),
        task_category=initial.get("task_category", ""),
        initial_url=page.url,
        initial_snapshot=initial,
    )
    bctx = BrowserCtx(
        page=page, server_url=server_url, trajectory=traj,
        screenshot_dir=shots_dir,
    )

    # Pre-navigate to the gym home page so the agent starts on a
    # rendered page, not about:blank. See eval/run.py for full context.
    try:
        await page.goto(f"{server_url}/", wait_until="load")
        traj.initial_url = page.url
    except Exception as e:
        print(f"[compare] WARNING: failed to pre-load {server_url}/: {e}")

    try:
        if agent_kind == "oracle":
            await ORACLE_SOLVERS[task_id](bctx)
        elif agent_kind == "pixel":
            from agents.pixel_agent import PixelBrowserAgent
            agent = PixelBrowserAgent(model=llm_model)
            await agent.run(bctx, task_brief=initial.get("task_brief", ""))
        else:
            from agents.llm_agent import LLMBrowserAgent
            agent = LLMBrowserAgent(model=llm_model)
            await agent.run(bctx, task_brief=initial.get("task_brief", ""))
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

def _agent_summary(trajectories: list[Trajectory]) -> dict:
    """Aggregate metrics for one agent's worth of trajectories."""
    if not trajectories:
        return {}
    scores = [float(t.verifier_result.get("score", 0.0)) for t in trajectories]
    successes = [bool(t.verifier_result.get("success", False)) for t in trajectories]
    steps = [len(t.steps) for t in trajectories]

    tokens_in = sum(int(s.tokens_in or 0) for t in trajectories for s in t.steps)
    tokens_out = sum(int(s.tokens_out or 0) for t in trajectories for s in t.steps)
    cost_usd = (tokens_in * _PRICE_IN_PER_TOK
                + tokens_out * _PRICE_OUT_PER_TOK)

    fail_cats = Counter(
        t.verifier_result.get("primary_failure_category")
        for t in trajectories
        if not t.verifier_result.get("success", False)
        and t.verifier_result.get("primary_failure_category")
    )

    return {
        "n_episodes":          len(trajectories),
        "mean_score":          round(statistics.mean(scores), 4),
        "score_std":           round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
        "success_rate":        sum(successes) / len(successes),
        "pass_k_consistent":   int(all(successes)),  # 1 if all seeds succeeded
        "mean_steps":          round(statistics.mean(steps), 1),
        "tokens_in_total":     tokens_in,
        "tokens_out_total":    tokens_out,
        "cost_estimate_usd":   round(cost_usd, 4),
        "primary_failure_categories": dict(fail_cats),
        "individual_scores":   [round(s, 3) for s in scores],
        "individual_success":  successes,
    }


def _build_summary(by_agent_task: dict, agents: list[str],
                   tasks: list[str], seeds: list[int]) -> dict:
    """Compose the full _summary.json blob."""
    per_task: dict = {}
    for task in tasks:
        per_task[task] = {}
        for agent in agents:
            trajs = by_agent_task.get((agent, task), [])
            per_task[task][agent] = _agent_summary(trajs)

    overall: dict = {}
    for agent in agents:
        all_trajs = [
            t for (a, _task), ts in by_agent_task.items() if a == agent
            for t in ts
        ]
        overall[agent] = _agent_summary(all_trajs)

    # Head-to-head DOM vs Pixel (only when both ran)
    h2h: dict = {}
    if "llm" in agents and "pixel" in agents:
        for task in tasks:
            dom = per_task[task].get("llm", {})
            px = per_task[task].get("pixel", {})
            if not dom or not px:
                continue
            d, p = dom["mean_score"], px["mean_score"]
            h2h[task] = {
                "dom_score": d,
                "pixel_score": p,
                "delta": round(p - d, 4),
                "winner": "pixel" if p > d else ("dom" if d > p else "tie"),
                "dom_cost_usd": dom["cost_estimate_usd"],
                "pixel_cost_usd": px["cost_estimate_usd"],
                "cost_ratio_pixel_over_dom": round(
                    px["cost_estimate_usd"]
                    / max(dom["cost_estimate_usd"], 1e-9),
                    2,
                ),
            }

    return {
        "agents": agents,
        "tasks": tasks,
        "seeds": seeds,
        "per_task": per_task,
        "overall": overall,
        "head_to_head_dom_vs_pixel": h2h,
    }


def _markdown_summary(summary: dict) -> str:
    """Render a human-readable markdown table from the summary."""
    lines = []
    lines.append("# Pixel vs DOM — Comparison Results")
    lines.append("")
    lines.append(f"- Agents: {', '.join(summary['agents'])}")
    lines.append(f"- Tasks ({len(summary['tasks'])}): {', '.join(summary['tasks'])}")
    lines.append(f"- Seeds: {summary['seeds']}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append("| Agent | Episodes | Success Rate | Mean Score | Mean Steps | Tokens In | Tokens Out | Cost (USD) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for agent, o in summary["overall"].items():
        lines.append(
            f"| {agent} | {o.get('n_episodes', 0)} | "
            f"{o.get('success_rate', 0)*100:.1f}% | "
            f"{o.get('mean_score', 0):.2f} | "
            f"{o.get('mean_steps', 0):.1f} | "
            f"{o.get('tokens_in_total', 0):,} | "
            f"{o.get('tokens_out_total', 0):,} | "
            f"${o.get('cost_estimate_usd', 0):.2f} |"
        )
    lines.append("")
    lines.append("## Per-task scores")
    lines.append("")
    headers = ["Task"] + [a for a in summary["agents"]]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))
    for task in summary["tasks"]:
        row = [task]
        for agent in summary["agents"]:
            stats = summary["per_task"][task].get(agent, {})
            score = stats.get("mean_score", 0.0)
            success = "✓" if stats.get("pass_k_consistent") else "✗"
            row.append(f"{score:.2f} {success}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    if summary.get("head_to_head_dom_vs_pixel"):
        lines.append("## Head-to-head: DOM vs Pixel")
        lines.append("")
        lines.append("| Task | DOM | Pixel | Δ | Winner | Cost ratio (px/dom) |")
        lines.append("|---|---|---|---|---|---|")
        for task, h in summary["head_to_head_dom_vs_pixel"].items():
            lines.append(
                f"| {task} | {h['dom_score']:.2f} | {h['pixel_score']:.2f} | "
                f"{h['delta']:+.2f} | {h['winner']} | "
                f"{h['cost_ratio_pixel_over_dom']}× |"
            )
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--agents", default="oracle,llm,pixel",
        help="Comma-separated agents to run. Default: oracle,llm,pixel. "
             "Use 'llm,pixel' to skip the oracle sanity check.",
    )
    ap.add_argument("--tasks", default="all",
                    help="Comma-separated task ids, or 'all'")
    ap.add_argument("--seeds", default="0,1,2",
                    help="Comma-separated seed list (default 0,1,2)")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--model", default=None,
                    help="LLM model id (Anthropic). Same model used for both "
                         "llm and pixel agents for fair comparison.")
    ap.add_argument("--out-dir", default="trajectories/comparison")
    args = ap.parse_args()

    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    tasks = ALL_TASKS if args.tasks == "all" else [
        t.strip() for t in args.tasks.split(",") if t.strip()
    ]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Reachability check
    try:
        httpx.get(f"{args.server}/_harness/tasks", timeout=3.0)
    except Exception as e:
        print(f"ERROR: cannot reach gym at {args.server}: {e}\n"
              "Start the server first: uvicorn server.main:app --reload",
              file=sys.stderr)
        sys.exit(2)

    print(f"Running {len(agents)} × {len(tasks)} × {len(seeds)} = "
          f"{len(agents) * len(tasks) * len(seeds)} episodes")
    print(f"Agents: {agents}\nTasks: {tasks}\nSeeds: {seeds}\nModel: {args.model or 'default'}")
    print()

    by_agent_task: dict = defaultdict(list)
    started = time.time()
    total = len(agents) * len(tasks) * len(seeds)
    done = 0

    for task in tasks:
        for agent in agents:
            for seed in seeds:
                done += 1
                t0 = time.time()
                print(f"[{done}/{total}] {agent} on {task} seed={seed}", end=" ")
                try:
                    traj = asyncio.run(_run_one(
                        agent_kind=agent, task_id=task, seed=seed,
                        server_url=args.server,
                        headless=args.headless,
                        out_traj_dir=out_dir,
                        llm_model=args.model,
                    ))
                except Exception as e:
                    print(f"\n  RUN FAILED: {type(e).__name__}: {e}")
                    continue
                elapsed = time.time() - t0
                v = traj.verifier_result
                print(f"-> score={v.get('score', 0):.2f} "
                      f"success={v.get('success', False)} "
                      f"steps={len(traj.steps)} "
                      f"failure={v.get('primary_failure_category', '-') or '-'} "
                      f"({elapsed:.1f}s)")
                by_agent_task[(agent, task)].append(traj)

    elapsed_total = time.time() - started

    summary = _build_summary(dict(by_agent_task), agents, tasks, seeds)
    summary["elapsed_seconds"] = round(elapsed_total, 1)

    (out_dir / "_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    (out_dir / "_summary.md").write_text(
        _markdown_summary(summary), encoding="utf-8",
    )

    print()
    print(_markdown_summary(summary))
    print()
    print(f"Wrote: {out_dir}/_summary.json and {out_dir}/_summary.md")
    print(f"Total elapsed: {elapsed_total:.1f}s")


if __name__ == "__main__":
    main()
