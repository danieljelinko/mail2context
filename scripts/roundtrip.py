#!/usr/bin/env python
"""TEMPORARY cross-provider round-trip runner (D-011). Deleted at `01_plan.md` Phase 6.

Sends a known conversation alternating Proton and Gmail, then asserts the tool rebuilds it.
The assertions themselves live in `mail2context/roundtrip.py` and are unit-tested; this file is
the I/O around them — SMTP, IMAP polling, and a ledger under verify/ (gitignored).
"""
import argparse
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from mail2context.compose import build_message, build_reply
from mail2context.mailbox import connect, load_account, search_messages
from mail2context.roundtrip import check_reply_chain, check_thread
from mail2context.send import check_recipients, load_smtp, send_message
from mail2context.thread import message_id, sent_at

ROOT = Path(__file__).resolve().parent.parent
ALL_MAIL = {'proton': 'All Mail', 'gmail': '[Gmail]/All Mail'}
ADDR = {'proton': 'dj@ai4hu.org', 'gmail': 'daniel.jelinko@gmail.com'}
OTHER = {'proton': 'gmail', 'gmail': 'proton'}
STEPS = 6


def _subject(run_id: str) -> str: return f'm2c roundtrip {run_id}'
def _token(run_id: str, n: int) -> str: return f'm2c-rt-{run_id}-step-{n}'
def _ledger(run_id: str) -> Path: return ROOT / 'verify' / f'roundtrip_{run_id}.json'


def _signature() -> tuple[str | None, str | None]:
    "The real signature, so the round-trip exercises the production compose path."
    txt, html = ROOT / 'signature.txt', ROOT / 'signature.html'
    return (txt.read_text() if txt.exists() else None,
            html.read_text() if html.exists() else None)


def _body(run_id: str, n: int) -> str:
    "Body for step `n`, carrying its own identifying token on a line of its own."
    return (f'Round-trip step {n} of {STEPS}, sent automatically under D-011.\n\n'
            f'{_token(run_id, n)}\n\nThis conversation exists only to verify thread '
            f'reconstruction and will be deleted.')


def _step_of(msg, run_id: str, steps: int) -> int | None:
    "Which step `msg` is, by the token in its plain body. Survives Re:/Auto: subject rewriting."
    part = msg.get_body(('plain',))
    text = part.get_content() if part else msg.as_string()
    return next((n for n in range(1, steps + 1) if _token(run_id, n) in text), None)


def _fetch_side(account: str, run_id: str, limit: int = 50) -> list:
    "Every message of this run visible to `account`, found by a server-side subject search."
    M = connect(load_account(account))
    # imaplib quotes nothing — a multi-word SEARCH term must carry its own quotes.
    msgs = search_messages(M, ALL_MAIL[account], ['SUBJECT', f'"{_subject(run_id)}"'], limit)
    M.logout()
    return msgs


def _wait_for(account: str, run_id: str, step: int, timeout: float, interval: float = 6):
    "Poll `account` until step `step` of this run is visible there; returns it or raises."
    deadline = time.time() + timeout
    while time.time() < deadline:
        for m in _fetch_side(account, run_id):
            if _step_of(m, run_id, STEPS + 1) == step: return m
        time.sleep(interval)
    raise SystemExit(f"step {step} never reached {account} within {timeout:.0f}s")


def _send_step(n: int, run_id: str, prev, dry_run: bool):
    "Build, guard-check and send step `n`. `prev` is the delivered previous message, or None."
    sender = 'proton' if n % 2 else 'gmail'
    sig_t, sig_h = _signature()
    if prev is None:
        msg = build_message(to=ADDR[OTHER[sender]], subject=_subject(run_id),
                            body=_body(run_id, n), frm=ADDR[sender],
                            signature_text=sig_t, signature_html=sig_h)
    else:
        # Let build_reply derive To/Subject/In-Reply-To from the delivered message, exactly as a
        # real reply does — that is the production logic under test, not a fixture.
        msg = build_reply([prev], body=_body(run_id, n), frm=ADDR[sender],
                          signature_text=sig_t, signature_html=sig_h)
        if n == 4:   # an autoresponder stacking a prefix, so step 5 really has one to collapse
            msg.replace_header('Subject', f"Auto: {msg['Subject']}")
    approved = check_recipients(msg)              # printed BEFORE anything leaves the machine
    print(f"  step {n}  {sender:6} -> {', '.join(approved)}")
    print(f"           subject     : {msg['Subject']}")
    print(f"           in-reply-to : {msg['In-Reply-To'] or '(new conversation)'}")
    if msg['To'] != ADDR[OTHER[sender]]:
        raise SystemExit(f"  derived To {msg['To']!r} is not {ADDR[OTHER[sender]]!r}")
    if dry_run: print("           DRY RUN — not sent"); return None
    send_message(load_smtp(sender), msg)
    print(f"           sent, waiting for it to reach {OTHER[sender]} ...", flush=True)
    return _wait_for(OTHER[sender], run_id, n, timeout=420)


def send_conversation(run_id: str, dry_run: bool) -> str:
    "Send the alternating conversation, waiting for each message to arrive before replying."
    print(f"run {run_id} — subject {_subject(run_id)!r}\n")
    prev, steps = None, []
    for n in range(1, STEPS + 1):
        prev = _send_step(n, run_id, prev, dry_run)
        if prev is None: return run_id     # dry run stops after showing step 1
        steps.append({'step': n, 'delivered_message_id': message_id(prev),
                      'subject': prev['Subject'], 'received_by': OTHER['proton' if n % 2 else 'gmail']})
        print(f"           delivered as {message_id(prev)}\n", flush=True)
    led = _ledger(run_id)
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(json.dumps({'run_id': run_id, 'sent_at': datetime.now().astimezone().isoformat(),
                               'steps': steps}, indent=2))
    print(f"ledger {led}\nnow run: just roundtrip-verify {run_id}")
    return run_id


