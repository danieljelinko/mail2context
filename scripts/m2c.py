#!/usr/bin/env python
"mail2context CLI. Read mail, rebuild threads, render context, draft replies. Never sends."
import argparse
import imaplib
import re
import ssl
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from mail2context.audit import audit_messages
from mail2context.compose import build_message, build_reply, list_participants
from mail2context.markdown_mail import render_markdown
from mail2context.mailbox import (append_draft, connect, fetch_recent, list_folders,
                                  load_account, search_messages)
from mail2context.search import build_search_criteria, flags_of, is_unread
from mail2context.render import render_thread
from mail2context.thread import group_threads, message_id, sent_at, thread_key

ROOT = Path(__file__).resolve().parent.parent
DRAFTS   = {'proton': 'Drafts',   'gmail': '[Gmail]/Drafts'}
ALL_MAIL = {'proton': 'All Mail', 'gmail': '[Gmail]/All Mail'}   # Gmail namespaces its system folders


def _signature(a) -> tuple[str | None, str | None]:
    "Signature text/HTML from signature.txt / signature.html at the repo root, unless disabled."
    if getattr(a, 'no_signature', False): return None, None
    txt, html = ROOT / 'signature.txt', ROOT / 'signature.html'
    return (txt.read_text() if txt.exists() else None,
            html.read_text() if html.exists() else None)


def _folder(a) -> str:
    "The folder to scan: what was asked for, else the account's all-mail folder."
    return a.folder or ALL_MAIL[a.account]


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


def _needs_reply(thread: list, me: str) -> bool:
    "Whether the last word in `thread` was someone else's."
    return me.lower() not in (thread[-1].get('From') or '').lower()


def _status(thread: list, me: str) -> str:
    "Compact per-thread status: unread count, answered, awaiting your reply."
    n = sum(is_unread(m) for m in thread)
    marks = []
    if n:                            marks.append(f'{n} unread')
    if _needs_reply(thread, me):     marks.append('awaiting you')
    if any('\\Answered' in flags_of(m) for m in thread): marks.append('answered')
    return ', '.join(marks)


def _print_threads(threads: list, show: int, me: str) -> None:
    "Render a thread list with status markers."
    for t in threads[:show]:
        who = sorted({(m['From'] or '').split('<')[0].strip(' "') or '?' for m in t})
        st = _status(t, me)
        print(f"  {thread_key(t)}  {len(t):3} msg  {str(sent_at(t[-1]))[:16]:18} "
              f"{(t[0]['Subject'] or '(no subject)')[:52]}")
        print(f"            {', '.join(who)[:80]}{('  [' + st + ']') if st else ''}")


def cmd_threads(a):
    "List reconstructed threads, newest activity first."
    M, threads = _load(a.account, _folder(a), a.limit)
    me = load_account(a.account).user
    if a.needs_reply: threads = [t for t in threads if _needs_reply(t, me)]
    print(f"{len(threads)} threads from the last {a.limit} messages in {_folder(a)}\n")
    _print_threads(threads, a.show, me)
    M.logout()


def cmd_search(a):
    "Search the mailbox server-side, then group the matches into threads."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    crit = build_search_criteria(frm=a.frm, to=a.to, subject=a.subject, text=a.text,
                                 since=a.since, before=a.before, unread=a.unread,
                                 flagged=a.flagged, unanswered=a.unanswered)
    acct = load_account(a.account)
    M = connect(acct)
    matched = search_messages(M, _folder(a), crit, a.limit)
    # Grouping only the matches would rebuild partial threads with keys that do not agree with
    # `threads`. Union the matches with the recent window so threads come out whole and keyed
    # the same way; a match older than the window still appears, just with less context.
    by_id = {}
    for m in fetch_recent(M, _folder(a), a.limit) + matched:
        by_id.setdefault(message_id(m) or id(m), m)
    hits = {message_id(m) or id(m) for m in matched}
    threads = [t for t in group_threads(list(by_id.values()))
               if any((message_id(m) or id(m)) in hits for m in t)]
    threads.sort(key=lambda t: sent_at(t[-1]), reverse=True)
    if a.needs_reply: threads = [t for t in threads if _needs_reply(t, acct.user)]
    print(f"IMAP SEARCH {' '.join(crit)}")
    print(f"{len(matched)} matching messages -> {len(threads)} threads in {_folder(a)}\n")
    _print_threads(threads, a.show, acct.user)
    M.logout()


