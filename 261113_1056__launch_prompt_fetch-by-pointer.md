# Launch prompt: mail2context fetch by pointer and special-use Drafts

Runs in `~/Work/tools/mail2context` on `feat/fetch-by-pointer`. com-desk needs to fetch one message's body from an index pointer and to attach a draft to a message, not to a thread key. Runs in parallel with other sessions; touches this repo only.

---

You are working in `mail2context` (`~/Work/tools/mail2context`). Dani wants two small additions so the planned `com-desk` can fetch bodies and create reply drafts **by message**, without rebuilding threads from the last N messages.

Read first, in this order:

1. `README.md`, `01_plan.md`, `02_progress.md`, `03_decisions.md` (all; D-003, D-008, D-009, D-014, D-017…D-023 matter most), `04_learnings.md`, the `justfile`, `scripts/m2c.py`, `mail2context/mailbox.py`, `compose.py`, `drafts.py`, `thread.py`.
2. Invoke the `mail` skill and run `just guard-status` and `just accounts` before acting (expect: guard not installed, direct mode).
3. The caller's needs: `~/Work/com-tools/com-desk/01_plan.md` ("Before S1", S2) and `03_decisions.md` D-009; review `~/Work/com-tools/com-desk/261113_0724__review_plan_architecture.md` findings B4, M8, m2, m3.

## Why

- com-index stores, per mail, `pointer = imap://<acct>/<folder>;UIDVALIDITY=<v>/;UID=<uid>` and the Message-ID. mail2context has no function that fetches by either: `just thread KEY` reloads the last `--limit` messages and matches a key prefix (`scripts/m2c.py:52-66`), and the key (`sha1` of the earliest Message-ID in the window) changes with the window.
- `draft` and `compose` use a hardcoded folder dict (`DRAFTS = {'proton': 'Drafts', 'gmail': '[Gmail]/Drafts'}`, `scripts/m2c.py:27`), while `drafts.find_drafts_folder` (special-use detection) is used only by `draft-list` and `draft-delete`.
- Ruled 2026-11-13 (com-desk D-009): a draft refers to a message pointer, never a thread key.

## Objective

1. **First, bring in the headers-only read:** `git merge feat/header-read` into this branch (it is 1 commit ahead of `main`, 4 behind: `fetch_headers`, `read_folder_state`). Resolve conflicts, `just check` green, before anything else.
2. **Fetch by pointer** (read-only): a function in `mailbox.py` that returns one message given `(account, folder, uidvalidity, uid)`, opened read-only with PEEK as the existing reads do. If UIDVALIDITY differs or the UID is gone, fall back to a `HEADER Message-ID` search in that folder, then in All Mail, and say which path answered. A function for several pointers in one connection. Recipe: `just message ACCOUNT --pointer 'imap://…'` and `--message-id '<…>'`, Markdown by default, `--json`, `--raw`.
3. **Thread around a message** (read-only): given a Message-ID, return the messages of its thread found by References / In-Reply-To search on the server (Gmail: `X-GM-THRID` if available), not by a recent-messages window. Recipe: `just thread-of ACCOUNT --message-id '<…>'`. Say plainly where Proton's search can't follow the chain.
4. **Draft a reply to a message** (mutating, Drafts only): `just draft-to ACCOUNT --message-id '<…>' body.md` builds the reply with `compose.build_reply` from the fetched message and appends it. Keep D-008: recipients and threading are shown and confirmed before the append, with the existing `--preview` pattern. The existing `draft KEY` stays.
5. **Special-use Drafts everywhere:** `draft`, `draft-to`, `compose*` use `drafts.find_drafts_folder`; `--drafts` still overrides; the hardcoded dict goes. It must refuse to guess, as today.

## Decisions already made

- Drafts only; no send (D-003, D-021). Don't touch `send.py` or the roundtrip recipes.
- Reads never change flags (`readonly=True`, PEEK).
- Proton strips `In-Reply-To` on draft APPEND (D-009, D-015): a known limit, not yours to fix. State it in `draft-to`'s output for Proton.
- All IMAP stays in this repo (workspace D-017 bis).

## Constraints

- Branch `feat/fetch-by-pointer`. Red/green TDD with pytest against the repo's existing fakes; `just check` green.
- **Live checks:** read-only recipes may run against the real mailboxes. A live `draft-to` only on a message Dani names, with `--preview` first; delete the test draft afterwards with `draft-delete` and say so. Nothing is sent, moved, flagged or deleted otherwise. Never print mail content of third parties into committed files.
- com-index imports this repo as an editable path dependency, and a session is working there in parallel: keep `fetch_headers` and `read_folder_state` signatures as they are on `feat/header-read`.
- Don't modify other repos. Don't install or change mail-guard. Commits local; ask Dani before pushing or merging to `main`.

## Done when

- Tests cover: pointer hit, stale UIDVALIDITY falling back to Message-ID, a message missing everywhere, several pointers in one call, special-use detection used by `draft`, refusal when no Drafts folder is flagged.
- Live, read-only: `just message` returns a message Dani names on Proton and on Gmail by pointer and by Message-ID; `just thread-of` returns its thread.
- README and the `mail` skill's recipe table list the new recipes with read-only / mutating flags (the skill lives in `~/.claude/skills/mail/`; ask Dani before editing it).
- `02_progress.md` Done row and next step; a decision row for anything you chose; learnings for any server quirk.
- You report to Dani in 5–10 lines: the recipes, what works per provider, the limits found, and whether `feat/header-read` merged cleanly.
