# Handoff — mail-guard (three enforcement levels) + scheduled send study

Orientation for a fresh agent. Written 2026-09-17 at the end of the Phase 3 session of
`mail2context`. **Points at the living docs rather than repeating them — read those too.**
Supersedes `260916_1816__handoff_phase3_content.md` for orientation; that file stays as the
Phase 3 record.

## What exists

`~/Work/tools/mail2context`: a CLI that turns two mailboxes into LLM context and composes
replies. Proton `dj@ai4hu.org` (via local Proton Mail Bridge, IMAP 127.0.0.1:1143 / SMTP 1025)
and Gmail `daniel.jelinko@gmail.com` (imap.gmail.com:993 / smtp.gmail.com:587, app password).
Everything runs through `just`. The `mail` skill at `~/.claude/skills/mail/SKILL.md` is current.

Read, in order: `01_plan.md`, `02_progress.md`, `03_decisions.md` (D-003, D-011, D-016, D-017
matter most), `04_learnings.md` (44 hazards), `README.md`.

## State at handoff

- `main` is at `a3bf25a`, pushed. Branch `feat/content-roundtrip` carries four more commits
  (D-016, Spam search + resume, extract_text-based check, this handoff). **Ask the owner** what
  to do with it — merge / push / PR is a fresh decision every session, never assumed.
- `just check`: 107 tests, lint clean, 0 loss across 900 Proton messages.
- **Phase 3 content round-trip passed on both providers** (run `318ecf`): 0 loss, blue `4`
  intact, no monospace body, attachment bytes equal. Three findings, all in `04_learnings.md`:
  Gmail filed the rich message as **spam**; Proton **regenerates** the plain part on send and
  **drops** it on receipt (so the plain part is never ours through Proton).
