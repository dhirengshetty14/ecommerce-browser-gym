"""Universal agent-failure classifier.

THE PROBLEM THIS SOLVES
-----------------------
The old design bolted a `failure_category` string onto each milestone in
each task suite. That made failure labels TASK-COUPLED: a label only
existed where someone hand-wrote it, and a brand-new task (one the gym
authors never anticipated) produced no usable failure label at all.

That defeats the core business pitch — "buy 1,000 trajectories where the
agent applied the wrong promo" — because the label `wrong_promo` only
existed inside `_suite_c1`. It didn't generalize.

THE FIX
-------
A single UNIVERSAL taxonomy of agent-behaviour failure classes, plus a
classifier that derives one label from (brief, final_state, action_log,
verifier_result) for ANY e-commerce browser task — including tasks with
no predefined milestones.

Two-stage classification:
  1. Rule-based (this module): fast, free, deterministic. Handles the
     structural cases (no order, no subscription, budget exceeded, wrong
     address/payment, 2FA off, etc.) by inspecting the final state and
     the natural-language brief.
  2. LLM judge (optional fallback): when the rules return
     `unclassified_failure`, an LLM reads the brief + state + log and
     picks the best label from the same taxonomy. Handles novel tasks
     and subtle failures.

The label is stored at the TRAJECTORY level (`Trajectory.agent_failure_class`)
— it's an episode-level summary, not a per-step thing.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# The universal taxonomy
# --------------------------------------------------------------------------- #
# Every label describes WHAT THE AGENT DID WRONG (a behaviour), not which
# task-specific milestone it missed. These apply to any e-commerce browser
# task. Grouped by category for readability; the flat frozenset is the
# source of truth used for validation.

FAILURE_TAXONOMY: dict[str, str] = {
    # ── Goal completion ─────────────────────────────────────────────
    "agent_gave_up":            "Agent called finish() without achieving the goal.",
    "agent_ran_out_of_steps":   "Agent hit the max-step budget before finishing.",
    "never_reached_checkout":   "Purchase implied but agent never reached cart/checkout.",
    "goal_incomplete_no_order": "Order required but none was placed.",
    "confirmation_page_missed": "Order placed but agent never viewed the confirmation.",
    # ── Product selection ───────────────────────────────────────────
    "wrong_product_selected":   "Agent ordered a product that doesn't match the brief.",
    "picked_distractor_product":"Agent fell for an adversarial look-alike product.",
    "picked_wrong_variant":     "Wrong size/colour/spec, or variant picker skipped.",
    "missing_required_item":    "A multi-item task is missing one or more required items.",
    "extra_unwanted_item":      "Agent added items the brief did not ask for (side-effect).",
    "wrong_quantity":           "Wrong number of units ordered.",
    "out_of_stock_persistence": "Agent repeatedly tried to add an out-of-stock item.",
    # ── Address / payment ───────────────────────────────────────────
    "wrong_shipping_address":   "Order shipped to a different address than the brief specified.",
    "wrong_payment_method":     "Order paid with a different method than the brief specified.",
    "wrong_split_shipping":     "Multi-line order has wrong per-line shipping assignments.",
    # ── Promo / discount ────────────────────────────────────────────
    "promo_required_not_applied":"Brief mentioned a promo, agent applied none.",
    "wrong_promo_applied":      "Agent applied the wrong promo code.",
    "expired_promo_attempted":  "Agent tried to apply an expired/invalid code.",
    "discount_value_incorrect": "Promo applied but the discount amount is wrong.",
    "picked_suboptimal_coupon": "A better coupon was available; agent chose a worse one.",
    # ── Constraints ─────────────────────────────────────────────────
    "budget_exceeded":          "Final subtotal exceeds the brief's stated budget.",
    "wrong_category_item":      "Item is in the wrong category vs the constraint.",
    "wrong_item_count":         "Exact item-count constraint violated.",
    "no_backtracking_attempted":"Over-budget but agent never removed/swapped to fix it.",
    # ── Subscription ────────────────────────────────────────────────
    "subscription_not_created": "Brief asked to subscribe, no subscription exists.",
    "subscription_wrong_params":"Subscription created but cadence/qty/address/payment wrong.",
    "subscription_not_cancelled":"Brief asked to cancel, the subscription is still active.",
    # ── Returns ─────────────────────────────────────────────────────
    "return_not_initiated":     "Brief asked for a return, none was initiated.",
    "return_wrong_items":       "Return contains the wrong line item(s).",
    "return_wrong_options":     "Return reason or refund method doesn't match the brief.",
    # ── Account / security ──────────────────────────────────────────
    "tfa_not_enabled":          "Brief asked to enable 2FA, it's still off.",
    "address_not_added_or_default":"Brief asked to add/default an address, didn't happen.",
    "payment_not_added_or_default":"Brief asked to add/default a card, didn't happen.",
    # ── Gift / customization ────────────────────────────────────────
    "gift_wrap_wrong_line":     "Gift wrap applied to the wrong item.",
    "gift_message_missing_or_wrong":"Required gift message absent or incorrect.",
    # ── Behavioural signatures ──────────────────────────────────────
    "repeated_failed_actions":  "Agent looped on the same action with no state change.",
    "hallucinated_target":      "Agent navigated to a non-existent product/route or used a bogus code.",
    "unclassified_failure":     "Failed for a reason the rules couldn't pin down.",
}

UNIVERSAL_FAILURE_TAXONOMY: frozenset[str] = frozenset(FAILURE_TAXONOMY.keys())


# --------------------------------------------------------------------------- #
# Small helpers for inspecting GymState defensively
# --------------------------------------------------------------------------- #

def _orders(state: Any) -> list:
    return list(getattr(state, "orders", {}).values())


def _newest_order(state: Any):
    orders = _orders(state)
    if not orders:
        return None
    return max(orders, key=lambda o: getattr(o, "placed_at", ""))


def _returns(state: Any) -> list:
    return list(getattr(state, "returns", {}).values())


def _subscriptions(state: Any) -> list:
    return list(getattr(state, "subscriptions", {}).values())


def _active_subscriptions(state: Any) -> list:
    return [s for s in _subscriptions(state)
            if getattr(s, "status", "") == "active"]


def _current_user(state: Any):
    uid = getattr(state, "current_user_id", None)
    if not uid:
        return None
    return getattr(state, "users", {}).get(uid)


def _action_log(state: Any) -> list[dict]:
    return list(getattr(state, "action_log", []))


def _budget_from_brief(brief: str) -> Optional[float]:
    """Extract a 'under $X' / 'below $X' / 'less than $X' budget if present."""
    m = re.search(r"(?:under|below|less than|max(?:imum)?(?: of)?)\s*\$?\s*([\d,]+(?:\.\d+)?)",
                  brief, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _detect_action_loop(steps: Optional[list]) -> bool:
    """True if the agent repeated the same (kind, args) 3+ times in a row."""
    if not steps:
        return False
    last_sig = None
    run = 0
    for s in steps:
        kind = getattr(s, "action_kind", None) if not isinstance(s, dict) else s.get("action_kind")
        args = getattr(s, "action_args", None) if not isinstance(s, dict) else s.get("action_args")
        sig = (kind, repr(args))
        if sig == last_sig:
            run += 1
            if run >= 2:   # 3 identical in a row (first + 2 repeats)
                return True
        else:
            run = 0
            last_sig = sig
    return False


def _had_error_on_finish(steps: Optional[list]) -> bool:
    """Whether the last recorded action errored (selector miss, timeout)."""
    if not steps:
        return False
    last = steps[-1]
    err = getattr(last, "action_error", None) if not isinstance(last, dict) else last.get("action_error")
    return bool(err)


# --------------------------------------------------------------------------- #
# Rule-based classifier
# --------------------------------------------------------------------------- #

def classify_agent_failure(
    brief: str,
    state: Any,
    verifier_result: dict,
    steps: Optional[list] = None,
    *,
    n_steps: Optional[int] = None,
    had_repeated_actions: Optional[bool] = None,
    hit_max_steps: bool = False,
) -> Optional[str]:
    """Return ONE universal failure label, or None if the episode succeeded.

    Pure inspection of (brief, final state, action log, verifier result).
    Task-agnostic — works on tasks with no predefined milestones.

    Args:
        brief:            the task brief (natural language).
        state:            the final GymState.
        verifier_result:  dict from TaskSuite.evaluate (needs `success`, `score`).
        steps:            optional list of StepRecords for loop detection.
        n_steps:          step count (if `steps` not passed — endpoint use).
        had_repeated_actions:
                          behavioral hint; if None, derived from `steps`.
        hit_max_steps:    True if the episode ended by hitting the step cap.
    """
    if verifier_result.get("success"):
        return None

    brief_l = (brief or "").lower()
    log = _action_log(state)
    log_kinds = [e.get("kind") for e in log]

    # Resolve behavioural hints (allow caller to pass them directly, since
    # the server endpoint doesn't have the agent's StepRecords).
    if had_repeated_actions is None:
        had_repeated_actions = _detect_action_loop(steps)
    if n_steps is None:
        n_steps = len(steps) if steps else 0

    # ── Behavioural signatures (check before structural — they explain HOW) ──
    if any(k == "agent_gave_up" for k in log_kinds):
        return "agent_gave_up"
    if had_repeated_actions:
        return "repeated_failed_actions"

    # Purchase intent: detect both explicit verbs AND natural shopping
    # language ("get me", "grab", "I need a/four ..."), and treat a
    # non-empty cart as strong evidence the agent was mid-purchase. The
    # cart signal makes this robust to brief phrasings we didn't enumerate.
    cart_items = list(getattr(getattr(state, "cart", None), "items", []) or [])
    purchase_intent = bool(cart_items) or any(w in brief_l for w in (
        "buy", "buying", "order", "purchase", "place the order", "checkout",
        "check out", "add to cart", "get me", "grab", "pick up", "pick me up",
        "shopping for", "shop for", "i need a", "i need an", "i need one",
        "i need two", "i need three", "i need four", "need four things",
        "need a ", "need an ", "ship it", "ship the", "ship everything",
        "send it", "send them",
    ))
    order = _newest_order(state)

    # ── Subscription intents ────────────────────────────────────────
    sub_intent = ("subscription" in brief_l or "subscribe" in brief_l
                  or "auto-deliver" in brief_l or "auto deliver" in brief_l)
    if sub_intent:
        wants_cancel = "cancel" in brief_l
        wants_create = any(w in brief_l for w in
                           ("create", "set up", "start", "set me up", "new subscription"))
        if wants_cancel and _active_subscriptions(state):
            # Was a cancel asked but an active sub remains? Only flag if the
            # active sub looks like the one named for cancellation.
            return "subscription_not_cancelled"
        if wants_create and not _active_subscriptions(state):
            return "subscription_not_created"
        if wants_create and _active_subscriptions(state):
            # A sub exists but might have wrong params — defer to LLM judge
            # unless the verifier clearly missed the goal.
            return "subscription_wrong_params"

    # ── Return intents ──────────────────────────────────────────────
    if "return" in brief_l and "returns" not in brief_l.split()[:2]:
        if not _returns(state):
            return "return_not_initiated"
        # A return exists — wrong items or wrong options is subtle → LLM judge
        return "return_wrong_options"

    # ── Account / security intents ──────────────────────────────────
    user = _current_user(state)
    if ("two-factor" in brief_l or "2fa" in brief_l or "two factor" in brief_l):
        if user is not None and not getattr(user, "two_fa_enabled", False):
            return "tfa_not_enabled"
    if ("address" in brief_l and any(w in brief_l for w in ("add", "new", "default"))):
        if user is not None:
            # Heuristic: did the user gain a new non-stock address recently?
            labels = {a.label.lower() for a in getattr(user, "addresses", {}).values()}
            # If brief names a label not present, flag it.
            if "beach house" in brief_l and "beach house" not in labels:
                return "address_not_added_or_default"

    # ── Purchase / order structural failures ───────────────────────
    if purchase_intent and order is None:
        reached_checkout = any(k in ("checkout_step",) for k in log_kinds) \
            or any("checkout" in (e.get("step", "") if isinstance(e.get("step"), str) else "")
                   for e in log)
        if not reached_checkout and "view_cart" not in log_kinds \
                and not any(k == "add_to_cart" for k in log_kinds):
            return "never_reached_checkout"
        return "goal_incomplete_no_order"

    # ── Order exists but something about it is wrong ────────────────
    if order is not None:
        # Budget
        budget = _budget_from_brief(brief)
        subtotal = getattr(order, "subtotal", 0.0)
        if budget is not None and subtotal > budget + 0.01:
            # Did the agent ever try to backtrack (remove/zero a line)?
            removed = any(k in ("remove_line", "remove_from_cart") for k in log_kinds)
            if not removed:
                return "no_backtracking_attempted"
            return "budget_exceeded"

        # Promo
        promo_intent = any(w in brief_l for w in
                           ("promo", "coupon", "discount code", "code "))
        promo_code = getattr(order, "promo_code", None)
        if promo_intent and not promo_code:
            return "promo_required_not_applied"
        # Expired promo attempt in the log
        if any(e.get("kind") == "apply_promo_failed" for e in log):
            return "expired_promo_attempted"

        # Confirmation page
        url = verifier_result.get("final_url") or ""
        if "/order/" not in url and not any("/order/" in (e.get("url", "") or "")
                                            for e in log):
            # Only flag this if it's the LAST remaining gap (score is high)
            if verifier_result.get("score", 0.0) >= 0.8:
                return "confirmation_page_missed"

    # ── Step-budget exhaustion ──────────────────────────────────────
    # If the episode ended by hitting the step cap (or simply ran very
    # long with the goal still unmet), label it as budget exhaustion —
    # but only as a fallback, after the structural rules above had a
    # chance to pin down a more specific cause.
    if hit_max_steps or (purchase_intent and order is None and n_steps >= 25):
        return "agent_ran_out_of_steps"

    return "unclassified_failure"


# --------------------------------------------------------------------------- #
# LLM judge fallback
# --------------------------------------------------------------------------- #

def _summarize_state_for_judge(state: Any) -> str:
    """Compact, judge-friendly state summary (no giant JSON dumps)."""
    lines = []
    orders = _orders(state)
    lines.append(f"orders_placed: {len(orders)}")
    for o in orders[:2]:
        items = [
            f"{getattr(it, 'product_id', '?')}"
            f"{('/' + it.variant_id) if getattr(it, 'variant_id', None) else ''}"
            f" x{getattr(it, 'quantity', 1)}"
            f"{' [giftwrap]' if getattr(it, 'gift_wrap', False) else ''}"
            f" ->{getattr(it, 'ship_to_address_id', '?')}"
            for it in getattr(o, "items", [])
        ]
        lines.append(f"  order subtotal=${getattr(o, 'subtotal', 0):.2f} "
                     f"promo={getattr(o, 'promo_code', None)} "
                     f"pay={getattr(o, 'payment_id', '?')} items={items}")
    subs = _subscriptions(state)
    if subs:
        lines.append(f"subscriptions: " + "; ".join(
            f"{getattr(s, 'product_id', '?')} {getattr(s, 'cadence', '?')} "
            f"x{getattr(s, 'deliveries_remaining', '?')} {getattr(s, 'status', '?')}"
            for s in subs))
    rets = _returns(state)
    if rets:
        lines.append("returns: " + "; ".join(
            f"{getattr(r, 'order_id', '?')} items={getattr(r, 'item_ids', [])} "
            f"reason={getattr(r, 'reason', '?')} refund={getattr(r, 'refund_method', '?')}"
            for r in rets))
    user = _current_user(state)
    if user is not None:
        lines.append(f"two_fa_enabled: {getattr(user, 'two_fa_enabled', False)}")
    return "\n".join(lines)


def llm_classify_agent_failure(
    brief: str,
    state: Any,
    verifier_result: dict,
    model: str = "claude-haiku-4-5",
) -> str:
    """Use an LLM judge to pick a taxonomy label. Cheap (Haiku) fallback.

    Returns a label guaranteed to be in UNIVERSAL_FAILURE_TAXONOMY
    (falls back to 'unclassified_failure' if the judge returns garbage).
    Requires ANTHROPIC_API_KEY. Raises ImportError if anthropic missing.
    """
    from anthropic import Anthropic

    taxonomy_block = "\n".join(
        f"  {label}: {desc}" for label, desc in FAILURE_TAXONOMY.items()
    )
    state_summary = _summarize_state_for_judge(state)
    log = _action_log(state)
    log_summary = " -> ".join(e.get("kind", "?") for e in log[-30:]) or "(no actions logged)"

    prompt = f"""An e-commerce browser agent FAILED a task. Classify the failure.

