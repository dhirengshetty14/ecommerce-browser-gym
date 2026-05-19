"""FastAPI server — multi-page e-commerce app + harness endpoints.

Two route families:

  Pages (HTML responses, what the browser agent renders + clicks):
    GET  /                           home / featured products
    GET  /search                     search results with filters
    GET  /product/{product_id}       product detail page (variants, tabs)
    GET  /cart                       cart with line-level options
    GET  /checkout/address           checkout step 1: pick address
    GET  /checkout/payment           checkout step 2: pick payment
    GET  /checkout/review            checkout step 3: review (coupon) + place
    GET  /order/{order_id}           order confirmation page
    GET  /login                      login form
    GET  /account                    account hub
    GET  /account/addresses          manage addresses
    GET  /account/payments           manage payment methods
    GET  /account/orders             order history
    GET  /account/orders/{order_id}  order detail with tracking modal trigger
    GET  /account/returns            list of returns
    GET  /account/returns/new        initiate-return form
    GET  /account/security           2FA / security
    GET  /account/subscriptions      subscriptions list / confirmation

  Form POST endpoints (browser submits land here, mutations applied):
    POST /api/login
    POST /api/logout
    POST /api/cart/add
    POST /api/cart/update
    POST /api/cart/remove
    POST /api/cart/promo
    POST /api/checkout/place
    POST /api/account/addresses
    POST /api/account/addresses/{address_id}/default
    POST /api/account/payments
    POST /api/account/payments/{payment_id}/default
    POST /api/account/security/two-fa
    POST /api/returns
    POST /api/subscriptions

  Harness-only (for the verifier; not used by the UI):
    POST /_harness/reset             reset gym for (task_id, seed)
    GET  /_harness/state             dump GymState
    GET  /_harness/snapshot          minimal snapshot (URL-agnostic)
    POST /_harness/verify            evaluate the suite given current URL

The browser agent uses the same routes a human would. Forms are
standard HTML form submissions with redirects — no JavaScript app
required (though the UI uses fetch for some nicer interactions).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    Cookie, FastAPI, Form, HTTPException, Query, Request, Response,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from server import mutations, verifiers
from server.state import GymState, log_action
from server.tasks import TASKS, make_task


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = REPO_ROOT / "ui"

app = FastAPI(
    title="ecommerce-browser-gym",
    version="0.1.0",
    description=(
        "Production-grade browser-agent RL gym for e-commerce. Agents "
        "drive a real Chromium browser through a multi-page e-commerce "
        "site; a per-step milestone verifier grades progress."
    ),
)
app.mount("/static", StaticFiles(directory=UI_DIR / "static"), name="static")
templates = Jinja2Templates(directory=UI_DIR / "pages")


# --------------------------------------------------------------------------- #
# Single-tenant session
# --------------------------------------------------------------------------- #

class Session:
    initial: GymState | None = None
    current: GymState | None = None
    suite: verifiers.TaskSuite | None = None


SESSION = Session()


# --------------------------------------------------------------------------- #
# Global exception handlers — make 404s recoverable for the agent
# --------------------------------------------------------------------------- #

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """When a page doesn't exist, render an HTML recovery page instead of
    JSON. This is critical for agents: they can READ HTML and find the
    link back home, but a JSON 404 is a dead-end."""
    if exc.status_code == 404:
        # Don't 404-render for harness or API endpoints — they should
        # stay as JSON so the harness/agent code can detect failure.
        path = request.url.path
        if path.startswith("/_harness") or path.startswith("/api"):
            return JSONResponse(
                {"detail": exc.detail or "Not Found"},
                status_code=exc.status_code,
            )
        try:
            return templates.TemplateResponse(
                request, "not_found.html",
                _ctx(request, attempted_path=path,
                     detail=exc.detail or "Page not found"),
                status_code=404,
            )
        except Exception:
            # If template rendering itself fails, fall back to JSON.
            return JSONResponse(
                {"detail": exc.detail or "Not Found"},
                status_code=exc.status_code,
            )
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code,
    )


def _state() -> GymState:
    if SESSION.current is None:
        # Default to the easiest task so the UI doesn't crash if a human
        # opens the site without hitting reset.
        _reset_inline("A1/buy_wireless_mouse", 0)
    assert SESSION.current is not None
    return SESSION.current


def _reset_inline(task_id: str, seed: int) -> None:
    fresh = make_task(task_id, seed)
    SESSION.initial = copy.deepcopy(fresh)
    SESSION.current = fresh
    SESSION.suite = verifiers.build_suite(task_id)


# --------------------------------------------------------------------------- #
# Common context for templates
# --------------------------------------------------------------------------- #

def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    s = _state()
    user = None
    if s.current_user_id:
        user = s.users[s.current_user_id]
    flashes = list(s.flash_messages)
    s.flash_messages.clear()
    cart_count = sum(i.quantity for i in s.cart.items)
    return {
        "request": request, "state": s, "user": user,
        "task_brief": s.task_brief,
        "task_id": s.task_id,
        "task_difficulty": s.task_difficulty,
        "task_category": s.task_category,
        "cart_count": cart_count,
        "flashes": flashes,
        **extra,
    }


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    s = _state()
    # Show a diverse set across categories so the featured rail is varied.
    featured = sorted(
        s.products.values(), key=lambda p: -p.rating,
    )[:12]
    return templates.TemplateResponse(request, "home.html", _ctx(request, featured=featured))


# --- Sort helpers for search/category pages --------------------------------
def _sort_products(items: list, sort: str) -> list:
    if sort == "price_asc":
        return sorted(items, key=lambda p: p.base_price)
    if sort == "price_desc":
        return sorted(items, key=lambda p: -p.base_price)
    if sort == "rating":
        return sorted(items, key=lambda p: -p.rating)
    if sort == "reviews":
        return sorted(items, key=lambda p: -p.review_count)
    # default: featured (rating desc with mild stock bias)
    return sorted(items, key=lambda p: (-p.rating, -p.stock))


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    category: str = "",
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    in_stock: bool = False,
    sort: str = "featured",
):
    s = _state()
    products = list(s.products.values())
    q_low = (q or "").lower()
    results = []
    for p in products:
        if q_low and q_low not in p.name.lower() \
                and q_low not in p.brand.lower() \
                and not any(q_low in t.lower() for t in p.tags):
            continue
        if category and p.category != category:
            continue
        if max_price is not None and p.base_price > max_price:
            continue
        if min_rating is not None and p.rating < min_rating:
            continue
        if in_stock and p.stock <= 0:
            continue
        results.append(p)
    results = _sort_products(results, sort)
    log_action(s, "search", q=q, category=category,
               max_price=max_price, min_rating=min_rating,
               in_stock=in_stock, sort=sort, n_results=len(results))
    return templates.TemplateResponse(
        request, "search.html",
        _ctx(request, results=results, q=q, category=category,
             max_price=max_price, min_rating=min_rating,
             in_stock=in_stock, sort=sort),
    )


@app.get("/category/{cat}", response_class=HTMLResponse)
async def category_page(
    request: Request, cat: str,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    in_stock: bool = False,
    sort: str = "featured",
):
    """Category landing page — same backend as /search but with a
    category-specific hero and breadcrumbs. Browsing via the mega-menu
    lands here. This pattern matches real e-commerce sites."""
    s = _state()
    products = list(s.products.values())
    results = [p for p in products if p.category == cat]
    if max_price is not None:
        results = [p for p in results if p.base_price <= max_price]
    if min_rating is not None:
        results = [p for p in results if p.rating >= min_rating]
    if in_stock:
        results = [p for p in results if p.stock > 0]
    results = _sort_products(results, sort)
    log_action(s, "view_category", category=cat,
               max_price=max_price, min_rating=min_rating,
               in_stock=in_stock, sort=sort, n_results=len(results))
    return templates.TemplateResponse(
        request, "category.html",
        _ctx(request, results=results, cat=cat,
             max_price=max_price, min_rating=min_rating,
             in_stock=in_stock, sort=sort),
    )


@app.get("/deals", response_class=HTMLResponse)
async def deals_page(request: Request):
    """Today's deals page — highlights the discounted items."""
    s = _state()
    # Pick lower-priced, high-rated items as the "deals" set.
    deals = sorted(
        [p for p in s.products.values() if p.stock > 0],
        key=lambda p: (-p.rating, p.base_price),
    )[:12]
    log_action(s, "view_deals")
    return templates.TemplateResponse(
        request, "deals.html",
        _ctx(request, deals=deals),
    )


