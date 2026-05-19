"""Pixel-based browser agent — sees Set-of-Mark annotated screenshots.

The pixel sibling of ``LLMBrowserAgent``. Same Anthropic Claude
backend, same gym, same verifier, same trajectory schema. Different
perception:

  DOM/JSON agent (llm_agent.py):
      observation = JSON list of [data-test-id] interactables
      action      = click(selector), fill(selector, value), ...

  Pixel/SoM agent (this file):
      observation = annotated screenshot + URL + manifest text
      action      = click(mark_id), type_text(mark_id, text), ...

Why SoM (Set-of-Mark) instead of raw pixel coordinates?
  Holding the VLM constant (Claude Sonnet, no GUI fine-tuning), SoM
  with AX-tree-derived marks substantially outperforms coordinate
  regression on browser tasks. WebVoyager, SeeAct, VisualWebArena all
  use this approach. See PIXEL_VS_JSON.md for the research survey.

Why extended thinking + plan-then-act?
  Multi-turn browser tasks like C4/mega_checkout have 9 milestones and
  ~20 steps. Without explicit planning the agent reacts step-by-step
  and loses the thread. Plan-then-act forces a persistent mental model
  that the agent revises across turns — closer to how a real user
  works through a complex checkout.

Why no `navigate(url)` tool?
  The whole point of the pixel agent is to test pure visual navigation
  — what an agent can do on an unfamiliar UI with no a-priori route
  knowledge. The DOM agent has navigate(); this one doesn't. The
  agent must click its way to every page.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from harness.runner import BrowserCtx
from harness.som import (
    Mark, annotate_image, extract_marks, marks_to_manifest,
)


# --------------------------------------------------------------------------- #
# Tool spec for Claude — discrete, mark-id-based
# --------------------------------------------------------------------------- #

TOOLS_PIXEL = [
    {
        "name": "click",
        "description": (
            "Click the interactable element marked with the given mark_id "
            "in the current screenshot. Use this for buttons, links, "
            "checkboxes, dropdowns, radio buttons — anything you see "
            "marked with a numbered box. The harness resolves the mark "
            "to a coordinate; you only need to pick the number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mark_id": {"type": "integer",
                            "description": "The numbered mark to click."},
                "reason": {"type": "string"},
            },
            "required": ["mark_id"],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Click the marked input element (textbox/searchbox) and type "
            "the given text into it. Does NOT clear existing text first — "
            "if you need to overwrite, send `key` with name='Control+a' "
            "and then key with name='Backspace' before this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mark_id": {"type": "integer",
                            "description": "The textbox/searchbox mark."},
                "text": {"type": "string",
                         "description": "The text to type."},
                "reason": {"type": "string"},
            },
            "required": ["mark_id", "text"],
        },
    },
    {
        "name": "key",
        "description": (
            "Press a keyboard key (or chord). Examples: 'Enter' (submit "
            "form), 'Tab', 'Escape', 'Backspace', 'ArrowDown' (navigate "
            "dropdown options), 'Control+a' (select all)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "scroll",
        "description": (
            "Scroll the viewport up or down by the given pixel amount. "
            "Use this when the marks you need are not visible — content "
            "below the fold (related products, full review list, etc.) "
            "needs to be scrolled into view before it can be marked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]},
                "amount_px": {"type": "integer",
                              "description": "Typical: 400-800 pixels."},
                "reason": {"type": "string"},
            },
            "required": ["direction", "amount_px"],
        },
    },
    {
        "name": "finish",
        "description": (
            "End the episode. Call this ONLY after verifying that the "
            "task goal is fully achieved (e.g. confirmation page is "
            "visible, order ID is shown, all required milestones in your "
            "plan are marked done)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": [],
        },
    },
]


# --------------------------------------------------------------------------- #
# System prompt — plan-then-act, no DOM language, no selectors
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """\
You are operating a web browser to complete an e-commerce task on the
ShopGym site. You see the page through a SCREENSHOT — the same view
a human would see — annotated with numbered colored boxes around every
interactable element (buttons, links, inputs, dropdowns).

═══════════════════════════════════════════════════════════════════════════
HOW YOU SEE THE PAGE
═══════════════════════════════════════════════════════════════════════════

Each turn I give you:
  1. An annotated screenshot of the current page (1280×800 viewport)
  2. The current URL
  3. A text manifest listing each numbered mark: `[N] role "name"`
  4. The task brief (your goal)
  5. The result of your last action (if any)

The numbered boxes are colored by role:
  • BLUE        = button (click to perform an action)
  • TEAL        = link (click to navigate)
  • ORANGE      = textbox / searchbox (type into)
  • PURPLE      = combobox / select dropdown (click to open, then click an option)
  • EMERALD     = checkbox / radio / switch (click to toggle)
  • AMBER       = tab (click to switch view)

