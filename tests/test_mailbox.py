import socket, threading
from collections.abc import Callable

import pytest

from mail2context.mailbox import Account, check_account, connect, load_account, search_messages


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
