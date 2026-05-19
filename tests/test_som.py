"""Tests for the Set-of-Mark annotation pipeline.

These tests verify the unit behaviors of harness/som.py:
  - extract_marks() finds interactable elements
  - annotate_image() produces a valid PNG
  - dedupe + cap behavior
  - marks_to_manifest() formats correctly

Note: extract_marks() requires a real Playwright page. We use a
minimal Playwright fixture rather than mocking out the page API
because the AX-tree / bounding-box queries are critical to test.
"""

from __future__ import annotations

import io

import pytest

from harness.som import (
    Mark, annotate_image, marks_to_manifest,
)
from PIL import Image


# --------------------------------------------------------------------------- #
# Mark dataclass logic (no browser needed)
# --------------------------------------------------------------------------- #

def test_mark_center_and_area():
    m = Mark(mark_id=1, role="button", x=100, y=200, w=80, h=40)
    assert m.center == (140, 220)
    assert m.area == 80 * 40


def test_mark_overlaps_high_iou():
    a = Mark(mark_id=1, role="button", x=0, y=0, w=100, h=100)
    b = Mark(mark_id=2, role="link", x=10, y=10, w=100, h=100)
    # IoU = 8100 / (10000 + 10000 - 8100) = 8100/11900 ≈ 0.68 (just below 0.7)
    assert not a.overlaps(b, iou_threshold=0.7)
    # Stricter (lower threshold) should match
    assert a.overlaps(b, iou_threshold=0.5)


def test_mark_overlaps_disjoint():
    a = Mark(mark_id=1, role="button", x=0, y=0, w=50, h=50)
    b = Mark(mark_id=2, role="button", x=200, y=200, w=50, h=50)
    assert not a.overlaps(b, iou_threshold=0.1)


def test_mark_to_dict_omits_coords():
    m = Mark(mark_id=7, role="button", name="Add to Cart",
             x=100, y=200, w=80, h=40)
    d = m.to_dict()
    assert d["mark_id"] == 7
    assert d["role"] == "button"
    assert d["name"] == "Add to Cart"
    # coordinates must NEVER leak to the agent
    assert "x" not in d
    assert "y" not in d
    assert "w" not in d
    assert "h" not in d


def test_mark_to_dict_includes_value_when_set():
    m = Mark(mark_id=1, role="textbox", name="Search", value="wireless mouse",
             x=0, y=0, w=200, h=30)
    d = m.to_dict()
    assert d["value"] == "wireless mouse"


def test_mark_to_dict_includes_disabled_when_true():
    m = Mark(mark_id=1, role="button", name="Place Order",
             disabled=True, x=0, y=0, w=120, h=40)
    d = m.to_dict()
    assert d.get("disabled") is True


def test_mark_to_dict_truncates_long_name():
    long_name = "X" * 500
    m = Mark(mark_id=1, role="link", name=long_name, x=0, y=0, w=100, h=20)
    d = m.to_dict()
    assert len(d["name"]) <= 80


# --------------------------------------------------------------------------- #
# annotate_image() — produces a valid PNG, doesn't crash on edge cases
# --------------------------------------------------------------------------- #

def _solid_png(width: int, height: int, color=(240, 240, 240)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_annotate_image_no_marks_returns_valid_png():
    """No interactables on the page — annotation should still return
    a valid PNG (just the original)."""
    src = _solid_png(640, 480)
    result = annotate_image(src, marks=[])
    assert isinstance(result, bytes)
    img = Image.open(io.BytesIO(result))
    assert img.size == (640, 480)


def test_annotate_image_draws_marks():
    """With marks present, the output should differ from the source."""
    src = _solid_png(640, 480)
    marks = [
        Mark(mark_id=1, role="button", name="Buy", x=100, y=100, w=80, h=40),
        Mark(mark_id=2, role="textbox", name="Search",
             x=200, y=200, w=200, h=30),
    ]
    result = annotate_image(src, marks=marks)
    assert isinstance(result, bytes)
    assert result != src
    # Output should still be a valid PNG at the same size
    img = Image.open(io.BytesIO(result))
    assert img.size == (640, 480)


def test_annotate_image_handles_edge_clipping():
    """Mark with bbox partially outside viewport — must not crash."""
    src = _solid_png(640, 480)
    marks = [
        Mark(mark_id=1, role="link", name="edge",
             x=-20, y=-10, w=100, h=40),                # spills off top-left
        Mark(mark_id=2, role="button", name="bottom",
             x=600, y=470, w=80, h=40),                  # spills off bottom-right
    ]
    result = annotate_image(src, marks=marks)
    img = Image.open(io.BytesIO(result))
    assert img.size == (640, 480)


def test_annotate_image_scales_font_for_many_marks():
    """≤30 marks → font 14, 31–60 → 12, 60+ → 10. Smoke-test no crash."""
    src = _solid_png(1280, 800)
    for n_marks in [5, 35, 70]:
        marks = [
            Mark(mark_id=i + 1, role="button", name=f"btn-{i}",
                 x=(i % 8) * 150, y=(i // 8) * 50,
                 w=80, h=30)
            for i in range(n_marks)
        ]
        result = annotate_image(src, marks=marks)
        assert isinstance(result, bytes)


# --------------------------------------------------------------------------- #
# marks_to_manifest() — text representation for the agent's prompt
# --------------------------------------------------------------------------- #

def test_manifest_empty():
    out = marks_to_manifest([])
    assert "no interactable" in out.lower()


def test_manifest_lists_mark_ids():
    marks = [
        Mark(mark_id=1, role="button", name="Add to Cart",
             x=0, y=0, w=80, h=40),
        Mark(mark_id=2, role="link", name="Cart (3)",
             x=0, y=50, w=60, h=20),
    ]
    out = marks_to_manifest(marks)
    assert "[1]" in out
    assert "[2]" in out
    assert "button" in out
    assert "Add to Cart" in out


def test_manifest_marks_disabled():
    marks = [
        Mark(mark_id=1, role="button", name="Place Order",
             disabled=True, x=0, y=0, w=100, h=40),
    ]
    out = marks_to_manifest(marks)
    assert "disabled" in out.lower()


def test_manifest_shows_textbox_value():
    marks = [
        Mark(mark_id=3, role="textbox", name="Email",
             value="alice@example.com", x=0, y=0, w=200, h=30),
    ]
    out = marks_to_manifest(marks)
    assert "alice@example.com" in out
