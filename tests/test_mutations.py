"""Mutation correctness + invariants."""

from __future__ import annotations

import pytest

from server import mutations
from server.state import Cart


def test_login_succeeds_with_alice(fresh_state):
    s = fresh_state("A1/buy_wireless_mouse")
    s.current_user_id = None
    r = mutations.login(s, "alice@example.com", "password123")
    assert r["ok"] and s.current_user_id == "u_alice"


def test_login_fails_with_bad_password(fresh_state):
    s = fresh_state("A1/buy_wireless_mouse")
    s.current_user_id = None
    r = mutations.login(s, "alice@example.com", "wrong")
    assert not r["ok"]
    assert any(f.get("kind") == "error" for f in s.flash_messages)


def test_add_to_cart_variant_required(fresh_state):
    s = fresh_state("A1/buy_wireless_mouse")
    # Tshirt requires a variant
    r = mutations.add_to_cart(s, "p_clothing_tshirt", 1, None)
    assert not r["ok"] and r["error"] == "variant required"


def test_add_to_cart_oos_blocked(fresh_state):
    s = fresh_state("A1/buy_wireless_mouse")
    r = mutations.add_to_cart(s, "p_book_oos", 1)
    assert not r["ok"] and r["error"] == "out of stock"


def test_add_to_cart_ok(fresh_state):
    s = fresh_state("A1/buy_wireless_mouse")
    r = mutations.add_to_cart(s, "p_mouse_wireless", 2)
    assert r["ok"]
    assert len(s.cart.items) == 1
    assert s.cart.items[0].quantity == 2


def test_apply_invalid_promo(fresh_state):
    s = fresh_state("C1/promo_partial")
    r = mutations.apply_promo(s, "DOESNOTEXIST")
    assert not r["ok"]


def test_apply_expired_promo(fresh_state):
    s = fresh_state("C1/promo_partial")
    mutations.add_to_cart(s, "p_laptop_studio", 1)
    r = mutations.apply_promo(s, "EXPIRED10")
    assert not r["ok"] and r["error"] == "expired"


def test_apply_promo_min_purchase_not_met(fresh_state):
    s = fresh_state("C1/promo_partial")
    # BIGSAVE50 needs $500
    mutations.add_to_cart(s, "p_mouse_wireless", 1)
    r = mutations.apply_promo(s, "BIGSAVE50")
    assert not r["ok"]


def test_apply_promo_category_mismatch(fresh_state):
    s = fresh_state("C1/promo_partial")
    # TECH20 only applies to electronics
    mutations.add_to_cart(s, "p_clothing_tshirt", 1, "v_ts_m_blk")
    r = mutations.apply_promo(s, "TECH20")
    assert not r["ok"]


def test_apply_promo_valid(fresh_state):
    s = fresh_state("C1/promo_partial")
    mutations.add_to_cart(s, "p_laptop_studio", 1)
    r = mutations.apply_promo(s, "TECH20")
    assert r["ok"] and s.cart.applied_promo == "TECH20"


def test_place_order_full_pipeline(fresh_state):
    s = fresh_state("A1/buy_wireless_mouse")
    mutations.add_to_cart(s, "p_mouse_wireless", 1)
    r = mutations.place_order(s, payment_id="pay_visa")
    assert r["ok"]
    assert len(s.orders) == 1
    order = list(s.orders.values())[0]
    # Total = subtotal*(1.085) + 5.99
    expected_total = round(29.99 * 1.085 + 5.99, 2)
    assert abs(order.total - expected_total) < 0.01
    # Cart cleared
    assert s.cart.items == []
    # Inventory decremented
    assert s.products["p_mouse_wireless"].stock == 57


def test_place_order_with_promo_discount(fresh_state):
    s = fresh_state("C1/promo_partial")
    mutations.add_to_cart(s, "p_laptop_studio", 1)
    mutations.apply_promo(s, "TECH20")
    r = mutations.place_order(s, payment_id="pay_visa")
    assert r["ok"]
    order = list(s.orders.values())[0]
    expected = round(899.99 * 0.20, 2)
    assert abs(order.discount - expected) < 0.05


def test_initiate_return(fresh_state):
    s = fresh_state("B2/track_and_return")
    r = mutations.initiate_return(
        s, "ORD-EXISTING-1234", ["ln_mouse"],
        "defective", "original_payment",
    )
    assert r["ok"]
    assert len(s.returns) == 1
    ret = list(s.returns.values())[0]
    assert ret.item_ids == ["ln_mouse"]
    assert ret.reason == "defective"


def test_add_address_form_validation(fresh_state):
    s = fresh_state("B1/add_address")
    # Missing required fields
    r = mutations.add_address(s, "Label", "", "", "", "", "", "")
    assert not r["ok"]
    # Complete fields
    r = mutations.add_address(
        s, "Beach House", "Alice Anderson", "17 Ocean Drive",
        "", "Montauk", "NY", "11954", set_default=True,
    )
    assert r["ok"]
    u = s.users["u_alice"]
    assert any(a.label == "Beach House" and a.is_default
               for a in u.addresses.values())
    # Old default should be unset
    assert not s.users["u_alice"].addresses["addr_home"].is_default


def test_add_payment_method_validation(fresh_state):
    s = fresh_state("B3/account_overhaul")
    # Missing card fields
    r = mutations.add_payment_method(
        s, label="X", kind="credit_card",
        card_number="", expires="", cvv="",
    )
    assert not r["ok"]
    # Complete
    r = mutations.add_payment_method(
        s, label="Backup Card", kind="credit_card",
        card_number="4111111111111111", expires="12/29", cvv="123",
        nickname="Backup Card", set_default=True,
    )
    assert r["ok"]
    u = s.users["u_alice"]
    assert any(pm.is_default and "backup" in pm.label.lower()
               for pm in u.payment_methods.values())


def test_enable_two_fa(fresh_state):
    s = fresh_state("B3/account_overhaul")
    r = mutations.enable_two_fa(s, "wrong")
    assert not r["ok"]
    r = mutations.enable_two_fa(s, "123456")
    assert r["ok"]
    assert s.users["u_alice"].two_fa_enabled


def test_create_subscription_loyalty(fresh_state):
    s = fresh_state("C3/subscription_loyalty")
    r = mutations.create_subscription(
        s, product_id="p_pet_food", cadence="weekly",
        deliveries=4, address_id="addr_home", payment_id="pay_visa",
        quantity=1,
    )
    assert r["ok"]
    assert r["loyalty_discount_pct"] == 0.10
    sub = list(s.subscriptions.values())[0]
    assert sub.deliveries_remaining == 4 and sub.cadence == "weekly"
    assert abs(sub.loyalty_discount_pct - 0.10) < 0.001
