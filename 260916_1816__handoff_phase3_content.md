# Handoff — Phase 3, content fidelity

Orientation for a fresh agent taking over `mail2context`. Written 2026-09-16 at the end of the
Phase 2 session. **Points at the living docs rather than repeating them — read those too.**
Supersedes `archive/260916_1711__handoff_phase2_send.md`, whose "Nothing can send" is no longer
true: a send path now exists under D-011 and **Phase 6 must remove it**.

## What this repo is

A CLI that turns two mailboxes into LLM-readable context and composes replies: **Proton**
`dj@ai4hu.org` (business, via local Proton Mail Bridge) and **Gmail** `daniel.jelinko@gmail.com`
(personal). Everything runs through `just`. There is a `mail` skill at
`~/.claude/skills/mail/SKILL.md` — **invoke it before doing mail work**; it is current as of this
handoff.

## Read these first, in this order

| File | Why |
|---|---|
| `01_plan.md` | your objective — Phases 0, 1 and 2 are done, **you start at Phase 3** |
| `02_progress.md` | where things stand, what the owner still owes |
| `03_decisions.md` | D-001..D-015. **D-003, D-011 and D-015 matter most** |
| `04_learnings.md` | 40 hazards that each cost real debugging time |
| `README.md` | commands and setup |

## State at handoff

**Phases 0, 1 and 2 are complete.** `just check` exits 0: 87 tests green under both
`-p no:randomly` and the default shuffle, `ruff` clean, 0 conversion loss across 900 Proton
messages. Gmail also reports 0 loss across 900.

Phase 2 sent a live 6-message conversation alternating Proton and Gmail (run `91fcac`, still in
both mailboxes) and proved:

- `group_threads` rebuilds **one thread of exactly 6, in send order, identically on both sides**
- `In-Reply-To` and `References` **survive a real send on both providers** — D-009's stripping is
  specific to draft APPEND, not to Proton mail (**D-015**)
- a 7th reply sent with its threading headers removed **splits the thread 6 + 1 on both sides**
- the `Auto:` prefix stacked at step 4 was collapsed back to a single `Re:` in transit

### The send capability is LIVE and must be removed

`mail2context/send.py`, `mail2context/roundtrip.py`, `scripts/roundtrip.py` and the five
`roundtrip*` recipes all carry TEMPORARY in their own docstrings. **`01_plan.md` Phase 6 deletes
them.** That is part of the work, not cleanup for later — leaving send enabled after validation
violates D-011.

- The allowlist is `{dj@ai4hu.org, daniel.jelinko@gmail.com}` and is **never widened** — a new
  address is an owner decision, not a code edit.
- `check_recipients()` runs before any connection is opened; verified live that a third party, a
  mixed list and a lookalike domain are all refused with **zero sockets opened**.
- `just roundtrip-preview` shows what would be sent and whom the guard approves. It sends nothing.

## Where to start: Phase 3

Content fidelity. The plumbing exists, so most of it is: send a message exercising every Markdown
feature, accents and the signature, fetch the delivered copy, assert `just audit` reports 0 loss
and the blue `4` (`rgb(59, 131, 194)`) survives.

**Two items need the owner at a browser** and cannot be done from here: a **real** `gmail_quote`
block (owner replies from Gmail's web UI) and a real `protonmail_quote` (Proton's UI). Quote
stripping has so far only been tested against fixtures and observed mail. Ask for those replies
early — they gate the rest of Phase 3.

Attachment round-trip is also Phase 3, and attachment **contents** are still not extracted, only
filenames.

## Traps that already cost time

The rest are in `04_learnings.md`; these are the ones this session added or hit.

- **Never assert `References` equals what you sent.** Proton appends its own
  `@protonmail.internalid` to every stored message's `References`. Assert **containment**.
- **A broken *middle* reply does not split a thread** — later replies still name the orphan in
  `References` and union-find heals the gap. Only an orphaned **last** message splits. A test
  written the other way round returned "no problems" and was right.
- **Print normalised UTC, never a raw offset.** Proton sends `+0000` and Gmail `+0200`, so a
  correctly-ordered thread prints as scrambled. This session reintroduced that exact bug and
  removed it again.
- **A thread the tool splits can read as one conversation to a human** — the broken 7th reply
  still says `Re: ...`. Say "the tool grouped N messages", never "the thread has N".
- **`imaplib` quotes nothing** — not mailbox names, not multi-word SEARCH terms.
- **Gmail fetches are minutes, not seconds** (900 msgs ≈ 15 min vs ≈ 1 min for Bridge). Background
  every Gmail scan; never run two at once. A subject SEARCH is fast because it fetches only hits.
- **A listening port is not evidence.** After a Bridge restart, poll `just bridge-status` until it
  exits 0 — it logs in rather than grepping a port.
- `/usr/bin/protonmail-bridge` opens a **GUI and blocks**. The headless core is
  `/usr/lib/protonmail/bridge/bridge`.
- **`just` arguments are positional.** `just --list` prints defaults, not syntax.
- **Header-level verification is not verification.** For anything a human reads, inspect the
  render or ask the owner for a screenshot.

## Rules to carry forward

- **Never send** outside the D-011 allowlist, and **remove the capability entirely at Phase 6**.
- **Never commit mailbox content.** Exports go to `verify/`, gitignored. Ad-hoc probes belong in
  the session scratchpad, not the repo.
- Before drafting, **always ask** who receives it and whether it continues the thread or starts a
  new conversation (D-008). Show the `draft-preview` To/Cc/subject/OMITTED block first.
- Write bodies in **Markdown**, never hand-written HTML, and never hard-wrap. The signature is
  appended automatically from `signature.html`.
- Reads use `BODY.PEEK`; keep it that way.
- Red/green: write the failing test first. This session's negative tests corrected a wrong
  assumption about thread splitting before it reached live mail.

## Owner action outstanding

- The FIPDes Day thank-you draft to Barbara in Proton Drafts **still contains the literal
  `[FRIEND'S NAME]`**. The owner chose to edit it themselves in the Proton UI (2026-09-16). It is
  still sitting there — worth a reminder.
- The 7 `m2c roundtrip 91fcac` messages are still in both mailboxes; the owner chose to leave
  them and decide later. They are ready-made subjects for the Phase 5 browser screenshots.

## First commands

```bash
cd ~/Work/tools/mail2context
git log --oneline main..HEAD          # Phase 2 work on feat/send-roundtrip — ask what to do with it
just bridge-status && just accounts   # expect: up on 1143, then two OK lines
just check                            # 87 tests + lint + Proton loss audit, ~1 min
just roundtrip-verify 91fcac          # re-assert Phase 2 against the mail still in the mailboxes
```
