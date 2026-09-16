# Plan — cross-provider round-trip verification

**Objective:** use two mailboxes we own (Proton `dj@ai4hu.org`, Gmail `daniel.jelinko@gmail.com`)
to construct known conversations and prove the tool reproduces them exactly. Two providers give
us the **ground truth Bridge denies us** — every open question from the build phase becomes
decidable because we control both ends.

The previous plan (read + draft pipeline) is archived at
`plan/archive/260916__build_read_draft_pipeline.md`.

## Phase 0 — Decision required before any of this (owner)

- [ ] **D-003 says drafts only, never send. Round-trip testing requires sending.**
      Proposed scoped exception: sending is permitted *only* to addresses on a hard allowlist
      containing exactly our two test addresses, enforced in code and covered by a test that
      asserts any other recipient is refused. Without this, Phases 2-4 cannot run.
- [ ] Gmail app password in `.env` (`GMAIL_PASS`) — blocks everything below.

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

## Success criteria

A single `just verify-roundtrip` that constructs the conversation, asserts every property above,
and exits non-zero on any failure. Screenshots as evidence for what only a human eye can judge.
