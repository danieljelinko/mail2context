"IMAP access to a mail account: Proton via local Bridge, or Gmail with an app password."
import imaplib
import os
import re
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

from .search import _imap_date, annotate_flags, parse_flags
from .thread import message_id, sent_at

__all__ = ['Account', 'Found', 'Pointer', 'append_draft', 'check_account', 'connect', 'fetch_headers', 'fetch_message', 'fetch_messages',
           'fetch_recent', 'fetch_thread_of', 'find_sent_folder', 'find_special_folder', 'list_folders',
           'list_message_dates', 'list_uids', 'load_account', 'move_message', 'parse_pointer', 'read_folder_state', 'search_messages']

_LOCAL = ('127.0.0.1', 'localhost')
_TLS_MODES = ('starttls', 'tls', 'none')   # none: the mail-guard proxy's plaintext loopback listener
_HEADER_BATCH = 1000                       # UIDs per FETCH: keeps a whole-mailbox command line within server limits


@dataclass
class Account:
    name: str       # "proton" | "gmail" — the env-var prefix, lowercased
    host: str
    port: int
    user: str
    password: str
    tls: str        # "starttls" (Bridge on 1143), "tls" (Gmail on 993), "none" (mail-guard proxy on loopback)


def load_account(name: str) -> Account:
    "Build an `Account` from `<NAME>_*` environment variables."
    p = name.upper()
    host = os.environ[f'{p}_IMAP_HOST']
    pw = os.environ.get(f'{p}_PASS', '')
    if not pw: raise SystemExit(f"{p}_PASS is empty — set it in .env before using the {name} account")
    tls = os.environ.get(f'{p}_IMAP_TLS') or ('starttls' if host in _LOCAL else 'tls')
    if tls not in _TLS_MODES: raise SystemExit(f"{p}_IMAP_TLS={tls!r}; expected one of {_TLS_MODES}")
    return Account(name.lower(), host, int(os.environ[f'{p}_IMAP_PORT']), os.environ[f'{p}_USER'], pw, tls)


def connect(acct: Account,
            timeout: float | None = None,  # seconds; None blocks, which is right for bulk fetches
            ) -> imaplib.IMAP4:
    "Open an authenticated IMAP connection to `acct`."
    if acct.tls == 'tls': M = imaplib.IMAP4_SSL(acct.host, acct.port, timeout=timeout)
    else:
        M = imaplib.IMAP4(acct.host, acct.port, timeout=timeout)
    if acct.tls == 'starttls':
        ctx = ssl.create_default_context()
        if acct.host in _LOCAL:                       # Bridge serves a self-signed cert on loopback
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        M.starttls(ssl_context=ctx)
    M.login(acct.user, acct.password)
    return M


def check_account(acct: Account, timeout: float = 10) -> tuple[bool, str]:
    "Whether `acct` serves mail, by logging in. Bridge binds 1143 before loading the vault, so a listening port is not evidence."
    try:
        M = connect(acct, timeout=timeout)
        n = len(list_folders(M))
        M.logout()
        return True, f'{n} folders'
    except (OSError, imaplib.IMAP4.error, ssl.SSLError) as e:
        return False, f'{type(e).__name__}: {e}'


def _quote(folder: str) -> str:
    "imaplib does not quote mailbox names, and Proton's contain spaces."
    return f'"{folder}"' if ' ' in folder and not folder.startswith('"') else folder


def list_folders(M: imaplib.IMAP4) -> list[str]:
    "Mailbox names available on the server."
    _, data = M.list()
    return [line.decode('utf-8', 'replace').rsplit(' "/" ', 1)[-1].strip('"') for line in data if line]


def find_special_folder(M: imaplib.IMAP4,
                        attr: str,  # special-use LIST attribute, e.g. "\\Sent", "\\Drafts"
                        ) -> str | None:
    "The mailbox the server flags `attr`; None when none is flagged."
    _, data = M.list()
    for line in data:
        text = line.decode('utf-8', 'replace') if line else ''
        if attr in text.split(')', 1)[0].lstrip('(').split(): return text.rsplit(' "/" ', 1)[-1].strip('"')
    return None


