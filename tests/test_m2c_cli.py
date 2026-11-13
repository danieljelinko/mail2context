import hashlib, json, os, subprocess, sys
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def run_m2c(tmp_path) -> Callable[..., subprocess.CompletedProcess]:
    "Factory: run scripts/m2c.py with a plaintext proton account on `port`; port 1, the default, refuses every connect."
    def _run(*args: str, port: int = 1) -> subprocess.CompletedProcess:
        env = {**os.environ, 'PROTON_IMAP_HOST': '127.0.0.1', 'PROTON_IMAP_PORT': str(port), 'PROTON_IMAP_TLS': 'none',
               'PROTON_USER': 'dj@ai4hu.org', 'PROTON_PASS': 'x'}
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'm2c.py'), *args],
                              cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=False)
    return _run


@pytest.fixture
def shots(tmp_path) -> Path:
    "A folder of two numbered screenshots plus a body file beside it."
    d = tmp_path / 'shots'; d.mkdir()
    (d / '02_b.png').write_bytes(b'b' * 2048); (d / '01_a.png').write_bytes(b'a' * 1024)
    (tmp_path / 'body.md').write_text('Bonjour,\n\nVoici les captures.\n')
    return d


def test_compose_dry_run_lists_attachments_in_order_without_connecting(run_m2c, shots):
    # Given a folder of screenshots and an account no connection can reach
    # When we preview a compose with the folder attached
    r = run_m2c('compose', '--to', 'dj@ai4hu.org', '--subject', 'S', '--file', 'body.md',
                '--attach', str(shots), '--dry-run')

    # Then it succeeds and lists each file, in name order, with the total
    assert r.returncode == 0, r.stderr
    assert r.stdout.index('01_a.png (1.0 KB)') < r.stdout.index('02_b.png (2.0 KB)')
    assert 'attached: 2 files, 3.0 KB' in r.stdout


def test_compose_accepts_attach_repeated(run_m2c, shots):
    # Given two files named one by one
    # When --attach is repeated
    r = run_m2c('compose', '--to', 'a@x', '--subject', 'S', '--file', 'body.md',
                '--attach', str(shots / '02_b.png'), '--attach', str(shots / '01_a.png'), '--dry-run')

    # Then both are listed, in the order given
    assert r.stdout.index('02_b.png') < r.stdout.index('01_a.png')


def test_compose_refuses_a_missing_attachment_before_connecting(run_m2c, shots):
    # Given an attachment path that does not exist
    # When we compose for real (not a dry run)
    r = run_m2c('compose', '--to', 'a@x', '--subject', 'S', '--file', 'body.md', '--attach', 'nope.png')

    # Then it stops on the missing file, never reaching the (refused) connection
    assert r.returncode != 0
    assert 'attachment not found: nope.png' in r.stderr
    assert 'ConnectionRefused' not in r.stderr


def test_draft_refuses_a_missing_attachment_before_connecting(run_m2c, shots):
    # Given a reply draft with an attachment path that does not exist
    # When we run it
    r = run_m2c('draft', 'abcd1234', '--file', 'body.md', '--attach', 'nope.png', '--dry-run')

    # Then the missing file is reported before the thread is fetched
    assert r.returncode != 0
    assert 'attachment not found: nope.png' in r.stderr
    assert 'ConnectionRefused' not in r.stderr


def _mail(mid: str, refs: str = '') -> bytes:
    m = EmailMessage(); m['From'], m['To'], m['Subject'] = 'Barbara <barbara@example.org>', 'dj@ai4hu.org', 'Réunion'
    m['Date'], m['Message-ID'] = 'Thu, 12 Nov 2026 09:00:00 +0000', f'<{mid}>'
    if refs: m['References'] = m['In-Reply-To'] = refs
    m.set_content(f'Bonjour, body of {mid}.')
    return m.as_bytes()


def _account(drafts_name: str | None, all_mail: dict[int, list]) -> dict:
    "A server whose drafts folder is called `drafts_name` and flagged \\Drafts; None: a 'Drafts' folder nothing flags."
    return {'folders': {'All Mail': all_mail, drafts_name or 'Drafts': {}},
            'special': {'All Mail': '\\All', **({drafts_name: '\\Drafts'} if drafts_name else {})}}


@pytest.fixture
def body(tmp_path) -> str:
    (tmp_path / 'body.md').write_text('Merci Barbara.\n'); return 'body.md'


def test_draft_appends_to_the_folder_flagged_drafts_when_it_has_a_local_name(run_m2c, fake_imap, body):
    # Given a server whose drafts live in "Brouillons", flagged \Drafts, and a one-message thread
    port, box = fake_imap(**_account('Brouillons', {1: [set(), _mail('a@x')]}))
    key = hashlib.sha1(b'<a@x>').hexdigest()[:8]

    # When we draft a reply to the thread
    r = run_m2c('draft', key, '--file', body, port=port)

    # Then the draft lands in Brouillons, found by special-use, not by a hardcoded name
    assert r.returncode == 0, r.stderr
    assert len(box.folders['Brouillons']) == 1 and 'drafts  : Brouillons' in r.stdout


