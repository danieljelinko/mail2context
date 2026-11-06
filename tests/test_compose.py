from collections.abc import Callable
from email.message import EmailMessage
from email.utils import formatdate

import pytest

from pathlib import Path

from mail2context.compose import build_message, build_reply, describe_attachments, expand_attachment_paths


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
    r = build_reply([a, b], body='Understood, thanks.', frm='dj@ai4hu.org', attachments=[])

    # Then it points at the last message and carries the full reference chain
    assert r['In-Reply-To'] == '<b@x>'
    assert r['References'] == '<a@x> <b@x>'


def test_build_reply_addresses_the_last_sender_and_keeps_one_re_prefix(make_mail):
    # Given a thread whose last message already has a "Re:" subject
    b = make_mail('barbara@ap.fr', subj='Re: Budget', msgid='<b@x>')

    # When we reply
    r = build_reply([b], body='ok', frm='dj@ai4hu.org', attachments=[])

    # Then it goes back to that sender without stacking another Re:
    assert r['To'] == 'barbara@ap.fr'
    assert r['Subject'] == 'Re: Budget'


def test_build_reply_strips_autoresponder_noise_from_the_subject(make_mail):
    # Given a thread whose last message came from an autoresponder
    b = make_mail('barbara@ap.fr', subj='Auto: Re: Quelques questions', msgid='<b@x>')

    # When we reply
    r = build_reply([b], body='ok', frm='dj@ai4hu.org', attachments=[])

    # Then the Auto: marker is gone and exactly one Re: remains
    assert r['Subject'] == 'Re: Quelques questions'


def test_build_reply_leaves_other_participants_off_by_default(make_mail):
    # Given a three-way thread whose last message is from Elodie
    a = make_mail('barbara@ap.fr', msgid='<a@x>', secs=0)
    b = make_mail('elodie@ap.fr', msgid='<b@x>', secs=60)

    # When we reply without asking for reply-all
    r = build_reply([a, b], body='ok', frm='dj@ai4hu.org', attachments=[])

    # Then only the last sender is addressed, and nobody is silently Cc'd
    assert r['To'] == 'elodie@ap.fr'
    assert r['Cc'] is None


def test_build_reply_copies_the_other_participants_when_reply_all_is_asked(make_mail):
    # Given the same three-way thread
    a = make_mail('barbara@ap.fr', msgid='<a@x>', secs=0)
    b = make_mail('elodie@ap.fr', msgid='<b@x>', secs=60)

    # When we reply to all
    r = build_reply([a, b], body='ok', frm='dj@ai4hu.org', reply_all=True, attachments=[])

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
    r = build_reply([mine], body='ok', frm='dj@ai4hu.org', attachments=[])

    # Then it goes to who we wrote to, not back to ourselves
    assert r['To'] == 'elodie@ap.fr'


def test_build_message_carries_no_threading_headers_when_starting_a_new_conversation():
    # Given a fresh message to a chosen recipient
    from mail2context.compose import build_message
    m = build_message(to='barbara@ap.fr', subject='FIPDes Day', body='Hello',
                      frm='dj@ai4hu.org', attachments=[])

    # When we inspect it
    # Then it threads to nothing and keeps the subject exactly as given
    assert m['In-Reply-To'] is None
    assert m['References'] is None
    assert m['Subject'] == 'FIPDes Day'
    assert m['To'] == 'barbara@ap.fr'


def test_build_message_sets_cc_only_when_given():
    # Given a new message with no Cc
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='b', frm='me@x', attachments=[])

    # When we inspect it
    # Then no empty Cc header is emitted
    assert m['Cc'] is None


def test_build_message_adds_an_html_alternative_so_clients_do_not_render_monospace():
    # Given a two-paragraph body
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='First para.\n\nSecond para.', frm='me@x', attachments=[])

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
    m = build_message(to='a@x', subject='S', body='Dani JELINKO\nAI4HU | AI for humans', frm='me@x', attachments=[])

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then the break is preserved rather than collapsed into one line
    assert '<br' in html


