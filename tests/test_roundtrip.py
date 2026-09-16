import hashlib, time
from email.message import EmailMessage
from email.utils import formatdate

import pytest

from mail2context.markdown_mail import render_markdown
from mail2context.roundtrip import check_reply_chain, check_thread

BASE = time.mktime((2026, 9, 16, 10, 0, 0, 0, 0, -1))


@pytest.fixture
def make_chain():
    "Factory: `n` messages linked as a reply chain, oldest first, an hour apart."
    def _build(n: int, subject: str = 'm2c roundtrip zz9') -> list[EmailMessage]:
        msgs = []
        for i in range(n):
            m = EmailMessage()
            m['Message-ID'] = f'<step{i}@example.org>'
            m['Subject'] = subject if i == 0 else f'Re: {subject}'
            m['Date'] = formatdate(BASE + i * 3600)
            if i:
                m['In-Reply-To'] = f'<step{i - 1}@example.org>'
                m['References'] = ' '.join(f'<step{j}@example.org>' for j in range(i))
            m.set_content(f'step {i}')
            msgs.append(m)
        return msgs
    return _build


def ids_of(msgs: list[EmailMessage]) -> list[str]:
    "The Message-IDs of `msgs`, in the order given."
    return [m['Message-ID'] for m in msgs]


def test_check_thread_reports_no_problems_when_six_linked_messages_rebuild_as_one_thread(make_chain):
    # Given six messages forming one proper reply chain
    msgs = make_chain(6)

    # When we check them against the order they were sent in
    problems = check_thread(msgs, ids_of(msgs))

    # Then nothing is wrong
    assert problems == []


def test_check_thread_reports_a_split_when_the_LAST_reply_loses_its_threading_headers(make_chain):
    # Given six messages whose final reply has had its chain stripped — nothing later can name it
    msgs = make_chain(6)
    del msgs[5]['In-Reply-To'], msgs[5]['References']

    # When we check them against the order they were sent in
    problems = check_thread(msgs, ids_of(msgs))

    # Then the checker reports the split rather than passing
    assert problems and 'rebuilt 2 threads' in problems[0]


def test_check_thread_finds_one_thread_when_a_MIDDLE_reply_is_stripped_but_later_ones_name_it(make_chain):
    # Given six messages where the fourth lost its chain, while the fifth and sixth still carry
    # References naming every earlier message
    msgs = make_chain(6)
    del msgs[3]['In-Reply-To'], msgs[3]['References']

    # When we check them
    problems = check_thread(msgs, ids_of(msgs))

    # Then the thread is still whole — a later reply's References heals the gap, so a broken
    # middle message is NOT observable; only an orphaned last message splits a thread
    assert problems == []


def test_check_thread_reports_send_order_intact_when_the_messages_are_fetched_out_of_order(make_chain):
    # Given the six messages shuffled, as a mailbox fetch may well return them
    msgs = make_chain(6)
    fetched = [msgs[3], msgs[0], msgs[5], msgs[1], msgs[4], msgs[2]]

    # When we check the shuffled list against the send order
    problems = check_thread(fetched, ids_of(msgs))

    # Then order is recovered from Date, not from fetch order
    assert problems == []


def test_check_thread_reports_the_shortfall_when_a_message_never_arrived(make_chain):
    # Given only five of the six messages, the last one still missing
    msgs = make_chain(6)

    # When we check the five against all six expected ids
    problems = check_thread(msgs[:5], ids_of(msgs))

    # Then the shortfall is named rather than silently accepted
    assert problems == ['thread holds 5 messages, expected 6']


def test_check_reply_chain_reports_no_problems_when_every_reply_names_its_parent(make_chain):
    # Given six messages whose In-Reply-To and References arrived intact
    msgs = make_chain(6)

    # When we check the delivered chain
    problems = check_reply_chain(msgs, ids_of(msgs))

    # Then nothing is wrong
    assert problems == []