def test_draft_refuses_and_writes_nothing_when_no_folder_is_flagged_drafts(run_m2c, fake_imap, body):
    # Given a server with a folder called Drafts that nothing flags \Drafts
    port, box = fake_imap(**_account(None, {1: [set(), _mail('a@x')]}))
    key = hashlib.sha1(b'<a@x>').hexdigest()[:8]

    # When we draft a reply
    r = run_m2c('draft', key, '--file', body, port=port)

    # Then it refuses rather than guessing, and no APPEND reached the server
    assert r.returncode != 0 and 'refusing to guess' in r.stderr
    assert not any(b'APPEND' in l for l in box.seen) and box.folders['Drafts'] == {}


def test_compose_appends_to_the_folder_flagged_drafts_when_it_has_a_local_name(run_m2c, fake_imap, body):
    # Given a server whose drafts live in "Brouillons"
    port, box = fake_imap(**_account('Brouillons', {}))

    # When we compose a new conversation
    r = run_m2c('compose', '--to', 'barbara@example.org', '--subject', 'S', '--file', body, port=port)

    # Then it lands in Brouillons
    assert r.returncode == 0, r.stderr
    assert len(box.folders['Brouillons']) == 1


def test_message_prints_markdown_and_says_the_pointer_answered_when_the_pointer_is_current(run_m2c, fake_imap):
    # Given All Mail at UIDVALIDITY 7 with the message at UID 4
    port, _ = fake_imap(**_account('Drafts', {4: [set(), _mail('a@x')]}))

    # When we ask for it by pointer
    r = run_m2c('message', '--pointer', 'imap://proton/All Mail;UIDVALIDITY=7/;UID=4', port=port)

    # Then its body is rendered as markdown, and stderr names the path that answered
    assert r.returncode == 0, r.stderr
    assert 'body of a@x' in r.stdout and r.stdout.startswith('# Réunion')
    assert 'answered by: pointer' in r.stderr


def test_message_json_carries_the_current_pointer_and_path_when_found_by_message_id(run_m2c, fake_imap):
    # Given the message at UID 4
    port, _ = fake_imap(**_account('Drafts', {4: [set(), _mail('a@x')]}))

    # When we ask for it by Message-ID as JSON
    r = run_m2c('message', '--message-id', '<a@x>', '--json', port=port)

    # Then one record says where it lives now and how it was found
    rec = json.loads(r.stdout)[0]
    assert (rec['pointer'], rec['path'], rec['message_id']) == ('imap://proton/All Mail;UIDVALIDITY=7/;UID=4', 'Message-ID in All Mail', '<a@x>')
    assert 'body of a@x' in rec['body']


def test_message_exits_non_zero_when_the_message_is_missing(run_m2c, fake_imap):
    # Given All Mail without the message
    port, _ = fake_imap(**_account('Drafts', {4: [set(), _mail('a@x')]}))

    # When we ask for an absent Message-ID
    r = run_m2c('message', '--message-id', '<gone@x>', port=port)

    # Then it fails, saying it is missing
    assert r.returncode == 1 and 'missing' in r.stderr


def test_message_refuses_a_pointer_for_another_account(run_m2c):
    # Given a Gmail pointer and the proton account
    # When we ask for it
    r = run_m2c('message', '--pointer', 'imap://gmail/[Gmail]/All Mail;UIDVALIDITY=1/;UID=4')

    # Then it refuses before connecting
    assert r.returncode != 0 and 'gmail' in r.stderr and 'ConnectionRefused' not in r.stderr


def test_thread_of_prints_the_thread_and_how_it_was_found(run_m2c, fake_imap):
    # Given a root and a reply naming it
    port, _ = fake_imap(**_account('Drafts', {1: [set(), _mail('a@x')], 2: [set(), _mail('b@x', refs='<a@x>')]}))

    # When we ask for the thread of the reply
    r = run_m2c('thread-of', '--message-id', '<b@x>', port=port)

    # Then both messages are rendered, and stderr says how they were found and what that cannot see
    assert r.returncode == 0, r.stderr
    assert 'body of a@x' in r.stdout and 'body of b@x' in r.stdout
    assert 'References/In-Reply-To search' in r.stderr and 'cannot' in r.stderr


def test_draft_to_preview_shows_recipients_threading_and_proton_warning_and_writes_nothing(run_m2c, fake_imap, body):
    # Given the message to answer
    port, box = fake_imap(**_account('Drafts', {4: [set(), _mail('a@x')]}))

    # When we preview a reply to it by Message-ID
    r = run_m2c('draft-to', '--message-id', '<a@x>', body, '--dry-run', port=port)

    # Then recipients, subject, threading and Proton's stripping are shown, and nothing is appended
    assert r.returncode == 0, r.stderr
    for line in ('draft to: barbara@example.org', 'subject : Re: Réunion', 'threaded: <a@x>', 'In-Reply-To'): assert line in r.stdout
    assert not any(b'APPEND' in l for l in box.seen)


def test_draft_to_appends_a_reply_threaded_to_the_message_when_not_a_dry_run(run_m2c, fake_imap, body):
    # Given the message to answer
    port, box = fake_imap(**_account('Drafts', {4: [set(), _mail('a@x')]}))

    # When we draft the reply
    r = run_m2c('draft-to', '--message-id', 'a@x', body, port=port)

    # Then Drafts holds a reply whose In-Reply-To names the message, and the draft UID is printed
    assert r.returncode == 0, r.stderr
    (_, raw), = box.folders['Drafts'].values()
    assert b'In-Reply-To: <a@x>' in raw and 'draft uid: 1' in r.stdout
