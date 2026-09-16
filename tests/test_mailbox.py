from mail2context.mailbox import Account, check_account


def _closed_port_account() -> Account:
    "An account pointed at a port nothing listens on — a Bridge that is down."
    return Account('proton', '127.0.0.1', 1, 'dj@ai4hu.org', 'x', starttls=True)


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
    ok, _ = check_account(Account('proton', '127.0.0.1', port, 'dj@ai4hu.org', 'x', starttls=True))

    # Then a listening port alone does not count as up
    assert ok is False
    srv.close()
