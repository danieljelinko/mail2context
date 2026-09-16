import time
from email.message import EmailMessage
from email.utils import formatdate

import pytest

from mail2context.roundtrip import check_reply_chain, check_thread

BASE = time.mktime((2026, 9, 16, 10, 0, 0, 0, 0, -1))


@pytest.fixture
def make_chain():
    "Factory: `n` messages linked as a reply chain, oldest first, an hour apart."
    def _build(n: int, subject: str = 'm2c roundtrip zz9') -> list[EmailMessage]:
        msgs = []
        for i in range(n):
            m = EmailMessage()
            m['Message-ID'] = f'<step{i}@example.org>'
            m['Subject'] = subject if i == 0 else f'Re: {subject}'
            m['Date'] = formatdate(BASE + i * 3600)
            if i:
                m['In-Reply-To'] = f'<step{i - 1}@example.org>'
                m['References'] = ' '.join(f'<step{j}@example.org>' for j in range(i))
            m.set_content(f'step {i}')
            msgs.append(m)
        return msgs
    return _build


def ids_of(msgs: list[EmailMessage]) -> list[str]:
    "The Message-IDs of `msgs`, in the order given."
    return [m['Message-ID'] for m in msgs]


def test_check_thread_reports_no_problems_when_six_linked_messages_rebuild_as_one_thread(make_chain):
    # Given six messages forming one proper reply chain
    msgs = make_chain(6)

    # When we check them against the order they were sent in
    problems = check_thread(msgs, ids_of(msgs))

    # Then nothing is wrong
    assert problems == []


def test_check_thread_reports_a_split_when_the_LAST_reply_loses_its_threading_headers(make_chain):
    # Given six messages whose final reply has had its chain stripped — nothing later can name it
    msgs = make_chain(6)
    del msgs[5]['In-Reply-To'], msgs[5]['References']

    # When we check them against the order they were sent in
    problems = check_thread(msgs, ids_of(msgs))

    # Then the checker reports the split rather than passing
    assert problems and 'rebuilt 2 threads' in problems[0]


def test_check_thread_finds_one_thread_when_a_MIDDLE_reply_is_stripped_but_later_ones_name_it(make_chain):
    # Given six messages where the fourth lost its chain, while the fifth and sixth still carry
    # References naming every earlier message
    msgs = make_chain(6)
    del msgs[3]['In-Reply-To'], msgs[3]['References']

    # When we check them
    problems = check_thread(msgs, ids_of(msgs))

    # Then the thread is still whole — a later reply's References heals the gap, so a broken
    # middle message is NOT observable; only an orphaned last message splits a thread
    assert problems == []


def test_check_thread_reports_send_order_intact_when_the_messages_are_fetched_out_of_order(make_chain):
    # Given the six messages shuffled, as a mailbox fetch may well return them
    msgs = make_chain(6)
    fetched = [msgs[3], msgs[0], msgs[5], msgs[1], msgs[4], msgs[2]]

    # When we check the shuffled list against the send order
    problems = check_thread(fetched, ids_of(msgs))

    # Then order is recovered from Date, not from fetch order
    assert problems == []


def test_check_thread_reports_the_shortfall_when_a_message_never_arrived(make_chain):
    # Given only five of the six messages, the last one still missing
    msgs = make_chain(6)

    # When we check the five against all six expected ids
    problems = check_thread(msgs[:5], ids_of(msgs))

    # Then the shortfall is named rather than silently accepted
    assert problems == ['thread holds 5 messages, expected 6']


def test_check_reply_chain_reports_no_problems_when_every_reply_names_its_parent(make_chain):
    # Given six messages whose In-Reply-To and References arrived intact
    msgs = make_chain(6)

    # When we check the delivered chain
    problems = check_reply_chain(msgs, ids_of(msgs))

    # Then nothing is wrong
    assert problems == []


def test_check_reply_chain_names_the_step_whose_in_reply_to_was_stripped_in_transit(make_chain):
    # Given a delivered chain where step 4 arrived with no In-Reply-To — the shape D-009 records
    # for Proton draft APPEND, here asked of a real send
    msgs = make_chain(6)
    del msgs[3]['In-Reply-To']

    # When we check the delivered chain
    problems = check_reply_chain(msgs, ids_of(msgs))

    # Then that step is named, with what it should have carried
    assert problems == ['step 4: In-Reply-To is ABSENT, expected <step2@example.org>']


def test_check_reply_chain_names_the_ancestors_a_truncated_references_header_dropped(make_chain):
    # Given a delivered chain whose last reply kept only its immediate parent in References
    msgs = make_chain(6)
    msgs[5].replace_header('References', '<step4@example.org>')

    # When we check the delivered chain
    problems = check_reply_chain(msgs, ids_of(msgs))

    # Then the dropped ancestors are named rather than the header passing as present
    assert len(problems) == 1 and 'References is missing' in problems[0]
