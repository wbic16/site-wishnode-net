#!/usr/bin/env python3
"""wishnode.net backend — form workflows, claims register, citizen phexts,
and the edit.phext.io SSO consumer (aud=wishnode).

Tier model (see ARCHITECTURE.md):
  * Page phexts   — hosted by SQ (multi-tenant), PAGES tenant key. Read by
                    the site renderer; this backend never writes them.
  * Claims        — phexts/intake.phext hosted by SQ, INTAKE tenant key.
                    This backend is the only writer. Claims hold pointers +
                    hashes + workflow state, never submission content.
  * Citizen phexts— one file per submitter under <data>/citizen/, managed
                    directly with libphext (write-temp-then-rename, per-file
                    lock). No SQ instance points at this directory, so no SQ
                    key can read or write a citizen phext.

All SQ writes use the `update` (replace) endpoint, never `insert`: phext
coordinates are positional, and insert would renumber neighbouring scrolls
in the same run. Replace at a fresh coordinate pads with empty scrolls and
leaves every existing scroll at its coordinate.

Stdlib only, except libphext (PyPI `phext`) for citizen files.
"""

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --------------------------------------------------------------------------
# Config (environment; secrets come from a 0600 env file on the host,
# never from the repository)
# --------------------------------------------------------------------------

def env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default

PORT = int(env("WISHNODE_PORT", "8940"))
BIND = env("WISHNODE_BIND", "127.0.0.1")
SQ_URL = env("SQ_URL", "http://127.0.0.1:8931").rstrip("/")
SQ_PAGES_KEY = env("SQ_PAGES_KEY", "")
SQ_INTAKE_KEY = env("SQ_INTAKE_KEY", "")
DATA_DIR = env("WISHNODE_DATA_DIR", os.path.expanduser("~/wishnode/data"))
CITIZEN_DIR = os.path.join(DATA_DIR, "citizen")
CSS_PATH = env("WISHNODE_CSS_PATH", os.path.join(os.path.dirname(__file__), "..", "assets", "site.css"))
SSO_SECRET = env("WISHNODE_SSO_SECRET")            # shared with edit.phext.io (PHEXT_SSO_SECRET)
SESSION_SECRET = env("WISHNODE_SESSION_SECRET")    # this site's own session secret
SSO_AUD = env("WISHNODE_SSO_AUD", "wishnode")
EDIT_SSO_LOGIN_URL = env("EDIT_SSO_LOGIN_URL", "https://edit.phext.io/api/auth/sso/wishnode")
ADMIN_TOKEN = env("WISHNODE_ADMIN_TOKEN", "")
CITIZEN_SECRET = env("WISHNODE_CITIZEN_SECRET", "")
PUBLIC_ORIGIN = env("WISHNODE_PUBLIC_ORIGIN", "https://wishnode.net")

SSO_CONFIGURED = bool(SSO_SECRET or SESSION_SECRET)
SSO_VALID = bool(SSO_SECRET and SESSION_SECRET and len(SSO_SECRET) >= 32 and len(SESSION_SECRET) >= 32)
SSO_ENABLED = SSO_VALID
# Fail-closed (audit A-F02): a partial or weak SSO config is a startup
# error, never a silent pass-through. Running with sign-in off is an
# explicit operator choice: WISHNODE_DEMO_MODE=1, and backend pages
# carry a visible demo banner while it lasts. Enforced in main().
DEMO_MODE = env("WISHNODE_DEMO_MODE") == "1"
COOKIE_SECURE = env("WISHNODE_COOKIE_SECURE", "1") != "0"

MAX_BODY = 16384
RATE_LIMIT = 10          # posts per IP per endpoint per window
RATE_WINDOW = 3600       # seconds
SESSION_TTL = 12 * 3600
ASSERTION_MAX_LIFETIME = 120
IAT_FUTURE_SKEW = 30

WORKFLOW = {"received": {"routed"}, "routed": {"in_review"}, "in_review": {"closed"}, "closed": set()}
TRANSITION_ROLE = {"routed": "intake-staff", "in_review": "reviewer", "closed": "reviewer"}
STATE_PLAIN = {
    "received": "Received — we have your form.",
    "routed": "Sent on — your form is with the right person.",
    "in_review": "Being looked at — a person is reading it now.",
    "closed": "Closed — this one is done.",
}
PROGRAMS = {"records-desk", "minutes-publisher", "contract-ledger", "data-catalog", "forms-router", "not-sure"}

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def now_rfc3339():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def coord(ch, sec, base):
    return f"1.1.1/1.1.1/{ch}.{sec}.{base}"

def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("ascii"))