def find_sent_folder(M: imaplib.IMAP4) -> str | None:
    "The mailbox the server flags \\Sent (Gmail names it in the account's language); None when none is flagged."
    return find_special_folder(M, '\\Sent')


def list_message_dates(M: imaplib.IMAP4, folder: str,
                       since: str,  # ISO date, YYYY-MM-DD; messages that arrived that day or later
                       ) -> list[datetime]:
    "When each message arrived in `folder`, read-only. Only INTERNALDATE is asked for: no header, subject or body leaves the server."
    M.select(_quote(folder), readonly=True)
    _, data = M.uid('search', None, 'SINCE', _imap_date(since))
    uids = data[0].split() if data and data[0] else []
    if not uids: return []
    _, resp = M.uid('fetch', b','.join(uids), '(INTERNALDATE)')
    found = (re.search(rb'INTERNALDATE "([^"]+)"', line) for line in resp if isinstance(line, bytes))
    return [datetime.strptime(m.group(1).decode().strip(), '%d-%b-%Y %H:%M:%S %z') for m in found if m]


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


def read_folder_state(M: imaplib.IMAP4, folder: str) -> tuple[int, int]:
    "(UIDVALIDITY, UIDNEXT) of `folder`, by STATUS: the folder is not even opened."
    _, data = M.status(_quote(folder), '(UIDVALIDITY UIDNEXT)')
    text = data[0].decode('utf-8', 'replace')
    return int(re.search(r'UIDVALIDITY (\d+)', text).group(1)), int(re.search(r'UIDNEXT (\d+)', text).group(1))


def fetch_headers(M: imaplib.IMAP4, folder: str,
                  after_uid: int,      # only UIDs above this; 0 for all
                  since: str | None,   # ISO date, YYYY-MM-DD, or None for no bound
                  fields: list[str],   # header names, e.g. ["MESSAGE-ID", "FROM"]
                  ) -> list[tuple[int, EmailMessage]]:
    "(UID, headers) of the messages in `folder` past `after_uid`, read-only, flags annotated. Only `fields` leave the server: no body."
    M.select(_quote(folder), readonly=True)
    criteria = ['UID', f'{after_uid + 1}:*'] + (['SINCE', _imap_date(since)] if since else [])
    _, data = M.uid('search', None, *criteria)
    uids = [u for u in (data[0].split() if data and data[0] else []) if int(u) > after_uid]  # `n:*` always matches the last message
    want = f'(UID FLAGS BODY.PEEK[HEADER.FIELDS ({" ".join(fields)})])'
    out = []
    for i in range(0, len(uids), _HEADER_BATCH):
        _, resp = M.uid('fetch', b','.join(uids[i:i + _HEADER_BATCH]), want)
        for part in resp:
            if not isinstance(part, tuple): continue
            msg = BytesParser(policy=policy.default).parsebytes(part[1])
            annotate_flags(msg, parse_flags(part[0]))
            out.append((int(re.search(rb'UID (\d+)', part[0]).group(1)), msg))
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
    raw = [i for i, c in enumerate(criteria) if not c.isascii()]
    if len(raw) > 1: raise SystemExit('search: one accented term per search — imaplib carries a single literal')
    if raw:                                        # a quoted string is 7-bit only; Gmail refuses UTF-8 in one
        i = raw[0]; key, val = criteria[i-1], criteria[i]
        criteria = ['CHARSET', 'UTF-8'] + criteria[:i-1] + criteria[i+1:] + [key]
        M.literal = val.encode('utf-8')            # imaplib appends it after the last argument
    _, data = M.uid('search', *criteria)
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



_POINTER_RE = re.compile(r'imap://([^/]+)/(.+);UIDVALIDITY=(\d+)/;UID=(\d+)')