# --------------------------------------------------------------------------- #
# Safety-net alias routes — catch URL patterns agents commonly hallucinate
# and redirect to the canonical route. Real e-commerce sites do this; it
# also prevents the agent from getting stuck on a 404 mid-episode.
# --------------------------------------------------------------------------- #

@app.get("/products", include_in_schema=False)
@app.get("/products/", include_in_schema=False)
@app.get("/items", include_in_schema=False)
@app.get("/shop", include_in_schema=False)
@app.get("/store", include_in_schema=False)
@app.get("/catalog", include_in_schema=False)
@app.get("/browse", include_in_schema=False)
async def alias_to_search():
    """Catch /products, /items, /shop etc. — agent meant /search."""
    return RedirectResponse("/search", 303)


@app.get("/products/{product_id}", include_in_schema=False)
@app.get("/item/{product_id}", include_in_schema=False)
@app.get("/p/{product_id}", include_in_schema=False)
async def alias_product_detail(product_id: str):
    """Catch /products/{id} → /product/{id} (singular vs plural)."""
    return RedirectResponse(f"/product/{product_id}", 303)


@app.get("/checkout", include_in_schema=False)
async def alias_checkout():
    """Catch bare /checkout — route based on cart state."""
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    if not s.cart.items:
        return RedirectResponse("/cart", 303)
    return RedirectResponse("/checkout/address", 303)


