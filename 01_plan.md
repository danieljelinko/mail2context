# Plan — cross-provider round-trip verification

**Objective:** use two mailboxes we own (Proton `dj@ai4hu.org`, Gmail `daniel.jelinko@gmail.com`)
to construct known conversations and prove the tool reproduces them exactly. Two providers give
us the **ground truth Bridge denies us** — every open question from the build phase becomes
decidable because we control both ends.

The previous plan (read + draft pipeline) is archived at
`plan/archive/260916__build_read_draft_pipeline.md`.

## Phase 0 — Authorisation (settled) + credential

- [x] **Send capability authorised, TEMPORARILY and narrowly** (D-011, owner, 2026-09-16).
- [ ] Gmail app password in `.env` (`GMAIL_PASS`) — blocks everything below.

Implement the guard **test-first, before any send code exists**:

- [ ] `SEND_ALLOWLIST = {'dj@ai4hu.org', 'daniel.jelinko@gmail.com'}`
- [ ] `send()` refuses if **any** To/Cc/Bcc recipient is outside it → verify: a test asserts a
      third address raises, and that a mixed list (one allowed, one not) also raises
- [ ] The allowlist is never widened. A new address is a new owner decision, not a code edit.
- [ ] Every send path prints the recipients before sending

## Phase 1 — Gmail parity (no sending needed)
- [ ] `just accounts` authenticates both → verify: two OK lines
- [ ] `just threads gmail` / `just unread gmail` / `just from X gmail`
      → verify: Gmail's `[Gmail]/All Mail` duplication does not double-count threads
- [ ] `just audit gmail 900` → verify: 0 losses, as Proton reports
- [ ] Draft APPEND to `[Gmail]/Drafts` → **verify whether Gmail preserves `In-Reply-To`**
      → this decides whether D-009 is Proton-specific or universal

## Phase 2 — Header and threading round-trip
- [ ] Send a known 6-message conversation alternating Proton ↔ Gmail
- [ ] Fetch from both sides; assert `group_threads` rebuilds **one** thread of exactly 6,
      in the order sent → the completeness check that was impossible before
- [ ] Assert `In-Reply-To`/`References` survive an actual send (D-009 is about *drafts*;
      sent mail is untested)
- [ ] Break the chain deliberately: strip `References` from one reply and confirm the tool
      splits the thread — proving the known blind spot behaves as documented
- [ ] Subject prefixes as really generated (`Re:`, `Fwd:`, `Auto:`) rather than fixtures

## Phase 3 — Content fidelity round-trip
- [ ] Send a message exercising every Markdown feature + accents + the signature
- [ ] Fetch on the other side → assert `just audit` reports 0 loss, the blue `4`
      (`rgb(59, 131, 194)`) survives, and no body is monospace
- [ ] Reply from Gmail's web UI so a **real** `gmail_quote` block is generated, then verify
      stripping — so far quote stripping is tested against fixtures and observed mail only
- [ ] Same via Proton's UI for `protonmail_quote`
- [ ] Attachment round-trip: filenames surface, bytes match

## Phase 4 — Behaviour round-trip
- [ ] `\Answered` set after replying; `\Seen` never set by our reads (assert after a full scan)
- [ ] `needs-reply` correct on a conversation whose state we constructed
- [ ] Thread key stable as the conversation grows message by message

## Phase 5 — Visual evidence (browser)
- [ ] Use the `ui-feature-evidence` skill with a browser to open each sent message in the
      Proton and Gmail web UIs
- [ ] One screenshot per claim: proportional font, signature styling, list/table/link rendering,
      threading in the client's own conversation view
- [ ] Bind into an evidence README with a coverage matrix — no silent gaps

## Phase 6 — REMOVE the send capability (not optional)

The authorisation in D-011 is temporary. When Phases 1-5 pass:

- [ ] Delete the send code path, the allowlist and its CLI/just entry points
- [ ] Keep the round-trip tests that do not require sending; mark the rest skipped with a note
      pointing at D-011
- [ ] `grep -rn "smtp\|send" mail2context/ scripts/ justfile` → verify: nothing can send
- [ ] Restore the `mail` skill's unqualified "never send" wording
- [ ] Append a decision row recording that D-011 has been retired, with the date
- [ ] Tell the owner it is done

**Leaving send enabled after validation violates D-011.** Treat this phase as part of the work,
not cleanup to do later.

## Success criteria

A single `just verify-roundtrip` that constructs the conversation, asserts every property above,
and exits non-zero on any failure. Screenshots as evidence for what only a human eye can judge.
Then Phase 6, and the tool is back to drafts-only.