- **Phase 3 still open, owner at a browser:** un-spam and reply from Gmail's web UI to the
  copy in Gmail, reply from Proton's web UI to the copy in Proton, then `just content-quotes
  318ecf`; and screenshots of both rendered copies. Nothing else in Phase 3 is pending.
- Phases 4, 5, 6 of `01_plan.md` are untouched. **The send capability is LIVE** under D-011
  (`mail2context/send.py`, `roundtrip.py`, `scripts/roundtrip.py`, the `roundtrip*` and
  `content*` recipes, all marked TEMPORARY).

## Your objective A — build `mail-guard`, a separate repo

The owner asked for enforcement that the agent **cannot edit or lift**, in three levels, that
`mail2context` works **with and without** (D-017). Create `~/Work/tools/mail-guard`. It is a
separate repo so a mail2context session cannot touch the guard's code, unit or rules.

| Level | Read, search, threads | APPEND to Drafts only | STORE, MOVE, COPY, EXPUNGE, DELETE, CREATE, RENAME | SMTP |
|---|---|---|---|---|
| 1 | yes | yes | refused by the proxy | blocked by nftables |
| 2 | yes | yes | forwarded | blocked by nftables |
| 3 | yes | yes | forwarded | open |

Why this shape, established 2026-09-17 with the owner:

- **Code in the repo is a convention, not a guard.** The agent can edit `send.py`, the justfile
  and the skill, and can write a fresh `smtplib` script. Enforcement must remove the
  *capability* at a layer the agent has no write access to.
- **Levels 2/3 are a firewall switch.** Root-owned nftables rules drop outbound TCP to
  `127.0.0.1:1025` and to 25/465/587 for uid 1000, exempting the guard's own uid. The owner's
  mail clients are the Proton and Gmail web UIs (HTTPS), and Bridge talks to Proton over 443,
  so nothing the owner uses is affected.
- **Level 1 needs a filtering IMAP proxy.** Move/delete share the IMAP port and password with
  read and draft; no firewall or credential scope separates them (Gmail has no OAuth scope
  giving drafts without send; Bridge has no per-command permissions). The proxy runs as its own
  system user (`mailguard`), holds the **real** passwords in a root-owned file, listens on two
  loopback ports (one per account) in **plaintext**, and forwards to Bridge (STARTTLS) and
  Gmail (TLS). It inspects each tagged command verb and, for `APPEND`, the target folder;
  literals (`{n}` / `{n+}` continuations, which `APPEND` uses) and `IDLE`/`DONE` are passed
  through raw once the verb is approved. Refusals are a tagged `NO guard: level 1 forbids MOVE`.
- **`APPEND` outside Drafts is refused at every level** — appending into INBOX is how a message
  gets forged into a mailbox.
- **The switch is `sudo mail-guard 1|2|3`**, writing a root-owned, world-readable level file
  and applying both the proxy mode and the nft rules. `3` should take a duration and re-arm
  itself by systemd timer so send is never left open — the D-011 lesson made mechanical.
- **nftables also blocks uid 1000 from 1143, 993, 1025, 465, 587 directly**, so the agent cannot
  bypass the proxy even if it finds a password. Bridge listens as uid 1000 but only the proxy
  (uid `mailguard`) connects to it; `meta skuid` matches the connecting process.
- The agent has **no passwordless sudo** (verified) — that is what makes root-owned files and
  rules out of its reach. `nft`, `iptables`, `ufw` are installed. No Claude Code
  managed-settings file exists; hooks are pattern-based and bypassable, so they are belt, not
  braces. `chattr +i` on the skill file is a cheap second layer, not a guard.

**mail2context must work in both modes.** Add to `mailbox.py`'s `connect` a plaintext-loopback
option (the proxy does no STARTTLS), driven by `.env`: e.g. `PROTON_IMAP_HOST=127.0.0.1
PROTON_IMAP_PORT=2143 PROTON_IMAP_TLS=none` when the guard is on, the current values when it is
off. Nothing else in mail2context should know the guard exists. Add `just guard-status` that
reads the level file if present, else prints "guard not installed — direct mode"; make it the
first line of the `mail` skill's checks. Both modes are tested: `just check` in direct mode,
and the live checks below through the proxy.

**Tests that must exist before this is called done:**

- Unit tests of the verb filter and the literal passthrough against a fake IMAP server
  (an `asyncio` echo server is enough; do not mock the proxy's own code).
- Live at level 1: `just threads`, `just draft-preview`, `just draft` succeed through the proxy;
  `move_message` returns the guard's `NO`; a direct `imaplib` connect to 1143 and 993 from the
  agent's shell fails; `python -c "import socket; socket.create_connection(('smtp.gmail.com',
  587), 4)"` fails; `just content-preview` still works (it sends nothing).
- Level 2: `move_message` succeeds; SMTP still fails. Level 3: `just content-send` works.
- A negative test that the proxy refuses `APPEND` to INBOX at level 3.

**Open decisions to put to the owner, early:**

- Level 1 as drawn also refuses `STORE`, which is how `\Answered` is set and how a message is
  marked read. Phase 4's flag checks need level 2, or a narrow exception allowing `STORE
  +FLAGS` for `\Answered` and `\Flagged` only. Ask.
- The claude.ai **Gmail connector** (D-005) reaches Gmail through Google's API with its own
  OAuth grant and can send and trash mail today. The guard cannot see it. Level 1 is only
  honest if that connector is disconnected or scoped down in claude.ai settings. Say so.
- Whether Phase 6 (delete the send code) still stands once the guard exists. It interacts with
  objective B — see below. A decision row is needed either way.

## Your objective B — study scheduled send ("in 5 minutes", "tomorrow morning")

Not implemented anywhere. Study first, then implement only what the owner chooses. Facts:

- Neither provider exposes schedule-send outside its web UI: Gmail's REST API has no
  scheduled send; Proton has no API at all. So a scheduled send is either (a) **the owner
  using the web UI's own "schedule send"** on a draft the tool created — zero code, keeps
  D-003 intact, Proton's needs a paid plan (the owner has one, Bridge requires it); or (b) a
  **local scheduler** that sends at time T through SMTP — which means a send capability must
  exist at time T, contradicting Phase 6.
- If (b): the natural home is the guard, not mail2context. `just schedule KEY body.md "tomorrow
  09:00"` writes a queued message under a spool the agent can write but not send from; a
  guard-side sender (uid `mailguard`, holding the SMTP credentials) fires it at T **only if the
  owner approved that queue entry** (`sudo mail-guard approve ID`), and only if the level at T
  permits. That keeps a human decision per message while allowing the delay. The D-008
  questions (who receives, same thread or new) apply before queueing.
