#!/usr/bin/env python3
"""Rebuild phexts/security.phext now that the audit is published.

Plain-language chapters (1-6) are authored here to the site's UX bar
(FK <= 8, FRE >= 60, measured by this script with the audit's method).
The full technical record (chapters 7-12) is parsed verbatim from the
audit's own report, docs/SECURITY.md in wbic16/Exocortexia.

Usage: venv/bin/python scripts/build_security_phext.py <SECURITY.md> <out.phext>
"""
import re
import sys
from phext.phext import Phext
from phext.coordinate import Coordinate

PLAIN = {
    (1, 1, 1): ("wishnode.net — security page content phext (phexts/security.phext). "
                "Source of truth for the security page. The audit this page reports is "
                "docs/SECURITY.md in wbic16/Exocortexia @ exo 342a268 (2026-11-07): "
                "a full code audit plus a live pen-test of the suite at 9660d3b, a fix "
                "pass, and a 49-case live re-check. Plain chapters 1-6 are written for "
                "this site; chapters 7-12 hold the audit report word for word."),
    (1, 1, 2): "Security — Exocortexia | Phext, Inc.",
    (1, 1, 3): "Security",
    (1, 2, 1): "SUMMARY (plain English — rendered first)",
    (1, 2, 2): ("We asked for a hard check of these programs before we offer them to any "
                "office. A person read all the code. Then we attacked the programs live, "
                "the way a bad actor would. The check found real holes. One hole let a "
                "viewer read parts of records that should have stayed hidden. We fixed "
                "each hole we found. Then we ran the attacks again, and each one failed. "
                "The plain story is on this page. The full record is on this page too, "
                "below the plain words."),
    (2, 1, 1): "What the check found",
    (2, 1, 2): ("The check found five kinds of holes. None of them are still open. "
                "Here they are in plain words."),
    (2, 2, 1): "Hidden parts of records could be read",
    (2, 2, 2): ("This was the worst hole, and it was in Records Desk. Staff black out the "
                "parts of a record that the law protects. But the program kept the full "
                "text close at hand, and a viewer could get it. Search leaked it too. "
                "You could guess at a hidden word, and the hits told you if your guess "
                "was right."),
    (2, 3, 1): "Sign-in could switch itself off",
    (2, 3, 2): ("If the sign-in settings were half set, or set with a weak key, the "
                "programs did not complain. They just ran with no sign-in at all. A "
                "tool that guards records must not do that. If the settings are wrong, "
                "it should stop and say so."),
    (2, 4, 1): "Form codes could be guessed",
    (2, 4, 2): ("The codes that let a person track a form were short. They were also "
                "made from the form itself, in a set order. A patient person could "
                "work them out. Worse, one page would hand over a list of all the "
                "forms and their codes."),
    (2, 5, 1): "Forms took orders from other sites",
    (2, 5, 2): ("A form should take orders only from its own site. Ours took them from "
                "any site. A bad page could have sent a form, or changed one, in your "
                "name while you were signed in. Plain safety headers that tell "
                "browsers to be careful were missing too."),
    (2, 6, 1): "A huge request could crash a program",
    (2, 6, 2): ("A program read the size of a request and set aside that much room, "
                "with no cap. A request that claimed a huge size could kill the "
                "program. This worked before sign-in was even checked, so anyone "
                "could do it."),
    (3, 1, 1): "What we fixed, and how we know",
    (3, 1, 2): ("Hidden text now stays hidden. Page views, search, and exports all use "
                "the blacked-out copy. The full text opens only for a signed-in staff "
                "member whose name is on the staff list. In demo mode it does not open "
                "at all."),
    (3, 1, 3): ("Sign-in now fails shut. If the settings are missing, half set, or too "
                "weak, the program will not start. There is still a demo mode with no "
                "sign-in, but a person must choose it on purpose, by name. No tool "
                "wakes up open by accident."),
    (3, 1, 4): ("Tracking codes are now long and random. They are made by chance, not "
                "from the form. The space of codes is so large that guessing is not "
                "a real path in. Exports no longer hand out lists of codes."),
    (3, 1, 5): ("Forms now check where an order came from, and session forms carry a "
                "safety token. Cookies use the safe flags. Requests have size caps "
                "that bite before a program spends memory on them. The standard "
                "safety headers are now sent with each page."),
    (3, 1, 6): ("How we know: the suite is checked by 84 automated tests, and all 84 "
                "pass. We ran the live attacks again — 49 checks, and 49 passed. Four "
                "more checks show the programs refuse to start when sign-in is set up "
                "wrong. The sample data did not change in the fix. Make it again and "
                "you get the same files, byte for byte."),
    (4, 1, 1): "What is still limited",
    (4, 1, 2): ("These are sample programs. The small web server inside them is demo "
                "grade. It now has size caps and safety headers, but it has no rate "
                "limit — nothing slows a flood of requests — and it is not built to "
                "face the open internet on its own. A real office setup would put it "
                "behind a full web server."),
    (4, 1, 3): ("The tamper-proof record can now be locked with a key, and checked "
                "against a saved head mark, so a cut-short record shows. But a person "
                "must pin that head mark somewhere the record keeper cannot reach. "
                "The suite does not do that part for you yet. It is the operator's "
                "job, and we say so here so no one thinks it is done for them."),
    (4, 1, 4): ("Sign-in links travel in the web address, so they can land in logs. "
                "They live for two minutes and work once. A signed-in session lasts "
                "12 hours. Signing out clears your browser, but the server cannot cut "
                "a live session short. The safe cookie flags bound that risk; they "
                "do not erase it."),
    (4, 1, 5): ("One check did not run. A tool that scans the code libraries for known "
                "flaws would not install on our build machine. We read the list by "
                "hand: about ten libraries, all on current release lines. The scan "
                "stays on our list to run."),
    (5, 1, 1): "Reporting a problem",
    (5, 1, 2): ("Exocortexia is a public sample suite. It runs on made-up data. It "
                "holds no real records, and it is not a live state system. If you "
                "find a security flaw in the programs or on this site, please tell "
                "us. Use the “Ask about a pilot” form and say it is about security. "
                "We read every form."),
    (6, 1, 1): "Ask about a pilot",
    (6, 1, 2): ("Ask about a pilot for your office. Use the form on this site — the "
                "link says “Ask about a pilot.” Tell us which program you are "
                "interested in and what your office needs. When you send the form, "
                "you get a tracking code. A person from Phext, Inc. reads your form "
                "and replies."),
}

