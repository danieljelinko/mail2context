# Launch prompt — next session (Phase 3)

Paste everything below the line into a fresh Claude Code session started in
`~/Work/tools/mail2context`.

---

You are taking over the mail2context project at ~/Work/tools/mail2context.

Start by reading, in this order:
  - 260916_1816__handoff_phase3_content.md  (orientation, traps, first commands)
  - 01_plan.md        (your objective: Phases 0, 1 and 2 are DONE, you start at Phase 3)
  - 02_progress.md    (where things stand)
  - 03_decisions.md   (D-001..D-015 — D-003, D-011 and D-015 matter most)
  - 04_learnings.md   (40 hazards that already cost debugging time)

Then invoke the `mail` skill before doing any mail work.

Objective: Phase 3 of the round-trip plan — content fidelity. Send a message exercising every
Markdown feature plus accents and the signature, fetch the delivered copy from the other provider,
and assert `just audit` reports 0 loss, the blue `4` (rgb(59, 131, 194)) survives, and no body is
monospace. Then verify quote stripping against REAL quote blocks, and round-trip an attachment.

Phase 2 built the send path, so the plumbing exists — but the existing runner
(`scripts/roundtrip.py`) is threading-specific. Phase 3 needs a single rich-content message, not
a 6-message chain. Decide whether to extend that runner or add a sibling, and tell me which.

Two Phase 3 items are gated on me at a browser, and nothing else in Phase 3 depends on them, so
ASK ME EARLY and do the rest while you wait:
  - reply to something from GMAIL's web UI so a real `gmail_quote` block is generated
  - the same from PROTON's web UI for `protonmail_quote`
Quote stripping has so far only ever been tested against fixtures and observed mail. Also ask me
for a screenshot of the delivered rich-content message — "no body is monospace" and "the blue 4
survived" are not decidable from headers.

One Phase 3 item may need new code, not just verification: the plan asks that attachment
filenames surface AND bytes match, but attachment CONTENTS are still not extracted, only
filenames. Tell me if you think that belongs in Phase 3 or should be split out.

Before you start:
  - The Phase 2 work is on branch `feat/send-roundtrip`, 5 commits ahead of main, unmerged and
    unpushed. Run `git log --oneline main..HEAD` to see it, then ask me whether to merge, push,
    or open a PR. Do not assume. (Last session I chose merge-to-main-then-branch; do not treat
    that as a standing answer.)

Critical constraints:
  - THE SEND CAPABILITY IS LIVE. D-011 authorises sending ONLY to dj@ai4hu.org and
    daniel.jelinko@gmail.com, TEMPORARILY, via the hard allowlist in mail2context/send.py.
    Never widen it — a new address is a new owner decision, not a code edit. `check_recipients()`
    is wired into the send path and refuses before any connection opens; print what it returns
    before anything leaves the machine. `just roundtrip-preview` shows this without sending.
  - Phase 6 REMOVES the send capability entirely and restores drafts-only (D-003): send.py,
    roundtrip.py, scripts/roundtrip.py and the five `roundtrip*` just recipes all carry TEMPORARY
    in their docstrings. That is part of the work, not later cleanup.
  - Never commit mailbox content. Exports go to verify/, which is gitignored; ad-hoc probes belong
    in the session scratchpad, not the repo.
  - Before drafting or sending anything, ask me who receives it and whether it continues a thread
    or starts a new conversation (D-008).
  - Header-level verification is not verification. For anything a human reads, inspect the render
    or ask me for a screenshot. This bites hardest in Phase 3 — it is the whole phase.
  - Red/green TDD: write the failing test first. Last session a negative test corrected a wrong
    assumption about thread splitting before it ever reached live mail.

Confirm the baseline before starting: `just bridge-status && just accounts` (expect "up on 1143"
then two OK lines), then `just check` (expect 87 tests, lint clean, 0 loss across 900 Proton
messages). Bridge runs as a systemd user unit; if it is down, try
`systemctl --user start protonmail-bridge` yourself and poll `just bridge-status` until it exits 0
— the port listens ~5s before login works. You can also re-assert Phase 2 end to end with
`just roundtrip-verify 91fcac`, which is a good smoke test that send and fetch still work.

Phase 3 traps worth knowing before you write the audit assertions:
  - The audit measures `html_to_text(html)` against that same HTML (D-012). Do not compare against
    `extract_text()`, which returns the PLAIN part when one exists — that produced 26,967 phantom
    losses once already.
  - Never assert `References` equals what you sent: Proton appends its own
    `@protonmail.internalid` to every stored message. Assert containment (D-015).
  - Any BeautifulSoup rewrite pass must run innermost-first (D-013).
  - `imaplib` quotes nothing — not mailbox names, not multi-word SEARCH terms.
  - Gmail fetches are minutes, not seconds; background them and never run two at once.

Known open items: the FIPDes Day thank-you draft to Barbara in Proton Drafts still contains the
literal [FRIEND'S NAME]; I said I would fix it myself in the Proton UI, so leave it alone. The 7
`m2c roundtrip 91fcac` messages are still in both mailboxes on purpose — they are the ready-made
subjects for Phase 5's browser screenshots, so do not bin them without asking.
