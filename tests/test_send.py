from email.message import EmailMessage

import pytest

import mail2context.send
from mail2context.send import (SEND_ALLOWLIST, SendRefused, SmtpAccount, check_recipients,
                               load_smtp, send_message)

OWNER_PROTON, OWNER_GMAIL = 'dj@ai4hu.org', 'daniel.jelinko@gmail.com'


def make_message(to: str = '', cc: str = '', bcc: str = '') -> EmailMessage:
    "A message addressed however the test needs; body is irrelevant to the guard."
    m = EmailMessage()
    m['Subject'] = 'S'
    if to:  m['To'] = to
    if cc:  m['Cc'] = cc
    if bcc: m['Bcc'] = bcc
    m.set_content('body')
    return m


def test_check_recipients_returns_every_address_when_all_are_allowed():
    # Given a message to both owner-controlled addresses
    m = make_message(to=OWNER_PROTON, cc=OWNER_GMAIL)

    # When we check it
    allowed = check_recipients(m)

    # Then both are returned so the caller can print them before sending
    assert sorted(allowed) == sorted([OWNER_PROTON, OWNER_GMAIL])


def test_check_recipients_refuses_an_address_outside_the_allowlist():
    # Given a message to a third party
    m = make_message(to='barbara.rega@agroparistech.fr')

    # When we check it
    # Then it is refused
    with pytest.raises(SendRefused):
        check_recipients(m)


def test_check_recipients_refuses_a_mixed_list_where_only_one_address_is_allowed():
    # Given a message to an allowed address AND a third party — the dangerous case, because the
    # allowed recipient makes it look legitimate
    m = make_message(to=f'{OWNER_PROTON}, barbara.rega@agroparistech.fr')

    # When we check it
    # Then the whole message is refused, not just the offending recipient
    with pytest.raises(SendRefused):
        check_recipients(m)


def test_check_recipients_refuses_an_outside_address_hidden_in_bcc():
    # Given an allowed To with a third party concealed in Bcc
    m = make_message(to=OWNER_GMAIL, bcc='someone@example.com')

    # When we check it
    # Then Bcc is policed like every other recipient header
    with pytest.raises(SendRefused):
        check_recipients(m)


def test_check_recipients_refuses_a_lookalike_that_merely_starts_with_an_allowed_address():
    # Given an address whose prefix matches an allowed one but whose domain does not
    m = make_message(to='dj@ai4hu.org.attacker.example')

    # When we check it
    # Then matching is exact, never a substring or prefix
    with pytest.raises(SendRefused):
        check_recipients(m)


def test_check_recipients_allows_an_allowed_address_written_with_a_display_name():
    # Given the owner's address wrapped in a display name, as every mail client writes it
    m = make_message(to=f'"Dani JELINKO" <{OWNER_PROTON}>')

    # When we check it
    # Then the display name is not mistaken for part of the address
    assert check_recipients(m) == [OWNER_PROTON]


def test_check_recipients_allows_an_allowed_address_in_a_different_case():
    # Given the same mailbox typed in upper case
    m = make_message(to=OWNER_PROTON.upper())

    # When we check it
    # Then it is recognised — case is not a different mailbox, so this is not a widening
    assert check_recipients(m) == [OWNER_PROTON.upper()]


def test_check_recipients_refuses_a_message_addressed_to_nobody():
    # Given a message carrying no recipient header at all
    m = make_message()

    # When we check it
    # Then it is refused rather than passing vacuously
    with pytest.raises(SendRefused):
        check_recipients(m)


def test_send_allowlist_holds_exactly_the_two_addresses_d011_authorised():
    # Given the allowlist as shipped
    # When we read it
    # Then it names only the owner's two mailboxes — widening it is an owner decision, not a code
    # edit, so this test is the tripwire for a silent change
    assert set(SEND_ALLOWLIST) == {OWNER_PROTON, OWNER_GMAIL}


def test_load_smtp_reads_host_port_and_credentials_from_the_account_prefix(monkeypatch):
    # Given the four env vars an account's SMTP submission needs
    for k, v in {'GMAIL_SMTP_HOST': 'smtp.example.org', 'GMAIL_SMTP_PORT': '587',
                 'GMAIL_USER': 'u@example.org', 'GMAIL_PASS': 'app-password'}.items():
        monkeypatch.setenv(k, v)

    # When we load the gmail SMTP account
    acct = load_smtp('gmail')

    # Then host, port, user and password all come from the <NAME>_ prefix, port as an int
    assert (acct.host, acct.port, acct.user, acct.password) == (
        'smtp.example.org', 587, 'u@example.org', 'app-password')


@pytest.fixture
def smtp_sessions(monkeypatch):
    "Factory-free boundary stub: replaces smtplib.SMTP and yields the sessions it opened."
    sessions = []

    class _Recorder:
        def __init__(self, host, port, timeout=None):
            self.host, self.port, self.sent, self.logged_in_as = host, port, [], None
            sessions.append(self)
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def starttls(self, context=None): self.tls_context = context
        def login(self, user, password): self.logged_in_as = user
        def send_message(self, msg, from_addr=None, to_addrs=None):
            self.sent.append((from_addr, list(to_addrs or []), msg))

    monkeypatch.setattr(mail2context.send.smtplib, 'SMTP', _Recorder)
    return sessions


def an_account() -> SmtpAccount:
    "An SMTP account the recorder can accept; no connection is ever made to it."
    return SmtpAccount('smtp.example.org', 587, OWNER_GMAIL, 'app-password')


def test_send_message_opens_no_connection_when_a_recipient_is_outside_the_allowlist(smtp_sessions):
    # Given a message to a third party
    m = make_message(to='barbara.rega@agroparistech.fr')

    # When we try to send it
    with pytest.raises(SendRefused):
        send_message(an_account(), m)

    # Then the guard ran first — nothing ever reached the network
    assert smtp_sessions == []


def test_send_message_hands_the_envelope_exactly_the_addresses_the_guard_returned(smtp_sessions):
    # Given a message to both allowlisted mailboxes, one in To and one in Cc
    m = make_message(to=OWNER_PROTON, cc=OWNER_GMAIL)

    # When we send it
    returned = send_message(an_account(), m)

    # Then the envelope recipients are the guard's list, not re-derived from the headers
    (from_addr, to_addrs, _), = smtp_sessions[0].sent
    assert (from_addr, sorted(to_addrs)) == (OWNER_GMAIL, sorted(returned))
