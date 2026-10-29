from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pytest

from mail2context.drafts import delete_draft, find_drafts_folder, format_draft_row, list_drafts, parse_appenduid
from mail2context.mailbox import Account, connect

PARIS = ZoneInfo('Europe/Paris')


def _raw(to: str = 'barbara@example.org', subject: str = 'Re: réunion', body: str = 'Bonjour Barbara,\n\nMardi.') -> bytes:
    m = EmailMessage(); m['From'], m['To'], m['Subject'] = 'dj@ai4hu.org', to, subject
    m['Date'] = 'Thu, 29 Oct 2026 07:12:00 +0000'; m.set_content(body)
    return m.as_bytes()


def _mailbox(drafts: dict[int, list] | None = None, inbox: dict[int, list] | None = None, **kw) -> dict:
    "A Proton-shaped account: Drafts flagged \\Drafts, an INBOX beside it."
    return dict(folders={'INBOX': inbox or {}, 'Drafts': drafts if drafts is not None else {}},
                special={'Drafts': '\\Drafts'}, **kw)


def _open(port: int):
    return connect(Account('proton', '127.0.0.1', port, 'u', 'x', tls='none'), timeout=5)


def _sent(box, *verbs: str) -> list[bytes]:
    "Command lines whose verb (after the tag, `UID` included) is one of `verbs`."
    return [l for l in box.seen if any(l.split(b' ', 1)[1].upper().startswith(v.encode()) for v in verbs)]


def test_find_drafts_folder_returns_the_mailbox_the_server_flags_drafts_when_named_like_gmail(fake_imap):
    # Given a Gmail-shaped server whose drafts live under a namespaced name
    port, _ = fake_imap(folders={'INBOX': {}, '[Gmail]/Drafts': {}}, special={'[Gmail]/Drafts': '\\Drafts'})
    M = _open(port)

    # When we look the drafts folder up
    folder = find_drafts_folder(M)

    # Then it is the flagged mailbox, whole
    assert folder == '[Gmail]/Drafts'
    M.logout()


def test_find_drafts_folder_refuses_when_no_mailbox_is_flagged_drafts(fake_imap):
    # Given a server that flags nothing \Drafts, though a folder is called Drafts
    port, _ = fake_imap(folders={'INBOX': {}, 'Drafts': {}}, special={})
    M = _open(port)

    # When we look the drafts folder up
    # Then it refuses rather than guessing from a name
    with pytest.raises(SystemExit, match='Drafts'):
        find_drafts_folder(M)
    M.logout()


def test_list_drafts_returns_each_draft_with_its_uid_when_reading_drafts_read_only(fake_imap):
    # Given two drafts
    port, box = fake_imap(**_mailbox({196: [{'\\Draft'}, _raw(subject='a')], 197: [{'\\Draft', '\\Seen'}, _raw(subject='b')]}))
    M = _open(port)

    # When we list them
    drafts = list_drafts(M)

    # Then both come back keyed by UID, and Drafts was opened with EXAMINE (read-only)
    assert [(d.uid, d.msg['Subject']) for d in drafts] == [(196, 'a'), (197, 'b')]
    assert _sent(box, 'EXAMINE') and not _sent(box, 'SELECT', 'UID STORE')
    M.logout()


def test_format_draft_row_shows_uid_paris_time_to_subject_and_first_body_line_when_given_a_draft(fake_imap):
    # Given one draft dated 07:12 UTC, which is 08:12 in Paris on 29 October
    port, _ = fake_imap(**_mailbox({197: [{'\\Draft'}, _raw()]}))
    M = _open(port); d = list_drafts(M)[0]; M.logout()

    # When we format its row
    row = format_draft_row(d, PARIS)

    # Then every field the owner picks a draft by is there
    assert all(s in row for s in ('197', '2026-10-29 08:12', 'barbara@example.org', 'Re: réunion', 'Bonjour Barbara,'))


def test_delete_draft_refuses_a_uid_that_is_not_in_drafts_when_it_exists_only_in_inbox(fake_imap):
    # Given UID 42 exists in INBOX but not in Drafts
    port, box = fake_imap(**_mailbox({197: [{'\\Draft'}, _raw()]}, inbox={42: [set(), _raw()]}))
    M = _open(port)

    # When we ask to delete UID 42
    # Then it is refused, INBOX was never opened, and nothing was stored or expunged
    with pytest.raises(SystemExit, match='42'):
        delete_draft(M, 42, confirm=lambda d: True)
    assert not any(b'INBOX' in l for l in _sent(box, 'SELECT', 'EXAMINE'))
    assert not _sent(box, 'UID STORE', 'UID EXPUNGE', 'EXPUNGE') and 42 in box.folders['INBOX']
    M.logout()


