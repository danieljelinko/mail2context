"""TEMPORARY round-trip assertions — D-011. Deleted with the send path at `01_plan.md` Phase 6.

Pure functions over already-fetched messages: no IMAP, no SMTP. They exist so the verdict of
`just verify-roundtrip` is itself testable — a checker that cannot fail proves nothing (see the
`bridge-status` row in `04_learnings.md`).
"""
import hashlib, re
from email.message import EmailMessage

from bs4 import BeautifulSoup

from .audit import audit_messages, find_lost_chunks
from .render import extract_text, html_to_text, render_thread
from .thread import group_threads, message_id, sent_at

__all__ = ['check_attachment', 'check_content', 'check_quote_stripping', 'check_reply_chain',
           'check_thread', 'content_body']

# thread.py keeps its own copy private; this module is deleted at Phase 6, so a local pattern is
# cheaper than widening that module's public surface for a temporary caller.
_IDS = re.compile(r'<[^<>]+>')
_MONO_OK = ('code', 'pre')     # the only elements the converter styles monospace on purpose


def _squash(s: str) -> str: return re.sub(r'\s+', '', s or '')


def check_thread(msgs: list[EmailMessage],
                 expected_ids: list[str],  # delivered Message-IDs, in the order they were sent
                 ) -> list[str]:
    "Problems rebuilding `msgs` into ONE thread holding `expected_ids` in order; empty means good."
    threads = group_threads(msgs)
    if len(threads) != 1:
        sizes = ', '.join(f'{len(t)} msg' for t in sorted(threads, key=len, reverse=True))
        return [f'rebuilt {len(threads)} threads ({sizes}), expected exactly 1']
    got = [message_id(m) for m in sorted(threads[0], key=sent_at)]
    if len(got) != len(expected_ids):
        return [f'thread holds {len(got)} messages, expected {len(expected_ids)}']
    if got != expected_ids:
        return [f'thread order differs from send order:\n  got  {got}\n  want {expected_ids}']
    return []


def check_reply_chain(msgs: list[EmailMessage],
                      expected_ids: list[str],  # delivered Message-IDs, in the order they were sent
                      ) -> list[str]:
    "Problems in the DELIVERED In-Reply-To/References of `expected_ids`; empty means they survived."
    by_id = {message_id(m): m for m in msgs}
    problems = []
    for i, mid in enumerate(expected_ids[1:], start=1):
        m = by_id.get(mid)
        if m is None: problems.append(f'step {i + 1}: {mid} never arrived'); continue
        irt = _IDS.findall(m.get('In-Reply-To', '') or '')
        if expected_ids[i - 1] not in irt:
            problems.append(f'step {i + 1}: In-Reply-To is {irt or "ABSENT"}, '
                            f'expected {expected_ids[i - 1]}')
        refs = _IDS.findall(m.get('References', '') or '')
        if missing := [e for e in expected_ids[:i] if e not in refs]:
            problems.append(f'step {i + 1}: References is missing {missing} (has {refs or "ABSENT"})')
    return problems


def content_body(token: str) -> str:
    "Markdown body exercising every feature `render_markdown` supports, with accents, carrying `token`."
    return f"""# Rapport de fidélité du contenu

Ce message est envoyé automatiquement sous D-011 pour vérifier la **fidélité du contenu** en transit — accents compris : à, é, è, ê, ç, ï, œ, « guillemets » et l'apostrophe typographique ’.

## Mise en forme en ligne

Du **gras**, de l'*italique*, du `code en ligne`, et un lien vers [le site AI4HU](https://ai4hu.org/).

## Listes

- premier élément à puce
- deuxième élément, avec du **gras** et de l'*italique*
- troisième élément

1. première étape numérotée
2. deuxième étape numérotée
3. troisième étape numérotée

## Citation et code

> Une citation en bloc, comme un extrait d'un courriel précédent.

```
def saluer(nom): return f"Bonjour {{nom}} !"
```

## Tableau

| Colonne A | Colonne B |
|---|---|
| cellule-A1 | cellule-B1 |
| cellule-A2 | cellule-B2 |

---

### Jeton de vérification

{token}

Ce message sera supprimé une fois la vérification terminée."""


