from collections.abc import Callable
from email.message import EmailMessage
from email.utils import formatdate

import pytest

from mail2context.render import list_attachments, render_thread


@pytest.fixture
def make_mail() -> Callable[..., EmailMessage]:
    "Factory: build an `EmailMessage` with optional HTML body and attachments."
    def _build(frm: str = 'a@x', to: str = 'b@x', subj: str = 'S', text: str = 'body',
               secs: int = 0, msgid: str = '<m@x>',
               atts: tuple[tuple[str, str], ...] = ()) -> EmailMessage:
        m = EmailMessage()
        m['From'], m['To'], m['Subject'], m['Message-ID'] = frm, to, subj, msgid
        m['Date'] = formatdate(1_700_000_000 + secs)
        m.set_content(text)
        for name, data in atts:
            m.add_attachment(data.encode(), maintype='application', subtype='pdf', filename=name)
        return m
    return _build


def test_list_attachments_returns_filenames_when_message_carries_them(make_mail):
    # Given a message with two attached files
    m = make_mail(atts=(('invoice.pdf', 'x'), ('contract.pdf', 'y')))

    # When we list its attachments
    names = list_attachments(m)

    # Then both filenames come back
    assert names == ['invoice.pdf', 'contract.pdf']


def test_render_thread_labels_each_message_with_sender_and_date(make_mail):
    # Given a two-message exchange
    a = make_mail(frm='dj@ai4hu.org', subj='Budget', text='My question', msgid='<a@x>', secs=0)
    b = make_mail(frm='barbara@ap.fr', subj='Re: Budget', text='My answer', msgid='<b@x>', secs=60)

    # When we render the thread
    out = render_thread([a, b])

    # Then each message appears under its own attributed heading, in order
    assert out.index('dj@ai4hu.org') < out.index('barbara@ap.fr')
    assert 'My question' in out and 'My answer' in out


def test_render_thread_names_attachments_so_they_are_not_silently_dropped(make_mail):
    # Given a message whose payload is an attached file
    m = make_mail(text='See attached', atts=(('offer.pdf', 'z'),))

    # When we render the thread
    out = render_thread([m])

    # Then the attachment is named in the output
    assert 'offer.pdf' in out
