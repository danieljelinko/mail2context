import socket, threading
from collections.abc import Callable

import pytest

from mail2context.mailbox import (Account, check_account, connect, fetch_headers, find_sent_folder, list_message_dates, load_account,
                                  read_folder_state, search_messages)
from mail2context.search import flags_of


def _closed_port_account() -> Account:
    "An account pointed at a port nothing listens on — a Bridge that is down."
    return Account('proton', '127.0.0.1', 1, 'dj@ai4hu.org', 'x', tls='starttls')


def test_check_account_reports_down_when_nothing_is_listening():
    # Given an account whose IMAP server is not running
    acct = _closed_port_account()

    # When we health-check it
    ok, detail = check_account(acct)

    # Then it reports down, with the reason rather than an exception
    assert ok is False
    assert detail


def test_check_account_reports_down_when_an_unrelated_service_holds_a_similar_port():
    # Given a listening socket that is not an IMAP server — the 11434-vs-1143 confusion
    import socket, threading
    srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept(), daemon=True).start()

    # When we health-check an account pointed at it
    ok, _ = check_account(Account('proton', '127.0.0.1', port, 'dj@ai4hu.org', 'x', tls='starttls'))

    # Then a listening port alone does not count as up
    assert ok is False
    srv.close()


def test_load_account_defaults_tls_to_starttls_on_loopback_and_implicit_tls_elsewhere(monkeypatch):
    # Given the two accounts as .env has always described them, with no TLS variable
    for k, v in {'PROTON_IMAP_HOST': '127.0.0.1', 'PROTON_IMAP_PORT': '1143', 'PROTON_USER': 'u', 'PROTON_PASS': 'p',
                 'GMAIL_IMAP_HOST': 'imap.gmail.com', 'GMAIL_IMAP_PORT': '993', 'GMAIL_USER': 'g', 'GMAIL_PASS': 'p'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv('PROTON_IMAP_TLS', raising=False); monkeypatch.delenv('GMAIL_IMAP_TLS', raising=False)

    # When loaded
    # Then Bridge gets STARTTLS and Gmail implicit TLS, exactly as before the option existed
    assert load_account('proton').tls == 'starttls'
    assert load_account('gmail').tls == 'tls'


def test_load_account_reads_tls_none_for_the_guard_proxy(monkeypatch):
    # Given .env pointing the account at the guard's plaintext loopback listener
    for k, v in {'PROTON_IMAP_HOST': '127.0.0.1', 'PROTON_IMAP_PORT': '2143', 'PROTON_IMAP_TLS': 'none',
                 'PROTON_USER': 'u', 'PROTON_PASS': 'token'}.items():
        monkeypatch.setenv(k, v)

    # When loaded
    acct = load_account('proton')

    # Then the connection will be plaintext on that port
    assert (acct.port, acct.tls) == (2143, 'none')


def test_load_account_rejects_an_unknown_tls_mode(monkeypatch):
    # Given a typo in the TLS variable
    for k, v in {'PROTON_IMAP_HOST': '127.0.0.1', 'PROTON_IMAP_PORT': '2143', 'PROTON_IMAP_TLS': 'ssl',
                 'PROTON_USER': 'u', 'PROTON_PASS': 'token'}.items():
        monkeypatch.setenv(k, v)

    # When loaded
    # Then it fails at load time naming the variable, not at the first connection
    with pytest.raises(SystemExit, match='PROTON_IMAP_TLS'):
        load_account('proton')


def test_connect_logs_in_over_plaintext_when_tls_is_none():
    # Given a plaintext IMAP server that accepts one LOGIN — what the guard proxy looks like to us
    import socket, threading
    seen = []
    srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)
    def serve():
        c, _ = srv.accept(); c.sendall(b'* OK ready\r\n')
        f = c.makefile('rb')
        for line in f:
            seen.append(line); tag = line.split(b' ', 1)[0]
            verb = line.split(b' ')[1].upper().strip()
            if verb == b'CAPABILITY': c.sendall(b'* CAPABILITY IMAP4rev1\r\n' + tag + b' OK done\r\n')
            elif verb == b'LOGIN': c.sendall(tag + b' OK done\r\n')
            elif verb == b'LOGOUT': c.sendall(b'* BYE\r\n' + tag + b' OK done\r\n'); break
            else: c.sendall(tag + b' OK done\r\n')
        c.close()
    threading.Thread(target=serve, daemon=True).start()

    # When we connect with tls none
    M = connect(Account('proton', '127.0.0.1', srv.getsockname()[1], 'dj@ai4hu.org', 'token', tls='none'), timeout=5)
    M.logout()

    # Then the LOGIN went over the plain socket, with no STARTTLS attempted
    assert any(b' LOGIN ' in l for l in seen) and not any(b'STARTTLS' in l for l in seen)
    srv.close()


