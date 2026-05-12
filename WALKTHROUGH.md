# WALKTHROUGH — interview-ready deep dive

Read this top-to-bottom before talking through the gym. It covers
every component, every design choice, and the "why" behind each.

---

## Part 1 — What is this gym, in one paragraph

`ecommerce-browser-gym` is a production-grade RL gym for browser-based
LLM agents on e-commerce tasks. Agents drive a real Chromium browser
(headed by default, with video recording) through a multi-page
e-commerce simulator: search, filter, product variants, cart with
per-line options, multi-step checkout, account management, returns,
and subscriptions. After every agent action, the harness probes a
**milestone verifier** that inspects URL + DOM + ground-truth backend
state, awarding weighted partial credit. Final score is the
**fraction of weighted milestones fired**. Every episode produces a
trajectory JSONL with per-step screenshots, running reward, and which
milestones fired at each step — exactly the dense data RL training
needs.

---

## Part 2 — The 6 components

### 1. The browser (Chromium via Playwright)
The agent operates a real browser. Headed by default — you watch the
cursor move and click. Playwright records video of every episode
(`.webm`) and the harness takes a screenshot after every action.

### 2. The gym server (FastAPI)
Multi-page e-commerce site at <http://localhost:8000>. 16 page routes
+ 12 form POST endpoints + 5 harness-only endpoints (`/_harness/...`)
used by the verifier.

### 3. State + mutations (`server/state.py`, `server/mutations.py`)
Plain dataclasses for the entities. Mutations are the only legal way
to change state. Each mutation appends to an `action_log` so verifiers
can inspect "did this happen", and emits `flash_messages` that the UI
surfaces as banners.

### 4. Task factories (`server/tasks.py`)
9 functions, each builds a fresh `GymState` for one episode.
Adversarial elements baked in: distractor products, expired coupons,
miscategorized items, pre-existing orders for the return task,
pre-seeded subscriptions/promotions/loyalty tiers as needed.

### 5. Verifiers (`server/verifiers.py`)
Each task defines an ordered list of `Milestone`s. After every agent
action, the harness probes all milestones via `/_harness/verify` →
returns the running score and which milestones just fired. Per-task
milestone tables in [`TASKS.md`](./TASKS.md).

### 6. Agents (`agents/`)
- `oracle_agent.py` — hand-coded Playwright script per task. Always
  1.0. Used to validate verifiers.
- `llm_agent.py` — Anthropic Claude DOM-action loop. Each turn: dump
  interactables → pick a tool (click/fill/select/...) → translate to
  Playwright via `BrowserCtx`.

---

## Part 3 — One episode, end-to-end

Walk through what happens when the agent runs task `A1/buy_wireless_mouse`:

```
1. eval/run.py
   ├─ POST /_harness/reset {task_id: "A1/buy_wireless_mouse", seed: 0}
   │     → Backend: fresh GymState (Alice logged in, 23 products, 0 orders)
   ├─ Launch Chromium (headed) with video recording
   └─ Navigate to http://localhost:8000

2. Agent: observation
   ├─ harness.dump_interactables() → 80 elements with data-test-id keys
   ├─ harness.snapshot() → cart=0 items, orders=0, no promo
   └─ Sent to Claude with system prompt + tool schemas

3. Claude: "Navigate to /product/p_mouse_wireless"
   ├─ harness.goto("/product/p_mouse_wireless")
   │  ├─ page.goto(url)
   │  ├─ page.screenshot() → screenshots/.../step_000.png
   │  ├─ harness.snapshot()
   │  └─ harness.verify(url="/product/...", step=0)
   │     → suite probes 7 milestones, "viewed_product_page" fires
   │     → returns {score: 0.15, newly_fired: ["viewed_product_page"]}
   ├─ StepRecord appended to trajectory
   └─ Tool result returned to Claude: {ok: true, url: "/product/..."}

4. Claude: "Click button[data-test-id='btn-add-to-cart']"
   ├─ harness.click(selector)
   │  ├─ page.click(selector)
   │  │  └─ Browser submits form → POST /api/cart/add
   │  │     → mutations.add_to_cart(state, "p_mouse_wireless", 1)
   │  │     → cart now has 1 item
   │  │     → 303 redirect to /cart
   │  ├─ Screenshot, snapshot, verify
   │  └─ "added_target_to_cart" + "avoided_distractor" milestones fire
   │     → score: 0.45

... continue: cart → checkout/address → /payment → /review → place_order ...

8. Claude: "Click button[data-test-id='btn-place-order']"
   ├─ harness.click → POST /api/checkout/place → 303 to /order/ORD-XXX
   ├─ Browser is now on /order/ORD-XXX
   ├─ harness.verify → "order_placed" (required, 0.30) +
   │                  "on_confirmation_page" (0.10) +
   │                  "home_address_used" (0.05) fire
   └─ Running score: 1.00, success: True

9. Claude: "finish" — agent declares completion
   ├─ Final harness.verify
   ├─ Trajectory saved to trajectories/llm/A1__0__abc.jsonl
   ├─ Video saved to videos/llm/abc.webm
   └─ Scorecard updated
```

The trajectory JSON contains every step with: action_kind, action_args,
url_after, screenshot_path, milestones_fired_this_step, running_score,
snapshot_after, reasoning. **Anyone can replay the agent's decisions
by reading the JSON top-to-bottom.**

---

## Part 4 — The big design choices

### Why a real browser instead of a mocked DOM?

A mocked DOM gym (like we built earlier) is faster and simpler but
doesn't test:
- Real form-submission flow (HTTP POST + redirect + new page load)
- Modal popups and tab navigation
- Real CSS rendering quirks
- Multi-page navigation timing

