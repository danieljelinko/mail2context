"Fetch one message by pointer or Message-ID, and the thread around a message, from the server rather than a recent window."
from email.message import EmailMessage

import pytest

from mail2context.mailbox import Account, Pointer, connect, fetch_message, fetch_messages, fetch_thread_of, parse_pointer


def _raw(mid: str, subject: str = 'Réunion', refs: str = '', reply_to: str = '', date: str = 'Thu, 12 Nov 2026 09:00:00 +0000') -> bytes:
    m = EmailMessage(); m['From'], m['To'], m['Subject'], m['Date'] = 'barbara@example.org', 'dj@ai4hu.org', subject, date
    m['Message-ID'] = f'<{mid}>'
    if refs:     m['References'] = refs
    if reply_to: m['In-Reply-To'] = reply_to
    m.set_content(f'body of {mid}')
    return m.as_bytes()


def _open(port: int):
    return connect(Account('proton', '127.0.0.1', port, 'u', 'x', tls='none'), timeout=5)


def _proton(all_mail: dict[int, list], inbox: dict[int, list] | None = None, **kw) -> dict:
    "A Proton-shaped account: All Mail flagged \\All, INBOX and Drafts beside it."
    return dict(folders={'INBOX': inbox or {}, 'All Mail': all_mail, 'Drafts': {}},
                special={'All Mail': '\\All', 'Drafts': '\\Drafts'}, **kw)


def test_parse_pointer_reads_account_folder_uidvalidity_and_uid_when_the_folder_holds_a_slash_and_a_space():
    # Given a pointer as com-index writes it for Gmail
    text = 'imap://gmail/[Gmail]/All Mail;UIDVALIDITY=1/;UID=338469'

    # When parsed
    p = parse_pointer(text)

    # Then each part comes back, and it prints back to the same text
    assert p == Pointer('gmail', '[Gmail]/All Mail', 1, 338469)
    assert str(p) == text


def test_parse_pointer_refuses_text_that_is_not_an_imap_pointer():
    # Given a thread key passed where a pointer belongs
    # When parsed
    # Then it refuses, naming the expected shape
    with pytest.raises(SystemExit, match='imap://'):
        parse_pointer('9cb987c4')


def test_fetch_message_returns_the_message_by_uid_when_the_pointer_is_current(fake_imap):
    # Given All Mail at UIDVALIDITY 7 holding the message at UID 12
    port, box = fake_imap(**_proton({11: [set(), _raw('a@x')], 12: [set(), _raw('b@x')]}))
    M = _open(port)

    # When we fetch by a pointer naming that validity and UID
    found = fetch_message(M, 'proton', Pointer('proton', 'All Mail', 7, 12), None)

    # Then that message answers, by the pointer path, read-only and without a SEARCH
    assert (found.msg['Message-ID'], found.path, found.pointer) == ('<b@x>', 'pointer', Pointer('proton', 'All Mail', 7, 12))
    sent = b''.join(box.seen)
    assert b'EXAMINE' in sent and b' SELECT ' not in sent and b'SEARCH' not in sent and b'BODY.PEEK[]' in sent
    M.logout()


def test_fetch_message_falls_back_to_message_id_when_uidvalidity_changed(fake_imap):
    # Given a pointer minted under UIDVALIDITY 6, while All Mail is now at 7 and the message sits at UID 40
    port, _ = fake_imap(**_proton({12: [set(), _raw('other@x')], 40: [set(), _raw('b@x')]}))
    M = _open(port)

    # When we fetch by that pointer and its Message-ID
    found = fetch_message(M, 'proton', Pointer('proton', 'All Mail', 6, 12), '<b@x>')

    # Then UID 12 (now another message) is not trusted: the Message-ID answers, with its current pointer and the reason
    assert found.msg['Message-ID'] == '<b@x>'
    assert found.pointer == Pointer('proton', 'All Mail', 7, 40)
    assert found.path.startswith('Message-ID in All Mail') and 'UIDVALIDITY of All Mail is 7, pointer has 6' in found.path
    M.logout()


def test_fetch_message_searches_all_mail_when_the_uid_is_gone_from_the_pointers_folder(fake_imap):
    # Given a pointer into INBOX whose UID was archived away; the message is still in All Mail
    port, _ = fake_imap(**_proton({40: [set(), _raw('b@x')]}, inbox={3: [set(), _raw('c@x')]}))
    M = _open(port)

    # When we fetch by pointer and Message-ID, written without angle brackets
    found = fetch_message(M, 'proton', Pointer('proton', 'INBOX', 7, 9), 'b@x')

    # Then INBOX is searched first, then All Mail answers
    assert found.pointer == Pointer('proton', 'All Mail', 7, 40)
    assert 'UID 9 is gone from INBOX' in found.path
    M.logout()


def test_fetch_message_reports_missing_when_the_message_is_nowhere(fake_imap):
    # Given a stale pointer and a Message-ID no folder holds
    port, _ = fake_imap(**_proton({40: [set(), _raw('b@x')]}))
    M = _open(port)

    # When we fetch
    found = fetch_message(M, 'proton', Pointer('proton', 'All Mail', 7, 99), '<gone@x>')

    # Then no message, no pointer, and the path says where it looked
    assert (found.msg, found.pointer) == (None, None)
    assert found.path.startswith('missing: <gone@x> is in none of All Mail')
    M.logout()


