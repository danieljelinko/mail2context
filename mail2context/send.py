"""TEMPORARY send guard — D-011. This whole module is deleted at `01_plan.md` Phase 6.

D-003 forbids sending outright. D-011 lifts that narrowly and temporarily, so cross-provider
round-trip testing can verify header survival and real quote blocks. Nothing here sends: this is
only the refusal, written before any send code exists so no send path can predate its guard.
"""
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import getaddresses

__all__ = ['SEND_ALLOWLIST', 'SendRefused', 'SmtpAccount', 'check_recipients', 'load_smtp',
           'send_message']

_RECIPIENT_HEADERS = ('To', 'Cc', 'Bcc')
_LOCAL = ('127.0.0.1', 'localhost')

# Deliberately a module constant, not a parameter. The house rule is to pass project-specific
# vocabulary in as a required argument, but D-011 demands an allowlist that a call site CANNOT
# widen — a new address is a new owner decision, not a code edit. Safety outranks the style rule
# here, and `test_send_allowlist_holds_exactly_the_two_addresses_d011_authorised` is the tripwire.
SEND_ALLOWLIST = frozenset({'dj@ai4hu.org', 'daniel.jelinko@gmail.com'})


class SendRefused(Exception):
    "Raised when a message addresses anyone outside `SEND_ALLOWLIST`, or addresses nobody."


def check_recipients(msg: EmailMessage) -> list[str]:
    "Every To/Cc/Bcc address on `msg`; raises `SendRefused` unless all of them are allowlisted."
    # Only headers that are actually set: given two empty strings `getaddresses` discards the
    # whole list and returns [('', '')], which is every message with no Cc and no Bcc.
    present = [str(v) for h in _RECIPIENT_HEADERS if (v := msg.get(h))]
    addrs = [a for _, a in getaddresses(present) if a]
    if not addrs: raise SendRefused('refusing: message has no To/Cc/Bcc recipient')
    blocked = [a for a in addrs if a.lower() not in SEND_ALLOWLIST]   # exact match, never prefix
    if blocked:
        raise SendRefused(f"refusing: {', '.join(blocked)} outside the D-011 allowlist "
                          f"({', '.join(sorted(SEND_ALLOWLIST))})")
    return addrs


@dataclass
class SmtpAccount:
    host: str
    port: int
    user: str
    password: str


def load_smtp(name: str) -> SmtpAccount:
    "Build an `SmtpAccount` from `<NAME>_SMTP_HOST/PORT` and the account's usual user/password."
    p = name.upper()
    pw = os.environ.get(f'{p}_PASS', '')
    if not pw: raise SystemExit(f"{p}_PASS is empty — set it in .env before sending as {name}")
    return SmtpAccount(os.environ[f'{p}_SMTP_HOST'], int(os.environ[f'{p}_SMTP_PORT']),
                       os.environ[f'{p}_USER'], pw)


def send_message(acct: SmtpAccount, msg: EmailMessage) -> list[str]:
    "Submit `msg` over SMTP. `check_recipients` runs FIRST, so a refusal opens no connection."
    rcpt = check_recipients(msg)
    ctx = ssl.create_default_context()
    if acct.host in _LOCAL:                     # Bridge serves a self-signed cert on loopback
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with smtplib.SMTP(acct.host, acct.port, timeout=60) as S:
        S.starttls(context=ctx)
        S.login(acct.user, acct.password)
        # Envelope recipients are the guard's return value, not re-derived from the headers, so
        # what reaches the wire is exactly what was checked.
        S.send_message(msg, from_addr=acct.user, to_addrs=rcpt)
    return rcpt
