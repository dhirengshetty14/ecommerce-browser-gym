"""Domain model — entities and state for a realistic e-commerce gym.

This is a substantially richer model than a toy "cart + checkout" sim.
It supports the kinds of complex user journeys real shops run:

- Users with login sessions (cookie auth)
- Catalog with categories, variants (size/color), reviews
- Cart with line-level options (gift wrap, scheduled delivery, split shipping)
- Promotions with category/item/min-purchase restrictions
- Orders with multi-package shipments and tracking statuses
- Returns with reason codes and refund methods
- Subscriptions with delivery cadence
- Account: addresses (incl. add/edit), payment methods (add/edit), 2FA

Each task uses a slice of these. The model is intentionally over-built
so the same gym supports tasks across all 3 categories without us
needing to extend the schema mid-task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal


# --------------------------------------------------------------------------- #
# Type aliases
# --------------------------------------------------------------------------- #

PaymentKind = Literal["credit_card", "paypal", "apple_pay", "gift_card"]
OrderStatus = Literal[
    "pending", "confirmed", "preparing", "shipped",
    "out_for_delivery", "delivered", "cancelled",
]
ReturnStatus = Literal["initiated", "approved", "received", "refunded", "rejected"]
RefundMethod = Literal["original_payment", "store_credit"]
SubscriptionStatus = Literal["active", "paused", "cancelled"]
DeliveryCadence = Literal["weekly", "biweekly", "monthly"]


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #

@dataclass
class ProductVariant:
    """A specific configuration of a product (e.g. 'Red, Large')."""
    id: str
    label: str                     # human label, e.g. "Red — Large"
    attributes: dict[str, str]     # e.g. {"color": "red", "size": "L"}
    price_delta: float = 0.0       # added to base price
    stock: int = 0


@dataclass
class Review:
    id: str
    author: str
    rating: int                    # 1..5
    title: str
    body: str
    verified_purchase: bool = False


@dataclass
class Product:
    id: str
    name: str
    brand: str
    category: str
    base_price: float
    rating: float                  # rolled-up rating 0..5
    review_count: int
    stock: int                     # for variant-less products
    image_emoji: str
    short_description: str
    long_description: str = ""
    tags: list[str] = field(default_factory=list)
    variants: list[ProductVariant] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    is_subscribable: bool = False
    weight_kg: float = 0.5         # for shipping cost calc


# --------------------------------------------------------------------------- #
# User & account
# --------------------------------------------------------------------------- #

@dataclass
class Address:
    id: str
    label: str                     # "Home", "Work", "Mom's"
    full_name: str
    line1: str
    line2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    is_default: bool = False


@dataclass
class PaymentMethod:
    id: str
    label: str                     # "Visa ****4242"
    kind: PaymentKind
    is_default: bool = False
    expires: str = ""              # "MM/YY"
    nickname: str = ""


@dataclass
class User:
    id: str
    email: str
    password: str                  # plain-text in this in-memory mock — DON'T do this in prod
    full_name: str
    addresses: dict[str, Address] = field(default_factory=dict)
    payment_methods: dict[str, PaymentMethod] = field(default_factory=dict)
    two_fa_enabled: bool = False
    loyalty_tier: Literal["basic", "silver", "gold"] = "basic"


# --------------------------------------------------------------------------- #
# Cart, with line-level options
# --------------------------------------------------------------------------- #

@dataclass
class CartItem:
    id: str                        # unique per cart line (so dupes allowed)
    product_id: str
    variant_id: str | None
    quantity: int
    gift_wrap: bool = False
    gift_message: str = ""
    ship_to_address_id: str | None = None    # split shipping
    scheduled_delivery: str | None = None    # ISO date or None for "ASAP"


@dataclass
class Cart:
    items: list[CartItem] = field(default_factory=list)
    applied_promo: str | None = None


# --------------------------------------------------------------------------- #
# Promotions
# --------------------------------------------------------------------------- #

@dataclass
class Promotion:
    code: str
    name: str
    description: str
    discount_pct: float = 0.0            # e.g. 0.20 = 20%
    discount_flat: float = 0.0           # e.g. 10.00 = $10 off
    applies_to_category: str | None = None
    applies_to_product_id: str | None = None
    min_purchase: float = 0.0
    expired: bool = False
    one_per_customer: bool = True
    description_fineprint: str = ""


# --------------------------------------------------------------------------- #
# Orders, shipments, tracking
# --------------------------------------------------------------------------- #

@dataclass
class ShipmentEvent:
    timestamp: str                       # ISO
    status: str                          # e.g. "label_created", "in_transit"
    location: str = ""
    detail: str = ""


@dataclass
class Shipment:
    id: str
    tracking_number: str
    carrier: str                         # "USPS", "UPS", "FedEx"
    item_ids: list[str] = field(default_factory=list)   # CartItem ids in this shipment
    status: OrderStatus = "confirmed"
    estimated_delivery: str = ""
    events: list[ShipmentEvent] = field(default_factory=list)


@dataclass
class OrderItem:
    """A single item on the order. Mirrors CartItem but immutable."""
    id: str
    product_id: str
    product_name: str                    # snapshotted
    variant_id: str | None
    variant_label: str                   # snapshotted
    quantity: int
    unit_price: float
    gift_wrap: bool
    gift_message: str
    ship_to_address_id: str
    scheduled_delivery: str | None


@dataclass
class Order:
    id: str
    user_id: str
    placed_at: str                       # ISO
    items: list[OrderItem]
    subtotal: float
    discount: float
    tax: float
    shipping: float
    total: float
    promo_code: str | None
    payment_id: str
    status: OrderStatus = "confirmed"
    shipments: list[Shipment] = field(default_factory=list)
    is_subscription: bool = False
    subscription_id: str | None = None


# --------------------------------------------------------------------------- #
# Returns
# --------------------------------------------------------------------------- #

@dataclass
class ReturnRequest:
    id: str
    order_id: str
    user_id: str
    item_ids: list[str]                  # subset of OrderItem ids
    reason: str                          # "defective", "wrong_size", "changed_mind", etc.
    refund_method: RefundMethod
    status: ReturnStatus = "initiated"
    created_at: str = ""
    notes: str = ""


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #

@dataclass
class Subscription:
    id: str
    user_id: str
    product_id: str
    variant_id: str | None
    quantity: int
    cadence: DeliveryCadence
    deliveries_remaining: int            # e.g. 4 for "4 weeks of dog food"
    next_delivery_date: str
    address_id: str
    payment_id: str
    loyalty_discount_pct: float = 0.0    # gold tier = 0.10 etc.
    status: SubscriptionStatus = "active"


# --------------------------------------------------------------------------- #
# Whole-world state
# --------------------------------------------------------------------------- #

@dataclass
class GymState:
    """The gym's whole world for one episode.

    Everything verifiers will ever inspect is here. Reset between tasks.
    """

    task_id: str = ""
    seed: int = 0
    step: int = 0
    finished: bool = False
    task_brief: str = ""
    task_difficulty: Literal["easy", "medium", "hard"] = "easy"
    task_category: Literal["A", "B", "C"] = "A"     # discovery / mgmt / checkout

    # Catalog
    products: dict[str, Product] = field(default_factory=dict)
    promotions: dict[str, Promotion] = field(default_factory=dict)

    # Users
    users: dict[str, User] = field(default_factory=dict)
    current_user_id: str | None = None              # None == not logged in

    # Per-session live state
    cart: Cart = field(default_factory=Cart)
    orders: dict[str, Order] = field(default_factory=dict)
    returns: dict[str, ReturnRequest] = field(default_factory=dict)
    subscriptions: dict[str, Subscription] = field(default_factory=dict)

    # Trail (for verifiers)
    action_log: list[dict[str, Any]] = field(default_factory=list)
    flash_messages: list[dict[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Compact JSON snapshot for verifier inspection. The UI does its
        own targeted fetches; this is the verifier's omniscient view."""
        from dataclasses import asdict
        return {
            "task_id": self.task_id,
            "seed": self.seed, "step": self.step,
            "finished": self.finished,
            "task_brief": self.task_brief,
            "task_difficulty": self.task_difficulty,
            "task_category": self.task_category,
            "current_user_id": self.current_user_id,
            "current_user": (
                asdict(self.users[self.current_user_id])
                if self.current_user_id else None
            ),
            "cart": {
                "items": [asdict(i) for i in self.cart.items],
                "applied_promo": self.cart.applied_promo,
            },
            "orders": {oid: asdict(o) for oid, o in self.orders.items()},
            "returns": {rid: asdict(r) for rid, r in self.returns.items()},
            "subscriptions": {
                sid: asdict(s) for sid, s in self.subscriptions.items()
            },
            "products_count": len(self.products),
            "action_log": list(self.action_log),
            "flash_messages": list(self.flash_messages),
        }


# --------------------------------------------------------------------------- #
# Logging helpers
# --------------------------------------------------------------------------- #

def log_action(state: GymState, event_kind: str, **fields: Any) -> None:
    """Append a structured entry to the action log. Used by the FastAPI
    handlers so verifiers can inspect "did this happen" trajectory-style
    without needing the browser agent's own log.

    The dict key remains ``"kind"`` for backwards-compat with verifier
    checks that look up ``e.get("kind")``. The parameter name is
    ``event_kind`` so callers can use ``kind=`` as a payload field
    without collision.
    """
    state.action_log.append({
        "step": state.step, "kind": event_kind, **fields,
    })


def flash(state: GymState, kind: str, body: str) -> None:
    """Push a flash message. Surfaced in the UI as a banner; verifiers
    can see them via state.flash_messages."""
    state.flash_messages.append({"kind": kind, "body": body})
