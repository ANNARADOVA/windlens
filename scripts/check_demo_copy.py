#!/usr/bin/env python3
"""Scan jury-facing demo text for process-revealing, debug-looking, or
self-narrating language that should never reach a submitted prototype.

Usage: python3 scripts/check_demo_copy.py
Exits non-zero (and prints every hit as file:line: match) if anything is found.
This is a blunt substring/regex scan, not a style guide -- a clean run does
not mean the copy is good, only that it avoids this specific, previously
recurring failure mode. Add to this list whenever a new instance of the
pattern turns up; don't just fix the one line.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES = [
    *sorted((ROOT / "workspace").glob("*.js")),
    *sorted((ROOT / "workspace").glob("*.html")),
    ROOT / "src/windlens/insurance_report.py",
    ROOT / "docs/EXAMPLE_INSURANCE_REPORT_T3.md",
]

# Each pattern is (regex, why it's banned). Case-insensitive.
BANNED = [
    (r"\btonight\b", "reveals the build process / timeline, not product copy"),
    (r"\bovernight\b", "reveals the build process / timeline, not product copy"),
    (r"\bwe built\b", "talks about building the tool, not what it does for the reader"),
    (r"\bbuilt over\b", "reveals the build process / timeline"),
    (r"\bthis prototype\b", "self-referential about being a prototype rather than stating facts"),
    (r"\bthe demo\b", "calls itself a demo instead of reading as a finished product"),
    (r"\bthis demo\b", "calls itself a demo instead of reading as a finished product"),
    (r"\bdishonest\b", "self-narrates its own honesty instead of just stating facts"),
    (r"\bfabricat\w*", "self-narrates its own honesty instead of just stating facts"),
    (r"\bhonest view\b", "self-narrates its own honesty instead of just stating facts"),
    (r"\bto be transparent\b", "self-narrates its own honesty instead of just stating facts"),
    (r"\bnot hidden\b", "self-narrates its own honesty instead of just stating facts"),
    (r"schema_version", "raw internal/debug field name leaking into visible text"),
    (r"\bn/a\s*[-—]\s*not published by the challenge organiser", "leftover internal provenance note, no reader value"),
    (r"\bchecksum\b", "internal data-integrity detail, not reader-facing content"),
    (r"pipeline version", "internal build/version detail, not reader-facing content"),
    (r"\bv\d+(\.\d+)?\s*(self[- ]validation|wind_first|run_baywa)", "raw internal version/pipeline tag"),
]

COMPILED = [(re.compile(pat, re.IGNORECASE), why) for pat, why in BANNED]


def main() -> int:
    hits = 0
    for path in FILES:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for pattern, why in COMPILED:
                m = pattern.search(line)
                if m:
                    hits += 1
                    rel = path.relative_to(ROOT)
                    print(f"{rel}:{lineno}: '{m.group(0)}' -- {why}")
    if hits:
        print(f"\n{hits} finding(s). Fix the copy, don't just widen this list to ignore it.")
        return 1
    print("Clean: no banned patterns found in the scanned files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
