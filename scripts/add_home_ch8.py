#!/usr/bin/env python3
"""Add chapter 8 ("How this site works") to phexts/home.phext.

The phext builder regenerates home.phext from the old static pages and
does not know chapter 8; this hand addition is re-applied after any
builder re-run. Uses libphext replace semantics (never insert), so no
existing scroll moves. Run with the wishnode venv python:
  venv/bin/python scripts/add_home_ch8.py phexts/home.phext
"""
import sys
from phext.phext import Phext
from phext.coordinate import Coordinate

SCROLLS = {
    (8, 1, 1): "How this site works",
    (8, 1, 2): ("Every word on this site is kept in a phext. A phext is a way of storing "
                "information as plain text that both people and computers can read. "
                "When we fix a word, we fix it in the phext, and the site is rebuilt from it."),
    (8, 1, 3): ("Each page has its own phext. The home page, each program page, the test "
                "results, and the law sheets each live in their own file of plain text. "
                "A small server program called SQ serves those files to the tools that "
                "build and run this site."),
    (8, 2, 1): "Your form, your record",
    (8, 2, 2): ("When you send a form, it goes into a phext of your own. No one else's form "
                "is in it. The site also keeps a short claim card for your form: your "
                "tracking code, the date, a proof code made from your form's words, and "
                "where your form stands."),
    (8, 2, 3): ("The claim card never holds your words. It points to your record and holds "
                "the proof code, so anyone can check that a form was not changed after it "
                "was sent. When the state of your form changes, a new line is added to the "
                "card. Old lines are never removed or changed."),
    (8, 3, 1): "Who can do what",
    (8, 3, 2): ("Anyone can read the pages. Only you can read your form, with your tracking "
                "code or by signing in. Our staff can move a form from one state to the "
                "next, and each move is written on the claim card with the role that made "
                "it. Only the site owner can change the words on the pages."),
    (8, 3, 3): ("Sign-in uses the same account as edit.phext.io, the editor where these "
                "programs are built. When sign-in is turned on, it shows you every form "
                "tied to your account. Until then, your tracking code does the same job."),
}

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "phexts/home.phext"
    with open(path, "r", encoding="utf-8") as f:
        buffer = f.read()
    for (c, s, b), text in SCROLLS.items():
        buffer = Phext().replace(buffer, Coordinate.from_string(f"1.1.1/1.1.1/{c}.{s}.{b}"), text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(buffer)
    print(f"chapter 8 written to {path} ({len(SCROLLS)} scrolls)")

if __name__ == "__main__":
    main()