@dataclass(frozen=True)
class Pointer:
    "Where one copy of a message lives, as com-index stores it: imap://<account>/<folder>;UIDVALIDITY=<v>/;UID=<uid>."
    account: str
    folder: str
    uidvalidity: int
    uid: int
    def __str__(self) -> str: return f'imap://{self.account}/{self.folder};UIDVALIDITY={self.uidvalidity}/;UID={self.uid}'


def parse_pointer(text: str) -> Pointer:
    "The `Pointer` that `text` spells. The folder is taken raw, as com-index writes it, slashes and spaces included."
    m = _POINTER_RE.fullmatch(text.strip())
    if not m: raise SystemExit(f"not a message pointer: {text!r} — expected imap://<account>/<folder>;UIDVALIDITY=<n>/;UID=<n>")
    return Pointer(m[1], m[2], int(m[3]), int(m[4]))


@dataclass
class Found:
    msg: EmailMessage | None   # None when no copy was found
    pointer: Pointer | None    # where the copy that answered lives now
    path: str                  # which lookup answered: "pointer", "Message-ID in <folder> …", or "missing …"


def _bracket(mid: str) -> str: return mid.strip() if mid.strip().startswith('<') else f'<{mid.strip()}>'


def _open_folder(M: imaplib.IMAP4, folder: str) -> int:
    "Open `folder` read-only (EXAMINE) and return its UIDVALIDITY."
    validity, _ = read_folder_state(M, folder)
    M.select(_quote(folder), readonly=True)
    return validity


def _fetch_by_uid(M: imaplib.IMAP4, uids: list[int]) -> dict[int, EmailMessage]:
    "Fetch `uids` from the selected folder, keyed by UID, flags annotated. BODY.PEEK, so nothing is marked \\Seen."
    if not uids: return {}
    _, resp = M.uid('fetch', ','.join(map(str, sorted(set(uids)))), '(UID FLAGS BODY.PEEK[])')
    out = {}
    for part in resp:
        if not isinstance(part, tuple): continue
        msg = BytesParser(policy=policy.default).parsebytes(part[1])
        annotate_flags(msg, parse_flags(part[0]))
        out[int(re.search(rb'UID (\d+)', part[0]).group(1))] = msg
    return out


def _search_uids(M: imaplib.IMAP4, *criteria: str) -> list[int]:
    "UIDs in the selected folder matching `criteria`, ascending."
    _, data = M.uid('search', None, *criteria)
    return sorted(int(u) for u in (data[0].split() if data and data[0] else []))


def _find_by_message_id(M: imaplib.IMAP4, account: str, folder: str, mid: str) -> Found | None:
    "The lowest-UID copy in `folder` whose Message-ID is exactly `mid`; None when there is none."
    validity = _open_folder(M, folder)
    uids = _search_uids(M, 'HEADER', 'Message-ID', f'"{mid}"')
    if not uids: return None                     # bracketed, so Proton's substring match cannot hit another id
    copies = f', {len(uids)} copies, lowest UID taken' if len(uids) > 1 else ''
    return Found(_fetch_by_uid(M, uids[:1])[uids[0]], Pointer(account, folder, validity, uids[0]), f'Message-ID in {folder}{copies}')


def _all_mail(M: imaplib.IMAP4) -> str:
    "The mailbox the server flags \\All. Refuses rather than guess from a name."
    folder = find_special_folder(M, '\\All')
    if not folder: raise SystemExit('no mailbox is flagged \\All on this server — refusing to guess which one holds all mail')
    return folder


