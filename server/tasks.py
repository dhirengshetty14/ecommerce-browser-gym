"""Task factories — each builds a fresh GymState for one episode.

Three categories, 9 tasks total:

  A. Product discovery & purchase     (A1 easy, A2 medium, A3 hard)
  B. Account & order management       (B1 easy, B2 medium, B3 hard)
  C. Complex checkout & promotions    (C1 medium, C2 medium, C3 hard)

Each factory:
  * builds the user(s) the agent will use (with pre-set login creds)
  * picks the catalog slice that's relevant for this task
  * configures promotions / pre-existing orders / pre-existing
    subscriptions as needed by the task

Verifiers (in ``server/verifiers.py``) consume the task_id to look up
the right ordered list of milestones.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from server import catalog
from server.state import (
    Address, GymState, Order, OrderItem, PaymentMethod, Product, Promotion,
    Shipment, ShipmentEvent, User,
)


# --------------------------------------------------------------------------- #
# Default fixtures
# --------------------------------------------------------------------------- #

def _alice() -> User:
    """The default user. Tasks that need a logged-in user often use this."""
    u = User(
        id="u_alice", email="alice@example.com",
        password="password123", full_name="Alice Anderson",
        loyalty_tier="gold",
    )
    u.addresses["addr_home"] = Address(
        id="addr_home", label="Home", full_name="Alice Anderson",
        line1="100 Park Avenue", line2="Apt 4B",
        city="Brooklyn", state="NY", zip="11201", is_default=True,
    )
    u.addresses["addr_work"] = Address(
        id="addr_work", label="Work", full_name="Alice Anderson",
        line1="500 Madison Avenue", line2="22nd Floor",
        city="New York", state="NY", zip="10022", is_default=False,
    )
    u.payment_methods["pay_visa"] = PaymentMethod(
        id="pay_visa", label="Visa ****4242",
        kind="credit_card", expires="08/27", is_default=True,
    )
    u.payment_methods["pay_paypal"] = PaymentMethod(
        id="pay_paypal", label="PayPal (alice@example.com)",
        kind="paypal", is_default=False,
    )
    return u


# --------------------------------------------------------------------------- #
# Brief copy (these are what shows up in the task banner)
# --------------------------------------------------------------------------- #

BRIEFS = {
    "A1": (
        "You're logged in as Alice. Find and buy exactly 1 unit of the "
        "'Wireless Mouse' (NOT the 'Wireless Gaming Mouse' — that's a "
        "different product). Use your default Home address and Visa "
        "card. When the confirmation page shows your order ID, click "
        "'Submit task'."
    ),
    "A2": (
        "Find a laptop in the Electronics category under $1,000 with a "
        "rating of 4.5 stars or higher. Buy 1 unit (default variant is "
        "fine). Use Home + Visa. Submit when confirmation shows."
    ),
    "A3": (
        "Configure and buy ONE laptop with the '32GB RAM / 1TB SSD' "
        "variant. Add the Wireless Mouse and the Mechanical Keyboard "
        "as accessories. Combined cart subtotal must be under $1,900. "
        "Ship to Home with Visa. Submit when the order is placed."
    ),

    "B1": (
        "You're logged in as Alice. Go to your Account → Addresses and "
        "add a new address. Label it 'Beach House', recipient 'Alice "
        "Anderson', line 1 '17 Ocean Drive', city 'Montauk', state 'NY', "
        "zip '11954'. Set it as the new default address. Submit when "
        "you see the new address in the list marked default."
    ),
    "B2": (
        "Order ORDER_REF_HERE is in your order history. View its tracking "
        "modal (the carrier and tracking number should be visible), then "
        "initiate a return for the Wireless Mouse only. Reason: "
        "'defective'. Refund method: 'original payment'. Submit when the "
        "return is created."
    ),
    "B3": (
        "Make these account changes in one session: "
        "(1) set 'Work' as your default shipping address; "
        "(2) add a new payment method — label 'Backup Card', kind "
        "'credit_card', card number '4111111111111111', expires '12/29', "
        "CVV '123', and set it as the new default payment; "
        "(3) enable two-factor authentication using code '123456'. "
        "Submit once all three are done."
    ),

    "C1": (
        "Add 1 of the Studio Laptop AND 1 of the Cotton T-Shirt to your "
        "cart. At checkout, apply promo code 'TECH20' — it should "
        "discount only the electronics item, not the t-shirt. Place the "
        "order using Home + Visa. Submit when confirmation shows the "
        "discount applied to the laptop only."
    ),
    "C2": (
        "Buy 1 Bluetooth Headphone Studio AND 1 Wireless Mouse. Ship "
        "the headphones to your 'Home' address with gift wrap (gift "
        "message: 'Happy birthday'). Ship the mouse to your 'Work' "
        "address with NO gift wrap. Pay with Visa. Submit when "
        "confirmation shows TWO shipments."
    ),
    "C3": (
        "Set up a weekly subscription for the Premium Dog Food: "
        "4 deliveries, ship to Home, pay with Visa. As a gold-tier "
        "member you should automatically receive a 10% loyalty "
        "discount. Submit when the subscription confirmation page "
        "shows the 4-delivery schedule and the loyalty discount line."
    ),
}


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #

def _base_state(seed: int, task_id: str, difficulty: str,
                category: str, with_login: bool = False) -> GymState:
    state = GymState(
        task_id=task_id, seed=seed,
        task_brief=BRIEFS[task_id.split("/")[0]],
        task_difficulty=difficulty,                      # type: ignore[arg-type]
        task_category=category,                          # type: ignore[arg-type]
    )
    state.products = catalog._build_catalog()
    state.users = {"u_alice": _alice()}
    if with_login:
        state.current_user_id = "u_alice"
    return state


# ----- Category A: product discovery & purchase ---------------------------- #

def task_a1_buy_wireless_mouse(seed: int) -> GymState:
    return _base_state(
        seed, "A1/buy_wireless_mouse", "easy", "A", with_login=True,
    )


def task_a2_filter_laptop(seed: int) -> GymState:
    # Build the catalog and tweak laptop prices for this seed within
    # ranges that preserve the constraint (one valid laptop only).
    rng = random.Random(seed)
    state = _base_state(seed, "A2/filter_laptop", "medium", "A",
                        with_login=True)
    # Studio laptop is the "right" choice — $899.99, 4.6 rating
    state.products["p_laptop_studio"].base_price = round(
        rng.uniform(799.0, 989.0), 2,
    )
    return state


def task_a3_configure_bundle(seed: int) -> GymState:
    state = _base_state(
        seed, "A3/configure_bundle", "hard", "A", with_login=True,
    )
    # A3 specifically requires the variant-picker flow. We add variants
    # to the Studio Laptop only for this task.
    from server.state import ProductVariant
    state.products["p_laptop_studio"].variants = [
        ProductVariant("v_lt_16_512", "16GB RAM / 512GB SSD",
                       {"ram": "16GB", "storage": "512GB"}, 0.0, 6),
        ProductVariant("v_lt_16_1tb", "16GB RAM / 1TB SSD",
                       {"ram": "16GB", "storage": "1TB"}, 150.0, 4),
        ProductVariant("v_lt_32_1tb", "32GB RAM / 1TB SSD",
                       {"ram": "32GB", "storage": "1TB"}, 400.0, 2),
    ]
    return state


# ----- Category B: account & order management ------------------------------ #

def task_b1_add_address(seed: int) -> GymState:
    return _base_state(seed, "B1/add_address", "easy", "B",
                       with_login=True)


def task_b2_track_and_return(seed: int) -> GymState:
    """Seeds an order so the agent has something to return."""
    state = _base_state(seed, "B2/track_and_return", "medium", "B",
                        with_login=True)
    # Pre-create an order with 2 items to make the task realistic.
    alice = state.users["u_alice"]
    addr = list(alice.addresses.values())[0]
    pay = list(alice.payment_methods.values())[0]
    items = [
        OrderItem(
            id="ln_mouse", product_id="p_mouse_wireless",
            product_name="Wireless Mouse", variant_id=None,
            variant_label="", quantity=1, unit_price=29.99,
            gift_wrap=False, gift_message="",
            ship_to_address_id=addr.id, scheduled_delivery=None,
        ),
        OrderItem(
            id="ln_speaker", product_id="p_speaker",
            product_name="Bluetooth Speaker", variant_id=None,
            variant_label="", quantity=1, unit_price=79.99,
            gift_wrap=False, gift_message="",
            ship_to_address_id=addr.id, scheduled_delivery=None,
        ),
    ]
    sh = Shipment(
        id="sh_existing",
        tracking_number="1Z999AA10123456784",
        carrier="UPS",
        item_ids=[i.id for i in items],
        status="delivered",
        estimated_delivery=(
            datetime.now(timezone.utc) - timedelta(days=2)
        ).date().isoformat(),
        events=[
            ShipmentEvent("2024-01-01T10:00:00Z", "label_created",
                          "Distribution Center", "Shipping label created"),
            ShipmentEvent("2024-01-02T08:00:00Z", "in_transit",
                          "Newark, NJ", "In transit"),
            ShipmentEvent("2024-01-03T14:20:00Z", "delivered",
                          "Brooklyn, NY", "Delivered to mailbox"),
        ],
    )
    state.orders["ORD-EXISTING-1234"] = Order(
        id="ORD-EXISTING-1234", user_id="u_alice",
        placed_at="2024-01-01T09:30:00Z",
        items=items,
        subtotal=109.98, discount=0.0,
        tax=round(109.98 * 0.085, 2),
        shipping=5.99, total=round(109.98 * 1.085 + 5.99, 2),
        promo_code=None, payment_id=pay.id, status="delivered",
        shipments=[sh],
    )
    # Patch the brief to reference the actual order id.
    state.task_brief = BRIEFS["B2"].replace(
        "ORDER_REF_HERE", "ORD-EXISTING-1234",
    )
    return state


def task_b3_account_overhaul(seed: int) -> GymState:
    return _base_state(seed, "B3/account_overhaul", "hard", "B",
                       with_login=True)


# ----- Category C: complex checkout ---------------------------------------- #

def _promos_for_c1() -> dict[str, Promotion]:
    return {
        "TECH20": Promotion(
            code="TECH20", name="20% off electronics",
            description="20% off all electronics. Cannot combine with "
                        "other promotions.",
            discount_pct=0.20,
            applies_to_category="electronics",
            min_purchase=0.0,
            description_fineprint=(
                "Discount applied to the eligible line items only "
                "(electronics). Other items are charged at full price."
            ),
        ),
        "BIGSAVE50": Promotion(
            code="BIGSAVE50", name="$50 off $500+",
            description="$50 off when you spend over $500.",
            discount_flat=50.0, min_purchase=500.0,
        ),
        "EXPIRED10": Promotion(
            code="EXPIRED10", name="(expired) 10% off",
            description="This promo has expired.",
            discount_pct=0.10, expired=True,
        ),
    }


def task_c1_promo_partial(seed: int) -> GymState:
    state = _base_state(seed, "C1/promo_partial", "medium", "C",
                        with_login=True)
    state.promotions = _promos_for_c1()
    return state


def task_c2_split_shipping(seed: int) -> GymState:
    return _base_state(seed, "C2/split_shipping_gift", "medium", "C",
                       with_login=True)


def task_c3_subscription(seed: int) -> GymState:
    return _base_state(seed, "C3/subscription_loyalty", "hard", "C",
                       with_login=True)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

TASKS = {
    "A1/buy_wireless_mouse":     task_a1_buy_wireless_mouse,
    "A2/filter_laptop":          task_a2_filter_laptop,
    "A3/configure_bundle":       task_a3_configure_bundle,
    "B1/add_address":            task_b1_add_address,
    "B2/track_and_return":       task_b2_track_and_return,
    "B3/account_overhaul":       task_b3_account_overhaul,
    "C1/promo_partial":          task_c1_promo_partial,
    "C2/split_shipping_gift":    task_c2_split_shipping,
    "C3/subscription_loyalty":   task_c3_subscription,
}


def make_task(task_id: str, seed: int) -> GymState:
    if task_id not in TASKS:
        raise KeyError(f"unknown task {task_id!r}")
    return TASKS[task_id](seed)
