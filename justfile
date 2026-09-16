# mail2context — entry points for mail operations.
# Every recipe is safe to run: reads are read-only (BODY.PEEK, never sets \Seen),
# and the only write is `draft`, which appends to Drafts and never sends (D-003).

_m2c := "uv run python scripts/m2c.py"

# Show all available commands
default:
    @just --list --unsorted

# --- connectivity -----------------------------------------------------------

# Check which accounts authenticate (proton, gmail)
accounts:
    @{{_m2c}} accounts

# List mailboxes on an account
folders account="proton":
    @{{_m2c}} folders --account {{account}}

# --- reading ----------------------------------------------------------------

# List reconstructed threads, newest activity first. Each row starts with the thread key.
threads account="proton" limit="400" show="25" folder="":
    @{{_m2c}} threads --account {{account}} --limit {{limit}} --show {{show}} {{ if folder == "" { "" } else { "--folder \"" + folder + "\"" } }}

# Search server-side, then show whole threads: --from --to --subject --text --since --before --unread --flagged --unanswered --needs-reply
search *args:
    @{{_m2c}} search {{args}}

# Unread threads in the inbox
unread account="proton" show="25":
    @{{_m2c}} search --unread --folder INBOX --account {{account}} --show {{show}}

# Threads involving a sender
from sender account="proton" limit="900" show="25":
    @{{_m2c}} search --from "{{sender}}" --account {{account}} --limit {{limit}} --show {{show}}

# Threads mentioning a term anywhere in headers or body
about term account="proton" limit="900" show="25":
    @{{_m2c}} search --text "{{term}}" --account {{account}} --limit {{limit}} --show {{show}}

# Threads whose last message is not yours, since a date
needs-reply since="" account="proton" limit="900" show="30":
    @{{_m2c}} search --needs-reply --account {{account}} --limit {{limit}} --show {{show}} {{ if since == "" { "" } else { "--since " + since } }}

# Print one thread as markdown. KEY is the short id from `just threads`.
thread key account="proton" limit="400" folder="":
    @{{_m2c}} thread {{key}} --account {{account}} --limit {{limit}} {{ if folder == "" { "" } else { "--folder \"" + folder + "\"" } }}

# Print one thread with quoted originals KEPT — use to compare against the mail UI
thread-raw key account="proton" limit="400" folder="":
    @{{_m2c}} thread {{key}} --raw --account {{account}} --limit {{limit}} {{ if folder == "" { "" } else { "--folder \"" + folder + "\"" } }}

# Write a thread to verify/ as markdown (quotes stripped — what the agent reads)
export key account="proton" limit="400" out="" folder="":
    @{{_m2c}} export {{key}} --account {{account}} --limit {{limit}} {{ if folder == "" { "" } else { "--folder \"" + folder + "\"" } }} {{ if out == "" { "" } else { "--out " + out } }}

# Write a thread to verify/ WITH quoted originals — the fair comparison against the ProtonMail UI
export-raw key account="proton" limit="400" out="" folder="":
    @{{_m2c}} export {{key}} --raw --account {{account}} --limit {{limit}} {{ if folder == "" { "" } else { "--folder \"" + folder + "\"" } }} {{ if out == "" { "" } else { "--out " + out } }}

# Export BOTH variants of a thread, for side-by-side verification
export-both key account="proton" limit="400": (export key account limit) (export-raw key account limit)

# --- writing (drafts only — nothing is ever sent) ---------------------------

# Preview a reply draft without writing it. Args are POSITIONAL: KEY then BODY file.
draft-preview key body account="proton" limit="400":
    @{{_m2c}} draft {{key}} --file {{body}} --account {{account}} --limit {{limit}} --dry-run

# Preview a reply-all draft (Cc everyone else in the thread)
draft-preview-all key body account="proton" limit="400":
    @{{_m2c}} draft {{key}} --file {{body}} --account {{account}} --limit {{limit}} --all --dry-run

# Create a reply-all draft in Drafts. Review and send from your mail client.
draft-all key body account="proton" limit="400":
    @{{_m2c}} draft {{key}} --file {{body}} --account {{account}} --limit {{limit}} --all

# Create a reply draft in Drafts. Args are POSITIONAL: KEY then BODY file. Never sends.
draft key body account="proton" limit="400":
    @{{_m2c}} draft {{key}} --file {{body}} --account {{account}} --limit {{limit}}

# --- verification -----------------------------------------------------------

# Convert a markdown body to the HTML that would be mailed (prints it)
md2html file:
    @{{_m2c}} md2html --file {{file}}

# Render a markdown body to an HTML file you can open in a browser to check how it will look
md-preview file out="/tmp/m2c_preview.html":
    @{{_m2c}} md2html --file {{file}} --out {{out}}

# Draft a NEW conversation (not a reply): TO, SUBJECT, BODY file
compose to subject body account="proton":
    @{{_m2c}} compose --to "{{to}}" --subject "{{subject}}" --file {{body}} --account {{account}}

# Preview a new conversation without writing it
compose-preview to subject body account="proton":
    @{{_m2c}} compose --to "{{to}}" --subject "{{subject}}" --file {{body}} --account {{account}} --dry-run

# Full control over a draft: --to "a@x, b@y" --all --file BODY --dry-run --account --limit
draft-args *args:
    @{{_m2c}} draft {{args}}

# Measure what HTML->text conversion loses. Exits non-zero if anything is lost.
audit account="proton" limit="400":
    @{{_m2c}} audit --account {{account}} --limit {{limit}}

# Run the test suite
test:
    @uv run pytest tests/ -q

# Lint
lint:
    @uv run ruff check . --output-format=concise

# Tests + lint + a full-mailbox loss audit
check: test lint
    @just audit proton 900

# --- Proton Bridge ----------------------------------------------------------

# Is Bridge up and serving IMAP? Logs in — a listening port is not evidence.
bridge-status:
    @{{_m2c}} bridge-status