def _report(account: str, run_id: str, expect_threads: int, expect_len: int) -> list[str]:
    "Fetch this run from `account` and check thread, order and delivered reply chain."
    msgs = _fetch_side(account, run_id)
    by_step = {}
    for m in msgs:
        s = _step_of(m, run_id, STEPS + 1)
        if s: by_step.setdefault(s, m)
    print(f"\n{account}: {len(msgs)} messages matched, steps present: {sorted(by_step)}")
    for s in sorted(by_step):
        # Normalised UTC: Proton sends +0000 and Gmail +0200, so printing either raw offset makes
        # a correctly-ordered thread look scrambled (04_learnings.md).
        utc = sent_at(by_step[s]).astimezone(timezone.utc)
        print(f"  step {s}  {utc:%Y-%m-%d %H:%M:%S} UTC  {by_step[s]['Subject']}")
    ordered = [by_step[s] for s in sorted(by_step)]
    ids = [message_id(m) for m in ordered]
    problems = []
    if len(ordered) != expect_len:
        problems.append(f'{account}: {len(ordered)} steps present, expected {expect_len}')
    if expect_threads == 1:
        problems += [f'{account}: {p}' for p in check_thread(ordered, ids)]
        problems += [f'{account}: {p}' for p in check_reply_chain(ordered, ids)]
    else:
        got = check_thread(ordered, ids)
        if not got: problems.append(f'{account}: expected the broken reply to SPLIT the thread, '
                                    f'but it rebuilt as one')
        else: print(f"  split as intended: {got[0]}")
    return problems


def _check_subjects(account: str, run_id: str) -> list[str]:
    "Assert the Re:/Auto: prefixes really generated in transit are what the code claims."
    base = _subject(run_id)
    msgs = {s: m for m in _fetch_side(account, run_id)
            if (s := _step_of(m, run_id, STEPS + 1))}
    want = {1: base, 2: f'Re: {base}', 3: f'Re: {base}', 4: f'Auto: Re: {base}',
            5: f'Re: {base}', 6: f'Re: {base}'}
    return [f"{account}: step {s} subject {msgs[s]['Subject']!r}, expected {w!r}"
            for s, w in want.items() if s in msgs and msgs[s]['Subject'] != w]


def verify_conversation(run_id: str) -> None:
    "Assert one thread of six, in send order, with the delivered reply chain intact, on both sides."
    problems = []
    for account in ('proton', 'gmail'):
        problems += _report(account, run_id, expect_threads=1, expect_len=STEPS)
        problems += _check_subjects(account, run_id)
    _verdict(problems, 'round-trip')


def break_chain(run_id: str, dry_run: bool) -> None:
    "Send a 7th reply with its threading headers stripped; both sides must show the thread SPLIT."
    prev = _wait_for('proton', run_id, STEPS, timeout=30)
    sig_t, sig_h = _signature()
    msg = build_reply([prev], body=_body(run_id, STEPS + 1), frm=ADDR['proton'],
                      signature_text=sig_t, signature_html=sig_h)
    del msg['In-Reply-To'], msg['References']      # the deliberate break
    approved = check_recipients(msg)
    print(f"  step {STEPS + 1}  proton -> {', '.join(approved)}  (In-Reply-To and References REMOVED)")
    if dry_run: print("  DRY RUN — not sent"); return
    send_message(load_smtp('proton'), msg)
    print("  sent, waiting ...", flush=True)
    _wait_for('gmail', run_id, STEPS + 1, timeout=420)
    problems = []
    for account in ('proton', 'gmail'):
        problems += _report(account, run_id, expect_threads=2, expect_len=STEPS + 1)
    _verdict(problems, 'deliberate chain break')


def _verdict(problems: list[str], what: str) -> None:
    "Print the verdict and exit non-zero on any problem."
    if problems:
        print(f"\n{what.upper()} FAILED ({len(problems)} problems)")
        for p in problems: print(f"  - {p}")
        raise SystemExit(1)
    print(f"\n{what} OK")


def cmd_send(a):  send_conversation(a.run_id or secrets.token_hex(3), a.dry_run)
def cmd_verify(a): verify_conversation(a.run_id)
def cmd_break(a):  break_chain(a.run_id, a.dry_run)


def cmd_run(a):
    "Construct the conversation and assert every Phase 2 property. Non-zero on any failure."
    run_id = send_conversation(a.run_id or secrets.token_hex(3), dry_run=False)
    verify_conversation(run_id)
    break_chain(run_id, dry_run=False)
    print(f"\nPhase 2 complete for run {run_id}")


def main():
    load_dotenv(ROOT / '.env')
    p = argparse.ArgumentParser(prog='roundtrip', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('send', help=cmd_send.__doc__)
    s.add_argument('--run-id'); s.add_argument('--dry-run', action='store_true')
    s.set_defaults(fn=cmd_send)
    v = sub.add_parser('verify', help=cmd_verify.__doc__)
    v.add_argument('run_id'); v.set_defaults(fn=cmd_verify)
    b = sub.add_parser('break', help=cmd_break.__doc__)
    b.add_argument('run_id'); b.add_argument('--dry-run', action='store_true')
    b.set_defaults(fn=cmd_break)
    r = sub.add_parser('run', help=cmd_run.__doc__)
    r.add_argument('--run-id'); r.set_defaults(fn=cmd_run)
    a = p.parse_args(); a.fn(a)


if __name__ == '__main__': main()
