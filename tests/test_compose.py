from collections.abc import Callable
from email.message import EmailMessage
from email.utils import formatdate

import pytest

from mail2context.compose import build_reply


@pytest.fixture
def make_mail() -> Callable[..., EmailMessage]:
    "Factory: a message with the headers a reply must thread against."
    def _build(frm: str, to: str = 'dj@ai4hu.org', subj: str = 'Budget',
               msgid: str = '<m@x>', refs: str = '', secs: int = 0) -> EmailMessage:
        m = EmailMessage()
        m['From'], m['To'], m['Subject'], m['Message-ID'] = frm, to, subj, msgid
        m['Date'] = formatdate(1_700_000_000 + secs)
        if refs: m['References'] = refs
        m.set_content('x')
        return m
    return _build


def test_build_reply_threads_against_the_last_message_in_the_thread(make_mail):
    # Given a thread whose last message came from Barbara
    a = make_mail('dj@ai4hu.org', msgid='<a@x>', secs=0)
    b = make_mail('barbara@ap.fr', subj='Re: Budget', msgid='<b@x>', refs='<a@x>', secs=60)

    # When we build a reply to that thread
    r = build_reply([a, b], body='Understood, thanks.', frm='dj@ai4hu.org')

    # Then it points at the last message and carries the full reference chain
    assert r['In-Reply-To'] == '<b@x>'
    assert r['References'] == '<a@x> <b@x>'


def test_build_reply_addresses_the_last_sender_and_keeps_one_re_prefix(make_mail):
    # Given a thread whose last message already has a "Re:" subject
    b = make_mail('barbara@ap.fr', subj='Re: Budget', msgid='<b@x>')

    # When we reply
    r = build_reply([b], body='ok', frm='dj@ai4hu.org')

    # Then it goes back to that sender without stacking another Re:
    assert r['To'] == 'barbara@ap.fr'
    assert r['Subject'] == 'Re: Budget'


def test_build_reply_strips_autoresponder_noise_from_the_subject(make_mail):
    # Given a thread whose last message came from an autoresponder
    b = make_mail('barbara@ap.fr', subj='Auto: Re: Quelques questions', msgid='<b@x>')

    # When we reply
    r = build_reply([b], body='ok', frm='dj@ai4hu.org')

    # Then the Auto: marker is gone and exactly one Re: remains
    assert r['Subject'] == 'Re: Quelques questions'


def test_build_reply_leaves_other_participants_off_by_default(make_mail):
    # Given a three-way thread whose last message is from Elodie
    a = make_mail('barbara@ap.fr', msgid='<a@x>', secs=0)
    b = make_mail('elodie@ap.fr', msgid='<b@x>', secs=60)

    # When we reply without asking for reply-all
    r = build_reply([a, b], body='ok', frm='dj@ai4hu.org')

    # Then only the last sender is addressed, and nobody is silently Cc'd
    assert r['To'] == 'elodie@ap.fr'
    assert r['Cc'] is None


def test_build_reply_copies_the_other_participants_when_reply_all_is_asked(make_mail):
    # Given the same three-way thread
    a = make_mail('barbara@ap.fr', msgid='<a@x>', secs=0)
    b = make_mail('elodie@ap.fr', msgid='<b@x>', secs=60)

    # When we reply to all
    r = build_reply([a, b], body='ok', frm='dj@ai4hu.org', reply_all=True)

    # Then the earlier participant is Cc'd, and our own address is not
    assert r['To'] == 'elodie@ap.fr'
    assert 'barbara@ap.fr' in r['Cc']
    assert 'dj@ai4hu.org' not in (r['Cc'] or '')


def test_list_participants_names_everyone_in_the_thread_except_the_author(make_mail):
    # Given a thread with two other people
    from mail2context.compose import list_participants
    a = make_mail('barbara@ap.fr', to='dj@ai4hu.org', msgid='<a@x>')
    b = make_mail('elodie@ap.fr', to='dj@ai4hu.org', msgid='<b@x>', secs=60)

    # When we list its participants from our point of view
    who = list_participants([a, b], me='dj@ai4hu.org')

    # Then both correspondents appear and we do not
    assert set(who) == {'barbara@ap.fr', 'elodie@ap.fr'}