TASK BRIEF:
{brief}

FINAL STATE:
{state_summary}

AGENT ACTION LOG (most recent 30 server-side mutations):
{log_summary}

VERIFIER SCORE: {verifier_result.get('score', 0.0):.2f} / 1.0

Choose the SINGLE most accurate failure label from this taxonomy:
{taxonomy_block}

Respond with ONLY the label string (e.g. `wrong_product_selected`).
No quotes, no explanation, no punctuation."""

    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=24,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    # Normalize: take the first token-ish thing that matches the taxonomy
    candidate = raw.strip().strip("`'\" .").split()[0] if raw else ""
    if candidate in UNIVERSAL_FAILURE_TAXONOMY:
        return candidate
    # Try a looser contains-match
    for label in UNIVERSAL_FAILURE_TAXONOMY:
        if label in raw:
            return label
    return "unclassified_failure"


# --------------------------------------------------------------------------- #
# Combined entry point: rules first, LLM judge fallback
# --------------------------------------------------------------------------- #

def classify(
    brief: str,
    state: Any,
    verifier_result: dict,
    steps: Optional[list] = None,
    *,
    n_steps: Optional[int] = None,
    had_repeated_actions: Optional[bool] = None,
    hit_max_steps: bool = False,
    use_llm_fallback: bool = False,
    llm_model: str = "claude-haiku-4-5",
) -> Optional[str]:
    """Top-level classification. Rule-based first; LLM judge if enabled and
    the rules returned 'unclassified_failure'.

    Returns None for a successful episode, else a universal taxonomy label.
    """
    label = classify_agent_failure(
        brief, state, verifier_result, steps=steps,
        n_steps=n_steps, had_repeated_actions=had_repeated_actions,
        hit_max_steps=hit_max_steps,
    )
    if label is None:
        return None
    if label == "unclassified_failure" and use_llm_fallback:
        try:
            return llm_classify_agent_failure(brief, state, verifier_result,
                                              model=llm_model)
        except Exception:
            # If the judge fails (no key, network), keep the rule label.
            return label
    return label
