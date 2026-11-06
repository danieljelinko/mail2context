# Launch prompt — file attachments on drafts

Runs in mail2context. Launched 06/11/2026 from the lacsf67-site session, which needs a Proton draft with 25 screenshots attached.

---

You are working in mail2context (`~/Work/tools/mail2context`). Dani wants `just compose` and `just draft` to attach local files to the draft they create, and the `mail` skill to document it.

Read first, in this order: `01_plan.md`, `02_progress.md`, `03_decisions.md` (D-003 drafts only, D-008 ask recipients and threading, D-009/D-014/D-015 threading on APPEND, D-010 deterministic Markdown→HTML, D-016 attachment contents vs fidelity, D-017/D-021/D-022 mail-guard), `04_learnings.md`, then the skill `~/.claude/skills/mail/SKILL.md`. Run `just guard-status` and `just bridge-status` before any live step.

## Why

On 06/11/2026 Dani asked for a Proton draft to Colin (UD CSF 67) with 25 PNG screenshots (4.4 MB in total). `just compose sg@lacsf67.org "<subject>" body.md` created draft uid 215 without them: `compose` and `draft` have no way to attach a file. Dani now has to drag the 25 files in by hand in the Proton web UI.

The pieces exist: `scripts/m2c.py` `cmd_compose` / `cmd_draft` build an `EmailMessage` (`mail2context/compose.py` `build_message` / `build_reply`) and add it to Drafts with `append_draft`. `scripts/roundtrip.py` already calls `msg.add_attachment(...)`, and `mail2context/roundtrip.py` `check_attachment` checks the bytes by sha256, but only on the send path, never on a draft.

## Objective

1. **Library** (`mail2context/compose.py`): `build_message` and `build_reply` take the files to attach (a list of paths, required parameter or explicit empty list, per the style rules). Each file is added with its MIME type guessed from the extension (`mimetypes`, fallback `application/octet-stream`) and its basename as filename. The HTML/text body and the signature are unchanged. Missing or unreadable file: fail before anything is appended.
2. **CLI** (`scripts/m2c.py`): a repeatable `--attach PATH` on `compose` and `draft`. Also accept a directory and attach its files in sorted name order, because the real use is a numbered folder `01_….png` … `25_….png`. The preview and dry-run print each attachment's name and size, and the total.
3. **Recipes** (`justfile`), **mutating** where they append: for example `compose-attach TO SUBJECT BODY PATHS…` with its `-preview` twin, and the matching thing for `draft`, or another positional form that fits the existing recipes. Keep the existing recipes working unchanged.
4. **Live check, one per provider**: one test draft to `dj@ai4hu.org` with two attachments (one PNG, one text file with accents in its name). Fetch it back from Drafts and assert each filename and sha256 match. Write down how big a message Proton Bridge and Gmail accept on APPEND, or at least that ~5 MB goes through.
5. **Skill**: update `~/.claude/skills/mail/SKILL.md`, which is a git repo at `~/.claude/skills`. Cover the new recipes in the command table, a short "Attachments" section (what gets attached, size note, Proton result), and the "Known gaps" line. Commit there separately, with its own message.

## Decisions already made

- Still drafts only (D-003): nothing is sent, and the send path is not touched.
- Attaching is about files the owner names. Reading the contents of received attachments (D-016) stays out of scope.
- The skill keeps its rule of asking for recipients and threading before every draft (D-008).

## Constraints

- Branch `feat/draft-attachments`, created from `main` by the launcher. Leave `feat/header-read` (unmerged) alone.
- Red/green TDD with pytest (`uv run pytest`), tests in `tests/test_compose.py`, no live IMAP in unit tests. Lint with ruff if the repo uses it.
- Plain Python (D-004): do not add nbdev cells or a new `nbs/` folder.
- Live steps: only the test drafts to `dj@ai4hu.org` above. Give their uids to Dani. Delete them only when Dani says so (D-022: `just draft-delete UID account --dry-run`, then `--yes`).
- Ask Dani before merging into `main`; do not push.
- Update `02_progress.md`, and `03_decisions.md` / `04_learnings.md` if you decide or learn something non-obvious (e.g. an APPEND size limit, or how Proton stores draft attachments).

## Done when

- New tests fail first, then pass. The full suite passes: `just check`, or `uv run pytest` if the mailbox audit cannot run.
- `just compose-preview`-style dry runs list the attachments, with no network call.
- Each provider has one test draft with attachments, verified by filename and sha256 when read back. Dani has the uids, and either a screenshot of the Proton web view or confirmation from Dani that the attachments show there.
- The skill documents the feature and is committed in `~/.claude/skills`.
- Report to Dani: the recipe to use for the real case, i.e. a new draft to `sg@lacsf67.org` with `/home/helinko/Work/lab/lacsf67-site/scratch/mail_etat_du_site/` attached. That draft is created back in the lacsf67-site session, not here, and replaces draft uid 215.
