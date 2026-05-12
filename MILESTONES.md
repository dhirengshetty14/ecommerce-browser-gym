# MILESTONES — the per-step reward model

## The idea

Each task = an ordered list of **milestones**. After every agent
action, the harness probes every milestone and awards weighted credit
for any that have just become satisfied.

This is dense reward — the agent earns small payouts each time it
makes meaningful progress, instead of all-or-nothing at the end. That's
the signal RL training needs.

## Anatomy of a milestone

```python
@dataclass
class Milestone:
    name: str                              # e.g. "added_target_to_cart"
    weight: float                          # contribution to final score
    check: Callable[[Probe], bool]         # the predicate
    required_for_success: bool = False     # gates success=True
    fired_at_step: int = -1                # set by harness; -1 = never
```

Where `Probe` gives the check access to:
- The current `GymState` (full ground truth)
- The current browser URL
- The initial state at episode start

## How scoring aggregates

```
score   = sum(m.weight for m in milestones if m.fired_at_step >= 0)
         / sum(m.weight for m in milestones)

success = score >= 0.999 AND
          all(m.fired_at_step >= 0
              for m in milestones
              if m.required_for_success)
```

`success=True` requires both full score AND every "required" milestone
fired. The "required" flag is what defines task goals — buying the
target product, completing the return, etc. Non-required milestones
are intermediate progress markers.

## Where milestones look

Three places per check:

1. **URL** — `_on_url(probe, "/checkout/review")`. Cheapest, most
   common. Captures "did the agent navigate to the right place".

2. **Backend state** — `probe.state.orders`, `probe.state.cart`,
   `probe.state.subscriptions`, etc. Captures ground-truth outcomes.

3. **Action log** — `probe.state.action_log`. Captures *what
   happened*, not just *what state we ended up in*. Used for sequence
   checks (e.g. "tracking was viewed").

Combinations of these give precise milestones like:
- "Order was placed AND it contains exactly the target product AND it
  shipped to Home AND was paid with Visa"
- "AUDIO20 coupon was applied AND it was applied BEFORE place_order AND
  the resulting discount is approximately 20% of subtotal"

## Why each milestone has a weight

Weights let us encode **what matters**:
- "Order placed" is heavier than "viewed product page" — completing
  the goal is the point.
- "Used correct address" is lighter than "ordered correct item" — the
  product matters more than where it ships.
- Hard-fail-eligible milestones can have weight 0 — they exist to
  signal "if this fails, zero everything" without contributing to the
  positive score.

## How "required" works

`required_for_success` lets us express:
- "You can score 0.9 but I won't call it a success unless you actually
  placed the order"

Tasks that have multiple required milestones (e.g. B3 needs ALL THREE
of: default-Work-address, backup-card-default, 2FA-enabled) must
satisfy each one.

## Why ordered (not free-form)

Listing milestones in the order an agent would naturally complete them
gives the trajectory file a story-like quality:

```
step 0: navigate /product/p_mouse_wireless
        → fires "viewed_product_page" (0.15)
step 1: click btn-add-to-cart
        → fires "added_target_to_cart" (0.20)
        → fires "avoided_distractor" (0.10)
step 2: navigate /checkout/address
        → fires "reached_checkout" (0.10)
step 3: click btn-place-order
        → fires "order_placed" (0.30) [REQUIRED]
step 4: arrived /order/ORD-...
        → fires "on_confirmation_page" (0.10)
        → fires "home_address_used" (0.05)

final score: 1.00, success: True
```

Anyone reading the trajectory can reconstruct exactly what the agent
did and where it earned credit.

## Why this beats binary success

| Metric | Binary | Milestone |
|---|---|---|
| Reward signal | sparse (1 at the end) | dense (after every step) |
| Partial-credit attribution | none | exact step at which each milestone fired |
| Failure diagnostics | "didn't succeed" | "completed steps 0-3, never reached step 5" |
| Useful for RL training | no | yes (the gradient has shape) |
| Useful for evals | yes | better |
| Useful for failure clustering | no | yes (group by which milestone is most-often-missed) |

This is the design pattern WebArena/VisualWebArena standardized for
browser-agent benchmarking, with our gym adding the **backend-state-
inspection** ability (since we own the server).

## See also

- [`TASKS.md`](./TASKS.md) — every task's milestone table with weights
- [`server/verifiers.py`](./server/verifiers.py) — the implementation
- [`DESIGN.md`](./DESIGN.md) — architecture overview
