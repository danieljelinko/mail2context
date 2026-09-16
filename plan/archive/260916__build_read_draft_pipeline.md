# Plan

**Objective:** a CLI that turns both mailboxes — Proton (business) and Gmail (personal) — into
LLM-readable context, and composes replies as **drafts only**.

## Phase 1 — Credentials (owner-only, blocking)
- [ ] Proton Bridge login via `/usr/lib/protonmail/bridge/bridge --cli` → `login`
- [ ] Capture `info` output: IMAP/SMTP ports + generated bridge password → `.env`
- [ ] Confirm Proton plan is paid (Bridge is a paid-plan feature)
- [ ] Gmail app password (needs 2FA on the account) → `.env`
- [ ] Verify both mailboxes answer over IMAP

## Phase 2 — Read layer
- [ ] IMAP connect + folder list, both accounts → verify: list INBOX message count for each
- [ ] Fetch headers + raw RFC822 → verify: round-trip a real message through `BytesParser`
- [ ] **Thread reconstruction** from `Message-ID` / `In-Reply-To` / `References`
      → verify: a known multi-message exchange rebuilds in correct order
      → **if this proves unworkable, see decision D-001 fallback**

## Phase 3 — Context rendering
- [ ] Quote + signature stripping for Proton / Gmail / Outlook markup → verify: fixture tests
- [ ] HTML→text flattening → verify: fixture tests
- [ ] Thread → markdown renderer → verify: a real thread renders readably, no repeated boilerplate

## Phase 4 — Draft composition
- [ ] Build RFC 5322 reply with correct `In-Reply-To` / `References`
- [ ] IMAP `APPEND` to Drafts with `\Draft` flag → verify: draft appears in Proton Mail UI, threaded

## Phase 5 — CLI
- [ ] Commands: list / show thread / dump context / draft reply
- [ ] Smoke test end-to-end on a real thread in each account