def test_check_reply_chain_names_the_step_whose_in_reply_to_was_stripped_in_transit(make_chain):
    # Given a delivered chain where step 4 arrived with no In-Reply-To — the shape D-009 records
    # for Proton draft APPEND, here asked of a real send
    msgs = make_chain(6)
    del msgs[3]['In-Reply-To']

    # When we check the delivered chain
    problems = check_reply_chain(msgs, ids_of(msgs))

    # Then that step is named, with what it should have carried
    assert problems == ['step 4: In-Reply-To is ABSENT, expected <step2@example.org>']


def test_check_reply_chain_names_the_ancestors_a_truncated_references_header_dropped(make_chain):
    # Given a delivered chain whose last reply kept only its immediate parent in References
    msgs = make_chain(6)
    msgs[5].replace_header('References', '<step4@example.org>')

    # When we check the delivered chain
    problems = check_reply_chain(msgs, ids_of(msgs))

    # Then the dropped ancestors are named rather than the header passing as present
    assert len(problems) == 1 and 'References is missing' in problems[0]


# --- Phase 3: content fidelity -----------------------------------------------------------

from email import policy
from email.parser import BytesParser

from bs4 import BeautifulSoup

from mail2context.compose import build_message
from mail2context.roundtrip import (check_attachment, check_content, check_quote_stripping,
                                    content_body)

SIG_HTML = ('<div><span>Dani JELINKO</span></div><div><span>AI</span>'
            '<span style="color: rgb(59, 131, 194);">4</span><span>HU | AI for humans</span></div>')
SIG_TEXT = 'Dani JELINKO\nAI4HU | AI for humans'
BLUE = 'rgb(59, 131, 194)'


def test_content_body_renders_every_markdown_feature_the_converter_supports():
    # Given the body the content round-trip sends
    html = render_markdown(content_body('m2c-ct-zz9-from-proton'))
    soup = BeautifulSoup(html, 'html.parser')

    # When we look at what it rendered to
    tags = {t.name for t in soup.find_all(True)}

    # Then every block and inline feature is present, so the round-trip exercises all of them
    assert {'h1', 'h2', 'h3', 'strong', 'em', 'code', 'pre', 'a', 'ul', 'ol', 'li',
            'blockquote', 'table', 'th', 'td', 'hr'} <= tags
    assert soup.find('a')['href'].startswith('https://')


def test_content_body_carries_accented_text_and_its_token():
    # Given the body for a token
    body = content_body('m2c-ct-zz9-from-proton')

    # Then it carries French accents, typographic punctuation and the token on its own line
    assert all(ch in body for ch in 'éèêàçïœ«»')
    assert '\nm2c-ct-zz9-from-proton\n' in body


@pytest.fixture
def make_rich_pair():
    "Factory: the rich-content message as sent, and its copy as a recipient would fetch it."
    def _build(mutate=None) -> tuple[EmailMessage, EmailMessage]:
        sent = build_message(to='daniel.jelinko@gmail.com', subject='m2c content zz9',
                             body=content_body('m2c-ct-zz9-from-proton'), frm='dj@ai4hu.org',
                             signature_text=SIG_TEXT, signature_html=SIG_HTML)
        raw = sent.as_bytes()
        if mutate: raw = mutate(raw)
        delivered = BytesParser(policy=policy.default).parsebytes(raw)
        return sent, delivered
    return _build


def _b64_swap(old: str, new: str):
    "Mutator: rewrite `old` to `new` inside the message's HTML part, re-encoding its base64."
    def _mutate(raw: bytes) -> bytes:
        m = BytesParser(policy=policy.default).parsebytes(raw)
        html = m.get_body(('html',))
        assert old in html.get_content()
        html.set_content(html.get_content().replace(old, new), subtype='html')
        return m.as_bytes()
    return _mutate


def test_check_content_reports_no_problems_when_the_delivered_copy_matches_what_was_sent(make_rich_pair):
    # Given the rich message and a delivered copy that survived transit byte for byte
    sent, delivered = make_rich_pair()

    # When we check the delivered copy against what was sent
    problems = check_content(delivered, sent, accent_color=BLUE)

    # Then nothing is wrong
    assert problems == []


