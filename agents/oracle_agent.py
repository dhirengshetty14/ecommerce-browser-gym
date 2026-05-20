"""Hand-coded oracle agent — uses Playwright directly through BrowserCtx.

This is the gold trajectory for each task. It always scores 1.0 if the
verifier is correctly designed. Its purpose:
  1. Validate verifiers (oracle != 1.0 means the verifier has a bug)
  2. Produce gold trajectories for downstream SFT data
  3. Anchor the score range: the oracle is the ceiling

It's NOT an LLM. It's Python that knows exactly what each task wants.
"""

from __future__ import annotations

from harness.runner import BrowserCtx


# --------------------------------------------------------------------------- #
# Per-task solvers
# --------------------------------------------------------------------------- #

async def solve_a1_buy_wireless_mouse(ctx: BrowserCtx) -> None:
    await ctx.goto("/")
    await ctx.goto("/product/p_mouse_wireless",
                   reasoning="The target is 'Wireless Mouse' "
                             "(not 'Wireless Gaming Mouse').")
    await ctx.fill("input[data-test-id='input-qty']", "1")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    await ctx.click("a[data-test-id='link-cart']")
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    await ctx.click("button[data-test-id='btn-place-order']")


async def solve_a2_filter_laptop(ctx: BrowserCtx) -> None:
    await ctx.goto("/search?category=electronics")
    await ctx.select("select[data-test-id='filter-category']", "electronics")
    await ctx.fill("input[data-test-id='filter-max-price']", "1000")
    await ctx.fill("input[data-test-id='filter-min-rating']", "4.5")
    await ctx.click("button[data-test-id='btn-apply-filters']")
    await ctx.click("a[data-test-id='card-product-p_laptop_studio']")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    await ctx.click("a[data-test-id='link-cart']")
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    await ctx.click("button[data-test-id='btn-place-order']")


async def solve_a3_configure_bundle(ctx: BrowserCtx) -> None:
    # Add laptop with the right variant
    await ctx.goto("/product/p_laptop_studio")
    await ctx.select("select[data-test-id='select-variant']", "v_lt_32_1tb")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Add mouse
    await ctx.goto("/product/p_mouse_wireless")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Add keyboard
    await ctx.goto("/product/p_kb_mech")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Checkout
    await ctx.click("a[data-test-id='link-cart']")
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    await ctx.click("button[data-test-id='btn-place-order']")


async def solve_b1_add_address(ctx: BrowserCtx) -> None:
    await ctx.goto("/account/addresses")
    await ctx.fill("input[data-test-id='input-addr-label']", "Beach House")
    await ctx.fill("input[data-test-id='input-addr-full-name']",
                   "Alice Anderson")
    await ctx.fill("input[data-test-id='input-addr-line1']", "17 Ocean Drive")
    await ctx.fill("input[data-test-id='input-addr-city']", "Montauk")
    await ctx.fill("input[data-test-id='input-addr-state']", "NY")
    await ctx.fill("input[data-test-id='input-addr-zip']", "11954")
    await ctx.check("input[data-test-id='cb-set-default']")
    await ctx.click("button[data-test-id='btn-save-address']")


async def solve_b2_track_and_return(ctx: BrowserCtx) -> None:
    await ctx.goto("/account/orders")
    await ctx.click("a[data-test-id='link-order-ORD-EXISTING-1234']")
    # Open tracking modal page (in-place, since popup window won't be
    # navigable from here)
    await ctx.goto("/account/orders/ORD-EXISTING-1234/track",
                   reasoning="View tracking before initiating return.")
    await ctx.goto("/account/returns/new?order_id=ORD-EXISTING-1234")
    await ctx.check("input[data-test-id='cb-return-item-ln_mouse']")
    await ctx.select("select[data-test-id='select-return-reason']",
                     "defective")
    await ctx.click("input[data-test-id='radio-refund-original']")
    await ctx.click("button[data-test-id='btn-submit-return']")