def cmd_thread(a):
    "Render one thread as markdown on stdout."
    M, threads = _load(a.account, _folder(a), a.limit)
    sys.stdout.write(render_thread(_pick(threads, a.key), strip_quotes=not a.raw))
    M.logout()


def cmd_export(a):
    "Write one thread to a markdown file for side-by-side comparison with the mail UI."
    M, threads = _load(a.account, _folder(a), a.limit)
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
    M, threads = _load(a.account, _folder(a), a.limit)
    t = _pick(threads, a.key)
    body = Path(a.file).read_text() if a.file else sys.stdin.read()
    acct = load_account(a.account)
    sig_t, sig_h = _signature(a)
    msg = build_reply(t, body=body, frm=acct.user, to=a.to, reply_all=a.all,
                      markdown=not a.plain, signature_text=sig_t, signature_html=sig_h)
    addressed = {x.strip().lower() for x in f"{msg['To']},{msg['Cc'] or ''}".split(',') if x.strip()}
    omitted = [w for w in list_participants(t, acct.user) if w.lower() not in addressed]
    print(f"draft to: {msg['To']}")
    if msg['Cc']: print(f"cc      : {msg['Cc']}")
    print(f"subject : {msg['Subject']}\nthreaded: {msg['In-Reply-To']}")
    if omitted:
        print(f"OMITTED : {', '.join(omitted)}")
        print("          this thread has other participants — pass --all to copy them in")
    if a.dry_run: print("\n--- dry run, nothing written ---\n"); print(body); M.logout(); return
    print("result  :", append_draft(M, a.drafts or DRAFTS[a.account], msg))
    M.logout()


def cmd_compose(a):
    "Draft a NEW conversation to chosen recipients. Appends to Drafts; never sends."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    acct = load_account(a.account)
    body = Path(a.file).read_text() if a.file else sys.stdin.read()
    sig_t, sig_h = _signature(a)
    msg = build_message(to=a.to, subject=a.subject, body=body, frm=acct.user, cc=a.cc,
                        markdown=not a.plain, signature_text=sig_t, signature_html=sig_h)
    print(f"draft to: {msg['To']}")
    if msg['Cc']: print(f"cc      : {msg['Cc']}")
    print(f"subject : {msg['Subject']}\nthreaded: (new conversation)")
    if a.dry_run: print("\n--- dry run, nothing written ---\n"); print(body); return
    M = connect(acct)
    print("result  :", append_draft(M, a.drafts or DRAFTS[a.account], msg))
    M.logout()


def cmd_md2html(a):
    "Convert a markdown body to the exact HTML that would be mailed. No LLM involved."
    html = render_markdown(Path(a.file).read_text())
    _, sig_h = _signature(a)
    if sig_h: html += f'\n{sig_h.strip()}'
    if not a.out: print(html); return
    out = Path(a.out)
    out.write_text('<!doctype html><meta charset="utf-8">'
                   f'<title>{out.name}</title>\n<body style="margin:2em; background:#fff">\n'
                   f'{html}\n</body>\n')
    print(f"wrote {out} — open it in a browser to see how the mail will look")


def cmd_audit(a):
    "Measure what HTML→text conversion loses across the mailbox. Zero is the target."
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    M = connect(load_account(a.account))
    rep = audit_messages(fetch_recent(M, _folder(a), a.limit))
    for k, v in rep.items(): print(f"  {k:22} {v}")
    bad = sum(rep[k] for k in ('text_chunks_lost', 'urls_dropped', 'alts_dropped', 'attachments_unnamed'))
    print(f"\n  {'LOSS DETECTED' if bad else 'no loss detected'} ({bad} items)")
    M.logout()
    raise SystemExit(1 if bad else 0)


