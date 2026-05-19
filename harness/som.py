"""Set-of-Mark (SoM) image annotation.

This module is what makes the pixel agent strong without forcing it to
do coordinate regression. The pipeline:

    raw screenshot + Playwright page
        ↓ extract_marks()
    list[Mark]  (one per interactable element, ordered)
        ↓ annotate_image()
    annotated screenshot bytes  (numbered badges + role-colored boxes)

The agent sees the ANNOTATED image and emits a discrete `mark_id`.
The harness resolves `mark_id` back to a pixel coordinate (the centre
of that mark's bounding box) and dispatches the actual Playwright
click. The agent never sees the underlying coordinates — pure visual
classification.

Marks are derived from the accessibility tree (`page.accessibility.
snapshot()`), NOT from our gym's `data-test-id` attributes. This
matters because it means a pixel agent built against this gym will
deploy unchanged against any real web app that exposes basic ARIA
roles (which is ~90% of production sites).

References:
- WebVoyager (arxiv 2401.13649) — SoM marks from DOM walk
- Set-of-Mark paper (arxiv 2310.11441) — original SoM technique
- VisualWebArena — uses SoM on AX tree for browser tasks
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont


# --------------------------------------------------------------------------- #
# Mark dataclass
# --------------------------------------------------------------------------- #

@dataclass
class Mark:
    """One interactable element on the page, ready to be numbered.

    Fields are intentionally minimal — the agent will see numbered
    boxes in the screenshot plus a per-turn text list of (mark_id,
    role, name). Coordinates are kept here for the harness to resolve
    clicks; they're NEVER shown to the agent.
    """
    mark_id: int                           # 1..N, stable within a turn
    role: str                              # ARIA role: button, link, textbox, ...
    name: str = ""                         # accessible name (the visible label)
    value: str = ""                        # for textbox: current text content
    disabled: bool = False
    # Bounding box in viewport coordinates (origin top-left, pixels)
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def area(self) -> int:
        return self.w * self.h

    def overlaps(self, other: "Mark", iou_threshold: float = 0.7) -> bool:
        """True if this mark's bbox overlaps `other` by ≥ IoU threshold."""
        ax1, ay1, ax2, ay2 = self.x, self.y, self.x + self.w, self.y + self.h
        bx1, by1, bx2, by2 = other.x, other.y, other.x + other.w, other.y + other.h
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return False
        intersection = (ix2 - ix1) * (iy2 - iy1)
        union = self.area + other.area - intersection
        return (intersection / union) >= iou_threshold if union > 0 else False

    def to_dict(self) -> dict[str, Any]:
        """Compact JSON form for the agent's text-side context.
        Note: x/y/w/h omitted — agent must rely on the visual marks."""
        return {
            "mark_id": self.mark_id,
            "role": self.role,
            "name": self.name[:80],
            **({"value": self.value[:60]} if self.value else {}),
            **({"disabled": True} if self.disabled else {}),
        }


# --------------------------------------------------------------------------- #
# Mark extraction from a Playwright page
# --------------------------------------------------------------------------- #

# Roles we treat as interactable. Source: ARIA WAI roles spec, filtered
# to ones a browser-agent actually clicks/types into.
_INTERACTABLE_ROLES = {
    "button", "link", "textbox", "searchbox", "combobox", "listbox",
    "checkbox", "radio", "menuitem", "menuitemcheckbox", "menuitemradio",
    "tab", "option", "switch", "slider", "spinbutton",
}

# Cap mark count per page so the agent isn't drowned in numbers.
_MAX_MARKS = 80

# Filter offscreen / zero-size elements before numbering.
_MIN_DIMENSION_PX = 8

# Per-role colors for the bounding-box outlines. Helps the model
# distinguish "I should click this" from "I should type into this"
# at a glance.
_ROLE_COLORS = {
    "button":    (37, 99, 235),    # blue-600
    "link":      (13, 148, 136),   # teal-600
    "textbox":   (234, 88, 12),    # orange-600
    "searchbox": (234, 88, 12),
    "combobox":  (147, 51, 234),   # purple-600
    "listbox":   (147, 51, 234),
    "checkbox":  (16, 185, 129),   # emerald-500
    "radio":     (16, 185, 129),
    "switch":    (16, 185, 129),
    "tab":       (217, 119, 6),    # amber-600
    "option":    (107, 114, 128),  # slate-500
    "menuitem":  (37, 99, 235),
    "menuitemcheckbox": (37, 99, 235),
    "menuitemradio": (37, 99, 235),
    "slider":    (147, 51, 234),
    "spinbutton":(234, 88, 12),
}
_DEFAULT_COLOR = (107, 114, 128)


