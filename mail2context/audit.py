"Audit what the HTML→text conversion loses. Bridge gives no ground truth, so we self-check."
import re
from email.message import EmailMessage

from bs4 import BeautifulSoup

from .render import extract_text, list_attachments, render_thread

__all__ = ['audit_messages', 'find_lost_chunks']

_CHUNK = re.compile(r'\S{8,}')      # long runs: robust to inline markup splitting words


def _squash(s: str) -> str: return re.sub(r'\s+', '', s or '')


def find_lost_chunks(html: str,      # source HTML of the message
                     rendered: str,  # what the renderer produced from it
                     ) -> list[str]:
    "Long text runs present in `html` but absent from `rendered`, compared whitespace-insensitively."
    soup = BeautifulSoup(html, 'html.parser')
    for bad in soup(['script', 'style', 'head']): bad.decompose()
    got, flat = _squash(rendered), _squash(soup.get_text(''))
    return [c for c in _CHUNK.findall(soup.get_text(' '))
            if _squash(c) in flat and _squash(c) not in got]


def audit_messages(msgs: list[EmailMessage]) -> dict[str, int]:
    "Count what extraction loses across `msgs`, with quote stripping off so nothing should go."
    rep = {'messages': len(msgs), 'text_chunks_lost': 0, 'messages_losing_text': 0,
           'urls_dropped': 0, 'alts_dropped': 0, 'attachments': 0, 'attachments_unnamed': 0}
    for m in msgs:
        out = extract_text(m, strip_quotes=False)
        html = m.get_body(('html',))
        if html:
            src = html.get_content()
            lost = find_lost_chunks(src, out)
            if lost:
                rep['text_chunks_lost'] += len(lost); rep['messages_losing_text'] += 1
            soup = BeautifulSoup(src, 'html.parser')
            rep['urls_dropped'] += sum(
                1 for a in soup.find_all('a')
                if (h := (a.get('href') or '')).startswith('http') and h not in out)
            rep['alts_dropped'] += sum(
                1 for i in soup.find_all('img')
                if (alt := (i.get('alt') or '').strip()) and alt not in out)
        names = list_attachments(m)
        if names:      # filenames surface in render_thread, not in the bare body text
            ctx = render_thread([m], strip_quotes=False)
            rep['attachments'] += len(names)
            rep['attachments_unnamed'] += sum(1 for n in names if n not in ctx)
    return rep
