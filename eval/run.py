"""Episode runner — launch browser, drive the agent, collect rewards.

CLI:
    # Hand-coded oracle (no API key needed) — verifier sanity check
    python -m eval.run --agent oracle --tasks all --seeds 0

    # LLM browser agent (Anthropic)
    python -m eval.run --agent llm --tasks A1/buy_wireless_mouse --seeds 0

    # All 9 tasks, headed, recording video
    python -m eval.run --agent llm --tasks all --seeds 0

Output:
    trajectories/<agent>/<task>__<seed>__<id>.jsonl
    videos/*.webm                                       (Playwright video)
    screenshots/<task>__<seed>__<id>/step_NNN.png

Requires the gym server running first:
    uvicorn server.main:app --reload
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

from agents.oracle_agent import SOLVERS as ORACLE_SOLVERS
from harness.runner import (
    BrowserCtx, Trajectory, open_browser, reset_gym, save_trajectory,
)


ALL_TASKS = list(ORACLE_SOLVERS.keys())


def _parse_seeds(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _parse_tasks(spec: str) -> list[str]:
    if spec == "all":
        return ALL_TASKS
    return [t.strip() for t in spec.split(",") if t.strip()]


async def _run_one(*, agent_kind: str, task_id: str, seed: int,
                   server_url: str, headless: bool, record_video: bool,
                   out_traj_dir: Path, out_screens_dir: Path,
                   llm_model: str | None) -> Trajectory:
    # Reset the gym for this task
    reset = await reset_gym(server_url, task_id, seed)

    pw, browser, ctx_browser, page = await open_browser(
        server_url=server_url, headless=headless,
        record_video=record_video,
        videos_dir=Path("videos") / agent_kind,
    )

    episode_id = uuid.uuid4().hex[:8]
    shots_dir = out_screens_dir / f"{task_id.replace('/', '_')}__{seed}__{episode_id}"
    shots_dir.mkdir(parents=True, exist_ok=True)

    traj = Trajectory(
        episode_id=episode_id, task_id=task_id, seed=seed,
        agent_name=f"oracle" if agent_kind == "oracle"
                   else f"llm[{llm_model or 'default'}]",
        started_at=time.time(),
        task_brief=reset["task_brief"],
        task_difficulty=reset["task_difficulty"],
        task_category=reset["task_category"],
    )
    bctx = BrowserCtx(
        page=page, server_url=server_url, trajectory=traj,
        screenshot_dir=shots_dir,
    )

    # Initial snapshot
    traj.initial_url = page.url
    async with httpx.AsyncClient() as c:
        snap = (await c.get(f"{server_url}/_harness/snapshot")).json()
    traj.initial_snapshot = snap

    # Drive the agent
    try:
        if agent_kind == "oracle":
            solver = ORACLE_SOLVERS[task_id]
            await solver(bctx)
        else:
            from agents.llm_agent import LLMBrowserAgent
            agent = LLMBrowserAgent(model=llm_model)
            await agent.run(bctx, task_brief=reset["task_brief"])
    except Exception as e:
        traj.error = f"{type(e).__name__}: {e}"

    # Final probe
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

    # Close browser BEFORE asking for video path — Playwright finalizes
    # the file on close, so a path requested before close may not exist yet.
    await ctx_browser.close()
    await browser.close()
    await pw.stop()

    # Capture video path after close. page.video.path() is async in
    # modern Playwright — must await.
    if record_video and page.video is not None:
        try:
            video_path = await page.video.path()
            traj.video_path = str(video_path) if video_path else ""
        except Exception:
            traj.video_path = ""
    else:
        traj.video_path = ""

    save_trajectory(traj, out_traj_dir)
    return traj


def _print_scorecard(rows: list[Trajectory]) -> None:
    if not rows:
        print("No episodes ran.")
        return
    print()
    print("=" * 96)
    print(f"{'task':<32} {'cat':>4} {'diff':>6} {'seed':>5} {'score':>7} {'success':>8}")
    print("-" * 96)
    for t in rows:
        print(f"{t.task_id:<32} {t.task_category:>4} {t.task_difficulty:>6} "
              f"{t.seed:>5} {t.verifier_result.get('score', 0.0):>7.2f} "
              f"{str(t.verifier_result.get('success', False)):>8}")
    print("-" * 96)
    overall = sum(t.verifier_result.get("score", 0.0) for t in rows) / len(rows)
    succ = sum(1 for t in rows if t.verifier_result.get("success", False)) / len(rows)
    print(f"{'OVERALL':<32} {'':>4} {'':>6} {'':>5} {overall:>7.2f} {succ*100:>7.1f}%")
    print("=" * 96)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", choices=["oracle", "llm"], required=True)
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--headless", action="store_true",
                    help="Hide the browser window. Default: SHOW it.")
    ap.add_argument("--no-video", action="store_true",
                    help="Disable Playwright video recording.")
    ap.add_argument("--model", default=None,
                    help="LLM model id (Anthropic) — overrides default.")
    ap.add_argument("--out-traj", default=None)
    ap.add_argument("--out-screens", default=None)
    args = ap.parse_args()

    tasks = _parse_tasks(args.tasks)
    seeds = _parse_seeds(args.seeds)
    out_traj_dir = Path(args.out_traj or f"trajectories/{args.agent}")
    out_screens_dir = Path(args.out_screens
                           or f"screenshots/{args.agent}")
    out_screens_dir.mkdir(parents=True, exist_ok=True)

    # Quick reach check
    try:
        httpx.get(f"{args.server}/_harness/tasks", timeout=3.0)
    except Exception as e:
        print(f"ERROR: cannot reach gym at {args.server}: {e}\n"
              "Start the server first: uvicorn server.main:app --reload",
              file=sys.stderr)
        sys.exit(2)

    trajectories: list[Trajectory] = []
    started = time.time()
    for task_id in tasks:
        for seed in seeds:
            print(f"\n>>> {args.agent} on {task_id} seed={seed}")
            traj = asyncio.run(_run_one(
                agent_kind=args.agent, task_id=task_id, seed=seed,
                server_url=args.server,
                headless=args.headless,
                record_video=(not args.no_video),
                out_traj_dir=out_traj_dir,
                out_screens_dir=out_screens_dir,
                llm_model=args.model,
            ))
            v = traj.verifier_result
            print(f"  -> score={v.get('score', 0):.2f} "
                  f"success={v.get('success', False)} "
                  f"steps={len(traj.steps)} video={traj.video_path or 'none'}")
            trajectories.append(traj)

    elapsed = time.time() - started
    print(f"\nRan {len(trajectories)} episodes in {elapsed:.1f}s")
    _print_scorecard(trajectories)

    # Save scorecard
    summary = {
        "agent": args.agent,
        "model": args.model,
        "n_episodes": len(trajectories),
        "overall_score": (
            sum(t.verifier_result.get("score", 0.0) for t in trajectories)
            / max(len(trajectories), 1)
        ),
        "overall_success_rate": (
            sum(1 for t in trajectories
                if t.verifier_result.get("success", False))
            / max(len(trajectories), 1)
        ),
        "by_task": {
            task: {
                "n": sum(1 for t in trajectories if t.task_id == task),
                "score": (
                    sum(t.verifier_result.get("score", 0.0)
                        for t in trajectories if t.task_id == task)
                    / max(1, sum(1 for t in trajectories
                                 if t.task_id == task))
                ),
            } for task in tasks
        },
    }
    (out_traj_dir / "_scorecard.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print(f"Scorecard written to {out_traj_dir}/_scorecard.json")


if __name__ == "__main__":
    main()
