# Citizen phext template — wishnode.net intake

Task 34.6.6/7.7.10/7.6.10 · Lane A (content). The backend provisions one
phext per submitter ("citizen") at runtime from this template. Lane A
creates **no real citizen phexts** — only this specification and the
skeleton file `phexts/citizen-template.phext`.

## File

- Path pattern: `citizen/<citizen_id>.phext`
- `citizen_id` is opaque and server-derived at first submission:
  `cz-<16 lowercase hex>`. It is never a name, email, or any value the
  submitter typed (the pilot form collects no name or contact field).

## Layout (coordinates are `library.shelf.series / collection.volume.book / chapter.section.scroll`)

| Coordinate | Scroll |
|---|---|
| `1.1.1/1.1.1/1.1.1` | Header: what this phext is + provisioning note |
| `1.1.1/1.1.1/1.1.2` | `citizen_id: cz-…` (written once) |
| `1.1.1/1.1.1/1.1.3` | `created_at: <RFC 3339 UTC>` (written once) |
| Submission N (N ≥ 1) | Lives in chapter `1 + N` |
| `…/<1+N>.1.1` | `tracking_code: <code shown to the submitter>` |
| `…/<1+N>.1.2` | `form: ask-about-a-pilot` (form kind) |
| `…/<1+N>.1.3` | `submitted_at: <RFC 3339 UTC>` |
| `…/<1+N>.1.4` | `content_hash: sha256:<hex>` — SHA-256 of the section-2 field scroll texts concatenated in coordinate order; identical to the claim's `+3` scroll in `phexts/intake.phext` |
| `…/<1+N>.2.<k>` | One scroll per form field, in form order, format `field: <name> — <value as given>`. Pilot form fields: `program`, `office`, `need`, `message` |
| `…/<1+N>.3.1` | `state: <latest state>` — a read mirror copied from the claims register; the register's transition records stay authoritative |

## Rules

- Field scrolls are written once at submission and never edited.
  Corrections arrive as a new submission (new chapter), not an edit.
- The citizen reads their own phext (and their claim state) by presenting
  the tracking code; staff roles read per the roles scroll in
  `phexts/intake.phext` (`1.1.1/1.1.1/1.5.1`).
- The claims register (`phexts/intake.phext`) holds only the pointer,
  hash, timestamp, and workflow state — never submission content.