Mark IDs are 1..N, ordered top-to-bottom-left-to-right. **They are
re-numbered every turn** — mark 7 last turn may be mark 3 now. Always
read the current image, never assume continuity.

═══════════════════════════════════════════════════════════════════════════
HOW YOU ACT
═══════════════════════════════════════════════════════════════════════════

You have five tools, all reference mark IDs (never coordinates):

  click(mark_id)
      Click button/link/checkbox/dropdown-opener.
  type_text(mark_id, text)
      Click textbox + type text. Doesn't clear first.
  key(name)
      Press a key. Examples: "Enter" (submit), "Tab", "Escape",
      "Backspace", "ArrowDown", "Control+a".
  scroll(direction, amount_px)
      Scroll viewport. Use when you need to see marks below the fold.
  finish(reason)
      End the episode. Only when goal is confirmed achieved.

There is NO `navigate(url)` tool. You must reach every page by
clicking visible links — exactly like a human on an unfamiliar site.

There is NO `select_option` for dropdowns. Click the dropdown to
open it, then in the next turn click the option you see.

═══════════════════════════════════════════════════════════════════════════
RESPONSE STRUCTURE — plan-then-act, every single turn
═══════════════════════════════════════════════════════════════════════════

Every visible response (after your private thinking) MUST contain
three sections in this order:

  ## Plan
  Numbered list of steps toward the goal. Mark each as [done] /
  [in progress] / [next] / [later]. REVISE this plan as new
  information arrives — don't just rebuild it from scratch each turn,
  amend the existing plan. Always anchor it to the original task
  brief verbatim.

  ## What I see now
  Brief description of the visible page. Reference specific mark
  numbers when relevant: "the green Add to Cart button is mark 23".
  Note any flash banners (red = error, green = success). If you see
  a confirmation page, an error, or unexpected content, call it out.

  ## Next action
  One tool_use block. Just one action per turn.

═══════════════════════════════════════════════════════════════════════════
PATTERNS YOU WILL NEED
═══════════════════════════════════════════════════════════════════════════

Form filling:
  - type_text(mark_id, text) clicks-then-types — one call is enough.
  - To overwrite existing text: key("Control+a") → key("Backspace") →
    type_text(mark_id, new_text)

Dropdown selection:
  - Turn N:   click(opener_mark)
  - Turn N+1: the dropdown is now open; new marks appear for each
              option; click the option you want.

Form submission:
  - Either: click(submit_button_mark)
  - Or:     key("Enter") when focused inside the form

