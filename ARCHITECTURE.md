# wishnode.net — architecture

Task 34.6.6/7.7.10/7.6.10 · This document describes what is built and
running, what is staged, and the one step that needs root.

## The model (Will, 2026-11-07)

> Each citizen gets their own phext, and then we have higher level ones
> for the various pages — secured by roles and claims.

Three tiers:

| Tier | What it is | Where it lives | Who holds the key |
|---|---|---|---|
| **Page phexts** | Published content: one phext per page/section (`phexts/*.phext` in this repo) | Hosted by SQ on the site host, `pages` tenant | Backend + renderer only (server-side) |
| **Claims register** | `intake.phext`: one claim card per form submission — tracking code, opaque citizen id, pointer to the citizen phext, SHA-256 content hash, timestamps, workflow state. **Never the submission itself.** | Hosted by SQ, `intake` tenant (separate key, separate data dir) | Backend only |
| **Citizen phexts** | One phext file per submitter, provisioned at first submission or first sign-in. Holds that person's submissions as per-field scrolls. | Plain files under `~/wishnode/data/citizen/` on the host. **No SQ instance points at this directory.** | The backend process only (filesystem) |

Because citizen phexts are not behind SQ at all, a page-tier or
intake-tier SQ key *physically cannot* read or write a citizen phext,
and the citizen code path in the backend never writes page phexts.

**Claims flow.** A form submission is written to the submitter's citizen
phext (per-field scrolls, citizen template layout). A claim card is then
registered in `intake.phext` at a coordinate derived from the tracking
code (SHA-256 derivation + a documented +20 probe walk — see
`docs/COORDINATE-MAP.md`). State changes are **appended** as transition
scrolls (`from -> to | actor_role | timestamp | note`); the creation
scrolls are never overwritten, and current state is read from the latest
transition. The public status page reads the claim card, and shows the
submission summary from the citizen phext the card points to.

**Write primitive.** All SQ writes use `POST /api/v2/update` (replace),
never `insert`. Phext coordinates are positional: inserting at an
occupied coordinate renumbers its neighbours in the same run, which
would corrupt hash-derived claim addressing. Replace at a fresh
coordinate pads with empty scrolls and moves nothing. Citizen files are
written temp-file-then-rename under a per-citizen lock.

## Roles

| Role | Can read | Can write |
|---|---|---|
| **public** | Rendered pages (static HTML built from the page phexts) | Nothing |
| **citizen** | Own claim state + own submission, by tracking code; own phext's submissions when signed in | Own submissions (the two forms) |
| **staff** (`intake-staff`, `reviewer`) | Any claim card, via the token-gated admin API | Append transitions: `intake-staff` makes `received -> routed`; `reviewer` makes `routed -> in_review` and `in_review -> closed`. No other moves exist. |
| **admin** (site owner) | Everything | Page phext content (edit in this repo, redeploy), service config |

The workflow is the Forms Router state machine:
`received → routed → in_review → closed` — three legal moves, enforced
by the backend; an illegal move writes nothing.

## Sign-in (SSO)

The backend is an SSO consumer for edit.phext.io, built exactly like
the Exocortexia `exo-sso` crate (task 13.6.8/7.6.9/6.6.9):

- `GET /auth/login` → redirect to `https://edit.phext.io/api/auth/sso/wishnode`
- The lattice handler appends its fixed callback path, so assertions
  land at **`GET /api/auth/callback?assertion=…`** on this origin
  (Will sets `PHEXT_SSO_WISHNODE_URL` to the backend origin).
- Verification mirrors exo-sso: `b64url(claims) "." b64url(HMAC-SHA256)`
  checked in constant time; `aud=wishnode`; `exp`/`iat` required with a
  120-second maximum lifetime and 30-second future skew; `jti` replay
  cache. The session is the backend's own cookie (`wishnode_session`,
  host-only, HttpOnly, SameSite=Lax, Secure, 12 h), sealed with a
  separate session secret.
- A signed-in identity maps to a citizen phext (provisioned on first
  sign-in). Citizen id = `cz-` + first 16 hex of
  `HMAC-SHA256(citizen_secret, "sso:"+sub)`; form submitters get the
  same shape from `"email:"+email`. The raw email/sub is never a
  filename or an exposed id.
