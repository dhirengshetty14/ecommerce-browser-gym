# TASKS — per-task briefs and milestone tables

All **12 tasks** across 3 categories and 4 difficulty tiers
(easy / medium / hard / **very hard**). Each milestone shows its
weight, whether it's required for `success=True`, and the
`failure_category` label the verifier emits when missed (added in the
May 2026 τ-bench-inspired audit).

Total tasks per category:
- **A — Product Discovery & Purchase**: 4 (A1 easy, A2 medium, A3 hard, **A4 very hard**)
- **B — Account & Order Management**: 4 (B1 easy, B2 medium, B3 hard, **B4 very hard**)
- **C — Complex Checkout**: 4 (C1 medium, C2 medium, C3 hard, **C4 very hard**)

---

## Category A — Product Discovery & Purchase

### A1 — easy/buy_wireless_mouse

**Brief**: You're logged in as Alice. Find and buy exactly 1 unit of
the 'Wireless Mouse' (NOT the 'Wireless Gaming Mouse', NOT the
'Wireless Ergonomic Mouse', NOT the 'Wireless Mini Mouse'). Use Home
address + Visa. Submit when confirmation shows the order ID.

**Adversarial elements**: 4 distractor mice with similar names
(`p_mouse_gaming`, `p_mouse_ergonomic`, `p_mouse_mini`, `p_mouse_trackpad`).

| Milestone | Weight | Required | Failure category if missed |
|---|---|---|---|
| viewed_product_page | 0.15 | | never_viewed_product |
| added_target_to_cart | 0.20 | | wrong_product_in_cart |
| avoided_all_distractors | 0.10 | | picked_distractor_product |
| reached_checkout | 0.10 | | never_reached_checkout |
| order_placed | 0.30 | ✓ | goal_incomplete_no_order |
| on_confirmation_page | 0.10 | | missed_confirmation_page |
| home_address_used | 0.05 | | wrong_shipping_address |

### A2 — medium/filter_laptop

**Brief**: Find a laptop in the Electronics category under $1,000 with
a rating of 4.5 stars or higher. Buy 1 unit (default variant is fine).
Use Home + Visa.

**Adversarial elements**: Only `p_laptop_studio` ($899.99, 4.6★)
satisfies ALL three constraints. Other laptops fail at least one:
- `p_laptop_pro` — over $1000
- `p_laptop_budget` — rating too low (3.6★)
- `p_laptop_studio_pro` — over $1000
- `p_laptop_creator` — rating too low (4.4★)

| Milestone | Weight | Required | Failure category if missed |
|---|---|---|---|
| searched_or_filtered_laptops | 0.20 | | never_searched |
| viewed_an_electronics_laptop | 0.15 | | (default) |
| ordered_a_laptop | 0.30 | ✓ | (default) |
| under_1000_subtotal | 0.20 | | (default) |
| ordered_product_rating_ge_45 | 0.15 | | (default) |

### A3 — hard/configure_bundle

**Brief**: Configure and buy ONE laptop with the '32GB RAM / 1TB SSD'
variant (`v_lt_32_1tb`). Add the Wireless Mouse and the Mechanical
Keyboard as accessories. Combined cart subtotal must be under $1,900.
Ship to Home with Visa.

**Adversarial elements**: variant selection required, exact 3-item
count enforced, budget constraint.

| Milestone | Weight | Required |
|---|---|---|
| opened_variant_picker_on_laptop | 0.10 | |
| ordered_correct_laptop_variant | 0.25 | |
| ordered_wireless_mouse | 0.15 | |
| ordered_mechanical_keyboard | 0.15 | |
| subtotal_under_1900 | 0.20 | |
| three_items_in_order | 0.10 | ✓ |
| on_confirmation_page | 0.05 | |

### A4 — very-hard/home_office_bundle  🔥

**Brief**: Build a complete home office bundle in a single order:
(1) ONE 27-inch monitor (the 1440p one, not the 24-inch),
(2) ONE Mechanical Keyboard (not the wireless one, not the mini
variant, not the membrane keyboard),
(3) ONE Wireless Ergonomic Mouse (NOT the standard Wireless Mouse and
NOT the Gaming Mouse),
(4) ONE USB-C Fast Charger.
ALL FOUR items must be in the 'electronics' category — the 'office'
category contains adversarial look-alikes. Cart subtotal MUST be
under $550. Ship the entire order to your Work address (not Home).
Pay with PayPal (not Visa). Submit when the confirmation page shows
all 4 line items.

