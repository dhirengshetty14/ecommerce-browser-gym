"""Browser harness — wraps Playwright + the per-step verifier probe.

This is the layer that sits between the agent and the browser. Key
responsibilities:

  1. Launch a real Chromium browser (headed by default — you can WATCH it).
  2. Record video of every episode (saved to ``videos/``).
  3. Take a screenshot after every agent step.
  4. After every step, probe the FastAPI ``/_harness/verify`` endpoint
     to detect newly-fired milestones and capture the running score.
  5. Build a Trajectory record with everything.

The agent doesn't talk to this directly — instead, the agent calls
Playwright methods through a thin wrapper that yields hooks (so we can
intercept after every action). See ``BrowserCtx`` below.

Why per-step probing?
- The score is **monotone** — it only goes up — so probing after each
  action shows exactly when the agent earns each milestone.
- For RL training, this gives a dense reward signal (small reward each
  time a milestone fires, big reward at completion) rather than a
  sparse one (one reward at the end).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
from playwright.async_api import (
    Browser, BrowserContext, Page, Playwright, async_playwright,
)


# --------------------------------------------------------------------------- #
# Step record + Trajectory
# --------------------------------------------------------------------------- #

@dataclass
class StepRecord:
    """One snapshot of agent activity. Captured AFTER each action."""
    step_idx: int
    action_kind: str               # "click", "fill", "navigate", "screenshot", ...
    action_args: dict[str, Any]
    url_after: str
    screenshot_path: str | None
    milestones_fired_this_step: list[str]
    running_score: float
    snapshot_after: dict[str, Any]   # /_harness/snapshot
    reasoning: str = ""


@dataclass
class Trajectory:
    episode_id: str
    task_id: str
    seed: int
    agent_name: str
    started_at: float
    finished_at: float | None = None
    task_brief: str = ""
    task_difficulty: str = ""
    task_category: str = ""
    initial_url: str = ""
    initial_snapshot: dict[str, Any] = field(default_factory=dict)
    steps: list[StepRecord] = field(default_factory=list)
    final_url: str = ""
    final_snapshot: dict[str, Any] = field(default_factory=dict)
    verifier_result: dict[str, Any] = field(default_factory=dict)
    video_path: str = ""
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task_id": self.task_id, "seed": self.seed,
            "agent_name": self.agent_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "task_brief": self.task_brief,
            "task_difficulty": self.task_difficulty,
            "task_category": self.task_category,
            "initial_url": self.initial_url,
            "initial_snapshot": self.initial_snapshot,
            "steps": [asdict(s) for s in self.steps],
            "final_url": self.final_url,
            "final_snapshot": self.final_snapshot,
            "verifier_result": self.verifier_result,
            "video_path": self.video_path,
            "error": self.error,
        }


def save_trajectory(traj: Trajectory, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_task = traj.task_id.replace("/", "_")
    path = out_dir / f"{safe_task}__{traj.seed}__{traj.episode_id}.jsonl"
    # default=str makes the serializer resilient to unusual values
    # (Path objects, datetime, accidental coroutines, etc.).
    path.write_text(
        json.dumps(traj.to_json(), indent=2, default=str),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# BrowserCtx — the harness instance the agent operates through
# --------------------------------------------------------------------------- #

@dataclass
class BrowserCtx:
    """A thin wrapper that exposes Playwright operations to the agent
    AND hooks our verifier probe / screenshot / trajectory recording
    after every step.

    The agent only needs to call:
        await ctx.goto("/login")
        await ctx.click("input[data-test-id='input-email']")
        await ctx.fill("input[data-test-id='input-email']", "alice@example.com")
        await ctx.click("button[data-test-id='btn-login']")
        ...
    Each call yields one StepRecord with full reward / milestone info.
    """
    page: Page
    server_url: str
    trajectory: Trajectory
    screenshot_dir: Path
    http: httpx.Client = field(
        default_factory=lambda: httpx.Client(timeout=30.0),
    )

    # --------- helpers the agent calls ---------

    async def goto(self, path: str, reasoning: str = "") -> StepRecord:
        url = self._abs(path)
        await self.page.goto(url, wait_until="load")
        return await self._record(
            "navigate", {"url": path}, reasoning=reasoning,
        )

    async def click(self, selector: str, reasoning: str = "") -> StepRecord:
        await self.page.click(selector)
        await self.page.wait_for_load_state("load")
        return await self._record(
            "click", {"selector": selector}, reasoning=reasoning,
        )

    async def fill(self, selector: str, value: str,
                   reasoning: str = "") -> StepRecord:
        await self.page.fill(selector, value)
        return await self._record(
            "fill", {"selector": selector, "value": value},
            reasoning=reasoning,
        )

    async def select(self, selector: str, value: str,
                     reasoning: str = "") -> StepRecord:
        await self.page.select_option(selector, value=value)
        return await self._record(
            "select", {"selector": selector, "value": value},
            reasoning=reasoning,
        )

    async def check(self, selector: str, reasoning: str = "") -> StepRecord:
        await self.page.check(selector)
        return await self._record(
            "check", {"selector": selector}, reasoning=reasoning,
        )

    async def submit(self, selector: str,
                     reasoning: str = "") -> StepRecord:
        """Submit a form by clicking a button inside it."""
        await self.page.click(selector)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        return await self._record(
            "submit", {"selector": selector}, reasoning=reasoning,
        )

    # --------- internal: probe + record after each action ---------

    async def _record(self, kind: str, args: dict[str, Any],
                      reasoning: str = "") -> StepRecord:
        step_idx = len(self.trajectory.steps)
        url = self.page.url

        # Screenshot
        shot_path = self.screenshot_dir / f"step_{step_idx:03d}.png"
        try:
            await self.page.screenshot(path=str(shot_path), full_page=False)
        except Exception:
            shot_path = None

        # Snapshot + verifier probe
        snap = self.http.get(f"{self.server_url}/_harness/snapshot").json()
        verifier_resp = self.http.post(
            f"{self.server_url}/_harness/verify",
            json={"url": url, "step": step_idx},
        ).json()
        newly = list(verifier_resp.get("newly_fired", []))
        running_score = float(verifier_resp.get("score", 0.0))

        rec = StepRecord(
            step_idx=step_idx,
            action_kind=kind, action_args=args,
            url_after=url,
            screenshot_path=(str(shot_path) if shot_path else None),
            milestones_fired_this_step=newly,
            running_score=running_score,
            snapshot_after=snap,
            reasoning=reasoning,
        )
        self.trajectory.steps.append(rec)
        return rec

    def _abs(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.server_url}{path}"


# --------------------------------------------------------------------------- #
# Harness lifecycle
# --------------------------------------------------------------------------- #

async def open_browser(
    *, server_url: str = "http://localhost:8000",
    headless: bool = False, record_video: bool = True,
    videos_dir: str | Path = "videos",
    viewport: dict[str, int] | None = None,
) -> tuple[Playwright, Browser, BrowserContext, Page]:
    """Launch a real Chromium and open one page tab."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    ctx_kwargs: dict[str, Any] = {
        "viewport": viewport or {"width": 1280, "height": 800},
    }
    if record_video:
        Path(videos_dir).mkdir(parents=True, exist_ok=True)
        ctx_kwargs["record_video_dir"] = str(videos_dir)
        ctx_kwargs["record_video_size"] = ctx_kwargs["viewport"]
    context = await browser.new_context(**ctx_kwargs)
    page = await context.new_page()
    return pw, browser, context, page


async def reset_gym(server_url: str, task_id: str, seed: int) -> dict[str, Any]:
    """Tell the backend to reset state for this task/seed."""
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{server_url}/_harness/reset",
            json={"task_id": task_id, "seed": seed},
        )
        r.raise_for_status()
        return r.json()


async def final_verify(server_url: str, url: str, step: int) -> dict[str, Any]:
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{server_url}/_harness/verify",
            json={"url": url, "step": step},
        )
        r.raise_for_status()
        return r.json()