def test_delete_draft_refuses_an_unknown_uid_when_drafts_holds_others(fake_imap):
    # Given Drafts holds UID 197 only
    port, box = fake_imap(**_mailbox({197: [{'\\Draft'}, _raw()]}))
    M = _open(port)

    # When we ask to delete UID 999
    # Then it is refused and Drafts is untouched
    with pytest.raises(SystemExit, match='999'):
        delete_draft(M, 999, confirm=lambda d: True)
    assert list(box.folders['Drafts']) == [197] and not _sent(box, 'UID STORE')
    M.logout()


def test_delete_draft_refuses_a_message_without_the_draft_flag_when_it_sits_in_drafts(fake_imap):
    # Given a message in Drafts that is not flagged \Draft
    port, box = fake_imap(**_mailbox({197: [{'\\Seen'}, _raw()]}))
    M = _open(port)

    # When we ask to delete it
    # Then it is refused naming the missing flag, and nothing is stored
    with pytest.raises(SystemExit, match=r'\\Draft'):
        delete_draft(M, 197, confirm=lambda d: True)
    assert 197 in box.folders['Drafts'] and not _sent(box, 'UID STORE')
    M.logout()


def test_delete_draft_writes_nothing_when_confirmation_is_declined_as_in_a_dry_run(fake_imap):
    # Given one draft, and a confirm step that declines (what --dry-run and a "no" both do)
    port, box = fake_imap(**_mailbox({197: [{'\\Draft'}, _raw()]}))
    M = _open(port); shown = []

    # When we ask to delete it
    deleted = delete_draft(M, 197, confirm=lambda d: shown.append(d.uid) or False)

    # Then the draft was shown, nothing was stored or expunged, and it is still there
    assert (deleted, shown) == (False, [197])
    assert not _sent(box, 'UID STORE', 'UID EXPUNGE', 'EXPUNGE') and box.folders['Drafts'][197][0] == {'\\Draft'}
    M.logout()


def test_delete_draft_removes_exactly_that_message_when_another_is_already_flagged_deleted(fake_imap):
    # Given three drafts, one of which some other client already flagged \Deleted
    port, box = fake_imap(**_mailbox({196: [{'\\Draft', '\\Deleted'}, _raw()], 197: [{'\\Draft'}, _raw()],
                                      198: [{'\\Draft'}, _raw()]}))
    M = _open(port)

    # When we delete UID 197
    deleted = delete_draft(M, 197, confirm=lambda d: True)

    # Then only 197 is gone — a bare EXPUNGE would have taken 196 with it — and the expunge was UID-scoped
    assert deleted is True and sorted(box.folders['Drafts']) == [196, 198]
    assert [l.split(b' ', 1)[1] for l in _sent(box, 'UID STORE', 'UID EXPUNGE', 'EXPUNGE')] == \
           [b'UID STORE 197 +FLAGS.SILENT (\\Deleted)\r\n', b'UID EXPUNGE 197\r\n']
    M.logout()


def test_delete_draft_refuses_before_storing_when_the_server_lacks_uidplus(fake_imap):
    # Given a server without UIDPLUS, where only a bare EXPUNGE would be possible
    port, box = fake_imap(**_mailbox({197: [{'\\Draft'}, _raw()]}, capabilities='IMAP4rev1'))
    M = _open(port)

    # When we ask to delete a draft
    # Then it is refused before anything is flagged
    with pytest.raises(SystemExit, match='UIDPLUS'):
        delete_draft(M, 197, confirm=lambda d: True)
    assert not _sent(box, 'UID STORE')
    M.logout()


def test_delete_draft_reports_the_guard_level_when_mail_guard_refuses_the_store(fake_imap):
    # Given mail-guard at level 1, which answers STORE \Deleted with NO
    port, box = fake_imap(**_mailbox({197: [{'\\Draft'}, _raw()]}, refuse={'UID STORE': 'guard: level 1 forbids UID STORE'}))
    M = _open(port)

    # When we ask to delete a draft
    # Then the refusal is passed on with what the owner must do, and the draft is intact
    with pytest.raises(SystemExit, match=r'level 1 forbids UID STORE.*sudo mail-guard 2'):
        delete_draft(M, 197, confirm=lambda d: True)
    assert box.folders['Drafts'][197][0] == {'\\Draft'} and not _sent(box, 'UID EXPUNGE')
    M.logout()


def test_parse_appenduid_returns_the_uid_when_the_server_answers_with_appenduid():
    # Given what append_draft returned on Proton
    result = 'OK [APPENDUID 114340474 197] APPEND completed'

    # When we parse it
    # Then the message UID comes out, not the UIDVALIDITY
    assert parse_appenduid(result) == 197


def test_parse_appenduid_returns_none_when_the_server_sends_no_appenduid():
    # Given a server without UIDPLUS
    # When we parse its APPEND answer
    # Then there is no UID to report
    assert parse_appenduid('OK APPEND completed') is None
