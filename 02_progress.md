# Progress

## In flight
- Phase 2 read layer — thread reconstruction landed; IMAP fetch still to write

## Next
- Authenticate over IMAP as `dj@ai4hu.org` and fetch a real thread
- Validate thread reconstruction against real Proton mail (the D-001 fallback trigger)
- Gmail app password → second account over the same code path

## Blocked
- **IMAP verification** — needs `PROTON_PASS` (the Bridge-generated password) in `.env`.
  Bridge is logged in and serving, but no client can authenticate until that value is set.
- **Gmail CLI access** — needs an app password. The claude.ai connector covers in-session
  Gmail work meanwhile, so this blocks only the CLI path.

## Done

| Date | Task | Verified by |
|---|---|---|
| 2026-09-16 | Thread reconstruction from headers (union-find) | 4 pytest tests green incl. missing-middle case; passes under `-p no:randomly` |
| 2026-09-16 | Add Ruff with the house ignore set | `uv run ruff check .` → All checks passed |
| 2026-09-16 | Rebuild venv with correct interpreter paths | `uv run pytest` spawns; shebang now points at this repo |
| 2026-09-16 | Proton Bridge login + IMAP serving | Bridge `list` shows `dani.jelinko` connected; IMAP greeting + STARTTLS on 1143 |
| 2026-09-16 | Drop `solvemail` + 19 Google-stack packages from deps | `uv remove solvemail`; `pyproject.toml` now lists only `fastcore`, `python-dotenv` |
| 2026-09-16 | Analyse solvemail feature-by-feature for reuse | `260916__solvemail_feature_analysis.md` |
| 2026-09-16 | Confirm Gmail reachable via claude.ai connector | Live `search_threads` returned real inbox threads |
| 2026-09-16 | Establish Bridge is installed but unconfigured | No `~/.config/protonmail/`; nothing on 1143/1025 |
