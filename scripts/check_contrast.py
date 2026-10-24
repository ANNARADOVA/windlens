#!/usr/bin/env python3
"""WCAG contrast-ratio check for WindLens's actual color palette.

Reads the --tokens defined in workspace/styles.css's :root and checks every
text/background pair that's actually plausible in the UI (listed in PAIRS
below -- update this list by hand if the palette or its usage changes).
WCAG AA requires >= 4.5:1 for normal text, >= 3:1 for large text (>=18px,
or >=14px bold).

Usage: python3 scripts/check_contrast.py
Exits non-zero if any checked pair fails its AA threshold.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES = ROOT / "workspace/styles.css"

# (foreground_token, background_token, "normal" | "large", where it's used)
PAIRS = [
    ("ink", "paper", "normal", "primary body text on the page background"),
    ("ink", "panel", "normal", "primary body text on card/panel backgrounds"),
    ("muted", "paper", "normal", "secondary/caption text on the page background"),
    ("muted", "panel", "normal", "secondary/caption text on card backgrounds"),
    ("signal-dark", "paper", "normal", "accent-colored text (links, highlights) on the page background"),
    ("signal", "paper", "large", "accent-colored large text/headings on the page background"),
    ("paper", "navy", "normal", "sidebar nav text (light on dark)"),
    ("signal-light", "navy", "normal", "accent-colored text on dark/navy backgrounds (hero status badge, chart tooltips) -- signal-dark is for light backgrounds only, signal-light is the dark-background counterpart"),
    ("sage", "paper", "normal", "status/positive-signal text on the page background"),
]


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1 = relative_luminance(hex_to_rgb(fg_hex))
    l2 = relative_luminance(hex_to_rgb(bg_hex))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def load_tokens() -> dict[str, str]:
    text = STYLES.read_text(encoding="utf-8")
    root_line = re.search(r":root\s*\{([^}]*)\}", text)
    if not root_line:
        raise SystemExit("Could not find :root token block in styles.css")
    tokens = dict(re.findall(r"--([a-zA-Z-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", root_line.group(1)))
    return tokens


def main() -> int:
    tokens = load_tokens()
    threshold = {"normal": 4.5, "large": 3.0}
    failures = 0
    for fg, bg, size, where in PAIRS:
        if fg not in tokens or bg not in tokens:
            print(f"SKIP: --{fg} or --{bg} not found in styles.css tokens")
            continue
        ratio = contrast_ratio(tokens[fg], tokens[bg])
        need = threshold[size]
        status = "OK  " if ratio >= need else "FAIL"
        if ratio < need:
            failures += 1
        print(f"{status} {ratio:5.2f}:1 (need {need}:1, {size}) -- --{fg} on --{bg} -- {where}")
    if failures:
        print(f"\n{failures} pair(s) below WCAG AA. Darken the foreground or lighten/darken the background.")
        return 1
    print("\nAll checked pairs meet WCAG AA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
