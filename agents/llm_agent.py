"""LLM browser agent — drives the real browser through tool calls.

This is a simple, transparent browser-agent loop. Each turn:
  1. Take a screenshot + dump accessible elements
  2. Send to the LLM (Anthropic Claude by default) with a tool spec
  3. LLM returns one of: navigate, click, fill, select, check, submit,
     finish
  4. Translate to Playwright via BrowserCtx (which also probes the
     verifier after each action)

We deliberately use the DOM-action interface (CSS selector + value)
rather than pixel coordinates because:
  - It's reliable across viewport changes
  - data-test-id selectors are deterministic
  - It works against any LLM (no need for screenshot-grounded models)

For pixel-level / OpenAI Computer Use / Claude Computer Use, the same
``BrowserCtx`` works — just swap the agent loop. Left as a TODO.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from harness.runner import BrowserCtx


TOOLS_ANTHROPIC = [
    {"name": "navigate", "description": "Navigate to a path like '/cart' or '/product/X'.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "reason": {"type": "string"}}, "required": ["path"]}},
    {"name": "click", "description": "Click an element by CSS selector. Use [data-test-id='...'] for reliability.",
     "input_schema": {"type": "object", "properties": {
         "selector": {"type": "string"},
         "reason": {"type": "string"}}, "required": ["selector"]}},
    {"name": "fill", "description": "Fill a text input by CSS selector.",
     "input_schema": {"type": "object", "properties": {
         "selector": {"type": "string"},
         "value": {"type": "string"},
         "reason": {"type": "string"}}, "required": ["selector", "value"]}},
    {"name": "select", "description": "Select an <option> by value in a <select>.",
     "input_schema": {"type": "object", "properties": {
         "selector": {"type": "string"},
         "value": {"type": "string"},
         "reason": {"type": "string"}}, "required": ["selector", "value"]}},
    {"name": "check", "description": "Toggle a checkbox to checked.",
     "input_schema": {"type": "object", "properties": {
         "selector": {"type": "string"},
         "reason": {"type": "string"}}, "required": ["selector"]}},
    {"name": "submit", "description": "Click a submit button. Same as click but the harness waits for form completion.",
     "input_schema": {"type": "object", "properties": {
         "selector": {"type": "string"},
         "reason": {"type": "string"}}, "required": ["selector"]}},
    {"name": "finish", "description": "Indicate that you believe the task is complete.",
     "input_schema": {"type": "object", "properties": {
         "reason": {"type": "string"}}, "required": []}},
]


SYSTEM_PROMPT = """\
You are operating a real web browser to complete an e-commerce task on
the ShopGym site.

For each step:
1. Read the task brief carefully (shown in the amber banner at the top of every page)
2. Look at the current page state I'll show you (URL + visible elements)
3. Decide ONE next action: navigate / click / fill / select / check / submit / finish
4. Use CSS selectors targeting [data-test-id='...'] — every interactable in this app has a data-test-id

═══════════════════════════════════════════════════════════════════════════
CRITICAL RULES — read this section twice before your first action.
═══════════════════════════════════════════════════════════════════════════

NEVER invent URLs. Real e-commerce sites have arbitrary routes that
you cannot guess. This gym is the same. NEVER guess paths like
/products, /cart/add/SKU001, /shop, /add-to-cart, etc. — they don't
exist and you will land on a 404.

NEVER guess product IDs. They look like p_mouse_wireless or
p_laptop_studio but are NOT predictable from product names. Trying
/product/p_shirt_cotton_basic or /product/p_tshirt will 404 even
though "Cotton T-Shirt" exists (its real ID is p_clothing_tshirt).

The correct way to reach a product page:
  Option A (preferred): use `click` on a [data-test-id='card-product-X']
    selector you can see in the interactables list.
  Option B: navigate to /search?q=<keyword> or /category/<cat>, then
    click the product card.
  Option C: only use /product/<id> if you have the EXACT id from
    snapshot.products or from a card-product-* test_id.