async def solve_b3_account_overhaul(ctx: BrowserCtx) -> None:
    # 1. Set Work as default address
    await ctx.goto("/account/addresses")
    await ctx.click("button[data-test-id='btn-set-default-addr_work']")
    # 2. Add a backup payment method
    await ctx.goto("/account/payments")
    await ctx.fill("input[data-test-id='input-pay-nickname']", "Backup Card")
    await ctx.fill("input[data-test-id='input-pay-label']", "Backup Card")
    await ctx.fill("input[data-test-id='input-card-number']",
                   "4111111111111111")
    await ctx.fill("input[data-test-id='input-card-expires']", "12/29")
    await ctx.fill("input[data-test-id='input-card-cvv']", "123")
    await ctx.check("input[data-test-id='cb-set-default-pay']")
    await ctx.click("button[data-test-id='btn-save-payment']")
    # 3. Enable 2FA
    await ctx.goto("/account/security")
    await ctx.fill("input[data-test-id='input-2fa-code']", "123456")
    await ctx.click("button[data-test-id='btn-enable-2fa']")


async def solve_c1_promo_partial(ctx: BrowserCtx) -> None:
    # Add laptop + t-shirt
    await ctx.goto("/product/p_laptop_studio")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    await ctx.goto("/product/p_clothing_tshirt")
    await ctx.select("select[data-test-id='select-variant']", "v_ts_m_blk")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Checkout
    await ctx.click("a[data-test-id='link-cart']")
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    # Apply promo
    await ctx.fill("input[data-test-id='input-promo-code']", "TECH20")
    await ctx.click("button[data-test-id='btn-apply-promo']")
    # Place order
    await ctx.click("button[data-test-id='btn-place-order']")


async def solve_c2_split_shipping(ctx: BrowserCtx) -> None:
    # Add headphones
    await ctx.goto("/product/p_hp_studio")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Add mouse
    await ctx.goto("/product/p_mouse_wireless")
    await ctx.click("button[data-test-id='btn-add-to-cart']")

    # Go to cart and configure per-line options
    await ctx.goto("/cart")
    # Need to grab the line ids by reading the page. Easiest: backend
    # snapshot.
    snap = ctx.http.get(f"{ctx.server_url}/_harness/state").json()
    hp_line = next(
        l for l in snap["cart"]["items"]
        if l["product_id"] == "p_hp_studio"
    )
    mouse_line = next(
        l for l in snap["cart"]["items"]
        if l["product_id"] == "p_mouse_wireless"
    )
    # Configure headphone line: home + gift wrap + message
    await ctx.click(f"summary[data-test-id='toggle-line-options-{hp_line['id']}']")
    await ctx.check(f"input[data-test-id='cb-gift-wrap-{hp_line['id']}']")
    await ctx.fill(
        f"input[data-test-id='input-gift-message-{hp_line['id']}']",
        "Happy birthday",
    )
    await ctx.select(
        f"select[data-test-id='select-ship-address-{hp_line['id']}']",
        "addr_home",
    )
    await ctx.click(f"button[data-test-id='btn-save-line-{hp_line['id']}']")
    # Configure mouse line: work, no gift wrap
    await ctx.click(f"summary[data-test-id='toggle-line-options-{mouse_line['id']}']")
    await ctx.select(
        f"select[data-test-id='select-ship-address-{mouse_line['id']}']",
        "addr_work",
    )
    await ctx.click(f"button[data-test-id='btn-save-line-{mouse_line['id']}']")
    # Place order
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    await ctx.click("button[data-test-id='btn-place-order']")


async def solve_c3_subscription(ctx: BrowserCtx) -> None:
    await ctx.goto("/product/p_pet_food")
    # Open subscription form (it's hidden initially)
    await ctx.page.evaluate(
        "document.getElementById('subscribe-form').classList.remove('hidden')"
    )
    await ctx.select("select[data-test-id='select-cadence']", "weekly")
    await ctx.fill("input[data-test-id='input-deliveries']", "4")
    await ctx.select("select[data-test-id='select-sub-address']", "addr_home")
    await ctx.select("select[data-test-id='select-sub-payment']", "pay_visa")
    await ctx.click("button[data-test-id='btn-create-subscription']")


