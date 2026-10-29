# Plan — cross-provider round-trip verification

**Objective:** use two mailboxes we own (Proton `dj@ai4hu.org`, Gmail `daniel.jelinko@gmail.com`)
to construct known conversations and prove the tool reproduces them exactly. Two providers give
us the **ground truth Bridge denies us** — every open question from the build phase becomes
decidable because we control both ends.

The previous plan (read + draft pipeline) is archived at
`plan/archive/260916__build_read_draft_pipeline.md`.

## Phase 0 — Authorisation (settled) + credential

- [x] **Send capability authorised, TEMPORARILY and narrowly** (D-011, owner, 2026-09-16).
- [x] Gmail app password in `.env` (`GMAIL_PASS`) — set by the owner; both accounts authenticate.

Implement the guard **test-first, before any send code exists** — **DONE 2026-09-16**:

- [x] `SEND_ALLOWLIST = {'dj@ai4hu.org', 'daniel.jelinko@gmail.com'}` in `mail2context/send.py`,
      a module constant and **not** a parameter, so no call site can widen it. This knowingly
      departs from the house "pass project vocabulary in as a required argument" rule; safety
      outranks it here, and the departure is commented at the constant.
- [x] `check_recipients()` refuses if **any** To/Cc/Bcc recipient is outside it → 9 tests: a
      third address raises, a **mixed** list (one allowed, one not) raises, an address hidden in
      Bcc raises, a lookalike (`dj@ai4hu.org.attacker.example`) raises, and a message addressed
      to nobody raises rather than passing vacuously.
- [x] The allowlist is never widened — `test_send_allowlist_holds_exactly_the_two_addresses_
      d011_authorised` is the tripwire for a silent edit.
- [x] `check_recipients()` *returns* the addresses so every future send path can print them
      before sending. **No send path exists yet** — `grep -rniE "smtplib|sendmail|SMTP\(" ` over
      `mail2context/ scripts/ justfile` matches nothing. The guard deliberately predates it.

## Phase 1 — Gmail parity (no sending needed) — **DONE 2026-09-16**
- [x] `just accounts` authenticates both → two OK lines (proton 20 folders, gmail 13)
- [x] `just threads gmail` / `just unread gmail` / `just from X gmail`
      → no double-counting: 400/400 distinct `Message-ID` in **both** `[Gmail]/All Mail` and
        `INBOX`, 0 duplicates, 0 threads holding the same id twice. `cmd_search` already
        de-duplicates its two fetches by `Message-ID`.
- [x] `just audit gmail 900` → **0 losses**, matching Proton. Took three real defects to get
      there: the audit compared the HTML part against plain-part output (D-012), nested anchors
      lost their href, and anchors parsed inside an `<img>` were destroyed (D-013).
- [x] Draft APPEND to `[Gmail]/Drafts` → **Gmail PRESERVES `In-Reply-To`, `References` and the
      original `Message-ID`**; the pair regrouped as one thread of 2. **D-009 is Proton-specific**
      (D-014). Probe was self-addressed and binned afterwards.

## Phase 2 — Header and threading round-trip — **DONE 2026-09-16** (run `91fcac`)
- [x] Send a known 6-message conversation alternating Proton ↔ Gmail — `just verify-roundtrip`,
      each reply built by the production `build_reply` from the copy that actually arrived
- [x] Fetch from both sides; assert `group_threads` rebuilds **one** thread of exactly 6,
      in the order sent → **passes identically on Proton and Gmail**
- [x] Assert `In-Reply-To`/`References` survive an actual send → **they do, on both providers**.
      D-009's stripping is specific to draft APPEND, not to Proton mail generally (D-015)
- [x] Break the chain deliberately → the 7th reply, sent with `In-Reply-To`/`References`
      removed, splits into 6 + 1 on **both** sides. Note it must be the LAST message: a broken
      middle reply is healed by later replies' `References` (`04_learnings.md`)
- [x] Subject prefixes as really generated: five real `Re:` prefixes, and an `Auto:` stacked at
      step 4 that step 5's `_reply_subject` collapsed back to a single `Re:` in transit

## Phase 3 — Content fidelity round-trip
- [ ] Send a message exercising every Markdown feature + accents + the signature
- [ ] Fetch on the other side → assert `just audit` reports 0 loss, the blue `4`
      (`rgb(59, 131, 194)`) survives, and no body is monospace
- [ ] Reply from Gmail's web UI so a **real** `gmail_quote` block is generated, then verify
      stripping — so far quote stripping is tested against fixtures and observed mail only