- Time parsing: `systemd-run --on-calendar` / `--on-active` handles "in 5 minutes" and
  "tomorrow 09:00" natively and survives reboots when persistent; `dateparser` handles free
  text. Print normalised local time AND UTC back to the owner before queueing — the mailbox
  already mixes +0000 and +0200.
- Present (a) and (b) with costs, recommend one, and record the owner's choice as a decision
  row. If (b) is chosen, Phase 6 is rewritten: the send path is not deleted but confined to the
  guard at level 3 / approved queue, with the allowlist lifted only by the owner's approval.

## Traps carried forward (the rest are in `04_learnings.md`)

- `imaplib` quotes nothing — not mailbox names, not multi-word SEARCH terms. Your proxy will see
  exactly what `imaplib` sends, quoted or not.
- A listening port is not evidence; Bridge binds 1143 ~5 s before login works. Poll `just
  bridge-status`, which logs in. Your proxy needs the same discipline: health-check by LOGIN.
- `[Gmail]/All Mail` and Proton's `All Mail` **exclude Spam**. A "never arrived" verdict must
  search Spam first.
- Proton stores only the HTML part; `extract_text` always takes the HTML path there. Do not
  write a test that expects a plain part on a Proton-stored message.
- Never assert `References` equals what was sent (Proton appends `@protonmail.internalid`).
- Gmail full-body fetches take minutes; background them, never two at once.
- `just` arguments are positional; `just --list` prints defaults, not syntax.
- Header-level verification is not verification; ask for a screenshot for anything a human reads.

## Rules

- **Never send** outside the D-011 allowlist; D-011 stays temporary until a decision replaces it.
- **Never commit mailbox content** — exports go to `verify/` (gitignored); probes to the session
  scratchpad. The guard repo must never hold a real password in git: root-owned file outside it.
- Before drafting or sending: ask who receives it and whether it continues a thread (D-008).
- Red/green TDD, one failing test at a time. Tests use a real fake server, not mocks of your own
  code. Ruff with the house ignore set. UV only.
- Work on a topic branch; ask before merging, pushing or opening a PR.

## Owner actions outstanding

- Phase 3 browser steps above (Gmail un-spam + reply, Proton reply, two screenshots).
- The FIPDes Day thank-you draft to Barbara in Proton Drafts still has `[FRIEND'S NAME]`; the
  owner said they would fix it in the Proton UI. Leave it.
- The 7 `m2c roundtrip 91fcac` and 2 `m2c content 318ecf` messages stay in both mailboxes on
  purpose: Phase 5 screenshot subjects. Do not bin them without asking.
- Installing the guard needs the owner's sudo password, once; each level change too.

## First commands

```bash
cd ~/Work/tools/mail2context
git log --oneline main..HEAD          # unmerged Phase 3 tail — ask what to do with it
just bridge-status && just accounts   # expect: up on 1143, then two OK lines
just check                            # 107 tests + lint + Proton audit, ~1 min
sudo -n true; echo $?                 # expect 1: the agent has no passwordless sudo — that is the point
ss -ltn '( sport = :1025 or sport = :1143 )'   # Bridge's two loopback ports
```