def test_check_content_names_text_the_delivered_html_lost(make_rich_pair):
    # Given a delivered copy whose HTML part lost one table cell in transit
    sent, delivered = make_rich_pair(_b64_swap('cellule-B2', ''))

    # When we check it
    problems = check_content(delivered, sent, accent_color=BLUE)

    # Then the lost run is named
    assert any('cellule-B2' in p for p in problems)


def test_check_content_reports_the_signature_colour_when_transit_stripped_it(make_rich_pair):
    # Given a delivered copy whose blue 4 lost its colour
    sent, delivered = make_rich_pair(_b64_swap(f'color: {BLUE};', ''))

    # When we check it
    problems = check_content(delivered, sent, accent_color=BLUE)

    # Then the missing colour is reported
    assert any(BLUE in p for p in problems)


def test_check_content_reports_a_body_that_would_render_monospace(make_rich_pair):
    # Given a delivered copy whose wrapper font became monospace, as a plain-text-only draft reads
    sent, delivered = make_rich_pair(_b64_swap('Arial, Helvetica, sans-serif', 'monospace'))

    # When we check it
    problems = check_content(delivered, sent, accent_color=BLUE)

    # Then the monospace body is reported
    assert any('monospace' in p for p in problems)


def test_check_content_reports_a_delivered_copy_with_no_html_part(make_rich_pair):
    # Given a delivered copy reduced to its plain part alone
    sent, delivered = make_rich_pair()
    plain = EmailMessage(); plain['Subject'] = delivered['Subject']
    plain.set_content(delivered.get_body(('plain',)).get_content())

    # When we check it
    problems = check_content(plain, sent, accent_color=BLUE)

    # Then the absence is reported rather than passing as "no HTML to fault"
    assert any('no text/html' in p for p in problems)


def test_check_content_reports_a_plain_part_that_differs_from_the_one_sent(make_rich_pair):
    # Given a delivered copy whose plain part was rewritten in transit
    sent, delivered = make_rich_pair()
    delivered.get_body(('plain',)).set_content('quelque chose d\'autre')

    # When we check it
    problems = check_content(delivered, sent, accent_color=BLUE)

    # Then the plain-part drift is reported
    assert any('plain' in p for p in problems)


ATT_BYTES = 'Pièce jointe de vérification — œuvre, çà et là.\n'.encode() * 40


def _with_attachment(msg: EmailMessage, data: bytes = ATT_BYTES,
                     name: str = 'm2c-content-zz9.txt') -> EmailMessage:
    "Attach `data` as `name` and return the message as a recipient would fetch it."
    msg.add_attachment(data, maintype='text', subtype='plain', filename=name)
    return BytesParser(policy=policy.default).parsebytes(msg.as_bytes())


def test_check_attachment_reports_no_problems_when_name_surfaces_and_bytes_match(make_rich_pair):
    # Given a delivered copy carrying the attachment exactly as sent
    sent, _ = make_rich_pair()
    delivered = _with_attachment(sent)

    # When we check it against the name and digest recorded at send time
    problems = check_attachment(delivered, 'm2c-content-zz9.txt', hashlib.sha256(ATT_BYTES).hexdigest())

    # Then nothing is wrong
    assert problems == []


def test_check_attachment_reports_a_digest_mismatch_when_the_bytes_changed_in_transit(make_rich_pair):
    # Given a delivered copy whose attachment lost its last line
    sent, _ = make_rich_pair()
    delivered = _with_attachment(sent, data=ATT_BYTES[:-10])

    # When we check it against the digest of what was sent
    problems = check_attachment(delivered, 'm2c-content-zz9.txt', hashlib.sha256(ATT_BYTES).hexdigest())

    # Then the mismatch is named, with the byte counts
    assert len(problems) == 1 and 'sha256' in problems[0] and f'{len(ATT_BYTES) - 10} bytes' in problems[0]


def test_check_attachment_reports_an_attachment_that_never_arrived(make_rich_pair):
    # Given a delivered copy with no attachment at all
    _, delivered = make_rich_pair()

    # When we check it
    problems = check_attachment(delivered, 'm2c-content-zz9.txt', hashlib.sha256(ATT_BYTES).hexdigest())

    # Then the absence is named
    assert problems == ["attachment 'm2c-content-zz9.txt' did not arrive (delivered: none)"]