- [ ] Same via Proton's UI for `protonmail_quote`
- [ ] Attachment round-trip: filenames surface, bytes match (bytes compared by digest inside
      `check_attachment`; surfacing attachment *contents* to the LLM is split out — D-016)

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

## Phase 6 — CONFINE the send capability to the guard (rewritten 2026-09-17, D-021)

D-011's "delete the send code" is replaced: with `mail-guard` installed the code path cannot reach the
wire except through the guard's SMTP relay, and only while the owner has opened level 3 with sudo for
a bounded time. The code stays; the guarantee moved out of the repo.

- [ ] `mail-guard` installed and `just live-check` green at levels 1, 2 and 3 (Track G)
- [ ] The D-011 allowlist stays in `send.py` as a second belt; `test_send_allowlist_holds_exactly_the_two_addresses_d011_authorised` stays its tripwire
- [ ] `grep -rn "smtp\|send" mail2context/ scripts/ justfile` documents what exists — every send path goes through `send_message`, whose host/port come from `.env`, which routes to the relay
- [ ] Drop the TEMPORARY markers from `send.py`, `roundtrip.py`, `scripts/roundtrip.py` and the recipes; point them at D-021 instead
- [ ] The `mail` skill says: sending needs level 3, which only the owner opens

## Track G — `mail-guard`: enforcement the agent cannot lift (D-017, separate repo)
- [x] `~/Work/tools/mail-guard` with its own L4 docs, tests (89), justfile — built 2026-09-17
- [x] nftables: uid 1000 rejected on 25, 110, 143, 465, 587, 993, 995, 1025, 1143 at every level (D-020: no toggling)
- [x] Filtering IMAP proxy as system user `mailguard`, real credentials root-owned, plaintext loopback per account;
      level 1 refuses STORE/MOVE/COPY/EXPUNGE/DELETE/CREATE/RENAME/CLOSE except D-018; APPEND to Drafts only; literals and IDLE raw
- [x] SMTP relay per account: refuses below level 3, authenticates upstream with the real password at 3 (D-020)
- [x] `sudo mail-guard 1|2|3 --for DURATION`; level 3 carries its expiry in the file and re-arms by transient timer
- [x] mail2context works in BOTH modes: `*_IMAP_TLS=none` / `*_SMTP_TLS=none`, `just guard-status`, skill's first check
- [x] Unit tests: filter, literal passthrough, desync on upstream NO, IDLE, TLS/STARTTLS upstreams, relay, CLI
- [ ] **Owner:** `sudo ~/Work/tools/mail-guard/install.sh --seed-from ~/Work/tools/mail2context/.env`, merge
      `/etc/mail-guard/mail2context.env` into `.env`, then the live matrix: `just live-check` (in mail-guard) at 1, 2, 3
      plus `just threads`, `just draft-preview`, `just draft`, `just content-preview` at 1 and `just content-send` at 3
- [ ] **Owner:** rotate the Gmail app password; disconnect the claude.ai Gmail connector
- [x] Owner decisions: D-018 STORE exception; connector to be disconnected; docker group kept; Phase 6 rewritten (D-021)

## Track S — scheduled send: decided (D-019, 2026-09-17)
- [x] Compared (a) draft + the provider web UI's own schedule-send with (b) a guard-side approved queue
- [x] Owner chose (a): no code; the `mail` skill tells the agent to draft and hand over the schedule step

## Track D — delete an agent-made draft (D-022, 2026-10-29)
- [x] `just draft-list [account]` — read-only; UID, Paris time, To, Subject, first body line
- [x] `just draft-delete UID [account] [--dry-run|--yes]` — Drafts only, `\Draft` only, UID STORE + UID EXPUNGE
- [x] `just draft` / `just compose` print `draft uid: N`
- [x] Live round-trip on Proton and Gmail with throwaway drafts
- [ ] Live check at guard levels 1 (refused) and 2 (deletes), once the guard is installed

## Later — attachment contents (split out of Phase 3, D-016)
- [ ] Surface attachment *contents*, not just filenames: decide formats (txt/pdf/docx), where the
      extracted text goes, size limits. Own phase after Phase 6; needs no send capability.

## Success criteria

A single `just verify-roundtrip` that constructs the conversation, asserts every property above,
and exits non-zero on any failure. Screenshots as evidence for what only a human eye can judge.
Then Phase 6, and the tool is back to drafts-only.
