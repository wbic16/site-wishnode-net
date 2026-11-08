#!/usr/bin/env python3
"""Render wishnode.net's static pages from its page phexts, hosted in SQ.

The phexts are the source of truth; the HTML in the docroot is a build
artifact. This script reads every scroll through the SQ HTTP API (pages
tenant key, server-side only), and writes self-contained HTML pages in
the site's existing design.

Env: SQ_URL (default http://127.0.0.1:8931), SQ_PAGES_KEY (required),
     OUT_DIR (required), CSS_PATH (default ../assets/site.css).
"""

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

SQ_URL = os.environ.get("SQ_URL", "http://127.0.0.1:8931").rstrip("/")
SQ_PAGES_KEY = os.environ.get("SQ_PAGES_KEY", "")
OUT_DIR = os.environ.get("OUT_DIR", "")
CSS_PATH = os.environ.get("CSS_PATH", os.path.join(os.path.dirname(__file__), "..", "assets", "site.css"))

APPS = ["records-desk", "minutes-publisher", "contract-ledger", "data-catalog", "forms-router"]
APP_NAMES = {
    "records-desk": "Records Desk",
    "minutes-publisher": "Minutes Publisher",
    "contract-ledger": "Contract Ledger",
    "data-catalog": "Data Catalog",
    "forms-router": "Forms Router",
}

def sq_query(phext_name):
    url = SQ_URL + "/api/v2/query?" + urllib.parse.urlencode(
        {"p": phext_name, "from": "1.1.1/1.1.1/1.1.1", "to": "9.9.9/9.9.9/9.9.9"})
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + SQ_PAGES_KEY)
    with urllib.request.urlopen(req, timeout=15) as resp:
        entries = json.loads(resp.read().decode("utf-8"))
    scrolls = {}
    for e in entries:
        third = e["coordinate"].split("/")[2]
        c, s, b = (int(x) for x in third.split("."))
        if e["scroll"]:
            scrolls[(c, s, b)] = e["scroll"]
    if not scrolls:
        raise SystemExit(f"FATAL: phext {phext_name} returned no scrolls")
    return scrolls

def esc(t):
    return html.escape(t or "", quote=True)