def sign_token(secret: str, claims: dict) -> str:
    payload = b64url_encode(json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return payload + "." + b64url_encode(sig)

def verify_signed_token(secret: str, token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("malformed token")
    payload, sig_text = parts
    expected = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    try:
        given = b64url_decode(sig_text)
    except Exception:
        raise ValueError("malformed signature")
    if not hmac.compare_digest(expected, given):
        raise ValueError("bad signature")
    return json.loads(b64url_decode(payload).decode("utf-8"))

def citizen_id_for(identity: str) -> str:
    mac = hmac.new(CITIZEN_SECRET.encode("utf-8"), identity.encode("utf-8"), hashlib.sha256).hexdigest()
    return "cz-" + mac[:16]

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

def new_tracking_code() -> str:
    # 128-bit CSPRNG codes (audit A-F17): 26 Crockford characters ≈ 130
    # bits, from `secrets` — never sequential, never derived from the
    # submission's contents.
    chars = "".join(secrets.choice(CROCKFORD) for _ in range(26))
    return f"WN-{chars[0:6]}-{chars[6:12]}-{chars[12:18]}-{chars[18:24]}-{chars[24:26]}"

# --------------------------------------------------------------------------
# SQ client (server-side only; keys never leave this process)
# --------------------------------------------------------------------------

def sq_request(key, method, endpoint, params=None, body=None):
    url = SQ_URL + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

def sq_select(key, phext_name, coordinate):
    status, text = sq_request(key, "GET", "/api/v2/select", {"p": phext_name, "c": coordinate})
    if status != 200:
        raise RuntimeError(f"sq select failed: {status} {text[:120]}")
    return text

def sq_update(key, phext_name, coordinate, text):
    status, out = sq_request(key, "POST", "/api/v2/update", {"p": phext_name, "c": coordinate}, body=text)
    if status != 200:
        raise RuntimeError(f"sq update failed: {status} {out[:120]}")
    return out

def sq_query(key, phext_name):
    status, out = sq_request(key, "GET", "/api/v2/query",
                             {"p": phext_name, "from": "1.1.1/1.1.1/1.1.1", "to": "9.9.9/9.9.9/9.9.9"})
    if status != 200:
        raise RuntimeError(f"sq query failed: {status} {out[:120]}")
    return json.loads(out)

# --------------------------------------------------------------------------
# Citizen phexts (libphext, file-per-citizen, temp-write + rename, locked)
# --------------------------------------------------------------------------

from phext.phext import Phext          # noqa: E402
from phext.coordinate import Coordinate  # noqa: E402

PX = Phext()

_citizen_locks = {}
_citizen_locks_guard = threading.Lock()

def citizen_lock(citizen_id):
    with _citizen_locks_guard:
        return _citizen_locks.setdefault(citizen_id, threading.Lock())

def citizen_path(citizen_id):
    return os.path.join(CITIZEN_DIR, citizen_id + ".phext")

def citizen_read(citizen_id):
    path = citizen_path(citizen_id)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def citizen_fetch(buffer, coordinate):
    return PX.fetch(buffer, Coordinate.from_string(coordinate)) or ""

CITIZEN_LAYOUT = (
    "SUBMISSION LAYOUT — submission N (N from 1) lives in chapter 1+N. "
    "Within a submission chapter: section 1 = meta (tracking_code, form kind, "
    "submitted_at, content_hash); section 2 = one scroll per form field; "
    "section 3 = state mirror (append-only transition lines)."
)

def create_submission(citizen_id, form_kind, code, fields):
    """Provision the citizen phext if absent, append one submission chapter,
    return (first_field_coordinate, content_hash)."""
    lock = citizen_lock(citizen_id)
    with lock:
        buffer = citizen_read(citizen_id)
        created = not buffer
        if created:
            buffer = PX.replace(buffer, Coordinate.from_string(coord(1, 1, 1)),
                                   "CITIZEN PHEXT — one person's own record on wishnode.net, "
                                   "provisioned by the site backend. Holds only what this "
                                   "person sent through the site's forms.")
            buffer = PX.replace(buffer, Coordinate.from_string(coord(1, 1, 2)),
                                   f"citizen_id: {citizen_id}")
            buffer = PX.replace(buffer, Coordinate.from_string(coord(1, 1, 3)),
                                   f"created_at: {now_rfc3339()}")
            buffer = PX.replace(buffer, Coordinate.from_string(coord(1, 2, 1)), CITIZEN_LAYOUT)
        # next submission chapter: first chapter >= 2 whose meta scroll is empty
        chapter = 2
        while citizen_fetch(buffer, coord(chapter, 1, 1)):
            chapter += 1
        field_texts = []
        for i, (name, value) in enumerate(fields):
            text = f"field: {name} — {value}"
            field_texts.append(text)
            buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 2, i + 1)), text)
        content_hash = "sha256:" + sha256_hex("\n".join(field_texts))
        buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 1, 1)), f"tracking_code: {code}")
        buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 1, 2)), f"form: {form_kind}")
        buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 1, 3)), f"submitted_at: {now_rfc3339()}")
        buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 1, 4)), f"content_hash: {content_hash}")
        buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 3, 1)), "state: received")
        path = citizen_path(citizen_id)
        os.makedirs(CITIZEN_DIR, exist_ok=True)
        tmp = path + f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(buffer)
        os.replace(tmp, path)
        return coord(chapter, 2, 1), content_hash

