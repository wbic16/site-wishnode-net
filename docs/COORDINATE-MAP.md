# wishnode.net — phext coordinate map

Task 34.6.6/7.7.10/7.6.10 · Lane A (content inventory + build) · 2026-11-07
Sources: site clone `wbic16/site-wishnode-net @ exo c5fd64b6a367`;
content sources `wbic16/Exocortexia @ exo 9660d3becd` (`~/exo-verify`).

## The tier model (Will, 2026-11-07 22:33 CST)

Three tiers, secured by roles and claims:

1. **Citizen phexts** — one per submitter, provisioned by the backend at
   runtime. Hold submission content. Template: `phexts/citizen-template.md`
   + skeleton `phexts/citizen-template.phext`.
2. **Page phexts** — one per major page/section of wishnode.net (this
   directory, `phexts/`). Published content only; the source of truth the
   page templates render from.
3. **Claims register** — `phexts/intake.phext`. Holds pointers + hashes +
   workflow state for every form submission, never the content itself.
   Transitions append; nothing is overwritten.

## Files built

| File | Serves | Scrolls |
|---|---|---|
| `phexts/home.phext` | `/` (suite overview + shared elements) | 32 |
| `phexts/records-desk.phext` | `/exocortexia/records-desk.html` | 33 |
| `phexts/minutes-publisher.phext` | `/exocortexia/minutes-publisher.html` | 31 |
| `phexts/contract-ledger.phext` | `/exocortexia/contract-ledger.html` | 32 |
| `phexts/data-catalog.phext` | `/exocortexia/data-catalog.html` | 31 |
| `phexts/forms-router.phext` | `/exocortexia/forms-router.html` | 34 |
| `phexts/verification.phext` | "Read the full test results" page | 57 |
| `phexts/statutes.phext` | Statute/framing sheets for all five apps | 83 |
| `phexts/security.phext` | `/exocortexia/security.html` | 46 |
| `phexts/intake.phext` | Claims register (scheme + empty root) | 14 |
| `phexts/citizen-template.phext` | Citizen phext skeleton (template only) | 13 |

Total: 415 scrolls across 11 phexts. (Updated 2026-11-07 by the
coordinator: home.phext gained ch. 8 "How this site works" (32 → 41
scrolls, `scripts/add_home_ch8.py`), and security.phext was rebuilt
from the published audit (17 → 46 scrolls,
`scripts/build_security_phext.py`).)

**Statutes placement decision:** statutes live in their own
`phexts/statutes.phext`, not folded into each app phext. Why: the sheets
are a single legal source of truth cited by all pages; one home means one
place to correct, and each app phext already carries the *material* statute
facts in its main copy (chapter "What the law says") plus a descriptive
link. Folding five full sheets into five app phexts would duplicate the
texts the templates render least and bloat every page phext.

## Coordinate conventions (all phexts)

Coordinates are `library.shelf.series / collection.volume.book /
chapter.section.scroll`. Every phext built here uses `1.1.1/1.1.1` as its
base; meaning is carried by **chapter.section.scroll**:

- Chapter 1 always opens the phext: `1.1.1` = header/provenance scroll,
  `1.1.2` = page title, `1.1.3` = headline/tagline.
- **The plain-English summary is always its own named scroll range:
  `1.2.1` (range label) + `1.2.2` (the summary text). Templates render it
  first.** (Verification and security phexts follow the same rule.)
- Main copy chapters follow in reading order; within a chapter, section 1
  scroll 1 is the section heading, scrolls 2+ are paragraphs/bullets, one
  scroll per block.
- **Chapter 9 is always "For technical staff"** — component paths, ports,
  SSO internals, raw counts, and a provenance scroll holding the page's
  pre-rewrite text. Templates must not render chapter 9 into main copy.
- App phext chapter order: 1 header + summary · 2.. main sections ·
  "What the law says" (material statute facts, main copy) · "Good to know"
  (replaces the old Details box) · "Ask about a pilot" (next step) ·
  links (descriptive labels only) · 9 technical.

### home.phext specifics