@app.get("/orders", include_in_schema=False)
@app.get("/my-orders", include_in_schema=False)
async def alias_orders():
    return RedirectResponse("/account/orders", 303)


@app.get("/returns", include_in_schema=False)
async def alias_returns():
    return RedirectResponse("/account/returns", 303)


@app.get("/subscriptions", include_in_schema=False)
@app.get("/subs", include_in_schema=False)
async def alias_subscriptions():
    return RedirectResponse("/account/subscriptions", 303)


@app.get("/profile", include_in_schema=False)
@app.get("/me", include_in_schema=False)
async def alias_account():
    return RedirectResponse("/account", 303)


@app.get("/signin", include_in_schema=False)
@app.get("/sign-in", include_in_schema=False)
@app.get("/log-in", include_in_schema=False)
async def alias_login():
    return RedirectResponse("/login", 303)


# Form POST endpoints sometimes get GETted by hallucinating agents.
# Redirect them to the page they belong on.
@app.get("/cart/add", include_in_schema=False)
@app.get("/cart/add/{sku}", include_in_schema=False)
@app.get("/api/cart/add", include_in_schema=False)
async def alias_cart_add(sku: str = ""):
    """The agent tried to GET /cart/add/{sku}. The real flow is:
    click the [data-test-id='btn-add-to-cart'] button on a product page."""
    s = _state()
    # If sku looks like a product_id, send them to the product page
    if sku and sku in s.products:
        return RedirectResponse(f"/product/{sku}", 303)
    return RedirectResponse("/search", 303)


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_page(request: Request, product_id: str,
                       tab: str = "description"):
    s = _state()
    p = s.products.get(product_id)
    if p is None:
        # Smart 404 recovery — try to find similar products by ID or
        # name so a hallucinating agent gets a useful suggestion instead
        # of a dead end. Same idea Amazon's "Did you mean..." pages use.
        import difflib
        candidates = list(s.products.keys())
        # Fuzzy by ID
        id_matches = difflib.get_close_matches(
            product_id.lower(), [c.lower() for c in candidates], n=5, cutoff=0.4,
        )
        # Also search by tokens in product names (e.g. "shirt cotton" → tshirt)
        query_tokens = set(
            tok for tok in product_id.replace("p_", "").lower().split("_")
            if len(tok) > 2
        )
        name_matches: list[str] = []
        for pid, prod in s.products.items():
            name_lower = prod.name.lower()
            if any(t in name_lower for t in query_tokens):
                name_matches.append(pid)
        # Dedupe, preserve order
        suggestions: list[str] = []
        for m in id_matches + name_matches:
            real_id = next((c for c in candidates if c.lower() == m), m)
            if real_id in s.products and real_id not in suggestions:
                suggestions.append(real_id)
        suggested_products = [s.products[sid] for sid in suggestions[:6]]
        return templates.TemplateResponse(
            request, "product_not_found.html",
            _ctx(request,
                 attempted_id=product_id,
                 suggested_products=suggested_products),
            status_code=404,
        )
    log_action(s, "view_product", product_id=product_id, tab=tab)
    return templates.TemplateResponse(request, "product.html", _ctx(request, p=p, tab=tab))