**Solvable at**: $329.99 + $119.99 + $49.99 + $29.99 = **$529.96** (under $550)

**Adversarial elements**:
- 2 monitors (24" vs 27") — must pick 27"
- 4 keyboards (mechanical, wireless, mini-mech, membrane) — must pick mechanical
- 4 mice — must pick **ergonomic** specifically (not Wireless Mouse!)
- `p_office_display` in 'office' category looks like a monitor — wrong category
- Non-default shipping address (Work) + non-default payment (PayPal)

| Milestone | Weight | Required | Failure category if missed |
|---|---|---|---|
| all_four_required_items | 0.20 | ✓ | missing_required_item |
| no_forbidden_distractor | 0.15 | | picked_distractor_product |
| exactly_four_line_items | 0.10 | | wrong_item_count |
| all_items_electronics_category | 0.10 | | wrong_category |
| subtotal_under_550 | 0.15 | | over_budget |
| shipped_to_work_address | 0.10 | | wrong_shipping_address |
| paid_with_paypal | 0.10 | | wrong_payment_method |
| on_confirmation_page | 0.10 | | (default) |

---

## Category B — Account & Order Management

### B1 — easy/add_address

**Brief**: Add a new 'Beach House' address (line1: 17 Ocean Drive,
city: Montauk, state: NY, zip: 11954). Set as default.

| Milestone | Weight | Required |
|---|---|---|
| navigated_to_addresses | 0.20 | |
| address_added | 0.30 | ✓ |
| address_fields_correct | 0.20 | |
| address_set_as_default | 0.30 | ✓ |

### B2 — medium/track_and_return

**Brief**: View tracking on order `ORD-EXISTING-1234`, then initiate a
return for the Wireless Mouse only (reason: defective, refund:
original payment).

| Milestone | Weight | Required |
|---|---|---|
| navigated_to_orders | 0.15 | |
| opened_order_detail | 0.15 | |
| opened_tracking_modal | 0.15 | |
| return_initiated | 0.25 | ✓ |
| return_is_for_mouse_only | 0.20 | ✓ |
| return_reason_defective | 0.05 | |
| refund_method_original_payment | 0.05 | |

### B3 — hard/account_overhaul

**Brief**: In one session: (1) set Work as default address, (2) add a
backup card (4111111111111111 exp 12/29 CVV 123) and set as default
payment, (3) enable 2FA with code 123456.

| Milestone | Weight | Required |
|---|---|---|
| navigated_to_account | 0.10 | |
| set_work_as_default_address | 0.30 | ✓ |
| backup_card_added_and_default | 0.30 | ✓ |
| two_fa_enabled | 0.30 | ✓ |

### B4 — very-hard/subscription_juggle  🔥

**Brief**: You currently have one ACTIVE subscription for Premium Dog
Food. Make these account changes IN A SINGLE SESSION:
(1) Cancel the existing Premium Dog Food subscription.
(2) Create a NEW subscription for the Premium Dog TREATS — biweekly
cadence, exactly 6 deliveries, ship to your Work address, pay with
PayPal (NOT Visa).
(3) Enable two-factor authentication with code '123456'.
(4) Initiate a return on the existing order for the Bluetooth Speaker
ONLY (not the Mouse) — reason 'changed_mind', refund as 'store_credit'
(you want the 5% bonus).
Submit when all four changes are reflected in your account.

**Pre-seeded state**:
- `sub_existing_dogfood` — active Premium Dog Food subscription
- `ORD-B4-9999` — delivered order with both Wireless Mouse AND
  Bluetooth Speaker (agent must return speaker ONLY)

**Adversarial elements**:
- 2 subscribable pet products (`p_pet_food` vs `p_pet_treats`) — must
  cancel old, create new for different product
- 2-item order — must return ONE item only
- Non-default payment (PayPal) for new subscription
- Non-default address (Work) for new subscription

