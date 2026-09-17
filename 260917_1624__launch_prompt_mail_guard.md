# Launch prompt — next session (mail-guard + scheduled send)

Paste everything below the line into a fresh Claude Code session started in
`~/Work/tools/mail2context`.

---

You are taking over from the Phase 3 session of mail2context at ~/Work/tools/mail2context.

Start by reading, in this order:
  - 260917_1624__handoff_mail_guard.md   (orientation, the two objectives, traps, first commands)
  - 01_plan.md        (Phases 0-3 of the round-trip are done or owner-gated; two new tracks)
  - 02_progress.md    (where things stand, what I still owe)
  - 03_decisions.md   (D-001..D-017 — D-003, D-011, D-016, D-017 matter most)
  - 04_learnings.md   (44 hazards that already cost debugging time)

Then invoke the `mail` skill before doing any mail work.

Objective A — build `mail-guard` as a SEPARATE repo at ~/Work/tools/mail-guard: an
enforcement layer the agent cannot edit or lift, with three levels the owner switches with sudo.
  1. read + draft only: the proxy refuses STORE/MOVE/COPY/EXPUNGE/DELETE/CREATE/RENAME, nftables
     blocks SMTP
  2. read + draft + move/delete: proxy forwards mutations, SMTP still blocked
  3. everything: SMTP open, ideally for a duration that re-arms itself
The mechanism is fixed in the handoff and D-017: root-owned nftables rules per uid, a filtering
IMAP proxy running as its own system user that holds the real passwords, a root-owned level
file and a `sudo mail-guard 1|2|3` switch. APPEND is allowed to Drafts only, at every level.
mail2context must keep working with the guard OFF (direct, as today) and ON (through the
proxy, plaintext loopback) — add the `.env`-driven connect option and `just guard-status`, and
test both modes. The tests the handoff lists are the definition of done; write them first.

Objective B — STUDY scheduled send ("in 5 minutes", "tomorrow 09:00"). Nothing exists. Neither
provider has an API for it, so the choice is between the owner using the web UI's own
schedule-send on a draft the tool made (no code, keeps D-003), and a local scheduler that must
retain a send capability at fire time (contradicts Phase 6). Present both with costs, recommend
one, ASK ME, then implement only what I choose and record it as a decision row. If a scheduler
is chosen it lives in the guard, fires only queue entries I approved with sudo, and rewrites
Phase 6 rather than ignoring it.

Ask me EARLY, all at once, because none of these block the build:
  - what to do with branch `feat/content-roundtrip` (4 commits ahead of main, unmerged): merge,
    push, or PR. Do not assume — last time I chose merge-and-push; that is not a standing answer.
  - whether level 1 may allow `STORE +FLAGS` for \Answered and \Flagged only (Phase 4 needs it)
  - that the claude.ai Gmail connector bypasses the guard entirely — I need to disconnect or
    scope it for level 1 to be honest; tell me plainly
  - my sudo password is needed once to install; tell me exactly what the install will do first
  - Phase 3 is still waiting on me at a browser: un-spam + reply from Gmail's web UI to
    `m2c content 318ecf`, reply from Proton's web UI to the other copy, then you run
    `just content-quotes 318ecf`; plus screenshots of both rendered copies. Remind me once.

Critical constraints:
  - THE SEND CAPABILITY IS LIVE under D-011, allowlisted to dj@ai4hu.org and
    daniel.jelinko@gmail.com only. Never widen it. `check_recipients()` refuses before any
    connection opens; `just content-preview` / `just roundtrip-preview` show it without sending.
  - The guard repo must never contain a real password; they move to a root-owned file outside git.
  - Never commit mailbox content. Exports go to verify/ (gitignored); probes to the scratchpad.
  - Before drafting or sending anything, ask me who receives it and whether it continues a
    thread (D-008).
  - You have no passwordless sudo. That is the property the guard relies on; do not work around
    it — anything needing root is a command you hand me to run.
  - Red/green TDD: failing test first, real fake server over mocks. Ruff, UV, topic branches.

Confirm the baseline: `just bridge-status && just accounts` (up on 1143, two OK lines), then
`just check` (107 tests, lint clean, 0 loss across 900 Proton messages). If Bridge is down,
`systemctl --user start protonmail-bridge` and poll `just bridge-status` until it exits 0.

Traps that will bite THIS work specifically:
  - `imaplib` quotes nothing; your proxy sees raw command lines, quoted or not, and APPEND
    arrives as a literal `{n}` continuation you must pass through as bytes, not parse.
  - A listening port is not evidence — health-check the proxy by LOGIN, like `bridge-status`.
  - All Mail excludes Spam on both providers; Gmail spam-filed the last rich message.
  - Proton stores only the HTML part of any message and rewrites the plain part on send.
  - Gmail fetches are minutes; background them, never two at once.
  - `just` arguments are positional.

Do not bin the `m2c roundtrip 91fcac` or `m2c content 318ecf` messages — Phase 5 needs them.
Leave the Barbara draft with `[FRIEND'S NAME]` alone; I will fix it in the Proton UI.