- The consumer is **verified against the Exocortexia mock minter**
  (`edit-minter`, mock feature). Production sign-in completes only
  after Will merges the lattice branch, sets `PHEXT_SSO_WISHNODE_URL`,
  restarts phext-edit, **and** provisions the shared secret into the
  backend env (`WISHNODE_SSO_SECRET`). Until then the backend runs in
  the explicit demo mode described under A-F02 above
  (`WISHNODE_DEMO_MODE=1` is set in the deployed env; remove it when
  the secret lands) and the site says so plainly; tracking codes are
  unaffected.

## Serving

- **Pages are rendered at deploy time** by `scripts/render_site.py`,
  which reads every scroll through the SQ API (pages tenant) and writes
  self-contained static HTML into the docroot. The phexts are the
  source of truth; the HTML is a build artifact. (Request-time
  rendering was the alternative; deploy-time was chosen because the
  docroot is the one surface wbic16 fully controls — see the blocker
  below — and static pages cannot fail when a service is down.)
- **SQ** runs as one `sq host` process in multi-tenant config mode
  (`~/wishnode/sq-tenants.json`, mode 0600): token = tier, `p=` = phext
  file in that tier's data dir. Keys live only in that file and in the
  backend env file (0600). SQ is **never proxied to the public**: its
  single key authorizes reads *and* writes, and insert/update/delete
  even work over GET, so any public SQ path would be a write path.
- **Backend** (`backend/wishnode_backend.py`, Python stdlib + libphext
  for citizen files) listens on `127.0.0.1:8940`. Routes: `/api/intake`,
  `/api/records-request` (the two forms), `/status` (claim lookup),
  `/my`, `/auth/login`, `/api/auth/callback`, `/auth/logout`,
  `/api/admin/claim`, `/api/admin/advance`, `/api/health`.
- **Demo applications** (task 27.6.8/8.6.11/5.6.8): the five real
  Exocortexia programs (wbic16/Exocortexia @ 342a268, the
  post-security-pass build, binaries unmodified) run on this host as
  systemd user units `exo-<app>.service`, bound to 127.0.0.1 only:

  | Public path (once the include lands) | App | Port | Demo corpus |
  |---|---|---|---|
  | `/apps/records-desk/` | records-desk | 8801 | 400 synthetic documents |
  | `/apps/minutes-publisher/` | minutes-publisher | 8802 | 12 boards × 6 meetings |
  | `/apps/contract-ledger/` | contract-ledger | 8803 | 60 contracts, 29 amendments |
  | `/apps/data-catalog/` | data-catalog | 8804 | 8 datasets |
  | `/apps/forms-router/` | forms-router | 8805 | public-records-request form |

  Each unit sets `EXO_DEMO_MODE=1` (the apps' explicit open demo mode:
  a visible "AUTH DISABLED — local demo mode" banner, synthetic data
  only) and `EXO_STATE_DIR=~/exocortexia/state/<app>/`, so redactions,
  submissions, and audit chains persist across restarts (verified:
  a forms-router submission stayed `closed` with full history after a
  unit restart). `EXO_AUDIT_KEY` lives in `~/exocortexia/exo.env`
  (mode 0600, generated on the host, never in this repo). Binaries
  live in `~/exocortexia/bin/` — build artifacts stay out of this
  repo; `scripts/install_exo_apps.sh` (run on aletheia-core) rebuilds,
  ships, hash-verifies, and smoke-checks them.

  The apps emit root-absolute links and know nothing of the subpath.
  The nginx snippet maps them honestly instead of patching the audited
  binaries: `proxy_pass …/` strips the `/apps/<app>/` prefix inbound,
  `proxy_redirect` maps redirects back, and `sub_filter` (the host's
  nginx is built `--with-http_sub_module`) rewrites the two
  absolute-URL attribute forms (`href="/…`, `action="/…`) outbound.
  Source inspection confirmed the complete set: the apps build no URLs
  in JavaScript and use no external assets, and `sub_filter` applies
  to text/html only, so JSON API responses pass through byte-exact.
  Documented limit: if a future app version builds URLs in script or
  emits another absolute-reference form, this mapping must be
  revisited before that version is deployed.
- **Supervision:** systemd *user* units (`deploy/systemd/`), enabled
  with linger, so the services survive logout and reboot:
  `wishnode-sq.service`, `wishnode-backend.service`, and the five
  `exo-<app>.service` units above.