def check_content(delivered: EmailMessage,
                  sent: EmailMessage,
                  accent_color: str,  # CSS colour the signature's "4" must still carry, e.g. "rgb(59, 131, 194)"
                  ) -> list[str]:
    "Problems in `delivered` against `sent`: lost text, drifted plain part, lost colour, monospace body."
    html = delivered.get_body(('html',))
    if html is None: return ['delivered copy has no text/html part — it would render monospace']
    src, src_sent = html.get_content(), sent.get_body(('html',)).get_content()
    problems = []
    rep = audit_messages([delivered])
    problems += [f'audit: {k} = {v}' for k, v in rep.items()
                 if v and k in ('text_chunks_lost', 'urls_dropped', 'alts_dropped', 'attachments_unnamed')]
    got = html_to_text(src, strip_quotes=False)
    if lost := find_lost_chunks(src_sent, got):
        problems.append(f'delivered HTML lost text that was sent: {lost}')
    elif _squash(got) != _squash(html_to_text(src_sent, strip_quotes=False)):
        problems.append('delivered HTML reads differently from what was sent (nothing lost, something added)')
    plain, plain_sent = delivered.get_body(('plain',)), sent.get_body(('plain',))
    if plain is None or _squash(plain.get_content()) != _squash(plain_sent.get_content()):
        problems.append('delivered text/plain part differs from the one sent')
    soup = BeautifulSoup(src, 'html.parser')
    if not any(accent_color in (t.get('style') or '') and t.get_text(strip=True) == '4'
               for t in soup.find_all(True)):
        problems.append(f'no element styled {accent_color} wraps the signature\'s 4 any more')
    problems += [f'<{t.name}> is styled monospace, so the body would not render proportionally'
                 for t in soup.find_all(True)
                 if 'monospace' in (t.get('style') or '').lower() and t.name not in _MONO_OK]
    return problems


def check_attachment(delivered: EmailMessage,
                     filename: str,
                     sha256: str,  # hex digest of the bytes attached at send time
                     ) -> list[str]:
    "Problems with `filename` on `delivered`: absent, not surfaced by the renderer, or bytes changed."
    atts = {n: p for p in delivered.iter_attachments() if (n := p.get_filename())}
    if filename not in atts:
        return [f"attachment {filename!r} did not arrive (delivered: {', '.join(atts) or 'none'})"]
    problems = []
    if filename not in render_thread([delivered], strip_quotes=False):
        problems.append(f'attachment {filename!r} is not surfaced by render_thread')
    data = atts[filename].get_payload(decode=True)
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        problems.append(f'attachment {filename!r} sha256 {got[:12]}… differs from sent {sha256[:12]}… '
                        f'({len(data)} bytes delivered)')
    return problems


def check_quote_stripping(reply: EmailMessage,
                          quoted_markers: list[str],  # text only the quoted original carries
                          quote_class: str,           # wrapper class the provider's UI emits, e.g. "gmail_quote"
                          ) -> list[str]:
    "Problems stripping a REAL web-UI quote from `reply`: markers must show raw and vanish stripped."
    problems = []
    html = reply.get_body(('html',))
    src = html.get_content() if html else ''
    if quote_class not in src: problems.append(f'{quote_class} block not present in the delivered HTML')
    raw = extract_text(reply, strip_quotes=False)
    problems += [f'raw rendition lacks {m!r}: the quote was never there, so there is nothing to strip'
                 for m in quoted_markers if m not in raw]
    stripped = extract_text(reply, strip_quotes=True)
    if not stripped.strip(): problems.append('nothing left after stripping — the reply itself was removed')
    problems += [f'{m!r} survived stripping in extract_text' for m in quoted_markers if m in stripped]
    if html:
        via_html = html_to_text(src, strip_quotes=True)
        problems += [f'{m!r} survived stripping in the html path' for m in quoted_markers if m in via_html]
    return problems