def fetch_messages(M: imaplib.IMAP4, account: str,
                   wants: list[tuple[Pointer | None, str | None]],  # (pointer, Message-ID); either may be None
                   ) -> list[Found]:
    """One `Found` per want, in order, over one connection, read-only. By pointer first; when its UIDVALIDITY
    changed or its UID is gone, by Message-ID in the pointer's folder, then in the folder flagged \\All."""
    out: list[Found | None] = [None] * len(wants)
    why: dict[int, str] = {}
    by_folder: dict[str, list[int]] = {}
    for i, (p, _) in enumerate(wants):
        if p: by_folder.setdefault(p.folder, []).append(i)
    for folder, idx in by_folder.items():
        validity = _open_folder(M, folder)
        live = [i for i in idx if wants[i][0].uidvalidity == validity]
        for i in idx:
            if i not in live: why[i] = f'UIDVALIDITY of {folder} is {validity}, pointer has {wants[i][0].uidvalidity}'
        got = _fetch_by_uid(M, [wants[i][0].uid for i in live])
        for i in live:
            p = wants[i][0]
            if p.uid in got: out[i] = Found(got[p.uid], p, 'pointer')
            else:            why[i] = f'UID {p.uid} is gone from {folder}'
    for i, (p, mid) in enumerate(wants):
        if out[i]: continue
        stale = f' (pointer stale: {why[i]})' if p else ''
        if not mid: out[i] = Found(None, None, f'missing{stale}; no Message-ID to search by'); continue
        folders = list(dict.fromkeys([*([p.folder] if p else []), _all_mail(M)]))
        hit = next((h for f in folders if (h := _find_by_message_id(M, account, f, _bracket(mid)))), None)
        out[i] = (Found(hit.msg, hit.pointer, hit.path + stale) if hit else
                  Found(None, None, f'missing: {_bracket(mid)} is in none of {", ".join(folders)}{stale}'))
    return out


def fetch_message(M: imaplib.IMAP4, account: str, pointer: Pointer | None, mid: str | None) -> Found:
    "One message by `pointer`, falling back to its Message-ID `mid` — see `fetch_messages`."
    return fetch_messages(M, account, [(pointer, mid)])[0]


def _ids_of(m: EmailMessage) -> set[str]:
    "This message's own Message-ID and every id it names in In-Reply-To and References."
    return set(re.findall(r'<[^<>]+>', ' '.join(str(m.get(h, '') or '') for h in ('Message-ID', 'In-Reply-To', 'References'))))


def _follow_headers(M: imaplib.IMAP4, start: dict[int, EmailMessage]) -> dict[int, EmailMessage]:
    "Grow `start` to every message in the selected folder linked to it, either way, through Message-ID / References / In-Reply-To."
    got, done = dict(start), set()
    while todo := set().union(*map(_ids_of, got.values())) - done:
        for x in todo:
            new = {u for h in ('Message-ID', 'References', 'In-Reply-To') for u in _search_uids(M, 'HEADER', h, f'"{x}"')}
            got |= _fetch_by_uid(M, sorted(new - got.keys()))
        done |= todo
    return got


def fetch_thread_of(M: imaplib.IMAP4, mid: str) -> tuple[list[EmailMessage], str]:
    """The messages of the thread holding Message-ID `mid`, oldest first, one per Message-ID, found on the server in the
    folder flagged \\All — not in a recent window. Returns (messages, how they were found); ([], how) when `mid` is absent.
    Gmail: its own conversation id, X-GM-THRID. Elsewhere: header search outward until no new id turns up, so a reply
    whose client dropped In-Reply-To and References cannot be found."""
    folder = _all_mail(M)
    _open_folder(M, folder)
    start = _search_uids(M, 'HEADER', 'Message-ID', f'"{_bracket(mid)}"')
    _, caps = M.capability()                       # after LOGIN: the pre-login list can lack extensions
    gmail = b'X-GM-EXT-1' in b' '.join(caps).upper().split()
    how = f'X-GM-THRID in {folder}' if gmail else f'References/In-Reply-To search in {folder}'
    if not start: return [], how
    if gmail:
        _, resp = M.uid('fetch', str(start[0]), '(X-GM-THRID)')
        thrid = re.search(rb'X-GM-THRID (\d+)', b' '.join(r[0] if isinstance(r, tuple) else r for r in resp)).group(1).decode()
        got = _fetch_by_uid(M, _search_uids(M, 'X-GM-THRID', thrid))
    else: got = _follow_headers(M, _fetch_by_uid(M, start))
    unique = {message_id(m) or f'#uid-{u}': m for u, m in sorted(got.items(), reverse=True)}   # duplicate copies: lowest UID kept
    return sorted(unique.values(), key=sent_at), how
