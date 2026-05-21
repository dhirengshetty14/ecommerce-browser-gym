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

# Briefs are written the way a REAL USER would phrase a request — natural
# language with intent and context, NOT spoon-fed "(NOT the X, NOT the Y)"
# disambiguation. The agent has to interpret the intent and decide which
# product/option matches, just like a human shopper would. Adversarial
# look-alikes in the catalog (gaming mouse, office-category monitor, dog
# treats vs food, Studio Laptop vs Studio Laptop Pro, etc.) are the traps
# the agent must reason past on its own.
BRIEFS = {
    "A1": (
        "I need a basic wireless mouse for my office desk — just the "
        "standard model for everyday clicking, nothing specialized. "
        "Order one for me, ship it to my home, and put it on my Visa."
    ),
    "A2": (
        "I'm shopping for a reliable laptop. My budget tops out at "
        "$1,000, and I only buy well-reviewed products — 4.5 stars or "
        "better. Find one that fits and buy it. Ship it home and charge "
        "my Visa."
    ),
    "A3": (
        "I'm putting together a work setup. Get me the Studio Laptop "
        "configured with the most memory and storage it offers — I want "
        "32GB of RAM and a 1TB SSD. Add a wireless mouse and a mechanical "
        "keyboard to go with it. Keep the whole cart under $1,900. Ship "
        "everything home and pay with my Visa."
    ),

    "B1": (
        "Add my beach house to my saved addresses — it's at 17 Ocean "
        "Drive, Montauk, NY 11954, under my name, Alice Anderson. From "
        "now on I want everything shipped there by default."
    ),
    "B2": (
        "The wireless mouse from my order ORDER_REF_HERE stopped working "
        "— it's defective. Pull up that order and check the tracking so I "
        "know it actually got delivered, then start a return for just the "
        "mouse and refund it back to my original payment method."
    ),
    "B3": (
        "Tidy up my account for me, please. Make my Work address the "
        "default for shipping. Add a backup credit card — number "
        "4111 1111 1111 1111, expiring 12/29, CVV 123 — and make that my "
        "default way to pay. And turn on two-factor authentication; use "
        "123456 as the verification code."
    ),

    "C1": (
        "Grab me a Studio Laptop and a plain cotton t-shirt. I've got a "
        "promo code, TECH20, that takes money off electronics — apply it "
        "at checkout. Ship the order to my home and pay with my Visa."
    ),
    "C2": (
        "I'm buying two things and they go to different places. The "
        "Bluetooth headphones — the studio pair — are a birthday gift for "
        "a friend: send them to my home address, gift-wrapped, with the "
        "note 'Happy birthday'. The wireless mouse is for me at the "
        "office, so ship that one to my work address, no gift wrap. Put "
        "it all on my Visa."
    ),
    "C3": (
        "Set me up on auto-delivery for the premium dog food — once a "
        "week, four deliveries to start. Ship it home and bill my Visa. "
        "I'm a gold member, so I should be getting my loyalty discount "
        "automatically on each delivery."
    ),

    # ──────────────────────────────────────────────────────────────
    # VERY HARD tasks — multi-step, multi-constraint, real-user phrasing.
    # No "(NOT the X)" hand-holding: the agent must infer which product
    # and option each natural description points to.
    # ──────────────────────────────────────────────────────────────

    "A4": (
        "I'm setting up a new home office and need four things: a large "
        "27-inch monitor, a proper mechanical keyboard with a good typing "
        "feel, a comfortable mouse that won't wreck my wrist on long days, "
        "and a fast USB-C charger. I've got $550 for the whole lot, so "
        "keep it under that. Ship everything to my work address — I'm "
        "there during the day — and use my PayPal; I'm saving the credit "
        "card for something else this month."
    ),

    "B4": (
        "I'm switching my dog from kibble over to treats, so a few things "
        "in my account. First, cancel my current premium dog food "
        "subscription. Then set me up on a new one for the premium dog "
        "treats — every two weeks, six deliveries, shipped to my work "
        "address and billed to PayPal. While you're in there, turn on "
        "two-factor authentication for me; the code is 123456. Oh, and I "
        "changed my mind about the Bluetooth speaker from my recent order "
        "— send just the speaker back (keep the mouse, that one's great) "
        "and take store credit, since there's a 5% bonus for it."
    ),

    "C4": (
        "Big order, bear with me. I need a Studio Laptop, a black cotton "
        "t-shirt in medium, and a basic wireless mouse. The laptop ships "
        "to my work address. The t-shirt is a birthday present for my mom "
        "— send it to my home, gift-wrapped, with the message 'Happy "
        "Birthday Mom!'. The mouse goes home too, but no gift wrap on "
        "that. I've got a TECH20 promo code for the electronics discount "
        "— apply it. Pay with my Visa and place the order."
    ),

    # ──────────────────────────────────────────────────────────────
    # TAXONOMY-NAVIGATION tasks — the agent must BROWSE the category /
    # subcategory tree to find products, the way a shopper browses when
    # they don't know the exact product name. Searching the search bar
    # is the lazy shortcut these tasks are designed to discourage.
    # ──────────────────────────────────────────────────────────────

    "D1": (
        "I'm in the mood to browse rather than search for something "
        "specific. Take me through the Audio department, look at the "
        "headphones, and pick out a well-reviewed pair — 4.5 stars or "
        "better. Buy it, ship it home, and use my Visa. (I'd rather you "
        "browse the store than type in the search box.)"
    ),

    "D2": (
        "Walk me through the Electronics department to the keyboards "
        "section — I want to see what's there rather than search. Pick "
        "me out a proper mechanical keyboard with real tactile feedback, "
        "not one of the cheap membrane ones. Buy it, ship home, pay with "
        "Visa."
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
# VERY HARD tasks — added May 2026. One per category. Each is designed to
# stress multiple edge-case clusters simultaneously:
#   - heavy adversarial product naming
#   - constraints across multiple dimensions (price + category + brand)
#   - multi-step sequences with order dependencies
#   - non-default address / non-default payment
# --------------------------------------------------------------------------- #

def task_a4_home_office_bundle(seed: int) -> GymState:
    """4-product bundle with strict constraints — tests filtering,
    distractor avoidance across multiple product types, budget math,
    non-default address + non-default payment."""
    return _base_state(seed, "A4/home_office_bundle", "hard", "A",
                       with_login=True)


def task_b4_subscription_juggle(seed: int) -> GymState:
    """Multi-flow account task: cancel an existing subscription,
    create a new one (different cadence/payment/address), enable 2FA,
    initiate a partial return — all in one session.

    Pre-seeds: an active Dog Food subscription + an existing order
    with both a mouse and a speaker the agent can return.
    """
    state = _base_state(seed, "B4/subscription_juggle", "hard", "B",
                        with_login=True)
    from server.state import Subscription
    alice = state.users["u_alice"]
    addr = alice.addresses["addr_home"]
    pay = alice.payment_methods["pay_visa"]

    # Pre-existing active Dog Food subscription that agent must cancel
    state.subscriptions["sub_existing_dogfood"] = Subscription(
        id="sub_existing_dogfood", user_id="u_alice",
        product_id="p_pet_food", variant_id=None, quantity=1,
        cadence="weekly", deliveries_remaining=3,
        next_delivery_date="2026-06-01",
        address_id=addr.id, payment_id=pay.id,
        loyalty_discount_pct=0.10, status="active",
    )

    # Pre-existing order with mouse + speaker for the return flow
    items = [
        OrderItem(id="ln_mouse", product_id="p_mouse_wireless",
                  product_name="Wireless Mouse", variant_id=None,
                  variant_label="", quantity=1, unit_price=29.99,
                  gift_wrap=False, gift_message="",
                  ship_to_address_id=addr.id, scheduled_delivery=None),
        OrderItem(id="ln_speaker", product_id="p_speaker",
                  product_name="Bluetooth Speaker", variant_id=None,
                  variant_label="", quantity=1, unit_price=79.99,
                  gift_wrap=False, gift_message="",
                  ship_to_address_id=addr.id, scheduled_delivery=None),
    ]
    sh = Shipment(
        id="sh_b4", tracking_number="1Z999AA20987654321",
        carrier="UPS",
        item_ids=[i.id for i in items],
        status="delivered",
        estimated_delivery=(
            datetime.now(timezone.utc) - timedelta(days=5)
        ).date().isoformat(),
        events=[
            ShipmentEvent("2026-05-01T10:00:00Z", "label_created",
                          "Distribution Center", "Shipping label created"),
            ShipmentEvent("2026-05-03T14:20:00Z", "delivered",
                          "Brooklyn, NY", "Delivered"),
        ],
    )
    state.orders["ORD-B4-9999"] = Order(
        id="ORD-B4-9999", user_id="u_alice",
        placed_at="2026-05-01T09:30:00Z",
        items=items,
        subtotal=109.98, discount=0.0,
        tax=round(109.98 * 0.085, 2),
        shipping=5.99, total=round(109.98 * 1.085 + 5.99, 2),
        promo_code=None, payment_id=pay.id, status="delivered",
        shipments=[sh],
    )
    return state


def task_c4_mega_checkout(seed: int) -> GymState:
    """The hardest checkout task — combines C1 (promo on right line) +
    C2 (split shipping + gift wrap) + variant selection on the t-shirt.
    Three line items, three different shipping/gift-wrap configurations,
    a category-restricted promo, and a non-default payment vs address mix.
    """
    state = _base_state(seed, "C4/mega_checkout", "hard", "C",
                        with_login=True)
    state.promotions = _promos_for_c1()
    return state


# ----- Category D: taxonomy navigation ------------------------------------- #

def task_d1_browse_audio(seed: int) -> GymState:
    """Browse the Audio category -> headphones subcategory, no search."""
    return _base_state(seed, "D1/browse_audio_no_search", "medium", "D",
                       with_login=True)


def task_d2_drill_keyboards(seed: int) -> GymState:
    """Drill Electronics -> keyboards subcategory, pick a mechanical one."""
    return _base_state(seed, "D2/drill_electronics_keyboards", "hard", "D",
                       with_login=True)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

TASKS = {
    "A1/buy_wireless_mouse":     task_a1_buy_wireless_mouse,
    "A2/filter_laptop":          task_a2_filter_laptop,
    "A3/configure_bundle":       task_a3_configure_bundle,
    "A4/home_office_bundle":     task_a4_home_office_bundle,
    "B1/add_address":            task_b1_add_address,
    "B2/track_and_return":       task_b2_track_and_return,
    "B3/account_overhaul":       task_b3_account_overhaul,
    "B4/subscription_juggle":    task_b4_subscription_juggle,
    "C1/promo_partial":          task_c1_promo_partial,
    "C2/split_shipping_gift":    task_c2_split_shipping,
    "C3/subscription_loyalty":   task_c3_subscription,
    "C4/mega_checkout":          task_c4_mega_checkout,
    "D1/browse_audio_no_search":     task_d1_browse_audio,
    "D2/drill_electronics_keyboards": task_d2_drill_keyboards,
}


def make_task(task_id: str, seed: int) -> GymState:
    if task_id not in TASKS:
        raise KeyError(f"unknown task {task_id!r}")
    return TASKS[task_id](seed)