If you land on data-test-id='page-product-not-found', the page shows
"Did you mean..." suggestions — click one of those instead of guessing
again.

The ONLY way to reach a new page is:
  1. Click a link or button visible in the interactables list (PREFERRED),
     using `click` with the data-test-id you can see.
  2. Or use `navigate` with one of these EXACT canonical paths:
       /                         home
       /search                   search results (use ?q=foo for query)
       /search?q=mouse           keyword search
       /category/<cat>           cat in: electronics, audio, books,
                                  clothing, home, pet, office
       /product/<product_id>     product_id comes from snapshot.products
                                 or from an interactable like
                                 card-product-p_mouse_wireless
       /cart                     shopping cart
       /checkout/address         step 1 of checkout
       /checkout/payment         step 2 of checkout
       /checkout/review          step 3 of checkout (apply promo here)
       /login                    sign-in page
       /account                  account hub
       /account/orders           past orders
       /account/orders/<id>      one order's detail (id from snapshot.orders)
       /account/addresses        manage addresses
       /account/payments         manage payment methods
       /account/security         2FA / security
       /account/subscriptions    subscriptions
       /account/returns          returns
       /account/returns/new      initiate a return
       /deals                    today's deals page

Product IDs always start with `p_` (e.g. p_mouse_wireless, p_laptop_studio).
You can see all valid product IDs in the snapshot. Address IDs are
addr_home / addr_work / addr_giftee etc. Payment IDs are pm_visa,
pm_paypal, etc.

To ADD items to cart: click the [data-test-id='btn-add-to-cart'] button
on a product page. NEVER navigate to a path like /cart/add/... — there
is no such GET endpoint.

