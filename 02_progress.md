# Progress

## In flight
- **Phase 3 — content fidelity round-trip**, run `318ecf`, branch `feat/content-roundtrip`
  (`main` was fast-forwarded to `a3bf25a` and pushed; later commits are on the branch).
  `just content-verify 318ecf` → **OK on both providers**: 0 audit loss, blue `4` intact, no
  monospace body, attachment bytes equal. Findings: Gmail filed the Proton copy as **spam**;
  Proton **regenerated** the plain part on send and **dropped** it on receipt (learnings).
  Still open, owner at a browser: reply from Gmail's web UI (after un-spamming) and from
  Proton's to the two copies → `just content-quotes 318ecf`; screenshots of both rendered copies.

## Next
- **Phase 3 — content fidelity round-trip.** The send path now exists, so Phase 3 needs no new
  plumbing: send a message exercising every Markdown feature, accents and the signature, then
  audit the delivered copy. The two items it cannot reach by header inspection are a **real**
  `gmail_quote` block (reply from Gmail's web UI) and a real `protonmail_quote` (Proton's UI) —
  both need the owner at a browser.
- **The send capability is now LIVE** and must be removed at Phase 6. `mail2context/send.py`,
  `mail2context/roundtrip.py`, `scripts/roundtrip.py` and the five `roundtrip*` just recipes are
  all marked TEMPORARY in their own docstrings. Run `just roundtrip-preview` to see the guard
  refuse-or-approve without sending.
- Attachment *contents* (currently only filenames surface)
- Consider whether `just check` should audit Gmail too — it is Proton-only because a 900-message
  Gmail fetch takes ~15 min against ~1 min for Bridge.

## Blocked
- Nothing. Phases 3-5 can proceed on the send path built in Phase 2; Phase 3's quote-block items
  need the owner to reply from each provider's web UI.

## Owner action outstanding
- The FIPDes Day thank-you draft to Barbara in Proton Drafts still contains the literal
  `[FRIEND'S NAME]`. Owner chose to edit it in the Proton UI themselves (2026-09-16).

## Done

| Date | Task | Verified by |
|---|---|---|
| 2026-09-16 | Phase 3 content round-trip `318ecf` passes both ways | `just content-verify 318ecf` OK: 0 loss, blue 4, proportional font, attachment sha256 equal on the Gmail and Proton copies. Gmail spam-filed it; Proton rewrote/dropped the plain part — three learnings rows |
| 2026-09-16 | Phase 3 checkers + runner, test-first; found and fixed the missing Markdown table rule | 104 tests (was 87); `check_content`/`check_attachment`/`check_quote_stripping` each fail on their own negative fixture; `just content-preview` dry-runs both directions with the guard's approval printed first |
| 2026-09-16 | **Phase 2 complete** — cross-provider threading round-trip | Run `91fcac`: 6 messages alternating Proton↔Gmail rebuild as **one thread of 6 in send order on both sides**, delivered `In-Reply-To`/`References` intact, `Auto:` collapsed back to `Re:` in transit, and a 7th reply with its headers removed splits 6+1 on both sides. D-015 |
| 2026-09-16 | SMTP send path + round-trip checkers, behind the D-011 guard | 87 tests (was 76); guard opens no connection on refusal; checker's negative tests prove it can fail. `just verify-roundtrip` runs the whole thing and exits non-zero on any problem |
| 2026-09-16 | Merged the Gmail-parity branch to `main` and pushed | `main` fast-forwarded to `a7ea2a8` and pushed to origin; Phase 2 work on `feat/send-roundtrip` |
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
