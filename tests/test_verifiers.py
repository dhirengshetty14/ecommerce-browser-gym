"""Verifier suite tests.

For each task, we simulate a successful run by applying mutations
directly and synthesizing URL transitions, then run the milestone
probes. The verifier should award the full score and mark
``success=True``.

Failure-mode tests verify that wrong actions produce the correct
partial-credit / missing-milestone outcome.
"""

from __future__ import annotations

import copy

import pytest

from server import mutations
from server.tasks import make_task
from server.verifiers import Probe, build_suite


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _Sim:
    """Tiny simulator over (state, suite, current_url, step). Lets tests
    drive a sequence of URL changes + mutations and probe the verifier
    after each."""

    def __init__(self, task_id: str, seed: int = 0):
        self.state = make_task(task_id, seed)
        self.initial = copy.deepcopy(self.state)
        self.suite = build_suite(task_id)
        self.url = "/"
        self.step = 0

    def go(self, url: str):
        self.url = url
        return self._probe()

    def do(self, fn):
        """Apply a state mutation (already passed in as a thunk)."""
        fn()
        return self._probe()

    def _probe(self) -> dict:
        self.step += 1
        return self.suite.evaluate(
            Probe(state=self.state, url=self.url, initial_state=self.initial),
            self.step,
        )


# --------------------------------------------------------------------------- #
# A1: buy_wireless_mouse
# --------------------------------------------------------------------------- #

def test_a1_full_path_scores_one():
    sim = _Sim("A1/buy_wireless_mouse")
    sim.go("/product/p_mouse_wireless")
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_mouse_wireless", 1))
    sim.go("/checkout/address")
    sim.do(lambda: mutations.place_order(sim.state, "pay_visa"))
    order_id = list(sim.state.orders.keys())[0]
    final = sim.go(f"/order/{order_id}")
    assert final["success"] is True
    assert final["score"] == 1.0


def test_a1_no_order_partial_credit():
    sim = _Sim("A1/buy_wireless_mouse")
    sim.go("/product/p_mouse_wireless")
    result = sim.go("/cart")
    # Earned: viewed_product_page (0.15) only
    assert not result["success"]
    assert result["score"] < 0.30


# --------------------------------------------------------------------------- #
# A2: filter_laptop
# --------------------------------------------------------------------------- #

def test_a2_correct_laptop_scores_one():
    sim = _Sim("A2/filter_laptop")
    sim.go("/search?category=electronics&max_price=1000&min_rating=4.5")
    sim.go("/product/p_laptop_studio")
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_laptop_studio", 1))
    sim.do(lambda: mutations.place_order(sim.state, "pay_visa"))
    order_id = list(sim.state.orders.keys())[0]
    result = sim.go(f"/order/{order_id}")
    assert result["success"] is True


def test_a2_over_budget_laptop_partial():
    sim = _Sim("A2/filter_laptop")
    sim.go("/search")
    sim.go("/product/p_laptop_pro")          # > $1000
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_laptop_pro", 1))
    sim.do(lambda: mutations.place_order(sim.state, "pay_visa"))
    order_id = list(sim.state.orders.keys())[0]
    result = sim.go(f"/order/{order_id}")
    # over budget — the under_1000 milestone won't fire
    assert not result["success"]
    assert result["score"] < 1.0


# --------------------------------------------------------------------------- #
# B1: add_address
# --------------------------------------------------------------------------- #

def test_b1_complete_address_default():
    sim = _Sim("B1/add_address")
    sim.go("/account/addresses")
    sim.do(lambda: mutations.add_address(
        sim.state, label="Beach House", full_name="Alice Anderson",
        line1="17 Ocean Drive", city="Montauk", st="NY", zip_="11954",
        set_default=True,
    ))
    result = sim.go("/account/addresses")
    assert result["success"] is True


def test_b1_added_but_not_default_partial():
    sim = _Sim("B1/add_address")
    sim.go("/account/addresses")
    sim.do(lambda: mutations.add_address(
        sim.state, label="Beach House", full_name="Alice Anderson",
        line1="17 Ocean Drive", city="Montauk", st="NY", zip_="11954",
        set_default=False,
    ))
    result = sim.go("/account/addresses")
    assert not result["success"]
    # Earned: nav (0.20) + added (0.30) + fields_correct (0.20) = 0.70
    assert 0.6 < result["score"] < 0.8


# --------------------------------------------------------------------------- #
# B2: track_and_return
# --------------------------------------------------------------------------- #

