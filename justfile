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

# Preview a reply draft without writing it. BODY is a file path.
draft-preview key body account="proton" limit="400":
    @{{_m2c}} draft {{key}} --file {{body}} --account {{account}} --limit {{limit}} --dry-run

# Create a reply draft in the Drafts folder. Review and send from your mail client.
draft key body account="proton" limit="400":
    @{{_m2c}} draft {{key}} --file {{body}} --account {{account}} --limit {{limit}}

# --- verification -----------------------------------------------------------

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

# Is Bridge up and serving IMAP?
bridge-status:
    @ss -tlnp 2>/dev/null | grep -q 127.0.0.1:1143 && echo "Bridge IMAP: up on 1143" || echo "Bridge IMAP: DOWN — start it, mail commands will fail"