To SUBMIT a form: use the `submit` action with the form's submit-button
selector. Forms post to /api/* endpoints automatically; you never call
those endpoints directly.

═══════════════════════════════════════════════════════════════════════════
General rules:
═══════════════════════════════════════════════════════════════════════════

- One tool call per turn. After each action I show you the new state.
- Read the task brief literally. If it says "Home address", use addr_home, not addr_work.
- If a form field is required and you skip it, the form will reject with an error banner — read those banners.
- If you see [data-test-id='page-not-found'] in the interactables, you
  hit a 404 — recover by clicking [data-test-id='btn-nf-home'] (go home).
- Call `finish` only when you believe the task is complete.

The task brief is your goal. Everything else is a hint.
"""


class LLMBrowserAgent:
    """An Anthropic-backed browser agent.

    Pass ``model`` to override (e.g. claude-sonnet-4-5-20250929). Set
    ANTHROPIC_API_KEY env var.
    """

    def __init__(self, model: str | None = None, max_steps: int = 30,
                 verbose: bool = True):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model or os.getenv(
            "ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929",
        )
        self.max_steps = max_steps
        self.verbose = verbose

    async def run(self, ctx: BrowserCtx, task_brief: str) -> None:
        messages: list[dict[str, Any]] = []

        for turn in range(self.max_steps):
            observation = await self._observation(ctx)
            messages.append({"role": "user", "content": observation})

            resp = self.client.messages.create(
                model=self.model, max_tokens=1024,
                system=SYSTEM_PROMPT + f"\n\nTASK: {task_brief}",
                tools=TOOLS_ANTHROPIC,
                messages=messages,
            )

            tool_call = None
            text_parts: list[str] = []
            tool_use_id = None
            for block in resp.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use" and tool_call is None:
                    tool_call = {"name": block.name,
                                 "input": dict(block.input or {})}
                    tool_use_id = block.id

            assistant_blocks: list[dict[str, Any]] = []
            if text_parts:
                assistant_blocks.append({"type": "text",
                                         "text": "\n".join(text_parts)})
            if tool_call:
                assistant_blocks.append({
                    "type": "tool_use", "id": tool_use_id,
                    "name": tool_call["name"], "input": tool_call["input"],
                })
            messages.append({"role": "assistant", "content": assistant_blocks})

            if tool_call is None:
                if self.verbose:
                    print(f"[llm_agent] no tool call. raw={text_parts}")
                break

            kind = tool_call["name"]
            args = tool_call["input"]
            if self.verbose:
                print(f"[llm_agent] step {turn}: {kind}({json.dumps(args)})")

            try:
                if kind == "navigate":
                    await ctx.goto(args["path"], reasoning=args.get("reason", ""))
                elif kind == "click":
                    await ctx.click(args["selector"], reasoning=args.get("reason", ""))
                elif kind == "fill":
                    await ctx.fill(args["selector"], args["value"],
                                   reasoning=args.get("reason", ""))
                elif kind == "select":
                    await ctx.select(args["selector"], args["value"],
                                     reasoning=args.get("reason", ""))
                elif kind == "check":
                    await ctx.check(args["selector"], reasoning=args.get("reason", ""))
                elif kind == "submit":
                    await ctx.submit(args["selector"], reasoning=args.get("reason", ""))
                elif kind == "finish":
                    if self.verbose:
                        print(f"[llm_agent] finishing: "
                              f"{args.get('reason', '')}")
                    break
                else:
                    raise ValueError(f"unknown tool {kind}")
                tool_result = {"ok": True}
            except Exception as e:
                tool_result = {"ok": False,
                               "error": f"{type(e).__name__}: {e}"}
                if self.verbose:
                    print(f"[llm_agent] action failed: {tool_result}")

            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result", "tool_use_id": tool_use_id,
                    "content": json.dumps({
                        "result": tool_result,
                        "current_url": ctx.page.url,
                    }),
                }],
            })

    async def _observation(self, ctx: BrowserCtx) -> str:
        """Compact observation: URL + accessible interactables + cart snapshot.

        Also includes an `href` for anchor tags so the model can navigate
        without guessing — and a short `valid_route_patterns` reminder
        that the model sees every turn (not just at system-prompt time).
        """
        page = ctx.page
        url = page.url
        # Extract data-test-id'd interactables — include href for <a> tags
        elements = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('[data-test-id]').forEach(el => {
                const text = (el.innerText || el.value || el.placeholder || '').trim().slice(0, 80);
                const item = {
                    test_id: el.getAttribute('data-test-id'),
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || null,
                    text: text,
                };
                if (el.tagName.toLowerCase() === 'a' && el.getAttribute('href')) {
                    item.href = el.getAttribute('href');
                }
                out.push(item);
            });
            return out.slice(0, 100);
        }""")
        # Backend snapshot for context
        snap = ctx.http.get(f"{ctx.server_url}/_harness/snapshot").json()

        # Surface valid product/order IDs so the model uses real ones
        product_ids = sorted(snap.get("products", {}).keys()) if isinstance(snap.get("products"), dict) else []
        order_ids = sorted(snap.get("orders", {}).keys()) if isinstance(snap.get("orders"), dict) else []

        # In-prompt reminder of what URLs are real
        valid_route_patterns = [
            "/", "/search", "/search?q=<query>",
            "/category/<electronics|audio|books|clothing|home|pet|office>",
            "/product/<product_id>", "/cart",
            "/checkout/address", "/checkout/payment", "/checkout/review",
            "/login", "/account", "/account/orders", "/account/orders/<id>",
            "/account/addresses", "/account/payments", "/account/security",
            "/account/subscriptions", "/account/returns",
            "/account/returns/new", "/deals",
        ]

        obs = {
            "url": url,
            "snapshot": snap,
            "interactables": elements,
            "hints": {
                "valid_route_patterns": valid_route_patterns,
                "note": "Use ONLY these route patterns. Never invent paths. "
                        "Prefer clicking visible links over navigating.",
            },
        }
        return f"```json\n{json.dumps(obs, indent=2)[:10000]}\n```"