def md_inline(text):
    """Strip the markdown markers that read as noise in prose."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = text.replace("`", "")
    return text

def block(text):
    """Render one scroll: code/table-ish blocks as <pre>, bullet lists
    as <ul>, prose as <p>."""
    lines = text.split("\n")
    nonblank = [l for l in lines if l.strip()]
    if not nonblank:
        return ""
    pipe_lines = sum(1 for l in nonblank if l.count("|") >= 2)
    if len(nonblank) > 1 and (pipe_lines >= max(1, len(nonblank) // 2) or "```" in text):
        cleaned = text.replace("```", "").strip()
        return f'<pre class="record">{esc(cleaned)}</pre>'
    bullets = [l for l in nonblank if l.lstrip().startswith("- ")]
    if len(nonblank) > 1 and len(bullets) >= len(nonblank) - 1:
        items = "".join(f"<li>{esc(md_inline(l.lstrip()[2:].strip()))}</li>" for l in bullets)
        return f'<ul class="sentlist">{items}</ul>'
    joined = md_inline(" ".join(l.strip() for l in nonblank))
    return f"<p>{esc(joined)}</p>"

def chapter_sections(scrolls, chapter, skip_first_heading=False):
    """Return list of (heading, [scroll texts]) for sections in a chapter."""
    sections = []
    secs = sorted({s for (c, s, b) in scrolls if c == chapter})
    for s in secs:
        keys = sorted(b for (cc, ss, b) in scrolls if cc == chapter and ss == s)
        if not keys:
            continue
        heading = scrolls.get((chapter, s, keys[0]), "")
        body = [scrolls[(chapter, s, b)] for b in keys[1:]] if len(keys) > 1 else []
        if s == 1 and len(keys) >= 1 and not body and len(secs) == 1:
            body = []
        sections.append((heading, body, keys[0]))
    return sections

def render_chapter(scrolls, chapter, slug=None, plain_heading_h2=True):
    """Render a standard chapter: section 1 is heading + paragraphs;
    later sections get their own sub-headings."""
    out = []
    secs = sorted({s for (c, s, b) in scrolls if c == chapter})
    if not secs:
        return ""
    heading = scrolls.get((chapter, 1, 1), "")
    paras = [scrolls[(chapter, 1, b)] for b in sorted(b for (c, s, b) in scrolls if c == chapter and s == 1) if b > 1]
    kind = "normal"
    h = heading.lower()
    if "good to know" in h:
        kind = "goodtoknow"
    elif "ask about a pilot" in h:
        kind = "cta"
    elif "links on this page" in h:
        kind = "links"
    inner = f"<h2>{esc(heading)}</h2>" + "".join(block(p) for p in paras)
    for s in secs:
        if s == 1:
            continue
        sub_head = scrolls.get((chapter, s, 1), "")
        sub_paras = [scrolls[(chapter, s, b)] for b in sorted(b for (c, ss, b) in scrolls if c == chapter and ss == s) if b > 1]
        if sub_head:
            inner += f"<h3>{esc(sub_head)}</h3>"
        inner += "".join(block(p) for p in sub_paras)
    if kind == "goodtoknow":
        return f'<div class="goodtoknow">{inner}</div>'
    if kind == "cta":
        return (f'<div class="cta-box">{inner}'
                f'<p><a class="btn" href="/ask.html">Ask about a pilot</a> '
                f'<a href="/status.html">Check a submission</a></p></div>')
    if kind == "links":
        return (f'<details class="tech"><summary>Links and sources for this page</summary>'
                f'{scrub_offsite(inner)}</details>')
    extra = ""
    if slug and "what the law says" in h:
        extra = (f'<p><a class="btn secondary" href="/statutes/{slug}.html">'
                 f'How {esc(APP_NAMES[slug])} matches Nebraska law — read the full sheet</a></p>')
    return f"<section>{inner}{extra}</section>"

def scrub_offsite(text):
    """Chapter 9 holds pre-rewrite page text as provenance, and that old
    text names off-site addresses. The served site links — and names —
    nothing off-site (Will's rule), so addresses are scrubbed at render
    time in the technical/provenance details only. The phext keeps the
    original words; main copy never contained them."""
    return re.sub(r"github\.com[^\s<]*", "[off-site address removed]", text)

def tech_details(scrolls):
    keys = sorted((c, s, b) for (c, s, b) in scrolls if c == 9)
    if not keys:
        return ""
    inner = "".join(block(scrub_offsite(scrolls[k])) for k in keys)
    return f'<details class="tech"><summary>For technical staff</summary>{inner}</details>'

# ---------------------------------------------------------------------------
# Shared chrome (from home.phext chapter 7)
# ---------------------------------------------------------------------------

META_CSP = ('<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
            'style-src \'unsafe-inline\'; script-src \'self\'; img-src \'self\' data:; '
            'form-action \'self\'; base-uri \'self\'">')

def chrome(home, title, body, hero=None, extra_head=""):
    nav_labels = home.get((7, 1, 2), "")
    hrefs = {
        "Records Desk": "/exocortexia/records-desk.html",
        "Minutes Publisher": "/exocortexia/minutes-publisher.html",
        "Contract Ledger": "/exocortexia/contract-ledger.html",
        "Data Catalog": "/exocortexia/data-catalog.html",
        "Forms Router": "/exocortexia/forms-router.html",
        "Security": "/exocortexia/security.html",
        "Ask about a pilot": "/ask.html",
    }
    nav = ""
    for label in [x.strip() for x in nav_labels.split("|") if x.strip()]:
        href = hrefs.get(label)
        if not href:
            continue
        cls = ' class="nav-cta"' if label == "Ask about a pilot" else ""
        nav += f'<a href="{href}"{cls}>{esc(label)}</a>'
    nav += '<a href="/status.html">Check a submission</a><a href="/auth/login">Sign in</a>'
    footer1 = esc(home.get((7, 1, 3), ""))
    footer2 = esc(home.get((7, 1, 4), ""))
    hero_html = ""
    if hero:
        hero_html = f'<div class="hero"><h1>{esc(hero[0])}</h1><p class="lede">{esc(hero[1])}</p></div>'
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css = f.read()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{META_CSP}
<title>{esc(title)}</title>
<style>{css}</style>{extra_head}
</head>
<body>
<header class="site"><div class="wrap">
<a class="brand" href="/">Exocortexia <span>by Phext, Inc.</span></a>
<nav class="main">{nav}</nav>
</div></header>
<main class="wrap">
{hero_html}
{body}
</main>
<footer class="site"><div class="wrap">
<p>{footer1}</p>
<p>{footer2}</p>
<p><a href="/how-it-works.html">How this site works</a> · <a href="/exocortexia/verification.html">Read the full test results</a> · <a href="/status.html">Check a submission</a> · <a href="/ask.html">Ask about a pilot</a></p>
</div></footer>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------

def render_app(home, slug):
    sc = sq_query(slug)
    title = sc.get((1, 1, 2), APP_NAMES[slug])
    body = f"<section><h1>{esc(sc.get((1, 1, 3), APP_NAMES[slug]))}</h1>"
    if sc.get((1, 1, 4)):
        body += f'<p class="lede">{esc(sc[(1, 1, 4)])}</p>'
    body += "</section>"
    if sc.get((1, 2, 2)):
        body += f'<div class="summary-lead">{block(sc[(1, 2, 2)])}</div>'
    if sc.get((1, 2, 3)):
        body += '<div class="tryit"><h2>Try it now</h2>'
        body += block(sc[(1, 2, 3)])
        if sc.get((1, 2, 4)):
            body += block(sc[(1, 2, 4)])
        body += (f'<p><a class="btn" href="/apps/{slug}/">Open the live {esc(APP_NAMES[slug])} demo</a></p>'
                 "</div>")
    for ch in range(2, 9):
        body += render_chapter(sc, ch, slug=slug)
    body += tech_details(sc)
    return chrome(home, title, body)

def render_home(home):
    title = home.get((1, 1, 2), "Exocortexia — Phext, Inc.")
    body = ""
    # Chapter 3 first: the five applications, running live — the homepage
    # leads with using the software; the description chapters follow.
    cards = ""
    for i, slug in enumerate(APPS):
        text = home.get((3, 1, 2 + i), "")
        if not text:
            continue
        name, _, rest = text.partition(". ")
        cards += (f'<div class="card"><h3><a href="/exocortexia/{slug}.html">{esc(name)}</a></h3>'
                  f"<p>{esc(rest)}</p>"
                  f'<p><a class="btn" href="/apps/{slug}/">Try the live demo</a></p>'
                  f'<p><a href="/exocortexia/{slug}.html">More about {esc(APP_NAMES[slug])}</a></p></div>')
    body += f'<section><h2>{esc(home.get((3, 1, 1), "The five applications"))}</h2><div class="cards">{cards}</div></section>'
    # Chapter 2: What it is
    body += render_chapter(home, 2)
    # Chapter 4: proof
    body += render_chapter(home, 4)
    body = body.replace("</section>", '<p><a class="btn secondary" href="/exocortexia/verification.html">Read the full test results</a></p></section>', 1) if False else body
    # Chapter 5: security note
    body += render_chapter(home, 5)
    body += '<p><a href="/exocortexia/security.html">Read the security page</a></p>'
    # Chapter 6: ask about a pilot
    body += render_chapter(home, 6)
    body += tech_details(home)
    hero = (home.get((1, 1, 3), ""), home.get((1, 1, 4), ""))
    return chrome(home, title, body, hero=hero)

def render_verification(home):
    sc = sq_query("verification")
    title = sc.get((1, 1, 2), "Test results — Exocortexia | Phext, Inc.")
    body = f"<section><h1>{esc(sc.get((1, 1, 3), 'Read the full test results'))}</h1></section>"
    if sc.get((1, 2, 2)):
        body += f'<div class="summary-lead">{block(sc[(1, 2, 2)])}</div>'
    # rest of chapter 1 (next-step scroll etc.)
    for s in sorted({s for (c, s, b) in sc if c == 1 and s >= 3}):
        head = sc.get((1, s, 1), "")
        paras = [sc[(1, s, b)] for b in sorted(b for (c, ss, b) in sc if c == 1 and ss == s) if b > 1]
        if head:
            body += f"<section><h2>{esc(head)}</h2>" + "".join(block(p) for p in paras) + "</section>"
    body += "<section><h2>The full technical record</h2><p>What follows is the full record, word for word, for technical staff. The plain summary above covers the same ground in plain words.</p></section>"
    for ch in range(2, 11):
        if not any(c == ch for (c, s, b) in sc):
            continue
        heading = sc.get((ch, 1, 1), "")
        body += f"<section><h2>{esc(heading)}</h2>"
        for s in sorted({s for (c, s, b) in sc if c == ch}):
            keys = sorted(b for (c, ss, b) in sc if c == ch and ss == s)
            for b in keys:
                if s == 1 and b == 1:
                    continue
                body += block(sc[(ch, s, b)])
        body += "</section>"
    body += ('<div class="cta-box"><h2>Ask about a pilot</h2>'
             "<p>Tell us which program you want to try. You get a tracking code, and a person from Phext, Inc. replies.</p>"
             '<p><a class="btn" href="/ask.html">Ask about a pilot</a></p></div>')
    return chrome(home, title, body)

def render_security(home):
    sc = sq_query("security")
    title = sc.get((1, 1, 2), "Security — Exocortexia | Phext, Inc.")
    body = f"<section><h1>{esc(sc.get((1, 1, 3), 'Security'))}</h1>"
    if sc.get((1, 1, 4)):
        body += f'<p class="lede">{esc(sc[(1, 1, 4)])}</p>'
    body += "</section>"
    if sc.get((1, 2, 2)):
        body += f'<div class="summary-lead">{block(sc[(1, 2, 2)])}</div>'
    record = []
    for ch in range(2, 13):
        heading = sc.get((ch, 1, 1), "")
        if heading.startswith("FULL TECHNICAL RECORD"):
            record.append(ch)
        elif any(c == ch for (c, s, b) in sc):
            body += render_chapter(sc, ch)
    if record:
        body += ("<section><h2>The full technical record</h2>"
                 "<p>What follows is the full audit record, word for word, for technical staff. "
                 "The plain words above cover the same ground.</p></section>")
        for ch in record:
            heading = sc.get((ch, 1, 1), "")
            body += f"<section><h2>{esc(heading)}</h2>"
            for s in sorted({s for (c, s, b) in sc if c == ch}):
                for b in sorted(b for (c, ss, b) in sc if c == ch and ss == s):
                    if s == 1 and b == 1:
                        continue
                    body += block(sc[(ch, s, b)])
            body += "</section>"
    body += tech_details(sc)
    return chrome(home, title, body)

def render_statute(home, statutes, chapter, slug):
    name = APP_NAMES[slug]
    title = statutes.get((chapter, 1, 1), f"How {name} matches Nebraska law")
    body = f"<section><h1>{esc(title)}</h1>"
    body += f'<p><a href="/exocortexia/{slug}.html">Back to the {esc(name)} page</a></p></section>'
    if statutes.get((chapter, 1, 2)):
        body += f'<div class="summary-lead">{block(statutes[(chapter, 1, 2)])}</div>'
    if statutes.get((chapter, 1, 3)):
        body += f'<div class="panel">{block(statutes[(chapter, 1, 3)])}</div>'
    for s in sorted({s for (c, s, b) in statutes if c == chapter and s >= 2}):
        heading = statutes.get((chapter, s, 1), "")
        paras = [statutes[(chapter, s, b)] for b in sorted(b for (c, ss, b) in statutes if c == chapter and ss == s) if b > 1]
        body += "<section>"
        if heading:
            body += f"<h2>{esc(heading)}</h2>"
        body += "".join(block(p) for p in paras)
        body += "</section>"
    body += ('<div class="cta-box"><h2>Ask about a pilot</h2>'
             "<p>Tell us which program you want to try. You get a tracking code, and a person from Phext, Inc. replies.</p>"
             '<p><a class="btn" href="/ask.html">Ask about a pilot</a></p></div>')
    return chrome(home, f"{title} | Phext, Inc.", body)

ASK_BODY = """
<section><h1>Ask about a pilot</h1>
<div class="summary-lead"><p>Tell us which program your office wants to try. A person at Phext, Inc. reads every form. You get a tracking code when you send it, and we reply by email.</p></div>
<h2>Ask about a pilot for your office</h2>
<form class="plain" method="post" action="/api/intake">
<label for="f-name">Your name</label>
<input type="text" id="f-name" name="name" required maxlength="120">
<label for="f-org">Your office or organization</label>
<input type="text" id="f-org" name="organization" required maxlength="160">
<label for="f-email">Email — so we can reply</label>
<input type="email" id="f-email" name="email" required maxlength="160">
<fieldset><legend>Which program do you want to try?</legend>
<label class="check"><input type="checkbox" name="program" value="records-desk"> Records Desk — public records requests</label>
<label class="check"><input type="checkbox" name="program" value="minutes-publisher"> Minutes Publisher — meeting agendas and minutes</label>
<label class="check"><input type="checkbox" name="program" value="contract-ledger"> Contract Ledger — state contracts</label>
<label class="check"><input type="checkbox" name="program" value="data-catalog"> Data Catalog — public datasets</label>
<label class="check"><input type="checkbox" name="program" value="forms-router"> Forms Router — forms intake and tracking</label>
<label class="check"><input type="checkbox" name="program" value="not-sure"> Not sure yet</label>
</fieldset>
<label for="f-msg">What does your office need?</label>
<textarea id="f-msg" name="message" rows="6" required maxlength="4000"></textarea>
<input type="hidden" name="csrf_token" value="">
<p class="hp"><label>Leave this field empty<input type="text" name="website" tabindex="-1" autocomplete="off"></label></p>
<p><button class="btn" type="submit">Send the form</button></p>
</form>
<div class="note"><p><strong>What happens to your form:</strong> it is stored in your own private record on this site, and a short claim card (your tracking code, the date, and where your form stands) is kept on the site so you can check it. No one else can read your form without your tracking code. Please do not put private records or anyone's personal details in the message — a few plain words about what your office needs is enough.</p></div>
</section>
<section><h2>Sample form: ask an office for public records (demo)</h2>
<p>This second form is a sample. It shows how a records request could work. It does not go to any real office. Do not use it for a real request, and do not put private information in it.</p>
<form class="plain" method="post" action="/api/records-request">
<label for="r-name">Your name</label>
<input type="text" id="r-name" name="name" required maxlength="120">
<label for="r-email">Email — so we can reply</label>
<input type="email" id="r-email" name="email" required maxlength="160">
<label for="r-agency">Which office holds the records?</label>
<input type="text" id="r-agency" name="agency" required maxlength="160">
<label for="r-desc">Which records are you asking for?</label>
<textarea id="r-desc" name="description" rows="5" required maxlength="4000"></textarea>
<input type="hidden" name="csrf_token" value="">
<p class="hp"><label>Leave this field empty<input type="text" name="website" tabindex="-1" autocomplete="off"></label></p>
<p><button class="btn" type="submit">Send the sample request</button></p>
</form>
<p>Both forms give you a tracking code. <a href="/status.html">Check where a form stands</a> with its code — no password needed.</p>
</section>
"""

STATUS_BODY = """
<section><h1>Check where your form stands</h1>
<div class="summary-lead"><p>Type the tracking code you got when you sent your form. It is long — six groups of letters and numbers, starting with WN-. You do not need a password.</p></div>
<form class="plain" method="get" action="/status">
<label for="code">Tracking code</label>
<input type="text" id="code" name="code" required maxlength="40" autocomplete="off">
<p><button class="btn" type="submit">Check</button></p>
</form>
<p>Signed in instead? <a href="/my">See all your forms</a>.</p>
</section>
"""

def render_how_it_works(home):
    body = "<section><h1>How this site works</h1></section>"
    secs = sorted({s for (c, s, b) in home if c == 8})
    for s in secs:
        keys = sorted(b for (c, ss, b) in home if c == 8 and ss == s)
        if not keys:
            continue
        if s == 1:
            paras = [home[(8, 1, b)] for b in keys if b > 1]
            body += "<section>" + "".join(block(p) for p in paras) + "</section>"
        else:
            head = home.get((8, s, 1), "")
            paras = [home[(8, s, b)] for b in keys if b > 1]
            body += "<section>"
            if head:
                body += f"<h2>{esc(head)}</h2>"
            body += "".join(block(p) for p in paras) + "</section>"
    return chrome(home, "How this site works | Phext, Inc.", body)

def write(relpath, content):
    path = os.path.join(OUT_DIR, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"wrote {relpath} ({len(content)} bytes)")

def main():
    if not SQ_PAGES_KEY:
        raise SystemExit("SQ_PAGES_KEY is required")
    if not OUT_DIR:
        raise SystemExit("OUT_DIR is required")
    home = sq_query("home")
    statutes = sq_query("statutes")
    write("index.html", render_home(home))
    for slug in APPS:
        write(f"exocortexia/{slug}.html", render_app(home, slug))
    write("exocortexia/verification.html", render_verification(home))
    write("exocortexia/security.html", render_security(home))
    for i, slug in enumerate(APPS):
        write(f"statutes/{slug}.html", render_statute(home, statutes, 2 + i, slug))
    write("ask.html", chrome(home, "Ask about a pilot | Phext, Inc.", ASK_BODY,
                             extra_head='<script src="/assets/csrf.js" defer></script>'))
    write("status.html", chrome(home, "Check a submission | Phext, Inc.", STATUS_BODY))
    write("how-it-works.html", render_how_it_works(home))
    # shared stylesheet for backend-rendered pages
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css = f.read()
    write("assets/site.css", css)
    csrf_js = os.path.join(os.path.dirname(CSS_PATH), "csrf.js")
    if os.path.exists(csrf_js):
        with open(csrf_js, "r", encoding="utf-8") as f:
            write("assets/csrf.js", f.read())
    print("render complete")

if __name__ == "__main__":
    main()
