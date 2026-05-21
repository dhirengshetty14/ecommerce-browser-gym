# Universal failure taxonomy — the core differentiator

**What it is:** every trajectory this gym produces carries one label from
a fixed, 38-class taxonomy describing *what the agent did wrong* — and
that label is **task-agnostic**. It applies to the 12 tasks shipped here
AND to any new task someone writes tomorrow, with no code changes.

**Why it matters:** this is the single feature no other browser-agent
benchmark has, and it's the thing that turns a benchmark into a sellable
data product.

---

## The problem it solves

The naive way to label failures is to attach a `failure_category` string
to each milestone in each task. We did that first — and it was wrong.

The labels were **task-coupled**: `wrong_promo` only existed inside the
C1 task's milestone list. Hand someone a brand-new task they wrote
themselves — *"buy two mugs and a candle, ship home"* — and the verifier
had nothing to say about why the agent failed. There were no milestones
for that task, so no labels.

That defeats the entire business pitch. When an LLM lab says *"sell us
1,000 trajectories where the agent applied the wrong promo,"* they need
that label to span **every** task — present and future. A label welded
to one task's milestone list doesn't generalize.

---

## The two-tier fix

We split the two jobs that were tangled together:

| Tier | Job | Bound to | Lives in |
|---|---|---|---|
| **1. Scoring** | "did the agent earn this 0.30 of weight?" | a specific milestone | `server/verifiers.py` |
| **2. Classification** | "what *kind* of failure was this?" | the agent's behaviour + final state | `harness/failure_classifier.py` |

Milestones are now **pure scoring units** — weighted predicates, nothing
more. They no longer carry failure labels.

Failure classification happens **once per episode**, at the end, by
inspecting `(brief, final GymState, action_log, verifier_result)` and
returning one label from the universal taxonomy. It never looks at
milestone names, so it works on tasks with no milestones at all.

---

## The 38-class taxonomy

Grouped for readability; the flat set is the source of truth.

### Goal completion
`agent_gave_up` · `agent_ran_out_of_steps` · `never_reached_checkout` ·
`goal_incomplete_no_order` · `confirmation_page_missed`

### Product selection
`wrong_product_selected` · `picked_distractor_product` ·
`picked_wrong_variant` · `missing_required_item` · `extra_unwanted_item` ·
`wrong_quantity` · `out_of_stock_persistence`

### Address / payment
`wrong_shipping_address` · `wrong_payment_method` · `wrong_split_shipping`

### Promo / discount
`promo_required_not_applied` · `wrong_promo_applied` ·
`expired_promo_attempted` · `discount_value_incorrect` ·
`picked_suboptimal_coupon`

### Constraints
`budget_exceeded` · `wrong_category_item` · `wrong_item_count` ·
`no_backtracking_attempted`

### Subscription
`subscription_not_created` · `subscription_wrong_params` ·
`subscription_not_cancelled`

### Returns
`return_not_initiated` · `return_wrong_items` · `return_wrong_options`

### Account / security
`tfa_not_enabled` · `address_not_added_or_default` ·
`payment_not_added_or_default`

### Gift / customization
`gift_wrap_wrong_line` · `gift_message_missing_or_wrong`

### Behavioural signatures
`repeated_failed_actions` · `hallucinated_target` · `unclassified_failure`

---

## How classification works (rules + LLM judge)

### Stage 1 — rule-based (free, deterministic, ~70% of cases)

`classify_agent_failure(brief, state, verifier_result, ...)` runs a chain
of pattern matchers. It infers intent from the brief (keyword/regex) and
checks it against the final state:

- Brief mentions "buy/order" + no order placed → `goal_incomplete_no_order`
  (or `never_reached_checkout` if the agent never even reached the cart)
- Brief mentions "subscribe" + no active sub → `subscription_not_created`
- Brief mentions "cancel" + sub still active → `subscription_not_cancelled`
- Brief mentions "return" + no return exists → `return_not_initiated`
- Brief mentions "2FA" + flag off → `tfa_not_enabled`
- Order exists but subtotal > the "under $X" budget → `budget_exceeded`
  (or `no_backtracking_attempted` if the agent never tried to remove items)
- Brief mentions a promo + order has no promo_code → `promo_required_not_applied`
- Plus behavioural signals: repeated identical actions →
  `repeated_failed_actions`; step-cap hit → `agent_ran_out_of_steps`

### Stage 2 — LLM judge (optional, paid fallback)

When the rules return `unclassified_failure`, an LLM judge (Haiku) reads
the brief + a compact state summary + the action log and picks the best
label from the same taxonomy. This is what handles **arbitrary new tasks**
the rules don't have keywords for. Enabled with `--llm-judge`; off by
default so normal runs stay free and deterministic.

```python
from harness.failure_classifier import classify
label = classify(brief, final_state, verifier_result,
                 use_llm_fallback=True)   # rules first, Haiku judge if needed
```

### Where it runs

The server owns the real `GymState`, so the classifier runs server-side
via `POST /_harness/classify_failure`. The eval runner calls it after the
final verify and stores the result on `Trajectory.agent_failure_class`.
Behavioural hints the server can't see (loop detection, step count) are
passed in by the eval runner.

---

## Why this is the differentiator

| Benchmark | Failure labels |
|---|---|
| WebArena / VisualWebArena / WorkArena / OSWorld / WebShop | binary success/fail only |
| Mind2Web | step-level accuracy, no episode label |
| τ-bench | a few policy-violation tags, tied to its 2 domains |
| **This gym** | **38-class universal taxonomy, works on any task, queryable** |

The trajectory store becomes a **queryable failure-mode catalogue**:

```
"give me 1,000 trajectories where agent_failure_class = picked_distractor_product"
"give me 500 where agent_failure_class = subscription_wrong_params"
"give me everything tagged budget_exceeded across all tasks"
```

Every label spans every task, present and future. That's a SaaS-grade
training-data product, not just a leaderboard.

---

## What a buyer gets per trajectory

Each JSONL carries, in addition to the failure label:
- per-step `(observation, reasoning, action, running_score)` tuples
- the full model reasoning chain (incl. extended thinking for the pixel agent)
- per-step latency + token counts (cost-per-success analysis)
- the complete final `GymState` (ground truth)
- screenshots per step (multimodal training input)

A single trajectory file is therefore usable for SFT (imitation),
RLVR/GRPO (verifiable reward), DPO (chosen-vs-rejected pairs), and
failure-mode-targeted fine-tuning — all keyed off one universal label.