def citizen_append_transition(citizen_id, chapter, line):
    lock = citizen_lock(citizen_id)
    with lock:
        buffer = citizen_read(citizen_id)
        if not buffer:
            return
        idx = 2
        while citizen_fetch(buffer, coord(chapter, 3, idx)):
            idx += 1
        buffer = PX.replace(buffer, Coordinate.from_string(coord(chapter, 3, idx)), line)
        path = citizen_path(citizen_id)
        tmp = path + f".tmp-{os.getpid()}-{secrets.token_hex(4)}"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(buffer)
        os.replace(tmp, path)

def citizen_submissions(citizen_id):
    """Return a list of dicts describing each submission chapter."""
    buffer = citizen_read(citizen_id)
    out = []
    if not buffer:
        return out
    chapter = 2
    while True:
        meta = citizen_fetch(buffer, coord(chapter, 1, 1))
        if not meta:
            break
        fields = []
        i = 1
        while True:
            t = citizen_fetch(buffer, coord(chapter, 2, i))
            if not t:
                break
            fields.append(t)
            i += 1
        states = []
        j = 1
        while True:
            t = citizen_fetch(buffer, coord(chapter, 3, j))
            if not t:
                break
            states.append(t)
            j += 1
        out.append({
            "chapter": chapter,
            "tracking_code": meta.split(":", 1)[1].strip() if ":" in meta else "",
            "form": citizen_fetch(buffer, coord(chapter, 1, 2)),
            "submitted_at": citizen_fetch(buffer, coord(chapter, 1, 3)),
            "fields": fields,
            "states": states,
        })
        chapter += 1
    return out

# --------------------------------------------------------------------------
# Claims register (intake phext via SQ, INTAKE tenant key)
# --------------------------------------------------------------------------

def claim_base_for(code):
    code = code.strip().upper()
    h = sha256_hex("wishnode-claim:" + code)
    ch = 2 + (int(h[0:5], 16) % 800)
    sec = 1 + (int(h[5:10], 16) % 900)
    base = 1 + (int(h[10:15], 16) % 880)
    return ch, sec, base

def find_claim(code):
    """Locate a claim by tracking code, applying the documented +20 probe
    walk. Returns (ch, sec, base) or None."""
    code = code.strip().upper()
    ch, sec, base = claim_base_for(code)
    for _ in range(50):
        header = sq_select(SQ_INTAKE_KEY, "intake", coord(ch, sec, base))
        if not header:
            return None
        if header.strip() == f"claim: {code}":
            return ch, sec, base
        base += 20
        if base > 999:
            return None
    return None

def read_claim_at(ch, sec, base):
    claim = {}
    labels = ["header", "citizen_id", "citizen_pointer", "content_hash", "created_at", "state"]
    for off, label in enumerate(labels):
        claim[label] = sq_select(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + off))
    transitions = []
    idx = base + 10
    while True:
        t = sq_select(SQ_INTAKE_KEY, "intake", coord(ch, sec, idx))
        if not t:
            break
        transitions.append(t)
        idx += 1
    claim["transitions"] = transitions
    state = claim["state"].split(":", 1)[1].strip() if ":" in claim["state"] else "received"
    for t in transitions:
        m = re.match(r"transition:\s*(\S+)\s*->\s*(\S+)", t)
        if m:
            state = m.group(2)
    claim["current_state"] = state
    return claim

def create_claim(code, citizen_id, pointer, content_hash):
    ch, sec, base = claim_base_for(code)
    # probe walk: first slot whose header is empty
    for _ in range(50):
        header = sq_select(SQ_INTAKE_KEY, "intake", coord(ch, sec, base))
        if not header:
            break
        if header.strip() == f"claim: {code}":
            raise RuntimeError("duplicate tracking code")
        base += 20
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + 0), f"claim: {code}")
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + 1), f"citizen_id: {citizen_id}")
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + 2), f"citizen_pointer: citizen/{citizen_id}.phext @ {pointer}")
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + 3), f"content_hash: {content_hash}")
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + 4), f"created_at: {now_rfc3339()}")
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, base + 5), "state: received")
    bump_register_root()
    return ch, sec, base

def bump_register_root():
    root_coord = coord(1, 1, 2)
    text = sq_select(SQ_INTAKE_KEY, "intake", root_coord)
    m = re.search(r"claims_written:\s*(\d+)", text)
    n = int(m.group(1)) + 1 if m else 1
    if m:
        text = text[:m.start()] + f"claims_written: {n}" + text[m.end():]
    else:
        text = text.rstrip() + f"\nclaims_written: {n}"
    text = text.replace("state: EMPTY", "state: ACTIVE")
    sq_update(SQ_INTAKE_KEY, "intake", root_coord, text)

