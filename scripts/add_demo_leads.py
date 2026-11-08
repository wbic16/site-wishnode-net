#!/usr/bin/env python3
"""Add the "Try it now" live-demo lead scrolls to the wishnode page phexts.

Task 27.6.8/8.6.11/5.6.8: the site must lead with the working software,
not with description. Each app phext gains:
  (1,2,3) — plain words: what to click in the live demo, what you see.
  (1,2,4) — the demo-mode honesty note (open demo, made-up data; a real
            deployment adds sign-in through edit.phext.io).
The renderer (scripts/render_site.py, render_app) shows these two
scrolls in a "Try it now" box right after the plain summary, with a
button to /apps/<slug>/.

home.phext gains:
  (1,1,4) — hero lede rewritten to lead with the live demos.
  (3,1,1) — cards heading: "Use the five applications now".
  (8,4,1)/(8,4,2) — a "The live demos" section in "How this site works".

Idempotent: scrolls are replaced, never inserted (replace does not
renumber neighbours). Run with the wishnode venv python:
    ~/wishnode-venv/bin/python scripts/add_demo_leads.py
Exits non-zero if any new main-copy scroll breaks the UX bars
(FK <= 8, FRE >= 60, same method as scripts/build_security_phext.py).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_security_phext import readability  # noqa: E402
from phext.coordinate import Coordinate  # noqa: E402
from phext.phext import Phext  # noqa: E402

PX = Phext()
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "phexts")

HONESTY = (
    "This demo is open to all, and it uses made-up data. No sign-in is "
    "needed, and no real files are here. In a real setup for your office, "
    "staff sign in first through edit.phext.io, and the files are your "
    "own real ones."
)

TRY_IT = {
    "records-desk": (
        "Click the button below to open the live demo. Type a word in the "
        "search box and press Search. Then open a file from the list. You "
        "see just what the public sees: the parts the law protects stay "
        "blacked out, and the rest reads in full."
    ),
    "minutes-publisher": (
        "Click the button below to open the live demo. You will see the "
        "boards and their meetings. Each meeting shows if its agenda and "
        "its notes went up on time or late. The link named Static "
        "snapshot shows the one finished page a board can post for the "
        "public."
    ),
    "contract-ledger": (
        "Click the button below to open the live demo. You will see the "
        "list of contracts. The alerts list shows which contracts end "
        "soon. It also flags the ones that are not on the state public "
        "list."
    ),
    "data-catalog": (
        "Click the button below to open the live demo. You will see each "
        "dataset and how fresh it is. You can ask the demo to check the "
        "links. It shows which links still work and which ones fail."
    ),
    "forms-router": (
        "Click the button below to open the live demo. Fill in the short "
        "form and send it. You will get a tracking code. Keep your code: "
        "with it, the tracking page shows where your form stands."
    ),
}

HOME_LEDE = (
    "All five programs run live on this site. You can try each one now. "
    "They use made-up data, so click freely: you cannot break a thing. "
    "Exocortexia is a set of five sample programs for state and local "
    "offices. They help staff share public records, post meeting notes, "
    "track contracts, list public data, and take in forms. We built them "
    "for states with fewer than 5 million people, and we followed "
    "Nebraska law as we built them."
)

HOME_CARDS_HEADING = "Use the five applications now"

HOW_HEADING = "The live demos"

HOW_BODY = (
    "The five programs on this site are not pictures or write-ups. Each "
    "one runs on this host, and the demo links open the real program. "
    "The demos hold made-up data and ask for no sign-in. A real setup "
    "for an office adds sign-in through edit.phext.io and holds that "
    "office's own files. Each demo runs as its own small service, so if "
    "one demo stops, the pages and the other demos still work."
)


def coord(c, s, b):
    return Coordinate.from_string(f"1.1.1/1.1.1/{c}.{s}.{b}")


def load(name):
    with open(os.path.join(ROOT, name + ".phext"), encoding="utf-8") as f:
        return f.read()


def save(name, buffer):
    with open(os.path.join(ROOT, name + ".phext"), "w", encoding="utf-8") as f:
        f.write(buffer)


def check(label, text, failures):
    fk, fre, n = readability(text)
    ok = fk <= 8.0 and fre >= 60.0
    print(f"{label}: FK {fk:.1f} / FRE {fre:.1f} / {n} words — {'OK' if ok else 'OVER BAR'}")
    if not ok:
        failures.append(label)


def main():
    failures = []
    for slug, text in TRY_IT.items():
        buf = load(slug)
        buf = PX.replace(buf, coord(1, 2, 3), text)
        buf = PX.replace(buf, coord(1, 2, 4), HONESTY)
        save(slug, buf)
        check(f"{slug} try-it", text, failures)
    check("shared honesty note", HONESTY, failures)

    home = load("home")
    home = PX.replace(home, coord(1, 1, 4), HOME_LEDE)
    home = PX.replace(home, coord(3, 1, 1), HOME_CARDS_HEADING)
    home = PX.replace(home, coord(8, 4, 1), HOW_HEADING)
    home = PX.replace(home, coord(8, 4, 2), HOW_BODY)
    save("home", home)
    check("home lede", HOME_LEDE, failures)
    check("how-it-works demos section", HOW_BODY, failures)

    if failures:
        print("FAILED scrolls:", ", ".join(failures))
        return 1
    print("demo leads written; all new copy inside the bars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
