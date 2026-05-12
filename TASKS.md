# TASKS — per-task briefs and milestone tables

All 9 tasks. Each milestone shows its weight and whether it's required
for `success=True`.

---

## Category A — Product Discovery & Purchase

### A1 — easy/buy_specific_product

**Brief**: Buy 1 unit of 'Wireless Mouse' (NOT the Wireless Gaming Mouse).
Use Home address + Visa. Submit when confirmation shows the order ID.

| Milestone | Weight | Required |
|---|---|---|
| viewed_product_page | 0.15 | |
| added_target_to_cart | 0.20 | |
| avoided_distractor (no gaming mouse) | 0.10 | |
| reached_checkout | 0.10 | |
| order_placed | 0.30 | ✓ |
| on_confirmation_page | 0.10 | |
| home_address_used | 0.05 | |

### A2 — medium/filter_laptop

**Brief**: Find a laptop in Electronics under $1,000 with ≥4.5★. Buy 1.
Home + Visa.

| Milestone | Weight | Required |
|---|---|---|
| searched_or_filtered_laptops | 0.20 | |
| viewed_an_electronics_laptop | 0.15 | |
| ordered_a_laptop | 0.30 | ✓ |
| under_1000_subtotal | 0.20 | |
| ordered_product_rating_ge_45 | 0.15 | |

### A3 — hard/configure_bundle

**Brief**: Configure laptop with 32GB/1TB variant + Wireless Mouse +
Mechanical Keyboard. Subtotal under $1900. Home + Visa.

| Milestone | Weight | Required |
|---|---|---|
| opened_variant_picker_on_laptop | 0.10 | |
| ordered_correct_laptop_variant | 0.25 | |
| ordered_wireless_mouse | 0.15 | |
| ordered_mechanical_keyboard | 0.15 | |
| subtotal_under_1900 | 0.20 | |
| three_items_in_order | 0.10 | ✓ |
| on_confirmation_page | 0.05 | |

---

## Category B — Account & Order Management

### B1 — easy/add_address

**Brief**: Add a new 'Beach House' address (line1: 17 Ocean Drive, city:
Montauk, state: NY, zip: 11954). Set as default.

| Milestone | Weight | Required |
|---|---|---|
| navigated_to_addresses | 0.20 | |
| address_added | 0.30 | ✓ |
| address_fields_correct | 0.20 | |
| address_set_as_default | 0.30 | ✓ |

### B2 — medium/track_and_return

**Brief**: View tracking on order ORD-EXISTING-1234, then initiate a
return for the Wireless Mouse only (reason: defective, refund: original
payment).

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
backup card and set as default payment, (3) enable 2FA.

| Milestone | Weight | Required |
|---|---|---|
| navigated_to_account | 0.10 | |
| set_work_as_default_address | 0.30 | ✓ |
| backup_card_added_and_default | 0.30 | ✓ |
| two_fa_enabled | 0.30 | ✓ |

---

## Category C — Complex Checkout

### C1 — medium/promo_partial

**Brief**: Buy 1 Studio Laptop + 1 Cotton T-Shirt. Apply TECH20 promo
(20% off electronics only — applies to the laptop, not the t-shirt).

| Milestone | Weight | Required |
|---|---|---|
| both_items_in_order | 0.25 | ✓ |
| tech20_applied | 0.30 | ✓ |
| discount_is_20pct_of_laptop_only | 0.30 | ✓ |
| on_confirmation_page | 0.15 | |

### C2 — medium/split_shipping_gift

**Brief**: Buy headphones AND mouse. Headphones → Home with gift wrap
("Happy birthday"). Mouse → Work, no gift wrap.

| Milestone | Weight | Required |
|---|---|---|
| two_items_ordered | 0.15 | ✓ |
| headphones_home_with_giftwrap | 0.30 | ✓ |
| mouse_work_no_giftwrap | 0.25 | ✓ |
| two_shipments_in_confirmation | 0.20 | ✓ |
| on_confirmation_page | 0.10 | |

### C3 — hard/subscription_loyalty

**Brief**: Set up a weekly subscription for Premium Dog Food (4
deliveries, Home, Visa). Gold-tier loyalty discount should auto-apply.

| Milestone | Weight | Required |
|---|---|---|
| on_pet_food_product_page | 0.10 | |
| subscription_created | 0.40 | ✓ |
| loyalty_10pct_recorded | 0.30 | ✓ |
| on_subscription_confirmation | 0.20 | |

---

## How partial credit works

If an agent does most of A1 but doesn't ever reach the confirmation
page:

- viewed_product_page ✓ → +0.15
- added_target_to_cart ✓ → +0.20
- avoided_distractor ✓ → +0.10
- reached_checkout ✓ → +0.10
- order_placed ✓ → +0.30
- on_confirmation_page ✗
- home_address_used ✓ → +0.05

**Score: 0.90, success: False** (full score but missed the
non-required confirmation milestone — wait, that's confusing. Let me
clarify: `success=True` requires score ≥ 0.999. So missing a 0.10
non-required milestone caps you at 0.90, success=False.)

If the agent missed the `order_placed` (required) milestone — even
with everything else right — `success=False`.

## How adversarial elements interact with milestones

- **Wireless Gaming Mouse distractor (A1)**: there's a dedicated
  `avoided_distractor` milestone — buying the gaming mouse loses 0.10
- **Out-of-stock book (Category A reuse)**: ordering it would fail the
  `ordered_product_was_in_stock` style check
- **TECH20 vs SAVE10 vs EXPIRED10 (C1)**: using the wrong code
  prevents the `tech20_applied` milestone from firing → -0.30
- **Office vs electronics category (A3)**: monitors miscategorized as
  `office` won't satisfy the `both_items_in_electronics_category`
  milestone

These aren't just decorative — each adversarial element maps directly
to a specific milestone the agent has to recognize.
