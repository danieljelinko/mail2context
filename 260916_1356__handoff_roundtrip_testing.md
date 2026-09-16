# Handoff — cross-provider round-trip testing

Orientation for a fresh agent taking over `mail2context`. Written 2026-09-16 at the end of the
build phase. **Points at the living docs rather than repeating them — read those too.**

## What this repo is

A CLI that turns two mailboxes into LLM-readable context and composes replies as drafts:
**Proton** `dj@ai4hu.org` (business, via local Proton Mail Bridge) and **Gmail**
`daniel.jelinko@gmail.com` (personal). Everything runs through `just`. There is a `mail` skill at
`~/.claude/skills/mail/SKILL.md` — **invoke it before doing mail work**; it carries the safety
rules and the gotchas.

## Read these first, in this order

| File | Why |
|---|---|
| `01_plan.md` | your objective — the round-trip test plan, Phases 0-5 |
| `02_progress.md` | where things stand, what is blocked |
| `03_decisions.md` | D-001..D-010. **D-003 and D-009 will bite you** |
| `04_learnings.md` | ~18 hazards that each cost real debugging time |
| `README.md` | commands and setup |

## State at handoff

Proton works end to end, verified against real mail — not fixtures:

- 898 messages, 262 threads reconstructed from headers (IMAP has no threading; Bridge exposes no
  conversation id)
- `just audit` reports **0 information loss** across all 898 messages, checking text runs, link
  targets, image alt text and attachment names
- Search and flag awareness work (`just unread`, `just from`, `just about`, `just needs-reply`)
- Drafts are written to Proton's Drafts folder, rendered from Markdown by a deterministic
  converter, carrying the real AI4HU signature
- 59 tests green, `ruff` clean

**Gmail is entirely unvalidated.** `GMAIL_PASS` is empty. Nothing about Gmail has ever run.

## Two blockers before Phase 2

1. **`GMAIL_PASS`** — owner generates a Google app password. Without it every Gmail command
   refuses.
2. **The send policy — read D-011 carefully.** The owner has authorised sending, but
   **temporarily and only** to `dj@ai4hu.org` and `daniel.jelinko@gmail.com`. Enforce it with a
   hard allowlist in code, written test-first, refusing any message with *any* recipient outside
   it. **Never widen the allowlist** — a new address is a new owner decision, not a code edit.
   **The capability is removed once the suite passes** (`01_plan.md` Phase 6); leaving it in
   place violates D-011.

## Traps that already cost time

- `/usr/bin/protonmail-bridge` opens a **GUI and blocks**. The headless core is
  `/usr/lib/protonmail/bridge/bridge`. Wrap exploratory calls in `timeout`.
- Bridge must be running or Proton commands fail — it *is* the IMAP server. `just bridge-status`.
  It currently lives in the owner's terminal and dies with it; a systemd unit was offered and
  not yet installed.
- **`just` arguments are positional.** `just --list` prints defaults, not syntax. Never paste a
  signature.
- Sorting the raw `Date` header sorts by weekday name. Use `thread.sent_at`.
- `imaplib` does not quote mailbox names; Proton's contain spaces (`All Mail`, `Labels/...`).
- **Proton strips `In-Reply-To` from appended drafts** (D-009). Whether *sent* mail keeps it is
  untested — Phase 2 answers this.
- Header-level verification is not verification. Checking To/Subject/body-present passed a draft
  that rendered monospace with sentences broken mid-phrase. For anything a human reads, inspect
  the render or ask for a screenshot.

## Rules to carry forward

- **Never send** outside the D-011 allowlist, and remove the capability entirely at Phase 6.
- **Never commit mailbox content.** Exports go to `verify/`, gitignored.
- Before drafting, **always ask** who receives it and whether it continues the thread or starts a
  new conversation (D-008). Show the `draft-preview` To/Cc/subject/OMITTED block first.
- Write bodies in **Markdown**, never hand-written HTML, and never hard-wrap. The signature is
  appended automatically from `signature.html` — do not put one in the body.
- Reads use `BODY.PEEK`; keep it that way so scanning never marks mail read.

## First commands

```bash
cd ~/Work/tools/mail2context
just bridge-status && just accounts      # expect proton OK; gmail OK once GMAIL_PASS is set
just check                               # tests + lint + full-mailbox loss audit
just threads gmail 400 10                # first ever Gmail call — Phase 1 starts here
```

Then work `01_plan.md` Phase 1, which needs no sending. Stop at Phase 2 until the owner has
answered Phase 0.
