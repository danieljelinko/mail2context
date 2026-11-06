"Compose replies as RFC 5322 messages. Drafts only — nothing here sends (D-003)."
import html as _html
import mimetypes
import re
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid
from pathlib import Path

from .markdown_mail import render_markdown

__all__ = ['build_message', 'build_reply', 'describe_attachments', 'expand_attachment_paths', 'list_participants']

# Autoresponders and forwards stack markers onto the subject; strip them all, then add one Re:.
_NOISE_PREFIX = re.compile(r'^\s*((re|fwd?|tr|auto|automatic reply)\s*:\s*)+', re.I)


def _as_html(body: str) -> str:
    "Minimal HTML for `body`: blank lines start paragraphs, single newlines are breaks."
    paras = [p for p in re.split(r'\n\s*\n', body.strip()) if p.strip()]
    return '\n'.join('<p>' + '<br>'.join(_html.escape(ln) for ln in p.splitlines()) + '</p>'
                      for p in paras)


def _set_body(m: EmailMessage,
              body: str,
              markdown: bool,
              sig_text: str | None,   # signature for the plain part
              sig_html: str | None,   # signature for the HTML part, styling preserved verbatim
              ) -> None:
    "Set the plain body plus an HTML alternative, so clients do not render it monospace."
    plain = f'{body.rstrip()}\n\n{sig_text.rstrip()}\n' if sig_text else body
    m.set_content(plain)                           # plain part stays the markdown source
    html = render_markdown(body) if markdown else _as_html(body)
    if sig_html: html += f'\n{sig_html.strip()}'
    m.add_alternative(html, subtype='html')


def _attach_files(m: EmailMessage, paths: list[Path]) -> None:
    "Attach each file under its basename, typed from its extension (octet-stream when unknown)."
    for p in map(Path, paths):
        ctype = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        m.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)


def expand_attachment_paths(paths: list[Path]) -> list[Path]:  # files, or folders to attach whole
    "Files as given; a folder becomes its files in name order. Fails on a missing path or an empty folder."
    out = []
    for p in map(Path, paths):
        if not p.exists(): raise FileNotFoundError(f"attachment not found: {p}")
        if not p.is_dir(): out.append(p); continue
        files = sorted((f for f in p.iterdir() if f.is_file()), key=lambda f: f.name)
        if not files: raise ValueError(f"no files to attach in folder {p}")
        out += files
    return out


def _format_size(n: int) -> str: return f"{n} B" if n < 1024 else f"{n/1024:.1f} KB" if n < 1024**2 else f"{n/1024**2:.1f} MB"


def describe_attachments(paths: list[Path]) -> list[str]:
    "One line per file with its size, then the count and total, for previews."
    sizes = [(p.name, p.stat().st_size) for p in map(Path, paths)]
    total = sum(n for _, n in sizes)
    return ([f"attach  : {name} ({_format_size(n)})" for name, n in sizes] +
            [f"attached: {len(sizes)} files, {_format_size(total)} (base64 on the wire: ~{_format_size(total*4//3)})"])


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
                markdown: bool = True,       # render the body as markdown
                signature_text: str | None = None,
                signature_html: str | None = None,
                *,
                attachments: list[Path],     # files to attach; [] for none
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
    _set_body(m, body, markdown, signature_text, signature_html)
    _attach_files(m, attachments)
    return m


def build_message(to: str,        # one address, or several comma-separated
                  subject: str,
                  body: str,
                  frm: str,
                  cc: str | None = None,
                  markdown: bool = True,
                  signature_text: str | None = None,
                  signature_html: str | None = None,
                  *,
                  attachments: list[Path]) -> EmailMessage:  # files to attach; [] for none
    "Build a new message that threads to nothing — a fresh conversation, not a reply."
    m = EmailMessage()
    m['From'], m['To'], m['Subject'] = frm, to, subject
    if cc: m['Cc'] = cc
    m['Date'] = formatdate(localtime=True)
    m['Message-ID'] = make_msgid()
    _set_body(m, body, markdown, signature_text, signature_html)
    _attach_files(m, attachments)
    return m

