"Render mail into text/markdown context for an LLM."
import re
from email.message import EmailMessage

from bs4 import BeautifulSoup

__all__ = ['extract_text', 'list_attachments', 'render_thread']

_BLOCK_TAGS = ['p', 'div', 'br', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote']

# Wrappers each mail client puts around the text being replied to, or around a signature.
# Proton dominates this mailbox; the others cost nothing and appear in correspondents' mail.
_QUOTE_SELECTORS = ['.protonmail_quote', '.gmail_quote', '.gmail_signature',
                    '.moz-cite-prefix', '#divRplyFwdMsg', 'blockquote[type=cite]']

# Zimbra and Outlook quote with a bare header block carrying no class to select on, so the
# quoted original has to be cut at the text level instead. Matched conservatively: a lone
# "From:" is ordinary prose, and only counts as an attribution when more headers follow it.
_FROM_RE   = re.compile(r'^[ \t]*(?:De|From|Von|Da)\s*:\s*\S', re.I)
_FOLLOW_RE = re.compile(r'^[ \t]*(?:Envoy[ée]|Sent|Gesendet|À|To|Date|Objet|Subject|Cc)\s*:', re.I)
_WROTE_RE  = re.compile(r'^[ \t]*(?:Le|On)\b.{0,200}?(?:a\s+écrit|wrote)\s*:?\s*$', re.I)
_ORIG_RE   = re.compile(r"^[ \t]*-{2,}\s*(?:Original Message|Message d'origine)", re.I)


def _cut_at_attribution(text: str) -> str:
    "Drop everything from the first quoted-original attribution line onward."
    lines = text.splitlines()
    for i, line in enumerate(lines):
        starts_quote = (_WROTE_RE.match(line) or _ORIG_RE.match(line)
                        or (_FROM_RE.match(line)
                            and any(_FOLLOW_RE.match(x) for x in lines[i+1:i+5])))
        if starts_quote: return '\n'.join(lines[:i]).strip()
    return text


def _squash(s: str) -> str: return re.sub(r'\s+', '', s or '')


def _inline_links(soup) -> None:
    "Rewrite anchors as markdown so the link target survives flattening."
    for a in soup.find_all('a'):
        href = (a.get('href') or '').strip()
        if not href.startswith(('http://', 'https://', 'mailto:')): continue
        text = a.get_text(' ', strip=True)
        if text and _squash(text) != _squash(href): a.replace_with(f'[{text}]({href})')
        else:                                      a.replace_with(href)


def _inline_images(soup) -> None:
    "Keep image alt text, which often carries the only content of a graphical mail."
    for img in soup.find_all('img'):
        alt = (img.get('alt') or '').strip()
        img.replace_with(f'[image: {alt}]' if alt else '')


def _html_to_text(html: str, strip_quotes: bool) -> str:
    "Flatten `html` to text, optionally dropping quoted originals and signatures first."
    soup = BeautifulSoup(html, 'html.parser')
    for bad in soup(['script', 'style', 'head']): bad.decompose()
    if strip_quotes:
        for sel in _QUOTE_SELECTORS:
            for node in soup.select(sel): node.decompose()
    _inline_images(soup)     # before links: a linked image's alt is the anchor's only text
    _inline_links(soup)
    for tag in soup.find_all(_BLOCK_TAGS): tag.append('\n')
    return re.sub(r'\n{3,}', '\n\n', soup.get_text()).strip()


def extract_text(msg: EmailMessage, strip_quotes: bool = True) -> str:
    "Readable text of `msg`: its text/plain part, else its HTML flattened."
    plain = msg.get_body(('plain',))
    if plain:
        text = plain.get_content().strip()
        if text: return _cut_at_attribution(text) if strip_quotes else text  # empty plain part alongside HTML is common
    html = msg.get_body(('html',))
    if not html: return ''
    text = _html_to_text(html.get_content(), strip_quotes)
    return _cut_at_attribution(text) if strip_quotes else text


def list_attachments(msg: EmailMessage) -> list[str]:
    "Filenames of `msg`'s attachments, so a file-only mail is not rendered as empty."
    return [n for p in msg.iter_attachments() if (n := p.get_filename())]


def render_thread(msgs: list[EmailMessage], strip_quotes: bool = True) -> str:
    "Render an ordered thread as markdown: one attributed section per message."
    out: list[str] = []
    subj = next((m['Subject'] for m in msgs if m['Subject']), '(no subject)')
    out.append(f'# {subj}\n')
    for i, m in enumerate(msgs, 1):
        out.append(f"## {i}. {m['From'] or '(unknown sender)'} — {m['Date'] or '(no date)'}")
        if m['Subject'] and m['Subject'] != subj: out.append(f"*Subject:* {m['Subject']}")
        if m['To']: out.append(f"*To:* {m['To']}")
        if m['Cc']: out.append(f"*Cc:* {m['Cc']}")
        atts = list_attachments(m)
        if atts: out.append(f"*Attachments:* {', '.join(atts)}")
        body = extract_text(m, strip_quotes=strip_quotes)
        out.append('')
        out.append(body if body.strip() else '*(no text content)*')
        out.append('')
    return '\n'.join(out).strip() + '\n'