@pytest.fixture
def plain_imap(request) -> Callable[[], tuple[int, list[bytes]]]:
    "Factory: a plaintext IMAP server that OKs everything, honours literals, and records raw command lines."
    servers = []
    def _start() -> tuple[int, list[bytes]]:
        seen: list[bytes] = []
        srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1); servers.append(srv)
        def serve():
            c, _ = srv.accept(); c.sendall(b'* OK ready\r\n'); f = c.makefile('rb')
            for line in f:
                seen.append(line); tag, verb = line.split(b' ', 2)[:2]; verb = verb.upper().strip()
                if line.rstrip().endswith(b'}'):                       # literal follows: ask for it, record it
                    n = int(line.rstrip()[line.rstrip().rindex(b'{') + 1:-1]); c.sendall(b'+ go\r\n')
                    seen.append(f.read(n)); f.readline()
                if verb == b'CAPABILITY': c.sendall(b'* CAPABILITY IMAP4rev1\r\n' + tag + b' OK done\r\n')
                elif verb == b'UID' and b'SEARCH' in line.upper(): c.sendall(b'* SEARCH\r\n' + tag + b' OK done\r\n')
                elif verb == b'LOGOUT': c.sendall(b'* BYE\r\n' + tag + b' OK done\r\n'); break
                else: c.sendall(tag + b' OK done\r\n')
            c.close()
        threading.Thread(target=serve, daemon=True).start()
        return srv.getsockname()[1], seen
    yield _start
    for s in servers: s.close()


def _search_lines(seen: list[bytes]) -> list[bytes]:
    "The raw UID SEARCH command line(s) and any literal bytes that followed."
    out = []
    for i, l in enumerate(seen):
        if b'UID SEARCH' in l.upper(): out.append(l); out.extend(seen[i+1:i+2] if l.rstrip().endswith(b'}') else [])
    return out


def test_search_messages_sends_ascii_criteria_as_one_plain_command(plain_imap):
    # Given a plain server and quoted ASCII criteria
    port, seen = plain_imap()
    M = connect(Account('proton', '127.0.0.1', port, 'u', 'x', tls='none'), timeout=5)

    # When we search
    search_messages(M, 'INBOX', ['FROM', 'adrien', 'SUBJECT', '"DEUXIEME ETAGE"'], 10)

    # Then exactly one SEARCH went out, with no CHARSET and the phrase still quoted
    lines = _search_lines(seen)
    assert len(lines) == 1 and lines[0].endswith(b'UID SEARCH FROM adrien SUBJECT "DEUXIEME ETAGE"\r\n')
    M.logout()


def test_search_messages_sends_a_non_ascii_value_as_a_utf8_literal_last(plain_imap):
    # Given an accented value in the middle of the criteria — Gmail refuses it in a quoted string
    port, seen = plain_imap()
    M = connect(Account('gmail', '127.0.0.1', port, 'u', 'x', tls='none'), timeout=5)

    # When we search
    search_messages(M, 'INBOX', ['SUBJECT', 'RUE DE SÉLESTAT', 'FROM', 'adrien'], 10)

    # Then the command declares UTF-8, moves that key last, and sends the value as a literal
    line, literal = _search_lines(seen)
    assert line.endswith(b'UID SEARCH CHARSET UTF-8 FROM adrien SUBJECT {16}\r\n')
    assert literal == 'RUE DE SÉLESTAT'.encode()
    M.logout()


def test_search_messages_refuses_two_non_ascii_values(plain_imap):
    # Given two accented values — imaplib carries one literal per command
    port, _ = plain_imap()
    M = connect(Account('gmail', '127.0.0.1', port, 'u', 'x', tls='none'), timeout=5)

    # When we search
    # Then it is refused with an explanation rather than sent malformed
    with pytest.raises(SystemExit, match='one'):
        search_messages(M, 'INBOX', ['SUBJECT', 'Sélestat', 'TEXT', 'Adrién'], 10)
    M.logout()


