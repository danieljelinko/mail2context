import pytest

from mail2context.search import build_search_criteria, parse_flags


def test_build_search_criteria_returns_all_when_no_filter_is_given():
    # Given no filters at all
    # When we build IMAP search criteria
    crit = build_search_criteria()

    # Then everything matches
    assert crit == ['ALL']


def test_build_search_criteria_maps_unread_to_the_unseen_flag():
    # Given a request for unread mail
    # When we build criteria
    crit = build_search_criteria(unread=True)

    # Then it uses IMAP's UNSEEN, not "UNREAD"
    assert crit == ['UNSEEN']


def test_build_search_criteria_reformats_iso_dates_to_imap_form():
    # Given an ISO date, which IMAP does not accept
    # When we build criteria
    crit = build_search_criteria(since='2026-06-01')

    # Then it is rewritten as DD-Mon-YYYY
    assert crit == ['SINCE', '01-Jun-2026']


def test_build_search_criteria_combines_every_filter_given():
    # Given a sender, a subject and a date bound
    # When we build criteria
    crit = build_search_criteria(frm='barbara', subject='septembre', before='2026-08-01')

    # Then all three appear as IMAP key/value pairs
    assert crit == ['FROM', 'barbara', 'SUBJECT', 'septembre', 'BEFORE', '01-Aug-2026']


def test_build_search_criteria_rejects_a_date_it_cannot_parse():
    # Given a malformed date
    # When we build criteria
    # Then it fails loudly rather than silently searching the whole mailbox
    with pytest.raises(ValueError):
        build_search_criteria(since='last tuesday')


def test_parse_flags_extracts_the_flag_list_from_a_fetch_response():
    # Given an IMAP FETCH response header carrying flags
    line = b'1 (UID 42 FLAGS (\\Seen \\Answered) BODY[] {1234}'

    # When we parse its flags
    flags = parse_flags(line)

    # Then both flags come back
    assert flags == {'\\Seen', '\\Answered'}


def test_parse_flags_returns_empty_when_the_response_has_no_flags():
    # Given a response with no FLAGS section
    # When we parse it
    # Then nothing is reported, rather than raising
    assert parse_flags(b'1 (UID 42 BODY[] {1234}') == set()


def test_flags_of_reads_back_what_annotate_flags_recorded():
    # Given a message annotated with the flags IMAP reported for it
    from email.message import EmailMessage

    from mail2context.search import annotate_flags, flags_of
    m = EmailMessage()
    annotate_flags(m, {'\\Seen', '\\Answered'})

    # When we read its flags back
    # Then both survive the round trip
    assert flags_of(m) == {'\\Seen', '\\Answered'}


def test_flags_of_returns_empty_for_a_message_that_was_never_annotated():
    # Given a message fetched without flags
    from email.message import EmailMessage

    from mail2context.search import flags_of

    # When we read its flags
    # Then nothing is claimed about it
    assert flags_of(EmailMessage()) == set()


def test_annotate_flags_replaces_rather_than_appends_on_refetch():
    # Given a message annotated twice, as happens when it is refetched
    from email.message import EmailMessage

    from mail2context.search import annotate_flags, flags_of
    m = EmailMessage()
    annotate_flags(m, {'\\Seen'})
    annotate_flags(m, {'\\Seen', '\\Flagged'})

    # When we read its flags
    # Then the newest annotation wins, with no duplicate header left behind
    assert flags_of(m) == {'\\Seen', '\\Flagged'}


def test_build_search_criteria_quotes_a_multi_word_value():
    # Given a phrase — imaplib quotes nothing, and a bare space ends the command
    crit = build_search_criteria(subject='DEUXIEME ETAGE', frm='adrien')

    # Then the phrase is quoted and the single word is not
    assert crit == ['FROM', 'adrien', 'SUBJECT', '"DEUXIEME ETAGE"']


def test_build_search_criteria_escapes_quotes_and_backslashes_inside_a_quoted_value():
    # Given a value containing the quoted-string specials
    crit = build_search_criteria(text='say "hi" \\ there')

    # Then they are escaped so the server reads one string
    assert crit == ['TEXT', '"say \\"hi\\" \\\\ there"']


def test_build_search_criteria_leaves_a_non_ascii_value_raw_for_the_transport():
    # Given an accented value — a quoted string may only carry 7-bit; the transport sends it as a literal
    crit = build_search_criteria(subject='RUE DE SÉLESTAT')

    # Then it is passed through untouched, unquoted
    assert crit == ['SUBJECT', 'RUE DE SÉLESTAT']
