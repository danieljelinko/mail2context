from collections.abc import Callable
from email.message import EmailMessage

import pytest

from mail2context.render import extract_text


@pytest.fixture
def make_mail() -> Callable[..., EmailMessage]:
    "Factory: build an `EmailMessage` with a plain body, an HTML body, or both."
    def _build(text: str | None = None, html: str | None = None) -> EmailMessage:
        m = EmailMessage()
        m['Subject'], m['From'] = 'S', 'a@x'
        if text is not None and html is not None:
            m.set_content(text); m.add_alternative(html, subtype='html')
        elif html is not None: m.set_content(html, subtype='html')  #HTML-only: no plain part at all
        elif text is not None: m.set_content(text)
        return m
    return _build


def test_extract_text_returns_plain_part_when_message_has_one(make_mail):
    # Given a message carrying a text/plain body
    m = make_mail(text='Hello there')

    # When we extract its text
    out = extract_text(m)

    # Then the plain body comes back verbatim
    assert out == 'Hello there'


def test_extract_text_converts_html_when_no_plain_part_exists(make_mail):
    # Given an HTML-only message, as 85/120 of the real mailbox turned out to be
    m = make_mail(html='<p>First line</p><p>Second line</p>')

    # When we extract its text
    out = extract_text(m)

    # Then the markup is flattened to readable lines
    assert out == 'First line\nSecond line'


def test_extract_text_drops_quoted_original_when_stripping_is_on(make_mail):
    # Given an HTML reply whose quoted original sits in a protonmail_quote block
    m = make_mail(html='<p>My answer</p>'
                       '<div class="protonmail_quote"><p>Original message text</p></div>')

    # When we extract with quote stripping on
    out = extract_text(m, strip_quotes=True)

    # Then only the newly written content survives
    assert out == 'My answer'


def test_extract_text_cuts_at_attribution_block_when_client_quotes_without_markup(make_mail):
    # Given a reply whose quoted original is a bare De:/Envoyé: block (Zimbra and Outlook do this)
    m = make_mail(html='<p>Bonjour, voici ma réponse.</p>'
                       '<p>De: Someone &lt;a@b.fr&gt;<br>'
                       'Envoyé: lundi 8 juin 2026 11:18<br>'
                       'À: Dani<br>Objet: Re: sujet</p>'
                       '<p>Texte original cité</p>')

    # When we extract with stripping on
    out = extract_text(m, strip_quotes=True)

    # Then everything from the attribution block onward is dropped
    assert out == 'Bonjour, voici ma réponse.'


def test_extract_text_keeps_body_when_from_line_has_no_header_block_after_it(make_mail):
    # Given prose that merely mentions "From:" without a following header block
    m = make_mail(text='Quick note.\nFrom: the budget we discussed, I think we are fine.\nThanks')

    # When we extract with stripping on
    out = extract_text(m, strip_quotes=True)

    # Then nothing is cut — a lone From: is not an attribution
    assert 'we are fine' in out and out.endswith('Thanks')