Production browser agents have to work in real Chromium. The cost of
the gym matching that (Playwright launch overhead) is worth it.

### Why milestone verifiers instead of "did the order get placed"?

Dense reward. Diagnostics. Partial credit. See
[`MILESTONES.md`](./MILESTONES.md) for the full argument.

### Why DOM-action agent (not pixel-level)?

DOM-action with `data-test-id` selectors is:
- More reliable (no viewport sensitivity)
- Works with any LLM (not just vision-grounded ones)
- Faster (no screenshot processing per step)

The same `BrowserCtx` supports adding a pixel-level (Computer Use)
agent — just swap the agent loop. The current cut uses DOM.

### Why FastAPI instead of a frontend framework (React/Next.js)?

Server-rendered Jinja templates + form-POST endpoints behave more like
real enterprise e-commerce shops (which often run server-rendered
under the hood — Shopify, BigCommerce, even Amazon's checkout). No
build step needed. The agent gets real page-load transitions, not
SPA route changes.

### Why in-memory state + single tenant?

Each episode = a clean reset. Production sandboxing (Docker isolation,
multi-tenant pools) is explicitly out of scope but the architecture
supports it: each gym instance is stateless across episodes thanks to
`/_harness/reset`.

---

## Part 5 — Failure modes the gym surfaces

| Mistake | Milestone that doesn't fire | Net |
|---|---|---|
| Buys wrong product | `added_target_to_cart` doesn't | -0.20 |
| Forgets to place order | `order_placed` (required) doesn't | success=False |
| Buys laptop over $1000 in A2 | `under_1000_subtotal` doesn't | -0.20 |
| Uses Home in C2 instead of split | `mouse_work_no_giftwrap` doesn't | -0.25 |
| Applies SAVE10 instead of TECH20 in C1 | `tech20_applied` (required) doesn't | success=False |
| Forgets 2FA in B3 | `two_fa_enabled` (required) doesn't | success=False |
| Buys 32GB variant but no mouse in A3 | `ordered_wireless_mouse` doesn't | -0.15 |
| Skips loyalty calc in C3 | `loyalty_10pct_recorded` (required) doesn't | success=False |

The trajectory JSONL records WHICH milestone never fired, so failure
clustering is trivial:

```python
from collections import Counter
import json
from pathlib import Path

missing = Counter()
for f in Path("trajectories/llm").glob("*.jsonl"):
    t = json.loads(f.read_text())
    for m in t["verifier_result"]["all_milestones"]:
        if m["fired_at_step"] < 0:
            missing[m["name"]] += 1
print(missing.most_common(10))
```

This is the closed-loop failure-mode → training-signal pipeline that
production browser-agent gyms exist to enable.

---

## Part 6 — How the harness integrates with browser agents

The `BrowserCtx` abstraction is what makes the harness agent-agnostic.

```python
class BrowserCtx:
    page: Page                      # raw Playwright handle
    server_url: str
    trajectory: Trajectory          # the recorder
    screenshot_dir: Path

    async def goto(self, path: str, reasoning: str = "") -> StepRecord:
        await self.page.goto(self._abs(path))
        return await self._record("navigate", {"path": path}, reasoning)

    async def click(self, selector: str, reasoning: str = "") -> StepRecord:
        await self.page.click(selector)
        return await self._record("click", {"selector": selector}, reasoning)

    # ... and fill, select, check, submit ...

    async def _record(self, kind, args, reasoning) -> StepRecord:
        # 1. Screenshot
        # 2. Backend snapshot
        # 3. Verifier probe
        # 4. Append StepRecord
        # 5. Return it
        ...
```

To plug in Browser Use, Computer Use, OpenAI CUA, Stagehand, etc.,
implement the agent loop to call these methods. The verifier and
trajectory infrastructure is unchanged.

---

## Part 7 — Talking points

If you're walking someone through this:

1. **"Real browser, real clicks."** Playwright + Chromium, headed. You
   can watch the agent operate. Video recording is on by default.

2. **"Per-step milestone rewards."** Not just final-state grading.
   Every action gets evaluated; if it crosses a milestone, partial
   credit is awarded. This is the dense reward signal RL training
   needs.

3. **"Multi-level inspection."** Milestones check URL, DOM, AND
   backend state. We own the simulator, so we can inspect ground
   truth (was the order placed with the right address? Was the
   subscription created with the loyalty discount?) — not just parse
   receipts.

4. **"9 tasks across 3 categories."** Discovery & Purchase, Account &
   Order Management, Complex Checkout. Difficulty curve from easy
   (full happy-path) to hard (multi-item bundle / multi-change
   session / per-line options).

5. **"Adversarial state baked in."** Distractor products with similar
   names, expired and category-restricted coupons, miscategorized
   items, OOS ringers. Each maps directly to a specific milestone the
   agent has to recognize.

6. **"Multi-backend agent."** Same loop works against Anthropic Claude
   (default), Together AI / OpenRouter / vLLM via LiteLLM.

7. **"Pytest suite."** 37 tests covering mutations + verifier
   correctness (oracle scores 1.0 on every task; failure modes
   produce specific partial-credit outcomes).

8. **"Honest about gaps."** No pixel-level (Computer Use) agent here —
   architecture supports it; not implemented. No multi-tenant /
   sandbox isolation — production concern.

9. **"Trajectory format is RL-ready."** Each step records the running
   reward and which milestones fired. Drop it directly into a TRL
   reward function and you have a training substrate (RLVR pattern).
