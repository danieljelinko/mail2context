"List the Drafts folder and delete exactly one draft by UID. Only the mailbox the server flags \\Drafts is ever opened (D-022)."
import imaplib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import tzinfo
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

from .mailbox import _quote, find_special_folder
from .render import extract_text
from .search import parse_flags
from .thread import sent_at

__all__ = ['Draft', 'delete_draft', 'find_drafts_folder', 'format_draft_row', 'list_drafts', 'parse_appenduid']

_RAISE_GUARD = 'the owner must raise it: sudo mail-guard 2 --for 10m'


@dataclass
class Draft:
    uid: int
    flags: set[str]
    msg: EmailMessage


def find_drafts_folder(M: imaplib.IMAP4) -> str:
    "The mailbox the server flags \\Drafts. Refuses rather than guess from a name."
    folder = find_special_folder(M, '\\Drafts')
    if not folder: raise SystemExit('no mailbox is flagged \\Drafts on this server — refusing to guess which one holds drafts')
    return folder


def _fetch(M: imaplib.IMAP4, uids: list[bytes]) -> list[Draft]:
    "Fetch `uids` from the selected mailbox with their flags. BODY.PEEK, so nothing is marked \\Seen."
    if not uids: return []
    _, resp = M.uid('fetch', b','.join(uids), '(UID FLAGS BODY.PEEK[])')
    return [Draft(int(re.search(rb'UID (\d+)', p[0]).group(1)), parse_flags(p[0]),
                  BytesParser(policy=policy.default).parsebytes(p[1]))
            for p in resp if isinstance(p, tuple)]


def list_drafts(M: imaplib.IMAP4) -> list[Draft]:
    "Every message in the Drafts folder, oldest first, read-only."
    M.select(_quote(find_drafts_folder(M)), readonly=True)
    _, data = M.uid('search', None, 'ALL')
    return _fetch(M, data[0].split() if data and data[0] else [])


def format_draft_row(d: Draft, tz: tzinfo) -> str:
    "Two lines: UID, local date, To, Subject; then the first line of the body."
    first = next((line.strip() for line in extract_text(d.msg).splitlines() if line.strip()), '(empty body)')
    return (f"  {d.uid:>6}  {sent_at(d.msg).astimezone(tz):%Y-%m-%d %H:%M}  To: {d.msg['To'] or '(nobody)'}  "
            f"Subject: {d.msg['Subject'] or '(no subject)'}\n          {first[:100]}")


def _check(resp: tuple[str, list], what: str) -> None:
    "Raise with the server's own words when `resp` is not OK; name the guard level when mail-guard refused."
    typ, data = resp
    if typ == 'OK': return
    text = data[0].decode('utf-8', 'replace') if data and data[0] else ''
    raise SystemExit(f"{what} refused: {typ} {text}" + (f' — mail-guard level is too low; {_RAISE_GUARD}' if 'guard:' in text else ''))


def delete_draft(M: imaplib.IMAP4, uid: int,
                 confirm: Callable[[Draft], bool],  # shown the draft before anything is written; False writes nothing
                 ) -> bool:
    "Expunge exactly one \\Draft-flagged message from the Drafts folder by UID. True when it was deleted."
    folder = find_drafts_folder(M)
    _, caps = M.capability()
    if b'UIDPLUS' not in b' '.join(caps).upper().split():
        raise SystemExit('server lacks UIDPLUS, so only a bare EXPUNGE is possible, which could take other messages — refusing')
    _check(M.select(_quote(folder)), f'SELECT {folder}')
    found = _fetch(M, [str(uid).encode()])
    if not found: raise SystemExit(f'UID {uid} is not in {folder} — see `just draft-list`')
    d = found[0]
    if '\\Draft' not in d.flags: raise SystemExit(f'UID {uid} in {folder} lacks the \\Draft flag — refusing to delete it')
    if not confirm(d): return False
    _check(M.uid('store', str(uid), '+FLAGS.SILENT', '(\\Deleted)'), f'STORE \\Deleted on UID {uid}')
    _check(M.uid('expunge', str(uid)), f'UID EXPUNGE {uid} (the draft is now flagged \\Deleted but still present)')
    if _fetch(M, [str(uid).encode()]): raise SystemExit(f'UID {uid} is still in {folder} after UID EXPUNGE')
    return True


def parse_appenduid(result: str) -> int | None:
    "The message UID from an `APPENDUID <uidvalidity> <uid>` answer; None when the server sent none."
    m = re.search(r'APPENDUID \d+ (\d+)', result)
    return int(m.group(1)) if m else None
