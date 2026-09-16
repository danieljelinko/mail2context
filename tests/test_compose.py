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