def append_transition(code, to_state, role, note):
    loc = find_claim(code)
    if not loc:
        return None, "no such tracking code"
    ch, sec, base = loc
    claim = read_claim_at(ch, sec, base)
    current = claim["current_state"]
    if to_state not in WORKFLOW.get(current, set()):
        return None, f"illegal transition {current} -> {to_state}"
    if TRANSITION_ROLE.get(to_state) != role:
        return None, f"role {role} may not make the {to_state} move (needs {TRANSITION_ROLE.get(to_state)})"
    line = (f"transition: {current} -> {to_state} | actor_role: {role} | "
            f"at: {now_rfc3339()} | note: {note or '—'}")
    idx = base + 10 + len(claim["transitions"])
    sq_update(SQ_INTAKE_KEY, "intake", coord(ch, sec, idx), line)
    # mirror into the citizen phext (same line), chapter from the pointer
    m = re.search(r"@ 1\.1\.1/1\.1\.1/(\d+)\.2\.1", claim["citizen_pointer"])
    cid = claim["citizen_id"].split(":", 1)[1].strip() if ":" in claim["citizen_id"] else ""
    if m and cid:
        citizen_append_transition(cid, int(m.group(1)), line)
    return {"from": current, "to": to_state, "line": line}, None

# --------------------------------------------------------------------------
# SSO consumer (mirrors the Exocortexia exo-sso verification contract)
# --------------------------------------------------------------------------

_seen_jti = {}
_seen_jti_lock = threading.Lock()

def verify_assertion(token):
    """Verify an edit.phext.io assertion exactly as exo-sso does:
    signature (constant-time), aud, exp, iat required with a 120-second
    maximum lifetime, 30-second future-iat skew, expiry at most 150
    seconds out, and a jti replay cache. Returns claims or raises."""
    claims = verify_signed_token(SSO_SECRET, token)
    now = int(time.time())
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise ValueError("missing sub claim")
    if claims.get("aud") != SSO_AUD:
        raise ValueError("wrong audience")
    exp = claims.get("exp")
    if not isinstance(exp, int):
        raise ValueError("missing exp claim")
    if now >= exp:
        raise ValueError("expired assertion")
    iat = claims.get("iat")
    if not isinstance(iat, int):
        raise ValueError("missing iat claim")
    if exp - iat > ASSERTION_MAX_LIFETIME:
        raise ValueError("assertion lifetime too long")
    if iat > now + IAT_FUTURE_SKEW:
        raise ValueError("assertion issued in the future")
    if exp - now > ASSERTION_MAX_LIFETIME + IAT_FUTURE_SKEW:
        raise ValueError("assertion expiry too far in the future")
    jti = claims.get("jti")
    if not jti or not isinstance(jti, str):
        raise ValueError("missing jti claim")
    with _seen_jti_lock:
        for k in [k for k, e in _seen_jti.items() if e <= now]:
            del _seen_jti[k]
        if jti in _seen_jti:
            raise ValueError("replay: jti already used")
        _seen_jti[jti] = exp
    return claims

def seal_session(sub, handle):
    return sign_token(SESSION_SECRET, {
        "sub": sub, "handle": handle, "aud": SSO_AUD,
        "exp": int(time.time()) + SESSION_TTL,
    })

def open_session(value):
    if not SSO_ENABLED or not value:
        return None
    try:
        claims = verify_signed_token(SESSION_SECRET, value)
    except Exception:
        return None
    if claims.get("aud") != SSO_AUD:
        return None
    exp = claims.get("exp")
    if not isinstance(exp, int) or int(time.time()) >= exp:
        return None
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        return None
    return {"sub": sub, "handle": claims.get("handle", ""), "exp": exp}

# --------------------------------------------------------------------------
# Rate limiting (in-memory, per IP + endpoint)
# --------------------------------------------------------------------------

_rate = {}
_rate_lock = threading.Lock()