RECORD_TITLES = [
    ("scope and method", "FULL TECHNICAL RECORD — scope and method"),
    ("Findings and status", "FULL TECHNICAL RECORD — findings and status"),
    ("Pen-test battery — before / after", "FULL TECHNICAL RECORD — pen-test battery, before and after"),
    ("Re-verification numbers", "FULL TECHNICAL RECORD — re-verification numbers"),
    ("New operator surface (from this pass)", "FULL TECHNICAL RECORD — new operator surface"),
    ("Residual risks — stated plainly", "FULL TECHNICAL RECORD — residual risks, stated plainly"),
]

def syllables(word):
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and groups > 1:
        groups -= 1
    return max(1, groups)

def readability(text):
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = text.split()
    syl = sum(syllables(w) for w in words)
    n_w, n_s = max(1, len(words)), max(1, len(sentences))
    fk = 0.39 * (n_w / n_s) + 11.8 * (syl / n_w) - 15.59
    fre = 206.835 - 1.015 * (n_w / n_s) - 84.6 * (syl / n_w)
    return fk, fre, n_w

def split_blocks(md):
    return [b.strip() for b in re.split(r"\n\s*\n", md) if b.strip()]

def main():
    md_path, out_path = sys.argv[1], sys.argv[2]
    with open(md_path, "r", encoding="utf-8") as f:
        md = f.read()
    # split into preamble + ## sections
    parts = re.split(r"^## ", md, flags=re.M)
    preamble = parts[0]
    sections = {}
    for p in parts[1:]:
        title, _, rest = p.partition("\n")
        sections[title.strip()] = rest.strip()
    scrolls = dict(PLAIN)
    chapter = 7
    pre_blocks = [b for b in split_blocks(preamble) if not b.startswith("# ")]
    scrolls[(chapter, 1, 1)] = RECORD_TITLES[0][1]
    for i, b in enumerate(pre_blocks):
        scrolls[(chapter, 1, 2 + i)] = b
    chapter += 1
    for key, record_title in RECORD_TITLES[1:]:
        body = sections.get(key, "")
        if not body:
            raise SystemExit(f"section not found in SECURITY.md: {key}")
        scrolls[(chapter, 1, 1)] = record_title
        for i, b in enumerate(split_blocks(body)):
            scrolls[(chapter, 1, 2 + i)] = b
        chapter += 1
    buffer = ""
    for (c, s, b) in sorted(scrolls):
        buffer = Phext().replace(buffer, Coordinate.from_string(f"1.1.1/1.1.1/{c}.{s}.{b}"), scrolls[(c, s, b)])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(buffer)
    plain_text = " ".join(scrolls[k] for k in sorted(scrolls)
                          if k[0] <= 6 and not (k[2] == 1 and k[1] == 1 and k[0] > 1))
    fk, fre, n = readability(plain_text)
    print(f"security.phext rebuilt: {len(scrolls)} scrolls")
    print(f"plain chapters readability: FK {fk:.1f} (bar <= 8), FRE {fre:.1f} (bar >= 60), {n} words")

if __name__ == "__main__":
    main()