# --------------------------------------------------------------------------- #
# Very-hard tasks (A4, B4, C4) — added May 2026 alongside the new tasks.
# These exist primarily as verifier sanity gates: if the oracle scores < 1.0,
# the task is unsolvable as designed.
# --------------------------------------------------------------------------- #

async def solve_a4_home_office_bundle(ctx: BrowserCtx) -> None:
    """4-item electronics bundle under $550 → Work + PayPal.

    Note: per-line address is set in the cart via the line-options
    `<details>` toggle (mirrors C2's pattern). Final payment is
    selected at the /checkout/review step's dropdown.
    """
    # Add the 4 required items
    for pid in ("p_monitor_27", "p_kb_mech",
                "p_mouse_ergonomic", "p_charger"):
        await ctx.goto(f"/product/{pid}")
        await ctx.click("button[data-test-id='btn-add-to-cart']")

    # Per-line: ship all four to Work
    await ctx.goto("/cart")
    snap = ctx.http.get(f"{ctx.server_url}/_harness/state").json()
    for line in snap["cart"]["items"]:
        lid = line["id"]
        await ctx.click(
            f"summary[data-test-id='toggle-line-options-{lid}']"
        )
        await ctx.select(
            f"select[data-test-id='select-ship-address-{lid}']",
            "addr_work",
        )
        await ctx.click(f"button[data-test-id='btn-save-line-{lid}']")

    # Through checkout → pay with PayPal at the review step
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    await ctx.select(
        "select[data-test-id='select-final-payment']", "pay_paypal",
    )
    await ctx.click("button[data-test-id='btn-place-order']")


async def solve_b4_subscription_juggle(ctx: BrowserCtx) -> None:
    """Cancel dogfood sub + create treats sub + enable 2FA + partial return."""
    # 1. Cancel existing Premium Dog Food subscription
    await ctx.goto("/account/subscriptions")
    await ctx.click(
        "button[data-test-id='btn-cancel-sub-sub_existing_dogfood']",
        reasoning="Cancel the pre-seeded active dog food subscription.",
    )

    # 2. Create NEW subscription for Dog TREATS — biweekly, 6, Work, PayPal
    await ctx.goto("/product/p_pet_treats")
    # The subscribe form is collapsed behind a toggle button
    await ctx.click("button[data-test-id='btn-toggle-subscribe']")
    await ctx.select("select[data-test-id='select-cadence']", "biweekly")
    await ctx.fill("input[data-test-id='input-deliveries']", "6")
    await ctx.select("select[data-test-id='select-sub-address']", "addr_work")
    await ctx.select("select[data-test-id='select-sub-payment']", "pay_paypal")
    await ctx.click("button[data-test-id='btn-create-subscription']")

    # 3. Enable 2FA
    await ctx.goto("/account/security")
    await ctx.fill("input[data-test-id='input-2fa-code']", "123456")
    await ctx.click("button[data-test-id='btn-enable-2fa']")

    # 4. Initiate return on ORD-B4-9999 for Bluetooth Speaker only
    await ctx.goto("/account/returns/new?order_id=ORD-B4-9999")
    await ctx.check("input[data-test-id='cb-return-item-ln_speaker']")
    await ctx.select("select[data-test-id='select-return-reason']",
                     "changed_mind")
    await ctx.click("input[data-test-id='radio-refund-credit']")
    await ctx.click("button[data-test-id='btn-submit-return']")


