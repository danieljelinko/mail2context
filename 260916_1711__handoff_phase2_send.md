# Handoff — Phase 2, the send path

Orientation for a fresh agent taking over `mail2context`. Written 2026-09-16 at the end of the
Gmail-parity session. **Points at the living docs rather than repeating them — read those too.**
Supersedes `archive/260916_1356__handoff_roundtrip_testing.md`, whose "Gmail is entirely
unvalidated" is no longer true.

## What this repo is

A CLI that turns two mailboxes into LLM-readable context and composes replies as drafts:
**Proton** `dj@ai4hu.org` (business, via local Proton Mail Bridge) and **Gmail**
`daniel.jelinko@gmail.com` (personal). Everything runs through `just`. There is a `mail` skill at
`~/.claude/skills/mail/SKILL.md` — **invoke it before doing mail work**; it carries the safety
rules and the gotchas, and it is current as of this handoff.

## Read these first, in this order

| File | Why |
|---|---|
| `01_plan.md` | your objective — Phases 0 and 1 are done, **you start at Phase 2** |
| `02_progress.md` | where things stand, what the owner still owes |
| `03_decisions.md` | D-001..D-014. **D-003, D-011, D-013 and D-014 will bite you** |
| `04_learnings.md` | 36 hazards that each cost real debugging time |
| `README.md` | commands and setup |

## State at handoff

**Both mailboxes are validated. Phases 0 and 1 are complete.**

- Proton **and** Gmail each report **0 conversion loss across 900 messages** (`just audit`)
- 76 tests green under both `-p no:randomly` and the default shuffle; `ruff` clean; `just check`
  exits 0
- Bridge runs as a **systemd user unit** — it no longer dies with a terminal
- The D-011 send allowlist guard exists in `mail2context/send.py`
- **Nothing can send.** `grep -rniE "smtplib|sendmail|SMTP\(" mail2context/ scripts/ justfile`
  matches nothing. That is the state Phase 2 deliberately changes, and Phase 6 restores.

### The work is on a branch, unmerged and unpushed

```bash
git log --oneline main..HEAD    # the branch is fix/gmail-parity-audit
```

Each commit is independently green, so it bisects. **Ask the owner** whether to merge, push, or
open a PR before you build on top of it — do not assume.

## Where to start: Phase 2

`01_plan.md` Phase 2 sends a known 6-message conversation alternating Proton ↔ Gmail and asserts
the tool rebuilds exactly one thread of 6. Two things block the first send:

1. **`.env` has no `GMAIL_SMTP_*` entries.** Add host/port before anything can send via Gmail.
   Proton's SMTP is Bridge on `127.0.0.1:1025`, already in `.env`.
2. **Wire `check_recipients()` into the send path and print what it returns before sending.**
   It exists and is tested; it is not yet called by anything, because nothing sends yet.

## The send policy — read D-011 before writing a line of send code

Sending is authorised **temporarily** and **only** to `dj@ai4hu.org` and
`daniel.jelinko@gmail.com`, enforced by the hard allowlist in `mail2context/send.py`.

- **Never widen the allowlist.** A new address is a new owner decision, not a code edit.
  `SEND_ALLOWLIST` is a module constant rather than a parameter precisely so a call site cannot
  widen it — that is a deliberate departure from the house "pass vocabulary in as an argument"
  rule, commented at the constant.
- **Phase 6 REMOVES the send capability entirely** and restores drafts-only (D-003). That is
  part of the work, not cleanup for later. Leaving send enabled after validation violates D-011.
- If you find send code and the round-trip suite has already passed, that is a bug to report,
  not a feature to use.

## Traps that already cost time

Newly learned this session — the rest are in `04_learnings.md`:

- **`getaddresses` discards everything when handed two empty strings.** Building a list as
  `[msg.get(h) or '' for h in ('To','Cc','Bcc')]` breaks on every message with no Cc and no Bcc.
  Pass only headers that are set. This will bite again when the send path collects recipients.
- **A listening port is still not evidence.** After any Bridge restart the port accepts
  connections in ~2 s but LOGIN returns `no such user` for another ~5 s. Poll `just
  bridge-status` until it exits 0. It logs in now rather than grepping a port, so it tells the
  truth — the old version matched Ollama's `11434` and could never report DOWN.
- **Gmail fetches are minutes, not seconds.** 900 messages ≈ 15 min against ≈ 1 min for Bridge.
  Background every Gmail scan; never run two large ones at once. `just check` audits Proton only
  for this reason.
- **`imaplib` quotes nothing** — not mailbox names, and not multi-word SEARCH terms either.
  `M.uid('search', None, 'SUBJECT', 'two words')` is a `BAD` command.
- **Any BeautifulSoup rewrite pass must run innermost-first** (D-013). `find_all` returns a
  static list, so replacing an outer node detaches an inner one and its replacement never lands.
- **Gmail preserves `In-Reply-To`, `References` and `Message-ID` on draft APPEND; Proton strips
  them** (D-014). The "your draft will not thread" warning is Proton-only — do not repeat it for
  a Gmail draft.
- `/usr/bin/protonmail-bridge` opens a **GUI and blocks**. The headless core is
  `/usr/lib/protonmail/bridge/bridge`. Wrap exploratory calls in `timeout`.
- **`just` arguments are positional.** `just --list` prints defaults, not syntax.
- **Header-level verification is not verification.** For anything a human reads, inspect the
  render or ask the owner for a screenshot.

## Rules to carry forward

- **Never send** outside the D-011 allowlist, and remove the capability entirely at Phase 6.
- **Never commit mailbox content.** Exports go to `verify/`, gitignored. Ad-hoc probes belong in
  the session scratchpad, not the repo.
- Before drafting, **always ask** who receives it and whether it continues the thread or starts a
  new conversation (D-008). Show the `draft-preview` To/Cc/subject/OMITTED block first.
- Write bodies in **Markdown**, never hand-written HTML, and never hard-wrap. The signature is
  appended automatically from `signature.html` — do not put one in the body.
- Reads use `BODY.PEEK`; keep it that way so scanning never marks mail read.
- Red/green: the guard's own tests caught a real bug in the guard. Write the failing test first.

## Owner action outstanding

The FIPDes Day thank-you draft to Barbara in Proton Drafts still contains the literal
`[FRIEND'S NAME]`. The owner chose to edit it themselves in the Proton UI (2026-09-16) — leave it
alone, but it is fair to remind them it is still sitting there.

## First commands

```bash
cd ~/Work/tools/mail2context
git log --oneline main..HEAD          # unmerged commits — ask the owner what to do with them
just bridge-status && just accounts   # expect: up on 1143, then two OK lines
just check                            # 76 tests + lint + Proton loss audit, ~1 min
```

Then work `01_plan.md` Phase 2. Ask the owner for the `GMAIL_SMTP_*` values before your first
send, and show them the recipient list the guard returns before anything leaves the machine.
