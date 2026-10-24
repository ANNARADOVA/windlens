#!/usr/bin/env python3
"""Static check for buttons/interactive elements with no apparent JS wiring.

This is NOT a real click-through test (that would need a headless browser --
Playwright or similar -- which is a new dependency not yet installed/flagged
in this project; ask before adding it). This is a cheap, stdlib-only proxy:
for every <button id="..."> or <a id="..."> in workspace/index.html, check
that id string appears somewhere in workspace/app.js (via $('id'),
getElementById('id'), or any other reference). A hit doesn't prove the
control genuinely works end to end -- only that nothing obviously forgot to
wire it up at all (exactly the class of bug the old "Present" button was:
present in HTML, in a component whose JS never actually gave it the right
behavior). Treat a flagged id as "go look at this", not as a confirmed bug.

Usage: python3 scripts/check_dead_controls.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "workspace/index.html"
JS_FILES = sorted((ROOT / "workspace").glob("*.js"))


def main() -> int:
    html = HTML.read_text(encoding="utf-8")
    js_text = "\n".join(p.read_text(encoding="utf-8") for p in JS_FILES)

    # Interactive elements with an id: <button id="x" ...> or <a id="x" ...>
    controls = re.findall(r'<(?:button|a)\b[^>]*\bid="([a-zA-Z0-9_-]+)"', html)

    unwired = []
    for control_id in sorted(set(controls)):
        # Any mention of the id in JS at all -- $('id'), getElementById('id'),
        # querySelector('#id'), or a bare string reference.
        pattern = re.compile(rf"""['"]{re.escape(control_id)}['"]""")
        if not pattern.search(js_text):
            unwired.append(control_id)

    print(f"Checked {len(set(controls))} interactive element(s) with an id in workspace/index.html.")
    if unwired:
        print("\nNo reference found in any workspace/*.js file for:")
        for cid in unwired:
            print(f"  - #{cid}")
        print("\nGo look at each by hand -- this script can't tell you WHY, only that nothing in the JS mentions the id at all.")
        return 1
    print("Every interactive element's id is referenced somewhere in the JS. (Still verify behavior by hand -- this only catches total omission, not a handler that's wired but broken.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