def test_html_alternative_escapes_markup_so_a_body_cannot_inject_html():
    # Given a body containing characters that are markup in HTML
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Coût < 100 & "urgent"', frm='me@x', attachments=[])

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
    r = build_reply([last], body='Bonjour,\n\nMerci.', frm='me@x', attachments=[])

    # Then it too has an HTML part, so replies are not monospace either
    assert r.get_body(('html',)) is not None


def test_build_message_renders_the_body_as_markdown_by_default():
    # Given a body using markdown emphasis and a link
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', frm='me@x',
                      body='Please see **the deck** at [lab](https://lab.ai4hu.org).', attachments=[])

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then the markdown became real markup
    assert '<strong>the deck</strong>' in html
    assert 'href="https://lab.ai4hu.org"' in html


def test_build_message_leaves_the_plain_part_as_the_markdown_source():
    # Given a markdown body
    from mail2context.compose import build_message
    src = 'Please see **the deck**.'
    m = build_message(to='a@x', subject='S', body=src, frm='me@x', attachments=[])

    # When we read the plain part
    # Then it is the markdown itself, which reads fine as plain text
    assert m.get_body(('plain',)).get_content().strip() == src


def test_build_message_skips_markdown_when_plain_is_requested():
    # Given a body where asterisks are literal, not emphasis
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', frm='me@x',
                      body='The file is named *_draft*.', markdown=False, attachments=[])

    # When we read the HTML part
    html = m.get_body(('html',)).get_content()

    # Then nothing was interpreted as emphasis
    assert '<em>' not in html


def test_build_message_appends_the_signature_to_both_parts_when_given():
    # Given a signature supplied in both plain and HTML form
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Hello.', frm='me@x',
                      signature_text='Dani JELINKO\nAI4HU',
                      signature_html='<div><span style="color: rgb(59,131,194)">4</span></div>', attachments=[])

    # When we read both parts
    plain, html = m.get_body(('plain',)).get_content(), m.get_body(('html',)).get_content()

    # Then each carries the signature in its own form, the HTML one keeping its styling
    assert plain.rstrip().endswith('AI4HU')
    assert 'color: rgb(59,131,194)' in html


def test_build_message_adds_nothing_when_no_signature_is_given():
    # Given no signature
    from mail2context.compose import build_message
    m = build_message(to='a@x', subject='S', body='Hello.', frm='me@x', attachments=[])

    # When we read the plain part
    # Then the body stands alone, with no stray separator appended
    assert m.get_body(('plain',)).get_content().strip() == 'Hello.'


# --- attachments --------------------------------------------------------------

@pytest.fixture
def make_file(tmp_path) -> Callable[..., Path]:
    "Factory: write `data` to `name` under tmp_path (or a subdir) and return its path."
    def _build(name: str, data: bytes = b'x', subdir: str = '') -> Path:
        d = tmp_path / subdir if subdir else tmp_path
        d.mkdir(parents=True, exist_ok=True)
        p = d / name; p.write_bytes(data)
        return p
    return _build


def _atts(m: EmailMessage) -> dict[str, EmailMessage]: return {p.get_filename(): p for p in m.iter_attachments()}


def test_build_message_attaches_each_file_by_basename_with_its_exact_bytes(make_file):
    # Given a PNG and a text file whose name carries accents
    png = make_file('01_capture.png', b'\x89PNG\r\n\x1a\n' + bytes(range(256)))
    txt = make_file('état_du_site é.txt', 'Sélestat, déjà vu\n'.encode())

    # When we build a message attaching both
    m = build_message(to='a@x', subject='S', body='Hello.', frm='me@x', attachments=[png, txt])

    # Then each comes back under its basename with byte-identical content
    atts = _atts(m)
    assert set(atts) == {'01_capture.png', 'état_du_site é.txt'}
    assert atts['01_capture.png'].get_payload(decode=True) == png.read_bytes()
    assert atts['état_du_site é.txt'].get_payload(decode=True) == txt.read_bytes()