| Milestone | Weight | Required | Failure category if missed |
|---|---|---|---|
| dogfood_sub_cancelled | 0.20 | ✓ | failed_to_cancel_subscription |
| dog_treats_sub_created_correctly | 0.30 | ✓ | wrong_subscription_setup |
| two_fa_enabled | 0.15 | ✓ | two_fa_not_enabled |
| speaker_only_return_with_correct_options | 0.25 | ✓ | wrong_return_setup |
| avoided_returning_mouse | 0.10 | | returned_wrong_item |

---

## Category C — Complex Checkout

### C1 — medium/promo_partial

**Brief**: Add 1 Studio Laptop AND 1 Cotton T-Shirt. Apply TECH20
promo (20% off electronics only — applies to the laptop, not the
t-shirt). Place the order using Home + Visa.

**Adversarial elements**: 3 promo codes exist; only TECH20 is correct.
Cotton T-Shirt has 5 variants (S/M/L Black, M/L White) — agent must
pick one before adding.

| Milestone | Weight | Required | Failure category if missed |
|---|---|---|---|
| both_items_in_order | 0.25 | ✓ | missing_required_item |
| tech20_applied | 0.30 | ✓ | wrong_or_missing_promo |
| discount_is_20pct_of_laptop_only | 0.30 | ✓ | discount_applied_to_wrong_line |
| on_confirmation_page | 0.15 | | missed_confirmation_page |

### C2 — medium/split_shipping_gift

**Brief**: Buy 1 Bluetooth Headphone **Studio** (NOT Premium, NOT
Lite, NOT Studio Pro!) AND 1 Wireless Mouse. Ship the headphones to
Home with gift wrap (message: 'Happy birthday'). Ship the mouse to
Work with NO gift wrap. Pay with Visa.

**Adversarial elements**: 4 Bluetooth headphones in the catalog — only
Studio satisfies. Line-level shipping option must be enabled (hidden
inside `<details>` toggle on the cart page).

| Milestone | Weight | Required |
|---|---|---|
| two_items_ordered | 0.15 | ✓ |
| headphones_home_with_giftwrap | 0.30 | ✓ |
| mouse_work_no_giftwrap | 0.25 | ✓ |
| two_shipments_in_confirmation | 0.20 | ✓ |
| on_confirmation_page | 0.10 | |

### C3 — hard/subscription_loyalty

**Brief**: Set up a weekly subscription for Premium Dog Food (4
deliveries, Home, Visa). Gold-tier loyalty discount (10%) should
auto-apply.

**Adversarial elements**: `p_pet_treats` exists in the catalog with
the same brand name (Wellness) — must pick `p_pet_food`.

| Milestone | Weight | Required |
|---|---|---|
| on_pet_food_product_page | 0.10 | |
| subscription_created | 0.40 | ✓ |
| loyalty_10pct_recorded | 0.30 | ✓ |
| on_subscription_confirmation | 0.20 | |

### C4 — very-hard/mega_checkout  🔥

**Brief**: Complex multi-item checkout with all the constraints:
(1) Add 1 Studio Laptop 14 (NOT the Pro 14) to cart.
(2) Add 1 Cotton T-Shirt — Size M, color BLACK (variant `v_ts_m_blk`).
(3) Add 1 Wireless Mouse (the standard one, NOT ergonomic or gaming).
Then in the cart: ship the LAPTOP to Work, the T-SHIRT to Home with
gift wrap and message 'Happy Birthday Mom!', and the MOUSE to Home
with NO gift wrap. Apply promo code 'TECH20' — it discounts only the
laptop. Pay with Visa. Place the order.

**Adversarial elements** (the kitchen-sink stress test):
- Studio Laptop 14 vs Studio Laptop **Pro** 14 — must pick the
  non-Pro
- Cotton T-Shirt variant must be exactly M Black (not S Black, not M
  White)
- 5 wireless mice in catalog — must pick the **standard** (not
  ergonomic, gaming, mini, or trackpad)
- 3 different shipping configurations on 3 line items
- Gift wrap on ONE line only (the t-shirt)
- Custom gift message with two specific phrases ("Happy Birthday" and
  "Mom")
- Promo TECH20 discounts laptop only (verifier checks the math exactly)
- 3 promo codes exist; 2 are wrong/expired

Combines C1's promo logic + C2's split shipping + A3's variant flow
into a single 9-milestone episode.

