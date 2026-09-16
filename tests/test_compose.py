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
