import pytest

from mail2context.mailbox import Account, check_account, connect, load_account


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