class _ScriptedImap:
    "An IMAP connection that answers from a script and records what it was asked. The server is the external boundary."
    def __init__(self, folders: list[bytes], uids: bytes, fetched: list[bytes]): self.folders, self.uids, self.fetched, self.asked = folders, uids, fetched, []
    def list(self): return 'OK', self.folders
    def select(self, folder, readonly=False): self.asked.append(('select', folder, readonly)); return 'OK', [b'3']
    def uid(self, command, *args):
        self.asked.append((command, *args))
        return ('OK', [self.uids]) if command == 'search' else ('OK', self.fetched)


def test_find_sent_folder_returns_the_mailbox_flagged_sent_when_its_name_holds_a_space():
    # Given a server whose sent mailbox has a localised, two-word name
    M = _ScriptedImap([b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"', b'(\\Drafts) "/" "[Gmail]/Drafts"'], b'', [])

    # When we ask for the sent folder
    folder = find_sent_folder(M)

    # Then it is the flagged one, whole
    assert folder == '[Gmail]/Sent Mail'


def test_list_message_dates_asks_for_arrival_times_only_when_reading_a_folder():
    # Given a folder with two messages since the date
    M = _ScriptedImap([], b'7 9', [b'1 (UID 7 INTERNALDATE "05-Oct-2026 09:15:02 +0200")', b'2 (UID 9 INTERNALDATE "06-Oct-2026 18:40:00 +0000")'])

    # When we list the dates since 5 October
    dates = list_message_dates(M, 'Sent', '2026-10-05')

    # Then both times come back with their zone, the folder was opened read-only, and nothing but INTERNALDATE was fetched
    assert [d.isoformat() for d in dates] == ['2026-10-05T09:15:02+02:00', '2026-10-06T18:40:00+00:00']
    assert M.asked == [('select', 'Sent', True), ('search', None, 'SINCE', '05-Oct-2026'), ('fetch', b'7,9', '(INTERNALDATE)')]


def _headers(mid: str) -> bytes: return f'Message-ID: <{mid}>\r\nFrom: a@example.org\r\n\r\n'.encode()


def test_read_folder_state_returns_uidvalidity_and_uidnext_when_asked_for_a_folder_with_a_space(fake_imap):
    # Given a mailbox whose name needs quoting
    port, box = fake_imap(folders={'All Mail': {4: [set(), _headers('a@x')]}}, special={}, uidvalidity=99)
    M = connect(Account('p', '127.0.0.1', port, 'u', 'x', tls='none'))

    # When we read its state
    state = read_folder_state(M, 'All Mail')

    # Then both numbers come back and the folder was never selected
    assert state == (99, 5)
    assert not any(b'SELECT' in c or b'EXAMINE' in c for c in box.seen)


def test_fetch_headers_returns_only_uids_past_the_cursor_when_the_server_echoes_the_last_message(fake_imap):
    # Given a folder whose newest UID is the cursor itself: `UID 8:*` still matches it
    port, _ = fake_imap(folders={'INBOX': {3: [set(), _headers('a@x')], 7: [{'\\Draft'}, _headers('b@x')]}}, special={})
    M = connect(Account('p', '127.0.0.1', port, 'u', 'x', tls='none'))

    # When we fetch past that cursor, then past an older one
    at_end, past_3 = fetch_headers(M, 'INBOX', 7, '2025-01-01', ['MESSAGE-ID']), fetch_headers(M, 'INBOX', 3, '2025-01-01', ['MESSAGE-ID'])

    # Then the cursor's own message is not returned again, and flags and uid travel with the headers
    assert at_end == []
    assert [(u, m['Message-ID'], flags_of(m)) for u, m in past_3] == [(7, '<b@x>', {'\\Draft'})]


def test_fetch_headers_selects_read_only_and_peeks_only_the_named_fields_when_reading(fake_imap):
    # Given a folder with one message
    port, box = fake_imap(folders={'INBOX': {1: [set(), _headers('a@x')]}}, special={})
    M = connect(Account('p', '127.0.0.1', port, 'u', 'x', tls='none'))

    # When we fetch its headers since a date
    fetch_headers(M, 'INBOX', 0, '2025-01-01', ['MESSAGE-ID', 'FROM'])
    sent = b''.join(box.seen)

    # Then the folder is opened with EXAMINE, the date bounds the search, and no body is asked for
    assert b'EXAMINE INBOX' in sent and b' SELECT ' not in sent
    assert b'UID 1:* SINCE 01-Jan-2025' in sent
    assert b'BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM)]' in sent
    assert b'BODY[' not in sent and b'BODY.PEEK[]' not in sent