async def solve_c4_mega_checkout(ctx: BrowserCtx) -> None:
    """3 items × 3 shipping configs + TECH20 promo on laptop only + Visa."""
    # Add Studio Laptop 14 (NOT the Pro)
    await ctx.goto("/product/p_laptop_studio")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Add Cotton T-Shirt in size M Black
    await ctx.goto("/product/p_clothing_tshirt")
    await ctx.select("select[data-test-id='select-variant']", "v_ts_m_blk")
    await ctx.click("button[data-test-id='btn-add-to-cart']")
    # Add standard Wireless Mouse (NOT ergonomic / gaming)
    await ctx.goto("/product/p_mouse_wireless")
    await ctx.click("button[data-test-id='btn-add-to-cart']")

    # Configure per-line shipping in the cart
    await ctx.goto("/cart")
    snap = ctx.http.get(f"{ctx.server_url}/_harness/state").json()
    laptop_line = next(
        l for l in snap["cart"]["items"]
        if l["product_id"] == "p_laptop_studio"
    )
    tshirt_line = next(
        l for l in snap["cart"]["items"]
        if l["product_id"] == "p_clothing_tshirt"
    )
    mouse_line = next(
        l for l in snap["cart"]["items"]
        if l["product_id"] == "p_mouse_wireless"
    )
    # Laptop → Work (no gift wrap)
    await ctx.click(
        f"summary[data-test-id='toggle-line-options-{laptop_line['id']}']"
    )
    await ctx.select(
        f"select[data-test-id='select-ship-address-{laptop_line['id']}']",
        "addr_work",
    )
    await ctx.click(f"button[data-test-id='btn-save-line-{laptop_line['id']}']")
    # T-shirt → Home, gift wrap, "Happy Birthday Mom!"
    await ctx.click(
        f"summary[data-test-id='toggle-line-options-{tshirt_line['id']}']"
    )
    await ctx.check(f"input[data-test-id='cb-gift-wrap-{tshirt_line['id']}']")
    await ctx.fill(
        f"input[data-test-id='input-gift-message-{tshirt_line['id']}']",
        "Happy Birthday Mom!",
    )
    await ctx.select(
        f"select[data-test-id='select-ship-address-{tshirt_line['id']}']",
        "addr_home",
    )
    await ctx.click(f"button[data-test-id='btn-save-line-{tshirt_line['id']}']")
    # Mouse → Home, no gift wrap
    await ctx.click(
        f"summary[data-test-id='toggle-line-options-{mouse_line['id']}']"
    )
    await ctx.select(
        f"select[data-test-id='select-ship-address-{mouse_line['id']}']",
        "addr_home",
    )
    await ctx.click(f"button[data-test-id='btn-save-line-{mouse_line['id']}']")

    # Proceed → checkout → review with TECH20 promo + Visa
    await ctx.click("a[data-test-id='btn-proceed-checkout']")
    await ctx.click("a[data-test-id='btn-continue-payment']")
    await ctx.click("a[data-test-id='btn-continue-review']")
    await ctx.fill("input[data-test-id='input-promo-code']", "TECH20")
    await ctx.click("button[data-test-id='btn-apply-promo']")
    await ctx.select(
        "select[data-test-id='select-final-payment']", "pay_visa",
    )
    await ctx.click("button[data-test-id='btn-place-order']")


SOLVERS = {
    "A1/buy_wireless_mouse":     solve_a1_buy_wireless_mouse,
    "A2/filter_laptop":          solve_a2_filter_laptop,
    "A3/configure_bundle":       solve_a3_configure_bundle,
    "A4/home_office_bundle":     solve_a4_home_office_bundle,
    "B1/add_address":            solve_b1_add_address,
    "B2/track_and_return":       solve_b2_track_and_return,
    "B3/account_overhaul":       solve_b3_account_overhaul,
    "B4/subscription_juggle":    solve_b4_subscription_juggle,
    "C1/promo_partial":          solve_c1_promo_partial,
    "C2/split_shipping_gift":    solve_c2_split_shipping,
    "C3/subscription_loyalty":   solve_c3_subscription,
    "C4/mega_checkout":          solve_c4_mega_checkout,
}
