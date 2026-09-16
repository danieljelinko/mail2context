"Build IMAP SEARCH criteria, and read message flags out of FETCH responses."
import re
from datetime import datetime
from email.message import EmailMessage

__all__ = ['FLAGS_HEADER', 'annotate_flags', 'build_search_criteria', 'flags_of', 'is_unread', 'parse_flags']

_FLAGS_RE = re.compile(rb'FLAGS \(([^)]*)\)')
_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _imap_date(iso: str) -> str:
    "IMAP wants DD-Mon-YYYY; callers speak ISO."
    try: d = datetime.strptime(iso, '%Y-%m-%d')  # noqa: DTZ007 — IMAP dates are date-only, no zone
    except ValueError as e: raise ValueError(f"date must be YYYY-MM-DD, got {iso!r}") from e
    return f'{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}'


def build_search_criteria(frm: str | None = None,       # substring of the From header
                          to: str | None = None,        # substring of the To header
                          subject: str | None = None,
                          text: str | None = None,      # substring anywhere, headers or body
                          since: str | None = None,     # ISO date, inclusive lower bound
                          before: str | None = None,    # ISO date, exclusive upper bound
                          unread: bool = False,
                          flagged: bool = False,
                          unanswered: bool = False) -> list[str]:
    "IMAP SEARCH criteria for the given filters; `['ALL']` when none are set."
    crit: list[str] = []
    if unread:     crit.append('UNSEEN')
    if flagged:    crit.append('FLAGGED')
    if unanswered: crit.append('UNANSWERED')
    for key, val in (('FROM', frm), ('TO', to), ('SUBJECT', subject), ('TEXT', text)):
        if val: crit += [key, val]
    for key, val in (('SINCE', since), ('BEFORE', before)):
        if val: crit += [key, _imap_date(val)]
    return crit or ['ALL']


def parse_flags(line: bytes) -> set[str]:
    "IMAP flags from a FETCH response header line, e.g. `{'\\\\Seen', '\\\\Answered'}`."
    m = _FLAGS_RE.search(line)
    return set(m.group(1).decode('ascii', 'replace').split()) if m else set()


# IMAP flags are mailbox state, not part of the message, but every layer downstream takes an
# EmailMessage — so they ride along as a synthetic header rather than changing every signature.
FLAGS_HEADER = 'X-M2C-Flags'


def annotate_flags(msg: EmailMessage, flags: set[str]) -> None:
    "Record `flags` on `msg`, replacing any previous annotation."
    del msg[FLAGS_HEADER]                     # del on a missing header is a no-op here
    msg[FLAGS_HEADER] = ' '.join(sorted(flags))


def flags_of(msg: EmailMessage) -> set[str]:
    "IMAP flags recorded on `msg`, empty when it was fetched without them."
    return set((msg.get(FLAGS_HEADER) or '').split())


def is_unread(msg: EmailMessage) -> bool:
    "Whether `msg` is unread. False when flags were never fetched — absence is not evidence."
    f = flags_of(msg)
    return bool(f) and '\\Seen' not in f
