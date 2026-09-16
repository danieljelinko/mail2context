# Launch prompt — next session (Phase 2)

Paste everything below the line into a fresh Claude Code session started in
`~/Work/tools/mail2context`.

---

You are taking over the mail2context project at ~/Work/tools/mail2context.

Start by reading, in this order:
  - 260916_1711__handoff_phase2_send.md  (orientation, traps, first commands)
  - 01_plan.md        (your objective: Phases 0 and 1 are DONE, you start at Phase 2)
  - 02_progress.md    (where things stand)
  - 03_decisions.md   (D-001..D-014 — D-003, D-011, D-013 and D-014 matter most)
  - 04_learnings.md   (36 hazards that already cost debugging time)

Then invoke the `mail` skill before doing any mail work.

Objective: Phase 2 of the round-trip plan. Send a known 6-message conversation alternating
Proton dj@ai4hu.org and Gmail daniel.jelinko@gmail.com, fetch it from both sides, and assert
group_threads rebuilds exactly ONE thread of exactly 6 in the order sent — the thread-completeness
check that was impossible before two mailboxes were available. Then assert In-Reply-To/References
survive an actual send (D-009 and D-014 are about DRAFTS; sent mail is untested), and deliberately
break the chain on one reply to confirm the tool splits the thread as documented.

Before you write any send code:
  - The previous session's work is on branch `fix/gmail-parity-audit`, unmerged and unpushed.
    Run `git log --oneline main..HEAD` to see it, then ask me whether to merge, push, or open a
    PR. Do not assume.
  - `.env` has no GMAIL_SMTP_* entries. Ask me for them. Proton's SMTP is Bridge on 127.0.0.1:1025
    and is already configured.

Critical constraints:
  - D-011 authorises sending ONLY to dj@ai4hu.org and daniel.jelinko@gmail.com, TEMPORARILY, via
    the hard allowlist already written and tested in mail2context/send.py. Never widen it — a new
    address is a new owner decision, not a code edit. Wire check_recipients() into the send path
    and print what it returns before anything leaves the machine.
  - Phase 6 REMOVES the send capability entirely and restores drafts-only (D-003). That is part of
    the work, not later cleanup.
  - Never commit mailbox content. Exports go to verify/, which is gitignored; ad-hoc probes belong
    in the session scratchpad, not the repo.
  - Before drafting anything, ask me who receives it and whether it continues a thread or starts a
    new conversation (D-008).
  - Header-level verification is not verification. For anything a human reads, inspect the render
    or ask me for a screenshot.
  - Red/green TDD: write the failing test first. Last session the send guard's own tests caught a
    real bug in the guard.

Confirm the baseline before starting: `just bridge-status && just accounts` (expect "up on 1143"
then two OK lines), then `just check` (expect 76 tests, lint clean, 0 loss across 900 Proton
messages). Bridge now runs as a systemd user unit; if it is down, try
`systemctl --user start protonmail-bridge` yourself and poll `just bridge-status` until it exits 0
— the port listens ~5s before login works.

Known open items: the FIPDes Day thank-you draft to Barbara in Proton Drafts still contains the
literal [FRIEND'S NAME]; I said I would fix it myself in the Proton UI, so leave it alone.
Attachment contents are still not extracted, only filenames.