async def extract_marks(page) -> list[Mark]:
    """Walk the accessibility tree and return one Mark per interactable.

    Uses a single page.evaluate() call to extract bounding boxes from
    the live DOM by ARIA role — avoids the round-trip cost of querying
    each element separately. Returns marks ordered top-to-bottom-left-
    to-right (stable reading order) with mark_id 1..N.
    """
    # Run all DOM work in one JS call. The browser already exposes
    # role + name + bbox + value + disabled through ARIA semantics.
    raw = await page.evaluate(
        """(args) => {
            const INTERACTABLE = new Set(args.roles);

            // Compute the implicit ARIA role of an element. Matches
            // the W3C ARIA-in-HTML mapping for the most common cases.
            function implicitRole(el) {
                const t = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                if (t === 'a' && el.hasAttribute('href')) return 'link';
                if (t === 'button') return 'button';
                if (t === 'input') {
                    if (type === 'checkbox') return 'checkbox';
                    if (type === 'radio') return 'radio';
                    if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
                    if (type === 'range') return 'slider';
                    if (type === 'number') return 'spinbutton';
                    if (type === 'search') return 'searchbox';
                    // text, email, password, url, tel, date, etc.
                    return 'textbox';
                }
                if (t === 'textarea') return 'textbox';
                if (t === 'select') return 'combobox';
                if (t === 'option') return 'option';
                if (t === 'summary') return 'button';
                return '';
            }

            function accessibleName(el) {
                // Order: aria-label > aria-labelledby > <label for=id> > visible text > placeholder > value > title
                const al = el.getAttribute('aria-label');
                if (al && al.trim()) return al.trim();
                const labelledby = el.getAttribute('aria-labelledby');
                if (labelledby) {
                    const ref = document.getElementById(labelledby);
                    if (ref && ref.innerText) return ref.innerText.trim();
                }
                if (el.id) {
                    const lab = document.querySelector('label[for="' + el.id + '"]');
                    if (lab && lab.innerText) return lab.innerText.trim();
                }
                const t = el.tagName.toLowerCase();
                if (['button', 'a', 'summary'].includes(t)) {
                    const inner = (el.innerText || '').trim();
                    if (inner) return inner;
                }
                const placeholder = el.getAttribute('placeholder');
                if (placeholder) return placeholder;
                const value = el.value || '';
                if (value && el.tagName.toLowerCase() !== 'textarea') return value;
                const title = el.getAttribute('title');
                if (title) return title;
                return (el.innerText || '').trim();
            }

            const out = [];
            const candidates = document.querySelectorAll(
                'a[href], button, input, textarea, select, summary, ' +
                '[role], [tabindex]:not([tabindex="-1"])'
            );
            const seen = new Set();

            candidates.forEach(el => {
                if (seen.has(el)) return;
                seen.add(el);

                // Resolve role: explicit attribute wins over implicit
                let role = (el.getAttribute('role') || '').toLowerCase();
                if (!role) role = implicitRole(el);
                if (!INTERACTABLE.has(role)) return;

                const rect = el.getBoundingClientRect();
                // Filter offscreen / collapsed elements
                if (rect.width < args.minDim || rect.height < args.minDim) return;
                if (rect.bottom < 0 || rect.top > window.innerHeight) return;
                if (rect.right < 0 || rect.left > window.innerWidth) return;

                // Skip if element is hidden via display:none / visibility:hidden
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' ||
                    parseFloat(style.opacity) < 0.05) return;

                out.push({
                    role: role,
                    name: accessibleName(el).slice(0, 200),
                    value: (el.value || '').slice(0, 100),
                    disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                });
            });

            return out;
        }""",
        {"roles": list(_INTERACTABLE_ROLES), "minDim": _MIN_DIMENSION_PX},
    )

    # Convert to Mark objects, sort by reading order, deduplicate
    # overlapping (e.g. an <a> wrapping a <button>), cap at _MAX_MARKS.
    marks = [
        Mark(
            mark_id=0,  # assigned after sort/dedupe
            role=r["role"], name=r["name"], value=r["value"],
            disabled=r["disabled"],
            x=r["x"], y=r["y"], w=r["w"], h=r["h"],
        )
        for r in raw
    ]
    # Stable reading order: top-to-bottom, then left-to-right
    marks.sort(key=lambda m: (m.y, m.x))

    # Deduplicate near-duplicates (e.g. <a><span><button>buy</button></span></a>
    # produces 2 interactables at almost the same bbox)
    deduped: list[Mark] = []
    for m in marks:
        if any(m.overlaps(prev, iou_threshold=0.7) for prev in deduped):
            continue
        deduped.append(m)
        if len(deduped) >= _MAX_MARKS:
            break

    # Assign mark_ids 1..N
    for i, m in enumerate(deduped, start=1):
        m.mark_id = i

    return deduped