def test_build_message_guesses_the_mime_type_from_the_extension(make_file):
    # Given a PNG and a file with an unknown extension
    png, odd = make_file('a.png'), make_file('b.zzunknown')

    # When we attach them
    atts = _atts(build_message(to='a@x', subject='S', body='b', frm='me@x', attachments=[png, odd]))

    # Then the PNG is typed image/png and the unknown one falls back to octet-stream
    assert atts['a.png'].get_content_type() == 'image/png'
    assert atts['b.zzunknown'].get_content_type() == 'application/octet-stream'


def test_build_message_keeps_body_and_signature_when_attaching(make_file):
    # Given a signed message with one attachment
    m = build_message(to='a@x', subject='S', body='Hello.', frm='me@x', attachments=[make_file('a.png')],
                      signature_text='Dani', signature_html='<div>sig4</div>')

    # When we read the body parts
    plain, html = m.get_body(('plain',)).get_content(), m.get_body(('html',)).get_content()

    # Then both parts still carry body and signature
    assert plain.startswith('Hello.') and plain.rstrip().endswith('Dani')
    assert 'Hello.' in html and 'sig4' in html


def test_build_message_has_no_attachment_when_given_an_empty_list():
    # Given no files
    m = build_message(to='a@x', subject='S', body='b', frm='me@x', attachments=[])

    # When we look for attachments
    # Then there are none and the message is not multipart/mixed
    assert list(m.iter_attachments()) == []
    assert m.get_content_type() == 'multipart/alternative'


def test_build_message_raises_when_an_attachment_is_missing(tmp_path):
    # Given a path that does not exist
    # When we build / Then it fails rather than producing a message without the file
    with pytest.raises(FileNotFoundError):
        build_message(to='a@x', subject='S', body='b', frm='me@x', attachments=[tmp_path / 'nope.png'])


def test_build_reply_attaches_files_too(make_file):
    # Given a thread and one file
    last = EmailMessage()
    last['From'], last['Subject'], last['Message-ID'] = 'b@x', 'Budget', '<b@x>'
    last.set_content('x')

    # When we reply with an attachment
    r = build_reply([last], body='ok', frm='me@x', attachments=[make_file('a.pdf', b'%PDF-1.4')])

    # Then it is attached and the reply still threads
    assert _atts(r)['a.pdf'].get_content_type() == 'application/pdf'
    assert r['In-Reply-To'] == '<b@x>'


def test_expand_attachment_paths_lists_a_directory_in_name_order(make_file, tmp_path):
    # Given a folder of numbered screenshots written out of order, plus a lone file
    for n in ('02_b.png', '10_c.png', '01_a.png'): make_file(n, subdir='shots')
    lone = make_file('notes.txt')

    # When we expand the folder and the file
    got = expand_attachment_paths([tmp_path / 'shots', lone])

    # Then the folder's files come sorted by name, followed by the file as given
    assert [p.name for p in got] == ['01_a.png', '02_b.png', '10_c.png', 'notes.txt']


def test_expand_attachment_paths_raises_on_a_missing_path(tmp_path):
    # Given a path that does not exist
    # When we expand it / Then it fails before any mail is built
    with pytest.raises(FileNotFoundError, match='nope'):
        expand_attachment_paths([tmp_path / 'nope'])


def test_expand_attachment_paths_raises_on_an_empty_directory(tmp_path):
    # Given an empty folder, which would silently attach nothing
    (tmp_path / 'empty').mkdir()

    # When we expand it / Then it is refused
    with pytest.raises(ValueError, match='no files'):
        expand_attachment_paths([tmp_path / 'empty'])


def test_describe_attachments_lists_each_size_and_the_total(make_file):
    # Given two files of known sizes
    a, b = make_file('a.png', b'x' * 1536), make_file('b.txt', b'y' * 512)

    # When we describe them
    lines = describe_attachments([a, b])

    # Then each line names a file and its size, and the last gives count and total
    assert lines == ['attach  : a.png (1.5 KB)', 'attach  : b.txt (512 B)',
                     'attached: 2 files, 2.0 KB (base64 on the wire: ~2.7 KB)']