@app.get("/cart", response_class=HTMLResponse)
async def cart_page(request: Request):
    return templates.TemplateResponse(request, "cart.html", _ctx(request))


@app.get("/checkout/address", response_class=HTMLResponse)
async def checkout_address(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    if not s.cart.items:
        return RedirectResponse("/cart", 303)
    log_action(s, "checkout_step", step="address")
    return templates.TemplateResponse(request, "checkout_address.html", _ctx(request))


@app.get("/checkout/payment", response_class=HTMLResponse)
async def checkout_payment(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    log_action(s, "checkout_step", step="payment")
    return templates.TemplateResponse(request, "checkout_payment.html", _ctx(request))


@app.get("/checkout/review", response_class=HTMLResponse)
async def checkout_review(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    log_action(s, "checkout_step", step="review")
    return templates.TemplateResponse(request, "checkout_review.html", _ctx(request))


@app.get("/order/{order_id}", response_class=HTMLResponse)
async def order_confirmation(request: Request, order_id: str):
    s = _state()
    o = s.orders.get(order_id)
    if o is None:
        raise HTTPException(404, "order not found")
    return templates.TemplateResponse(request, "order_confirmation.html", _ctx(request, order=o))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", _ctx(request))


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(request, "account_hub.html", _ctx(request))


@app.get("/account/addresses", response_class=HTMLResponse)
async def account_addresses(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(request, "account_addresses.html", _ctx(request))


@app.get("/account/payments", response_class=HTMLResponse)
async def account_payments(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(request, "account_payments.html", _ctx(request))


@app.get("/account/orders", response_class=HTMLResponse)
async def account_orders(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    user_orders = [o for o in s.orders.values()
                   if o.user_id == s.current_user_id]
    return templates.TemplateResponse(request, "account_orders.html", _ctx(request, orders=user_orders))


@app.get("/account/orders/{order_id}", response_class=HTMLResponse)
async def account_order_detail(request: Request, order_id: str):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    o = s.orders.get(order_id)
    if o is None or o.user_id != s.current_user_id:
        raise HTTPException(404, "order not found")
    log_action(s, "view_order_detail", order_id=order_id)
    return templates.TemplateResponse(request, "account_order_detail.html", _ctx(request, order=o))


@app.get("/account/orders/{order_id}/track", response_class=HTMLResponse)
async def view_tracking(request: Request, order_id: str):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    o = s.orders.get(order_id)
    if o is None or o.user_id != s.current_user_id:
        raise HTTPException(404, "order not found")
    log_action(s, "viewed_tracking", order_id=order_id)
    return templates.TemplateResponse(request, "tracking_modal.html", _ctx(request, order=o))


@app.get("/account/returns", response_class=HTMLResponse)
async def account_returns(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    user_returns = [r for r in s.returns.values()
                    if r.user_id == s.current_user_id]
    return templates.TemplateResponse(request, "account_returns.html", _ctx(request, returns=user_returns))


@app.get("/account/returns/new", response_class=HTMLResponse)
async def new_return(request: Request, order_id: str = Query(...)):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    o = s.orders.get(order_id)
    if o is None or o.user_id != s.current_user_id:
        raise HTTPException(404, "order not found")
    return templates.TemplateResponse(request, "return_form.html", _ctx(request, order=o))


@app.get("/account/security", response_class=HTMLResponse)
async def account_security(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(request, "account_security.html", _ctx(request))


@app.get("/account/subscriptions", response_class=HTMLResponse)
async def account_subscriptions(request: Request):
    s = _state()
    if s.current_user_id is None:
        return RedirectResponse("/login", 303)
    user_subs = [sub for sub in s.subscriptions.values()
                 if sub.user_id == s.current_user_id]
    return templates.TemplateResponse(request, "account_subscriptions.html", _ctx(request, subscriptions=user_subs))


# --------------------------------------------------------------------------- #
# Form POST endpoints
# --------------------------------------------------------------------------- #

@app.post("/api/login")
async def api_login(email: str = Form(""), password: str = Form("")):
    s = _state()
    r = mutations.login(s, email, password)
    if r.get("ok"):
        return RedirectResponse("/account", 303)
    return RedirectResponse("/login?err=1", 303)


@app.post("/api/logout")
async def api_logout():
    s = _state()
    mutations.logout(s)
    return RedirectResponse("/", 303)


@app.post("/api/cart/add")
async def api_add_to_cart(
    product_id: str = Form(...),
    quantity: int = Form(1),
    variant_id: Optional[str] = Form(None),
    redirect: Optional[str] = Form(None),
):
    s = _state()
    result = mutations.add_to_cart(
        s, product_id=product_id,
        quantity=quantity, variant_id=variant_id,
    )
    # If add-to-cart failed (e.g. variant required), stay on the
    # product page so the agent sees both the error flash AND the
    # variant picker. Don't honor the form's `redirect` field in this
    # case — that would silently land the agent on /cart with only a
    # toast that's easy to miss in a heavy observation.
    if not result.get("ok"):
        return RedirectResponse(f"/product/{product_id}", 303)
    return RedirectResponse(redirect or f"/product/{product_id}", 303)


@app.post("/api/cart/update")
async def api_update_line(
    line_id: str = Form(...),
    quantity: Optional[int] = Form(None),
    gift_wrap: Optional[bool] = Form(None),
    gift_message: Optional[str] = Form(None),
    ship_to_address_id: Optional[str] = Form(None),
    scheduled_delivery: Optional[str] = Form(None),
):
    s = _state()
    mutations.update_line(
        s, line_id=line_id, quantity=quantity,
        gift_wrap=gift_wrap, gift_message=gift_message,
        ship_to_address_id=ship_to_address_id,
        scheduled_delivery=scheduled_delivery,
    )
    return RedirectResponse("/cart", 303)


@app.post("/api/cart/remove")
async def api_remove_line(line_id: str = Form(...)):
    s = _state()
    mutations.remove_line(s, line_id=line_id)
    return RedirectResponse("/cart", 303)


@app.post("/api/cart/promo")
async def api_apply_promo(
    code: str = Form(""),
    action: str = Form("apply"),
):
    s = _state()
    if action == "remove":
        mutations.remove_promo(s)
    else:
        mutations.apply_promo(s, code=code)
    return RedirectResponse("/checkout/review", 303)


@app.post("/api/checkout/place")
async def api_place_order(payment_id: str = Form(...)):
    s = _state()
    r = mutations.place_order(s, payment_id=payment_id)
    if r.get("ok"):
        return RedirectResponse(f"/order/{r['order_id']}", 303)
    return RedirectResponse("/checkout/review?err=1", 303)


@app.post("/api/account/addresses")
async def api_add_address(
    label: str = Form(...),
    full_name: str = Form(...),
    line1: str = Form(...),
    line2: str = Form(""),
    city: str = Form(...),
    state: str = Form(...),
    zip: str = Form(...),
    set_default: bool = Form(False),
):
    s = _state()
    mutations.add_address(s, label=label, full_name=full_name,
                          line1=line1, line2=line2, city=city,
                          st=state, zip_=zip, set_default=set_default)
    return RedirectResponse("/account/addresses", 303)


@app.post("/api/account/addresses/{address_id}/default")
async def api_set_default_address(address_id: str):
    s = _state()
    mutations.set_default_address(s, address_id=address_id)
    return RedirectResponse("/account/addresses", 303)


@app.post("/api/account/payments")
async def api_add_payment(
    label: str = Form(""),
    kind: str = Form("credit_card"),
    card_number: str = Form(""),
    expires: str = Form(""),
    cvv: str = Form(""),
    nickname: str = Form(""),
    set_default: bool = Form(False),
):
    s = _state()
    mutations.add_payment_method(
        s, label=label, kind=kind, card_number=card_number,
        expires=expires, cvv=cvv, nickname=nickname,
        set_default=set_default,
    )
    return RedirectResponse("/account/payments", 303)


@app.post("/api/account/payments/{payment_id}/default")
async def api_set_default_payment(payment_id: str):
    s = _state()
    mutations.set_default_payment(s, payment_id=payment_id)
    return RedirectResponse("/account/payments", 303)


@app.post("/api/account/security/two-fa")
async def api_enable_two_fa(code: str = Form(...)):
    s = _state()
    mutations.enable_two_fa(s, code=code)
    return RedirectResponse("/account/security", 303)


@app.post("/api/returns")
async def api_create_return(
    order_id: str = Form(...),
    item_ids: list[str] = Form(...),
    reason: str = Form(...),
    refund_method: str = Form(...),
    notes: str = Form(""),
):
    s = _state()
    r = mutations.initiate_return(
        s, order_id=order_id, item_ids=item_ids,
        reason=reason, refund_method=refund_method, notes=notes,
    )
    return RedirectResponse("/account/returns", 303)


@app.post("/api/subscriptions")
async def api_create_subscription(
    product_id: str = Form(...),
    cadence: str = Form("weekly"),
    deliveries: int = Form(4),
    address_id: str = Form(...),
    payment_id: str = Form(...),
    quantity: int = Form(1),
    variant_id: Optional[str] = Form(None),
):
    s = _state()
    r = mutations.create_subscription(
        s, product_id=product_id, cadence=cadence,
        deliveries=deliveries, address_id=address_id,
        payment_id=payment_id, quantity=quantity, variant_id=variant_id,
    )
    return RedirectResponse("/account/subscriptions", 303)


# --------------------------------------------------------------------------- #
# Harness endpoints
# --------------------------------------------------------------------------- #

class HarnessResetRequest(BaseModel):
    task_id: str
    seed: int = 0


class HarnessVerifyRequest(BaseModel):
    url: str = ""
    step: int = 0


@app.get("/_harness/tasks")
def harness_tasks() -> dict[str, list[str]]:
    return {"tasks": list(TASKS)}


@app.post("/_harness/reset")
def harness_reset(req: HarnessResetRequest) -> dict[str, Any]:
    if req.task_id not in TASKS:
        raise HTTPException(404, "unknown task")
    _reset_inline(req.task_id, req.seed)
    s = _state()
    return {"ok": True, "task_id": s.task_id, "seed": s.seed,
            "task_brief": s.task_brief,
            "task_category": s.task_category,
            "task_difficulty": s.task_difficulty,
            "current_user_id": s.current_user_id}


@app.get("/_harness/state")
def harness_state() -> dict[str, Any]:
    return _state().to_json()


@app.get("/_harness/snapshot")
def harness_snapshot() -> dict[str, Any]:
    """Lightweight snapshot: cart count, orders count, current user, etc."""
    s = _state()
    return {
        "task_id": s.task_id, "step": s.step, "finished": s.finished,
        "current_user_id": s.current_user_id,
        "cart_item_count": sum(i.quantity for i in s.cart.items),
        "orders_count": len(s.orders),
        "returns_count": len(s.returns),
        "subscriptions_count": len(s.subscriptions),
        "applied_promo": s.cart.applied_promo,
    }


@app.post("/_harness/verify")
def harness_verify(req: HarnessVerifyRequest) -> dict[str, Any]:
    if SESSION.suite is None or SESSION.initial is None:
        raise HTTPException(409, "no active episode")
    s = _state()
    s.step = req.step
    probe = verifiers.Probe(
        state=s, url=req.url, initial_state=SESSION.initial,
    )
    return SESSION.suite.evaluate(probe, req.step)
