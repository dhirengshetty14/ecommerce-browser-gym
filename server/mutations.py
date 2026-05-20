"""Business-logic mutations.

Every state change in the gym goes through one of these functions.
Each returns a uniform ``{"ok": bool, ...}`` dict and appends to
``state.action_log`` so verifiers can attribute outcomes to specific
agent actions.

Critical design rule: **never bypass these and mutate state directly
from the FastAPI handlers**. Handlers should be thin wrappers that
parse args, call a mutation, and return its result.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from server import catalog
from server.state import (
    Address, Cart, CartItem, GymState, Order, OrderItem,
    PaymentMethod, ReturnRequest, RefundMethod, Shipment, ShipmentEvent,
    Subscription, User, flash, log_action,
)


TAX_RATE = 0.085
SHIPPING_FLAT = 5.99
GIFT_WRAP_FEE = 4.99


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _require_login(state: GymState) -> str | None:
    if state.current_user_id is None:
        flash(state, "error", "You must be logged in to do that.")
        return None
    return state.current_user_id


def _resolve_unit_price(state: GymState, product_id: str,
                       variant_id: str | None) -> float:
    p = state.products[product_id]
    if not variant_id:
        return p.base_price
    for v in p.variants:
        if v.id == variant_id:
            return p.base_price + v.price_delta
    return p.base_price


def _resolve_variant_label(state: GymState, product_id: str,
                          variant_id: str | None) -> str:
    if not variant_id:
        return ""
    p = state.products.get(product_id)
    if not p:
        return ""
    for v in p.variants:
        if v.id == variant_id:
            return v.label
    return ""


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

def login(state: GymState, email: str, password: str) -> dict[str, Any]:
    email = (email or "").strip().lower()
    user = next(
        (u for u in state.users.values() if u.email.lower() == email), None,
    )
    if user is None or user.password != password:
        log_action(state, "login_failed", email=email)
        flash(state, "error", "Invalid email or password.")
        return {"ok": False, "error": "invalid credentials"}
    state.current_user_id = user.id
    log_action(state, "login_ok", user_id=user.id)
    flash(state, "success", f"Welcome back, {user.full_name}.")
    return {"ok": True, "user_id": user.id}


def logout(state: GymState) -> dict[str, Any]:
    uid = state.current_user_id
    state.current_user_id = None
    log_action(state, "logout", user_id=uid)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Account: addresses, payment methods, 2FA
# --------------------------------------------------------------------------- #

def add_address(state: GymState, label: str, full_name: str, line1: str,
                line2: str = "", city: str = "", st: str = "",
                zip_: str = "", set_default: bool = False) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    if not (label and full_name and line1 and city and st and zip_):
        flash(state, "error", "Please fill in every required field.")
        log_action(state, "add_address_failed", reason="missing fields")
        return {"ok": False, "error": "missing fields"}
    addr_id = _new_id("addr")
    new_addr = Address(
        id=addr_id, label=label, full_name=full_name,
        line1=line1, line2=line2, city=city, state=st, zip=zip_,
        is_default=set_default,
    )
    user = state.users[uid]
    if set_default:
        for a in user.addresses.values():
            a.is_default = False
    user.addresses[addr_id] = new_addr
    log_action(state, "add_address",
               user_id=uid, address_id=addr_id, label=label,
               set_default=set_default)
    flash(state, "success", f"Address '{label}' saved.")
    return {"ok": True, "address_id": addr_id}


def set_default_address(state: GymState, address_id: str) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    user = state.users[uid]
    if address_id not in user.addresses:
        return {"ok": False, "error": "address not found"}
    for a in user.addresses.values():
        a.is_default = (a.id == address_id)
    log_action(state, "set_default_address",
               user_id=uid, address_id=address_id)
    return {"ok": True}


def add_payment_method(state: GymState, label: str, kind: str,
                       card_number: str = "", expires: str = "",
                       cvv: str = "", nickname: str = "",
                       set_default: bool = False) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    if kind == "credit_card" and not (card_number and expires and cvv):
        flash(state, "error", "Please complete the card information.")
        log_action(state, "add_payment_failed", reason="missing card fields")
        return {"ok": False, "error": "missing card fields"}
    last4 = (card_number[-4:] if card_number else "0000")
    pay_id = _new_id("pay")
    pm = PaymentMethod(
        id=pay_id,
        label=label or f"{kind.title()} ****{last4}",
        kind=kind, expires=expires, nickname=nickname,
        is_default=set_default,
    )
    user = state.users[uid]
    if set_default:
        for p in user.payment_methods.values():
            p.is_default = False
    user.payment_methods[pay_id] = pm
    log_action(state, "add_payment_method",
               user_id=uid, payment_id=pay_id, kind=kind,
               set_default=set_default)
    flash(state, "success", f"Payment method '{pm.label}' added.")
    return {"ok": True, "payment_id": pay_id}


def set_default_payment(state: GymState, payment_id: str) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    user = state.users[uid]
    if payment_id not in user.payment_methods:
        return {"ok": False, "error": "payment not found"}
    for p in user.payment_methods.values():
        p.is_default = (p.id == payment_id)
    log_action(state, "set_default_payment",
               user_id=uid, payment_id=payment_id)
    return {"ok": True}


def enable_two_fa(state: GymState, code: str) -> dict[str, Any]:
    """Mock 2FA — code 123456 always succeeds."""
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    if code != "123456":
        flash(state, "error", "Invalid 2FA code.")
        log_action(state, "enable_two_fa_failed")
        return {"ok": False, "error": "invalid code"}
    state.users[uid].two_fa_enabled = True
    log_action(state, "enable_two_fa", user_id=uid)
    flash(state, "success", "Two-factor authentication enabled.")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Cart
# --------------------------------------------------------------------------- #

def _line_id() -> str:
    return _new_id("ln")


def add_to_cart(state: GymState, product_id: str, quantity: int,
                variant_id: str | None = None) -> dict[str, Any]:
    p = state.products.get(product_id)
    if p is None:
        return {"ok": False, "error": "unknown product"}
    if quantity <= 0:
        flash(state, "error", "Quantity must be at least 1.")
        return {"ok": False, "error": "invalid quantity"}

    # Variant validation
    if p.variants and variant_id is None:
        flash(state, "error", f"Please pick an option for {p.name}.")
        log_action(state, "add_to_cart_failed",
                   product_id=product_id, reason="missing variant")
        return {"ok": False, "error": "variant required"}
    if variant_id is not None:
        v = next((v for v in p.variants if v.id == variant_id), None)
        if v is None:
            return {"ok": False, "error": "unknown variant"}
        if v.stock < quantity:
            flash(state, "error", f"Only {v.stock} of that variant in stock.")
            log_action(state, "add_to_cart_failed",
                       product_id=product_id, variant_id=variant_id,
                       reason="insufficient variant stock")
            return {"ok": False, "error": "out of stock"}
    else:
        if p.stock < quantity:
            flash(state, "error", f"Only {p.stock} of {p.name} in stock.")
            log_action(state, "add_to_cart_failed",
                       product_id=product_id, reason="insufficient stock")
            return {"ok": False, "error": "out of stock"}

    item = CartItem(
        id=_line_id(), product_id=product_id, variant_id=variant_id,
        quantity=quantity,
    )
    state.cart.items.append(item)
    log_action(state, "add_to_cart",
               product_id=product_id, variant_id=variant_id,
               quantity=quantity, line_id=item.id)
    flash(state, "success", f"Added {p.name} to cart.")
    return {"ok": True, "line_id": item.id}


def update_line(state: GymState, line_id: str, *,
                quantity: int | None = None,
                gift_wrap: bool | None = None,
                gift_message: str | None = None,
                ship_to_address_id: str | None = None,
                scheduled_delivery: str | None = None) -> dict[str, Any]:
    line = next((l for l in state.cart.items if l.id == line_id), None)
    if line is None:
        return {"ok": False, "error": "line not in cart"}
    if quantity is not None:
        if quantity <= 0:
            return remove_line(state, line_id)
        p = state.products.get(line.product_id)
        if p is None:
            return {"ok": False, "error": "unknown product"}
        max_stock = (
            next(v.stock for v in p.variants if v.id == line.variant_id)
            if line.variant_id else p.stock
        )
        if quantity > max_stock:
            flash(state, "error", f"Only {max_stock} in stock.")
            return {"ok": False, "error": "insufficient stock"}
        line.quantity = quantity
    if gift_wrap is not None:
        line.gift_wrap = gift_wrap
    if gift_message is not None:
        line.gift_message = gift_message
    if ship_to_address_id is not None:
        line.ship_to_address_id = ship_to_address_id
    if scheduled_delivery is not None:
        line.scheduled_delivery = scheduled_delivery
    log_action(state, "update_line", line_id=line_id,
               changes={k: v for k, v in locals().items()
                        if k not in ("state", "line", "p", "max_stock")
                        and v is not None and k != "line_id"})
    return {"ok": True}


def remove_line(state: GymState, line_id: str) -> dict[str, Any]:
    for i, l in enumerate(state.cart.items):
        if l.id == line_id:
            del state.cart.items[i]
            log_action(state, "remove_line", line_id=line_id)
            return {"ok": True}
    return {"ok": False, "error": "line not in cart"}


# --------------------------------------------------------------------------- #
# Promotions
# --------------------------------------------------------------------------- #

def apply_promo(state: GymState, code: str) -> dict[str, Any]:
    code = (code or "").strip().upper()
    promo = state.promotions.get(code)
    if promo is None:
        flash(state, "error", f"Promo {code!r} not found.")
        log_action(state, "apply_promo_failed",
                   code=code, reason="not found")
        return {"ok": False, "error": "not found"}
    if promo.expired:
        flash(state, "error", f"Promo {code!r} has expired.")
        log_action(state, "apply_promo_failed",
                   code=code, reason="expired")
        return {"ok": False, "error": "expired"}

    subtotal = _cart_subtotal(state)
    if subtotal < promo.min_purchase:
        flash(state, "error",
              f"Promo {code!r} needs a minimum of ${promo.min_purchase:.2f} "
              f"(your subtotal is ${subtotal:.2f}).")
        log_action(state, "apply_promo_failed",
                   code=code, reason="min purchase not met")
        return {"ok": False, "error": "min purchase not met"}

    # If the promo is category- or product-restricted, check at least one
    # eligible item.
    if promo.applies_to_category or promo.applies_to_product_id:
        eligible = False
        for line in state.cart.items:
            p = state.products.get(line.product_id)
            if p is None:
                continue
            if promo.applies_to_product_id and p.id == promo.applies_to_product_id:
                eligible = True
                break
            if promo.applies_to_category and p.category == promo.applies_to_category:
                eligible = True
                break
        if not eligible:
            flash(state, "error", f"Promo {code!r} doesn't apply to your cart.")
            log_action(state, "apply_promo_failed",
                       code=code, reason="no eligible items")
            return {"ok": False, "error": "no eligible items"}

    state.cart.applied_promo = code
    log_action(state, "apply_promo", code=code)
    flash(state, "success", f"Promo {code!r} applied.")
    return {"ok": True}


def remove_promo(state: GymState) -> dict[str, Any]:
    state.cart.applied_promo = None
    log_action(state, "remove_promo")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Order placement
# --------------------------------------------------------------------------- #

def _cart_subtotal(state: GymState) -> float:
    total = 0.0
    for line in state.cart.items:
        total += _resolve_unit_price(state, line.product_id, line.variant_id) \
                 * line.quantity
        if line.gift_wrap:
            total += GIFT_WRAP_FEE
    return round(total, 2)


def _promo_discount_on_eligible(state: GymState) -> float:
    """Compute discount only on lines eligible for the applied promo."""
    if not state.cart.applied_promo:
        return 0.0
    promo = state.promotions.get(state.cart.applied_promo)
    if promo is None or promo.expired:
        return 0.0
    eligible_subtotal = 0.0
    for line in state.cart.items:
        p = state.products.get(line.product_id)
        if p is None:
            continue
        if promo.applies_to_product_id and p.id != promo.applies_to_product_id:
            continue
        if promo.applies_to_category and p.category != promo.applies_to_category:
            continue
        eligible_subtotal += _resolve_unit_price(
            state, line.product_id, line.variant_id,
        ) * line.quantity
    discount = round(
        eligible_subtotal * promo.discount_pct + promo.discount_flat, 2,
    )
    return min(discount, eligible_subtotal)


def place_order(state: GymState, payment_id: str,
                default_address_id: str | None = None) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    user = state.users[uid]
    if not state.cart.items:
        flash(state, "error", "Your cart is empty.")
        return {"ok": False, "error": "cart empty"}
    if payment_id not in user.payment_methods:
        flash(state, "error", "Pick a payment method.")
        return {"ok": False, "error": "no payment"}

    # Resolve per-line shipping address (defaults to the default address
    # if not set per-line).
    if default_address_id is None:
        default_address_id = next(
            (a.id for a in user.addresses.values() if a.is_default),
            next(iter(user.addresses), None),
        )

    if default_address_id is None:
        flash(state, "error", "Add a shipping address first.")
        return {"ok": False, "error": "no address"}

    items_resolved: list[OrderItem] = []
    for line in state.cart.items:
        p = state.products.get(line.product_id)
        if p is None:
            return {"ok": False, "error": f"unknown product {line.product_id}"}
        addr_for_line = line.ship_to_address_id or default_address_id
        if addr_for_line not in user.addresses:
            return {"ok": False, "error": "invalid line address"}
        unit_price = _resolve_unit_price(state, line.product_id, line.variant_id)
        items_resolved.append(OrderItem(
            id=line.id, product_id=line.product_id,
            product_name=p.name, variant_id=line.variant_id,
            variant_label=_resolve_variant_label(
                state, line.product_id, line.variant_id),
            quantity=line.quantity, unit_price=unit_price,
            gift_wrap=line.gift_wrap, gift_message=line.gift_message,
            ship_to_address_id=addr_for_line,
            scheduled_delivery=line.scheduled_delivery,
        ))

    subtotal = _cart_subtotal(state)
    discount = _promo_discount_on_eligible(state)
    taxable = max(0.0, subtotal - discount)
    tax = round(taxable * TAX_RATE, 2)
    shipping = SHIPPING_FLAT
    total = round(taxable + tax + shipping, 2)

    # Build shipments — one per unique address.
    by_addr: dict[str, list[str]] = {}
    for oi in items_resolved:
        by_addr.setdefault(oi.ship_to_address_id, []).append(oi.id)

    order_id = _new_id("ord").upper()
    shipments: list[Shipment] = []
    for addr_id, item_ids in by_addr.items():
        sh = Shipment(
            id=_new_id("sh"),
            tracking_number=f"1Z{secrets.token_hex(6).upper()}",
            carrier="USPS",
            item_ids=item_ids,
            status="confirmed",
            estimated_delivery=(
                datetime.now(timezone.utc) + timedelta(days=3)
            ).date().isoformat(),
            events=[ShipmentEvent(
                timestamp=_now(),
                status="label_created",
                detail="Shipping label created.",
            )],
        )
        shipments.append(sh)

    order = Order(
        id=order_id, user_id=uid, placed_at=_now(),
        items=items_resolved,
        subtotal=subtotal, discount=discount, tax=tax,
        shipping=shipping, total=total,
        promo_code=state.cart.applied_promo,
        payment_id=payment_id, status="confirmed",
        shipments=shipments,
    )
    state.orders[order_id] = order

    # Decrement inventory.
    for oi in items_resolved:
        p = state.products[oi.product_id]
        if oi.variant_id:
            for v in p.variants:
                if v.id == oi.variant_id:
                    v.stock -= oi.quantity
        else:
            p.stock -= oi.quantity

    state.cart = Cart()  # clear
    log_action(state, "place_order", order_id=order_id, total=total)
    flash(state, "success", f"Order {order_id} placed.")
    return {"ok": True, "order_id": order_id, "total": total}


# --------------------------------------------------------------------------- #
# Returns
# --------------------------------------------------------------------------- #

def initiate_return(state: GymState, order_id: str,
                    item_ids: list[str], reason: str,
                    refund_method: str,
                    notes: str = "") -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    order = state.orders.get(order_id)
    if order is None or order.user_id != uid:
        return {"ok": False, "error": "order not found"}
    valid_item_ids = {oi.id for oi in order.items}
    bad = [i for i in item_ids if i not in valid_item_ids]
    if bad:
        return {"ok": False, "error": f"unknown items in return: {bad}"}
    if refund_method not in ("original_payment", "store_credit"):
        return {"ok": False, "error": "invalid refund_method"}

    ret_id = _new_id("ret").upper()
    state.returns[ret_id] = ReturnRequest(
        id=ret_id, order_id=order_id, user_id=uid,
        item_ids=list(item_ids),
        reason=reason,
        refund_method=refund_method,
        status="initiated",
        created_at=_now(),
        notes=notes,
    )
    log_action(state, "initiate_return",
               return_id=ret_id, order_id=order_id,
               item_ids=list(item_ids), reason=reason,
               refund_method=refund_method)
    flash(state, "success", f"Return {ret_id} initiated.")
    return {"ok": True, "return_id": ret_id}


def cancel_order(state: GymState, order_id: str) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    order = state.orders.get(order_id)
    if order is None or order.user_id != uid:
        return {"ok": False, "error": "order not found"}
    if order.status in ("shipped", "out_for_delivery", "delivered"):
        flash(state, "error",
              f"Order {order_id} has already shipped and can't be cancelled.")
        return {"ok": False, "error": "already shipped"}
    order.status = "cancelled"
    log_action(state, "cancel_order", order_id=order_id)
    flash(state, "success", f"Order {order_id} cancelled.")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #

def create_subscription(state: GymState, product_id: str,
                        cadence: str, deliveries: int,
                        address_id: str, payment_id: str,
                        variant_id: str | None = None,
                        quantity: int = 1) -> dict[str, Any]:
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    user = state.users[uid]
    p = state.products.get(product_id)
    if p is None or not p.is_subscribable:
        return {"ok": False, "error": "not subscribable"}
    if cadence not in ("weekly", "biweekly", "monthly"):
        return {"ok": False, "error": "invalid cadence"}
    if deliveries <= 0:
        return {"ok": False, "error": "invalid deliveries"}
    if address_id not in user.addresses:
        return {"ok": False, "error": "unknown address"}
    if payment_id not in user.payment_methods:
        return {"ok": False, "error": "unknown payment"}

    loyalty = (
        0.10 if user.loyalty_tier == "gold"
        else 0.05 if user.loyalty_tier == "silver"
        else 0.0
    )
    sub_id = _new_id("sub").upper()
    state.subscriptions[sub_id] = Subscription(
        id=sub_id, user_id=uid,
        product_id=product_id, variant_id=variant_id, quantity=quantity,
        cadence=cadence,                       # type: ignore[arg-type]
        deliveries_remaining=deliveries,
        next_delivery_date=(
            datetime.now(timezone.utc) + timedelta(days=7)
        ).date().isoformat(),
        address_id=address_id, payment_id=payment_id,
        loyalty_discount_pct=loyalty,
    )
    log_action(state, "create_subscription",
               subscription_id=sub_id, product_id=product_id,
               cadence=cadence, deliveries=deliveries,
               loyalty_discount_pct=loyalty)
    flash(state, "success",
          f"Subscription {sub_id} created. {deliveries} deliveries scheduled.")
    return {"ok": True, "subscription_id": sub_id,
            "loyalty_discount_pct": loyalty}


def cancel_subscription(state: GymState,
                        subscription_id: str) -> dict[str, Any]:
    """Cancel an active subscription owned by the current user."""
    uid = _require_login(state)
    if uid is None:
        return {"ok": False, "error": "not logged in"}
    sub = state.subscriptions.get(subscription_id)
    if sub is None or sub.user_id != uid:
        flash(state, "error", "Subscription not found.")
        return {"ok": False, "error": "unknown subscription"}
    if sub.status == "cancelled":
        # Idempotent — already cancelled is treated as success.
        return {"ok": True, "subscription_id": subscription_id,
                "already_cancelled": True}
    sub.status = "cancelled"
    log_action(state, "cancel_subscription",
               subscription_id=subscription_id,
               product_id=sub.product_id)
    flash(state, "success",
          f"Subscription {subscription_id} has been cancelled.")
    return {"ok": True, "subscription_id": subscription_id}
