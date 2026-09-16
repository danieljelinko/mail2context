# Progress

## In flight
- Owner's manual verification of exported threads against the ProtonMail UI (`verify/`)

## Next
- Confirm a drafted reply appears correctly threaded in the Proton UI (`just draft`, untested live)
- Attachment *contents* (currently only filenames surface)
- Gmail app password → validate threading and stripping on a second provider
- systemd user unit so Bridge survives closing the terminal

## Blocked
- **Gmail CLI access** — needs an app password. The claude.ai connector covers in-session
  Gmail work meanwhile, so this blocks only the CLI path and the cross-provider validation.
- **Bridge survives only as long as its terminal.** Running interactively via `--cli`; closing
  that window kills IMAP. Needs the systemd user unit (offered, not yet installed).

## Done

| Date | Task | Verified by |
|---|---|---|
| 2026-09-16 | IMAP SEARCH + flag awareness | 13 tests; live: 55 unread found, `--from barbara` returns whole 14-msg thread with matching key |
| 2026-09-16 | `just` entry points + README | `just --list` shows 14 documented recipes |
| 2026-09-16 | Zero-loss conversion audit | `just audit` → 0 losses across all 898 messages; found+fixed 489 URLs, 105 alts, 42 attachments |
| 2026-09-16 | Thread → markdown renderer + export | `verify/*.md`: 14/14 messages present in both raw and stripped |
| 2026-09-16 | Reply composition with correct threading headers | 2 tests; live draft still unverified |
| 2026-09-16 | Body extraction + quote stripping | 9 tests green; on 400 real msgs 41% of chars removed, residual quotes 1/400 |
| 2026-09-16 | Validate threading on real Proton mail | 400 msgs → 262 threads, 105 multi-message, 0 mis-ordered in UTC; D-006 |
| 2026-09-16 | Authenticate to Bridge IMAP as `dj@ai4hu.org` | LOGIN OK; 84 in INBOX; labels listed as `Labels/*` |
| 2026-09-16 | Thread reconstruction from headers (union-find) | 4 pytest tests green incl. missing-middle case; passes under `-p no:randomly` |
| 2026-09-16 | Add Ruff with the house ignore set | `uv run ruff check .` → All checks passed |
| 2026-09-16 | Rebuild venv with correct interpreter paths | `uv run pytest` spawns; shebang now points at this repo |
| 2026-09-16 | Proton Bridge login + IMAP serving | Bridge `list` shows `dani.jelinko` connected; IMAP greeting + STARTTLS on 1143 |
| 2026-09-16 | Drop `solvemail` + 19 Google-stack packages from deps | `uv remove solvemail`; `pyproject.toml` now lists only `fastcore`, `python-dotenv` |
| 2026-09-16 | Analyse solvemail feature-by-feature for reuse | `260916__solvemail_feature_analysis.md` |
| 2026-09-16 | Confirm Gmail reachable via claude.ai connector | Live `search_threads` returned real inbox threads |
| 2026-09-16 | Establish Bridge is installed but unconfigured | No `~/.config/protonmail/`; nothing on 1143/1025 |
