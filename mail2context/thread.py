"Reconstruct mail threads from RFC 5322 headers (IMAP offers no THREAD extension)."
import hashlib
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

__all__ = ['group_threads', 'message_id', 'sent_at', 'thread_key']

_ID_RE = re.compile(r'<[^<>]+>')
_EPOCH = datetime.fromtimestamp(0, timezone.utc)


def sent_at(m: EmailMessage) -> datetime:
    "Date header as an aware UTC datetime; epoch when absent or unparseable."
    try: d = parsedate_to_datetime(m.get('Date', '') or '')
    except (TypeError, ValueError): return _EPOCH
    if d is None: return _EPOCH
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)  # naive dates would break sorting


def _find(parent: dict[str, str], k: str) -> str:
    "Union-find root of `k`, path-compressing as it climbs."
    while parent[k] != k: parent[k] = parent[parent[k]]; k = parent[k]
    return k


def _union(parent: dict[str, str], a: str, b: str) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb: parent[rb] = ra


def message_id(m: EmailMessage) -> str:
    "This message's Message-ID, or '' when the header is missing or malformed."
    found = _ID_RE.findall(m.get('Message-ID', '') or '')
    return found[0] if found else ''


def _own_id(m: EmailMessage, i: int) -> str:
    "This message's Message-ID, or a synthetic key when the header is missing or malformed."
    found = _ID_RE.findall(m.get('Message-ID', '') or '')
    return found[0] if found else f'#no-msgid-{i}'


def _linked_ids(m: EmailMessage) -> list[str]:
    "Every Message-ID this message points at, via In-Reply-To and the References chain."
    hdrs = ' '.join(h for h in (m.get('In-Reply-To', ''), m.get('References', '')) if h)
    return _ID_RE.findall(hdrs)


def group_threads(msgs: list[EmailMessage]) -> list[list[EmailMessage]]:
    "Group `msgs` into threads by their Message-ID / In-Reply-To / References links, each oldest-first."
    ids = [_own_id(m, i) for i, m in enumerate(msgs)]
    parent: dict[str, str] = {}
    for k in ids: parent.setdefault(k, k)
    for mid, m in zip(ids, msgs):
        for link in _linked_ids(m):
            parent.setdefault(link, link)
            _union(parent, mid, link)
    out: dict[str, list[EmailMessage]] = {}
    for mid, m in zip(ids, msgs): out.setdefault(_find(parent, mid), []).append(m)
    return [sorted(t, key=sent_at) for t in out.values()]


def thread_key(thread: list[EmailMessage]) -> str:
    "Short identifier for `thread`, from its earliest Message-ID so later replies do not change it."
    root = min(thread, key=sent_at)
    return hashlib.sha1(_own_id(root, 0).encode()).hexdigest()[:8]