def main():
    p = argparse.ArgumentParser(prog='m2c', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)

    def common(sp):
        sp.add_argument('--account', default='proton', help='proton | gmail')
        sp.add_argument('--folder', default=None, help='defaults to the account\'s all-mail folder')
        sp.add_argument('--limit', type=int, default=400, help='how many recent messages to scan')
        return sp

    sub.add_parser('accounts', help=cmd_accounts.__doc__).set_defaults(fn=cmd_accounts)
    f = sub.add_parser('folders', help=cmd_folders.__doc__); f.add_argument('--account', default='proton')
    f.set_defaults(fn=cmd_folders)

    t = common(sub.add_parser('threads', help=cmd_threads.__doc__))
    t.add_argument('--show', type=int, default=25)
    t.add_argument('--needs-reply', action='store_true', help='only threads whose last message is not yours')
    t.set_defaults(fn=cmd_threads)

    q = common(sub.add_parser('search', help=cmd_search.__doc__))
    q.add_argument('--from', dest='frm'); q.add_argument('--to'); q.add_argument('--subject')
    q.add_argument('--text', help='substring anywhere in headers or body')
    q.add_argument('--since', help='ISO date, inclusive'); q.add_argument('--before', help='ISO date, exclusive')
    q.add_argument('--unread', action='store_true'); q.add_argument('--flagged', action='store_true')
    q.add_argument('--unanswered', action='store_true')
    q.add_argument('--needs-reply', action='store_true')
    q.add_argument('--show', type=int, default=25)
    q.set_defaults(fn=cmd_search)

    s = common(sub.add_parser('thread', help=cmd_thread.__doc__))
    s.add_argument('key'); s.add_argument('--raw', action='store_true', help='keep quoted originals')
    s.set_defaults(fn=cmd_thread)

    e = common(sub.add_parser('export', help=cmd_export.__doc__))
    e.add_argument('key'); e.add_argument('--out'); e.add_argument('--raw', action='store_true')
    e.set_defaults(fn=cmd_export)

    d = common(sub.add_parser('draft', help=cmd_draft.__doc__))
    d.add_argument('key'); d.add_argument('--file'); d.add_argument('--to'); d.add_argument('--drafts')
    d.add_argument('--dry-run', action='store_true')
    d.add_argument('--all', action='store_true', help='Cc everyone else in the thread')
    d.add_argument('--plain', action='store_true', help='do not interpret the body as markdown')
    d.add_argument('--no-signature', action='store_true')
    d.set_defaults(fn=cmd_draft)

    c = sub.add_parser('compose', help=cmd_compose.__doc__)
    c.add_argument('--to', required=True); c.add_argument('--cc')
    c.add_argument('--subject', required=True); c.add_argument('--file')
    c.add_argument('--account', default='proton'); c.add_argument('--drafts')
    c.add_argument('--dry-run', action='store_true')
    c.add_argument('--plain', action='store_true', help='do not interpret the body as markdown')
    c.add_argument('--no-signature', action='store_true')
    c.set_defaults(fn=cmd_compose)

    h = sub.add_parser('md2html', help=cmd_md2html.__doc__)
    h.add_argument('--file', required=True); h.add_argument('--out')
    h.add_argument('--no-signature', action='store_true'); h.set_defaults(fn=cmd_md2html)

    common(sub.add_parser('audit', help=cmd_audit.__doc__)).set_defaults(fn=cmd_audit)

    # `just --list` prints signatures like `draft key body account="proton"`, which read as if
    # name=value were valid. just arguments are positional, so those arrive here as literals.
    for arg in sys.argv[1:]:
        if re.fullmatch(r'(account|limit|show|folder|out|since|body|key|sender|term)=.*', arg):
            p.error(f"got the literal {arg!r} — `just` arguments are POSITIONAL, not name=value.\n"
                    f"       `just --list` shows defaults, not syntax to copy.\n"
                    f"       Try: just draft <KEY> <BODY-FILE>   (then optionally <account> <limit>)")
    a = p.parse_args(); a.fn(a)


if __name__ == '__main__': main()