def test_fetch_message_takes_the_lowest_uid_when_proton_holds_two_copies(fake_imap):
    # Given two copies of one message, as Proton's All Mail often holds, beside an unrelated one
    port, _ = fake_imap(**_proton({5: [set(), _raw('c@x')], 8: [set(), _raw('b@x')], 30: [set(), _raw('b@x')]}))
    M = _open(port)

    # When we fetch by Message-ID alone
    found = fetch_message(M, 'proton', None, '<b@x>')

    # Then the lowest UID answers, and the path counts the copies
    assert found.pointer.uid == 8
    assert found.path == 'Message-ID in All Mail, 2 copies, lowest UID taken'
    M.logout()


def test_fetch_message_refuses_to_guess_all_mail_when_no_folder_is_flagged_all(fake_imap):
    # Given a server that flags no mailbox \All
    port, _ = fake_imap(folders={'All Mail': {1: [set(), _raw('b@x')]}}, special={})
    M = _open(port)

    # When a Message-ID lookup needs the all-mail folder
    # Then it refuses rather than picking one by name
    with pytest.raises(SystemExit, match='All'):
        fetch_message(M, 'proton', None, '<b@x>')
    M.logout()


def test_fetch_messages_answers_several_pointers_in_order_over_one_connection_with_one_fetch_per_folder(fake_imap):
    # Given three current pointers into two folders and one stale pointer
    port, box = fake_imap(**_proton({12: [set(), _raw('a@x')], 13: [set(), _raw('b@x')], 40: [set(), _raw('d@x')]},
                                    inbox={3: [set(), _raw('c@x')]}))
    M = _open(port)
    wants = [(Pointer('proton', 'All Mail', 7, 13), None), (Pointer('proton', 'INBOX', 7, 3), None),
             (Pointer('proton', 'All Mail', 7, 12), None), (Pointer('proton', 'All Mail', 6, 1), '<d@x>')]

    # When we fetch them together
    found = fetch_messages(M, 'proton', wants)

    # Then each answers in the order asked, and the current ones cost one UID FETCH per folder, no SEARCH
    assert [f.msg['Message-ID'] for f in found] == ['<b@x>', '<c@x>', '<a@x>', '<d@x>']
    assert [f.path for f in found][:3] == ['pointer'] * 3
    fetches = [l for l in box.seen if b'UID FETCH' in l.upper()]
    assert b'12,13' in fetches[0] and len(fetches) == 3          # All Mail, INBOX, then the fallback's
    assert sum(b'LOGIN' in l for l in box.seen) == 1
    M.logout()


def _day(d: int) -> str: return f'Thu, {d} Nov 2026 09:00:00 +0000'


def test_fetch_thread_of_follows_references_and_in_reply_to_both_ways_when_the_server_has_no_thread_id(fake_imap):
    # Given a root, a reply naming it, a reply naming both, a reply carrying only In-Reply-To, an unrelated message,
    # and a second copy of the middle message (Proton's All Mail holds duplicates)
    port, _ = fake_imap(**_proton({1: [set(), _raw('root@x', date=_day(1))],
                                     2: [set(), _raw('b@x', refs='<root@x>', reply_to='<root@x>', date=_day(2))],
                                     3: [set(), _raw('c@x', refs='<root@x> <b@x>', reply_to='<b@x>', date=_day(3))],
                                     4: [set(), _raw('e@x', reply_to='<c@x>', date=_day(4))],
                                     5: [set(), _raw('other@x', date=_day(2))],
                                     6: [set(), _raw('b@x', refs='<root@x>', reply_to='<root@x>', date=_day(2))]}))
    M = _open(port)

    # When we ask for the thread of the middle message
    msgs, method = fetch_thread_of(M, '<b@x>')

    # Then the whole chain comes back once each, oldest first, found by header search in All Mail
    assert [m['Message-ID'] for m in msgs] == ['<root@x>', '<b@x>', '<c@x>', '<e@x>']
    assert method == 'References/In-Reply-To search in All Mail'
    M.logout()


def test_fetch_thread_of_uses_gmail_thread_id_when_the_server_offers_it(fake_imap):
    # Given a Gmail-like server where Gmail put two header-unrelated messages in one conversation
    port, box = fake_imap(folders={'[Gmail]/All Mail': {10: [set(), _raw('a@x', date=_day(1))], 11: [set(), _raw('z@x', date=_day(3))],
                                                         12: [set(), _raw('other@x', date=_day(2))]}},
                          special={'[Gmail]/All Mail': '\\All'}, thrids={10: 77, 11: 77, 12: 88})
    M = _open(port)

    # When we ask for the thread of the first
    msgs, method = fetch_thread_of(M, 'a@x')

    # Then Gmail's conversation answers, without any References search
    assert [m['Message-ID'] for m in msgs] == ['<a@x>', '<z@x>']
    assert method == 'X-GM-THRID in [Gmail]/All Mail'
    assert not any(b'HEADER References' in l for l in box.seen)
    M.logout()


def test_fetch_thread_of_returns_nothing_when_the_message_is_not_in_all_mail(fake_imap):
    # Given All Mail without the message
    port, _ = fake_imap(**_proton({1: [set(), _raw('root@x')]}))
    M = _open(port)

    # When we ask for its thread
    msgs, _ = fetch_thread_of(M, '<gone@x>')

    # Then nothing comes back
    assert msgs == []
    M.logout()