## The one root step (blocker, precisely scoped)

wishnode.net's nginx vhost (`/etc/nginx/sites-available/wishnode.net`)
is root-owned, has no wbic16-writable include, and wbic16 has no
passwordless sudo — so the dynamic routes above are reachable on the
host's localhost today, but not yet through `https://wishnode.net`.
Everything else is live. The fix is one line, once, by root, inside the
443 server block:

```nginx
include /sites/web/wishnode.net/nginx/wishnode-dynamic.conf;
```

The included file (this repo: `deploy/nginx/wishnode-dynamic.conf`,
deployed to that path) proxies `/api/`, `/auth/`, `/status`, and
`/my` to `127.0.0.1:8940` with `proxy_http_version 1.1` and a 32k body
cap, and the five demo applications under `/apps/<app>/` to
127.0.0.1:8801–8805 (see "Demo applications" above). It does not proxy
SQ. After the include + `nginx -t` + reload, the forms, status page,
sign-in, admin API, and all five live demos are public with no further
changes here. Until then the vhost's static fallback serves the
homepage for those paths (HTTP 200 HTML), which is why "reachable"
claims in this document are always stated as host-side or public
separately.

## How staff advance a submission

On the host (via aletheia-core: `ssh wbic16@44.248.235.76`):

```sh
TOKEN=$(grep ^WISHNODE_ADMIN_TOKEN ~/wishnode/backend.env | cut -d= -f2)
# read a claim card
curl -s -H "X-Admin-Token: $TOKEN" "http://127.0.0.1:8940/api/admin/claim?code=WN-XXXXX-XXXXX"
# advance it (roles: intake-staff -> routed; reviewer -> in_review, closed)
curl -s -X POST -H "X-Admin-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"code":"WN-XXXXX-XXXXX","to":"routed","role":"intake-staff","note":"sent to the clerk team"}' \
  http://127.0.0.1:8940/api/admin/advance
```

Once the nginx include lands, the same calls work against
`https://wishnode.net` from anywhere the token is available.

## Form field sets (reconciliation note)

The intake brief specifies Workflow A's fields (name, organization,
email, program(s), message); the citizen template's layout (chapter per
submission, §1 meta, §2 one scroll per field, §3 state mirror) is
followed exactly, with field scrolls named for the actual fields. The
claims register stays free of personal data per the intake scheme: it
holds the opaque citizen id, pointer, and hash only. Workflow B
(records-request demo) uses name, email, agency, description, and is
labeled a demo everywhere it appears.

## Safety basics

Server-side validation and length caps on every field; output escaping
on every page that renders submitted text (status and account pages are
not stored-XSS vectors); 16 KB body cap enforced before the body is
read; per-IP rate limit on the form endpoints; a honeypot field; no
email is sent; forms state plainly what happens to a submission. Admin
endpoints require the token header and compare in constant time; there
are no unauthenticated state changes.

## Lessons applied from the Exocortexia security pass

This backend is the same code family as the Exocortexia suite, whose
audit + pen-test (task 36.5.6/5.5.10/4.5.8, `docs/SECURITY.md` in that
repo) found real holes. The applicable findings map to controls here:

| Finding | What it was there | Control here |
|---|---|---|
| **A-F02** (High) | Auth failed open: missing/short SSO config silently disabled the gate; apps bound `0.0.0.0` | Backend **fails closed**: any partial or short-secret SSO config is a startup error; running with sign-in off requires the explicit `WISHNODE_DEMO_MODE=1` opt-in **and** backend pages carry a visible "Demo mode" banner while it lasts. Backend binds `127.0.0.1` only, behind nginx. |
| **A-F09** (Med) | `iat` optional voided the 120 s assertion lifetime cap | Assertion verification **requires `iat`**, caps `exp − iat` at 120 s, and caps `exp − now` at 150 s independently — the exo-sso contract, copied check for check. |
| **A-F11** (Med) | No CSRF defence on state-changing POSTs | **Origin/Host match enforced on every POST**, plus a double-submit CSRF token (`GET /api/csrf` sets the cookie; the ask page's script fills the hidden field) for clients that send no Origin. Session cookie is `SameSite=Lax`. The admin API is not a browser form: it requires a custom token header, which cross-site forms cannot set. |
| **A-F13** (Med) | No security response headers anywhere | Baseline set on every backend response: CSP `default-src 'self'; …; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`. Rendered static pages carry a meta CSP (frame-ancestors is not meta-expressible; full header coverage for static files arrives with the vhost include). |
| **A-F17** (Med) | Tracking codes 40-bit, deterministic, derivable offline | Codes are **128-bit CSPRNG** values (26 Crockford characters ≈ 130 bits, from `secrets`), never derived from submission contents; the only derivation is the claim's *address*, which is a hash of the code itself. |

Also applied from the same pass: **A-F06** (unbounded pre-auth
allocation) — 16 KB body cap checked from `Content-Length` before
reading, negative/absent lengths rejected, a 30 s per-connection read
deadline, and `client_max_body_size 32k` at the nginx edge; Python's
`http.client` header parser caps header lines/count underneath.
**A-F08** (session cookie without `Secure`) — the session cookie is
`Secure` + `HttpOnly` + `SameSite=Lax` (the `WISHNODE_COOKIE_SECURE=0`
opt-out exists only for plain-HTTP local staging, mirroring
`EXO_COOKIE_SECURE`).

One rendering disclosure: chapter 9 of the app phexts quotes the
pre-rewrite pages as provenance, and that old text names off-site
addresses. The renderer scrubs off-site addresses out of the
technical-details rendering (`[off-site address removed]`), so the
served site contains zero off-site links or addresses; the phexts
keep the original words as provenance.

## Deploy

`scripts/deploy.sh` (run on aletheia-core) ships this repo's `phexts/`,
`backend/`, `scripts/`, `assets/` and `deploy/` to the host's
`~/wishnode-stage/`, then `scripts/box-setup.sh` installs/updates:
data dirs, the Python venv (`phext==0.3.2`), secrets on first run
(generated on the host, 0600, never in this repo), systemd user units
(the two wishnode units plus the five `exo-*.service` units), a
docroot backup under `/sites/backups/`, a phext refresh + SQ restart
(replacing a hosted phext file wedges the daemon, so the restart is
part of the deploy), the nginx snippet copy into the docroot, and a
fresh render into the docroot.

The demo-app binaries are separate from the site deploy:
`scripts/install_exo_apps.sh` (run on aletheia-core) builds
wbic16/Exocortexia in release mode, ships the five binaries to
`~/exocortexia/bin/` with SHA-256 comparison, generates
`~/exocortexia/exo.env` on the host on first run, installs the
`exo-*.service` units, and smoke-checks ports 8801–8805.

Content edits: edit the phexts in this repo (the builder
`build_phexts.py` regenerates most of them from the Exocortexia
sources; `home.phext` chapter 8, "How this site works", is a hand
addition re-applied by `scripts/add_home_ch8.py`), commit, push, and
re-run `scripts/deploy.sh`.

## Honest limits

- Dynamic routes wait on the one-line nginx include above. Until then
  the forms are verified end-to-end against the backend on the host,
  the five demo apps are exercised end-to-end on the host, and the
  static pages carry the site.
- The demo apps' subpath mapping relies on `sub_filter` rewriting two
  attribute forms; it is exact for the audited 342a268 build (verified
  in source) and must be re-checked if the apps ever build URLs in
  JavaScript or emit other absolute references.
- The demo apps run in open demo mode by design: anyone who can reach
  them can use them, with synthetic data only. A real deployment adds
  sign-in via edit.phext.io (the same SSO the backend consumes) and
  the office's own data; the demo state directories are throwaway.
- SQ flushes by rewriting the whole phext file (no atomic rename); at
  this scale that is fine, and citizen files (the write-heavy tier) use
  temp-then-rename in the backend instead.
- SQ binds all interfaces in host mode (no bind flag); the tenant keys
  are the gate, same posture as the host's existing SQ services.
- Sessions and rate limits are in-memory: a backend restart signs
  everyone out and resets the counters. Acceptable for a demo intake;
  a shared store is the upgrade path.
- Claim addressing is sparse (720k section slots) but phext
  coordinates are positional; the +20 probe walk and replace-only
  writes keep collisions from corrupting neighbours at this scale.
- `home.phext` chapter 9 and the other "For technical staff" scrolls
  are provenance, including pre-rewrite page text; templates never
  render chapter 9 into main copy.