def test_b2_full_return_scores_one():
    sim = _Sim("B2/track_and_return")
    sim.go("/account/orders")
    sim.go("/account/orders/ORD-EXISTING-1234")
    # Simulate "viewed tracking" by triggering the action_log entry
    from server.state import log_action
    log_action(sim.state, "viewed_tracking", order_id="ORD-EXISTING-1234")
    sim.go("/account/orders/ORD-EXISTING-1234/track")
    sim.do(lambda: mutations.initiate_return(
        sim.state, "ORD-EXISTING-1234", ["ln_mouse"],
        "defective", "original_payment",
    ))
    result = sim.go("/account/returns")
    assert result["success"] is True


# --------------------------------------------------------------------------- #
# B3: account_overhaul
# --------------------------------------------------------------------------- #

def test_b3_three_changes_score_one():
    sim = _Sim("B3/account_overhaul")
    sim.go("/account")
    sim.do(lambda: mutations.set_default_address(sim.state, "addr_work"))
    sim.do(lambda: mutations.add_payment_method(
        sim.state, label="Backup Card", kind="credit_card",
        card_number="4111111111111111", expires="12/29", cvv="123",
        nickname="Backup Card", set_default=True,
    ))
    sim.do(lambda: mutations.enable_two_fa(sim.state, "123456"))
    result = sim.go("/account")
    assert result["success"] is True


# --------------------------------------------------------------------------- #
# C1: promo_partial
# --------------------------------------------------------------------------- #

def test_c1_promo_correctly_applied():
    sim = _Sim("C1/promo_partial")
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_laptop_studio", 1))
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_clothing_tshirt",
                                         1, "v_ts_m_blk"))
    sim.do(lambda: mutations.apply_promo(sim.state, "TECH20"))
    sim.do(lambda: mutations.place_order(sim.state, "pay_visa"))
    order_id = list(sim.state.orders.keys())[0]
    result = sim.go(f"/order/{order_id}")
    assert result["success"] is True


# --------------------------------------------------------------------------- #
# C2: split_shipping_gift
# --------------------------------------------------------------------------- #

def test_c2_split_shipping_correct():
    sim = _Sim("C2/split_shipping_gift")
    # Add both items
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_hp_studio", 1))
    sim.do(lambda: mutations.add_to_cart(sim.state, "p_mouse_wireless", 1))
    # Configure per-line: headphones → home + giftwrap; mouse → work, no wrap
    lines = sim.state.cart.items
    hp_line = next(l for l in lines if l.product_id == "p_hp_studio")
    mouse_line = next(l for l in lines
                      if l.product_id == "p_mouse_wireless")
    sim.do(lambda: mutations.update_line(
        sim.state, hp_line.id,
        ship_to_address_id="addr_home",
        gift_wrap=True, gift_message="Happy birthday",
    ))
    sim.do(lambda: mutations.update_line(
        sim.state, mouse_line.id,
        ship_to_address_id="addr_work",
        gift_wrap=False,
    ))
    sim.do(lambda: mutations.place_order(sim.state, "pay_visa"))
    order_id = list(sim.state.orders.keys())[0]
    result = sim.go(f"/order/{order_id}")
    # Order should have 2 shipments since 2 addresses
    order = sim.state.orders[order_id]
    assert len(order.shipments) == 2
    assert result["success"] is True


# --------------------------------------------------------------------------- #
# C3: subscription_loyalty
# --------------------------------------------------------------------------- #

def test_c3_subscription_loyalty():
    sim = _Sim("C3/subscription_loyalty")
    sim.go("/product/p_pet_food")
    sim.do(lambda: mutations.create_subscription(
        sim.state, product_id="p_pet_food", cadence="weekly",
        deliveries=4, address_id="addr_home", payment_id="pay_visa",
    ))
    result = sim.go("/account/subscriptions")
    assert result["success"] is True


# --------------------------------------------------------------------------- #
# Aggregator sanity
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("task_id", [
    "A1/buy_wireless_mouse", "A2/filter_laptop", "A3/configure_bundle",
    "B1/add_address", "B2/track_and_return", "B3/account_overhaul",
    "C1/promo_partial", "C2/split_shipping_gift",
    "C3/subscription_loyalty",
])
def test_no_milestones_no_score(task_id):
    """Touching nothing should give score 0 and success=False."""
    sim = _Sim(task_id)
    result = sim.go("/")  # just opens the home page
    # Most tasks will have score 0 here; allow tiny credit from URL-only
    # milestones that happen to match "/".
    assert result["success"] is False
