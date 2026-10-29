# Launch prompt — `draft-list` + `draft-delete`

Start a fresh Claude Code session in `~/Work/tools/mail2context` (or a worktree of it on
`feat/draft-delete`) with everything below the line as its first prompt.

---

You are working in mail2context (~/Work/tools/mail2context). The owner, Dani, wants to be able to
delete a draft that an agent created, without opening the Proton or Gmail UI.

Read first, in this order: `01_plan.md`, `02_progress.md`, `03_decisions.md` (D-003, D-009,
D-017, D-021 matter most), `04_learnings.md`. Then invoke the `mail` skill. Run
`just guard-status` and `just bridge-status` before any mail command.

## Why

On 29/10/2026 an agent created several Proton reply drafts with `just draft`; one became stale
(wrong meeting days) and had to be deleted by hand in the Proton UI, because mail2context can only
create drafts. Each `just draft` prints `APPENDUID <uidvalidity> <uid>`, e.g.
`OK [APPENDUID 114340474 197]`. That pair identifies a draft exactly.

## Objective

Add two recipes, test-first (red/green, pytest, real data over mocks; the IMAP server is the
external boundary):

1. `just draft-list [account]` — **read-only.** Lists the Drafts folder: UID, date (Paris time),
   To, Subject, first line of the body. Gives the owner and agents the UID to act on.
2. `just draft-delete UID [account]` — **mutating.** Deletes exactly one message from the Drafts
   folder. Behaviour:
   - Works **only** on the Drafts folder (`Drafts` on Proton, `[Gmail]/Drafts` on Gmail). It
     never selects or touches another folder. Refuse any other folder by construction, not by flag.
   - Requires the UID; no subject or fuzzy matching. Refuse if the UID is not in Drafts or if the
     message lacks the `\Draft` flag.
   - Prints the same summary as `draft-list` for that UID and asks for confirmation; `--yes` skips
     the prompt for scripted use. A `--dry-run` shows what would be deleted.
   - Deletes with `UID STORE +FLAGS (\Deleted)` then `UID EXPUNGE <uid>` (UIDPLUS) so only that
     message is expunged, never a bare `EXPUNGE` that could take other flagged messages with it.
     Verify what Proton Bridge actually does (moves to Trash? permanent?) and what Gmail does,
     and record it in `04_learnings.md`.
   - Under mail-guard level 1, STORE \Deleted / EXPUNGE are refused (`NO guard: level 1 forbids
     …`). Report that clearly: the owner must raise the level. Never work around the guard.
3. Have `just draft` print the UID in a line agents can reuse (`draft uid: 197`), so a draft can
   be listed or deleted later without searching.

## Constraints

- D-003 stands: nothing sends. This change only removes drafts.
- Decide whether this needs a new decision row (it widens what the tool mutates): if so, add
  D-0NN to `03_decisions.md`.
- Update the `mail` skill (`~/.claude/skills/mail/SKILL.md`): commands table, the guard-level table
  if relevant, and the rule that an agent deletes a draft only when the owner asks, after showing
  the `draft-list` row.
- Do not test destructive paths against the owner's real drafts. For a live check, create a
  throwaway draft with `just compose dj@ai4hu.org "test draft-delete" body.md`, then delete it by
  its UID, on Proton and on Gmail.
- Work on branch `feat/draft-delete`; one logical change per commit; `just check` green before
  each commit; do not push without asking.

## Done when

- Tests cover: refusal outside Drafts, refusal of an unknown UID, refusal of a non-`\Draft`
  message, dry-run writes nothing, a real delete removes exactly one message.
- Live round-trip done on both providers with a throwaway draft, results in `02_progress.md`.
- Skill and L4 docs updated. Report to Dani what changed and what Proton does with a deleted draft.