Recovering from errors:
  - If a flash-error banner is visible in the screenshot, READ IT.
    It tells you what went wrong (e.g. "Please pick an option for
    Cotton T-Shirt" means you forgot variant selection).
  - If nothing visible changed after your last action, your click
    may have missed. Re-examine the screenshot before retrying.

Scrolling:
  - If no mark matches what you need, the target is likely below the
    fold. Scroll down 600px and re-examine.

═══════════════════════════════════════════════════════════════════════════
WHEN TO CALL finish
═══════════════════════════════════════════════════════════════════════════

ONLY when:
  1. Your Plan shows every step as [done]
  2. The visible page confirms the outcome (e.g. order confirmation
     page with an order ID, "subscription created" page, return
     confirmation, etc.)

Premature finish() loses points. If unsure, take one more action to
verify.

═══════════════════════════════════════════════════════════════════════════

The task brief is your goal. Read it literally. If it says "Home
address" use Home, not Work. If it says "size M Black" pick exactly
that variant. If it says "under $550", check the running subtotal.
"""


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #

class PixelBrowserAgent:
    """An Anthropic-backed pixel/SoM browser agent.

    Pass ``model`` to override the default (Claude Sonnet 4.5).
    Set ANTHROPIC_API_KEY in the environment.
    """

    def __init__(self, model: str | None = None, max_steps: int = 30,
                 verbose: bool = True, thinking_budget: int = 4000):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model or os.getenv(
            "ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929",
        )
        self.max_steps = max_steps
        self.verbose = verbose
        self.thinking_budget = thinking_budget

    async def run(self, ctx: BrowserCtx, task_brief: str) -> None:
        messages: list[dict[str, Any]] = []
        last_action_result: str = ""

        for turn in range(self.max_steps):
            # ─── OBSERVE: capture screenshot, extract marks, annotate ───
            marks = await extract_marks(ctx.page)
            raw_png = await ctx.page.screenshot(full_page=False)
            annotated_png = annotate_image(raw_png, marks)
            manifest = marks_to_manifest(marks)
            b64 = base64.standard_b64encode(annotated_png).decode("ascii")

            url = ctx.page.url
            user_text = (
                f"URL: {url}\n"
                f"Task: {task_brief}\n"
                f"\n"
                f"Visible marks ({len(marks)}):\n{manifest}\n"
                f"\n"
                f"Last action result: {last_action_result or '(this is your first turn)'}"
            )

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            })

            # ─── THINK + ACT: call Claude with extended thinking ───
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": self.thinking_budget,
                    },
                    system=SYSTEM_PROMPT + f"\n\n## TASK\n\n{task_brief}",
                    tools=TOOLS_PIXEL,
                    messages=messages,
                )
            except Exception as e:
                if self.verbose:
                    print(f"[pixel_agent] API error: {type(e).__name__}: {e}")
                break

            # ─── PARSE the response ───
            tool_call = None
            tool_use_id = None
            text_parts: list[str] = []
            thinking_text: str = ""
            for block in resp.content:
                btype = getattr(block, "type", None)
                if btype == "thinking":
                    # Extended-thinking block — capture for trajectory
                    thinking_text = getattr(block, "thinking", "")
                elif btype == "text":
                    text_parts.append(block.text)
                elif btype == "tool_use" and tool_call is None:
                    tool_call = {
                        "name": block.name,
                        "input": dict(block.input or {}),
                    }
                    tool_use_id = block.id

            visible_text = "\n".join(text_parts)
            raw_model_output = (
                (f"<thinking>\n{thinking_text}\n</thinking>\n\n" if thinking_text else "")
                + visible_text
            )

            # Persist the full assistant turn for conversation continuity.
            # We preserve ALL blocks (including thinking) — Anthropic
            # requires thinking blocks to be passed back to maintain
            # tool_use context.
            messages.append({
                "role": "assistant",
                "content": [
                    self._serialize_block(b) for b in resp.content
                ],
            })

            if tool_call is None:
                if self.verbose:
                    print(f"[pixel_agent] no tool call. visible={visible_text[:200]!r}")
                break

            kind = tool_call["name"]
            args = tool_call["input"]
            if self.verbose:
                print(f"[pixel_agent] step {turn}: {kind}({json.dumps(args)[:120]})")

            # ─── DISPATCH the tool to BrowserCtx ───
            try:
                step_record = None
                if kind == "click":
                    step_record = await ctx.click_mark(
                        mark_id=int(args["mark_id"]),
                        marks=marks,
                        reasoning=args.get("reason", ""),
                    )
                elif kind == "type_text":
                    step_record = await ctx.type_into_mark(
                        mark_id=int(args["mark_id"]),
                        marks=marks,
                        text=args["text"],
                        reasoning=args.get("reason", ""),
                    )
                elif kind == "key":
                    step_record = await ctx.key_press(
                        name=args["name"],
                        reasoning=args.get("reason", ""),
                    )
                elif kind == "scroll":
                    step_record = await ctx.scroll_by(
                        direction=args["direction"],
                        amount_px=int(args["amount_px"]),
                        reasoning=args.get("reason", ""),
                    )
                elif kind == "finish":
                    if self.verbose:
                        print(f"[pixel_agent] finishing: {args.get('reason', '')}")
                    break
                else:
                    raise ValueError(f"unknown tool {kind}")

                # Decorate the StepRecord with reasoning + token info
                if step_record is not None:
                    step_record.raw_model_output = raw_model_output[:4000]
                    if hasattr(resp, "usage") and resp.usage:
                        step_record.tokens_in = int(getattr(resp.usage, "input_tokens", 0) or 0)
                        step_record.tokens_out = int(getattr(resp.usage, "output_tokens", 0) or 0)

                # Build a concise result string for the next turn's user message
                if step_record is None:
                    last_action_result = "(no record)"
                elif step_record.action_error:
                    last_action_result = (
                        f"ERROR: {step_record.action_error}. "
                        f"URL is now {step_record.url_after}."
                    )
                else:
                    last_action_result = (
                        f"OK ({kind}). URL is now {step_record.url_after}. "
                        f"Newly fired milestones: "
                        f"{step_record.milestones_fired_this_step or '[]'}. "
                        f"Running score: {step_record.running_score:.2f}."
                    )
            except Exception as e:
                last_action_result = (
                    f"DISPATCH ERROR: {type(e).__name__}: {e}"
                )
                if self.verbose:
                    print(f"[pixel_agent] dispatch error: {last_action_result}")

            # Append the tool_result so Claude can ground its next thinking
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": last_action_result,
                    },
                ],
            })

    @staticmethod
    def _serialize_block(block: Any) -> dict[str, Any]:
        """Convert an Anthropic content block (Pydantic model) to the
        plain dict shape needed for sending back into messages."""
        btype = getattr(block, "type", None)
        if btype == "thinking":
            return {
                "type": "thinking",
                "thinking": getattr(block, "thinking", ""),
                "signature": getattr(block, "signature", ""),
            }
        if btype == "text":
            return {"type": "text", "text": getattr(block, "text", "")}
        if btype == "tool_use":
            return {
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": dict(getattr(block, "input", {}) or {}),
            }
        # Fallback — return whatever shape is present
        return {"type": btype or "unknown"}