def test_build_reply_addresses_the_original_recipients_when_we_sent_the_last_message(make_mail):
    # Given a thread whose last message is our own, as when we are chasing a reply
    mine = make_mail('dj@ai4hu.org', to='elodie@ap.fr', msgid='<b@x>')

    # When we reply to that thread
    r = build_reply([mine], body='ok', frm='dj@ai4hu.org')

    # Then it goes to who we wrote to, not back to ourselves
    assert r['To'] == 'elodie@ap.fr'


def test_build_message_carries_no_threading_headers_when_starting_a_new_conversation():
    # Given a fresh message to a chosen recipient
    from mail2context.compose import build_message
    m = build_message(to='barbara@ap.fr', subject='FIPDes Day', body='Hello',
                      frm='dj@ai4hu.org')

    # When we inspect it
    # Then it threads to nothing and keeps the subject exactly as given
    assert m['In-Reply-To'] is None
    assert m['References'] is None
    assert m['Subject'] == 'FIPDes Day'
    assert m['To'] == 'barbara@ap.fr'


def test_build_message_sets_cc_only_when_given():
    # Given a new message with no Cc
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='b', frm='me@x')

    # When we inspect it
    # Then no empty Cc header is emitted
    assert m['Cc'] is None


def test_build_message_adds_an_html_alternative_so_clients_do_not_render_monospace():
    # Given a two-paragraph body
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='First para.\n\nSecond para.', frm='me@x')

    # When we look for an HTML part
    html = m.get_body(('html',))

    # Then one exists, with each paragraph marked up
    assert html is not None
    assert 'First para.' in html.get_content()
    assert 'Second para.' in html.get_content()
    assert html.get_content().count('<p') == 2


def test_html_alternative_keeps_deliberate_line_breaks_inside_a_paragraph():
    # Given a signature block, where the line breaks are meant
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Dani JELINKO\nAI4HU | AI for humans', frm='me@x')

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then the break is preserved rather than collapsed into one line
    assert '<br' in html


def test_html_alternative_escapes_markup_so_a_body_cannot_inject_html():
    # Given a body containing characters that are markup in HTML
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Coût < 100 & "urgent"', frm='me@x')

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then they are escaped, not emitted raw
    assert '&lt; 100 &amp;' in html


def test_build_reply_also_carries_an_html_alternative():
    # Given a reply built from a thread
    from email.message import EmailMessage
    last = EmailMessage()
    last['From'], last['Subject'], last['Message-ID'] = 'b@x', 'Budget', '<b@x>'
    last.set_content('x')

    # When we build the reply
    r = build_reply([last], body='Bonjour,\n\nMerci.', frm='me@x')

    # Then it too has an HTML part, so replies are not monospace either
    assert r.get_body(('html',)) is not None


def test_build_message_renders_the_body_as_markdown_by_default():
    # Given a body using markdown emphasis and a link
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', frm='me@x',
                      body='Please see **the deck** at [lab](https://lab.ai4hu.org).')

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then the markdown became real markup
    assert '<strong>the deck</strong>' in html
    assert 'href="https://lab.ai4hu.org"' in html


def test_build_message_leaves_the_plain_part_as_the_markdown_source():
    # Given a markdown body
    from mail2context.compose import build_message
    src = 'Please see **the deck**.'
    m = build_message(to='a@x', subject='S', body=src, frm='me@x')

    # When we read the plain part
    # Then it is the markdown itself, which reads fine as plain text
    assert m.get_body(('plain',)).get_content().strip() == src


def test_build_message_skips_markdown_when_plain_is_requested():
    # Given a body where asterisks are literal, not emphasis
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', frm='me@x',
                      body='The file is named *_draft*.', markdown=False)

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then nothing was interpreted as emphasis
    assert '<em>' not in html


def test_build_message_appends_the_signature_to_both_parts_when_given():
    # Given a signature supplied in both plain and HTML form
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Hello.', frm='me@x',
                      signature_text='Dani JELINKO\nAI4HU',
                      signature_html='<div><span style="color: rgb(59,131,194)">4</span></div>')

    # When we read both parts
    plain, html = m.get_body(('plain',)).get_content(), m.get_body(('html',)).get_content()

    # Then each carries the signature in its own form, the HTML one keeping its styling
    assert plain.rstrip().endswith('AI4HU')
    assert 'color: rgb(59,131,194)' in html


def test_build_message_adds_nothing_when_no_signature_is_given():
    # Given no signature
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Hello.', frm='me@x')

    # When we read the plain part
    # Then the body stands alone, with no stray separator appended
    assert m.get_body(('plain',)).get_content().strip() == 'Hello.'
