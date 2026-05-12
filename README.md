# ecommerce-browser-gym

🛒 A **production-grade browser-agent RL gym** for e-commerce. Agents
drive a real Chromium browser through a multi-page e-commerce site —
search, filter, product variants, cart with per-line options, multi-step
checkout, account management, returns, subscriptions — and a per-step
**milestone verifier** grades progress action-by-action.

You can **watch the agent click**. Videos are recorded automatically.
Screenshots saved per step. Trajectories include the running reward
after every action.

## Why this exists

Most e-commerce gyms used for benchmarking browser agents (WebArena,
VisualWebArena, etc.) either grade only the final state ("did you place
an order?") OR have super coarse rewards. This one combines:

- **Real browser, real DOM, real clicks** — Playwright + Chromium, headed by
  default. The agent moves a cursor you can see.
- **Stateful in-house simulator** — we own the backend, so milestone
  checks can inspect ground truth (was the right address used? was the
  promo applied to the right line? did the subscription get the loyalty
  discount?) rather than parsing receipts from a real shop.
- **Per-step rewards**, not just final-state grading — agents get
  credit each time they cross a milestone. This is exactly the dense
  reward signal RL training needs.
- **Three task categories with multi-step journeys** — Product Discovery
  & Purchase, Account & Order Management, Complex Checkout. 9 tasks
  total, multiple difficulty tiers, multi-step.
- **Realistic adversarial elements** — distractor products with similar
  names, expired and category-restricted coupons, miscategorized items,
  variants that matter, OOS ringers.

## What's in here

```
ecommerce-browser-gym/
├── README.md
├── DESIGN.md              architecture write-up
├── TASKS.md               briefs + milestone tables per task
├── MILESTONES.md          how per-step rewards work
├── WALKTHROUGH.md         deep technical explainer
├── server/                FastAPI + state + tasks + verifiers
│   ├── state.py           entities (users/orders/returns/subscriptions...)
│   ├── catalog.py         catalog factory (23 products, 6 categories)
│   ├── tasks.py           9 task factories with adversarial state
│   ├── verifiers.py       Milestone + TaskSuite + per-task suites
│   ├── mutations.py       business logic (cart/checkout/account/...)
│   └── main.py            FastAPI app (16 page routes + 12 form POSTs)
├── ui/
│   ├── pages/             15 Jinja templates (home/search/product/...)
│   └── static/            CSS + tiny JS
├── harness/
│   └── runner.py          Playwright wrapper + per-step verifier probe
├── agents/
│   ├── oracle_agent.py    hand-coded gold trajectories per task
│   └── llm_agent.py       Anthropic Claude DOM-action loop
├── eval/
│   └── run.py             CLI runner + scorecard
├── tests/                 pytest suite (37 tests)
└── scripts/
    └── start_server.sh
```

## Quick start

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev,agent]"
playwright install chromium

# 2. Run the pytest suite (37 tests, ~1 second)
pytest -v

# 3. Start the gym server
uvicorn server.main:app --reload --port 8000
```

Open <http://localhost:8000> and click around as a human. The task banner at
the top tells you what to do. The verifier scores you when you finish.

### Run the hand-coded oracle (verifier sanity check)

```bash
# In another terminal — server must be running
python -m eval.run --agent oracle --tasks all --seeds 0
```

You'll watch 9 separate Chromium windows pop up and drive themselves
through every task. Each should end at score 1.0.

### Run the LLM browser agent

```bash
export ANTHROPIC_API_KEY=...
python -m eval.run --agent llm --tasks A1/buy_wireless_mouse --seeds 0
```

A Chromium window opens, Claude looks at the page and emits one tool
call per turn (click / fill / select / etc.), the harness translates
each to a Playwright action, and after every step probes
`/_harness/verify` for the running score.

Output:
```
>>> llm on A1/buy_wireless_mouse seed=0
[llm_agent] step 0: navigate({"path": "/product/p_mouse_wireless", ...})
[llm_agent] step 1: click({"selector": "button[data-test-id='btn-add-to-cart']"})
[llm_agent] step 2: click({"selector": "a[data-test-id='link-cart']"})
...
  -> score=1.00 success=True steps=8 video=videos/llm/abc123.webm
```

### What you'll see

- A **real Chromium window** moves on your screen, with the cursor
  moving, clicking, typing.
- A **video file** (.webm) is recorded for every episode.
- A **screenshot** per step is saved to `screenshots/<agent>/<task>__<seed>__<id>/`.
- A **trajectory JSONL** includes the running score, which milestones
  fired this step, and the URL after every action.

## 9 tasks across 3 categories

| ID | Cat | Diff | Brief |
|---|---|---|---|
| A1 | Discovery | easy | Buy a specific 'Wireless Mouse' (not the gaming mouse distractor) |
| A2 | Discovery | medium | Filter laptops under $1000 with ≥4.5★, buy 1 |
| A3 | Discovery | hard | Configure laptop with 32GB/1TB variant + mouse + keyboard, subtotal < $1900 |
| B1 | Mgmt | easy | Log in, add 'Beach House' address, set as default |
| B2 | Mgmt | medium | View tracking on past order, initiate return for one item (defective) |
| B3 | Mgmt | hard | Set default to Work + add backup card + enable 2FA, all in one session |
| C1 | Checkout | medium | Apply category-restricted promo (TECH20 only on electronics) |
| C2 | Checkout | medium | Split shipping: headphones→Home with gift wrap, mouse→Work |
| C3 | Checkout | hard | Set up weekly subscription with loyalty discount |

See [`TASKS.md`](./TASKS.md) for full briefs and milestone tables.

## See also

- [`DESIGN.md`](./DESIGN.md) — architecture
- [`MILESTONES.md`](./MILESTONES.md) — per-step reward model
- [`WALKTHROUGH.md`](./WALKTHROUGH.md) — interview-ready deep dive
- [`TASKS.md`](./TASKS.md) — task briefs + milestone weights
