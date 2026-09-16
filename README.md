# mail2context

Turns mailboxes into LLM-readable context, and composes replies as **drafts only**.
Two accounts over one code path: **Proton** (business, via local Proton Mail Bridge) and
**Gmail** (personal, via an app password).

`just` is the entry point for both humans and agents — run `just` to list every command.

## Why IMAP for both

Proton has no API; Bridge exposes the mailbox only over IMAP/SMTP on localhost. Gmail offers
both, so IMAP serves both accounts uniformly and needs no Google Cloud project. The cost is that
**IMAP has no thread concept** — Bridge advertises no `THREAD` or `SORT` extension and exposes no
conversation id — so threads are rebuilt here from `Message-ID` / `In-Reply-To` / `References`.
See `03_decisions.md` (D-001) for the fallback if that ever stops holding.

## Setup

### 1. Proton Mail Bridge (paid Proton plan required)

```bash
/usr/lib/protonmail/bridge/bridge --cli     # NOT /usr/bin/protonmail-bridge — that opens the GUI
>>> login                                    # address, password, 2FA
>>> info                                     # copy the GENERATED password, not your account one
```

Bridge must be running for any Proton command to work — it *is* the IMAP server.
`just bridge-status` says whether it is up.

### 2. Credentials

```bash
cp .env.example .env    # then fill PROTON_PASS and GMAIL_PASS
```

`PROTON_PASS` is Bridge's generated password. `GMAIL_PASS` is a 16-character app password from
myaccount.google.com → Security → App passwords (needs 2-Step Verification). `.env` is gitignored.

```bash
just accounts           # confirms both authenticate
```

## Commands

| Command | Does |
|---|---|
| `just accounts` | check which accounts authenticate |
| `just folders [account]` | list mailboxes |
| `just threads [account] [limit] [show]` | list rebuilt threads, newest first; each row starts with a **thread key** |
| `just unread [account]` | unread threads in the inbox |
| `just from SENDER` | threads involving a sender |
| `just about TERM` | threads mentioning a term, headers or body |
| `just needs-reply [since]` | threads whose last message is not yours |
| `just search --from X --since 2026-07-01 --unread` | any combination of IMAP filters |
| `just thread KEY` | print that thread as markdown (quotes stripped) |
| `just thread-raw KEY` | same, quoted originals kept — use when comparing against the mail UI |
| `just export KEY` | write the thread to a markdown file |
| `just draft-preview KEY body.md` | show the reply that would be drafted, write nothing |
| `just draft KEY body.md` | append the reply to **Drafts** — never sends |
| `just draft-all KEY body.md` | same, but Cc everyone else in the thread |
| `just audit [account] [limit]` | measure conversion loss; exits non-zero if anything is lost |
| `just check` | tests + lint + full-mailbox loss audit |

**`just` arguments are positional.** `just --list` prints signatures like
`draft key body account="proton"` — those `name="value"` parts are *defaults*, not syntax to
type. Write `just draft 9cb987c4 reply.md`, optionally `just draft 9cb987c4 reply.md gmail 900`.

Reads use `BODY.PEEK`, so nothing is ever marked as read. The only writes are `just draft` and
`just draft-all`.

A reply goes to the **last sender** only. Any other participants are listed as `OMITTED` in the
preview — check that line before drafting, and use `draft-all` to copy them in.

Search runs server-side (IMAP `SEARCH`), then the matches are unioned with the recent window
before grouping, so you get **whole** threads keyed the same way `just threads` keys them — not
the partial thread that grouping only the matches would produce. A match older than the window
still appears, just with less surrounding context; raise `--limit` to widen it.

Thread rows carry status markers: unread count, `awaiting you` when the last message is not
yours, and `answered` when any message in the thread is flagged `\Answered`.

A **thread key** is derived from the thread's earliest `Message-ID`, so it is stable as replies
arrive. It is not stable if you change `--limit` so much that an older root enters the window.

## Verifying nothing is lost

Threads are reconstructed locally and HTML is converted to text, so both steps could silently drop
content. Three defences:

1. **`just audit`** compares every long text run in the source HTML against the rendered output,
   whitespace-insensitively, and separately checks link targets, image alt text and attachment
   names. Currently **0 losses across all 898 messages**. It exits non-zero on any loss, so it
   works in CI.
2. **Thread invariants** in the test suite: every message lands in exactly one thread, and the
   partition is identical regardless of input order.
3. **Manual comparison** — `just export KEY` and `just thread-raw KEY` produce files to read beside
   the ProtonMail UI. Exports land in `verify/`, which is gitignored: **never commit mailbox
   content.**

What the audit deliberately does *not* police is quote stripping, which removes content on
purpose (~41% of characters). Use `--raw` / `just thread-raw` to see everything.

## Layout

```
mail2context/
  thread.py    rebuild threads from headers (union-find over Message-ID/In-Reply-To/References)
  render.py    body extraction, quote + signature stripping, thread → markdown
  compose.py   build replies with correct In-Reply-To / References
  mailbox.py   IMAP connection, fetch, APPEND to Drafts
  audit.py     conversion-loss measurement
scripts/m2c.py the CLI behind every just recipe
```

Living documentation is in `01_plan.md`, `02_progress.md`, `03_decisions.md`, `04_learnings.md` —
read those before changing behaviour; they record why things are the way they are.
