"Compose replies as RFC 5322 messages. Drafts only — nothing here sends (D-003)."
import re
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid

__all__ = ['build_reply']

_RE_PREFIX = re.compile(r'^\s*(re\s*:\s*)+', re.I)


def _reply_subject(subj: str) -> str:
    "Prefix `subj` with a single Re:, however many it already carries."
    return 'Re: ' + _RE_PREFIX.sub('', subj or '(no subject)').strip()


def _reply_refs(last: EmailMessage) -> str:
    "References chain for a reply to `last`: its own chain plus its Message-ID."
    prior = (last.get('References') or last.get('In-Reply-To') or '').split()
    mid = last.get('Message-ID')
    return ' '.join([*prior, mid] if mid and mid not in prior else prior)


def build_reply(thread: list[EmailMessage],  # ordered oldest-first
                body: str,
                frm: str,
                to: str | None = None) -> EmailMessage:  # override the default reply-to-sender
    "Build a reply to the last message of `thread`, threaded via In-Reply-To/References."
    last = thread[-1]
    addrs = getaddresses([last.get('Reply-To') or last.get('From') or ''])
    m = EmailMessage()
    m['From'] = frm
    m['To'] = to or ', '.join(a for _, a in addrs if a)
    m['Subject'] = _reply_subject(last.get('Subject'))
    m['Date'] = formatdate(localtime=True)
    m['Message-ID'] = make_msgid()
    if last.get('Message-ID'): m['In-Reply-To'] = last['Message-ID']
    refs = _reply_refs(last)
    if refs: m['References'] = refs
    m.set_content(body)
    return m