# --------------------------------------------------------------------------- #
# Image annotation
# --------------------------------------------------------------------------- #

def _load_font(size: int = 14):
    """Pillow font loader with fallback. Returns a PIL ImageFont."""
    for candidate in [
        "C:\\Windows\\Fonts\\arialbd.ttf",   # Arial Bold (Windows)
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def annotate_image(png_bytes: bytes, marks: list[Mark]) -> bytes:
    """Overlay numbered badges + role-colored bounding boxes onto an
    existing screenshot. Returns annotated PNG bytes.

    Design:
    - 2px outline in the role's color around each mark's bbox
    - Numbered badge in the top-left of the bbox: white digit on a
      filled square in the role's color. Size scales slightly with N
      so 1-2 digits remain readable.
    """
    image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Adaptive font size: 14px is fine for ≤20 marks, shrink slightly
    # for higher counts so badges don't dominate small elements.
    font_size = 14 if len(marks) <= 30 else (12 if len(marks) <= 60 else 10)
    font = _load_font(font_size)

    for m in marks:
        color = _ROLE_COLORS.get(m.role, _DEFAULT_COLOR)
        rgba = (*color, 230)
        # Bounding box outline
        draw.rectangle(
            [m.x, m.y, m.x + m.w - 1, m.y + m.h - 1],
            outline=rgba, width=2,
        )
        # Numbered badge — filled rect + white digit
        label = str(m.mark_id)
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except AttributeError:
            text_w, text_h = font.getsize(label) if hasattr(font, "getsize") else (10, 12)
        pad = 3
        badge_w = text_w + pad * 2
        badge_h = text_h + pad * 2
        # Position the badge: top-left of bbox, nudged so it doesn't
        # spill outside the viewport on left-edge elements.
        bx = max(0, m.x)
        by = max(0, m.y)
        draw.rectangle(
            [bx, by, bx + badge_w, by + badge_h],
            fill=rgba,
        )
        draw.text(
            (bx + pad, by + pad - 1),
            label, fill=(255, 255, 255, 255), font=font,
        )

    annotated = Image.alpha_composite(image, overlay).convert("RGB")
    out = io.BytesIO()
    annotated.save(out, format="PNG", optimize=True)
    return out.getvalue()


# --------------------------------------------------------------------------- #
# Convenience: produce a text manifest of marks for the agent's prompt
# --------------------------------------------------------------------------- #

def marks_to_manifest(marks: list[Mark]) -> str:
    """A compact text list the agent sees alongside the annotated image.

    The image shows numbered boxes; this manifest tells the agent
    `role: name` for each number, so it can quickly find the right
    target without having to OCR text out of the screenshot.
    """
    if not marks:
        return "(no interactable marks detected on this page)"
    lines = []
    for m in marks:
        bits = [f"[{m.mark_id}] {m.role}"]
        if m.name:
            bits.append(f'"{m.name[:60]}"')
        if m.value:
            bits.append(f'value="{m.value[:40]}"')
        if m.disabled:
            bits.append("(disabled)")
        lines.append("  ".join(bits))
    return "\n".join(lines)
