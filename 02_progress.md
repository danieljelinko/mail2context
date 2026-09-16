# Progress

## In flight
- Nothing. **Phases 0 and 1 are complete** — see `01_plan.md`. Next session starts Phase 2.

## Next
- **Phase 2 — the actual send path**, behind the D-011 guard that now exists
  (`mail2context/send.py`). Still nothing that can send: `grep -rniE "smtplib|sendmail|SMTP\("`
  over `mail2context/ scripts/ justfile` matches nothing, and that is the state to preserve
  until Phase 2 deliberately changes it.
  - `.env` has **no `GMAIL_SMTP_*` entries** — add them first. Proton's SMTP is Bridge on 1025.
  - Wire `check_recipients()` into the send path and print what it returns before sending.
- Attachment *contents* (currently only filenames surface)
- Consider whether `just check` should audit Gmail too — it is Proton-only because a 900-message
  Gmail fetch takes ~15 min against ~1 min for Bridge.

## Blocked
- **Phases 2-5 need the send capability built** under the D-011 allowlist. That is the next
  piece of work, not an external blocker.

## Owner action outstanding
- The FIPDes Day thank-you draft to Barbara in Proton Drafts still contains the literal
  `[FRIEND'S NAME]`. Owner chose to edit it in the Proton UI themselves (2026-09-16).

## Done

| Date | Task | Verified by |
|---|---|---|
| 2026-09-16 | Handoff + launch prompt for the Phase 2 session | `260916_1711__handoff_phase2_send.md`, `260916_1711__launch_prompt_phase2.md`; prior handoff moved to `archive/` |
| 2026-09-16 | D-011 send allowlist guard, written before any send code | 9 tests incl. mixed list, Bcc-hidden address, lookalike domain and empty-recipient message; `grep` confirms nothing can send |
| 2026-09-16 | Gmail parity (Phase 1) complete | `just audit gmail 900` → 0 losses, matching Proton; threads/unread/from all work on Gmail |
| 2026-09-16 | Fixed three real losses the Gmail corpus exposed | Gmail audit 26,967 → 697 → 42 → **0**; Proton unchanged at 0 across 900. D-012, D-013 |
| 2026-09-16 | Answered D-009 for Gmail: it preserves threading headers | Self-addressed root+reply in `[Gmail]/Drafts` returned `In-Reply-To`/`References`/`Message-ID` intact, regrouped as one thread of 2, then binned. D-014 |
| 2026-09-16 | `just bridge-status` rewritten to log in, not grep a port | It matched Ollama's `11434` and could never report DOWN; now verified reporting up **and** down with Ollama running |
| 2026-09-16 | Proton Bridge installed as a systemd user unit | `systemctl --user enable --now protonmail-bridge`; survives restart, reconnects from the vault in ~5 s with no 2FA prompt; linger already on |
| 2026-09-16 | Markdown→mail converter + real signature | 59 tests; drafts re-read from Proton show sans-serif body and the blue `4` intact |
| 2026-09-16 | Drafts render as HTML, bodies unwrapped | Re-read from Drafts: `text/html` with `<p>`/`<br>` markup; owner's screenshot drove the fix |
| 2026-09-16 | First live drafts written to Proton Drafts | `APPENDUID` returned; both read back from Drafts with correct To/Subject/body. Threading headers stripped by Proton — D-009 |
| 2026-09-16 | `compose` for new conversations + `--to`/`--all` control | 43 tests; live new-conversation draft to Barbara |
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
