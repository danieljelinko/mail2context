"IMAP access to a mail account: Proton via local Bridge, or Gmail with an app password."
import imaplib
import os
import ssl
import time
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

from .search import annotate_flags, parse_flags

__all__ = ['Account', 'append_draft', 'connect', 'fetch_recent', 'list_folders', 'list_uids',
           'load_account', 'move_message', 'search_messages']

_LOCAL = ('127.0.0.1', 'localhost')


@dataclass
class Account:
    name: str       # "proton" | "gmail" — the env-var prefix, lowercased
    host: str
    port: int
    user: str
    password: str
    starttls: bool  # True for Bridge (STARTTLS on 1143), False for implicit TLS (993)


def load_account(name: str) -> Account:
    "Build an `Account` from `<NAME>_*` environment variables."
    p = name.upper()
    host = os.environ[f'{p}_IMAP_HOST']
    pw = os.environ.get(f'{p}_PASS', '')
    if not pw: raise SystemExit(f"{p}_PASS is empty — set it in .env before using the {name} account")
    return Account(name.lower(), host, int(os.environ[f'{p}_IMAP_PORT']),
                   os.environ[f'{p}_USER'], pw, starttls=host in _LOCAL)


def connect(acct: Account) -> imaplib.IMAP4:
    "Open an authenticated IMAP connection to `acct`."
    if not acct.starttls: M = imaplib.IMAP4_SSL(acct.host, acct.port)
    else:
        M = imaplib.IMAP4(acct.host, acct.port)
        ctx = ssl.create_default_context()
        if acct.host in _LOCAL:                       # Bridge serves a self-signed cert on loopback
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        M.starttls(ssl_context=ctx)
    M.login(acct.user, acct.password)
    return M


def _quote(folder: str) -> str:
    "imaplib does not quote mailbox names, and Proton's contain spaces."
    return f'"{folder}"' if ' ' in folder and not folder.startswith('"') else folder


def list_folders(M: imaplib.IMAP4) -> list[str]:
    "Mailbox names available on the server."
    _, data = M.list()
    return [line.decode('utf-8', 'replace').rsplit(' "/" ', 1)[-1].strip('"') for line in data if line]


def _fetch_uids(M: imaplib.IMAP4, uids: list[bytes]) -> list[EmailMessage]:
    "Fetch `uids` with their flags. BODY.PEEK so nothing is marked \\Seen."
    if not uids: return []
    _, resp = M.uid('fetch', b','.join(uids), '(FLAGS BODY.PEEK[])')
    out = []
    for part in resp:
        if not isinstance(part, tuple): continue
        msg = BytesParser(policy=policy.default).parsebytes(part[1])
        annotate_flags(msg, parse_flags(part[0]))
        out.append(msg)
    return out


def fetch_recent(M: imaplib.IMAP4, folder: str, limit: int) -> list[EmailMessage]:
    "Fetch the newest `limit` messages from `folder`, read-only."
    M.select(_quote(folder), readonly=True)
    _, data = M.uid('search', None, 'ALL')
    return _fetch_uids(M, data[0].split()[-limit:] if data and data[0] else [])


def search_messages(M: imaplib.IMAP4,
                    folder: str,
                    criteria: list[str],  # from `search.build_search_criteria`
                    limit: int,           # cap on matches, newest kept
                    ) -> list[EmailMessage]:
    "Fetch the newest `limit` messages in `folder` matching IMAP SEARCH `criteria`."
    M.select(_quote(folder), readonly=True)
    try: _, data = M.uid('search', 'UTF-8', *criteria)
    except imaplib.IMAP4.error: _, data = M.uid('search', None, *criteria)  # server may refuse a charset
    return _fetch_uids(M, data[0].split()[-limit:] if data and data[0] else [])


def append_draft(M: imaplib.IMAP4, folder: str, msg: EmailMessage) -> str:
    "APPEND `msg` to `folder` flagged \\Draft. Never sends — see D-003."
    typ, data = M.append(_quote(folder), '\\Draft',
                         imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    return f"{typ} {data[0].decode('utf-8', 'replace') if data and data[0] else ''}"


def list_uids(M: imaplib.IMAP4, folder: str) -> list[bytes]:
    "UIDs in `folder`, oldest first."
    M.select(_quote(folder), readonly=True)
    _, data = M.uid('search', None, 'ALL')
    return data[0].split() if data and data[0] else []


def move_message(M: imaplib.IMAP4, folder: str, uid: bytes, dest: str) -> str:
    "Move one message to `dest`. Used to bin a draft — recoverable, unlike EXPUNGE."
    M.select(_quote(folder))                       # not readonly: MOVE mutates
    typ, _ = M.uid("move", uid, _quote(dest))
    return f"{typ} {uid.decode()} -> {dest}"