def test_check_attachment_reports_a_name_the_rendered_thread_does_not_surface(make_rich_pair):
    # Given a delivered copy whose attachment arrived with its filename stripped
    sent, _ = make_rich_pair()
    delivered = _with_attachment(sent)
    att = next(delivered.iter_attachments())
    del att['Content-Disposition']; att['Content-Disposition'] = 'attachment'

    # When we check it
    problems = check_attachment(delivered, 'm2c-content-zz9.txt', hashlib.sha256(ATT_BYTES).hexdigest())

    # Then the name is reported missing rather than the bytes silently passing
    assert any('did not arrive' in p for p in problems)


def _quoted_reply(quote_class: str, own_text: str, quoted_html: str, plain_quote: str) -> EmailMessage:
    "A web-UI reply: plain part with an attribution line, HTML part with a classed quote block."
    m = EmailMessage()
    m['Subject'] = 'Re: m2c content zz9'
    m.set_content(f'{own_text}\n\nOn Wed, 16 Sep 2026, Dani wrote:\n> {plain_quote}\n')
    m.add_alternative(f'<div dir="ltr">{own_text}</div><br><div class="{quote_class}">'
                      f'<div>On Wed, 16 Sep 2026, Dani wrote:</div><blockquote>{quoted_html}'
                      f'</blockquote></div>', subtype='html')
    return BytesParser(policy=policy.default).parsebytes(m.as_bytes())


def test_check_quote_stripping_reports_no_problems_when_the_quote_is_removed_and_the_reply_kept():
    # Given a Gmail-style reply quoting the rich message under a gmail_quote block
    reply = _quoted_reply('gmail_quote', 'Merci, bien reçu.',
                          '<h1>Rapport de fidélité</h1><p>cellule-A1 m2c-ct-zz9-from-proton</p>',
                          'cellule-A1 m2c-ct-zz9-from-proton')

    # When we check stripping against markers only the quoted original carries
    problems = check_quote_stripping(reply, ['cellule-A1', 'm2c-ct-zz9-from-proton'], 'gmail_quote')

    # Then nothing is wrong
    assert problems == []


def test_check_quote_stripping_reports_a_marker_that_survived_stripping_in_the_html_path():
    # Given a reply whose quote block carries a class the stripper does not know
    reply = _quoted_reply('some_other_quote', 'Merci.', '<p>cellule-A1 m2c-ct-zz9-from-proton</p>',
                          'cellule-A1 m2c-ct-zz9-from-proton')

    # When we check stripping, naming the class the provider was expected to emit
    problems = check_quote_stripping(reply, ['cellule-A1'], 'gmail_quote')

    # Then both the missing class and the surviving marker are reported
    assert any('gmail_quote' in p and 'not present' in p for p in problems)
    assert any('cellule-A1' in p and 'html' in p for p in problems)


def test_check_quote_stripping_reports_when_the_raw_rendition_lacks_the_quote():
    # Given a reply whose quote block is empty — the provider quoted nothing
    reply = _quoted_reply('gmail_quote', 'Merci.', '', '')

    # When we check stripping
    problems = check_quote_stripping(reply, ['cellule-A1'], 'gmail_quote')

    # Then the check refuses to pass vacuously: a quote that was never there cannot prove stripping
    assert any('raw' in p and 'cellule-A1' in p for p in problems)


def test_check_quote_stripping_reports_an_empty_result_when_stripping_ate_the_reply_itself():
    # Given a reply whose own text sits INSIDE the quote block, so stripping removes everything
    m = EmailMessage(); m['Subject'] = 'Re: x'
    m.set_content('On Wed, 16 Sep 2026, Dani wrote:\n> cellule-A1\n')
    m.add_alternative('<div class="gmail_quote"><p>Merci.</p><p>cellule-A1</p></div>', subtype='html')
    reply = BytesParser(policy=policy.default).parsebytes(m.as_bytes())

    # When we check stripping
    problems = check_quote_stripping(reply, ['cellule-A1'], 'gmail_quote')

    # Then the empty result is reported, not counted as a clean strip
    assert any('nothing left' in p for p in problems)
