"Compose replies as RFC 5322 messages. Drafts only — nothing here sends (D-003)."
import re
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid

__all__ = ['build_reply', 'list_participants']

# Autoresponders and forwards stack markers onto the subject; strip them all, then add one Re:.
_NOISE_PREFIX = re.compile(r'^\s*((re|fwd?|tr|auto|automatic reply)\s*:\s*)+', re.I)


def _reply_subject(subj: str) -> str:
    "Prefix `subj` with a single Re:, dropping any stacked Re:/Fwd:/Auto: markers."
    return 'Re: ' + _NOISE_PREFIX.sub('', subj or '(no subject)').strip()


def list_participants(thread: list[EmailMessage], me: str) -> list[str]:
    "Every address appearing in `thread`, except `me`. Use to show who a reply would omit."
    seen: dict[str, None] = {}
    for m in thread:
        for hdr in ('From', 'To', 'Cc'):
            for _, addr in getaddresses([m.get(hdr) or '']):
                if addr and addr.lower() != me.lower(): seen.setdefault(addr, None)
    return list(seen)


def _reply_refs(last: EmailMessage) -> str:
    "References chain for a reply to `last`: its own chain plus its Message-ID."
    prior = (last.get('References') or last.get('In-Reply-To') or '').split()
    mid = last.get('Message-ID')
    return ' '.join([*prior, mid] if mid and mid not in prior else prior)


def build_reply(thread: list[EmailMessage],  # ordered oldest-first
                body: str,
                frm: str,
                to: str | None = None,       # override the default reply-to-last-sender
                reply_all: bool = False,     # Cc everyone else in the thread
                ) -> EmailMessage:
    "Build a reply to the last message of `thread`, threaded via In-Reply-To/References."
    last = thread[-1]
    src = last.get('Reply-To') or last.get('From') or ''
    # Replying to our own last message (chasing an unanswered mail) must not address ourselves:
    # fall back to whoever that message went to, which is what a mail client does.
    if frm.lower() in src.lower(): src = last.get('To') or src
    addrs = getaddresses([src])
    m = EmailMessage()
    m['From'] = frm
    m['To'] = to or ', '.join(a for _, a in addrs if a)
    if reply_all:
        direct = {a.lower() for a in (m['To'] or '').split(', ') if a}
        cc = [a for a in list_participants(thread, frm) if a.lower() not in direct]
        if cc: m['Cc'] = ', '.join(cc)
    m['Subject'] = _reply_subject(last.get('Subject'))
    m['Date'] = formatdate(localtime=True)
    m['Message-ID'] = make_msgid()
    if last.get('Message-ID'): m['In-Reply-To'] = last['Message-ID']
    refs = _reply_refs(last)
    if refs: m['References'] = refs
    m.set_content(body)
    return m