- Ch. 2 "What it is" — includes the site's single plain explanation of
  phext ("a way of storing information as plain text that both people and
  computers can read"); other phexts do not lean on the term.
- Ch. 3 the five applications (one scroll per app: name, plain line, law).
- Ch. 4 proof in office terms (numbers translated; engineering figures
  live in `verification.phext`).
- Ch. 5 security note (audit in progress, no results).
- Ch. 6 "Ask about a pilot" next-step copy (shared wording, also the
  closing chapter of every app phext and of `verification.phext`).
- Ch. 7 **shared elements**: brand line (7.1.1), nav labels (7.1.2),
  footer company block (7.1.3: Phext, Inc. named as a company — what it
  does + the on-site form path; **no personal links of any kind**),
  license line (7.1.4).

### verification.phext specifics

- Ch. 1: plain summary of all receipts (numbers translated into office
  terms at first use) + next-step scroll.
- Ch. 2–10: the **full text of `docs/VERIFICATION.md`, section by
  section** (Environment, Build, Unit tests, Seed generation, Store
  benchmarks, Functional smoke, SSO smoke, HTTP load, Known failures and
  the fix) — one chapter per `##` section, heading scroll first, then one
  scroll per paragraph/block, each labelled "FULL TECHNICAL RECORD".
  Test counts appear in main copy only in translated form ("checked by
  69 automated tests"); the per-target table lives here.

### statutes.phext specifics

- Ch. 1: header. Ch. 2–6: one chapter per app, in site order
  (Records Desk, Minutes Publisher, Contract Ledger, Data Catalog,
  Forms Router). Within a chapter: `x.1.1` title, `x.1.2` plain-English
  note, `x.1.3` the sheet's preamble (title/demo/statute lines), then one
  section per `##` section of the sheet (`x.<s>.1` heading, `x.<s>.2+`
  paragraphs) — **full verbatim text** of `docs/*-statute.md`.

### security.phext specifics

- Rebuilt 2026-11-07 from the published audit (`docs/SECURITY.md` in
  wbic16/Exocortexia @ exo `342a268`, task 36.5.6/5.5.10/4.5.8) by
  `scripts/build_security_phext.py`. The audit-pending placeholder is
  retired; the audit is complete and its results are the content.
- Ch. 1 header + plain summary (`1.2.x`, FK 3.7 / FRE 88.3 measured at
  build). Ch. 2 "What the check found" (five holes, plain words, one
  section each). Ch. 3 "What we fixed, and how we know" (84 tests,
  49/49 live re-checks). Ch. 4 "What is still limited" (residual risks
  in plain words). Ch. 5 reporting a problem (on-site form first).
  Ch. 6 next step ("Ask about a pilot").
- Ch. 7–12 **the full technical record**: the audit report word for
  word, one chapter per `##` section (scope and method; findings and
  status; pen-test battery; re-verification numbers; new operator
  surface; residual risks). Headings carry the prefix
  `FULL TECHNICAL RECORD —`, which is how the renderer routes them
  under the record banner (same pattern as verification.phext's
  record chapters; the ch. 9 "technical staff" convention does not
  apply inside the record).

## Claims register scheme (`phexts/intake.phext`)

Chapter 1 is the scheme; the register root is `1.1.2` (state: EMPTY,
claims_written: 0 — seeded with **no fake claims**). Claims live at
chapter ≥ 2.

### Claim record (6 field scrolls + transitions)

At base coordinate `B = 1.1.1/1.1.1/<chapter>.<section>.<base>`:

| Offset | Scroll | Format |
|---|---|---|
| +0 | header | `claim: <tracking_code>` |
| +1 | citizen_id | `citizen_id: cz-<16 lowercase hex>` (opaque, server-derived) |
| +2 | citizen_pointer | `citizen_pointer: citizen/<citizen_id>.phext @ <submission's first field coordinate>` |
| +3 | content_hash | `content_hash: sha256:<64 hex>` of the citizen-phext field scrolls in coordinate order |
| +4 | created_at | `created_at: <RFC 3339 UTC>` (written once) |
| +5 | state | `state: received` at creation; **never overwritten** — authoritative state is the latest transition record |
| +10, +11, … | transitions | `transition: <from> -> <to> \| actor_role: <role> \| at: <RFC 3339 UTC> \| note: <text>` — append-only, one scroll per state change |

Workflow: `received → routed → in_review → closed` (only these 3
transitions are legal; the backend rejects any other move and writes
nothing). Roles: `submitter` (create + read own by code), `intake-staff`
(routed), `reviewer` (in_review, closed), `system` (timed actions).
Full scheme text: intake.phext scrolls `1.2.1`–`1.5.2`.

### Addressing derivation (from the tracking code)

```
h        = sha256_hex("wishnode-claim:" + CODE)   # CODE trimmed, upper-cased
chapter  = 2   + (int(h[0:5],  16) mod 800)
section  = 1   + (int(h[5:10], 16) mod 900)
base     = 1   + (int(h[10:15],16) mod 880)
```

Anyone holding the code can recompute the address with any SHA-256 tool.
Collision rule: if the `+0` header at the derived base names a different
code, probe `base+20`, `base+40`, … in the same chapter/section; the
probe count is recorded in the header; lookup walks the same probes.

**Worked example** (scheme illustration, not a real claim): tracking code
`TEST-0000-EXAMPLE` derives to chapter 663, section 280, base scroll 829 —
claim fields at `1.1.1/1.1.1/663.280.829` … `663.280.834`, first
transition at `663.280.839`.

## Citizen phext template

See `phexts/citizen-template.md` (full spec) and
`phexts/citizen-template.phext` (skeleton with placeholder scrolls).
Summary: ch. 1 identity (`citizen_id`, `created_at`); submission N in
chapter `1+N` — §1 meta (tracking code, form kind, time, content hash),
§2 one scroll per form field, §3 state mirror. The backend provisions
these at runtime; Lane A created none.

## Readability evidence (UX audit method)

Method: visible copy → Flesch-Kincaid / Flesch Reading Ease, syllables by
vowel-group heuristic (trailing silent-e discounted, min 1/word) — the
audit's method (`~/workspace/your_files/wishnode-ux-audit-34.5.6.md`).
Measured over each page phext's **main copy** (plain summary + main
sections + statute-facts chapter + "Good to know" + next step; chapter 9
technical scrolls, full statute texts, and the verification technical
record are reference material and are excluded, exactly as the audit
excludes nothing it calls main copy). Bar: FK ≤ 8, FRE ≥ 60.

| Page phext | FK grade | Reading Ease | Words | Pass |
|---|---|---|---|---|
| home | 3.7 | 85.3 | 721 | ✅ |
| records-desk | 3.7 | 87.2 | 568 | ✅ |
| minutes-publisher | 4.5 | 83.8 | 549 | ✅ |
| contract-ledger | 3.8 | 87.2 | 527 | ✅ |
| data-catalog | 3.8 | 88.6 | 518 | ✅ |
| forms-router | 3.8 | 87.4 | 633 | ✅ |
| verification (plain summary) | 3.3 | 88.3 | 512 | ✅ |
| security | 4.7 | 82.1 | 361 | ✅ |

Coordinator's update (2026-11-07): the security row above is the
retired placeholder. The rebuilt security phext's plain chapters
(1–6) measure **FK 3.7 / FRE 88.3** over 1,017 words (printed by
`scripts/build_security_phext.py` at build time), and the rendered
security page's main copy measures FK 7.0 / FRE 69.5 (full page incl.
the verbatim record: FK 9.3 / FRE 58.8 — the record is reference
material, excluded from the bar on the same basis as the statute
texts). Rendered main copy for every other page measures FK ≤ 4.7 /
FRE ≥ 82; full-page scores incl. technical details run FK ≤ 6.8 /
FRE ≥ 69.7 for the app and home pages.

Copy rules applied throughout: plain summary first; jargon translated at
first use (tamper-proof record gloss, phext explained once on home,
"made-up" for synthetic, "checked" for computed); the old Details box is
gone — replaced by "Good to know"; performance numbers translated into
office terms at first use; every page closes with who made it (Phext,
Inc.) + the intake path; link labels are descriptive sentences, never
file paths.