| Milestone | Weight | Required | Failure category if missed |
|---|---|---|---|
| all_three_required_items | 0.15 | ✓ | missing_required_item |
| no_distractor_picked | 0.10 | | picked_distractor_product |
| tshirt_size_m_black | 0.10 | | wrong_variant |
| laptop_shipped_to_work | 0.10 | | wrong_shipping_address |
| tshirt_home_with_giftwrap_message | 0.15 | | wrong_gift_options |
| mouse_home_no_giftwrap | 0.10 | | wrong_gift_options |
| tech20_applied_to_laptop_only | 0.15 | ✓ | discount_applied_to_wrong_line |
| paid_with_visa | 0.05 | | wrong_payment_method |
| on_confirmation_page | 0.10 | | (default) |

---

## How partial credit works

Score = sum of weights of fired milestones, divided by total weight
(which is normalized to 1.00 per task). `success=True` requires:
1. ALL `required_for_success` milestones fired, AND
2. Score ≥ 0.999

If an agent does most of A1 but doesn't reach the confirmation page:
- viewed_product_page ✓ → +0.15
- added_target_to_cart ✓ → +0.20
- avoided_all_distractors ✓ → +0.10
- reached_checkout ✓ → +0.10
- order_placed ✓ → +0.30 (required ✓)
- on_confirmation_page ✗
- home_address_used ✓ → +0.05

**Score: 0.90, success: False** (missing the 0.10 non-required
milestone caps the score below the 0.999 success threshold).

If the agent misses any `required_for_success` milestone — even with
everything else right — `success=False`.

## Failure mode taxonomy (τ-bench-inspired)

Every missed milestone now emits an explicit `failure_category` label.
The verifier's `evaluate()` output includes a `primary_failure_category`
field — the failure category of the first unfired required milestone
(or the highest-weight unfired milestone if all required ones fired).

Common categories across tasks:
- `goal_incomplete_no_order` — never placed an order
- `wrong_product_in_cart` — added the wrong product
- `picked_distractor_product` — fell for an adversarial look-alike
- `missing_required_item` — multi-item task missing a required SKU
- `wrong_variant` — picked the wrong size/color/spec
- `wrong_shipping_address` — used Home when Work was required (or vice versa)
- `wrong_payment_method` — used Visa when PayPal was required
- `wrong_or_missing_promo` — didn't apply the right promo code
- `discount_applied_to_wrong_line` — promo math wrong
- `wrong_gift_options` — gift wrap on the wrong line, or wrong message
- `over_budget` — cart subtotal exceeded the constraint
- `failed_to_cancel_subscription` — didn't cancel the right sub
- `wrong_subscription_setup` — new sub had wrong cadence/address/payment
- `two_fa_not_enabled` — security setting not toggled
- `wrong_return_setup` — partial-return options didn't match brief
- `returned_wrong_item` — initiated return for the wrong line

## How adversarial elements interact with milestones

- **Wireless Mouse distractors (A1, C2, C4)**: there are now 4
  non-target mice; `avoided_all_distractors` rejects any of them
  appearing in the order.
- **Laptop distractors (A2, A4, C4)**: 5 laptops total; only specific
  ones satisfy the price+rating+category constraints.
- **Cotton T-Shirt vs Polo vs Long-Sleeve vs Graphic vs Tank (C1, C4)**:
  5 cotton clothing items with similar names; only `p_clothing_tshirt`
  is correct.
- **Bluetooth Headphone Premium/Studio/Lite/Studio Pro (C2, C4)**:
  4 headphones — only the specific one named in the brief satisfies.
- **TECH20 vs BIGSAVE50 vs EXPIRED10 (C1, C4)**: only TECH20 is the
  right promo; the others either don't satisfy or are expired.
- **Office vs electronics category (A4)**: Office Display Pro looks
  like a monitor but lives in `office`, failing `all_items_electronics_category`.
- **`p_pet_food` vs `p_pet_treats` (B4, C3)**: both subscribable, same
  brand — must pick the one in the brief.
- **Studio Laptop vs Studio Laptop Pro (C4)**: same name root, +Pro
  suffix — must pick the non-Pro.
- **5 t-shirt variants (C1, C4)**: variant selection mandatory; only
  `v_ts_m_blk` satisfies C4.

These aren't just decorative — each adversarial element maps directly
to a specific milestone (or failure_category label) the agent has to
recognize and avoid.
