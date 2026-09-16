#!/usr/bin/env python
"mail2context CLI. Read mail, rebuild threads, render context, draft replies. Never sends."
import argparse
import imaplib
import ssl
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from mail2context.audit import audit_messages
from mail2context.compose import build_reply
from mail2context.mailbox import append_draft, connect, fetch_recent, list_folders, load_account
from mail2context.render import render_thread
from mail2context.thread import group_threads, sent_at, thread_key

DRAFTS = {'proton': 'Drafts', 'gmail': '[Gmail]/Drafts'}


def _load(account: str, folder: str, limit: int):
    "Connect, fetch, and rebuild threads. Returns (connection, threads newest-activity-first)."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    M = connect(load_account(account))
    msgs = fetch_recent(M, folder, limit)
    threads = group_threads(msgs)
    threads.sort(key=lambda t: sent_at(t[-1]), reverse=True)  # parsed, not the raw header string
    return M, threads


def _pick(threads: list, key: str) -> list:
    "Find the thread whose key starts with `key`."
    hits = [t for t in threads if thread_key(t).startswith(key)]
    if not hits: raise SystemExit(f"no thread matching {key!r} in this window — widen --limit")
    if len(hits) > 1: raise SystemExit(f"{key!r} is ambiguous, matches {len(hits)} threads")
    return hits[0]


def cmd_accounts(a):
    "Check that each configured account authenticates."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    for name in ('proton', 'gmail'):
        try:
            M = connect(load_account(name)); n = len(list_folders(M)); M.logout()
            print(f"  {name:8} OK   ({n} folders)")
        except SystemExit as e: print(f"  {name:8} not configured — {e}")
        except (OSError, imaplib.IMAP4.error, ssl.SSLError, KeyError) as e:
            print(f"  {name:8} FAILED — {type(e).__name__}: {e}")


def cmd_folders(a):
    "List mailboxes on the account."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    M = connect(load_account(a.account))
    for f in list_folders(M): print(" ", f)
    M.logout()


def cmd_threads(a):
    "List reconstructed threads, newest activity first."
    M, threads = _load(a.account, a.folder, a.limit)
    print(f"{len(threads)} threads from the last {a.limit} messages in {a.folder}\n")
    for t in threads[:a.show]:
        who = sorted({(m['From'] or '').split('<')[0].strip(' "') or '?' for m in t})
        print(f"  {thread_key(t)}  {len(t):3} msg  {str(t[-1]['Date'])[:16]:18} "
              f"{(t[0]['Subject'] or '(no subject)')[:52]}")
        print(f"            {', '.join(who)[:96]}")
    M.logout()


def cmd_thread(a):
    "Render one thread as markdown on stdout."
    M, threads = _load(a.account, a.folder, a.limit)
    sys.stdout.write(render_thread(_pick(threads, a.key), strip_quotes=not a.raw))
    M.logout()


def cmd_export(a):
    "Write one thread to a markdown file for side-by-side comparison with the mail UI."
    M, threads = _load(a.account, a.folder, a.limit)
    t = _pick(threads, a.key)
    stamp = datetime.now().astimezone()
    variant = 'raw' if a.raw else 'stripped'
    # default into verify/, which is gitignored — mailbox content must never reach the remote
    out = Path(a.out or Path(__file__).resolve().parent.parent / 'verify' /
               f"{stamp:%y%m%d_%H%M}__thread_{thread_key(t)}.{variant}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_thread(t, strip_quotes=not a.raw))
    print(f"wrote {out}  ({len(t)} messages)")
    M.logout()


def cmd_draft(a):
    "Create a reply draft on the thread. Appends to Drafts; never sends (D-003)."
    M, threads = _load(a.account, a.folder, a.limit)
    t = _pick(threads, a.key)
    body = Path(a.file).read_text() if a.file else sys.stdin.read()
    acct = load_account(a.account)
    msg = build_reply(t, body=body, frm=acct.user, to=a.to)
    print(f"draft to: {msg['To']}\nsubject : {msg['Subject']}\nthreaded: {msg['In-Reply-To']}")
    if a.dry_run: print("\n--- dry run, nothing written ---\n"); print(body); M.logout(); return
    print("result  :", append_draft(M, a.drafts or DRAFTS[a.account], msg))
    M.logout()


def cmd_audit(a):
    "Measure what HTML→text conversion loses across the mailbox. Zero is the target."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    M = connect(load_account(a.account))
    rep = audit_messages(fetch_recent(M, a.folder, a.limit))
    for k, v in rep.items(): print(f"  {k:22} {v}")
    bad = sum(rep[k] for k in ('text_chunks_lost', 'urls_dropped', 'alts_dropped', 'attachments_unnamed'))
    print(f"\n  {'LOSS DETECTED' if bad else 'no loss detected'} ({bad} items)")
    M.logout()
    raise SystemExit(1 if bad else 0)


def main():
    p = argparse.ArgumentParser(prog='m2c', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)

    def common(sp, folder='All Mail'):
        sp.add_argument('--account', default='proton', help='proton | gmail')
        sp.add_argument('--folder', default=folder)
        sp.add_argument('--limit', type=int, default=400, help='how many recent messages to scan')
        return sp

    sub.add_parser('accounts', help=cmd_accounts.__doc__).set_defaults(fn=cmd_accounts)
    f = sub.add_parser('folders', help=cmd_folders.__doc__); f.add_argument('--account', default='proton')
    f.set_defaults(fn=cmd_folders)

    t = common(sub.add_parser('threads', help=cmd_threads.__doc__))
    t.add_argument('--show', type=int, default=25); t.set_defaults(fn=cmd_threads)

    s = common(sub.add_parser('thread', help=cmd_thread.__doc__))
    s.add_argument('key'); s.add_argument('--raw', action='store_true', help='keep quoted originals')
    s.set_defaults(fn=cmd_thread)

    e = common(sub.add_parser('export', help=cmd_export.__doc__))
    e.add_argument('key'); e.add_argument('--out'); e.add_argument('--raw', action='store_true')
    e.set_defaults(fn=cmd_export)

    d = common(sub.add_parser('draft', help=cmd_draft.__doc__))
    d.add_argument('key'); d.add_argument('--file'); d.add_argument('--to'); d.add_argument('--drafts')
    d.add_argument('--dry-run', action='store_true'); d.set_defaults(fn=cmd_draft)

    common(sub.add_parser('audit', help=cmd_audit.__doc__)).set_defaults(fn=cmd_audit)

    a = p.parse_args(); a.fn(a)


if __name__ == '__main__': main()
