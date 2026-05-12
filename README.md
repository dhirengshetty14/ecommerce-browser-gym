# ecommerce-browser-gym

🛒 A **production-grade browser-agent RL gym** for e-commerce. Agents
drive a real Chromium browser through a multi-page e-commerce site —
search, filter, product variants, cart with per-line options, multi-step
checkout, account management, returns, subscriptions — and a per-step
**milestone verifier** grades progress action-by-action.

---

## 🎬 Agent in Action

Four live recordings of Claude (claude-sonnet-4-5) completing real tasks.
All four score **1.00 — success**.

### C1 — Promo / Partial Discount &nbsp;·&nbsp; 1.00 ✅ &nbsp;·&nbsp; 15 steps

Buy Studio Laptop + Cotton T-Shirt, apply TECH20 (electronics-only coupon — applies to the laptop, not the t-shirt).

https://github.com/dhirengshetty14/ecommerce-browser-gym/releases/download/demos-v1/C1_promo_partial_seed0.webm

### C3 — Subscription + Loyalty Discount &nbsp;·&nbsp; 1.00 ✅ &nbsp;·&nbsp; 18 steps

Set up weekly subscription for Premium Dog Food (4 deliveries). Gold-tier loyalty discount auto-applies.

https://github.com/dhirengshetty14/ecommerce-browser-gym/releases/download/demos-v1/C3_subscription_loyalty_seed0.webm

### B2 — Track Order & Initiate Return &nbsp;·&nbsp; 1.00 ✅ &nbsp;·&nbsp; 14 steps

View tracking timeline on a past order, then initiate a return for the Wireless Mouse only (reason: defective, refund: original payment).

https://github.com/dhirengshetty14/ecommerce-browser-gym/releases/download/demos-v1/B2_track_and_return_seed0.webm

### B3 — Account Overhaul &nbsp;·&nbsp; 1.00 ✅ &nbsp;·&nbsp; 16 steps

In one session: set Work as default address, add backup card and set as default payment, enable 2FA.

https://github.com/dhirengshetty14/ecommerce-browser-gym/releases/download/demos-v1/B3_account_overhaul_seed0.webm

All trajectory JSONL files (per-step scores, screenshots, milestone firings) are in
[`trajectories/llm/`](./trajectories/llm/).

---

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

---

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
│   ├── pages/             21 Jinja templates (home/search/product/...)
│   └── static/            CSS + tiny JS
├── harness/
│   └── runner.py          Playwright wrapper + per-step verifier probe
├── agents/
│   ├── oracle_agent.py    hand-coded gold trajectories per task
│   └── llm_agent.py       Anthropic Claude DOM-action loop
├── eval/
│   └── run.py             CLI runner + scorecard
├── demos/                 4 recorded agent runs (.webm)
├── trajectories/llm/      10 JSONL trajectory files + scorecard
└── tests/                 pytest suite (37 tests)
```

---

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

---

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

---

## LLM agent results (claude-sonnet-4-5, seed 0)

| Task | Score | Success | Steps |
|---|---|---|---|
| A1 buy_wireless_mouse | 1.00 | ✅ | 8 |
| A2 filter_laptop | 0.80 | ❌ | 8 |
| A3 configure_bundle | 0.10 | ❌ | 15 |
| B1 add_address | 1.00 | ✅ | 11 |
| B2 track_and_return | 1.00 | ✅ | 14 |
| B3 account_overhaul | 1.00 | ✅ | 16 |
| C1 promo_partial | 1.00 | ✅ | 15 |
| C2 split_shipping_gift | 0.00 | ❌ | 20 |
| C3 subscription_loyalty | 1.00 | ✅ | 18 |
| **Overall** | **0.77** | **6/9** | |

Full scorecard: [`trajectories/llm/_scorecard.json`](./trajectories/llm/_scorecard.json)

---

## See also

- [`DESIGN.md`](./DESIGN.md) — architecture
- [`MILESTONES.md`](./MILESTONES.md) — per-step reward model
- [`WALKTHROUGH.md`](./WALKTHROUGH.md) — interview-ready deep dive
- [`TASKS.md`](./TASKS.md) — task briefs + milestone weights
