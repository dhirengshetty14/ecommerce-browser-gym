"""Per-step milestone verifier.

Each task is defined as an ORDERED LIST OF MILESTONES. A milestone is a
weighted predicate over the gym state and the current URL. After every
agent action, the harness probes the milestone list and awards credit
for any milestone that has just become satisfied.

Why ordered milestones (not free-form assertions)?
- The agent should achieve them in order to complete a real user
  journey ("logged in" before "added to cart" before "place_order").
- Awarding them in order means partial progress is meaningful — a
  half-completed task gets a half-credit score, with a clear failure
  point (where did the agent stop?).
- Each milestone records its first-fired step so we can reconstruct
  the agent's progression in the trajectory file.

The harness queries this in two places:
  1. After every action — to detect newly-satisfied milestones (live
     progress monitoring).
  2. At episode end — to compute the final aggregated score.

This pattern is what production browser-agent benchmarks (WebArena,
VisualWebArena, Mind2Web, BrowserGym) actually use. The novelty here
is using it on a stateful in-house simulator so milestone checks can
inspect backend state, not just DOM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from server.state import GymState


# --------------------------------------------------------------------------- #
# Probe — the snapshot a milestone check sees on each evaluation
# --------------------------------------------------------------------------- #

@dataclass
class Probe:
    """All the information a milestone check can use to evaluate itself."""
    state: GymState
    url: str                                      # current browser URL
    initial_state: GymState                       # snapshot at episode start


# --------------------------------------------------------------------------- #
# Milestone
# --------------------------------------------------------------------------- #

@dataclass
class Milestone:
    """One checkpoint along the agent's path to task completion.

    A milestone is purely a SCORING unit: a weighted predicate that
    fires once, the first time it becomes true. Milestones intentionally
    no longer carry a per-task `failure_category` label — that approach
    was task-coupled and didn't generalize to novel tasks. Failure
    classification now happens at the trajectory level via the universal
    taxonomy in ``harness/failure_classifier.py``.

    Attributes:
        name:               Human-readable identifier (used in details +
                            for debugging which scoring unit was missed).
        weight:             Contribution to final score (sum across all
                            milestones in a task should = 1.0).
        check:              ``(probe) -> bool``. The predicate.
        required_for_success:
                            If True, missing this means the episode
                            cannot be marked ``success=True`` regardless
                            of score (goal-defining milestones).
        fired_at_step:      Set by the harness when the milestone first
                            evaluates to True. Default -1 = never.
        category:           Optional grouping string (analytics only).
    """
    name: str
    weight: float
    check: Callable[[Probe], bool]
    required_for_success: bool = False
    fired_at_step: int = -1
    category: str = ""


# --------------------------------------------------------------------------- #
# Suite — the per-task milestone list
# --------------------------------------------------------------------------- #

@dataclass
class TaskSuite:
    task_id: str
    milestones: list[Milestone] = field(default_factory=list)

    def evaluate(self, probe: Probe, current_step: int) -> dict[str, Any]:
        """Probe every milestone. For any that fire for the first time,
        mark fired_at_step. Return a summary dict (which milestones just
        fired, aggregated score, success).

        Failure CLASSIFICATION is no longer done here — it happens once
        per episode at the trajectory level via
        ``harness/failure_classifier.classify``. The verifier's job is
        purely scoring + success determination. ``missed_milestones``
        is still surfaced for debugging which scoring unit didn't fire.
        """
        newly_fired: list[str] = []
        for m in self.milestones:
            if m.fired_at_step >= 0:
                continue
            try:
                ok = bool(m.check(probe))
            except Exception:
                ok = False
            if ok:
                m.fired_at_step = current_step
                newly_fired.append(m.name)

        return {
            "score":   self.aggregate_score(),
            "success": self.is_success(),
            "newly_fired": newly_fired,
            "missed_milestones": [
                m.name for m in self.milestones if m.fired_at_step < 0
            ],
            "all_milestones": [
                {"name": m.name, "weight": m.weight,
                 "fired_at_step": m.fired_at_step,
                 "required": m.required_for_success}
                for m in self.milestones
            ],
        }

    def aggregate_score(self) -> float:
        total_w = sum(m.weight for m in self.milestones) or 1.0
        earned = sum(m.weight for m in self.milestones
                     if m.fired_at_step >= 0)
        return round(earned / total_w, 4)

    def is_success(self) -> bool:
        """All required milestones must have fired AND total score == 1.0."""
        for m in self.milestones:
            if m.required_for_success and m.fired_at_step < 0:
                return False
        return self.aggregate_score() >= 0.999


# --------------------------------------------------------------------------- #
# Helpers used by checks
# --------------------------------------------------------------------------- #

def _on_url(probe: Probe, *substrs: str) -> bool:
    return any(s in probe.url for s in substrs)


def _order_with(probe: Probe, *,
                product_ids: tuple[str, ...] | None = None,
                variant_id: str | None = None,
                exclude_product_ids: tuple[str, ...] = (),
                exactly_n_items: int | None = None,
                ) -> bool:
    """Returns True iff an order exists with the requested shape."""
    for o in probe.state.orders.values():
        if exactly_n_items is not None and len(o.items) != exactly_n_items:
            continue
        if exclude_product_ids:
            if any(it.product_id in exclude_product_ids for it in o.items):
                continue
        if product_ids:
            present = {it.product_id for it in o.items}
            if not set(product_ids).issubset(present):
                continue
        if variant_id is not None:
            if not any(it.variant_id == variant_id for it in o.items):
                continue
        return True
    return False


def _newest_order(probe: Probe):
    if not probe.state.orders:
        return None
    return max(probe.state.orders.values(),
               key=lambda o: o.placed_at)


def _log_has(probe: Probe, kind: str, **fields: Any) -> bool:
    """True if the action_log contains an event of `kind` whose fields
    all match. Used by taxonomy-navigation verifiers to confirm the
    agent browsed categories/subcategories rather than searching."""
    for e in probe.state.action_log:
        if e.get("kind") != kind:
            continue
        if all(e.get(k) == v for k, v in fields.items()):
            return True
    return False


def _log_count(probe: Probe, kind: str) -> int:
    return sum(1 for e in probe.state.action_log if e.get("kind") == kind)


# --------------------------------------------------------------------------- #
# Per-task suite builders
# --------------------------------------------------------------------------- #

# --- A1: buy_wireless_mouse ---

def _suite_a1() -> TaskSuite:
    target = "p_mouse_wireless"
    # The catalog has multiple "wireless" mice; reject ANY non-target mouse.
    # Updated when the catalog grew (May 2026) — was just p_mouse_gaming.
    mouse_distractors = (
        "p_mouse_gaming",
        "p_mouse_ergonomic",
        "p_mouse_mini",
        "p_mouse_trackpad",
    )
    return TaskSuite(
        task_id="A1/buy_wireless_mouse",
        milestones=[
            Milestone("viewed_product_page", weight=0.15,
                      check=lambda p: _on_url(p, "/product/p_mouse_wireless")),
            Milestone("added_target_to_cart", weight=0.20,
                      check=lambda p: any(
                          it.product_id == target
                          for it in p.state.cart.items
                      ) or any(
                          it.product_id == target
                          for o in p.state.orders.values()
                          for it in o.items
                      )),
            Milestone("avoided_all_distractors", weight=0.10,
                      check=lambda p: not any(
                          it.product_id in mouse_distractors
                          for o in p.state.orders.values()
                          for it in o.items
                      )),
            Milestone("reached_checkout", weight=0.10,
                      check=lambda p: _on_url(p, "/checkout")),
            Milestone("order_placed", weight=0.30,
                      check=lambda p: _order_with(
                          p, product_ids=(target,), exactly_n_items=1,
                          exclude_product_ids=mouse_distractors,
                      ),
                      required_for_success=True),
            Milestone("on_confirmation_page", weight=0.10,
                      check=lambda p: _on_url(p, "/order/")),
            Milestone("home_address_used", weight=0.05,
                      check=lambda p: (
                          _newest_order(p) is not None
                          and all(
                              it.ship_to_address_id == "addr_home"
                              for it in _newest_order(p).items
                          )
                      )),
        ],
    )


# --- A2: filter_laptop ---

def _suite_a2() -> TaskSuite:
    return TaskSuite(
        task_id="A2/filter_laptop",
        milestones=[
            Milestone("searched_or_filtered_laptops", weight=0.20,
                      check=lambda p: (
                          _on_url(p, "/search")
                          or _on_url(p, "/category/electronics")
                      )),
            Milestone("viewed_an_electronics_laptop", weight=0.15,
                      check=lambda p: any(
                          s in p.url for s in (
                              "/product/p_laptop_studio",
                              "/product/p_laptop_pro",
                              "/product/p_laptop_budget",
                              # New laptops added May 2026; viewing them
                              # counts as exploration but they won't
                              # satisfy the rating/price constraints.
                              "/product/p_laptop_studio_pro",
                              "/product/p_laptop_creator",
                          )
                      )),
            Milestone("ordered_a_laptop", weight=0.30,
                      check=lambda p: any(
                          ("laptop" in p.state.products[it.product_id].name.lower()
                           and p.state.products[it.product_id].category == "electronics")
                          for o in p.state.orders.values()
                          for it in o.items
                      ),
                      required_for_success=True),
            Milestone("under_1000_subtotal", weight=0.20,
                      check=lambda p: (
                          _newest_order(p) is not None
                          and _newest_order(p).subtotal < 1000.0
                      )),
            Milestone("ordered_product_rating_ge_45", weight=0.15,
                      check=lambda p: all(
                          p.state.products[it.product_id].rating >= 4.5
                          for it in (_newest_order(p).items
                                     if _newest_order(p) else [])
                      ) and _newest_order(p) is not None),
        ],
    )


# --- A3: configure_bundle ---

def _suite_a3() -> TaskSuite:
    return TaskSuite(
        task_id="A3/configure_bundle",
        milestones=[
            Milestone("opened_variant_picker_on_laptop", weight=0.10,
                      check=lambda p: any(
                          s in p.url for s in (
                              "/product/p_laptop_studio",
                              "/product/p_laptop_pro",
                          )
                      )),
            Milestone("ordered_correct_laptop_variant", weight=0.25,
                      check=lambda p: any(
                          it.variant_id == "v_lt_32_1tb"
                          for o in p.state.orders.values()
                          for it in o.items
                      ),
                      required_for_success=True),
            Milestone("ordered_wireless_mouse", weight=0.15,
                      check=lambda p: _order_with(
                          p, product_ids=("p_mouse_wireless",),
                      )),
            Milestone("ordered_mechanical_keyboard", weight=0.15,
                      check=lambda p: _order_with(
                          p, product_ids=("p_kb_mech",),
                      )),
            Milestone("subtotal_under_1900", weight=0.20,
                      check=lambda p: (
                          _newest_order(p) is not None
                          and _newest_order(p).subtotal < 1900.0
                      )),
            Milestone("three_items_in_order", weight=0.10,
                      check=lambda p: _order_with(
                          p, exactly_n_items=3,
                      ),
                      required_for_success=True),
            Milestone("on_confirmation_page", weight=0.05,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --- B1: add_address ---

def _suite_b1() -> TaskSuite:
    return TaskSuite(
        task_id="B1/add_address",
        milestones=[
            Milestone("navigated_to_addresses", weight=0.20,
                      check=lambda p: _on_url(
                          p, "/account/addresses",
                      )),
            Milestone("address_added", weight=0.30,
                      check=lambda p: (
                          p.state.current_user_id is not None
                          and any(
                              a.label.lower() == "beach house"
                              for a in p.state.users[p.state.current_user_id].addresses.values()
                          )
                      ),
                      required_for_success=True),
            Milestone("address_fields_correct", weight=0.20,
                      check=lambda p: (
                          p.state.current_user_id is not None
                          and any(
                              (a.label.lower() == "beach house"
                               and "ocean drive" in a.line1.lower()
                               and a.city.lower() == "montauk"
                               and a.zip == "11954")
                              for a in p.state.users[p.state.current_user_id].addresses.values()
                          )
                      )),
            Milestone("address_set_as_default", weight=0.30,
                      check=lambda p: (
                          p.state.current_user_id is not None
                          and any(
                              (a.label.lower() == "beach house" and a.is_default)
                              for a in p.state.users[p.state.current_user_id].addresses.values()
                          )
                      ),
                      required_for_success=True),
        ],
    )


# --- B2: track_and_return ---

def _suite_b2() -> TaskSuite:
    return TaskSuite(
        task_id="B2/track_and_return",
        milestones=[
            Milestone("navigated_to_orders", weight=0.15,
                      check=lambda p: _on_url(
                          p, "/account/orders",
                      )),
            Milestone("opened_order_detail", weight=0.15,
                      check=lambda p: _on_url(
                          p, "/account/orders/ORD-EXISTING-1234",
                      )),
            Milestone("opened_tracking_modal", weight=0.15,
                      check=lambda p: any(
                          e.get("kind") == "viewed_tracking"
                          for e in p.state.action_log
                      )),
            Milestone("return_initiated", weight=0.25,
                      check=lambda p: any(
                          r.order_id == "ORD-EXISTING-1234"
                          for r in p.state.returns.values()
                      ),
                      required_for_success=True),
            Milestone("return_is_for_mouse_only", weight=0.20,
                      check=lambda p: any(
                          (r.order_id == "ORD-EXISTING-1234"
                           and r.item_ids == ["ln_mouse"])
                          for r in p.state.returns.values()
                      ),
                      required_for_success=True),
            Milestone("return_reason_defective", weight=0.05,
                      check=lambda p: any(
                          (r.order_id == "ORD-EXISTING-1234"
                           and r.reason == "defective")
                          for r in p.state.returns.values()
                      )),
            Milestone("refund_method_original_payment", weight=0.05,
                      check=lambda p: any(
                          (r.order_id == "ORD-EXISTING-1234"
                           and r.refund_method == "original_payment")
                          for r in p.state.returns.values()
                      )),
        ],
    )


# --- B3: account_overhaul ---

def _suite_b3() -> TaskSuite:
    def _has_default_work(p: Probe) -> bool:
        if p.state.current_user_id is None:
            return False
        u = p.state.users[p.state.current_user_id]
        a = u.addresses.get("addr_work")
        return a is not None and a.is_default

    def _has_backup_card_default(p: Probe) -> bool:
        if p.state.current_user_id is None:
            return False
        u = p.state.users[p.state.current_user_id]
        return any(
            (pm.nickname == "Backup Card" or pm.label == "Backup Card"
             or "backup" in pm.label.lower())
            and pm.is_default
            for pm in u.payment_methods.values()
        )

    def _two_fa_enabled(p: Probe) -> bool:
        if p.state.current_user_id is None:
            return False
        return p.state.users[p.state.current_user_id].two_fa_enabled

    return TaskSuite(
        task_id="B3/account_overhaul",
        milestones=[
            Milestone("navigated_to_account", weight=0.10,
                      check=lambda p: _on_url(p, "/account")),
            Milestone("set_work_as_default_address", weight=0.30,
                      check=_has_default_work,
                      required_for_success=True),
            Milestone("backup_card_added_and_default", weight=0.30,
                      check=_has_backup_card_default,
                      required_for_success=True),
            Milestone("two_fa_enabled", weight=0.30,
                      check=_two_fa_enabled,
                      required_for_success=True),
        ],
    )


# --- C1: promo_partial ---

def _suite_c1() -> TaskSuite:
    def _order_has_both(p: Probe) -> bool:
        return _order_with(
            p, product_ids=("p_laptop_studio", "p_clothing_tshirt"),
        )

    def _used_correct_promo(p: Probe) -> bool:
        o = _newest_order(p)
        return o is not None and o.promo_code == "TECH20"

    def _discount_matches_20pct_of_laptop_only(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None or o.promo_code != "TECH20":
            return False
        laptop_total = sum(
            it.unit_price * it.quantity
            for it in o.items
            if p.state.products[it.product_id].category == "electronics"
        )
        expected = round(laptop_total * 0.20, 2)
        return abs(o.discount - expected) <= 0.05

    return TaskSuite(
        task_id="C1/promo_partial",
        milestones=[
            Milestone("both_items_in_order", weight=0.25,
                      check=_order_has_both,
                      required_for_success=True),
            Milestone("tech20_applied", weight=0.30,
                      check=_used_correct_promo,
                      required_for_success=True),
            Milestone("discount_is_20pct_of_laptop_only", weight=0.30,
                      check=_discount_matches_20pct_of_laptop_only,
                      required_for_success=True),
            Milestone("on_confirmation_page", weight=0.15,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --- C2: split_shipping_gift ---

def _suite_c2() -> TaskSuite:
    def _two_shipments(p: Probe) -> bool:
        o = _newest_order(p)
        return o is not None and len(o.shipments) == 2

    def _hp_home_with_giftwrap(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id == "p_hp_studio"
             and it.ship_to_address_id == "addr_home"
             and it.gift_wrap is True
             and "happy birthday" in (it.gift_message or "").lower())
            for it in o.items
        )

    def _mouse_work_no_giftwrap(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id == "p_mouse_wireless"
             and it.ship_to_address_id == "addr_work"
             and it.gift_wrap is False)
            for it in o.items
        )

    return TaskSuite(
        task_id="C2/split_shipping_gift",
        milestones=[
            Milestone("two_items_ordered", weight=0.15,
                      check=lambda p: _order_with(
                          p, product_ids=("p_hp_studio", "p_mouse_wireless"),
                          exactly_n_items=2,
                      ),
                      required_for_success=True),
            Milestone("headphones_home_with_giftwrap", weight=0.30,
                      check=_hp_home_with_giftwrap,
                      required_for_success=True),
            Milestone("mouse_work_no_giftwrap", weight=0.25,
                      check=_mouse_work_no_giftwrap,
                      required_for_success=True),
            Milestone("two_shipments_in_confirmation", weight=0.20,
                      check=_two_shipments,
                      required_for_success=True),
            Milestone("on_confirmation_page", weight=0.10,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --- C3: subscription_loyalty ---

def _suite_c3() -> TaskSuite:
    def _has_subscription(p: Probe) -> bool:
        return any(
            (s.product_id == "p_pet_food"
             and s.cadence == "weekly"
             and s.deliveries_remaining == 4)
            for s in p.state.subscriptions.values()
        )

    def _loyalty_discount_set(p: Probe) -> bool:
        return any(
            (s.product_id == "p_pet_food"
             and abs(s.loyalty_discount_pct - 0.10) < 0.001)
            for s in p.state.subscriptions.values()
        )

    return TaskSuite(
        task_id="C3/subscription_loyalty",
        milestones=[
            Milestone("on_pet_food_product_page", weight=0.10,
                      check=lambda p: _on_url(
                          p, "/product/p_pet_food",
                      )),
            Milestone("subscription_created", weight=0.40,
                      check=_has_subscription,
                      required_for_success=True),
            Milestone("loyalty_10pct_recorded", weight=0.30,
                      check=_loyalty_discount_set,
                      required_for_success=True),
            Milestone("on_subscription_confirmation", weight=0.20,
                      check=lambda p: _on_url(p, "/account/subscriptions")),
        ],
    )


# --------------------------------------------------------------------------- #
# VERY HARD tasks — added May 2026. Heavy adversarial pressure + multi-step
# state inspection.
# --------------------------------------------------------------------------- #

# --- A4: home_office_bundle ---

def _suite_a4() -> TaskSuite:
    """4-item bundle: 27" monitor + mechanical keyboard + ergonomic mouse
    + USB-C charger. All electronics, subtotal < $550, ship to Work, pay
    PayPal. Heavy distractor pressure (multiple mice, multiple keyboards,
    Office Display masquerading as electronics)."""

    REQUIRED_PRODUCTS = {
        "p_monitor_27",           # 27" — NOT p_monitor_24
        "p_kb_mech",              # mechanical — NOT p_kb_mini / p_kb_wireless / p_kb_membrane
        "p_mouse_ergonomic",      # ergonomic — NOT p_mouse_wireless / p_mouse_gaming
        "p_charger",
    }
    FORBIDDEN_PRODUCTS = {
        "p_monitor_24",          # 24" — wrong size
        "p_office_display",      # office category, not electronics
        "p_kb_wireless", "p_kb_mini", "p_kb_membrane",  # wrong keyboards
        "p_mouse_wireless", "p_mouse_gaming", "p_mouse_mini", "p_mouse_trackpad",
    }

    def _has_all_required(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        present = {it.product_id for it in o.items}
        return REQUIRED_PRODUCTS.issubset(present)

    def _no_forbidden(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return not any(it.product_id in FORBIDDEN_PRODUCTS for it in o.items)

    def _exactly_four_items(p: Probe) -> bool:
        o = _newest_order(p)
        return o is not None and len(o.items) == 4

    def _all_electronics(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return all(
            p.state.products[it.product_id].category == "electronics"
            for it in o.items
        )

    def _subtotal_under_550(p: Probe) -> bool:
        o = _newest_order(p)
        return o is not None and o.subtotal < 550.0

    def _shipped_to_work(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return all(
            it.ship_to_address_id == "addr_work"
            for it in o.items
        )

    def _paid_with_paypal(p: Probe) -> bool:
        o = _newest_order(p)
        return o is not None and o.payment_id == "pay_paypal"

    return TaskSuite(
        task_id="A4/home_office_bundle",
        milestones=[
            Milestone("all_four_required_items", weight=0.20,
                      check=_has_all_required, required_for_success=True),
            Milestone("no_forbidden_distractor", weight=0.15,
                      check=_no_forbidden),
            Milestone("exactly_four_line_items", weight=0.10,
                      check=_exactly_four_items),
            Milestone("all_items_electronics_category", weight=0.10,
                      check=_all_electronics),
            Milestone("subtotal_under_550", weight=0.15,
                      check=_subtotal_under_550),
            Milestone("shipped_to_work_address", weight=0.10,
                      check=_shipped_to_work),
            Milestone("paid_with_paypal", weight=0.10,
                      check=_paid_with_paypal),
            Milestone("on_confirmation_page", weight=0.10,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --- B4: subscription_juggle ---

def _suite_b4() -> TaskSuite:
    """Four parallel account changes:
      (1) Cancel the active Dog Food subscription
      (2) Create a new Dog TREATS subscription (biweekly, 6, Work, PayPal)
      (3) Enable 2FA
      (4) Initiate return on speaker only from the existing order
    """

    def _dogfood_cancelled(p: Probe) -> bool:
        sub = p.state.subscriptions.get("sub_existing_dogfood")
        return sub is not None and sub.status == "cancelled"

    def _new_treats_subscription(p: Probe) -> bool:
        return any(
            (s.product_id == "p_pet_treats"
             and s.cadence == "biweekly"
             and s.deliveries_remaining == 6
             and s.address_id == "addr_work"
             and s.payment_id == "pay_paypal"
             and s.status == "active")
            for s in p.state.subscriptions.values()
        )

    def _two_fa_on(p: Probe) -> bool:
        if p.state.current_user_id is None:
            return False
        return p.state.users[p.state.current_user_id].two_fa_enabled

    def _speaker_return_only(p: Probe) -> bool:
        return any(
            (r.order_id == "ORD-B4-9999"
             and r.item_ids == ["ln_speaker"]
             and r.reason == "changed_mind"
             and r.refund_method == "store_credit")
            for r in p.state.returns.values()
        )

    def _no_mouse_in_return(p: Probe) -> bool:
        return not any(
            (r.order_id == "ORD-B4-9999" and "ln_mouse" in r.item_ids)
            for r in p.state.returns.values()
        )

    return TaskSuite(
        task_id="B4/subscription_juggle",
        milestones=[
            Milestone("dogfood_sub_cancelled", weight=0.20,
                      check=_dogfood_cancelled,
                      required_for_success=True),
            Milestone("dog_treats_sub_created_correctly", weight=0.30,
                      check=_new_treats_subscription,
                      required_for_success=True),
            Milestone("two_fa_enabled", weight=0.15,
                      check=_two_fa_on,
                      required_for_success=True),
            Milestone("speaker_only_return_with_correct_options", weight=0.25,
                      check=_speaker_return_only,
                      required_for_success=True),
            Milestone("avoided_returning_mouse", weight=0.10,
                      check=_no_mouse_in_return),
        ],
    )


# --- C4: mega_checkout ---

def _suite_c4() -> TaskSuite:
    """The hardest checkout task. 3 items with 3 different shipping
    configurations + variant selection on t-shirt + promo + non-default
    payment. Combines C1 + C2 patterns into one episode."""

    def _has_all_three(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        present = {it.product_id for it in o.items}
        return {"p_laptop_studio", "p_clothing_tshirt", "p_mouse_wireless"}.issubset(present)

    def _no_distractors(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        forbidden = {
            "p_laptop_studio_pro", "p_laptop_pro", "p_laptop_budget",
            "p_mouse_gaming", "p_mouse_ergonomic", "p_mouse_mini", "p_mouse_trackpad",
            "p_clothing_polo", "p_clothing_long_sleeve",
            "p_clothing_graphic", "p_clothing_tank", "p_clothing_hoodie",
        }
        return not any(it.product_id in forbidden for it in o.items)

    def _tshirt_size_m_black(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id == "p_clothing_tshirt"
             and it.variant_id == "v_ts_m_blk")
            for it in o.items
        )

    def _laptop_to_work(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id == "p_laptop_studio"
             and it.ship_to_address_id == "addr_work")
            for it in o.items
        )

    def _tshirt_home_giftwrap_message(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id == "p_clothing_tshirt"
             and it.ship_to_address_id == "addr_home"
             and it.gift_wrap is True
             and "happy birthday" in (it.gift_message or "").lower()
             and "mom" in (it.gift_message or "").lower())
            for it in o.items
        )

    def _mouse_home_no_giftwrap(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id == "p_mouse_wireless"
             and it.ship_to_address_id == "addr_home"
             and it.gift_wrap is False)
            for it in o.items
        )

    def _tech20_applied_correctly(p: Probe) -> bool:
        """TECH20 = 20% off electronics. In C4 there are TWO electronics
        items (laptop + wireless mouse), so the expected discount is
        20% of the sum of BOTH. The t-shirt (clothing) is not eligible."""
        o = _newest_order(p)
        if o is None or o.promo_code != "TECH20":
            return False
        electronics_total = sum(
            it.unit_price * it.quantity
            for it in o.items
            if p.state.products[it.product_id].category == "electronics"
        )
        expected = round(electronics_total * 0.20, 2)
        return abs(o.discount - expected) <= 0.05

    def _paid_with_visa(p: Probe) -> bool:
        o = _newest_order(p)
        return o is not None and o.payment_id == "pay_visa"

    return TaskSuite(
        task_id="C4/mega_checkout",
        milestones=[
            Milestone("all_three_required_items", weight=0.15,
                      check=_has_all_three, required_for_success=True),
            Milestone("no_distractor_picked", weight=0.10,
                      check=_no_distractors),
            Milestone("tshirt_size_m_black", weight=0.10,
                      check=_tshirt_size_m_black),
            Milestone("laptop_shipped_to_work", weight=0.10,
                      check=_laptop_to_work),
            Milestone("tshirt_home_with_giftwrap_message", weight=0.15,
                      check=_tshirt_home_giftwrap_message),
            Milestone("mouse_home_no_giftwrap", weight=0.10,
                      check=_mouse_home_no_giftwrap),
            Milestone("tech20_discount_on_all_electronics", weight=0.15,
                      check=_tech20_applied_correctly,
                      required_for_success=True),
            Milestone("paid_with_visa", weight=0.05,
                      check=_paid_with_visa),
            Milestone("on_confirmation_page", weight=0.10,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --------------------------------------------------------------------------- #
# Category D: taxonomy navigation
# --------------------------------------------------------------------------- #

# --- D1: browse_audio_no_search ---

def _suite_d1() -> TaskSuite:
    """Browse Audio -> headphones, pick a 4.5+ pair, WITHOUT the search bar."""
    QUALIFYING_HP = {"p_hp_premium", "p_hp_studio", "p_hp_studio_pro"}  # rating >= 4.5

    def _ordered_qualifying_hp(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return False
        return any(
            (it.product_id in QUALIFYING_HP
             and p.state.products[it.product_id].rating >= 4.5)
            for it in o.items
        )

    return TaskSuite(
        task_id="D1/browse_audio_no_search",
        milestones=[
            Milestone("visited_audio_category", weight=0.20,
                      check=lambda p: _log_has(p, "view_category", category="audio"),
                      required_for_success=True),
            Milestone("browsed_headphones_subcategory", weight=0.20,
                      check=lambda p: _log_has(p, "view_subcategory",
                                               category="audio", sub="headphones")),
            Milestone("avoided_search_bar", weight=0.15,
                      check=lambda p: _log_count(p, "search") == 0),
            Milestone("ordered_qualifying_headphone", weight=0.35,
                      check=_ordered_qualifying_hp,
                      required_for_success=True),
            Milestone("on_confirmation_page", weight=0.10,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --- D2: drill_electronics_keyboards ---

def _suite_d2() -> TaskSuite:
    """Drill Electronics -> keyboards subcategory, buy the mechanical one
    (p_kb_mech), avoiding the membrane keyboard. Browse, don't search."""

    def _ordered_mechanical(p: Probe) -> bool:
        return _order_with(p, product_ids=("p_kb_mech",))

    def _avoided_membrane(p: Probe) -> bool:
        o = _newest_order(p)
        if o is None:
            return True  # nothing ordered yet → hasn't picked the wrong one
        return not any(it.product_id == "p_kb_membrane" for it in o.items)

    return TaskSuite(
        task_id="D2/drill_electronics_keyboards",
        milestones=[
            Milestone("visited_electronics_category", weight=0.15,
                      check=lambda p: _log_has(p, "view_category",
                                               category="electronics"),
                      required_for_success=True),
            Milestone("drilled_keyboards_subcategory", weight=0.25,
                      check=lambda p: _log_has(p, "view_subcategory",
                                               category="electronics",
                                               sub="keyboards"),
                      required_for_success=True),
            Milestone("avoided_search_bar", weight=0.15,
                      check=lambda p: _log_count(p, "search") == 0),
            Milestone("ordered_mechanical_keyboard", weight=0.30,
                      check=_ordered_mechanical,
                      required_for_success=True),
            Milestone("avoided_membrane_keyboard", weight=0.05,
                      check=_avoided_membrane),
            Milestone("on_confirmation_page", weight=0.10,
                      check=lambda p: _on_url(p, "/order/")),
        ],
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

SUITE_FACTORIES = {
    "A1/buy_wireless_mouse":     _suite_a1,
    "A2/filter_laptop":          _suite_a2,
    "A3/configure_bundle":       _suite_a3,
    "A4/home_office_bundle":     _suite_a4,
    "B1/add_address":            _suite_b1,
    "B2/track_and_return":       _suite_b2,
    "B3/account_overhaul":       _suite_b3,
    "B4/subscription_juggle":    _suite_b4,
    "C1/promo_partial":          _suite_c1,
    "C2/split_shipping_gift":    _suite_c2,
    "C3/subscription_loyalty":   _suite_c3,
    "C4/mega_checkout":          _suite_c4,
    "D1/browse_audio_no_search":     _suite_d1,
    "D2/drill_electronics_keyboards": _suite_d2,
}


def build_suite(task_id: str) -> TaskSuite:
    if task_id not in SUITE_FACTORIES:
        raise KeyError(f"no verifier suite for {task_id}")
    return SUITE_FACTORIES[task_id]()