def rate_ok(ip, endpoint):
    key = (ip, endpoint)
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate.get(key, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            _rate[key] = hits
            return False
        hits.append(now)
        _rate[key] = hits
        return True

# --------------------------------------------------------------------------
# HTML shell for backend-rendered pages (status, account, messages)
# --------------------------------------------------------------------------

def page_shell(title, body, session=None):
    who = ""
    if session:
        who = (f'<span class="who">Signed in as {html.escape(session.get("handle") or session["sub"])} · '
               f'<a href="/auth/logout">Sign out</a></span>')
    banner = ""
    if not SSO_ENABLED:
        banner = ('<div class="note" role="note"><p><strong>Demo mode:</strong> '
                  'sign-in is not turned on for this site yet. Forms work, and '
                  'tracking codes are the way to check them.</p></div>')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="/assets/site.css">
</head>
<body>
<header class="site"><div class="wrap">
<a class="brand" href="/">Exocortexia <span>by Phext, Inc.</span></a>
<nav class="main">
<a href="/">Home</a><a href="/exocortexia/records-desk.html">Records Desk</a><a href="/exocortexia/minutes-publisher.html">Minutes Publisher</a><a href="/exocortexia/contract-ledger.html">Contract Ledger</a><a href="/exocortexia/data-catalog.html">Data Catalog</a><a href="/exocortexia/forms-router.html">Forms Router</a><a href="/exocortexia/security.html">Security</a><a href="/status.html">Check a submission</a><a href="/ask.html" class="nav-cta">Ask about a pilot</a>{who}
</nav>
</div></header>
<main class="wrap">
{banner}
{body}
</main>
<footer class="site"><div class="wrap">
<p>Phext, Inc. makes open software for public offices. This site is the home of our Exocortexia suite. To reach us, use the “Ask about a pilot” form on this site.</p>
<p><a href="/how-it-works.html">How this site works</a> · <a href="/status.html">Check a submission</a> · <a href="/ask.html">Ask about a pilot</a></p>
</div></footer>
</body>
</html>"""

def esc(text):
    return html.escape(text or "", quote=True)

def plain_state(state):
    return STATE_PLAIN.get(state, state)

# --------------------------------------------------------------------------
# Form handling
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def clean(value, maxlen, multiline=False):
    value = (value or "").strip()
    value = "".join(c for c in value if c.isprintable() or (multiline and c == "\n"))
    return value[:maxlen]

def handle_submission(handler, form_kind, raw):
    """Shared engine for both workflows. raw: dict of form lists.
    Returns (status_code, html_body)."""
    if raw.get("website", [""])[0]:
        # honeypot tripped: pretend success, write nothing
        return 200, page_shell("Thank you", "<section><h1>Thank you</h1>"
                                "<p>Your form was received.</p></section>")
    def one(name):
        return raw.get(name, [""])[0]
    session = current_session(handler)
    if form_kind == "ask-about-a-pilot":
        name = clean(one("name"), 120)
        organization = clean(one("organization"), 160)
        email = clean(one("email"), 160)
        programs = [clean(p, 40) for p in raw.get("program", [])]
        programs = [p for p in programs if p in PROGRAMS] or ["not-sure"]
        message = clean(one("message"), 4000, multiline=True)
        errors = []
        if not name:
            errors.append("Please tell us your name.")
        if not organization:
            errors.append("Please tell us your office or organization.")
        if not EMAIL_RE.match(email):
            errors.append("Please give an email address we can reply to.")
        if not message:
            errors.append("Please tell us, in a few words, what your office needs.")
        fields = [("name", name), ("organization", organization), ("email", email),
                  ("program", ", ".join(programs)), ("message", message)]
    else:  # records-request-demo
        name = clean(one("name"), 120)
        email = clean(one("email"), 160)
        agency = clean(one("agency"), 160)
        description = clean(one("description"), 4000, multiline=True)
        errors = []
        if not name:
            errors.append("Please tell us your name.")
        if not EMAIL_RE.match(email):
            errors.append("Please give an email address we can reply to.")
        if not agency:
            errors.append("Please tell us which office holds the records.")
        if not description:
            errors.append("Please say which records you are asking for.")
        fields = [("name", name), ("email", email), ("agency", agency),
                  ("description", description)]
    if errors:
        items = "".join(f"<li>{esc(e)}</li>" for e in errors)
        return 400, page_shell("Check your form",
                               f"<section><h1>A couple of things to fix</h1><ul>{items}</ul>"
                               f"<p><a href=\"/ask.html\">Back to the form</a></p></section>", session)
    # citizen identity: SSO session wins; otherwise derive from the email
    if session:
        citizen_id = citizen_id_for("sso:" + session["sub"])
    else:
        citizen_id = citizen_id_for("email:" + email.lower())
    code = new_tracking_code()
    first_field, content_hash = create_submission(citizen_id, form_kind, code, fields)
    create_claim(code, citizen_id, first_field, content_hash)
    body = f"""<section><h1>Thank you — your form is in</h1>
<div class="panel">
<p>Your tracking code is:</p>
<p class="trackcode">{esc(code)}</p>
<p>Write it down. With this code you can <a href="/status?code={esc(code)}">check where your form stands</a> at any time. You do not need a password.</p>
<p>What happens next: a person at Phext, Inc. reads your form, sends it to the right person, and replies to the email address you gave. Your form is stored in your own private record on this site. It is not posted in public.</p>
</div></section>"""
    return 200, page_shell("Thank you", body, session)

# --------------------------------------------------------------------------
# CSRF defence (audit A-F11): Origin/Host match on every POST, plus a
# double-submit token for clients that send no Origin. Browsers always
# send Origin on POSTs, so a cross-site form post is rejected on the
# Origin check alone; the token (GET /api/csrf sets a cookie and returns
# the value for the form's hidden field) covers non-browser flows.
# --------------------------------------------------------------------------

def csrf_ok(handler, form=None):
    origin = handler.headers.get("Origin", "")
    host = handler.headers.get("Host", "")
    if origin:
        try:
            authority = urllib.parse.urlparse(origin).netloc
        except Exception:
            return False
        return bool(authority) and authority == host
    field = ""
    if form:
        field = (form.get("csrf_token") or [""])[0]
    cookie_token = ""
    for part in handler.headers.get("Cookie", "").split(";"):
        part = part.strip()
        if part.startswith("wishnode_csrf="):
            cookie_token = part.split("=", 1)[1]
    return bool(field) and bool(cookie_token) and hmac.compare_digest(field, cookie_token)

# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------

def current_session(handler):
    cookie = handler.headers.get("Cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("wishnode_session="):
            return open_session(part.split("=", 1)[1])
    return None

class Handler(BaseHTTPRequestHandler):
    server_version = "wishnode-backend/1.0"

    def setup(self):
        super().setup()
        self.request.settimeout(30)  # per-connection read deadline

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def send_html(self, status, body, extra_headers=None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # Baseline security headers on every response (audit A-F13).
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; form-action 'self'; base-uri 'self'; "
                         "frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location, extra_headers=None):
        self.send_response(302)
        self.send_header("Location", location)
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- routes ------------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                return self.send_json(200, {"ok": True, "sso_enabled": SSO_ENABLED, "demo_mode": DEMO_MODE and not SSO_ENABLED})
            if path == "/api/csrf":
                return self.csrf_token()
            if path == "/assets/site.css":
                return self.serve_css()
            if path == "/auth/login":
                return self.auth_login()
            if path == "/api/auth/callback":
                return self.auth_callback(qs)
            if path == "/auth/logout":
                return self.redirect("/", {"Set-Cookie": "wishnode_session=; Path=/; Max-Age=0; HttpOnly"})
            if path == "/status":
                return self.status_page(qs)
            if path == "/my":
                return self.my_page()
            if path == "/api/admin/claim":
                return self.admin_claim(qs)
            return self.send_html(404, page_shell("Not found", "<section><h1>Not found</h1><p>That page is not here.</p></section>", current_session(self)))
        except Exception as e:  # keep the error plain; details stay in the log
            print(f"error on GET {path}: {e!r}", flush=True)
            return self.send_html(500, page_shell("Something went wrong",
                                                  "<section><h1>Something went wrong</h1><p>Please try again in a few minutes.</p></section>"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0:
            return self.send_html(400, page_shell("Bad request", "<section><h1>That request was not well formed</h1></section>"))
        if length > MAX_BODY:
            return self.send_html(413, page_shell("Too large", "<section><h1>That form was too large</h1><p>Please shorten it and try again.</p></section>"))
        raw_body = self.rfile.read(length) if length else b""
        try:
            if path in ("/api/intake", "/api/records-request"):
                # Behind the site's nginx the peer is localhost; nginx sets
                # X-Forwarded-For to the real client. The backend binds
                # localhost only, so the header can only arrive via nginx
                # or a local process.
                client_ip = self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]
                if not rate_ok(client_ip, path):
                    return self.send_html(429, page_shell("Slow down",
                                                          "<section><h1>Too many forms</h1><p>Please wait a while before sending another form.</p></section>"))
                form = urllib.parse.parse_qs(raw_body.decode("utf-8", "replace"))
                if not csrf_ok(self, form):
                    return self.send_html(403, page_shell("That form did not come from this site",
                        "<section><h1>That form did not come from this site</h1>"
                        "<p>For safety, we only take forms sent from pages on this site. "
                        "Please use the form on this site.</p>"
                        "<p><a href=\"/ask.html\">Go to the form</a></p></section>", current_session(self)))
                kind = "ask-about-a-pilot" if path == "/api/intake" else "records-request-demo"
                status, body = handle_submission(self, kind, form)
                return self.send_html(status, body)
            if path == "/api/admin/advance":
                origin = self.headers.get("Origin", "")
                if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host", ""):
                    return self.send_json(403, {"error": "origin mismatch"})
                return self.admin_advance(raw_body)
            return self.send_html(404, page_shell("Not found", "<section><h1>Not found</h1></section>", current_session(self)))
        except Exception as e:
            print(f"error on POST {path}: {e!r}", flush=True)
            return self.send_html(500, page_shell("Something went wrong",
                                                  "<section><h1>Something went wrong</h1><p>Please try again in a few minutes.</p></section>"))

    # -- individual handlers -------------------------------------------------
    def csrf_token(self):
        tok = secrets.token_urlsafe(32)
        data = json.dumps({"csrf_token": tok}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        cookie = f"wishnode_csrf={tok}; Path=/; SameSite=Lax; Max-Age=3600"
        if COOKIE_SECURE:
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def serve_css(self):
        try:
            with open(CSS_PATH, "rb") as f:
                data = f.read()
        except OSError:
            return self.send_html(404, "not found")
        self.send_response(200)
        self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def auth_login(self):
        if not SSO_ENABLED:
            return self.send_html(200, page_shell("Sign in",
                "<section><h1>Sign in</h1><div class=\"panel\">"
                "<p>Sign-in is not turned on for this site yet. You do not need it to use the site.</p>"
                "<p>Sent a form already? <a href=\"/status.html\">Check it with your tracking code</a> — no password needed.</p>"
                "</div></section>"))
        return self.redirect(EDIT_SSO_LOGIN_URL)

    def auth_callback(self, qs):
        if not SSO_ENABLED:
            return self.send_html(503, page_shell("Sign in",
                "<section><h1>Sign in is not turned on yet</h1>"
                "<p><a href=\"/status.html\">Check a submission with your tracking code</a> instead.</p></section>"))
        token = (qs.get("assertion") or [""])[0]
        try:
            claims = verify_assertion(token)
        except Exception as e:
            print(f"assertion rejected: {e}", flush=True)
            return self.send_html(401, page_shell("Sign-in did not work",
                "<section><h1>Sign-in did not work</h1>"
                "<p>The sign-in link was old, already used, or not for this site. Please try signing in again.</p>"
                "<p><a href=\"/auth/login\">Try again</a> · <a href=\"/status.html\">Check a submission with your tracking code</a></p></section>"))
        sub = claims["sub"]
        handle = claims.get("handle", "")
        # provision the citizen phext on first sign-in
        citizen_id = citizen_id_for("sso:" + sub)
        if not os.path.exists(citizen_path(citizen_id)):
            with citizen_lock(citizen_id):
                if not citizen_read(citizen_id):
                    buf = PX.replace("", Coordinate.from_string(coord(1, 1, 1)),
                                        "CITIZEN PHEXT — one person's own record on wishnode.net, "
                                        "provisioned at first sign-in.")
                    buf = PX.replace(buf, Coordinate.from_string(coord(1, 1, 2)), f"citizen_id: {citizen_id}")
                    buf = PX.replace(buf, Coordinate.from_string(coord(1, 1, 3)), f"created_at: {now_rfc3339()}")
                    buf = PX.replace(buf, Coordinate.from_string(coord(1, 2, 1)), CITIZEN_LAYOUT)
                    os.makedirs(CITIZEN_DIR, exist_ok=True)
                    path = citizen_path(citizen_id)
                    tmp = path + f".tmp-{os.getpid()}"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(buf)
                    os.replace(tmp, path)
        cookie = seal_session(sub, handle)
        ret = claims.get("ret") or "/my"
        if not isinstance(ret, str) or not ret.startswith("/") or ret.startswith("//"):
            ret = "/my"
        return self.redirect(ret, {"Set-Cookie":
            f"wishnode_session={cookie}; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age={SESSION_TTL}"})

    def status_page(self, qs):
        code = (qs.get("code") or [""])[0].strip().upper()
        session = current_session(self)
        if not code:
            return self.send_html(400, page_shell("Check a submission",
                "<section><h1>Check a submission</h1><p>Please type the tracking code from your form.</p>"
                "<p><a href=\"/status.html\">Back to the code form</a></p></section>", session))
        loc = find_claim(code)
        if not loc:
            return self.send_html(404, page_shell("Code not found",
                f"<section><h1>We could not find that code</h1>"
                f"<p>We have no form with the code <strong>{esc(code)}</strong>. Check the code and try again. "
                f"Codes are long — six groups of letters and numbers, starting with WN-.</p></section>", session))
        claim = read_claim_at(*loc)
        state = claim["current_state"]
        rows = ""
        created = claim["created_at"].split(":", 1)[1].strip() if ":" in claim["created_at"] else ""
        rows += f"<tr><td>{esc(created)}</td><td>Form received</td></tr>"
        for t in claim["transitions"]:
            m = re.match(r"transition:\s*(\S+)\s*->\s*(\S+)\s*\|\s*actor_role:\s*(\S+)\s*\|\s*at:\s*(\S+)\s*\|\s*note:\s*(.*)", t)
            if m:
                rows += (f"<tr><td>{esc(m.group(4))}</td><td>Now: {esc(STATE_PLAIN.get(m.group(2), m.group(2)))}"
                         f"<br><span class=\"small\">Note: {esc(m.group(5))}</span></td></tr>")
        # submission summary from the citizen phext (the citizen's own record)
        summary = ""
        cid = claim["citizen_id"].split(":", 1)[1].strip() if ":" in claim["citizen_id"] else ""
        m = re.search(r"@ 1\.1\.1/1\.1\.1/(\d+)\.2\.1", claim["citizen_pointer"])
        if cid and m:
            chapter = int(m.group(1))
            for sub in citizen_submissions(cid):
                if sub["chapter"] == chapter:
                    items = "".join(f"<li>{esc(f)}</li>" for f in sub["fields"])
                    summary = f"<h2>What you sent</h2><ul class=\"sentlist\">{items}</ul>"
                    break
        body = f"""<section><h1>Where your form stands</h1>
<div class="panel">
<p>Tracking code: <strong>{esc(code)}</strong></p>
<p class="bigstate">{esc(plain_state(state))}</p>
<table class="timeline"><tr><th>When</th><th>What happened</th></tr>{rows}</table>
{summary}
<p class="small">This page reads the claim card for your form. Your form itself stays in your own private record on this site.</p>
</div></section>"""
        return self.send_html(200, page_shell("Where your form stands", body, session))

    def my_page(self):
        session = current_session(self)
        if not session:
            return self.send_html(200, page_shell("Your forms",
                "<section><h1>Your forms</h1><div class=\"panel\">"
                "<p>Two ways to see your forms:</p>"
                "<p><a class=\"btn\" href=\"/auth/login\">Sign in</a> <a class=\"btn secondary\" href=\"/status.html\">Use a tracking code</a></p>"
                "<p class=\"small\">A tracking code needs no password. Sign-in shows every form tied to your account.</p>"
                "</div></section>"))
        citizen_id = citizen_id_for("sso:" + session["sub"])
        subs = citizen_submissions(citizen_id)
        if not subs:
            listing = "<p>You have not sent a form yet. <a href=\"/ask.html\">Ask about a pilot</a>.</p>"
        else:
            items = ""
            for s in subs:
                state = "received"
                for line in s["states"]:
                    mm = re.match(r"transition:\s*(\S+)\s*->\s*(\S+)", line)
                    if mm:
                        state = mm.group(2)
                code = s["tracking_code"]  # citizen_submissions returns the bare code
                items += (f"<li><strong>{esc(code)}</strong> — "
                          f"{esc(plain_state(state))} "
                          f"<a href=\"/status?code={esc(code)}\">See the full record</a></li>")
            listing = f"<ul class=\"sentlist\">{items}</ul>"
        return self.send_html(200, page_shell("Your forms",
            f"<section><h1>Your forms</h1><div class=\"panel\">{listing}</div></section>", session))

    def admin_claim(self, qs):
        token = self.headers.get("X-Admin-Token", "")
        if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
            return self.send_json(401, {"error": "unauthorized"})
        code = (qs.get("code") or [""])[0].strip().upper()
        loc = find_claim(code)
        if not loc:
            return self.send_json(404, {"error": "no such tracking code"})
        claim = read_claim_at(*loc)
        return self.send_json(200, {"code": code, "at": list(loc), "claim": claim})

    def admin_advance(self, raw_body):
        token = self.headers.get("X-Admin-Token", "")
        if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
            return self.send_json(401, {"error": "unauthorized"})
        try:
            req = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return self.send_json(400, {"error": "body must be JSON"})
        code = str(req.get("code", "")).strip().upper()
        to_state = str(req.get("to", "")).strip()
        role = str(req.get("role", "")).strip()
        note = clean(str(req.get("note", "")), 300)
        if not code or to_state not in TRANSITION_ROLE:
            return self.send_json(400, {"error": "need code and a target state of routed, in_review, or closed"})
        result, error = append_transition(code, to_state, role, note)
        if error:
            return self.send_json(409, {"error": error})
        return self.send_json(200, {"ok": True, "code": code, **result})

def main():
    # Fail-closed, mirroring exo-sso (audit A-F02): a partial or weak SSO
    # configuration is a startup error, and running with sign-in off
    # requires the explicit WISHNODE_DEMO_MODE=1 opt-in.
    if SSO_CONFIGURED and not SSO_VALID:
        raise SystemExit(
            "partial or weak SSO configuration: WISHNODE_SSO_SECRET and "
            "WISHNODE_SESSION_SECRET must both be set and at least 32 chars. "
            "Refusing to start with the gate silently disabled.")
    if not SSO_ENABLED and not DEMO_MODE:
        raise SystemExit(
            "SSO is not configured (WISHNODE_SSO_SECRET / WISHNODE_SESSION_SECRET "
            "unset) and WISHNODE_DEMO_MODE=1 was not given: refusing to start. "
            "Set the SSO variables, or set WISHNODE_DEMO_MODE=1 for an "
            "explicitly open demo.")
    if not CITIZEN_SECRET or len(CITIZEN_SECRET) < 32:
        raise SystemExit("WISHNODE_CITIZEN_SECRET must be set (>= 32 chars)")
    if not ADMIN_TOKEN or len(ADMIN_TOKEN) < 32:
        raise SystemExit("WISHNODE_ADMIN_TOKEN must be set (>= 32 chars)")
    if not SQ_PAGES_KEY or not SQ_INTAKE_KEY:
        raise SystemExit("SQ_PAGES_KEY and SQ_INTAKE_KEY must be set")
    os.makedirs(CITIZEN_DIR, exist_ok=True)
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"wishnode-backend listening on {BIND}:{PORT} "
          f"(sso_enabled={SSO_ENABLED}, demo_mode={DEMO_MODE and not SSO_ENABLED})", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
